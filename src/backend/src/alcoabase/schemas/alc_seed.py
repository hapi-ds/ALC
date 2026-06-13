"""Pydantic schemas for ALC corporate environment seed reports.

Provides validated response schemas for the ALCSeedService,
including step-level results and the complete SeedReport.

References:
    - Design doc: Seed_Report Schema, Error Handling
    - Requirements 6.4, 7.5, 8.4
"""

from pydantic import BaseModel


class UserPoolResult(BaseModel):
    """Result of user pool provisioning step.

    Attributes:
        users_created: Usernames of newly created users.
        users_skipped: Usernames that already existed.
    """

    users_created: list[str]
    users_skipped: list[str]


class FolderResult(BaseModel):
    """Result of folder structure creation step.

    Attributes:
        folders_created: Folder names created.
        folders_skipped: Folder names that already existed.
    """

    folders_created: list[str]
    folders_skipped: list[str]


class AgentResult(BaseModel):
    """Result of agent activation step.

    Attributes:
        agents_activated: Agent names newly activated or re-activated.
        agents_skipped: Agent names already active.
    """

    agents_activated: list[str]
    agents_skipped: list[str]


class SeedReport(BaseModel):
    """Complete report of ALC corporate environment seeding.

    Attributes:
        company_id: ID of the ALC company entity.
        company_slug: URL slug for the ALC company.
        users_created: Usernames of newly created users.
        users_skipped: Usernames that already existed.
        folders_created: Folder names created.
        folders_skipped: Folder names that already existed.
        risk_profile_created: Whether a new risk profile was created.
        regulatory_baseline_created: Whether the regulatory baseline config was created.
        audit_config_created: Whether the audit config was created.
        agents_activated: Agent names newly activated or re-activated.
        agents_skipped: Agent names already active.
        workflow_created: Whether the governance workflow was created.
        total_duration_ms: Total execution time in milliseconds.
    """

    company_id: int
    company_slug: str = "alc-corporate"
    users_created: list[str]
    users_skipped: list[str]
    folders_created: list[str]
    folders_skipped: list[str]
    risk_profile_created: bool
    regulatory_baseline_created: bool
    audit_config_created: bool
    agents_activated: list[str]
    agents_skipped: list[str]
    workflow_created: bool
    documents_uploaded: list[str] = []
    documents_skipped: list[str] = []
    total_duration_ms: int


class SeedError(BaseModel):
    """Error response when seeding fails.

    Attributes:
        error: Human-readable error message.
        failed_step: Step name that failed.
        detail: Additional context (e.g., missing task types).
    """

    error: str
    failed_step: str
    detail: str | None = None
