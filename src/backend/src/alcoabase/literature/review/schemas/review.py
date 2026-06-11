"""Pydantic v2 schemas for SLR Review management.

Defines schemas for creating/retrieving SLR reviews, PRISMA flow
statistics, screening progress, inter-rater reliability, and
summary reports.

References:
    - Requirements: 9.1, 9.3, 9.5
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from alcoabase.literature.review.schemas.protocol import PICOCriteriaSchema


class SLRReviewCreateSchema(BaseModel):
    """Request schema for creating a new SLR Review.

    Links a review to an existing screening protocol and defines the
    set of records to screen via a filter.

    Attributes:
        protocol_id: Associated Screening Protocol ID.
        name: Review name (1–200 characters).
        description: Optional review description.
        record_filter: Filter dict to resolve the set of IngestionRecords.
    """

    protocol_id: int = Field(
        ...,
        description="Associated Screening Protocol ID.",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Review name (1–200 characters).",
    )
    description: str | None = Field(
        default=None,
        description="Optional review description.",
    )
    record_filter: dict[str, Any] = Field(
        default_factory=dict,
        description="Filter dict to resolve the set of IngestionRecords to screen.",
    )


class PRISMAFlowSchema(BaseModel):
    """PRISMA flow diagram statistics for a review.

    Represents the key counts at each stage of the PRISMA flow,
    computed from ScreeningDecision aggregates.

    Attributes:
        records_identified: Total records identified for screening.
        records_screened: Total records that have been screened.
        records_eligible: Records passing screening (include verdicts).
        records_included_final: Records included in final synthesis.
        records_excluded_with_reasons: Exclusion counts grouped by reason.
    """

    records_identified: int = Field(
        default=0,
        ge=0,
        description="Total records identified for screening.",
    )
    records_screened: int = Field(
        default=0,
        ge=0,
        description="Total records that have been screened.",
    )
    records_eligible: int = Field(
        default=0,
        ge=0,
        description="Records passing screening (include verdicts).",
    )
    records_included_final: int = Field(
        default=0,
        ge=0,
        description="Records included in final synthesis.",
    )
    records_excluded_with_reasons: dict[str, int] = Field(
        default_factory=dict,
        description="Exclusion counts grouped by reason.",
    )


class SLRReviewResponseSchema(BaseModel):
    """Response schema for an SLR Review record.

    Includes full review metadata, status, and optional PRISMA flow.

    Attributes:
        id: Review primary key.
        company_id: Company this review belongs to.
        protocol_id: Associated Screening Protocol ID.
        name: Review name.
        description: Review description.
        status: Review lifecycle status.
        record_filter: Filter used to resolve the record set.
        created_by: User ID who created this review.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
        prisma_flow: Optional PRISMA flow statistics.
    """

    id: int
    company_id: int
    protocol_id: int
    name: str
    description: str | None = None
    status: str
    record_filter: dict[str, Any] = Field(default_factory=dict)
    created_by: int
    created_at: datetime
    updated_at: datetime
    prisma_flow: PRISMAFlowSchema | None = None

    model_config = ConfigDict(from_attributes=True)


class ScreeningProgressSchema(BaseModel):
    """Real-time screening progress for an SLR Review.

    Attributes:
        total_records: Total records to screen.
        screened_count: Records already screened.
        pending_count: Records awaiting screening.
        include_count: Records with include verdict.
        exclude_count: Records with exclude verdict.
        uncertain_count: Records with uncertain verdict.
        estimated_time_remaining_seconds: Estimated seconds until completion.
    """

    total_records: int = Field(
        default=0,
        ge=0,
        description="Total records to screen.",
    )
    screened_count: int = Field(
        default=0,
        ge=0,
        description="Records already screened.",
    )
    pending_count: int = Field(
        default=0,
        ge=0,
        description="Records awaiting screening.",
    )
    include_count: int = Field(
        default=0,
        ge=0,
        description="Records with include verdict.",
    )
    exclude_count: int = Field(
        default=0,
        ge=0,
        description="Records with exclude verdict.",
    )
    uncertain_count: int = Field(
        default=0,
        ge=0,
        description="Records with uncertain verdict.",
    )
    estimated_time_remaining_seconds: float | None = Field(
        default=None,
        description="Estimated seconds until screening completion.",
    )


class InterRaterReliabilitySchema(BaseModel):
    """Inter-rater reliability metrics between AI and human reviewers.

    Computed from decisions that have both AI and human verdicts.

    Attributes:
        agreement_rate: Proportion of decisions where AI and human agree.
        cohens_kappa: Cohen's kappa coefficient for inter-rater agreement.
        false_positive_rate: Rate of AI include verdicts overridden to exclude.
        false_negative_rate: Rate of AI exclude verdicts overridden to include.
    """

    agreement_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Proportion of decisions where AI and human agree.",
    )
    cohens_kappa: float = Field(
        ...,
        description="Cohen's kappa coefficient for inter-rater agreement.",
    )
    false_positive_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Rate of AI include verdicts overridden to exclude.",
    )
    false_negative_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Rate of AI exclude verdicts overridden to include.",
    )


class SLRReportSchema(BaseModel):
    """Complete SLR summary report for regulatory submissions.

    Combines review metadata, PRISMA flow, screening statistics,
    and inter-rater reliability into a single exportable structure.

    Attributes:
        review_id: SLR Review primary key.
        review_name: Review name.
        protocol_name: Associated protocol name.
        protocol_version: Protocol version used for screening.
        pico_criteria: PICO criteria from the protocol.
        status: Current review status.
        created_at: Review creation timestamp.
        completed_at: Review completion timestamp (if completed).
        prisma_flow: PRISMA flow statistics.
        screening_statistics: Aggregate screening metrics.
        inter_rater_reliability: Inter-rater reliability metrics (if available).
    """

    review_id: int
    review_name: str
    protocol_name: str
    protocol_version: int
    pico_criteria: PICOCriteriaSchema
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    prisma_flow: PRISMAFlowSchema
    screening_statistics: dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregate screening metrics.",
    )
    inter_rater_reliability: InterRaterReliabilitySchema | None = None
