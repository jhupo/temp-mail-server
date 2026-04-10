from contextlib import asynccontextmanager
import threading

import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import (
    cleanup_expired,
    create_mailbox,
    get_mailbox_by_token,
    get_message_by_id,
    get_message_by_id_admin,
    get_messages,
    get_messages_admin,
)
from app.database import SessionLocal, init_db
from app.rate_limit import limiter
from app.time_utils import ensure_utc, utcnow
from app.utils import is_allowed_domain, is_valid_local_part


_cleanup_stop_event = threading.Event()
_cleanup_thread: threading.Thread | None = None


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
    return bearer or (x_user_token or "").strip() or None


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


def _cleanup_loop(stop_event: threading.Event) -> None:
    interval = max(settings.cleanup_interval_seconds, 1)
    while not stop_event.wait(interval):
        db = SessionLocal()
        try:
            cleanup_expired(db)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _cleanup_thread
    init_db()
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_stop_event.clear()
        _cleanup_thread = threading.Thread(target=_cleanup_loop, args=(_cleanup_stop_event,), daemon=True)
        _cleanup_thread.start()
    try:
        yield
    finally:
        _cleanup_stop_event.set()
        if _cleanup_thread is not None:
            _cleanup_thread.join(timeout=1)
            _cleanup_thread = None


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
    payload = payload or {}
    domain = (payload.get("domain") or settings.primary_domain).lower()
    local_part = payload.get("name")
    if payload.get("local_part"):
        local_part = payload.get("local_part")
    ttl_minutes = payload.get("ttl_minutes")
    if not is_allowed_domain(domain):
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
    mailbox, token = create_mailbox(
        db,
        domain=settings.primary_domain,
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
