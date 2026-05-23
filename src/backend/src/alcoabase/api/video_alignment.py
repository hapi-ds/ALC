"""FastAPI router for video alignment endpoints.

Provides endpoints for video frame extraction, analysis, audio transcription,
SOP linking, alignment, discrepancy report retrieval, and job status polling.

References:
    - Design doc Section 6: Video Alignment Router
    - Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8
"""

import logging
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.document import Document
from alcoabase.schemas.video_alignment import (
    DiscrepancyReportResponse,
    JobStatusDetailResponse,
    JobStatusResponse,
    LinkSOPRequest,
    SOPLinkResponse,
)
from alcoabase.services.alignment_service import AlignmentService
from alcoabase.services.job_tracker import JobConflictError, JobTracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/videos", tags=["Video Alignment"])

# UUID v4 pattern for document_uuid validation
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Document-UUID format used in this project: YYYY-NNNNN
_DOCUMENT_UUID_PATTERN = re.compile(r"^\d{4}-\d{5}$")


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_alignment_service() -> AlignmentService:
    """Provide the AlignmentService instance as a FastAPI dependency.

    Uses the service factory pattern to ensure shared dependencies
    (ModelManager, InferenceClient, KnowledgeService) are properly wired.

    Returns:
        The properly wired AlignmentService instance.
    """
    from alcoabase.services.service_factory import (
        get_inference_client,
        get_knowledge_service,
        get_model_manager,
    )

    return AlignmentService(
        model_manager=get_model_manager(),
        inference_client=get_inference_client(),
        knowledge_service=get_knowledge_service(),
    )


def get_job_tracker() -> JobTracker:
    """Provide the JobTracker instance as a FastAPI dependency.

    Returns:
        A JobTracker instance.
    """
    return JobTracker()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_document_uuid_format(document_uuid: str) -> None:
    """Validate document_uuid matches expected format.

    Accepts both UUID v4 format and the project's YYYY-NNNNN format.

    Args:
        document_uuid: The document UUID string to validate.

    Raises:
        HTTPException: 422 if format is invalid.
    """
    if not _UUID_PATTERN.match(document_uuid) and not _DOCUMENT_UUID_PATTERN.match(
        document_uuid
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid document_uuid format: '{document_uuid}'. "
            f"Expected UUID v4 or YYYY-NNNNN format.",
        )


async def _get_validated_document(
    document_uuid: str,
    tenant: TenantContext,
    session: AsyncSession,
) -> Document:
    """Validate document exists, belongs to tenant, and is a Training Video.

    Args:
        document_uuid: The document UUID to look up.
        tenant: Resolved tenant context with company_id.
        session: Active database session.

    Returns:
        The validated Document instance.

    Raises:
        HTTPException: 422 if UUID format invalid, 404 if not found,
            403 if wrong tenant, 422 if wrong document_type.
    """
    _validate_document_uuid_format(document_uuid)

    result = await session.execute(
        select(Document).where(Document.document_uuid == document_uuid)
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document '{document_uuid}' not found.",
        )

    if document.company_id != tenant.company_id:
        raise HTTPException(
            status_code=403,
            detail=f"Document '{document_uuid}' does not belong to your company.",
        )

    if document.document_type != "Training Video":
        raise HTTPException(
            status_code=422,
            detail=f"Document '{document_uuid}' is not a Training Video "
            f"(type: '{document.document_type}'). "
            f"Only Training Video documents support video alignment operations.",
        )

    return document


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{document_uuid}/extract-frames", status_code=202)
async def extract_frames(
    document_uuid: str,
    interval_seconds: int = Query(default=5, ge=1, le=60),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    service: AlignmentService = Depends(get_alignment_service),
) -> JobStatusResponse:
    """Trigger frame extraction for a Training Video document.

    Extracts key frames from the video at the specified interval using ffmpeg.
    Returns immediately with a job_id for polling progress.

    Args:
        document_uuid: UUID of the Training Video document.
        interval_seconds: Seconds between frame extractions (1-60).
        x_change_reason: Audit reason for the operation.
        tenant: Resolved tenant context.
        session: Database session.
        service: AlignmentService dependency.

    Returns:
        JobStatusResponse with job_id and processing status.

    Raises:
        HTTPException: 404/403/422 for document validation failures,
            409 if extraction already in progress.
    """
    await _get_validated_document(document_uuid, tenant, session)

    try:
        job_id = await service.extract_frames(
            document_uuid=document_uuid,
            interval_seconds=interval_seconds,
        )
    except JobConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Frame extraction is already in progress for document "
            f"'{document_uuid}' (job_id: {e.existing_job_id}).",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return JobStatusResponse(
        job_id=job_id,
        status="processing",
        estimated_duration_seconds=60,
    )


