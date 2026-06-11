"""FastAPI router for literature screening protocol and configuration endpoints.

Provides endpoints for:
- Screening Protocol CRUD (POST/GET/PUT/DELETE /protocols)
- Protocol activation (POST /protocols/{protocol_id}/activate)
- Per-company screening configuration (GET/PUT /config)

Exception handlers:
- NoCriteriaDefinedError → HTTP 422
- ProtocolNotFoundError → HTTP 404
- InvalidStateTransitionError → HTTP 409
- ConfigurationRangeError → HTTP 422

References:
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 11.4
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import logging
from math import ceil
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.review.exceptions import (
    ConfigurationRangeError,
    InvalidStateTransitionError,
    NoCriteriaDefinedError,
    ProtocolNotFoundError,
)
from alcoabase.literature.review.schemas.configuration import (
    ScreeningConfigurationUpdateSchema,
)
from alcoabase.literature.review.schemas.protocol import (
    ScreeningProtocolCreateSchema,
    ScreeningProtocolUpdateSchema,
)
from alcoabase.literature.review.services.screening_config_service import (
    ScreeningConfigService,
)
from alcoabase.literature.review.services.screening_protocol_service import (
    ScreeningProtocolService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature/screening", tags=["Literature Screening"])


# ─────────────────────────────────────────────────────────────────────────────
# Role-checking dependencies
# ─────────────────────────────────────────────────────────────────────────────


def _require_member():
    """Return a dependency enforcing at least member role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have at least a member-level membership role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"member", "document_admin", "system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions. Requires at least member role.",
            )
        return tenant

    return _check


def _require_document_admin():
    """Return a dependency enforcing document_admin or higher role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have document_admin, system_admin, or admin role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"document_admin", "system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Requires document_admin or system_admin role.",
            )
        return tenant

    return _check


def _require_system_admin():
    """Return a dependency enforcing system_admin role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have system_admin or admin role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Requires system_admin role.",
            )
        return tenant

    return _check


require_member = _require_member()
require_document_admin = _require_document_admin()
require_system_admin = _require_system_admin()


# ─────────────────────────────────────────────────────────────────────────────
# Service singletons
# ─────────────────────────────────────────────────────────────────────────────

_protocol_service = ScreeningProtocolService()
_config_service = ScreeningConfigService()


# ─────────────────────────────────────────────────────────────────────────────
# POST /protocols — Create Screening Protocol
# Requirements: 8.1, 8.7, 8.8
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/protocols",
    status_code=201,
    summary="Create a new screening protocol",
)
async def create_protocol(
    payload: ScreeningProtocolCreateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Create a new Screening Protocol in draft status.

    Requires at least the ``document_admin`` role. The protocol must have
    at least one criterion defined (PICO field, inclusion, or exclusion).

    Args:
        payload: Protocol creation payload with name, criteria, etc.
        ctx: Resolved tenant context with company_id and user_id.
        session: Async database session.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Created protocol details with HTTP 201.

    Raises:
        HTTPException 403: If user lacks document_admin role.
        HTTPException 422: If no criteria are defined.
    """
    try:
        result = await _protocol_service.create_protocol(
            session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            name=payload.name,
            description=payload.description,
            pico_criteria=payload.pico_criteria.model_dump() if payload.pico_criteria else None,
            inclusion_criteria=payload.inclusion_criteria,
            exclusion_criteria=payload.exclusion_criteria,
            publication_date_from=payload.publication_date_from,
            publication_date_to=payload.publication_date_to,
            allowed_publication_types=payload.allowed_publication_types,
            allowed_languages=payload.allowed_languages,
        )
        await session.commit()
        return result
    except NoCriteriaDefinedError as e:
        raise HTTPException(status_code=422, detail=e.message)


# ─────────────────────────────────────────────────────────────────────────────
# GET /protocols — List Screening Protocols
# Requirements: 8.2, 8.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/protocols",
    summary="List screening protocols",
)
async def list_protocols(
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status: Annotated[str | None, Query(description="Filter by status")] = None,
) -> dict[str, Any]:
    """List screening protocols for the requesting company with pagination.

    Supports optional filtering by status (draft, active, archived).
    Requires at least the ``member`` role.

    Args:
        ctx: Resolved tenant context.
        session: Async database session.
        page: Page number (1-indexed).
        page_size: Items per page (1–100).
        status: Optional status filter.

    Returns:
        Paginated list of protocols with total count and page metadata.
    """
    protocols, total_count = await _protocol_service.list_protocols(
        session,
        company_id=ctx.company_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    total_pages = ceil(total_count / page_size) if total_count > 0 else 0

    return {
        "items": protocols,
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /protocols/{protocol_id} — Get Protocol Details
# Requirements: 8.3, 8.8
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/protocols/{protocol_id}",
    summary="Get screening protocol details",
)
async def get_protocol(
    protocol_id: Annotated[int, Path(description="Protocol ID")],
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get full screening protocol details including version history.

    Requires at least the ``member`` role.

    Args:
        protocol_id: Target protocol ID.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Full protocol details with version history.

    Raises:
        HTTPException 404: If protocol not found in this company.
    """
    try:
        return await _protocol_service.get_protocol(
            session,
            protocol_id=protocol_id,
            company_id=ctx.company_id,
        )
    except ProtocolNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /protocols/{protocol_id} — Update Protocol
# Requirements: 8.4, 8.7, 8.8
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/protocols/{protocol_id}",
    summary="Update a screening protocol",
)
async def update_protocol(
    protocol_id: Annotated[int, Path(description="Protocol ID")],
    payload: ScreeningProtocolUpdateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Update a screening protocol, auto-incrementing the version.

    If the protocol is active with in-progress reviews, a new version is
    created while preserving the original for those reviews.

    Requires ``document_admin`` role.

    Args:
        protocol_id: Target protocol ID.
        payload: Update payload with optional fields.
        ctx: Resolved tenant context.
        session: Async database session.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Updated protocol with new version number.

    Raises:
        HTTPException 404: If protocol not found.
        HTTPException 422: If update leaves zero criteria.
    """
    # Build update fields dict, only including non-None values
    fields: dict[str, Any] = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.description is not None:
        fields["description"] = payload.description
    if payload.pico_criteria is not None:
        fields["pico_criteria"] = payload.pico_criteria.model_dump()
    if payload.inclusion_criteria is not None:
        fields["inclusion_criteria"] = payload.inclusion_criteria
    if payload.exclusion_criteria is not None:
        fields["exclusion_criteria"] = payload.exclusion_criteria
    if payload.publication_date_from is not None:
        fields["publication_date_from"] = payload.publication_date_from
    if payload.publication_date_to is not None:
        fields["publication_date_to"] = payload.publication_date_to
    if payload.allowed_publication_types is not None:
        fields["allowed_publication_types"] = payload.allowed_publication_types
    if payload.allowed_languages is not None:
        fields["allowed_languages"] = payload.allowed_languages

    try:
        result = await _protocol_service.update_protocol(
            session,
            protocol_id=protocol_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            **fields,
        )
        await session.commit()
        return result
    except ProtocolNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except NoCriteriaDefinedError as e:
        raise HTTPException(status_code=422, detail=e.message)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /protocols/{protocol_id} — Archive (soft-delete) Protocol
# Requirements: 8.5, 8.7, 8.8
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/protocols/{protocol_id}",
    summary="Archive (soft-delete) a screening protocol",
)
async def delete_protocol(
    protocol_id: Annotated[int, Path(description="Protocol ID")],
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Soft-delete a screening protocol by transitioning to archived status.

    Does not physically delete the record. Requires ``document_admin`` role.

    Args:
        protocol_id: Target protocol ID.
        ctx: Resolved tenant context.
        session: Async database session.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Archived protocol details.

    Raises:
        HTTPException 404: If protocol not found.
        HTTPException 409: If protocol is already archived.
    """
    try:
        result = await _protocol_service.archive_protocol(
            session,
            protocol_id=protocol_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
        )
        await session.commit()
        return result
    except ProtocolNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=e.message)


