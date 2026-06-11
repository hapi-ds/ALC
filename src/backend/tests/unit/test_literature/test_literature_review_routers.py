"""Unit tests for literature review API routers.

Tests cover:
- Screening protocol router (POST/GET/PUT/DELETE /protocols)
- SLR review router (POST/GET /reviews)
- Contradiction router (GET /contradictions, PUT status)
- Novelty router (GET /novelty, PUT status)
- Role-based access enforcement (403 for unauthorized roles)
- X-Company-Id header requirement (400 when missing)
- X-Change-Reason requirement via middleware (400 when missing on mutations)
- Exception mapping (service errors → correct HTTP responses)

References:
    - Requirements: 8.8, 9.10, 10.9
    - Task: 15.5 Write unit tests for API routers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.review.exceptions import (
    AlertNotFoundError,
    ConfigurationRangeError,
    FlagNotFoundError,
    InvalidStateTransitionError,
    NoCriteriaDefinedError,
    ProtocolNotFoundError,
    ReviewNotFoundError,
)
from alcoabase.main import app

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def member_context() -> TenantContext:
    """Create a TenantContext with member role (read-only)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="member",
    )


@pytest.fixture
def document_admin_context() -> TenantContext:
    """Create a TenantContext with document_admin role (can mutate)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="document_admin",
    )


@pytest.fixture
def system_admin_context() -> TenantContext:
    """Create a TenantContext with system_admin role."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="system_admin",
    )


