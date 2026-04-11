from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_common import account_payload, fail, get_db, get_setting, ok, require_user
from app.domain_utils import domain_allowed
from app.models import Account

router = APIRouter()


@router.post("/account/add")
def account_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    setting = get_setting(db)
    if setting.add_email != 0:
        return fail("add account disabled", 403)
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return fail("invalid email", 400)
    local_part, domain = email.split("@", 1)
    if not domain_allowed(domain, setting.allowed_domains):
        return fail("domain not allowed", 400)
    if len(local_part) < max(setting.min_email_prefix, 1):
        return fail("email prefix too short", 400)
    account = Account(email=email, name=local_part, user_id=user.user_id, sort=int(datetime.utcnow().timestamp()))
    db.add(account)
    db.commit()
    db.refresh(account)
    return ok(account_payload(account))


@router.get("/account/list")
def account_list(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    accounts = db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0).order_by(Account.sort.desc(), Account.account_id.asc())).scalars().all()
    return ok([account_payload(item) for item in accounts])


@router.put("/account/setName")
def account_set_name(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == int(payload.get("accountId", 0)), Account.user_id == user.user_id)).scalar_one_or_none()
    if account is None:
        return fail("account not found", 404)
    account.name = payload.get("name") or account.name
    db.commit()
    return ok()


@router.delete("/account/delete")
def account_delete(accountId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == accountId, Account.user_id == user.user_id)).scalar_one_or_none()
    if account is None:
        return fail("account not found", 404)
    account.is_del = 1
    db.commit()
    return ok()


@router.put("/account/setAllReceive")
def account_set_all_receive(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    target_id = int(payload.get("accountId", 0))
    accounts = db.execute(select(Account).where(Account.user_id == user.user_id, Account.is_del == 0)).scalars().all()
    found = False
    for item in accounts:
        if item.account_id == target_id:
            item.all_receive = 0 if item.all_receive else 1
            found = True
        else:
            item.all_receive = 0
    if not found:
        return fail("account not found", 404)
    db.commit()
    return ok()


@router.put("/account/setAsTop")
def account_set_top(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == int(payload.get("accountId", 0)), Account.user_id == user.user_id, Account.is_del == 0)).scalar_one_or_none()
    if account is None:
        return fail("account not found", 404)
    account.sort = int(datetime.utcnow().timestamp())
    db.commit()
    return ok()
