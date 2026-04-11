from __future__ import annotations

import hashlib
import json
import secrets

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.domain_utils import split_domains
from app.models import Account, IncomingEmail, Role, Setting, User, UserSession
from app.outbound_mail import direct_mx_enabled, smtp_relay_enabled
from app.redis_client import get_redis


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = "cloudmail-vps"
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ok(data=None):
    return {"code": 200, "message": "success", "data": data}


def fail(message: str, code: int = 500):
    return {"code": code, "message": message}


def session_key(token: str) -> str:
    return f"{settings.session_prefix}{hash_value(token)}"


def save_session(db: Session, user_id: int, token: str) -> None:
    token_hash = hash_value(token)
    try:
        get_redis().set(session_key(token), str(user_id))
    except Exception:
        pass
    db.add(UserSession(user_id=user_id, token_hash=token_hash))


def delete_session(db: Session, token: str) -> None:
    token_hash = hash_value(token)
    try:
        get_redis().delete(session_key(token))
    except Exception:
        pass
    db.execute(delete(UserSession).where(UserSession.token_hash == token_hash))


def delete_user_sessions(db: Session, user_id: int) -> None:
    sessions = db.execute(select(UserSession).where(UserSession.user_id == user_id)).scalars().all()
    for session in sessions:
        try:
            get_redis().delete(f"{settings.session_prefix}{session.token_hash}")
        except Exception:
            pass
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))


def get_session_user_id(token: str, db: Session) -> int | None:
    token_hash = hash_value(token)
    try:
        cached = get_redis().get(session_key(token))
        if cached:
            return int(cached)
    except Exception:
        pass
    session = db.execute(select(UserSession).where(UserSession.token_hash == token_hash)).scalar_one_or_none()
    if session is None:
        return None
    try:
        get_redis().set(session_key(token), str(session.user_id))
    except Exception:
        pass
    return session.user_id


def require_user(db: Session, authorization: str | None) -> User:
    token = (authorization or "").replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing token")
    user_id = get_session_user_id(token, db)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid token")
    user = db.execute(select(User).where(User.user_id == user_id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="invalid user")
    return user


def get_setting(db: Session) -> Setting:
    env_domains = split_domains(settings.cloud_mail_domain)
    setting = db.execute(select(Setting).where(Setting.id == 1)).scalar_one_or_none()
    if setting is None:
        setting = Setting(id=1, title="Temp Mail", login_domain=1, allowed_domains=json.dumps(env_domains))
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def account_payload(account: Account) -> dict:
    return {
        "accountId": account.account_id,
        "email": account.email,
        "name": account.name,
        "allReceive": account.all_receive,
        "sort": account.sort,
        "isDel": account.is_del,
    }


def email_payload(email: IncomingEmail, user_email: str = "") -> dict:
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


def role_payload(role: Role) -> dict:
    return {
        "roleId": role.role_id,
        "name": role.name,
        "description": role.description or "",
        "sort": role.sort,
        "isDefault": role.is_default,
        "permIds": json.loads(role.perm_ids or "[]"),
        "sendType": role.send_type,
        "sendCount": role.send_count,
        "accountCount": role.account_count,
        "banEmail": json.loads(role.ban_email or "[]"),
        "availDomain": json.loads(role.avail_domain or "[]"),
    }


def user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == email)).scalar_one_or_none()


def perm_keys(user: User) -> list[str]:
    return ["*"] if user.type == 0 else ["account:query", "email:send", "setting:query"]


def setting_payload(setting: Setting) -> dict:
    domain_list = [f"@{domain}" for domain in split_domains(setting.allowed_domains)]
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
        "allowedDomains": split_domains(setting.allowed_domains),
        "resendConfigured": bool(setting.resend_token),
        "smtpHost": settings.smtp_out_host,
        "smtpPort": settings.smtp_out_port,
        "smtpUsername": settings.smtp_out_username,
        "smtpPassword": "",
        "smtpUseTls": settings.smtp_out_use_tls,
        "smtpUseSsl": settings.smtp_out_use_ssl,
        "smtpFromEmail": settings.smtp_out_from_email,
        "sendMode": "resend" if setting.resend_token else ("smtp" if smtp_relay_enabled() else ("direct-mx" if direct_mx_enabled() else "record")),
        "directHeloHost": settings.direct_helo_host,
        "dkimSelector": settings.dkim_selector,
        "dkimDomain": settings.dkim_domain,
    }


def ensure_default_admin(db: Session) -> None:
    admin = db.execute(select(User).where(User.email == settings.default_admin_email)).scalar_one_or_none()
    if admin is None:
        admin = User(
            email=settings.default_admin_email,
            password_hash=hash_password(settings.default_admin_password),
            name=settings.default_admin_email.split("@", 1)[0],
            type=0,
            status=0,
        )
        db.add(admin)
        db.flush()
        db.add(Account(email=admin.email, name=admin.name, user_id=admin.user_id, sort=0))
        db.add(
            Role(
                role_id=1,
                name="User",
                description="Default role",
                sort=0,
                is_default=1,
                perm_ids=json.dumps([1, 2, 3]),
                send_type="ban",
                send_count=0,
                account_count=0,
                ban_email="[]",
                avail_domain="[]",
            )
        )
        db.commit()
