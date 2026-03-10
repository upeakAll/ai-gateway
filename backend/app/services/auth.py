"""Authentication service."""

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.core.security import create_access_token, decode_access_token, verify_password
from app.models import User

logger = structlog.get_logger()


class AuthService:
    """Service for authentication operations."""

    def __init__(self) -> None:
        self._token_blacklist: set[str] = set()

    async def authenticate_user(
        self,
        user: User,
        password: str,
    ) -> dict[str, Any] | None:
        """Authenticate user with password.

        Returns access token if successful, None otherwise.
        """
        if not user.is_active:
            logger.warning(
                "authentication_failed_inactive",
                user_id=str(user.id),
            )
            return None

        if not verify_password(password, user.password_hash):
            logger.warning(
                "authentication_failed_password",
                user_id=str(user.id),
            )
            return None

        # Update last login
        user.last_login_at = datetime.now(UTC).isoformat()

        # Generate access token
        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
            }
        )

        logger.info(
            "user_authenticated",
            user_id=str(user.id),
            email=user.email,
        )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def authenticate_oauth2(
        self,
        user: User,
        provider: str,
    ) -> dict[str, Any]:
        """Authenticate user via OAuth2.

        Creates access token for OAuth2-authenticated user.
        """
        if not user.is_active:
            return None

        # Update OAuth info
        user.last_login_at = datetime.now(UTC).isoformat()

        access_token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "auth_provider": provider,
            }
        )

        logger.info(
            "oauth2_authenticated",
            user_id=str(user.id),
            provider=provider,
        )

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }

    async def validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate access token.

        Returns token payload if valid, None otherwise.
        """
        if token in self._token_blacklist:
            return None

        payload = decode_access_token(token)
        return payload

    async def revoke_token(self, token: str) -> None:
        """Revoke an access token."""
        self._token_blacklist.add(token)

        # Clean up old tokens from blacklist
        # In production, use Redis with TTL
        if len(self._token_blacklist) > 10000:
            self._token_blacklist.clear()

    async def refresh_token(self, token: str) -> dict[str, Any] | None:
        """Refresh access token.

        Returns new access token if valid, None otherwise.
        """
        payload = await self.validate_token(token)
        if not payload:
            return None

        # Revoke old token
        await self.revoke_token(token)

        # Create new token
        new_token = create_access_token(data=payload)

        return {
            "access_token": new_token,
            "token_type": "Bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
        }


# Global auth service
auth_service = AuthService()
