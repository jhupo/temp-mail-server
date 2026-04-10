from contextlib import asynccontextmanager
import threading

import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.cert_manager import apply_cert_update, cert_status_payload, run_certbot_script
from app.compat import fail, ok
from app.crud import (
    add_account_for_user,
    add_reg_key,
    add_role,
    add_user_admin,
    all_accounts_for_user,
    batch_delete_all_emails,
    authenticate_user,
    cleanup_expired,
    create_mailbox,
    create_sent_email,
    create_user_with_mailbox,
    delete_reg_keys,
    delete_role_record,
    delete_account,
    delete_all_emails,
    delete_messages,
    delete_user_session,
    get_primary_mailbox,
    get_analysis_snapshot,
    get_app_settings,
    get_mailbox_by_token,
    get_mailboxes_by_user,
    get_message_by_id,
    get_message_by_id_admin,
    get_messages,
    get_messages_admin,
    get_default_role,
    get_user_by_session_token,
    ensure_default_admin,
    list_all_emails,
    list_emails_for_account,
    list_latest_all_emails,
    list_latest_emails,
    list_reg_keys,
    list_users_admin,
    mark_messages_read,
    rename_account,
    reg_key_history_list,
    role_list,
    role_select_use,
    PERM_TREE,
    serialize_attachment_rows,
    set_default_role,
    set_account_all_receive,
    set_account_as_top,
    set_user_password,
    set_user_status,
    set_user_type,
    set_star_state,
    reset_user_send_count,
    update_role,
    update_app_settings,
    clear_unused_reg_keys,
    configured_domains,
    configured_primary_domain,
    delete_users_admin,
)
from app.database import SessionLocal, init_db
from app.mailer import send_via_smtp
from app.models import Mailbox
from app.rate_limit import limiter
from app.security import hash_password
from app.storage import resolve_object_path, save_base64_object
from app.time_utils import ensure_utc, utcnow
from app.update_manager import apply_update, update_status
from app.utils import is_allowed_domain, is_valid_local_part, normalize_address, split_address


_cleanup_stop_event = threading.Event()
_cleanup_thread: threading.Thread | None = None
_cert_stop_event = threading.Event()
_cert_thread: threading.Thread | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_admin_auth(admin_auth: str | None) -> None:
    if not settings.api_master_key:
        raise HTTPException(status_code=503, detail="admin API disabled")
    if admin_auth != settings.api_master_key:
        raise HTTPException(status_code=401, detail="invalid admin auth")


def _require_mailbox_from_token(db: Session, token: str | None):
    if not token:
        raise HTTPException(status_code=401, detail="token required")
    mailbox = get_mailbox_by_token(db, token)
    if mailbox is None:
        raise HTTPException(status_code=403, detail="invalid token")
    return mailbox


def _serialize_message(message, *, address: str) -> dict:
    received_at = ensure_utc(message.received_at)
    return {
        "id": str(message.id),
        "mail_id": str(message.id),
        "address": address,
        "source": message.from_addr,
        "from": message.from_addr,
        "subject": message.subject,
        "text": message.text_body,
        "body": message.text_body,
        "html": message.html_body,
        "raw": message.raw_headers,
        "createdAt": received_at.isoformat() if received_at else None,
        "created_at": received_at.isoformat() if received_at else None,
    }


def _extract_token_header(authorization: str | None, x_user_token: str | None) -> str | None:
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    raw_auth = (authorization or "").strip()
    return bearer or raw_auth or (x_user_token or "").strip() or None


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _check_new_mailbox_rate_limit(request: Request) -> None:
    allowed, retry_after = limiter.check_new_mailbox(_client_ip(request))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def _require_login_user(db: Session, authorization: str | None):
    token = _extract_token_header(authorization, None)
    user = get_user_by_session_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid login token")
    return user, token


def _current_app_settings(db: Session) -> dict:
    current = get_app_settings(db)
    current["allowedDomains"] = configured_domains(current)
    current["domainList"] = [f"@{domain}" for domain in current["allowedDomains"]]
    return current


def _domain_allowed_from_settings(current: dict, domain: str) -> bool:
    normalized = domain.lower()
    for root in configured_domains(current):
        if normalized == root or normalized.endswith(f".{root}"):
            return True
    return False


