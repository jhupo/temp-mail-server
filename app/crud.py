from datetime import timedelta
import json

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting, Attachment, Mailbox, Message, RegKey, RegKeyHistory, Role, User, UserSession
from app.security import generate_token, hash_password, hash_token, verify_password, verify_token
from app.storage import save_base64_object
from app.time_utils import ensure_utc, utcnow
from app.utils import is_valid_local_part, make_random_local_part, normalize_address, split_address


def create_mailbox(
    db: Session,
    *,
    domain: str,
    local_part: str | None,
    ttl_minutes: int | None,
    user_id: int | None = None,
    name: str | None = None,
) -> tuple[Mailbox, str]:
    domain = domain.lower()
    ttl = ttl_minutes or settings.mailbox_default_ttl_minutes

    if local_part:
        if not is_valid_local_part(local_part):
            raise ValueError("invalid local_part format")
        desired_local = local_part.lower()
    else:
        desired_local = None

    def _issue_token(mailbox: Mailbox) -> tuple[Mailbox, str]:
        token = generate_token()
        mailbox.token_hash = hash_token(token)
        mailbox.expires_at = utcnow() + timedelta(minutes=ttl)
        db.commit()
        db.refresh(mailbox)
        return mailbox, token

    for _ in range(20):
        final_local = desired_local or make_random_local_part()
        address = normalize_address(f"{final_local}@{domain}")
        existing = db.execute(select(Mailbox).where(Mailbox.address == address)).scalar_one_or_none()
        if existing is None:
            token = generate_token()
            mailbox = Mailbox(
                user_id=user_id,
                address=address,
                domain=domain,
                token_hash=hash_token(token),
                name=name or final_local,
                sort=int(utcnow().timestamp()),
                expires_at=utcnow() + timedelta(minutes=ttl),
            )
            db.add(mailbox)
            try:
                db.commit()
                db.refresh(mailbox)
                return mailbox, token
            except IntegrityError:
                db.rollback()
                existing = db.execute(select(Mailbox).where(Mailbox.address == address)).scalar_one_or_none()
                if existing is None:
                    if desired_local:
                        continue
                    continue
                if desired_local:
                    if ensure_utc(existing.expires_at) <= utcnow() or existing.token_hash is None:
                        if user_id is not None:
                            existing.user_id = user_id
                            existing.name = name or desired_local
                        return _issue_token(existing)
                    raise ValueError("mailbox already exists and not expired")
                continue

        if desired_local:
            if ensure_utc(existing.expires_at) <= utcnow() or existing.token_hash is None:
                if user_id is not None:
                    existing.user_id = user_id
                    existing.name = name or desired_local
                return _issue_token(existing)
            raise ValueError("mailbox already exists and not expired")

    raise ValueError("failed to create unique local part")


def get_mailbox_by_address(db: Session, address: str) -> Mailbox | None:
    return db.execute(select(Mailbox).where(Mailbox.address == normalize_address(address))).scalar_one_or_none()


def get_mailboxes_by_user(db: Session, user_id: int) -> list[Mailbox]:
    return (
        db.execute(
            select(Mailbox)
            .where(Mailbox.user_id == user_id)
            .order_by(Mailbox.sort.desc(), Mailbox.id.asc())
        )
        .scalars()
        .all()
    )


def get_mailbox_by_token(db: Session, token: str) -> Mailbox | None:
    if not token:
        return None
    token_digest = hash_token(token)
    mailbox = (
        db.execute(
            select(Mailbox).where(
                Mailbox.token_hash == token_digest,
                Mailbox.expires_at > utcnow(),
            )
        )
        .scalars()
        .first()
    )
    if mailbox is None:
        return None
    if not verify_token(token, mailbox.token_hash):
        return None
    return mailbox


def authorize_mailbox(db: Session, address: str, token: str) -> Mailbox:
    mailbox = get_mailbox_by_address(db, address)
    if mailbox is None:
        raise LookupError("mailbox not found")
    if ensure_utc(mailbox.expires_at) <= utcnow():
        raise PermissionError("mailbox expired")
    if not verify_token(token, mailbox.token_hash):
        raise PermissionError("invalid token")
    return mailbox


