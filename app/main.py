from datetime import datetime
import re

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import authorize_mailbox, cleanup_expired, create_mailbox, get_latest_message
from app.database import Base, SessionLocal, engine
from app.rate_limit import limiter
from app.schemas import MailboxCodeResponse, MailboxLatestResponse, MailboxNewRequest, MailboxNewResponse, MessageOut
from app.utils import is_allowed_domain, is_valid_local_part


app = FastAPI(title="Temp Mail Service", version="0.1.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _require_api_key(api_key: str | None) -> None:
    if settings.api_master_key and api_key != settings.api_master_key:
        raise HTTPException(status_code=401, detail="invalid api key")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    cleaned = cleanup_expired(db)
    return {"ok": True, "cleaned_mailboxes": cleaned, "ts": datetime.utcnow().isoformat()}


@app.post("/api/v1/mailboxes/new", response_model=MailboxNewResponse)
def new_mailbox(
    payload: MailboxNewRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _require_api_key(api_key)
    client_ip = _get_client_ip(request)
    allowed, retry_after = limiter.check_new_mailbox(client_ip)
    if not allowed:
        response.headers["Retry-After"] = str(retry_after)
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    cleanup_expired(db)
    domain = (payload.domain or settings.allowed_root_domain).lower()
    if not is_allowed_domain(domain):
        raise HTTPException(status_code=400, detail="domain not allowed")
    if payload.local_part and not is_valid_local_part(payload.local_part):
        raise HTTPException(status_code=400, detail="invalid local_part format")

    try:
        mailbox, token = create_mailbox(
            db,
            domain=domain,
            local_part=payload.local_part,
            ttl_minutes=payload.ttl_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return MailboxNewResponse(address=mailbox.address, token=token, expires_at=mailbox.expires_at)


@app.get("/api/v1/mailboxes/{address}/latest", response_model=MailboxLatestResponse)
def latest_mail(
    address: str,
    db: Session = Depends(get_db),
    token_query: str | None = Query(default=None, alias="token"),
    token_header: str | None = Header(default=None, alias="X-Mailbox-Token"),
):
    cleanup_expired(db)
    token = token_header or token_query
    if not token:
        raise HTTPException(status_code=401, detail="token required")
    try:
        mailbox = authorize_mailbox(db, address=address, token=token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    latest = get_latest_message(db, mailbox.id)
    latest_out = None
    if latest:
        latest_out = MessageOut(
            from_addr=latest.from_addr,
            subject=latest.subject,
            text_body=latest.text_body,
            html_body=latest.html_body,
            raw_headers=latest.raw_headers,
            received_at=latest.received_at,
        )
    return MailboxLatestResponse(address=mailbox.address, latest=latest_out)


@app.get("/api/v1/mailboxes/{address}/latest/code", response_model=MailboxCodeResponse)
def latest_code(
    address: str,
    db: Session = Depends(get_db),
    token_query: str | None = Query(default=None, alias="token"),
    token_header: str | None = Header(default=None, alias="X-Mailbox-Token"),
    pattern: str = Query(default=r"\b(\d{4,8})\b"),
):
    cleanup_expired(db)
    token = token_header or token_query
    if not token:
        raise HTTPException(status_code=401, detail="token required")
    try:
        mailbox = authorize_mailbox(db, address=address, token=token)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    latest = get_latest_message(db, mailbox.id)
    if latest is None:
        return MailboxCodeResponse(address=mailbox.address, code=None, received_at=None)

    try:
        code_re = re.compile(pattern)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"invalid regex pattern: {exc}") from exc

    text_pool = "\n".join(
        part for part in [latest.subject or "", latest.text_body or "", latest.html_body or ""] if part
    )
    match = code_re.search(text_pool)
    code = match.group(1) if match and match.groups() else (match.group(0) if match else None)
    return MailboxCodeResponse(address=mailbox.address, code=code, received_at=latest.received_at)


def run_api() -> None:
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    run_api()
