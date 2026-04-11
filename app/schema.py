from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS resend_token TEXT DEFAULT '' NOT NULL"))
