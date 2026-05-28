"""Template and TemplateField models for report template management.

This module defines the template models that support the deterministic
PDF protocol-to-report mapping system. Templates define JSON schemas
for fillable PDF forms, with each field receiving a unique Field-UUID.

References:
    - Field-UUID format: FLD-XXXXXXXX (prefix + 8 hex chars from uuid4)
    - Content block UUID format: CB-XXXXXXXX (prefix + 8 hex chars from uuid4)
    - Template immutability: Once status is "ReadOnly", the schema cannot be modified
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.template_version import TemplateVersion


class Template(Base, AuditMixin):
    """Report template model with JSON schema and immutability enforcement.

    Templates define the structure of fillable PDF forms. Once saved with
    status "ReadOnly", the JSON schema becomes immutable to ensure
    deterministic PDF generation and extraction.

    Attributes:
        id: Primary key.
        document_uuid: Unique identifier in YYYY-NNNNN format.
        name: Template name (max 500 chars).
        json_schema: JSON object defining the form structure and field types.
        status: Template lifecycle status (Draft or ReadOnly).
        created_by: Foreign key to the creating user.
        fields: One-to-many relationship to TemplateField.
        versions: One-to-many relationship to TemplateVersion.
    """

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_uuid: Mapped[str] = mapped_column(
        String(12), unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(500))
    json_schema: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    is_demo_data: Mapped[bool] = mapped_column(default=False)

    fields: Mapped[list["TemplateField"]] = relationship(
        back_populates="template"
    )
    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template",
        order_by="TemplateVersion.version_number",
    )


class TemplateField(Base):
    """Individual field definition within a template.

    Each field has a unique Field-UUID that serves as the AcroForm field
    name in generated PDFs, enabling deterministic extraction. Fields can
    be data-collecting inputs (element_type="field") or static content
    blocks (element_type="content_block").

    Attributes:
        id: Primary key.
        template_id: Foreign key to the parent template.
        field_uuid: Unique field identifier (format: FLD-XXXXXXXX or CB-XXXXXXXX).
        field_type: Data type (Text, Float, Integer, Date, Boolean).
        field_label: Human-readable label displayed in the form.
        field_order: Display order within the template.
        element_type: Discriminator ("field" or "content_block").
        content_type: Content block subtype (heading_h1, heading_h2, etc.).
        text_content: Text content for headers and paragraphs.
        config: JSONB column storing type-specific field configuration.
        required: Whether the field is required for data collection.
        help_text: Optional help text displayed below the field label.
        default_value: Optional pre-filled default value for the field.
        template: Back-reference to the parent Template.
    """

    __tablename__ = "template_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    field_uuid: Mapped[str] = mapped_column(
        String(40), unique=True, index=True
    )
    field_type: Mapped[str] = mapped_column(String(20))
    field_label: Mapped[str] = mapped_column(String(200))
    field_order: Mapped[int] = mapped_column()
    element_type: Mapped[str] = mapped_column(String(20), default="field")
    content_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    required: Mapped[bool] = mapped_column(default=False)
    help_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped["Template"] = relationship(back_populates="fields")
