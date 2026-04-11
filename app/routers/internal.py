from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Account, IncomingEmail

router = APIRouter()


@router.post("/internal/smtp/receive")
def internal_smtp_receive(payload: dict, smtp_gateway_token: str | None = Header(default=None, alias="x-smtp-gateway-token")):
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
