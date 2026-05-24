"""Property-based tests for the Dynamic Feedback Service.

Tests Property 12 from the AI-Enhanced Training Ecosystem design document:
- Property 12: Dynamic feedback requires at least one failed attempt

Verifies that get_feedback raises HTTPException(403) when the user has no
failed attempts for the question, and proceeds (returns feedback) when at
least one failed attempt exists.

**Validates: Requirements 7.7, 9.12**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md (Property 12)
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md (7.7, 9.12)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from fastapi import HTTPException
from hypothesis import given, settings

from alcoabase.models.training_ecosystem import GeneratedQuestion
from alcoabase.schemas.training_ecosystem import DynamicFeedbackResponse
from alcoabase.services.dynamic_feedback import DynamicFeedbackService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

#: Strategy for user IDs (positive integers).
st_user_id = st.integers(min_value=1, max_value=10_000)

#: Strategy for question IDs (positive integers).
st_question_id = st.integers(min_value=1, max_value=10_000)

#: Strategy for company IDs (positive integers).
st_company_id = st.integers(min_value=1, max_value=1_000)

#: Strategy for the has_failed boolean.
st_has_failed = st.booleans()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_question(question_id: int, company_id: int) -> MagicMock:
    """Create a mock GeneratedQuestion with the given ID and company.

    Args:
        question_id: The question ID.
        company_id: The company ID the question belongs to.

    Returns:
        A MagicMock configured as a GeneratedQuestion.
    """
    question = MagicMock(spec=GeneratedQuestion)
    question.id = question_id
    question.company_id = company_id
    question.document_version_id = 1
    question.correct_answer = "The correct answer"
    question.question_text = "What is the procedure?"
    question.sop_section_ref = "Section 2.1"
    return question


def _make_service() -> DynamicFeedbackService:
    """Create a DynamicFeedbackService with mocked dependencies.

    Returns:
        A DynamicFeedbackService instance with mock session_factory,
        inference_client, and knowledge_service.
    """
    session_factory = MagicMock()
    inference_client = AsyncMock()
    knowledge_service = MagicMock()
    return DynamicFeedbackService(
        session_factory=session_factory,
        inference_client=inference_client,
        knowledge_service=knowledge_service,
    )


# ---------------------------------------------------------------------------
# Property 12: Dynamic feedback requires at least one failed attempt
# ---------------------------------------------------------------------------


# Feature: ai-enhanced-training-ecosystem, Property 12: 403 when no failed attempt
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    user_id=st_user_id,
    question_id=st_question_id,
    company_id=st_company_id,
)
async def test_feedback_returns_403_when_no_failed_attempt(
    user_id: int,
    question_id: int,
    company_id: int,
) -> None:
    """For any user/question combination where has_failed_attempt returns
    False, get_feedback SHALL raise HTTPException with status_code 403.

    **Validates: Requirements 7.7, 9.12**
    """
    service = _make_service()
    mock_question = _make_mock_question(question_id, company_id)

    # Mock the session context manager to return a mock session
    mock_session = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    service._session_factory.return_value = mock_session_ctx

    # Mock the question lookup to return our mock question
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_question
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock _has_failed_attempt to return False (no failed attempts)
    service._has_failed_attempt = AsyncMock(return_value=False)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_feedback(question_id, user_id, company_id)

    assert exc_info.value.status_code == 403


# Feature: ai-enhanced-training-ecosystem, Property 12: 200 when failed attempt exists
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(
    user_id=st_user_id,
    question_id=st_question_id,
    company_id=st_company_id,
)
async def test_feedback_proceeds_when_failed_attempt_exists(
    user_id: int,
    question_id: int,
    company_id: int,
) -> None:
    """For any user/question combination where has_failed_attempt returns
    True, get_feedback SHALL proceed and return a DynamicFeedbackResponse
    (not raise 403).

    **Validates: Requirements 7.7, 9.12**
    """
    service = _make_service()
    mock_question = _make_mock_question(question_id, company_id)

    # Mock the session context manager to return a mock session
    mock_session = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    service._session_factory.return_value = mock_session_ctx

    # Mock the question lookup to return our mock question
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_question
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock _has_failed_attempt to return True (has failed attempts)
    service._has_failed_attempt = AsyncMock(return_value=True)

    # Mock _get_cached_feedback to return None (no cache hit)
    service._get_cached_feedback = AsyncMock(return_value=None)

    # Mock generate_feedback to return a valid response
    expected_feedback = DynamicFeedbackResponse(
        correct_answer="The correct answer",
        paragraph_text="Source paragraph text.",
        section_reference="Section 2.1",
        page_number=5,
        explanation="This paragraph explains the procedure.",
    )
    service.generate_feedback = AsyncMock(return_value=expected_feedback)

    # The second session context (for caching) also needs mocking
    mock_cache_session = AsyncMock()
    mock_cache_session.add = MagicMock()  # add() is sync, not async
    mock_cache_session.commit = AsyncMock()
    mock_cache_session_ctx = AsyncMock()
    mock_cache_session_ctx.__aenter__ = AsyncMock(
        return_value=mock_cache_session
    )
    mock_cache_session_ctx.__aexit__ = AsyncMock(return_value=False)

    # session_factory is called twice: once for the main logic, once for caching
    service._session_factory.side_effect = [
        mock_session_ctx,
        mock_cache_session_ctx,
    ]

    result = await service.get_feedback(question_id, user_id, company_id)

    assert isinstance(result, DynamicFeedbackResponse)
    assert result.correct_answer == expected_feedback.correct_answer
    assert result.paragraph_text == expected_feedback.paragraph_text


# Feature: ai-enhanced-training-ecosystem, Property 12: Boolean determines outcome
@pytest.mark.asyncio
@settings(max_examples=200, deadline=None)
@given(
    user_id=st_user_id,
    question_id=st_question_id,
    company_id=st_company_id,
    has_failed=st_has_failed,
)
async def test_feedback_outcome_determined_by_has_failed_attempt(
    user_id: int,
    question_id: int,
    company_id: int,
    has_failed: bool,
) -> None:
    """For any user/question combination, the outcome of get_feedback SHALL
    be determined by has_failed_attempt: False → 403, True → feedback returned.

    **Validates: Requirements 7.7, 9.12**
    """
    service = _make_service()
    mock_question = _make_mock_question(question_id, company_id)

    # Mock the session context manager
    mock_session = AsyncMock()
    mock_session_ctx = AsyncMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    # Mock the question lookup
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_question
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Mock _has_failed_attempt with the generated boolean
    service._has_failed_attempt = AsyncMock(return_value=has_failed)

    if not has_failed:
        # Should raise 403
        service._session_factory.return_value = mock_session_ctx

        with pytest.raises(HTTPException) as exc_info:
            await service.get_feedback(question_id, user_id, company_id)

        assert exc_info.value.status_code == 403
    else:
        # Should return feedback
        service._get_cached_feedback = AsyncMock(return_value=None)

        expected_feedback = DynamicFeedbackResponse(
            correct_answer="The correct answer",
            paragraph_text="Source paragraph text.",
            section_reference="Section 2.1",
            page_number=None,
            explanation="Explanation text.",
        )
        service.generate_feedback = AsyncMock(return_value=expected_feedback)

        # Two session factory calls: main logic + caching
        mock_cache_session = AsyncMock()
        mock_cache_session.add = MagicMock()  # add() is sync, not async
        mock_cache_session.commit = AsyncMock()
        mock_cache_session_ctx = AsyncMock()
        mock_cache_session_ctx.__aenter__ = AsyncMock(
            return_value=mock_cache_session
        )
        mock_cache_session_ctx.__aexit__ = AsyncMock(return_value=False)
        service._session_factory.side_effect = [
            mock_session_ctx,
            mock_cache_session_ctx,
        ]

        result = await service.get_feedback(question_id, user_id, company_id)

        assert isinstance(result, DynamicFeedbackResponse)
        assert result.correct_answer == expected_feedback.correct_answer
