"""Pydantic request/response schemas for template endpoints.

Provides validated schemas for template creation, retrieval,
and field type validation.

References:
    - Design doc Section 4: Template Service
    - Requirements 3: Template JSON schema validation
"""

from typing import Literal

from pydantic import BaseModel, Field


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


class TemplateCreate(BaseModel):
    """Request schema for creating a new template.

    Attributes:
        name: Template name (1-500 chars).
        json_schema: Template field definitions.
        user_id: ID of the creating user.
    """

    name: str = Field(..., min_length=1, max_length=500)
    json_schema: TemplateSchemaCreate = Field(
        ..., description="Template schema with field definitions."
    )
    user_id: int = Field(default=1, description="ID of the creating user.")


class TemplateUpdate(BaseModel):
    """Request schema for updating a template.

    Attributes:
        name: Optional new template name.
        json_schema: Optional new JSON schema.
    """

    name: str | None = Field(default=None, min_length=1, max_length=500)
    json_schema: TemplateSchemaCreate | None = None


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
