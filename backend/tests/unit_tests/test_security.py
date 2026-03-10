"""Tests for security utilities."""

import pytest
from datetime import datetime, timedelta, UTC

from app.core.security import (
    generate_api_key,
    generate_sub_key,
    generate_request_id,
    hash_api_key,
    verify_api_key_hash,
    create_access_token,
    decode_access_token,
    verify_password,
    get_password_hash,
)


class TestAPIKeyGeneration:
    """Tests for API key generation."""

    def test_generate_api_key_format(self):
        """Test that API key has correct format."""
        key = generate_api_key()
        assert key.startswith("sk-")
        assert len(key) == 35  # sk- (3) + 32 hex chars

    def test_generate_api_key_unique(self):
        """Test that generated keys are unique."""
        key1 = generate_api_key()
        key2 = generate_api_key()
        assert key1 != key2

    def test_generate_api_key_custom_prefix(self):
        """Test custom prefix for API key."""
        key = generate_api_key(prefix="custom-")
        assert key.startswith("custom-")

    def test_generate_sub_key_format(self):
        """Test that sub-key has correct format."""
        key = generate_sub_key()
        assert key.startswith("sk-sub-")
        assert len(key) == 39  # sk-sub- (6) + 32 hex chars


class TestKeyHashing:
    """Tests for key hashing."""

    def test_hash_api_key(self):
        """Test API key hashing."""
        key = "sk-test123"
        hashed = hash_api_key(key)
        assert hashed != key
        assert len(hashed) == 64  # SHA-256 hex length

    def test_hash_consistency(self):
        """Test that same key produces same hash."""
        key = "sk-test123"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        assert hash1 == hash2

    def test_verify_api_key_hash(self):
        """Test API key verification."""
        key = "sk-test123"
        hashed = hash_api_key(key)
        assert verify_api_key_hash(key, hashed) is True
        assert verify_api_key_hash("wrong-key", hashed) is False


class TestRequestID:
    """Tests for request ID generation."""

    def test_generate_request_id_format(self):
        """Test request ID format."""
        req_id = generate_request_id()
        assert req_id.startswith("req-")

    def test_generate_request_id_unique(self):
        """Test that request IDs are unique."""
        id1 = generate_request_id()
        id2 = generate_request_id()
        assert id1 != id2


class TestJWT:
    """Tests for JWT token handling."""

    def test_create_access_token(self):
        """Test access token creation."""
        data = {"sub": "user123", "email": "test@example.com"}
        token = create_access_token(data)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self):
        """Test access token decoding."""
        data = {"sub": "user123", "email": "test@example.com"}
        token = create_access_token(data)
        decoded = decode_access_token(token)
        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"

    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        decoded = decode_access_token("invalid-token")
        assert decoded is None


class TestPasswordHashing:
    """Tests for password hashing."""

    def test_get_password_hash(self):
        """Test password hashing."""
        password = "testpassword123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_verify_password(self):
        """Test password verification."""
        password = "testpassword123"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False
