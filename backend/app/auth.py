"""Password hashing, bearer tokens, and the current-user dependency.

Deliberately dependency-free: PBKDF2-HMAC-SHA256 from the stdlib (no bcrypt/argon2 wheel to
build on Windows) and opaque random session tokens stored in the AuthSession table. Fine for a
proof-of-concept; a real deployment would move to a vetted password hasher and add token expiry.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from .db import get_session
from .models import AuthSession, User

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000
_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


def hash_password(password: str) -> str:
    """Return a self-describing `pbkdf2_sha256$iterations$salt$hash` string."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of a plaintext password against a stored hash. False (never raises)
    on any malformed stored value."""
    try:
        algo, iterations, salt_hex, expected_hex = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), expected_hex)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extract the raw token from an `Authorization: Bearer <token>` header, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated", headers=_UNAUTHENTICATED)
    token = authorization[len("bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=_UNAUTHENTICATED)
    return token


def get_current_user(
    token: str = Depends(bearer_token), session: Session = Depends(get_session)
) -> User:
    auth = session.get(AuthSession, token)
    user = session.get(User, auth.user_id) if auth is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token", headers=_UNAUTHENTICATED)
    return user
