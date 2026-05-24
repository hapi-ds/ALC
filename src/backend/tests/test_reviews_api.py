"""Unit tests for Reviews API endpoints.

Tests the review pipeline endpoints including submission, listing,
session detail, approve/reject, and action item management.
Covers HTTP status codes: 202, 200, 201, 400, 404, 409, 422.

References:
    - Task 10.6: Write unit tests for API endpoints
    - Requirements: 10.1–10.8
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.api.reviews import get_review_pipeline_service
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.services.review_pipeline import ConflictError, ReviewPipelineService


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
def mock_review_service() -> AsyncMock:
    """Create a mock ReviewPipelineService."""
    return AsyncMock(spec=ReviewPipelineService)


class _FakeSession:
    """Fake review session model object that supports attribute access."""

    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


class _FakeActionItem:
    """Fake action item model object that supports attribute access."""

    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


@pytest.fixture
def sample_session() -> dict:
    """Sample review session data."""
    return {
        "id": 1,
        "document_id": 10,
        "document_title": "SOP-001 Manufacturing",
        "document_type": "SOP",
        "status": "Completed",
        "compliance_score": 75.0,
        "summary_failed": False,
        "submitted_by": 42,
        "submitted_at": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC),
        "completed_at": datetime(2025, 6, 15, 11, 0, 0, tzinfo=UTC),
        "agent_reviews": None,
        "master_summary": None,
    }


@pytest.fixture
def sample_action_item() -> dict:
    """Sample action item data."""
    return {
        "id": 1,
        "finding_id": "F-001",
        "title": "Fix critical deviation",
        "description": "Address the critical deviation in section 3.2",
        "severity": "Critical",
        "status": "Open",
        "assigned_to": None,
        "resolved_at": None,
        "resolution_note": None,
        "created_at": datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        "updated_at": None,
    }


@pytest_asyncio.fixture
async def client(
    mock_review_service: AsyncMock,
    tenant_context: TenantContext,
) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""

    async def _override_get_tenant_context():
        return tenant_context

    def _override_review_service():
        return mock_review_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_review_pipeline_service] = _override_review_service

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
    mock_review_service: AsyncMock,
    tenant_context: TenantContext,
) -> AsyncClient:
    """Create an httpx AsyncClient WITHOUT X-Change-Reason header."""

    async def _override_get_tenant_context():
        return tenant_context

    def _override_review_service():
        return mock_review_service

    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_review_pipeline_service] = _override_review_service

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
# Test: POST /api/reviews (Requirement 10.1)
# ---------------------------------------------------------------------------


class TestSubmitReview:
    """Tests for POST /api/reviews."""

    @pytest.mark.asyncio
    async def test_submit_review_returns_202(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 202 Accepted with session_id and status."""
        mock_review_service.submit_review.return_value = _FakeSession(
            {"id": 5, "status": "Pending"}
        )

        response = await client.post(
            "/api/reviews",
            json={"document_id": 10, "document_version_id": 1},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["session_id"] == 5
        assert data["status"] == "Pending"

    @pytest.mark.asyncio
    async def test_submit_review_with_audit_profile(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Passes audit_profile_id to service when provided."""
        mock_review_service.submit_review.return_value = _FakeSession(
            {"id": 6, "status": "Pending"}
        )

        response = await client.post(
            "/api/reviews",
            json={
                "document_id": 10,
                "document_version_id": 1,
                "audit_profile_id": 3,
            },
        )

        assert response.status_code == 202
        mock_review_service.submit_review.assert_called_once_with(
            document_id=10,
            document_version_id=1,
            audit_profile_id=3,
            company_id=1,
            user_id=42,
        )

    @pytest.mark.asyncio
    async def test_submit_review_conflict_returns_409(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 409 when document already has an active review."""
        mock_review_service.submit_review.side_effect = ConflictError(
            "Document already has an active review session"
        )

        response = await client.post(
            "/api/reviews",
            json={"document_id": 10, "document_version_id": 1},
        )

        assert response.status_code == 409
        assert "active review session" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_review_validation_error_returns_422(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 422 when service raises ValueError (e.g., no default profile)."""
        mock_review_service.submit_review.side_effect = ValueError(
            "No default audit profile configured for this company"
        )

        response = await client.post(
            "/api/reviews",
            json={"document_id": 10, "document_version_id": 1},
        )

        assert response.status_code == 422
        assert "audit profile" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_review_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """POST without X-Change-Reason returns 400."""
        response = await client_no_change_reason.post(
            "/api/reviews",
            json={"document_id": 10, "document_version_id": 1},
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_submit_review_invalid_body_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when request body is invalid."""
        response = await client.post(
            "/api/reviews",
            json={"document_id": "not-an-int"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /api/reviews (Requirement 10.2)
# ---------------------------------------------------------------------------


class TestListReviews:
    """Tests for GET /api/reviews."""

    @pytest.mark.asyncio
    async def test_list_reviews_returns_200(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """Returns 200 with paginated list of sessions."""
        mock_review_service.list_sessions.return_value = (
            [_FakeSession(sample_session)],
            1,
        )

        response = await client.get("/api/reviews")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == 1

    @pytest.mark.asyncio
    async def test_list_reviews_with_pagination(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Passes pagination params to service."""
        mock_review_service.list_sessions.return_value = ([], 0)

        response = await client.get(
            "/api/reviews", params={"limit": 5, "offset": 10}
        )

        assert response.status_code == 200
        call_kwargs = mock_review_service.list_sessions.call_args[1]
        assert call_kwargs["limit"] == 5
        assert call_kwargs["offset"] == 10

    @pytest.mark.asyncio
    async def test_list_reviews_with_filters(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Passes filter params to service."""
        mock_review_service.list_sessions.return_value = ([], 0)

        response = await client.get(
            "/api/reviews",
            params={
                "status": "Completed",
                "document_type": "SOP",
                "min_score": 50.0,
                "max_score": 90.0,
            },
        )

        assert response.status_code == 200
        call_kwargs = mock_review_service.list_sessions.call_args[1]
        assert call_kwargs["status"] == "Completed"
        assert call_kwargs["document_type"] == "SOP"
        assert call_kwargs["min_score"] == 50.0
        assert call_kwargs["max_score"] == 90.0

    @pytest.mark.asyncio
    async def test_list_reviews_empty(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 200 with empty list when no sessions exist."""
        mock_review_service.list_sessions.return_value = ([], 0)

        response = await client.get("/api/reviews")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_reviews_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_review_service.list_sessions.return_value = ([], 0)

        response = await client_no_change_reason.get("/api/reviews")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: GET /api/reviews/{session_id} (Requirement 10.3)
# ---------------------------------------------------------------------------


class TestGetReviewSession:
    """Tests for GET /api/reviews/{session_id}."""

    @pytest.mark.asyncio
    async def test_get_session_returns_200(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """Returns 200 with full session detail."""
        mock_review_service.get_session.return_value = _FakeSession(sample_session)

        response = await client.get("/api/reviews/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["document_title"] == "SOP-001 Manufacturing"
        assert data["status"] == "Completed"
        assert data["compliance_score"] == 75.0

    @pytest.mark.asyncio
    async def test_get_session_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 404 when session does not exist or wrong company."""
        mock_review_service.get_session.return_value = None

        response = await client.get("/api/reviews/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Review session not found"

    @pytest.mark.asyncio
    async def test_get_session_no_change_reason_succeeds(
        self,
        client_no_change_reason: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """GET requests do not require X-Change-Reason header."""
        mock_review_service.get_session.return_value = _FakeSession(sample_session)

        response = await client_no_change_reason.get("/api/reviews/1")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: POST /api/reviews/{session_id}/approve (Requirement 10.4)
# ---------------------------------------------------------------------------


class TestApproveReview:
    """Tests for POST /api/reviews/{session_id}/approve."""

    @pytest.mark.asyncio
    async def test_approve_returns_200(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """Returns 200 with updated session when approved."""
        approved = {**sample_session, "status": "Approved"}
        mock_review_service.approve_session.return_value = _FakeSession(approved)

        response = await client.post("/api/reviews/1/approve")

        assert response.status_code == 200
        assert response.json()["status"] == "Approved"
        mock_review_service.approve_session.assert_called_once_with(
            session_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_approve_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 404 when session not found."""
        mock_review_service.approve_session.side_effect = ValueError(
            "Review session not found"
        )

        response = await client.post("/api/reviews/999/approve")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_non_completed_returns_409(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 409 when session is not in Completed status."""
        mock_review_service.approve_session.side_effect = ValueError(
            "Only completed sessions can be approved"
        )

        response = await client.post("/api/reviews/1/approve")

        assert response.status_code == 409
        assert "completed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_approve_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """POST approve without X-Change-Reason returns 400."""
        response = await client_no_change_reason.post("/api/reviews/1/approve")

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: POST /api/reviews/{session_id}/reject (Requirement 10.4)
# ---------------------------------------------------------------------------


class TestRejectReview:
    """Tests for POST /api/reviews/{session_id}/reject."""

    @pytest.mark.asyncio
    async def test_reject_returns_200(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """Returns 200 with updated session when rejected."""
        rejected = {**sample_session, "status": "Rejected"}
        mock_review_service.reject_session.return_value = _FakeSession(rejected)

        response = await client.post("/api/reviews/1/reject")

        assert response.status_code == 200
        assert response.json()["status"] == "Rejected"
        mock_review_service.reject_session.assert_called_once_with(
            session_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_reject_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 404 when session not found."""
        mock_review_service.reject_session.side_effect = ValueError(
            "Review session not found"
        )

        response = await client.post("/api/reviews/999/reject")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_non_completed_returns_409(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 409 when session is not in Completed status."""
        mock_review_service.reject_session.side_effect = ValueError(
            "Only completed sessions can be rejected"
        )

        response = await client.post("/api/reviews/1/reject")

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_reject_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """POST reject without X-Change-Reason returns 400."""
        response = await client_no_change_reason.post("/api/reviews/1/reject")

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: GET /api/reviews/{session_id}/action-items (Requirement 10.5)
# ---------------------------------------------------------------------------


class TestListActionItems:
    """Tests for GET /api/reviews/{session_id}/action-items."""

    @pytest.mark.asyncio
    async def test_list_action_items_returns_200(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_action_item: dict,
    ):
        """Returns 200 with list of action items."""
        mock_review_service.list_action_items.return_value = [
            _FakeActionItem(sample_action_item)
        ]

        response = await client.get("/api/reviews/1/action-items")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["finding_id"] == "F-001"
        assert data[0]["severity"] == "Critical"
        assert data[0]["status"] == "Open"

    @pytest.mark.asyncio
    async def test_list_action_items_session_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 404 when session not found."""
        mock_review_service.list_action_items.side_effect = ValueError(
            "Review session not found"
        )

        response = await client.get("/api/reviews/999/action-items")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_action_items_empty(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 200 with empty list when no action items exist."""
        mock_review_service.list_action_items.return_value = []

        response = await client.get("/api/reviews/1/action-items")

        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# Test: POST /api/reviews/{session_id}/action-items (Requirement 10.6)
# ---------------------------------------------------------------------------


class TestCreateActionItem:
    """Tests for POST /api/reviews/{session_id}/action-items."""

    @pytest.mark.asyncio
    async def test_create_action_item_returns_201(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_action_item: dict,
    ):
        """Returns 201 with created action item."""
        mock_review_service.create_action_item.return_value = _FakeActionItem(
            sample_action_item
        )

        response = await client.post(
            "/api/reviews/1/action-items",
            json={
                "finding_id": "F-001",
                "title": "Fix critical deviation",
                "description": "Address the critical deviation in section 3.2",
                "severity": "Critical",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["finding_id"] == "F-001"
        assert data["title"] == "Fix critical deviation"

    @pytest.mark.asyncio
    async def test_create_action_item_session_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 404 when session not found."""
        mock_review_service.create_action_item.side_effect = ValueError(
            "Review session not found"
        )

        response = await client.post(
            "/api/reviews/999/action-items",
            json={
                "finding_id": "F-001",
                "title": "Fix issue",
                "description": "Fix the issue",
                "severity": "Major",
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_action_item_invalid_body_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when request body is invalid (missing required fields)."""
        response = await client.post(
            "/api/reviews/1/action-items",
            json={"finding_id": "F-001"},  # missing title, description, severity
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_action_item_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """POST without X-Change-Reason returns 400."""
        response = await client_no_change_reason.post(
            "/api/reviews/1/action-items",
            json={
                "finding_id": "F-001",
                "title": "Fix issue",
                "description": "Fix the issue",
                "severity": "Major",
            },
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: PATCH /api/reviews/{session_id}/action-items/{item_id} (Req 10.5)
# ---------------------------------------------------------------------------


class TestUpdateActionItem:
    """Tests for PATCH /api/reviews/{session_id}/action-items/{item_id}."""

    @pytest.mark.asyncio
    async def test_update_action_item_returns_200(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_action_item: dict,
    ):
        """Returns 200 with updated action item."""
        updated = {**sample_action_item, "status": "InProgress"}
        mock_review_service.update_action_item.return_value = _FakeActionItem(
            updated
        )

        response = await client.patch(
            "/api/reviews/1/action-items/1",
            json={"status": "InProgress"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "InProgress"
        mock_review_service.update_action_item.assert_called_once_with(
            session_id=1,
            item_id=1,
            status="InProgress",
            resolution_note=None,
            company_id=1,
        )

    @pytest.mark.asyncio
    async def test_update_action_item_with_resolution_note(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_action_item: dict,
    ):
        """Passes resolution_note to service when provided."""
        resolved = {
            **sample_action_item,
            "status": "Resolved",
            "resolution_note": "Fixed in v2.1",
            "resolved_at": datetime(2025, 6, 16, 9, 0, 0, tzinfo=UTC),
        }
        mock_review_service.update_action_item.return_value = _FakeActionItem(
            resolved
        )

        response = await client.patch(
            "/api/reviews/1/action-items/1",
            json={"status": "Resolved", "resolution_note": "Fixed in v2.1"},
        )

        assert response.status_code == 200
        assert response.json()["resolution_note"] == "Fixed in v2.1"

    @pytest.mark.asyncio
    async def test_update_action_item_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """Returns 404 when action item not found."""
        mock_review_service.update_action_item.side_effect = ValueError(
            "Action item not found"
        )

        response = await client.patch(
            "/api/reviews/1/action-items/999",
            json={"status": "InProgress"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_action_item_invalid_body_returns_422(
        self,
        client: AsyncClient,
    ):
        """Returns 422 when request body is invalid."""
        response = await client.patch(
            "/api/reviews/1/action-items/1",
            json={"status": ""},  # empty string fails min_length=1
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_action_item_without_change_reason_returns_400(
        self,
        client_no_change_reason: AsyncClient,
    ):
        """PATCH without X-Change-Reason returns 400."""
        response = await client_no_change_reason.patch(
            "/api/reviews/1/action-items/1",
            json={"status": "InProgress"},
        )

        assert response.status_code == 400
        assert "X-Change-Reason" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: Company scoping (Requirement 1.10)
# ---------------------------------------------------------------------------


class TestReviewsCompanyScoping:
    """Tests that all review operations are scoped to the tenant's company."""

    @pytest.mark.asyncio
    async def test_submit_passes_company_id(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """POST reviews passes company_id from tenant context."""
        mock_review_service.submit_review.return_value = _FakeSession(
            {"id": 1, "status": "Pending"}
        )

        await client.post(
            "/api/reviews",
            json={"document_id": 10, "document_version_id": 1},
        )

        call_kwargs = mock_review_service.submit_review.call_args[1]
        assert call_kwargs["company_id"] == 1

    @pytest.mark.asyncio
    async def test_list_passes_company_id(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
    ):
        """GET reviews passes company_id from tenant context."""
        mock_review_service.list_sessions.return_value = ([], 0)

        await client.get("/api/reviews")

        call_kwargs = mock_review_service.list_sessions.call_args[1]
        assert call_kwargs["company_id"] == 1

    @pytest.mark.asyncio
    async def test_get_session_passes_company_id(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """GET reviews/{id} passes company_id from tenant context."""
        mock_review_service.get_session.return_value = _FakeSession(sample_session)

        await client.get("/api/reviews/1")

        mock_review_service.get_session.assert_called_once_with(
            session_id=1, company_id=1
        )

    @pytest.mark.asyncio
    async def test_approve_passes_company_id(
        self,
        client: AsyncClient,
        mock_review_service: AsyncMock,
        sample_session: dict,
    ):
        """POST approve passes company_id from tenant context."""
        approved = {**sample_session, "status": "Approved"}
        mock_review_service.approve_session.return_value = _FakeSession(approved)

        await client.post("/api/reviews/1/approve")

        mock_review_service.approve_session.assert_called_once_with(
            session_id=1, company_id=1
        )
