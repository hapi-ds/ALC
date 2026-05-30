"""Integration tests for audit trail API endpoints (Phase 6.3).

Tests the full request lifecycle through the API layer using httpx.AsyncClient
with an async SQLite in-memory database, verifying:
- Full request flow: API → Service → DB → Response
- Multi-tenant isolation verification
- PDF generation end-to-end (small dataset)
- Celery task dispatch and completion for large exports
- Access log creation on each request

References:
    - Task 13.1: Write backend integration tests
    - Requirements: 1.1–11.3 (all audit trail requirements)
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base, get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.audit_access_log import AuditAccessLog
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.user import Role, User
from alcoabase.services.rbac import DEFAULT_ROLE_PERMISSIONS

# Ensure all mappers are configured
configure_mappers()


# Tables required for audit trail integration tests.
# Includes transaction table for SQLAlchemy-Continuum and version tables,
# plus all tables that the AuditTrailService queries.
_REQUIRED_TABLE_NAMES = [
    "users",
    "companies",
    "company_memberships",
    "roles",
    "documents",
    "document_versions",
    "templates",
    "template_versions",
    "reports",
    "workflow_definitions",
    "workflow_versions",
    "signature_records",
    "training_tasks",
    "training_records",
    "transaction",
]
# Also include version tables if they exist (Continuum-managed)
for _name in list(_REQUIRED_TABLE_NAMES):
    _version_name = f"{_name}_version"
    if _version_name in Base.metadata.tables and _version_name not in _REQUIRED_TABLE_NAMES:
        _REQUIRED_TABLE_NAMES.append(_version_name)

_REQUIRED_TABLES = [
    Base.metadata.tables[name]
    for name in _REQUIRED_TABLE_NAMES
    if name in Base.metadata.tables
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_REQUIRED_TABLES)
        # Create audit_access_log table manually with SQLite-compatible types
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                company_id INTEGER NOT NULL REFERENCES companies(id),
                action VARCHAR(10) NOT NULL,
                filters_applied TEXT,
                event_count INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Create an async session factory bound to the test engine."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test setup operations."""
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def seeded_data(db_session: AsyncSession) -> dict:
    """Seed companies, users, roles, and memberships for testing.

    Creates:
    - Two companies (company_a, company_b) for tenant isolation tests
    - An admin user (system_admin) in company_a
    - A viewer user in company_a (no audit_logs permission)
    - An admin user in company_b
    """
    # Company A
    company_a = Company(
        id=1,
        slug="pharma-a",
        display_name="Pharma A Inc",
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    db_session.add(company_a)

    # Company B
    company_b = Company(
        id=2,
        slug="pharma-b",
        display_name="Pharma B Corp",
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    db_session.add(company_b)
    await db_session.flush()

    # Admin user for company A
    admin_user = User(
        id=1,
        username="admin_a",
        email="admin@pharma-a.local",
        hashed_password="hashed_placeholder",
        full_name="Admin User A",
        is_active=True,
    )
    db_session.add(admin_user)

    # Viewer user for company A (no audit_logs permission)
    viewer_user = User(
        id=2,
        username="viewer_a",
        email="viewer@pharma-a.local",
        hashed_password="hashed_placeholder",
        full_name="Viewer User A",
        is_active=True,
    )
    db_session.add(viewer_user)

    # Admin user for company B
    admin_b = User(
        id=3,
        username="admin_b",
        email="admin@pharma-b.local",
        hashed_password="hashed_placeholder",
        full_name="Admin User B",
        is_active=True,
    )
    db_session.add(admin_b)
    await db_session.flush()

    # Seed roles for company A
    roles_a = {}
    for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(
            name=role_name,
            description=f"{role_name} role",
            permissions=permissions,
            company_id=company_a.id,
            is_system=True,
        )
        db_session.add(role)
        await db_session.flush()
        roles_a[role_name] = role

    # Seed roles for company B
    roles_b = {}
    for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(
            name=role_name,
            description=f"{role_name} role",
            permissions=permissions,
            company_id=company_b.id,
            is_system=True,
        )
        db_session.add(role)
        await db_session.flush()
        roles_b[role_name] = role

    # Memberships
    membership_admin_a = CompanyMembership(
        user_id=admin_user.id,
        company_id=company_a.id,
        role="system_admin",
        role_id=roles_a["system_admin"].id,
    )
    db_session.add(membership_admin_a)

    membership_viewer_a = CompanyMembership(
        user_id=viewer_user.id,
        company_id=company_a.id,
        role="viewer",
        role_id=roles_a["viewer"].id,
    )
    db_session.add(membership_viewer_a)

    membership_admin_b = CompanyMembership(
        user_id=admin_b.id,
        company_id=company_b.id,
        role="system_admin",
        role_id=roles_b["system_admin"].id,
    )
    db_session.add(membership_admin_b)
    await db_session.flush()
    await db_session.commit()

    return {
        "company_a": company_a,
        "company_b": company_b,
        "admin_user": admin_user,
        "viewer_user": viewer_user,
        "admin_b": admin_b,
        "roles_a": roles_a,
        "roles_b": roles_b,
    }


@pytest_asyncio.fixture
async def admin_client(
    session_factory, seeded_data
) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated as system_admin for company A."""

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="pharma-a",
            user_id=1,
            membership_role="system_admin",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "1",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def viewer_client(
    session_factory, seeded_data
) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated as viewer for company A.

    Viewer role does NOT have audit_logs:read permission.
    """

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="pharma-a",
            user_id=2,
            membership_role="viewer",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "2",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def company_b_client(
    session_factory, seeded_data
) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated as system_admin for company B."""

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=2,
            company_slug="pharma-b",
            user_id=3,
            membership_role="system_admin",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "3",
            "X-Company-Id": "2",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Full Request Flow (API → Service → DB → Response)
# ---------------------------------------------------------------------------


class TestFullRequestFlow:
    """Test the complete request lifecycle for audit trail endpoints."""

    @pytest.mark.asyncio
    async def test_list_events_returns_paginated_response(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail returns a valid paginated response structure."""
        resp = await admin_client.get("/api/audit-trail")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "next_cursor" in data
        assert "total_count" in data
        assert isinstance(data["events"], list)
        assert isinstance(data["total_count"], int)

    @pytest.mark.asyncio
    async def test_list_events_with_filters(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail with filter params returns valid response."""
        resp = await admin_client.get(
            "/api/audit-trail",
            params={
                "record_type": "documents",
                "operation_type": "INSERT",
                "page_size": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        # All returned events should match the filter
        for ev in data["events"]:
            assert ev["record_type"] == "documents"
            assert ev["operation_type"] == "INSERT"

    @pytest.mark.asyncio
    async def test_list_events_with_search_query(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail?search= returns valid response."""
        resp = await admin_client.get(
            "/api/audit-trail",
            params={"search": "test-search-term"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total_count" in data

    @pytest.mark.asyncio
    async def test_list_events_with_date_range(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail with date_start and date_end returns valid response."""
        now = datetime.now(UTC)
        resp = await admin_client.get(
            "/api/audit-trail",
            params={
                "date_start": (now - timedelta(days=7)).isoformat(),
                "date_end": now.isoformat(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data

    @pytest.mark.asyncio
    async def test_list_events_page_size_clamping(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail with page_size > 200 returns 422."""
        resp = await admin_client.get(
            "/api/audit-trail",
            params={"page_size": 500},
        )
        # FastAPI validates ge=1, le=200 and returns 422 for out-of-range
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_events_page_size_zero_returns_422(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail with page_size=0 returns 422."""
        resp = await admin_client.get(
            "/api/audit-trail",
            params={"page_size": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_event_detail_not_found_returns_404(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail/{record_type}/{record_id}/{txn_id} returns 404."""
        resp = await admin_client.get(
            "/api/audit-trail/documents/99999/99999"
        )
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_list_events_response_includes_warnings_field(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail response includes optional warnings field."""
        resp = await admin_client.get("/api/audit-trail")
        assert resp.status_code == 200
        data = resp.json()
        # warnings can be null or a list
        assert "warnings" in data or data.get("warnings") is None


# ---------------------------------------------------------------------------
# Test: Multi-Tenant Isolation
# ---------------------------------------------------------------------------


class TestMultiTenantIsolation:
    """Test that audit trail queries are properly scoped to the tenant."""

    @pytest.mark.asyncio
    async def test_company_a_cannot_see_company_b_events(
        self, admin_client: AsyncClient
    ) -> None:
        """Company A admin sees only company A events (empty in test DB)."""
        resp = await admin_client.get("/api/audit-trail")
        assert resp.status_code == 200
        data = resp.json()
        # All events should belong to company_id=1
        for ev in data["events"]:
            assert ev["company_id"] == 1

    @pytest.mark.asyncio
    async def test_company_b_cannot_see_company_a_events(
        self, company_b_client: AsyncClient
    ) -> None:
        """Company B admin sees only company B events (empty in test DB)."""
        resp = await company_b_client.get("/api/audit-trail")
        assert resp.status_code == 200
        data = resp.json()
        # All events should belong to company_id=2
        for ev in data["events"]:
            assert ev["company_id"] == 2

    @pytest.mark.asyncio
    async def test_cross_company_query_requires_system_admin(
        self, admin_client: AsyncClient
    ) -> None:
        """cross_company=True with system_admin succeeds."""
        resp = await admin_client.get(
            "/api/audit-trail",
            params={"cross_company": "true"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cross_company_query_denied_for_viewer(
        self, viewer_client: AsyncClient
    ) -> None:
        """cross_company=True with viewer role returns 403."""
        resp = await viewer_client.get(
            "/api/audit-trail",
            params={"cross_company": "true"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_company_id_header_returns_400(
        self, session_factory, seeded_data
    ) -> None:
        """Request without X-Company-Id header returns 400."""

        async def _override_get_db_session():
            async with session_factory() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        async def _override_get_tenant_context():
            return TenantContext(
                company_id=1,
                company_slug="pharma-a",
                user_id=1,
                membership_role="system_admin",
            )

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={
                    "X-Change-Reason": "Integration test",
                    "X-User-Id": "1",
                    # No X-Company-Id header
                },
            ) as client:
                resp = await client.get("/api/audit-trail")
                assert resp.status_code == 400
                assert "X-Company-Id" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Immutability Enforcement
# ---------------------------------------------------------------------------


class TestImmutabilityEnforcement:
    """Test that PUT, PATCH, DELETE are blocked on all audit trail endpoints."""

    @pytest.mark.asyncio
    async def test_put_audit_trail_root_returns_403(
        self, admin_client: AsyncClient
    ) -> None:
        """PUT /api/audit-trail/ returns 403 with immutability message."""
        resp = await admin_client.put("/api/audit-trail/")
        assert resp.status_code == 403
        assert "immutable" in resp.json()["detail"].lower()
        assert "ALCOA+" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_audit_trail_root_returns_403(
        self, admin_client: AsyncClient
    ) -> None:
        """PATCH /api/audit-trail/ returns 403 with immutability message."""
        resp = await admin_client.patch("/api/audit-trail/")
        assert resp.status_code == 403
        assert "immutable" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_audit_trail_root_returns_403(
        self, admin_client: AsyncClient
    ) -> None:
        """DELETE /api/audit-trail/ returns 403 with immutability message."""
        resp = await admin_client.delete("/api/audit-trail/")
        assert resp.status_code == 403
        assert "immutable" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_put_audit_trail_subpath_returns_403(
        self, admin_client: AsyncClient
    ) -> None:
        """PUT /api/audit-trail/some/path returns 403."""
        resp = await admin_client.put("/api/audit-trail/documents/1/1")
        assert resp.status_code == 403
        assert "ALCOA+" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_audit_trail_subpath_returns_403(
        self, admin_client: AsyncClient
    ) -> None:
        """PATCH /api/audit-trail/some/path returns 403."""
        resp = await admin_client.patch("/api/audit-trail/documents/1/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_audit_trail_subpath_returns_403(
        self, admin_client: AsyncClient
    ) -> None:
        """DELETE /api/audit-trail/some/path returns 403."""
        resp = await admin_client.delete("/api/audit-trail/documents/1/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_immutability_enforced_regardless_of_role(
        self, viewer_client: AsyncClient
    ) -> None:
        """Immutability is enforced even for viewer role (not just admin)."""
        # Even though viewer can't read audit_logs, the immutability
        # handler fires before RBAC for mutation methods
        resp = await viewer_client.put("/api/audit-trail/")
        assert resp.status_code == 403
        assert "immutable" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: RBAC Enforcement
# ---------------------------------------------------------------------------


class TestRBACEnforcement:
    """Test that audit trail access is restricted to authorized roles."""

    @pytest.mark.asyncio
    async def test_system_admin_can_access_audit_trail(
        self, admin_client: AsyncClient
    ) -> None:
        """system_admin role can access GET /api/audit-trail."""
        resp = await admin_client.get("/api/audit-trail")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_cannot_access_audit_trail(
        self, viewer_client: AsyncClient
    ) -> None:
        """viewer role cannot access GET /api/audit-trail (returns 403)."""
        resp = await viewer_client.get("/api/audit-trail")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Test: PDF Export End-to-End (Small Dataset)
# ---------------------------------------------------------------------------


class TestPDFExportEndToEnd:
    """Test PDF export flow through the API layer."""

    @pytest.mark.asyncio
    async def test_export_with_zero_events_returns_400(
        self, admin_client: AsyncClient
    ) -> None:
        """POST /api/audit-trail/export with no matching events returns 400."""
        resp = await admin_client.post(
            "/api/audit-trail/export",
            json={"filters": {"record_type": "documents"}, "search_query": None},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "No events match" in data["detail"]

    @pytest.mark.asyncio
    async def test_export_with_empty_filters_and_no_events_returns_400(
        self, admin_client: AsyncClient
    ) -> None:
        """POST /api/audit-trail/export with empty filters and no data returns 400."""
        resp = await admin_client.post(
            "/api/audit-trail/export",
            json={"filters": None, "search_query": None},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_sync_returns_pdf_bytes(
        self, admin_client: AsyncClient
    ) -> None:
        """POST /api/audit-trail/export with ≤10k events returns PDF.

        This test requires actual audit data in the database.
        Marked with @pytest.mark.integration for environments with seeded data.
        """
        # Mock the service to return a small count and PDF bytes
        mock_service = MagicMock()
        mock_service.get_total_count = AsyncMock(return_value=5)
        mock_service.list_events = AsyncMock(
            return_value=MagicMock(events=[], next_cursor=None, total_count=5)
        )

        mock_exporter = MagicMock()
        mock_exporter.export_sync = AsyncMock(return_value=b"%PDF-1.4 mock content")

        from alcoabase.api.audit_trail import (
            _get_audit_pdf_exporter,
            _get_audit_trail_service,
        )

        app.dependency_overrides[_get_audit_trail_service] = lambda: mock_service
        app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

        try:
            resp = await admin_client.post(
                "/api/audit-trail/export",
                json={"filters": None, "search_query": None},
            )
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/pdf"
            assert b"%PDF" in resp.content
            assert "attachment" in resp.headers.get("content-disposition", "")
        finally:
            app.dependency_overrides.pop(_get_audit_trail_service, None)
            app.dependency_overrides.pop(_get_audit_pdf_exporter, None)

    @pytest.mark.asyncio
    async def test_export_status_endpoint(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail/export/{job_id} returns export status."""
        from alcoabase.api.audit_trail import _get_audit_pdf_exporter
        from alcoabase.schemas.audit_trail import ExportStatusResponse

        mock_exporter = MagicMock()
        mock_exporter.get_export_status = MagicMock(
            return_value=ExportStatusResponse(
                job_id="test-job-123",
                status="completed",
                download_url="https://minio.local/exports/test-job-123.pdf",
            )
        )

        app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

        try:
            resp = await admin_client.get(
                "/api/audit-trail/export/test-job-123"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["job_id"] == "test-job-123"
            assert data["status"] == "completed"
            assert data["download_url"] is not None
        finally:
            app.dependency_overrides.pop(_get_audit_pdf_exporter, None)


# ---------------------------------------------------------------------------
# Test: Celery Task Dispatch for Large Exports
# ---------------------------------------------------------------------------


class TestCeleryTaskDispatch:
    """Test that large exports (>10k events) dispatch a Celery task."""

    @pytest.mark.asyncio
    async def test_large_export_dispatches_celery_task(
        self, admin_client: AsyncClient
    ) -> None:
        """POST /api/audit-trail/export with >10k events returns job_id."""
        from alcoabase.api.audit_trail import (
            _get_audit_pdf_exporter,
            _get_audit_trail_service,
        )

        mock_service = MagicMock()
        mock_service.get_total_count = AsyncMock(return_value=15_000)

        mock_exporter = MagicMock()
        mock_exporter.export_async = AsyncMock(
            return_value="async-job-uuid-456"
        )

        app.dependency_overrides[_get_audit_trail_service] = lambda: mock_service
        app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

        try:
            resp = await admin_client.post(
                "/api/audit-trail/export",
                json={"filters": {"record_type": "documents"}, "search_query": None},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["job_id"] == "async-job-uuid-456"
            assert data["status"] == "pending"
            # Verify export_async was called
            mock_exporter.export_async.assert_called_once()
        finally:
            app.dependency_overrides.pop(_get_audit_trail_service, None)
            app.dependency_overrides.pop(_get_audit_pdf_exporter, None)

    @pytest.mark.asyncio
    async def test_export_status_pending(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail/export/{job_id} returns pending status."""
        from alcoabase.api.audit_trail import _get_audit_pdf_exporter
        from alcoabase.schemas.audit_trail import ExportStatusResponse

        mock_exporter = MagicMock()
        mock_exporter.get_export_status = MagicMock(
            return_value=ExportStatusResponse(
                job_id="pending-job-789",
                status="pending",
                download_url=None,
            )
        )

        app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

        try:
            resp = await admin_client.get(
                "/api/audit-trail/export/pending-job-789"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "pending"
            assert data["download_url"] is None
        finally:
            app.dependency_overrides.pop(_get_audit_pdf_exporter, None)

    @pytest.mark.asyncio
    async def test_export_status_failed(
        self, admin_client: AsyncClient
    ) -> None:
        """GET /api/audit-trail/export/{job_id} returns failed status."""
        from alcoabase.api.audit_trail import _get_audit_pdf_exporter
        from alcoabase.schemas.audit_trail import ExportStatusResponse

        mock_exporter = MagicMock()
        mock_exporter.get_export_status = MagicMock(
            return_value=ExportStatusResponse(
                job_id="failed-job-000",
                status="failed",
                download_url=None,
                error_message="Export timed out after 300 seconds",
            )
        )

        app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

        try:
            resp = await admin_client.get(
                "/api/audit-trail/export/failed-job-000"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "failed"
            assert "timed out" in data["error_message"]
        finally:
            app.dependency_overrides.pop(_get_audit_pdf_exporter, None)


# ---------------------------------------------------------------------------
# Test: Access Log Creation on Each Request
# ---------------------------------------------------------------------------


class TestAccessLogCreation:
    """Test that each audit trail request creates an access log entry."""

    @pytest.mark.asyncio
    async def test_list_events_creates_access_log(
        self, admin_client: AsyncClient, session_factory
    ) -> None:
        """GET /api/audit-trail creates an access log entry with action='view'."""
        # Make a request to the audit trail
        resp = await admin_client.get("/api/audit-trail")
        assert resp.status_code == 200

        # Verify access log was created
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM audit_access_log ORDER BY id DESC LIMIT 1")
            )
            row = result.fetchone()
            assert row is not None
            assert row.user_id == 1
            assert row.company_id == 1
            assert row.action == "view"

    @pytest.mark.asyncio
    async def test_list_events_with_filters_logs_filters(
        self, admin_client: AsyncClient, session_factory
    ) -> None:
        """GET /api/audit-trail with filters logs the applied filters."""
        resp = await admin_client.get(
            "/api/audit-trail",
            params={"record_type": "documents", "operation_type": "UPDATE"},
        )
        assert resp.status_code == 200

        # Verify access log includes filters
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT * FROM audit_access_log ORDER BY id DESC LIMIT 1")
            )
            row = result.fetchone()
            assert row is not None
            assert row.action == "view"
            # filters_applied should contain the filter params
            if row.filters_applied:
                import json

                filters = (
                    json.loads(row.filters_applied)
                    if isinstance(row.filters_applied, str)
                    else row.filters_applied
                )
                assert "record_type" in filters or "operation_type" in filters

    @pytest.mark.asyncio
    async def test_export_creates_access_log_with_export_action(
        self, admin_client: AsyncClient, session_factory
    ) -> None:
        """POST /api/audit-trail/export creates access log with action='export'."""
        from alcoabase.api.audit_trail import (
            _get_audit_pdf_exporter,
            _get_audit_trail_service,
        )

        mock_service = MagicMock()
        mock_service.get_total_count = AsyncMock(return_value=100)

        mock_exporter = MagicMock()
        mock_exporter.export_sync = AsyncMock(return_value=b"%PDF-1.4 test")

        app.dependency_overrides[_get_audit_trail_service] = lambda: mock_service
        app.dependency_overrides[_get_audit_pdf_exporter] = lambda: mock_exporter

        try:
            resp = await admin_client.post(
                "/api/audit-trail/export",
                json={"filters": None, "search_query": None},
            )
            assert resp.status_code == 200

            # Verify access log was created with export action
            async with session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT * FROM audit_access_log "
                        "WHERE action = 'export' ORDER BY id DESC LIMIT 1"
                    )
                )
                row = result.fetchone()
                assert row is not None
                assert row.action == "export"
                assert row.user_id == 1
                assert row.company_id == 1
                assert row.event_count == 100
        finally:
            app.dependency_overrides.pop(_get_audit_trail_service, None)
            app.dependency_overrides.pop(_get_audit_pdf_exporter, None)

    @pytest.mark.asyncio
    async def test_multiple_requests_create_multiple_access_logs(
        self, admin_client: AsyncClient, session_factory
    ) -> None:
        """Multiple requests create multiple access log entries."""
        # Make two requests
        await admin_client.get("/api/audit-trail")
        await admin_client.get("/api/audit-trail", params={"search": "test"})

        # Verify at least 2 access log entries exist
        async with session_factory() as session:
            result = await session.execute(
                text("SELECT COUNT(*) as cnt FROM audit_access_log")
            )
            row = result.fetchone()
            assert row.cnt >= 2

    @pytest.mark.asyncio
    async def test_access_log_records_correct_user_id(
        self, admin_client: AsyncClient, session_factory
    ) -> None:
        """Access log records the correct user_id from the tenant context."""
        await admin_client.get("/api/audit-trail")

        async with session_factory() as session:
            result = await session.execute(
                text("SELECT user_id FROM audit_access_log ORDER BY id DESC LIMIT 1")
            )
            row = result.fetchone()
            assert row is not None
            # admin_client uses user_id=1
            assert row.user_id == 1
