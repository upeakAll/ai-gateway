"""Tests for API endpoints."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "version" in data

    @pytest.mark.asyncio
    async def test_liveness_check(self, client: AsyncClient):
        """Test liveness endpoint."""
        response = await client.get("/health/live")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "alive"


class TestModelsEndpoint:
    """Tests for models endpoint."""

    @pytest.mark.asyncio
    async def test_list_models(self, client: AsyncClient):
        """Test listing models."""
        response = await client.get("/v1/models")
        assert response.status_code == 200

        data = response.json()
        assert "object" in data
        assert data["object"] == "list"
        assert "data" in data
        assert isinstance(data["data"], list)


class TestChatCompletionsEndpoint:
    """Tests for chat completions endpoint."""

    @pytest.mark.asyncio
    async def test_chat_completions_unauthorized(self, client: AsyncClient):
        """Test chat completions without auth."""
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            },
        )
        # Should return 401 without API key
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_chat_completions_invalid_model(self, client: AsyncClient, mock_redis):
        """Test chat completions with invalid model."""
        # This would test with a valid API key but no channels configured
        pass


class TestAdminEndpoints:
    """Tests for admin endpoints."""

    @pytest.mark.asyncio
    async def test_create_tenant(self, client: AsyncClient, db_session):
        """Test creating a tenant."""
        response = await client.post(
            "/admin/tenants",
            json={
                "name": "Test Company",
                "slug": "test-company",
                "quota_total": 100.00,
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Company"
        assert data["slug"] == "test-company"

    @pytest.mark.asyncio
    async def test_list_tenants(self, client: AsyncClient):
        """Test listing tenants."""
        response = await client.get("/admin/tenants")
        assert response.status_code == 200

        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_create_duplicate_tenant(self, client: AsyncClient):
        """Test creating duplicate tenant."""
        # Create first tenant
        await client.post(
            "/admin/tenants",
            json={
                "name": "Duplicate",
                "slug": "duplicate",
            },
        )

        # Try to create duplicate
        response = await client.post(
            "/admin/tenants",
            json={
                "name": "Duplicate 2",
                "slug": "duplicate",  # Same slug
            },
        )
        assert response.status_code == 400


class TestUsageEndpoints:
    """Tests for usage endpoints."""

    @pytest.mark.asyncio
    async def test_get_usage_unauthorized(self, client: AsyncClient):
        """Test getting usage without auth."""
        response = await client.get("/dashboard/usage")
        assert response.status_code == 401