@router.post("/{document_uuid}/analyze-frames", status_code=202)
async def analyze_frames(
    document_uuid: str,
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    service: AlignmentService = Depends(get_alignment_service),
) -> JobStatusResponse:
    """Trigger frame analysis via Vision Model for a Training Video.

    Analyzes previously extracted frames using the vision model to produce
    a Step_Sequence. Frame extraction must be completed first.

    Args:
        document_uuid: UUID of the Training Video document.
        x_change_reason: Audit reason for the operation.
        tenant: Resolved tenant context.
        session: Database session.
        service: AlignmentService dependency.

    Returns:
        JobStatusResponse with job_id and processing status.

    Raises:
        HTTPException: 404/403/422 for document validation failures,
            409 if analysis already in progress,
            422 if frame extraction not completed.
    """
    await _get_validated_document(document_uuid, tenant, session)

    try:
        job_id = await service.analyze_frames(document_uuid=document_uuid)
    except JobConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Frame analysis is already in progress for document "
            f"'{document_uuid}' (job_id: {e.existing_job_id}).",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return JobStatusResponse(
        job_id=job_id,
        status="processing",
        estimated_duration_seconds=300,
    )


@router.post("/{document_uuid}/transcribe-audio", status_code=202)
async def transcribe_audio(
    document_uuid: str,
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    service: AlignmentService = Depends(get_alignment_service),
) -> JobStatusResponse:
    """Trigger audio transcription for a Training Video.

    Extracts and transcribes the audio track from the video file.
    Returns immediately with a job_id for polling progress.

    Args:
        document_uuid: UUID of the Training Video document.
        x_change_reason: Audit reason for the operation.
        tenant: Resolved tenant context.
        session: Database session.
        service: AlignmentService dependency.

    Returns:
        JobStatusResponse with job_id and processing status.

    Raises:
        HTTPException: 404/403/422 for document validation failures,
            409 if transcription already in progress.
    """
    await _get_validated_document(document_uuid, tenant, session)

    try:
        job_id = await service.transcribe_audio(document_uuid=document_uuid)
    except JobConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Audio transcription is already in progress for document "
            f"'{document_uuid}' (job_id: {e.existing_job_id}).",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return JobStatusResponse(
        job_id=job_id,
        status="processing",
        estimated_duration_seconds=120,
    )


