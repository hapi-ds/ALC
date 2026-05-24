"""Pydantic request/response schemas for review pipeline endpoints.

Provides validated schemas for multi-agent review sessions, audit profiles,
compliance scorecards, missing link detection, and anomaly alerts.

References:
    - Design doc Section 8: Pydantic Schemas
    - Requirements 10.1–10.8
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Review Session Schemas ---


class ReviewSubmitRequest(BaseModel):
    """Request schema for submitting a document for multi-agent review.

    Attributes:
        document_id: ID of the document to review.
        document_version_id: ID of the specific document version to review.
        audit_profile_id: Optional audit profile override (uses company default if None).
    """

    document_id: int
    document_version_id: int
    audit_profile_id: int | None = None


class AgentReviewResponse(BaseModel):
    """Response schema for an individual agent's review within a session.

    Attributes:
        id: Agent review primary key.
        agent_definition_id: ID of the agent definition that performed the review.
        agent_name: Display name of the reviewing agent.
        agent_archetype: Archetype category of the agent (null for v1.0 agents).
        status: Current review status (Pending/InProgress/Completed/Failed).
        report_data: Full structured review report (null if not yet completed).
        error_reason: Reason for failure (null if not failed).
        inference_duration_ms: Wall-clock inference time in milliseconds.
        started_at: When the agent review task started.
        completed_at: When the agent review task completed.
    """

    id: int
    agent_definition_id: int
    agent_name: str
    agent_archetype: str | None
    status: str
    report_data: dict | None
    error_reason: str | None
    inference_duration_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class MasterSummaryResponse(BaseModel):
    """Response schema for the Master Auditor's synthesized summary.

    Attributes:
        id: Master summary primary key.
        compliance_score: Overall compliance score (0.0–100.0).
        risk_assessment: Risk band classification (Critical/At Risk/Needs Attention/Good/Excellent).
        executive_summary: High-level textual summary of findings.
        consensus_findings: Findings agreed upon by 2+ agents.
        contradictions: Findings where agents disagree on severity or presence.
        prioritized_action_items: Action items ordered by severity then frequency.
    """

    id: int
    compliance_score: float = Field(ge=0.0, le=100.0)
    risk_assessment: str
    executive_summary: str
    consensus_findings: list[dict]
    contradictions: list[dict]
    prioritized_action_items: list[dict]

    model_config = ConfigDict(from_attributes=True)


class ReviewSessionResponse(BaseModel):
    """Response schema for a review session with optional nested details.

    Attributes:
        id: Review session primary key.
        document_id: ID of the reviewed document.
        document_title: Title of the reviewed document.
        document_type: Type classification of the document.
        status: Current session status (Pending/InProgress/Completed/Failed/Approved/Rejected).
        compliance_score: Overall compliance score (null if not yet computed).
        summary_failed: Whether the Master Auditor summarization failed.
        submitted_by: ID of the user who submitted the review.
        submitted_at: When the review was submitted.
        completed_at: When the review session completed (null if still in progress).
        agent_reviews: List of individual agent reviews (included in detail view).
        master_summary: Master Auditor summary (included if completed).
    """

    id: int
    document_id: int
    document_title: str
    document_type: str
    status: str
    compliance_score: float | None = Field(default=None, ge=0.0, le=100.0)
    summary_failed: bool
    submitted_by: int
    submitted_at: datetime
    completed_at: datetime | None
    agent_reviews: list[AgentReviewResponse] | None = None
    master_summary: MasterSummaryResponse | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Action Item Schemas ---


class ActionItemResponse(BaseModel):
    """Response schema for a review action item.

    Attributes:
        id: Action item primary key.
        finding_id: Reference to the original finding identifier.
        title: Short title describing the action item.
        description: Detailed description of what needs to be done.
        severity: Finding severity (Critical/Major/Minor/Informational).
        status: Current status (Open/InProgress/Resolved/Dismissed).
        assigned_to: ID of the user assigned to resolve this item (null if unassigned).
        resolved_at: When the item was resolved (null if not resolved).
        resolution_note: Note explaining the resolution (null if not resolved).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: int
    finding_id: str
    title: str
    description: str
    severity: str
    status: str
    assigned_to: int | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ActionItemCreateRequest(BaseModel):
    """Request schema for creating a new action item from a finding.

    Attributes:
        finding_id: Reference to the original finding identifier.
        title: Short title describing the action item.
        description: Detailed description of what needs to be done.
        severity: Finding severity (Critical/Major/Minor/Informational).
        assigned_to: Optional user ID to assign the item to.
    """

    finding_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    assigned_to: int | None = None


class ActionItemUpdateRequest(BaseModel):
    """Request schema for updating an action item's status.

    Attributes:
        status: New status (Open/InProgress/Resolved/Dismissed).
        resolution_note: Optional note explaining the resolution.
    """

    status: str = Field(min_length=1)
    resolution_note: str | None = None


