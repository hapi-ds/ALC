"""Unit tests for GeneratedDocReviewService.

Tests the review workflow for AI-generated documents, including
approve/reject transitions, non-AI-generated document rejection,
and already-reviewed document handling.

Requirements: 6.3, 6.4, 6.8, 6.9
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.services.generated_doc_review import GeneratedDocReviewService


@pytest.fixture
def mock_session():
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a session factory that mimics async_sessionmaker behavior.

    async_sessionmaker returns an async context manager when called,
    i.e., `async with session_factory() as session:`.
    """
    context_manager = AsyncMock()
    context_manager.__aenter__ = AsyncMock(return_value=mock_session)
    context_manager.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = context_manager
    return factory


@pytest.fixture
def service(mock_session_factory):
    """Create a GeneratedDocReviewService with mocked dependencies."""
    return GeneratedDocReviewService(session_factory=mock_session_factory)


def _make_document(doc_id: int = 1, company_id: int = 10, current_status: str = "Draft"):
    """Create a mock Document object."""
    doc = MagicMock()
    doc.id = doc_id
    doc.company_id = company_id
    doc.current_status = current_status
    return doc


def _make_job_metadata(
    content_status: str = "pending_review",
    result_document_id: int = 1,
    company_id: int = 10,
):
    """Create a mock GenerationJobMetadata object."""
    job = MagicMock()
    job.content_status = content_status
    job.result_document_id = result_document_id
    job.company_id = company_id
    return job


def _setup_session_execute(mock_session, document, provenance_id, job_metadata):
    """Configure mock_session.execute to return document, provenance, and job metadata.

    The service calls session.execute three times in sequence:
    1. Document lookup
    2. GenerationProvenance check (returns provenance_id or None)
    3. GenerationJobMetadata lookup
    """
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = document

    prov_result = MagicMock()
    prov_result.scalar_one_or_none.return_value = provenance_id

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job_metadata

    mock_session.execute.side_effect = [doc_result, prov_result, job_result]


class TestApproveDocument:
    """Tests for approve action on review_document.

    Validates: Requirement 6.3 - Approve transitions document from Draft to Review.
    """

    @pytest.mark.asyncio
    async def test_approve_transitions_status_to_review(self, service, mock_session):
        """Approve sets current_status to 'Review' and content_status to 'approved'."""
        document = _make_document(doc_id=1, company_id=10, current_status="Draft")
        job_metadata = _make_job_metadata(content_status="pending_review")
        _setup_session_execute(mock_session, document, 42, job_metadata)

        result = await service.review_document(
            document_id=1,
            action="approve",
            reviewer_id=5,
            company_id=10,
        )

        assert result["document_id"] == 1
        assert result["current_status"] == "Review"
        assert result["content_status"] == "approved"
        assert document.current_status == "Review"
        assert job_metadata.content_status == "approved"

    @pytest.mark.asyncio
    async def test_approve_commits_session(self, service, mock_session):
        """Approve calls session.commit to persist changes."""
        document = _make_document()
        job_metadata = _make_job_metadata()
        _setup_session_execute(mock_session, document, 42, job_metadata)

        await service.review_document(
            document_id=1,
            action="approve",
            reviewer_id=5,
            company_id=10,
        )

        mock_session.commit.assert_awaited_once()


class TestRejectDocument:
    """Tests for reject action on review_document.

    Validates: Requirement 6.4 - Reject marks ContentStatus as 'rejected',
    document remains in Draft.
    """

    @pytest.mark.asyncio
    async def test_reject_marks_content_status_rejected(self, service, mock_session):
        """Reject sets content_status to 'rejected' while keeping Draft status."""
        document = _make_document(doc_id=2, company_id=10, current_status="Draft")
        job_metadata = _make_job_metadata(content_status="pending_review")
        _setup_session_execute(mock_session, document, 42, job_metadata)

        result = await service.review_document(
            document_id=2,
            action="reject",
            reviewer_id=5,
            company_id=10,
        )

        assert result["document_id"] == 2
        assert result["current_status"] == "Draft"
        assert result["content_status"] == "rejected"
        assert document.current_status == "Draft"
        assert job_metadata.content_status == "rejected"

    @pytest.mark.asyncio
    async def test_reject_does_not_change_current_status(self, service, mock_session):
        """Reject leaves current_status unchanged at 'Draft'."""
        document = _make_document(current_status="Draft")
        job_metadata = _make_job_metadata()
        _setup_session_execute(mock_session, document, 42, job_metadata)

        await service.review_document(
            document_id=1,
            action="reject",
            reviewer_id=5,
            company_id=10,
        )

        assert document.current_status == "Draft"


