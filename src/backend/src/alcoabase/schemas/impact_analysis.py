"""Pydantic request/response schemas for impact analysis endpoints.

Provides validated schemas for dependency graph operations, impact reports,
gap analysis, notifications, and job status tracking.

References:
    - Design doc: Pydantic Schemas (Key Structures)
    - Requirements: 1.5, 1.8, 3.5, 4.3, 5.1, 5.3, 5.4, 6.3, 6.4, 8.2, 8.5
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Core Data Structures (stored in JSONB) ---


class AffectedItemSchema(BaseModel):
    """Structure stored in ImpactReport.affected_items JSONB.

    Represents a document or training task identified as impacted by a change,
    including severity assessment and AI reasoning metadata.

    Attributes:
        affected_document_uuid: UUID of the affected document (null for training tasks).
        training_task_id: ID of the affected training task (null for documents).
        affected_document_title: Display title of the affected item.
        dependency_type: Type of dependency relationship to the changed document.
        impact_severity: Assessed severity of the impact.
        affected_sections: List of section headings in the dependent document that are impacted.
        change_summary: One-sentence description of why the item is affected.
        recommended_action: Recommended remediation action.
        inference_prompt_summary: First 500 characters of the prompt sent to the AI agent.
        model_response_summary: First 500 characters of the AI response.
        token_count: Token count for this individual assessment.
    """

    affected_document_uuid: str | None = None
    training_task_id: int | None = None
    affected_document_title: str
    dependency_type: str
    impact_severity: Literal["critical", "major", "minor", "unknown"]
    affected_sections: list[str]
    change_summary: str = Field(max_length=500)
    recommended_action: Literal[
        "update_required",
        "review_recommended",
        "retraining_required",
        "manual_review_required",
    ]
    inference_prompt_summary: str = Field(max_length=500)
    model_response_summary: str = Field(max_length=500)
    token_count: int


class GapFindingSchema(BaseModel):
    """Structure stored in ImpactReport.gap_findings and GapAnalysisResult.gap_findings.

    Represents a specific mismatch identified between an updated source document
    and a dependent document.

    Attributes:
        source_section: Section heading and paragraph index in the source document.
        source_content_excerpt: First 300 characters of the relevant source text.
        target_section: Section in the target document, or "not_found".
        target_content_excerpt: First 300 characters of the existing target text.
        gap_type: Classification of the gap.
        severity: Assessed severity of the gap.
        remediation_suggestion: AI-generated recommendation for fixing the gap.
        inference_prompt_summary: First 500 characters of the prompt sent to the AI agent.
        model_response_summary: First 500 characters of the AI response.
        token_count: Token count for this individual assessment.
    """

    source_section: str
    source_content_excerpt: str = Field(max_length=300)
    target_section: str
    target_content_excerpt: str = Field(max_length=300)
    gap_type: Literal["missing", "contradicts", "incomplete", "outdated"]
    severity: Literal["critical", "major", "minor"]
    remediation_suggestion: str
    inference_prompt_summary: str = Field(max_length=500)
    model_response_summary: str = Field(max_length=500)
    token_count: int


class ChangeDeltaSchema(BaseModel):
    """Structure stored in ImpactReport.change_delta_summary.

    Represents the semantic difference between two versions of a document,
    classified by change type and significance.

    Attributes:
        sections_added: List of sections present in new version but absent in old.
        sections_modified: List of sections present in both with different content.
        sections_deleted: List of sections present in old version but absent in new.
        significance_levels: Count of changes by significance level.
        metadata: Additional metadata (e.g., fallback_used, user_attribution_unavailable).
    """

    sections_added: list[dict[str, str]]
    sections_modified: list[dict[str, str]]
    sections_deleted: list[dict[str, str]]
    significance_levels: dict[str, int]
    metadata: dict[str, Any] = {}


# --- Request Schemas ---


class BuildGraphRequest(BaseModel):
    """Request schema for triggering a dependency graph build.

    Attributes:
        scope: Build scope - "full" rebuilds entire graph, "incremental" updates only
            documents modified since last successful build.
    """

    scope: Literal["full", "incremental"] = "incremental"


class TriggerAnalysisRequest(BaseModel):
    """Request schema for manually triggering impact analysis.

    Attributes:
        document_id: ID of the document to analyze.
        document_version_id: Specific version to analyze (defaults to latest if None).
    """

    document_id: int
    document_version_id: int | None = None


class GapAnalysisRequest(BaseModel):
    """Request schema for triggering gap analysis between two documents.

    Attributes:
        source_document_id: ID of the source (updated) document.
        target_document_id: ID of the target (dependent) document.
        source_version_id: Specific source version (defaults to latest if None).
        target_version_id: Specific target version (defaults to latest if None).
    """

    source_document_id: int
    target_document_id: int
    source_version_id: int | None = None
    target_version_id: int | None = None


# --- Response Schemas ---


class DependencyEdgeResponse(BaseModel):
    """Response schema for a single dependency edge in the graph.

    Attributes:
        id: Edge primary key.
        source_document_uuid: UUID of the source document.
        target_document_uuid: UUID of the target document.
        dependency_type: Type of dependency relationship.
        confidence_score: Confidence score (0.0 to 1.0).
        detected_references: Array of reference identifiers linking the documents.
        last_verified_at: When the edge was last verified.
        created_at: When the edge was created.
        updated_at: When the edge was last updated.
    """

    id: int
    source_document_uuid: str
    target_document_uuid: str
    dependency_type: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    detected_references: list[str]
    last_verified_at: datetime
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ImpactReportResponse(BaseModel):
    """Response schema for a full impact report.

    Attributes:
        id: Report primary key.
        report_id: UUID identifier for the report.
        triggering_document_uuid: UUID of the document that triggered the analysis.
        triggering_version_id: Version ID that triggered the analysis.
        change_delta_summary: Structured summary of what changed.
        affected_items: List of affected items with severity and recommendations.
        gap_findings: List of gap findings.
        status: Terminal status of the analysis job.
        analysis_timestamp: When the analysis was performed.
        analysis_duration_ms: Duration of the analysis in milliseconds.
        agent_archetype_used: Name of the agent archetype used.
        model_used: Name of the AI model used.
        total_token_count: Total tokens consumed across all assessments.
        requesting_user_id: ID of the user who requested the analysis (null for auto-triggered).
        company_id: ID of the owning company.
        created_at: When the report record was created.
    """

    id: int
    report_id: str
    triggering_document_uuid: str
    triggering_version_id: int
    change_delta_summary: ChangeDeltaSchema
    affected_items: list[AffectedItemSchema]
    gap_findings: list[GapFindingSchema]
    status: Literal["completed", "partial_success", "failed"]
    analysis_timestamp: datetime
    analysis_duration_ms: int
    agent_archetype_used: str
    model_used: str
    total_token_count: int
    requesting_user_id: int | None = None
    company_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImpactReportListResponse(BaseModel):
    """Response schema for paginated list of impact reports.

    Attributes:
        reports: List of impact reports for the current page.
        total_count: Total number of matching reports before pagination.
    """

    reports: list[ImpactReportResponse]
    total_count: int


class GapAnalysisResultResponse(BaseModel):
    """Response schema for gap analysis results.

    Attributes:
        id: Result primary key.
        job_id: Job identifier for the gap analysis.
        source_document_uuid: UUID of the source document.
        target_document_uuid: UUID of the target document.
        gap_findings: List of gap findings.
        total_gaps_detected: Total number of gaps detected (before limiting).
        gaps_retained: Number of gaps retained (after limiting to top 100).
        status: Terminal status of the gap analysis.
        analysis_duration_ms: Duration of the analysis in milliseconds.
        company_id: ID of the owning company.
        created_at: When the result record was created.
    """

    id: int
    job_id: str
    source_document_uuid: str
    target_document_uuid: str
    gap_findings: list[GapFindingSchema]
    total_gaps_detected: int
    gaps_retained: int
    status: Literal["completed", "partial_success", "failed"]
    analysis_duration_ms: int
    company_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobStatusResponse(BaseModel):
    """Response schema for job status and progress tracking.

    Attributes:
        job_id: Unique job identifier.
        status: Current job status.
        progress_percent: Progress percentage (0-100).
        current_phase: Current phase of the analysis pipeline.
        items_assessed: Number of items assessed so far.
        items_total: Total number of items to assess.
        critical_findings_count: Number of critical findings discovered.
        major_findings_count: Number of major findings discovered.
        minor_findings_count: Number of minor findings discovered.
        error_message: Failure reason (null unless status is failed).
    """

    job_id: str
    status: Literal["processing", "completed", "partial_success", "failed"]
    progress_percent: int = Field(ge=0, le=100)
    current_phase: Literal[
        "computing_delta",
        "querying_dependencies",
        "assessing_impact",
        "analyzing_gaps",
        "persisting_report",
    ]
    items_assessed: int = Field(ge=0)
    items_total: int = Field(ge=0)
    critical_findings_count: int = Field(ge=0)
    major_findings_count: int = Field(ge=0)
    minor_findings_count: int = Field(ge=0)
    error_message: str | None = Field(default=None, max_length=1000)


class NotificationResponse(BaseModel):
    """Response schema for an impact notification.

    Attributes:
        id: Notification primary key.
        report_id: UUID of the associated impact report.
        affected_document_uuid: UUID of the affected document.
        notification_type: Type of notification.
        impact_severity: Severity of the impact.
        change_summary: Summary of the change that caused the notification.
        target_user_id: ID of the user targeted by the notification.
        is_acknowledged: Whether the notification has been acknowledged.
        acknowledged_at: When the notification was acknowledged.
        acknowledged_by: ID of the user who acknowledged the notification.
        company_id: ID of the owning company.
        created_at: When the notification was created.
    """

    id: int
    report_id: str
    affected_document_uuid: str
    notification_type: Literal["change_impact"]
    impact_severity: Literal["critical", "major", "minor", "unknown"]
    change_summary: str = Field(max_length=2000)
    target_user_id: int
    is_acknowledged: bool
    acknowledged_at: datetime | None = None
    acknowledged_by: int | None = None
    company_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentImpactStatusResponse(BaseModel):
    """Response schema for a document's impact analysis status.

    Attributes:
        document_uuid: UUID of the document.
        last_analysis_date: When the last analysis was performed (null if never).
        last_analysis_report_id: Report ID of the last analysis (null if never).
        outstanding_critical_count: Number of unresolved critical findings.
        outstanding_major_count: Number of unresolved major findings.
        is_up_to_date: True if no unresolved critical or major findings exist.
    """

    document_uuid: str
    last_analysis_date: datetime | None = None
    last_analysis_report_id: str | None = None
    outstanding_critical_count: int = Field(ge=0, default=0)
    outstanding_major_count: int = Field(ge=0, default=0)
    is_up_to_date: bool = True


# --- Filter and Pagination Schemas ---


class ReportFilters(BaseModel):
    """Filter parameters for listing impact reports.

    Attributes:
        triggering_document_uuid: Filter by triggering document UUID.
        severity: Filter by reports containing at least one finding of this severity.
        start_date: Filter by analysis timestamp >= start_date (ISO 8601).
        end_date: Filter by analysis timestamp <= end_date (ISO 8601).
        status: Filter by report status.
    """

    triggering_document_uuid: str | None = None
    severity: Literal["critical", "major", "minor"] | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    status: Literal["completed", "partial_success", "failed"] | None = None


class GraphFilters(BaseModel):
    """Filter parameters for listing dependency graph edges.

    Attributes:
        source_document_uuid: Filter by source document UUID.
        target_document_uuid: Filter by target document UUID.
        dependency_type: Filter by dependency type.
    """

    source_document_uuid: str | None = None
    target_document_uuid: str | None = None
    dependency_type: Literal[
        "validates", "references", "implements", "trains_on", "derived_from"
    ] | None = None


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints.

    Attributes:
        limit: Maximum number of items to return.
        offset: Number of items to skip.
    """

    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
