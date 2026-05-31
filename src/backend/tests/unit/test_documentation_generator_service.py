"""Unit tests for DocumentationGeneratorService — prerequisites, cross-references, and advisory lock.

Tests cover:
- Task 7.1: validate_prerequisites (all present, missing company, missing doc-admin,
  missing workflow, check order), load_cross_reference_data (URS available/unavailable,
  AI Guidelines available/unavailable), advisory_lock (acquired, concurrent rejection).

References:
    - Requirements: 1.9, 1.10, 3.6, 3.7, 3.8, 7.6, 7.7, 8.1, 8.2, 8.3, 8.7
    - Design: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
"""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag
from alcoabase.models.user import User
from alcoabase.models.workflow import WorkflowDefinition
from alcoabase.services.documentation_generator_service import (
    DocumentationGeneratorService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_scalar_one_or_none(value):
    """Create a mock result that returns value from result.scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


def _mock_scalar(value):
    """Create a mock result that returns value from result.scalar()."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = value
    return mock_result


def _mock_scalars_unique_all(items: list):
    """Create a mock result that returns items from result.scalars().unique().all()."""
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_unique = MagicMock()
    mock_unique.all.return_value = items
    mock_scalars.unique.return_value = mock_unique
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_company(id_: int = 1) -> MagicMock:
    """Create a Company mock matching ALC corporate."""
    company = MagicMock(spec=Company)
    company.id = id_
    company.slug = "alc-corporate"
    return company


def _make_doc_admin(id_: int = 10) -> MagicMock:
    """Create a User mock for the doc-admin."""
    user = MagicMock(spec=User)
    user.id = id_
    user.username = "alc-doc-admin"
    return user


def _make_workflow(id_: int = 5, company_id: int = 1) -> MagicMock:
    """Create a WorkflowDefinition mock for the governance workflow."""
    workflow = MagicMock(spec=WorkflowDefinition)
    workflow.id = id_
    workflow.name = "ALC Governance Document Lifecycle"
    workflow.document_tag = "ALC-GOV"
    workflow.company_id = company_id
    return workflow


def _make_document(
    id_: int = 100,
    title: str = "Test Document",
    uuid: str = "2025-00042",
    company_id: int = 1,
    current_status: str = "Draft",
) -> MagicMock:
    """Create a Document mock for testing."""
    doc = MagicMock(spec=Document)
    doc.id = id_
    doc.document_uuid = uuid
    doc.title = title
    doc.company_id = company_id
    doc.current_status = current_status
    return doc


def _make_service(session: AsyncMock | None = None) -> DocumentationGeneratorService:
    """Create a DocumentationGeneratorService with a mock session."""
    if session is None:
        session = AsyncMock()
    return DocumentationGeneratorService(session=session)


# ---------------------------------------------------------------------------
# Task 7.1: validate_prerequisites Tests
# ---------------------------------------------------------------------------


class TestValidatePrerequisitesAllPresent:
    """Test: validate_prerequisites with all present returns company, user, workflow.

    Validates: Requirements 3.6, 3.7, 3.8, 8.1, 8.2, 8.3
    """

    @pytest.mark.asyncio
    async def test_returns_company_user_workflow(self, async_session: AsyncMock):
        """Returns (company, doc_admin, workflow) when all prerequisites exist."""
        company = _make_company()
        doc_admin = _make_doc_admin()
        workflow = _make_workflow(company_id=company.id)

        # Mock session.execute to return each prerequisite in order
        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),
                _mock_scalar_one_or_none(doc_admin),
                _mock_scalar_one_or_none(workflow),
            ]
        )

        service = _make_service(async_session)
        result = await service._validate_prerequisites()

        assert result == (company, doc_admin, workflow)
        assert result[0].slug == "alc-corporate"
        assert result[1].username == "alc-doc-admin"
        assert result[2].document_tag == "ALC-GOV"


class TestValidatePrerequisitesNoCompany:
    """Test: validate_prerequisites no company raises RuntimeError with correct message.

    Validates: Requirements 8.1, 8.7
    """

    @pytest.mark.asyncio
    async def test_raises_runtime_error_no_company(self, async_session: AsyncMock):
        """Raises RuntimeError when ALC company is not found."""
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError) as exc_info:
            await service._validate_prerequisites()

        assert "ALC corporate environment not provisioned" in str(exc_info.value)
        assert "Run Phase 8.2 seed first" in str(exc_info.value)


