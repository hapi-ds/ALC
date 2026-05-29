"""RBAC permission enforcement dependency for FastAPI routes.

This module provides the ``require_permission`` factory that returns a
FastAPI dependency enforcing role-based access control. It chains on top
of the existing ``get_tenant_context`` dependency and delegates permission
evaluation to :class:`~alcoabase.services.rbac.RBACService`.

Usage in route handlers::

    @router.get(
        "/admin/users",
        dependencies=[Depends(require_permission("users", "read"))],
    )
    async def list_users(...):
        ...

Or to receive the TenantContext in the handler::

    @router.get("/admin/users")
    async def list_users(
        ctx: TenantContext = Depends(require_permission("users", "read")),
    ):
        ...

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md §6
    - Requirements: 2.6, 8.2, 12.1, 12.2, 12.3
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.services.rbac import AccessDenied, RBACService


def require_permission(resource: str, action: str) -> Callable:
    """Factory that returns a FastAPI dependency enforcing RBAC.

    Creates a dependency function that:
    1. Resolves TenantContext (user_id, company_id) via ``get_tenant_context``
    2. Checks the user's ``is_active`` flag
    3. Loads the user's role for the company
    4. Evaluates role permissions via :class:`RBACService`
    5. Raises HTTP 403 with a descriptive message on denial

    Args:
        resource: The resource type to check (e.g., "users", "documents").
        action: The action to check (e.g., "read", "create", "update").

    Returns:
        A FastAPI-compatible async dependency function that returns
        :class:`TenantContext` on success.

    Example::

        @router.get("/admin/users")
        async def list_users(
            ctx: TenantContext = Depends(require_permission("users", "read")),
        ):
            # ctx is available here with company_id, user_id, etc.
            ...
    """

    async def _permission_dependency(
        tenant_ctx: TenantContext = Depends(get_tenant_context),
        session: AsyncSession = Depends(get_db_session),
    ) -> TenantContext:
        """Inner dependency that performs the actual permission check.

        Args:
            tenant_ctx: Resolved tenant context from upstream dependency.
            session: Active async database session.

        Returns:
            The same TenantContext on successful authorization.

        Raises:
            HTTPException: 403 if the user lacks the required permission.
        """
        rbac_service = RBACService()

        result = await rbac_service.check_permission(
            user_id=tenant_ctx.user_id,
            company_id=tenant_ctx.company_id,
            resource=resource,
            action=action,
            session=session,
        )

        if isinstance(result, AccessDenied):
            raise HTTPException(
                status_code=403,
                detail=result.reason,
            )

        return tenant_ctx

    return _permission_dependency
