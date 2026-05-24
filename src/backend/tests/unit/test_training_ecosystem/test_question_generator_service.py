"""Unit tests for QuestionGeneratorService.

Tests question validation, difficulty distribution enforcement,
and grading method routing.

Requirements: 4.1–4.14, 5.1–5.9
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.training_ecosystem import (
    ContentStatus,
    GeneratedQuestion,
    QuestionType,
)
from alcoabase.services.question_generator import (
    FILL_IN_BLANK_THRESHOLD,
    SCENARIO_BASED_THRESHOLD,
    QuestionGeneratorService,
    GradeResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()

    mock_factory = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_factory.return_value = mock_cm
    mock_factory._session = session
    return mock_factory


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(return_value="SCORE: 0.85\nEXPLANATION: Good answer.")
    client.create_embeddings = AsyncMock(return_value=[
        [0.1, 0.2, 0.3, 0.4, 0.5],
        [0.1, 0.2, 0.3, 0.4, 0.5],
    ])
    return client


@pytest.fixture
def mock_agent_registry():
    """Create a mock AgentRegistryService."""
    registry = MagicMock()
    registry._load_archetype_raw = MagicMock(return_value={
        "archetype": "Educational Specialist",
        "system_prompt": "You are an Educational Specialist.",
        "contextual_tuning": {"temperature": 0.6, "max_tokens": 8192},
    })
    return registry


@pytest.fixture
def service(mock_session_factory, mock_inference_client, mock_agent_registry):
    """Create a QuestionGeneratorService with mocked dependencies."""
    return QuestionGeneratorService(
        session_factory=mock_session_factory,
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
    )


@pytest.fixture
def mc_question():
    """Create a multiple-choice question fixture."""
    q = MagicMock(spec=GeneratedQuestion)
    q.id = 1
    q.question_text = "What is the correct PPE for this procedure?"
    q.question_type = QuestionType.MULTIPLE_CHOICE
    q.correct_answer = "B"
    q.distractors = ["A", "C", "D"]
    q.sop_section_ref = "Section 3.1"
    q.company_id = 1
    return q


@pytest.fixture
def tf_question():
    """Create a true/false question fixture."""
    q = MagicMock(spec=GeneratedQuestion)
    q.id = 2
    q.question_text = "Gloves must be worn at all times."
    q.question_type = QuestionType.TRUE_FALSE
    q.correct_answer = "True"
    q.sop_section_ref = "Section 2.1"
    q.company_id = 1
    return q


@pytest.fixture
def fill_blank_question():
    """Create a fill-in-blank question fixture."""
    q = MagicMock(spec=GeneratedQuestion)
    q.id = 3
    q.question_text = "The process must be completed within ___ hours."
    q.question_type = QuestionType.FILL_IN_BLANK
    q.correct_answer = "24 hours"
    q.sop_section_ref = "Section 4.2"
    q.company_id = 1
    return q


@pytest.fixture
def scenario_question():
    """Create a scenario-based question fixture."""
    q = MagicMock(spec=GeneratedQuestion)
    q.id = 4
    q.question_text = "A spill occurs in the lab. What steps do you take?"
    q.question_type = QuestionType.SCENARIO_BASED
    q.correct_answer = "Evacuate, contain, report to supervisor."
    q.sop_section_ref = "Section 5.3"
    q.company_id = 1
    return q


# ---------------------------------------------------------------------------
# Tests: grade_answer — routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGradeAnswerRouting:
    """Tests for grading method routing based on question type."""

    async def test_empty_answer_returns_incorrect_without_inference(
        self, service, mc_question, mock_inference_client
    ):
        """Empty answer is marked incorrect with confidence 0.0, no inference."""
        result = await service.grade_answer(mc_question, "")

        assert result.is_correct is False
        assert result.confidence_score == 0.0
        assert result.grading_method == "exact"
        mock_inference_client.chat_completion.assert_not_called()
        mock_inference_client.create_embeddings.assert_not_called()

    async def test_none_answer_returns_incorrect(self, service, mc_question):
        """None answer is marked incorrect without inference."""
        result = await service.grade_answer(mc_question, None)

        assert result.is_correct is False
        assert result.confidence_score == 0.0
        assert result.grading_method == "exact"

    async def test_whitespace_only_answer_returns_incorrect(
        self, service, mc_question
    ):
        """Whitespace-only answer is treated as empty."""
        result = await service.grade_answer(mc_question, "   ")

        assert result.is_correct is False
        assert result.confidence_score == 0.0

    async def test_multiple_choice_uses_exact_match(
        self, service, mc_question
    ):
        """Multiple choice uses exact string matching."""
        result = await service.grade_answer(mc_question, "B")

        assert result.is_correct is True
        assert result.confidence_score == 1.0
        assert result.grading_method == "exact"

    async def test_multiple_choice_wrong_answer(self, service, mc_question):
        """Wrong MC answer returns incorrect with confidence 0.0."""
        result = await service.grade_answer(mc_question, "A")

        assert result.is_correct is False
        assert result.confidence_score == 0.0
        assert result.grading_method == "exact"

    async def test_true_false_uses_exact_match(self, service, tf_question):
        """True/false uses exact string matching."""
        result = await service.grade_answer(tf_question, "True")

        assert result.is_correct is True
        assert result.confidence_score == 1.0
        assert result.grading_method == "exact"

    async def test_true_false_wrong_answer(self, service, tf_question):
        """Wrong T/F answer returns incorrect."""
        result = await service.grade_answer(tf_question, "False")

        assert result.is_correct is False
        assert result.confidence_score == 0.0

    async def test_fill_in_blank_uses_semantic_grading(
        self, service, fill_blank_question
    ):
        """Fill-in-blank routes to semantic similarity grading."""
        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_embedding_name="test-embed"
            )
            result = await service.grade_answer(
                fill_blank_question, "24 hours"
            )

        assert result.grading_method == "semantic"

    async def test_scenario_based_uses_llm_evaluation(
        self, service, scenario_question
    ):
        """Scenario-based routes to LLM evaluation grading."""
        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_chat_name="test-model"
            )
            result = await service.grade_answer(
                scenario_question, "Evacuate the area and report."
            )

        assert result.grading_method == "llm_evaluated"

    async def test_grade_answer_records_time(self, service, mc_question):
        """All grade results include time_to_grade_ms."""
        result = await service.grade_answer(mc_question, "B")

        assert result.time_to_grade_ms >= 0


# ---------------------------------------------------------------------------
# Tests: grade_fill_in_blank
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGradeFillInBlank:
    """Tests for fill-in-blank semantic grading."""

    async def test_exact_match_returns_true_with_score_1(self, service):
        """Exact match (case-insensitive) returns passed with score 1.0."""
        passed, score = await service.grade_fill_in_blank(
            "24 hours", "24 hours"
        )

        assert passed is True
        assert score == 1.0

    async def test_case_insensitive_exact_match(self, service):
        """Case differences still match exactly."""
        passed, score = await service.grade_fill_in_blank(
            "Sodium Chloride", "sodium chloride"
        )

        assert passed is True
        assert score == 1.0

    async def test_high_similarity_passes(
        self, service, mock_inference_client
    ):
        """Similarity >= 0.85 threshold passes."""
        # Mock embeddings that produce high similarity
        mock_inference_client.create_embeddings.return_value = [
            [1.0, 0.0, 0.0],
            [0.95, 0.05, 0.0],
        ]

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_embedding_name="test-embed"
            )
            passed, score = await service.grade_fill_in_blank(
                "correct answer", "close answer"
            )

        assert passed is True
        assert score >= FILL_IN_BLANK_THRESHOLD

    async def test_low_similarity_fails(self, service, mock_inference_client):
        """Similarity < 0.85 threshold fails."""
        # Mock embeddings that produce low similarity
        mock_inference_client.create_embeddings.return_value = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ]

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_embedding_name="test-embed"
            )
            passed, score = await service.grade_fill_in_blank(
                "correct answer", "wrong answer"
            )

        assert passed is False
        assert score < FILL_IN_BLANK_THRESHOLD

    async def test_inference_unavailable_falls_back_to_exact(
        self, service, mock_inference_client
    ):
        """When inference fails, falls back to exact match."""
        mock_inference_client.create_embeddings.side_effect = Exception(
            "Connection refused"
        )

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_embedding_name="test-embed"
            )
            passed, score = await service.grade_fill_in_blank(
                "answer", "different"
            )

        assert passed is False
        assert score == 0.0

    async def test_inference_unavailable_exact_match_passes(
        self, service, mock_inference_client
    ):
        """Fallback exact match still passes on identical strings."""
        mock_inference_client.create_embeddings.side_effect = Exception(
            "Timeout"
        )

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_embedding_name="test-embed"
            )
            passed, score = await service.grade_fill_in_blank(
                "answer", "answer"
            )

        assert passed is True
        assert score == 1.0


# ---------------------------------------------------------------------------
# Tests: grade_scenario_based
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGradeScenarioBased:
    """Tests for scenario-based LLM evaluation grading."""

    async def test_high_score_passes(self, service, mock_inference_client):
        """LLM score >= 0.70 passes."""
        mock_inference_client.chat_completion.return_value = (
            "SCORE: 0.85\nEXPLANATION: Excellent response."
        )

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_chat_name="test-model"
            )
            passed, score, explanation = await service.grade_scenario_based(
                "What do you do?",
                "Evacuate and report.",
                "Section 5 describes evacuation procedures.",
                "I would evacuate and report to my supervisor.",
            )

        assert passed is True
        assert score == 0.85
        assert "Excellent" in explanation

    async def test_low_score_fails(self, service, mock_inference_client):
        """LLM score < 0.70 fails."""
        mock_inference_client.chat_completion.return_value = (
            "SCORE: 0.40\nEXPLANATION: Incomplete response."
        )

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_chat_name="test-model"
            )
            passed, score, explanation = await service.grade_scenario_based(
                "What do you do?",
                "Evacuate and report.",
                "Section 5 describes evacuation procedures.",
                "I don't know.",
            )

        assert passed is False
        assert score == 0.40

    async def test_inference_unavailable_falls_back_to_exact(
        self, service, mock_inference_client
    ):
        """When LLM fails, falls back to exact match."""
        mock_inference_client.chat_completion.side_effect = Exception(
            "Service unavailable"
        )

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_chat_name="test-model"
            )
            passed, score, explanation = await service.grade_scenario_based(
                "Question?",
                "Correct answer",
                "Source paragraph",
                "Wrong answer",
            )

        assert passed is False
        assert score == 0.0
        assert explanation == ""

    async def test_inference_fallback_exact_match_passes(
        self, service, mock_inference_client
    ):
        """Fallback exact match passes on identical strings."""
        mock_inference_client.chat_completion.side_effect = Exception(
            "Timeout"
        )

        with patch("alcoabase.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_chat_name="test-model"
            )
            passed, score, explanation = await service.grade_scenario_based(
                "Question?",
                "correct answer",
                "Source paragraph",
                "correct answer",
            )

        assert passed is True
        assert score == 1.0


# ---------------------------------------------------------------------------
# Tests: _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Tests for the cosine similarity helper."""

    def test_identical_vectors_return_1(self, service):
        """Identical vectors have similarity 1.0."""
        result = service._cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert abs(result - 1.0) < 1e-6

    def test_orthogonal_vectors_return_0(self, service):
        """Orthogonal vectors have similarity 0.0."""
        result = service._cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0])
        assert abs(result) < 1e-6

    def test_opposite_vectors_return_negative_1(self, service):
        """Opposite vectors have similarity -1.0."""
        result = service._cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(result - (-1.0)) < 1e-6

    def test_zero_vector_returns_0(self, service):
        """Zero vector returns 0.0 (avoids division by zero)."""
        result = service._cosine_similarity([0.0, 0.0], [1.0, 0.0])
        assert result == 0.0


