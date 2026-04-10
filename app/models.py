from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.time_utils import utcnow


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    send_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    mailboxes: Mapped[list["Mailbox"]] = relationship(back_populates="user")
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class Mailbox(Base):
    __tablename__ = "mailboxes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    address: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    domain: Mapped[str] = mapped_column(String(253), index=True)
    token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    all_receive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User | None] = relationship(back_populates="mailboxes")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="mailbox",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("mailboxes.id", ondelete="CASCADE"),
        index=True,
    )
    from_addr: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_headers: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    direction: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_star: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)

    mailbox: Mapped[Mailbox] = relationship(back_populates="messages")
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    message: Mapped[Message] = relationship(back_populates="attachments")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_default: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    perm_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    send_type: Mapped[str] = mapped_column(String(16), nullable=False, default="ban")
    send_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    account_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ban_email_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    avail_domain_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class RegKey(Base):
    __tablename__ = "reg_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, nullable=False)
    expire_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class RegKeyHistory(Base):
    __tablename__ = "reg_key_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reg_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("reg_keys.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
