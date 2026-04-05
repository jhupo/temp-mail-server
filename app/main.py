from datetime import datetime

import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
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
from app.utils import is_allowed_domain, is_valid_local_part


app = FastAPI(title="Temp Mail Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_admin_auth(admin_auth: str | None) -> None:
    if settings.api_master_key and admin_auth != settings.api_master_key:
        raise HTTPException(status_code=401, detail="invalid admin auth")


def _require_mailbox_from_token(db: Session, token: str | None):
    if not token:
        raise HTTPException(status_code=401, detail="token required")
    mailbox = get_mailbox_by_token(db, token)
    if mailbox is None:
        raise HTTPException(status_code=403, detail="invalid token")
    return mailbox


def _serialize_message(message, *, address: str) -> dict:
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
        "createdAt": message.received_at.isoformat() if message.received_at else None,
        "created_at": message.received_at.isoformat() if message.received_at else None,
    }


def _extract_token_header(authorization: str | None, x_user_token: str | None) -> str | None:
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    return bearer or (x_user_token or "").strip() or None


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    cleaned = cleanup_expired(db)
    return {"ok": True, "cleaned_mailboxes": cleaned, "ts": datetime.utcnow().isoformat()}


@app.post("/admin/new_address")
def compat_admin_new_address(
    payload: dict | None = Body(default=None),
    db: Session = Depends(get_db),
    admin_auth: str | None = Header(default=None, alias="x-admin-auth"),
):
    _require_admin_auth(admin_auth)
    cleanup_expired(db)
    payload = payload or {}
    domain = (payload.get("domain") or settings.allowed_root_domain).lower()
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
    db: Session = Depends(get_db),
):
    cleanup_expired(db)
    mailbox, token = create_mailbox(
        db,
        domain=settings.allowed_root_domain.lower(),
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
    cleanup_expired(db)
    mailbox = _require_mailbox_from_token(db, token)
    items = get_messages(db, mailbox.id, limit=50)
    emails = [
        {
            "from": item.from_addr,
            "subject": item.subject,
            "body": item.text_body,
            "html": item.html_body,
            "date": int(item.received_at.timestamp()) if item.received_at else None,
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
    cleanup_expired(db)
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
    cleanup_expired(db)
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
    cleanup_expired(db)
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
    cleanup_expired(db)
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
    cleanup_expired(db)
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
    cleanup_expired(db)
    mailbox = _require_mailbox_from_token(db, x_user_token)
    message = get_message_by_id(db, mailbox.id, mail_id)
    if message is None:
        raise HTTPException(status_code=404, detail="mail not found")
    return _serialize_message(message, address=mailbox.address)


def run_api() -> None:
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    run_api()
