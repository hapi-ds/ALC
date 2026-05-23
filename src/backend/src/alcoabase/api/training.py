"""FastAPI router for training management endpoints.

Provides endpoints for:
- GET /api/training/tasks: List training tasks for the current user
- POST /api/training/tasks/{task_id}/complete: Mark a training task as completed
- GET /api/training/status/{sop_uuid}/{version}: Get training status for an SOP version
- GET /api/training/content/{content_id}: Get training content by ID
- POST /api/training/content/{content_id}/approve: Approve training content
- POST /api/training/content/{content_id}/reject: Reject training content
- POST /api/training/quiz/submit: Submit quiz answers for evaluation

References:
    - Design doc Section 7: Training Service (ABAC)
    - Design doc Section 12: Training Content Generator
    - Requirements 9, 10: Training Assignment and Execution Gate
    - Task 16.7: FastAPI endpoints for training content review and approval
    - Phase 3.5: Training-Gated Access Control (Quiz endpoints)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.services.quiz_service import QuizService
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
# Quiz Submission Schemas (Phase 3.5)
# ---------------------------------------------------------------------------


class QuizSubmitRequest(BaseModel):
    """Request schema for quiz answer submission."""

    content_id: str = Field(..., description="Training content identifier")
    user_id: int = Field(..., description="ID of the user submitting the quiz")
    answers: dict[str, str] = Field(
        ..., description="Mapping of question_id to selected answer"
    )


class QuizSubmitResponse(BaseModel):
    """Response schema for quiz submission result."""

    attempt_id: int
    score: int
    total_questions: int
    passed: bool
    passing_score_threshold: float
    correct_answers: dict[str, str]
    attempted_at: datetime


class QuizResultItem(BaseModel):
    """Response schema for a single quiz attempt in the results list."""

    attempt_id: int
    score: int
    total_questions: int
    passed: bool
    attempted_at: datetime
    answers: dict[str, str]

    model_config = {"from_attributes": True}


class QuizResultsResponse(BaseModel):
    """Response schema for quiz results list endpoint."""

    results: list[QuizResultItem]
    has_passed: bool


class QuizPassStatusResponse(BaseModel):
    """Response schema for lightweight quiz pass status check."""

    content_id: str
    user_id: int
    has_passed: bool
    best_score: int | None = None


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


_training_content_generator: TrainingContentGenerator | None = None


def get_training_content_generator() -> TrainingContentGenerator:
    """Provide a TrainingContentGenerator instance as a FastAPI dependency."""
    global _training_content_generator
    if _training_content_generator is None:
        _training_content_generator = TrainingContentGenerator()
    return _training_content_generator


def get_quiz_service(
    generator: TrainingContentGenerator = Depends(get_training_content_generator),
) -> QuizService:
    """Provide a QuizService instance as a FastAPI dependency."""
    return QuizService(content_generator=generator)


def get_training_service(
    quiz_service: QuizService = Depends(get_quiz_service),
) -> TrainingService:
    """Provide a TrainingService instance as a FastAPI dependency."""
    return TrainingService(quiz_service=quiz_service)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=list[TrainingTaskResponse])
async def get_training_tasks(
    user_id: int = Query(..., description="User ID to get tasks for"),
    session: AsyncSession = Depends(get_db_session),
    service: TrainingService = Depends(get_training_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[TrainingTaskResponse]:
    """Get all training tasks assigned to a user.

    Args:
        user_id: The user's primary key.
        session: Database session (injected).
        service: TrainingService instance (injected).

    Returns:
        List of training tasks assigned to the user.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
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
    tenant: TenantContext = Depends(get_tenant_context),
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
    # TODO: Pass tenant.company_id to service layer for filtering
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
    tenant: TenantContext = Depends(get_tenant_context),
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
    # TODO: Pass tenant.company_id to service layer for filtering
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
# Training Content Endpoints (Task 16.7)
# ---------------------------------------------------------------------------