def _require_domains_configured(current: dict):
    if not configured_domains(current):
        raise HTTPException(status_code=400, detail="no domains configured")


def _compat_email(message, mailbox_address: str, user_email: str) -> dict:
    received_at = ensure_utc(message.received_at)
    return {
        "emailId": message.id,
        "name": (message.from_addr or "").split("@", 1)[0] if message.direction == 0 else mailbox_address.split("@", 1)[0],
        "sendEmail": message.from_addr or "",
        "toEmail": mailbox_address,
        "userEmail": user_email,
        "subject": message.subject or "",
        "content": message.html_body or "",
        "text": message.text_body or "",
        "createTime": received_at.isoformat() if received_at else None,
        "recipient": message.recipient_json or f'[{{"address":"{mailbox_address}"}}]',
        "isStar": int(message.is_star),
        "unread": 0 if message.is_read else 1,
        "status": message.status,
        "message": None,
        "type": message.direction,
        "isDel": 0,
        "raw": message.raw_headers or "",
        "attList": serialize_attachment_rows(getattr(message, "attachments", [])),
    }


def _compat_account(mailbox) -> dict:
    return {
        "accountId": mailbox.id,
        "email": mailbox.address,
        "name": mailbox.name or mailbox.address.split("@", 1)[0],
        "allReceive": mailbox.all_receive,
        "sort": mailbox.sort,
    }


def _compat_user_payload(db: Session, user) -> dict:
    account = get_primary_mailbox(db, user.id)
    if account is None:
        raise HTTPException(status_code=400, detail="user has no account")
    perm_keys = [
        "account:query",
        "account:add",
        "account:delete",
        "email:delete",
        "email:send",
        "star:query",
        "my:delete",
        "all-email:query",
        "analysis:query",
        "setting:query",
    ]
    return {
        "userId": user.id,
        "email": user.email,
        "username": user.username,
        "name": user.name,
        "sendCount": user.send_count,
        "permKeys": perm_keys,
        "account": _compat_account(account),
        "role": {
            "name": "Admin" if user.type == 0 else (next((role.name for role in role_list(db) if role.id == user.type), "User")),
            "accountCount": 0,
            "sendType": "ban",
            "sendCount": 0,
        },
        "type": user.type,
    }


def _send_email_with_config(app_settings: dict, payload: dict, user) -> int:
    smtp_host = (app_settings.get("smtpHost") or "").strip()
    smtp_port = int(app_settings.get("smtpPort") or 587)
    smtp_username = (app_settings.get("smtpUsername") or "").strip() or None
    smtp_password = app_settings.get("smtpPassword") or None
    smtp_use_tls = bool(app_settings.get("smtpUseTls", True))
    smtp_use_ssl = bool(app_settings.get("smtpUseSsl", False))
    smtp_from_email = (app_settings.get("smtpFromEmail") or payload.get("sendEmail") or user.email).strip()
    send_mode = app_settings.get("sendMode") or "record"

    if send_mode != "smtp":
        return 2
    if not smtp_host:
        raise ValueError("smtp not configured")

    send_via_smtp(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_tls=smtp_use_tls,
        smtp_use_ssl=smtp_use_ssl,
        from_email=smtp_from_email,
        to_emails=payload.get("receiveEmail") or [],
        subject=(payload.get("subject") or "").strip(),
        text_body=payload.get("text") or "",
        html_body=payload.get("content") or "",
        attachments=payload.get("attachments") or [],
    )
    return 2


def _cleanup_loop(stop_event: threading.Event) -> None:
    interval = max(settings.cleanup_interval_seconds, 1)
    while not stop_event.wait(interval):
        db = SessionLocal()
        try:
            cleanup_expired(db)
        finally:
            db.close()


