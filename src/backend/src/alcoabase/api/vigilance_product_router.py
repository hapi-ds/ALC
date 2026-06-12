"""FastAPI router for vigilance product portfolio and search profile endpoints.

Provides endpoints for:
- Medical Product CRUD (POST, GET, PUT, DELETE /vigilance/products)
- Vigilance Search Profile CRUD (POST, GET /vigilance/products/{id}/profiles)
- Profile update (PUT /vigilance/profiles/{id})
- Manual profile execution (POST /vigilance/profiles/{id}/execute)

All endpoints are scoped by X-Company-Id header via TenantContext dependency.
Mutation endpoints (POST, PUT, DELETE) require X-Change-Reason header enforced
by AuditMiddleware.

References:
    - Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11
    - Design: vigilance_product_router in Phase 9.5 design doc
"""

from __future__ import annotations

import logging
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.vigilance.exceptions import (
    DuplicateUDIError,
    InvalidCronExpressionError,
    ProductNotFoundError,
    ProfileNotFoundError,
)
from alcoabase.literature.vigilance.schemas.product import (
    MedicalProductCreateSchema,
    MedicalProductResponseSchema,
    MedicalProductUpdateSchema,
)
from alcoabase.literature.vigilance.schemas.profile import (
    VigilanceSearchProfileCreateSchema,
    VigilanceSearchProfileResponseSchema,
    VigilanceSearchProfileUpdateSchema,
)
from alcoabase.literature.vigilance.services.product_portfolio_service import (
    ProductPortfolioService,
)
from alcoabase.literature.vigilance.services.vigilance_search_profile_service import (
    VigilanceSearchProfileService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vigilance/products", tags=["Vigilance Products"])


# ─────────────────────────────────────────────────────────────────────────────
# Role-checking dependencies
# ─────────────────────────────────────────────────────────────────────────────


def _require_member():
    """Return a dependency enforcing at least member role."""

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
    """Return a dependency enforcing document_admin or higher role."""

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


require_member = _require_member()
require_document_admin = _require_document_admin()


# ─────────────────────────────────────────────────────────────────────────────
# Service Dependencies
# ─────────────────────────────────────────────────────────────────────────────

_product_service = ProductPortfolioService()
_profile_service: VigilanceSearchProfileService | None = None


def _get_profile_service() -> VigilanceSearchProfileService:
    """Get or create the VigilanceSearchProfileService singleton.

    Uses a module-level singleton initialized with the database module's
    session factory. Lazily initialized on first call to ensure the DB
    engine is available.
    """
    global _profile_service
    if _profile_service is None:
        from alcoabase.database import _session_factory as session_factory

        if session_factory is None:
            raise RuntimeError(
                "Database not initialized. Cannot create VigilanceSearchProfileService."
            )
        _profile_service = VigilanceSearchProfileService(
            session_factory=session_factory,
        )
    return _profile_service


# ─────────────────────────────────────────────────────────────────────────────
# POST /vigilance/products — Create Medical Product
# Requirements: 9.1, 2.5, 2.6
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    status_code=201,
    response_model=MedicalProductResponseSchema,
    summary="Create a medical product",
    responses={
        409: {"description": "Duplicate UDI within company"},
        422: {"description": "Validation error"},
    },
)
async def create_product(
    body: MedicalProductCreateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Register a new medical device/product in the company portfolio.

    Requires document_admin or system_admin role. The X-Change-Reason
    header is enforced by AuditMiddleware.

    Args:
        body: Product creation payload with required fields.
        ctx: Resolved tenant context (company_id, user_id).
        session: Async database session.

    Returns:
        Created product data (HTTP 201).

    Raises:
        HTTPException 403: Insufficient permissions.
        HTTPException 409: Duplicate UDI within company.
        HTTPException 422: Validation failure.
    """
    try:
        product = await _product_service.create_product(
            session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            name=body.name,
            device_class=body.device_class,
            intended_purpose=body.intended_purpose,
            udi=body.udi,
            gmdn_code=body.gmdn_code,
            manufacturer_name=body.manufacturer_name,
            predicate_devices=body.predicate_devices,
            risk_class_justification=body.risk_class_justification,
        )
    except DuplicateUDIError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return product


# ─────────────────────────────────────────────────────────────────────────────
# GET /vigilance/products — List Medical Products
# Requirements: 9.2
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=dict[str, Any],
    summary="List medical products",
)
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    device_class: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """List medical products for the requesting company with pagination.

    Supports filtering by status and device_class.

    Args:
        page: Page number (1-indexed, default 1).
        page_size: Items per page (1–100, default 20).
        status: Optional filter (active, discontinued, recalled).
        device_class: Optional device class filter.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Paginated response with items, page, page_size, total, total_pages.
    """
    products, total = await _product_service.list_products(
        session,
        company_id=ctx.company_id,
        page=page,
        page_size=page_size,
        status=status,
        device_class=device_class,
    )

    total_pages = ceil(total / page_size) if page_size > 0 else 0

    return {
        "items": products,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /vigilance/products/{product_id} — Get Product Detail
# Requirements: 9.3, 9.11
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{product_id}",
    response_model=dict[str, Any],
    summary="Get medical product details",
    responses={404: {"description": "Product not found"}},
)
async def get_product(
    product_id: int,
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Get full product details including profiles and signal counts.

    Returns HTTP 404 if the product does not exist or belongs to a
    different company (cross-tenant isolation).

    Args:
        product_id: Target product ID.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Product details with associated profiles and signal counts.
    """
    try:
        product = await _product_service.get_product(
            session,
            product_id=product_id,
            company_id=ctx.company_id,
        )
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found.")

    return product


# ─────────────────────────────────────────────────────────────────────────────
# PUT /vigilance/products/{product_id} — Update Product
# Requirements: 9.4, 9.10, 9.11
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{product_id}",
    response_model=MedicalProductResponseSchema,
    summary="Update a medical product",
    responses={
        404: {"description": "Product not found"},
        409: {"description": "Duplicate UDI within company"},
        422: {"description": "Validation error"},
    },
)
async def update_product(
    product_id: int,
    body: MedicalProductUpdateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Update an existing medical product.

    Requires document_admin or system_admin role. Only provided fields
    are updated. Status change to discontinued/recalled suspends
    associated vigilance search profiles.

    Args:
        product_id: Target product ID.
        body: Update payload with optional fields.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Updated product data (HTTP 200).
    """
    update_fields = body.model_dump(exclude_unset=True)

    if not update_fields:
        raise HTTPException(status_code=422, detail="No fields to update.")

    try:
        product = await _product_service.update_product(
            session,
            product_id=product_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            **update_fields,
        )
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found.")
    except DuplicateUDIError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return product


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /vigilance/products/{product_id} — Soft-Delete Product
# Requirements: 9.5, 9.10, 9.11
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{product_id}",
    response_model=MedicalProductResponseSchema,
    summary="Soft-delete a medical product",
    responses={404: {"description": "Product not found"}},
)
async def delete_product(
    product_id: int,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Soft-delete a product by setting status to 'discontinued'.

    Does not physically delete. Suspends associated vigilance search
    profiles. Requires document_admin or system_admin role.

    Args:
        product_id: Target product ID.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Updated product with status='discontinued' (HTTP 200).
    """
    try:
        product = await _product_service.soft_delete_product(
            session,
            product_id=product_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
        )
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found.")

    return product


# ─────────────────────────────────────────────────────────────────────────────
# POST /vigilance/products/{product_id}/profiles — Create Profile
# Requirements: 9.6, 9.10, 9.11
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{product_id}/profiles",
    status_code=201,
    response_model=VigilanceSearchProfileResponseSchema,
    summary="Create a vigilance search profile for a product",
    responses={
        404: {"description": "Product not found"},
        422: {"description": "Validation error"},
    },
)
async def create_profile(
    product_id: int,
    body: VigilanceSearchProfileCreateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    profile_service: VigilanceSearchProfileService = Depends(_get_profile_service),
) -> dict[str, Any]:
    """Create a vigilance search profile linked to the specified product.

    Validates cron expression, required arrays, and product existence.
    If product is discontinued/recalled, profile is auto-paused.
    Requires document_admin or system_admin role.

    Args:
        product_id: Target product ID (from path).
        body: Profile creation payload.
        ctx: Resolved tenant context.
        session: Async database session.
        profile_service: Injected profile service.

    Returns:
        Created profile data (HTTP 201).
    """
    try:
        profile = await profile_service.create_profile(
            session,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            product_id=product_id,
            name=body.name,
            search_terms=body.search_terms,
            adverse_event_keywords=body.adverse_event_keywords,
            mesh_terms=body.mesh_terms,
            device_identifiers=body.device_identifiers,
            exclusion_terms=body.exclusion_terms,
            source_ids=body.source_ids,
            schedule_cron=body.schedule_cron,
        )
    except ProductNotFoundError:
        raise HTTPException(status_code=404, detail="Product not found.")
    except InvalidCronExpressionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return profile


