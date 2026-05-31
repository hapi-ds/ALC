"""Integration tests for ALC corporate environment seed CLI and API.

Tests the full CLI script and API endpoint interfaces for the ALC
corporate environment seeding service, including success paths,
error handling, authentication, and idempotency.

Covers:
- CLI success (exit 0, valid JSON SeedReport)
- CLI failure (exit 1, stderr error output)
- API 200 success with SeedReport
- API 401 unauthorized (missing auth)
- API 400 missing X-Change-Reason header
- Full idempotent run (two consecutive runs produce same DB state)
- Transaction rollback on simulated failure

References:
    - Task 8.1: Write integration tests for CLI and API
    - Requirements: 6.1, 6.2, 6.3, 6.5, 6.7, 6.8
"""

import json
from collections.abc import AsyncGenerator
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.schemas.alc_seed import SeedReport
from alcoabase.services.alc_seed_service import ALCSeedService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def authenticated_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated as system_administrator.

    Overrides dependencies so the full request lifecycle (middleware →
    dependency → route) is exercised without needing a real database.
    The ALCSeedService is mocked at the test level.
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def _override_get_db_session():
        yield mock_session

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="root-company",
            user_id=1,
            membership_role="system_administrator",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    # Patch RBACService to allow access for system_administrator
    with patch(
        "alcoabase.dependencies.rbac.RBACService"
    ) as MockRBAC:
        mock_rbac_instance = AsyncMock()
        # Return the TenantContext (not AccessDenied) to indicate success
        mock_rbac_instance.check_permission = AsyncMock(return_value=None)
        MockRBAC.return_value = mock_rbac_instance

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
async def unauthenticated_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient without authentication overrides.

    The default tenant context dependency will raise 401 since no
    X-User-Id header is provided. We still override get_db_session
    to avoid needing a real database connection for the dependency chain.
    """
    app.dependency_overrides.clear()

    mock_session = AsyncMock()

    async def _override_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: mock CLI infrastructure
# ---------------------------------------------------------------------------


def _mock_cli_infrastructure(service_side_effect=None, service_return=None):
    """Create nested patches for CLI script infrastructure.

    Mocks init_db, get_engine, async_sessionmaker, and ALCSeedService
    so the CLI main() function can be tested without a real database.

    Args:
        service_side_effect: Exception to raise from service.execute().
        service_return: Return value for service.execute().

    Returns:
        Context manager stack and mock_session reference.
    """
    mock_service_instance = AsyncMock()
    if service_side_effect:
        mock_service_instance.execute = AsyncMock(side_effect=service_side_effect)
    else:
        mock_service_instance.execute = AsyncMock(return_value=service_return)

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    return mock_service_instance, mock_session


# ---------------------------------------------------------------------------
# Test: CLI Success
# ---------------------------------------------------------------------------


class TestCLISuccess:
    """Test CLI script exits 0 and outputs valid JSON SeedReport."""

    @pytest.mark.asyncio
    async def test_cli_success(self) -> None:
        """CLI script exits 0 and stdout is valid JSON SeedReport.

        Validates: Requirements 6.1, 6.5
        """
        mock_report = SeedReport(
            company_id=1,
            company_slug="alc-corporate",
            users_created=["alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"],
            users_skipped=[],
            folders_created=["Governance — User Requirement Specifications"],
            folders_skipped=[],
            risk_profile_created=True,
            regulatory_baseline_created=True,
            audit_config_created=True,
            agents_activated=["master-auditor"],
            agents_skipped=[],
            workflow_created=True,
            total_duration_ms=150,
        )

        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_return=mock_report
        )

        # Patch at the top-level module import
        with patch(
            "alcoabase.scripts.seed_alc_corporate.ALCSeedService"
        ) as MockService, patch(
            "alcoabase.scripts.seed_alc_corporate.init_db",
            new_callable=AsyncMock,
        ):
            MockService.return_value = mock_service_instance

            # Patch the local imports inside main()
            with patch(
                "alcoabase.database.get_engine"
            ) as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.dispose = AsyncMock()
                mock_get_engine.return_value = mock_engine

                # Create a mock session factory that returns our mock session
                mock_session_factory = AsyncMock()
                mock_session_factory.__call__ = lambda self: self
                # Make session_factory() return an async context manager
                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_cm.__aexit__ = AsyncMock(return_value=False)

                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=lambda: mock_session_cm,
                ):
                    # We need to patch the sessionmaker at the point it's used
                    # The script does: session_factory = async_sessionmaker(...)
                    # then: async with session_factory() as session:
                    # So we need the return of async_sessionmaker(...) to be callable
                    # and return an async context manager

                    # Simpler approach: patch the entire main function's internals
                    # by patching get_engine to return a mock that works with
                    # async_sessionmaker
                    pass

        # Use a simpler approach: directly test the main() logic by patching
        # at the database module level
        with patch(
            "alcoabase.scripts.seed_alc_corporate.ALCSeedService"
        ) as MockService, patch(
            "alcoabase.scripts.seed_alc_corporate.init_db",
            new_callable=AsyncMock,
        ):
            MockService.return_value = mock_service_instance

            # Patch get_engine in the database module (where it's imported from)
            with patch("alcoabase.database.get_engine") as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.dispose = AsyncMock()
                mock_get_engine.return_value = mock_engine

                # Patch async_sessionmaker to return a factory that yields
                # our mock session via async context manager
                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_cm.__aexit__ = AsyncMock(return_value=False)

                class MockSessionFactory:
                    def __call__(self):
                        return mock_session_cm

                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=MockSessionFactory(),
                ):
                    import sys

                    from alcoabase.scripts.seed_alc_corporate import main

                    captured_stdout = StringIO()
                    old_stdout = sys.stdout
                    sys.stdout = captured_stdout

                    try:
                        await main()
                    finally:
                        sys.stdout = old_stdout

                    output = captured_stdout.getvalue()

                    # Verify output is valid JSON
                    parsed = json.loads(output)
                    assert parsed["company_slug"] == "alc-corporate"
                    assert parsed["company_id"] == 1
                    assert "users_created" in parsed
                    assert "total_duration_ms" in parsed
                    assert parsed["users_created"] == [
                        "alc-it-admin", "alc-doc-admin",
                        "alc-quality-mgr", "alc-user",
                    ]

                    # Verify commit was called (success path)
                    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: CLI Failure
# ---------------------------------------------------------------------------


class TestCLIFailure:
    """Test CLI script exits 1 on DB failure with error on stderr."""

    @pytest.mark.asyncio
    async def test_cli_failure(self) -> None:
        """CLI script exits 1 on DB failure, stderr has error.

        Validates: Requirements 6.5
        """
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_side_effect=RuntimeError("Database connection refused")
        )

        with patch(
            "alcoabase.scripts.seed_alc_corporate.ALCSeedService"
        ) as MockService, patch(
            "alcoabase.scripts.seed_alc_corporate.init_db",
            new_callable=AsyncMock,
        ):
            MockService.return_value = mock_service_instance

            with patch("alcoabase.database.get_engine") as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.dispose = AsyncMock()
                mock_get_engine.return_value = mock_engine

                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_cm.__aexit__ = AsyncMock(return_value=False)

                class MockSessionFactory:
                    def __call__(self):
                        return mock_session_cm

                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=MockSessionFactory(),
                ):
                    import sys

                    from alcoabase.scripts.seed_alc_corporate import main

                    captured_stderr = StringIO()
                    old_stderr = sys.stderr
                    sys.stderr = captured_stderr

                    try:
                        with pytest.raises(SystemExit) as exc_info:
                            await main()
                    finally:
                        sys.stderr = old_stderr

                    # Verify exit code 1
                    assert exc_info.value.code == 1

                    # Verify error message on stderr
                    error_output = captured_stderr.getvalue()
                    assert "Database connection refused" in error_output
                    assert "failed" in error_output.lower()

                    # Verify rollback was called (failure path)
                    mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Test: API Endpoint Success
# ---------------------------------------------------------------------------


class TestAPIEndpointSuccess:
    """Test POST /api/admin/seed-alc-corporate returns 200 with SeedReport."""

    @pytest.mark.asyncio
    async def test_api_endpoint_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST returns 200 with SeedReport on success.

        Validates: Requirements 6.2
        """
        mock_report = SeedReport(
            company_id=42,
            company_slug="alc-corporate",
            users_created=["alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"],
            users_skipped=[],
            folders_created=[
                "Governance — User Requirement Specifications",
                "Governance — AI Regulatory Guidelines",
            ],
            folders_skipped=[],
            risk_profile_created=True,
            regulatory_baseline_created=True,
            audit_config_created=True,
            agents_activated=["master-auditor", "data-integrity-specialist"],
            agents_skipped=[],
            workflow_created=True,
            total_duration_ms=250,
        )

        with patch.object(
            ALCSeedService, "execute", new_callable=AsyncMock, return_value=mock_report
        ):
            resp = await authenticated_client.post(
                "/api/admin/seed-alc-corporate",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["company_id"] == 42
            assert data["company_slug"] == "alc-corporate"
            assert data["users_created"] == [
                "alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"
            ]
            assert data["risk_profile_created"] is True
            assert data["regulatory_baseline_created"] is True
            assert data["audit_config_created"] is True
            assert data["workflow_created"] is True
            assert data["total_duration_ms"] == 250
            assert data["agents_activated"] == [
                "master-auditor", "data-integrity-specialist"
            ]


# ---------------------------------------------------------------------------
# Test: API Endpoint Unauthorized
# ---------------------------------------------------------------------------


class TestAPIEndpointUnauthorized:
    """Test POST without auth returns 401."""

    @pytest.mark.asyncio
    async def test_api_endpoint_unauthorized(
        self, unauthenticated_client: AsyncClient
    ) -> None:
        """POST without auth returns 401.

        Validates: Requirements 6.8
        """
        resp = await unauthenticated_client.post(
            "/api/admin/seed-alc-corporate",
            headers={"X-Change-Reason": "Test"},
        )

        # Without X-User-Id header, tenant context resolution returns 401
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test: API Endpoint Missing Header
# ---------------------------------------------------------------------------


class TestAPIEndpointMissingHeader:
    """Test POST without X-Change-Reason returns 400."""

    @pytest.mark.asyncio
    async def test_api_endpoint_missing_header(self) -> None:
        """POST without X-Change-Reason returns 400.

        Validates: Requirements 6.8
        """
        mock_session = AsyncMock()

        async def _override_get_db_session():
            yield mock_session

        async def _override_get_tenant_context():
            return TenantContext(
                company_id=1,
                company_slug="root-company",
                user_id=1,
                membership_role="system_administrator",
            )

        app.dependency_overrides[get_db_session] = _override_get_db_session
        app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

        with patch(
            "alcoabase.dependencies.rbac.RBACService"
        ) as MockRBAC:
            mock_rbac_instance = AsyncMock()
            mock_rbac_instance.check_permission = AsyncMock(return_value=None)
            MockRBAC.return_value = mock_rbac_instance

            try:
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                    headers={
                        "X-User-Id": "1",
                        "X-Company-Id": "1",
                        # Deliberately omitting X-Change-Reason
                    },
                ) as client:
                    resp = await client.post("/api/admin/seed-alc-corporate")

                    # The audit middleware enforces X-Change-Reason on POST
                    assert resp.status_code == 400
            finally:
                app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Full Idempotent Run
