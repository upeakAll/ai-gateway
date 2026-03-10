"""Pytest configuration and fixtures."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Base
from app.config import settings


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_gateway_test"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests."""
    async_session = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test HTTP client."""
    from app.api.deps import get_db_session

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# Test data fixtures
@pytest.fixture
def test_tenant_data():
    """Sample tenant data for tests."""
    return {
        "name": "Test Company",
        "slug": "test-company",
        "quota_total": 100.00,
        "billing_mode": "prepaid",
        "routing_strategy": "weighted_round_robin",
    }


@pytest.fixture
def test_api_key_data():
    """Sample API key data for tests."""
    return {
        "name": "Test Key",
        "quota_total": 50.00,
        "rpm_limit": 100,
        "tpm_limit": 100000,
    }


@pytest.fixture
def test_channel_data():
    """Sample channel data for tests."""
    return {
        "name": "Test OpenAI",
        "provider": "openai",
        "api_key": "sk-test-key-1234567890",
        "api_base": "https://api.openai.com/v1",
        "weight": 1,
        "priority": 0,
    }


@pytest.fixture
def test_chat_request():
    """Sample chat completion request."""
    return {
        "model": "gpt-4o",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "temperature": 0.7,
        "max_tokens": 100,
    }


# Mock fixtures
@pytest.fixture
def mock_redis():
    """Mock Redis client for tests."""
    from unittest.mock import AsyncMock, MagicMock

    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.eval = AsyncMock(return_value=[1, 0, 0])
    mock.ping = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response."""
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! I'm doing well, thank you!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18,
        },
    }
