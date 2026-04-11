from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Header, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api_common import default_role_id, email_payload, fail, get_db, hash_password, ok, permission_tree_payload, require_user, role_payload, user_by_email
from app.models import Account, IncomingEmail, RegKey, RegKeyUser, Role, User

router = APIRouter()


def _match_text(value: str | None, expected: str | None, match_type: str) -> bool:
    if not expected:
        return True
    left = (value or "").strip().lower()
    right = expected.strip().lower()
    if match_type == "eq":
        return left == right
    if match_type == "left":
        return left.startswith(right)
    return right in left


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("/allEmail/list")
def all_email_list(
    emailId: int = Query(0),
    size: int = Query(50),
    timeSort: int = Query(0),
    type: str = Query("all"),
    userEmail: str | None = Query(None),
    accountEmail: str | None = Query(None),
    name: str | None = Query(None),
    subject: str | None = Query(None),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
    stmt = select(IncomingEmail)
    if type == "receive":
        stmt = stmt.where(IncomingEmail.type == 0, IncomingEmail.is_del == 0)
    elif type == "send":
        stmt = stmt.where(IncomingEmail.type == 1, IncomingEmail.is_del == 0)
    elif type == "delete":
        stmt = stmt.where(IncomingEmail.is_del == 1)
    elif type == "noone":
        stmt = stmt.where(IncomingEmail.status == 7, IncomingEmail.is_del == 0)
    else:
        stmt = stmt.where(IncomingEmail.is_del == 0)
    if userEmail:
        stmt = stmt.where(IncomingEmail.user_id.in_(select(User.user_id).where(User.email.contains(userEmail))))
    if accountEmail:
        stmt = stmt.where(
            or_(
                IncomingEmail.to_email.contains(accountEmail),
                IncomingEmail.mail_from.contains(accountEmail),
                IncomingEmail.rcpt_to.contains(accountEmail),
            )
        )
    if name:
        stmt = stmt.where(IncomingEmail.name.contains(name))
    if subject:
        stmt = stmt.where(IncomingEmail.subject.contains(subject))
    if emailId:
        stmt = stmt.where(IncomingEmail.id > emailId) if timeSort else stmt.where(IncomingEmail.id < emailId)
    order_field = IncomingEmail.id.asc() if timeSort else IncomingEmail.id.desc()
    filtered_rows = db.execute(stmt.order_by(order_field)).scalars().all()
    items = filtered_rows[:size]
    total = len(filtered_rows)
    latest = email_payload(items[0], user.email) if items else {"emailId": 0}
    return ok({"list": [email_payload(item, item.mail_from or "") for item in items], "total": total, "latestEmail": latest})


@router.get("/role/permTree")
def role_perm_tree(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    return ok(permission_tree_payload())


@router.get("/role/list")
def role_list_api(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    roles = db.execute(select(Role).order_by(Role.sort.asc(), Role.role_id.asc())).scalars().all()
    return ok([role_payload(role) for role in roles])


@router.get("/role/selectUse")
def role_select_use(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    roles = db.execute(select(Role).order_by(Role.sort.asc(), Role.role_id.asc())).scalars().all()
    return ok([{"roleId": role.role_id, "name": role.name} for role in roles])


@router.post("/role/add")
def role_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    role = Role(
        name=payload.get("name") or "",
        description=payload.get("description") or "",
        sort=int(payload.get("sort") or 0),
        is_default=0,
        perm_ids=json.dumps(payload.get("permIds") or []),
        send_type=payload.get("sendType") or "ban",
        send_count=int(payload.get("sendCount") or 0),
        account_count=int(payload.get("accountCount") or 0),
        ban_email=json.dumps(payload.get("banEmail") or []),
        avail_domain=json.dumps(payload.get("availDomain") or []),
    )
    db.add(role)
    db.commit()
    return ok()


@router.put("/role/set")
def role_set(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    role = db.execute(select(Role).where(Role.role_id == int(payload.get("roleId", 0)))).scalar_one_or_none()
    if role is None:
        return fail("role not found", 404)
    role.name = payload.get("name") or role.name
    role.description = payload.get("description") or role.description
    role.sort = int(payload.get("sort") or role.sort)
    role.perm_ids = json.dumps(payload.get("permIds") or json.loads(role.perm_ids or "[]"))
    role.send_type = payload.get("sendType") or role.send_type
    role.send_count = int(payload.get("sendCount") or role.send_count)
    role.account_count = int(payload.get("accountCount") or role.account_count)
    role.ban_email = json.dumps(payload.get("banEmail") or json.loads(role.ban_email or "[]"))
    role.avail_domain = json.dumps(payload.get("availDomain") or json.loads(role.avail_domain or "[]"))
    db.commit()
    return ok()


@router.put("/role/setDefault")
def role_set_default(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    role_id = int(payload.get("roleId", 0))
    roles = db.execute(select(Role)).scalars().all()
    for role in roles:
        role.is_default = 1 if role.role_id == role_id else 0
    db.commit()
    return ok()


@router.delete("/role/delete")
def role_delete(roleId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    role = db.execute(select(Role).where(Role.role_id == roleId)).scalar_one_or_none()
    if role is None:
        return fail("role not found", 404)
    db.delete(role)
    db.commit()
    return ok()


@router.get("/user/list")
def user_list(num: int = Query(1), size: int = Query(15), email: str | None = Query(None), status: int = Query(-1), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    stmt = select(User).order_by(User.user_id.desc())
    users = db.execute(stmt).scalars().all()
    if email:
        users = [u for u in users if email.lower() in u.email.lower()]
    if status >= 0:
        users = [u for u in users if u.status == status]
    roles = {role.role_id: role for role in db.execute(select(Role)).scalars().all()}
    rows = []
    for user in users:
        accounts = db.execute(select(Account).where(Account.user_id == user.user_id)).scalars().all()
        inbox_count = len(db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.type == 0)).scalars().all())
        send_count = len(db.execute(select(IncomingEmail).where(IncomingEmail.user_id == user.user_id, IncomingEmail.type == 1)).scalars().all())
        role = roles.get(user.type)
        rows.append({
            "userId": user.user_id,
            "email": user.email,
            "receiveEmailCount": inbox_count,
            "delReceiveEmailCount": 0,
            "sendEmailCount": send_count,
            "delSendEmailCount": 0,
            "accountCount": len(accounts),
            "delAccountCount": 0,
            "createTime": user.create_time.isoformat() if user.create_time else "",
            "status": user.status,
            "isDel": 0,
            "type": user.type,
            "sendCount": user.send_count,
            "sendAction": {"hasPerm": True, "sendType": role.send_type if role else "ban", "sendCount": role.send_count if role else 0},
            "name": user.name,
            "username": None,
            "createIp": "",
            "activeIp": "",
            "activeTime": user.create_time.isoformat() if user.create_time else "",
            "device": "",
            "os": "",
            "browser": "",
            "avatar": "",
            "trustLevel": "",
        })
    start = max((num - 1) * size, 0)
    end = start + size
    return ok({"list": rows[start:end], "total": len(rows)})


@router.post("/user/add")
def user_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    email = (payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return fail("invalid email", 400)
    if user_by_email(db, email):
        return fail("user already exists", 400)
    requested_type = payload.get("type")
    role_id = int(requested_type) if requested_type not in (None, "") else default_role_id(db)
    user = User(email=email, password_hash=hash_password(payload.get("password") or ""), name=email.split("@", 1)[0], type=role_id, status=0)
    db.add(user)
    db.flush()
    db.add(Account(email=email, name=user.name, user_id=user.user_id, sort=0))
    db.commit()
    return ok()


@router.put("/user/setPwd")
def user_set_pwd(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    user = db.execute(select(User).where(User.user_id == int(payload.get("userId", 0)))).scalar_one_or_none()
    if user is None:
        return fail("user not found", 404)
    user.password_hash = hash_password(payload.get("password") or "")
    db.commit()
    return ok()


@router.put("/user/setStatus")
def user_set_status(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    user = db.execute(select(User).where(User.user_id == int(payload.get("userId", 0)))).scalar_one_or_none()
    if user is None:
        return fail("user not found", 404)
    user.status = int(payload.get("status", 0))
    db.commit()
    return ok()


@router.put("/user/setType")
def user_set_type(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    user = db.execute(select(User).where(User.user_id == int(payload.get("userId", 0)))).scalar_one_or_none()
    if user is None:
        return fail("user not found", 404)
    user.type = int(payload.get("type", 1))
    db.commit()
    return ok()


@router.delete("/user/delete")
def user_delete(userIds: str = Query(""), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    ids = [int(item) for item in userIds.split(",") if item.strip().isdigit()]
    rows = db.execute(select(User).where(User.user_id.in_(ids))).scalars().all()
    for row in rows:
        if row.type != 0:
            db.delete(row)
    db.commit()
    return ok()


@router.put("/user/resetSendCount")
def user_reset_send_count(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    user = db.execute(select(User).where(User.user_id == int(payload.get("userId", 0)))).scalar_one_or_none()
    if user is None:
        return fail("user not found", 404)
    user.send_count = 0
    db.commit()
    return ok()


@router.put("/user/restore")
def user_restore(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    user = db.execute(select(User).where(User.user_id == int(payload.get("userId", 0)))).scalar_one_or_none()
    if user is None:
        return fail("user not found", 404)
    user.status = 0
    db.commit()
    return ok()


@router.get("/user/allAccount")
def user_all_account(userId: int = Query(...), num: int = Query(1), size: int = Query(10), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    accounts = db.execute(select(Account).where(Account.user_id == userId).order_by(Account.account_id.desc())).scalars().all()
    start = max((num - 1) * size, 0)
    end = start + size
    rows = [{"accountId": item.account_id, "email": item.email, "isDel": item.is_del} for item in accounts]
    return ok({"list": rows[start:end], "total": len(rows)})


@router.delete("/user/deleteAccount")
def user_delete_account(accountId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    account = db.execute(select(Account).where(Account.account_id == accountId)).scalar_one_or_none()
    if account is None:
        return fail("account not found", 404)
    account.is_del = 1
    db.commit()
    return ok()


@router.get("/regKey/list")
def reg_key_list(code: str | None = Query(None), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    roles = {role.role_id: role for role in db.execute(select(Role)).scalars().all()}
    rows = db.execute(select(RegKey).order_by(RegKey.reg_key_id.desc())).scalars().all()
    if code:
        rows = [row for row in rows if code in row.code]
    return ok([{"regKeyId": row.reg_key_id, "code": row.code, "count": row.count, "roleName": roles.get(row.role_id).name if roles.get(row.role_id) else "User", "expireTime": row.expire_time.isoformat() if row.expire_time else None} for row in rows])


@router.post("/regKey/add")
def reg_key_add(payload: dict = Body(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    row = RegKey(code=payload.get("code") or "", count=int(payload.get("count") or 1), role_id=int(payload.get("roleId") or 1), expire_time=None)
    db.add(row)
    db.commit()
    return ok()


@router.delete("/regKey/delete")
def reg_key_delete(regKeyIds: str = Query(""), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    ids = [int(item) for item in regKeyIds.split(",") if item.strip().isdigit()]
    rows = db.execute(select(RegKey).where(RegKey.reg_key_id.in_(ids))).scalars().all()
    for row in rows:
        db.delete(row)
    db.commit()
    return ok()


@router.delete("/regKey/clearNotUse")
def reg_key_clear_not_use(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    rows = db.execute(select(RegKey).where(RegKey.count <= 0)).scalars().all()
    for row in rows:
        db.delete(row)
    db.commit()
    return ok()


@router.get("/regKey/history")
def reg_key_history(regKeyId: int = Query(...), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    require_user(db, authorization)
    rows = db.execute(select(RegKeyUser).where(RegKeyUser.reg_key_id == regKeyId).order_by(RegKeyUser.id.desc())).scalars().all()
    return ok([{"email": row.email, "createTime": row.create_time.isoformat() if row.create_time else ""} for row in rows])


@router.get("/allEmail/latest")
def all_email_latest(emailId: int = Query(0), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
    stmt = select(IncomingEmail).where(IncomingEmail.id > emailId, IncomingEmail.type == 0, IncomingEmail.is_del == 0)
    items = db.execute(stmt.order_by(IncomingEmail.id.desc()).limit(20)).scalars().all()
    return ok([email_payload(item, item.mail_from or "") for item in items])


@router.get("/analysis/echarts")
def analysis_echarts(db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
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
    return ok({
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
        "receiveRatio": {"nameRatio": [{"name": key, "total": value} for key, value in sorted(sender_counter.items(), key=lambda item: item[1], reverse=True)[:10]]},
        "userDayCount": [{"date": key, "total": value} for key, value in sorted(user_day.items())],
        "emailDayCount": {
            "receiveDayCount": [{"date": key, "total": value} for key, value in sorted(receive_day.items())],
            "sendDayCount": [{"date": key, "total": value} for key, value in sorted(send_day.items())],
        },
        "daySendTotal": day_send_total,
    })


@router.delete("/allEmail/delete")
def all_email_delete(emailIds: str = Query(""), db: Session = Depends(get_db), authorization: str | None = Header(default=None, alias="Authorization")):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
    ids = [int(item) for item in emailIds.split(",") if item.strip().isdigit()]
    rows = db.execute(select(IncomingEmail).where(IncomingEmail.id.in_(ids))).scalars().all()
    for row in rows:
        row.is_del = 1
    db.commit()
    return ok()


@router.delete("/allEmail/batchDelete")
def all_email_batch_delete(
    sendName: str | None = Query(None),
    subject: str | None = Query(None),
    sendEmail: str | None = Query(None),
    toEmail: str | None = Query(None),
    startTime: str | None = Query(None),
    endTime: str | None = Query(None),
    type: str = Query("eq"),
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    user = require_user(db, authorization)
    if user.type != 0:
        return fail("forbidden", 403)
    start_dt = _parse_dt(startTime)
    end_dt = _parse_dt(endTime)
    rows = db.execute(select(IncomingEmail)).scalars().all()
    for row in rows:
        if not _match_text(row.name, sendName, type):
            continue
        if not _match_text(row.subject, subject, type):
            continue
        if not _match_text(row.mail_from, sendEmail, type):
            continue
        if not _match_text(row.to_email, toEmail, type):
            continue
        if start_dt and row.created_at < start_dt:
            continue
        if end_dt and row.created_at >= end_dt:
            continue
        row.is_del = 1
    db.commit()
    return ok()
