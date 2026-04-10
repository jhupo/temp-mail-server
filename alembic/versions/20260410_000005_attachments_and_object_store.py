"""attachments and object store

Revision ID: 20260410_000005
Revises: 20260410_000004
Create Date: 2026-04-10 20:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_000005"
down_revision = "20260410_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachments_message_id", "attachments", ["message_id"], unique=False)
    op.create_index("ix_attachments_storage_key", "attachments", ["storage_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_attachments_storage_key", table_name="attachments")
    op.drop_index("ix_attachments_message_id", table_name="attachments")
    op.drop_table("attachments")
