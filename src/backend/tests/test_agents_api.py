"""Unit tests for Agent CRUD API endpoints.

Tests the CRUD operations, validation, tenant scoping, and audit header
enforcement for the /api/agents endpoints.

References:
    - Task 9.4: Write unit tests for CRUD endpoints
    - Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.services.agent_registry import (
    AgentInUseError,
    AgentNotFoundError,
    AgentRegistryService,
    AgentValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test TenantContext."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="admin",
    )


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create a mock AgentRegistryService."""
    service = AsyncMock(spec=AgentRegistryService)
    return service


@pytest.fixture
def sample_agent_data() -> dict:
    """Sample agent data as returned by the service (DB model-like object)."""
    return {
        "id": 1,
        "schema_version": "2.0",
        "name": "Test Agent",
        "description": "A test agent for unit testing",
        "agent_type": "review",
        "archetype": "Regulatory Compliance Auditor",
        "personality_profile": {
            "tone": "formal",
            "verbosity": "detailed",
            "strictness": 0.9,
            "domain_focus": ["regulatory", "compliance"],
            "communication_style": "structured findings",
        },
        "contextual_tuning": {
            "temperature": 0.1,
            "max_tokens": 4096,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
        "evaluation_rubric": None,
        "system_prompt": "You are a regulatory compliance auditor.",
        "dspy_modules": [{"name": "analyze", "type": "ChainOfThought", "params": {}}],
        "knowledge_scopes": {"tags": ["Regulatory"]},
        "is_active": True,
        "created_at": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
        "updated_at": None,
    }


@pytest.fixture
def sample_create_request() -> dict:
    """Sample request body for creating an agent."""
    return {
        "schema_version": "2.0",
        "name": "Test Agent",
        "description": "A test agent for unit testing",
        "agent_type": "review",
        "archetype": "Regulatory Compliance Auditor",
        "system_prompt": "You are a regulatory compliance auditor.",
        "dspy_modules": [{"name": "analyze", "type": "ChainOfThought", "params": {}}],
        "knowledge_scopes": {"tags": ["Regulatory"]},
        "personality_profile": {
            "tone": "formal",
            "verbosity": "detailed",
            "strictness": 0.9,
            "domain_focus": ["regulatory", "compliance"],
            "communication_style": "structured findings",
        },
        "contextual_tuning": {
            "temperature": 0.1,
            "max_tokens": 4096,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
    }


class _FakeAgentModel:
    """Fake agent model object that supports attribute access and model_validate."""

    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


@pytest_asyncio.fixture
async def client(
    mock_service: AsyncMock, tenant_context: TenantContext
) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""
    from alcoabase.api.agents import get_agent_registry_service

    async def _override_get_tenant_context():
        return tenant_context

    def _override_get_service():
        return mock_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_agent_registry_service] = _override_get_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Unit test operation",
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_change_reason(
    mock_service: AsyncMock, tenant_context: TenantContext
) -> AsyncClient:
    """Create an httpx AsyncClient WITHOUT X-Change-Reason header."""
    from alcoabase.api.agents import get_agent_registry_service

    async def _override_get_tenant_context():
        return tenant_context

    def _override_get_service():
        return mock_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_agent_registry_service] = _override_get_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: POST /api/agents (Requirement 5.1)
# ---------------------------------------------------------------------------


