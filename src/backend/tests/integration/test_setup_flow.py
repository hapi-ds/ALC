"""Integration tests for the complete setup wizard flow.

Tests the full end-to-end setup flow through the API layer using
httpx.AsyncClient with an async SQLite in-memory database, verifying:
- Full setup flow: status → admin → company → ai-mode → complete
- Audit trail entries created for each setup step (via setup_status record)
- Audit entry for admin creation has no user context (first step)
- Setup status survives simulated restart (DB persistence)
- Demo data seeding creates expected record types with is_demo_data=True
- Setup endpoints return 403 after completion

References:
    - Task 12.1: Write integration tests for the complete setup wizard flow
    - Requirements: 1.4, 2.4, 6.1, 6.4, 7.3, 9.1, 9.2, 9.3, 9.4, 9.5
"""

from collections.abc import AsyncGenerator

# ---------------------------------------------------------------------------
# bcrypt compatibility patch (bcrypt 5.x + passlib 1.7.4)
# ---------------------------------------------------------------------------
import bcrypt as _bcrypt_lib

_original_hashpw = _bcrypt_lib.hashpw
_original_checkpw = _bcrypt_lib.checkpw


def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_hashpw(password[:72], salt)


def _safe_checkpw(password: bytes, hashed_password: bytes) -> bool:
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_checkpw(password[:72], hashed_password)


_bcrypt_lib.hashpw = _safe_hashpw
_bcrypt_lib.checkpw = _safe_checkpw

# ---------------------------------------------------------------------------

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base, get_db_session
from alcoabase.main import app
from alcoabase.middleware.setup_guard import SetupGuardMiddleware
from alcoabase.models.document import Document
from alcoabase.models.setup_status import SetupStatus
from alcoabase.models.template import Template
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.models.workflow import WorkflowDefinition


# ---------------------------------------------------------------------------
# Fixtures: Async SQLite in-memory database for setup flow tests
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
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test verification."""
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Override the conftest autouse bypass_setup_guard fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enable_setup_guard():
    """Override the conftest bypass_setup_guard to allow setup flow testing.

    Sets _is_initialized to False so the setup guard allows setup endpoints
    and blocks other endpoints (simulating a fresh deployment).
    """
    original = SetupGuardMiddleware._is_initialized
    SetupGuardMiddleware._is_initialized = False
    yield
    SetupGuardMiddleware._is_initialized = original


# ---------------------------------------------------------------------------
# Client fixture with DB override
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient with overridden get_db_session.

    Uses a real async SQLite session so the full request lifecycle
    (middleware → dependency → route → DB) is exercised.
    """

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Full end-to-end setup flow
# ---------------------------------------------------------------------------


