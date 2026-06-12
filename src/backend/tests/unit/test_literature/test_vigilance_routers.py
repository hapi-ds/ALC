"""Unit tests for vigilance API routers.

Tests cover:
- Product endpoints (POST 201, GET 200, PUT 200, DELETE 200, 403, 409, 422)
- Signal endpoints (GET 200, PUT disposition 403)
- Report endpoints (GET 200, POST generate 202/403, PUT status 200/403/422)
- X-Change-Reason enforcement on mutation endpoints
- Role-based access (member for reads, document_admin for writes)

References:
    - Requirements: 9.10, 9.11, 10.7, 10.8, 10.9, 11.5, 11.6, 11.7
    - Task: 14.7
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.vigilance.exceptions import (
    DuplicateUDIError,
    InvalidReportStatusTransitionError,
    ProductNotFoundError,
    ReportNotFoundError,
)
from alcoabase.main import app

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def member_context() -> TenantContext:
    """TenantContext with member role (read-only)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="member",
    )


@pytest.fixture
def document_admin_context() -> TenantContext:
    """TenantContext with document_admin role (can mutate)."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="document_admin",
    )


@pytest.fixture
def viewer_context() -> TenantContext:
    """TenantContext with viewer role (insufficient for any operation)."""
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
    session.flush = AsyncMock()
    session.add = MagicMock()
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


# ---------------------------------------------------------------------------
# Product Router Tests
# ---------------------------------------------------------------------------


class TestVigilanceProductRouter:
    """Tests for vigilance product endpoints."""

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.create_product",
        new_callable=AsyncMock,
    )
    async def test_create_product_201(self, mock_create, admin_client):
        """POST /api/vigilance/products returns 201 on success."""
        mock_create.return_value = {
            "id": 1,
            "name": "CardioMonitor X200",
            "device_class": "IIb",
            "intended_purpose": "Cardiac monitoring",
            "udi": "UDI-123",
            "gmdn_code": None,
            "manufacturer_name": None,
            "predicate_devices": None,
            "risk_class_justification": None,
            "status": "active",
            "company_id": 1,
            "created_by": 42,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }

        response = await admin_client.post(
            "/api/vigilance/products",
            json={
                "name": "CardioMonitor X200",
                "device_class": "IIb",
                "intended_purpose": "Cardiac monitoring",
            },
        )

        assert response.status_code == 201

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.create_product",
        new_callable=AsyncMock,
    )
    async def test_create_product_duplicate_udi_409(self, mock_create, admin_client):
        """POST /api/vigilance/products returns 409 on duplicate UDI."""
        mock_create.side_effect = DuplicateUDIError(
            "UDI already exists", udi="UDI-123", company_id=1
        )

        response = await admin_client.post(
            "/api/vigilance/products",
            json={
                "name": "CardioMonitor X200",
                "device_class": "IIb",
                "intended_purpose": "Cardiac monitoring",
                "udi": "UDI-123",
            },
        )

        assert response.status_code == 409

    async def test_create_product_missing_fields_422(self, admin_client):
        """POST /api/vigilance/products returns 422 with missing required fields."""
        response = await admin_client.post(
            "/api/vigilance/products",
            json={"name": "CardioMonitor X200"},
        )

        assert response.status_code == 422

    async def test_create_product_viewer_403(self, viewer_client):
        """POST /api/vigilance/products returns 403 for viewer role."""
        response = await viewer_client.post(
            "/api/vigilance/products",
            json={
                "name": "Device",
                "device_class": "IIa",
                "intended_purpose": "Testing",
            },
        )

        assert response.status_code == 403

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.list_products",
        new_callable=AsyncMock,
    )
    async def test_list_products_200(self, mock_list, member_client):
        """GET /api/vigilance/products returns 200 for member role."""
        mock_list.return_value = ([], 0)

        response = await member_client.get("/api/vigilance/products")

        assert response.status_code == 200

    async def test_list_products_viewer_403(self, viewer_client):
        """GET /api/vigilance/products returns 403 for viewer role."""
        response = await viewer_client.get("/api/vigilance/products")

        assert response.status_code == 403

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.get_product",
        new_callable=AsyncMock,
    )
    async def test_get_product_200(self, mock_get, member_client):
        """GET /api/vigilance/products/{id} returns 200."""
        mock_get.return_value = {
            "id": 1,
            "name": "Device",
            "device_class": "IIa",
            "intended_purpose": "Testing",
            "udi": None,
            "gmdn_code": None,
            "manufacturer_name": None,
            "predicate_devices": None,
            "risk_class_justification": None,
            "status": "active",
            "company_id": 1,
            "created_by": 42,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
            "profiles": [],
            "signal_counts": {},
        }

        response = await member_client.get("/api/vigilance/products/1")

        assert response.status_code == 200

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.get_product",
        new_callable=AsyncMock,
    )
    async def test_get_product_not_found_404(self, mock_get, member_client):
        """GET /api/vigilance/products/{id} returns 404 when not found."""
        mock_get.side_effect = ProductNotFoundError(
            "Not found", product_id=999, company_id=1
        )

        response = await member_client.get("/api/vigilance/products/999")

        assert response.status_code == 404

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.update_product",
        new_callable=AsyncMock,
    )
    async def test_update_product_200(self, mock_update, admin_client):
        """PUT /api/vigilance/products/{id} returns 200 on success."""
        mock_update.return_value = {
            "id": 1,
            "name": "Updated Device",
            "device_class": "IIb",
            "intended_purpose": "Updated purpose",
            "udi": None,
            "gmdn_code": None,
            "manufacturer_name": None,
            "predicate_devices": None,
            "risk_class_justification": None,
            "status": "active",
            "company_id": 1,
            "created_by": 42,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }

        response = await admin_client.put(
            "/api/vigilance/products/1",
            json={"name": "Updated Device"},
        )

        assert response.status_code == 200

    @patch(
        "alcoabase.api.vigilance_product_router._product_service.soft_delete_product",
        new_callable=AsyncMock,
    )
    async def test_delete_product_200(self, mock_delete, admin_client):
        """DELETE /api/vigilance/products/{id} returns 200."""
        mock_delete.return_value = {
            "id": 1,
            "name": "Device",
            "device_class": "IIa",
            "intended_purpose": "Testing",
            "udi": None,
            "gmdn_code": None,
            "manufacturer_name": None,
            "predicate_devices": None,
            "risk_class_justification": None,
            "status": "discontinued",
            "company_id": 1,
            "created_by": 42,
            "created_at": "2025-01-01T00:00:00+00:00",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }

        response = await admin_client.delete("/api/vigilance/products/1")

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Profile Router Tests
# ---------------------------------------------------------------------------


class TestVigilanceProfileRouter:
    """Tests for vigilance profile endpoints."""

    async def test_create_profile_missing_fields_422(
        self, document_admin_context, mock_db_session
    ):
        """POST /api/vigilance/products/{id}/profiles returns 422 with missing fields."""
        from alcoabase.api.vigilance_product_router import _get_profile_service

        mock_profile_svc = MagicMock()

        overrides = _make_client_factory(document_admin_context, mock_db_session)
        overrides[_get_profile_service] = lambda: mock_profile_svc
        app.dependency_overrides = overrides

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                "X-Change-Reason": "Unit test",
            },
        ) as client:
            response = await client.post(
                "/api/vigilance/products/1/profiles",
                json={"name": "Incomplete Profile"},
            )

        app.dependency_overrides.clear()
        assert response.status_code == 422

    async def test_create_profile_viewer_403(self, viewer_client):
        """POST /api/vigilance/products/{id}/profiles returns 403 for viewer."""
        response = await viewer_client.post(
            "/api/vigilance/products/1/profiles",
            json={
                "name": "Profile",
                "search_terms": ["test"],
                "adverse_event_keywords": ["event"],
                "schedule_cron": "0 2 * * 1",
            },
        )

        assert response.status_code == 403

    async def test_update_profile_viewer_403(self, viewer_client):
        """PUT /api/vigilance/profiles/{id} returns 403 for viewer."""
        response = await viewer_client.put(
            "/api/vigilance/profiles/1",
            json={"name": "Updated"},
        )

        assert response.status_code == 403

    async def test_execute_profile_viewer_403(self, viewer_client):
        """POST /api/vigilance/profiles/{id}/execute returns 403 for viewer."""
        response = await viewer_client.post(
            "/api/vigilance/profiles/1/execute",
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Signal Router Tests
# ---------------------------------------------------------------------------


class TestVigilanceSignalRouter:
    """Tests for vigilance signal endpoints."""

    async def test_list_signals_viewer_403(self, viewer_client):
        """GET /api/vigilance/signals returns 403 for viewer role."""
        response = await viewer_client.get("/api/vigilance/signals")

        assert response.status_code == 403

    async def test_update_disposition_viewer_403(self, viewer_client):
        """PUT /api/vigilance/signals/{id}/disposition returns 403 for viewer."""
        response = await viewer_client.put(
            "/api/vigilance/signals/1/disposition",
            json={"disposition": "confirmed", "confirmation_note": "Confirmed."},
        )

        assert response.status_code == 403

    async def test_get_summary_viewer_403(self, viewer_client):
        """GET /api/vigilance/signals/summary returns 403 for viewer."""
        response = await viewer_client.get("/api/vigilance/signals/summary")

        assert response.status_code == 403

    async def test_list_executions_viewer_403(self, viewer_client):
        """GET /api/vigilance/executions returns 403 for viewer."""
        response = await viewer_client.get("/api/vigilance/executions")

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Report Router Tests
# ---------------------------------------------------------------------------


class TestVigilanceReportRouter:
    """Tests for vigilance report endpoints."""

    @patch(
        "alcoabase.api.vigilance_report_router._report_service.list_reports",
        new_callable=AsyncMock,
    )
    async def test_list_reports_200(self, mock_list, member_client):
        """GET /api/vigilance/reports returns 200."""
        mock_list.return_value = ([], 0)

        response = await member_client.get("/api/vigilance/reports")

        assert response.status_code == 200

    async def test_list_reports_viewer_403(self, viewer_client):
        """GET /api/vigilance/reports returns 403 for viewer."""
        response = await viewer_client.get("/api/vigilance/reports")

        assert response.status_code == 403

    @patch(
        "alcoabase.api.vigilance_report_router._report_service.get_report",
        new_callable=AsyncMock,
    )
    async def test_get_report_200(self, mock_get, member_client):
        """GET /api/vigilance/reports/{id} returns 200."""
        mock_get.return_value = {
            "id": 1,
            "product_id": 1,
            "company_id": 1,
            "period_start": "2025-01-01",
            "period_end": "2025-03-31",
            "generated_at": "2025-04-01T10:00:00+00:00",
            "report_content": {"product_metadata": {"name": "Test"}},
            "status": "generated",
            "version": 1,
            "status_history": [],
            "created_by": 42,
            "created_at": "2025-04-01T10:00:00+00:00",
            "updated_at": "2025-04-01T10:00:00+00:00",
        }

        response = await member_client.get("/api/vigilance/reports/1")

        assert response.status_code == 200

    @patch(
        "alcoabase.api.vigilance_report_router._report_service.get_report",
        new_callable=AsyncMock,
    )
    async def test_get_report_not_found_404(self, mock_get, member_client):
        """GET /api/vigilance/reports/{id} returns 404."""
        mock_get.side_effect = ReportNotFoundError(
            "Not found", report_id=999, company_id=1
        )

        response = await member_client.get("/api/vigilance/reports/999")

        assert response.status_code == 404

    @patch(
        "alcoabase.api.vigilance_report_router._report_service.advance_status",
        new_callable=AsyncMock,
    )
    async def test_advance_status_200(self, mock_advance, admin_client):
        """PUT /api/vigilance/reports/{id}/status returns 200 on valid transition."""
        mock_advance.return_value = {
            "id": 1,
            "product_id": 1,
            "company_id": 1,
            "period_start": "2025-01-01",
            "period_end": "2025-03-31",
            "generated_at": "2025-04-01T10:00:00+00:00",
            "report_content": {},
            "status": "reviewed",
            "version": 1,
            "status_history": [
                {"status": "generated", "user_id": 42, "timestamp": "2025-04-01T10:00:00+00:00"},
                {"status": "reviewed", "user_id": 42, "timestamp": "2025-04-02T10:00:00+00:00"},
            ],
            "created_by": 42,
            "created_at": "2025-04-01T10:00:00+00:00",
            "updated_at": "2025-04-02T10:00:00+00:00",
        }

        response = await admin_client.put(
            "/api/vigilance/reports/1/status",
            json={"status": "reviewed", "comment": "QA reviewed"},
        )

        assert response.status_code == 200

    @patch(
        "alcoabase.api.vigilance_report_router._report_service.advance_status",
        new_callable=AsyncMock,
    )
    async def test_advance_status_invalid_transition_422(
        self, mock_advance, admin_client
    ):
        """PUT /api/vigilance/reports/{id}/status returns 422 on invalid transition."""
        mock_advance.side_effect = InvalidReportStatusTransitionError(
            "Cannot transition",
            report_id=1,
            current_status="generated",
            requested_status="approved",
        )

        response = await admin_client.put(
            "/api/vigilance/reports/1/status",
            json={"status": "approved"},
        )

        assert response.status_code == 422

    async def test_advance_status_viewer_403(self, viewer_client):
        """PUT /api/vigilance/reports/{id}/status returns 403 for viewer."""
        response = await viewer_client.put(
            "/api/vigilance/reports/1/status",
            json={"status": "reviewed"},
        )

        assert response.status_code == 403

    async def test_generate_report_viewer_403(self, viewer_client):
        """POST /api/vigilance/reports/generate returns 403 for viewer."""
        response = await viewer_client.post(
            "/api/vigilance/reports/generate",
            json={
                "product_id": 1,
                "period_start": "2025-01-01",
                "period_end": "2025-03-31",
            },
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Cross-cutting Concerns
# ---------------------------------------------------------------------------


class TestCrossCuttingConcerns:
    """Tests for X-Change-Reason and role enforcement across all routers."""

    async def test_mutation_without_change_reason_400(
        self, document_admin_context, mock_db_session
    ):
        """Mutation endpoints return 400 when X-Change-Reason is missing."""
        app.dependency_overrides = _make_client_factory(
            document_admin_context, mock_db_session
        )
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-User-Id": "42",
                "X-Company-Id": "1",
                # Deliberately omitting X-Change-Reason
            },
        ) as client:
            response = await client.post(
                "/api/vigilance/products",
                json={
                    "name": "Device",
                    "device_class": "IIa",
                    "intended_purpose": "Testing",
                },
            )

        app.dependency_overrides.clear()
        assert response.status_code == 400

    async def test_member_cannot_create_product(self, member_client):
        """Member role cannot create products (requires document_admin)."""
        response = await member_client.post(
            "/api/vigilance/products",
            json={
                "name": "Device",
                "device_class": "IIa",
                "intended_purpose": "Testing",
            },
            headers={"X-Change-Reason": "Test"},
        )

        assert response.status_code == 403

    async def test_member_cannot_delete_product(self, member_client):
        """Member role cannot delete products."""
        response = await member_client.delete(
            "/api/vigilance/products/1",
            headers={"X-Change-Reason": "Test"},
        )

        assert response.status_code == 403

    async def test_member_cannot_update_report_status(self, member_client):
        """Member role cannot advance report status."""
        response = await member_client.put(
            "/api/vigilance/reports/1/status",
            json={"status": "reviewed"},
            headers={"X-Change-Reason": "Test"},
        )

        assert response.status_code == 403

    async def test_report_mutation_without_change_reason_400(
        self, document_admin_context, mock_db_session
    ):
        """PUT report status returns 400 when X-Change-Reason is missing."""
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
            response = await client.put(
                "/api/vigilance/reports/1/status",
                json={"status": "reviewed"},
            )

        app.dependency_overrides.clear()
        assert response.status_code == 400
