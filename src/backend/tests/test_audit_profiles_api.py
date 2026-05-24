"""Unit tests for Audit Profiles API endpoints.

Tests the audit profile CRUD endpoints including creation, listing,
retrieval, update, deletion, and validation (quorum, agent assignments).
Covers HTTP status codes: 201, 200, 204, 400, 404, 422.

References:
    - Task 10.6: Write unit tests for API endpoints
    - Requirements: 4.3, 4.5, 4.6, 4.7, 10.1–10.8
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.api.audit_profiles import get_audit_profile_service
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.services.audit_profile_service import (
    SUPPORTED_FRAMEWORKS,
    AuditProfileService,
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
def mock_audit_profile_service() -> AsyncMock:
    """Create a mock AuditProfileService."""
    return AsyncMock(spec=AuditProfileService)


class _FakeProfile:
    """Fake audit profile model object that supports attribute access."""

    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


@pytest.fixture
def sample_profile() -> dict:
    """Sample audit profile data."""
    return {
        "id": 1,
        "company_id": 1,
        "name": "GMP Review Profile",
        "description": "Standard GMP review configuration",
        "regulatory_frameworks": ["GMP", "21 CFR Part 11"],
        "assigned_agent_ids": [10, 11, 12],
        "quorum": 2,
        "severity_thresholds": {
            "critical": 25.0,
            "major": 10.0,
            "minor": 3.0,
            "informational": 0.5,
        },
        "is_default": True,
        "is_active": True,
        "created_at": datetime(2025, 6, 10, 8, 0, 0, tzinfo=UTC),
        "updated_at": None,
    }


@pytest.fixture
def valid_profile_request() -> dict:
    """Valid request body for creating/updating an audit profile."""
    return {
        "name": "GMP Review Profile",
        "description": "Standard GMP review configuration",
        "regulatory_frameworks": ["GMP", "21 CFR Part 11"],
        "assigned_agent_ids": [10, 11, 12],
        "quorum": 2,
        "is_default": False,
    }


@pytest_asyncio.fixture
async def client(
    mock_audit_profile_service: AsyncMock,
    tenant_context: TenantContext,
) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""

    async def _override_get_tenant_context():
        return tenant_context

    def _override_audit_profile_service():
        return mock_audit_profile_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_audit_profile_service] = (
        _override_audit_profile_service
    )

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
    mock_audit_profile_service: AsyncMock,
    tenant_context: TenantContext,
) -> AsyncClient:
    """Create an httpx AsyncClient WITHOUT X-Change-Reason header."""

    async def _override_get_tenant_context():
        return tenant_context

    def _override_audit_profile_service():
        return mock_audit_profile_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_audit_profile_service] = (
        _override_audit_profile_service
    )

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
# Test: POST /api/audit-profiles (Requirement 4.3)
# ---------------------------------------------------------------------------


class TestCreateAuditProfile:
    """Tests for POST /api/audit-profiles."""

    @pytest.mark.asyncio
    async def test_create_profile_returns_201(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
        valid_profile_request: dict,
    ):
        """Returns 201 with created profile."""
        mock_audit_profile_service.create_profile.return_value = _FakeProfile(
            sample_profile
        )

        response = await client.post(
            "/api/audit-profiles", json=valid_profile_request
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "GMP Review Profile"
        assert data["quorum"] == 2
        assert data["assigned_agent_ids"] == [10, 11, 12]

    @pytest.mark.asyncio
    async def test_create_profile_quorum_exceeds_agents_returns_422(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 422 when quorum exceeds assigned agent count."""
        mock_audit_profile_service.create_profile.side_effect = ValueError(
            "Quorum (5) exceeds assigned agent count (3)"
        )

        response = await client.post(
            "/api/audit-profiles",
            json={
                "name": "Bad Profile",
                "regulatory_frameworks": ["GMP"],
                "assigned_agent_ids": [10, 11, 12],
                "quorum": 5,
            },
        )

        assert response.status_code == 422
        assert "Quorum" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_profile_invalid_agents_returns_422(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 422 when agent assignments are invalid."""
        mock_audit_profile_service.create_profile.side_effect = ValueError(
            "Validation failed: Agent 99 not found or not active"
        )

        response = await client.post(
            "/api/audit-profiles",
            json={
                "name": "Bad Profile",
                "regulatory_frameworks": ["GMP"],
                "assigned_agent_ids": [99],
                "quorum": 1,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_profile_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
        valid_profile_request: dict,
    ):
        """POST without X-Change-Reason returns 400."""
        response = await client_no_change_reason.post(
            "/api/audit-profiles", json=valid_profile_request
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_profile_invalid_body_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when request body is invalid."""
        response = await client.post(
            "/api/audit-profiles",
            json={"name": ""},  # empty name fails min_length=1
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_profile_missing_required_fields_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when required fields are missing."""
        response = await client.post(
            "/api/audit-profiles",
            json={"name": "Test"},  # missing frameworks, agents, quorum
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /api/audit-profiles (Requirement 4.3)
# ---------------------------------------------------------------------------


class TestListAuditProfiles:
    """Tests for GET /api/audit-profiles."""

    @pytest.mark.asyncio
    async def test_list_profiles_returns_200(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
    ):
        """Returns 200 with list of profiles."""
        mock_audit_profile_service.list_profiles.return_value = [
            _FakeProfile(sample_profile)
        ]

        response = await client.get("/api/audit-profiles")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "GMP Review Profile"
        mock_audit_profile_service.list_profiles.assert_called_once_with(
            company_id=1
        )

    @pytest.mark.asyncio
    async def test_list_profiles_empty(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 200 with empty list when no profiles exist."""
        mock_audit_profile_service.list_profiles.return_value = []

        response = await client.get("/api/audit-profiles")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_profiles_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_audit_profile_service.list_profiles.return_value = []

        response = await client_no_change_reason.get("/api/audit-profiles")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: GET /api/audit-profiles/frameworks (Requirement 4.7)
# ---------------------------------------------------------------------------


class TestListFrameworks:
    """Tests for GET /api/audit-profiles/frameworks."""

    @pytest.mark.asyncio
    async def test_list_frameworks_returns_200(
        self,
        client: AsyncClient,
    ):
        """Returns 200 with list of supported frameworks."""
        response = await client.get("/api/audit-profiles/frameworks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert "GMP" in data
        assert "ISO 13485" in data
        assert "21 CFR Part 11" in data
        assert len(data) == len(SUPPORTED_FRAMEWORKS)

    @pytest.mark.asyncio
    async def test_list_frameworks_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """GET requests do not require X-Change-Reason header."""
        response = await client_no_change_reason.get(
            "/api/audit-profiles/frameworks"
        )

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: GET /api/audit-profiles/{profile_id} (Requirement 4.3)
# ---------------------------------------------------------------------------


class TestGetAuditProfile:
    """Tests for GET /api/audit-profiles/{profile_id}."""

    @pytest.mark.asyncio
    async def test_get_profile_returns_200(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
    ):
        """Returns 200 with profile detail."""
        mock_audit_profile_service.get_profile.return_value = _FakeProfile(
            sample_profile
        )

        response = await client.get("/api/audit-profiles/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "GMP Review Profile"
        mock_audit_profile_service.get_profile.assert_called_once_with(
            profile_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_get_profile_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 404 when profile not found or wrong company."""
        mock_audit_profile_service.get_profile.return_value = None

        response = await client.get("/api/audit-profiles/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Audit profile not found"


# ---------------------------------------------------------------------------
# Test: PUT /api/audit-profiles/{profile_id} (Requirement 4.3)
# ---------------------------------------------------------------------------


class TestUpdateAuditProfile:
    """Tests for PUT /api/audit-profiles/{profile_id}."""

    @pytest.mark.asyncio
    async def test_update_profile_returns_200(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
        valid_profile_request: dict,
    ):
        """Returns 200 with updated profile."""
        updated = {**sample_profile, "name": "Updated Profile"}
        mock_audit_profile_service.update_profile.return_value = _FakeProfile(
            updated
        )

        response = await client.put(
            "/api/audit-profiles/1", json=valid_profile_request
        )

        assert response.status_code == 200
        mock_audit_profile_service.update_profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_profile_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        valid_profile_request: dict,
    ):
        """Returns 404 when profile not found."""
        mock_audit_profile_service.update_profile.side_effect = ValueError(
            "Audit profile not found for company 1"
        )

        response = await client.put(
            "/api/audit-profiles/999", json=valid_profile_request
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_profile_quorum_validation_returns_422(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 422 when quorum exceeds agent count on update."""
        mock_audit_profile_service.update_profile.side_effect = ValueError(
            "Quorum (5) exceeds assigned agent count (2)"
        )

        response = await client.put(
            "/api/audit-profiles/1",
            json={
                "name": "Bad Update",
                "regulatory_frameworks": ["GMP"],
                "assigned_agent_ids": [10, 11],
                "quorum": 5,
            },
        )

        assert response.status_code == 422
        assert "Quorum" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_profile_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
        valid_profile_request: dict,
    ):
        """PUT without X-Change-Reason returns 400."""
        response = await client_no_change_reason.put(
            "/api/audit-profiles/1", json=valid_profile_request
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: DELETE /api/audit-profiles/{profile_id} (Requirement 4.3)
# ---------------------------------------------------------------------------


class TestDeleteAuditProfile:
    """Tests for DELETE /api/audit-profiles/{profile_id}."""

    @pytest.mark.asyncio
    async def test_delete_profile_returns_204(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 204 No Content on successful soft-delete."""
        mock_audit_profile_service.delete_profile.return_value = None

        response = await client.delete("/api/audit-profiles/1")

        assert response.status_code == 204
        mock_audit_profile_service.delete_profile.assert_called_once_with(
            profile_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_delete_profile_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """Returns 404 when profile not found."""
        mock_audit_profile_service.delete_profile.side_effect = ValueError(
            "Audit profile not found"
        )

        response = await client.delete("/api/audit-profiles/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Audit profile not found"

    @pytest.mark.asyncio
    async def test_delete_profile_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """DELETE without X-Change-Reason returns 400."""
        response = await client_no_change_reason.delete("/api/audit-profiles/1")

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Company scoping (Requirement 4.6)
# ---------------------------------------------------------------------------


class TestAuditProfilesCompanyScoping:
    """Tests that all audit profile operations are scoped to the tenant."""

    @pytest.mark.asyncio
    async def test_create_passes_company_id(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
        valid_profile_request: dict,
    ):
        """POST passes company_id from tenant context."""
        mock_audit_profile_service.create_profile.return_value = _FakeProfile(
            sample_profile
        )

        await client.post("/api/audit-profiles", json=valid_profile_request)

        call_kwargs = mock_audit_profile_service.create_profile.call_args[1]
        assert call_kwargs["company_id"] == 1

    @pytest.mark.asyncio
    async def test_list_passes_company_id(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """GET list passes company_id from tenant context."""
        mock_audit_profile_service.list_profiles.return_value = []

        await client.get("/api/audit-profiles")

        mock_audit_profile_service.list_profiles.assert_called_once_with(
            company_id=1
        )

    @pytest.mark.asyncio
    async def test_get_passes_company_id(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
    ):
        """GET profile passes company_id from tenant context."""
        mock_audit_profile_service.get_profile.return_value = _FakeProfile(
            sample_profile
        )

        await client.get("/api/audit-profiles/1")

        mock_audit_profile_service.get_profile.assert_called_once_with(
            profile_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_update_passes_company_id(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
        sample_profile: dict,
        valid_profile_request: dict,
    ):
        """PUT passes company_id from tenant context."""
        mock_audit_profile_service.update_profile.return_value = _FakeProfile(
            sample_profile
        )

        await client.put("/api/audit-profiles/1", json=valid_profile_request)

        call_kwargs = mock_audit_profile_service.update_profile.call_args[1]
        assert call_kwargs["company_id"] == 1

    @pytest.mark.asyncio
    async def test_delete_passes_company_id(
        self,
        client: AsyncClient,
        mock_audit_profile_service: AsyncMock,
    ):
        """DELETE passes company_id from tenant context."""
        mock_audit_profile_service.delete_profile.return_value = None

        await client.delete("/api/audit-profiles/1")

        mock_audit_profile_service.delete_profile.assert_called_once_with(
            profile_id=1, company_id=1
        )
