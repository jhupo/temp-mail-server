from __future__ import annotations

import json


def split_domains(raw: str | list[str] | None) -> list[str]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            items = json.loads(raw) if raw.startswith("[") else raw.split(",")
        except Exception:
            items = raw.split(",")
    else:
        items = []

    domains: list[str] = []
    for item in items:
        value = str(item).strip().lower()
        if value and value not in domains:
            domains.append(value)
    return domains


def domain_allowed(domain: str, allowed_domains: str | list[str] | None) -> bool:
    normalized = str(domain).strip().lower()
    if not normalized:
        return False
    configured_domains = split_domains(allowed_domains)
    if not configured_domains:
        return True
    for item in configured_domains:
        if normalized == item or normalized.endswith(f".{item}"):
            return True
    return False
