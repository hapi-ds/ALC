"""Unit tests for audit trail API router.

Tests all endpoints: list, detail, export, immutability enforcement,
cross-company queries, and access logging.

Requirements: 1.1–1.7, 2.1–2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3,
             6.1–6.5, 7.1–7.10, 8.1–8.4, 9.1–9.4, 11.1–11.2
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from alcoabase.api.audit_trail import (
    _get_audit_access_logger,
    _get_audit_pdf_exporter,
    _get_audit_trail_service,
    router as audit_trail_router,
)
from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.audit_trail import (
    AuditEvent,
    AuditEventDetail,
    AuditTrailPage,
    ExportStatusResponse,
    FieldChange,
)
from alcoabase.services.audit_access_logger import AuditAccessLogger
from alcoabase.services.audit_pdf_exporter import AuditPDFExporter
from alcoabase.services.audit_trail_service import AuditTrailService
from alcoabase.services.rbac import AccessDenied, AccessGranted


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

ACCESS_GRANTED = AccessGranted(
    user_id=42, resource="audit_logs", action="read"
)

ACCESS_DENIED = AccessDenied(
    user_id=42,
    resource="audit_logs",
    action="read",
    reason="Missing permission: read on audit_logs",
)


def _make_event(
    transaction_id: int = 100,
    record_type: str = "documents",
    record_id: int = 1,
    operation_type: str = "UPDATE",
) -> AuditEvent:
    """Create a sample AuditEvent for testing."""
    return AuditEvent(
        transaction_id=transaction_id,
        timestamp=NOW,
        user_id=42,
        user_display_name="Test User",
        record_type=record_type,
        record_id=record_id,
        operation_type=operation_type,
        change_reason="Test change",
        changed_fields=["title", "status"],
        total_changed_fields=2,
        company_id=1,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create a mock AuditTrailService."""
    svc = AsyncMock(spec=AuditTrailService)
    svc.list_events = AsyncMock(
        return_value=AuditTrailPage(
            events=[_make_event()],
            next_cursor=None,
            total_count=1,
            warnings=None,
        )
    )
    svc.get_event_detail = AsyncMock(
        return_value=AuditEventDetail(
            transaction_id=100,
            timestamp=NOW,
            user_id=42,
            user_display_name="Test User",
            record_type="documents",
            record_id=1,
            operation_type="UPDATE",
            change_reason="Updated title",
            field_changes=[
                FieldChange(
                    field_name="title",
                    old_value="Old Title",
                    new_value="New Title",
                )
            ],
            company_id=1,
        )
    )
    svc.get_total_count = AsyncMock(return_value=5)
    return svc


@pytest.fixture
def mock_access_logger() -> AsyncMock:
    """Create a mock AuditAccessLogger."""
    logger = AsyncMock(spec=AuditAccessLogger)
    logger.log_access = AsyncMock()
    return logger


@pytest.fixture
def mock_exporter() -> AsyncMock:
    """Create a mock AuditPDFExporter."""
    exporter = AsyncMock(spec=AuditPDFExporter)
    exporter.export_sync = AsyncMock(
        return_value=b"%PDF-1.4 mock pdf content"
    )
    exporter.export_async = AsyncMock(return_value="job-uuid-1234")
    exporter.get_export_status = MagicMock(
        return_value=ExportStatusResponse(
            job_id="job-uuid-1234",
            status="completed",
            download_url="https://minio.local/exports/job-uuid-1234.pdf",
        )
    )
    return exporter


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def _build_app(
    mock_service: AsyncMock,
    mock_access_logger: AsyncMock,
    mock_exporter: AsyncMock,
    mock_session: AsyncMock,
) -> FastAPI:
    """Build a FastAPI app with the audit trail router and overridden deps."""
    app = FastAPI()
    api = APIRouter(prefix="/api")
    api.include_router(audit_trail_router)
    app.include_router(api)

    app.dependency_overrides[get_tenant_context] = lambda: TENANT_CTX
    app.dependency_overrides[get_db_session] = lambda: mock_session
    app.dependency_overrides[_get_audit_trail_service] = lambda: mock_service
    app.dependency_overrides[_get_audit_access_logger] = lambda: mock_access_logger
    app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

    return app


@pytest.fixture
def _patch_rbac_granted():
    """Patch RBACService to always grant access."""
    with patch("alcoabase.dependencies.rbac.RBACService") as MockRBAC:
        instance = AsyncMock()
        instance.check_permission = AsyncMock(return_value=ACCESS_GRANTED)
        MockRBAC.return_value = instance
        yield instance


@pytest.fixture
def _patch_rbac_denied():
    """Patch RBACService to always deny access."""
    with patch("alcoabase.dependencies.rbac.RBACService") as MockRBAC:
        instance = AsyncMock()
        instance.check_permission = AsyncMock(return_value=ACCESS_DENIED)
        MockRBAC.return_value = instance
        yield instance