@pytest.fixture
def viewer_context() -> TenantContext:
    """Create a TenantContext with viewer role (insufficient for any operation)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="viewer",
    )


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_client_factory(tenant_ctx: TenantContext, mock_session: AsyncMock):
    """Build overrides dict for FastAPI dependency injection."""

    async def _override_tenant():
        return tenant_ctx

    async def _override_db():
        yield mock_session

    return {
        get_tenant_context: _override_tenant,
        get_db_session: _override_db,
    }


@pytest_asyncio.fixture
async def admin_client(
    document_admin_context: TenantContext, mock_db_session: AsyncMock
) -> AsyncClient:
    """AsyncClient with document_admin role and required headers."""
    app.dependency_overrides = _make_client_factory(
        document_admin_context, mock_db_session
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def member_client(
    member_context: TenantContext, mock_db_session: AsyncMock
) -> AsyncClient:
    """AsyncClient with member role and required headers."""
    app.dependency_overrides = _make_client_factory(
        member_context, mock_db_session
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


@pytest_asyncio.fixture
async def viewer_client(
    viewer_context: TenantContext, mock_db_session: AsyncMock
) -> AsyncClient:
    """AsyncClient with viewer role (insufficient permissions)."""
    app.dependency_overrides = _make_client_factory(
        viewer_context, mock_db_session
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def system_admin_client(
    system_admin_context: TenantContext, mock_db_session: AsyncMock
) -> AsyncClient:
    """AsyncClient with system_admin role."""
    app.dependency_overrides = _make_client_factory(
        system_admin_context, mock_db_session
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "42",
            "X-Company-Id": "1",
            "X-Change-Reason": "Unit test",
        },
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Screening Protocol Router Tests
# ---------------------------------------------------------------------------


class TestScreeningProtocolRouter:
    """Tests for /api/literature/screening/protocols endpoints."""

    PROTOCOLS_URL = "/api/literature/screening/protocols"

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_create_protocol_returns_201(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /protocols returns 201 on successful creation."""
        mock_service.create_protocol = AsyncMock(
            return_value={"id": 1, "name": "Test Protocol", "version": 1}
        )

        resp = await admin_client.post(
            self.PROTOCOLS_URL,
            json={
                "name": "Test Protocol",
                "inclusion_criteria": ["keyword1"],
            },
        )

        assert resp.status_code == 201
        assert resp.json()["id"] == 1

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_create_protocol_returns_422_no_criteria(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /protocols returns 422 when no criteria defined."""
        mock_service.create_protocol = AsyncMock(
            side_effect=NoCriteriaDefinedError()
        )

        resp = await admin_client.post(
            self.PROTOCOLS_URL,
            json={
                "name": "Empty Protocol",
                "inclusion_criteria": ["at least one"],
            },
        )

        assert resp.status_code == 422

    async def test_create_protocol_returns_403_for_member(
        self, member_client: AsyncClient
    ) -> None:
        """POST /protocols returns 403 for member role."""
        resp = await member_client.post(
            self.PROTOCOLS_URL,
            json={
                "name": "Test Protocol",
                "inclusion_criteria": ["keyword1"],
            },
            headers={"X-Change-Reason": "Testing"},
        )

        assert resp.status_code == 403

    async def test_create_protocol_returns_403_for_viewer(
        self, viewer_client: AsyncClient
    ) -> None:
        """POST /protocols returns 403 for viewer role."""
        resp = await viewer_client.post(
            self.PROTOCOLS_URL,
            json={
                "name": "Test Protocol",
                "inclusion_criteria": ["keyword1"],
            },
        )

        assert resp.status_code == 403

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_list_protocols_returns_200(
        self, mock_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /protocols returns 200 with paginated results."""
        mock_service.list_protocols = AsyncMock(
            return_value=(
                [{"id": 1, "name": "Protocol A"}],
                1,
            )
        )

        resp = await member_client.get(self.PROTOCOLS_URL)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    async def test_list_protocols_returns_403_for_viewer(
        self, viewer_client: AsyncClient
    ) -> None:
        """GET /protocols returns 403 for viewer role."""
        resp = await viewer_client.get(self.PROTOCOLS_URL)

        assert resp.status_code == 403

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_get_protocol_returns_200(
        self, mock_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /protocols/{id} returns 200 with protocol details."""
        mock_service.get_protocol = AsyncMock(
            return_value={"id": 1, "name": "Protocol A", "version": 1}
        )

        resp = await member_client.get(f"{self.PROTOCOLS_URL}/1")

        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_get_protocol_returns_404(
        self, mock_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /protocols/{id} returns 404 when not found."""
        mock_service.get_protocol = AsyncMock(
            side_effect=ProtocolNotFoundError(
                "Not found", protocol_id=999, company_id=1
            )
        )

        resp = await member_client.get(f"{self.PROTOCOLS_URL}/999")

        assert resp.status_code == 404

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_update_protocol_returns_200(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """PUT /protocols/{id} returns 200 on successful update."""
        mock_service.update_protocol = AsyncMock(
            return_value={"id": 1, "name": "Updated", "version": 2}
        )

        resp = await admin_client.put(
            f"{self.PROTOCOLS_URL}/1",
            json={"name": "Updated"},
        )

        assert resp.status_code == 200
        assert resp.json()["version"] == 2

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_update_protocol_returns_404(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """PUT /protocols/{id} returns 404 when not found."""
        mock_service.update_protocol = AsyncMock(
            side_effect=ProtocolNotFoundError(
                "Not found", protocol_id=999, company_id=1
            )
        )

        resp = await admin_client.put(
            f"{self.PROTOCOLS_URL}/999",
            json={"name": "Renamed"},
        )

        assert resp.status_code == 404

    async def test_update_protocol_returns_403_for_member(
        self, member_client: AsyncClient
    ) -> None:
        """PUT /protocols/{id} returns 403 for member role."""
        resp = await member_client.put(
            f"{self.PROTOCOLS_URL}/1",
            json={"name": "Updated"},
            headers={"X-Change-Reason": "Testing"},
        )

        assert resp.status_code == 403

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_delete_protocol_returns_200(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """DELETE /protocols/{id} returns 200 (soft-delete/archive)."""
        mock_service.archive_protocol = AsyncMock(
            return_value={"id": 1, "status": "archived"}
        )

        resp = await admin_client.delete(f"{self.PROTOCOLS_URL}/1")

        assert resp.status_code == 200

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_delete_protocol_returns_409_on_invalid_transition(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """DELETE /protocols/{id} returns 409 for invalid state transition."""
        mock_service.archive_protocol = AsyncMock(
            side_effect=InvalidStateTransitionError(
                "Already archived",
                current_state="archived",
                target_state="archived",
            )
        )

        resp = await admin_client.delete(f"{self.PROTOCOLS_URL}/1")

        assert resp.status_code == 409

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_activate_protocol_returns_200(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /protocols/{id}/activate returns 200 on success."""
        mock_service.activate_protocol = AsyncMock(
            return_value={"id": 1, "status": "active"}
        )

        resp = await admin_client.post(
            f"{self.PROTOCOLS_URL}/1/activate",
        )

        assert resp.status_code == 200

    @patch(
        "alcoabase.api.literature_screening_router._protocol_service"
    )
    async def test_activate_protocol_returns_409_when_not_draft(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /protocols/{id}/activate returns 409 if not in draft."""
        mock_service.activate_protocol = AsyncMock(
            side_effect=InvalidStateTransitionError(
                "Protocol is not in draft status",
                current_state="active",
                target_state="active",
            )
        )

        resp = await admin_client.post(
            f"{self.PROTOCOLS_URL}/1/activate",
        )

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Screening Configuration Router Tests
# ---------------------------------------------------------------------------


class TestScreeningConfigRouter:
    """Tests for /api/literature/screening/config endpoints."""

    CONFIG_URL = "/api/literature/screening/config"

    @patch(
        "alcoabase.api.literature_screening_router._config_service"
    )
    async def test_get_config_returns_200(
        self, mock_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """GET /config returns 200 with configuration."""
        mock_service.get_config = AsyncMock(
            return_value={
                "auto_screen_on_index": False,
                "default_batch_size": 20,
                "confidence_threshold": 0.8,
                "max_concurrent": 5,
            }
        )

        resp = await admin_client.get(self.CONFIG_URL)

        assert resp.status_code == 200
        assert resp.json()["default_batch_size"] == 20

    async def test_get_config_returns_403_for_member(
        self, member_client: AsyncClient
    ) -> None:
        """GET /config returns 403 for member role (requires document_admin)."""
        resp = await member_client.get(self.CONFIG_URL)

        assert resp.status_code == 403

    @patch(
        "alcoabase.api.literature_screening_router._config_service"
    )
    async def test_update_config_returns_200(
        self, mock_service: MagicMock, system_admin_client: AsyncClient
    ) -> None:
        """PUT /config returns 200 on successful update."""
        mock_service.update_config = AsyncMock(
            return_value={"default_batch_size": 50}
        )

        resp = await system_admin_client.put(
            self.CONFIG_URL,
            json={"default_batch_size": 50},
        )

        assert resp.status_code == 200

    @patch(
        "alcoabase.api.literature_screening_router._config_service"
    )
    async def test_update_config_returns_422_on_range_error(
        self, mock_service: MagicMock, system_admin_client: AsyncClient
    ) -> None:
        """PUT /config returns 422 when value is out of range."""
        mock_service.update_config = AsyncMock(
            side_effect=ConfigurationRangeError(
                "batch_size out of range",
                field_name="default_batch_size",
                value=200,
                min_value=1,
                max_value=100,
            )
        )

        resp = await system_admin_client.put(
            self.CONFIG_URL,
            json={"default_batch_size": 50},
        )

        assert resp.status_code == 422

    async def test_update_config_returns_403_for_document_admin(
        self, admin_client: AsyncClient
    ) -> None:
        """PUT /config returns 403 for document_admin (requires system_admin)."""
        resp = await admin_client.put(
            self.CONFIG_URL,
            json={"default_batch_size": 50},
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# SLR Review Router Tests
# ---------------------------------------------------------------------------


class TestSLRReviewRouter:
    """Tests for /api/literature/reviews endpoints."""

    REVIEWS_URL = "/api/literature/reviews"

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_create_review_returns_201(
        self, mock_get_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /reviews returns 201 on successful creation."""
        mock_service = MagicMock()
        mock_service.create_review = AsyncMock(
            return_value={"id": 1, "name": "Test Review", "status": "protocol_defined"}
        )
        mock_get_service.return_value = mock_service

        resp = await admin_client.post(
            self.REVIEWS_URL,
            json={
                "protocol_id": 1,
                "name": "Test Review",
                "record_filter": {},
            },
        )

        assert resp.status_code == 201
        assert resp.json()["id"] == 1

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_create_review_returns_404_protocol_not_found(
        self, mock_get_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /reviews returns 404 when protocol not found."""
        mock_service = MagicMock()
        mock_service.create_review = AsyncMock(
            side_effect=ProtocolNotFoundError(
                "Protocol not found", protocol_id=999, company_id=1
            )
        )
        mock_get_service.return_value = mock_service

        resp = await admin_client.post(
            self.REVIEWS_URL,
            json={
                "protocol_id": 999,
                "name": "Test Review",
                "record_filter": {},
            },
        )

        assert resp.status_code == 404

    async def test_create_review_returns_403_for_member(
        self, member_client: AsyncClient
    ) -> None:
        """POST /reviews returns 403 for member role."""
        resp = await member_client.post(
            self.REVIEWS_URL,
            json={
                "protocol_id": 1,
                "name": "Test Review",
                "record_filter": {},
            },
            headers={"X-Change-Reason": "Testing"},
        )

        assert resp.status_code == 403

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_list_reviews_returns_200(
        self, mock_get_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /reviews returns 200 with paginated results."""
        mock_service = MagicMock()
        mock_service.list_reviews = AsyncMock(
            return_value=(
                [{"id": 1, "name": "Review A"}],
                1,
            )
        )
        mock_service.get_prisma_flow = AsyncMock(
            return_value={"records_identified": 10}
        )
        mock_get_service.return_value = mock_service

        resp = await member_client.get(self.REVIEWS_URL)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_get_review_returns_200(
        self, mock_get_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /reviews/{id} returns 200 with full details."""
        mock_service = MagicMock()
        mock_service.get_review = AsyncMock(
            return_value={"id": 1, "name": "Review A", "status": "protocol_defined"}
        )
        mock_service.get_prisma_flow = AsyncMock(
            return_value={"records_identified": 10}
        )
        mock_service.get_progress = AsyncMock(
            return_value={"total_records": 10, "screened_count": 0}
        )
        mock_service.compute_inter_rater_reliability = AsyncMock(
            return_value={"agreement_rate": 0.0}
        )
        mock_get_service.return_value = mock_service

        resp = await member_client.get(f"{self.REVIEWS_URL}/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert "prisma_flow" in data

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_get_review_returns_404(
        self, mock_get_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /reviews/{id} returns 404 when review not found."""
        mock_service = MagicMock()
        mock_service.get_review = AsyncMock(
            side_effect=ReviewNotFoundError(
                "Review not found", review_id=999, company_id=1
            )
        )
        mock_get_service.return_value = mock_service

        resp = await member_client.get(f"{self.REVIEWS_URL}/999")

        assert resp.status_code == 404

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_initiate_screening_returns_202(
        self, mock_get_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /reviews/{id}/screen returns 202 with task_id."""
        mock_service = MagicMock()
        mock_service.initiate_screening = AsyncMock(
            return_value={"task_id": "abc-123", "status": "screening_in_progress"}
        )
        mock_get_service.return_value = mock_service

        resp = await admin_client.post(f"{self.REVIEWS_URL}/1/screen")

        assert resp.status_code == 202
        assert resp.json()["task_id"] == "abc-123"

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_initiate_screening_returns_409_invalid_state(
        self, mock_get_service: MagicMock, admin_client: AsyncClient
    ) -> None:
        """POST /reviews/{id}/screen returns 409 on invalid state transition."""
        mock_service = MagicMock()
        mock_service.initiate_screening = AsyncMock(
            side_effect=InvalidStateTransitionError(
                "Cannot start screening in completed state",
                current_state="completed",
                target_state="screening_in_progress",
            )
        )
        mock_get_service.return_value = mock_service

        resp = await admin_client.post(f"{self.REVIEWS_URL}/1/screen")

        assert resp.status_code == 409

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_get_progress_returns_200(
        self, mock_get_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /reviews/{id}/progress returns 200 with progress data."""
        mock_service = MagicMock()
        mock_service.get_progress = AsyncMock(
            return_value={
                "total_records": 100,
                "screened_count": 50,
                "pending_count": 50,
            }
        )
        mock_get_service.return_value = mock_service

        resp = await member_client.get(f"{self.REVIEWS_URL}/1/progress")

        assert resp.status_code == 200
        assert resp.json()["total_records"] == 100

    @patch(
        "alcoabase.api.literature_review_router._get_review_service"
    )
    async def test_get_report_returns_200(
        self, mock_get_service: MagicMock, member_client: AsyncClient
    ) -> None:
        """GET /reviews/{id}/report returns 200 with report JSON."""
        mock_service = MagicMock()
        mock_service.generate_report = AsyncMock(
            return_value={"review_id": 1, "prisma_flow": {}}
        )
        mock_get_service.return_value = mock_service

        resp = await member_client.get(f"{self.REVIEWS_URL}/1/report")

        assert resp.status_code == 200

    async def test_reviews_missing_x_company_id_returns_400(
        self,
        document_admin_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """POST /reviews returns 400 when X-Company-Id header is missing."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Change-Reason": "Unit test",
                # No X-Company-Id header
            },
        ) as client:
            resp = await client.post(
                self.REVIEWS_URL,
                json={
                    "protocol_id": 1,
                    "name": "Test Review",
                    "record_filter": {},
                },
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400
        assert "X-Company-Id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Contradiction Router Tests
# ---------------------------------------------------------------------------


class TestContradictionRouter:
    """Tests for /api/literature/contradictions endpoints."""

    CONTRADICTIONS_URL = "/api/literature/contradictions"

    @patch(
        "alcoabase.api.literature_contradiction_router._get_alert_or_404"
    )
    async def test_get_contradiction_returns_200(
        self, mock_get_alert: AsyncMock, member_client: AsyncClient
    ) -> None:
        """GET /contradictions/{id} returns 200 with alert details."""
        mock_alert = MagicMock()
        mock_alert.id = 1
        mock_alert.ingestion_record_id = 10
        mock_alert.internal_document_id = "doc-1"
        mock_alert.company_id = 1
        mock_alert.severity = "major"
        mock_alert.contradiction_description = "Contradicts SOP"
        mock_alert.evidence_from_literature = "Paper says..."
        mock_alert.recommended_action = "Review SOP"
        mock_alert.confidence = 0.85
        mock_alert.affected_internal_sections = ["section 3.1"]
        mock_alert.status = "new"
        mock_alert.acknowledged_by = None
        mock_alert.acknowledged_at = None
        mock_alert.resolution_note = None
        mock_alert.change_request_id = None
        mock_alert.resolved_by = None
        mock_alert.resolved_at = None
        mock_alert.dismissal_reason = None
        mock_alert.dismissed_by = None
        mock_alert.dismissed_at = None
        mock_alert.impact_report_id = None
        mock_alert.created_at = None
        mock_get_alert.return_value = mock_alert

        resp = await member_client.get(f"{self.CONTRADICTIONS_URL}/1")

        assert resp.status_code == 200
        assert resp.json()["severity"] == "major"

    @patch(
        "alcoabase.api.literature_contradiction_router._get_alert_or_404"
    )
    async def test_get_contradiction_returns_404(
        self, mock_get_alert: AsyncMock, member_client: AsyncClient
    ) -> None:
        """GET /contradictions/{id} returns 404 when not found."""
        mock_get_alert.side_effect = AlertNotFoundError(
            "Not found", alert_id=999, company_id=1
        )

        resp = await member_client.get(f"{self.CONTRADICTIONS_URL}/999")

        assert resp.status_code == 404

    @patch(
        "alcoabase.api.literature_contradiction_router._get_alert_or_404"
    )
    async def test_update_contradiction_status_returns_200(
        self, mock_get_alert: AsyncMock, admin_client: AsyncClient
    ) -> None:
        """PUT /contradictions/{id}/status returns 200 on valid transition."""
        mock_alert = MagicMock()
        mock_alert.id = 1
        mock_alert.status = "new"
        mock_alert.company_id = 1
        mock_alert.ingestion_record_id = 10
        mock_alert.internal_document_id = "doc-1"
        mock_alert.severity = "major"
        mock_alert.contradiction_description = "Contradicts"
        mock_alert.evidence_from_literature = "Evidence"
        mock_alert.recommended_action = "Review"
        mock_alert.confidence = 0.85
        mock_alert.affected_internal_sections = []
        mock_alert.acknowledged_by = None
        mock_alert.acknowledged_at = None
        mock_alert.resolution_note = None
        mock_alert.change_request_id = None
        mock_alert.resolved_by = None
        mock_alert.resolved_at = None
        mock_alert.dismissal_reason = None
        mock_alert.dismissed_by = None
        mock_alert.dismissed_at = None
        mock_alert.impact_report_id = None
        mock_alert.created_at = None
        mock_get_alert.return_value = mock_alert

        resp = await admin_client.put(
            f"{self.CONTRADICTIONS_URL}/1/status",
            json={"status": "acknowledged"},
        )

        assert resp.status_code == 200

    @patch(
        "alcoabase.api.literature_contradiction_router._get_alert_or_404"
    )
    async def test_update_contradiction_status_returns_409_invalid_transition(
        self, mock_get_alert: AsyncMock, admin_client: AsyncClient
    ) -> None:
        """PUT /contradictions/{id}/status returns 409 on invalid transition."""
        mock_alert = MagicMock()
        mock_alert.status = "new"  # can only go to "acknowledged", not "resolved"
        mock_get_alert.return_value = mock_alert

        resp = await admin_client.put(
            f"{self.CONTRADICTIONS_URL}/1/status",
            json={"status": "resolved"},
        )

        assert resp.status_code == 409

    async def test_update_contradiction_status_returns_403_for_member(
        self, member_client: AsyncClient
    ) -> None:
        """PUT /contradictions/{id}/status returns 403 for member role."""
        resp = await member_client.put(
            f"{self.CONTRADICTIONS_URL}/1/status",
            json={"status": "acknowledged"},
            headers={"X-Change-Reason": "Testing"},
        )

        assert resp.status_code == 403

    async def test_contradictions_missing_x_company_id_returns_400(
        self,
        member_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """GET /contradictions returns 400 when X-Company-Id missing."""
        app.dependency_overrides = _make_client_factory(
            member_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                # No X-Company-Id header
            },
        ) as client:
            resp = await client.get(self.CONTRADICTIONS_URL)

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    async def test_update_contradiction_missing_x_change_reason_returns_400(
        self,
        document_admin_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """PUT /contradictions/{id}/status returns 400 without X-Change-Reason."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason header
            },
        ) as client:
            resp = await client.put(
                f"{self.CONTRADICTIONS_URL}/1/status",
                json={"status": "acknowledged"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Novelty Router Tests
# ---------------------------------------------------------------------------


class TestNoveltyRouter:
    """Tests for /api/literature/novelty endpoints."""

    NOVELTY_URL = "/api/literature/novelty"

    @patch(
        "alcoabase.api.literature_contradiction_router._get_flag_or_404"
    )
    async def test_update_novelty_status_returns_200(
        self, mock_get_flag: AsyncMock, admin_client: AsyncClient
    ) -> None:
        """PUT /novelty/{id}/status returns 200 on valid transition."""
        mock_flag = MagicMock()
        mock_flag.id = 1
        mock_flag.status = "new"
        mock_flag.ingestion_record_id = 10
        mock_flag.company_id = 1
        mock_flag.novelty_description = "Novel finding"
        mock_flag.relevance_score = 0.9
        mock_flag.high_priority = True
        mock_flag.suggested_document_types = ["SOP"]
        mock_flag.group_id = None
        mock_flag.linked_document_id = None
        mock_flag.acknowledged_by = None
        mock_flag.acknowledged_at = None
        mock_flag.integrated_by = None
        mock_flag.integrated_at = None
        mock_flag.dismissal_reason = None
        mock_flag.dismissed_by = None
        mock_flag.dismissed_at = None
        mock_flag.created_at = None
        mock_flag.updated_at = None
        mock_get_flag.return_value = mock_flag

        resp = await admin_client.put(
            f"{self.NOVELTY_URL}/1/status",
            json={"status": "acknowledged"},
        )

        assert resp.status_code == 200

    @patch(
        "alcoabase.api.literature_contradiction_router._get_flag_or_404"
    )
    async def test_update_novelty_status_returns_409_invalid_transition(
        self, mock_get_flag: AsyncMock, admin_client: AsyncClient
    ) -> None:
        """PUT /novelty/{id}/status returns 409 on invalid transition."""
        mock_flag = MagicMock()
        mock_flag.status = "new"  # can only go to "acknowledged", not "integrated"
        mock_get_flag.return_value = mock_flag

        resp = await admin_client.put(
            f"{self.NOVELTY_URL}/1/status",
            json={"status": "integrated"},
        )

        assert resp.status_code == 409

    @patch(
        "alcoabase.api.literature_contradiction_router._get_flag_or_404"
    )
    async def test_update_novelty_status_returns_404(
        self, mock_get_flag: AsyncMock, admin_client: AsyncClient
    ) -> None:
        """PUT /novelty/{id}/status returns 404 when flag not found."""
        mock_get_flag.side_effect = FlagNotFoundError(
            "Not found", flag_id=999, company_id=1
        )

        resp = await admin_client.put(
            f"{self.NOVELTY_URL}/999/status",
            json={"status": "acknowledged"},
        )

        assert resp.status_code == 404

    async def test_update_novelty_status_returns_403_for_member(
        self, member_client: AsyncClient
    ) -> None:
        """PUT /novelty/{id}/status returns 403 for member role."""
        resp = await member_client.put(
            f"{self.NOVELTY_URL}/1/status",
            json={"status": "acknowledged"},
            headers={"X-Change-Reason": "Testing"},
        )

        assert resp.status_code == 403

    async def test_novelty_missing_x_company_id_returns_400(
        self,
        member_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """GET /novelty returns 400 when X-Company-Id missing."""
        app.dependency_overrides = _make_client_factory(
            member_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                # No X-Company-Id header
            },
        ) as client:
            resp = await client.get(self.NOVELTY_URL)

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    async def test_update_novelty_missing_x_change_reason_returns_400(
        self,
        document_admin_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """PUT /novelty/{id}/status returns 400 without X-Change-Reason."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason header
            },
        ) as client:
            resp = await client.put(
                f"{self.NOVELTY_URL}/1/status",
                json={"status": "acknowledged"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cross-cutting: X-Change-Reason enforcement via middleware
# ---------------------------------------------------------------------------


class TestAuditMiddlewareEnforcement:
    """Test X-Change-Reason enforcement on mutation endpoints.

    The AuditMiddleware enforces X-Change-Reason on all POST/PUT/DELETE
    requests to non-exempt paths.
    """

    async def test_screening_protocol_post_without_change_reason(
        self,
        document_admin_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """POST /protocols returns 400 without X-Change-Reason header."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason
            },
        ) as client:
            resp = await client.post(
                "/api/literature/screening/protocols",
                json={
                    "name": "Test Protocol",
                    "inclusion_criteria": ["keyword1"],
                },
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    async def test_screening_protocol_put_without_change_reason(
        self,
        document_admin_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """PUT /protocols/{id} returns 400 without X-Change-Reason header."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason
            },
        ) as client:
            resp = await client.put(
                "/api/literature/screening/protocols/1",
                json={"name": "Updated"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    async def test_screening_protocol_delete_without_change_reason(
        self,
        document_admin_context: TenantContext,
        mock_db_session: AsyncMock,
    ) -> None:
        """DELETE /protocols/{id} returns 400 without X-Change-Reason header."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # No X-Change-Reason
            },
        ) as client:
            resp = await client.delete(
                "/api/literature/screening/protocols/1",
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 400
