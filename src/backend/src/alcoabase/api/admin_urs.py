"""FastAPI router for URS generation endpoint.

Provides the POST /api/admin/generate-urs-alc endpoint that triggers
the full URS document generation, upload, tagging, and workflow
application sequence. Requires system_administrator or
document_administrator role authentication and X-Change-Reason header
(enforced by audit middleware).

References:
    - Design: .kiro/specs/Step_8-3_urs-alc-corporate/design.md
    - Requirements: 6.2, 6.6, 6.7
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.schemas.urs_generation import URSGenerationError, URSGenerationReport
from alcoabase.services.urs_generator_service import URSGeneratorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post(
    "/generate-urs-alc",
    response_model=URSGenerationReport,
    responses={
        400: {"description": "Missing X-Change-Reason header"},
        401: {"description": "Unauthorized"},
        403: {"description": "Insufficient permissions"},
        500: {"model": URSGenerationError, "description": "URS generation failed"},
    },
)
async def generate_urs_alc(
    ctx: TenantContext = Depends(require_permission("documents", "approve")),
    session: AsyncSession = Depends(get_db_session),
) -> URSGenerationReport | JSONResponse:
    """Execute the URS generation and upload sequence.

    Triggers the full URS generation process: content generation,
    document upload, tag application, and governance workflow assignment.
    All operations execute within a single database transaction.

    Requires system_administrator or document_administrator role
    (documents:approve permission). The X-Change-Reason header is
    enforced by the audit middleware for all mutating requests.

    Args:
        ctx: Resolved tenant context with documents:approve permission.
        session: Database session (auto-commits on success, rollbacks on error).

    Returns:
        URSGenerationReport on success (HTTP 200), or
        URSGenerationError on failure (HTTP 500).
    """
    try:
        service = URSGeneratorService(session)
        report = await service.execute()

        logger.info(
            "URS generation completed successfully via API "
            "(user_id=%d, company_id=%d)",
            ctx.user_id,
            ctx.company_id,
            extra={"urs_step": "api_endpoint"},
        )

        return report

    except Exception as e:
        logger.error(
            "URS generation failed via API: %s",
            str(e),
            exc_info=True,
            extra={"urs_step": "api_endpoint"},
        )

        # Determine the failed step from the error message
        error_msg = str(e)
        failed_step = "unknown"
        if "content" in error_msg.lower() or "requirement" in error_msg.lower():
            failed_step = "content_generation"
        elif "upload" in error_msg.lower() or "storage" in error_msg.lower():
            failed_step = "document_upload"
        elif "tag" in error_msg.lower():
            failed_step = "tag_application"
        elif "workflow" in error_msg.lower():
            failed_step = "workflow_assignment"
        elif "company" in error_msg.lower():
            failed_step = "content_generation"
        elif "user" in error_msg.lower() or "admin" in error_msg.lower():
            failed_step = "content_generation"

        generation_error = URSGenerationError(
            error=f"URS generation failed: {error_msg}",
            failed_step=failed_step,
            detail=error_msg,
        )

        return JSONResponse(
            status_code=500,
            content=generation_error.model_dump(),
        )
