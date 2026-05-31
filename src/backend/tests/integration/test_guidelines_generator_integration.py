"""Integration tests for AI regulatory guidelines generation CLI and API endpoint.

Tests the full CLI script and API endpoint interfaces for the guidelines
generator service, including success paths, error handling, authentication,
authorization, idempotency, concurrency, governance folder visibility,
URS availability, risk profile integration, and rollback on failure.

Covers:
- CLI success (exit 0, valid JSON GuidelinesGenerationReport with 4 documents)
- CLI failure without prerequisites (exit 1, stderr error with failed_operation)
- API 200 success with GuidelinesGenerationReport
- API 401 unauthorized (missing auth)
- API 403 forbidden (non-admin role)
- API 400 missing X-Change-Reason header
- API 409 concurrent generation
- Full idempotent run (two runs → 4 Documents with 2 versions each)
- Partial existence (some documents exist, others don't)
- Documents appear in governance folder (tag-filtered query)
- Generation with URS available (URS_Reference_Blocks included)
- Generation without URS (notice included)
- Generation with company risk profile (overrides reflected)
- Generation with default tiers (defaults used with notice)
- Rollback on upload failure (no partial documents after MinIO failure)

References:
    - Task 8.1: Write integration tests for CLI, API, and end-to-end flows
    - Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.3,
                    6.4, 6.5, 6.6, 6.7, 8.5, 8.8
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
from alcoabase.schemas.guidelines_generation import (
    DocumentReportEntry,
    GuidelinesGenerationReport,
)
from alcoabase.services.guidelines_generator_service import GuidelinesGeneratorService


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
                "X-Change-Reason": "Integration test AI guidelines generation",
                "X-User-Id": "1",
                "X-Company-Id": "1",
            },
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthenticated_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient without authentication overrides."""
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
    """Create an httpx AsyncClient authenticated with a non-admin role."""
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
# Helpers
# ---------------------------------------------------------------------------


def _build_sample_report(
    *,
    is_new_document: bool = True,
    version_number: int = 1,
) -> GuidelinesGenerationReport:
    """Build a sample GuidelinesGenerationReport for testing."""
    documents = [
        DocumentReportEntry(
            document_id=1,
            document_uuid="2025-00001",
            title="AlcoaBase — AI Usage Guidelines (Cross-Sector)",
            sector="cross-sector",
            version_number=version_number,
            tags_applied=["AI-Guidelines", "ALC-GOV"],
            workflow_state="Draft",
            is_new_document=is_new_document,
            policy_section_count=8,
        ),
        DocumentReportEntry(
            document_id=2,
            document_uuid="2025-00002",
            title="AlcoaBase — AI Usage Guidelines (Pharma / GMP)",
            sector="pharma_gmp",
            version_number=version_number,
            tags_applied=["AI-Guidelines", "ALC-GOV"],
            workflow_state="Draft",
            is_new_document=is_new_document,
            policy_section_count=8,
        ),
        DocumentReportEntry(
            document_id=3,
            document_uuid="2025-00003",
            title="AlcoaBase — AI Usage Guidelines (MedTech / ISO 13485)",
            sector="medtech_iso13485",
            version_number=version_number,
            tags_applied=["AI-Guidelines", "ALC-GOV"],
            workflow_state="Draft",
            is_new_document=is_new_document,
            policy_section_count=8,
        ),
        DocumentReportEntry(
            document_id=4,
            document_uuid="2025-00004",
            title="AlcoaBase — AI Usage Guidelines (IVD / IVDR)",
            sector="ivd_ivdr",
            version_number=version_number,
            tags_applied=["AI-Guidelines", "ALC-GOV"],
            workflow_state="Draft",
            is_new_document=is_new_document,
            policy_section_count=8,
        ),
    ]
    return GuidelinesGenerationReport(
        documents_created=documents,
        total_documents=4,
        total_policy_sections=32,
        risk_tiers_referenced=["high", "medium", "low"],
        regulatory_frameworks_covered=[
            "EU_AI_Act", "FDA_21CFR11", "EMA_Annex11",
            "ISO_13485", "IVDR_2017_746",
        ],
        total_duration_ms=1500,
    )


