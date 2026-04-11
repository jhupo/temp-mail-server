from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Account, IncomingEmail, Setting, User, UserSession


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_password(password: str) -> str:
    salt = "cloudmail-vps"
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()


def _split_domains(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            items = json.loads(raw) if raw.startswith("[") else raw.split(",")
        except Exception:
            items = raw.split(",")
    else:
        items = []
    domains: list[str] = []
    for item in items:
        value = str(item).strip().lower()
        if value and value not in domains:
            domains.append(value)
    return domains


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_setting(db: Session) -> Setting:
    setting = db.execute(select(Setting).where(Setting.id == 1)).scalar_one_or_none()
    if setting is None:
        setting = Setting(
            id=1,
            title="Temp Mail",
            login_domain=1,
            allowed_domains=json.dumps(_split_domains(settings.cloud_mail_domain)),
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def _setting_payload(setting: Setting) -> dict:
    domain_list = [f"@{domain}" for domain in _split_domains(setting.allowed_domains)]
    return {
        "title": setting.title,
        "register": setting.register,
        "receive": setting.receive,
        "manyEmail": setting.many_email,
        "addEmail": setting.add_email,
        "autoRefresh": setting.auto_refresh,
        "addEmailVerify": setting.add_email_verify,
        "registerVerify": setting.register_verify,
        "send": setting.send,
        "r2Domain": setting.r2_domain,
        "siteKey": setting.site_key,
        "background": setting.background,
        "loginOpacity": setting.login_opacity / 100,
        "domainList": domain_list,
        "regKey": setting.reg_key,
        "regVerifyOpen": False,
        "addVerifyOpen": False,
        "noticeTitle": setting.notice_title,
        "noticeContent": setting.notice_content,
        "noticeType": setting.notice_type,
        "noticeDuration": setting.notice_duration,
        "noticePosition": setting.notice_position,
        "noticeWidth": setting.notice_width,
        "noticeOffset": setting.notice_offset,
        "notice": setting.notice,
        "loginDomain": setting.login_domain,
        "linuxdoClientId": "",
        "linuxdoCallbackUrl": "",
        "linuxdoSwitch": False,
        "minEmailPrefix": setting.min_email_prefix,
        "projectLink": bool(setting.project_link),
        "allowedDomains": _split_domains(setting.allowed_domains),
    }


def _primary_domain(setting: Setting) -> str:
    domains = _split_domains(setting.allowed_domains)
    return domains[0] if domains else ""


def _email_payload(email: IncomingEmail, user_email: str = "") -> dict:
    return {
        "emailId": email.id,
        "sendEmail": email.mail_from or "",
        "name": email.name or (email.mail_from or "").split("@", 1)[0],
        "accountId": email.account_id or 0,
        "userId": email.user_id or 0,
        "subject": email.subject or "",
        "text": email.text_body or "",
        "content": email.html_body or "",
        "recipient": email.recipient or json.dumps([{"address": email.rcpt_to}]),
        "toEmail": email.to_email or email.rcpt_to,
        "type": email.type,
        "status": email.status,
        "unread": email.unread,
        "createTime": email.created_at.isoformat() if email.created_at else "",
        "isDel": email.is_del,
        "userEmail": user_email,
        "isStar": email.is_star,
        "message": "",
        "attList": [],
    }


def _ok(data=None):
    return {"code": 200, "message": "success", "data": data}


def _fail(message: str, code: int = 500):
    return {"code": code, "message": message}


def _perm_keys(user: User) -> list[str]:
    return ["*"] if user.type == 0 else ["account:query", "email:send", "setting:query"]


def _account_payload(account: Account) -> dict:
    return {
        "accountId": account.account_id,
        "email": account.email,
        "name": account.name,
        "allReceive": account.all_receive,
        "sort": account.sort,
        "isDel": account.is_del,
    }


def _require_user(db: Session, authorization: str | None) -> User:
    token = (authorization or "").replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    session = db.execute(select(UserSession).where(UserSession.token_hash == _hash(token))).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=401, detail="invalid token")
    user = db.execute(select(User).where(User.user_id == session.user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="invalid user")
    return user


def _ensure_default_admin(db: Session) -> None:
    admin = db.execute(select(User).where(User.email == settings.default_admin_email)).scalar_one_or_none()
    if admin is None:
        admin = User(
            email=settings.default_admin_email,
            password_hash=_hash_password(settings.default_admin_password),
            name=settings.default_admin_email.split("@", 1)[0],
            type=0,
            status=0,
        )
        db.add(admin)
        db.flush()
        db.add(
            Account(
                email=admin.email,
                name=admin.name,
                user_id=admin.user_id,
                sort=0,
            )
        )
        db.commit()


def _user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_default_admin(db)
        _get_setting(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Cloud Mail Python Backend", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/login")
def login(payload: dict = Body(...), db: Session = Depends(get_db)):
    login_value = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    user = db.execute(select(User).where(User.email == login_value)).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).where(User.name == login_value)).scalar_one_or_none()
    if user is None or user.password_hash != _hash_password(password):
        return _fail("invalid email or password", 401)
    token = secrets.token_urlsafe(32)
    db.add(UserSession(user_id=user.user_id, token_hash=_hash(token)))
    db.commit()
    return _ok({"token": token})


