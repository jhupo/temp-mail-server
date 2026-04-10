"""initial schema

Revision ID: 20260410_000001
Revises:
Create Date: 2026-04-10 17:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailboxes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(length=320), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mailboxes_address", "mailboxes", ["address"], unique=True)
    op.create_index("ix_mailboxes_domain", "mailboxes", ["domain"], unique=False)
    op.create_index("ix_mailboxes_expires_at", "mailboxes", ["expires_at"], unique=False)
    op.create_index("ix_mailboxes_token_hash", "mailboxes", ["token_hash"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mailbox_id", sa.Integer(), nullable=False),
        sa.Column("from_addr", sa.String(length=320), nullable=True),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("text_body", sa.Text(), nullable=True),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("raw_headers", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mailboxes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_mailbox_id", "messages", ["mailbox_id"], unique=False)
    op.create_index("ix_messages_received_at", "messages", ["received_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_messages_received_at", table_name="messages")
    op.drop_index("ix_messages_mailbox_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_mailboxes_token_hash", table_name="mailboxes")
    op.drop_index("ix_mailboxes_expires_at", table_name="mailboxes")
    op.drop_index("ix_mailboxes_domain", table_name="mailboxes")
    op.drop_index("ix_mailboxes_address", table_name="mailboxes")
    op.drop_table("mailboxes")
