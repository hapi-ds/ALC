"""FastAPI router for admin role management endpoints.

Provides read-only endpoints for listing roles with user counts and
viewing role details with full permission matrices.

Endpoints:
    GET /api/admin/roles - List all roles with user counts
    GET /api/admin/roles/{role_id} - Get role detail with permission matrix

References:
    - Design doc: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements: 1.4, 10.1, 10.2, 10.3, 10.4
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.models.company import CompanyMembership
from alcoabase.models.user import Role
from alcoabase.schemas.admin_roles import (
    RoleDetailResponse,
    RoleListResponse,
    RoleWithCount,
)

router = APIRouter(prefix="/admin/roles", tags=["Admin Roles"])


@router.get("", response_model=RoleListResponse)
async def list_roles(
    ctx: TenantContext = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> RoleListResponse:
    """List all roles for the current company with user counts.

    Returns all roles scoped to the current company (including system
    roles provisioned for the company). Each role includes a count of
    active users currently assigned to that role.

    Args:
        ctx: Resolved tenant context with company_id.
        session: Async database session.

    Returns:
        RoleListResponse containing all roles with user counts.
    """
    # Subquery to count active memberships per role
    user_count_subq = (
        select(
            CompanyMembership.role_id,
            func.count(CompanyMembership.id).label("user_count"),
        )
        .where(
            CompanyMembership.company_id == ctx.company_id,
            CompanyMembership.revoked_at.is_(None),
            CompanyMembership.role_id.isnot(None),
        )
        .group_by(CompanyMembership.role_id)
        .subquery()
    )

    # Query roles for this company with user counts
    stmt = (
        select(Role, func.coalesce(user_count_subq.c.user_count, 0).label("user_count"))
        .outerjoin(user_count_subq, Role.id == user_count_subq.c.role_id)
        .where(Role.company_id == ctx.company_id)
        .order_by(Role.name)
    )

    result = await session.execute(stmt)
    rows = result.all()

    roles = [
        RoleWithCount(
            id=role.id,
            name=role.name,
            description=role.description,
            is_system=role.is_system,
            user_count=user_count,
        )
        for role, user_count in rows
    ]

    return RoleListResponse(roles=roles)


@router.get("/{role_id}", response_model=RoleDetailResponse)
async def get_role_detail(
    role_id: int,
    ctx: TenantContext = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> RoleDetailResponse:
    """Get detailed role information with full permission matrix.

    Returns the role's complete permission matrix showing all resource
    types and their granted actions, along with the count of users
    currently assigned to this role.

    Args:
        role_id: The database ID of the role to retrieve.
        ctx: Resolved tenant context with company_id.
        session: Async database session.

    Returns:
        RoleDetailResponse with full permission matrix and user count.

    Raises:
        HTTPException: 404 if role not found or not in current company.
    """
    # Load the role scoped to the current company
    stmt = select(Role).where(
        Role.id == role_id,
        Role.company_id == ctx.company_id,
    )
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()

    if role is None:
        raise HTTPException(status_code=404, detail="Role not found.")

    # Count active memberships for this role
    count_stmt = (
        select(func.count(CompanyMembership.id))
        .where(
            CompanyMembership.role_id == role_id,
            CompanyMembership.company_id == ctx.company_id,
            CompanyMembership.revoked_at.is_(None),
        )
    )
    count_result = await session.execute(count_stmt)
    user_count = count_result.scalar_one()

    return RoleDetailResponse(
        id=role.id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=role.permissions or {},
        user_count=user_count,
    )
