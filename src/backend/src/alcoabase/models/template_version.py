"""TemplateVersion and TemplateVersionField models for template versioning.

This module defines the versioning models that support immutable version
snapshots of template schemas. Each version captures the complete template
state at a point in time, enabling ALCOA+ audit trail compliance.

References:
    - Field-UUID format: FLD-XXXXXXXX (prefix + 8 hex chars from uuid4)
    - Content block UUID format: CB-XXXXXXXX (prefix + 8 hex chars from uuid4)
    - Version immutability: Once created, version schema cannot be modified
    - ALCOA+ "Original" principle: versions preserve the original template state
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base


class TemplateVersion(Base):
    """Immutable version snapshot of a template schema.

    Each version captures the complete template state (fields, content blocks,
    configurations) at the time of creation. Versions are immutable once
    created to satisfy ALCOA+ "Original" data integrity requirements.
    
    Note: Does NOT use AuditMixin because versions are themselves immutable
    audit records — tracking changes to an immutable record is unnecessary.

    Attributes:
        id: Primary key.
        template_id: Foreign key to the parent template.
        version_number: Sequential version number (1, 2, 3...).
        document_uuid: Inherited from parent template for convenience.
        json_schema: Complete JSON schema snapshot of the template.
        status: Version status (always "ReadOnly" after creation).
        is_active: Whether this is the current active version for data collection.
        created_by: Foreign key to the user who created this version.
        change_reason: ALCOA+ audit reason for creating this version.
        created_at: Timestamp of version creation.
        template: Back-reference to the parent Template.
        fields: One-to-many relationship to TemplateVersionField.
    """

    __tablename__ = "template_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    version_number: Mapped[int] = mapped_column()
    document_uuid: Mapped[str] = mapped_column(String(12))
    json_schema: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="ReadOnly")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    change_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    template: Mapped["Template"] = relationship(back_populates="versions")
    fields: Mapped[list["TemplateVersionField"]] = relationship(
        back_populates="version", order_by="TemplateVersionField.field_order"
    )


class TemplateVersionField(Base):
    """Individual element (field or content block) within a template version.

    Stores the complete configuration of each element at the time the
    version was created. Elements can be either data-collecting fields
    (element_type="field") or static content blocks (element_type="content_block").

    Attributes:
        id: Primary key.
        version_id: Foreign key to the parent TemplateVersion.
        field_uuid: Unique field identifier (FLD-XXXXXXXX or CB-XXXXXXXX).
        field_type: Data type for fields (Text, Float, Integer, Date, Boolean).
        field_label: Human-readable label displayed in the form.
        field_order: Display order within the template version.
        element_type: Discriminator ("field" or "content_block").
        content_type: Content block subtype (heading_h1, heading_h2, etc.).
        text_content: Text content for headers and paragraphs.
        config: JSONB column storing type-specific field configuration.
        required: Whether the field is required for data collection.
        help_text: Optional help text displayed below the field label.
        default_value: Optional pre-filled default value for the field.
        version: Back-reference to the parent TemplateVersion.
    """

    __tablename__ = "template_version_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("template_versions.id")
    )
    field_uuid: Mapped[str] = mapped_column(String(40))
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

    version: Mapped["TemplateVersion"] = relationship(back_populates="fields")