@router.post("/{document_uuid}/link-sop", status_code=201)
async def link_sop(
    document_uuid: str,
    request: LinkSOPRequest,
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    service: AlignmentService = Depends(get_alignment_service),
) -> SOPLinkResponse:
    """Link an SOP document to a Training Video for alignment.

    Creates an association between the video and an SOP document.
    Maximum 10 SOPs can be linked per video.

    Args:
        document_uuid: UUID of the Training Video document.
        request: LinkSOPRequest with sop_document_uuid and optional version.
        x_change_reason: Audit reason for the operation.
        tenant: Resolved tenant context.
        session: Database session.
        service: AlignmentService dependency.

    Returns:
        SOPLinkResponse with link details.

    Raises:
        HTTPException: 404/403/422 for document validation failures,
            409 if SOP already linked, 422 if validation fails.
    """
    await _get_validated_document(document_uuid, tenant, session)

    try:
        link_result = await service.link_sop(
            video_document_uuid=document_uuid,
            sop_document_uuid=request.sop_document_uuid,
            sop_version=request.sop_version,
            company_id=tenant.company_id,
        )
    except JobConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=f"SOP '{request.sop_document_uuid}' is already linked "
            f"to video '{document_uuid}'.",
        )
    except ValueError as e:
        error_msg = str(e)
        # Distinguish between "already linked" (409) and other validation errors (422)
        if "already linked" in error_msg.lower():
            raise HTTPException(status_code=409, detail=error_msg)
        raise HTTPException(status_code=422, detail=error_msg)

    return SOPLinkResponse(
        video_document_uuid=link_result.get(
            "video_document_uuid", document_uuid
        ),
        sop_document_uuid=link_result.get(
            "sop_document_uuid", request.sop_document_uuid
        ),
        sop_version=link_result.get("sop_version", request.sop_version or "latest"),
        linked_at=link_result.get("linked_at"),
    )


@router.post("/{document_uuid}/align", status_code=202)
async def trigger_alignment(
    document_uuid: str,
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    service: AlignmentService = Depends(get_alignment_service),
) -> JobStatusResponse:
    """Trigger alignment between video steps and linked SOPs.

    Compares the video's extracted Step_Sequence against linked SOP
    procedures and generates a Discrepancy_Report.

    Args:
        document_uuid: UUID of the Training Video document.
        x_change_reason: Audit reason for the operation.
        tenant: Resolved tenant context.
        session: Database session.
        service: AlignmentService dependency.

    Returns:
        JobStatusResponse with job_id and processing status.

    Raises:
        HTTPException: 404/403/422 for document validation failures,
            409 if alignment already in progress,
            422 if prerequisites not met.
    """
    await _get_validated_document(document_uuid, tenant, session)

    try:
        job_id = await service.align(document_uuid=document_uuid)
    except JobConflictError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Alignment is already in progress for document "
            f"'{document_uuid}' (job_id: {e.existing_job_id}).",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return JobStatusResponse(
        job_id=job_id,
        status="processing",
        estimated_duration_seconds=180,
    )


@router.get("/{document_uuid}/report")
async def get_report(
    document_uuid: str,
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    service: AlignmentService = Depends(get_alignment_service),
) -> DiscrepancyReportResponse:
    """Retrieve the latest discrepancy report for a Training Video.

    Returns the most recent alignment report comparing the video's
    extracted steps against linked SOP procedures.

    Args:
        document_uuid: UUID of the Training Video document.
        tenant: Resolved tenant context.
        session: Database session.
        service: AlignmentService dependency.

    Returns:
        DiscrepancyReportResponse with full alignment details.

    Raises:
        HTTPException: 404 if document not found or no report exists,
            403 if wrong tenant, 422 if invalid UUID format.
    """
    await _get_validated_document(document_uuid, tenant, session)

    report = await service.get_report(document_uuid=document_uuid)

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No alignment report has been generated for document "
            f"'{document_uuid}'. Run frame extraction, analysis, and "
            f"alignment first.",
        )

    return DiscrepancyReportResponse(**report)


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    tracker: JobTracker = Depends(get_job_tracker),
) -> JobStatusDetailResponse:
    """Get the current status of a processing job.

    Polls the status of an async operation (frame extraction, analysis,
    transcription, or alignment).

    Args:
        job_id: UUID of the processing job.
        tenant: Resolved tenant context.
        session: Database session.
        tracker: JobTracker dependency.

    Returns:
        JobStatusDetailResponse with full job state.

    Raises:
        HTTPException: 404 if job_id not found.
    """
    job = await tracker.get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found.",
        )

    return JobStatusDetailResponse(
        job_id=job.job_id,
        status=job.status.value if hasattr(job.status, "value") else job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        progress_percent=job.progress_percent,
        result_reference=job.result_reference,
        error_message=job.error_message,
    )