# ─────────────────────────────────────────────────────────────────────────────
# GET /vigilance/products/{product_id}/profiles — List Profiles for Product
# Requirements: 9.7, 9.11
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{product_id}/profiles",
    response_model=dict[str, Any],
    summary="List vigilance search profiles for a product",
    responses={404: {"description": "Product not found"}},
)
async def list_profiles(
    product_id: int,
    status: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_member),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """List all vigilance search profiles for a product.

    Supports optional status filter (active, paused, archived).
    Returns HTTP 404 if the product doesn't exist in this company.

    Args:
        product_id: Target product ID.
        status: Optional status filter.
        ctx: Resolved tenant context.
        session: Async database session.

    Returns:
        Response with list of profiles.
    """
    from sqlalchemy import select

    from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
    from alcoabase.literature.vigilance.models.vigilance_search_profile import (
        VigilanceSearchProfile,
    )

    # Verify product exists in company
    product_stmt = select(MedicalProduct).where(
        MedicalProduct.id == product_id,
        MedicalProduct.company_id == ctx.company_id,
    )
    product_result = await session.execute(product_stmt)
    product = product_result.scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")

    # Query profiles
    profiles_filter = [
        VigilanceSearchProfile.product_id == product_id,
        VigilanceSearchProfile.company_id == ctx.company_id,
    ]
    if status is not None:
        profiles_filter.append(VigilanceSearchProfile.status == status)

    profiles_stmt = (
        select(VigilanceSearchProfile)
        .where(*profiles_filter)
        .order_by(VigilanceSearchProfile.created_at.desc())
    )
    profiles_result = await session.execute(profiles_stmt)
    profiles = list(profiles_result.scalars().all())

    return {
        "items": [
            {
                "id": p.id,
                "company_id": p.company_id,
                "product_id": p.product_id,
                "name": p.name,
                "search_terms": p.search_terms,
                "mesh_terms": p.mesh_terms,
                "adverse_event_keywords": p.adverse_event_keywords,
                "device_identifiers": p.device_identifiers,
                "exclusion_terms": p.exclusion_terms,
                "source_ids": p.source_ids,
                "schedule_cron": p.schedule_cron,
                "status": p.status,
                "created_by": p.created_by,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in profiles
        ],
        "total": len(profiles),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUT /vigilance/profiles/{profile_id} — Update Profile
# Requirements: 9.8, 9.10, 9.11
# Note: This endpoint uses a different path prefix (/vigilance/profiles)
# ─────────────────────────────────────────────────────────────────────────────

# We use a separate sub-router for profile-level endpoints that don't
# nest under /products/{product_id}.
profile_router = APIRouter(prefix="/vigilance/profiles", tags=["Vigilance Profiles"])


@profile_router.put(
    "/{profile_id}",
    response_model=VigilanceSearchProfileResponseSchema,
    summary="Update a vigilance search profile",
    responses={
        404: {"description": "Profile not found"},
        422: {"description": "Validation error"},
    },
)
async def update_profile(
    profile_id: int,
    body: VigilanceSearchProfileUpdateSchema,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    profile_service: VigilanceSearchProfileService = Depends(_get_profile_service),
) -> dict[str, Any]:
    """Update an existing vigilance search profile.

    Requires document_admin or system_admin role. Only provided fields
    are updated. Re-registers Celery beat if cron changes.

    Args:
        profile_id: Target profile ID.
        body: Update payload with optional fields.
        ctx: Resolved tenant context.
        session: Async database session.
        profile_service: Injected profile service.

    Returns:
        Updated profile data (HTTP 200).
    """
    update_fields = body.model_dump(exclude_unset=True)

    if not update_fields:
        raise HTTPException(status_code=422, detail="No fields to update.")

    try:
        profile = await profile_service.update_profile(
            session,
            profile_id=profile_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            **update_fields,
        )
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found.")
    except InvalidCronExpressionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return profile


# ─────────────────────────────────────────────────────────────────────────────
# POST /vigilance/profiles/{profile_id}/execute — Trigger Manual Execution
# Requirements: 9.9, 9.10, 9.11
# ─────────────────────────────────────────────────────────────────────────────


@profile_router.post(
    "/{profile_id}/execute",
    status_code=202,
    summary="Trigger manual profile execution",
    responses={
        404: {"description": "Profile not found"},
    },
)
async def execute_profile(
    profile_id: int,
    ctx: TenantContext = Depends(require_document_admin),
    session: AsyncSession = Depends(get_db_session),
    profile_service: VigilanceSearchProfileService = Depends(_get_profile_service),
) -> JSONResponse:
    """Trigger immediate execution of a vigilance search profile.

    Dispatches a Celery task for on-demand search execution regardless
    of the profile's current status. Returns HTTP 202 with a task_id
    for progress tracking.

    Requires document_admin or system_admin role.

    Args:
        profile_id: Target profile ID.
        ctx: Resolved tenant context.
        session: Async database session.
        profile_service: Injected profile service.

    Returns:
        HTTP 202 with task_id for async tracking.
    """
    try:
        task_id = await profile_service.trigger_manual_execution(
            session,
            profile_id=profile_id,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
        )
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found.")

    return JSONResponse(
        status_code=202,
        content={"task_id": task_id, "status": "queued"},
    )
