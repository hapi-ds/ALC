"""FastAPI router for AI-enhanced training materials endpoints.

Provides endpoints for:
- POST /api/training/materials/generate: Request async material generation
- GET /api/training/materials/{document_id}: List materials for a document
- PATCH /api/training/materials/{material_id}/approve: Approve a material
- PATCH /api/training/materials/{material_id}/reject: Reject a material

All mutating endpoints require the X-Change-Reason header (enforced by
AuditMiddleware). Endpoints are scoped to the requesting company via
the TenantContext dependency.

References:
    - Design doc Section 7: Training Materials Router
    - Requirements 9.1, 9.2, 9.3: Training Materials API
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.training_ecosystem import (
    JobAcceptedResponse,
    MaterialGenerateRequest,
    TrainingMaterialResponse,
)
from alcoabase.services.training_material_generator import (
    TrainingMaterialGeneratorService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training/materials", tags=["training-materials"])


# ---------------------------------------------------------------------------
# Dependency: TrainingMaterialGeneratorService
# ---------------------------------------------------------------------------

_training_material_generator_service: TrainingMaterialGeneratorService | None = None


def set_training_material_generator_service(
    service: TrainingMaterialGeneratorService,
) -> None:
    """Set the module-level TrainingMaterialGeneratorService instance.

    Called during application startup to wire the service into the router.

    Args:
        service: The initialized TrainingMaterialGeneratorService instance.
    """
    global _training_material_generator_service
    _training_material_generator_service = service


def get_training_material_generator_service() -> TrainingMaterialGeneratorService:
    """Provide the TrainingMaterialGeneratorService as a FastAPI dependency.

    Returns:
        The module-level TrainingMaterialGeneratorService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _training_material_generator_service is None:
        raise HTTPException(
            status_code=503,
            detail="Training material generator service is not available.",
        )
    return _training_material_generator_service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/generate", response_model=JobAcceptedResponse, status_code=202)
async def generate_materials(
    request: MaterialGenerateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingMaterialGeneratorService = Depends(
        get_training_material_generator_service
    ),
) -> JobAcceptedResponse:
    """Request async generation of training materials from a document.

    Dispatches a Celery task to generate training materials for the
    specified document version. Returns immediately with a job ID for
    status polling.

    Args:
        request: Material generation request with document_id,
            document_version_id, and optional material_types.
        tenant: Resolved tenant context (company_id, user_id).
        service: TrainingMaterialGeneratorService dependency.

    Returns:
        JobAcceptedResponse with job_id and status "pending" (HTTP 202).

    Raises:
        HTTPException 404: If the document or version does not exist
            for the requesting company.
    """
    try:
        job_id = await service.request_generation(
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            company_id=tenant.company_id,
            material_types=request.material_types,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return JobAcceptedResponse(job_id=job_id, status="pending")


@router.get("/{document_id}", response_model=list[TrainingMaterialResponse])
async def list_materials(
    document_id: int,
    material_type: str | None = Query(
        default=None, description="Filter by material type"
    ),
    status: str | None = Query(
        default=None, description="Filter by content status"
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingMaterialGeneratorService = Depends(
        get_training_material_generator_service
    ),
) -> list[TrainingMaterialResponse]:
    """List generated training materials for a document.

    Returns paginated materials filtered by optional material_type and
    status parameters. Results are scoped to the requesting company.

    Args:
        document_id: Source document ID to list materials for.
        material_type: Optional filter by material type.
        status: Optional filter by content status.
        limit: Maximum number of results (1–100, default 20).
        offset: Number of results to skip (default 0).
        tenant: Resolved tenant context (company_id, user_id).
        service: TrainingMaterialGeneratorService dependency.

    Returns:
        List of TrainingMaterialResponse objects.
    """
    materials, _total = await service.get_materials(
        document_id=document_id,
        company_id=tenant.company_id,
        material_type=material_type,
        status=status,
        limit=limit,
        offset=offset,
    )

    return [
        TrainingMaterialResponse(
            id=m.id,
            document_id=m.document_id,
            document_version_id=m.document_version_id,
            material_type=m.material_type,
            content_data=m.content_data or {},
            learning_objectives=m.learning_objectives or [],
            estimated_duration_minutes=m.estimated_duration_minutes or 5,
            status=m.status,
            generated_by_agent_id=m.generated_by_agent_id,
            inference_duration_ms=m.inference_duration_ms,
            reviewed_by=m.reviewed_by,
            reviewed_at=m.reviewed_at,
            created_at=m.created_at,
        )
        for m in materials
    ]


@router.patch("/{material_id}/approve", response_model=TrainingMaterialResponse)
async def approve_material(
    material_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingMaterialGeneratorService = Depends(
        get_training_material_generator_service
    ),
) -> TrainingMaterialResponse:
    """Approve a training material after coordinator review.

    Material must be in pending_review status. The reviewer is identified
    from the X-User-Id header via the tenant context.

    Args:
        material_id: ID of the material to approve.
        tenant: Resolved tenant context (company_id, user_id as reviewer).
        service: TrainingMaterialGeneratorService dependency.

    Returns:
        Updated TrainingMaterialResponse with approved status.

    Raises:
        HTTPException 404: If material not found for the company.
        HTTPException 400: If material is not in pending_review status.
    """
    try:
        material = await service.approve_material(
            material_id=material_id,
            reviewer_id=tenant.user_id,
            company_id=tenant.company_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    return TrainingMaterialResponse(
        id=material.id,
        document_id=material.document_id,
        document_version_id=material.document_version_id,
        material_type=material.material_type,
        content_data=material.content_data or {},
        learning_objectives=material.learning_objectives or [],
        estimated_duration_minutes=material.estimated_duration_minutes or 5,
        status=material.status,
        generated_by_agent_id=material.generated_by_agent_id,
        inference_duration_ms=material.inference_duration_ms,
        reviewed_by=material.reviewed_by,
        reviewed_at=material.reviewed_at,
        created_at=material.created_at,
    )


@router.patch("/{material_id}/reject", response_model=TrainingMaterialResponse)
async def reject_material(
    material_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TrainingMaterialGeneratorService = Depends(
        get_training_material_generator_service
    ),
) -> TrainingMaterialResponse:
    """Reject a training material after coordinator review.

    Material must be in pending_review status. The reviewer is identified
    from the X-User-Id header via the tenant context.

    Args:
        material_id: ID of the material to reject.
        tenant: Resolved tenant context (company_id, user_id as reviewer).
        service: TrainingMaterialGeneratorService dependency.

    Returns:
        Updated TrainingMaterialResponse with rejected status.

    Raises:
        HTTPException 404: If material not found for the company.
        HTTPException 400: If material is not in pending_review status.
    """
    try:
        material = await service.reject_material(
            material_id=material_id,
            reviewer_id=tenant.user_id,
            company_id=tenant.company_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    return TrainingMaterialResponse(
        id=material.id,
        document_id=material.document_id,
        document_version_id=material.document_version_id,
        material_type=material.material_type,
        content_data=material.content_data or {},
        learning_objectives=material.learning_objectives or [],
        estimated_duration_minutes=material.estimated_duration_minutes or 5,
        status=material.status,
        generated_by_agent_id=material.generated_by_agent_id,
        inference_duration_ms=material.inference_duration_ms,
        reviewed_by=material.reviewed_by,
        reviewed_at=material.reviewed_at,
        created_at=material.created_at,
    )
