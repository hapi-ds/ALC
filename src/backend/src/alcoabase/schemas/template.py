"""Pydantic request/response schemas for template endpoints.

Provides validated schemas for template creation, retrieval,
field type validation, and type-specific field configuration.

References:
    - Design doc Section 4: Template Service
    - Requirements 2–6: Rich field configuration
    - Requirements 3: Template JSON schema validation
"""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Field Configuration Schemas (Requirements 2–6)
# ---------------------------------------------------------------------------


class FieldConfigBase(BaseModel):
    """Base class for type-specific field configuration.

    All field config models inherit from this to share common
    serialization settings.
    """

    model_config = {"extra": "forbid"}


class TextFieldConfig(FieldConfigBase):
    """Configuration for Text fields.

    Attributes:
        min_length: Minimum character count (>= 0).
        max_length: Maximum character count (>= 1).
        placeholder: Placeholder hint text (max 200 chars).
        regex_pattern: Validation regex pattern (max 500 chars).
    """

    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=1)
    placeholder: str | None = Field(default=None, max_length=200)
    regex_pattern: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_min_max_length(self) -> "TextFieldConfig":
        """Ensure min_length <= max_length when both are specified."""
        if (
            self.min_length is not None
            and self.max_length is not None
            and self.min_length > self.max_length
        ):
            raise ValueError(
                "min_length must not exceed max_length"
            )
        return self

    @model_validator(mode="after")
    def validate_regex_pattern(self) -> "TextFieldConfig":
        """Ensure regex_pattern is syntactically valid."""
        if self.regex_pattern is not None:
            try:
                re.compile(self.regex_pattern)
            except re.error as e:
                raise ValueError(
                    f"regex_pattern is not a valid regular expression: {e}"
                )
        return self


class FloatFieldConfig(FieldConfigBase):
    """Configuration for Float fields.

    Attributes:
        decimal_precision: Number of decimal places (0-10).
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        unit_label: Unit of measurement label (max 50 chars).
    """

    decimal_precision: int | None = Field(default=None, ge=0, le=10)
    min_value: float | None = None
    max_value: float | None = None
    unit_label: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_min_max_value(self) -> "FloatFieldConfig":
        """Ensure min_value <= max_value when both are specified."""
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError(
                "min_value must not exceed max_value"
            )
        return self


class IntegerFieldConfig(FieldConfigBase):
    """Configuration for Integer fields.

    Attributes:
        min_value: Minimum allowed value.
        max_value: Maximum allowed value.
        step_size: Increment step (positive integer, default 1).
        unit_label: Unit of measurement label (max 50 chars).
    """

    min_value: int | None = None
    max_value: int | None = None
    step_size: int | None = Field(default=1, gt=0)
    unit_label: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_min_max_value(self) -> "IntegerFieldConfig":
        """Ensure min_value <= max_value when both are specified."""
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError(
                "min_value must not exceed max_value"
            )
        return self


class DateFieldConfig(FieldConfigBase):
    """Configuration for Date fields.

    Attributes:
        min_date: Earliest allowed date (ISO 8601 format).
        max_date: Latest allowed date (ISO 8601 format).
        date_format: Display format for the date field.
    """

    min_date: str | None = None
    max_date: str | None = None
    date_format: (
        Literal["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MMM-YYYY"] | None
    ) = None

    @model_validator(mode="after")
    def validate_dates(self) -> "DateFieldConfig":
        """Validate ISO 8601 format and ensure min_date <= max_date."""
        parsed_min: date | None = None
        parsed_max: date | None = None

        if self.min_date is not None:
            parsed_min = _parse_iso_date(self.min_date, "min_date")

        if self.max_date is not None:
            parsed_max = _parse_iso_date(self.max_date, "max_date")

        if (
            parsed_min is not None
            and parsed_max is not None
            and parsed_min > parsed_max
        ):
            raise ValueError(
                "min_date must not be later than max_date"
            )
        return self


class BooleanFieldConfig(FieldConfigBase):
    """Configuration for Boolean fields.

    Attributes:
        true_label: Custom label for the true/positive option.
        false_label: Custom label for the false/negative option.
    """

    true_label: str = Field(default="True", min_length=1, max_length=50)
    false_label: str = Field(default="False", min_length=1, max_length=50)


