"""FastAPI router for template management endpoints (AI Document Generator).

Provides endpoints for registering .docx files as Master Templates,
listing registered templates with filtering and pagination, and
retrieving individual templates with full structural analysis.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 1.1, 1.5, 1.6, 1.7, 1.9, 1.10, 1.11, 1.13
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.document_generation import (
    JobAcceptedResponse,
    TemplateListResponse,
    TemplateRegisterRequest,
    TemplateResponse,
)
from alcoabase.services.job_tracker import JobTracker
from alcoabase.services.storage_service import StorageService
from alcoabase.services.template_analysis import TemplateAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents/templates", tags=["Document Templates"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_template_analysis_service() -> TemplateAnalysisService:
    """Provide the TemplateAnalysisService instance as a FastAPI dependency.

    Creates the service with a session factory derived from the database
    module, along with StorageService and JobTracker instances.

    Returns:
        A configured TemplateAnalysisService instance.
    """
    from alcoabase.database import _session_factory

    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    return TemplateAnalysisService(
        session_factory=_session_factory,
        storage_service=StorageService(),
        job_tracker=JobTracker(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=JobAcceptedResponse,
    status_code=202,
    responses={
        200: {"model": TemplateResponse, "description": "Template already exists"},
        404: {"description": "Document or version not found"},
        422: {"description": "Validation error (non-.docx or invalid input)"},
    },
)
async def register_template(
    request: TemplateRegisterRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TemplateAnalysisService = Depends(get_template_analysis_service),
) -> JSONResponse | JobAcceptedResponse:
    """Register a .docx file as a Master Template for AI document generation.

    Accepts a document version reference and initiates async structural
    analysis. Returns HTTP 202 with a job_id for new registrations, or
    HTTP 200 with the existing template if already registered.

    Args:
        request: Template registration parameters.
        session: Database session (unused directly; tenant resolution uses it).
        tenant: Resolved tenant context with company_id and user_id.
        service: TemplateAnalysisService dependency.

    Returns:
        JobAcceptedResponse (202) for new registrations, or
        TemplateResponse (200) for duplicate registrations.

    Raises:
        HTTPException: 404 if document/version not found.
        HTTPException: 422 if file is not .docx.
    """
    try:
        template_id, job_id = await service.register_template(
            document_id=request.document_id,
            document_version_id=request.document_version_id,
            template_name=request.template_name,
            document_type_target=request.document_type_target,
            registered_by=tenant.user_id,
            company_id=tenant.company_id,
        )
    except ValueError as e:
        error_msg = str(e)
        # Distinguish between "not found" and "not .docx" errors
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        # Non-.docx file or other validation error
        raise HTTPException(status_code=422, detail=error_msg)

    # job_id is None when template already exists (duplicate detection)
    if job_id is None:
        existing_template = await service.get_template(
            template_id=template_id,
            company_id=tenant.company_id,
        )
        if existing_template is None:
            raise HTTPException(
                status_code=500,
                detail="Template registration inconsistency.",
            )
        response_data = TemplateResponse(
            id=existing_template.id,
            document_id=existing_template.document_id,
            document_version_id=existing_template.document_version_id,
            template_name=existing_template.template_name,
            document_type_target=existing_template.document_type_target,
            status=existing_template.status,
            registered_by=existing_template.registered_by,
            registered_at=existing_template.registered_at,
            template_analysis=existing_template.template_analysis,
        )
        return JSONResponse(
            status_code=200,
            content=response_data.model_dump(mode="json"),
        )

    return JobAcceptedResponse(job_id=job_id, status="pending")


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    document_type_target: str | None = Query(
        default=None,
        description="Filter by target document type (e.g., 'URS', 'SOP').",
    ),
    limit: int = Query(default=20, ge=1, le=100, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Number of items to skip."),
    tenant: TenantContext = Depends(get_tenant_context),
    service: TemplateAnalysisService = Depends(get_template_analysis_service),
) -> TemplateListResponse:
    """List registered templates with optional filtering and pagination.

    Returns templates scoped to the requesting company, optionally
    filtered by document_type_target.

    Args:
        document_type_target: Optional filter by target document type.
        limit: Maximum number of results (1-100, default 20).
        offset: Number of results to skip (default 0).
        tenant: Resolved tenant context with company_id.
        service: TemplateAnalysisService dependency.

    Returns:
        Paginated list of templates with total count.
    """
    templates, total = await service.list_templates(
        company_id=tenant.company_id,
        document_type_target=document_type_target,
        limit=limit,
        offset=offset,
    )

    items = [
        TemplateResponse(
            id=t.id,
            document_id=t.document_id,
            document_version_id=t.document_version_id,
            template_name=t.template_name,
            document_type_target=t.document_type_target,
            status=t.status,
            registered_by=t.registered_by,
            registered_at=t.registered_at,
            template_analysis=None,  # Excluded from list view
        )
        for t in templates
    ]

    return TemplateListResponse(items=items, total=total)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: TemplateAnalysisService = Depends(get_template_analysis_service),
) -> TemplateResponse:
    """Retrieve a registered template with full structural analysis.

    Returns the template details including the complete Template_Analysis
    JSON (section hierarchy, placeholders, styles, etc.).

    Args:
        template_id: The template ID to retrieve.
        tenant: Resolved tenant context with company_id.
        service: TemplateAnalysisService dependency.

    Returns:
        Template details with full analysis.

    Raises:
        HTTPException: 404 if template not found or doesn't belong to company.
    """
    template = await service.get_template(
        template_id=template_id,
        company_id=tenant.company_id,
    )

    if template is None:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} not found.",
        )

    return TemplateResponse(
        id=template.id,
        document_id=template.document_id,
        document_version_id=template.document_version_id,
        template_name=template.template_name,
        document_type_target=template.document_type_target,
        status=template.status,
        registered_by=template.registered_by,
        registered_at=template.registered_at,
        template_analysis=template.template_analysis,
    )