class TestValidatePrerequisitesNoDocAdmin:
    """Test: validate_prerequisites no doc-admin raises RuntimeError with correct message.

    Validates: Requirements 8.2, 8.7
    """

    @pytest.mark.asyncio
    async def test_raises_runtime_error_no_doc_admin(self, async_session: AsyncMock):
        """Raises RuntimeError when doc-admin user is not found."""
        company = _make_company()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),  # company found
                _mock_scalar_one_or_none(None),  # doc-admin not found
            ]
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError) as exc_info:
            await service._validate_prerequisites()

        assert "ALC Document Administrator user not found" in str(exc_info.value)
        assert "Run Phase 8.2 seed first" in str(exc_info.value)


class TestValidatePrerequisitesNoWorkflow:
    """Test: validate_prerequisites no workflow raises RuntimeError with correct message.

    Validates: Requirements 8.3, 8.7
    """

    @pytest.mark.asyncio
    async def test_raises_runtime_error_no_workflow(self, async_session: AsyncMock):
        """Raises RuntimeError when governance workflow is not found."""
        company = _make_company()
        doc_admin = _make_doc_admin()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),  # company found
                _mock_scalar_one_or_none(doc_admin),  # doc-admin found
                _mock_scalar_one_or_none(None),  # workflow not found
            ]
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError) as exc_info:
            await service._validate_prerequisites()

        assert "ALC Governance workflow not found" in str(exc_info.value)
        assert "Run Phase 8.2 seed first" in str(exc_info.value)


class TestValidatePrerequisitesCheckOrder:
    """Test: validate_prerequisites check order (company before doc-admin before workflow).

    Validates: Requirements 8.7
    """

    @pytest.mark.asyncio
    async def test_halts_on_first_failure_company(self, async_session: AsyncMock):
        """Halts at company check — never queries doc-admin or workflow."""
        async_session.execute = AsyncMock(
            return_value=_mock_scalar_one_or_none(None)
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError, match="ALC corporate environment"):
            await service._validate_prerequisites()

        # Only one query executed (company check)
        assert async_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_halts_on_second_failure_doc_admin(self, async_session: AsyncMock):
        """Halts at doc-admin check — never queries workflow."""
        company = _make_company()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),  # company found
                _mock_scalar_one_or_none(None),  # doc-admin not found
            ]
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError, match="ALC Document Administrator"):
            await service._validate_prerequisites()

        # Two queries executed (company + doc-admin)
        assert async_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_halts_on_third_failure_workflow(self, async_session: AsyncMock):
        """Halts at workflow check after company and doc-admin succeed."""
        company = _make_company()
        doc_admin = _make_doc_admin()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(company),  # company found
                _mock_scalar_one_or_none(doc_admin),  # doc-admin found
                _mock_scalar_one_or_none(None),  # workflow not found
            ]
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError, match="ALC Governance workflow"):
            await service._validate_prerequisites()

        # Three queries executed (company + doc-admin + workflow)
        assert async_session.execute.call_count == 3


# ---------------------------------------------------------------------------
# Task 7.1: load_cross_reference_data Tests
# ---------------------------------------------------------------------------


class TestLoadCrossReferencesURSAvailable:
    """Test: load_cross_references with URS available (urs_available=True, metadata populated).

    Validates: Requirements 1.9, 7.6
    """

    @pytest.mark.asyncio
    async def test_urs_available_populates_metadata(self, async_session: AsyncMock):
        """When URS document exists, urs_available=True and metadata is populated."""
        company = _make_company()
        urs_doc = _make_document(
            id_=200,
            title="AlcoaBase — Enhanced User Requirements Specification",
            uuid="2025-00010",
            company_id=company.id,
            current_status="Approved",
        )

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(urs_doc),  # URS query
                _mock_scalars_unique_all([]),  # AI Guidelines query (empty)
                _mock_scalars_unique_all([urs_doc]),  # All ALC-GOV docs
            ]
        )

        service = _make_service(async_session)
        result = await service._load_cross_reference_data(company)

        assert result.urs_available is True
        assert result.urs_document_uuid == "2025-00010"
        assert result.urs_document_title == "AlcoaBase — Enhanced User Requirements Specification"


class TestLoadCrossReferencesURSUnavailable:
    """Test: load_cross_references with URS unavailable (urs_available=False).

    Validates: Requirements 1.10, 7.7
    """

    @pytest.mark.asyncio
    async def test_urs_unavailable_sets_false(self, async_session: AsyncMock):
        """When URS document does not exist, urs_available=False and metadata is None."""
        company = _make_company()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(None),  # URS query (not found)
                _mock_scalars_unique_all([]),  # AI Guidelines query (empty)
                _mock_scalars_unique_all([]),  # All ALC-GOV docs (empty)
            ]
        )

        service = _make_service(async_session)
        result = await service._load_cross_reference_data(company)

        assert result.urs_available is False
        assert result.urs_document_uuid is None
        assert result.urs_document_title is None


