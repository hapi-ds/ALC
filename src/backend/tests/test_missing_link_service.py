"""Unit tests for MissingLinkService.

Tests the missing link detection logic including training completeness,
signature completeness, severity classification, and days-since-approval
computation.

References:
    - Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.services.missing_link_service import (
    MissingLinkService,
    classify_severity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    factory = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    return factory, session


@pytest.fixture
def service(mock_session_factory):
    """Create a MissingLinkService with mocked session factory."""
    factory, _ = mock_session_factory
    return MissingLinkService(session_factory=factory)


@pytest.fixture
def approved_document():
    """Create a sample approved document."""
    doc = Document(
        id=1,
        document_uuid="2025-00001",
        title="Test SOP",
        folder_path="/sops",
        document_type="SOP",
        current_status="Approved",
        created_by=1,
        company_id=1,
    )
    doc.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    return doc


@pytest.fixture
def active_document():
    """Create a sample active document."""
    doc = Document(
        id=2,
        document_uuid="2025-00002",
        title="Active Report",
        folder_path="/reports",
        document_type="Report",
        current_status="Active",
        created_by=1,
        company_id=1,
    )
    doc.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    return doc


@pytest.fixture
def sample_version():
    """Create a sample document version."""
    return DocumentVersion(
        id=10,
        document_id=1,
        major_version=2,
        minor_version=0,
        storage_key="documents/2025-00001/2.0/test.pdf",
        file_hash="a" * 128,
        uploaded_by=1,
    )


# ---------------------------------------------------------------------------
# classify_severity tests
# ---------------------------------------------------------------------------


class TestClassifySeverity:
    """Tests for the classify_severity pure function."""

    def test_both_missing_is_critical(self):
        """Both training and signature missing → Critical."""
        assert classify_severity(training_missing=True, signature_missing=True) == "Critical"

    def test_only_training_missing_is_major(self):
        """Only training missing → Major."""
        assert classify_severity(training_missing=True, signature_missing=False) == "Major"

    def test_only_signature_missing_is_major(self):
        """Only signature missing → Major."""
        assert classify_severity(training_missing=False, signature_missing=True) == "Major"

    def test_neither_missing_is_major(self):
        """Neither missing — this case shouldn't normally be called but returns Major."""
        # This case is guarded by the caller (documents with no gaps are skipped)
        assert classify_severity(training_missing=False, signature_missing=False) == "Major"


# ---------------------------------------------------------------------------
# check_training_completeness tests
# ---------------------------------------------------------------------------


class TestCheckTrainingCompleteness:
    """Tests for training completeness checking."""

    @pytest.mark.asyncio
    async def test_document_not_found_returns_true(self, mock_session_factory):
        """Should return True when document doesn't exist."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        # Document query returns None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        result = await service.check_training_completeness(document_id=999)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_version_returns_true(self, mock_session_factory, approved_document):
        """Should return True when document has no versions."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        # First call: document found; Second call: no version
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [doc_result, version_result]

        result = await service.check_training_completeness(document_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_training_tasks_returns_true(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return True when no training tasks are assigned."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        # Document found, version found, no training tasks
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        # No assigned users
        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))

        session.execute.side_effect = [doc_result, version_result, assigned_result]

        result = await service.check_training_completeness(document_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_all_users_trained_returns_true(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return True when all assigned users have valid training."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        # 3 users assigned
        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1, 2, 3])
        )

        # All 3 users have valid training
        trained_result = MagicMock()
        trained_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1, 2, 3])
        )

        session.execute.side_effect = [
            doc_result, version_result, assigned_result, trained_result
        ]

        result = await service.check_training_completeness(document_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_some_users_missing_training_returns_false(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return False when some users lack valid training."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        # 3 users assigned
        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1, 2, 3])
        )

        # Only 1 user has valid training
        trained_result = MagicMock()
        trained_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1])
        )

        session.execute.side_effect = [
            doc_result, version_result, assigned_result, trained_result
        ]

        result = await service.check_training_completeness(document_id=1)
        assert result is False


