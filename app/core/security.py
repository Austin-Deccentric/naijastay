from datetime import datetime, timedelta, timezone
from typing import Any
import bcrypt
import jwt

from app.core.config import settings


async def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")

    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)

    return hashed_password.decode("utf-8")


async def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    hashed_password_bytes = password_hash.encode("utf-8")

    return bcrypt.checkpw(
        password_bytes,
        hashed_password_bytes,
    )

def create_access_token(subject: str, role: str) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "iat": issued_at,
        "exp": expires_at,
        "token_type": "access",
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={
                "require": ["sub", "role", "iat", "exp", "token_type"],
            },
        )
        if payload.get("token_type") != "access":
            return None
        if not isinstance(payload.get("role"), str) or not payload["role"]:
            return None
        return payload
    except (jwt.InvalidTokenError, TypeError, ValueError):
        return None