class TestLoadCrossReferencesAIGuidelinesAvailable:
    """Test: load_cross_references with AI Guidelines available (ai_guidelines_available=True).

    Validates: Requirements 1.9, 7.6
    """

    @pytest.mark.asyncio
    async def test_ai_guidelines_available_populates_list(self, async_session: AsyncMock):
        """When AI Guidelines documents exist, ai_guidelines_available=True and list populated."""
        company = _make_company()
        ai_doc_1 = _make_document(
            id_=300,
            title="AlcoaBase — AI Usage Guidelines (Cross-Sector)",
            uuid="2025-00020",
            company_id=company.id,
            current_status="Draft",
        )
        ai_doc_2 = _make_document(
            id_=301,
            title="AlcoaBase — AI Usage Guidelines (Pharma/GMP)",
            uuid="2025-00021",
            company_id=company.id,
            current_status="Draft",
        )

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(None),  # URS query (not found)
                _mock_scalars_unique_all([ai_doc_1, ai_doc_2]),  # AI Guidelines
                _mock_scalars_unique_all([ai_doc_1, ai_doc_2]),  # All ALC-GOV docs
            ]
        )

        service = _make_service(async_session)
        result = await service._load_cross_reference_data(company)

        assert result.ai_guidelines_available is True
        assert len(result.ai_guidelines_documents) == 2
        assert result.ai_guidelines_documents[0]["title"] == "AlcoaBase — AI Usage Guidelines (Cross-Sector)"
        assert result.ai_guidelines_documents[0]["uuid"] == "2025-00020"
        assert result.ai_guidelines_documents[1]["title"] == "AlcoaBase — AI Usage Guidelines (Pharma/GMP)"
        assert result.ai_guidelines_documents[1]["uuid"] == "2025-00021"


class TestLoadCrossReferencesAIGuidelinesUnavailable:
    """Test: load_cross_references with AI Guidelines unavailable (ai_guidelines_available=False).

    Validates: Requirements 1.10, 7.7
    """

    @pytest.mark.asyncio
    async def test_ai_guidelines_unavailable_sets_false(self, async_session: AsyncMock):
        """When no AI Guidelines documents exist, ai_guidelines_available=False."""
        company = _make_company()

        async_session.execute = AsyncMock(
            side_effect=[
                _mock_scalar_one_or_none(None),  # URS query (not found)
                _mock_scalars_unique_all([]),  # AI Guidelines (empty)
                _mock_scalars_unique_all([]),  # All ALC-GOV docs (empty)
            ]
        )

        service = _make_service(async_session)
        result = await service._load_cross_reference_data(company)

        assert result.ai_guidelines_available is False
        assert result.ai_guidelines_documents == []


# ---------------------------------------------------------------------------
# Task 7.1: advisory_lock Tests
# ---------------------------------------------------------------------------


class TestAdvisoryLockAcquiredSuccessfully:
    """Test: advisory_lock acquired successfully on first call.

    Validates: Requirements 3.6
    """

    @pytest.mark.asyncio
    async def test_lock_acquired_no_error(self, async_session: AsyncMock):
        """Advisory lock is acquired successfully when no other session holds it."""
        async_session.execute = AsyncMock(
            return_value=_mock_scalar(True)
        )

        service = _make_service(async_session)

        # Should not raise
        await service._acquire_advisory_lock()

        # Verify the advisory lock query was executed
        async_session.execute.assert_called_once()


class TestAdvisoryLockConcurrentRejection:
    """Test: advisory_lock concurrent rejection raises RuntimeError.

    Validates: Requirements 3.6
    """

    @pytest.mark.asyncio
    async def test_lock_rejected_raises_runtime_error(self, async_session: AsyncMock):
        """Raises RuntimeError when advisory lock cannot be acquired (concurrent generation)."""
        async_session.execute = AsyncMock(
            return_value=_mock_scalar(False)
        )

        service = _make_service(async_session)

        with pytest.raises(RuntimeError) as exc_info:
            await service._acquire_advisory_lock()

        assert "already in progress" in str(exc_info.value)
        assert "wait for the current generation to complete" in str(exc_info.value)
