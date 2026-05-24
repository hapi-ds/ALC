"""Unit tests for DynamicFeedbackService.

Tests cache hit/miss, fallback behavior, threshold handling,
and failed attempt verification.

Requirements: 7.1–7.10
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.training_ecosystem import (
    DynamicFeedbackCache,
    GeneratedQuestion,
)
from alcoabase.schemas.training_ecosystem import DynamicFeedbackResponse
from alcoabase.services.dynamic_feedback import (
    GENERIC_EXPLANATION,
    GENERIC_NO_PARAGRAPH_MESSAGE,
    SIMILARITY_THRESHOLD,
    DynamicFeedbackService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a mock async session factory."""
    mock_factory = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_cm
    mock_factory._session = mock_session
    return mock_factory


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value="This paragraph explains the correct procedure."
    )
    return client


@pytest.fixture
def mock_knowledge_service():
    """Create a mock KnowledgeService."""
    service = MagicMock()
    # Default: return results above threshold
    mock_result = MagicMock()
    mock_result.relevance_score = 0.85
    mock_result.excerpt = "The correct procedure is to follow step 3."
    mock_result.metadata = {
        "section_reference": "Section 3.1",
        "page_number": 5,
    }
    service.hybrid_search = MagicMock(return_value=([mock_result], 1))
    return service


@pytest.fixture
def service(mock_session_factory, mock_inference_client, mock_knowledge_service):
    """Create a DynamicFeedbackService with mocked dependencies."""
    return DynamicFeedbackService(
        session_factory=mock_session_factory,
        inference_client=mock_inference_client,
        knowledge_service=mock_knowledge_service,
    )


@pytest.fixture
def sample_question():
    """Create a sample GeneratedQuestion."""
    q = MagicMock(spec=GeneratedQuestion)
    q.id = 1
    q.question_text = "What is the correct procedure for step 3?"
    q.correct_answer = "Follow the safety protocol."
    q.sop_section_ref = "Section 3.1"
    q.document_version_id = 10
    q.company_id = 1
    return q


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for service constants."""

    def test_similarity_threshold_is_0_75(self):
        """Similarity threshold is 0.75."""
        assert SIMILARITY_THRESHOLD == 0.75

    def test_generic_explanation_is_defined(self):
        """Generic explanation fallback message is defined."""
        assert "Review the highlighted paragraph" in GENERIC_EXPLANATION

    def test_generic_no_paragraph_message_is_defined(self):
        """Generic no-paragraph fallback message is defined."""
        assert "review" in GENERIC_NO_PARAGRAPH_MESSAGE.lower()


# ---------------------------------------------------------------------------
# Tests: generate_feedback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGenerateFeedback:
    """Tests for feedback generation via RAG + LLM."""

    async def test_returns_feedback_with_paragraph_above_threshold(
        self, service, sample_question, mock_knowledge_service
    ):
        """Returns feedback when paragraph similarity >= 0.75."""
        feedback = await service.generate_feedback(sample_question)

        assert feedback.correct_answer == sample_question.correct_answer
        assert feedback.paragraph_text == "The correct procedure is to follow step 3."
        assert feedback.section_reference == "Section 3.1"
        assert feedback.page_number == 5

    async def test_fallback_when_no_paragraph_above_threshold(
        self, service, sample_question, mock_knowledge_service
    ):
        """Returns generic message when no paragraph meets threshold."""
        # All results below threshold
        mock_result = MagicMock()
        mock_result.relevance_score = 0.50
        mock_result.excerpt = "Irrelevant text."
        mock_result.metadata = {}
        mock_knowledge_service.hybrid_search.return_value = ([mock_result], 1)

        feedback = await service.generate_feedback(sample_question)

        assert feedback.paragraph_text == GENERIC_NO_PARAGRAPH_MESSAGE
        assert feedback.section_reference == sample_question.sop_section_ref
        assert feedback.page_number is None

    async def test_fallback_when_no_results_returned(
        self, service, sample_question, mock_knowledge_service
    ):
        """Returns generic message when RAG returns no results."""
        mock_knowledge_service.hybrid_search.return_value = ([], 0)

        feedback = await service.generate_feedback(sample_question)

        assert feedback.paragraph_text == GENERIC_NO_PARAGRAPH_MESSAGE

    async def test_selects_highest_similarity_paragraph(
        self, service, sample_question, mock_knowledge_service
    ):
        """Selects the paragraph with highest similarity above threshold."""
        result_low = MagicMock()
        result_low.relevance_score = 0.76
        result_low.excerpt = "Low relevance paragraph."
        result_low.metadata = {"section_reference": "Section 1.1"}

        result_high = MagicMock()
        result_high.relevance_score = 0.92
        result_high.excerpt = "High relevance paragraph."
        result_high.metadata = {"section_reference": "Section 3.2", "page_number": 7}

        mock_knowledge_service.hybrid_search.return_value = (
            [result_low, result_high],
            2,
        )

        feedback = await service.generate_feedback(sample_question)

        assert feedback.paragraph_text == "High relevance paragraph."
        assert feedback.section_reference == "Section 3.2"
        assert feedback.page_number == 7

    async def test_inference_unavailable_returns_generic_explanation(
        self, service, sample_question, mock_inference_client
    ):
        """When InferenceClient fails, returns generic explanation."""
        from alcoabase.services.inference_client import InferenceConnectionError

        mock_inference_client.chat_completion.side_effect = (
            InferenceConnectionError("Connection refused")
        )

        feedback = await service.generate_feedback(sample_question)

        assert feedback.explanation == GENERIC_EXPLANATION
        # Paragraph text should still be present from RAG
        assert feedback.paragraph_text != GENERIC_NO_PARAGRAPH_MESSAGE

    async def test_uses_sop_section_ref_when_metadata_missing(
        self, service, sample_question, mock_knowledge_service
    ):
        """Falls back to question's sop_section_ref when metadata lacks section_reference."""
        mock_result = MagicMock()
        mock_result.relevance_score = 0.80
        mock_result.excerpt = "Some paragraph text."
        mock_result.metadata = {}  # No section_reference
        mock_knowledge_service.hybrid_search.return_value = ([mock_result], 1)

        feedback = await service.generate_feedback(sample_question)

        assert feedback.section_reference == sample_question.sop_section_ref


