"""Pydantic v2 schemas for Vigilance Signal endpoints.

Provides response schemas for vigilance signals, disposition updates,
and signal summary aggregations.

References:
    - Requirements: 5.3, 6.4, 10.1, 10.3
    - Design doc: VigilanceSignalAnalyzer interface
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SignalSeverityEnum = Literal["critical", "major", "minor"]
SignalDispositionEnum = Literal[
    "under_review", "confirmed", "dismissed", "escalated"
]


class VigilanceSignalResponseSchema(BaseModel):
    """Response schema for a vigilance signal.

    Attributes:
        id: Signal record ID.
        ingestion_record_id: Associated literature ingestion record.
        product_id: Associated medical product ID.
        profile_id: Originating search profile ID.
        company_id: Company this signal belongs to.
        severity: Signal severity classification.
        evidence_summary: Explanation of findings.
        affected_product_aspects: Device functions/components implicated.
        regulatory_references: Applicable regulation articles.
        recommended_actions: Suggested next steps.
        confidence: Analysis confidence score (0.0–1.0).
        disposition: Current signal disposition.
        dismissal_reason: Reason for dismissal (if dismissed).
        confirmation_note: Note confirming signal (if confirmed).
        reviewer_user_id: User who last updated disposition.
        detection_timestamp: When the signal was detected.
        created_at: When the record was created.
        updated_at: When the record was last modified.
    """

    id: int
    ingestion_record_id: int
    product_id: int
    profile_id: int
    company_id: int
    severity: SignalSeverityEnum
    evidence_summary: str
    affected_product_aspects: list[str]
    regulatory_references: list[str]
    recommended_actions: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    disposition: SignalDispositionEnum
    dismissal_reason: str | None = None
    confirmation_note: str | None = None
    reviewer_user_id: int | None = None
    detection_timestamp: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SignalDispositionUpdateSchema(BaseModel):
    """Request schema for updating a signal's disposition.

    Valid transitions:
        under_review → confirmed | dismissed | escalated
        confirmed → escalated

    When disposition is 'confirmed', confirmation_note is required.
    When disposition is 'dismissed', dismissal_reason is required.

    Attributes:
        disposition: Target disposition state.
        confirmation_note: Required when confirming (max 3000 chars).
        dismissal_reason: Required when dismissing (max 2000 chars).
    """

    disposition: SignalDispositionEnum
    confirmation_note: str | None = Field(None, max_length=3000)
    dismissal_reason: str | None = Field(None, max_length=2000)

    @model_validator(mode="after")
    def validate_disposition_fields(self) -> "SignalDispositionUpdateSchema":
        """Ensure required fields are present for specific dispositions."""
        if self.disposition == "confirmed" and not self.confirmation_note:
            msg = "confirmation_note is required when disposition is 'confirmed'"
            raise ValueError(msg)
        if self.disposition == "dismissed" and not self.dismissal_reason:
            msg = "dismissal_reason is required when disposition is 'dismissed'"
            raise ValueError(msg)
        return self


class SignalCountByProduct(BaseModel):
    """Signal count aggregation for a single product.

    Attributes:
        product_id: The medical product ID.
        product_name: The product name for display.
        critical: Count of open critical signals.
        major: Count of open major signals.
        minor: Count of open minor signals.
    """

    product_id: int
    product_name: str
    critical: int = Field(ge=0, default=0)
    major: int = Field(ge=0, default=0)
    minor: int = Field(ge=0, default=0)


class SignalSummaryResponseSchema(BaseModel):
    """Response schema for signal summary aggregations.

    Provides aggregate statistics on open signals by severity and product,
    escalation counts, and time-to-disposition metrics.

    Attributes:
        total_open_signals: Total signals with disposition under_review or confirmed.
        signals_by_product: Breakdown of open signals by product and severity.
        escalated_this_period: Number of signals escalated in current period.
        avg_time_to_disposition_hours: Average hours from detection to disposition.
    """

    total_open_signals: int = Field(ge=0)
    signals_by_product: list[SignalCountByProduct]
    escalated_this_period: int = Field(ge=0)
    avg_time_to_disposition_hours: float | None = None
