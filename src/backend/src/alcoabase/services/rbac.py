"""RBAC (Role-Based Access Control) service for permission evaluation.

This module provides the RBACService that evaluates user permissions
based on assigned roles and permission templates. It implements:
- Permission evaluation for resource:action pairs
- Document access checks with permission template enforcement
- Role lookup for users within a company context
- Default role seeding for new companies

The permission model uses a "most restrictive wins" policy when
permission templates are involved: access is granted only if BOTH
the user's base role AND the template grant the requested action.

References:
    - Phase 6.1 design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements: 2.1–2.6, 3.1–3.5, 13.1–13.2
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.company import CompanyMembership
from alcoabase.models.document import Document
from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.models.user import Role, User

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESOURCE_TYPES: list[str] = [
    "documents",
    "workflows",
    "users",
    "audit_logs",
    "templates",
    "training",
    "signatures",
    "system_config",
]

ACTIONS: list[str] = ["create", "read", "update", "delete", "approve"]

DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "system_admin": {resource: ACTIONS[:] for resource in RESOURCE_TYPES},
    "doc_admin": {
        "documents": ["create", "read", "update", "approve"],
        "workflows": ["create", "read", "update", "approve"],
        "templates": ["create", "read", "update", "approve"],
        "training": ["create", "read", "update", "approve"],
        "audit_logs": ["read"],
        "signatures": ["create", "read", "approve"],
    },
    "it_admin": {
        "system_config": ["read", "update"],
        "audit_logs": ["read"],
        "users": ["read"],
    },
    "member": {
        "documents": ["create", "read", "update"],
        "training": ["create", "read", "update"],
        "workflows": ["read"],
        "templates": ["read"],
    },
    "viewer": {
        "documents": ["read"],
        "workflows": ["read"],
        "templates": ["read"],
        "training": ["read"],
    },
}


# ---------------------------------------------------------------------------
# Result Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessGranted:
    """Result indicating permission was granted.

    Attributes:
        user_id: The user who was granted access.
        resource: The resource type that was accessed.
        action: The action that was permitted.
    """

    user_id: int
    resource: str
    action: str


@dataclass(frozen=True)
class AccessDenied:
    """Result indicating permission was denied.

    Attributes:
        user_id: The user who was denied access.
        resource: The resource type that was requested.
        action: The action that was denied.
        reason: Human-readable explanation of why access was denied.
    """

    user_id: int
    resource: str
    action: str
    reason: str


# Type alias for permission check results
AccessResult = AccessGranted | AccessDenied


# ---------------------------------------------------------------------------
# RBACService
# ---------------------------------------------------------------------------


class RBACService:
    """Service for evaluating role-based access control permissions.

    Provides methods for checking user permissions against their assigned
    role within a company context, with support for permission template
    overrides on document access.
    """

    async def check_permission(
        self,
        user_id: int,
        company_id: int,
        resource: str,
        action: str,
        session: AsyncSession,
    ) -> AccessResult:
        """Evaluate whether a user has permission to perform an action on a resource.

        Loads the user's active membership for the specified company, checks
        the user's is_active flag, loads the role's permissions JSON, and
        evaluates whether the requested resource:action is granted.

        Args:
            user_id: The ID of the user requesting access.
            company_id: The ID of the company context.
            resource: The resource type (e.g., "documents", "workflows").
            action: The action being requested (e.g., "read", "create").
            session: Active async database session.

        Returns:
            AccessGranted if the user has the required permission,
            AccessDenied with a reason otherwise.
        """
        # 1. Load user and check is_active
        user_stmt = select(User).where(User.id == user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if user is None:
            return AccessDenied(
                user_id=user_id,
                resource=resource,
                action=action,
                reason="User not found.",
            )

        if not user.is_active:
            return AccessDenied(
                user_id=user_id,
                resource=resource,
                action=action,
                reason="Account is deactivated. Contact your administrator.",
            )

        # 2. Load active membership for company
        membership_stmt = select(CompanyMembership).where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.revoked_at.is_(None),
        )
        membership_result = await session.execute(membership_stmt)
        membership = membership_result.scalar_one_or_none()

        if membership is None:
            return AccessDenied(
                user_id=user_id,
                resource=resource,
                action=action,
                reason="Not a member of the specified company.",
            )

        # 3. Load role permissions
        permissions = await self._get_role_permissions(membership, session)
        if permissions is None:
            role_name = membership.role or "unknown"
            role_id_info = f" (role_id={membership.role_id})" if membership.role_id else ""
            return AccessDenied(
                user_id=user_id,
                resource=resource,
                action=action,
                reason=(
                    f"Role '{role_name}'{role_id_info} not recognized. "
                    f"Valid roles: system_admin, doc_admin, it_admin, member, viewer."
                ),
            )

        # 4. Evaluate resource:action grant
        if self._has_permission(permissions, resource, action):
            return AccessGranted(
                user_id=user_id,
                resource=resource,
                action=action,
            )

        role_name = membership.role or "unknown"
        role_id_info = f" (role_id={membership.role_id})" if membership.role_id else ""
        return AccessDenied(
            user_id=user_id,
            resource=resource,
            action=action,
            reason=(
                f"Role '{role_name}'{role_id_info} does not have "
                f"'{action}' permission on '{resource}'."
            ),
        )

    async def check_document_access(
        self,
        user_id: int,
        company_id: int,
        document: Document,
        action: str,
        session: AsyncSession,
    ) -> AccessResult:
        """Evaluate document access using base role AND permission template.

        Checks both the user's base role permissions for the "documents"
        resource AND any permission template associated with the document's
        type. Applies "most restrictive wins" policy: access is granted
        only if BOTH the base role AND the template (if present) grant
        the requested action.

        Args:
            user_id: The ID of the user requesting access.
            company_id: The ID of the company context.
            document: The Document instance being accessed.
            action: The action being requested (e.g., "read", "write", "approve").
            session: Active async database session.

        Returns:
            AccessGranted if both base role and template allow the action,
            AccessDenied with a reason otherwise.
        """
        # 1. Check base role permission for documents
        base_result = await self.check_permission(
            user_id=user_id,
            company_id=company_id,
            resource="documents",
            action=action,
            session=session,
        )

        # If base role denies, no need to check template
        if isinstance(base_result, AccessDenied):
            return base_result

        # 2. Check permission template (if document has one)
        template_stmt = select(PermissionTemplate).where(
            PermissionTemplate.company_id == company_id,
            PermissionTemplate.document_type == document.document_type,
        )
        template_result = await session.execute(template_stmt)
        template = template_result.scalar_one_or_none()

        # If no template, base role permission is sufficient
        if template is None:
            return base_result

        # 3. Get user's role name for template evaluation
        role = await self.get_role_for_user(user_id, company_id, session)
        if role is None:
            return AccessDenied(
                user_id=user_id,
                resource="documents",
                action=action,
                reason="Role not found.",
            )

        # 4. Evaluate template permissions (most restrictive wins)
        role_name = role.name
        template_permissions: dict[str, list[str]] = template.role_permissions or {}

        # If the role is not listed in the template, deny access
        if role_name not in template_permissions:
            return AccessDenied(
                user_id=user_id,
                resource="documents",
                action=action,
                reason=f"Permission template '{template.name}' does not grant "
                f"'{action}' for role '{role_name}'.",
            )

        # Check if the action is in the template's allowed actions for this role
        allowed_actions = template_permissions[role_name]
        if action not in allowed_actions:
            return AccessDenied(
                user_id=user_id,
                resource="documents",
                action=action,
                reason=f"Permission template '{template.name}' does not grant "
                f"'{action}' for role '{role_name}'.",
            )

        return AccessGranted(
            user_id=user_id,
            resource="documents",
            action=action,
        )

    async def get_role_for_user(
        self,
        user_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> Role | None:
        """Load the user's role for a specific company via CompanyMembership.

        Args:
            user_id: The ID of the user.
            company_id: The ID of the company context.
            session: Active async database session.

        Returns:
            The Role instance if found, None otherwise.
        """
        membership_stmt = select(CompanyMembership).where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.revoked_at.is_(None),
        )
        membership_result = await session.execute(membership_stmt)
        membership = membership_result.scalar_one_or_none()

        if membership is None or membership.role_id is None:
            return None

        role_stmt = select(Role).where(Role.id == membership.role_id)
        role_result = await session.execute(role_stmt)
        return role_result.scalar_one_or_none()

    async def seed_default_roles(
        self,
        company_id: int,
        session: AsyncSession,
    ) -> list[Role]:
        """Create the five default system roles for a company.

        Seeds system_admin, doc_admin, it_admin, member, and viewer roles
        with their predefined permission sets. Roles are marked as
        is_system=True to prevent editing.

        Args:
            company_id: The ID of the company to seed roles for.
            session: Active async database session.

        Returns:
            List of the five created Role instances.
        """
        role_descriptions: dict[str, str] = {
            "system_admin": "Full system access. Can manage users, roles, and all resources.",
            "doc_admin": "Document lifecycle management. Can create, edit, and approve documents, workflows, and templates.",
            "it_admin": "IT infrastructure management. Can view and configure system settings and audit logs.",
            "member": "Standard team member. Can create and edit documents and training materials.",
            "viewer": "Read-only access. Can view documents, workflows, templates, and training materials.",
        }

        created_roles: list[Role] = []

        for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            role = Role(
                name=role_name,
                description=role_descriptions[role_name],
                permissions=permissions,
                company_id=company_id,
                is_system=True,
            )
            session.add(role)
            created_roles.append(role)

        await session.flush()
        return created_roles

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    async def _get_role_permissions(
        self,
        membership: CompanyMembership,
        session: AsyncSession,
    ) -> dict[str, list[str]] | None:
        """Load the permissions JSON for a membership's role.

        If the membership has a role_id FK, loads from the Role table.
        Otherwise falls back to DEFAULT_ROLE_PERMISSIONS using the legacy
        role string field.

        Args:
            membership: The CompanyMembership instance.
            session: Active async database session.

        Returns:
            The permissions dict if found, None otherwise.
        """
        if membership.role_id is not None:
            role_stmt = select(Role).where(Role.id == membership.role_id)
            role_result = await session.execute(role_stmt)
            role = role_result.scalar_one_or_none()
            if role is not None and role.permissions:
                # Only use DB permissions if they're non-empty
                return role.permissions
            # If role exists but permissions is empty/{}, fall through to defaults
            # using the role name from the DB record
            if role is not None and role.name in DEFAULT_ROLE_PERMISSIONS:
                return DEFAULT_ROLE_PERMISSIONS[role.name]

        # Fallback to legacy role string → default permissions
        legacy_role = membership.role
        if legacy_role in DEFAULT_ROLE_PERMISSIONS:
            return DEFAULT_ROLE_PERMISSIONS[legacy_role]

        return None

    @staticmethod
    def _has_permission(
        permissions: dict[str, list[str]],
        resource: str,
        action: str,
    ) -> bool:
        """Check if a permissions dict grants a specific resource:action.

        Args:
            permissions: The role's permissions mapping.
            resource: The resource type to check.
            action: The action to check.

        Returns:
            True if the action is granted for the resource, False otherwise.
        """
        resource_actions: Any = permissions.get(resource)
        if resource_actions is None:
            return False
        return action in resource_actions
