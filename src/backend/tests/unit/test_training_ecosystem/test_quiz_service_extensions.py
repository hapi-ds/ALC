"""Unit tests for QuizService extensions.

Tests enhanced grading, bridge record creation, and
register_approved_questions.

Requirements: 11.1–11.8
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.quiz_service import QuizService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_content_generator():
    """Create a mock TrainingContentGenerator."""
    generator = MagicMock()
    generator.get_questions_for_content = MagicMock(return_value=[
        {"id": "q1", "question": "What is X?", "correct_answer": "A"},
        {"id": "q2", "question": "What is Y?", "correct_answer": "B"},
    ])
    return generator


@pytest.fixture
def mock_question_generator_service():
    """Create a mock QuestionGeneratorService."""
    service = AsyncMock()
    grade_result = MagicMock()
    grade_result.is_correct = True
    service.grade_answer = AsyncMock(return_value=grade_result)
    return service


@pytest.fixture
def service(mock_content_generator, mock_question_generator_service):
    """Create a QuizService with mocked dependencies."""
    return QuizService(
        content_generator=mock_content_generator,
        question_generator_service=mock_question_generator_service,
    )


@pytest.fixture
def service_without_question_generator(mock_content_generator):
    """Create a QuizService without question generator (legacy mode)."""
    return QuizService(
        content_generator=mock_content_generator,
        question_generator_service=None,
    )


# ---------------------------------------------------------------------------
# Tests: compute_pass_threshold
# ---------------------------------------------------------------------------


class TestComputePassThreshold:
    """Tests for the 80% pass threshold computation."""

    def test_threshold_for_10_questions(self, service):
        """10 questions requires 8 correct (80%)."""
        assert service.compute_pass_threshold(10) == 8

    def test_threshold_for_5_questions(self, service):
        """5 questions requires 4 correct (ceil(5*0.8) = 4)."""
        assert service.compute_pass_threshold(5) == 4

    def test_threshold_for_1_question(self, service):
        """1 question requires 1 correct (ceil(1*0.8) = 1)."""
        assert service.compute_pass_threshold(1) == 1

    def test_threshold_rounds_up(self, service):
        """Threshold rounds up (ceil) for non-integer results."""
        # 7 * 0.8 = 5.6 → ceil = 6
        assert service.compute_pass_threshold(7) == 6

    def test_threshold_for_20_questions(self, service):
        """20 questions requires 16 correct."""
        assert service.compute_pass_threshold(20) == 16


# ---------------------------------------------------------------------------
# Tests: _parse_content_id
# ---------------------------------------------------------------------------


class TestParseContentId:
    """Tests for content_id parsing."""

    def test_parses_standard_format(self, service):
        """Parses {document_uuid}_v{sop_version} format."""
        uuid, version = service._parse_content_id("2025-00001_v2.0")
        assert uuid == "2025-00001"
        assert version == "2.0"

    def test_parses_complex_uuid(self, service):
        """Parses content_id with complex UUID."""
        uuid, version = service._parse_content_id("DOC-ABC-123_v1.5")
        assert uuid == "DOC-ABC-123"
        assert version == "1.5"

    def test_parses_version_with_multiple_dots(self, service):
        """Handles version strings with multiple dots."""
        uuid, version = service._parse_content_id("2025-00001_v1.2.3")
        assert uuid == "2025-00001"
        assert version == "1.2.3"


# ---------------------------------------------------------------------------
# Tests: evaluate_and_persist_enhanced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEvaluateAndPersistEnhanced:
    """Tests for enhanced evaluation with semantic grading."""

    async def test_falls_back_to_legacy_when_no_active_set(
        self, service
    ):
        """Falls back to evaluate_and_persist when no active question set."""
        session = AsyncMock()

        # Mock user exists
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = MagicMock(id=1)

        # Mock no active question set
        mock_set_result = MagicMock()
        mock_set_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(
            side_effect=[mock_user_result, mock_set_result]
        )

        # Patch the legacy method
        with patch.object(
            service, "evaluate_and_persist", new_callable=AsyncMock
        ) as mock_legacy:
            mock_legacy.return_value = MagicMock(passed=True)
            result = await service.evaluate_and_persist_enhanced(
                session=session,
                content_id="2025-00001_v1.0",
                user_id=1,
                answers={"q1": "A"},
                company_id=1,
            )

        mock_legacy.assert_called_once()

    async def test_raises_404_for_nonexistent_user(self, service):
        """Raises 404 when user does not exist."""
        session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_and_persist_enhanced(
                session=session,
                content_id="2025-00001_v1.0",
                user_id=999,
                answers={},
                company_id=1,
            )

        assert exc_info.value.status_code == 404

    async def test_raises_400_when_no_approved_questions(self, service):
        """Raises 400 when active set exists but no approved questions."""
        session = AsyncMock()

        # Mock user exists
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = MagicMock(id=1)

        # Mock active question set exists
        mock_set = MagicMock()
        mock_set.document_id = 1
        mock_set.document_version_id = 1
        mock_set_result = MagicMock()
        mock_set_result.scalar_one_or_none.return_value = mock_set

        # Mock no approved questions
        mock_questions_result = MagicMock()
        mock_questions_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )

        session.execute = AsyncMock(
            side_effect=[mock_user_result, mock_set_result, mock_questions_result]
        )

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.evaluate_and_persist_enhanced(
                session=session,
                content_id="2025-00001_v1.0",
                user_id=1,
                answers={},
                company_id=1,
            )

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Tests: register_approved_questions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRegisterApprovedQuestions:
    """Tests for registering approved questions as active question set."""

    async def test_returns_content_id_format(self, service):
        """Returns content_id in {document_uuid}_v{sop_version} format."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Mock approved count > 0
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 5

        # Mock update (deactivate previous sets) and subsequent operations
        mock_update_result = MagicMock()

        session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_update_result]
        )

        content_id = await service.register_approved_questions(
            session=session,
            document_id=1,
            document_version_id=1,
            document_uuid="2025-00001",
            sop_version="2.0",
            company_id=1,
        )

        assert content_id == "2025-00001_v2.0"

    async def test_raises_400_when_no_approved_questions(self, service):
        """Raises 400 when no approved questions exist."""
        session = AsyncMock()

        # Mock approved count = 0
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0
        session.execute = AsyncMock(return_value=mock_count_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.register_approved_questions(
                session=session,
                document_id=1,
                document_version_id=1,
                document_uuid="2025-00001",
                sop_version="1.0",
                company_id=1,
            )

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Tests: has_user_passed_enhanced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHasUserPassedEnhanced:
    """Tests for training gate OR logic (quiz OR virtual audit)."""

    async def test_returns_true_when_quiz_passed(self, service):
        """Returns True when user has a passed quiz attempt."""
        session = AsyncMock()

        # Mock passed quiz attempt found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(id=1)
        session.execute = AsyncMock(return_value=mock_result)

        result = await service.has_user_passed_enhanced(
            session=session,
            user_id=1,
            content_id="2025-00001_v1.0",
        )

        assert result is True

    async def test_returns_false_when_neither_passed(self, service):
        """Returns False when no quiz pass and no virtual audit pass."""
        session = AsyncMock()

        # Mock no passed quiz
        mock_quiz_result = MagicMock()
        mock_quiz_result.scalar_one_or_none.return_value = None

        # Mock no active question set
        mock_set_result = MagicMock()
        mock_set_result.scalar_one_or_none.return_value = None

        # Mock no document found by UUID
        mock_doc_result = MagicMock()
        mock_doc_result.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(
            side_effect=[mock_quiz_result, mock_set_result, mock_doc_result]
        )

        result = await service.has_user_passed_enhanced(
            session=session,
            user_id=1,
            content_id="2025-00001_v1.0",
        )

        assert result is False


# ---------------------------------------------------------------------------
# Tests: _create_synthetic_quiz_attempt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateSyntheticQuizAttempt:
    """Tests for bridge record creation from virtual audit."""

    async def test_creates_attempt_with_correct_fields(self, service):
        """Synthetic attempt has passed=True and correct scoring."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Mock audit session with turns
        audit_session = MagicMock()
        audit_session.id = 1
        audit_session.total_turns = 5
        audit_session.company_id = 1
        audit_session.session_data = {
            "turns": [
                {
                    "evaluation": {
                        "factual_accuracy": 0.9,
                        "completeness": 0.8,
                        "document_reference_quality": 0.7,
                    }
                },
                {
                    "evaluation": {
                        "factual_accuracy": 0.5,
                        "completeness": 0.4,
                        "document_reference_quality": 0.3,
                    }
                },
                {
                    "evaluation": {
                        "factual_accuracy": 0.8,
                        "completeness": 0.9,
                        "document_reference_quality": 0.8,
                    }
                },
            ]
        }

        attempt = await service._create_synthetic_quiz_attempt(
            session=session,
            user_id=1,
            content_id="2025-00001_v1.0",
            audit_session=audit_session,
        )

        session.add.assert_called_once()
        added_attempt = session.add.call_args[0][0]
        assert added_attempt.passed is True
        assert added_attempt.user_id == 1
        assert added_attempt.content_id == "2025-00001_v1.0"
        assert added_attempt.total_questions == 5
        assert added_attempt.answers == {}

    async def test_counts_turns_above_threshold(self, service):
        """Score counts turns with weighted score >= 0.70."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Turn 1: 0.9*0.5 + 0.8*0.3 + 0.7*0.2 = 0.45+0.24+0.14 = 0.83 (above)
        # Turn 2: 0.5*0.5 + 0.4*0.3 + 0.3*0.2 = 0.25+0.12+0.06 = 0.43 (below)
        # Turn 3: 0.8*0.5 + 0.9*0.3 + 0.8*0.2 = 0.40+0.27+0.16 = 0.83 (above)
        audit_session = MagicMock()
        audit_session.id = 1
        audit_session.total_turns = 5
        audit_session.company_id = 1
        audit_session.session_data = {
            "turns": [
                {
                    "evaluation": {
                        "factual_accuracy": 0.9,
                        "completeness": 0.8,
                        "document_reference_quality": 0.7,
                    }
                },
                {
                    "evaluation": {
                        "factual_accuracy": 0.5,
                        "completeness": 0.4,
                        "document_reference_quality": 0.3,
                    }
                },
                {
                    "evaluation": {
                        "factual_accuracy": 0.8,
                        "completeness": 0.9,
                        "document_reference_quality": 0.8,
                    }
                },
            ]
        }

        await service._create_synthetic_quiz_attempt(
            session=session,
            user_id=1,
            content_id="2025-00001_v1.0",
            audit_session=audit_session,
        )

        added_attempt = session.add.call_args[0][0]
        # 2 turns above 0.70 threshold
        assert added_attempt.score == 2

    async def test_empty_session_data_scores_zero(self, service):
        """Empty session_data results in score 0."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        audit_session = MagicMock()
        audit_session.id = 1
        audit_session.total_turns = 5
        audit_session.company_id = 1
        audit_session.session_data = {}

        await service._create_synthetic_quiz_attempt(
            session=session,
            user_id=1,
            content_id="2025-00001_v1.0",
            audit_session=audit_session,
        )

        added_attempt = session.add.call_args[0][0]
        assert added_attempt.score == 0

    async def test_none_session_data_scores_zero(self, service):
        """None session_data results in score 0."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        audit_session = MagicMock()
        audit_session.id = 1
        audit_session.total_turns = 5
        audit_session.company_id = 1
        audit_session.session_data = None

        await service._create_synthetic_quiz_attempt(
            session=session,
            user_id=1,
            content_id="2025-00001_v1.0",
            audit_session=audit_session,
        )

        added_attempt = session.add.call_args[0][0]
        assert added_attempt.score == 0