def save_incoming_message(
    db: Session,
    *,
    recipient: str,
    from_addr: str | None,
    subject: str | None,
    text_body: str | None,
    html_body: str | None,
    raw_headers: str | None,
) -> tuple[Mailbox, Message] | None:
    address = normalize_address(recipient)
    _, domain = split_address(address)
    mailbox = get_mailbox_by_address(db, address)
    if mailbox is None:
        if not settings.allow_auto_create_on_smtp:
            return
        mailbox = Mailbox(
            address=address,
            domain=domain,
            token_hash=None,
            name=address.split("@", 1)[0],
            sort=int(utcnow().timestamp()),
            expires_at=utcnow() + timedelta(minutes=settings.mailbox_default_ttl_minutes),
        )
        db.add(mailbox)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            mailbox = get_mailbox_by_address(db, address)
            if mailbox is None:
                raise

    message = Message(
        mailbox_id=mailbox.id,
        from_addr=from_addr,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        raw_headers=raw_headers,
        recipient_json=json.dumps([{"address": mailbox.address}]),
        direction=0,
        status=0,
    )
    mailbox.last_message_at = utcnow()
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(message)
    return mailbox, message


def get_latest_message(db: Session, mailbox_id: int) -> Message | None:
    return (
        db.execute(
            select(Message)
            .where(Message.mailbox_id == mailbox_id)
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_messages(db: Session, mailbox_id: int, limit: int = 20) -> list[Message]:
    safe_limit = max(1, min(limit, 100))
    return (
        db.execute(
            select(Message)
            .where(Message.mailbox_id == mailbox_id)
            .order_by(Message.received_at.desc(), Message.id.desc())
            .limit(safe_limit)
        )
        .scalars()
        .all()
    )


def get_message_by_id(db: Session, mailbox_id: int, message_id: int) -> Message | None:
    return (
        db.execute(
            select(Message)
            .where(Message.mailbox_id == mailbox_id, Message.id == message_id)
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_message_by_id_admin(db: Session, message_id: int) -> tuple[Mailbox, Message] | None:
    row = (
        db.execute(
            select(Mailbox, Message)
            .join(Message, Message.mailbox_id == Mailbox.id)
            .where(Message.id == message_id)
            .limit(1)
        )
        .first()
    )
    if row is None:
        return None
    return row[0], row[1]


def get_messages_admin(
    db: Session,
    *,
    address: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[Mailbox, Message]]:
    safe_limit = max(1, min(limit, 100))
    safe_offset = max(0, offset)
    stmt = (
        select(Mailbox, Message)
        .join(Message, Message.mailbox_id == Mailbox.id)
        .order_by(Message.received_at.desc(), Message.id.desc())
        .limit(safe_limit)
        .offset(safe_offset)
    )
    if address:
        stmt = stmt.where(Mailbox.address == normalize_address(address))
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def cleanup_expired(db: Session) -> int:
    now = utcnow()
    expired_ids = db.execute(select(Mailbox.id).where(Mailbox.expires_at <= now)).scalars().all()
    if not expired_ids:
        return 0
    db.execute(delete(Mailbox).where(Mailbox.id.in_(expired_ids)))
    db.commit()
    return len(expired_ids)


def create_user_with_mailbox(db: Session, *, email: str, password: str) -> tuple[User, Mailbox, str]:
    address = normalize_address(email)
    local_part, domain = split_address(address)
    if get_user_by_email(db, address) is not None:
        raise ValueError("user already exists")
    user = User(
        email=address,
        username=None,
        password_hash=hash_password(password),
        name=local_part,
        type=1,
    )
    db.add(user)
    db.flush()
    mailbox, _mailbox_token = create_mailbox(
        db,
        domain=domain,
        local_part=local_part,
        ttl_minutes=None,
        user_id=user.id,
        name=local_part,
    )
    token = create_user_session(db, user.id)
    return user, mailbox, token


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(select(User).where(User.email == normalize_address(email))).scalar_one_or_none()


def get_user_by_login(db: Session, login: str) -> User | None:
    normalized = normalize_address(login)
    return (
        db.execute(select(User).where((User.email == normalized) | (User.username == login)))
        .scalars()
        .first()
    )


def create_user_session(db: Session, user_id: int) -> str:
    token = generate_token()
    session = UserSession(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(days=30),
    )
    db.add(session)
    db.commit()
    return token


def get_user_by_session_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    token_hash = hash_token(token)
    session = (
        db.execute(
            select(UserSession)
            .where(UserSession.token_hash == token_hash, UserSession.expires_at > utcnow())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if session is None:
        return None
    return db.execute(select(User).where(User.id == session.user_id)).scalar_one_or_none()


def delete_user_session(db: Session, token: str | None) -> None:
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    db.commit()


def authenticate_user(db: Session, email: str, password: str) -> str:
    user = get_user_by_login(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise ValueError("invalid email or password")
    return create_user_session(db, user.id)


def get_primary_mailbox(db: Session, user_id: int) -> Mailbox | None:
    return (
        db.execute(
            select(Mailbox)
            .where(Mailbox.user_id == user_id)
            .order_by(Mailbox.sort.desc(), Mailbox.id.asc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def add_account_for_user(db: Session, *, user: User, email: str) -> Mailbox:
    address = normalize_address(email)
    local_part, domain = split_address(address)
    mailbox, _token = create_mailbox(
        db,
        domain=domain,
        local_part=local_part,
        ttl_minutes=None,
        user_id=user.id,
        name=local_part,
    )
    return mailbox


def rename_account(db: Session, *, user_id: int, account_id: int, name: str) -> None:
    mailbox = db.execute(select(Mailbox).where(Mailbox.id == account_id, Mailbox.user_id == user_id)).scalar_one_or_none()
    if mailbox is None:
        raise LookupError("account not found")
    mailbox.name = name
    db.commit()


def set_account_all_receive(db: Session, *, user_id: int, account_id: int) -> Mailbox:
    accounts = get_mailboxes_by_user(db, user_id)
    target: Mailbox | None = None
    for account in accounts:
        if account.id == account_id:
            target = account
            account.all_receive = 0 if account.all_receive else 1
        else:
            account.all_receive = 0
    if target is None:
        raise LookupError("account not found")
    db.commit()
    return target


def set_account_as_top(db: Session, *, user_id: int, account_id: int) -> None:
    mailbox = db.execute(select(Mailbox).where(Mailbox.id == account_id, Mailbox.user_id == user_id)).scalar_one_or_none()
    if mailbox is None:
        raise LookupError("account not found")
    mailbox.sort = int(utcnow().timestamp())
    db.commit()


def delete_account(db: Session, *, user_id: int, account_id: int) -> None:
    mailbox = db.execute(select(Mailbox).where(Mailbox.id == account_id, Mailbox.user_id == user_id)).scalar_one_or_none()
    if mailbox is None:
        raise LookupError("account not found")
    db.delete(mailbox)
    db.commit()


def list_emails_for_account(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    all_receive: int,
    cursor_id: int = 0,
    size: int = 50,
    starred_only: bool = False,
    filters: dict | None = None,
) -> tuple[list[Message], int]:
    safe_size = max(1, min(size, 100))
    account_ids = [account_id]
    if all_receive:
        account_ids = [mailbox.id for mailbox in get_mailboxes_by_user(db, user_id)]
    stmt = select(Message).join(Mailbox, Mailbox.id == Message.mailbox_id).where(Mailbox.id.in_(account_ids))
    filters = filters or {}
    message_type = filters.get("type")
    if message_type is not None:
        stmt = stmt.where(Message.direction == message_type)
    if starred_only:
        stmt = stmt.where(Message.is_star == 1)
    if cursor_id:
        stmt = stmt.where(Message.id < cursor_id)
    stmt = stmt.order_by(Message.id.desc()).limit(safe_size)
    items = db.execute(stmt).scalars().all()
    total_stmt = select(Message).join(Mailbox, Mailbox.id == Message.mailbox_id).where(Mailbox.id.in_(account_ids))
    if message_type is not None:
        total_stmt = total_stmt.where(Message.direction == message_type)
    if starred_only:
        total_stmt = total_stmt.where(Message.is_star == 1)
    total = len(db.execute(total_stmt).scalars().all())
    return items, total


def list_latest_emails(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    all_receive: int,
    email_id: int,
) -> list[Message]:
    account_ids = [account_id]
    if all_receive:
        account_ids = [mailbox.id for mailbox in get_mailboxes_by_user(db, user_id)]
    stmt = (
        select(Message)
        .join(Mailbox, Mailbox.id == Message.mailbox_id)
        .where(Mailbox.id.in_(account_ids), Message.id > email_id)
        .order_by(Message.id.desc())
    )
    return db.execute(stmt).scalars().all()


def create_sent_email(
    db: Session,
    *,
    user_id: int,
    account_id: int,
    send_email: str,
    sender_name: str,
    subject: str,
    html_body: str | None,
    text_body: str | None,
    receive_emails: list[str],
    attachments: list[dict] | None = None,
    status: int = 2,
) -> Message:
    mailbox = db.execute(select(Mailbox).where(Mailbox.id == account_id, Mailbox.user_id == user_id)).scalar_one_or_none()
    if mailbox is None:
        raise LookupError("account not found")
    message = Message(
        mailbox_id=mailbox.id,
        from_addr=send_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        raw_headers="",
        recipient_json=json.dumps([{"address": item} for item in receive_emails]),
        direction=1,
        status=status,
        is_read=1,
    )
    db.add(message)
    db.flush()
    for item in attachments or []:
        if not item.get("content") or not item.get("filename"):
            continue
        storage_key, size, content_type = save_base64_object(
            item["content"],
            filename=item.get("filename"),
            prefix="attachments",
        )
        db.add(
            Attachment(
                message_id=message.id,
                storage_key=storage_key,
                filename=item.get("filename", "attachment"),
                content_type=item.get("contentType") or content_type,
                size=item.get("size") or size,
            )
        )
    db.commit()
    db.refresh(message)
    return message


def serialize_attachment_rows(attachments: list[Attachment]) -> list[dict]:
    return [
        {
            "attId": item.id,
            "filename": item.filename,
            "key": f"/oss/{item.storage_key}",
            "size": item.size,
            "contentType": item.content_type,
        }
        for item in attachments
    ]


def mark_messages_read(db: Session, *, user_id: int, email_ids: list[int]) -> None:
    if not email_ids:
        return
    messages = (
        db.execute(
            select(Message)
            .join(Mailbox, Mailbox.id == Message.mailbox_id)
            .where(Message.id.in_(email_ids), Mailbox.user_id == user_id)
        )
        .scalars()
        .all()
    )
    for message in messages:
        message.is_read = 1
    db.commit()


def delete_messages(db: Session, *, user_id: int, email_ids: list[int]) -> None:
    if not email_ids:
        return
    db.execute(
        delete(Message).where(
            Message.id.in_(
                select(Message.id)
                .join(Mailbox, Mailbox.id == Message.mailbox_id)
                .where(Mailbox.user_id == user_id, Message.id.in_(email_ids))
            )
        )
    )
    db.commit()


def set_star_state(db: Session, *, user_id: int, email_id: int, is_star: int) -> None:
    message = (
        db.execute(
            select(Message)
            .join(Mailbox, Mailbox.id == Message.mailbox_id)
            .where(Message.id == email_id, Mailbox.user_id == user_id)
            .limit(1)
        )
        .scalars()
        .first()
    )
    if message is None:
        raise LookupError("email not found")
    message.is_star = is_star
    db.commit()


def list_all_emails(
    db: Session,
    *,
    cursor_id: int = 0,
    size: int = 50,
    filters: dict | None = None,
) -> tuple[list[tuple[Mailbox, Message]], int]:
    safe_size = max(1, min(size, 100))
    filters = filters or {}
    stmt = select(Mailbox, Message).join(Message, Message.mailbox_id == Mailbox.id)
    stmt = _apply_all_email_filters(stmt, filters)
    if cursor_id:
        stmt = stmt.where(Message.id < cursor_id)
    stmt = stmt.order_by(Message.id.desc()).limit(safe_size)
    rows = [(row[0], row[1]) for row in db.execute(stmt).all()]

    total_stmt = select(Mailbox, Message).join(Message, Message.mailbox_id == Mailbox.id)
    total_stmt = _apply_all_email_filters(total_stmt, filters)
    total = len(db.execute(total_stmt).all())
    return rows, total


def list_latest_all_emails(db: Session, *, email_id: int) -> list[tuple[Mailbox, Message]]:
    stmt = (
        select(Mailbox, Message)
        .join(Message, Message.mailbox_id == Mailbox.id)
        .where(Message.id > email_id)
        .order_by(Message.id.desc())
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def delete_all_emails(db: Session, *, email_ids: list[int]) -> None:
    if not email_ids:
        return
    db.execute(delete(Message).where(Message.id.in_(email_ids)))
    db.commit()


def batch_delete_all_emails(db: Session, *, filters: dict) -> None:
    stmt = select(Message.id).join(Mailbox, Mailbox.id == Message.mailbox_id)
    stmt = _apply_all_email_filters(stmt, filters)
    ids = db.execute(stmt).scalars().all()
    if not ids:
        return
    db.execute(delete(Message).where(Message.id.in_(ids)))
    db.commit()


def get_analysis_snapshot(db: Session) -> dict:
    users = db.execute(select(User)).scalars().all()
    mailboxes = db.execute(select(Mailbox)).scalars().all()
    messages = db.execute(select(Message)).scalars().all()

    receive_messages = [item for item in messages]
    send_messages: list[Message] = []

    def _day_key(value):
        dt = ensure_utc(value)
        return dt.date().isoformat() if dt else utcnow().date().isoformat()

    receive_by_day: dict[str, int] = {}
    user_by_day: dict[str, int] = {}
    sender_ratio: dict[str, int] = {}
    for user in users:
        user_by_day[_day_key(user.created_at)] = user_by_day.get(_day_key(user.created_at), 0) + 1
    for message in receive_messages:
        key = _day_key(message.received_at)
        receive_by_day[key] = receive_by_day.get(key, 0) + 1
        sender = message.from_addr or "unknown"
        sender_ratio[sender] = sender_ratio.get(sender, 0) + 1

    def _sorted_day_counts(source: dict[str, int]) -> list[dict]:
        return [{"date": key, "total": source[key]} for key in sorted(source.keys())]

    return {
        "numberCount": {
            "receiveTotal": len(receive_messages),
            "sendTotal": len(send_messages),
            "accountTotal": len(mailboxes),
            "userTotal": len(users),
            "normalReceiveTotal": len(receive_messages),
            "normalSendTotal": len(send_messages),
            "normalAccountTotal": len(mailboxes),
            "normalUserTotal": len(users),
            "delReceiveTotal": 0,
            "delSendTotal": 0,
            "delAccountTotal": 0,
            "delUserTotal": 0,
        },
        "receiveRatio": {
            "nameRatio": [{"name": key, "total": value} for key, value in sorted(sender_ratio.items(), key=lambda item: item[1], reverse=True)[:10]]
        },
        "userDayCount": _sorted_day_counts(user_by_day),
        "emailDayCount": {
            "receiveDayCount": _sorted_day_counts(receive_by_day),
            "sendDayCount": _sorted_day_counts({}),
        },
        "daySendTotal": 0,
    }


def _apply_all_email_filters(stmt, filters: dict):
    value = filters.get("type")
    if value == "delete":
        stmt = stmt.where(Message.id == -1)
    if value == "noone":
        stmt = stmt.where(Mailbox.address == "")
    if filters.get("userEmail"):
        stmt = stmt.join(User, User.id == Mailbox.user_id, isouter=True).where(User.email.contains(filters["userEmail"]))
    if filters.get("accountEmail"):
        stmt = stmt.where(Mailbox.address.contains(filters["accountEmail"]))
    if filters.get("name"):
        stmt = stmt.where(Message.from_addr.contains(filters["name"]))
    if filters.get("subject"):
        stmt = stmt.where(Message.subject.contains(filters["subject"]))
    if filters.get("sendEmail"):
        stmt = stmt.where(Message.from_addr.contains(filters["sendEmail"]))
    if filters.get("toEmail"):
        stmt = stmt.where(Mailbox.address.contains(filters["toEmail"]))
    return stmt


DEFAULT_SETTINGS = {
    "title": "Temp Mail",
    "allowedDomains": settings.allowed_domains,
    "register": 0,
    "loginDomain": 0,
    "regKey": 1,
    "addEmail": 0,
    "manyEmail": 0,
    "loginOpacity": 1,
    "background": "",
    "receive": 0,
    "autoRefresh": 10,
    "send": 1,
    "noRecipient": 1,
    "r2Domain": "",
    "storageType": "local",
    "tgBotStatus": 1,
    "forwardStatus": 1,
    "ruleType": 0,
    "registerVerify": 1,
    "addEmailVerify": 1,
    "siteKey": "",
    "secretKey": "",
    "notice": 1,
    "noticeWidth": 420,
    "noticeTitle": "",
    "noticeContent": "",
    "noticeType": "info",
    "noticeDuration": 4500,
    "noticePosition": "top-right",
    "noticeOffset": 16,
    "projectLink": 0,
    "linuxdoSwitch": 0,
    "linuxdoClientId": "",
    "linuxdoCallbackUrl": "",
    "minEmailPrefix": 1,
    "emailPrefixFilter": "",
    "regVerifyOpen": False,
    "addVerifyOpen": False,
    "resendTokens": {},
    "bucket": "",
    "endpoint": "",
    "region": "",
    "forcePathStyle": 1,
    "tgBotToken": "",
    "customDomain": "",
    "tgChatId": "",
    "tgMsgFrom": 0,
    "tgMsgText": 0,
    "tgMsgTo": 0,
    "forwardEmail": "",
    "ruleEmail": "",
    "addVerifyCount": 1,
    "regVerifyCount": 1,
    "sendMode": "record",
    "smtpHost": "",
    "smtpPort": 587,
    "smtpUsername": "",
    "smtpPassword": "",
    "smtpUseTls": True,
    "smtpUseSsl": False,
    "smtpFromEmail": "",
    "certDomain": "",
    "certEmail": "",
    "certAutoRenew": 0,
    "certStatus": "idle",
    "certLastResult": "",
    "certLastRunAt": "",
}


def configured_domains(current: dict) -> list[str]:
    raw = current.get("allowedDomains")
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, str):
        values = raw.split(",")
    else:
        values = settings.allowed_domains
    domains: list[str] = []
    for item in values:
        domain = str(item).strip().lower()
        if domain and domain not in domains:
            domains.append(domain)
    return domains or settings.allowed_domains


def configured_primary_domain(current: dict) -> str:
    domains = configured_domains(current)
    return domains[0] if domains else settings.primary_domain


def get_app_settings(db: Session) -> dict:
    row = db.execute(select(AppSetting).where(AppSetting.id == 1)).scalar_one_or_none()
    if row is None:
        row = AppSetting(id=1, data_json=json.dumps(DEFAULT_SETTINGS), updated_at=utcnow())
        db.add(row)
        db.commit()
        return dict(DEFAULT_SETTINGS)
    current = DEFAULT_SETTINGS | json.loads(row.data_json or "{}")
    return current


ADMIN_PERM_KEYS = [
    "*",
]


USER_PERM_KEYS = [
    "account:query",
    "account:add",
    "account:delete",
    "email:delete",
    "email:send",
    "star:query",
    "my:delete",
    "all-email:query",
    "analysis:query",
    "setting:query",
]


PERM_TREE = [
    {"permId": 1, "name": "Account", "permKey": "account:query", "children": []},
    {"permId": 2, "name": "Send Email", "permKey": "email:send", "children": []},
    {"permId": 3, "name": "All Mail", "permKey": "all-email:query", "children": []},
    {"permId": 4, "name": "Analysis", "permKey": "analysis:query", "children": []},
    {"permId": 5, "name": "Settings", "permKey": "setting:query", "children": []},
    {"permId": 6, "name": "Users", "permKey": "user:query", "children": []},
    {"permId": 7, "name": "Roles", "permKey": "role:query", "children": []},
    {"permId": 8, "name": "Reg Keys", "permKey": "reg-key:query", "children": []},
]


def ensure_default_admin(db: Session) -> None:
    role = db.execute(select(Role).where(Role.id == 1)).scalar_one_or_none()
    if role is None:
        role = Role(
            id=1,
            name="User",
            description="Default user role",
            sort=1,
            is_default=1,
            perm_ids_json=json.dumps([1, 2, 3, 4, 5]),
            send_type="ban",
            send_count=0,
            account_count=0,
            ban_email_json="[]",
            avail_domain_json=json.dumps(settings.allowed_domains),
        )
        db.add(role)
        db.commit()

    admin = db.execute(select(User).where(User.username == "superadmin")).scalar_one_or_none()
    if admin is None:
        admin = User(
            email=f"superadmin@{settings.primary_domain}",
            username="superadmin",
            password_hash=hash_password("sueradmin"),
            name="superadmin",
            type=0,
            status=0,
        )
        db.add(admin)
        db.commit()


def perm_keys_for_user(user: User) -> list[str]:
    if user.type == 0:
        return ADMIN_PERM_KEYS
    return USER_PERM_KEYS


def role_list(db: Session) -> list[Role]:
    return db.execute(select(Role).order_by(Role.sort.asc(), Role.id.asc())).scalars().all()


def role_select_use(db: Session) -> list[Role]:
    return role_list(db)


def add_role(db: Session, data: dict) -> Role:
    role = Role(
        name=data.get("name", ""),
        description=data.get("description"),
        sort=int(data.get("sort", 0) or 0),
        is_default=0,
        perm_ids_json=json.dumps(data.get("permIds", [])),
        send_type=data.get("sendType", "ban"),
        send_count=int(data.get("sendCount", 0) or 0),
        account_count=int(data.get("accountCount", 0) or 0),
        ban_email_json=json.dumps(data.get("banEmail", [])),
        avail_domain_json=json.dumps(data.get("availDomain", [])),
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def update_role(db: Session, data: dict) -> None:
    role = db.execute(select(Role).where(Role.id == int(data.get("roleId", 0)))).scalar_one_or_none()
    if role is None:
        raise LookupError("role not found")
    role.name = data.get("name", role.name)
    role.description = data.get("description")
    role.sort = int(data.get("sort", role.sort) or 0)
    role.perm_ids_json = json.dumps(data.get("permIds", json.loads(role.perm_ids_json)))
    role.send_type = data.get("sendType", role.send_type)
    role.send_count = int(data.get("sendCount", role.send_count) or 0)
    role.account_count = int(data.get("accountCount", role.account_count) or 0)
    role.ban_email_json = json.dumps(data.get("banEmail", json.loads(role.ban_email_json)))
    role.avail_domain_json = json.dumps(data.get("availDomain", json.loads(role.avail_domain_json)))
    db.commit()


def delete_role_record(db: Session, role_id: int) -> None:
    role = db.execute(select(Role).where(Role.id == role_id)).scalar_one_or_none()
    if role is None:
        raise LookupError("role not found")
    db.delete(role)
    db.commit()


def set_default_role(db: Session, role_id: int) -> None:
    roles = role_list(db)
    for role in roles:
        role.is_default = 1 if role.id == role_id else 0
    db.commit()


def get_default_role(db: Session) -> Role | None:
    return db.execute(select(Role).where(Role.is_default == 1).limit(1)).scalars().first()


def add_user_admin(db: Session, data: dict) -> User:
    email = normalize_address(data["email"])
    local_part, domain = split_address(email)
    if get_user_by_email(db, email):
        raise ValueError("user already exists")
    role_id = int(data.get("type", 1) or 1)
    user = User(
        email=email,
        username=None,
        password_hash=hash_password(data["password"]),
        name=local_part,
        type=role_id,
        status=0,
    )
    db.add(user)
    db.flush()
    create_mailbox(db, domain=domain, local_part=local_part, ttl_minutes=None, user_id=user.id, name=local_part)
    db.refresh(user)
    return user


def list_users_admin(db: Session, params: dict) -> tuple[list[dict], int]:
    users = db.execute(select(User).order_by(User.id.desc())).scalars().all()
    role_map = {role.id: role for role in role_list(db)}
    filtered = []
    for user in users:
        if params.get("email") and params["email"] not in user.email:
            continue
        if params.get("status", -1) not in (-1, None) and user.status != params["status"]:
            continue
        mailboxes = get_mailboxes_by_user(db, user.id)
        messages = list_emails_for_account(
            db,
            user_id=user.id,
            account_id=mailboxes[0].id if mailboxes else 0,
            all_receive=1,
            size=100,
            filters={},
        )[0] if mailboxes else []
        filtered.append(
            {
                "userId": user.id,
                "email": user.email,
                "username": user.username,
                "receiveEmailCount": len([m for m in messages if m.direction == 0]),
                "delReceiveEmailCount": 0,
                "sendEmailCount": len([m for m in messages if m.direction == 1]),
                "delSendEmailCount": 0,
                "accountCount": len(mailboxes),
                "delAccountCount": 0,
                "createTime": ensure_utc(user.created_at).isoformat() if user.created_at else "",
                "status": user.status,
                "isDel": 0,
                "type": user.type,
                "sendCount": user.send_count,
                "sendAction": {
                    "hasPerm": True,
                    "sendType": role_map.get(user.type).send_type if role_map.get(user.type) else "ban",
                    "sendCount": role_map.get(user.type).send_count if role_map.get(user.type) else 0,
                },
                "createIp": "",
                "activeIp": "",
                "activeTime": ensure_utc(user.created_at).isoformat() if user.created_at else "",
                "device": "",
                "os": "",
                "browser": "",
                "avatar": "",
                "trustLevel": "",
                "name": user.name,
            }
        )
    return filtered, len(filtered)


def set_user_password(db: Session, user_id: int, password: str) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise LookupError("user not found")
    user.password_hash = hash_password(password)
    db.commit()


def set_user_status(db: Session, user_id: int, status: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise LookupError("user not found")
    user.status = status
    db.commit()


def set_user_type(db: Session, user_id: int, user_type: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise LookupError("user not found")
    user.type = user_type
    db.commit()


def reset_user_send_count(db: Session, user_id: int) -> None:
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise LookupError("user not found")
    user.send_count = 0
    db.commit()


def delete_users_admin(db: Session, user_ids: list[int]) -> None:
    if not user_ids:
        return
    db.execute(delete(User).where(User.id.in_(user_ids), User.type != 0))
    db.commit()


def all_accounts_for_user(db: Session, user_id: int, num: int, size: int) -> tuple[list[dict], int]:
    accounts = [_compat_account_data(mailbox) for mailbox in get_mailboxes_by_user(db, user_id)]
    start = max((num - 1) * size, 0)
    end = start + size
    return accounts[start:end], len(accounts)


def _compat_account_data(mailbox: Mailbox) -> dict:
    return {"accountId": mailbox.id, "email": mailbox.address, "isDel": 0}


def add_reg_key(db: Session, data: dict) -> RegKey:
    role_id = int(data.get("roleId", 1) or 1)
    expire_time = data.get("expireTime")
    reg = RegKey(code=data["code"], count=int(data.get("count", 1) or 1), role_id=role_id, expire_time=expire_time)
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return reg


def list_reg_keys(db: Session, code: str | None = None) -> list[dict]:
    roles = {role.id: role for role in role_list(db)}
    items = db.execute(select(RegKey).order_by(RegKey.id.desc())).scalars().all()
    if code:
        items = [item for item in items if code in item.code]
    return [
        {
            "regKeyId": item.id,
            "code": item.code,
            "count": item.count,
            "roleName": roles.get(item.role_id).name if roles.get(item.role_id) else "User",
            "expireTime": ensure_utc(item.expire_time).isoformat() if item.expire_time else None,
        }
        for item in items
    ]


def delete_reg_keys(db: Session, reg_key_ids: list[int]) -> None:
    if not reg_key_ids:
        return
    db.execute(delete(RegKey).where(RegKey.id.in_(reg_key_ids)))
    db.commit()


def clear_unused_reg_keys(db: Session) -> None:
    db.execute(delete(RegKey).where(RegKey.count <= 0))
    db.commit()


def reg_key_history_list(db: Session, reg_key_id: int) -> list[dict]:
    rows = db.execute(select(RegKeyHistory).where(RegKeyHistory.reg_key_id == reg_key_id).order_by(RegKeyHistory.id.desc())).scalars().all()
    return [{"email": row.email, "createTime": ensure_utc(row.created_at).isoformat() if row.created_at else ""} for row in rows]


def update_app_settings(db: Session, patch: dict) -> dict:
    current = get_app_settings(db)
    current.update(patch)
    row = db.execute(select(AppSetting).where(AppSetting.id == 1)).scalar_one()
    row.data_json = json.dumps(current)
    row.updated_at = utcnow()
    db.commit()
    return current
