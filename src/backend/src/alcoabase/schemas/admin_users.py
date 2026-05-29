"""Pydantic request/response schemas for admin user management endpoints.

Provides validated schemas for user listing, creation, editing,
deactivation, password reset, and change history retrieval.

References:
    - Design doc: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements 5.1, 5.2, 5.3, 5.4, 6.1, 6.6, 7.1, 7.2, 9.3, 14.3
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- Request Schemas ---


class UserCreateRequest(BaseModel):
    """Request body for POST /api/admin/users.

    Attributes:
        username: Unique username (alphanumeric, dots, hyphens, underscores).
        email: Valid email address (must be unique system-wide).
        full_name: User's display name.
        role: Role to assign within the current company.
    """

    username: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_.\-]+$",
        description="Unique username (alphanumeric, dots, hyphens, underscores).",
    )
    email: EmailStr = Field(..., description="Valid email address.")
    full_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="User's full display name.",
    )
    role: Literal["system_admin", "doc_admin", "it_admin", "member", "viewer"] = Field(
        ..., description="Role to assign within the current company."
    )


class UserUpdateRequest(BaseModel):
    """Request body for PATCH /api/admin/users/{user_id}.

    All fields are optional; only provided fields are updated.

    Attributes:
        full_name: Updated display name.
        email: Updated email address (must be unique system-wide).
        role: Updated role assignment within the current company.
    """

    full_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated display name.",
    )
    email: EmailStr | None = Field(
        default=None, description="Updated email address."
    )
    role: Literal[
        "system_admin", "doc_admin", "it_admin", "member", "viewer"
    ] | None = Field(default=None, description="Updated role assignment.")


class UserListParams(BaseModel):
    """Query parameters for GET /api/admin/users.

    Attributes:
        search: Free-text search against username, email, or full_name.
        sort_by: Field to sort results by.
        sort_dir: Sort direction (ascending or descending).
        page: Page number (1-indexed).
        page_size: Number of results per page (1–100).
        is_active: Filter by active status (None returns all).
    """

    search: str | None = Field(
        default=None,
        max_length=200,
        description="Free-text search against username, email, or full_name.",
    )
    sort_by: Literal[
        "full_name", "username", "role", "is_active", "created_at"
    ] = Field(default="created_at", description="Field to sort results by.")
    sort_dir: Literal["asc", "desc"] = Field(
        default="desc", description="Sort direction."
    )
    page: int = Field(default=1, ge=1, description="Page number (1-indexed).")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Number of results per page."
    )
    is_active: bool | None = Field(
        default=None, description="Filter by active status (None returns all)."
    )


# --- Response Schemas ---


class UserListItem(BaseModel):
    """Single user in the paginated list response.

    Attributes:
        id: User's database ID.
        username: User's unique username.
        email: User's email address.
        full_name: User's display name.
        role: User's role within the current company.
        is_active: Whether the user account is active.
        created_at: Account creation timestamp (UTC).
    """

    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """Paginated response for GET /api/admin/users.

    Attributes:
        users: List of user items for the current page.
        total: Total number of users matching the query.
        page: Current page number.
        page_size: Number of results per page.
        total_pages: Total number of pages.
    """

    users: list[UserListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserCreateResponse(BaseModel):
    """Response for POST /api/admin/users (includes temporary password).

    The temporary_password is returned only on creation so the
    administrator can communicate it securely to the new user.

    Attributes:
        id: Newly created user's database ID.
        username: User's unique username.
        email: User's email address.
        full_name: User's display name.
        role: Assigned role within the current company.
        is_active: Whether the user account is active (always True on creation).
        created_at: Account creation timestamp (UTC).
        temporary_password: Initial password to communicate to the user.
    """

    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    temporary_password: str = Field(
        ..., description="Initial password to communicate to the user."
    )

    model_config = ConfigDict(from_attributes=True)


class MembershipInfo(BaseModel):
    """Membership info nested in user detail response.

    Attributes:
        id: Membership record ID.
        company_id: Associated company's database ID.
        company_name: Associated company's display name.
        role: User's role within this company.
        created_at: Membership creation timestamp (UTC).
        revoked_at: Timestamp when membership was revoked (None if active).
    """

    id: int
    company_id: int
    company_name: str
    role: str
    created_at: datetime
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class UserDetailResponse(BaseModel):
    """Detailed user response with company memberships.

    Attributes:
        id: User's database ID.
        username: User's unique username.
        email: User's email address.
        full_name: User's display name.
        is_active: Whether the user account is active.
        created_at: Account creation timestamp (UTC).
        memberships: List of company memberships (active and revoked).
    """

    id: int
    username: str
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    memberships: list[MembershipInfo]

    model_config = ConfigDict(from_attributes=True)


class PasswordResetResponse(BaseModel):
    """Response for POST /api/admin/users/{user_id}/reset-password.

    Attributes:
        user_id: ID of the user whose password was reset.
        temporary_password: New temporary password to communicate securely.
        message: Confirmation message.
    """

    user_id: int
    temporary_password: str = Field(
        ..., description="New temporary password to communicate securely."
    )
    message: str = "Password reset successful. Communicate the temporary password securely."


class UserHistoryEntry(BaseModel):
    """Single entry in user change history.

    Attributes:
        version_id: Version record identifier.
        changed_at: Timestamp of the change (UTC).
        changed_by: ID of the user who made the change.
        changed_by_username: Username of the user who made the change.
        change_reason: The X-Change-Reason value recorded with the change.
        changes: Dictionary of field changes {field: {old: value, new: value}}.
    """

    version_id: int
    changed_at: datetime
    changed_by: int
    changed_by_username: str
    change_reason: str
    changes: dict  # {field_name: {old: value, new: value}}

    model_config = ConfigDict(from_attributes=True)


class UserHistoryResponse(BaseModel):
    """Response for GET /api/admin/users/{user_id}/history.

    Attributes:
        user_id: ID of the user whose history is returned.
        entries: List of change history entries, ordered by most recent first.
    """

    user_id: int
    entries: list[UserHistoryEntry]
