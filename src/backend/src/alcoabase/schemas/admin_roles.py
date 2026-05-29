"""Pydantic request/response schemas for admin role management endpoints.

Provides validated schemas for listing roles and viewing role details
with their permission matrices.

References:
    - Design doc: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements 10.1, 10.2
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class PermissionEntry(BaseModel):
    """Single resource-actions entry in a permission matrix.

    Attributes:
        resource: The resource type (e.g., "documents", "workflows").
        actions: List of permitted actions on the resource.
    """

    resource: str
    actions: list[Literal["create", "read", "update", "delete", "approve"]]


class RoleWithCount(BaseModel):
    """Role summary with user count for list view.

    Attributes:
        id: The role's database ID.
        name: The role name (e.g., "system_admin", "doc_admin").
        description: Human-readable description of the role.
        is_system: Whether this is a system-defined non-editable role.
        user_count: Number of users currently assigned to this role.
    """

    id: int
    name: str
    description: str | None
    is_system: bool
    user_count: int

    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    """Response for GET /api/admin/roles.

    Attributes:
        roles: List of roles with user counts.
    """

    roles: list[RoleWithCount]


class RoleDetailResponse(BaseModel):
    """Detailed role response with full permission matrix.

    Attributes:
        id: The role's database ID.
        name: The role name.
        description: Human-readable description of the role.
        is_system: Whether this is a system-defined non-editable role.
        permissions: Mapping of resource types to their granted actions.
        user_count: Number of users currently assigned to this role.
    """

    id: int
    name: str
    description: str | None
    is_system: bool
    permissions: dict[str, list[str]]
    user_count: int

    model_config = ConfigDict(from_attributes=True)