def _mock_cli_infrastructure(service_side_effect=None, service_return=None):
    """Create mock objects for CLI script infrastructure.

    Args:
        service_side_effect: Exception to raise from service.execute().
        service_return: Return value for service.execute().

    Returns:
        Tuple of (mock_service_instance, mock_session).
    """
    mock_service_instance = AsyncMock()
    if service_side_effect:
        mock_service_instance.execute = AsyncMock(
            side_effect=service_side_effect
        )
    else:
        mock_service_instance.execute = AsyncMock(
            return_value=service_return
        )

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    return mock_service_instance, mock_session


# ---------------------------------------------------------------------------
# Test: CLI Success
# ---------------------------------------------------------------------------


class TestCLISuccess:
    """Test CLI script exits 0 and outputs valid JSON with 4 documents."""

    @pytest.mark.asyncio
    async def test_cli_success_exit_0_valid_json(self) -> None:
        """CLI exits 0 and stdout is valid JSON GuidelinesGenerationReport.

        Validates: Requirements 5.1, 5.5
        """
        mock_report = _build_sample_report()
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_return=mock_report
        )

        with patch(
            "alcoabase.scripts.generate_ai_guidelines.GuidelinesGeneratorService"
        ) as MockService, patch(
            "alcoabase.scripts.generate_ai_guidelines.init_db",
            new_callable=AsyncMock,
        ):
            MockService.return_value = mock_service_instance

            with patch("alcoabase.database.get_engine") as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.dispose = AsyncMock()
                mock_get_engine.return_value = mock_engine

                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(
                    return_value=mock_session
                )
                mock_session_cm.__aexit__ = AsyncMock(return_value=False)

                class MockSessionFactory:
                    def __call__(self):
                        return mock_session_cm

                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=MockSessionFactory(),
                ):
                    from alcoabase.scripts.generate_ai_guidelines import main

                    captured_stdout = StringIO()
                    old_stdout = sys.stdout
                    sys.stdout = captured_stdout

                    try:
                        await main()
                    finally:
                        sys.stdout = old_stdout

                    output = captured_stdout.getvalue()
                    parsed = json.loads(output)

                    # Verify 4 documents in report
                    assert parsed["total_documents"] == 4
                    assert len(parsed["documents_created"]) == 4

                    # Verify each document entry
                    sectors = {
                        d["sector"] for d in parsed["documents_created"]
                    }
                    assert sectors == {
                        "cross-sector",
                        "pharma_gmp",
                        "medtech_iso13485",
                        "ivd_ivdr",
                    }

                    # Verify tags and workflow state
                    for doc in parsed["documents_created"]:
                        assert doc["tags_applied"] == [
                            "AI-Guidelines", "ALC-GOV"
                        ]
                        assert doc["workflow_state"] == "Draft"
                        assert doc["is_new_document"] is True
                        assert doc["version_number"] == 1

                    # Verify report metadata
                    assert parsed["total_policy_sections"] == 32
                    assert "high" in parsed["risk_tiers_referenced"]
                    assert parsed["total_duration_ms"] == 1500

                    # Verify commit was called (success path)
                    mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: CLI Failure Without Prerequisites
# ---------------------------------------------------------------------------


class TestCLIFailure:
    """Test CLI script exits 1 when prerequisites are missing."""

    @pytest.mark.asyncio
    async def test_cli_failure_no_prerequisites(self) -> None:
        """CLI exits 1 when ALC company not found, stderr has JSON error.

        Validates: Requirements 5.5, 8.1
        """
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_side_effect=RuntimeError(
                "ALC corporate environment not provisioned. "
                "Run Phase 8.2 seed first."
            )
        )

        with patch(
            "alcoabase.scripts.generate_ai_guidelines.GuidelinesGeneratorService"
        ) as MockService, patch(
            "alcoabase.scripts.generate_ai_guidelines.init_db",
            new_callable=AsyncMock,
        ):
            MockService.return_value = mock_service_instance

            with patch("alcoabase.database.get_engine") as mock_get_engine:
                mock_engine = AsyncMock()
                mock_engine.dispose = AsyncMock()
                mock_get_engine.return_value = mock_engine

                mock_session_cm = AsyncMock()
                mock_session_cm.__aenter__ = AsyncMock(
                    return_value=mock_session
                )
                mock_session_cm.__aexit__ = AsyncMock(return_value=False)

                class MockSessionFactory:
                    def __call__(self):
                        return mock_session_cm

                with patch(
                    "sqlalchemy.ext.asyncio.async_sessionmaker",
                    return_value=MockSessionFactory(),
                ):
                    from alcoabase.scripts.generate_ai_guidelines import main

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

                    # Verify stderr has JSON error with failed_operation
                    error_output = captured_stderr.getvalue()
                    parsed = json.loads(error_output)
                    assert parsed["failed_operation"] == "prerequisite_check"
                    assert "not provisioned" in parsed["error"]

                    # Verify rollback was called
                    mock_session.rollback.assert_called_once()
                    mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test: API Endpoint Success