@app.delete("/logout")
def logout(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    token = (authorization or "").replace("Bearer ", "").strip()
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))
        db.commit()
    return _ok()


@app.post("/register")
def register(payload: dict = Body(...), db: Session = Depends(get_db)):
    setting = _get_setting(db)
    if setting.register != 0:
        return _fail("register disabled", 403)
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or "@" not in email:
        return _fail("invalid email", 400)
    local_part, domain = email.split("@", 1)
    if len(local_part) < max(setting.min_email_prefix, 1):
        return _fail("email prefix too short", 400)
    if domain not in _split_domains(setting.allowed_domains):
        return _fail("domain not allowed", 400)
    if _user_by_email(db, email):
        return _fail("account already exists", 400)
    user = User(
        email=email,
        password_hash=_hash_password(password),
        name=local_part,
        type=1,
        status=0,
    )
    db.add(user)
    db.flush()
    account = Account(email=email, name=local_part, user_id=user.user_id, sort=0)
    db.add(account)
    db.flush()
    token = secrets.token_urlsafe(32)
    db.add(UserSession(user_id=user.user_id, token_hash=_hash(token)))
    db.commit()
    return _ok({"token": token, "regVerifyOpen": False})


@app.get("/my/loginUserInfo")
def login_user_info(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    account = db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0).order_by(Account.sort.asc(), Account.account_id.asc())).scalars().first()
    return _ok(
        {
            "userId": user.user_id,
            "email": user.email,
            "name": user.name,
            "sendCount": user.send_count,
            "permKeys": _perm_keys(user),
            "account": _account_payload(account) if account else {},
            "role": {"name": "Admin" if user.type == 0 else "User", "accountCount": 0, "sendType": "ban", "sendCount": 0},
            "type": user.type,
        }
    )


@app.get("/setting/query")
@app.get("/setting/websiteConfig")
def setting_query(db: Session = Depends(get_db)):
    return _ok(_setting_payload(_get_setting(db)))