# ---------------------------------------------------------------------------
# Tests: invalidate_cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInvalidateCache:
    """Tests for cache invalidation."""

    async def test_invalidate_deletes_entries_for_version(
        self, service, mock_session
    ):
        """Invalidation deletes all cache entries for the document version."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await service.invalidate_cache(document_version_id=10)

        assert count == 5
        mock_session.commit.assert_called_once()

    async def test_invalidate_returns_0_when_no_entries(
        self, service, mock_session
    ):
        """Returns 0 when no cache entries exist for the version."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        count = await service.invalidate_cache(document_version_id=999)

        assert count == 0


# ---------------------------------------------------------------------------
# Tests: has_failed_attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHasFailedAttempt:
    """Tests for failed attempt verification."""

    async def test_returns_true_when_failed_attempt_exists(
        self, service, mock_session
    ):
        """Returns True when user has a failed quiz attempt."""
        # Mock question lookup
        mock_question_result = MagicMock()
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question_result.scalar_one_or_none.return_value = mock_question

        # Mock failed attempt lookup
        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = MagicMock(id=1)

        mock_session.execute = AsyncMock(
            side_effect=[mock_question_result, mock_attempt_result]
        )

        result = await service.has_failed_attempt(
            question_id=1, user_id=1, company_id=1
        )

        assert result is True

    async def test_returns_false_when_no_failed_attempt(
        self, service, mock_session
    ):
        """Returns False when user has no failed attempts."""
        # Mock question lookup
        mock_question_result = MagicMock()
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question_result.scalar_one_or_none.return_value = mock_question

        # Mock no failed attempt
        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[mock_question_result, mock_attempt_result]
        )

        result = await service.has_failed_attempt(
            question_id=1, user_id=1, company_id=1
        )

        assert result is False

    async def test_returns_false_when_question_not_found(
        self, service, mock_session
    ):
        """Returns False when question does not exist."""
        mock_question_result = MagicMock()
        mock_question_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(return_value=mock_question_result)

        result = await service.has_failed_attempt(
            question_id=999, user_id=1, company_id=1
        )

        assert result is False


# ---------------------------------------------------------------------------
# Tests: get_feedback (integration of checks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetFeedback:
    """Tests for the get_feedback orchestration method."""

    async def test_raises_404_when_question_not_found(
        self, service, mock_session
    ):
        """Raises 404 when question does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_feedback(
                question_id=999, user_id=1, company_id=1
            )

        assert exc_info.value.status_code == 404

    async def test_raises_403_when_no_failed_attempt(
        self, service, mock_session
    ):
        """Raises 403 when user has no failed attempts."""
        # Question exists
        mock_question = MagicMock(spec=GeneratedQuestion)
        mock_question.id = 1
        mock_question.company_id = 1
        mock_question.document_version_id = 10

        mock_question_result = MagicMock()
        mock_question_result.scalar_one_or_none.return_value = mock_question

        # No failed attempt (question found but no attempt)
        mock_attempt_question_result = MagicMock()
        mock_attempt_question_result.scalar_one_or_none.return_value = mock_question

        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(
            side_effect=[
                mock_question_result,
                mock_attempt_question_result,
                mock_attempt_result,
            ]
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_feedback(
                question_id=1, user_id=1, company_id=1
            )

        assert exc_info.value.status_code == 403

    async def test_returns_cached_feedback_when_available(
        self, service, mock_session
    ):
        """Returns cached feedback without regenerating."""
        # Question exists
        mock_question = MagicMock(spec=GeneratedQuestion)
        mock_question.id = 1
        mock_question.company_id = 1
        mock_question.correct_answer = "The correct answer."
        mock_question.document_version_id = 10

        mock_question_result = MagicMock()
        mock_question_result.scalar_one_or_none.return_value = mock_question

        # Has failed attempt
        mock_attempt_question_result = MagicMock()
        mock_attempt_question_result.scalar_one_or_none.return_value = mock_question

        mock_attempt_result = MagicMock()
        mock_attempt_result.scalar_one_or_none.return_value = MagicMock(id=1)

        # Cached feedback exists
        mock_cache = MagicMock(spec=DynamicFeedbackCache)
        mock_cache.paragraph_text = "Cached paragraph."
        mock_cache.section_reference = "Section 2.1"
        mock_cache.page_number = 3
        mock_cache.explanation = "Cached explanation."

        mock_cache_result = MagicMock()
        mock_cache_result.scalar_one_or_none.return_value = mock_cache

        mock_session.execute = AsyncMock(
            side_effect=[
                mock_question_result,
                mock_attempt_question_result,
                mock_attempt_result,
                mock_cache_result,
            ]
        )

        feedback = await service.get_feedback(
            question_id=1, user_id=1, company_id=1
        )

        assert feedback.paragraph_text == "Cached paragraph."
        assert feedback.section_reference == "Section 2.1"
        assert feedback.page_number == 3
        assert feedback.explanation == "Cached explanation."
