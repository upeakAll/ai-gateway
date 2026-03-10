"""API dependencies for authentication and request context."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import APIKeyExpiredError, APIKeyNotFoundError, AuthenticationError
from app.core.security import hash_api_key, verify_api_key_hash
from app.models import APIKey, KeyStatus, Tenant
from app.storage import get_db_session

# Security schemes
bearer_scheme = HTTPBearer(auto_error=False)


async def get_api_key_from_header(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Extract API key from Authorization header or X-API-Key header.

    Supports:
    - Bearer token in Authorization header
    - X-API-Key header
    """
    api_key = None

    # Check Authorization header first (Bearer token)
    if authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]
        else:
            api_key = authorization

    # Fall back to X-API-Key header
    if not api_key and x_api_key:
        api_key = x_api_key

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Use Authorization: Bearer <key> or X-API-Key header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return api_key


async def validate_api_key(
    api_key: Annotated[str, Depends(get_api_key_from_header)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> APIKey:
    """Validate API key and return the key object.

    Raises HTTPException if key is invalid or expired.
    """
    # Hash the key for lookup
    key_hash = hash_api_key(api_key)

    # Look up the key
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    )
    db_key = result.scalar_one_or_none()

    if not db_key:
        # Also check sub-keys
        from app.models import SubKey
        result = await db.execute(
            select(SubKey).where(SubKey.key_hash == key_hash)
        )
        sub_key = result.scalar_one_or_none()

        if not sub_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        # Get parent key for sub-key validation
        result = await db.execute(
            select(APIKey).where(APIKey.id == sub_key.parent_key_id)
        )
        db_key = result.scalar_one_or_none()

        if not db_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        # Store sub-key in context for quota tracking
        # This is a bit of a hack, but works for now
        db_key._sub_key = sub_key  # type: ignore

    # Check if key is active
    if not db_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is inactive or expired",
        )

    return db_key


async def get_current_tenant(
    api_key: Annotated[APIKey, Depends(validate_api_key)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Tenant:
    """Get the tenant for the current API key."""
    result = await db.execute(
        select(Tenant).where(Tenant.id == api_key.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tenant not found for API key",
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant account is disabled",
        )

    return tenant


class RequestContext:
    """Request context with authenticated user info."""

    def __init__(
        self,
        api_key: APIKey,
        tenant: Tenant,
        request_id: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.tenant = tenant
        self.request_id = request_id
        self.client_ip = client_ip
        self.user_agent = user_agent

    @property
    def tenant_id(self) -> str:
        return str(self.tenant.id)

    @property
    def api_key_id(self) -> str:
        return str(self.api_key.id)

    def has_model_access(self, model: str) -> bool:
        """Check if the API key has access to the specified model."""
        return self.api_key.is_model_allowed(model)


async def get_request_context(
    request: Request,
    api_key: Annotated[APIKey, Depends(validate_api_key)],
    tenant: Annotated[Tenant, Depends(get_current_tenant)],
) -> RequestContext:
    """Build request context from authenticated user."""
    from app.core.security import generate_request_id

    request_id = request.headers.get("X-Request-ID") or generate_request_id()

    return RequestContext(
        api_key=api_key,
        tenant=tenant,
        request_id=request_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


# Type aliases for dependency injection
CurrentAPIKey = Annotated[APIKey, Depends(validate_api_key)]
CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]
CurrentContext = Annotated[RequestContext, Depends(get_request_context)]
DBSession = Annotated[AsyncSession, Depends(get_db_session)]
