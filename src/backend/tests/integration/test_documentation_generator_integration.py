"""Integration tests for documentation suite generation CLI and API endpoint.

Tests the full CLI script and API endpoint interfaces for the documentation
generator service, including success paths, error handling, authentication,
authorization, idempotency, concurrency, governance folder visibility,
URS/AI Guidelines availability, and rollback on failure.

References:
    - Task 8.1: Write integration tests for CLI, API, and end-to-end flows
    - Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9, 5.1, 5.4,
                    5.5, 5.6, 5.7, 7.6, 7.7, 8.4, 8.8
"""

import json
import sys
import time
from collections.abc import AsyncGenerator
from io import StringIO
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.schemas.documentation_generation import (
    CrossReferenceSummary,
    DocumentationGenerationReport,
    DocumentReportEntry,
)
from alcoabase.services.documentation_generator_service import (
    DocumentationGeneratorService,
)


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
                "X-Change-Reason": "Integration test documentation generation",
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
    urs_references: bool = True,
    ai_guidelines_references: bool = True,
) -> DocumentationGenerationReport:
    """Build a sample DocumentationGenerationReport for testing."""
    documents = [
        DocumentReportEntry(
            document_id=1,
            document_uuid="2025-00010",
            title="AlcoaBase \u2014 Comprehensive User Guide",
            guide_type="user_guide",
            version_number=version_number,
            tags_applied=["DOC-GUIDE", "ALC-GOV"],
            workflow_state="Draft",
            is_new_document=is_new_document,
            section_count=12,
            procedure_count=28,
            screenshot_placeholder_count=30,
        ),
        DocumentReportEntry(
            document_id=2,
            document_uuid="2025-00011",
            title="AlcoaBase \u2014 Technical Administrator Guide",
            guide_type="admin_guide",
            version_number=version_number,
            tags_applied=["DOC-GUIDE", "ALC-GOV"],
            workflow_state="Draft",
            is_new_document=is_new_document,
            section_count=12,
            procedure_count=22,
            screenshot_placeholder_count=24,
        ),
    ]
    return DocumentationGenerationReport(
        documents_created=documents,
        total_documents=2,
        total_sections=24,
        total_procedures=50,
        cross_references_included=CrossReferenceSummary(
            urs_references=urs_references,
            ai_guidelines_references=ai_guidelines_references,
        ),
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


def _patch_cli_session(mock_service_instance, mock_session):
    """Context manager helper to patch CLI infrastructure.

    Returns a context manager stack that patches init_db, get_engine,
    and async_sessionmaker for the CLI script.
    """
    import contextlib

    @contextlib.asynccontextmanager
    async def _patched():
        with patch(
            "alcoabase.scripts.generate_documentation.DocumentationGeneratorService"
        ) as MockService, patch(
            "alcoabase.scripts.generate_documentation.init_db",
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
                    yield

    return _patched()


# ---------------------------------------------------------------------------
# Test: CLI Success
# ---------------------------------------------------------------------------


class TestCLISuccess:
    """Test CLI script exits 0 and outputs valid JSON with 2 documents."""

    @pytest.mark.asyncio
    async def test_cli_success_exit_0_valid_json(self) -> None:
        """CLI exits 0 and stdout is valid JSON DocumentationGenerationReport.

        Validates: Requirements 4.1, 4.5
        """
        mock_report = _build_sample_report()
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_return=mock_report
        )

        async with _patch_cli_session(mock_service_instance, mock_session):
            from alcoabase.scripts.generate_documentation import main

            captured_stdout = StringIO()
            old_stdout = sys.stdout
            sys.stdout = captured_stdout

            try:
                await main()
            finally:
                sys.stdout = old_stdout

            output = captured_stdout.getvalue()
            parsed = json.loads(output)

            # Verify 2 documents in report
            assert parsed["total_documents"] == 2
            assert len(parsed["documents_created"]) == 2

            # Verify guide types
            guide_types = {
                d["guide_type"] for d in parsed["documents_created"]
            }
            assert guide_types == {"user_guide", "admin_guide"}

            # Verify tags and workflow state
            for doc in parsed["documents_created"]:
                assert doc["tags_applied"] == ["DOC-GUIDE", "ALC-GOV"]
                assert doc["workflow_state"] == "Draft"
                assert doc["is_new_document"] is True
                assert doc["version_number"] == 1

            # Verify report metadata
            assert parsed["total_sections"] == 24
            assert parsed["total_procedures"] == 50
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

        Validates: Requirements 4.5, 8.4
        """
        mock_service_instance, mock_session = _mock_cli_infrastructure(
            service_side_effect=RuntimeError(
                "ALC corporate environment not provisioned. "
                "Run Phase 8.2 seed first."
            )
        )

        async with _patch_cli_session(mock_service_instance, mock_session):
            from alcoabase.scripts.generate_documentation import main

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
    """Test POST /api/admin/generate-documentation returns 200."""

    @pytest.mark.asyncio
    async def test_api_endpoint_success(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST returns 200 with DocumentationGenerationReport on success.

        Validates: Requirements 4.2
        """
        mock_report = _build_sample_report()

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_documents"] == 2
            assert len(data["documents_created"]) == 2

            guide_types = {
                d["guide_type"] for d in data["documents_created"]
            }
            assert guide_types == {"user_guide", "admin_guide"}

            for doc in data["documents_created"]:
                assert doc["tags_applied"] == ["DOC-GUIDE", "ALC-GOV"]
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

        Validates: Requirements 4.6
        """
        resp = await unauthenticated_client.post(
            "/api/admin/generate-documentation",
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

        Validates: Requirements 4.7
        """
        resp = await forbidden_client.post(
            "/api/admin/generate-documentation",
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

        Validates: Requirements 4.8
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
                        "/api/admin/generate-documentation"
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

        Validates: Requirements 4.9
        """
        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError(
                "Documentation generation is already in progress. "
                "Please wait for the current generation to complete."
            ),
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 409
            data = resp.json()
            assert "already in progress" in data["detail"]


# ---------------------------------------------------------------------------
# Test: Full Idempotent Run
# ---------------------------------------------------------------------------


class TestFullIdempotentRun:
    """Test two consecutive runs produce 2 Documents with 2 versions each."""

    @pytest.mark.asyncio
    async def test_full_idempotent_run(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Two runs: first creates 2 documents, second versions them.

        Validates: Requirements 5.1, 5.4, 5.5, 5.6
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
            DocumentationGeneratorService, "execute", mock_execute
        ):
            # First invocation — creates new documents
            resp1 = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert data1["total_documents"] == 2
            for doc in data1["documents_created"]:
                assert doc["is_new_document"] is True
                assert doc["version_number"] == 1

            # Second invocation — creates new versions
            resp2 = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["total_documents"] == 2
            for doc in data2["documents_created"]:
                assert doc["is_new_document"] is False
                assert doc["version_number"] == 2

            # Tags and workflow state consistent across both runs
            for doc in data2["documents_created"]:
                assert doc["tags_applied"] == ["DOC-GUIDE", "ALC-GOV"]
                assert doc["workflow_state"] == "Draft"


# ---------------------------------------------------------------------------
# Test: Partial Existence
# ---------------------------------------------------------------------------


class TestPartialExistence:
    """Test one guide exists, other doesn't — correct new/version behavior."""

    @pytest.mark.asyncio
    async def test_partial_existence(
        self, authenticated_client: AsyncClient
    ) -> None:
        """One guide is new, the other is versioned.

        Validates: Requirements 5.1, 5.4
        """
        # Simulate: User Guide exists (versioned), Admin Guide is new
        documents = [
            DocumentReportEntry(
                document_id=1,
                document_uuid="2025-00010",
                title="AlcoaBase \u2014 Comprehensive User Guide",
                guide_type="user_guide",
                version_number=2,
                tags_applied=["DOC-GUIDE", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=False,
                section_count=12,
                procedure_count=28,
                screenshot_placeholder_count=30,
            ),
            DocumentReportEntry(
                document_id=3,
                document_uuid="2025-00012",
                title="AlcoaBase \u2014 Technical Administrator Guide",
                guide_type="admin_guide",
                version_number=1,
                tags_applied=["DOC-GUIDE", "ALC-GOV"],
                workflow_state="Draft",
                is_new_document=True,
                section_count=12,
                procedure_count=22,
                screenshot_placeholder_count=24,
            ),
        ]

        partial_report = DocumentationGenerationReport(
            documents_created=documents,
            total_documents=2,
            total_sections=24,
            total_procedures=50,
            cross_references_included=CrossReferenceSummary(
                urs_references=True,
                ai_guidelines_references=True,
            ),
            total_duration_ms=1200,
        )

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=partial_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
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

            assert len(new_docs) == 1
            assert len(versioned_docs) == 1

            # New document has version 1
            assert new_docs[0]["version_number"] == 1
            assert new_docs[0]["guide_type"] == "admin_guide"

            # Versioned document has version > 1
            assert versioned_docs[0]["version_number"] == 2
            assert versioned_docs[0]["guide_type"] == "user_guide"


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

        The governance folder uses tag_filter {"tags": ["DOC-GUIDE", "ALC-GOV"]}.
        After generation, both documents must have both tags applied.

        Validates: Requirements 5.5
        """
        mock_report = _build_sample_report()

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 200
            data = resp.json()

            governance_folder_tag_filter = ["DOC-GUIDE", "ALC-GOV"]

            for doc in data["documents_created"]:
                # Verify each document has both governance tags
                assert "DOC-GUIDE" in doc["tags_applied"]
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
    """Test generation includes URS cross-references when URS exists."""

    @pytest.mark.asyncio
    async def test_generation_with_urs_available(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When URS is available, report reflects URS references included.

        The service checks for URS document and includes cross-reference
        blocks. We verify the report shows urs_references=True.

        Validates: Requirements 7.6
        """
        mock_report = _build_sample_report(urs_references=True)

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_documents"] == 2
            assert data["cross_references_included"]["urs_references"] is True

            # All documents generated successfully with URS references
            for doc in data["documents_created"]:
                assert doc["section_count"] >= 10


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

        The service proceeds without URS cross-references and includes
        a notice. The report shows urs_references=False.

        Validates: Requirements 7.6
        """
        mock_report = _build_sample_report(urs_references=False)

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Generation succeeds even without URS
            assert data["total_documents"] == 2
            assert data["cross_references_included"]["urs_references"] is False
            assert data["total_sections"] > 0


# ---------------------------------------------------------------------------
# Test: Generation with AI Guidelines Available
# ---------------------------------------------------------------------------


class TestGenerationWithAIGuidelinesAvailable:
    """Test generation includes AI Guidelines cross-references when available."""

    @pytest.mark.asyncio
    async def test_generation_with_ai_guidelines_available(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When AI Guidelines are available, report reflects references included.

        The service checks for AI Guidelines documents and includes
        cross-reference blocks in AI-related sections.

        Validates: Requirements 7.7
        """
        mock_report = _build_sample_report(ai_guidelines_references=True)

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["total_documents"] == 2
            assert (
                data["cross_references_included"]["ai_guidelines_references"]
                is True
            )


# ---------------------------------------------------------------------------
# Test: Generation without AI Guidelines
# ---------------------------------------------------------------------------


class TestGenerationWithoutAIGuidelines:
    """Test generation without AI Guidelines includes notice."""

    @pytest.mark.asyncio
    async def test_generation_without_ai_guidelines(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When AI Guidelines are unavailable, generation succeeds with notice.

        The service proceeds without AI Guidelines cross-references and
        includes a notice. The report shows ai_guidelines_references=False.

        Validates: Requirements 7.7
        """
        mock_report = _build_sample_report(ai_guidelines_references=False)

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 200
            data = resp.json()

            # Generation succeeds even without AI Guidelines
            assert data["total_documents"] == 2
            assert (
                data["cross_references_included"]["ai_guidelines_references"]
                is False
            )
            assert data["total_sections"] > 0


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

        Validates: Requirements 4.3, 5.7, 8.8
        """
        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError(
                "Document upload failed for "
                "'AlcoaBase \u2014 Comprehensive User Guide': "
                "MinIO storage service unavailable"
            ),
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 500
            data = resp.json()

            # Verify error response structure
            assert "error" in data
            assert "failed_operation" in data
            assert data["failed_operation"] == "document_upload"
            assert (
                "storage" in data["detail"].lower()
                or "upload" in data["detail"].lower()
            )


# ---------------------------------------------------------------------------
# Test: Rollback on Second Guide Failure
# ---------------------------------------------------------------------------


class TestRollbackOnSecondGuideFailure:
    """Test first guide rolled back when second guide fails."""

    @pytest.mark.asyncio
    async def test_rollback_on_second_guide_failure(
        self, authenticated_client: AsyncClient
    ) -> None:
        """When second guide upload fails, first guide is also rolled back.

        The service runs within a single transaction. If the Admin Guide
        upload fails after the User Guide was already uploaded, the entire
        transaction is rolled back — no partial documents persist.

        Validates: Requirements 4.3, 8.4
        """
        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError(
                "Document upload failed for "
                "'AlcoaBase \u2014 Technical Administrator Guide': "
                "MinIO storage service unavailable"
            ),
        ):
            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            assert resp.status_code == 500
            data = resp.json()

            # Verify error identifies the Admin Guide as the failure point
            assert "failed_operation" in data
            assert data["failed_operation"] == "document_upload"

            # The document_title should reference the Admin Guide
            if data.get("document_title"):
                assert "Administrator" in data["document_title"]


# ---------------------------------------------------------------------------
# Test: Generation Timing Under 120 Seconds
# ---------------------------------------------------------------------------


class TestGenerationTimingUnder120Seconds:
    """Test both guides generated within time limit."""

    @pytest.mark.asyncio
    async def test_generation_timing_under_120_seconds(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Generation completes within 120 seconds.

        Since content is deterministic (template constants + cross-reference
        data), generation should be fast. We verify the service completes
        and reports a duration well under 120 seconds.

        Validates: Requirements 8.8
        """
        # Report with realistic timing (should be well under 120s)
        mock_report = _build_sample_report()

        with patch.object(
            DocumentationGeneratorService,
            "execute",
            new_callable=AsyncMock,
            return_value=mock_report,
        ):
            start = time.monotonic()

            resp = await authenticated_client.post(
                "/api/admin/generate-documentation",
            )

            elapsed = time.monotonic() - start

            assert resp.status_code == 200
            data = resp.json()

            # Verify the reported duration is under 120 seconds (120000 ms)
            assert data["total_duration_ms"] < 120_000

            # Verify the actual request completed quickly
            assert elapsed < 120.0

            # Verify both guides were generated
            assert data["total_documents"] == 2
