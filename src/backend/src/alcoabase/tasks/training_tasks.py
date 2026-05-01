"""Celery tasks for asynchronous training content generation.

Handles background generation of training materials (summaries, quizzes,
procedural steps) triggered when an SOP enters InTraining status.

References:
    - Task 16.4: Create Celery task for async training content generation
    - Design doc Section 12: Training Content Generator
"""

import asyncio
import logging
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger

from alcoabase.services.training_content_generator import TrainingContentGenerator

logger = get_task_logger(__name__)

# Module-level service instance (reused across task invocations)
_training_content_generator: TrainingContentGenerator | None = None


def _get_training_content_generator() -> TrainingContentGenerator:
    """Get or create the TrainingContentGenerator singleton for task workers.

    Returns:
        TrainingContentGenerator: The service instance.
    """
    global _training_content_generator
    if _training_content_generator is None:
        _training_content_generator = TrainingContentGenerator()
    return _training_content_generator


@shared_task(
    bind=True,
    name="alcoabase.tasks.generate_training_content",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def generate_training_content_task(
    self: Any,
    sop_document_uuid: str,
    sop_version: str,
    sop_text: str,
    previous_version_text: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Asynchronously generate training content for an SOP version.

    Triggered when an SOP enters InTraining status. Generates training
    summaries, comprehension quizzes, and key procedural steps.

    Args:
        self: Celery task instance (bound).
        sop_document_uuid: Document-UUID of the SOP.
        sop_version: Version string of the SOP.
        sop_text: Full text content of the current SOP version.
        previous_version_text: Optional text of the previous version.
        user_id: ID of the user who triggered the generation.

    Returns:
        Dict with generation results (content_id, status, quiz_count).
    """
    generator = _get_training_content_generator()

    logger.info(
        "Starting training content generation for SOP %s v%s",
        sop_document_uuid,
        sop_version,
    )

    # Run the async generation in a sync context (Celery worker)
    loop = asyncio.new_event_loop()
    try:
        content = loop.run_until_complete(
            generator.generate_training_content(
                sop_document_uuid=sop_document_uuid,
                sop_version=sop_version,
                sop_text=sop_text,
                previous_version_text=previous_version_text,
                user_id=user_id,
            )
        )
    finally:
        loop.close()

    logger.info(
        "Successfully generated training content %s for SOP %s v%s "
        "(%d quiz questions, %d procedural steps)",
        content.content_id,
        sop_document_uuid,
        sop_version,
        len(content.quiz_questions),
        len(content.procedural_steps),
    )

    return {
        "content_id": content.content_id,
        "sop_document_uuid": sop_document_uuid,
        "sop_version": sop_version,
        "status": content.status.value,
        "quiz_question_count": len(content.quiz_questions),
        "procedural_step_count": len(content.procedural_steps),
        "safety_point_count": len(content.safety_points),
    }