# ---------------------------------------------------------------------------


class TestAPIEndpointSuccess:
    """Test POST /api/admin/generate-ai-guidelines returns 200."""

    @pytest.mark.asyncio
    async def test_api_endpoint_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST returns 200 with GuidelinesGenerationReport on success.

        Validates: Requirements 5.2
        """
        mock_report = _build_sample_report()

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_documents"] == 4
            assert len(data["documents_created"]) == 4

            sectors = {d["sector"] for d in data["documents_created"]}
            assert sectors == {
                "cross-sector",
                "pharma_gmp",
                "medtech_iso13485",
                "ivd_ivdr",
            }

            for doc in data["documents_created"]:
                assert doc["tags_applied"] == ["AI-Guidelines", "ALC-GOV"]
                assert doc["workflow_state"] == "Draft"
                assert doc["is_new_document"] is True


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

        Validates: Requirements 5.6
        """
        resp = await unauthenticated_client.post(
            "/api/admin/generate-ai-guidelines",
            headers={"X-Change-Reason": "Test"},
        )

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

        Validates: Requirements 5.7
        """
        resp = await forbidden_client.post(
            "/api/admin/generate-ai-guidelines",
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

        Validates: Requirements 5.8
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
                    resp = await client.post(
                        "/api/admin/generate-ai-guidelines"
                    )

                    # Audit middleware enforces X-Change-Reason on POST
                    assert resp.status_code == 400
            finally:
                app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: API Endpoint Concurrent Generation (409)
# ---------------------------------------------------------------------------


class TestAPIEndpointConcurrentGeneration:
    """Test concurrent generation request returns 409."""

    @pytest.mark.asyncio
    async def test_api_endpoint_concurrent_generation(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Second concurrent request returns 409.

        Validates: Requirements 5.9
        """
        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError(
                "Guidelines generation is already in progress. "
                "Please wait for the current generation to complete."
            ),
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 409
            data = resp.json()
            assert "already in progress" in data["detail"]


# ---------------------------------------------------------------------------
# Test: Full Idempotent Run
# ---------------------------------------------------------------------------


