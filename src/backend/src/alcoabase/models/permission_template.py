"""Permission template model for document-type-specific RBAC overrides.

This module defines the PermissionTemplate model that allows document
administrators to create reusable permission configurations for specific
document types. Templates define role-action mappings that override or
restrict base role permissions using a "most restrictive wins" policy.

References:
    - Phase 6.1 design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements: 4.1, 4.2, 4.3, 4.4
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company
    from alcoabase.models.user import User


class PermissionTemplate(Base, AuditMixin):
    """Reusable permission template for document types.

    Defines role-action mappings that override or restrict base role
    permissions for documents of a specific type. Uses "most restrictive
    wins" policy when evaluating access.

    The role_permissions field stores a JSON object mapping role names
    to their permitted actions on the template's document type:
    {
        "system_admin": ["read", "write", "approve"],
        "doc_admin": ["read", "write", "approve"],
        "member": ["read"],
        "viewer": ["read"]
    }

    Attributes:
        id: Primary key.
        name: Template name (unique within company).
        description: Human-readable description.
        document_type: The document type this template governs.
        role_permissions: JSON mapping role names to permitted actions.
        company_id: FK to company.
        is_default: Whether this is a system-seeded default template.
        created_by: FK to user who created the template.
        created_at: Server-side UTC timestamp.
        company: Relationship to the Company model.
        creator: Relationship to the User who created this template.
    """

    __tablename__ = "permission_templates"
    __table_args__ = (
        UniqueConstraint(
            "name", "company_id",
            name="uq_permission_templates_name_company",
        ),
        Index(
            "ix_permission_templates_company_doctype",
            "company_id",
            "document_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str] = mapped_column(String(100))
    role_permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    company: Mapped["Company"] = relationship()
    creator: Mapped["User"] = relationship()
