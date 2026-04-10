"""sent mail support

Revision ID: 20260410_000003
Revises: 20260410_000002
Create Date: 2026-04-10 19:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_000003"
down_revision = "20260410_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("recipient_json", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("direction", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("messages", sa.Column("status", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("messages", "status")
    op.drop_column("messages", "direction")
    op.drop_column("messages", "recipient_json")
