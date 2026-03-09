from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from http.cookies import SimpleCookie


SESSION_COOKIE_NAME = "goalmate_session"
SESSION_TTL_DAYS = 30
PASSWORD_ITERATIONS = 390000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_digest = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations_text),
    ).hex()
    return hmac.compare_digest(digest, expected_digest)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str, session_secret: str) -> str:
    return hashlib.sha256(f"{session_secret}:{token}".encode("utf-8")).hexdigest()


def session_expiry_iso() -> str:
    return (datetime.now() + timedelta(days=SESSION_TTL_DAYS)).replace(microsecond=0).isoformat(sep=" ")


def build_session_cookie(token: str, *, clear: bool = False) -> str:
    cookie = SimpleCookie()
    cookie[SESSION_COOKIE_NAME] = "" if clear else token
    morsel = cookie[SESSION_COOKIE_NAME]
    morsel["path"] = "/"
    morsel["httponly"] = True
    morsel["samesite"] = "Lax"
    morsel["max-age"] = "0" if clear else str(SESSION_TTL_DAYS * 24 * 60 * 60)
    return cookie.output(header="").strip()
