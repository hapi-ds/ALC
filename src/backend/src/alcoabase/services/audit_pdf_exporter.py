"""Audit PDF Exporter service for regulatory-compliant PDF generation.

Generates PDF documents from filtered audit trail data using ReportLab.
Supports both synchronous (≤10,000 events) and asynchronous (>10,000 events)
export modes. Async exports are dispatched as Celery tasks.

The generated PDFs are formatted for FDA/EMA regulatory submissions with:
- A4 page size, portrait orientation
- Fixed-width font (Courier) for tabular data
- Table-based layout with visible row separators
- Column headers repeated on each page
- Header with company name, export timestamp, filters, event count, user
- Footer with page number, total pages, generation timestamp

References:
    - Design doc: Components > AuditPDFExporter
    - Requirements 7.1–7.10: PDF Export for Regulatory Submissions
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from alcoabase.schemas.audit_trail import (
    AuditEvent,
    AuditTrailFilters,
    ExportMetadata,
    ExportStatusResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# PDF layout constants
_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_LEFT = 1.5 * cm
_MARGIN_RIGHT = 1.5 * cm
_MARGIN_TOP = 2.5 * cm
_MARGIN_BOTTOM = 2.0 * cm
_CHANGE_REASON_MAX_LENGTH = 500


class AuditPDFExporter:
    """Service for generating regulatory-compliant PDF exports of audit events.

    Provides synchronous PDF generation from a list of events, as well as
    async export dispatch via Celery for large datasets (>10,000 events).
    """

    def generate_pdf(
        self,
        events: list[AuditEvent],
        metadata: ExportMetadata,
    ) -> bytes:
        """Generate a PDF document from audit events.

        Creates a regulatory-compliant PDF with header metadata, tabular
        event data using fixed-width font, and page footers.

        Args:
            events: List of audit events to include in the PDF.
            metadata: Export metadata for the PDF header.

        Returns:
            The generated PDF document as bytes.
        """
        buffer = io.BytesIO()

        # Build the PDF document
        doc = _AuditPDFDocument(buffer, metadata)
        elements = doc.build_elements(events, metadata)
        doc.multiBuild(elements)

        return buffer.getvalue()

    async def export_sync(
        self,
        session: "AsyncSession",
        company_id: int,
        filters: AuditTrailFilters | None,
        search_query: str | None,
        requesting_user_id: int,
    ) -> bytes:
        """Generate PDF synchronously by fetching events and building PDF.

        Fetches all matching events via AuditTrailService, builds metadata,
        and generates the PDF in-process.

        Args:
            session: Active async database session.
            company_id: Company ID to scope the export.
            filters: Optional filter criteria for the export.
            search_query: Optional search query for the export.
            requesting_user_id: ID of the user requesting the export.

        Returns:
            The generated PDF document as bytes.

        Raises:
            ValueError: If no events match the current filters.
        """
        from sqlalchemy import select

        from alcoabase.models.company import Company
        from alcoabase.models.user import User
        from alcoabase.services.audit_trail_service import AuditTrailService

        audit_service = AuditTrailService()
        effective_filters = filters or AuditTrailFilters()

        # Fetch all matching events (iterate through all pages)
        all_events: list[AuditEvent] = []
        cursor: str | None = None

        while True:
            page = await audit_service.list_events(
                session=session,
                company_id=company_id,
                filters=effective_filters,
                search_query=search_query,
                cursor=cursor,
                page_size=200,
            )
            all_events.extend(page.events)
            cursor = page.next_cursor
            if cursor is None:
                break

        if len(all_events) == 0:
            raise ValueError("No events match the current filters")

        # Resolve company name
        company_result = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_result.scalar_one_or_none()
        company_name = company.display_name if company else f"Company {company_id}"

        # Resolve requesting user name
        user_result = await session.execute(
            select(User).where(User.id == requesting_user_id)
        )
        user = user_result.scalar_one_or_none()
        requesting_user_name = user.full_name if user else f"User {requesting_user_id}"

        # Build metadata
        export_metadata = ExportMetadata(
            company_name=company_name,
            export_timestamp=datetime.now(timezone.utc),
            filters_applied=effective_filters,
            total_event_count=len(all_events),
            requesting_user_name=requesting_user_name,
        )

        # Generate and return PDF
        return self.generate_pdf(all_events, export_metadata)

    async def export_async(
        self,
        session: "AsyncSession",
        company_id: int,
        filters: AuditTrailFilters | None,
        search_query: str | None,
        requesting_user_id: int,
    ) -> str:
        """Dispatch an asynchronous PDF export via Celery.

        Generates a job_id and dispatches a Celery task to handle the
        export in the background.

        Args:
            session: Active async database session (unused, kept for interface consistency).
            company_id: Company ID to scope the export.
            filters: Optional filter criteria for the export.
            search_query: Optional search query for the export.
            requesting_user_id: ID of the user requesting the export.

        Returns:
            The job_id (UUID string) for tracking the export status.
        """
        from alcoabase.tasks.audit_export_tasks import export_audit_pdf_task

        job_id = str(uuid.uuid4())

        # Serialize filters to dict for Celery JSON serialization
        filters_dict = filters.model_dump(mode="json") if filters else None

        export_audit_pdf_task.apply_async(
            kwargs={
                "job_id": job_id,
                "company_id": company_id,
                "filters": filters_dict,
                "search_query": search_query,
                "requesting_user_id": requesting_user_id,
            },
            task_id=job_id,
        )

        return job_id

    def get_export_status(self, job_id: str) -> ExportStatusResponse:
        """Check the status of an async export job.

        Queries the Celery result backend for the task state and returns
        a structured status response.

        Args:
            job_id: The UUID of the export job to check.

        Returns:
            ExportStatusResponse with current status and download_url if completed.
        """
        from celery.result import AsyncResult

        from alcoabase.tasks.celery_app import celery_app

        result = AsyncResult(job_id, app=celery_app)

        if result.state == "PENDING":
            return ExportStatusResponse(
                job_id=job_id,
                status="pending",
            )
        elif result.state == "STARTED":
            return ExportStatusResponse(
                job_id=job_id,
                status="processing",
            )
        elif result.state == "SUCCESS":
            task_result = result.result or {}
            if isinstance(task_result, dict) and task_result.get("status") == "completed":
                return ExportStatusResponse(
                    job_id=job_id,
                    status="completed",
                    download_url=task_result.get("download_url"),
                )
            elif isinstance(task_result, dict) and task_result.get("status") == "failed":
                return ExportStatusResponse(
                    job_id=job_id,
                    status="failed",
                    error_message=task_result.get("error_message"),
                )
            return ExportStatusResponse(
                job_id=job_id,
                status="completed",
                download_url=task_result.get("download_url") if isinstance(task_result, dict) else None,
            )
        elif result.state == "FAILURE":
            return ExportStatusResponse(
                job_id=job_id,
                status="failed",
                error_message=str(result.result) if result.result else "Export failed",
            )
        else:
            # RETRY or other states
            return ExportStatusResponse(
                job_id=job_id,
                status="processing",
            )


# ---------------------------------------------------------------------------
# Internal PDF document builder
# ---------------------------------------------------------------------------


def _truncate_change_reason(text: str | None) -> str:
    """Truncate change_reason to 500 chars with ellipsis if needed.

    Args:
        text: The change_reason text to truncate.

    Returns:
        Truncated text with "..." appended if it exceeds 500 characters,
        or "(none)" if the text is None/empty.
    """
    if not text:
        return "(none)"
    if len(text) > _CHANGE_REASON_MAX_LENGTH:
        return text[:_CHANGE_REASON_MAX_LENGTH] + "..."
    return text


def _format_filters_summary(filters: AuditTrailFilters) -> str:
    """Format applied filters into a human-readable summary string.

    Args:
        filters: The filter criteria to summarize.

    Returns:
        A comma-separated summary of active filters, or "None" if no filters.
    """
    parts: list[str] = []

    if filters.user_id is not None:
        parts.append(f"User ID: {filters.user_id}")
    if filters.date_start is not None:
        parts.append(f"From: {filters.date_start.strftime('%Y-%m-%d %H:%M UTC')}")
    if filters.date_end is not None:
        parts.append(f"To: {filters.date_end.strftime('%Y-%m-%d %H:%M UTC')}")
    if filters.record_type is not None:
        parts.append(f"Record Type: {filters.record_type}")
    if filters.operation_type is not None:
        parts.append(f"Operation: {filters.operation_type}")

    return ", ".join(parts) if parts else "None"


class _AuditPDFDocument(BaseDocTemplate):
    """Custom PDF document template for audit trail exports.

    Handles page headers, footers, and multi-page table layout with
    repeated column headers.
    """

    def __init__(
        self,
        buffer: io.BytesIO,
        metadata: ExportMetadata,
    ) -> None:
        """Initialize the audit PDF document.

        Args:
            buffer: BytesIO buffer to write the PDF into.
            metadata: Export metadata for header/footer rendering.
        """
        super().__init__(
            buffer,
            pagesize=A4,
            leftMargin=_MARGIN_LEFT,
            rightMargin=_MARGIN_RIGHT,
            topMargin=_MARGIN_TOP,
            bottomMargin=_MARGIN_BOTTOM,
            title="Audit Trail Export",
            author="AlcoaBase",
        )
        self._metadata = metadata
        self._generation_timestamp = datetime.now(timezone.utc)

        # Define page template with header/footer
        frame = Frame(
            _MARGIN_LEFT,
            _MARGIN_BOTTOM,
            _PAGE_WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT,
            _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM,
            id="main_frame",
        )
        page_template = PageTemplate(
            id="audit_page",
            frames=[frame],
            onPage=self._draw_header_footer,
        )
        self.addPageTemplates([page_template])

    def _draw_header_footer(self, canvas, doc) -> None:
        """Draw header and footer on each page.

        Header: company name, export date/time (UTC)
        Footer: page number, total pages, generation timestamp

        Args:
            canvas: The ReportLab canvas for the current page.
            doc: The document template instance.
        """
        canvas.saveState()

        # --- Header ---
        canvas.setFont("Courier-Bold", 9)
        canvas.drawString(
            _MARGIN_LEFT,
            _PAGE_HEIGHT - 1.2 * cm,
            f"{self._metadata.company_name} — Audit Trail Export",
        )
        canvas.setFont("Courier", 8)
        canvas.drawString(
            _MARGIN_LEFT,
            _PAGE_HEIGHT - 1.7 * cm,
            f"Exported: {self._metadata.export_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        )

        # --- Footer ---
        canvas.setFont("Courier", 8)
        # Page number (uses placeholder for total pages)
        page_text = f"Page {doc.page}"
        canvas.drawString(_MARGIN_LEFT, 1.0 * cm, page_text)

        # Generation timestamp on the right
        gen_text = f"Generated: {self._generation_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        canvas.drawRightString(
            _PAGE_WIDTH - _MARGIN_RIGHT, 1.0 * cm, gen_text
        )

        canvas.restoreState()

    def _draw_header_footer_with_total(self, canvas, doc) -> None:
        """Draw header and footer with total page count (used in afterFlowable).

        This is called during the second pass of multiBuild to render
        the total page count in the footer.

        Args:
            canvas: The ReportLab canvas for the current page.
            doc: The document template instance.
        """
        canvas.saveState()

        # --- Header ---
        canvas.setFont("Courier-Bold", 9)
        canvas.drawString(
            _MARGIN_LEFT,
            _PAGE_HEIGHT - 1.2 * cm,
            f"{self._metadata.company_name} — Audit Trail Export",
        )
        canvas.setFont("Courier", 8)
        canvas.drawString(
            _MARGIN_LEFT,
            _PAGE_HEIGHT - 1.7 * cm,
            f"Exported: {self._metadata.export_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        )

        # --- Footer ---
        canvas.setFont("Courier", 8)
        page_text = f"Page {doc.page} of {self.total_pages}"
        canvas.drawString(_MARGIN_LEFT, 1.0 * cm, page_text)

        gen_text = f"Generated: {self._generation_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        canvas.drawRightString(
            _PAGE_WIDTH - _MARGIN_RIGHT, 1.0 * cm, gen_text
        )

        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:
        """Track page count after each flowable is rendered."""
        pass

    def multiBuild(self, flowables, **kwargs) -> None:
        """Build PDF with two passes to get total page count.

        First pass determines total pages, second pass renders with
        "Page X of Y" in the footer.
        """
        # First pass: count pages
        self._is_first_pass = True
        super().multiBuild(flowables, **kwargs)
        self.total_pages = self.page

        # Update page template to use total pages in footer
        frame = Frame(
            _MARGIN_LEFT,
            _MARGIN_BOTTOM,
            _PAGE_WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT,
            _PAGE_HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM,
            id="main_frame",
        )
        page_template = PageTemplate(
            id="audit_page",
            frames=[frame],
            onPage=self._draw_header_footer_with_total,
        )
        self.pageTemplates = [page_template]

        # Second pass: render with total page count
        self._is_first_pass = False
        super().multiBuild(flowables, **kwargs)

    def build_elements(
        self,
        events: list[AuditEvent],
        metadata: ExportMetadata,
    ) -> list:
        """Build the list of flowable elements for the PDF.

        Creates the header section with metadata, followed by the
        event table with repeated column headers on each page.

        Args:
            events: List of audit events to render.
            metadata: Export metadata for the header section.

        Returns:
            List of ReportLab flowable elements.
        """
        elements: list = []
        styles = getSampleStyleSheet()

        # --- Header metadata section ---
        header_style = ParagraphStyle(
            "AuditHeader",
            parent=styles["Normal"],
            fontName="Courier",
            fontSize=8,
            leading=11,
        )
        header_bold_style = ParagraphStyle(
            "AuditHeaderBold",
            parent=styles["Normal"],
            fontName="Courier-Bold",
            fontSize=9,
            leading=12,
        )

        elements.append(
            Paragraph(f"<b>Company:</b> {metadata.company_name}", header_bold_style)
        )
        elements.append(
            Paragraph(
                f"<b>Export Date/Time:</b> {metadata.export_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                header_style,
            )
        )
        elements.append(
            Paragraph(
                f"<b>Filters:</b> {_format_filters_summary(metadata.filters_applied)}",
                header_style,
            )
        )
        elements.append(
            Paragraph(
                f"<b>Total Events:</b> {metadata.total_event_count}",
                header_style,
            )
        )
        elements.append(
            Paragraph(
                f"<b>Requested By:</b> {metadata.requesting_user_name}",
                header_style,
            )
        )
        elements.append(Spacer(1, 0.5 * cm))

        # --- Event table ---
        # Column headers
        col_headers = [
            "#",
            "Timestamp",
            "User",
            "Record Type",
            "Record ID",
            "Operation",
            "Change Reason",
        ]

        # Build table data with header row
        table_data = [col_headers]

        for idx, event in enumerate(events, start=1):
            user_display = event.user_display_name or str(event.user_id)
            timestamp_str = event.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            change_reason = _truncate_change_reason(event.change_reason)

            row = [
                str(idx),
                timestamp_str,
                user_display,
                event.record_type,
                str(event.record_id),
                event.operation_type,
                change_reason,
            ]
            table_data.append(row)

        # Column widths (proportional to A4 width minus margins)
        available_width = _PAGE_WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT
        col_widths = [
            available_width * 0.04,   # #
            available_width * 0.14,   # Timestamp
            available_width * 0.12,   # User
            available_width * 0.12,   # Record Type
            available_width * 0.08,   # Record ID
            available_width * 0.09,   # Operation
            available_width * 0.41,   # Change Reason
        ]

        # Create table with repeated headers
        table = Table(
            table_data,
            colWidths=col_widths,
            repeatRows=1,
        )

        # Table styling
        table_style = TableStyle([
            # Header row styling
            ("FONTNAME", (0, 0), (-1, 0), "Courier-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 0), (-1, 0), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            # Data row styling
            ("FONTNAME", (0, 1), (-1, -1), "Courier"),
            ("FONTSIZE", (0, 1), (-1, -1), 6),
            ("LEADING", (0, 1), (-1, -1), 8),
            # Grid and separators
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),
            # Padding
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ])
        table.setStyle(table_style)

        elements.append(table)

        return elements
