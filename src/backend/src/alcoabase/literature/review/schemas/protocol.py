"""Pydantic v2 schemas for Screening Protocol management.

Defines PICO criteria, create/update/response schemas with field validators
including at-least-one-criterion cross-field validation and ISO-8601 date
format enforcement.

References:
    - Requirements: 8.1, 8.2, 8.3
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ISO-8601 date pattern (YYYY-MM-DD)
_ISO_8601_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PICOCriteriaSchema(BaseModel):
    """PICO framework criteria for systematic literature review.

    Attributes:
        population: Target population description (max 2000 chars).
        intervention: Intervention or exposure of interest (max 2000 chars).
        comparison: Comparator or control description (max 2000 chars).
        outcome: Outcome measures of interest (max 2000 chars).
    """

    population: str | None = Field(
        default=None,
        max_length=2000,
        description="Target population description.",
    )
    intervention: str | None = Field(
        default=None,
        max_length=2000,
        description="Intervention or exposure of interest.",
    )
    comparison: str | None = Field(
        default=None,
        max_length=2000,
        description="Comparator or control description.",
    )
    outcome: str | None = Field(
        default=None,
        max_length=2000,
        description="Outcome measures of interest.",
    )

    def has_any_field(self) -> bool:
        """Return True if at least one PICO field is non-empty."""
        return any(
            v is not None and v.strip() != ""
            for v in (self.population, self.intervention, self.comparison, self.outcome)
        )


class ScreeningProtocolCreateSchema(BaseModel):
    """Request schema for creating a new Screening Protocol.

    Validates that at least one criterion is defined across PICO fields,
    inclusion criteria, or exclusion criteria.

    Attributes:
        name: Protocol name (1–200 characters).
        description: Optional description (max 5000 characters).
        pico_criteria: PICO framework criteria.
        inclusion_criteria: List of inclusion criterion strings (max 20, each 1–500 chars).
        exclusion_criteria: List of exclusion criterion strings (max 20, each 1–500 chars).
        publication_date_from: Optional start date filter (ISO-8601 YYYY-MM-DD).
        publication_date_to: Optional end date filter (ISO-8601 YYYY-MM-DD).
        allowed_publication_types: Optional list of allowed publication types.
        allowed_languages: Optional list of ISO 639-1 language codes.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Protocol name (1–200 characters).",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional protocol description (max 5000 characters).",
    )
    pico_criteria: PICOCriteriaSchema = Field(
        default_factory=PICOCriteriaSchema,
        description="PICO framework criteria.",
    )
    inclusion_criteria: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Inclusion criterion strings (max 20 items).",
    )
    exclusion_criteria: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Exclusion criterion strings (max 20 items).",
    )
    publication_date_from: str | None = Field(
        default=None,
        description="Start date filter (ISO-8601 YYYY-MM-DD format).",
    )
    publication_date_to: str | None = Field(
        default=None,
        description="End date filter (ISO-8601 YYYY-MM-DD format).",
    )
    allowed_publication_types: list[str] | None = Field(
        default=None,
        description="Allowed publication types filter.",
    )
    allowed_languages: list[str] | None = Field(
        default=None,
        description="Allowed ISO 639-1 language codes.",
    )

    @field_validator("inclusion_criteria", "exclusion_criteria")
    @classmethod
    def validate_criteria_items(cls, v: list[str]) -> list[str]:
        """Validate each criterion string is 1–500 characters.

        Args:
            v: List of criterion strings.

        Returns:
            Validated list.

        Raises:
            ValueError: If any criterion is empty or exceeds 500 chars.
        """
        for i, item in enumerate(v):
            if len(item) < 1:
                msg = f"Criterion at index {i} must be at least 1 character."
                raise ValueError(msg)
            if len(item) > 500:
                msg = f"Criterion at index {i} must not exceed 500 characters."
                raise ValueError(msg)
        return v

    @field_validator("publication_date_from", "publication_date_to")
    @classmethod
    def validate_iso_date(cls, v: str | None) -> str | None:
        """Validate date string is in ISO-8601 YYYY-MM-DD format.

        Args:
            v: Date string or None.

        Returns:
            Validated date string or None.

        Raises:
            ValueError: If date does not match ISO-8601 format.
        """
        if v is None:
            return v
        if not _ISO_8601_DATE_RE.match(v):
            msg = "Date must be in ISO-8601 format (YYYY-MM-DD)."
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_at_least_one_criterion(self) -> "ScreeningProtocolCreateSchema":
        """Ensure at least one screening criterion is defined.

        A valid protocol must have at least one of:
        - A non-empty PICO field
        - At least one inclusion criterion
        - At least one exclusion criterion

        Raises:
            ValueError: If no criteria are defined.
        """
        has_pico = self.pico_criteria.has_any_field()
        has_inclusion = len(self.inclusion_criteria) > 0
        has_exclusion = len(self.exclusion_criteria) > 0

        if not (has_pico or has_inclusion or has_exclusion):
            msg = (
                "At least one screening criterion must be defined: "
                "provide a PICO field, inclusion criterion, or exclusion criterion."
            )
            raise ValueError(msg)
        return self


