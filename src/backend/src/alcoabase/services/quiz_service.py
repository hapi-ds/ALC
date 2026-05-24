"""Quiz Service for comprehension quiz evaluation and persistence.

This module implements:
- Quiz answer evaluation with exact string matching
- Score computation and pass/fail determination
- Quiz attempt persistence for audit trail
- Quiz pass status verification for gate enforcement
- Quiz attempt history retrieval
- Enhanced evaluation with semantic grading for AI-generated questions
- Registration of approved AI-generated question sets
- Training gate OR logic (quiz pass OR virtual audit pass)

References:
    - Design doc: QuizService component
    - Requirements 1: Quiz Attempt Data Model
    - Requirements 2: Quiz Submission API Endpoint
    - Requirements 3: Quiz Results API Endpoint
    - Requirements 4: Quiz Pass Verification API Endpoint
    - Requirements 11.1–11.8: Integration with Training-Gated Access Control
"""

import logging
import math
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.training import QuizAttempt
from alcoabase.models.training_ecosystem import (
    ActiveQuestionSet,
    ContentStatus,
    GeneratedQuestion,
    SessionStatus,
    VirtualAuditSession,
)
from alcoabase.models.user import User
from alcoabase.services.training_content_generator import (
    TrainingContentGenerator,
)

if TYPE_CHECKING:
    from alcoabase.services.question_generator import (
        QuestionGeneratorService,
    )

logger = logging.getLogger(__name__)


