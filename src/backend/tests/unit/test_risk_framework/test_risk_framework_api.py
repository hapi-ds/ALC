"""Unit tests for AI Risk & Compliance Framework API router.

Tests all endpoint validation, error responses (400, 403, 404, 409, 422),
pagination parameters, filter combinations, and X-Company-Id scoping.

Requirements: 10.13, 10.14, 10.15, 10.16
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from alcoabase.api.risk_framework import (
    _require_risk_framework_role,
    router as risk_framework_router,
)
from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.risk_framework import (
    AITaskTypeDetailResponse,
    AITaskTypeResponse,
    CompanyRiskProfileResponse,
    DashboardStatsResponse,
    HITLCheckpointResponse,
    PaginatedResult,
)
from alcoabase.services.hitl_checkpoint_service import (
    CheckpointNotFoundError,
    CheckpointNotPendingError,
    ConcurrentReviewError,
    InsufficientReviewPermissionError,
    RejectionRequiresCommentsError,
)


# ---------------------------------------------------------------------------
# Constants and helpers
# ---------------------------------------------------------------------------

TENANT_CTX = TenantContext(
    company_id=1,
    company_slug="test-company",
    user_id=42,
    membership_role="admin",
)

NOW = datetime(2025, 6, 20, 14, 30, 0, tzinfo=UTC)
PROFILE_ID = uuid4()
CHECKPOINT_ID = uuid4()
TASK_TYPE_ID = "document_generation"


def _make_task_type_response(**overrides) -> AITaskTypeResponse:
    """Create a sample AITaskTypeResponse for testing."""
    defaults = {
        "id": uuid4(),
        "task_type_id": TASK_TYPE_ID,
        "display_name": "Document Generation",
        "module_reference": "5.4",
        "default_risk_tier": "high",
        "company_tier": None,
        "is_active": True,
        "is_system_defined": True,
    }
    defaults.update(overrides)
    return AITaskTypeResponse(**defaults)


def _make_task_type_detail_response(**overrides) -> AITaskTypeDetailResponse:
    """Create a sample AITaskTypeDetailResponse for testing."""
    defaults = {
        "id": uuid4(),
        "task_type_id": TASK_TYPE_ID,
        "display_name": "Document Generation",
        "description": "Generates GxP-regulated documents.",
        "module_reference": "5.4",
        "default_risk_tier": "high",
        "company_tier": None,
        "risk_factors": ["Regulatory content", "Approval workflow"],
        "is_active": True,
        "is_system_defined": True,
        "control_set": None,
        "created_at": NOW,
        "updated_at": None,
    }
    defaults.update(overrides)
    return AITaskTypeDetailResponse(**defaults)


def _make_profile_response(**overrides) -> CompanyRiskProfileResponse:
    """Create a sample CompanyRiskProfileResponse for testing."""
    defaults = {
        "id": PROFILE_ID,
        "company_id": 1,
        "profile_name": "GMP Pharma Profile",
        "description": "Standard GMP profile",
        "regulatory_frameworks": ["21_cfr_part_11", "eu_annex_11"],
        "is_active": True,
        "overrides": [],
        "created_by": 42,
        "created_at": NOW,
        "updated_at": None,
    }
    defaults.update(overrides)
    return CompanyRiskProfileResponse(**defaults)


def _make_checkpoint_response(**overrides) -> HITLCheckpointResponse:
    """Create a sample HITLCheckpointResponse for testing."""
    defaults = {
        "id": CHECKPOINT_ID,
        "company_id": 1,
        "operation_id": "op-12345",
        "task_type_id": TASK_TYPE_ID,
        "ai_output_reference": "s3://outputs/op-12345.json",
        "status": "pending",
        "assigned_reviewer_role": "doc_admin",
        "reviewer_user_id": None,
        "reviewer_comments": None,
        "reviewed_sections": None,
        "created_at": NOW,
        "expires_at": datetime(2025, 6, 23, 14, 30, 0, tzinfo=UTC),
        "reviewed_at": None,
    }
    defaults.update(overrides)
    return HITLCheckpointResponse(**defaults)


def _make_dashboard_stats(**overrides) -> DashboardStatsResponse:
    """Create a sample DashboardStatsResponse for testing."""
    defaults = {
        "operations_by_tier": {"high": 5, "medium": 12, "low": 45},
        "pending_checkpoints": 3,
        "expired_checkpoints": 1,
        "blocked_operations": 2,
        "active_profile_name": "GMP Pharma Profile",
    }
    defaults.update(overrides)
    return DashboardStatsResponse(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_risk_service() -> AsyncMock:
    """Create a mock RiskClassificationService."""
    svc = AsyncMock()
    svc.get_task_types = AsyncMock(
        return_value=PaginatedResult[AITaskTypeResponse](
            items=[_make_task_type_response()],
            total=1,
            limit=20,
            offset=0,
        )
    )
    svc.get_task_type = AsyncMock(
        return_value=_make_task_type_detail_response()
    )
    svc.create_profile = AsyncMock(
        return_value=_make_profile_response()
    )
    svc.get_active_profile = AsyncMock(
        return_value=_make_profile_response()
    )
    svc.update_profile = AsyncMock(
        return_value=_make_profile_response()
    )
    svc.get_profile_history = AsyncMock(
        return_value=PaginatedResult[CompanyRiskProfileResponse](
            items=[_make_profile_response()],
            total=1,
            limit=20,
            offset=0,
        )
    )
    svc.get_dashboard_stats = AsyncMock(
        return_value=_make_dashboard_stats()
    )
    return svc


@pytest.fixture
def mock_hitl_service() -> AsyncMock:
    """Create a mock HITLCheckpointService."""
    svc = AsyncMock()
    svc.list_checkpoints = AsyncMock(
        return_value=PaginatedResult[HITLCheckpointResponse](
            items=[_make_checkpoint_response()],
            total=1,
            limit=20,
            offset=0,
        )
    )
    svc.review_checkpoint = AsyncMock(
        return_value=_make_checkpoint_response(status="approved")
    )
    return svc


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _build_app(
    mock_risk_service: AsyncMock,
    mock_hitl_service: AsyncMock,
    mock_session: AsyncMock,
    tenant_ctx: TenantContext = TENANT_CTX,
) -> FastAPI:
    """Build a FastAPI app with the risk framework router and overridden deps."""
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(risk_framework_router)
    app.include_router(api)

    # Override the role-checking dependency to return tenant context directly
    app.dependency_overrides[_require_risk_framework_role] = lambda: tenant_ctx
    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[get_tenant_context] = lambda: tenant_ctx

    return app


@pytest.fixture
def client(
    mock_risk_service: AsyncMock,
    mock_hitl_service: AsyncMock,
    mock_session: AsyncMock,
) -> TestClient:
    """Create a TestClient with all deps overridden (authorized)."""
    app = _build_app(mock_risk_service, mock_hitl_service, mock_session)

    # Patch module-level service instances
    with (
        patch(
            "alcoabase.api.risk_framework._risk_service", mock_risk_service
        ),
        patch(
            "alcoabase.api.risk_framework._hitl_service", mock_hitl_service
        ),
    ):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def unauthorized_client(
    mock_risk_service: AsyncMock,
    mock_hitl_service: AsyncMock,
    mock_session: AsyncMock,
) -> TestClient:
    """Create a TestClient that simulates 403 (role check fails)."""
    from fastapi import HTTPException

    app = _build_app(mock_risk_service, mock_hitl_service, mock_session)

    # Override role dependency to raise 403
    def _deny():
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires system_admin or doc_admin role.",
        )

    app.dependency_overrides[_require_risk_framework_role] = _deny

    with (
        patch(
            "alcoabase.api.risk_framework._risk_service", mock_risk_service
        ),
        patch(
            "alcoabase.api.risk_framework._hitl_service", mock_hitl_service
        ),
    ):
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/task-types
# ---------------------------------------------------------------------------


class TestListTaskTypes:
    """Tests for GET /api/risk-framework/task-types endpoint."""

    def test_returns_paginated_task_types(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns paginated list of task types with correct structure."""
        response = client.get("/api/risk-framework/task-types")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["task_type_id"] == TASK_TYPE_ID

    def test_pagination_params_passed_to_service(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Pagination parameters are forwarded to the service."""
        response = client.get(
            "/api/risk-framework/task-types?limit=50&offset=10"
        )
        assert response.status_code == 200
        call_kwargs = mock_risk_service.get_task_types.call_args.kwargs
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 10

    def test_invalid_limit_returns_422(
        self, client: TestClient
    ) -> None:
        """Limit > 100 returns 422 validation error."""
        response = client.get(
            "/api/risk-framework/task-types?limit=200"
        )
        assert response.status_code == 422

    def test_invalid_offset_returns_422(
        self, client: TestClient
    ) -> None:
        """Negative offset returns 422 validation error."""
        response = client.get(
            "/api/risk-framework/task-types?offset=-1"
        )
        assert response.status_code == 422

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get(
            "/api/risk-framework/task-types"
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/task-types/{task_type_id}
# ---------------------------------------------------------------------------


class TestGetTaskType:
    """Tests for GET /api/risk-framework/task-types/{task_type_id}."""

    def test_returns_task_type_detail(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns full task type detail for valid ID."""
        response = client.get(
            f"/api/risk-framework/task-types/{TASK_TYPE_ID}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["task_type_id"] == TASK_TYPE_ID
        assert body["display_name"] == "Document Generation"
        assert "risk_factors" in body

    def test_returns_404_for_unknown_task_type(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 404 when task type is not found."""
        mock_risk_service.get_task_type.side_effect = ValueError(
            "Task type 'nonexistent' not found."
        )
        response = client.get(
            "/api/risk-framework/task-types/nonexistent"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get(
            f"/api/risk-framework/task-types/{TASK_TYPE_ID}"
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/tiers
# ---------------------------------------------------------------------------


class TestListTiers:
    """Tests for GET /api/risk-framework/tiers endpoint."""

    def test_returns_three_tier_definitions(
        self, client: TestClient
    ) -> None:
        """Returns exactly 3 tier definitions (high, medium, low)."""
        response = client.get("/api/risk-framework/tiers")
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        tier_levels = {t["tier_level"] for t in body}
        assert tier_levels == {"high", "medium", "low"}

    def test_tier_definitions_have_required_fields(
        self, client: TestClient
    ) -> None:
        """Each tier definition includes all required control set fields."""
        response = client.get("/api/risk-framework/tiers")
        assert response.status_code == 200
        for tier in response.json():
            assert "hitl_required" in tier
            assert "audit_depth" in tier
            assert "validations" in tier
            assert "enforcement_type" in tier

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get("/api/risk-framework/tiers")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/tiers/{tier_level}
# ---------------------------------------------------------------------------


class TestGetTier:
    """Tests for GET /api/risk-framework/tiers/{tier_level}."""

    @pytest.mark.parametrize("tier_level", ["high", "medium", "low"])
    def test_returns_valid_tier_definition(
        self, client: TestClient, tier_level: str
    ) -> None:
        """Returns tier definition for valid tier levels."""
        response = client.get(
            f"/api/risk-framework/tiers/{tier_level}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tier_level"] == tier_level

    def test_returns_400_for_invalid_tier(
        self, client: TestClient
    ) -> None:
        """Returns 400 for invalid tier level."""
        response = client.get("/api/risk-framework/tiers/critical")
        assert response.status_code == 400
        assert "Invalid tier level" in response.json()["detail"]
        assert "critical" in response.json()["detail"]

    def test_returns_400_for_uppercase_tier(
        self, client: TestClient
    ) -> None:
        """Returns 400 for uppercase tier level (case-sensitive)."""
        response = client.get("/api/risk-framework/tiers/HIGH")
        assert response.status_code == 400
        assert "Invalid tier level" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: POST /api/risk-framework/profiles
# ---------------------------------------------------------------------------


class TestCreateProfile:
    """Tests for POST /api/risk-framework/profiles endpoint."""

    def test_creates_profile_successfully(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 201 with created profile on valid request."""
        payload = {
            "profile_name": "GMP Pharma Profile",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [
                {
                    "task_type_id": "document_generation",
                    "assigned_tier": "high",
                    "justification": "High risk due to regulatory content generation in GxP environment.",
                }
            ],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Creating new risk profile"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["profile_name"] == "GMP Pharma Profile"
        mock_risk_service.create_profile.assert_called_once()

    def test_returns_422_for_short_profile_name(
        self, client: TestClient
    ) -> None:
        """Returns 422 when profile_name is too short (< 3 chars)."""
        payload = {
            "profile_name": "AB",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [
                {
                    "task_type_id": "document_generation",
                    "assigned_tier": "high",
                    "justification": "Valid justification text here.",
                }
            ],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_empty_regulatory_frameworks(
        self, client: TestClient
    ) -> None:
        """Returns 422 when regulatory_frameworks is empty."""
        payload = {
            "profile_name": "Valid Profile Name",
            "regulatory_frameworks": [],
            "overrides": [
                {
                    "task_type_id": "document_generation",
                    "assigned_tier": "high",
                    "justification": "Valid justification text here.",
                }
            ],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_empty_overrides(
        self, client: TestClient
    ) -> None:
        """Returns 422 when overrides array is empty."""
        payload = {
            "profile_name": "Valid Profile Name",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_duplicate_task_type_ids_in_overrides(
        self, client: TestClient
    ) -> None:
        """Returns 422 when overrides contain duplicate task_type_ids."""
        payload = {
            "profile_name": "Valid Profile Name",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [
                {
                    "task_type_id": "document_generation",
                    "assigned_tier": "high",
                    "justification": "First override justification text.",
                },
                {
                    "task_type_id": "document_generation",
                    "assigned_tier": "medium",
                    "justification": "Duplicate override justification text.",
                },
            ],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_invalid_task_type_id_pattern(
        self, client: TestClient
    ) -> None:
        """Returns 422 when task_type_id has invalid characters."""
        payload = {
            "profile_name": "Valid Profile Name",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [
                {
                    "task_type_id": "Invalid-ID!",
                    "assigned_tier": "high",
                    "justification": "Valid justification text here.",
                }
            ],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_when_service_raises_validation_error(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 422 when service raises ValueError for validation."""
        mock_risk_service.create_profile.side_effect = ValueError(
            "Task type 'unknown_type' not found in registry."
        )
        payload = {
            "profile_name": "Valid Profile Name",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [
                {
                    "task_type_id": "unknown_type",
                    "assigned_tier": "high",
                    "justification": "Valid justification text here.",
                }
            ],
        }
        response = client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        payload = {
            "profile_name": "Valid Profile Name",
            "regulatory_frameworks": ["21_cfr_part_11"],
            "overrides": [
                {
                    "task_type_id": "document_generation",
                    "assigned_tier": "high",
                    "justification": "Valid justification text here.",
                }
            ],
        }
        response = unauthorized_client.post(
            "/api/risk-framework/profiles",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/profiles
# ---------------------------------------------------------------------------


class TestGetActiveProfile:
    """Tests for GET /api/risk-framework/profiles endpoint."""

    def test_returns_active_profile(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns the active profile for the company."""
        response = client.get("/api/risk-framework/profiles")
        assert response.status_code == 200
        body = response.json()
        assert body["profile_name"] == "GMP Pharma Profile"
        assert body["is_active"] is True

    def test_returns_404_when_no_active_profile(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 404 when no active profile exists for the company."""
        mock_risk_service.get_active_profile.return_value = None
        response = client.get("/api/risk-framework/profiles")
        assert response.status_code == 404
        assert "No active risk profile" in response.json()["detail"]

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get(
            "/api/risk-framework/profiles"
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: PUT /api/risk-framework/profiles/{profile_id}
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    """Tests for PUT /api/risk-framework/profiles/{profile_id}."""

    def test_updates_profile_successfully(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 200 with updated profile on valid request."""
        payload = {
            "profile_name": "Updated Profile Name",
        }
        response = client.put(
            f"/api/risk-framework/profiles/{PROFILE_ID}",
            json=payload,
            headers={"X-Change-Reason": "Updating profile name"},
        )
        assert response.status_code == 200
        mock_risk_service.update_profile.assert_called_once()

    def test_returns_404_for_unknown_profile(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 404 when profile is not found."""
        mock_risk_service.update_profile.side_effect = ValueError(
            "Profile not found for this company."
        )
        unknown_id = uuid4()
        payload = {"profile_name": "Updated Name"}
        response = client.put(
            f"/api/risk-framework/profiles/{unknown_id}",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_422_for_validation_error(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns 422 when service raises validation ValueError."""
        mock_risk_service.update_profile.side_effect = ValueError(
            "Task type 'invalid_type' does not exist in registry."
        )
        payload = {
            "overrides": [
                {
                    "task_type_id": "invalid_type",
                    "assigned_tier": "low",
                    "justification": "Valid justification text here.",
                }
            ],
        }
        response = client.put(
            f"/api/risk-framework/profiles/{PROFILE_ID}",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_short_profile_name(
        self, client: TestClient
    ) -> None:
        """Returns 422 when profile_name is too short."""
        payload = {"profile_name": "AB"}
        response = client.put(
            f"/api/risk-framework/profiles/{PROFILE_ID}",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        payload = {"profile_name": "Updated Name"}
        response = unauthorized_client.put(
            f"/api/risk-framework/profiles/{PROFILE_ID}",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/profiles/history
# ---------------------------------------------------------------------------


class TestGetProfileHistory:
    """Tests for GET /api/risk-framework/profiles/history endpoint."""

    def test_returns_paginated_profile_history(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns paginated list of all profiles (active and inactive)."""
        response = client.get("/api/risk-framework/profiles/history")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 1

    def test_pagination_params_passed_to_service(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Pagination parameters are forwarded to the service."""
        response = client.get(
            "/api/risk-framework/profiles/history?limit=10&offset=5"
        )
        assert response.status_code == 200
        call_kwargs = mock_risk_service.get_profile_history.call_args.kwargs
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/checkpoints
# ---------------------------------------------------------------------------


class TestListCheckpoints:
    """Tests for GET /api/risk-framework/checkpoints endpoint."""

    def test_returns_paginated_checkpoints(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns paginated list of HITL checkpoints."""
        response = client.get("/api/risk-framework/checkpoints")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 1
        assert body["items"][0]["status"] == "pending"

    def test_filter_by_status(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Passes status filter to the service."""
        response = client.get(
            "/api/risk-framework/checkpoints?status=pending"
        )
        assert response.status_code == 200
        call_kwargs = mock_hitl_service.list_checkpoints.call_args.kwargs
        assert call_kwargs["filters"].status == "pending"

    def test_filter_by_task_type_id(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Passes task_type_id filter to the service."""
        response = client.get(
            "/api/risk-framework/checkpoints?task_type_id=document_generation"
        )
        assert response.status_code == 200
        call_kwargs = mock_hitl_service.list_checkpoints.call_args.kwargs
        assert call_kwargs["filters"].task_type_id == "document_generation"

    def test_filter_by_date_range(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Passes date range filters to the service."""
        response = client.get(
            "/api/risk-framework/checkpoints"
            "?start_date=2025-01-01T00:00:00Z"
            "&end_date=2025-06-30T23:59:59Z"
        )
        assert response.status_code == 200
        call_kwargs = mock_hitl_service.list_checkpoints.call_args.kwargs
        assert call_kwargs["filters"].start_date is not None
        assert call_kwargs["filters"].end_date is not None

    def test_pagination_params_passed_to_service(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Pagination parameters are forwarded to the service."""
        response = client.get(
            "/api/risk-framework/checkpoints?limit=50&offset=20"
        )
        assert response.status_code == 200
        call_kwargs = mock_hitl_service.list_checkpoints.call_args.kwargs
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 20

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get(
            "/api/risk-framework/checkpoints"
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: POST /api/risk-framework/checkpoints/{checkpoint_id}/review
# ---------------------------------------------------------------------------


class TestReviewCheckpoint:
    """Tests for POST /api/risk-framework/checkpoints/{id}/review."""

    def test_approves_checkpoint_successfully(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 200 with approved checkpoint on valid approval."""
        payload = {
            "action": "approve",
            "reviewer_comments": "Looks good.",
        }
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Approving checkpoint"},
        )
        assert response.status_code == 200
        mock_hitl_service.review_checkpoint.assert_called_once()

    def test_rejects_checkpoint_with_comments(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 200 with rejected checkpoint when comments provided."""
        mock_hitl_service.review_checkpoint.return_value = (
            _make_checkpoint_response(status="rejected")
        )
        payload = {
            "action": "reject",
            "reviewer_comments": "Output contains inaccuracies.",
        }
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Rejecting checkpoint"},
        )
        assert response.status_code == 200

    def test_returns_422_for_reject_without_comments(
        self, client: TestClient
    ) -> None:
        """Returns 422 when rejecting without reviewer_comments."""
        payload = {
            "action": "reject",
            "reviewer_comments": None,
        }
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_reject_with_empty_comments(
        self, client: TestClient
    ) -> None:
        """Returns 422 when rejecting with empty/whitespace comments."""
        payload = {
            "action": "reject",
            "reviewer_comments": "   ",
        }
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_422_for_invalid_action(
        self, client: TestClient
    ) -> None:
        """Returns 422 when action is not 'approve' or 'reject'."""
        payload = {
            "action": "escalate",
            "reviewer_comments": "Some comment.",
        }
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422

    def test_returns_403_for_insufficient_permission(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 403 when service raises InsufficientReviewPermissionError."""
        mock_hitl_service.review_checkpoint.side_effect = (
            InsufficientReviewPermissionError(user_id=42)
        )
        payload = {"action": "approve"}
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["detail"]

    def test_returns_404_for_unknown_checkpoint(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 404 when checkpoint is not found."""
        unknown_id = uuid4()
        mock_hitl_service.review_checkpoint.side_effect = (
            CheckpointNotFoundError(checkpoint_id=unknown_id, company_id=1)
        )
        payload = {"action": "approve"}
        response = client.post(
            f"/api/risk-framework/checkpoints/{unknown_id}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_returns_409_for_already_reviewed_checkpoint(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 409 when checkpoint is not in pending state."""
        mock_hitl_service.review_checkpoint.side_effect = (
            CheckpointNotPendingError(
                checkpoint_id=CHECKPOINT_ID, current_status="approved"
            )
        )
        payload = {"action": "approve"}
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 409
        assert "already in state" in response.json()["detail"].lower()

    def test_returns_409_for_concurrent_review(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 409 when another user already reviewed the checkpoint."""
        mock_hitl_service.review_checkpoint.side_effect = (
            ConcurrentReviewError(checkpoint_id=CHECKPOINT_ID)
        )
        payload = {"action": "approve"}
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 409
        assert "already reviewed by another user" in response.json()["detail"].lower()

    def test_returns_422_for_rejection_requires_comments_error(
        self, client: TestClient, mock_hitl_service: AsyncMock
    ) -> None:
        """Returns 422 when service raises RejectionRequiresCommentsError."""
        mock_hitl_service.review_checkpoint.side_effect = (
            RejectionRequiresCommentsError()
        )
        payload = {"action": "reject", "reviewer_comments": "x"}
        response = client.post(
            f"/api/risk-framework/checkpoints/{CHECKPOINT_ID}/review",
            json=payload,
            headers={"X-Change-Reason": "Test"},
        )
        assert response.status_code == 422
        assert "reviewer_comments" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/operation-logs
# ---------------------------------------------------------------------------


class TestListOperationLogs:
    """Tests for GET /api/risk-framework/operation-logs endpoint."""

    def test_returns_paginated_operation_logs(
        self, client: TestClient, mock_session: AsyncMock
    ) -> None:
        """Returns paginated list of operation logs."""
        # Mock the count query and data query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_data_result]
        )

        response = client.get("/api/risk-framework/operation-logs")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 0

    def test_pagination_params_applied(
        self, client: TestClient, mock_session: AsyncMock
    ) -> None:
        """Pagination parameters are applied to the query."""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_data_result]
        )

        response = client.get(
            "/api/risk-framework/operation-logs?limit=50&offset=10"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 50
        assert body["offset"] == 10

    def test_filter_by_risk_tier(
        self, client: TestClient, mock_session: AsyncMock
    ) -> None:
        """Accepts risk_tier filter parameter."""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_data_result]
        )

        response = client.get(
            "/api/risk-framework/operation-logs?risk_tier=high"
        )
        assert response.status_code == 200

    def test_filter_by_task_type_id(
        self, client: TestClient, mock_session: AsyncMock
    ) -> None:
        """Accepts task_type_id filter parameter."""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_data_result]
        )

        response = client.get(
            "/api/risk-framework/operation-logs"
            "?task_type_id=document_generation"
        )
        assert response.status_code == 200

    def test_filter_by_date_range(
        self, client: TestClient, mock_session: AsyncMock
    ) -> None:
        """Accepts date range filter parameters."""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_data_result]
        )

        response = client.get(
            "/api/risk-framework/operation-logs"
            "?start_date=2025-01-01T00:00:00Z"
            "&end_date=2025-06-30T23:59:59Z"
        )
        assert response.status_code == 200

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get(
            "/api/risk-framework/operation-logs"
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/risk-framework/dashboard-stats
# ---------------------------------------------------------------------------


class TestGetDashboardStats:
    """Tests for GET /api/risk-framework/dashboard-stats endpoint."""

    def test_returns_dashboard_stats(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Returns dashboard statistics with correct structure."""
        response = client.get("/api/risk-framework/dashboard-stats")
        assert response.status_code == 200
        body = response.json()
        assert "operations_by_tier" in body
        assert "pending_checkpoints" in body
        assert "expired_checkpoints" in body
        assert "blocked_operations" in body
        assert "active_profile_name" in body
        assert body["operations_by_tier"]["high"] == 5
        assert body["pending_checkpoints"] == 3

    def test_unauthorized_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """Returns 403 when user lacks required role."""
        response = unauthorized_client.get(
            "/api/risk-framework/dashboard-stats"
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: X-Company-Id scoping
# ---------------------------------------------------------------------------


class TestCompanyScoping:
    """Tests for X-Company-Id header enforcement and tenant scoping."""

    def test_company_id_passed_to_service(
        self, client: TestClient, mock_risk_service: AsyncMock
    ) -> None:
        """Company ID from tenant context is passed to service calls."""
        client.get("/api/risk-framework/task-types")
        call_kwargs = mock_risk_service.get_task_types.call_args.kwargs
        assert call_kwargs["company_id"] == TENANT_CTX.company_id

    def test_different_company_scopes_independently(
        self,
        mock_risk_service: AsyncMock,
        mock_hitl_service: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """Different company IDs result in different service calls."""
        other_tenant = TenantContext(
            company_id=99,
            company_slug="other-company",
            user_id=10,
            membership_role="admin",
        )
        app = _build_app(
            mock_risk_service, mock_hitl_service, mock_session,
            tenant_ctx=other_tenant,
        )
        with (
            patch(
                "alcoabase.api.risk_framework._risk_service",
                mock_risk_service,
            ),
            patch(
                "alcoabase.api.risk_framework._hitl_service",
                mock_hitl_service,
            ),
        ):
            other_client = TestClient(app, raise_server_exceptions=False)
            other_client.get("/api/risk-framework/task-types")
            call_kwargs = mock_risk_service.get_task_types.call_args.kwargs
            assert call_kwargs["company_id"] == 99