def _parse_iso_date(value: str, field_name: str) -> date:
    """Parse an ISO 8601 date string (YYYY-MM-DD).

    Args:
        value: The date string to parse.
        field_name: Name of the field for error messages.

    Returns:
        Parsed date object.

    Raises:
        ValueError: If the string is not a valid ISO 8601 date.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"{field_name} must be a valid ISO 8601 date (YYYY-MM-DD), "
            f"got: '{value}'"
        )


# ---------------------------------------------------------------------------
# Template Field and Schema Definitions
# ---------------------------------------------------------------------------


class TemplateFieldCreate(BaseModel):
    """Schema for a single field in the template JSON schema.

    Attributes:
        label: Human-readable field label.
        type: Data type constraint for the field.
    """

    label: str = Field(..., min_length=1, max_length=200)
    type: Literal["Text", "Float", "Integer", "Date", "Boolean"] = Field(
        ..., description="Field data type."
    )


class TemplateSchemaCreate(BaseModel):
    """Schema for the template JSON schema structure.

    Attributes:
        fields: List of field definitions.
    """

    fields: list[TemplateFieldCreate] = Field(
        ..., min_length=1, description="List of template field definitions."
    )


# ---------------------------------------------------------------------------
# Enhanced Template Schema — Discriminated Union (Requirements 18.1–18.4)
# ---------------------------------------------------------------------------


class SerializedFieldElement(BaseModel):
    """Serialized representation of a field element in the enhanced schema.

    Uses element_type="field" as the discriminator value for the
    discriminated union in EnhancedTemplateSchema.

    Attributes:
        element_type: Discriminator literal, always "field".
        label: Human-readable field label (1-200 chars).
        type: Field data type (Text, Float, Integer, Date, Boolean).
        required: Whether the field is required for data collection.
        help_text: Optional guidance text for data collectors (max 500 chars).
        default_value: Optional pre-filled value (validated per type in service layer).
        config: Type-specific configuration dict (validated per type in service layer).
    """

    element_type: Literal["field"]
    label: str = Field(..., min_length=1, max_length=200)
    type: Literal["Text", "Float", "Integer", "Date", "Boolean"]
    required: bool = False
    help_text: str | None = Field(default=None, max_length=500)
    default_value: str | None = None
    config: dict | None = None


class SerializedContentBlockElement(BaseModel):
    """Serialized representation of a content block element in the enhanced schema.

    Uses element_type="content_block" as the discriminator value for the
    discriminated union in EnhancedTemplateSchema.

    Attributes:
        element_type: Discriminator literal, always "content_block".
        content_type: The specific content block type.
        text: Text content for headings and paragraphs (null for dividers).
    """

    element_type: Literal["content_block"]
    content_type: Literal[
        "heading_h1", "heading_h2", "heading_h3", "paragraph", "divider"
    ]
    text: str | None = None


class EnhancedTemplateSchema(BaseModel):
    """Enhanced template schema supporting interleaved fields and content blocks.

    Uses a discriminated union on the `element_type` field to distinguish
    between field elements and content block elements. The elements array
    preserves ordering for rendering.

    Attributes:
        elements: Ordered list of field and content block elements.
            Must contain at least one element.
    """

    elements: list[SerializedFieldElement | SerializedContentBlockElement] = Field(
        ..., min_length=1
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "EnhancedTemplateSchema":
        """Ensure at least one field element exists for data collection."""
        has_field = any(
            elem.element_type == "field" for elem in self.elements
        )
        if not has_field:
            raise ValueError(
                "Template must contain at least one field element"
            )
        return self


# ---------------------------------------------------------------------------
# Template Create — Backward Compatible (supports both fields and elements)
# ---------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    """Request schema for creating a new template.

    Supports both the legacy format (json_schema with `fields` key) and
    the enhanced format (json_schema with `elements` key) for backward
    compatibility.

    Attributes:
        name: Template name (1-500 chars).
        json_schema: Template schema — either TemplateSchemaCreate (legacy)
            or EnhancedTemplateSchema (enhanced).
        user_id: ID of the creating user.
    """

    name: str = Field(..., min_length=1, max_length=500)
    json_schema: TemplateSchemaCreate | EnhancedTemplateSchema = Field(
        ..., description="Template schema with field definitions."
    )
    user_id: int = Field(default=1, description="ID of the creating user.")


class TemplateUpdate(BaseModel):
    """Request schema for updating a template.

    Attributes:
        name: Optional new template name.
        json_schema: Optional new JSON schema (supports both legacy and enhanced).
    """

    name: str | None = Field(default=None, min_length=1, max_length=500)
    json_schema: TemplateSchemaCreate | EnhancedTemplateSchema | None = None


# ---------------------------------------------------------------------------
# Version Schemas (Requirements 10.3, 10.5, 10.6)
# ---------------------------------------------------------------------------


class VersionCreate(BaseModel):
    """Request schema for creating a new template version.

    Attributes:
        json_schema: Enhanced template schema with elements array.
        user_id: ID of the user creating the version.
    """

    json_schema: EnhancedTemplateSchema
    user_id: int = Field(default=1, description="ID of the user creating the version.")


class TemplateVersionFieldResponse(BaseModel):
    """Response schema for a single field/element within a template version.

    Attributes:
        id: Field primary key.
        field_uuid: Unique field identifier (FLD-XXXXXXXX or CB-XXXXXXXX format).
        field_type: Data type (Text, Float, Integer, Date, Boolean) or content block type.
        field_label: Human-readable label or content text.
        field_order: Display order within the version.
        element_type: Discriminator — "field" or "content_block".
        content_type: Content block subtype (null for fields).
        text_content: Text content for headings/paragraphs (null for fields/dividers).
        config: Type-specific configuration dict (null for content blocks).
        required: Whether the field is required (always False for content blocks).
        help_text: Optional guidance text.
        default_value: Optional pre-filled value.
    """

    id: int
    field_uuid: str
    field_type: str
    field_label: str
    field_order: int
    element_type: str
    content_type: str | None = None
    text_content: str | None = None
    config: dict | None = None
    required: bool = False
    help_text: str | None = None
    default_value: str | None = None

    model_config = {"from_attributes": True}


class TemplateVersionResponse(BaseModel):
    """Response schema for a template version with metadata and fields.

    Attributes:
        id: Version primary key.
        version_number: Sequential version number (1, 2, 3...).
        document_uuid: Parent template's Document_UUID.
        json_schema: Complete schema snapshot as stored.
        status: Version status (always "ReadOnly" after creation).
        is_active: Whether this is the currently active version.
        created_by: ID of the user who created the version.
        change_reason: ALCOA+ audit reason for version creation.
        created_at: ISO 8601 timestamp of version creation.
        fields: List of version fields/elements with assigned UUIDs.
    """

    id: int
    version_number: int
    document_uuid: str
    json_schema: dict
    status: str
    is_active: bool
    created_by: int
    change_reason: str
    created_at: str
    fields: list[TemplateVersionFieldResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}

    @field_validator("created_at", mode="before")
    @classmethod
    def coerce_created_at(cls, v: object) -> str:
        """Convert datetime objects to ISO 8601 strings."""
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)


class TemplateFieldResponse(BaseModel):
    """Response schema for a template field.

    Attributes:
        id: Field primary key.
        field_uuid: Unique field identifier (FLD-XXXXXXXX format).
        field_type: Data type (Text, Float, Integer, Date, Boolean).
        field_label: Human-readable label.
        field_order: Display order within the template.
    """

    id: int
    field_uuid: str
    field_type: str
    field_label: str
    field_order: int

    model_config = {"from_attributes": True}


class TemplateResponse(BaseModel):
    """Response schema for a template with metadata and fields.

    Attributes:
        id: Template primary key.
        document_uuid: Unique identifier in YYYY-NNNNN format.
        name: Template name.
        json_schema: Template field definitions.
        status: Template lifecycle status (Draft or ReadOnly).
        created_by: ID of the creating user.
        fields: List of template fields with assigned Field-UUIDs.
    """

    id: int
    document_uuid: str
    name: str
    json_schema: dict
    status: str
    created_by: int
    fields: list[TemplateFieldResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}
