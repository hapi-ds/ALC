"""Report and ReportFieldValue models for extracted PDF data storage.

This module defines the models that store data extracted from completed
offline PDFs. Reports link back to their source template and contain
individual field values mapped by Field-UUID.

References:
    - PDF Extractor: Reads completed PDFs and maps field values to database columns
    - Field-UUID: Used as AcroForm field identifier for deterministic extraction
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class Report(Base, AuditMixin):
    """Report model for extracted PDF data.

    A Report represents a completed offline PDF that has been uploaded
    and processed by the PDF Extractor. It links to the source template
    and contains extracted field values.

    Attributes:
        id: Primary key.
        document_uuid: Reference to the document's UUID.
        template_id: Foreign key to the source template.
        uploaded_by: Foreign key to the uploading user.
        uploaded_at: Server-side UTC timestamp of upload.
        status: Report processing status (e.g., "Extracted", "Validated").
        field_values: One-to-many relationship to ReportFieldValue.
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(50))
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))

    field_values: Mapped[list["ReportFieldValue"]] = relationship(
        back_populates="report"
    )


class ReportFieldValue(Base):
    """Individual field value extracted from a completed PDF.

    Each value is mapped by Field-UUID to ensure deterministic
    correspondence between PDF form fields and database columns.

    Attributes:
        id: Primary key.
        report_id: Foreign key to the parent report.
        field_uuid: Field-UUID identifying which template field this value belongs to.
        value: Extracted text value from the PDF form field.
        validated: Whether the value passed type validation.
        report: Back-reference to the parent Report.
    """

    __tablename__ = "report_field_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"))
    field_uuid: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    validated: Mapped[bool] = mapped_column(default=False)

    report: Mapped["Report"] = relationship(back_populates="field_values")
