"""FastAPI router for ALC corporate environment seed endpoint.

Provides the POST /api/admin/seed-alc-corporate endpoint that triggers
the full ALC corporate environment seeding sequence. Requires
system_administrator role authentication and X-Change-Reason header
(enforced by audit middleware).

References:
    - Design: .kiro/specs/Step_8-2_alc-corporate-environment-setup/design.md
    - Requirements: 6.2, 6.8
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.schemas.alc_seed import SeedError, SeedReport
from alcoabase.services.alc_seed_service import ALCSeedService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Seed"])


@router.post(
    "/seed-alc-corporate",
    response_model=SeedReport,
    responses={
        400: {"description": "Missing X-Change-Reason header"},
        401: {"description": "Unauthorized"},
        403: {"description": "Insufficient permissions"},
        500: {"model": SeedError, "description": "Seeding failed"},
    },
)
async def seed_alc_corporate(
    ctx: TenantContext = Depends(require_permission("system_config", "create")),
    session: AsyncSession = Depends(get_db_session),
) -> SeedReport | JSONResponse:
    """Execute the ALC corporate environment seeding sequence.

    Triggers the full seeding process: company creation, user pool
    provisioning, regulatory baseline, folder structure, risk profile,
    agent activations, and governance workflow.

    Requires system_administrator role. The X-Change-Reason header is
    enforced by the audit middleware for all mutating requests.

    Args:
        ctx: Resolved tenant context with system_config:create permission.
        session: Database session (auto-commits on success, rollbacks on error).

    Returns:
        SeedReport on success (HTTP 200), or SeedError on failure (HTTP 500).
    """
    try:
        service = ALCSeedService(session)
        report = await service.execute()

        logger.info(
            "ALC corporate environment seed completed successfully via API "
            "(user_id=%d, company_id=%d)",
            ctx.user_id,
            ctx.company_id,
            extra={"seed_step": "api_endpoint"},
        )

        return report

    except Exception as e:
        logger.error(
            "ALC corporate environment seed failed via API: %s",
            str(e),
            exc_info=True,
            extra={"seed_step": "api_endpoint"},
        )

        # Determine the failed step from the error message
        error_msg = str(e)
        failed_step = "unknown"
        if "company" in error_msg.lower():
            failed_step = "company_creation"
        elif "user" in error_msg.lower() or "admin" in error_msg.lower():
            failed_step = "user_provisioning"
        elif "regulatory" in error_msg.lower() or "baseline" in error_msg.lower():
            failed_step = "regulatory_baseline"
        elif "folder" in error_msg.lower():
            failed_step = "folder_structure"
        elif "risk" in error_msg.lower() or "task type" in error_msg.lower():
            failed_step = "risk_profile"
        elif "agent" in error_msg.lower():
            failed_step = "agent_activation"
        elif "workflow" in error_msg.lower():
            failed_step = "governance_workflow"

        seed_error = SeedError(
            error=f"ALC corporate environment seeding failed: {error_msg}",
            failed_step=failed_step,
            detail=error_msg,
        )

        return JSONResponse(
            status_code=500,
            content=seed_error.model_dump(),
        )
