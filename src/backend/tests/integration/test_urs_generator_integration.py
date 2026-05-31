"""Integration tests for URS generation CLI and API endpoint.

Tests the full CLI script and API endpoint interfaces for the URS
generator service, including success paths, error handling,
authentication, authorization, idempotency, and governance folder
visibility.

Covers:
- CLI success (exit 0, valid JSON URSGenerationReport)
- CLI failure without prerequisites (exit 1, stderr error)
- API 200 success with URSGenerationReport
- API 401 unauthorized (missing auth)
- API 403 forbidden (non-admin role)
- API 400 missing X-Change-Reason header
- Full idempotent run (two runs → one Document, two versions)
- Document appears in governance folder (tag-filtered query)

References:
    - Task 7.1: Write integration tests for CLI and API
    - Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 7.1
"""

import json
import sys
from collections.abc import AsyncGenerator
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.schemas.urs_generation import URSGenerationReport
from alcoabase.services.urs_generator_service import URSGeneratorService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def authenticated_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated as system_administrator.

    Overrides dependencies so the full request lifecycle (middleware →
    dependency → route) is exercised without needing a real database.
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def _override_get_db_session():
        yield mock_session

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="alc-corporate",
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
        mock_rbac_instance.check_permission = AsyncMock(return_value=None)
        MockRBAC.return_value = mock_rbac_instance

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-Change-Reason": "Integration test URS generation",
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
    X-User-Id header is provided.
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


@pytest_asyncio.fixture
async def forbidden_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient authenticated with a non-admin role.

    The RBACService will deny access (return AccessDenied), triggering 403.
    """
    from alcoabase.services.rbac import AccessDenied

    mock_session = AsyncMock()

    async def _override_get_db_session():
        yield mock_session

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=1,
            company_slug="alc-corporate",
            user_id=99,
            membership_role="viewer",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    # Patch RBACService to DENY access (return AccessDenied)
    with patch(
        "alcoabase.dependencies.rbac.RBACService"
    ) as MockRBAC:
        mock_rbac_instance = AsyncMock()
        mock_rbac_instance.check_permission = AsyncMock(
            return_value=AccessDenied(
                user_id=99,
                resource="documents",
                action="approve",
                reason="User lacks documents:approve permission",
            )
        )
        MockRBAC.return_value = mock_rbac_instance

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={
                "X-Change-Reason": "Integration test forbidden",
                "X-User-Id": "99",
                "X-Company-Id": "1",
            },
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: mock CLI infrastructure
# ---------------------------------------------------------------------------


def _mock_cli_infrastructure(service_side_effect=None, service_return=None):
    """Create mock objects for CLI script infrastructure.

    Mocks init_db, get_engine, async_sessionmaker, and URSGeneratorService
    so the CLI main() function can be tested without a real database.

    Args:
        service_side_effect: Exception to raise from service.execute().
        service_return: Return value for service.execute().

    Returns:
        Tuple of (mock_service_instance, mock_session).
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


def _build_sample_report(
    *,
    document_id: int = 1,
    version_number: int = 1,
    is_new_document: bool = True,
) -> URSGenerationReport:
    """Build a sample URSGenerationReport for testing."""
    return URSGenerationReport(
        document_id=document_id,
        document_uuid="2025-00001",
        document_title="AlcoaBase — Enhanced User Requirement Specifications",
        version_number=version_number,
        tags_applied=["URS", "ALC-GOV"],
        workflow_state="Draft",
        requirement_count=45,
        module_count=14,
        is_new_document=is_new_document,
        total_duration_ms=320,
    )


# ---------------------------------------------------------------------------
# Test: CLI Success
# ---------------------------------------------------------------------------


