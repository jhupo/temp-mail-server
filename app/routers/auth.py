from __future__ import annotations

import secrets

from fastapi import APIRouter, Body, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_common import (
    account_payload,
    delete_session,
    delete_user_sessions,
    fail,
    get_db,
    get_setting,
    hash_password,
    ok,
    perm_keys,
    require_user,
    save_session,
    user_by_email,
)
from app.domain_utils import domain_allowed
from app.models import Account, User

router = APIRouter()


@router.post("/login")
def login(payload: dict = Body(...), db: Session = Depends(get_db)):
    login_value = (payload.get("email") or "").strip()
    password = payload.get("password") or ""
    user = db.execute(select(User).where(User.email == login_value)).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).where(User.name == login_value)).scalar_one_or_none()
    if user is None or user.password_hash != hash_password(password):
        return fail("invalid email or password", 401)
    token = secrets.token_urlsafe(32)
    save_session(db, user.user_id, token)
    db.commit()
    return ok({"token": token})


@router.delete("/logout")
def logout(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    token = (authorization or "").replace("Bearer ", "").strip()
    if token:
        delete_session(db, token)
        db.commit()
    return ok()


@router.post("/register")
def register(payload: dict = Body(...), db: Session = Depends(get_db)):
    setting = get_setting(db)
    if setting.register != 0:
        return fail("register disabled", 403)
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or "@" not in email:
        return fail("invalid email", 400)
    local_part, domain = email.split("@", 1)
    if len(local_part) < max(setting.min_email_prefix, 1):
        return fail("email prefix too short", 400)
    if not domain_allowed(domain, setting.allowed_domains):
        return fail("domain not allowed", 400)
    if user_by_email(db, email):
        return fail("account already exists", 400)
    user = User(email=email, password_hash=hash_password(password), name=local_part, type=1, status=0)
    db.add(user)
    db.flush()
    db.add(Account(email=email, name=local_part, user_id=user.user_id, sort=0))
    db.flush()
    token = secrets.token_urlsafe(32)
    save_session(db, user.user_id, token)
    db.commit()
    return ok({"token": token, "regVerifyOpen": False})


@router.get("/my/loginUserInfo")
def login_user_info(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    account = db.execute(
        select(Account).where(Account.user_id == user.user_id, Account.is_del == 0).order_by(Account.sort.asc(), Account.account_id.asc())
    ).scalars().first()
    return ok(
        {
            "userId": user.user_id,
            "email": user.email,
            "name": user.name,
            "sendCount": user.send_count,
            "permKeys": perm_keys(user),
            "account": account_payload(account) if account else {},
            "role": {"name": "Admin" if user.type == 0 else "User", "accountCount": 0, "sendType": "ban", "sendCount": 0},
            "type": user.type,
        }
    )


@router.put("/my/resetPassword")
def my_reset_password(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    password = payload.get("password") or ""
    if not password:
        return fail("password required", 400)
    user.password_hash = hash_password(password)
    db.commit()
    return ok()


@router.delete("/my/delete")
def my_delete(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    if user.type == 0:
        return fail("admin cannot delete self", 403)
    delete_user_sessions(db, user.user_id)
    db.delete(user)
    db.commit()
    return ok()


@router.post("/oauth/linuxDo/login")
def oauth_linuxdo_login():
    return fail("oauth login is not enabled on the python backend", 403)


@router.put("/oauth/bindUser")
def oauth_bind_user():
    return fail("oauth login is not enabled on the python backend", 403)
