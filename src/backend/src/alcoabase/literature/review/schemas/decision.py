"""Pydantic v2 schemas for Screening Decision management.

Defines response schema for screening decisions and request schema
for human override submissions.

References:
    - Requirements: 9.3, 9.5
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScreeningDecisionResponseSchema(BaseModel):
    """Response schema for a Screening Decision record.

    Contains the AI verdict, confidence, rationale, matched criteria,
    and any human override information.

    Attributes:
        id: Decision primary key.
        screening_run_id: Parent screening run ID.
        ingestion_record_id: Screened IngestionRecord ID.
        verdict: AI verdict (include, exclude, uncertain).
        confidence: AI confidence score (0.0–1.0).
        rationale: AI rationale text.
        matched_inclusion_criteria: Indices of matched inclusion criteria.
        matched_exclusion_criteria: Indices of matched exclusion criteria.
        human_verdict: Human override verdict (include or exclude), if any.
        human_rationale: Human override rationale text, if any.
        reviewer_user_id: User who provided the human override, if any.
        override_timestamp: When the human override was recorded.
        created_at: Decision creation timestamp.
    """

    id: int
    screening_run_id: int
    ingestion_record_id: int
    verdict: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    matched_inclusion_criteria: list[int] = Field(default_factory=list)
    matched_exclusion_criteria: list[int] = Field(default_factory=list)
    human_verdict: str | None = None
    human_rationale: str | None = None
    reviewer_user_id: int | None = None
    override_timestamp: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HumanOverrideRequestSchema(BaseModel):
    """Request schema for submitting a human override on a screening decision.

    Attributes:
        human_verdict: Human reviewer's verdict (include or exclude).
        human_rationale: Explanation for the override (max 2000 characters).
    """

    human_verdict: Literal["include", "exclude"] = Field(
        ...,
        description="Human reviewer's verdict: 'include' or 'exclude'.",
    )
    human_rationale: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Explanation for the human override (max 2000 characters).",
    )