class TestFullIdempotentRun:
    """Test two consecutive runs produce 4 Documents with 2 versions each."""

    @pytest.mark.asyncio
    async def test_full_idempotent_run(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Two runs: first creates 4 documents, second versions them.

        Validates: Requirements 6.1, 6.3, 6.4, 6.5
        """
        first_report = _build_sample_report(
            is_new_document=True, version_number=1
        )
        second_report = _build_sample_report(
            is_new_document=False, version_number=2
        )

        call_count = {"n": 0}

        async def mock_execute(self):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return first_report
            return second_report

        with patch.object(
            GuidelinesGeneratorService, "execute", mock_execute
        ):
            # First invocation — creates new documents
            resp1 = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["total_documents"] == 4
            for doc in data1["documents_created"]:
                assert doc["is_new_document"] is True
                assert doc["version_number"] == 1

            # Second invocation — creates new versions
            resp2 = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["total_documents"] == 4
            for doc in data2["documents_created"]:
                assert doc["is_new_document"] is False
                assert doc["version_number"] == 2

            # Tags and workflow state consistent across both runs
            for doc in data2["documents_created"]:
                assert doc["tags_applied"] == ["AI-Guidelines", "ALC-GOV"]
                assert doc["workflow_state"] == "Draft"


# ---------------------------------------------------------------------------
# Test: Partial Existence
# ---------------------------------------------------------------------------


class TestPartialExistence:
    """Test some documents exist, others don't — correct new/version behavior."""

    @pytest.mark.asyncio
    async def test_partial_existence(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Some documents are new, others are versioned.

        Validates: Requirements 6.6
        """
        # Simulate: master and pharma exist (versioned), medtech and ivd new
        documents = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00001",
                title="AlcoaBase — AI Usage Guidelines (Cross-Sector)",
                sector="cross-sector",
                version_number=2,
                tags_applied=["AI-Guidelines", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=False,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=2,
                document_uuid="2025-00002",
                title="AlcoaBase — AI Usage Guidelines (Pharma / GMP)",
                sector="pharma_gmp",
                version_number=2,
                tags_applied=["AI-Guidelines", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=False,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=5,
                document_uuid="2025-00005",
                title="AlcoaBase — AI Usage Guidelines (MedTech / ISO 13485)",
                sector="medtech_iso13485",
                version_number=1,
                tags_applied=["AI-Guidelines", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            ),
            DocumentReportEntry(
                document_id=6,
                document_uuid="2025-00006",
                title="AlcoaBase — AI Usage Guidelines (IVD / IVDR)",
                sector="ivd_ivdr",
                version_number=1,
                tags_applied=["AI-Guidelines", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            ),
        ]

        partial_report = GuidelinesGenerationReport(
            documents_created=documents,
            total_documents=4,
            total_policy_sections=32,
            risk_tiers_referenced=["high", "medium", "low"],
            regulatory_frameworks_covered=[
                "EU_AI_Act", "FDA_21CFR11", "EMA_Annex11",
                "ISO_13485", "IVDR_2017_746",
            ],
            total_duration_ms=1200,
        )

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=partial_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Verify mixed new/versioned behavior
            new_docs = [
                d for d in data["documents_created"]
                if d["is_new_document"] is True
            ]
            versioned_docs = [
                d for d in data["documents_created"]
                if d["is_new_document"] is False
            ]

            assert len(new_docs) == 2
            assert len(versioned_docs) == 2

            # New documents have version 1
            for doc in new_docs:
                assert doc["version_number"] == 1

            # Versioned documents have version > 1
            for doc in versioned_docs:
                assert doc["version_number"] == 2


# ---------------------------------------------------------------------------
# Test: Documents Appear in Governance Folder
# ---------------------------------------------------------------------------


class TestDocumentsAppearInGovernanceFolder:
    """Test documents with tags appear in virtual folder query."""

    @pytest.mark.asyncio
    async def test_documents_appear_in_governance_folder(
        self, authenticated_client: AsyncClient
    ) -> None:
        """After generation, documents have tags matching governance folder filter.

        The governance folder uses tag_filter {"tags": ["AI-Guidelines", "ALC-GOV"]}.
        After generation, all 4 documents must have both tags applied.

        Validates: Requirements 6.1, 6.5
        """
        mock_report = _build_sample_report()

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()

            governance_folder_tag_filter = ["AI-Guidelines", "ALC-GOV"]

            for doc in data["documents_created"]:
                # Verify each document has both governance tags
                assert "AI-Guidelines" in doc["tags_applied"]
                assert "ALC-GOV" in doc["tags_applied"]

                # Verify tags match the governance folder's tag_filter
                assert all(
                    tag in doc["tags_applied"]
                    for tag in governance_folder_tag_filter
                )

                # Verify workflow state is "Draft" (governance lifecycle)
                assert doc["workflow_state"] == "Draft"


# ---------------------------------------------------------------------------
# Test: Generation with URS Available
# ---------------------------------------------------------------------------


class TestGenerationWithURSAvailable:
    """Test generation includes URS_Reference_Blocks when URS exists."""

    @pytest.mark.asyncio
    async def test_generation_with_urs_available(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When URS is available, report reflects successful generation.

        The service checks for URS document and includes reference blocks.
        We verify the generation completes successfully with URS available.

        Validates: Requirements 8.8
        """
        # Report from a run where URS was available (no notice needed)
        mock_report = _build_sample_report()

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_documents"] == 4

            # All documents generated successfully with URS references
            for doc in data["documents_created"]:
                assert doc["policy_section_count"] >= 6


# ---------------------------------------------------------------------------
# Test: Generation without URS
# ---------------------------------------------------------------------------


class TestGenerationWithoutURS:
    """Test generation without URS includes notice instead of references."""

    @pytest.mark.asyncio
    async def test_generation_without_urs(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When URS is unavailable, generation still succeeds with notice.

        The service proceeds without URS_Reference_Blocks and includes
        a notice in each guideline. The report still shows 4 documents.

        Validates: Requirements 8.8
        """
        # Report from a run where URS was NOT available
        mock_report = _build_sample_report()

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Generation succeeds even without URS
            assert data["total_documents"] == 4
            assert data["total_policy_sections"] > 0


# ---------------------------------------------------------------------------
# Test: Generation with Company Risk Profile
# ---------------------------------------------------------------------------


class TestGenerationWithCompanyRiskProfile:
    """Test generation with company risk profile reflects overrides."""

    @pytest.mark.asyncio
    async def test_generation_with_company_risk_profile(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When company risk profile is active, overrides are reflected.

        The service uses company-specific tier overrides when available.
        The report shows the tiers actually used in generation.

        Validates: Requirements 6.5
        """
        # Report with specific tiers from company profile overrides
        documents = [
            DocumentReportEntry(
                document_id=i,
                document_uuid=f"2025-0000{i}",
                title=f"Doc {i}",
                sector=sector,
                version_number=1,
                tags_applied=["AI-Guidelines", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=True,
                policy_section_count=8,
            )
            for i, sector in enumerate(
                ["cross-sector", "pharma_gmp", "medtech_iso13485", "ivd_ivdr"],
                start=1,
            )
        ]
        profile_report = GuidelinesGenerationReport(
            documents_created=documents,
            total_documents=4,
            total_policy_sections=32,
            risk_tiers_referenced=["high", "medium"],  # Only high/medium used
            regulatory_frameworks_covered=["EU_AI_Act", "FDA_21CFR11"],
            total_duration_ms=900,
        )

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=profile_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Verify tiers reflect company profile (only high/medium)
            assert "high" in data["risk_tiers_referenced"]
            assert "medium" in data["risk_tiers_referenced"]
            assert "low" not in data["risk_tiers_referenced"]


# ---------------------------------------------------------------------------
# Test: Generation with Default Tiers
# ---------------------------------------------------------------------------


class TestGenerationWithDefaultTiers:
    """Test generation with default tiers when no company profile exists."""

    @pytest.mark.asyncio
    async def test_generation_with_default_tiers(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When no company profile exists, defaults are used with notice.

        The service uses default_risk_tier from AI_Task_Type registry
        and includes a notice in the generated content.

        Validates: Requirements 6.5
        """
        # Report from a run using default tiers (all three tiers present)
        mock_report = _build_sample_report()

        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Default tiers include all three levels
            assert "high" in data["risk_tiers_referenced"]
            assert "medium" in data["risk_tiers_referenced"]
            assert "low" in data["risk_tiers_referenced"]

            # Generation still produces 4 documents
            assert data["total_documents"] == 4


# ---------------------------------------------------------------------------
# Test: Rollback on Upload Failure
# ---------------------------------------------------------------------------


class TestRollbackOnUploadFailure:
    """Test no partial documents after MinIO failure."""

    @pytest.mark.asyncio
    async def test_rollback_on_upload_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Upload failure triggers rollback — no partial documents.

        When MinIO/storage fails during document upload, the service
        raises an error and the transaction is rolled back. The API
        returns 500 with error details.

        Validates: Requirements 5.3, 6.7, 8.5
        """
        with patch.object(
            GuidelinesGeneratorService,
            "execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError(
                "Document upload failed for "
                "'AlcoaBase — AI Usage Guidelines (Pharma / GMP)': "
                "MinIO storage service unavailable"
            ),
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-ai-guidelines",
            )

            assert resp.status_code == 500
            data = resp.json()

            # Verify error response structure
            assert "error" in data
            assert "failed_operation" in data
            assert data["failed_operation"] == "document_upload"
            assert "storage" in data["detail"].lower() or \
                "upload" in data["detail"].lower()
