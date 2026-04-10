"""app settings json store

Revision ID: 20260410_000004
Revises: 20260410_000003
Create Date: 2026-04-10 19:50:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_000004"
down_revision = "20260410_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
