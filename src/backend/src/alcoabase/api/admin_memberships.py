"""FastAPI router for admin membership management endpoints.

Provides endpoints for managing user-company memberships with RBAC
enforcement. Supports listing memberships for a user, assigning users
to companies, and revoking memberships (soft-delete).

Endpoints:
    GET  /api/admin/memberships/user/{user_id} - List memberships for user
    POST /api/admin/memberships               - Assign user to company
    DELETE /api/admin/memberships/{membership_id} - Revoke membership

All mutation endpoints require the X-Change-Reason header for ALCOA+
compliance (enforced by AuditMiddleware).

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md §4
    - Requirements: 11.1, 11.2, 11.3, 11.4, 11.5
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.models.company import Company
from alcoabase.models.user import User
from alcoabase.schemas.admin_memberships import (
    AssignMembershipRequest,
    MembershipDetailResponse,
)
from alcoabase.services.user_management import UserManagementService

router = APIRouter(prefix="/admin/memberships", tags=["Admin Memberships"])


@router.get(
    "/user/{user_id}",
    response_model=list[MembershipDetailResponse],
)
async def list_memberships_for_user(
    user_id: int,
    ctx: TenantContext = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[MembershipDetailResponse]:
    """List all memberships for a user (active and revoked).

    Returns all company memberships for the specified user including
    company names, roles, and timestamps. Both active and revoked
    memberships are included for audit visibility.

    Args:
        user_id: The ID of the user whose memberships to list.
        ctx: Resolved tenant context (requires users:read permission).
        session: Active async database session.

    Returns:
        List of membership detail records ordered by creation date descending.
    """
    service = UserManagementService()
    memberships = await service.list_memberships(user_id=user_id, session=session)

    # Enrich with user details (username, full_name)
    user_stmt = select(User).where(User.id == user_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    user_username = user.username if user else ""
    user_full_name = user.full_name if user else ""

    return [
        MembershipDetailResponse(
            id=m["id"],
            user_id=m["user_id"],
            user_username=user_username,
            user_full_name=user_full_name,
            company_id=m["company_id"],
            company_name=m["company_name"],
            role=m["role"],
            created_at=m["created_at"],
            revoked_at=m["revoked_at"],
        )
        for m in memberships
    ]


@router.post(
    "",
    response_model=MembershipDetailResponse,
    status_code=201,
)
async def assign_membership(
    payload: AssignMembershipRequest,
    ctx: TenantContext = Depends(require_permission("users", "create")),
    session: AsyncSession = Depends(get_db_session),
) -> MembershipDetailResponse:
    """Assign a user to a company with a specified role.

    Creates a new CompanyMembership linking the user to the company.
    Validates that no active (non-revoked) membership already exists
    for the same (user_id, company_id) pair.

    Args:
        payload: Request body with user_id, company_id, and role.
        ctx: Resolved tenant context (requires users:create permission).
        session: Active async database session.

    Returns:
        The newly created membership detail.

    Raises:
        HTTPException 409: If an active membership already exists.
        HTTPException 404: If the specified role is not found for the company.
    """
    service = UserManagementService()
    membership = await service.assign_membership(
        user_id=payload.user_id,
        company_id=payload.company_id,
        role=payload.role,
        session=session,
    )

    # Load user and company details for the response
    user_stmt = select(User).where(User.id == membership.user_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    company_stmt = select(Company).where(Company.id == membership.company_id)
    company_result = await session.execute(company_stmt)
    company = company_result.scalar_one_or_none()

    return MembershipDetailResponse(
        id=membership.id,
        user_id=membership.user_id,
        user_username=user.username if user else "",
        user_full_name=user.full_name if user else "",
        company_id=membership.company_id,
        company_name=company.display_name if company else "",
        role=membership.role,
        created_at=membership.created_at,
        revoked_at=membership.revoked_at,
    )


@router.delete(
    "/{membership_id}",
    response_model=MembershipDetailResponse,
)
async def revoke_membership(
    membership_id: int,
    ctx: TenantContext = Depends(require_permission("users", "delete")),
    session: AsyncSession = Depends(get_db_session),
) -> MembershipDetailResponse:
    """Revoke a company membership (soft-delete).

    Sets the revoked_at timestamp on the membership record rather than
    hard-deleting it, preserving the audit trail for GxP compliance.

    Args:
        membership_id: The ID of the membership to revoke.
        ctx: Resolved tenant context (requires users:delete permission).
        session: Active async database session.

    Returns:
        The revoked membership detail with revoked_at set.

    Raises:
        HTTPException 404: If membership not found or does not belong
            to the current company.
    """
    service = UserManagementService()
    membership = await service.revoke_membership(
        membership_id=membership_id,
        company_id=ctx.company_id,
        session=session,
    )

    # Load user and company details for the response
    user_stmt = select(User).where(User.id == membership.user_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    company_stmt = select(Company).where(Company.id == membership.company_id)
    company_result = await session.execute(company_stmt)
    company = company_result.scalar_one_or_none()

    return MembershipDetailResponse(
        id=membership.id,
        user_id=membership.user_id,
        user_username=user.username if user else "",
        user_full_name=user.full_name if user else "",
        company_id=membership.company_id,
        company_name=company.display_name if company else "",
        role=membership.role,
        created_at=membership.created_at,
        revoked_at=membership.revoked_at,
    )
