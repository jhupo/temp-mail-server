from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS resend_token TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS no_recipient INTEGER DEFAULT 1 NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS secret_key VARCHAR(255) DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS email_prefix_filter TEXT DEFAULT '[]' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS resend_tokens TEXT DEFAULT '{}' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS bucket VARCHAR(255) DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS endpoint VARCHAR(255) DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS region VARCHAR(255) DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS s3_access_key TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS s3_secret_key TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS force_path_style INTEGER DEFAULT 1 NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS storage_type VARCHAR(32) DEFAULT 'postgres' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS tg_bot_status INTEGER DEFAULT 1 NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS tg_bot_token TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS custom_domain VARCHAR(255) DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS tg_chat_id TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS tg_msg_from VARCHAR(32) DEFAULT 'show' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS tg_msg_text VARCHAR(32) DEFAULT 'show' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS tg_msg_to VARCHAR(32) DEFAULT 'show' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS forward_status INTEGER DEFAULT 1 NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS forward_email TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS rule_type INTEGER DEFAULT 0 NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS rule_email TEXT DEFAULT '' NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS add_verify_count INTEGER DEFAULT 1 NOT NULL"))
        conn.execute(text("ALTER TABLE setting ADD COLUMN IF NOT EXISTS reg_verify_count INTEGER DEFAULT 1 NOT NULL"))