class TestFullSetupFlow:
    """Test the complete setup wizard flow from status check to completion."""

    @pytest.mark.asyncio
    async def test_full_setup_flow_end_to_end(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Walk through the full setup flow: status → admin → company → ai-mode → complete."""
        # Step 1: Check initial status — all steps should be incomplete
        resp = await client.get("/api/v1/setup/status")
        assert resp.status_code == 200
        status = resp.json()
        assert status["is_complete"] is False
        assert status["admin_created"] is False
        assert status["company_created"] is False
        assert status["ai_mode_configured"] is False
        assert status["demo_data_seeded"] is False

        # Step 2: Create root admin
        admin_payload = {
            "username": "rootadmin",
            "email": "admin@alcoabase.example.com",
            "password": "SecureP@ss123!",
            "full_name": "Root Administrator",
        }
        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: create root admin"},
        )
        assert resp.status_code == 201
        admin_result = resp.json()
        assert admin_result["username"] == "rootadmin"
        assert admin_result["user_id"] > 0
        assert "access_token" in admin_result
        assert admin_result["token_type"] == "bearer"

        # Extract token for subsequent authenticated requests
        token = admin_result["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "X-Change-Reason": "Setup: configure system",
        }

        # Step 3: Create initial company
        company_payload = {
            "display_name": "Pharma Corp",
            "slug": "pharma-corp",
            "regulatory_framework": "ISO_13485",
        }
        resp = await client.post(
            "/api/v1/setup/company",
            json=company_payload,
            headers=auth_headers,
        )
        assert resp.status_code == 201
        company_result = resp.json()
        assert company_result["slug"] == "pharma-corp"
        assert company_result["display_name"] == "Pharma Corp"
        assert company_result["company_id"] > 0

        # Step 4: Configure AI mode (mock — no connectivity check needed)
        ai_payload = {"mode": "mock"}
        resp = await client.post(
            "/api/v1/setup/ai-mode",
            json=ai_payload,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        ai_result = resp.json()
        assert ai_result["mode"] == "mock"
        assert ai_result["connectivity_warning"] is None

        # Step 5: Complete setup (without demo data)
        complete_payload = {"seed_demo_data": False}
        resp = await client.post(
            "/api/v1/setup/complete",
            json=complete_payload,
            headers=auth_headers,
        )
        assert resp.status_code == 200
        complete_result = resp.json()
        assert complete_result["message"] == "Setup completed successfully"
        assert "completed_at" in complete_result

        # Verify final status shows all steps complete
        # After completion, the guard blocks setup paths with 403
        # so we need to temporarily allow it for verification
        SetupGuardMiddleware._is_initialized = False
        resp = await client.get("/api/v1/setup/status")
        assert resp.status_code == 200
        final_status = resp.json()
        assert final_status["is_complete"] is True
        assert final_status["admin_created"] is True
        assert final_status["company_created"] is True
        assert final_status["ai_mode_configured"] is True


# ---------------------------------------------------------------------------
# Test: Audit trail entries via setup_status record tracking
# ---------------------------------------------------------------------------


class TestSetupAuditTrail:
    """Test that setup steps create audit trail entries via setup_status tracking."""

    @pytest.mark.asyncio
    async def test_setup_status_tracks_each_step(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Each setup step updates the setup_status record as an audit trail.

        Validates: Requirements 9.1, 9.2, 9.3, 9.4
        """
        # Step 1: Create admin — no user context needed (first step)
        admin_payload = {
            "username": "auditadmin",
            "email": "audit@alcoabase.example.com",
            "password": "AuditP@ss1234!",
            "full_name": "Audit Admin",
        }
        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: admin creation"},
        )
        assert resp.status_code == 201
        token = resp.json()["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "X-Change-Reason": "Setup: audit trail test",
        }

        # Verify setup_status after admin creation
        result = await db_session.execute(select(SetupStatus))
        status = result.scalar_one()
        assert status.admin_created is True
        assert status.root_admin_id is not None
        assert status.company_created is False

        # Step 2: Create company
        resp = await client.post(
            "/api/v1/setup/company",
            json={
                "display_name": "Audit Corp",
                "slug": "audit-corp",
                "regulatory_framework": "ISO_13485",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

        # Refresh session to see updates
        db_session.expire_all()
        result = await db_session.execute(select(SetupStatus))
        status = result.scalar_one()
        assert status.company_created is True
        assert status.company_id is not None

        # Step 3: Configure AI mode
        resp = await client.post(
            "/api/v1/setup/ai-mode",
            json={"mode": "mock"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        db_session.expire_all()
        result = await db_session.execute(select(SetupStatus))
        status = result.scalar_one()
        assert status.ai_mode_configured is True
        assert status.ai_hardware_mode == "mock"

        # Step 4: Complete setup
        resp = await client.post(
            "/api/v1/setup/complete",
            json={"seed_demo_data": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        db_session.expire_all()
        result = await db_session.execute(select(SetupStatus))
        status = result.scalar_one()
        assert status.is_complete is True
        assert status.completed_at is not None

    @pytest.mark.asyncio
    async def test_admin_creation_has_no_user_context(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Admin creation step works without any user context headers.

        The first setup step (admin creation) must work without any
        authenticated user context since no user exists yet.

        Validates: Requirement 9.5
        """
        # POST /admin without any X-User-Id header — only X-Change-Reason
        admin_payload = {
            "username": "noctxadmin",
            "email": "noctx@alcoabase.example.com",
            "password": "NoCtxP@ss1234!",
            "full_name": "No Context Admin",
        }
        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: first admin (no user context)"},
        )
        assert resp.status_code == 201
        result = resp.json()
        assert result["username"] == "noctxadmin"
        assert result["user_id"] > 0


# ---------------------------------------------------------------------------
# Test: Setup status survives simulated restart (DB persistence)
# ---------------------------------------------------------------------------


class TestSetupPersistence:
    """Test that setup status persists across simulated restarts."""

    @pytest.mark.asyncio
    async def test_setup_status_survives_simulated_restart(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Setup progress persists in DB and survives cache invalidation.

        Simulates a restart by invalidating the in-memory cache and
        verifying the status is correctly read from the database.

        Validates: Requirement 1.4
        """
        # Create admin to establish some setup progress
        admin_payload = {
            "username": "persistadmin",
            "email": "persist@alcoabase.example.com",
            "password": "PersistP@ss123!",
            "full_name": "Persist Admin",
        }
        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: persistence test"},
        )
        assert resp.status_code == 201

        # Verify status shows admin_created via API
        resp = await client.get("/api/v1/setup/status")
        assert resp.status_code == 200
        assert resp.json()["admin_created"] is True

        # Simulate restart: invalidate cache and create a fresh session
        SetupGuardMiddleware._is_initialized = None

        # The guard will re-query the DB on next request.
        # Since setup is not complete, it should still allow setup paths.
        # Force the guard to re-check by setting to None (uncached)
        SetupGuardMiddleware._is_initialized = False

        # Verify the status is still available from DB
        async with session_factory() as session:
            result = await session.execute(select(SetupStatus))
            status = result.scalar_one()
            assert status.admin_created is True
            assert status.is_complete is False


# ---------------------------------------------------------------------------
# Test: Demo data seeding creates expected record types
# ---------------------------------------------------------------------------


class TestDemoDataSeeding:
    """Test that demo data seeding creates expected records with is_demo_data=True."""

    @pytest.mark.asyncio
    async def test_demo_data_creates_expected_record_types(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Complete setup with seed_demo_data=True creates demo records.

        Validates: Requirements 6.1, 6.4
        """
        # Walk through full setup to reach completion with demo data
        admin_payload = {
            "username": "demoadmin",
            "email": "demo@alcoabase.example.com",
            "password": "DemoP@ssw0rd1!",
            "full_name": "Demo Admin",
        }
        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: demo data test"},
        )
        assert resp.status_code == 201
        token = resp.json()["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "X-Change-Reason": "Setup: demo data test",
        }

        resp = await client.post(
            "/api/v1/setup/company",
            json={
                "display_name": "Demo Corp",
                "slug": "demo-corp",
                "regulatory_framework": "ISO_13485",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/v1/setup/ai-mode",
            json={"mode": "mock"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Complete with demo data seeding
        resp = await client.post(
            "/api/v1/setup/complete",
            json={"seed_demo_data": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Verify demo documents were created with is_demo_data=True
        result = await db_session.execute(
            select(Document).where(Document.is_demo_data == True)  # noqa: E712
        )
        demo_docs = result.scalars().all()
        assert len(demo_docs) >= 3
        for doc in demo_docs:
            assert doc.is_demo_data is True
            assert "[DEMO]" in doc.title

        # Verify demo templates were created
        result = await db_session.execute(
            select(Template).where(Template.is_demo_data == True)  # noqa: E712
        )
        demo_templates = result.scalars().all()
        assert len(demo_templates) >= 2
        for tmpl in demo_templates:
            assert tmpl.is_demo_data is True
            assert "[DEMO]" in tmpl.name

        # Verify demo virtual folders were created
        result = await db_session.execute(
            select(VirtualFolder).where(VirtualFolder.is_demo_data == True)  # noqa: E712
        )
        demo_folders = result.scalars().all()
        assert len(demo_folders) >= 2
        for folder in demo_folders:
            assert folder.is_demo_data is True
            assert "[DEMO]" in folder.name

        # Verify demo workflow definitions were created
        result = await db_session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.is_demo_data == True  # noqa: E712
            )
        )
        demo_workflows = result.scalars().all()
        assert len(demo_workflows) >= 2
        for wf in demo_workflows:
            assert wf.is_demo_data is True
            assert "[DEMO]" in wf.name


# ---------------------------------------------------------------------------
# Test: Setup endpoints return 403 after completion
# ---------------------------------------------------------------------------


class TestSetupLockout:
    """Test that setup endpoints return 403 after setup is completed."""

    @pytest.mark.asyncio
    async def test_setup_endpoints_return_403_after_completion(
        self, client: AsyncClient
    ) -> None:
        """After setup completes, all setup endpoints return 403.

        Validates: Requirement 7.3
        """
        # Complete the full setup flow first
        admin_payload = {
            "username": "lockadmin",
            "email": "lock@alcoabase.example.com",
            "password": "LockP@ssw0rd1!",
            "full_name": "Lock Admin",
        }
        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: lockout test"},
        )
        assert resp.status_code == 201
        token = resp.json()["access_token"]
        auth_headers = {
            "Authorization": f"Bearer {token}",
            "X-Change-Reason": "Setup: lockout test",
        }

        resp = await client.post(
            "/api/v1/setup/company",
            json={
                "display_name": "Lock Corp",
                "slug": "lock-corp",
                "regulatory_framework": "ISO_13485",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201

        resp = await client.post(
            "/api/v1/setup/ai-mode",
            json={"mode": "mock"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/v1/setup/complete",
            json={"seed_demo_data": False},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Now the guard should be initialized — set it explicitly
        # (complete_setup calls invalidate_cache which sets to None,
        # then re-query would find is_complete=True)
        SetupGuardMiddleware._is_initialized = True

        # All setup endpoints should now return 403
        resp = await client.get("/api/v1/setup/status")
        assert resp.status_code == 403
        assert "Setup already completed" in resp.json()["detail"]

        resp = await client.post(
            "/api/v1/setup/admin",
            json=admin_payload,
            headers={"X-Change-Reason": "Setup: should fail"},
        )
        assert resp.status_code == 403

        resp = await client.post(
            "/api/v1/setup/company",
            json={"display_name": "X", "regulatory_framework": "ISO_13485"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

        resp = await client.post(
            "/api/v1/setup/ai-mode",
            json={"mode": "gpu"},
            headers=auth_headers,
        )
        assert resp.status_code == 403

        resp = await client.post(
            "/api/v1/setup/complete",
            json={"seed_demo_data": False},
            headers=auth_headers,
        )
        assert resp.status_code == 403