class TestNonAIGeneratedDocument:
    """Tests for review on non-AI-generated documents.

    Validates: Requirement 6.8 - Review on non-AI-generated document raises ValueError
    (maps to HTTP 422 at the API layer).
    """

    @pytest.mark.asyncio
    async def test_non_ai_generated_raises_value_error(self, service, mock_session):
        """Review on document without GenerationProvenance raises ValueError."""
        document = _make_document(doc_id=3, company_id=10)

        # Document exists but has no provenance record
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = document

        prov_result = MagicMock()
        prov_result.scalar_one_or_none.return_value = None  # No provenance

        mock_session.execute.side_effect = [doc_result, prov_result]

        with pytest.raises(ValueError, match="Only AI-generated documents"):
            await service.review_document(
                document_id=3,
                action="approve",
                reviewer_id=5,
                company_id=10,
            )

    @pytest.mark.asyncio
    async def test_non_ai_generated_does_not_commit(self, service, mock_session):
        """No commit occurs when document is not AI-generated."""
        document = _make_document()

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = document

        prov_result = MagicMock()
        prov_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [doc_result, prov_result]

        with pytest.raises(ValueError):
            await service.review_document(
                document_id=1,
                action="approve",
                reviewer_id=5,
                company_id=10,
            )

        mock_session.commit.assert_not_awaited()


class TestAlreadyReviewedDocument:
    """Tests for review on already-reviewed documents.

    Validates: Requirement 6.9 - Review on already-reviewed document raises ValueError
    (maps to HTTP 409 at the API layer).
    """

    @pytest.mark.asyncio
    async def test_already_approved_raises_value_error(self, service, mock_session):
        """Review on document with content_status 'approved' raises ValueError."""
        document = _make_document(doc_id=4, company_id=10)
        job_metadata = _make_job_metadata(content_status="approved")
        _setup_session_execute(mock_session, document, 42, job_metadata)

        with pytest.raises(ValueError, match="already been reviewed"):
            await service.review_document(
                document_id=4,
                action="approve",
                reviewer_id=5,
                company_id=10,
            )

    @pytest.mark.asyncio
    async def test_already_rejected_raises_value_error(self, service, mock_session):
        """Review on document with content_status 'rejected' raises ValueError."""
        document = _make_document(doc_id=5, company_id=10)
        job_metadata = _make_job_metadata(content_status="rejected")
        _setup_session_execute(mock_session, document, 42, job_metadata)

        with pytest.raises(ValueError, match="already been reviewed"):
            await service.review_document(
                document_id=5,
                action="reject",
                reviewer_id=5,
                company_id=10,
            )

    @pytest.mark.asyncio
    async def test_already_reviewed_includes_current_status_in_message(
        self, service, mock_session
    ):
        """Error message includes the current content_status."""
        document = _make_document()
        job_metadata = _make_job_metadata(content_status="approved")
        _setup_session_execute(mock_session, document, 42, job_metadata)

        with pytest.raises(ValueError, match="approved"):
            await service.review_document(
                document_id=1,
                action="reject",
                reviewer_id=5,
                company_id=10,
            )

    @pytest.mark.asyncio
    async def test_already_reviewed_does_not_commit(self, service, mock_session):
        """No commit occurs when document has already been reviewed."""
        document = _make_document()
        job_metadata = _make_job_metadata(content_status="approved")
        _setup_session_execute(mock_session, document, 42, job_metadata)

        with pytest.raises(ValueError):
            await service.review_document(
                document_id=1,
                action="approve",
                reviewer_id=5,
                company_id=10,
            )

        mock_session.commit.assert_not_awaited()
