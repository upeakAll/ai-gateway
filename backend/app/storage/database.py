"""Database session management and utilities."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings

# Create async engine
engine_kwargs: dict[str, Any] = {
    "echo": settings.debug,
    "future": True,
}

# Configure pool settings
if settings.environment == "production":
    engine_kwargs.update({
        "pool_size": settings.database_pool_size,
        "max_overflow": settings.database_max_overflow,
        "pool_timeout": settings.database_pool_timeout,
        "pool_pre_ping": True,
    })
else:
    # Use NullPool for development to avoid connection issues
    engine_kwargs["poolclass"] = NullPool

engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    **engine_kwargs,
)

# Session factory
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Get database session as context manager."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database connection and create tables if needed."""
    # Test connection
    async with engine.begin() as conn:
        # Import models to register them
        from app.models import Base  # noqa: F401

        # Create tables if they don't exist (use Alembic in production)
        if settings.environment == "development":
            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connection pool."""
    await engine.dispose()


# Add connection pool monitoring
@event.listens_for(engine.sync_engine, "checkout")
def receive_checkout(dbapi_connection: Any, connection_record: Any, connection_proxy: Any) -> None:
    """Monitor connection pool checkout."""
    pass  # Can add logging here if needed