class ScreeningProtocolUpdateSchema(BaseModel):
    """Request schema for updating a Screening Protocol.

    All fields are optional; only provided fields are updated.

    Attributes:
        name: Protocol name (1–200 characters).
        description: Optional description (max 5000 characters).
        pico_criteria: PICO framework criteria.
        inclusion_criteria: Inclusion criterion strings (max 20, each 1–500 chars).
        exclusion_criteria: Exclusion criterion strings (max 20, each 1–500 chars).
        publication_date_from: Start date filter (ISO-8601 YYYY-MM-DD).
        publication_date_to: End date filter (ISO-8601 YYYY-MM-DD).
        allowed_publication_types: Allowed publication types.
        allowed_languages: Allowed ISO 639-1 language codes.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Protocol name (1–200 characters).",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Optional protocol description (max 5000 characters).",
    )
    pico_criteria: PICOCriteriaSchema | None = Field(
        default=None,
        description="PICO framework criteria.",
    )
    inclusion_criteria: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Inclusion criterion strings (max 20 items).",
    )
    exclusion_criteria: list[str] | None = Field(
        default=None,
        max_length=20,
        description="Exclusion criterion strings (max 20 items).",
    )
    publication_date_from: str | None = Field(
        default=None,
        description="Start date filter (ISO-8601 YYYY-MM-DD format).",
    )
    publication_date_to: str | None = Field(
        default=None,
        description="End date filter (ISO-8601 YYYY-MM-DD format).",
    )
    allowed_publication_types: list[str] | None = Field(
        default=None,
        description="Allowed publication types filter.",
    )
    allowed_languages: list[str] | None = Field(
        default=None,
        description="Allowed ISO 639-1 language codes.",
    )

    @field_validator("inclusion_criteria", "exclusion_criteria")
    @classmethod
    def validate_criteria_items(cls, v: list[str] | None) -> list[str] | None:
        """Validate each criterion string is 1–500 characters.

        Args:
            v: List of criterion strings or None.

        Returns:
            Validated list or None.

        Raises:
            ValueError: If any criterion is empty or exceeds 500 chars.
        """
        if v is None:
            return v
        for i, item in enumerate(v):
            if len(item) < 1:
                msg = f"Criterion at index {i} must be at least 1 character."
                raise ValueError(msg)
            if len(item) > 500:
                msg = f"Criterion at index {i} must not exceed 500 characters."
                raise ValueError(msg)
        return v

    @field_validator("publication_date_from", "publication_date_to")
    @classmethod
    def validate_iso_date(cls, v: str | None) -> str | None:
        """Validate date string is in ISO-8601 YYYY-MM-DD format.

        Args:
            v: Date string or None.

        Returns:
            Validated date string or None.

        Raises:
            ValueError: If date does not match ISO-8601 format.
        """
        if v is None:
            return v
        if not _ISO_8601_DATE_RE.match(v):
            msg = "Date must be in ISO-8601 format (YYYY-MM-DD)."
            raise ValueError(msg)
        return v


class ScreeningProtocolResponseSchema(BaseModel):
    """Response schema for a Screening Protocol record.

    Extends the create fields with server-managed fields (id, company_id,
    version, status, audit timestamps).

    Attributes:
        id: Protocol primary key.
        company_id: Company this protocol belongs to.
        name: Protocol name.
        description: Protocol description.
        pico_criteria: PICO framework criteria.
        inclusion_criteria: List of inclusion criterion strings.
        exclusion_criteria: List of exclusion criterion strings.
        publication_date_from: Start date filter.
        publication_date_to: End date filter.
        allowed_publication_types: Allowed publication types.
        allowed_languages: Allowed language codes.
        version: Protocol version (auto-incremented on update).
        status: Protocol lifecycle status (draft, active, archived).
        created_by: User ID who created this protocol.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    id: int
    company_id: int
    name: str
    description: str | None = None
    pico_criteria: PICOCriteriaSchema
    inclusion_criteria: list[str] = Field(default_factory=list)
    exclusion_criteria: list[str] = Field(default_factory=list)
    publication_date_from: str | None = None
    publication_date_to: str | None = None
    allowed_publication_types: list[str] | None = None
    allowed_languages: list[str] | None = None
    version: int
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
