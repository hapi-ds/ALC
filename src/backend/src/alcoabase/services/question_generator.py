"""Question Generator Service for AI-powered comprehension assessments.

This module implements:
- Async question generation dispatch via Celery tasks
- Question retrieval with filtering and pagination
- Question approval/rejection workflow
- Answer grading with multiple methods:
  - Exact match for multiple_choice and true_false
  - Semantic similarity (threshold 0.85) for fill_in_blank
  - LLM evaluation (threshold 0.70) for scenario_based
- Empty/null answer handling (confidence_score 0.0, no inference)
- Grading metadata recording (method, confidence, time_to_grade_ms)

References:
    - Design doc Section 3: Question Generator Service
    - Requirements 4.1–4.14: Automated Question Generator
    - Requirements 5.1–5.9: Automated Grading and Validation
"""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document
from alcoabase.models.training_ecosystem import (
    ContentStatus,
    GeneratedQuestion,
    QuestionType,
)
from alcoabase.services.agent_registry import AgentRegistryService
from alcoabase.services.inference_client import (
    InferenceClient,
    InferenceConnectionError,
    InferenceError,
    InferenceTimeoutError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class GradeResult:
    """Result of grading a single answer.

    Attributes:
        is_correct: Whether the answer is correct.
        confidence_score: Confidence of the grading (0.0–1.0).
        grading_method: Method used (exact, semantic, llm_evaluated).
        time_to_grade_ms: Time taken to grade in milliseconds.
        explanation: Optional explanation for LLM-evaluated answers.
    """

    is_correct: bool
    confidence_score: float
    grading_method: str
    time_to_grade_ms: int
    explanation: str | None = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Semantic similarity threshold for fill_in_blank grading
FILL_IN_BLANK_THRESHOLD = 0.85

# LLM evaluation score threshold for scenario_based grading
SCENARIO_BASED_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class QuestionGeneratorService:
    """AI-powered question generation and semantic grading.

    Provides methods for:
    - Dispatching async question generation via Celery
    - Retrieving generated questions with filtering
    - Approving/rejecting questions through coordinator review
    - Grading answers using appropriate methods per question type

    Usage:
        service = QuestionGeneratorService(
            session_factory, inference_client, agent_registry
        )
        job_id = await service.request_generation(doc_id, ver_id, company_id)
        questions, total = await service.get_questions(doc_id, company_id)
        result = await service.grade_answer(question, user_answer)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        inference_client: InferenceClient,
        agent_registry: AgentRegistryService,
    ) -> None:
        """Initialize the QuestionGeneratorService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
            inference_client: Client for vLLM inference (embeddings + chat).
            agent_registry: Registry for retrieving agent archetype configs.
        """
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._agent_registry = agent_registry

    # -----------------------------------------------------------------------
    # Generation
    # -----------------------------------------------------------------------

    async def request_generation(
        self,
        document_id: int,
        document_version_id: int,
        company_id: int,
        question_count: int = 10,
        difficulty_distribution: dict[str, float] | None = None,
    ) -> str:
        """Dispatch async question generation task.

        Validates the document exists and belongs to the company, then
        dispatches a Celery task for background generation.

        Args:
            document_id: Source document ID.
            document_version_id: Specific version to generate questions from.
            company_id: Company ID for tenant isolation.
            question_count: Number of questions to generate (5–20).
            difficulty_distribution: Optional distribution across difficulty
                levels (e.g., {"basic": 0.4, "intermediate": 0.4, "advanced": 0.2}).

        Returns:
            Job ID string for tracking the async generation.

        Raises:
            HTTPException: 404 if document not found or doesn't belong to company.
        """
        async with self._session_factory() as session:
            # Validate document exists and belongs to company
            result = await session.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            document = result.scalar_one_or_none()
            if document is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Document not found: {document_id}",
                )

        # Generate job_id
        job_id = uuid.uuid4().hex

        # Default difficulty distribution if not provided
        if difficulty_distribution is None:
            difficulty_distribution = {
                "basic": 0.4,
                "intermediate": 0.4,
                "advanced": 0.2,
            }

        # Dispatch Celery task
        from alcoabase.tasks.training_tasks import generate_training_content_task

        generate_training_content_task.apply_async(
            kwargs={
                "sop_document_uuid": str(document_id),
                "sop_version": str(document_version_id),
                "sop_text": "",  # Content retrieved by the task itself
            },
            task_id=job_id,
            queue="ai_operations",
        )

        logger.info(
            "Dispatched question generation job %s for document %d version %d",
            job_id,
            document_id,
            document_version_id,
        )

        return job_id

    # -----------------------------------------------------------------------
    # Retrieval
    # -----------------------------------------------------------------------

    async def get_questions(
        self,
        document_id: int,
        company_id: int,
        status: str | None = None,
        difficulty_level: str | None = None,
        question_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[GeneratedQuestion], int]:
        """Retrieve generated questions with filtering and pagination.

        Args:
            document_id: Source document ID.
            company_id: Company ID for tenant isolation.
            status: Optional filter by content status.
            difficulty_level: Optional filter by difficulty level.
            question_type: Optional filter by question type.
            limit: Maximum number of results (default 20).
            offset: Pagination offset (default 0).

        Returns:
            Tuple of (list of questions, total count).
        """
        async with self._session_factory() as session:
            # Build base query
            base_filter = [
                GeneratedQuestion.document_id == document_id,
                GeneratedQuestion.company_id == company_id,
            ]

            if status is not None:
                base_filter.append(GeneratedQuestion.status == status)
            if difficulty_level is not None:
                base_filter.append(
                    GeneratedQuestion.difficulty_level == difficulty_level
                )
            if question_type is not None:
                base_filter.append(
                    GeneratedQuestion.question_type == question_type
                )

            # Get total count
            count_stmt = select(func.count(GeneratedQuestion.id)).where(
                *base_filter
            )
            count_result = await session.execute(count_stmt)
            total = count_result.scalar_one()

            # Get paginated results
            query_stmt = (
                select(GeneratedQuestion)
                .where(*base_filter)
                .order_by(GeneratedQuestion.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(query_stmt)
            questions = list(result.scalars().all())

            return questions, total

    # -----------------------------------------------------------------------
    # Approval / Rejection
    # -----------------------------------------------------------------------

    async def approve_question(
        self,
        question_id: int,
        reviewer_id: int,
        company_id: int,
    ) -> GeneratedQuestion:
        """Approve a generated question for use in assessments.

        Validates the question exists, belongs to the company, and is
        currently in pending_review status.

        Args:
            question_id: ID of the question to approve.
            reviewer_id: ID of the reviewing user.
            company_id: Company ID for tenant isolation.

        Returns:
            The updated GeneratedQuestion record.

        Raises:
            HTTPException: 404 if question not found.
            HTTPException: 400 if question is not in pending_review status.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(GeneratedQuestion).where(
                    GeneratedQuestion.id == question_id,
                    GeneratedQuestion.company_id == company_id,
                )
            )
            question = result.scalar_one_or_none()

            if question is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Question not found: {question_id}",
                )

            if question.status != ContentStatus.PENDING_REVIEW.value:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Question {question_id} is not in pending_review "
                        f"status (current: {question.status})"
                    ),
                )

            question.status = ContentStatus.APPROVED.value
            question.reviewed_by = reviewer_id
            question.reviewed_at = datetime.now(UTC)

            await session.commit()
            await session.refresh(question)

            logger.info(
                "Question %d approved by reviewer %d",
                question_id,
                reviewer_id,
            )

            return question

    async def reject_question(
        self,
        question_id: int,
        reviewer_id: int,
        company_id: int,
    ) -> GeneratedQuestion:
        """Reject a generated question.

        Validates the question exists, belongs to the company, and is
        currently in pending_review status.

        Args:
            question_id: ID of the question to reject.
            reviewer_id: ID of the reviewing user.
            company_id: Company ID for tenant isolation.

        Returns:
            The updated GeneratedQuestion record.

        Raises:
            HTTPException: 404 if question not found.
            HTTPException: 400 if question is not in pending_review status.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(GeneratedQuestion).where(
                    GeneratedQuestion.id == question_id,
                    GeneratedQuestion.company_id == company_id,
                )
            )
            question = result.scalar_one_or_none()

            if question is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Question not found: {question_id}",
                )

            if question.status != ContentStatus.PENDING_REVIEW.value:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Question {question_id} is not in pending_review "
                        f"status (current: {question.status})"
                    ),
                )

            question.status = ContentStatus.REJECTED.value
            question.reviewed_by = reviewer_id
            question.reviewed_at = datetime.now(UTC)

            await session.commit()
            await session.refresh(question)

            logger.info(
                "Question %d rejected by reviewer %d",
                question_id,
                reviewer_id,
            )

            return question

    # -----------------------------------------------------------------------
    # Grading
    # -----------------------------------------------------------------------

    async def grade_answer(
        self,
        question: GeneratedQuestion,
        user_answer: str | None,
    ) -> GradeResult:
        """Grade a single answer using the appropriate method.

        Routes to the correct grading method based on question_type:
        - multiple_choice / true_false → exact match
        - fill_in_blank → semantic similarity (threshold 0.85)
        - scenario_based → LLM evaluation (threshold 0.70)

        Empty/null answers are marked incorrect with confidence_score 0.0
        without invoking any inference.

        Args:
            question: The GeneratedQuestion being answered.
            user_answer: The user's submitted answer (may be None or empty).

        Returns:
            GradeResult with correctness, confidence, method, and timing.
        """
        start_time = time.perf_counter()

        # Handle empty/null answers without invoking inference
        if not user_answer or user_answer.strip() == "":
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return GradeResult(
                is_correct=False,
                confidence_score=0.0,
                grading_method="exact",
                time_to_grade_ms=elapsed_ms,
            )

        # Route to appropriate grading method
        question_type = question.question_type
        if isinstance(question_type, QuestionType):
            question_type_value = question_type.value
        else:
            question_type_value = str(question_type)

        if question_type_value in (
            QuestionType.MULTIPLE_CHOICE.value,
            QuestionType.TRUE_FALSE.value,
        ):
            # Exact match for MC and T/F
            is_correct = user_answer.strip() == question.correct_answer.strip()
            confidence_score = 1.0 if is_correct else 0.0
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return GradeResult(
                is_correct=is_correct,
                confidence_score=confidence_score,
                grading_method="exact",
                time_to_grade_ms=elapsed_ms,
            )

        elif question_type_value == QuestionType.FILL_IN_BLANK.value:
            # Semantic similarity for fill_in_blank
            passed, score = await self.grade_fill_in_blank(
                question.correct_answer, user_answer
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return GradeResult(
                is_correct=passed,
                confidence_score=score,
                grading_method="semantic",
                time_to_grade_ms=elapsed_ms,
            )

        elif question_type_value == QuestionType.SCENARIO_BASED.value:
            # LLM evaluation for scenario_based
            passed, score, explanation = await self.grade_scenario_based(
                question.question_text,
                question.correct_answer,
                question.sop_section_ref,
                user_answer,
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return GradeResult(
                is_correct=passed,
                confidence_score=score,
                grading_method="llm_evaluated",
                time_to_grade_ms=elapsed_ms,
                explanation=explanation,
            )

        else:
            # Unknown question type — fallback to exact match
            is_correct = (
                user_answer.strip().lower()
                == question.correct_answer.strip().lower()
            )
            confidence_score = 1.0 if is_correct else 0.0
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return GradeResult(
                is_correct=is_correct,
                confidence_score=confidence_score,
                grading_method="exact",
                time_to_grade_ms=elapsed_ms,
            )

    async def grade_fill_in_blank(
        self,
        correct_answer: str,
        user_answer: str,
    ) -> tuple[bool, float]:
        """Grade a fill-in-blank answer using semantic similarity.

        Computes cosine similarity between the user's answer and the
        correct answer via the embedding model. Falls back to exact
        match if inference is unavailable.

        Args:
            correct_answer: The expected correct answer.
            user_answer: The user's submitted answer.

        Returns:
            Tuple of (passed, similarity_score).
            passed is True if similarity >= 0.85 threshold.
        """
        # Normalize inputs (case-insensitive comparison prior to embedding)
        normalized_correct = correct_answer.strip().lower()
        normalized_user = user_answer.strip().lower()

        # Exact match check first (fast path)
        if normalized_correct == normalized_user:
            return True, 1.0

        try:
            from alcoabase.config import get_settings

            settings = get_settings()

            # Get embeddings for both answers
            embeddings = await self._inference_client.create_embeddings(
                model=settings.model_embedding_name,
                inputs=[normalized_correct, normalized_user],
            )

            # Compute cosine similarity
            similarity = self._cosine_similarity(embeddings[0], embeddings[1])

            passed = similarity >= FILL_IN_BLANK_THRESHOLD
            return passed, similarity

        except (
            InferenceError,
            InferenceTimeoutError,
            InferenceConnectionError,
            Exception,
        ) as e:
            logger.warning(
                "Embedding inference unavailable for fill_in_blank grading, "
                "falling back to exact match: %s",
                str(e),
            )
            # Fallback to case-insensitive exact match
            is_exact = normalized_correct == normalized_user
            return is_exact, 1.0 if is_exact else 0.0

    async def grade_scenario_based(
        self,
        question_text: str,
        correct_answer: str,
        source_paragraph: str,
        user_answer: str,
    ) -> tuple[bool, float, str]:
        """Grade a scenario-based answer using LLM evaluation.

        Sends the question, correct answer, source paragraph, and user
        answer to the LLM for evaluation. Falls back to exact match if
        inference is unavailable.

        Args:
            question_text: The original question text.
            correct_answer: The expected correct answer.
            source_paragraph: Source document paragraph for context.
            user_answer: The user's submitted answer.

        Returns:
            Tuple of (passed, score, explanation).
            passed is True if LLM evaluation score >= 0.70 threshold.
        """
        try:
            from alcoabase.config import get_settings

            settings = get_settings()

            evaluation_prompt = (
                "You are an expert evaluator for training assessments in a "
                "regulated environment. Evaluate the user's answer against "
                "the correct answer and source material.\n\n"
                f"Question: {question_text}\n\n"
                f"Correct Answer: {correct_answer}\n\n"
                f"Source Material: {source_paragraph}\n\n"
                f"User's Answer: {user_answer}\n\n"
                "Evaluate the user's answer on a scale of 0.0 to 1.0 based on:\n"
                "- Factual accuracy compared to the correct answer\n"
                "- Completeness of the response\n"
                "- Demonstration of understanding of the source material\n\n"
                "Respond in exactly this format:\n"
                "SCORE: <float between 0.0 and 1.0>\n"
                "EXPLANATION: <brief explanation of the evaluation>"
            )

            response = await self._inference_client.chat_completion(
                model=settings.model_chat_name,
                messages=[
                    {"role": "system", "content": "You are a precise evaluator."},
                    {"role": "user", "content": evaluation_prompt},
                ],
                temperature=0.1,
                max_tokens=256,
                timeout=30.0,
            )

            # Parse the LLM response
            score, explanation = self._parse_evaluation_response(response)

            passed = score >= SCENARIO_BASED_THRESHOLD
            return passed, score, explanation

        except (
            InferenceError,
            InferenceTimeoutError,
            InferenceConnectionError,
            Exception,
        ) as e:
            logger.warning(
                "LLM inference unavailable for scenario_based grading, "
                "falling back to exact match: %s",
                str(e),
            )
            # Fallback to case-insensitive exact match
            normalized_correct = correct_answer.strip().lower()
            normalized_user = user_answer.strip().lower()
            is_exact = normalized_correct == normalized_user
            return is_exact, 1.0 if is_exact else 0.0, ""

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec_a: First embedding vector.
            vec_b: Second embedding vector.

        Returns:
            Cosine similarity value between -1.0 and 1.0.
        """
        import math

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        magnitude_a = math.sqrt(sum(a * a for a in vec_a))
        magnitude_b = math.sqrt(sum(b * b for b in vec_b))

        if magnitude_a == 0.0 or magnitude_b == 0.0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    @staticmethod
    def _parse_evaluation_response(response: str) -> tuple[float, str]:
        """Parse the LLM evaluation response to extract score and explanation.

        Expected format:
            SCORE: <float>
            EXPLANATION: <text>

        Args:
            response: Raw LLM response text.

        Returns:
            Tuple of (score, explanation). Defaults to (0.0, "") on parse failure.
        """
        score = 0.0
        explanation = ""

        lines = response.strip().split("\n")
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.upper().startswith("SCORE:"):
                try:
                    score_str = line_stripped.split(":", 1)[1].strip()
                    score = float(score_str)
                    # Clamp to valid range
                    score = max(0.0, min(1.0, score))
                except (ValueError, IndexError):
                    score = 0.0
            elif line_stripped.upper().startswith("EXPLANATION:"):
                explanation = line_stripped.split(":", 1)[1].strip()

        return score, explanation
