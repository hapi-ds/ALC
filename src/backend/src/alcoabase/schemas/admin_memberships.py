"""Pydantic request/response schemas for admin membership management endpoints.

Provides validated schemas for assigning users to companies and
viewing membership details including revocation status.

References:
    - Design doc: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements 11.1, 11.4
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AssignMembershipRequest(BaseModel):
    """Request body for POST /api/admin/memberships.

    Attributes:
        user_id: ID of the user to assign.
        company_id: ID of the company to assign the user to.
        role: The role to assign within the company.
    """

    user_id: int
    company_id: int
    role: Literal["system_admin", "doc_admin", "it_admin", "member", "viewer"]


class MembershipDetailResponse(BaseModel):
    """Response for membership endpoints.

    Attributes:
        id: The membership's database ID.
        user_id: ID of the associated user.
        user_username: Username of the associated user.
        user_full_name: Full name of the associated user.
        company_id: ID of the associated company.
        company_name: Name of the associated company.
        role: The assigned role within the company.
        created_at: Timestamp when the membership was created.
        revoked_at: Timestamp when the membership was revoked (None if active).
    """

    id: int
    user_id: int
    user_username: str
    user_full_name: str
    company_id: int
    company_name: str
    role: str
    created_at: datetime
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
