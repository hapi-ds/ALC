"""Pydantic v2 schemas for per-company screening configuration.

Defines response/update schemas for screening configuration with
range validators on batch_size, confidence_threshold, and max_concurrent.

References:
    - Requirements: 11.4, 11.6
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScreeningConfigurationSchema(BaseModel):
    """Response schema for a per-company screening configuration.

    Attributes:
        id: Configuration record primary key.
        company_id: Company this configuration belongs to.
        auto_screen_on_index: Whether to auto-screen records when indexed.
        default_batch_size: Default batch size for screening runs (1–100).
        confidence_threshold: Confidence threshold for auto-include (0.5–1.0).
        max_concurrent: Maximum concurrent screening tasks (1–20).
        contradiction_detection_enabled: Whether contradiction detection is active.
        created_at: Configuration creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    company_id: int
    auto_screen_on_index: bool = Field(
        default=False,
        description="Whether to auto-screen records when indexed.",
    )
    default_batch_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Default batch size for screening runs (1–100).",
    )
    confidence_threshold: float = Field(
        default=0.8,
        ge=0.5,
        le=1.0,
        description="Confidence threshold for auto-include decisions (0.5–1.0).",
    )
    max_concurrent: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum concurrent screening tasks per company (1–20).",
    )
    contradiction_detection_enabled: bool = Field(
        default=True,
        description="Whether contradiction detection is active on indexing.",
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScreeningConfigurationUpdateSchema(BaseModel):
    """Request schema for updating screening configuration.

    All fields are optional; only provided fields are updated.
    Range validators enforce: batch_size 1–100, confidence 0.5–1.0,
    max_concurrent 1–20.

    Attributes:
        auto_screen_on_index: Whether to auto-screen records when indexed.
        default_batch_size: Default batch size for screening runs (1–100).
        confidence_threshold: Confidence threshold for auto-include (0.5–1.0).
        max_concurrent: Maximum concurrent screening tasks (1–20).
        contradiction_detection_enabled: Whether contradiction detection is active.
    """

    auto_screen_on_index: bool | None = Field(
        default=None,
        description="Whether to auto-screen records when indexed.",
    )
    default_batch_size: int | None = Field(
        default=None,
        ge=1,
        le=100,
        description="Default batch size for screening runs (1–100).",
    )
    confidence_threshold: float | None = Field(
        default=None,
        ge=0.5,
        le=1.0,
        description="Confidence threshold for auto-include decisions (0.5–1.0).",
    )
    max_concurrent: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description="Maximum concurrent screening tasks per company (1–20).",
    )
    contradiction_detection_enabled: bool | None = Field(
        default=None,
        description="Whether contradiction detection is active on indexing.",
    )
