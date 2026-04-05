from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Mailbox, Message
from app.security import generate_token, hash_token, verify_token
from app.utils import is_valid_local_part, make_random_local_part, normalize_address, split_address


def create_mailbox(
    db: Session,
    *,
    domain: str,
    local_part: str | None,
    ttl_minutes: int | None,
) -> tuple[Mailbox, str]:
    domain = domain.lower()
    ttl = ttl_minutes or settings.mailbox_default_ttl_minutes

    if local_part:
        if not is_valid_local_part(local_part):
            raise ValueError("invalid local_part format")
        desired_local = local_part.lower()
    else:
        desired_local = None

    for _ in range(20):
        final_local = desired_local or make_random_local_part()
        address = normalize_address(f"{final_local}@{domain}")
        existing = db.execute(select(Mailbox).where(Mailbox.address == address)).scalar_one_or_none()
        if existing is None:
            token = generate_token()
            mailbox = Mailbox(
                address=address,
                domain=domain,
                token_hash=hash_token(token),
                expires_at=datetime.utcnow() + timedelta(minutes=ttl),
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
                    if existing.expires_at <= datetime.utcnow():
                        token = generate_token()
                        existing.token_hash = hash_token(token)
                        existing.expires_at = datetime.utcnow() + timedelta(minutes=ttl)
                        db.commit()
                        db.refresh(existing)
                        return existing, token
                    raise ValueError("mailbox already exists and not expired")
                continue

        if desired_local:
            if existing.expires_at <= datetime.utcnow():
                token = generate_token()
                existing.token_hash = hash_token(token)
                existing.expires_at = datetime.utcnow() + timedelta(minutes=ttl)
                db.commit()
                db.refresh(existing)
                return existing, token
            raise ValueError("mailbox already exists and not expired")

    raise ValueError("failed to create unique local part")


def get_mailbox_by_address(db: Session, address: str) -> Mailbox | None:
    return db.execute(select(Mailbox).where(Mailbox.address == normalize_address(address))).scalar_one_or_none()


def get_mailbox_by_token(db: Session, token: str) -> Mailbox | None:
    if not token:
        return None
    candidates = db.execute(select(Mailbox).where(Mailbox.token_hash.is_not(None))).scalars().all()
    for mailbox in candidates:
        if mailbox.expires_at <= datetime.utcnow():
            continue
        if verify_token(token, mailbox.token_hash):
            return mailbox
    return None


def authorize_mailbox(db: Session, address: str, token: str) -> Mailbox:
    mailbox = get_mailbox_by_address(db, address)
    if mailbox is None:
        raise LookupError("mailbox not found")
    if mailbox.expires_at <= datetime.utcnow():
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
) -> None:
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
            expires_at=datetime.utcnow() + timedelta(minutes=settings.mailbox_default_ttl_minutes),
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
    )
    mailbox.last_message_at = datetime.utcnow()
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise


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
    now = datetime.utcnow()
    expired_ids = db.execute(select(Mailbox.id).where(Mailbox.expires_at <= now)).scalars().all()
    if not expired_ids:
        return 0
    db.execute(delete(Mailbox).where(Mailbox.id.in_(expired_ids)))
    db.commit()
    return len(expired_ids)
