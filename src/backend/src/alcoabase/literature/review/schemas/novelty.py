"""Pydantic v2 schemas for Novelty Flag management.

Defines response schema for novelty flags and request schema for
status update transitions.

References:
    - Requirements: 10.1, 10.5
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NoveltyFlagResponseSchema(BaseModel):
    """Response schema for a Novelty Flag record.

    Represents a piece of literature that covers a topic not currently
    present in the company's internal document corpus.

    Attributes:
        id: Flag primary key.
        ingestion_record_id: External literature record that triggered the flag.
        company_id: Company this flag belongs to.
        novelty_description: Description of the novel topic.
        relevance_score: Relevance score (0.0–1.0).
        high_priority: Whether this flag is high priority (score >= 0.8).
        suggested_document_types: Suggested internal document types to create.
        status: Flag lifecycle status (open, acknowledged, integrated, dismissed).
        group_id: Optional group identifier for related novelty flags.
        linked_document_id: Linked internal document ID (once integrated).
        created_at: Flag creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    ingestion_record_id: int
    company_id: int
    novelty_description: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    high_priority: bool
    suggested_document_types: list[str] = Field(default_factory=list)
    status: str
    group_id: str | None = None
    linked_document_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NoveltyStatusUpdateSchema(BaseModel):
    """Request schema for updating the status of a Novelty Flag.

    Supports transitions to acknowledged, integrated, or dismissed.

    Attributes:
        status: New flag status (acknowledged, integrated, or dismissed).
        linked_document_id: Optional linked document ID (for integration).
        reason: Optional reason for the status change (max 2000 chars).
    """

    status: Literal["acknowledged", "integrated", "dismissed"] = Field(
        ...,
        description="New flag status.",
    )
    linked_document_id: int | None = Field(
        default=None,
        description="Linked internal document ID (when integrating).",
    )
    reason: str | None = Field(
        default=None,
        max_length=2000,
        description="Reason for the status change (max 2000 characters).",
    )
