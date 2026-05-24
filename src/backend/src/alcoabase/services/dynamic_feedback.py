"""Dynamic Feedback Service for paragraph-level guidance on incorrect answers.

This module implements:
- RAG-powered paragraph retrieval for incorrect quiz answers
- LLM-generated explanations connecting paragraphs to questions
- Feedback caching keyed by (question_id, document_version_id)
- Cache invalidation on new document version publication
- Failed attempt verification before feedback delivery
- Fallback handling for low-similarity results and inference unavailability

References:
    - Design doc Section 5: Dynamic Feedback Service
    - Requirements 7.1–7.10: Dynamic Feedback — Paragraph-Level Guidance
"""

import logging
from typing import TYPE_CHECKING

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.training import QuizAttempt
from alcoabase.models.training_ecosystem import (
    DynamicFeedbackCache,
    GeneratedQuestion,
)
from alcoabase.schemas.training_ecosystem import DynamicFeedbackResponse

if TYPE_CHECKING:
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum similarity score for paragraph selection (Req 7.3)
SIMILARITY_THRESHOLD = 0.75

# Generic fallback message when InferenceClient is unavailable (Req 7.9)
GENERIC_EXPLANATION = (
    "Review the highlighted paragraph for the correct information."
)

# Generic fallback message when no paragraph above threshold (Req 7.4)
GENERIC_NO_PARAGRAPH_MESSAGE = (
    "Please review the referenced section in the source document "
    "for the correct information."
)