def _cert_loop(stop_event: threading.Event) -> None:
    interval = max(settings.cert_renew_check_seconds, 300)
    while not stop_event.wait(interval):
        db = SessionLocal()
        try:
            current = get_app_settings(db)
            if current.get("certAutoRenew", 0) != 0:
                continue
            domain = (current.get("certDomain") or "").strip()
            email = (current.get("certEmail") or "").strip()
            if not domain or not email:
                continue
            result = run_certbot_script("renew", domain=domain, email=email)
            update_app_settings(db, apply_cert_update(current, result))
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _cleanup_thread, _cert_thread
    init_db()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_stop_event.clear()
        _cleanup_thread = threading.Thread(target=_cleanup_loop, args=(_cleanup_stop_event,), daemon=True)
        _cleanup_thread.start()
    if _cert_thread is None or not _cert_thread.is_alive():
        _cert_stop_event.clear()
        _cert_thread = threading.Thread(target=_cert_loop, args=(_cert_stop_event,), daemon=True)
        _cert_thread.start()
    try:
        yield
    finally:
        _cleanup_stop_event.set()
        _cert_stop_event.set()
        if _cleanup_thread is not None:
            _cleanup_thread.join(timeout=1)
            _cleanup_thread = None
        if _cert_thread is not None:
            _cert_thread.join(timeout=1)
            _cert_thread = None


app = FastAPI(title="Temp Mail Service", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True, "ts": utcnow().isoformat()}


@app.post("/admin/new_address")
def compat_admin_new_address(
    request: Request,
    payload: dict | None = Body(default=None),
    db: Session = Depends(get_db),
    admin_auth: str | None = Header(default=None, alias="x-admin-auth"),
):
    _require_admin_auth(admin_auth)
    _check_new_mailbox_rate_limit(request)
    app_settings = _current_app_settings(db)
    _require_domains_configured(app_settings)
    payload = payload or {}
    domain = (payload.get("domain") or configured_primary_domain(app_settings)).lower()
    local_part = payload.get("name")
    if payload.get("local_part"):
        local_part = payload.get("local_part")
    ttl_minutes = payload.get("ttl_minutes")
    if not _domain_allowed_from_settings(app_settings, domain):
        raise HTTPException(status_code=400, detail="domain not allowed")
    if local_part and not is_valid_local_part(local_part):
        raise HTTPException(status_code=400, detail="invalid local_part format")
    try:
        mailbox, token = create_mailbox(
            db,
            domain=domain,
            local_part=local_part,
            ttl_minutes=ttl_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "address": mailbox.address,
        "jwt": token,
        "token": token,
        "address_id": str(mailbox.id),
        "id": str(mailbox.id),
        "expires_at": mailbox.expires_at.isoformat(),
    }


@app.post("/inbox/create")
def compat_inbox_create(
    request: Request,
    db: Session = Depends(get_db),
):
    _check_new_mailbox_rate_limit(request)
    app_settings = _current_app_settings(db)
    _require_domains_configured(app_settings)
    mailbox, token = create_mailbox(
        db,
        domain=configured_primary_domain(app_settings),
        local_part=None,
        ttl_minutes=None,
    )
    return {
        "address": mailbox.address,
        "token": token,
        "expires_at": mailbox.expires_at.isoformat(),
    }


