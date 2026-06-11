"""Pydantic v2 schemas for Contradiction Alert management.

Defines response schemas for contradiction alerts, status update requests,
and summary/aggregate statistics.

References:
    - Requirements: 10.1, 10.5
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContradictionAlertResponseSchema(BaseModel):
    """Response schema for a Contradiction Alert record.

    Contains full alert details including severity, evidence, confidence,
    and resolution status.

    Attributes:
        id: Alert primary key.
        ingestion_record_id: External literature record that triggered the alert.
        internal_document_id: Internal document with potential contradiction.
        company_id: Company this alert belongs to.
        severity: Alert severity (critical, major, minor).
        description: Description of the detected contradiction.
        evidence: Supporting evidence from the literature.
        recommended_action: Suggested corrective action.
        confidence: Detection confidence score (0.0–1.0).
        status: Alert lifecycle status (open, acknowledged, resolved, dismissed).
        impact_report_id: Linked impact analysis report ID (if escalated).
        created_at: Alert creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    ingestion_record_id: int
    internal_document_id: int
    company_id: int
    severity: str
    description: str
    evidence: str
    recommended_action: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    status: str
    impact_report_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ContradictionStatusUpdateSchema(BaseModel):
    """Request schema for updating the status of a Contradiction Alert.

    Supports transitions to acknowledged, resolved, or dismissed with
    optional notes.

    Attributes:
        status: New status (acknowledged, resolved, or dismissed).
        resolution_note: Optional resolution explanation (max 3000 chars).
        dismissal_reason: Optional reason for dismissal (max 2000 chars).
        change_request_id: Optional linked change request ID.
    """

    status: Literal["acknowledged", "resolved", "dismissed"] = Field(
        ...,
        description="New alert status.",
    )
    resolution_note: str | None = Field(
        default=None,
        max_length=3000,
        description="Resolution explanation (max 3000 characters).",
    )
    dismissal_reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Reason for dismissal (max 2000 characters).",
    )
    change_request_id: int | None = Field(
        default=None,
        description="Linked change request ID for traceability.",
    )


class ContradictionSummarySchema(BaseModel):
    """Aggregate summary statistics for contradiction alerts.

    Used by the dashboard to display overall contradiction status.

    Attributes:
        total_open_by_severity: Count of open alerts grouped by severity.
        resolved_this_month: Number of alerts resolved in the current month.
        avg_time_to_resolution_hours: Average hours to resolve an alert.
        top_affected_docs: List of most frequently affected internal documents.
    """

    total_open_by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Count of open alerts grouped by severity level.",
    )
    resolved_this_month: int = Field(
        default=0,
        ge=0,
        description="Number of alerts resolved in the current month.",
    )
    avg_time_to_resolution_hours: float | None = Field(
        default=None,
        description="Average hours to resolve an alert (None if no resolved alerts).",
    )
    top_affected_docs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Most frequently affected internal documents.",
    )
