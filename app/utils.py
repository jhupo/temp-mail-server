import re
import secrets

from app.config import settings

LOCAL_RE = re.compile(r"^[a-zA-Z0-9._%+-]{1,64}$")


def normalize_address(address: str) -> str:
    return address.strip().lower()


def split_address(address: str) -> tuple[str, str]:
    if "@" not in address:
        raise ValueError("invalid email address")
    local_part, domain = address.rsplit("@", 1)
    return local_part.lower(), domain.lower()


def is_allowed_domain(domain: str) -> bool:
    normalized = domain.lower()
    for root in settings.allowed_domains:
        if normalized == root or normalized.endswith(f".{root}"):
            return True
    return False


def is_valid_local_part(local_part: str) -> bool:
    return bool(LOCAL_RE.fullmatch(local_part))


def make_random_local_part(length: int = 10) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))
