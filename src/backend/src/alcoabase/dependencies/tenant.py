"""Tenant context resolution dependency for multi-tenancy.

This module provides the TenantContext dataclass and the get_tenant_context
FastAPI dependency that resolves the active company for each request.

Resolution logic:
    1. Extract user_id from X-User-Id header.
    2. Query all active memberships (revoked_at IS NULL) for the user.
    3. If no memberships → 403.
    4. If exactly one membership → auto-select that company.
    5. If multiple memberships → require X-Company-Id header.
    6. Validate the target company is active.
    7. Return frozen TenantContext dataclass.

References:
    - Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 13.2
    - Design: .kiro/specs/multi-tenancy/design.md
"""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.models.company import Company, CompanyMembership


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant context for the current request.

    Attributes:
        company_id: Primary key of the active company.
        company_slug: URL-safe unique identifier of the active company.
        user_id: Primary key of the authenticated user.
        membership_role: User's role within the active company
            ("admin", "member", or "viewer").
    """

    company_id: int
    company_slug: str
    user_id: int
    membership_role: str


async def get_tenant_context(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TenantContext:
    """Resolve the active tenant from X-User-Id + optional X-Company-Id header.

    This dependency extracts the user identity from the X-User-Id header
    (JWT integration planned for future), queries active memberships, and
    resolves the target company. Single-company users are auto-selected;
    multi-company users must provide an X-Company-Id header.

    Args:
        request: The incoming HTTP request.
        session: Async database session (injected via Depends).

    Returns:
        TenantContext: Frozen dataclass with resolved tenant information.

    Raises:
        HTTPException 401: If X-User-Id header is missing.
        HTTPException 400: If user has multiple companies and X-Company-Id
            header is not provided.
        HTTPException 403: If user has no active memberships, is not a member
            of the specified company, or the company is inactive.
    """
    # 1. Extract user_id from X-User-Id header
    user_id_header = request.headers.get("X-User-Id")
    if not user_id_header:
        raise HTTPException(
            status_code=401,
            detail="User identification required. Set X-User-Id header.",
        )

    try:
        user_id = int(user_id_header)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="User identification required. Set X-User-Id header.",
        )

    # 2. Query all active memberships for the user (revoked_at IS NULL)
    stmt = (
        select(CompanyMembership)
        .where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.revoked_at.is_(None),
        )
    )
    result = await session.execute(stmt)
    memberships = result.scalars().all()

    # 3. If no memberships → 403
    if not memberships:
        raise HTTPException(
            status_code=403,
            detail="Not a member of the specified company.",
        )

    # 4. Determine target membership
    company_id_header = request.headers.get("X-Company-Id")

    if len(memberships) == 1:
        # Auto-select the single membership
        target_membership = memberships[0]
        # If X-Company-Id is provided, validate it matches
        if company_id_header:
            try:
                requested_company_id = int(company_id_header)
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=403,
                    detail="Not a member of the specified company.",
                )
            if requested_company_id != target_membership.company_id:
                raise HTTPException(
                    status_code=403,
                    detail="Not a member of the specified company.",
                )
    else:
        # 5. Multiple memberships → require X-Company-Id header
        if not company_id_header:
            raise HTTPException(
                status_code=400,
                detail="Company selection required. Set X-Company-Id header.",
            )

        try:
            requested_company_id = int(company_id_header)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=403,
                detail="Not a member of the specified company.",
            )

        # Find the matching membership
        target_membership = None
        for membership in memberships:
            if membership.company_id == requested_company_id:
                target_membership = membership
                break

        if target_membership is None:
            raise HTTPException(
                status_code=403,
                detail="Not a member of the specified company.",
            )

    # 6. Validate company is active
    company_stmt = select(Company).where(Company.id == target_membership.company_id)
    company_result = await session.execute(company_stmt)
    company = company_result.scalar_one_or_none()

    if company is None or not company.is_active:
        raise HTTPException(
            status_code=403,
            detail="Company is inactive.",
        )

    # 7. Return TenantContext
    return TenantContext(
        company_id=company.id,
        company_slug=company.slug,
        user_id=user_id,
        membership_role=target_membership.role,
    )
