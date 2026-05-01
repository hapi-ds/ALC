"""Training Content Generator service (LLM-Powered).

This module provides:
- DSPy pipeline (placeholder) for training summary generation
- Comprehension quiz generation
- Key procedural steps and safety points extraction
- Coordinator review gate for content approval
- Audit trail recording for generation events

References:
    - Task 16: Training Content Generator (LLM-Powered)
    - Design doc Section 12: Training Content Generator
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and Data Classes
# ---------------------------------------------------------------------------


class ContentStatus(str, Enum):
    """Status of generated training content."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DRAFT = "draft"


@dataclass
class QuizQuestion:
    """A comprehension quiz question.

    Attributes:
        question_id: Unique identifier for the question.
        question: The question text.
        correct_answer: The correct answer.
        distractors: Incorrect answer options.
        sop_section_ref: Reference to the SOP section.
    """

    question_id: str
    question: str
    correct_answer: str
    distractors: list[str]
    sop_section_ref: str


@dataclass
class ProceduralStep:
    """A key procedural step extracted from an SOP.

    Attributes:
        step_number: Sequential step number.
        description: Step description.
        is_safety_critical: Whether this step has safety implications.
        safety_note: Optional safety note for the step.
    """

    step_number: int
    description: str
    is_safety_critical: bool = False
    safety_note: str = ""


@dataclass
class TrainingContent:
    """Generated training content for an SOP version.

    Attributes:
        content_id: Unique identifier for this content.
        sop_document_uuid: Document-UUID of the source SOP.
        sop_version: Version of the SOP.
        summary: Training summary highlighting changes.
        quiz_questions: Comprehension quiz questions.
        procedural_steps: Key procedural steps.
        safety_points: Extracted safety points.
        status: Current review status.
        generated_at: When the content was generated.
        reviewed_by: User ID of the reviewer (if reviewed).
        reviewed_at: When the content was reviewed.
        review_notes: Reviewer's notes.
    """

    content_id: str
    sop_document_uuid: str
    sop_version: str
    summary: str
    quiz_questions: list[QuizQuestion]
    procedural_steps: list[ProceduralStep]
    safety_points: list[str]
    status: ContentStatus = ContentStatus.PENDING_REVIEW
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    review_notes: str = ""


@dataclass
class GenerationAuditEvent:
    """Audit trail record for training content generation.

    Attributes:
        event_id: Unique event identifier.
        content_id: ID of the generated content.
        sop_document_uuid: Source SOP Document-UUID.
        sop_version: Source SOP version.
        event_type: Type of event (generated, approved, rejected).
        user_id: User who triggered the event.
        timestamp: When the event occurred.
        details: Additional event details.
    """

    event_id: str
    content_id: str
    sop_document_uuid: str
    sop_version: str
    event_type: str
    user_id: int | None
    timestamp: datetime
    details: str = ""


# ---------------------------------------------------------------------------
# Training Content Generator
# ---------------------------------------------------------------------------


