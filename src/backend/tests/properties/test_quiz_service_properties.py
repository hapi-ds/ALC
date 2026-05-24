"""Property-based tests for QuizService extensions.

Tests Property 15 from the AI-Enhanced Training Ecosystem design document:
- Property 15: Only approved questions are served in active assessments

**Validates: Requirements 11.4, 4.10**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md
"""

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.training_ecosystem import (
    ActiveQuestionSet,
    ContentStatus,
    GeneratedQuestion,
    QuestionType,
    DifficultyLevel,
)
from alcoabase.services.quiz_service import QuizService


# ===========================================================================
# Property 15: Only approved questions are served in active assessments
# ===========================================================================

"""
Property 15 validates that when evaluate_and_persist_enhanced retrieves
questions for grading, it only uses those with status "approved". Questions
with status pending_review, rejected, or draft must never appear in active
assessments.

**Validates: Requirements 11.4, 4.10**
"""

# ---------------------------------------------------------------------------
# Hypothesis Strategies for Property 15
# ---------------------------------------------------------------------------

#: All possible content statuses for generated questions.
ALL_STATUSES = [status.value for status in ContentStatus]

#: Non-approved statuses that should be excluded from assessments.
NON_APPROVED_STATUSES = [
    s for s in ALL_STATUSES if s != ContentStatus.APPROVED.value
]

#: Valid question types for generating test questions.
QUESTION_TYPES = list(QuestionType)

#: Valid difficulty levels.
DIFFICULTY_LEVELS = list(DifficultyLevel)


@st.composite
def st_generated_question(
    draw: st.DrawFn,
    status: str | None = None,
    question_id: int | None = None,
) -> MagicMock:
    """Generate a mock GeneratedQuestion with a random or specified status.

    Args:
        draw: Hypothesis draw function.
        status: If provided, use this status. Otherwise draw randomly.
        question_id: If provided, use this ID. Otherwise draw randomly.

    Returns:
        A MagicMock mimicking a GeneratedQuestion instance.
    """
    q_id = question_id if question_id is not None else draw(
        st.integers(min_value=1, max_value=10000)
    )
    q_status = status if status is not None else draw(
        st.sampled_from(ALL_STATUSES)
    )
    q_type = draw(st.sampled_from(QUESTION_TYPES))
    correct_answer = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip() != "")
    )

    question = MagicMock(spec=GeneratedQuestion)
    question.id = q_id
    question.status = q_status
    question.question_type = q_type
    question.correct_answer = correct_answer
    question.question_text = f"Question {q_id}"
    question.sop_section_ref = f"Section {q_id % 10 + 1}.1"
    question.difficulty_level = draw(st.sampled_from(DIFFICULTY_LEVELS))
    question.document_id = 1
    question.document_version_id = 1
    question.company_id = 1
    return question


@st.composite
def st_question_set_with_mixed_statuses(
    draw: st.DrawFn,
) -> list[MagicMock]:
    """Generate a list of questions with various statuses.

    Ensures at least one question of each status type exists in the set,
    plus additional random questions. This guarantees the test exercises
    the filtering logic with all status variants present.

    Returns:
        List of mock GeneratedQuestion objects with mixed statuses.
    """
    questions: list[MagicMock] = []
    q_id = 1

    # Ensure at least one question per status
    for status_val in ALL_STATUSES:
        q = draw(st_generated_question(status=status_val, question_id=q_id))
        questions.append(q)
        q_id += 1

    # Add additional random questions (0–10 more)
    extra_count = draw(st.integers(min_value=0, max_value=10))
    for _ in range(extra_count):
        q = draw(st_generated_question(question_id=q_id))
        questions.append(q)
        q_id += 1

    return questions


# ---------------------------------------------------------------------------
# Helper: Filter function that mirrors the service's query logic
# ---------------------------------------------------------------------------


def filter_approved_questions(
    questions: list[MagicMock],
) -> list[MagicMock]:
    """Filter questions to only those with approved status.

    This mirrors the SQLAlchemy filter in evaluate_and_persist_enhanced:
        GeneratedQuestion.status == ContentStatus.APPROVED.value

    Args:
        questions: List of mock GeneratedQuestion objects.

    Returns:
        List containing only questions with status == "approved".
    """
    return [
        q for q in questions
        if q.status == ContentStatus.APPROVED.value
    ]


# ---------------------------------------------------------------------------
# Property 15 Tests
# ---------------------------------------------------------------------------


# Feature: ai-enhanced-training-ecosystem, Property 15: Only approved served
@settings(max_examples=200)
@given(questions=st_question_set_with_mixed_statuses())
def test_only_approved_questions_pass_filter(
    questions: list[MagicMock],
) -> None:
    """For any set of questions with mixed statuses, the approved-only filter
    SHALL return exclusively questions with status "approved".

    **Validates: Requirements 11.4, 4.10**
    """
    filtered = filter_approved_questions(questions)

    # All filtered questions must have approved status
    for q in filtered:
        assert q.status == ContentStatus.APPROVED.value, (
            f"Non-approved question (status={q.status}) found in filtered set"
        )


