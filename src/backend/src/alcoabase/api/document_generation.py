"""FastAPI router for template-based document generation endpoints.

Provides endpoints for starting template-based document generation,
polling job status, retrieving generation provenance, and viewing
cross-reference maps for generated documents.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 2.1, 2.8, 2.10, 2.11, 2.12, 2.13, 3.5, 5.3, 5.6, 7.3, 7.6, 7.8, 7.9
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.document import Document
from alcoabase.models.document_generation import (
    DocumentTemplate,
    GenerationProvenance,
)
from alcoabase.schemas.document_generation import (
    CrossReferenceListResponse,
    CrossReferenceResponse,
    GenerateFromTemplateRequest,
    GenerationJobStatusResponse,
    JobAcceptedResponse,
    ProvenanceResponse,
)
from alcoabase.services.cross_reference import CrossReferenceService
from alcoabase.services.template_document_generator import (
    TemplateDocumentGeneratorService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Document Generation"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _get_generator_service() -> TemplateDocumentGeneratorService:
    """Provide the TemplateDocumentGeneratorService instance.

    Lazily constructs the service with required dependencies from
    the application's configured services.

    Returns:
        Configured TemplateDocumentGeneratorService instance.

    Raises:
        RuntimeError: If the database has not been initialized.
    """
    from alcoabase.database import _session_factory
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.job_tracker import JobTracker
    from alcoabase.services.knowledge_service import KnowledgeService
    from alcoabase.services.storage_service import StorageService
    from alcoabase.services.template_analysis import TemplateAnalysisService

    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    storage_service = StorageService()
    knowledge_service = KnowledgeService()
    inference_client = InferenceClient()
    job_tracker = JobTracker()
    template_analysis_service = TemplateAnalysisService(
        session_factory=_session_factory,
        storage_service=storage_service,
        job_tracker=job_tracker,
    )

    return TemplateDocumentGeneratorService(
        session_factory=_session_factory,
        inference_client=inference_client,
        knowledge_service=knowledge_service,
        agent_registry=None,
        storage_service=storage_service,
        job_tracker=job_tracker,
        template_analysis_service=template_analysis_service,
    )


def _get_cross_reference_service() -> CrossReferenceService:
    """Provide the CrossReferenceService instance.

    Returns:
        Configured CrossReferenceService instance.

    Raises:
        RuntimeError: If the database has not been initialized.
    """
    from alcoabase.database import _session_factory
    from alcoabase.services.knowledge_service import KnowledgeService
    from alcoabase.services.storage_service import StorageService

    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    knowledge_service = KnowledgeService()
    storage_service = StorageService()

    return CrossReferenceService(
        session_factory=_session_factory,
        knowledge_service=knowledge_service,
        storage_service=storage_service,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/generate-from-template",
    response_model=JobAcceptedResponse,
    status_code=202,
    responses={
        404: {"description": "Template not found for the company"},
        409: {"description": "Concurrent generation job already exists"},
        422: {"description": "Validation error (invalid reference docs or empty instructions)"},
    },
)
async def start_generation(
    request: GenerateFromTemplateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
) -> JobAcceptedResponse:
    """Start a template-based document generation job.

    Validates the template_id, reference_document_ids, and generation
    instructions, then dispatches an async Celery task for the full
    generation pipeline.

    Args:
        request: Generation request with template_id, title, instructions, etc.
        tenant: Resolved tenant context (company_id, user_id).
        x_change_reason: Required audit header for mutating operations.

    Returns:
        HTTP 202 with job_id and initial status "pending".

    Raises:
        HTTPException 404: If template_id not found for the company.
        HTTPException 409: If a concurrent generation job already exists.
        HTTPException 422: If reference_document_ids are invalid or
            generation_instructions is empty.
    """
    service = _get_generator_service()

    try:
        job_id = await service.request_generation(
            template_id=request.template_id,
            title=request.title,
            generation_instructions=request.generation_instructions,
            output_folder_path=request.output_folder_path,
            requesting_user_id=tenant.user_id,
            company_id=tenant.company_id,
            reference_document_ids=request.reference_document_ids,
        )
    except ValueError as e:
        error_msg = str(e)
        # Distinguish between template not found (404) and validation errors (422)
        if "Template" in error_msg and "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)
    except RuntimeError as e:
        # Concurrent job conflict
        raise HTTPException(status_code=409, detail=str(e))

    return JobAcceptedResponse(job_id=job_id, status="pending")


@router.get(
    "/generate-from-template/{job_id}/status",
    response_model=GenerationJobStatusResponse,
    responses={
        404: {"description": "Job not found for the company"},
    },
)
async def get_generation_status(
    job_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
) -> GenerationJobStatusResponse:
    """Get the status and progress of a generation job.

    Returns current progress, section information, and result metadata
    once the job completes.

    Args:
        job_id: UUID of the generation job to query.
        tenant: Resolved tenant context (company_id).

    Returns:
        Job status with progress details.

    Raises:
        HTTPException 404: If job_id not found for the company.
    """
    service = _get_generator_service()
    job = await service.get_job_status(job_id=job_id, company_id=tenant.company_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Generation job '{job_id}' not found.",
        )

    # Calculate estimated time remaining
    estimated_time_remaining: int | None = None
    if job.status == "processing" and job.progress_percent < 100:
        estimated_duration = 30 * job.sections_total
        remaining_fraction = (100 - job.progress_percent) / 100.0
        estimated_time_remaining = int(remaining_fraction * estimated_duration)

    # Get result_document_uuid if completed
    result_document_uuid: str | None = None
    if job.result_document_id is not None:
        from alcoabase.database import _session_factory

        if _session_factory is not None:
            async with _session_factory() as session:
                doc_result = await session.execute(
                    select(Document.document_uuid).where(
                        Document.id == job.result_document_id
                    )
                )
                result_document_uuid = doc_result.scalar_one_or_none()

    return GenerationJobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        current_section=job.current_section,
        sections_completed=job.sections_completed,
        sections_total=job.sections_total,
        estimated_time_remaining_seconds=estimated_time_remaining,
        error_message=job.error_message,
        result_document_id=job.result_document_id,
        result_document_uuid=result_document_uuid,
        result_storage_key=job.result_storage_key,
        file_size_bytes=job.file_size_bytes,
        generation_duration_ms=job.generation_duration_ms,
    )


@router.get(
    "/{document_id}/provenance",
    response_model=ProvenanceResponse,
    responses={
        404: {"description": "Document not AI-generated or not found for company"},
    },
)
async def get_provenance(
    document_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProvenanceResponse:
    """Get the generation provenance for an AI-generated document.

    Returns the full audit trail including template used, sources consulted,
    generation parameters, and per-section provenance details.

    Args:
        document_id: ID of the generated document.
        tenant: Resolved tenant context (company_id).
        session: Database session dependency.

    Returns:
        Full provenance record for the document.

    Raises:
        HTTPException 404: If document is not AI-generated or not found
            for the company.
    """
    # Query provenance for this document scoped to company
    result = await session.execute(
        select(GenerationProvenance).where(
            GenerationProvenance.document_id == document_id,
            GenerationProvenance.company_id == tenant.company_id,
        )
    )
    provenance = result.scalar_one_or_none()

    if provenance is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No generation provenance found for document {document_id}. "
                "Either the document was not AI-generated or does not belong "
                "to this company."
            ),
        )

    # Get the template's source document UUID for the response
    template_result = await session.execute(
        select(DocumentTemplate.document_id).where(
            DocumentTemplate.id == provenance.template_id
        )
    )
    template_doc_id = template_result.scalar_one_or_none()

    template_document_uuid = ""
    if template_doc_id is not None:
        doc_uuid_result = await session.execute(
            select(Document.document_uuid).where(Document.id == template_doc_id)
        )
        template_document_uuid = doc_uuid_result.scalar_one_or_none() or ""

    return ProvenanceResponse(
        generation_id=provenance.generation_id,
        template_id=provenance.template_id,
        template_document_uuid=template_document_uuid,
        source_document_uuids=provenance.source_document_uuids or [],
        reference_document_ids=provenance.reference_document_ids or [],
        agent_archetype=provenance.agent_archetype,
        generation_parameters=provenance.generation_parameters,
        requesting_user_id=provenance.requesting_user_id,
        total_inference_duration_ms=provenance.total_inference_duration_ms,
        total_token_count=provenance.total_token_count,
        section_provenance=provenance.section_provenance or [],
        unverified_references=provenance.unverified_references or [],
        generation_timestamp=provenance.generation_timestamp,
        previous_generation_id=provenance.previous_generation_id,
    )


@router.get(
    "/{document_id}/cross-references",
    response_model=CrossReferenceListResponse,
)
async def get_cross_references(
    document_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
) -> CrossReferenceListResponse:
    """Get the cross-reference map for a generated document.

    Returns all cross-references extracted from reference documents
    and their locations in the generated output.

    Args:
        document_id: ID of the generated document.
        tenant: Resolved tenant context (company_id).

    Returns:
        List of cross-reference entries with source document details.
    """
    service = _get_cross_reference_service()
    entries = await service.get_cross_references(
        document_id=document_id,
        company_id=tenant.company_id,
    )

    # Build response items with source document titles
    items: list[CrossReferenceResponse] = []

    from alcoabase.database import _session_factory

    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    # Cache document titles to avoid repeated queries
    doc_title_cache: dict[int, str] = {}

    async with _session_factory() as session:
        for entry in entries:
            # Get source document title (with caching)
            if entry.source_document_id not in doc_title_cache:
                doc_result = await session.execute(
                    select(Document.title).where(
                        Document.id == entry.source_document_id
                    )
                )
                title = doc_result.scalar_one_or_none() or "Unknown Document"
                doc_title_cache[entry.source_document_id] = title

            items.append(
                CrossReferenceResponse(
                    source_document_id=entry.source_document_id,
                    source_document_title=doc_title_cache[entry.source_document_id],
                    reference_type=entry.reference_type,
                    reference_identifier=entry.reference_identifier,
                    reference_text=entry.reference_text,
                    location_in_output=entry.location_in_output,
                )
            )

    return CrossReferenceListResponse(
        items=items,
        total=len(items),
    )