@app.get("/inbox")
def compat_inbox(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    mailbox = _require_mailbox_from_token(db, token)
    items = get_messages(db, mailbox.id, limit=50)
    emails = [
        {
            "from": item.from_addr,
            "subject": item.subject,
            "body": item.text_body,
            "html": item.html_body,
            "date": int(ensure_utc(item.received_at).timestamp()) if item.received_at else None,
            "id": str(item.id),
        }
        for item in items
    ]
    return {
        "address": mailbox.address,
        "emails": emails,
    }




@app.get("/admin/mails")
def compat_admin_mails(
    db: Session = Depends(get_db),
    admin_auth: str | None = Header(default=None, alias="x-admin-auth"),
    address: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    _require_admin_auth(admin_auth)
    rows = get_messages_admin(db, address=address, limit=limit, offset=offset)
    return {
        "results": [_serialize_message(message, address=mailbox.address) for mailbox, message in rows]
    }


@app.get("/admin/mails/{mail_id}")
def compat_admin_mail_detail(
    mail_id: int,
    db: Session = Depends(get_db),
    admin_auth: str | None = Header(default=None, alias="x-admin-auth"),
):
    _require_admin_auth(admin_auth)
    row = get_message_by_id_admin(db, mail_id)
    if row is None:
        raise HTTPException(status_code=404, detail="mail not found")
    mailbox, message = row
    return _serialize_message(message, address=mailbox.address)


@app.get("/api/mails")
def compat_user_mails_bearer(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    token = _extract_token_header(authorization, None)
    mailbox = _require_mailbox_from_token(db, token)
    items = get_messages(db, mailbox.id, limit=limit + offset)
    sliced = items[offset : offset + limit]
    return {"results": [_serialize_message(item, address=mailbox.address) for item in sliced]}


@app.get("/api/mails/{mail_id}")
def compat_user_mail_detail_bearer(
    mail_id: int,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    token = _extract_token_header(authorization, None)
    mailbox = _require_mailbox_from_token(db, token)
    message = get_message_by_id(db, mailbox.id, mail_id)
    if message is None:
        raise HTTPException(status_code=404, detail="mail not found")
    return _serialize_message(message, address=mailbox.address)


@app.get("/user_api/mails")
def compat_user_mails_token(
    db: Session = Depends(get_db),
    x_user_token: str | None = Header(default=None, alias="x-user-token"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    mailbox = _require_mailbox_from_token(db, x_user_token)
    items = get_messages(db, mailbox.id, limit=limit + offset)
    sliced = items[offset : offset + limit]
    return {"results": [_serialize_message(item, address=mailbox.address) for item in sliced]}


@app.get("/user_api/mails/{mail_id}")
def compat_user_mail_detail_token(
    mail_id: int,
    db: Session = Depends(get_db),
    x_user_token: str | None = Header(default=None, alias="x-user-token"),
):
    mailbox = _require_mailbox_from_token(db, x_user_token)
    message = get_message_by_id(db, mailbox.id, mail_id)
    if message is None:
        raise HTTPException(status_code=404, detail="mail not found")
    return _serialize_message(message, address=mailbox.address)


@app.post("/login")
def compat_login(payload: dict = Body(...), db: Session = Depends(get_db)):
    try:
        token = authenticate_user(db, payload.get("email", ""), payload.get("password", ""))
    except ValueError as exc:
        return fail(str(exc), 401)
    return ok({"token": token})


@app.post("/register")
def compat_register(payload: dict = Body(...), db: Session = Depends(get_db)):
    app_settings = _current_app_settings(db)
    _require_domains_configured(app_settings)
    if app_settings.get("register", 0) != 0:
        return fail("register disabled", 403)
    email = normalize_address(payload.get("email", ""))
    password = payload.get("password", "")
    if len(password) < 6:
        return fail("password too short", 400)
    try:
        local_part, domain = split_address(email)
    except ValueError:
        return fail("invalid email", 400)
    if not _domain_allowed_from_settings(app_settings, domain) or not is_valid_local_part(local_part):
        return fail("invalid email", 400)
    if len(local_part) < int(app_settings.get("minEmailPrefix", 1)):
        return fail("email prefix too short", 400)
    try:
        _user, _mailbox, token = create_user_with_mailbox(db, email=email, password=password)
    except ValueError as exc:
        return fail(str(exc), 400)
    return ok({"token": token, "regVerifyOpen": False})


@app.delete("/logout")
def compat_logout(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, token = _require_login_user(db, authorization)
    delete_user_session(db, token)
    return ok()


@app.get("/my/loginUserInfo")
def compat_login_user_info(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    payload = _compat_user_payload(db, user)
    payload["role"]["accountCount"] = len(get_mailboxes_by_user(db, user.id))
    return ok(payload)


@app.put("/my/resetPassword")
def compat_reset_password(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    password = payload.get("password", "")
    if len(password) < 6:
        return fail("password too short", 400)
    user.password_hash = hash_password(password)
    db.commit()
    return ok()


@app.delete("/my/delete")
def compat_delete_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, token = _require_login_user(db, authorization)
    delete_user_session(db, token)
    db.delete(user)
    db.commit()
    return ok()


@app.get("/setting/websiteConfig")
@app.get("/setting/query")
def compat_website_config(db: Session = Depends(get_db)):
    return ok(_current_app_settings(db))


@app.put("/setting/set")
def compat_setting_set(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    current = update_app_settings(db, payload)
    current["domainList"] = [f"@{domain}" for domain in settings.allowed_domains]
    return ok(current)


@app.put("/setting/setBackground")
def compat_setting_set_background(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    background = payload.get("background", "")
    stored = background
    if isinstance(background, str) and background.startswith("data:"):
        key, _size, _content_type = save_base64_object(background, filename="background.png", prefix="background")
        stored = f"/oss/{key}"
    current = update_app_settings(db, {"background": stored})
    return ok(current.get("background", ""))


@app.delete("/setting/deleteBackground")
def compat_setting_delete_background(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    update_app_settings(db, {"background": ""})
    return ok()


@app.post("/account/add")
def compat_account_add(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    app_settings = _current_app_settings(db)
    _require_domains_configured(app_settings)
    if app_settings.get("addEmail", 0) != 0 or app_settings.get("manyEmail", 0) != 0:
        return fail("add account disabled", 403)
    email = normalize_address(payload.get("email", ""))
    try:
        local_part, domain = split_address(email)
    except ValueError:
        return fail("invalid email", 400)
    if not _domain_allowed_from_settings(app_settings, domain) or not is_valid_local_part(local_part):
        return fail("invalid email", 400)
    if len(local_part) < int(app_settings.get("minEmailPrefix", 1)):
        return fail("email prefix too short", 400)
    try:
        mailbox = add_account_for_user(db, user=user, email=email)
    except ValueError as exc:
        return fail(str(exc), 400)
    return ok({**_compat_account(mailbox), "addVerifyOpen": False})


@app.get("/account/list")
def compat_account_list(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    return ok([_compat_account(mailbox) for mailbox in get_mailboxes_by_user(db, user.id)])


@app.put("/account/setName")
def compat_account_set_name(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    try:
        rename_account(db, user_id=user.id, account_id=int(payload.get("accountId", 0)), name=payload.get("name", ""))
    except LookupError:
        return fail("account not found", 404)
    if get_primary_mailbox(db, user.id).id == int(payload.get("accountId", 0)):
        user.name = payload.get("name", "")
        db.commit()
    return ok()


@app.delete("/account/delete")
def compat_account_delete(
    account_id: int = Query(..., alias="accountId"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    primary = get_primary_mailbox(db, user.id)
    if primary and primary.id == account_id:
        return fail("cannot delete primary account", 400)
    try:
        delete_account(db, user_id=user.id, account_id=account_id)
    except LookupError:
        return fail("account not found", 404)
    return ok()


@app.put("/account/setAllReceive")
def compat_account_set_all_receive(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    try:
        set_account_all_receive(db, user_id=user.id, account_id=int(payload.get("accountId", 0)))
    except LookupError:
        return fail("account not found", 404)
    return ok()


@app.put("/account/setAsTop")
def compat_account_set_as_top(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    try:
        set_account_as_top(db, user_id=user.id, account_id=int(payload.get("accountId", 0)))
    except LookupError:
        return fail("account not found", 404)
    return ok()


@app.get("/email/list")
def compat_email_list(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    account_id: int = Query(..., alias="accountId"),
    all_receive: int = Query(0, alias="allReceive"),
    email_id: int = Query(0, alias="emailId"),
    size: int = Query(50),
    type: int = Query(0),
):
    user, _token = _require_login_user(db, authorization)
    items, total = list_emails_for_account(
        db,
        user_id=user.id,
        account_id=account_id,
        all_receive=all_receive,
        cursor_id=email_id,
        size=size,
        filters={"type": type},
    )
    accounts = {mailbox.id: mailbox for mailbox in get_mailboxes_by_user(db, user.id)}
    result_items = [_compat_email(item, accounts[item.mailbox_id].address, user.email) for item in items]
    latest = result_items[0] if result_items else {"emailId": email_id}
    return ok({"list": result_items, "latestEmail": latest, "total": total})


@app.post("/email/send")
def compat_email_send(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    app_settings = _current_app_settings(db)
    if app_settings.get("send", 1) != 0:
        return fail("send disabled", 403)
    receive_emails = payload.get("receiveEmail") or []
    if not receive_emails:
        return fail("recipient required", 400)
    subject = (payload.get("subject") or "").strip()
    if not subject:
        return fail("subject required", 400)
    html_body = payload.get("content") or ""
    text_body = payload.get("text") or ""
    send_email = payload.get("sendEmail") or user.email
    try:
        status = _send_email_with_config(app_settings, payload, user)
        message = create_sent_email(
            db,
            user_id=user.id,
            account_id=int(payload.get("accountId", 0)),
            send_email=send_email,
            sender_name=payload.get("name") or user.name,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            receive_emails=receive_emails,
            attachments=payload.get("attachments") or [],
            status=status,
        )
    except LookupError:
        return fail("account not found", 404)
    except ValueError as exc:
        return fail(str(exc), 400)
    except Exception as exc:
        return fail(f"smtp send failed: {exc}", 502)
    primary = get_primary_mailbox(db, user.id)
    mailbox_address = primary.address if primary else send_email
    return ok([_compat_email(message, mailbox_address, user.email)])


@app.get("/email/latest")
def compat_email_latest(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    account_id: int = Query(..., alias="accountId"),
    all_receive: int = Query(0, alias="allReceive"),
    email_id: int = Query(0, alias="emailId"),
):
    user, _token = _require_login_user(db, authorization)
    items = list_latest_emails(
        db,
        user_id=user.id,
        account_id=account_id,
        all_receive=all_receive,
        email_id=email_id,
    )
    accounts = {mailbox.id: mailbox for mailbox in get_mailboxes_by_user(db, user.id)}
    return ok([_compat_email(item, accounts[item.mailbox_id].address, user.email) for item in items])


@app.delete("/email/delete")
def compat_email_delete(
    email_ids: str = Query("", alias="emailIds"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    ids = [int(item) for item in email_ids.split(",") if item.strip().isdigit()]
    delete_messages(db, user_id=user.id, email_ids=ids)
    return ok()


@app.put("/email/read")
def compat_email_read(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    email_ids = [int(item) for item in payload.get("emailIds", [])]
    mark_messages_read(db, user_id=user.id, email_ids=email_ids)
    return ok()


@app.post("/star/add")
def compat_star_add(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    try:
        set_star_state(db, user_id=user.id, email_id=int(payload.get("emailId", 0)), is_star=1)
    except LookupError:
        return fail("email not found", 404)
    return ok()


@app.delete("/star/cancel")
def compat_star_cancel(
    email_id: int = Query(..., alias="emailId"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user, _token = _require_login_user(db, authorization)
    try:
        set_star_state(db, user_id=user.id, email_id=email_id, is_star=0)
    except LookupError:
        return fail("email not found", 404)
    return ok()


@app.get("/star/list")
def compat_star_list(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    email_id: int = Query(0, alias="emailId"),
    size: int = Query(50),
):
    user, _token = _require_login_user(db, authorization)
    primary = get_primary_mailbox(db, user.id)
    if primary is None:
        return ok({"list": [], "latestEmail": {"emailId": email_id}, "total": 0})
    items, total = list_emails_for_account(
        db,
        user_id=user.id,
        account_id=primary.id,
        all_receive=1,
        cursor_id=email_id,
        size=size,
        starred_only=True,
    )
    accounts = {mailbox.id: mailbox for mailbox in get_mailboxes_by_user(db, user.id)}
    result_items = [_compat_email(item, accounts[item.mailbox_id].address, user.email) for item in items]
    latest = result_items[0] if result_items else {"emailId": email_id}
    return ok({"list": result_items, "latestEmail": latest, "total": total})


@app.get("/allEmail/list")
def compat_all_email_list(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    email_id: int = Query(0, alias="emailId"),
    size: int = Query(50),
    type: str = Query("receive"),
    user_email: str | None = Query(None, alias="userEmail"),
    account_email: str | None = Query(None, alias="accountEmail"),
    name: str | None = Query(None),
    subject: str | None = Query(None),
):
    _user, _token = _require_login_user(db, authorization)
    rows, total = list_all_emails(
        db,
        cursor_id=email_id,
        size=size,
        filters={
            "type": type,
            "userEmail": user_email,
            "accountEmail": account_email,
            "name": name,
            "subject": subject,
        },
    )
    result_items = [_compat_email(message, mailbox.address, mailbox.user.email if mailbox.user else "") for mailbox, message in rows]
    latest = result_items[0] if result_items else {"emailId": email_id}
    return ok({"list": result_items, "latestEmail": latest, "total": total})


@app.get("/allEmail/latest")
def compat_all_email_latest(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    email_id: int = Query(0, alias="emailId"),
):
    _user, _token = _require_login_user(db, authorization)
    rows = list_latest_all_emails(db, email_id=email_id)
    return ok([_compat_email(message, mailbox.address, mailbox.user.email if mailbox.user else "") for mailbox, message in rows])


@app.delete("/allEmail/delete")
def compat_all_email_delete(
    email_ids: str = Query("", alias="emailIds"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    ids = [int(item) for item in email_ids.split(",") if item.strip().isdigit()]
    delete_all_emails(db, email_ids=ids)
    return ok()


@app.delete("/allEmail/batchDelete")
def compat_all_email_batch_delete(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    send_name: str | None = Query(None, alias="sendName"),
    subject: str | None = Query(None),
    send_email: str | None = Query(None, alias="sendEmail"),
    to_email: str | None = Query(None, alias="toEmail"),
):
    _user, _token = _require_login_user(db, authorization)
    batch_delete_all_emails(
        db,
        filters={
            "name": send_name,
            "subject": subject,
            "sendEmail": send_email,
            "toEmail": to_email,
        },
    )
    return ok()


@app.get("/analysis/echarts")
def compat_analysis_echarts(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    return ok(get_analysis_snapshot(db))


@app.get("/cert/status")
def compat_cert_status(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    return ok(cert_status_payload(get_app_settings(db)))


@app.post("/cert/apply")
def compat_cert_apply(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    current = get_app_settings(db)
    domain = (current.get("certDomain") or "").strip()
    email = (current.get("certEmail") or "").strip()
    if not domain or not email:
        return fail("certDomain/certEmail required", 400)
    result = run_certbot_script("issue", domain=domain, email=email)
    updated = update_app_settings(db, apply_cert_update(current, result))
    return ok(cert_status_payload(updated))


@app.post("/cert/renew")
def compat_cert_renew(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    current = get_app_settings(db)
    domain = (current.get("certDomain") or "").strip()
    email = (current.get("certEmail") or "").strip()
    if not domain or not email:
        return fail("certDomain/certEmail required", 400)
    result = run_certbot_script("renew", domain=domain, email=email)
    updated = update_app_settings(db, apply_cert_update(current, result))
    return ok(cert_status_payload(updated))


@app.get("/system/update/status")
@app.post("/system/update/check")
def compat_update_status(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    status = update_status()
    update_app_settings(
        db,
        {
            "updateLastCheckAt": status.get("checkedAt", ""),
            "updateLastResult": status.get("message", ""),
        },
    )
    return ok(status)


@app.post("/system/update/apply")
def compat_update_apply(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    result = apply_update()
    update_app_settings(
        db,
        {
            "updateLastCheckAt": result.get("finishedAt", ""),
            "updateLastResult": result.get("message", ""),
        },
    )
    if not result.get("ok"):
        payload = fail(result.get("message", "update failed"), 500)
        payload["data"] = result
        return payload
    return ok(result)


@app.get("/role/permTree")
def compat_role_perm_tree(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    return ok(PERM_TREE)


@app.get("/role/list")
def compat_role_list(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    roles = role_list(db)
    return ok(
        [
            {
                "roleId": role.id,
                "name": role.name,
                "description": role.description,
                "sort": role.sort,
                "isDefault": role.is_default,
                "permIds": __import__("json").loads(role.perm_ids_json),
                "sendType": role.send_type,
                "sendCount": role.send_count,
                "accountCount": role.account_count,
                "banEmail": __import__("json").loads(role.ban_email_json),
                "availDomain": __import__("json").loads(role.avail_domain_json),
            }
            for role in roles
        ]
    )


@app.get("/role/selectUse")
def compat_role_select_use(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    return ok([{"roleId": role.id, "name": role.name} for role in role_select_use(db)])


@app.post("/role/add")
def compat_role_add(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    role = add_role(db, payload)
    return ok({"roleId": role.id})


@app.put("/role/set")
def compat_role_set(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        update_role(db, payload)
    except LookupError:
        return fail("role not found", 404)
    return ok()


@app.put("/role/setDefault")
def compat_role_set_default(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    set_default_role(db, int(payload.get("roleId", 0)))
    return ok()


@app.delete("/role/delete")
def compat_role_delete(
    role_id: int = Query(..., alias="roleId"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        delete_role_record(db, role_id)
    except LookupError:
        return fail("role not found", 404)
    return ok()


@app.get("/user/list")
def compat_user_list(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
    email: str | None = Query(None),
    num: int = Query(1),
    size: int = Query(15),
    status: int = Query(-1),
):
    _user, _token = _require_login_user(db, authorization)
    users, total = list_users_admin(db, {"email": email, "status": status, "num": num, "size": size})
    start = max((num - 1) * size, 0)
    end = start + size
    return ok({"list": users[start:end], "total": total})


@app.post("/user/add")
def compat_user_add(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        user = add_user_admin(db, payload)
    except ValueError as exc:
        return fail(str(exc), 400)
    return ok({"userId": user.id})


@app.put("/user/setPwd")
def compat_user_set_pwd(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        set_user_password(db, int(payload.get("userId", 0)), payload.get("password", ""))
    except LookupError:
        return fail("user not found", 404)
    return ok()


@app.put("/user/setStatus")
def compat_user_set_status(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        set_user_status(db, int(payload.get("userId", 0)), int(payload.get("status", 0)))
    except LookupError:
        return fail("user not found", 404)
    return ok()


@app.put("/user/setType")
def compat_user_set_type(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        set_user_type(db, int(payload.get("userId", 0)), int(payload.get("type", 1)))
    except LookupError:
        return fail("user not found", 404)
    return ok()


@app.put("/user/resetSendCount")
def compat_user_reset_send_count(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        reset_user_send_count(db, int(payload.get("userId", 0)))
    except LookupError:
        return fail("user not found", 404)
    return ok()


@app.put("/user/restore")
def compat_user_restore(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        set_user_status(db, int(payload.get("userId", 0)), 0)
    except LookupError:
        return fail("user not found", 404)
    return ok()


@app.delete("/user/delete")
def compat_user_delete(
    user_ids: str = Query("", alias="userIds"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    ids = [int(item) for item in user_ids.split(",") if item.strip().isdigit()]
    delete_users_admin(db, ids)
    return ok()


@app.get("/user/allAccount")
def compat_user_all_account(
    user_id: int = Query(..., alias="userId"),
    num: int = Query(1),
    size: int = Query(10),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    items, total = all_accounts_for_user(db, user_id, num, size)
    return ok({"list": items, "total": total})


@app.delete("/user/deleteAccount")
def compat_user_delete_account(
    account_id: int = Query(..., alias="accountId"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    try:
        owner_id = db.execute(select(Mailbox.user_id).where(Mailbox.id == account_id)).scalar_one()
        delete_account(db, owner_id, account_id)
    except Exception:
        return fail("account not found", 404)
    return ok()


@app.get("/regKey/list")
def compat_reg_key_list(
    code: str | None = Query(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    return ok(list_reg_keys(db, code))


@app.post("/regKey/add")
def compat_reg_key_add(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    add_reg_key(db, payload)
    return ok()


@app.delete("/regKey/delete")
def compat_reg_key_delete(
    reg_key_ids: str = Query("", alias="regKeyIds"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    ids = [int(item) for item in reg_key_ids.split(",") if item.strip().isdigit()]
    delete_reg_keys(db, ids)
    return ok()


@app.delete("/regKey/clearNotUse")
def compat_reg_key_clear_not_use(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    clear_unused_reg_keys(db)
    return ok()


@app.get("/regKey/history")
def compat_reg_key_history(
    reg_key_id: int = Query(..., alias="regKeyId"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    _user, _token = _require_login_user(db, authorization)
    return ok(reg_key_history_list(db, reg_key_id))


@app.get("/oss/{storage_path:path}")
def compat_oss(storage_path: str):
    file_path = resolve_object_path(storage_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="object not found")
    return FileResponse(file_path)


frontend_dist = settings.frontend_dist_path
frontend_index = frontend_dist / "index.html"
if frontend_dist.exists():
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def frontend_root():
        if frontend_index.exists():
            return FileResponse(frontend_index)
        raise HTTPException(status_code=404, detail="frontend not built")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend_spa(full_path: str):
        if full_path.startswith(("admin/", "api/", "user_api/", "inbox", "healthz")):
            raise HTTPException(status_code=404, detail="not found")
        requested = frontend_dist / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        if frontend_index.exists():
            return FileResponse(frontend_index)
        raise HTTPException(status_code=404, detail="frontend not built")


def run_api() -> None:
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    run_api()