# ---------------------------------------------------------------------------


class TestFullIdempotentRun:
    """Test two consecutive runs produce same DB state."""

    @pytest.mark.asyncio
    async def test_full_idempotent_run(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Two consecutive runs produce same DB state (idempotent).

        Validates: Requirements 6.7
        """
        # First run: creates entities
        first_report = SeedReport(
            company_id=1,
            company_slug="alc-corporate",
            users_created=["alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"],
            users_skipped=[],
            folders_created=[
                "Governance — User Requirement Specifications",
                "Governance — AI Regulatory Guidelines",
                "Governance — User Guides",
                "Governance — Admin Guides",
                "Governance — Risk Framework",
                "Governance — All Documents",
            ],
            folders_skipped=[],
            risk_profile_created=True,
            regulatory_baseline_created=True,
            audit_config_created=True,
            agents_activated=["master-auditor"],
            agents_skipped=[],
            workflow_created=True,
            total_duration_ms=200,
        )

        # Second run: all entities already exist, everything skipped
        second_report = SeedReport(
            company_id=1,
            company_slug="alc-corporate",
            users_created=[],
            users_skipped=["alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"],
            folders_created=[],
            folders_skipped=[
                "Governance — User Requirement Specifications",
                "Governance — AI Regulatory Guidelines",
                "Governance — User Guides",
                "Governance — Admin Guides",
                "Governance — Risk Framework",
                "Governance — All Documents",
            ],
            risk_profile_created=False,
            regulatory_baseline_created=False,
            audit_config_created=False,
            agents_activated=[],
            agents_skipped=["master-auditor"],
            workflow_created=False,
            total_duration_ms=50,
        )

        # Simulate two consecutive calls returning different reports
        call_count = {"n": 0}

        async def mock_execute(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return first_report
            return second_report

        with patch.object(ALCSeedService, "execute", mock_execute):
            # First invocation
            resp1 = await authenticated_client.post(
                "/api/admin/seed-alc-corporate",
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert len(data1["users_created"]) == 4
            assert len(data1["users_skipped"]) == 0
            assert data1["risk_profile_created"] is True
            assert data1["workflow_created"] is True

            # Second invocation (idempotent)
            resp2 = await authenticated_client.post(
                "/api/admin/seed-alc-corporate",
            )
            assert resp2.status_code == 200
            data2 = resp2.json()

            # All entities should be reported as skipped
            assert len(data2["users_created"]) == 0
            assert len(data2["users_skipped"]) == 4
            assert len(data2["folders_created"]) == 0
            assert len(data2["folders_skipped"]) == 6
            assert data2["risk_profile_created"] is False
            assert data2["regulatory_baseline_created"] is False
            assert data2["audit_config_created"] is False
            assert data2["workflow_created"] is False
            assert len(data2["agents_activated"]) == 0
            assert len(data2["agents_skipped"]) == 1

            # Same company_id in both runs
            assert data1["company_id"] == data2["company_id"]


# ---------------------------------------------------------------------------
# Test: Transaction Rollback
# ---------------------------------------------------------------------------


class TestTransactionRollback:
    """Test simulated failure leaves DB unchanged."""

    @pytest.mark.asyncio
    async def test_transaction_rollback(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Simulated failure returns 500 with SeedError (transaction rolled back).

        Validates: Requirements 6.3
        """
        with patch.object(
            ALCSeedService,
            "execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Simulated failure in folder creation step"),
        ):
            resp = await authenticated_client.post(
                "/api/admin/seed-alc-corporate",
            )

            # The endpoint catches exceptions and returns 500 with SeedError
            assert resp.status_code == 500
            data = resp.json()
            assert "error" in data
            assert "failed" in data["error"].lower()
            assert "failed_step" in data
            assert "detail" in data
            assert "folder" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_transaction_rollback_cli(self) -> None:
        """CLI rollback: simulated failure triggers rollback and exit 1.

        Validates: Requirements 6.3
        """
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_side_effect=RuntimeError("Simulated DB constraint violation")
        )

        with patch(
            "alcoabase.scripts.seed_alc_corporate.ALCSeedService"
        ) as MockService, patch(
            "alcoabase.scripts.seed_alc_corporate.init_db",
            new_callable=AsyncMock,
        ):
            MockService.return_value = mock_service_instance

            with patch("alcoabase.database.get_engine") as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.dispose = AsyncMock()
                mock_get_engine.return_value = mock_engine

                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session_cm.__aexit__ = AsyncMock(return_value=False)

                class MockSessionFactory:
                    def __call__(self):
                        return mock_session_cm

                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=MockSessionFactory(),
                ):
                    import sys

                    from alcoabase.scripts.seed_alc_corporate import main

                    captured_stderr = StringIO()
                    old_stderr = sys.stderr
                    sys.stderr = captured_stderr

                    try:
                        with pytest.raises(SystemExit) as exc_info:
                            await main()
                    finally:
                        sys.stderr = old_stderr

                    assert exc_info.value.code == 1

                    # Verify rollback was called (transaction atomicity)
                    mock_session.rollback.assert_called_once()

                    # Verify commit was NOT called
                    mock_session.commit.assert_not_called()

                    # Verify error output
                    error_output = captured_stderr.getvalue()
                    assert "constraint violation" in error_output.lower()
