"""FastAPI router for audit profile CRUD endpoints.

Provides endpoints for managing company-specific audit profiles that
determine which agents review documents, what regulatory frameworks
apply, and what quorum is required.

Endpoints:
    - POST /api/audit-profiles: Create audit profile
    - GET /api/audit-profiles: List audit profiles
    - GET /api/audit-profiles/frameworks: List supported frameworks
    - GET /api/audit-profiles/{profile_id}: Get audit profile
    - PUT /api/audit-profiles/{profile_id}: Update audit profile
    - DELETE /api/audit-profiles/{profile_id}: Soft-delete audit profile

References:
    - Requirements 4.3, 4.6, 4.7
    - Design: FastAPI Routers — Audit Profiles Router
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.review import AuditProfileRequest, AuditProfileResponse
from alcoabase.services.audit_profile_service import (
    SUPPORTED_FRAMEWORKS,
    AuditProfileService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-profiles", tags=["Audit Profiles"])


# ---------------------------------------------------------------------------
# Dependency: AuditProfileService
# ---------------------------------------------------------------------------

_audit_profile_service: AuditProfileService | None = None


def set_audit_profile_service(service: AuditProfileService) -> None:
    """Set the module-level AuditProfileService instance.

    Called during application startup to wire the service into the router.

    Args:
        service: The initialized AuditProfileService instance.
    """
    global _audit_profile_service
    _audit_profile_service = service


def get_audit_profile_service() -> AuditProfileService:
    """Provide the AuditProfileService as a FastAPI dependency.

    Returns:
        The module-level AuditProfileService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _audit_profile_service is None:
        raise HTTPException(
            status_code=503,
            detail="Audit profile service is not available.",
        )
    return _audit_profile_service


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=AuditProfileResponse, status_code=201)
async def create_audit_profile(
    request: AuditProfileRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AuditProfileService = Depends(get_audit_profile_service),
) -> AuditProfileResponse:
    """Create a new audit profile for the current company.

    Validates agent assignments and quorum constraints before persisting.

    Args:
        request: Audit profile creation request body.
        tenant: Resolved tenant context (company_id).
        service: AuditProfileService dependency.

    Returns:
        The created audit profile with HTTP 201.

    Raises:
        HTTPException 422: If validation fails (quorum, agent assignments).
    """
    try:
        profile = await service.create_profile(
            data=request.model_dump(exclude_none=True),
            company_id=tenant.company_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return AuditProfileResponse.model_validate(profile, from_attributes=True)


@router.get("", response_model=list[AuditProfileResponse])
async def list_audit_profiles(
    tenant: TenantContext = Depends(get_tenant_context),
    service: AuditProfileService = Depends(get_audit_profile_service),
) -> list[AuditProfileResponse]:
    """List all active audit profiles for the current company.

    Args:
        tenant: Resolved tenant context (company_id).
        service: AuditProfileService dependency.

    Returns:
        List of active audit profiles.
    """
    profiles = await service.list_profiles(company_id=tenant.company_id)
    return [
        AuditProfileResponse.model_validate(p, from_attributes=True)
        for p in profiles
    ]


@router.get("/frameworks", response_model=list[str])
async def list_supported_frameworks() -> list[str]:
    """Return the list of supported regulatory frameworks.

    This endpoint does not require authentication as it returns
    static configuration data.

    Returns:
        List of supported regulatory framework identifiers.
    """
    return SUPPORTED_FRAMEWORKS


@router.get("/{profile_id}", response_model=AuditProfileResponse)
async def get_audit_profile(
    profile_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AuditProfileService = Depends(get_audit_profile_service),
) -> AuditProfileResponse:
    """Get a single audit profile by ID.

    Args:
        profile_id: The audit profile primary key.
        tenant: Resolved tenant context (company_id).
        service: AuditProfileService dependency.

    Returns:
        The audit profile.

    Raises:
        HTTPException 404: If profile not found or wrong company.
    """
    profile = await service.get_profile(
        profile_id=profile_id, company_id=tenant.company_id
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Audit profile not found")

    return AuditProfileResponse.model_validate(profile, from_attributes=True)


@router.put("/{profile_id}", response_model=AuditProfileResponse)
async def update_audit_profile(
    profile_id: int,
    request: AuditProfileRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AuditProfileService = Depends(get_audit_profile_service),
) -> AuditProfileResponse:
    """Update an existing audit profile.

    Validates agent assignments and quorum constraints before persisting.

    Args:
        profile_id: The audit profile primary key.
        request: Updated audit profile request body.
        tenant: Resolved tenant context (company_id).
        service: AuditProfileService dependency.

    Returns:
        The updated audit profile.

    Raises:
        HTTPException 404: If profile not found or wrong company.
        HTTPException 422: If validation fails (quorum, agent assignments).
    """
    try:
        profile = await service.update_profile(
            profile_id=profile_id,
            data=request.model_dump(exclude_none=True),
            company_id=tenant.company_id,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail="Audit profile not found")
        raise HTTPException(status_code=422, detail=error_msg)

    return AuditProfileResponse.model_validate(profile, from_attributes=True)


@router.delete("/{profile_id}", status_code=204)
async def delete_audit_profile(
    profile_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AuditProfileService = Depends(get_audit_profile_service),
) -> None:
    """Soft-delete an audit profile.

    Sets is_active to False. The profile will no longer appear in
    list queries.

    Args:
        profile_id: The audit profile primary key.
        tenant: Resolved tenant context (company_id).
        service: AuditProfileService dependency.

    Raises:
        HTTPException 404: If profile not found or wrong company.
    """
    try:
        await service.delete_profile(
            profile_id=profile_id, company_id=tenant.company_id
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Audit profile not found")