# --- Audit Profile Schemas ---


class AuditProfileRequest(BaseModel):
    """Request schema for creating or updating an audit profile.

    Attributes:
        name: Profile display name (1–200 chars).
        description: Optional description (max 2000 chars).
        regulatory_frameworks: List of applicable regulatory frameworks (at least 1).
        assigned_agent_ids: List of agent definition IDs to include (at least 1).
        quorum: Minimum number of agent reviews required (at least 1).
        severity_thresholds: Optional custom severity weight overrides.
        is_default: Whether this profile is the company default.
    """

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    regulatory_frameworks: list[str] = Field(min_length=1)
    assigned_agent_ids: list[int] = Field(min_length=1)
    quorum: int = Field(ge=1)
    severity_thresholds: dict[str, float] | None = None
    is_default: bool = False


class AuditProfileResponse(BaseModel):
    """Response schema for an audit profile.

    Attributes:
        id: Audit profile primary key.
        company_id: ID of the owning company.
        name: Profile display name.
        description: Profile description (null if not set).
        regulatory_frameworks: List of applicable regulatory frameworks.
        assigned_agent_ids: List of assigned agent definition IDs.
        quorum: Minimum number of agent reviews required.
        severity_thresholds: Severity weight configuration.
        is_default: Whether this is the company's default profile.
        is_active: Whether the profile is active (false = soft-deleted).
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: int
    company_id: int
    name: str
    description: str | None
    regulatory_frameworks: list[str]
    assigned_agent_ids: list[int]
    quorum: int = Field(ge=1)
    severity_thresholds: dict[str, float]
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


# --- Compliance Scorecard Schemas ---


class ComplianceScorecardResponse(BaseModel):
    """Response schema for the company-level compliance scorecard.

    Attributes:
        overall_score: Aggregate compliance score (0.0–100.0).
        risk_band: Risk classification (Excellent/Good/Needs Attention/At Risk/Critical).
        trend: Score trend over last 30 days (improving/stable/declining).
        total_documents_reviewed: Total documents reviewed in scoring window.
        documents_with_critical_findings: Count of documents with Critical findings.
        documents_with_open_action_items: Count of documents with unresolved action items.
        score_by_document_type: Compliance score breakdown by document type.
        last_updated: When the scorecard was last recalculated.
    """

    overall_score: float = Field(ge=0.0, le=100.0)
    risk_band: str
    trend: str
    total_documents_reviewed: int = Field(ge=0)
    documents_with_critical_findings: int = Field(ge=0)
    documents_with_open_action_items: int = Field(ge=0)
    score_by_document_type: dict[str, float]
    last_updated: datetime


# --- Missing Link Schemas ---


class MissingLinkResponse(BaseModel):
    """Response schema for a document with compliance gaps.

    Attributes:
        document_id: ID of the document with missing links.
        document_uuid: Unique document identifier (YYYY-NNNNN format).
        document_title: Title of the document.
        document_type: Type classification of the document.
        current_status: Current workflow status (Approved/Active).
        missing_items: List of missing compliance items ("training" and/or "signature").
        affected_user_count: Number of users affected by training gaps.
        days_since_approval: Days elapsed since the document was approved.
        severity: Gap severity (Critical if both missing, Major if one missing).
    """

    document_id: int
    document_uuid: str
    document_title: str
    document_type: str
    current_status: str
    missing_items: list[str]
    affected_user_count: int = Field(ge=0)
    days_since_approval: int = Field(ge=0)
    severity: str


# --- Anomaly Alert Schemas ---


class AnomalyAlertResponse(BaseModel):
    """Response schema for an anomaly detection alert.

    Attributes:
        id: Anomaly alert primary key.
        anomaly_type: Type of anomaly detected.
        severity: Alert severity (Critical/Major/Minor).
        description: Human-readable description of the anomaly.
        affected_document_id: ID of the affected document (null if not document-specific).
        affected_user_id: ID of the affected user (null if not user-specific).
        detected_at: When the anomaly was detected.
        is_resolved: Whether the anomaly has been resolved.
        resolved_at: When the anomaly was resolved (null if unresolved).
        resolution_note: Note explaining the resolution (null if unresolved).
        created_at: Creation timestamp.
    """

    id: int
    anomaly_type: str
    severity: str
    description: str
    affected_document_id: int | None
    affected_user_id: int | None
    detected_at: datetime
    is_resolved: bool
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnomalyResolveRequest(BaseModel):
    """Request schema for resolving an anomaly alert.

    Attributes:
        resolution_note: Explanation of how the anomaly was resolved (1–2000 chars).
    """

    resolution_note: str = Field(min_length=1, max_length=2000)
