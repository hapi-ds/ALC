"""Integration tests for system configuration API endpoints (Phase 6.2).

Tests the full system configuration API through the FastAPI layer using
httpx.AsyncClient with an async SQLite in-memory database.

Covers:
- All 23 system configuration endpoints
- RBAC permission enforcement (system_config:read, system_config:update)
- X-Change-Reason header enforcement on mutation endpoints
- Error responses (403, 404, 409, 422)
- Happy paths for GET and mutation endpoints

References:
    - Task 16.1: Write backend integration tests for system configuration API
    - Requirements: 1.1–15.5
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base, get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.system_config import (
    ResourceMetricPoint,
    SystemConfiguration,
)
from alcoabase.models.user import Role, User
from alcoabase.services.rbac import DEFAULT_ROLE_PERMISSIONS


# Render JSONB as JSON in SQLite (must be registered before configure_mappers)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


# Ensure all mappers (including Continuum version tables) are configured
configure_mappers()

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
        await conn.run_sync(Base.metadata.create_all)

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
    """Seed company, admin user, roles, and system config for testing."""
    # Create company
    company = Company(
        id=1,
        slug="test-pharma",
        display_name="Test Pharma Inc",
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    # Create admin user
    admin_user = User(
        id=1,
        username="admin_user",
        email="admin@example.com",
        hashed_password="hashed_placeholder",
        full_name="Admin User",
        is_active=True,
    )
    db_session.add(admin_user)
    await db_session.flush()

    # Seed default roles
    roles = {}
    for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
        role = Role(
            name=role_name,
            description=f"{role_name} role",
            permissions=permissions,
            company_id=company.id,
            is_system=True,
        )
        db_session.add(role)
        await db_session.flush()
        roles[role_name] = role

    # Create admin membership with system_admin role
    admin_membership = CompanyMembership(
        user_id=admin_user.id,
        company_id=company.id,
        role="system_admin",
        role_id=roles["system_admin"].id,
    )
    db_session.add(admin_membership)
    await db_session.flush()

    # Seed system configuration rows
    ai_config = SystemConfiguration(
        category="ai_hardware",
        config_values={
            "model_chat_name": "gemma-4-e4b-it",
            "model_chat_path": "/models/gemma-4-e4b-it",
            "model_chat_max_gpu_memory_gb": 24,
            "model_embedding_name": "bge-small",
            "model_embedding_path": "/models/bge-small",
            "model_embedding_dimension": 384,
            "model_ocr_name": "gemma-ocr",
            "model_ocr_path": "/models/gemma-ocr",
            "inference_mode": "mock",
            "gpu_device_id": 0,
            "vllm_chat_url": "http://localhost:8000",
            "vllm_embedding_url": "http://localhost:8001",
        },
        updated_by=admin_user.id,
    )
    db_session.add(ai_config)

    backup_schedule = SystemConfiguration(
        category="backup_schedule",
        config_values={"cron_expression": "0 2 * * *", "human_readable": "Daily at 02:00 UTC"},
        updated_by=admin_user.id,
    )
    db_session.add(backup_schedule)

    backup_retention = SystemConfiguration(
        category="backup_retention",
        config_values={"retention_days": 30},
        updated_by=admin_user.id,
    )
    db_session.add(backup_retention)

    health_config = SystemConfiguration(
        category="health_check",
        config_values={
            "polling_interval_seconds": 30,
            "degraded_threshold_seconds": 5,
            "unreachable_timeout_seconds": 10,
        },
        updated_by=admin_user.id,
    )
    db_session.add(health_config)
    await db_session.flush()
    await db_session.commit()

    return {
        "company": company,
        "admin_user": admin_user,
        "roles": roles,
        "admin_membership": admin_membership,
    }


@pytest_asyncio.fixture
async def client(session_factory, seeded_data) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated as system_admin."""

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
            company_slug="test-pharma",
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
    session_factory, seeded_data, db_session: AsyncSession
) -> AsyncGenerator[AsyncClient, None]:
    """Create a client authenticated as a viewer (no system_config permission)."""
    viewer = User(
        id=50,
        username="viewer_user",
        email="viewer@example.com",
        hashed_password="hashed_placeholder",
        full_name="Viewer User",
        is_active=True,
    )
    db_session.add(viewer)
    await db_session.flush()

    roles = seeded_data["roles"]
    membership = CompanyMembership(
        user_id=viewer.id,
        company_id=1,
        role="viewer",
        role_id=roles["viewer"].id,
    )
    db_session.add(membership)
    await db_session.flush()
    await db_session.commit()

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
            company_slug="test-pharma",
            user_id=50,
            membership_role="viewer",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "50",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: RBAC Permission Enforcement