# ---------------------------------------------------------------------------
# check_signature_completeness tests
# ---------------------------------------------------------------------------


class TestCheckSignatureCompleteness:
    """Tests for signature completeness checking."""

    @pytest.mark.asyncio
    async def test_document_not_found_returns_true(self, mock_session_factory):
        """Should return True when document doesn't exist."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        result = await service.check_signature_completeness(document_id=999)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_workflow_returns_true(
        self, mock_session_factory, approved_document
    ):
        """Should return True when no workflow is defined for the document type."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        # No workflow found
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [doc_result, workflow_result]

        result = await service.check_signature_completeness(document_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_workflow_no_signature_transitions_returns_true(
        self, mock_session_factory, approved_document
    ):
        """Should return True when workflow has no signature-required transitions."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        workflow = WorkflowDefinition(
            id=1,
            name="SOP Workflow",
            document_tag="SOP",
            bpmn_xml="<xml/>",
            signature_required_transitions=[],
            training_trigger_transitions=[],
            created_by=1,
            company_id=1,
        )
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow

        session.execute.side_effect = [doc_result, workflow_result]

        result = await service.check_signature_completeness(document_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_signature_exists_returns_true(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return True when PAdES signature exists."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        workflow = WorkflowDefinition(
            id=1,
            name="SOP Workflow",
            document_tag="SOP",
            bpmn_xml="<xml/>",
            signature_required_transitions=["Review→Approved"],
            training_trigger_transitions=[],
            created_by=1,
            company_id=1,
        )
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        # Signature count = 1
        sig_result = MagicMock()
        sig_result.scalar_one.return_value = 1

        session.execute.side_effect = [
            doc_result, workflow_result, version_result, sig_result
        ]

        result = await service.check_signature_completeness(document_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_signature_missing_returns_false(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return False when required PAdES signature is missing."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        workflow = WorkflowDefinition(
            id=1,
            name="SOP Workflow",
            document_tag="SOP",
            bpmn_xml="<xml/>",
            signature_required_transitions=["Review→Approved"],
            training_trigger_transitions=[],
            created_by=1,
            company_id=1,
        )
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        # Signature count = 0
        sig_result = MagicMock()
        sig_result.scalar_one.return_value = 0

        session.execute.side_effect = [
            doc_result, workflow_result, version_result, sig_result
        ]

        result = await service.check_signature_completeness(document_id=1)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_version_with_signature_required_returns_false(
        self, mock_session_factory, approved_document
    ):
        """Should return False when signature required but no version exists."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = approved_document

        workflow = WorkflowDefinition(
            id=1,
            name="SOP Workflow",
            document_tag="SOP",
            bpmn_xml="<xml/>",
            signature_required_transitions=["Review→Approved"],
            training_trigger_transitions=[],
            created_by=1,
            company_id=1,
        )
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow

        # No version
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [doc_result, workflow_result, version_result]

        result = await service.check_signature_completeness(document_id=1)
        assert result is False


# ---------------------------------------------------------------------------
# detect_missing_links tests
# ---------------------------------------------------------------------------


class TestDetectMissingLinks:
    """Tests for the full detect_missing_links method."""

    @pytest.mark.asyncio
    async def test_no_approved_documents_returns_empty(self, mock_session_factory):
        """Should return empty list when no documents are in Approved/Active status."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        # No documents found
        docs_result = MagicMock()
        docs_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        session.execute.return_value = docs_result

        result = await service.detect_missing_links(company_id=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_document_with_no_gaps_excluded(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should exclude documents where both training and signature are complete."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        # Documents query returns one approved document
        docs_result = MagicMock()
        docs_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[approved_document])
        )

        # Training: no tasks assigned (complete)
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )

        # Signature: no workflow (complete)
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            docs_result,
            # Training check: version, assigned users
            version_result, assigned_result,
            # Signature check: workflow
            workflow_result,
        ]

        result = await service.detect_missing_links(company_id=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_document_with_training_gap_returns_major(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return Major severity when only training is missing."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        docs_result = MagicMock()
        docs_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[approved_document])
        )

        # Training: version found, 2 users assigned, 0 trained
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1, 2])
        )

        trained_result = MagicMock()
        trained_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )

        # Signature: no workflow (complete)
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = None

        # Days since approval: no document state
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            docs_result,
            # Training check
            version_result, assigned_result, trained_result,
            # Signature check
            workflow_result,
            # Days since approval
            state_result,
        ]

        result = await service.detect_missing_links(company_id=1)
        assert len(result) == 1
        assert result[0].severity == "Major"
        assert result[0].missing_items == ["training"]
        assert result[0].affected_user_count == 2
        assert result[0].document_uuid == "2025-00001"

    @pytest.mark.asyncio
    async def test_document_with_both_gaps_returns_critical(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should return Critical severity when both training and signature are missing."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        docs_result = MagicMock()
        docs_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[approved_document])
        )

        # Training: version found, 3 users assigned, 1 trained
        version_result_training = MagicMock()
        version_result_training.scalar_one_or_none.return_value = sample_version

        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1, 2, 3])
        )

        trained_result = MagicMock()
        trained_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[1])
        )

        # Signature: workflow requires signature, no signature exists
        workflow = WorkflowDefinition(
            id=1,
            name="SOP Workflow",
            document_tag="SOP",
            bpmn_xml="<xml/>",
            signature_required_transitions=["Review→Approved"],
            training_trigger_transitions=[],
            created_by=1,
            company_id=1,
        )
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow

        version_result_sig = MagicMock()
        version_result_sig.scalar_one_or_none.return_value = sample_version

        sig_count_result = MagicMock()
        sig_count_result.scalar_one.return_value = 0

        # Days since approval
        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [
            docs_result,
            # Training check
            version_result_training, assigned_result, trained_result,
            # Signature check
            workflow_result, version_result_sig, sig_count_result,
            # Days since approval
            state_result,
        ]

        result = await service.detect_missing_links(company_id=1)
        assert len(result) == 1
        assert result[0].severity == "Critical"
        assert result[0].missing_items == ["training", "signature"]
        assert result[0].affected_user_count == 2

    @pytest.mark.asyncio
    async def test_days_since_approval_uses_document_state(
        self, mock_session_factory, approved_document, sample_version
    ):
        """Should compute days since approval from DocumentState.updated_at."""
        factory, session = mock_session_factory
        service = MissingLinkService(session_factory=factory)

        docs_result = MagicMock()
        docs_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[approved_document])
        )

        # Training: no tasks (complete)
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sample_version

        assigned_result = MagicMock()
        assigned_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )

        # Signature: workflow requires signature, no signature
        workflow = WorkflowDefinition(
            id=1,
            name="SOP Workflow",
            document_tag="SOP",
            bpmn_xml="<xml/>",
            signature_required_transitions=["Review→Approved"],
            training_trigger_transitions=[],
            created_by=1,
            company_id=1,
        )
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow

        version_result_sig = MagicMock()
        version_result_sig.scalar_one_or_none.return_value = sample_version

        sig_count_result = MagicMock()
        sig_count_result.scalar_one.return_value = 0

        # DocumentState with updated_at 10 days ago
        ten_days_ago = datetime.now(UTC) - timedelta(days=10)
        doc_state = DocumentState(
            id=1,
            document_id=1,
            current_state="Approved",
            workflow_id=1,
            updated_by=1,
        )
        doc_state.updated_at = ten_days_ago

        state_result = MagicMock()
        state_result.scalar_one_or_none.return_value = doc_state

        session.execute.side_effect = [
            docs_result,
            # Training check (no tasks)
            version_result, assigned_result,
            # Signature check
            workflow_result, version_result_sig, sig_count_result,
            # Days since approval
            state_result,
        ]

        result = await service.detect_missing_links(company_id=1)
        assert len(result) == 1
        assert result[0].days_since_approval == 10
        assert result[0].severity == "Major"
        assert result[0].missing_items == ["signature"]
