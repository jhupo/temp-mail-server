from __future__ import annotations

import base64
import mimetypes
import secrets
from pathlib import Path

from app.config import settings


def ensure_object_storage_dir() -> Path:
    path = settings.object_storage_path
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_base64_object(content: str, *, filename: str | None = None, prefix: str = "objects") -> tuple[str, int, str | None]:
    storage_root = ensure_object_storage_dir()
    raw = content
    content_type = None
    if content.startswith("data:") and ";base64," in content:
        header, raw = content.split(",", 1)
        content_type = header[5:].split(";", 1)[0] or None
    payload = base64.b64decode(raw)
    suffix = Path(filename or "").suffix if filename else ""
    key = f"{prefix}/{secrets.token_hex(16)}{suffix}"
    target = storage_root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    if content_type is None and filename:
        content_type = mimetypes.guess_type(filename)[0]
    return key, len(payload), content_type


def resolve_object_path(key: str) -> Path:
    normalized = key.lstrip("/")
    if normalized.startswith("oss/"):
        normalized = normalized[4:]
    return ensure_object_storage_dir() / normalized
