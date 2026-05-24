"""FastAPI router for AI-generated training question endpoints.

Provides endpoints for:
- POST /api/training/questions/generate: Request async question generation
- GET /api/training/questions/{document_id}: List generated questions with filters
- PATCH /api/training/questions/{question_id}/approve: Approve a question
- PATCH /api/training/questions/{question_id}/reject: Reject a question

References:
    - Design doc Section 7: Training Questions Router
    - Requirements 9.4, 9.5, 9.6: Training Questions API Endpoints
    - Requirements 4.1–4.14: Automated Question Generator
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.training_ecosystem import (
    GeneratedQuestionResponse,
    JobAcceptedResponse,
    QuestionGenerateRequest,
)
from alcoabase.services.question_generator import QuestionGeneratorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training/questions", tags=["training-questions"])


# ---------------------------------------------------------------------------
# Dependency: QuestionGeneratorService
# ---------------------------------------------------------------------------

_question_generator_service: QuestionGeneratorService | None = None


def set_question_generator_service(service: QuestionGeneratorService) -> None:
    """Set the module-level QuestionGeneratorService instance.

    Called during application startup to wire the service into the router.

    Args:
        service: The initialized QuestionGeneratorService instance.
    """
    global _question_generator_service
    _question_generator_service = service


def get_question_generator_service() -> QuestionGeneratorService:
    """Provide the QuestionGeneratorService as a FastAPI dependency.

    If the service has not been explicitly set via set_question_generator_service,
    creates one lazily using the database session factory and service factory.

    Returns:
        The QuestionGeneratorService instance.

    Raises:
        HTTPException 503: If required dependencies are not available.
    """
    global _question_generator_service
    if _question_generator_service is None:
        try:
            from alcoabase import database
            from alcoabase.services.service_factory import get_inference_client

            session_factory = database._session_factory
            if session_factory is None:
                raise HTTPException(
                    status_code=503,
                    detail="Question generator service is not available.",
                )

            inference_client = get_inference_client()

            # Get agent registry from the agents router module
            from alcoabase.api.agents import _agent_registry_service

            if _agent_registry_service is None:
                raise HTTPException(
                    status_code=503,
                    detail="Question generator service is not available.",
                )

            _question_generator_service = QuestionGeneratorService(
                session_factory=session_factory,
                inference_client=inference_client,
                agent_registry=_agent_registry_service,
            )
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail="Question generator service is not available.",
            )

    return _question_generator_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=JobAcceptedResponse, status_code=202)
async def generate_questions(
    request: QuestionGenerateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    service: QuestionGeneratorService = Depends(get_question_generator_service),
) -> JobAcceptedResponse:
    """Request async question generation for a document.

    Dispatches a Celery task to generate comprehension questions from
    the specified document version. Returns immediately with a job_id
    for status polling.

    The X-Change-Reason header is required (enforced by audit middleware).

    Args:
        request: Question generation parameters including document_id,
            document_version_id, question_count, and difficulty_distribution.
        tenant: Resolved tenant context (company_id, user_id).
        x_change_reason: Audit trail reason for the mutation.
        service: QuestionGeneratorService instance (injected).

    Returns:
        JobAcceptedResponse with job_id and status "pending".

    Raises:
        HTTPException 404: If document not found or doesn't belong to company.
    """
    job_id = await service.request_generation(
        document_id=request.document_id,
        document_version_id=request.document_version_id,
        company_id=tenant.company_id,
        question_count=request.question_count,
        difficulty_distribution=request.difficulty_distribution,
    )

    return JobAcceptedResponse(job_id=job_id, status="pending")


@router.get("/{document_id}", response_model=list[GeneratedQuestionResponse])
async def list_questions(
    document_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: QuestionGeneratorService = Depends(get_question_generator_service),
    status: str | None = Query(default=None, description="Filter by content status"),
    difficulty_level: str | None = Query(
        default=None, description="Filter by difficulty level"
    ),
    question_type: str | None = Query(
        default=None, description="Filter by question type"
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> list[GeneratedQuestionResponse]:
    """List generated questions for a document with filtering and pagination.

    Returns questions scoped to the requesting company. Supports filtering
    by status, difficulty_level, and question_type.

    Args:
        document_id: Source document ID.
        tenant: Resolved tenant context (company_id).
        service: QuestionGeneratorService instance (injected).
        status: Optional filter by content status.
        difficulty_level: Optional filter by difficulty level.
        question_type: Optional filter by question type.
        limit: Maximum number of results (1–100, default 20).
        offset: Pagination offset (default 0).

    Returns:
        List of GeneratedQuestionResponse objects.
    """
    questions, _total = await service.get_questions(
        document_id=document_id,
        company_id=tenant.company_id,
        status=status,
        difficulty_level=difficulty_level,
        question_type=question_type,
        limit=limit,
        offset=offset,
    )

    return [
        GeneratedQuestionResponse.model_validate(q) for q in questions
    ]


@router.patch(
    "/{question_id}/approve", response_model=GeneratedQuestionResponse
)
async def approve_question(
    question_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    service: QuestionGeneratorService = Depends(get_question_generator_service),
) -> GeneratedQuestionResponse:
    """Approve a generated question for use in assessments.

    Only questions in pending_review status can be approved. The reviewer
    is identified from the X-User-Id header (via tenant context).

    The X-Change-Reason header is required (enforced by audit middleware).

    Args:
        question_id: ID of the question to approve.
        tenant: Resolved tenant context (company_id, user_id).
        x_change_reason: Audit trail reason for the mutation.
        service: QuestionGeneratorService instance (injected).

    Returns:
        The updated GeneratedQuestionResponse.

    Raises:
        HTTPException 404: If question not found or doesn't belong to company.
        HTTPException 400: If question is not in pending_review status.
    """
    question = await service.approve_question(
        question_id=question_id,
        reviewer_id=tenant.user_id,
        company_id=tenant.company_id,
    )

    return GeneratedQuestionResponse.model_validate(question)


@router.patch(
    "/{question_id}/reject", response_model=GeneratedQuestionResponse
)
async def reject_question(
    question_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    service: QuestionGeneratorService = Depends(get_question_generator_service),
) -> GeneratedQuestionResponse:
    """Reject a generated question.

    Only questions in pending_review status can be rejected. The reviewer
    is identified from the X-User-Id header (via tenant context).

    The X-Change-Reason header is required (enforced by audit middleware).

    Args:
        question_id: ID of the question to reject.
        tenant: Resolved tenant context (company_id, user_id).
        x_change_reason: Audit trail reason for the mutation.
        service: QuestionGeneratorService instance (injected).

    Returns:
        The updated GeneratedQuestionResponse.

    Raises:
        HTTPException 404: If question not found or doesn't belong to company.
        HTTPException 400: If question is not in pending_review status.
    """
    question = await service.reject_question(
        question_id=question_id,
        reviewer_id=tenant.user_id,
        company_id=tenant.company_id,
    )

    return GeneratedQuestionResponse.model_validate(question)