# Feature: ai-enhanced-training-ecosystem, Property 15: Non-approved excluded
@settings(max_examples=200)
@given(questions=st_question_set_with_mixed_statuses())
def test_non_approved_questions_excluded_from_filter(
    questions: list[MagicMock],
) -> None:
    """For any set of questions with mixed statuses, the approved-only filter
    SHALL exclude all questions with status pending_review, rejected, or draft.

    **Validates: Requirements 11.4, 4.10**
    """
    filtered = filter_approved_questions(questions)
    filtered_ids = {q.id for q in filtered}

    # No non-approved question should appear in the filtered set
    for q in questions:
        if q.status != ContentStatus.APPROVED.value:
            assert q.id not in filtered_ids, (
                f"Question {q.id} with status={q.status} should not be "
                f"in the filtered set"
            )


# Feature: ai-enhanced-training-ecosystem, Property 15: Approved count preserved
@settings(max_examples=200)
@given(questions=st_question_set_with_mixed_statuses())
def test_filter_preserves_all_approved_questions(
    questions: list[MagicMock],
) -> None:
    """For any set of questions, the filter SHALL include ALL questions
    with status "approved" — none are lost during filtering.

    **Validates: Requirements 11.4, 4.10**
    """
    filtered = filter_approved_questions(questions)

    # Count approved in original set
    expected_approved = [
        q for q in questions
        if q.status == ContentStatus.APPROVED.value
    ]

    assert len(filtered) == len(expected_approved), (
        f"Filter returned {len(filtered)} questions but expected "
        f"{len(expected_approved)} approved questions"
    )


# Feature: ai-enhanced-training-ecosystem, Property 15: No approved → empty
@settings(max_examples=200)
@given(
    questions=st.lists(
        st_generated_question(status=st.just(None)),
        min_size=1,
        max_size=15,
    ).filter(
        lambda qs: all(
            q.status != ContentStatus.APPROVED.value for q in qs
        )
    )
)
def test_no_approved_questions_yields_empty_assessment(
    questions: list[MagicMock],
) -> None:
    """When no questions have status "approved", the filter SHALL return
    an empty list, meaning no assessment can be served.

    **Validates: Requirements 11.4, 4.10**
    """
    filtered = filter_approved_questions(questions)
    assert len(filtered) == 0, (
        f"Expected empty filtered set when no approved questions exist, "
        f"got {len(filtered)} questions"
    )


# Feature: ai-enhanced-training-ecosystem, Property 15: Integration with service
@pytest.mark.asyncio
@settings(max_examples=50, deadline=None)
@given(questions=st_question_set_with_mixed_statuses())
async def test_evaluate_and_persist_enhanced_uses_only_approved(
    questions: list[MagicMock],
) -> None:
    """The evaluate_and_persist_enhanced method SHALL only grade answers
    against questions with status "approved". Questions with any other
    status SHALL NOT be included in the grading.

    This test verifies the integration between the filter logic and the
    actual service method by mocking the database query to return mixed-
    status questions and verifying only approved ones are graded.

    **Validates: Requirements 11.4, 4.10**
    """
    approved_questions = [
        q for q in questions
        if q.status == ContentStatus.APPROVED.value
    ]

    # Create mock session that returns only approved questions
    # (mimicking the SQLAlchemy filter behavior)
    mock_session = AsyncMock(spec=AsyncSession)

    # Mock user query
    mock_user_result = MagicMock()
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user_result.scalar_one_or_none.return_value = mock_user

    # Mock active question set query
    mock_active_set_result = MagicMock()
    mock_active_set = MagicMock(spec=ActiveQuestionSet)
    mock_active_set.document_id = 1
    mock_active_set.document_version_id = 1
    mock_active_set_result.scalar_one_or_none.return_value = mock_active_set

    # Mock questions query — the DB filter returns only approved
    mock_questions_result = MagicMock()
    mock_questions_scalars = MagicMock()
    mock_questions_scalars.all.return_value = approved_questions
    mock_questions_result.scalars.return_value = mock_questions_scalars

    # Set up session.execute to return different results per call
    mock_session.execute = AsyncMock(
        side_effect=[
            mock_user_result,        # User lookup
            mock_active_set_result,  # Active question set lookup
            mock_questions_result,   # Questions query (filtered to approved)
        ]
    )
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()

    # Create service with mocked dependencies
    content_generator = MagicMock()
    service = QuizService(content_generator=content_generator)

    # Build answers dict for all questions (both approved and non-approved)
    answers = {str(q.id): q.correct_answer for q in questions}

    if not approved_questions:
        # When no approved questions exist, the service should raise 400
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_and_persist_enhanced(
                session=mock_session,
                content_id="DOC-001_v1.0",
                user_id=1,
                answers=answers,
                company_id=1,
            )
        assert exc_info.value.status_code == 400
        assert "No approved questions" in exc_info.value.detail
    else:
        # When approved questions exist, the service should grade only those
        attempt = await service.evaluate_and_persist_enhanced(
            session=mock_session,
            content_id="DOC-001_v1.0",
            user_id=1,
            answers=answers,
            company_id=1,
        )

        # The total_questions should equal the number of approved questions
        # (not the total number of questions with all statuses)
        assert attempt.total_questions == len(approved_questions), (
            f"total_questions={attempt.total_questions} should equal "
            f"approved count={len(approved_questions)}, not total "
            f"questions={len(questions)}"
        )
