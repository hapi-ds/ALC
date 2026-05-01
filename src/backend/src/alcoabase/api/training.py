"""FastAPI router for training management endpoints.

Provides endpoints for:
- GET /api/training/tasks: List training tasks for the current user
- POST /api/training/tasks/{task_id}/complete: Mark a training task as completed
- GET /api/training/status/{sop_uuid}/{version}: Get training status for an SOP version
- GET /api/training/content/{content_id}: Get training content by ID
- POST /api/training/content/{content_id}/approve: Approve training content
- POST /api/training/content/{content_id}/reject: Reject training content

References:
    - Design doc Section 7: Training Service (ABAC)
    - Design doc Section 12: Training Content Generator
    - Requirements 9, 10: Training Assignment and Execution Gate
    - Task 16.7: FastAPI endpoints for training content review and approval
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.services.training_service import TrainingService
from alcoabase.services.training_content_generator import (
    TrainingContentGenerator,
    ContentStatus,
)

router = APIRouter(prefix="/training", tags=["Training"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TrainingTaskResponse(BaseModel):
    """Response schema for a training task."""

    id: int
    sop_document_uuid: str
    sop_version: str
    assigned_user_id: int
    task_title: str
    is_completed: bool
    completed_at: str | None = None

    model_config = {"from_attributes": True}


class TrainingStatusResponse(BaseModel):
    """Response schema for training status."""

    sop_document_uuid: str
    sop_version: str
    total_tasks: int
    completed_tasks: int
    is_complete: bool


class TrainingTaskCompleteResponse(BaseModel):
    """Response schema for completing a training task."""

    id: int
    is_completed: bool
    completed_at: str | None = None
    message: str


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_training_service() -> TrainingService:
    """Provide a TrainingService instance as a FastAPI dependency."""
    return TrainingService()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TrainingTaskResponse])
async def get_training_tasks(
    user_id: int = Query(..., description="User ID to get tasks for"),
    session: AsyncSession = Depends(get_db_session),
    service: TrainingService = Depends(get_training_service),
) -> list[TrainingTaskResponse]:
    """Get all training tasks assigned to a user.

    Args:
        user_id: The user's primary key.
        session: Database session (injected).
        service: TrainingService instance (injected).

    Returns:
        List of training tasks assigned to the user.
    """
    tasks = await service.get_user_training_tasks(session, user_id)
    return [
        TrainingTaskResponse(
            id=task.id,
            sop_document_uuid=task.sop_document_uuid,
            sop_version=task.sop_version,
            assigned_user_id=task.assigned_user_id,
            task_title=task.task_title,
            is_completed=task.is_completed,
            completed_at=(
                task.completed_at.isoformat() if task.completed_at else None
            ),
        )
        for task in tasks
    ]


@router.post(
    "/tasks/{task_id}/complete", response_model=TrainingTaskCompleteResponse
)
async def complete_training_task(
    task_id: int,
    user_id: int = Query(..., description="User ID completing the task"),
    session: AsyncSession = Depends(get_db_session),
    service: TrainingService = Depends(get_training_service),
) -> TrainingTaskCompleteResponse:
    """Mark a training task as completed.

    Completes the task, creates a training record, and checks if all
    tasks for the SOP version are now complete (triggering auto-transition
    to Active if so).

    Args:
        task_id: The training task primary key.
        user_id: The user completing the task.
        session: Database session (injected).
        service: TrainingService instance (injected).

    Returns:
        Completion confirmation with task details.

    Raises:
        HTTPException: 400 if task not found, not assigned to user, or already completed.
    """
    task = await service.complete_training_task(session, task_id, user_id)
    return TrainingTaskCompleteResponse(
        id=task.id,
        is_completed=task.is_completed,
        completed_at=(
            task.completed_at.isoformat() if task.completed_at else None
        ),
        message="Training task completed successfully",
    )


@router.get(
    "/status/{sop_uuid}/{version}", response_model=TrainingStatusResponse
)
async def get_training_status(
    sop_uuid: str,
    version: str,
    session: AsyncSession = Depends(get_db_session),
    service: TrainingService = Depends(get_training_service),
) -> TrainingStatusResponse:
    """Get training status for an SOP version.

    Returns a summary of training progress including total tasks,
    completed tasks, and whether training is complete.

    Args:
        sop_uuid: Document-UUID of the SOP.
        version: Version string of the SOP (e.g., "2.0").
        session: Database session (injected).
        service: TrainingService instance (injected).

    Returns:
        Training status summary.
    """
    status = await service.get_training_status(session, sop_uuid, version)
    return TrainingStatusResponse(**status)


# ---------------------------------------------------------------------------
# Training Content Schemas (Task 16.7)
# ---------------------------------------------------------------------------


class QuizQuestionResponse(BaseModel):
    """Response schema for a quiz question."""

    question_id: str
    question: str
    correct_answer: str
    distractors: list[str]
    sop_section_ref: str


class ProceduralStepResponse(BaseModel):
    """Response schema for a procedural step."""

    step_number: int
    description: str
    is_safety_critical: bool
    safety_note: str = ""


class TrainingContentResponse(BaseModel):
    """Response schema for training content."""

    content_id: str
    sop_document_uuid: str
    sop_version: str
    summary: str
    quiz_questions: list[QuizQuestionResponse]
    procedural_steps: list[ProceduralStepResponse]
    safety_points: list[str]
    status: str
    generated_at: str
    reviewed_by: int | None = None
    reviewed_at: str | None = None
    review_notes: str = ""


class ContentReviewRequest(BaseModel):
    """Request schema for content review (approve/reject)."""

    reviewer_id: int = Field(..., description="ID of the reviewing coordinator")
    notes: str = Field(default="", description="Review notes or rejection reason")


class ContentReviewResponse(BaseModel):
    """Response schema for content review action."""

    content_id: str
    status: str
    reviewed_by: int
    reviewed_at: str
    message: str


# ---------------------------------------------------------------------------
# Training Content Dependency
# ---------------------------------------------------------------------------

_training_content_generator: TrainingContentGenerator | None = None


def get_training_content_generator() -> TrainingContentGenerator:
    """Provide a TrainingContentGenerator instance as a FastAPI dependency."""
    global _training_content_generator
    if _training_content_generator is None:
        _training_content_generator = TrainingContentGenerator()
    return _training_content_generator


# ---------------------------------------------------------------------------
# Training Content Endpoints (Task 16.7)
# ---------------------------------------------------------------------------


@router.get("/content/{content_id}", response_model=TrainingContentResponse)
async def get_training_content(
    content_id: str,
    generator: TrainingContentGenerator = Depends(get_training_content_generator),
) -> TrainingContentResponse:
    """Get training content by ID.

    Args:
        content_id: The training content identifier.
        generator: TrainingContentGenerator dependency.

    Returns:
        Training content details.

    Raises:
        HTTPException: 404 if content not found.
    """
    content = generator.get_content(content_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Training content not found: {content_id}")

    return TrainingContentResponse(
        content_id=content.content_id,
        sop_document_uuid=content.sop_document_uuid,
        sop_version=content.sop_version,
        summary=content.summary,
        quiz_questions=[
            QuizQuestionResponse(
                question_id=q.question_id,
                question=q.question,
                correct_answer=q.correct_answer,
                distractors=q.distractors,
                sop_section_ref=q.sop_section_ref,
            )
            for q in content.quiz_questions
        ],
        procedural_steps=[
            ProceduralStepResponse(
                step_number=s.step_number,
                description=s.description,
                is_safety_critical=s.is_safety_critical,
                safety_note=s.safety_note,
            )
            for s in content.procedural_steps
        ],
        safety_points=content.safety_points,
        status=content.status.value,
        generated_at=content.generated_at.isoformat(),
        reviewed_by=content.reviewed_by,
        reviewed_at=content.reviewed_at.isoformat() if content.reviewed_at else None,
        review_notes=content.review_notes,
    )


@router.post(
    "/content/{content_id}/approve", response_model=ContentReviewResponse
)
async def approve_training_content(
    content_id: str,
    request: ContentReviewRequest,
    generator: TrainingContentGenerator = Depends(get_training_content_generator),
) -> ContentReviewResponse:
    """Approve training content after coordinator review.

    Only content in PENDING_REVIEW status can be approved.
    Approved content will be presented to trainees.

    Args:
        content_id: The training content identifier.
        request: Review request with reviewer ID and notes.
        generator: TrainingContentGenerator dependency.

    Returns:
        Review confirmation.

    Raises:
        HTTPException: 404 if content not found, 400 if not in reviewable state.
    """
    try:
        content = generator.approve_content(
            content_id=content_id,
            reviewer_id=request.reviewer_id,
            notes=request.notes,
        )
        return ContentReviewResponse(
            content_id=content.content_id,
            status=content.status.value,
            reviewed_by=content.reviewed_by,
            reviewed_at=content.reviewed_at.isoformat() if content.reviewed_at else "",
            message="Training content approved successfully",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Training content not found: {content_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/content/{content_id}/reject", response_model=ContentReviewResponse
)
async def reject_training_content(
    content_id: str,
    request: ContentReviewRequest,
    generator: TrainingContentGenerator = Depends(get_training_content_generator),
) -> ContentReviewResponse:
    """Reject training content after coordinator review.

    Only content in PENDING_REVIEW status can be rejected.
    Rejected content will not be presented to trainees.

    Args:
        content_id: The training content identifier.
        request: Review request with reviewer ID and rejection reason.
        generator: TrainingContentGenerator dependency.

    Returns:
        Review confirmation.

    Raises:
        HTTPException: 404 if content not found, 400 if not in reviewable state.
    """
    try:
        content = generator.reject_content(
            content_id=content_id,
            reviewer_id=request.reviewer_id,
            notes=request.notes,
        )
        return ContentReviewResponse(
            content_id=content.content_id,
            status=content.status.value,
            reviewed_by=content.reviewed_by,
            reviewed_at=content.reviewed_at.isoformat() if content.reviewed_at else "",
            message="Training content rejected",
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Training content not found: {content_id}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
