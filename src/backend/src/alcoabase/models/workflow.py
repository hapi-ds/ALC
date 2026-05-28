"""Workflow models for BPMN-based document lifecycle management.

This module defines the WorkflowDefinition and DocumentState models
that support tag-based workflow binding and state transition enforcement.

References:
    - SpiffWorkflow: BPMN execution engine
    - Tag-based binding: Each workflow is bound to a document tag (e.g., "SOP", "Report")
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class WorkflowDefinition(Base, AuditMixin):
    """BPMN workflow definition bound to a document tag.

    Each workflow defines the state machine for a specific document type.
    The document_tag field creates a one-to-one binding between a tag
    (e.g., "SOP") and its lifecycle workflow.

    Attributes:
        id: Primary key.
        name: Human-readable workflow name.
        document_tag: Unique tag binding (e.g., "SOP", "Report").
        bpmn_xml: BPMN 2.0 XML definition of the workflow.
        signature_required_transitions: JSON list of transitions requiring
            PAdES signature (e.g., ["Review→Approved"]).
        training_trigger_transitions: JSON list of transitions that trigger
            training assignment (e.g., ["Approved→InTraining"]).
        is_active: Whether this workflow is currently active.
        risk_level: Risk classification for the workflow (low, medium, high, critical).
        auto_assignment_config: JSON config for AI-driven reviewer suggestions.
        current_version: Current version number of the workflow definition.
        created_by: Foreign key to the creating user.
    """

    __tablename__ = "workflow_definitions"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="risk_level",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    document_tag: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    bpmn_xml: Mapped[str] = mapped_column(Text)
    signature_required_transitions: Mapped[list] = mapped_column(
        JSON, default=list
    )
    training_trigger_transitions: Mapped[list] = mapped_column(
        JSON, default=list
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    is_demo_data: Mapped[bool] = mapped_column(default=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    auto_assignment_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    current_version: Mapped[int] = mapped_column(default=1)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))


class WorkflowVersion(Base, AuditMixin):
    """Immutable version record for a workflow definition.

    Each structural change (bpmn_xml, transitions) creates a new version.
    Metadata-only changes (name, is_active) do not create versions.

    Attributes:
        id: Primary key.
        workflow_id: Foreign key to the parent workflow definition.
        version_number: Sequential version number within the workflow.
        bpmn_xml: BPMN 2.0 XML snapshot at this version.
        name: Workflow name at this version.
        document_tag: Document tag at this version.
        risk_level: Risk classification at this version.
        signature_required_transitions: JSON list of signature-required transitions.
        training_trigger_transitions: JSON list of training-trigger transitions.
        auto_assignment_config: JSON config for AI-driven reviewer suggestions.
        created_by: Foreign key to the user who created this version.
        created_at: Server-side UTC timestamp of version creation.
        change_reason: Human-readable reason for the change.
        company_id: Foreign key to the owning company (tenant).
    """

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "version_number", name="uq_workflow_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id"), index=True
    )
    version_number: Mapped[int] = mapped_column()
    bpmn_xml: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(200))
    document_tag: Mapped[str] = mapped_column(String(100))
    risk_level: Mapped[str] = mapped_column(String(20))
    signature_required_transitions: Mapped[list] = mapped_column(
        JSON, default=list
    )
    training_trigger_transitions: Mapped[list] = mapped_column(
        JSON, default=list
    )
    auto_assignment_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    change_reason: Mapped[str] = mapped_column(String(500))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))


class DocumentState(Base, AuditMixin):
    """Current workflow state for a document.

    Tracks the current position of a document within its assigned
    BPMN workflow. Updated on each valid state transition.

    Attributes:
        id: Primary key.
        document_id: Foreign key to the document.
        current_state: Current workflow state (e.g., "Draft", "Review").
        workflow_id: Foreign key to the active workflow definition.
        updated_at: Server-side UTC timestamp of last state change.
        updated_by: Foreign key to the user who triggered the transition.
    """

    __tablename__ = "document_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    current_state: Mapped[str] = mapped_column(String(50))
    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
