from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "user"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    send_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class UserSession(Base):
    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.user_id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Account(Base):
    __tablename__ = "account"

    account_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latest_email_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.user_id", ondelete="CASCADE"), index=True)
    all_receive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_del: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Setting(Base):
    __tablename__ = "setting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    title: Mapped[str] = mapped_column(String(255), default="Temp Mail", nullable=False)
    register: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    receive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    many_email: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    add_email: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_refresh: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    add_email_verify: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    register_verify: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    send: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    r2_domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    site_key: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    background: Mapped[str] = mapped_column(Text, default="", nullable=False)
    login_opacity: Mapped[float] = mapped_column(Integer, default=88, nullable=False)
    reg_key: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notice_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    notice_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notice_type: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notice_duration: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notice_position: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    notice_width: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    notice_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notice: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    login_domain: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_email_prefix: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    project_link: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    allowed_domains: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class IncomingEmail(Base):
    __tablename__ = "incoming_email"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("user.user_id", ondelete="SET NULL"), nullable=True, index=True)
    account_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("account.account_id", ondelete="SET NULL"), nullable=True, index=True)
    mail_from: Mapped[str | None] = mapped_column(String(320), nullable=True)
    rcpt_to: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    unread: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_del: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    type: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
