"""SQLAlchemy model for Literature Traceability Links (Phase 9.6).

Defines:
- LiteratureTraceabilityLink: Links internalized literature documents to
  requirements or test cases in the Traceability Matrix.

All models follow existing project patterns:
- Inherit from Base (alcoabase.database)
- Use mapped_column with type annotations (SQLAlchemy 2.0 style)
- Include proper indexes and constraints

References:
    - Requirements 6.1, 6.2, 6.3, 6.4
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class LiteratureTraceabilityLink(Base):
    """Links internalized documents to requirements or test cases.

    Represents a directed evidence link from a literature document to
    a requirement or test case in the Traceability Matrix, with
    link_method="literature_evidence" and confidence=1.0 for manual links.

    Attributes:
        id: Primary key.
        document_id: FK to the internalized Document.
        target_type: Type of the target entity ("requirement" or "test_case").
        target_id: ID of the target requirement or test case.
        rationale: Optional justification for the link.
        link_method: Detection method used ("literature_evidence").
        link_confidence: Confidence score (1.0 for manual links).
        created_by: FK to the user who created the link.
        company_id: FK to companies table (tenant isolation).
        created_at: Link creation timestamp.
    """

    __tablename__ = "literature_traceability_links"

    __table_args__ = (
        Index(
            "ix_lit_trace_link_company_document",
            "company_id",
            "document_id",
        ),
        Index(
            "ix_lit_trace_link_company_target",
            "company_id",
            "target_type",
            "target_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[int] = mapped_column(Integer)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_method: Mapped[str] = mapped_column(
        String(50), default="literature_evidence"
    )
    link_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