@router.get("/content/{content_id}", response_model=TrainingContentResponse)
async def get_training_content(
    content_id: str,
    generator: TrainingContentGenerator = Depends(get_training_content_generator),
    tenant: TenantContext = Depends(get_tenant_context),
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
    # TODO: Pass tenant.company_id to service layer for filtering
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
    tenant: TenantContext = Depends(get_tenant_context),
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
    tenant: TenantContext = Depends(get_tenant_context),
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


# ---------------------------------------------------------------------------
# Quiz Endpoints (Phase 3.5)
# ---------------------------------------------------------------------------


@router.post("/quiz/submit", response_model=QuizSubmitResponse)
async def submit_quiz(
    request: QuizSubmitRequest,
    session: AsyncSession = Depends(get_db_session),
    quiz_service: QuizService = Depends(get_quiz_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> QuizSubmitResponse:
    """Submit quiz answers for evaluation and scoring.

    Evaluates the submitted answers against the correct answers for the
    training content, computes the score, determines pass/fail status
    using the 80% threshold, and persists a QuizAttempt record.

    The X-Change-Reason header is required (enforced by audit middleware).

    Args:
        request: Quiz submission with content_id, user_id, and answers.
        session: Database session (injected).
        quiz_service: QuizService instance (injected).
        tenant: Tenant context (injected).

    Returns:
        Quiz attempt result with score, pass/fail, and correct answers.

    Raises:
        HTTPException: 404 if training content or user not found.
        HTTPException: 400 if training content is not in approved status.
        HTTPException: 422 if request body validation fails.
    """
    attempt = await quiz_service.evaluate_and_persist(
        session=session,
        content_id=request.content_id,
        user_id=request.user_id,
        answers=request.answers,
        company_id=tenant.company_id,
    )

    # Build correct_answers map from training content
    content = quiz_service._content_generator.get_content(request.content_id)
    correct_answers = {
        q.question_id: q.correct_answer for q in content.quiz_questions
    }

    return QuizSubmitResponse(
        attempt_id=attempt.id,
        score=attempt.score,
        total_questions=attempt.total_questions,
        passed=attempt.passed,
        passing_score_threshold=0.8,
        correct_answers=correct_answers,
        attempted_at=attempt.attempted_at,
    )


@router.get("/quiz/results/{content_id}", response_model=QuizResultsResponse)
async def get_quiz_results(
    content_id: str,
    user_id: int = Query(..., gt=0, description="User ID to get results for"),
    session: AsyncSession = Depends(get_db_session),
    quiz_service: QuizService = Depends(get_quiz_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> QuizResultsResponse:
    """Get quiz attempt history for a user and training content.

    Returns the most recent quiz attempts (up to 50) ordered by
    attempted_at descending, along with a has_passed boolean indicating
    whether the user has ever passed the quiz for this content.

    Args:
        content_id: Training content identifier.
        user_id: The user's primary key (must be a positive integer).
        session: Database session (injected).
        quiz_service: QuizService instance (injected).
        tenant: Tenant context (injected).

    Returns:
        Quiz results with attempt history and pass status.

    Raises:
        HTTPException: 422 if user_id is missing or invalid.
    """
    results = await quiz_service.get_user_results(
        session=session,
        user_id=user_id,
        content_id=content_id,
        limit=50,
    )
    has_passed = await quiz_service.has_user_passed(
        session=session,
        user_id=user_id,
        content_id=content_id,
    )

    return QuizResultsResponse(
        results=[
            QuizResultItem(
                attempt_id=attempt.id,
                score=attempt.score,
                total_questions=attempt.total_questions,
                passed=attempt.passed,
                attempted_at=attempt.attempted_at,
                answers=attempt.answers,
            )
            for attempt in results
        ],
        has_passed=has_passed,
    )


@router.get("/quiz/passed/{content_id}", response_model=QuizPassStatusResponse)
async def get_quiz_pass_status(
    content_id: str,
    user_id: int = Query(..., gt=0, description="User ID to check pass status for"),
    session: AsyncSession = Depends(get_db_session),
    quiz_service: QuizService = Depends(get_quiz_service),
    tenant: TenantContext = Depends(get_tenant_context),
) -> QuizPassStatusResponse:
    """Check if a user has passed the quiz for a specific training content.

    Lightweight endpoint for the frontend gate guard and task completion
    flow to verify quiz pass status efficiently. Returns the pass status
    and best score without full attempt history.

    Args:
        content_id: Training content identifier.
        user_id: The user's primary key (must be a positive integer).
        session: Database session (injected).
        quiz_service: QuizService instance (injected).
        tenant: Tenant context (injected).

    Returns:
        Quiz pass status with content_id, user_id, has_passed, and best_score.

    Raises:
        HTTPException: 422 if user_id is missing or not a positive integer.
    """
    has_passed = await quiz_service.has_user_passed(
        session=session,
        user_id=user_id,
        content_id=content_id,
    )
    best_score = await quiz_service.get_best_score(
        session=session,
        user_id=user_id,
        content_id=content_id,
    )

    return QuizPassStatusResponse(
        content_id=content_id,
        user_id=user_id,
        has_passed=has_passed,
        best_score=best_score,
    )


# ---------------------------------------------------------------------------
# Quiz Immutability Handlers (Phase 3.5 - ALCOA+ Compliance)
# ---------------------------------------------------------------------------

_QUIZ_IMMUTABLE_DETAIL = (
    "Quiz attempt records are immutable and cannot be modified or deleted."
)


@router.api_route(
    "/quiz/submit",
    methods=["PUT", "PATCH", "DELETE"],
    status_code=405,
    include_in_schema=True,
)
async def quiz_submit_method_not_allowed() -> None:
    """Reject PUT/PATCH/DELETE on quiz submit endpoint.

    Quiz attempt records are append-only for ALCOA+ audit compliance.
    """
    raise HTTPException(status_code=405, detail=_QUIZ_IMMUTABLE_DETAIL)


@router.api_route(
    "/quiz/results/{content_id}",
    methods=["PUT", "PATCH", "DELETE"],
    status_code=405,
    include_in_schema=True,
)
async def quiz_results_method_not_allowed(content_id: str) -> None:
    """Reject PUT/PATCH/DELETE on quiz results endpoint.

    Quiz attempt records are append-only for ALCOA+ audit compliance.
    """
    raise HTTPException(status_code=405, detail=_QUIZ_IMMUTABLE_DETAIL)


@router.api_route(
    "/quiz/passed/{content_id}",
    methods=["PUT", "PATCH", "DELETE"],
    status_code=405,
    include_in_schema=True,
)
async def quiz_passed_method_not_allowed(content_id: str) -> None:
    """Reject PUT/PATCH/DELETE on quiz pass status endpoint.

    Quiz attempt records are append-only for ALCOA+ audit compliance.
    """
    raise HTTPException(status_code=405, detail=_QUIZ_IMMUTABLE_DETAIL)


@router.api_route(
    "/quiz/{path:path}",
    methods=["PUT", "PATCH", "DELETE"],
    status_code=405,
    include_in_schema=False,
)
async def quiz_catch_all_method_not_allowed(path: str) -> None:
    """Catch-all: reject PUT/PATCH/DELETE on any quiz sub-path.

    Quiz attempt records are append-only for ALCOA+ audit compliance.
    """
    raise HTTPException(status_code=405, detail=_QUIZ_IMMUTABLE_DETAIL)