# ---------------------------------------------------------------------------


class TestRBACEnforcement:
    """Test that system_config endpoints enforce RBAC permissions."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_read_ai_hardware(
        self, viewer_client: AsyncClient
    ) -> None:
        """GET /api/system-config/ai-hardware returns 403 for viewer role."""
        resp = await viewer_client.get("/api/system-config/ai-hardware")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_read_storage_usage(
        self, viewer_client: AsyncClient
    ) -> None:
        """GET /api/system-config/storage/usage returns 403 for viewer role."""
        resp = await viewer_client.get("/api/system-config/storage/usage")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_read_health_status(
        self, viewer_client: AsyncClient
    ) -> None:
        """GET /api/system-config/health/status returns 403 for viewer role."""
        resp = await viewer_client.get("/api/system-config/health/status")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_read_services(
        self, viewer_client: AsyncClient
    ) -> None:
        """GET /api/system-config/services returns 403 for viewer role."""
        resp = await viewer_client.get("/api/system-config/services")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_ai_hardware(
        self, viewer_client: AsyncClient
    ) -> None:
        """PUT /api/system-config/ai-hardware returns 403 for viewer role."""
        resp = await viewer_client.put(
            "/api/system-config/ai-hardware",
            json={"inference_mode": "cpu"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_trigger_backup(
        self, viewer_client: AsyncClient
    ) -> None:
        """POST /api/system-config/backups/trigger returns 403 for viewer role."""
        resp = await viewer_client.post("/api/system-config/backups/trigger")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_health_config(
        self, viewer_client: AsyncClient
    ) -> None:
        """PUT /api/system-config/health/config returns 403 for viewer role."""
        resp = await viewer_client.put(
            "/api/system-config/health/config",
            json={
                "polling_interval_seconds": 60,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_rollback_snapshot(
        self, viewer_client: AsyncClient
    ) -> None:
        """POST /api/system-config/snapshots/1/rollback returns 403 for viewer."""
        resp = await viewer_client.post("/api/system-config/snapshots/1/rollback")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_read_ai_hardware(
        self, client: AsyncClient
    ) -> None:
        """GET /api/system-config/ai-hardware succeeds for system_admin."""
        resp = await client.get("/api/system-config/ai-hardware")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test: X-Change-Reason Header Enforcement
# ---------------------------------------------------------------------------


class TestXChangeReasonEnforcement:
    """Test X-Change-Reason header enforcement on mutation endpoints."""

    @pytest.mark.asyncio
    async def test_missing_change_reason_on_put_ai_hardware(
        self, session_factory, seeded_data
    ) -> None:
        """PUT /api/system-config/ai-hardware returns 400 without X-Change-Reason."""

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
                company_slug="test-pharma",
                user_id=1,
                membership_role="system_admin",
            )

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-User-Id": "1", "X-Company-Id": "1"},
            ) as ac:
                resp = await ac.put(
                    "/api/system-config/ai-hardware",
                    json={"inference_mode": "cpu"},
                )
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_empty_change_reason_on_backup_trigger(
        self, session_factory, seeded_data
    ) -> None:
        """POST /api/system-config/backups/trigger returns 400 with empty reason."""

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
                company_slug="test-pharma",
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
                    "X-User-Id": "1",
                    "X-Company-Id": "1",
                    "X-Change-Reason": "   ",
                },
            ) as ac:
                resp = await ac.post("/api/system-config/backups/trigger")
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_endpoints_do_not_require_change_reason(
        self, session_factory, seeded_data
    ) -> None:
        """GET endpoints succeed without X-Change-Reason header."""

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
                company_slug="test-pharma",
                user_id=1,
                membership_role="system_admin",
            )

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"X-User-Id": "1", "X-Company-Id": "1"},
            ) as ac:
                # GET endpoints should work without X-Change-Reason
                resp = await ac.get("/api/system-config/backups/schedule")
                assert resp.status_code == 200

                resp = await ac.get("/api/system-config/backups/retention")
                assert resp.status_code == 200

                resp = await ac.get("/api/system-config/health/config")
                assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: AI Hardware Endpoints
# ---------------------------------------------------------------------------


class TestAIHardwareEndpoints:
    """Test AI hardware configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_ai_hardware_config(self, client: AsyncClient) -> None:
        """GET /api/system-config/ai-hardware returns current config."""
        resp = await client.get("/api/system-config/ai-hardware")
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_chat_name"] == "gemma-4-e4b-it"
        assert data["inference_mode"] == "mock"
        assert data["gpu_device_id"] == 0
        assert "vllm_chat_status" in data
        assert "vllm_embedding_status" in data

    @pytest.mark.asyncio
    async def test_update_ai_hardware_inference_mode(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/ai-hardware updates inference mode."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.validate_model_path",
            return_value=True,
        ):
            resp = await client.put(
                "/api/system-config/ai-hardware",
                json={"inference_mode": "cpu"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["inference_mode"] == "cpu"

    @pytest.mark.asyncio
    async def test_update_ai_hardware_invalid_inference_mode_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/ai-hardware returns 422 for invalid mode."""
        resp = await client.put(
            "/api/system-config/ai-hardware",
            json={"inference_mode": "invalid_mode"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_ai_hardware_invalid_model_path_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/ai-hardware returns 422 for non-existent path."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.validate_model_path",
            return_value=False,
        ):
            resp = await client.put(
                "/api/system-config/ai-hardware",
                json={"model_chat_path": "/nonexistent/path"},
            )
            assert resp.status_code == 422
            assert "path" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_ai_hardware_empty_payload_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/ai-hardware returns 422 with no fields."""
        resp = await client.put(
            "/api/system-config/ai-hardware",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_ai_hardware_gpu_memory_must_be_positive(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/ai-hardware rejects gpu_memory <= 0."""
        resp = await client.put(
            "/api/system-config/ai-hardware",
            json={"model_chat_max_gpu_memory_gb": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_restart_vllm(self, client: AsyncClient) -> None:
        """POST /api/system-config/ai-hardware/restart-vllm triggers restart."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.restart_vllm_service",
        ) as mock_restart:
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.message = "vLLM restart initiated"
            mock_result.error = None
            mock_restart.return_value = mock_result

            resp = await client.post("/api/system-config/ai-hardware/restart-vllm")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True

    @pytest.mark.asyncio
    async def test_restart_vllm_failure_500(self, client: AsyncClient) -> None:
        """POST /api/system-config/ai-hardware/restart-vllm returns 500 on failure."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.restart_vllm_service",
        ) as mock_restart:
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.message = "Restart failed"
            mock_result.error = "Container not found"
            mock_restart.return_value = mock_result

            resp = await client.post("/api/system-config/ai-hardware/restart-vllm")
            assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_get_vllm_status(self, client: AsyncClient) -> None:
        """GET /api/system-config/ai-hardware/vllm-status returns status."""
        with patch("alcoabase.api.system_config.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance

            resp = await client.get("/api/system-config/ai-hardware/vllm-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in ("running", "unreachable", "error")


# ---------------------------------------------------------------------------
# Test: Storage & Quota Endpoints
# ---------------------------------------------------------------------------


class TestStorageEndpoints:
    """Test storage usage and quota configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_storage_usage(self, client: AsyncClient) -> None:
        """GET /api/system-config/storage/usage returns usage data."""
        with patch(
            "alcoabase.services.storage_quota.StorageQuotaService.get_usage_per_company",
        ) as mock_usage, patch(
            "alcoabase.services.storage_quota.StorageQuotaService.get_total_usage",
        ) as mock_totals:
            mock_company = MagicMock()
            mock_company.company_id = 1
            mock_company.company_name = "Test Pharma Inc"
            mock_company.usage_bytes = 1073741824
            mock_company.human_readable = "1.00 GB"
            mock_company.quota_status = "normal"
            mock_company.quota_limit_bytes = None
            mock_company.alert_threshold_pct = None
            mock_usage.return_value = ([mock_company], False)

            mock_total = MagicMock()
            mock_total.total_used_bytes = 1073741824
            mock_total.total_capacity_bytes = 107374182400
            mock_total.human_readable_used = "1.00 GB"
            mock_total.human_readable_capacity = "100.00 GB"
            mock_total.last_updated = datetime.now(timezone.utc).isoformat()
            mock_totals.return_value = mock_total

            resp = await client.get("/api/system-config/storage/usage")
            assert resp.status_code == 200
            data = resp.json()
            assert "companies" in data
            assert "totals" in data
            assert "is_stale" in data
            assert len(data["companies"]) == 1
            assert data["companies"][0]["company_name"] == "Test Pharma Inc"

    @pytest.mark.asyncio
    async def test_get_storage_quotas(self, client: AsyncClient) -> None:
        """GET /api/system-config/storage/quotas returns quota list."""
        resp = await client.get("/api/system-config/storage/quotas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_update_storage_quota(self, client: AsyncClient) -> None:
        """PUT /api/system-config/storage/quotas/{company_id} sets quota."""
        with patch(
            "alcoabase.services.storage_quota.StorageQuotaService.set_quota",
        ) as mock_set_quota:
            mock_quota = MagicMock()
            mock_quota.quota_limit_bytes = 10737418240
            mock_quota.alert_threshold_pct = 80
            mock_quota.updated_at = datetime.now(timezone.utc)
            mock_quota.updated_by = 1
            mock_set_quota.return_value = mock_quota

            resp = await client.put(
                "/api/system-config/storage/quotas/1",
                json={"quota_limit_bytes": 10737418240},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["company_id"] == 1
            assert data["quota_limit_bytes"] == 10737418240

    @pytest.mark.asyncio
    async def test_update_storage_quota_invalid_threshold_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/storage/quotas/{id} rejects threshold > 99."""
        resp = await client.put(
            "/api/system-config/storage/quotas/1",
            json={"alert_threshold_pct": 100},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_storage_quota_no_fields_400(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/storage/quotas/{id} rejects empty payload."""
        resp = await client.put(
            "/api/system-config/storage/quotas/1",
            json={},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: Backup Endpoints
# ---------------------------------------------------------------------------


class TestBackupEndpoints:
    """Test backup schedule, retention, trigger, and history endpoints."""

    @pytest.mark.asyncio
    async def test_get_backup_schedule(self, client: AsyncClient) -> None:
        """GET /api/system-config/backups/schedule returns schedule."""
        resp = await client.get("/api/system-config/backups/schedule")
        assert resp.status_code == 200
        data = resp.json()
        assert "cron_expression" in data
        assert "human_readable" in data
        assert data["cron_expression"] == "0 2 * * *"

    @pytest.mark.asyncio
    async def test_update_backup_schedule(self, client: AsyncClient) -> None:
        """PUT /api/system-config/backups/schedule updates cron expression."""
        with patch(
            "alcoabase.services.backup_service.BackupService.update_schedule",
        ) as mock_update:
            mock_update.return_value = None

            resp = await client.put(
                "/api/system-config/backups/schedule",
                json={"cron_expression": "0 3 * * *"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["cron_expression"] == "0 3 * * *"
            assert "human_readable" in data

    @pytest.mark.asyncio
    async def test_update_backup_schedule_invalid_cron_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/backups/schedule rejects invalid cron."""
        from alcoabase.services.backup_service import InvalidCronExpressionError

        with patch(
            "alcoabase.services.backup_service.BackupService.update_schedule",
            side_effect=InvalidCronExpressionError("Invalid cron expression"),
        ):
            resp = await client.put(
                "/api/system-config/backups/schedule",
                json={"cron_expression": "invalid cron expression"},
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_backup_retention(self, client: AsyncClient) -> None:
        """GET /api/system-config/backups/retention returns retention policy."""
        resp = await client.get("/api/system-config/backups/retention")
        assert resp.status_code == 200
        data = resp.json()
        assert "retention_days" in data
        assert "backup_count" in data
        assert data["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_update_backup_retention(self, client: AsyncClient) -> None:
        """PUT /api/system-config/backups/retention updates retention days."""
        with patch(
            "alcoabase.services.backup_service.BackupService.update_retention",
        ) as mock_update:
            mock_update.return_value = None

            resp = await client.put(
                "/api/system-config/backups/retention",
                json={"retention_days": 60},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["retention_days"] == 60

    @pytest.mark.asyncio
    async def test_update_backup_retention_out_of_range_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/backups/retention rejects days > 365."""
        resp = await client.put(
            "/api/system-config/backups/retention",
            json={"retention_days": 400},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_backup_retention_zero_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/backups/retention rejects days < 1."""
        resp = await client.put(
            "/api/system-config/backups/retention",
            json={"retention_days": 0},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_trigger_backup(self, client: AsyncClient) -> None:
        """POST /api/system-config/backups/trigger creates backup record."""
        with patch(
            "alcoabase.services.backup_service.BackupService.trigger_backup",
        ) as mock_trigger:
            mock_record = MagicMock()
            mock_record.id = 1
            mock_record.task_id = "celery-task-123"
            mock_record.backup_type = "manual"
            mock_record.status = "queued"
            mock_record.started_at = None
            mock_record.completed_at = None
            mock_record.file_size_bytes = None
            mock_record.duration_seconds = None
            mock_record.error_message = None
            mock_trigger.return_value = mock_record

            resp = await client.post("/api/system-config/backups/trigger")
            assert resp.status_code == 202
            data = resp.json()
            assert data["task_id"] == "celery-task-123"
            assert data["status"] == "queued"
            assert data["backup_type"] == "manual"

    @pytest.mark.asyncio
    async def test_trigger_backup_concurrent_409(
        self, client: AsyncClient
    ) -> None:
        """POST /api/system-config/backups/trigger returns 409 if already running."""
        from alcoabase.services.backup_service import BackupAlreadyRunningError

        with patch(
            "alcoabase.services.backup_service.BackupService.trigger_backup",
            side_effect=BackupAlreadyRunningError("A backup is already in progress"),
        ):
            resp = await client.post("/api/system-config/backups/trigger")
            assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_get_backup_history(self, client: AsyncClient) -> None:
        """GET /api/system-config/backups/history returns backup list."""
        with patch(
            "alcoabase.services.backup_service.BackupService.get_backup_history",
        ) as mock_history:
            mock_record = MagicMock()
            mock_record.id = 1
            mock_record.task_id = "task-abc"
            mock_record.backup_type = "scheduled"
            mock_record.status = "completed"
            mock_record.started_at = datetime(2025, 1, 1, 2, 0, tzinfo=timezone.utc)
            mock_record.completed_at = datetime(2025, 1, 1, 2, 5, tzinfo=timezone.utc)
            mock_record.file_size_bytes = 52428800
            mock_record.duration_seconds = 300.0
            mock_record.error_message = None
            mock_history.return_value = [mock_record]

            resp = await client.get("/api/system-config/backups/history")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["task_id"] == "task-abc"
            assert data[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_backup_status(self, client: AsyncClient) -> None:
        """GET /api/system-config/backups/status/{task_id} returns status."""
        with patch(
            "alcoabase.services.backup_service.BackupService.get_backup_status",
        ) as mock_status:
            mock_record = MagicMock()
            mock_record.id = 1
            mock_record.task_id = "task-xyz"
            mock_record.backup_type = "manual"
            mock_record.status = "running"
            mock_record.started_at = datetime(2025, 1, 1, 3, 0, tzinfo=timezone.utc)
            mock_record.completed_at = None
            mock_record.file_size_bytes = None
            mock_record.duration_seconds = None
            mock_record.error_message = None
            mock_status.return_value = mock_record

            resp = await client.get("/api/system-config/backups/status/task-xyz")
            assert resp.status_code == 200
            data = resp.json()
            assert data["task_id"] == "task-xyz"
            assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_backup_status_not_found_404(
        self, client: AsyncClient
    ) -> None:
        """GET /api/system-config/backups/status/{task_id} returns 404."""
        with patch(
            "alcoabase.services.backup_service.BackupService.get_backup_status",
            return_value=None,
        ):
            resp = await client.get(
                "/api/system-config/backups/status/nonexistent-task"
            )
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Health Monitoring Endpoints
# ---------------------------------------------------------------------------


class TestHealthMonitoringEndpoints:
    """Test health status, history, and configuration endpoints."""

    @pytest.mark.asyncio
    async def test_get_health_status(self, client: AsyncClient) -> None:
        """GET /api/system-config/health/status returns service statuses."""
        with patch(
            "alcoabase.services.health_monitor.HealthMonitor",
        ) as MockHealthMonitor:
            mock_instance = MagicMock()
            mock_instance.get_current_status = AsyncMock(
                return_value=[
                    {
                        "service_name": "postgresql",
                        "status": "healthy",
                        "response_time_ms": 5.2,
                        "last_checked": datetime.now(timezone.utc),
                        "uptime_pct_24h": 99.9,
                        "avg_response_time_5min": 4.8,
                    },
                    {
                        "service_name": "redis",
                        "status": "healthy",
                        "response_time_ms": 1.1,
                        "last_checked": datetime.now(timezone.utc),
                        "uptime_pct_24h": 100.0,
                        "avg_response_time_5min": 1.0,
                    },
                ]
            )
            MockHealthMonitor.return_value = mock_instance

            resp = await client.get("/api/system-config/health/status")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 2
            assert data[0]["service_name"] == "postgresql"
            assert data[0]["status"] == "healthy"
            assert "uptime_pct_24h" in data[0]
            assert "avg_response_time_5min" in data[0]

    @pytest.mark.asyncio
    async def test_get_health_history(self, client: AsyncClient) -> None:
        """GET /api/system-config/health/history/{service} returns history."""
        with patch(
            "alcoabase.services.health_monitor.HealthMonitor",
        ) as MockHealthMonitor:
            mock_result = MagicMock()
            mock_result.id = 1
            mock_result.service_name = "postgresql"
            mock_result.status = "healthy"
            mock_result.response_time_ms = 5.0
            mock_result.error_message = None
            mock_result.checked_at = datetime.now(timezone.utc)
            mock_result.previous_status = None
            mock_result.is_transition = False

            mock_instance = MagicMock()
            mock_instance.get_service_history = AsyncMock(
                return_value=[mock_result]
            )
            MockHealthMonitor.return_value = mock_instance

            resp = await client.get(
                "/api/system-config/health/history/postgresql"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["service_name"] == "postgresql"
            assert data[0]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_get_health_history_unknown_service_404(
        self, client: AsyncClient
    ) -> None:
        """GET /api/system-config/health/history/{service} returns 404 for unknown."""
        resp = await client.get(
            "/api/system-config/health/history/unknown_service"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_health_config(self, client: AsyncClient) -> None:
        """GET /api/system-config/health/config returns configuration."""
        resp = await client.get("/api/system-config/health/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["polling_interval_seconds"] == 30
        assert data["degraded_threshold_seconds"] == 5
        assert data["unreachable_timeout_seconds"] == 10

    @pytest.mark.asyncio
    async def test_update_health_config(self, client: AsyncClient) -> None:
        """PUT /api/system-config/health/config updates parameters."""
        resp = await client.put(
            "/api/system-config/health/config",
            json={
                "polling_interval_seconds": 60,
                "degraded_threshold_seconds": 10,
                "unreachable_timeout_seconds": 30,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["polling_interval_seconds"] == 60
        assert data["degraded_threshold_seconds"] == 10
        assert data["unreachable_timeout_seconds"] == 30

    @pytest.mark.asyncio
    async def test_update_health_config_polling_below_min_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/health/config rejects polling < 10."""
        resp = await client.put(
            "/api/system-config/health/config",
            json={
                "polling_interval_seconds": 5,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_health_config_polling_above_max_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/health/config rejects polling > 300."""
        resp = await client.put(
            "/api/system-config/health/config",
            json={
                "polling_interval_seconds": 500,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_health_config_timeout_below_min_422(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/system-config/health/config rejects timeout < 5."""
        resp = await client.put(
            "/api/system-config/health/config",
            json={
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 3,
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: Service Status Endpoints
# ---------------------------------------------------------------------------


class TestServiceStatusEndpoints:
    """Test service info and resource metrics endpoints."""

    @pytest.mark.asyncio
    async def test_get_all_services(self, client: AsyncClient) -> None:
        """GET /api/system-config/services returns service list."""
        with patch(
            "alcoabase.services.service_registry.ServiceRegistry.get_all_services",
        ) as mock_services, patch(
            "alcoabase.services.service_registry.ServiceRegistry.get_service_stats",
        ) as mock_stats:
            mock_svc = MagicMock()
            mock_svc.container_name = "alcoabase-postgres"
            mock_svc.service_name = "postgresql"
            mock_svc.running_state = "running"
            mock_svc.version = "16.2"
            mock_svc.uptime = "5 days"

            mock_cached = MagicMock()
            mock_cached.services = [mock_svc]
            mock_cached.is_stale = False
            mock_services.return_value = mock_cached

            mock_stat = MagicMock()
            mock_stat.cpu_percent = 12.5
            mock_stat.memory_used_mb = 256.0
            mock_stat.memory_limit_mb = 1024.0
            mock_stats.return_value = mock_stat

            resp = await client.get("/api/system-config/services")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["service_name"] == "postgresql"
            assert data[0]["running_state"] == "running"
            assert data[0]["version"] == "16.2"
            assert data[0]["cpu_percent"] == 12.5

    @pytest.mark.asyncio
    async def test_get_service_metrics(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """GET /api/system-config/services/{service}/metrics returns metrics."""
        # Seed some metric data
        metric = ResourceMetricPoint(
            service_name="postgresql",
            cpu_percent=15.0,
            memory_used_mb=300.0,
            memory_limit_mb=1024.0,
            recorded_at=datetime.now(timezone.utc),
        )
        db_session.add(metric)
        await db_session.flush()
        await db_session.commit()

        resp = await client.get("/api/system-config/services/postgresql/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["service_name"] == "postgresql"
        assert data[0]["cpu_percent"] == 15.0

    @pytest.mark.asyncio
    async def test_get_service_metrics_unknown_service_404(
        self, client: AsyncClient
    ) -> None:
        """GET /api/system-config/services/{service}/metrics returns 404."""
        resp = await client.get(
            "/api/system-config/services/unknown_service/metrics"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Configuration Snapshot Endpoints
# ---------------------------------------------------------------------------


class TestSnapshotEndpoints:
    """Test snapshot history, diff, and rollback endpoints."""

    @pytest.mark.asyncio
    async def test_get_snapshot_history(self, client: AsyncClient) -> None:
        """GET /api/system-config/snapshots returns paginated history."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.get_snapshot_history",
        ) as mock_history:
            mock_result = MagicMock()
            mock_result.items = [
                {
                    "id": 1,
                    "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "created_by_name": "Admin User",
                    "change_reason": "Updated AI config",
                    "is_rollback": False,
                    "changed_keys": ["ai_hardware.inference_mode"],
                }
            ]
            mock_result.total = 1
            mock_result.page = 1
            mock_result.page_size = 20
            mock_result.total_pages = 1
            mock_history.return_value = mock_result

            resp = await client.get("/api/system-config/snapshots")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert "total" in data
            assert "page" in data
            assert "page_size" in data
            assert "total_pages" in data
            assert data["page"] == 1
            assert data["page_size"] == 20
            assert len(data["items"]) == 1
            assert data["items"][0]["change_reason"] == "Updated AI config"

    @pytest.mark.asyncio
    async def test_get_snapshot_history_pagination(
        self, client: AsyncClient
    ) -> None:
        """GET /api/system-config/snapshots respects page and page_size."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.get_snapshot_history",
        ) as mock_history:
            mock_result = MagicMock()
            mock_result.items = []
            mock_result.total = 0
            mock_result.page = 2
            mock_result.page_size = 5
            mock_result.total_pages = 0
            mock_history.return_value = mock_result

            resp = await client.get(
                "/api/system-config/snapshots?page=2&page_size=5"
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["page"] == 2
            assert data["page_size"] == 5

    @pytest.mark.asyncio
    async def test_get_snapshot_diff(self, client: AsyncClient) -> None:
        """GET /api/system-config/snapshots/{id}/diff returns diff."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.get_snapshot_diff",
        ) as mock_diff:
            from alcoabase.schemas.system_config import ConfigDiffItem

            mock_diff.return_value = [
                ConfigDiffItem(
                    key="ai_hardware.inference_mode",
                    old_value="gpu",
                    new_value="mock",
                )
            ]

            resp = await client.get("/api/system-config/snapshots/1/diff")
            assert resp.status_code == 200
            data = resp.json()
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["key"] == "ai_hardware.inference_mode"
            assert data[0]["old_value"] == "gpu"
            assert data[0]["new_value"] == "mock"

    @pytest.mark.asyncio
    async def test_get_snapshot_diff_not_found_404(
        self, client: AsyncClient
    ) -> None:
        """GET /api/system-config/snapshots/{id}/diff returns 404."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.get_snapshot_diff",
            side_effect=ValueError("Snapshot not found"),
        ):
            resp = await client.get("/api/system-config/snapshots/9999/diff")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rollback_to_snapshot(self, client: AsyncClient) -> None:
        """POST /api/system-config/snapshots/{id}/rollback performs rollback."""
        from alcoabase.schemas.system_config import ConfigDiffItem

        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.rollback_to_snapshot",
        ) as mock_rollback:
            mock_result = MagicMock()
            mock_result.snapshot_id = 1
            mock_result.snapshot_timestamp = "2025-01-01T00:00:00+00:00"
            mock_result.acting_user = "Admin User"
            mock_result.changed_categories = ["ai_hardware"]
            mock_result.diff = [
                ConfigDiffItem(
                    key="ai_hardware.inference_mode",
                    old_value="cpu",
                    new_value="mock",
                )
            ]
            mock_result.services_requiring_restart = ["vllm"]
            mock_rollback.return_value = mock_result

            resp = await client.post("/api/system-config/snapshots/1/rollback")
            assert resp.status_code == 200
            data = resp.json()
            assert data["snapshot_id"] == 1
            assert data["acting_user"] == "Admin User"
            assert "ai_hardware" in data["changed_categories"]
            assert "vllm" in data["services_requiring_restart"]
            assert len(data["diff"]) == 1

    @pytest.mark.asyncio
    async def test_rollback_snapshot_not_found_404(
        self, client: AsyncClient
    ) -> None:
        """POST /api/system-config/snapshots/{id}/rollback returns 404."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.rollback_to_snapshot",
            side_effect=ValueError("Snapshot not found"),
        ):
            resp = await client.post(
                "/api/system-config/snapshots/9999/rollback"
            )
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_rollback_validation_failure_422(
        self, client: AsyncClient
    ) -> None:
        """POST /api/system-config/snapshots/{id}/rollback returns 422 on validation error."""
        with patch(
            "alcoabase.services.system_config.SystemConfigurationService.rollback_to_snapshot",
            side_effect=ValueError(
                "Validation failed: ai_hardware.model_chat_max_gpu_memory_gb "
                "must be positive"
            ),
        ):
            resp = await client.post("/api/system-config/snapshots/1/rollback")
            assert resp.status_code == 422
            assert "validation" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_rollback_empty_change_reason_400(
        self, session_factory, seeded_data
    ) -> None:
        """POST /api/system-config/snapshots/{id}/rollback rejects empty reason."""

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
                company_slug="test-pharma",
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
                    "X-User-Id": "1",
                    "X-Company-Id": "1",
                    "X-Change-Reason": "",
                },
            ) as ac:
                resp = await ac.post("/api/system-config/snapshots/1/rollback")
                assert resp.status_code == 400
        finally:
            app.dependency_overrides.clear()