class TrainingContentGenerator:
    """LLM-powered training content generator using DSPy pipeline (placeholder).

    Generates training materials including summaries, comprehension quizzes,
    and key procedural steps from SOP documents. All generated content
    requires coordinator review before presentation to trainees.

    Attributes:
        _knowledge_service: Service for document retrieval.
        _content_store: In-memory store of generated content.
        _audit_log: Audit trail of generation events.
    """

    def __init__(
        self,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        """Initialize the TrainingContentGenerator.

        Args:
            knowledge_service: KnowledgeService instance for retrieval.
                Creates a new instance if not provided.
        """
        self._knowledge_service = knowledge_service or KnowledgeService()
        self._content_store: dict[str, TrainingContent] = {}
        self._audit_log: list[GenerationAuditEvent] = []

    # -----------------------------------------------------------------------
    # Training Summary Generation (Task 16.1)
    # -----------------------------------------------------------------------

    async def generate_training_content(
        self,
        sop_document_uuid: str,
        sop_version: str,
        sop_text: str,
        previous_version_text: str | None = None,
        user_id: int | None = None,
    ) -> TrainingContent:
        """Generate complete training content for an SOP version.

        Uses DSPy pipeline (placeholder) to generate:
        1. Training summary (highlighting changes from previous version)
        2. Comprehension quiz questions
        3. Key procedural steps and safety points

        Args:
            sop_document_uuid: Document-UUID of the SOP.
            sop_version: Version string of the SOP.
            sop_text: Full text content of the current SOP version.
            previous_version_text: Optional text of the previous version for diff.
            user_id: ID of the user triggering generation.

        Returns:
            Generated TrainingContent with pending_review status.
        """
        content_id = str(uuid.uuid4())

        # Generate summary
        summary = self._generate_summary(
            sop_text, previous_version_text
        )

        # Generate quiz questions
        quiz_questions = self._generate_quiz(sop_text)

        # Extract procedural steps and safety points
        procedural_steps = self._extract_procedural_steps(sop_text)
        safety_points = self._extract_safety_points(sop_text)

        content = TrainingContent(
            content_id=content_id,
            sop_document_uuid=sop_document_uuid,
            sop_version=sop_version,
            summary=summary,
            quiz_questions=quiz_questions,
            procedural_steps=procedural_steps,
            safety_points=safety_points,
            status=ContentStatus.PENDING_REVIEW,
            generated_at=datetime.now(UTC),
        )

        # Store content
        self._content_store[content_id] = content

        # Record audit event (Task 16.6)
        self._record_audit_event(
            content_id=content_id,
            sop_document_uuid=sop_document_uuid,
            sop_version=sop_version,
            event_type="generated",
            user_id=user_id,
            details=f"Generated training content with {len(quiz_questions)} quiz questions",
        )

        logger.info(
            "Generated training content %s for SOP %s v%s",
            content_id,
            sop_document_uuid,
            sop_version,
        )

        return content

    def _generate_summary(
        self, sop_text: str, previous_text: str | None
    ) -> str:
        """Generate a training summary (placeholder DSPy pipeline).

        Args:
            sop_text: Current SOP text.
            previous_text: Previous version text for diff comparison.

        Returns:
            Generated training summary.
        """
        if previous_text:
            return (
                "Training Summary (Changes from Previous Version):\n\n"
                "This SOP has been updated. Key changes include modifications "
                "to procedural steps and safety requirements. Please review "
                "all sections carefully.\n\n"
                "[Placeholder - Real summary will be generated by DSPy pipeline "
                "via Model_Manager (Task 18)]"
            )
        else:
            return (
                "Training Summary (New SOP):\n\n"
                "This is a new Standard Operating Procedure. Please read "
                "all sections thoroughly and ensure you understand the "
                "procedural requirements and safety precautions.\n\n"
                "[Placeholder - Real summary will be generated by DSPy pipeline "
                "via Model_Manager (Task 18)]"
            )

    # -----------------------------------------------------------------------
    # Comprehension Quiz Generation (Task 16.2)
    # -----------------------------------------------------------------------

    def _generate_quiz(self, sop_text: str) -> list[QuizQuestion]:
        """Generate comprehension quiz questions (placeholder DSPy pipeline).

        Args:
            sop_text: SOP text to generate questions from.

        Returns:
            List of quiz questions with answers and section references.
        """
        # Placeholder: generate sample questions based on text presence
        questions: list[QuizQuestion] = []

        questions.append(
            QuizQuestion(
                question_id=str(uuid.uuid4()),
                question="What is the primary purpose of this SOP?",
                correct_answer="To define the standard procedure for the described activity",
                distractors=[
                    "To provide general guidelines only",
                    "To replace all previous documentation",
                    "To serve as a training manual exclusively",
                ],
                sop_section_ref="Section 1: Purpose",
            )
        )

        questions.append(
            QuizQuestion(
                question_id=str(uuid.uuid4()),
                question="Who is responsible for ensuring compliance with this SOP?",
                correct_answer="All personnel performing the described activity",
                distractors=[
                    "Only the department manager",
                    "Only quality assurance staff",
                    "Only new employees",
                ],
                sop_section_ref="Section 3: Responsibilities",
            )
        )

        questions.append(
            QuizQuestion(
                question_id=str(uuid.uuid4()),
                question="What should you do if you encounter a deviation from this procedure?",
                correct_answer="Report the deviation immediately following the deviation reporting procedure",
                distractors=[
                    "Continue with the procedure as normal",
                    "Fix the issue yourself without reporting",
                    "Wait until the end of the shift to report",
                ],
                sop_section_ref="Section 4: Procedure",
            )
        )

        return questions

    # -----------------------------------------------------------------------
    # Key Procedural Steps and Safety Points (Task 16.3)
    # -----------------------------------------------------------------------

    def _extract_procedural_steps(self, sop_text: str) -> list[ProceduralStep]:
        """Extract key procedural steps from SOP text (placeholder).

        Args:
            sop_text: SOP text to extract steps from.

        Returns:
            List of key procedural steps.
        """
        # Placeholder: return sample procedural steps
        steps = [
            ProceduralStep(
                step_number=1,
                description="Review all prerequisites and ensure required materials are available",
                is_safety_critical=False,
            ),
            ProceduralStep(
                step_number=2,
                description="Don appropriate personal protective equipment (PPE)",
                is_safety_critical=True,
                safety_note="Failure to wear proper PPE may result in exposure to hazardous materials",
            ),
            ProceduralStep(
                step_number=3,
                description="Follow the procedure steps in sequential order",
                is_safety_critical=False,
            ),
            ProceduralStep(
                step_number=4,
                description="Document all observations and results in the designated forms",
                is_safety_critical=False,
            ),
            ProceduralStep(
                step_number=5,
                description="Verify completion and obtain required signatures",
                is_safety_critical=False,
            ),
        ]
        return steps

    def _extract_safety_points(self, sop_text: str) -> list[str]:
        """Extract safety points from SOP text (placeholder).

        Args:
            sop_text: SOP text to extract safety points from.

        Returns:
            List of safety point descriptions.
        """
        # Placeholder: return sample safety points
        return [
            "Always wear appropriate PPE as specified in the procedure",
            "Report any spills or exposure incidents immediately",
            "Ensure proper ventilation in the work area",
            "Follow emergency procedures if an incident occurs",
            "Do not proceed if safety equipment is unavailable or damaged",
        ]

    # -----------------------------------------------------------------------
    # Coordinator Review Gate (Task 16.5)
    # -----------------------------------------------------------------------

    def approve_content(
        self, content_id: str, reviewer_id: int, notes: str = ""
    ) -> TrainingContent:
        """Approve training content after coordinator review.

        Content must be in PENDING_REVIEW status to be approved.
        Approved content can be presented to trainees.

        Args:
            content_id: ID of the content to approve.
            reviewer_id: ID of the reviewing coordinator.
            notes: Optional reviewer notes.

        Returns:
            Updated TrainingContent with APPROVED status.

        Raises:
            KeyError: If content_id is not found.
            ValueError: If content is not in PENDING_REVIEW status.
        """
        content = self._get_content(content_id)

        if content.status != ContentStatus.PENDING_REVIEW:
            raise ValueError(
                f"Content {content_id} is not pending review "
                f"(current status: {content.status.value})"
            )

        content.status = ContentStatus.APPROVED
        content.reviewed_by = reviewer_id
        content.reviewed_at = datetime.now(UTC)
        content.review_notes = notes

        # Record audit event
        self._record_audit_event(
            content_id=content_id,
            sop_document_uuid=content.sop_document_uuid,
            sop_version=content.sop_version,
            event_type="approved",
            user_id=reviewer_id,
            details=f"Content approved by coordinator. Notes: {notes}",
        )

        logger.info(
            "Training content %s approved by user %d", content_id, reviewer_id
        )

        return content

    def reject_content(
        self, content_id: str, reviewer_id: int, notes: str = ""
    ) -> TrainingContent:
        """Reject training content after coordinator review.

        Rejected content will not be presented to trainees and may
        need to be regenerated.

        Args:
            content_id: ID of the content to reject.
            reviewer_id: ID of the reviewing coordinator.
            notes: Rejection reason/notes.

        Returns:
            Updated TrainingContent with REJECTED status.

        Raises:
            KeyError: If content_id is not found.
            ValueError: If content is not in PENDING_REVIEW status.
        """
        content = self._get_content(content_id)

        if content.status != ContentStatus.PENDING_REVIEW:
            raise ValueError(
                f"Content {content_id} is not pending review "
                f"(current status: {content.status.value})"
            )

        content.status = ContentStatus.REJECTED
        content.reviewed_by = reviewer_id
        content.reviewed_at = datetime.now(UTC)
        content.review_notes = notes

        # Record audit event
        self._record_audit_event(
            content_id=content_id,
            sop_document_uuid=content.sop_document_uuid,
            sop_version=content.sop_version,
            event_type="rejected",
            user_id=reviewer_id,
            details=f"Content rejected. Reason: {notes}",
        )

        logger.info(
            "Training content %s rejected by user %d", content_id, reviewer_id
        )

        return content

    def is_content_approved(self, content_id: str) -> bool:
        """Check if training content has been approved.

        Args:
            content_id: ID of the content to check.

        Returns:
            True if content is approved, False otherwise.

        Raises:
            KeyError: If content_id is not found.
        """
        content = self._get_content(content_id)
        return content.status == ContentStatus.APPROVED

    # -----------------------------------------------------------------------
    # Audit Trail (Task 16.6)
    # -----------------------------------------------------------------------

    def _record_audit_event(
        self,
        content_id: str,
        sop_document_uuid: str,
        sop_version: str,
        event_type: str,
        user_id: int | None,
        details: str = "",
    ) -> None:
        """Record a training content generation audit event.

        Args:
            content_id: ID of the related content.
            sop_document_uuid: Source SOP Document-UUID.
            sop_version: Source SOP version.
            event_type: Type of event.
            user_id: User who triggered the event.
            details: Additional details.
        """
        event = GenerationAuditEvent(
            event_id=str(uuid.uuid4()),
            content_id=content_id,
            sop_document_uuid=sop_document_uuid,
            sop_version=sop_version,
            event_type=event_type,
            user_id=user_id,
            timestamp=datetime.now(UTC),
            details=details,
        )
        self._audit_log.append(event)

    def get_audit_log(self) -> list[GenerationAuditEvent]:
        """Get the full audit trail for training content generation.

        Returns:
            List of all generation audit events.
        """
        return list(self._audit_log)

    # -----------------------------------------------------------------------
    # Content Access
    # -----------------------------------------------------------------------

    def _get_content(self, content_id: str) -> TrainingContent:
        """Get training content by ID.

        Args:
            content_id: The content identifier.

        Returns:
            The TrainingContent instance.

        Raises:
            KeyError: If content_id is not found.
        """
        if content_id not in self._content_store:
            raise KeyError(f"Training content not found: {content_id}")
        return self._content_store[content_id]

    def get_content(self, content_id: str) -> TrainingContent | None:
        """Get training content by ID (returns None if not found).

        Args:
            content_id: The content identifier.

        Returns:
            The TrainingContent instance, or None if not found.
        """
        return self._content_store.get(content_id)

    def get_content_for_sop(
        self, sop_document_uuid: str, sop_version: str
    ) -> list[TrainingContent]:
        """Get all training content for a specific SOP version.

        Args:
            sop_document_uuid: Document-UUID of the SOP.
            sop_version: Version string of the SOP.

        Returns:
            List of TrainingContent for the specified SOP version.
        """
        return [
            content
            for content in self._content_store.values()
            if content.sop_document_uuid == sop_document_uuid
            and content.sop_version == sop_version
        ]
