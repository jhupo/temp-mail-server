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
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _fail("invalid email", 400)
    account = Account(email=email, name=email.split("@", 1)[0], user_id=user.user_id, sort=int(datetime.utcnow().timestamp()))
    db.add(account)
    db.commit()
    db.refresh(account)
    return _ok(_account_payload(account))


@app.get("/account/list")
def account_list(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = _require_user(db, authorization)
    accounts = db.execute(select(Account).where(Account.user_id == user.user_id).order_by(Account.sort.asc(), Account.account_id.asc())).scalars().all()
    return _ok([_account_payload(item) for item in accounts])


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