@app.put("/setting/set")
def setting_set(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    _require_user(db, authorization)
    setting = _get_setting(db)
    field_map = {
        "title": "title",
        "register": "register",
        "receive": "receive",
        "manyEmail": "many_email",
        "addEmail": "add_email",
        "autoRefresh": "auto_refresh",
        "send": "send",
        "r2Domain": "r2_domain",
        "background": "background",
        "loginOpacity": "login_opacity",
        "regKey": "reg_key",
        "noticeTitle": "notice_title",
        "noticeContent": "notice_content",
        "noticeType": "notice_type",
        "noticeDuration": "notice_duration",
        "noticePosition": "notice_position",
        "noticeWidth": "notice_width",
        "noticeOffset": "notice_offset",
        "notice": "notice",
        "loginDomain": "login_domain",
        "minEmailPrefix": "min_email_prefix",
        "projectLink": "project_link",
    }
    for key, attr in field_map.items():
        if key in payload:
            value = payload[key]
            if key == "loginOpacity":
                value = int(float(value) * 100)
            setattr(setting, attr, value)
    if "allowedDomains" in payload:
        setting.allowed_domains = json.dumps(_split_domains(payload["allowedDomains"]))
    db.commit()
    db.refresh(setting)
    return _ok(_setting_payload(setting))


@app.post("/account/add")
def account_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    setting = _get_setting(db)
    if setting.add_email != 0:
        return _fail("add account disabled", 403)
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _fail("invalid email", 400)
    local_part, domain = email.split("@", 1)
    if domain not in _split_domains(setting.allowed_domains):
        return _fail("domain not allowed", 400)
    if len(local_part) < max(setting.min_email_prefix, 1):
        return _fail("email prefix too short", 400)
    account = Account(email=email, name=email.split("@", 1)[0], user_id=user.user_id, sort=int(datetime.utcnow().timestamp()))
    db.add(account)
    db.commit()
    db.refresh(account)
    return _ok(_account_payload(account))


@app.get("/account/list")
def account_list(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    accounts = db.execute(select(Account).where(Account.user_id == user.user_id).order_by(Account.sort.desc(), Account.account_id.asc())).scalars().all()
    return _ok([_account_payload(item) for item in accounts])


@app.put("/account/setName")
def account_set_name(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == int(payload.get("accountId", 0)), Account.user_id == user.user_id)).scalar_one_or_none()
    if account is None:
        return _fail("account not found", 404)
    account.name = payload.get("name") or account.name
    db.commit()
    return _ok()


@app.delete("/account/delete")
def account_delete(accountId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == accountId, Account.user_id == user.user_id)).scalar_one_or_none()
    if account is None:
        return _fail("account not found", 404)
    account.is_del = 1
    db.commit()
    return _ok()


@app.put("/account/setAllReceive")
def account_set_all_receive(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    target_id = int(payload.get("accountId", 0))
    accounts = db.execute(select(Account).where(Account.user_id == user.user_id)).scalars().all()
    found = False
    for item in accounts:
        if item.account_id == target_id:
            item.all_receive = 0 if item.all_receive else 1
            found = True
        else:
            item.all_receive = 0
    if not found:
        return _fail("account not found", 404)
    db.commit()
    return _ok()


@app.put("/account/setAsTop")
def account_set_top(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == int(payload.get("accountId", 0)), Account.user_id == user.user_id)).scalar_one_or_none()
    if account is None:
        return _fail("account not found", 404)
    account.sort = int(datetime.utcnow().timestamp())
    db.commit()
    return _ok()


@app.get("/email/list")
def email_list(
    accountId: int = Query(...),
    allReceive: int = Query(0),
    emailId: int = Query(0),
    size: int = Query(50),
    type: int = Query(0),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = _require_user(db, authorization)
    account_ids = [accountId]
    if allReceive:
        account_ids = [a.account_id for a in db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0)).scalars().all()]
    stmt = select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.account_id.in_(account_ids), IncomingEmail.type == type, IncomingEmail.is_del == 0)
    if emailId:
        stmt = stmt.where(IncomingEmail.id < emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(size)).scalars().all()
    total = len(db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.account_id.in_(account_ids), IncomingEmail.type == type, IncomingEmail.is_del == 0)).scalars().all())
    latest = _email_payload(items[0], user.email) if items else {"emailId": 0}
    return _ok({"list": [_email_payload(item, user.email) for item in items], "total": total, "latestEmail": latest})


@app.get("/email/latest")
def email_latest(
    emailId: int = Query(0),
    accountId: int = Query(...),
    allReceive: int = Query(0),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = _require_user(db, authorization)
    account_ids = [accountId]
    if allReceive:
        account_ids = [a.account_id for a in db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0)).scalars().all()]
    stmt = select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.account_id.in_(account_ids), IncomingEmail.type == 0, IncomingEmail.is_del == 0, IncomingEmail.id > emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(20)).scalars().all()
    return _ok([_email_payload(item, user.email) for item in items])


@app.put("/email/read")
def email_read(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    ids = [int(item) for item in payload.get("emailIds", [])]
    rows = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id.in_(ids))).scalars().all()
    for row in rows:
        row.unread = 1
    db.commit()
    return _ok()


@app.delete("/email/delete")
def email_delete(emailIds: str = Query(""), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    ids = [int(item) for item in emailIds.split(",") if item.strip().isdigit()]
    rows = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id.in_(ids))).scalars().all()
    for row in rows:
        row.is_del = 1
    db.commit()
    return _ok()