@pytest.fixture
def client(
    mock_service: AsyncMock,
    mock_access_logger: AsyncMock,
    mock_exporter: AsyncMock,
    mock_session: AsyncMock,
    _patch_rbac_granted,
) -> TestClient:
    """Create a TestClient with all deps overridden (authorized)."""
    app = _build_app(
        mock_service, mock_access_logger, mock_exporter, mock_session
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def unauthorized_client(
    mock_service: AsyncMock,
    mock_access_logger: AsyncMock,
    mock_exporter: AsyncMock,
    mock_session: AsyncMock,
    _patch_rbac_denied,
) -> TestClient:
    """Create a TestClient that simulates unauthorized access (403)."""
    app = _build_app(
        mock_service, mock_access_logger, mock_exporter, mock_session
    )
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Tests: GET /api/audit-trail (list events)
# ---------------------------------------------------------------------------


class TestListAuditEvents:
    """Tests for GET /api/audit-trail endpoint."""

    def test_returns_paginated_events_with_correct_structure(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / returns paginated events with correct response structure."""
        response = client.get(
            "/api/audit-trail",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "events" in body
        assert "next_cursor" in body
        assert "total_count" in body
        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["transaction_id"] == 100
        assert event["record_type"] == "documents"
        assert event["operation_type"] == "UPDATE"
        assert event["user_display_name"] == "Test User"

    def test_filter_by_user_id(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / with user_id filter passes it to the service."""
        response = client.get(
            "/api/audit-trail?user_id=5",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["filters"].user_id == 5

    def test_filter_by_date_range(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / with date_start and date_end passes them to the service."""
        response = client.get(
            "/api/audit-trail"
            "?date_start=2025-01-01T00:00:00Z"
            "&date_end=2025-06-30T23:59:59Z",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["filters"].date_start is not None
        assert call_kwargs["filters"].date_end is not None

    def test_filter_by_record_type(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / with record_type filter passes it to the service."""
        response = client.get(
            "/api/audit-trail?record_type=documents",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["filters"].record_type == "documents"

    def test_filter_by_operation_type(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / with operation_type filter passes it to the service."""
        response = client.get(
            "/api/audit-trail?operation_type=INSERT",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["filters"].operation_type == "INSERT"

    def test_search_query(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / with search query passes it to the service."""
        response = client.get(
            "/api/audit-trail?search=updated+title",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["search_query"] == "updated title"

    def test_cursor_pagination(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """GET / with cursor passes it to the service for pagination."""
        response = client.get(
            "/api/audit-trail?cursor=abc123&page_size=25",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["cursor"] == "abc123"
        assert call_kwargs["page_size"] == 25

    def test_missing_company_id_returns_400(
        self, client: TestClient
    ) -> None:
        """GET / without X-Company-Id header returns 400."""
        response = client.get("/api/audit-trail")
        assert response.status_code == 400
        assert "X-Company-Id" in response.json()["detail"]

    def test_unauthorized_role_returns_403(
        self, unauthorized_client: TestClient
    ) -> None:
        """GET / with unauthorized role returns 403."""
        response = unauthorized_client.get(
            "/api/audit-trail",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /api/audit-trail/{record_type}/{record_id}/{transaction_id}
# ---------------------------------------------------------------------------


class TestGetAuditEventDetail:
    """Tests for event detail endpoint."""

    def test_returns_event_detail(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """Returns full event detail with field changes."""
        response = client.get(
            "/api/audit-trail/documents/1/100",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["transaction_id"] == 100
        assert body["record_type"] == "documents"
        assert body["operation_type"] == "UPDATE"
        assert len(body["field_changes"]) == 1
        assert body["field_changes"][0]["field_name"] == "title"
        assert body["field_changes"][0]["old_value"] == "Old Title"
        assert body["field_changes"][0]["new_value"] == "New Title"

    def test_returns_404_for_nonexistent_event(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """Returns 404 when event is not found."""
        mock_service.get_event_detail.return_value = None
        response = client.get(
            "/api/audit-trail/documents/999/999",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tests: POST /api/audit-trail/export
# ---------------------------------------------------------------------------


class TestExportEndpoint:
    """Tests for POST /api/audit-trail/export."""

    def test_zero_events_returns_400(
        self, client: TestClient, mock_service: AsyncMock
    ) -> None:
        """POST /export with zero matching events returns 400."""
        mock_service.get_total_count.return_value = 0
        response = client.post(
            "/api/audit-trail/export",
            json={"filters": None, "search_query": None},
            headers={
                "X-Company-Id": "1",
                "X-Change-Reason": "Export audit trail",
            },
        )
        assert response.status_code == 400
        assert "No events match" in response.json()["detail"]

    def test_sync_export_returns_pdf(
        self, client: TestClient, mock_service: AsyncMock,
        mock_exporter: AsyncMock,
    ) -> None:
        """POST /export with ≤10,000 events returns PDF synchronously."""
        mock_service.get_total_count.return_value = 500
        response = client.post(
            "/api/audit-trail/export",
            json={"filters": None, "search_query": None},
            headers={
                "X-Company-Id": "1",
                "X-Change-Reason": "Export audit trail",
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert b"%PDF" in response.content
        mock_exporter.export_sync.assert_called_once()

    def test_async_export_returns_job_id(
        self, client: TestClient, mock_service: AsyncMock,
        mock_exporter: AsyncMock,
    ) -> None:
        """POST /export with >10,000 events returns job_id (async)."""
        mock_service.get_total_count.return_value = 15_000
        response = client.post(
            "/api/audit-trail/export",
            json={"filters": None, "search_query": None},
            headers={
                "X-Company-Id": "1",
                "X-Change-Reason": "Export audit trail",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "job-uuid-1234"
        assert body["status"] == "pending"
        mock_exporter.export_async.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: GET /api/audit-trail/export/{job_id}
# ---------------------------------------------------------------------------


class TestExportStatus:
    """Tests for GET /api/audit-trail/export/{job_id}."""

    def test_returns_export_status(
        self, client: TestClient, mock_exporter: AsyncMock
    ) -> None:
        """GET /export/{job_id} returns status response."""
        response = client.get(
            "/api/audit-trail/export/job-uuid-1234",
            headers={"X-Company-Id": "1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == "job-uuid-1234"
        assert body["status"] == "completed"
        assert body["download_url"] is not None


# ---------------------------------------------------------------------------
# Tests: Immutability enforcement (PUT, PATCH, DELETE)
# ---------------------------------------------------------------------------

IMMUTABILITY_MESSAGE = (
    "Audit records are immutable per ALCOA+ and CFR 21 Part 11"
)


class TestImmutabilityEnforcement:
    """Tests for PUT, PATCH, DELETE blocking on audit trail endpoints."""

    def test_put_returns_403(self, client: TestClient) -> None:
        """PUT /api/audit-trail returns 403 with immutability message."""
        response = client.put("/api/audit-trail/")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_patch_returns_403(self, client: TestClient) -> None:
        """PATCH /api/audit-trail returns 403 with immutability message."""
        response = client.patch("/api/audit-trail/")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE

    def test_delete_returns_403(self, client: TestClient) -> None:
        """DELETE /api/audit-trail returns 403 with immutability message."""
        response = client.delete("/api/audit-trail/")
        assert response.status_code == 403
        assert response.json()["detail"] == IMMUTABILITY_MESSAGE


# ---------------------------------------------------------------------------
# Tests: Cross-company queries
# ---------------------------------------------------------------------------


class TestCrossCompanyQueries:
    """Tests for cross_company query parameter."""

    def test_cross_company_with_system_admin_succeeds(
        self, mock_service: AsyncMock, mock_access_logger: AsyncMock,
        mock_exporter: AsyncMock, mock_session: AsyncMock,
        _patch_rbac_granted,
    ) -> None:
        """cross_company=True with system_admin role succeeds."""
        app = _build_app(
            mock_service, mock_access_logger, mock_exporter, mock_session
        )

        mock_role = MagicMock()
        mock_role.name = "system_admin"

        with patch(
            "alcoabase.api.audit_trail._rbac_service"
        ) as mock_rbac:
            mock_rbac.get_role_for_user = AsyncMock(
                return_value=mock_role
            )
            test_client = TestClient(app, raise_server_exceptions=False)
            response = test_client.get(
                "/api/audit-trail?cross_company=true",
                headers={"X-Company-Id": "1"},
            )

        assert response.status_code == 200
        call_kwargs = mock_service.list_events.call_args.kwargs
        assert call_kwargs["cross_company"] is True

    def test_cross_company_with_non_system_admin_returns_403(
        self, mock_service: AsyncMock, mock_access_logger: AsyncMock,
        mock_exporter: AsyncMock, mock_session: AsyncMock,
        _patch_rbac_granted,
    ) -> None:
        """cross_company=True with non-system_admin returns 403."""
        app = _build_app(
            mock_service, mock_access_logger, mock_exporter, mock_session
        )

        mock_role = MagicMock()
        mock_role.name = "member"

        with patch(
            "alcoabase.api.audit_trail._rbac_service"
        ) as mock_rbac:
            mock_rbac.get_role_for_user = AsyncMock(
                return_value=mock_role
            )
            test_client = TestClient(app, raise_server_exceptions=False)
            response = test_client.get(
                "/api/audit-trail?cross_company=true",
                headers={"X-Company-Id": "1"},
            )

        assert response.status_code == 403
        assert "system_admin" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: Access logging
# ---------------------------------------------------------------------------


class TestAccessLogging:
    """Tests for audit access logging on each request."""

    def test_access_logging_on_list_request(
        self, client: TestClient, mock_access_logger: AsyncMock
    ) -> None:
        """Access logging occurs on each list request."""
        client.get(
            "/api/audit-trail",
            headers={"X-Company-Id": "1"},
        )
        mock_access_logger.log_access.assert_called_once()
        call_kwargs = mock_access_logger.log_access.call_args.kwargs
        assert call_kwargs["user_id"] == 42
        assert call_kwargs["company_id"] == 1
        assert call_kwargs["action"] == "view"