# ─────────────────────────────────────────────────────────────────────────────
# POST /protocols/{protocol_id}/activate — Activate Protocol
# Requirements: 8.6, 8.7, 8.8
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/protocols/{protocol_id}/activate",
    summary="Activate a screening protocol",
)
async def activate_protocol(
    protocol_id: Annotated[int, Path(description="Protocol ID")],
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Transition a screening protocol from draft to active status.

    Only draft protocols can be activated. Requires ``document_admin`` role.

    Args:
        protocol_id: Target protocol ID.
        ctx: Resolved tenant context.
        session: Async database session.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Activated protocol details.

    Raises:
        HTTPException 404: If protocol not found.
        HTTPException 409: If protocol is not in draft status.
    """
    try:
        result = await _protocol_service.activate_protocol(
            session,
            protocol_id=protocol_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
        )
        await session.commit()
        return result
    except ProtocolNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=409, detail=e.message)


# ─────────────────────────────────────────────────────────────────────────────
# GET /config — Get Screening Configuration
# Requirements: 11.4
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/config",
    summary="Get screening configuration",
)
async def get_config(
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get the current screening configuration for the requesting company.

    Returns default values if no custom configuration has been set.
    Requires ``document_admin`` role.

    Args:
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Screening configuration fields.
    """
    return await _config_service.get_config(
        session,
        company_id=ctx.company_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUT /config — Update Screening Configuration
# Requirements: 11.4
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/config",
    summary="Update screening configuration",
)
async def update_config(
    payload: ScreeningConfigurationUpdateSchema,
    ctx: TenantContext = Depends(require_system_admin),
    session: AsyncSession = Depends(get_db_session),
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
) -> dict[str, Any]:
    """Update the screening configuration for the requesting company.

    Validates that numeric fields are within allowed ranges:
    - default_batch_size: 1–100
    - confidence_threshold: 0.5–1.0
    - max_concurrent: 1–20

    Requires ``system_admin`` role.

    Args:
        payload: Configuration update with optional fields.
        ctx: Resolved tenant context.
        session: Async database session.
        x_change_reason: Required audit trail reason (enforced by middleware).

    Returns:
        Updated configuration.

    Raises:
        HTTPException 422: If any value is outside its allowed range.
    """
    # Map schema field names to service field names
    data: dict[str, Any] = {}
    if payload.auto_screen_on_index is not None:
        data["auto_screen_on_index"] = payload.auto_screen_on_index
    if payload.default_batch_size is not None:
        data["default_batch_size"] = payload.default_batch_size
    if payload.confidence_threshold is not None:
        data["confidence_threshold_for_auto_include"] = payload.confidence_threshold
    if payload.max_concurrent is not None:
        data["max_concurrent_screening_tasks"] = payload.max_concurrent
    if payload.contradiction_detection_enabled is not None:
        data["contradiction_detection_enabled"] = payload.contradiction_detection_enabled

    try:
        result = await _config_service.update_config(
            session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            data=data,
        )
        await session.commit()
        return result
    except ConfigurationRangeError as e:
        raise HTTPException(status_code=422, detail=e.message)