@app.post("/star/add")
def star_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    row = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id == int(payload.get("emailId", 0)))).scalar_one_or_none()
    if row is None:
        return _fail("email not found", 404)
    row.is_star = 1
    db.commit()
    return _ok()


@app.delete("/star/cancel")
def star_cancel(emailId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    row = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id == emailId)).scalar_one_or_none()
    if row is None:
        return _fail("email not found", 404)
    row.is_star = 0
    db.commit()
    return _ok()


@app.get("/star/list")
def star_list(emailId: int = Query(0), size: int = Query(50), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    stmt = select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.is_star == 1, IncomingEmail.is_del == 0)
    if emailId:
        stmt = stmt.where(IncomingEmail.id < emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(size)).scalars().all()
    total = len(db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.is_star == 1, IncomingEmail.is_del == 0)).scalars().all())
    latest = _email_payload(items[0], user.email) if items else {"emailId": 0}
    return _ok({"list": [_email_payload(item, user.email) for item in items], "total": total, "latestEmail": latest})


@app.get("/allEmail/list")
def all_email_list(emailId: int = Query(0), size: int = Query(50), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    if user.type != 0:
        return _fail("forbidden", 403)
    stmt = select(IncomingEmail)
    if emailId:
        stmt = stmt.where(IncomingEmail.id < emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(size)).scalars().all()
    total = len(db.execute(select(IncomingEmail)).scalars().all())
    latest = _email_payload(items[0], user.email) if items else {"emailId": 0}
    return _ok({"list": [_email_payload(item, item.mail_from or "") for item in items], "total": total, "latestEmail": latest})


@app.get("/allEmail/latest")
def all_email_latest(emailId: int = Query(0), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    if user.type != 0:
        return _fail("forbidden", 403)
    stmt = select(IncomingEmail).where(IncomingEmail.id > emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(20)).scalars().all()
    return _ok([_email_payload(item, item.mail_from or "") for item in items])


@app.post("/email/send")
def email_send(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == int(payload.get("accountId", 0)), Account.user_id == user.user_id, Account.is_del == 0)).scalar_one_or_none()
    if account is None:
        return _fail("sender account not found", 404)
    recipients = payload.get("receiveEmail") or []
    if not recipients:
        return _fail("empty recipient", 400)
    row = IncomingEmail(
        user_id=user.user_id,
        account_id=account.account_id,
        mail_from=account.email,
        rcpt_to=recipients[0],
        to_email=recipients[0],
        subject=payload.get("subject") or "",
        text_body=payload.get("text") or "",
        html_body=payload.get("content") or "",
        recipient=json.dumps([{"address": item} for item in recipients]),
        name=account.name,
        unread=1,
        is_del=0,
        type=1,
        status=2,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _ok([_email_payload(row, user.email)])


@app.get("/analysis/echarts")
def analysis_echarts(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    if user.type != 0:
        return _fail("forbidden", 403)
    emails = db.execute(select(IncomingEmail)).scalars().all()
    users = db.execute(select(User)).scalars().all()
    accounts = db.execute(select(Account)).scalars().all()
    receive = [item for item in emails if item.type == 0]
    send = [item for item in emails if item.type == 1]
    today = datetime.utcnow().date().isoformat()
    day_send_total = len([item for item in send if item.created_at.date().isoformat() == today])
    sender_counter = {}
    for item in receive:
        key = item.mail_from or "unknown"
        sender_counter[key] = sender_counter.get(key, 0) + 1
    user_day = {}
    for item in users:
        key = item.create_time.date().isoformat()
        user_day[key] = user_day.get(key, 0) + 1
    receive_day = {}
    send_day = {}
    for item in receive:
        key = item.created_at.date().isoformat()
        receive_day[key] = receive_day.get(key, 0) + 1
    for item in send:
        key = item.created_at.date().isoformat()
        send_day[key] = send_day.get(key, 0) + 1
    return _ok({
        "numberCount": {
            "receiveTotal": len(receive),
            "sendTotal": len(send),
            "accountTotal": len([a for a in accounts if a.is_del == 0]),
            "userTotal": len(users),
            "normalReceiveTotal": len([e for e in receive if e.is_del == 0]),
            "normalSendTotal": len([e for e in send if e.is_del == 0]),
            "normalAccountTotal": len([a for a in accounts if a.is_del == 0]),
            "normalUserTotal": len(users),
            "delReceiveTotal": len([e for e in receive if e.is_del == 1]),
            "delSendTotal": len([e for e in send if e.is_del == 1]),
            "delAccountTotal": len([a for a in accounts if a.is_del == 1]),
            "delUserTotal": 0,
        },
        "receiveRatio": {
            "nameRatio": [{"name": key, "total": value} for key, value in sorted(sender_counter.items(), key=lambda item: item[1], reverse=True)[:10]]
        },
        "userDayCount": [{"date": key, "total": value} for key, value in sorted(user_day.items())],
        "emailDayCount": {
            "receiveDayCount": [{"date": key, "total": value} for key, value in sorted(receive_day.items())],
            "sendDayCount": [{"date": key, "total": value} for key, value in sorted(send_day.items())],
        },
        "daySendTotal": day_send_total,
    })


@app.delete("/allEmail/delete")
def all_email_delete(emailIds: str = Query(""), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    if user.type != 0:
        return _fail("forbidden", 403)
    ids = [int(item) for item in emailIds.split(",") if item.strip().isdigit()]
    rows = db.execute(select(IncomingEmail).where(IncomingEmail.id.in_(ids))).scalars().all()
    for row in rows:
        row.is_del = 1
    db.commit()
    return _ok()


@app.delete("/allEmail/batchDelete")
def all_email_batch_delete(
    sendName: str | None = Query(None),
    subject: str | None = Query(None),
    sendEmail: str | None = Query(None),
    toEmail: str | None = Query(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = _require_user(db, authorization)
    if user.type != 0:
        return _fail("forbidden", 403)
    stmt = select(IncomingEmail)
    if sendName:
        stmt = stmt.where(IncomingEmail.name.contains(sendName))
    if subject:
        stmt = stmt.where(IncomingEmail.subject.contains(subject))
    if sendEmail:
        stmt = stmt.where(IncomingEmail.mail_from.contains(sendEmail))
    if toEmail:
        stmt = stmt.where(IncomingEmail.to_email.contains(toEmail))
    rows = db.execute(stmt).scalars().all()
    for row in rows:
        row.is_del = 1
    db.commit()
    return _ok()


@app.put("/setting/setBackground")
def setting_set_background(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    _require_user(db, authorization)
    setting = _get_setting(db)
    setting.background = payload.get("background") or ""
    db.commit()
    return _ok(setting.background)


@app.delete("/setting/deleteBackground")
def setting_delete_background(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    _require_user(db, authorization)
    setting = _get_setting(db)
    setting.background = ""
    db.commit()
    return _ok()


@app.post("/internal/smtp/receive")
def internal_smtp_receive(
    payload: dict,
    smtp_gateway_token: str | None = Header(default=None, alias="x-smtp-gateway-token"),
):
    if smtp_gateway_token != settings.smtp_gateway_token:
        raise HTTPException(status_code=403, detail="invalid smtp gateway token")

    recipients = payload.get("to") or []
    if not isinstance(recipients, list) or not recipients:
        raise HTTPException(status_code=400, detail="no recipients")

    db = SessionLocal()
    try:
        for recipient in recipients:
            account = db.execute(select(Account).where(Account.email == recipient, Account.is_del == 0)).scalar_one_or_none()
            db.add(
                IncomingEmail(
                    mail_from=payload.get("from"),
                    rcpt_to=recipient,
                    subject=payload.get("subject"),
                    text_body=payload.get("text"),
                    html_body=payload.get("html"),
                    raw_body=payload.get("raw"),
                    user_id=account.user_id if account else None,
                    account_id=account.account_id if account else None,
                )
            )
        db.commit()
    finally:
        db.close()
    return {"ok": True}


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
        requested = frontend_dist / full_path
        if requested.exists() and requested.is_file():
            return FileResponse(requested)
        if frontend_index.exists():
            return FileResponse(frontend_index)
        raise HTTPException(status_code=404, detail="frontend not built")
