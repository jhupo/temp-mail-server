"""cloud mail compatibility tables

Revision ID: 20260410_000002
Revises: 20260410_000001
Create Date: 2026-04-10 19:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_000002"
down_revision = "20260410_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"], unique=False)
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)

    op.add_column("mailboxes", sa.Column("user_id", sa.Integer(), nullable=True))
    op.add_column("mailboxes", sa.Column("name", sa.String(length=128), nullable=True))
    op.add_column("mailboxes", sa.Column("all_receive", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mailboxes", sa.Column("sort", sa.Integer(), nullable=False, server_default="0"))
    if not is_sqlite:
        op.create_foreign_key("fk_mailboxes_user_id_users", "mailboxes", "users", ["user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_mailboxes_user_id", "mailboxes", ["user_id"], unique=False)
    op.create_index("ix_mailboxes_sort", "mailboxes", ["sort"], unique=False)

    op.add_column("messages", sa.Column("is_read", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("messages", sa.Column("is_star", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.drop_column("messages", "is_star")
    op.drop_column("messages", "is_read")

    op.drop_index("ix_mailboxes_sort", table_name="mailboxes")
    op.drop_index("ix_mailboxes_user_id", table_name="mailboxes")
    if not is_sqlite:
        op.drop_constraint("fk_mailboxes_user_id_users", "mailboxes", type_="foreignkey")
    op.drop_column("mailboxes", "sort")
    op.drop_column("mailboxes", "all_receive")
    op.drop_column("mailboxes", "name")
    op.drop_column("mailboxes", "user_id")

    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