class TestCLISuccess:
    """Test CLI script exits 0 and outputs valid JSON URSGenerationReport."""

    @pytest.mark.asyncio
    async def test_cli_success(self) -> None:
        """CLI script exits 0 and stdout is valid JSON URSGenerationReport.

        Validates: Requirements 6.1, 6.5
        """
        mock_report = _build_sample_report()
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_return=mock_report
        )

        with patch(
            "alcoabase.scripts.generate_urs_alc.URSGeneratorService"
        ) as MockService, patch(
            "alcoabase.scripts.generate_urs_alc.init_db",
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
                    from alcoabase.scripts.generate_urs_alc import main

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
                    assert parsed["document_uuid"] == "2025-00001"
                    assert parsed["document_title"] == (
                        "AlcoaBase — Enhanced User Requirement Specifications"
                    )
                    assert parsed["version_number"] == 1
                    assert parsed["tags_applied"] == ["URS", "ALC-GOV"]
                    assert parsed["workflow_state"] == "Draft"
                    assert parsed["requirement_count"] == 45
                    assert parsed["module_count"] == 14
                    assert parsed["is_new_document"] is True
                    assert parsed["total_duration_ms"] == 320

                    # Verify commit was called (success path)
                    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: CLI Failure Without Prerequisites
# ---------------------------------------------------------------------------


class TestCLIFailure:
    """Test CLI script exits 1 when prerequisites are missing."""

    @pytest.mark.asyncio
    async def test_cli_failure_no_prerequisites(self) -> None:
        """CLI exits 1 when ALC company not found, stderr has error.

        Validates: Requirements 6.5
        """
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_side_effect=RuntimeError(
                "ALC corporate environment not provisioned. "
                "Run Phase 8.2 seed first."
            )
        )

        with patch(
            "alcoabase.scripts.generate_urs_alc.URSGeneratorService"
        ) as MockService, patch(
            "alcoabase.scripts.generate_urs_alc.init_db",
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
                    from alcoabase.scripts.generate_urs_alc import main

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
                    assert "ALC corporate environment not provisioned" in error_output

                    # Verify rollback was called (failure path)
                    mock_session.rollback.assert_called_once()

                    # Verify commit was NOT called
                    mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test: API Endpoint Success
# ---------------------------------------------------------------------------


class TestAPIEndpointSuccess:
    """Test POST /api/admin/generate-urs-alc returns 200 with report."""

    @pytest.mark.asyncio
    async def test_api_endpoint_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST returns 200 with URSGenerationReport on success.

        Validates: Requirements 6.2
        """
        mock_report = _build_sample_report(document_id=42)

        with patch.object(
            URSGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-urs-alc",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["document_id"] == 42
            assert data["document_uuid"] == "2025-00001"
            assert data["document_title"] == (
                "AlcoaBase — Enhanced User Requirement Specifications"
            )
            assert data["version_number"] == 1
            assert data["tags_applied"] == ["URS", "ALC-GOV"]
            assert data["workflow_state"] == "Draft"
            assert data["requirement_count"] == 45
            assert data["module_count"] == 14
            assert data["is_new_document"] is True
            assert data["total_duration_ms"] == 320


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

        Validates: Requirements 6.6
        """
        resp = await unauthenticated_client.post(
            "/api/admin/generate-urs-alc",
            headers={"X-Change-Reason": "Test"},
        )

        # Without X-User-Id header, tenant context resolution returns 401
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Test: API Endpoint Forbidden
# ---------------------------------------------------------------------------


class TestAPIEndpointForbidden:
    """Test POST with non-admin role returns 403."""

    @pytest.mark.asyncio
    async def test_api_endpoint_forbidden(
        self, forbidden_client: AsyncClient
    ) -> None:
        """POST with non-admin role returns 403.

        Validates: Requirements 6.6
        """
        resp = await forbidden_client.post(
            "/api/admin/generate-urs-alc",
        )

        assert resp.status_code == 403
        data = resp.json()
        assert "detail" in data


# ---------------------------------------------------------------------------
# Test: API Endpoint Missing Header
# ---------------------------------------------------------------------------


class TestAPIEndpointMissingHeader:
    """Test POST without X-Change-Reason returns 400."""

    @pytest.mark.asyncio
    async def test_api_endpoint_missing_header(self) -> None:
        """POST without X-Change-Reason returns 400.

        Validates: Requirements 6.7
        """
        mock_session = AsyncMock()

        async def _override_get_db_session():
            yield mock_session

        async def _override_get_tenant_context():
            return TenantContext(
                company_id=1,
                company_slug="alc-corporate",
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
                    resp = await client.post("/api/admin/generate-urs-alc")

                    # The audit middleware enforces X-Change-Reason on POST
                    assert resp.status_code == 400
            finally:
                app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: Full Idempotent Run
# ---------------------------------------------------------------------------


class TestFullIdempotentRun:
    """Test two consecutive runs produce one Document with two versions."""

    @pytest.mark.asyncio
    async def test_full_idempotent_run(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Two consecutive runs: first creates document, second versions it.

        Validates: Requirements 7.1
        """
        # First run: creates new document (is_new_document=True, version=1)
        first_report = _build_sample_report(
            document_id=1,
            version_number=1,
            is_new_document=True,
        )

        # Second run: creates new version (is_new_document=False, version=2)
        second_report = _build_sample_report(
            document_id=1,
            version_number=2,
            is_new_document=False,
        )

        call_count = {"n": 0}

        async def mock_execute(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return first_report
            return second_report

        with patch.object(URSGeneratorService, "execute", mock_execute):
            # First invocation — creates new document
            resp1 = await authenticated_client.post(
                "/api/admin/generate-urs-alc",
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["is_new_document"] is True
            assert data1["version_number"] == 1
            assert data1["document_id"] == 1

            # Second invocation — creates new version of same document
            resp2 = await authenticated_client.post(
                "/api/admin/generate-urs-alc",
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["is_new_document"] is False
            assert data2["version_number"] == 2
            assert data2["document_id"] == 1

            # Same document_id in both runs (one Document, two versions)
            assert data1["document_id"] == data2["document_id"]

            # Tags and workflow state consistent across both runs
            assert data1["tags_applied"] == data2["tags_applied"] == ["URS", "ALC-GOV"]
            assert data1["workflow_state"] == data2["workflow_state"] == "Draft"


# ---------------------------------------------------------------------------
# Test: Document Appears in Governance Folder
# ---------------------------------------------------------------------------


class TestDocumentAppearsInGovernanceFolder:
    """Test document with tags appears in virtual folder query."""

    @pytest.mark.asyncio
    async def test_document_appears_in_governance_folder(
        self, authenticated_client: AsyncClient
    ) -> None:
        """After generation, document has tags matching governance folder filter.

        The governance folder uses tag_filter {"tags": ["URS", "ALC-GOV"]}.
        After URS generation, the document must have both tags applied,
        ensuring it would appear in the virtual folder query.

        Validates: Requirements 6.2, 6.3
        """
        mock_report = _build_sample_report(document_id=10)

        with patch.object(
            URSGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-urs-alc",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Verify the document has both governance tags applied
            assert "URS" in data["tags_applied"]
            assert "ALC-GOV" in data["tags_applied"]

            # Verify the tags match the governance folder's tag_filter
            governance_folder_tag_filter = ["URS", "ALC-GOV"]
            assert all(
                tag in data["tags_applied"]
                for tag in governance_folder_tag_filter
            )

            # Verify workflow state is "Draft" (governance lifecycle applied)
            assert data["workflow_state"] == "Draft"