class TestCreateAgent:
    """Tests for POST /api/agents."""

    @pytest.mark.asyncio
    async def test_create_agent_success(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
        sample_create_request: dict,
    ):
        """Returns 201 with agent data on successful creation."""
        mock_service.create_agent.return_value = _FakeAgentModel(sample_agent_data)

        response = await client.post("/api/agents", json=sample_create_request)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Agent"
        assert data["schema_version"] == "2.0"
        assert data["archetype"] == "Regulatory Compliance Auditor"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_agent_validation_failure(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_create_request: dict,
    ):
        """Returns 422 with error details when validation fails."""
        mock_service.create_agent.side_effect = AgentValidationError(
            ["name: must not be empty", "archetype: exceeds 100 characters"]
        )

        response = await client.post("/api/agents", json=sample_create_request)

        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["message"] == "Validation failed"
        assert len(data["detail"]["errors"]) == 2

    @pytest.mark.asyncio
    async def test_create_agent_pydantic_validation_failure(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when request body fails Pydantic validation."""
        # Missing required fields
        response = await client.post("/api/agents", json={"name": "Incomplete"})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /api/agents (Requirement 5.2)
# ---------------------------------------------------------------------------


class TestListAgents:
    """Tests for GET /api/agents."""

    @pytest.mark.asyncio
    async def test_list_agents_success(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
    ):
        """Returns 200 with list of agents."""
        mock_service.list_agents.return_value = [_FakeAgentModel(sample_agent_data)]

        response = await client.get("/api/agents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Agent"
        mock_service.list_agents.assert_called_once_with(
            company_id=1, archetype=None
        )

    @pytest.mark.asyncio
    async def test_list_agents_with_archetype_filter(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
    ):
        """Returns 200 with filtered agents when archetype query param is provided."""
        mock_service.list_agents.return_value = [_FakeAgentModel(sample_agent_data)]

        response = await client.get(
            "/api/agents", params={"archetype": "Regulatory Compliance Auditor"}
        )

        assert response.status_code == 200
        mock_service.list_agents.assert_called_once_with(
            company_id=1, archetype="Regulatory Compliance Auditor"
        )

    @pytest.mark.asyncio
    async def test_list_agents_empty(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """Returns 200 with empty list when no agents exist."""
        mock_service.list_agents.return_value = []

        response = await client.get("/api/agents")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Test: GET /api/agents/{agent_id} (Requirement 5.2, 5.7)
# ---------------------------------------------------------------------------


class TestGetAgent:
    """Tests for GET /api/agents/{agent_id}."""

    @pytest.mark.asyncio
    async def test_get_agent_success(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
    ):
        """Returns 200 with agent data when found."""
        mock_service.get_agent.return_value = _FakeAgentModel(sample_agent_data)

        response = await client.get("/api/agents/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Agent"
        mock_service.get_agent.assert_called_once_with(agent_id=1, company_id=1)

    @pytest.mark.asyncio
    async def test_get_agent_not_found(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """Returns 404 when agent does not exist or wrong company."""
        mock_service.get_agent.return_value = None

        response = await client.get("/api/agents/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Agent not found"


# ---------------------------------------------------------------------------
# Test: PUT /api/agents/{agent_id} (Requirement 5.3, 5.5, 5.7)
# ---------------------------------------------------------------------------


class TestUpdateAgent:
    """Tests for PUT /api/agents/{agent_id}."""

    @pytest.mark.asyncio
    async def test_update_agent_success(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
        sample_create_request: dict,
    ):
        """Returns 200 with updated agent data on success."""
        updated_data = {**sample_agent_data, "name": "Updated Agent"}
        mock_service.update_agent.return_value = _FakeAgentModel(updated_data)

        response = await client.put("/api/agents/1", json=sample_create_request)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Agent"

    @pytest.mark.asyncio
    async def test_update_agent_not_found(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_create_request: dict,
    ):
        """Returns 404 when agent does not exist or wrong company."""
        mock_service.update_agent.side_effect = AgentNotFoundError(
            "Agent not found"
        )

        response = await client.put("/api/agents/999", json=sample_create_request)

        assert response.status_code == 404
        assert response.json()["detail"] == "Agent not found"

    @pytest.mark.asyncio
    async def test_update_agent_validation_failure(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_create_request: dict,
    ):
        """Returns 422 when updated definition fails validation."""
        mock_service.update_agent.side_effect = AgentValidationError(
            ["system_prompt: must not be empty"]
        )

        response = await client.put("/api/agents/1", json=sample_create_request)

        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["message"] == "Validation failed"
        assert "system_prompt: must not be empty" in data["detail"]["errors"]


# ---------------------------------------------------------------------------
# Test: DELETE /api/agents/{agent_id} (Requirement 5.4, 5.7, 5.8)
# ---------------------------------------------------------------------------


class TestDeleteAgent:
    """Tests for DELETE /api/agents/{agent_id}."""

    @pytest.mark.asyncio
    async def test_delete_agent_success(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """Returns 204 on successful soft-delete."""
        mock_service.delete_agent.return_value = None

        response = await client.delete("/api/agents/1")

        assert response.status_code == 204
        mock_service.delete_agent.assert_called_once_with(
            agent_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """Returns 404 when agent does not exist or wrong company."""
        mock_service.delete_agent.side_effect = AgentNotFoundError(
            "Agent not found"
        )

        response = await client.delete("/api/agents/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Agent not found"

    @pytest.mark.asyncio
    async def test_delete_agent_in_use(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """Returns 409 when agent is assigned to an active pipeline."""
        mock_service.delete_agent.side_effect = AgentInUseError(
            "Agent is assigned to active pipeline"
        )

        response = await client.delete("/api/agents/1")

        assert response.status_code == 409
        assert "active pipeline" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: X-Change-Reason header enforcement (Requirement 5.6, 5.9)
# ---------------------------------------------------------------------------


class TestChangeReasonEnforcement:
    """Tests that mutating requests require X-Change-Reason header."""

    @pytest.mark.asyncio
    async def test_post_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
        sample_create_request: dict,
    ):
        """POST /api/agents without X-Change-Reason returns 400."""
        response = await client_no_change_reason.post(
            "/api/agents", json=sample_create_request
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_put_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
        sample_create_request: dict,
    ):
        """PUT /api/agents/{id} without X-Change-Reason returns 400."""
        response = await client_no_change_reason.put(
            "/api/agents/1", json=sample_create_request
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """DELETE /api/agents/{id} without X-Change-Reason returns 400."""
        response = await client_no_change_reason.delete("/api/agents/1")

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_without_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_service: AsyncMock,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_service.list_agents.return_value = []

        response = await client_no_change_reason.get("/api/agents")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: Company scoping isolation (Requirement 5.6)
# ---------------------------------------------------------------------------


class TestCompanyScoping:
    """Tests that all operations are scoped to the tenant's company."""

    @pytest.mark.asyncio
    async def test_create_passes_company_id(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
        sample_create_request: dict,
    ):
        """POST passes company_id from tenant context to service."""
        mock_service.create_agent.return_value = _FakeAgentModel(sample_agent_data)

        await client.post("/api/agents", json=sample_create_request)

        mock_service.create_agent.assert_called_once()
        call_kwargs = mock_service.create_agent.call_args[1]
        assert call_kwargs["company_id"] == 1
        assert call_kwargs["user_id"] == 42

    @pytest.mark.asyncio
    async def test_list_passes_company_id(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """GET list passes company_id from tenant context to service."""
        mock_service.list_agents.return_value = []

        await client.get("/api/agents")

        mock_service.list_agents.assert_called_once_with(
            company_id=1, archetype=None
        )

    @pytest.mark.asyncio
    async def test_get_passes_company_id(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
    ):
        """GET single passes company_id from tenant context to service."""
        mock_service.get_agent.return_value = _FakeAgentModel(sample_agent_data)

        await client.get("/api/agents/1")

        mock_service.get_agent.assert_called_once_with(agent_id=1, company_id=1)

    @pytest.mark.asyncio
    async def test_update_passes_company_id(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
        sample_agent_data: dict,
        sample_create_request: dict,
    ):
        """PUT passes company_id from tenant context to service."""
        mock_service.update_agent.return_value = _FakeAgentModel(sample_agent_data)

        await client.put("/api/agents/1", json=sample_create_request)

        mock_service.update_agent.assert_called_once()
        call_kwargs = mock_service.update_agent.call_args[1]
        assert call_kwargs["company_id"] == 1

    @pytest.mark.asyncio
    async def test_delete_passes_company_id(
        self,
        client: AsyncClient,
        mock_service: AsyncMock,
    ):
        """DELETE passes company_id from tenant context to service."""
        mock_service.delete_agent.return_value = None

        await client.delete("/api/agents/1")

        mock_service.delete_agent.assert_called_once_with(
            agent_id=1, company_id=1
        )
