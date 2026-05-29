"""Pydantic request/response schemas for admin permission template endpoints.

Provides validated schemas for creating, updating, listing, and viewing
permission templates that define role-action mappings for document types.

References:
    - Design doc: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements 4.1, 4.2
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RoleActionMapping(BaseModel):
    """Mapping of a role to its permitted actions on the template's document type.

    Attributes:
        role: The role name this mapping applies to.
        actions: List of permitted actions for this role on the document type.
    """

    role: Literal["system_admin", "doc_admin", "it_admin", "member", "viewer"]
    actions: list[Literal["read", "write", "approve"]]


class PermissionTemplateCreateRequest(BaseModel):
    """Request body for POST /api/admin/permission-templates.

    Attributes:
        name: Template name (unique within company).
        description: Human-readable description of the template.
        document_type: The document type this template governs.
        role_permissions: List of role-to-action mappings defining access rules.
    """

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    document_type: str = Field(min_length=1, max_length=100)
    role_permissions: list[RoleActionMapping] = Field(min_length=1)


class PermissionTemplateUpdateRequest(BaseModel):
    """Request body for PATCH /api/admin/permission-templates/{template_id}.

    All fields are optional; only provided fields are updated.

    Attributes:
        name: Updated template name.
        description: Updated description.
        role_permissions: Updated role-to-action mappings.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    role_permissions: list[RoleActionMapping] | None = None


class PermissionTemplateResponse(BaseModel):
    """Response for permission template endpoints.

    Attributes:
        id: The template's database ID.
        name: Template name.
        description: Human-readable description.
        document_type: The document type this template governs.
        role_permissions: Mapping of role names to their permitted actions.
        is_default: Whether this is a system-seeded default template.
        created_by: ID of the user who created the template.
        created_at: Timestamp when the template was created.
        active_document_count: Number of documents currently using this template.
    """

    id: int
    name: str
    description: str | None
    document_type: str
    role_permissions: dict[str, list[str]]
    is_default: bool
    created_by: int
    created_at: datetime
    active_document_count: int

    model_config = ConfigDict(from_attributes=True)


class PermissionTemplateListResponse(BaseModel):
    """Response for GET /api/admin/permission-templates.

    Attributes:
        templates: List of permission templates.
    """

    templates: list[PermissionTemplateResponse]
