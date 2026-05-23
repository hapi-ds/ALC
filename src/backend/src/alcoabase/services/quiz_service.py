"""Quiz Service for comprehension quiz evaluation and persistence.

This module implements:
- Quiz answer evaluation with exact string matching
- Score computation and pass/fail determination
- Quiz attempt persistence for audit trail
- Quiz pass status verification for gate enforcement
- Quiz attempt history retrieval

References:
    - Design doc: QuizService component
    - Requirements 1: Quiz Attempt Data Model
    - Requirements 2: Quiz Submission API Endpoint
    - Requirements 3: Quiz Results API Endpoint
    - Requirements 4: Quiz Pass Verification API Endpoint
"""

import math

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.training import QuizAttempt
from alcoabase.models.user import User
from alcoabase.services.training_content_generator import (
    TrainingContentGenerator,
)


class QuizService:
    """Service for quiz evaluation, scoring, and persistence.

    Provides methods for:
    - Evaluating quiz submissions against correct answers
    - Computing pass/fail status using the 80% threshold
    - Persisting quiz attempt records for audit compliance
    - Checking quiz pass status for gate enforcement
    - Retrieving quiz attempt history

    Usage:
        service = QuizService(content_generator)
        attempt = await service.evaluate_and_persist(
            session, content_id, user_id, answers, company_id
        )
    """

    def __init__(
        self, content_generator: TrainingContentGenerator
    ) -> None:
        """Initialize the QuizService.

        Args:
            content_generator: TrainingContentGenerator instance for
                retrieving training content and quiz questions.
        """
        self._content_generator = content_generator

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
