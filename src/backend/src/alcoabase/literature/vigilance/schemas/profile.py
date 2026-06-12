"""Pydantic v2 schemas for Vigilance Search Profile endpoints.

Provides request/response schemas for CRUD operations on per-company,
per-product vigilance search profiles. Profiles define the search terms,
MeSH descriptors, adverse event keywords, device identifiers, and
scheduling parameters used for automated vigilance literature searches.

References:
    - Requirements: 3.1, 3.6, 9.6
    - Design doc: VigilanceSearchProfileService interface
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProfileStatusEnum = Literal["active", "paused", "archived"]

# Standard 5-field cron: minute hour day-of-month month day-of-week
_CRON_FIELD_PATTERNS = [
    r"(\*|[0-5]?\d)([,/\-][0-5]?\d)*",  # minute: 0–59
    r"(\*|[01]?\d|2[0-3])([,/\-]([01]?\d|2[0-3]))*",  # hour: 0–23
    r"(\*|[1-9]|[12]\d|3[01])([,/\-]([1-9]|[12]\d|3[01]))*",  # day: 1–31
    r"(\*|[1-9]|1[0-2])([,/\-]([1-9]|1[0-2]))*",  # month: 1–12
    r"(\*|[0-6])([,/\-][0-6])*",  # dow: 0–6
]


def _validate_cron_expression(expression: str) -> str:
    """Validate a 5-field cron expression.

    Accepts standard cron syntax with *, ranges (-), lists (,), and steps (/).

    Args:
        expression: The cron expression to validate.

    Returns:
        The validated expression (stripped).

    Raises:
        ValueError: If the expression is not valid 5-field cron syntax.
    """
    stripped = expression.strip()
    fields = stripped.split()
    if len(fields) != 5:
        msg = (
            f"schedule_cron must be a 5-field cron expression "
            f"(minute hour day month weekday), got {len(fields)} fields"
        )
        raise ValueError(msg)

    field_names = ["minute", "hour", "day-of-month", "month", "day-of-week"]
    for i, (field, pattern, name) in enumerate(
        zip(fields, _CRON_FIELD_PATTERNS, field_names)
    ):
        # Allow step notation: */N or range/step
        parts = field.split(",")
        for part in parts:
            # Handle step: e.g., */5, 1-30/2
            step_parts = part.split("/")
            if len(step_parts) > 2:
                msg = f"Invalid step expression in {name} field: '{part}'"
                raise ValueError(msg)
            base = step_parts[0]
            # Validate base is * or a valid number/range
            if base != "*":
                range_parts = base.split("-")
                for rp in range_parts:
                    if not rp.isdigit():
                        msg = (
                            f"Invalid value '{rp}' in {name} field: "
                            f"expected numeric value"
                        )
                        raise ValueError(msg)
            # Validate step is a positive integer if present
            if len(step_parts) == 2:
                if not step_parts[1].isdigit() or int(step_parts[1]) == 0:
                    msg = (
                        f"Invalid step value '{step_parts[1]}' in {name} "
                        f"field: must be a positive integer"
                    )
                    raise ValueError(msg)

    return stripped


class VigilanceSearchProfileCreateSchema(BaseModel):
    """Request schema for creating a vigilance search profile.

    Attributes:
        name: Profile name (1–200 characters).
        product_id: Foreign key to the associated Medical Product.
        search_terms: Product names, brand names, synonyms
            (1–50 entries, each 1–500 chars).
        mesh_terms: MeSH descriptors (0–30 entries, each 1–200 chars).
        adverse_event_keywords: Adverse event descriptors
            (1–50 entries, each 1–500 chars).
        device_identifiers: UDIs, catalog numbers, model numbers
            (0–20 entries, each 1–200 chars).
        exclusion_terms: Terms to exclude from results
            (0–30 entries, each 1–500 chars).
        source_ids: Source adapter identifiers to search
            (empty means all enabled sources).
        schedule_cron: Valid 5-field cron expression for scheduling.
    """

    name: str = Field(..., min_length=1, max_length=200)
    product_id: int
    search_terms: list[str] = Field(..., min_length=1, max_length=50)
    mesh_terms: list[str] | None = Field(None, max_length=30)
    adverse_event_keywords: list[str] = Field(..., min_length=1, max_length=50)
    device_identifiers: list[str] | None = Field(None, max_length=20)
    exclusion_terms: list[str] | None = Field(None, max_length=30)
    source_ids: list[str] | None = Field(default=None)
    schedule_cron: str = Field(..., min_length=9, max_length=100)

    @field_validator("search_terms")
    @classmethod
    def validate_search_terms(cls, v: list[str]) -> list[str]:
        """Validate search_terms: 1–50 entries, each 1–500 chars."""
        if len(v) < 1:
            msg = "search_terms must have at least 1 entry"
            raise ValueError(msg)
        if len(v) > 50:
            msg = "search_terms must have at most 50 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 500:
                msg = (
                    f"search_terms[{i}] must be 1–500 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("mesh_terms")
    @classmethod
    def validate_mesh_terms(cls, v: list[str] | None) -> list[str] | None:
        """Validate mesh_terms: 0–30 entries, each 1–200 chars."""
        if v is None:
            return v
        if len(v) > 30:
            msg = "mesh_terms must have at most 30 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 200:
                msg = (
                    f"mesh_terms[{i}] must be 1–200 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("adverse_event_keywords")
    @classmethod
    def validate_adverse_event_keywords(cls, v: list[str]) -> list[str]:
        """Validate adverse_event_keywords: 1–50 entries, each 1–500 chars."""
        if len(v) < 1:
            msg = "adverse_event_keywords must have at least 1 entry"
            raise ValueError(msg)
        if len(v) > 50:
            msg = "adverse_event_keywords must have at most 50 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 500:
                msg = (
                    f"adverse_event_keywords[{i}] must be 1–500 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("device_identifiers")
    @classmethod
    def validate_device_identifiers(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate device_identifiers: 0–20 entries, each 1–200 chars."""
        if v is None:
            return v
        if len(v) > 20:
            msg = "device_identifiers must have at most 20 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 200:
                msg = (
                    f"device_identifiers[{i}] must be 1–200 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("exclusion_terms")
    @classmethod
    def validate_exclusion_terms(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate exclusion_terms: 0–30 entries, each 1–500 chars."""
        if v is None:
            return v
        if len(v) > 30:
            msg = "exclusion_terms must have at most 30 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 500:
                msg = (
                    f"exclusion_terms[{i}] must be 1–500 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("schedule_cron")
    @classmethod
    def validate_schedule_cron(cls, v: str) -> str:
        """Validate schedule_cron is a valid 5-field cron expression."""
        return _validate_cron_expression(v)


class VigilanceSearchProfileUpdateSchema(BaseModel):
    """Request schema for updating an existing vigilance search profile.

    All fields are optional; only provided fields are updated.

    Attributes:
        name: Updated profile name (1–200 chars).
        search_terms: Updated search terms (1–50 entries, each 1–500 chars).
        mesh_terms: Updated MeSH terms (0–30 entries, each 1–200 chars).
        adverse_event_keywords: Updated adverse event keywords
            (1–50 entries, each 1–500 chars).
        device_identifiers: Updated device identifiers
            (0–20 entries, each 1–200 chars).
        exclusion_terms: Updated exclusion terms
            (0–30 entries, each 1–500 chars).
        source_ids: Updated source adapter identifiers.
        schedule_cron: Updated cron expression (5-field).
        status: Updated profile status.
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    search_terms: list[str] | None = Field(None, min_length=1, max_length=50)
    mesh_terms: list[str] | None = Field(None, max_length=30)
    adverse_event_keywords: list[str] | None = Field(
        None, min_length=1, max_length=50
    )
    device_identifiers: list[str] | None = Field(None, max_length=20)
    exclusion_terms: list[str] | None = Field(None, max_length=30)
    source_ids: list[str] | None = None
    schedule_cron: str | None = Field(None, min_length=9, max_length=100)
    status: ProfileStatusEnum | None = None

    @field_validator("search_terms")
    @classmethod
    def validate_search_terms(cls, v: list[str] | None) -> list[str] | None:
        """Validate search_terms: 1–50 entries, each 1–500 chars."""
        if v is None:
            return v
        if len(v) < 1:
            msg = "search_terms must have at least 1 entry"
            raise ValueError(msg)
        if len(v) > 50:
            msg = "search_terms must have at most 50 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 500:
                msg = (
                    f"search_terms[{i}] must be 1–500 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("mesh_terms")
    @classmethod
    def validate_mesh_terms(cls, v: list[str] | None) -> list[str] | None:
        """Validate mesh_terms: 0–30 entries, each 1–200 chars."""
        if v is None:
            return v
        if len(v) > 30:
            msg = "mesh_terms must have at most 30 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 200:
                msg = (
                    f"mesh_terms[{i}] must be 1–200 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("adverse_event_keywords")
    @classmethod
    def validate_adverse_event_keywords(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate adverse_event_keywords: 1–50 entries, each 1–500 chars."""
        if v is None:
            return v
        if len(v) < 1:
            msg = "adverse_event_keywords must have at least 1 entry"
            raise ValueError(msg)
        if len(v) > 50:
            msg = "adverse_event_keywords must have at most 50 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 500:
                msg = (
                    f"adverse_event_keywords[{i}] must be 1–500 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("device_identifiers")
    @classmethod
    def validate_device_identifiers(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate device_identifiers: 0–20 entries, each 1–200 chars."""
        if v is None:
            return v
        if len(v) > 20:
            msg = "device_identifiers must have at most 20 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 200:
                msg = (
                    f"device_identifiers[{i}] must be 1–200 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("exclusion_terms")
    @classmethod
    def validate_exclusion_terms(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate exclusion_terms: 0–30 entries, each 1–500 chars."""
        if v is None:
            return v
        if len(v) > 30:
            msg = "exclusion_terms must have at most 30 entries"
            raise ValueError(msg)
        for i, term in enumerate(v):
            if not 1 <= len(term) <= 500:
                msg = (
                    f"exclusion_terms[{i}] must be 1–500 characters, "
                    f"got {len(term)}"
                )
                raise ValueError(msg)
        return v

    @field_validator("schedule_cron")
    @classmethod
    def validate_schedule_cron(cls, v: str | None) -> str | None:
        """Validate schedule_cron is a valid 5-field cron expression."""
        if v is None:
            return v
        return _validate_cron_expression(v)


class VigilanceSearchProfileResponseSchema(BaseModel):
    """Response schema for a vigilance search profile.

    Attributes:
        id: Profile record ID.
        company_id: Company this profile belongs to.
        product_id: Associated medical product ID.
        name: Profile name.
        search_terms: Product names, brand names, synonyms.
        mesh_terms: MeSH descriptors.
        adverse_event_keywords: Adverse event descriptors.
        device_identifiers: UDIs, catalog numbers, model numbers.
        exclusion_terms: Terms excluded from results.
        source_ids: Source adapter identifiers to search.
        schedule_cron: Cron expression for scheduling.
        status: Current profile status.
        created_by: User ID who created the profile.
        created_at: When the profile was created.
        updated_at: When the profile was last modified.
    """

    id: int
    company_id: int
    product_id: int
    name: str
    search_terms: list[str]
    mesh_terms: list[str] | None = None
    adverse_event_keywords: list[str]
    device_identifiers: list[str] | None = None
    exclusion_terms: list[str] | None = None
    source_ids: list[str] | None = None
    schedule_cron: str
    status: ProfileStatusEnum
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
