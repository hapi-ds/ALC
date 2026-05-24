"""FastAPI router for dynamic training feedback endpoints.

Provides endpoints for:
- GET /api/training/feedback/{question_id} — return paragraph-level dynamic
  feedback for an incorrectly answered question.

The endpoint returns 403 if the user has no failed attempts for the question,
ensuring feedback is only available after genuine incorrect answers.

References:
    - Design doc Section 5: Dynamic Feedback Service
    - Design doc Section 7: FastAPI Routers — Dynamic Feedback Router
    - Requirements 9.11, 9.12: Dynamic Feedback API
"""

from fastapi import APIRouter, Depends

from alcoabase.database import _session_factory
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.training_ecosystem import DynamicFeedbackResponse
from alcoabase.services.dynamic_feedback import DynamicFeedbackService
from alcoabase.services.service_factory import (
    get_inference_client,
    get_knowledge_service,
)

router = APIRouter(prefix="/training/feedback", tags=["training-feedback"])


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_dynamic_feedback_service() -> DynamicFeedbackService:
    """Provide a DynamicFeedbackService instance as a FastAPI dependency.

    Returns:
        DynamicFeedbackService: Configured service with session factory,
            inference client, and knowledge service.

    Raises:
        RuntimeError: If the database has not been initialized.
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    return DynamicFeedbackService(
        session_factory=_session_factory,
        inference_client=get_inference_client(),
        knowledge_service=get_knowledge_service(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{question_id}", response_model=DynamicFeedbackResponse)
async def get_training_feedback(
    question_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: DynamicFeedbackService = Depends(get_dynamic_feedback_service),
) -> DynamicFeedbackResponse:
    """Get paragraph-level dynamic feedback for an incorrectly answered question.

    Retrieves RAG-powered feedback including the source paragraph, section
    reference, page number, and an LLM-generated explanation connecting
    the paragraph to the correct answer.

    Args:
        question_id: ID of the question to get feedback for.
        tenant: Resolved tenant context (provides company_id and user_id).
        service: DynamicFeedbackService instance (injected).

    Returns:
        DynamicFeedbackResponse with correct_answer, paragraph_text,
        section_reference, page_number, and explanation.

    Raises:
        HTTPException 403: If the user has no failed attempts for the question.
        HTTPException 404: If the question does not exist or does not belong
            to the user's company.
    """
    return await service.get_feedback(
        question_id=question_id,
        user_id=tenant.user_id,
        company_id=tenant.company_id,
    )
