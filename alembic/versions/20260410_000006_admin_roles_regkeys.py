"""admin roles and regkeys

Revision ID: 20260410_000006
Revises: 20260410_000005
Create Date: 2026-04-10 20:45:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_000006"
down_revision = "20260410_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("type", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("perm_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("send_type", sa.String(length=16), nullable=False, server_default="ban"),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("account_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ban_email_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("avail_domain_json", sa.Text(), nullable=False, server_default="[]"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "reg_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("expire_time", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reg_keys_code", "reg_keys", ["code"], unique=True)

    op.create_table(
        "reg_key_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reg_key_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["reg_key_id"], ["reg_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reg_key_history_reg_key_id", "reg_key_history", ["reg_key_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reg_key_history_reg_key_id", table_name="reg_key_history")
    op.drop_table("reg_key_history")
    op.drop_index("ix_reg_keys_code", table_name="reg_keys")
    op.drop_table("reg_keys")
    op.drop_table("roles")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "type")
    op.drop_column("users", "username")
