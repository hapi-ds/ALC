"""FastAPI router for admin user management endpoints.

Provides endpoints for user listing, creation, editing, deactivation,
reactivation, password reset, and change history retrieval. All endpoints
require appropriate RBAC permissions via the require_permission dependency.

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md §1
    - Requirements: 5.1–5.5, 6.1–6.7, 7.1–7.5, 8.1–8.6, 9.1–9.5, 14.1–14.3
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.schemas.admin_users import (
    PasswordResetResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserDetailResponse,
    UserHistoryResponse,
    UserListParams,
    UserListResponse,
    UserUpdateRequest,
)
from alcoabase.services.password_reset import reset_password
from alcoabase.services.user_management import UserManagementService

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])

# Module-level service instance
_user_service = UserManagementService()


def _get_user_service() -> UserManagementService:
    """Provide the UserManagementService instance as a dependency."""
    return _user_service


@router.get("", response_model=UserListResponse)
async def list_users(
    search: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    ctx: TenantContext = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserListResponse:
    """List users for the current company with pagination, search, sort, and filter.

    Requires `users:read` permission.

    Args:
        search: Free-text search against username, email, or full_name.
        sort_by: Field to sort results by.
        sort_dir: Sort direction (asc or desc).
        page: Page number (1-indexed).
        page_size: Number of results per page.
        is_active: Filter by active status.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        Paginated list of users matching the query.
    """
    params = UserListParams(
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        is_active=is_active,
    )
    result = await service.list_users(ctx.company_id, params, session)
    return UserListResponse(**result)


@router.post("", response_model=UserCreateResponse, status_code=201)
async def create_user(
    payload: UserCreateRequest,
    ctx: TenantContext = Depends(require_permission("users", "create")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserCreateResponse:
    """Create a new user with a temporary password.

    Requires `users:create` permission and X-Change-Reason header.

    Args:
        payload: User creation request data.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        Created user details including the temporary password.
    """
    user, temp_password = await service.create_user(payload, ctx.company_id, session)
    return UserCreateResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=payload.role,
        is_active=user.is_active,
        created_at=user.created_at,
        temporary_password=temp_password,
    )


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_detail(
    user_id: int,
    ctx: TenantContext = Depends(require_permission("users", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserDetailResponse:
    """Get detailed user information with company memberships.

    Requires `users:read` permission.

    Args:
        user_id: The ID of the user to retrieve.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        User details with all company memberships.
    """
    result = await service.get_user_detail(user_id, ctx.company_id, session)
    return UserDetailResponse(**result)


@router.patch("/{user_id}", response_model=UserDetailResponse)
async def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    ctx: TenantContext = Depends(require_permission("users", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserDetailResponse:
    """Update a user's profile and/or role assignment.

    Requires `users:update` permission and X-Change-Reason header.

    Args:
        user_id: The ID of the user to update.
        payload: Partial update request data.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        Updated user details with memberships.
    """
    await service.update_user(user_id, payload, ctx.company_id, session)
    # Return full detail response after update
    result = await service.get_user_detail(user_id, ctx.company_id, session)
    return UserDetailResponse(**result)


@router.post("/{user_id}/deactivate", response_model=UserDetailResponse)
async def deactivate_user(
    user_id: int,
    ctx: TenantContext = Depends(require_permission("users", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserDetailResponse:
    """Deactivate a user account (soft operation).

    Requires `users:update` permission and X-Change-Reason header.
    Cannot deactivate your own account (returns 422).

    Args:
        user_id: The ID of the user to deactivate.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        Updated user details after deactivation.
    """
    await service.deactivate_user(user_id, ctx.user_id, ctx.company_id, session)
    result = await service.get_user_detail(user_id, ctx.company_id, session)
    return UserDetailResponse(**result)


@router.post("/{user_id}/reactivate", response_model=UserDetailResponse)
async def reactivate_user(
    user_id: int,
    ctx: TenantContext = Depends(require_permission("users", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserDetailResponse:
    """Reactivate a deactivated user account.

    Requires `users:update` permission and X-Change-Reason header.

    Args:
        user_id: The ID of the user to reactivate.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        Updated user details after reactivation.
    """
    await service.reactivate_user(user_id, ctx.company_id, session)
    result = await service.get_user_detail(user_id, ctx.company_id, session)
    return UserDetailResponse(**result)


@router.post("/{user_id}/reset-password", response_model=PasswordResetResponse)
async def reset_user_password(
    user_id: int,
    ctx: TenantContext = Depends(require_permission("users", "update")),
    session: AsyncSession = Depends(get_db_session),
) -> PasswordResetResponse:
    """Reset a user's password and return the temporary password.

    Requires `users:update` permission and X-Change-Reason header.
    Invalidates all existing refresh tokens for the user.

    Args:
        user_id: The ID of the user whose password to reset.
        ctx: Resolved tenant context with permission check.
        session: Database session.

    Returns:
        The temporary password for the admin to communicate securely.
    """
    temp_password = await reset_password(user_id, session)
    return PasswordResetResponse(
        user_id=user_id,
        temporary_password=temp_password,
    )


@router.get("/{user_id}/history", response_model=UserHistoryResponse)
async def get_user_history(
    user_id: int,
    ctx: TenantContext = Depends(require_permission("audit_logs", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: UserManagementService = Depends(_get_user_service),
) -> UserHistoryResponse:
    """Get the change history for a user.

    Requires `audit_logs:read` permission.

    Args:
        user_id: The ID of the user whose history to retrieve.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: UserManagementService instance.

    Returns:
        User change history with version diffs.
    """
    entries = await service.get_user_history(user_id, session)
    return UserHistoryResponse(user_id=user_id, entries=entries)
