"""Pydantic request/response schemas for the Setup Wizard endpoints.

Provides validated schemas for root admin creation, company setup,
AI hardware mode configuration, setup progress tracking, and completion.

References:
    - Design doc: .kiro/specs/setup-wizard/design.md
    - Requirements 3.1, 3.2, 4.1, 4.3, 5.1, 8.1
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RootAdminCreate(BaseModel):
    """Request schema for creating the root admin account during setup.

    Attributes:
        username: Unique username for the root admin (3-100 chars).
        email: Valid email address for the root admin.
        password: Password meeting the GxP password policy (12-128 chars).
        full_name: Full display name for the root admin (1-200 chars).
    """

    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)


class CompanySetupCreate(BaseModel):
    """Request schema for creating the initial company during setup.

    Attributes:
        display_name: Human-readable company name (1-300 chars).
        slug: Optional URL-safe identifier; auto-generated from display_name if omitted.
        regulatory_framework: Quality management standard governing the company (max 50 chars).
    """

    display_name: str = Field(min_length=1, max_length=300)
    slug: str | None = Field(default=None, max_length=100)
    regulatory_framework: str = Field(max_length=50)


class AIModeConfig(BaseModel):
    """Request schema for configuring the AI hardware mode.

    Attributes:
        mode: The inference backend mode — "gpu", "cpu", or "mock".
    """

    mode: Literal["gpu", "cpu", "mock"]


class SetupCompleteRequest(BaseModel):
    """Request schema for finalizing the setup wizard.

    Attributes:
        seed_demo_data: Whether to seed demo data during completion.
    """

    seed_demo_data: bool = False


class SetupProgress(BaseModel):
    """Response schema representing current setup wizard progress.

    Attributes:
        is_complete: Whether the entire setup flow has been completed.
        admin_created: Whether the root admin account has been created.
        company_created: Whether the initial company has been created.
        ai_mode_configured: Whether the AI hardware mode has been configured.
        demo_data_seeded: Whether demo data has been seeded.
    """

    is_complete: bool
    admin_created: bool
    company_created: bool
    ai_mode_configured: bool
    demo_data_seeded: bool


class RootAdminResult(BaseModel):
    """Response schema returned after successful root admin creation.

    Attributes:
        user_id: The database ID of the created admin user.
        username: The username of the created admin.
        access_token: JWT access token for subsequent setup steps.
        token_type: The token type (always "bearer").
    """

    user_id: int
    username: str
    access_token: str
    token_type: str = "bearer"


class CompanyResult(BaseModel):
    """Response schema returned after successful company creation.

    Attributes:
        company_id: The database ID of the created company.
        slug: The URL-safe slug for the company.
        display_name: The human-readable company name.
    """

    company_id: int
    slug: str
    display_name: str


class AIModeResult(BaseModel):
    """Response schema returned after AI mode configuration.

    Attributes:
        mode: The configured AI hardware mode.
        connectivity_warning: Optional warning if the inference endpoint is unreachable.
    """

    mode: str
    connectivity_warning: str | None = None


class SetupCompleteResult(BaseModel):
    """Response schema returned after setup wizard completion.

    Attributes:
        message: A human-readable completion message.
        completed_at: The UTC timestamp when setup was finalized.
    """

    message: str
    completed_at: datetime