class QuizService:
    """Service for quiz evaluation, scoring, and persistence.

    Provides methods for:
    - Evaluating quiz submissions against correct answers
    - Computing pass/fail status using the 80% threshold
    - Persisting quiz attempt records for audit compliance
    - Checking quiz pass status for gate enforcement
    - Retrieving quiz attempt history
    - Enhanced evaluation with semantic grading (fill_in_blank, scenario_based)
    - Registering approved AI-generated questions as active question sets
    - Training gate OR logic (quiz pass OR virtual audit pass)

    Usage:
        service = QuizService(content_generator)
        attempt = await service.evaluate_and_persist(
            session, content_id, user_id, answers, company_id
        )
    """

    def __init__(
        self,
        content_generator: TrainingContentGenerator,
        question_generator_service: "QuestionGeneratorService | None" = None,
    ) -> None:
        """Initialize the QuizService.

        Args:
            content_generator: TrainingContentGenerator instance for
                retrieving training content and quiz questions.
            question_generator_service: Optional QuestionGeneratorService
                for semantic grading of AI-generated questions.
        """
        self._content_generator = content_generator
        self._question_generator_service = question_generator_service

    def compute_pass_threshold(self, total_questions: int) -> int:
        """Compute the minimum score required to pass the quiz.

        The passing threshold is 80% of total questions, rounded up
        to the nearest integer.

        Args:
            total_questions: Total number of questions in the quiz.
                Must be >= 1.

        Returns:
            Minimum score required to pass.

        Raises:
            ValueError: If total_questions is less than 1.
        """
        if total_questions < 1:
            raise ValueError(
                "total_questions must be at least 1"
            )
        return math.ceil(total_questions * 0.8)

    async def evaluate_and_persist(
        self,
        session: AsyncSession,
        content_id: str,
        user_id: int,
        answers: dict[str, str],
        company_id: int,
    ) -> QuizAttempt:
        """Evaluate quiz answers and persist the attempt record.

        Retrieves the training content for the given content_id, validates
        that the content is in approved status, compares each submitted
        answer against the correct answer using exact string matching,
        computes the score, determines pass/fail, and persists a
        QuizAttempt record.

        Args:
            session: Active async database session.
            content_id: Training content identifier
                (format: {sop_document_uuid}_v{sop_version}).
            user_id: ID of the user submitting the quiz.
            answers: Mapping of question_id to selected answer string.
            company_id: Company ID for tenant isolation.

        Returns:
            The persisted QuizAttempt record.

        Raises:
            HTTPException: 404 if training content not found.
            HTTPException: 400 if training content is not in approved status.
            HTTPException: 404 if user not found.
        """
        # Verify user exists
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=404,
                detail=f"User not found: {user_id}",
            )

        # Retrieve training content
        content = self._content_generator.get_content(content_id)
        if content is None:
            raise HTTPException(
                status_code=404,
                detail=f"Training content not found: {content_id}",
            )

        # Validate content is approved
        if content.status.value != "approved":
            raise HTTPException(
                status_code=400,
                detail="Quiz is not available: training content is not in approved status",
            )

        # Compute score via exact string matching
        quiz_questions = content.quiz_questions
        total_questions = len(quiz_questions)

        if total_questions < 1:
            raise HTTPException(
                status_code=400,
                detail="Quiz has no questions and cannot be attempted",
            )

        score = 0
        for question in quiz_questions:
            submitted_answer = answers.get(question.question_id)
            if submitted_answer is not None and submitted_answer == question.correct_answer:
                score += 1

        # Determine pass/fail
        pass_threshold = self.compute_pass_threshold(total_questions)
        passed = score >= pass_threshold

        # Persist QuizAttempt
        attempt = QuizAttempt(
            user_id=user_id,
            content_id=content_id,
            sop_document_uuid=content.sop_document_uuid,
            sop_version=content.sop_version,
            answers=answers,
            score=score,
            total_questions=total_questions,
            passed=passed,
            company_id=company_id,
        )
        session.add(attempt)
        await session.flush()

        return attempt

    async def has_user_passed(
        self,
        session: AsyncSession,
        user_id: int,
        content_id: str,
    ) -> bool:
        """Check if a user has passed the quiz for a specific content.

        Checks for the existence of any QuizAttempt record with
        passed=True for the given user and content_id.

        Args:
            session: Active async database session.
            user_id: The user's primary key.
            content_id: Training content identifier.

        Returns:
            True if at least one passing attempt exists, False otherwise.
        """
        result = await session.execute(
            select(QuizAttempt.id)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.content_id == content_id,
                QuizAttempt.passed.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_best_score(
        self,
        session: AsyncSession,
        user_id: int,
        content_id: str,
    ) -> int | None:
        """Get the highest score among all attempts for a user and content.

        Args:
            session: Active async database session.
            user_id: The user's primary key.
            content_id: Training content identifier.

        Returns:
            The maximum score, or None if no attempts exist.
        """
        result = await session.execute(
            select(func.max(QuizAttempt.score)).where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.content_id == content_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_user_results(
        self,
        session: AsyncSession,
        user_id: int,
        content_id: str,
        limit: int = 50,
    ) -> list[QuizAttempt]:
        """Get quiz attempt history for a user and content.

        Returns attempts ordered by attempted_at descending (most recent
        first), limited to the specified number of results.

        Args:
            session: Active async database session.
            user_id: The user's primary key.
            content_id: Training content identifier.
            limit: Maximum number of results to return (default 50).

        Returns:
            List of QuizAttempt records ordered by attempted_at descending.
        """
        result = await session.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.content_id == content_id,
            )
            .order_by(desc(QuizAttempt.attempted_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------
    # Enhanced Methods for AI-Generated Questions (Requirements 11.1–11.8)
    # -------------------------------------------------------------------

    async def evaluate_and_persist_enhanced(
        self,
        session: AsyncSession,
        content_id: str,
        user_id: int,
        answers: dict[str, str],
        company_id: int,
    ) -> QuizAttempt:
        """Enhanced evaluation supporting semantic grading for AI-generated questions.

        Routes each answer to the appropriate grading method based on question type:
        - multiple_choice / true_false → exact match (existing behavior)
        - fill_in_blank → semantic similarity (threshold 0.85)
        - scenario_based → LLM evaluation (threshold 0.70)

        Falls back to exact match if inference is unavailable.

        Args:
            session: Active async database session.
            content_id: Training content identifier
                (format: {document_uuid}_v{sop_version}).
            user_id: ID of the user submitting the quiz.
            answers: Mapping of question_id (str) to user answer string.
            company_id: Company ID for tenant isolation.

        Returns:
            The persisted QuizAttempt record.

        Raises:
            HTTPException: 404 if user not found.
            HTTPException: 404 if no active question set found for content_id.
            HTTPException: 400 if no approved questions available.
        """
        # Verify user exists
        user_result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=404,
                detail=f"User not found: {user_id}",
            )

        # Find active question set for this content_id
        active_set_result = await session.execute(
            select(ActiveQuestionSet).where(
                ActiveQuestionSet.content_id == content_id,
                ActiveQuestionSet.is_active.is_(True),
                ActiveQuestionSet.company_id == company_id,
            )
        )
        active_set = active_set_result.scalar_one_or_none()

        if active_set is None:
            # Fallback to existing evaluate_and_persist for legacy content
            return await self.evaluate_and_persist(
                session, content_id, user_id, answers, company_id
            )

        # Retrieve approved questions for this document version
        questions_result = await session.execute(
            select(GeneratedQuestion).where(
                GeneratedQuestion.document_id == active_set.document_id,
                GeneratedQuestion.document_version_id
                == active_set.document_version_id,
                GeneratedQuestion.company_id == company_id,
                GeneratedQuestion.status == ContentStatus.APPROVED.value,
            )
        )
        questions = list(questions_result.scalars().all())

        if not questions:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No approved questions available for this assessment. "
                    "Please contact your training coordinator."
                ),
            )

        total_questions = len(questions)
        score = 0

        # Grade each answer
        for question in questions:
            question_id_str = str(question.id)
            user_answer = answers.get(question_id_str)

            if not user_answer or user_answer.strip() == "":
                # Empty answer — mark incorrect without inference
                continue

            # Route to appropriate grading method
            if self._question_generator_service is not None:
                try:
                    grade_result = (
                        await self._question_generator_service.grade_answer(
                            question, user_answer
                        )
                    )
                    if grade_result.is_correct:
                        score += 1
                except Exception:
                    # Fallback to exact match if grading fails
                    logger.warning(
                        "Semantic grading failed for question %d, "
                        "falling back to exact match",
                        question.id,
                    )
                    if (
                        user_answer.strip()
                        == question.correct_answer.strip()
                    ):
                        score += 1
            else:
                # No question generator service — use exact match
                if user_answer.strip() == question.correct_answer.strip():
                    score += 1

        # Determine pass/fail using 80% threshold
        pass_threshold = self.compute_pass_threshold(total_questions)
        passed = score >= pass_threshold

        # Parse content_id to extract sop_document_uuid and sop_version
        sop_document_uuid, sop_version = self._parse_content_id(content_id)

        # Persist QuizAttempt
        attempt = QuizAttempt(
            user_id=user_id,
            content_id=content_id,
            sop_document_uuid=sop_document_uuid,
            sop_version=sop_version,
            answers=answers,
            score=score,
            total_questions=total_questions,
            passed=passed,
            company_id=company_id,
        )
        session.add(attempt)
        await session.flush()

        return attempt

    async def register_approved_questions(
        self,
        session: AsyncSession,
        document_id: int,
        document_version_id: int,
        document_uuid: str,
        sop_version: str,
        company_id: int,
    ) -> str:
        """Register approved AI-generated questions as the active question set.

        Creates an ActiveQuestionSet record linking the content_id to the
        document and version. Marks any previous active sets for the same
        content_id as inactive.

        Args:
            session: Active async database session.
            document_id: Source document ID.
            document_version_id: Specific version with approved questions.
            document_uuid: Document UUID (e.g., "2024-00001").
            sop_version: SOP version string (e.g., "2.0").
            company_id: Company ID for tenant isolation.

        Returns:
            The content_id string ({document_uuid}_v{sop_version}).

        Raises:
            HTTPException: 400 if no approved questions exist for the
                specified document version.
        """
        content_id = f"{document_uuid}_v{sop_version}"

        # Verify approved questions exist
        count_result = await session.execute(
            select(func.count(GeneratedQuestion.id)).where(
                GeneratedQuestion.document_id == document_id,
                GeneratedQuestion.document_version_id
                == document_version_id,
                GeneratedQuestion.company_id == company_id,
                GeneratedQuestion.status == ContentStatus.APPROVED.value,
            )
        )
        approved_count = count_result.scalar_one()

        if approved_count == 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No approved questions exist for document "
                    f"{document_id} version {document_version_id}. "
                    "Approve questions before registering."
                ),
            )

        # Mark previous active sets for this content_id as inactive
        await session.execute(
            update(ActiveQuestionSet)
            .where(
                ActiveQuestionSet.content_id == content_id,
                ActiveQuestionSet.company_id == company_id,
                ActiveQuestionSet.is_active.is_(True),
            )
            .values(is_active=False)
        )

        # Create new active question set
        new_set = ActiveQuestionSet(
            content_id=content_id,
            document_id=document_id,
            document_version_id=document_version_id,
            company_id=company_id,
            is_active=True,
        )
        session.add(new_set)
        await session.flush()

        logger.info(
            "Registered active question set for content_id=%s "
            "(document=%d, version=%d, company=%d, approved_count=%d)",
            content_id,
            document_id,
            document_version_id,
            company_id,
            approved_count,
        )

        return content_id

    async def has_user_passed_enhanced(
        self,
        session: AsyncSession,
        user_id: int,
        content_id: str,
    ) -> bool:
        """Check if user passed via quiz OR virtual audit.

        Returns True if:
        - At least one QuizAttempt with passed=True exists for the
          user and content_id, OR
        - At least one VirtualAuditSession with passed=True exists for
          the user and the document/version associated with the content_id.

        When a passed virtual audit is found but no synthetic QuizAttempt
        exists, creates one for backward compatibility with the training gate.

        Args:
            session: Active async database session.
            user_id: The user's primary key.
            content_id: Training content identifier
                (format: {document_uuid}_v{sop_version}).

        Returns:
            True if the user has passed via either path, False otherwise.
        """
        # Check for passed quiz attempt (existing behavior)
        quiz_result = await session.execute(
            select(QuizAttempt.id)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.content_id == content_id,
                QuizAttempt.passed.is_(True),
            )
            .limit(1)
        )
        if quiz_result.scalar_one_or_none() is not None:
            return True

        # Check for passed virtual audit session
        # Find the active question set to get document_id and version_id
        active_set_result = await session.execute(
            select(ActiveQuestionSet).where(
                ActiveQuestionSet.content_id == content_id,
                ActiveQuestionSet.is_active.is_(True),
            )
        )
        active_set = active_set_result.scalar_one_or_none()

        if active_set is not None:
            # Look for passed virtual audit for this document version
            audit_result = await session.execute(
                select(VirtualAuditSession)
                .where(
                    VirtualAuditSession.user_id == user_id,
                    VirtualAuditSession.document_id
                    == active_set.document_id,
                    VirtualAuditSession.document_version_id
                    == active_set.document_version_id,
                    VirtualAuditSession.status
                    == SessionStatus.COMPLETED,
                    VirtualAuditSession.passed.is_(True),
                )
                .limit(1)
            )
            passed_audit = audit_result.scalar_one_or_none()

            if passed_audit is not None:
                # Create synthetic QuizAttempt for backward compatibility
                await self._create_synthetic_quiz_attempt(
                    session, user_id, content_id, passed_audit
                )
                return True
        else:
            # No active question set — try to find virtual audit by
            # parsing content_id to get document_uuid and version
            sop_document_uuid, sop_version = self._parse_content_id(
                content_id
            )

            # Look for passed virtual audit sessions for this user
            # where the document matches the sop_document_uuid
            from alcoabase.models.document import Document

            doc_result = await session.execute(
                select(Document.id).where(
                    Document.document_uuid == sop_document_uuid
                )
            )
            doc_id = doc_result.scalar_one_or_none()

            if doc_id is not None:
                audit_result = await session.execute(
                    select(VirtualAuditSession)
                    .where(
                        VirtualAuditSession.user_id == user_id,
                        VirtualAuditSession.document_id == doc_id,
                        VirtualAuditSession.status
                        == SessionStatus.COMPLETED,
                        VirtualAuditSession.passed.is_(True),
                    )
                    .limit(1)
                )
                passed_audit = audit_result.scalar_one_or_none()

                if passed_audit is not None:
                    # Create synthetic QuizAttempt for backward compatibility
                    await self._create_synthetic_quiz_attempt(
                        session, user_id, content_id, passed_audit
                    )
                    return True

        return False

    # -------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------

    async def _create_synthetic_quiz_attempt(
        self,
        session: AsyncSession,
        user_id: int,
        content_id: str,
        audit_session: VirtualAuditSession,
    ) -> QuizAttempt:
        """Create a synthetic QuizAttempt from a passed virtual audit session.

        This maintains backward compatibility with the training gate by
        creating a QuizAttempt record that the existing has_user_passed
        check will find.

        Args:
            session: Active async database session.
            user_id: The user's primary key.
            content_id: Training content identifier.
            audit_session: The passed VirtualAuditSession.

        Returns:
            The created synthetic QuizAttempt.
        """
        sop_document_uuid, sop_version = self._parse_content_id(content_id)

        # Score = number of turns scored above 0.70
        turns_above_threshold = 0
        session_data = audit_session.session_data or {}
        turns = session_data.get("turns", [])
        for turn in turns:
            evaluation = turn.get("evaluation", {})
            # Compute weighted score for this turn
            accuracy = evaluation.get("factual_accuracy", 0.0)
            completeness = evaluation.get("completeness", 0.0)
            reference = evaluation.get("document_reference_quality", 0.0)
            turn_score = (
                accuracy * 0.5 + completeness * 0.3 + reference * 0.2
            )
            if turn_score >= 0.70:
                turns_above_threshold += 1

        attempt = QuizAttempt(
            user_id=user_id,
            content_id=content_id,
            sop_document_uuid=sop_document_uuid,
            sop_version=sop_version,
            answers={},
            score=turns_above_threshold,
            total_questions=audit_session.total_turns,
            passed=True,
            company_id=audit_session.company_id,
        )
        session.add(attempt)
        await session.flush()

        logger.info(
            "Created synthetic QuizAttempt for user %d from virtual audit "
            "session %d (content_id=%s, score=%d/%d)",
            user_id,
            audit_session.id,
            content_id,
            turns_above_threshold,
            audit_session.total_turns,
        )

        return attempt

    @staticmethod
    def _parse_content_id(content_id: str) -> tuple[str, str]:
        """Parse content_id into sop_document_uuid and sop_version.

        The content_id format is: {document_uuid}_v{sop_version}

        Args:
            content_id: Training content identifier.

        Returns:
            Tuple of (sop_document_uuid, sop_version).
        """
        # Split on "_v" from the right to handle UUIDs that might contain "_v"
        parts = content_id.rsplit("_v", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        # Fallback: return the whole thing as uuid with empty version
        return content_id, ""