# ---------------------------------------------------------------------------
# Tests: _parse_evaluation_response
# ---------------------------------------------------------------------------


class TestParseEvaluationResponse:
    """Tests for parsing LLM evaluation responses."""

    def test_parses_valid_response(self, service):
        """Valid SCORE/EXPLANATION format is parsed correctly."""
        response = "SCORE: 0.85\nEXPLANATION: Good answer with detail."
        score, explanation = service._parse_evaluation_response(response)

        assert score == 0.85
        assert "Good answer" in explanation

    def test_parses_score_at_boundary(self, service):
        """Score at 0.70 boundary is parsed correctly."""
        response = "SCORE: 0.70\nEXPLANATION: Meets threshold."
        score, explanation = service._parse_evaluation_response(response)

        assert score == 0.70

    def test_handles_malformed_response(self, service):
        """Malformed response returns 0.0 score."""
        response = "This is not in the expected format."
        score, explanation = service._parse_evaluation_response(response)

        assert score == 0.0


# ---------------------------------------------------------------------------
# Tests: approve/reject question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestApproveRejectQuestion:
    """Tests for question approval and rejection flows."""

    async def test_approve_updates_status(self, service, mock_session_factory):
        """Approving a pending_review question sets status to approved."""
        session = mock_session_factory._session

        mock_question = MagicMock(spec=GeneratedQuestion)
        mock_question.id = 1
        mock_question.status = ContentStatus.PENDING_REVIEW.value
        mock_question.company_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_question
        session.execute = AsyncMock(return_value=mock_result)

        result = await service.approve_question(
            question_id=1, reviewer_id=1, company_id=1
        )

        assert mock_question.status == ContentStatus.APPROVED.value
        assert mock_question.reviewed_by == 1

    async def test_reject_updates_status(self, service, mock_session_factory):
        """Rejecting a pending_review question sets status to rejected."""
        session = mock_session_factory._session

        mock_question = MagicMock(spec=GeneratedQuestion)
        mock_question.id = 2
        mock_question.status = ContentStatus.PENDING_REVIEW.value
        mock_question.company_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_question
        session.execute = AsyncMock(return_value=mock_result)

        result = await service.reject_question(
            question_id=2, reviewer_id=1, company_id=1
        )

        assert mock_question.status == ContentStatus.REJECTED.value
        assert mock_question.reviewed_by == 1

    async def test_approve_non_pending_raises_error(
        self, service, mock_session_factory
    ):
        """Approving an already-approved question raises 400."""
        session = mock_session_factory._session

        mock_question = MagicMock(spec=GeneratedQuestion)
        mock_question.id = 3
        mock_question.status = ContentStatus.APPROVED.value
        mock_question.company_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_question
        session.execute = AsyncMock(return_value=mock_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.approve_question(
                question_id=3, reviewer_id=1, company_id=1
            )

        assert exc_info.value.status_code == 400

    async def test_approve_nonexistent_raises_404(
        self, service, mock_session_factory
    ):
        """Approving a non-existent question raises 404."""
        session = mock_session_factory._session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.approve_question(
                question_id=999, reviewer_id=1, company_id=1
            )

        assert exc_info.value.status_code == 404
