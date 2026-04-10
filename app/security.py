import hashlib
import secrets
from hmac import compare_digest


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str | None) -> bool:
    if not token_hash:
        return False
    return compare_digest(hash_token(token), token_hash)


def hash_password(password: str, salt: str | None = None) -> str:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), password_salt.encode("utf-8"), 120000)
    return f"{password_salt}${digest.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash or "$" not in password_hash:
        return False
    salt, _digest = password_hash.split("$", 1)
    return compare_digest(hash_password(password, salt), password_hash)
