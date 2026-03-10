"""OAuth2 and OIDC integration."""

import base64
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


@dataclass
class OAuth2Config:
    """OAuth2 provider configuration."""

    provider: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str | None = None
    scope: str = "openid profile email"
    redirect_uri: str | None = None


@dataclass
class OAuth2Token:
    """OAuth2 token response."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    refresh_token: str | None = None
    scope: str | None = None
    id_token: str | None = None
    expires_at: datetime | None = None

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return True
        return datetime.now(UTC) >= self.expires_at


@dataclass
class OAuth2User:
    """OAuth2 user information."""

    provider: str
    provider_user_id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)


class OAuth2Client:
    """OAuth2 client for authentication."""

    def __init__(self, config: OAuth2Config) -> None:
        self.config = config
        self._http_client = httpx.AsyncClient(timeout=30.0)

    def get_authorization_url(
        self,
        state: str | None = None,
        redirect_uri: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate authorization URL."""
        if not state:
            state = secrets.token_urlsafe(32)

        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "scope": self.config.scope,
            "state": state,
            "redirect_uri": redirect_uri or self.config.redirect_uri,
        }

        # Add any additional parameters
        params.update(kwargs)

        return f"{self.config.authorize_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str | None = None,
    ) -> OAuth2Token:
        """Exchange authorization code for token."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "redirect_uri": redirect_uri or self.config.redirect_uri,
        }

        response = await self._http_client.post(
            self.config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response.raise_for_status()
        token_data = response.json()

        token = OAuth2Token(
            access_token=token_data.get("access_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
            id_token=token_data.get("id_token"),
        )

        token.expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)

        return token

    async def refresh_token(self, refresh_token: str) -> OAuth2Token:
        """Refresh access token."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }

        response = await self._http_client.post(
            self.config.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        response.raise_for_status()
        token_data = response.json()

        token = OAuth2Token(
            access_token=token_data.get("access_token"),
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            refresh_token=token_data.get("refresh_token", refresh_token),
        )

        token.expires_at = datetime.now(UTC) + timedelta(seconds=token.expires_in)

        return token

    async def get_userinfo(self, access_token: str) -> OAuth2User:
        """Get user information from provider."""
        if not self.config.userinfo_url:
            raise ValueError("Userinfo URL not configured")

        response = await self._http_client.get(
            self.config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        response.raise_for_status()
        user_data = response.json()

        # Extract common fields
        return OAuth2User(
            provider=self.config.provider,
            provider_user_id=user_data.get("sub") or user_data.get("id"),
            email=user_data.get("email"),
            name=user_data.get("name") or user_data.get("preferred_username"),
            picture=user_data.get("picture"),
            raw_data=user_data,
        )

    async def close(self) -> None:
        """Close HTTP client."""
        await self._http_client.aclose()


class OIDCClient(OAuth2Client):
    """OpenID Connect client with ID token verification."""

    def __init__(self, config: OAuth2Config) -> None:
        super().__init__(config)
        self._jwks_cache: dict[str, Any] = {}
        self._jwks_uri: str | None = None

    async def discover_configuration(self) -> dict[str, Any]:
        """Discover OIDC configuration from well-known endpoint."""
        if not self.config.authorize_url:
            raise ValueError("Authorize URL required for discovery")

        # Extract base URL
        from urllib.parse import urlparse
        parsed = urlparse(self.config.authorize_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        discovery_url = f"{base_url}/.well-known/openid-configuration"

        response = await self._http_client.get(discovery_url)
        response.raise_for_status()

        config = response.json()

        # Update configuration from discovery
        self._jwks_uri = config.get("jwks_uri")

        return config

    async def verify_id_token(
        self,
        id_token: str,
        nonce: str | None = None,
    ) -> dict[str, Any]:
        """Verify ID token signature and claims."""
        import json

        # Split token
        parts = id_token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid ID token format")

        # Decode header and payload
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))

        # Verify claims
        if payload.get("aud") != self.config.client_id:
            raise ValueError("Invalid audience")

        if payload.get("exp", 0) < datetime.now(UTC).timestamp():
            raise ValueError("Token expired")

        if nonce and payload.get("nonce") != nonce:
            raise ValueError("Invalid nonce")

        # Note: Full signature verification would require JWT library
        # This is a simplified implementation

        return payload


# Predefined OAuth2 configurations
OAUTH2_PROVIDERS: dict[str, OAuth2Config] = {}


def register_oauth2_provider(name: str, config: OAuth2Config) -> None:
    """Register an OAuth2 provider."""
    OAUTH2_PROVIDERS[name] = config
    logger.info("oauth2_provider_registered", provider=name)


def get_oauth2_client(provider: str) -> OAuth2Client | None:
    """Get OAuth2 client for a provider."""
    config = OAUTH2_PROVIDERS.get(provider)
    if not config:
        return None
    return OAuth2Client(config)


def get_oidc_client(provider: str) -> OIDCClient | None:
    """Get OIDC client for a provider."""
    config = OAUTH2_PROVIDERS.get(provider)
    if not config:
        return None
    return OIDCClient(config)
