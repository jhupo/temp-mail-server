from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_common import email_payload, fail, get_db, get_setting, ok, require_user
from app.models import Account, IncomingEmail
from app.outbound_mail import direct_mx_enabled, resend_enabled, send_outbound_email, smtp_relay_enabled

router = APIRouter()


@router.get("/email/list")
def email_list(
    accountId: int = Query(...),
    allReceive: int = Query(0),
    emailId: int = Query(0),
    size: int = Query(50),
    type: int = Query(0),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = require_user(db, authorization)
    account_ids = [accountId]
    if allReceive:
        account_ids = [a.account_id for a in db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0)).scalars().all()]
    stmt = select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.account_id.in_(account_ids), IncomingEmail.type == type, IncomingEmail.is_del == 0)
    if emailId:
        stmt = stmt.where(IncomingEmail.id < emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(size)).scalars().all()
    total = len(db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.account_id.in_(account_ids), IncomingEmail.type == type, IncomingEmail.is_del == 0)).scalars().all())
    latest = email_payload(items[0], user.email) if items else {"emailId": 0}
    return ok({"list": [email_payload(item, user.email) for item in items], "total": total, "latestEmail": latest})


@router.get("/email/latest")
def email_latest(
    emailId: int = Query(0),
    accountId: int = Query(...),
    allReceive: int = Query(0),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = require_user(db, authorization)
    account_ids = [accountId]
    if allReceive:
        account_ids = [a.account_id for a in db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0)).scalars().all()]
    stmt = select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.account_id.in_(account_ids), IncomingEmail.type == 0, IncomingEmail.is_del == 0, IncomingEmail.id > emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(20)).scalars().all()
    return ok([email_payload(item, user.email) for item in items])


@router.put("/email/read")
def email_read(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    ids = [int(item) for item in payload.get("emailIds", [])]
    rows = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id.in_(ids))).scalars().all()
    for row in rows:
        row.unread = 1
    db.commit()
    return ok()


@router.delete("/email/delete")
def email_delete(emailIds: str = Query(""), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    ids = [int(item) for item in emailIds.split(",") if item.strip().isdigit()]
    rows = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id.in_(ids))).scalars().all()
    for row in rows:
        row.is_del = 1
    db.commit()
    return ok()


@router.post("/star/add")
def star_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    row = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id == int(payload.get("emailId", 0)))).scalar_one_or_none()
    if row is None:
        return fail("email not found", 404)
    row.is_star = 1
    db.commit()
    return ok()


@router.delete("/star/cancel")
def star_cancel(emailId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    row = db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.id == emailId)).scalar_one_or_none()
    if row is None:
        return fail("email not found", 404)
    row.is_star = 0
    db.commit()
    return ok()


@router.get("/star/list")
def star_list(emailId: int = Query(0), size: int = Query(50), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    stmt = select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.is_star == 1, IncomingEmail.is_del == 0)
    if emailId:
        stmt = stmt.where(IncomingEmail.id < emailId)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(size)).scalars().all()
    total = len(db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.is_star == 1, IncomingEmail.is_del == 0)).scalars().all())
    latest = email_payload(items[0], user.email) if items else {"emailId": 0}
    return ok({"list": [email_payload(item, user.email) for item in items], "total": total, "latestEmail": latest})


@router.post("/email/send")
def email_send(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == int(payload.get("accountId", 0)), Account.user_id == user.user_id, Account.is_del == 0)).scalar_one_or_none()
    if account is None:
        return fail("sender account not found", 404)
    recipients = payload.get("receiveEmail") or []
    if not recipients:
        return fail("empty recipient", 400)
    subject = payload.get("subject") or ""
    text_body = payload.get("text") or ""
    html_body = payload.get("content") or ""
    status = 2
    setting = get_setting(db)
    if resend_enabled(setting.resend_token) or smtp_relay_enabled() or direct_mx_enabled():
        try:
            send_outbound_email(account.email, recipients, subject, text_body, html_body, resend_token=setting.resend_token)
        except Exception as exc:
            status = 7
            row = IncomingEmail(
                user_id=user.user_id,
                account_id=account.account_id,
                mail_from=account.email,
                rcpt_to=recipients[0],
                to_email=recipients[0],
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                recipient=json.dumps([{"address": item} for item in recipients]),
                name=account.name,
                unread=1,
                is_del=0,
                type=1,
                status=status,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return fail(f"smtp send failed: {exc}", 502)
    row = IncomingEmail(
        user_id=user.user_id,
        account_id=account.account_id,
        mail_from=account.email,
        rcpt_to=recipients[0],
        to_email=recipients[0],
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        recipient=json.dumps([{"address": item} for item in recipients]),
        name=account.name,
        unread=1,
        is_del=0,
        type=1,
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok([email_payload(row, user.email)])
