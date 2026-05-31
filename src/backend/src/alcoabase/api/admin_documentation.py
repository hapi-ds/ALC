"""FastAPI router for documentation suite generation endpoint.

Provides the POST /api/admin/generate-documentation endpoint that triggers
the full documentation suite generation (User Guide + Admin Guide), upload,
tagging, and workflow application sequence. Requires system_administrator or
document_administrator role authentication and X-Change-Reason header.

References:
    - Design: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
    - Requirements: 4.2, 4.6, 4.7, 4.8, 4.9
"""

import logging
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.schemas.documentation_generation import (
    DocumentationGenerationError,
    DocumentationGenerationReport,
)
from alcoabase.services.documentation_generator_service import (
    DocumentationGeneratorService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Documentation"])


@router.post(
    "/generate-documentation",
    response_model=DocumentationGenerationReport,
    responses={
        400: {"description": "Missing X-Change-Reason header"},
        401: {"description": "Unauthorized"},
        403: {"description": "Insufficient permissions"},
        409: {"description": "Generation already in progress"},
        500: {
            "model": DocumentationGenerationError,
            "description": "Documentation generation failed",
        },
    },
)
async def generate_documentation(
    ctx: TenantContext = Depends(require_permission("documents", "approve")),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: str | None = Header(default=None, alias="X-Change-Reason"),
) -> DocumentationGenerationReport | JSONResponse:
    """Execute the documentation suite generation and upload sequence.

    Triggers the full documentation generation process: content generation
    for 2 guide documents (User Guide + Admin Guide), document upload,
    tag application, and governance workflow assignment. All operations
    execute within a single database transaction.

    Requires system_administrator or document_administrator role
    (documents:approve permission). The X-Change-Reason header is
    required for audit compliance.

    Args:
        ctx: Resolved tenant context with documents:approve permission.
        session: Database session (auto-commits on success, rollbacks on error).
        x_change_reason: Required audit header for mutating operations.

    Returns:
        DocumentationGenerationReport on success (HTTP 200), or
        DocumentationGenerationError on failure (HTTP 500), or
        HTTP 409 if generation is already in progress.
    """
    # Explicitly validate X-Change-Reason header
    if not x_change_reason or not x_change_reason.strip():
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating "
            "requests to GxP-relevant endpoints.",
        )

    try:
        service = DocumentationGeneratorService(session)
        report = await service.execute()

        logger.info(
            "Documentation suite generation completed successfully via API "
            "(user_id=%d, company_id=%d)",
            ctx.user_id,
            ctx.company_id,
            extra={"documentation_step": "api_endpoint"},
        )

        return report

    except RuntimeError as e:
        error_msg = str(e)

        # Handle concurrent generation (advisory lock conflict)
        if "already in progress" in error_msg.lower():
            logger.warning(
                "Documentation suite generation rejected — concurrent generation "
                "in progress (user_id=%d, company_id=%d)",
                ctx.user_id,
                ctx.company_id,
                extra={"documentation_step": "api_endpoint"},
            )
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Documentation generation is already in progress. "
                    "Please wait for the current generation to complete."
                },
            )

        # All other RuntimeErrors are generation failures
        logger.error(
            "Documentation suite generation failed via API: %s",
            error_msg,
            exc_info=True,
            extra={"documentation_step": "api_endpoint"},
        )

        failed_operation = _determine_failed_operation(error_msg)

        # Extract document title from error if present
        document_title = _extract_document_title(error_msg)

        generation_error = DocumentationGenerationError(
            error=f"Documentation suite generation failed: {error_msg}",
            failed_operation=failed_operation,
            document_title=document_title,
            detail=error_msg,
        )

        return JSONResponse(
            status_code=500,
            content=generation_error.model_dump(),
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(
            "Documentation suite generation failed via API (unexpected): %s",
            error_msg,
            exc_info=True,
            extra={"documentation_step": "api_endpoint"},
        )

        generation_error = DocumentationGenerationError(
            error=f"Documentation suite generation failed: {error_msg}",
            failed_operation="unknown",
            document_title=None,
            detail=error_msg,
        )

        return JSONResponse(
            status_code=500,
            content=generation_error.model_dump(),
        )


def _determine_failed_operation(error_msg: str) -> str:
    """Determine the failed operation from the error message.

    Args:
        error_msg: The error message string from the RuntimeError.

    Returns:
        A string identifying the failed operation step.
    """
    msg_lower = error_msg.lower()

    if "not provisioned" in msg_lower or "not found" in msg_lower:
        return "prerequisite_check"
    if "cross-reference" in msg_lower or "cross_reference" in msg_lower:
        return "cross_reference_load"
    if (
        "content" in msg_lower
        or "heading" in msg_lower
        or "section" in msg_lower
        or "empty" in msg_lower
    ):
        return "content_generation"
    if "upload" in msg_lower or "storage" in msg_lower:
        return "document_upload"
    if "tag" in msg_lower:
        return "tag_application"
    if "workflow" in msg_lower:
        return "workflow_assignment"

    return "unknown"


def _extract_document_title(error_msg: str) -> str | None:
    """Extract a document title from the error message if present.

    Looks for common patterns where the service includes the document
    title in error messages (e.g., content validation failures).

    Args:
        error_msg: The error message string from the RuntimeError.

    Returns:
        The document title if found, None otherwise.
    """
    # The service includes document titles in validation errors like:
    # "Content validation failed for 'AlcoaBase — Comprehensive User Guide'"
    if "AlcoaBase" in error_msg:
        # Try to extract the title between quotes or after "for"
        match = re.search(r"['\"]([^'\"]*AlcoaBase[^'\"]*)['\"]", error_msg)
        if match:
            return match.group(1)
        # Try pattern: "for <title>: ..."
        match = re.search(r"for (AlcoaBase[^:]+)", error_msg)
        if match:
            return match.group(1).strip()

    return None
