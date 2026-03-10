"""Security utilities for authentication and authorization."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key(prefix: str | None = None) -> str:
    """Generate a new API key with the configured prefix.

    Format: {prefix}{32_random_hex_characters}
    Example: sk-1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p
    """
    prefix = prefix or settings.api_key_prefix
    random_part = secrets.token_hex(16)  # 32 hex characters
    return f"{prefix}{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage.

    Uses SHA-256 for fast, deterministic hashing.
    """
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key_hash(plain_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash."""
    return hash_api_key(plain_key) == hashed_key


def generate_sub_key(parent_key_prefix: str | None = None) -> str:
    """Generate a sub-key derived from parent key format.

    Sub-keys have a distinct prefix to differentiate from main keys.
    Format: sk-sub-{32_random_hex_characters}
    """
    random_part = secrets.token_hex(16)
    return f"sk-sub-{random_part}"


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm="HS256")
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT access token.

    Returns None if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password for storage."""
    return pwd_context.hash(password)


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_request_id() -> str:
    """Generate a unique request ID for tracing."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    random_part = secrets.token_hex(4)
    return f"req-{timestamp}-{random_part}"


# Type alias for dependency injection
APIKeyHeader = Annotated[str, "X-API-Key header"]
BearerToken = Annotated[str, "Bearer token from Authorization header"]