class DynamicFeedbackService:
    """RAG-powered paragraph-level feedback for incorrect quiz answers.

    Retrieves exact source paragraphs via the KnowledgeService when users
    answer incorrectly, and generates LLM explanations connecting the
    paragraph to the question. Results are cached to avoid redundant
    RAG queries on repeated attempts.

    Args:
        session_factory: SQLAlchemy async session factory for DB access.
        inference_client: InferenceClient for LLM explanation generation.
        knowledge_service: KnowledgeService for RAG paragraph retrieval.

    Usage:
        service = DynamicFeedbackService(
            session_factory=session_factory,
            inference_client=inference_client,
            knowledge_service=knowledge_service,
        )
        feedback = await service.get_feedback(question_id, user_id, company_id)
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        inference_client: "InferenceClient",
        knowledge_service: "KnowledgeService",
    ) -> None:
        """Initialize the DynamicFeedbackService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
            inference_client: InferenceClient for LLM communication.
            knowledge_service: KnowledgeService for hybrid search retrieval.
        """
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._knowledge_service = knowledge_service

    async def get_feedback(
        self,
        question_id: int,
        user_id: int,
        company_id: int,
    ) -> DynamicFeedbackResponse:
        """Retrieve or generate feedback for a failed question.

        Checks that the user has at least one failed attempt for the
        question, then returns cached feedback if available or generates
        new feedback via RAG retrieval + LLM explanation.

        Args:
            question_id: ID of the question to get feedback for.
            user_id: ID of the requesting user.
            company_id: Company ID for tenant isolation.

        Returns:
            DynamicFeedbackResponse with paragraph text, section reference,
            and explanation.

        Raises:
            HTTPException: 403 if user has no failed attempts for the question.
            HTTPException: 404 if question does not exist or does not belong
                to the specified company.
        """
        async with self._session_factory() as session:
            # Verify the question exists and belongs to the company
            question_result = await session.execute(
                select(GeneratedQuestion).where(
                    GeneratedQuestion.id == question_id,
                    GeneratedQuestion.company_id == company_id,
                )
            )
            question = question_result.scalar_one_or_none()
            if question is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Question not found: {question_id}",
                )

            # Check for failed attempt (Req 7.7)
            has_failed = await self._has_failed_attempt(
                session, question_id, user_id, company_id
            )
            if not has_failed:
                raise HTTPException(
                    status_code=403,
                    detail="Feedback is only available after a failed attempt.",
                )

            # Check cache (Req 7.6)
            cached = await self._get_cached_feedback(
                session, question_id, question.document_version_id
            )
            if cached is not None:
                return DynamicFeedbackResponse(
                    correct_answer=question.correct_answer,
                    paragraph_text=cached.paragraph_text,
                    section_reference=cached.section_reference,
                    page_number=cached.page_number,
                    explanation=cached.explanation,
                )

        # Generate new feedback (outside session context for potentially
        # long-running RAG + LLM operations)
        feedback = await self.generate_feedback(question)

        # Cache the result
        async with self._session_factory() as session:
            cache_entry = DynamicFeedbackCache(
                question_id=question.id,
                document_version_id=question.document_version_id,
                paragraph_text=feedback.paragraph_text,
                section_reference=feedback.section_reference,
                page_number=feedback.page_number,
                similarity_score=0.0,  # Updated below if available
                explanation=feedback.explanation,
            )
            session.add(cache_entry)
            await session.commit()

        return feedback

    async def generate_feedback(
        self,
        question: GeneratedQuestion,
    ) -> DynamicFeedbackResponse:
        """Generate feedback via RAG retrieval + LLM explanation.

        Queries the KnowledgeService with the question text and correct
        answer scoped to the source document, selects the paragraph with
        the highest similarity score above the 0.75 threshold, and
        generates an explanation via the InferenceClient.

        Args:
            question: The GeneratedQuestion to generate feedback for.

        Returns:
            DynamicFeedbackResponse with paragraph, section reference,
            and explanation.
        """
        # Build search query combining question text and correct answer
        search_query = f"{question.question_text} {question.correct_answer}"

        # Query KnowledgeService for relevant paragraphs (Req 7.1)
        results, _total = self._knowledge_service.hybrid_search(
            query=search_query,
            user_id=0,  # System-level search, no ABAC filtering needed
            limit=5,
        )

        # Select paragraph with highest similarity above threshold (Req 7.3)
        best_result = None
        for result in results:
            if result.relevance_score >= SIMILARITY_THRESHOLD:
                if best_result is None or result.relevance_score > best_result.relevance_score:
                    best_result = result

        # Fallback: no paragraph above threshold (Req 7.4)
        if best_result is None:
            return DynamicFeedbackResponse(
                correct_answer=question.correct_answer,
                paragraph_text=GENERIC_NO_PARAGRAPH_MESSAGE,
                section_reference=question.sop_section_ref,
                page_number=None,
                explanation=GENERIC_NO_PARAGRAPH_MESSAGE,
            )

        paragraph_text = best_result.excerpt
        section_reference = (
            best_result.metadata.get("section_reference")
            or question.sop_section_ref
        )
        page_number = best_result.metadata.get("page_number")

        # Generate LLM explanation (Req 7.5)
        explanation = await self._generate_explanation(
            question_text=question.question_text,
            correct_answer=question.correct_answer,
            paragraph_text=paragraph_text,
        )

        return DynamicFeedbackResponse(
            correct_answer=question.correct_answer,
            paragraph_text=paragraph_text,
            section_reference=section_reference,
            page_number=page_number,
            explanation=explanation,
        )

    async def invalidate_cache(
        self,
        document_version_id: int,
    ) -> int:
        """Invalidate cached feedback for a document version.

        Deletes all DynamicFeedbackCache entries for the specified
        document version. Called when a new document version is published.

        Args:
            document_version_id: ID of the document version to invalidate.

        Returns:
            Number of cache entries deleted.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                delete(DynamicFeedbackCache).where(
                    DynamicFeedbackCache.document_version_id
                    == document_version_id
                )
            )
            await session.commit()
            count = result.rowcount  # type: ignore[assignment]
            logger.info(
                "Invalidated %d feedback cache entries for "
                "document_version_id=%d",
                count,
                document_version_id,
            )
            return count

    async def has_failed_attempt(
        self,
        question_id: int,
        user_id: int,
        company_id: int,
    ) -> bool:
        """Check if user has at least one failed attempt for this question.

        Public interface for checking failed attempts. Opens its own
        session for standalone usage.

        Args:
            question_id: ID of the question.
            user_id: ID of the user.
            company_id: Company ID for tenant isolation.

        Returns:
            True if at least one failed attempt exists, False otherwise.
        """
        async with self._session_factory() as session:
            return await self._has_failed_attempt(
                session, question_id, user_id, company_id
            )

    # -----------------------------------------------------------------------
    # Private Helpers
    # -----------------------------------------------------------------------

    async def _has_failed_attempt(
        self,
        session: AsyncSession,
        question_id: int,
        user_id: int,
        company_id: int,
    ) -> bool:
        """Check if user has at least one failed attempt for this question.

        Queries QuizAttempt records where the user answered incorrectly.
        A failed attempt is any QuizAttempt where passed=False for the
        content associated with this question.

        Args:
            session: Active async database session.
            question_id: ID of the question.
            user_id: ID of the user.
            company_id: Company ID for tenant isolation.

        Returns:
            True if at least one failed attempt exists, False otherwise.
        """
        # Get the question to find its associated content_id
        question_result = await session.execute(
            select(GeneratedQuestion).where(
                GeneratedQuestion.id == question_id,
            )
        )
        question = question_result.scalar_one_or_none()
        if question is None:
            return False

        # Check for any failed quiz attempt by this user for the same
        # document (content_id pattern: {document_uuid}_v{version})
        result = await session.execute(
            select(QuizAttempt.id)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.company_id == company_id,
                QuizAttempt.passed.is_(False),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _get_cached_feedback(
        self,
        session: AsyncSession,
        question_id: int,
        document_version_id: int,
    ) -> DynamicFeedbackCache | None:
        """Retrieve cached feedback entry if it exists.

        Args:
            session: Active async database session.
            question_id: ID of the question.
            document_version_id: ID of the document version.

        Returns:
            DynamicFeedbackCache entry or None if not cached.
        """
        result = await session.execute(
            select(DynamicFeedbackCache).where(
                DynamicFeedbackCache.question_id == question_id,
                DynamicFeedbackCache.document_version_id
                == document_version_id,
            )
        )
        return result.scalar_one_or_none()

    async def _generate_explanation(
        self,
        question_text: str,
        correct_answer: str,
        paragraph_text: str,
    ) -> str:
        """Generate an LLM explanation connecting the paragraph to the question.

        Uses the InferenceClient to produce a 2-3 sentence explanation
        of why the paragraph answers the question. Falls back to a generic
        message if the InferenceClient is unavailable (Req 7.9).

        Args:
            question_text: The question text.
            correct_answer: The correct answer text.
            paragraph_text: The source paragraph text.

        Returns:
            LLM-generated explanation or generic fallback message.
        """
        from alcoabase.services.inference_client import (
            InferenceConnectionError,
            InferenceError,
            InferenceTimeoutError,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a training assistant helping employees understand "
                    "why a specific paragraph from a document answers a quiz "
                    "question. Provide a clear, concise explanation in 2-3 "
                    "sentences connecting the paragraph content to the correct "
                    "answer. Do not repeat the question or answer verbatim."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question_text}\n\n"
                    f"Correct Answer: {correct_answer}\n\n"
                    f"Source Paragraph: {paragraph_text}\n\n"
                    "Explain in 2-3 sentences how this paragraph contains "
                    "the information needed to answer the question correctly."
                ),
            },
        ]

        try:
            explanation = await self._inference_client.chat_completion(
                model="",  # Uses default model from vLLM
                messages=messages,
                temperature=0.3,
                max_tokens=256,
                timeout=30.0,
            )
            return explanation.strip()
        except (
            InferenceTimeoutError,
            InferenceConnectionError,
            InferenceError,
        ) as e:
            logger.warning(
                "InferenceClient unavailable for explanation generation: %s. "
                "Returning generic message.",
                str(e),
            )
            return GENERIC_EXPLANATION
