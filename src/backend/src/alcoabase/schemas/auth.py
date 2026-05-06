"""Pydantic request/response schemas for authentication endpoints.

Provides validated schemas for login, token refresh, logout,
re-authentication, and user profile retrieval.

References:
    - Design doc: .kiro/specs/auth-session-frontend/design.md
    - Requirements 1.3, 1.4, 7.1, 7.3
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Request schema for user login.

    Attributes:
        username: The user's unique username.
        password: The user's password.
    """

    username: str = Field(..., description="The user's unique username.")
    password: str = Field(..., description="The user's password.")


class UserInfo(BaseModel):
    """Embedded user information returned in login response.

    Attributes:
        id: The user's database ID.
        username: The user's unique username.
        email: The user's email address.
        full_name: The user's full display name.
        roles: List of role names assigned to the user.
    """

    id: int
    username: str
    email: str
    full_name: str
    roles: list[str]

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    """Response schema for successful login.

    Attributes:
        access_token: JWT access token for authenticating subsequent requests.
        token_type: The token type (always "bearer").
        expires_in: Seconds until the access token expires.
        user: Basic user profile information.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Seconds until the access token expires.")
    user: UserInfo


class RefreshResponse(BaseModel):
    """Response schema for successful token refresh.

    Attributes:
        access_token: New JWT access token.
        token_type: The token type (always "bearer").
        expires_in: Seconds until the new access token expires.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Seconds until the access token expires.")


class LogoutResponse(BaseModel):
    """Response schema for successful logout.

    Attributes:
        message: Confirmation message.
    """

    message: str = "Logged out successfully"


class ReAuthRequest(BaseModel):
    """Request schema for re-authentication before sensitive operations.

    Attributes:
        password: The user's current password for verification.
    """

    password: str = Field(..., description="The user's current password for verification.")


class ReAuthResponse(BaseModel):
    """Response schema for successful re-authentication.

    Attributes:
        verified: Always True on success.
        signature_token: Short-lived token authorizing the signature operation.
        expires_in: Seconds until the signature token expires (e.g. 120).
    """

    verified: bool = True
    signature_token: str = Field(
        ..., description="Short-lived token for the signature operation."
    )
    expires_in: int = Field(
        ..., description="Seconds until the signature token expires."
    )


class CompanyMembership(BaseModel):
    """Embedded company membership information for the /me endpoint.

    Attributes:
        company_id: The company's database ID.
        company_slug: The company's URL-safe slug.
        role: The user's role within the company.
    """

    company_id: int
    company_slug: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class MeResponse(BaseModel):
    """Response schema for the /me endpoint returning the current user's profile.

    Attributes:
        id: The user's database ID.
        username: The user's unique username.
        email: The user's email address.
        full_name: The user's full display name.
        roles: List of role names assigned to the user.
        companies: List of company memberships with roles.
    """

    id: int
    username: str
    email: str
    full_name: str
    roles: list[str]
    companies: list[CompanyMembership]

    model_config = ConfigDict(from_attributes=True)
