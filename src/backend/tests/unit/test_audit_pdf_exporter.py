"""Unit tests for AuditPDFExporter service.

Tests cover:
- generate_pdf produces valid PDF bytes (parseable by PyMuPDF)
- PDF uses A4 page size, portrait orientation
- PDF uses fixed-width font for tabular data
- Column headers repeated on each page (multi-page document)
- Footer contains page number, total pages, generation timestamp
- Header contains company name, export timestamp, filters, event count, user
- change_reason truncation at 500 chars with ellipsis
- export_sync raises ValueError when zero events match
- export_async dispatches Celery task and returns job_id
- get_export_status returns correct status for pending/completed/failed jobs

References:
    - Requirements: 7.1–7.10
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import fitz  # PyMuPDF
import pytest

from alcoabase.schemas.audit_trail import (
    AuditEvent,
    AuditTrailFilters,
    AuditTrailPage,
    ExportMetadata,
    ExportStatusResponse,
)
from alcoabase.services.audit_pdf_exporter import AuditPDFExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def exporter() -> AuditPDFExporter:
    """Create an AuditPDFExporter instance."""
    return AuditPDFExporter()


@pytest.fixture
def sample_metadata() -> ExportMetadata:
    """Create sample export metadata for testing."""
    return ExportMetadata(
        company_name="Acme Pharma Inc.",
        export_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc),
        filters_applied=AuditTrailFilters(
            record_type="documents",
            operation_type="UPDATE",
        ),
        total_event_count=3,
        requesting_user_name="Jane Auditor",
    )


@pytest.fixture
def sample_events() -> list[AuditEvent]:
    """Create a small list of sample audit events."""
    return [
        AuditEvent(
            transaction_id=101,
            timestamp=datetime(2025, 6, 15, 14, 0, 0, tzinfo=timezone.utc),
            user_id=1,
            user_display_name="Alice Smith",
            record_type="documents",
            record_id=42,
            operation_type="UPDATE",
            change_reason="Updated document title for clarity",
            changed_fields=["title", "updated_at"],
            total_changed_fields=2,
            company_id=1,
        ),
        AuditEvent(
            transaction_id=102,
            timestamp=datetime(2025, 6, 15, 13, 0, 0, tzinfo=timezone.utc),
            user_id=2,
            user_display_name="Bob Jones",
            record_type="documents",
            record_id=43,
            operation_type="INSERT",
            change_reason="Initial document creation",
            changed_fields=["title", "content", "status"],
            total_changed_fields=3,
            company_id=1,
        ),
        AuditEvent(
            transaction_id=103,
            timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            user_id=1,
            user_display_name="Alice Smith",
            record_type="documents",
            record_id=44,
            operation_type="DELETE",
            change_reason=None,
            changed_fields=["status"],
            total_changed_fields=1,
            company_id=1,
        ),
    ]


def _make_many_events(count: int) -> list[AuditEvent]:
    """Generate a large number of events for multi-page testing."""
    events = []
    for i in range(count):
        events.append(
            AuditEvent(
                transaction_id=1000 + i,
                timestamp=datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
                user_id=1,
                user_display_name="Test User",
                record_type="documents",
                record_id=i,
                operation_type="UPDATE",
                change_reason=f"Change reason for event {i}",
                changed_fields=["field_a", "field_b"],
                total_changed_fields=2,
                company_id=1,
            )
        )
    return events


# ---------------------------------------------------------------------------
# generate_pdf: produces valid PDF bytes
# ---------------------------------------------------------------------------


class TestGeneratePdfValidity:
    """Tests that generate_pdf produces valid, parseable PDF bytes."""

    def test_produces_bytes(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """generate_pdf returns bytes."""
        result = exporter.generate_pdf(sample_events, sample_metadata)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_parseable_by_pymupdf(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """generate_pdf produces a valid PDF parseable by PyMuPDF."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        assert doc.page_count >= 1
        doc.close()

    def test_pdf_starts_with_magic_bytes(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """generate_pdf output starts with PDF magic bytes."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        assert pdf_bytes[:5] == b"%PDF-"


# ---------------------------------------------------------------------------
# generate_pdf: A4 page size, portrait orientation
# ---------------------------------------------------------------------------


class TestPdfPageSize:
    """Tests that PDF uses A4 page size in portrait orientation."""

    def test_a4_portrait_dimensions(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF pages use A4 dimensions (595.27 x 841.89 points, portrait)."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        width = page.rect.width
        height = page.rect.height
        # A4 is 595.27 x 841.89 points; allow small tolerance
        assert abs(width - 595.27) < 1.0
        assert abs(height - 841.89) < 1.0
        # Portrait: width < height
        assert width < height
        doc.close()


# ---------------------------------------------------------------------------
# generate_pdf: fixed-width font for tabular data
# ---------------------------------------------------------------------------


class TestPdfFixedWidthFont:
    """Tests that PDF uses fixed-width font (Courier) for tabular data."""

    def test_uses_courier_font(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF contains Courier font references for tabular data."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Check that Courier font is used in the document
        page = doc[0]
        text_dict = page.get_text("dict")
        font_names = set()
        for block in text_dict.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font_names.add(span.get("font", ""))
        # Courier or Courier-Bold should be present
        courier_fonts = [f for f in font_names if "Courier" in f]
        assert len(courier_fonts) > 0, f"Expected Courier font, found: {font_names}"
        doc.close()


# ---------------------------------------------------------------------------
# generate_pdf: column headers repeated on each page
# ---------------------------------------------------------------------------


class TestPdfColumnHeadersRepeated:
    """Tests that column headers are repeated on each page."""

    def test_headers_on_each_page(
        self, exporter: AuditPDFExporter, sample_metadata: ExportMetadata
    ) -> None:
        """Column headers appear on every page of a multi-page document."""
        # Generate enough events to span multiple pages
        many_events = _make_many_events(150)
        metadata = ExportMetadata(
            company_name=sample_metadata.company_name,
            export_timestamp=sample_metadata.export_timestamp,
            filters_applied=sample_metadata.filters_applied,
            total_event_count=len(many_events),
            requesting_user_name=sample_metadata.requesting_user_name,
        )
        pdf_bytes = exporter.generate_pdf(many_events, metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        assert doc.page_count > 1, "Expected multi-page PDF for header repetition test"

        # Check that "Timestamp" header appears on each page
        for page_idx in range(doc.page_count):
            page = doc[page_idx]
            text = page.get_text()
            assert "Timestamp" in text, (
                f"Column header 'Timestamp' not found on page {page_idx + 1}"
            )
        doc.close()


# ---------------------------------------------------------------------------
# generate_pdf: footer contains page number, total pages, generation timestamp
# ---------------------------------------------------------------------------


class TestPdfFooter:
    """Tests that footer contains page number, total pages, and generation timestamp."""

    def test_footer_contains_page_number(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """Footer contains page number text."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "Page 1" in text
        doc.close()

    def test_footer_contains_total_pages(
        self, exporter: AuditPDFExporter, sample_metadata: ExportMetadata
    ) -> None:
        """Footer contains total page count (Page X of Y)."""
        many_events = _make_many_events(150)
        metadata = ExportMetadata(
            company_name=sample_metadata.company_name,
            export_timestamp=sample_metadata.export_timestamp,
            filters_applied=sample_metadata.filters_applied,
            total_event_count=len(many_events),
            requesting_user_name=sample_metadata.requesting_user_name,
        )
        pdf_bytes = exporter.generate_pdf(many_events, metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        total_pages = doc.page_count
        assert f"of {total_pages}" in text
        doc.close()

    def test_footer_contains_generation_timestamp(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """Footer contains 'Generated:' timestamp."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "Generated:" in text
        doc.close()


# ---------------------------------------------------------------------------
# generate_pdf: header contains company name, export timestamp, filters, event count, user
# ---------------------------------------------------------------------------


class TestPdfHeader:
    """Tests that PDF header contains required metadata."""

    def test_header_contains_company_name(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF header contains the company name."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "Acme Pharma Inc." in text
        doc.close()

    def test_header_contains_export_timestamp(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF header contains the export timestamp."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "2025-06-15" in text
        assert "14:30:00 UTC" in text
        doc.close()

    def test_header_contains_filters(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF header contains applied filters summary."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "documents" in text
        assert "UPDATE" in text
        doc.close()

    def test_header_contains_event_count(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF header contains total event count."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "3" in text  # total_event_count from metadata
        doc.close()

    def test_header_contains_requesting_user(
        self, exporter: AuditPDFExporter, sample_events: list[AuditEvent], sample_metadata: ExportMetadata
    ) -> None:
        """PDF header contains the requesting user's name."""
        pdf_bytes = exporter.generate_pdf(sample_events, sample_metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        text = page.get_text()
        assert "Jane Auditor" in text
        doc.close()


# ---------------------------------------------------------------------------
# generate_pdf: change_reason truncation at 500 chars with ellipsis
# ---------------------------------------------------------------------------


class TestChangeReasonTruncation:
    """Tests that change_reason is truncated at 500 chars with ellipsis.

    Note: PDF table cells wrap long text, so extracted text may contain
    line breaks. We test the truncation logic by checking the internal
    _truncate_change_reason function and verifying PDF content properties.
    """

    def test_truncate_function_short_text(self) -> None:
        """_truncate_change_reason does not truncate text under 500 chars."""
        from alcoabase.services.audit_pdf_exporter import _truncate_change_reason

        short_reason = "A" * 100
        result = _truncate_change_reason(short_reason)
        assert result == short_reason
        assert "..." not in result

    def test_truncate_function_long_text(self) -> None:
        """_truncate_change_reason truncates text over 500 chars with ellipsis."""
        from alcoabase.services.audit_pdf_exporter import _truncate_change_reason

        long_reason = "X" * 600
        result = _truncate_change_reason(long_reason)
        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")
        assert result[:500] == "X" * 500

    def test_truncate_function_exactly_500_chars(self) -> None:
        """_truncate_change_reason does not truncate text of exactly 500 chars."""
        from alcoabase.services.audit_pdf_exporter import _truncate_change_reason

        exact_reason = "Y" * 500
        result = _truncate_change_reason(exact_reason)
        assert result == exact_reason
        assert "..." not in result

    def test_truncate_function_none_returns_placeholder(self) -> None:
        """_truncate_change_reason returns '(none)' for None input."""
        from alcoabase.services.audit_pdf_exporter import _truncate_change_reason

        result = _truncate_change_reason(None)
        assert result == "(none)"

    def test_truncate_function_empty_string_returns_placeholder(self) -> None:
        """_truncate_change_reason returns '(none)' for empty string."""
        from alcoabase.services.audit_pdf_exporter import _truncate_change_reason

        result = _truncate_change_reason("")
        assert result == "(none)"

    def test_pdf_long_reason_does_not_contain_full_text(
        self, exporter: AuditPDFExporter, sample_metadata: ExportMetadata
    ) -> None:
        """PDF with 600-char change_reason does not render the full untruncated text.

        The truncation function limits to 500 chars + ellipsis, and the table
        cell further constrains visible text. We verify the full 600-char
        string is not present in the rendered PDF.
        """
        long_reason = "X" * 600
        events = [
            AuditEvent(
                transaction_id=1,
                timestamp=datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
                user_id=1,
                user_display_name="User",
                record_type="documents",
                record_id=1,
                operation_type="UPDATE",
                change_reason=long_reason,
                changed_fields=["title"],
                total_changed_fields=1,
                company_id=1,
            )
        ]
        metadata = ExportMetadata(
            company_name=sample_metadata.company_name,
            export_timestamp=sample_metadata.export_timestamp,
            filters_applied=sample_metadata.filters_applied,
            total_event_count=1,
            requesting_user_name=sample_metadata.requesting_user_name,
        )
        pdf_bytes = exporter.generate_pdf(events, metadata)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Collect all text across pages
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        normalized_text = full_text.replace("\n", "").replace(" ", "")
        # The full 600 X's should NOT appear (truncated to 500 by the function)
        assert "X" * 600 not in normalized_text
        # Count total X's rendered — should be less than 600
        total_x = normalized_text.count("X")
        assert total_x < 600, f"Expected fewer than 600 X's, got {total_x}"
        doc.close()


# ---------------------------------------------------------------------------
# export_sync: raises ValueError when zero events match
# ---------------------------------------------------------------------------


class TestExportSyncZeroEvents:
    """Tests that export_sync raises ValueError when no events match."""

    @pytest.mark.asyncio
    async def test_raises_value_error_on_zero_events(
        self, exporter: AuditPDFExporter
    ) -> None:
        """export_sync raises ValueError when zero events match filters."""
        mock_session = AsyncMock()

        # Mock AuditTrailService to return empty page
        empty_page = AuditTrailPage(events=[], next_cursor=None, total_count=0)

        with patch(
            "alcoabase.services.audit_trail_service.AuditTrailService"
        ) as MockService:
            mock_service_instance = MockService.return_value
            mock_service_instance.list_events = AsyncMock(return_value=empty_page)

            with pytest.raises(ValueError, match="No events match the current filters"):
                await exporter.export_sync(
                    session=mock_session,
                    company_id=1,
                    filters=AuditTrailFilters(),
                    search_query=None,
                    requesting_user_id=1,
                )


# ---------------------------------------------------------------------------
# export_async: dispatches Celery task and returns job_id
# ---------------------------------------------------------------------------


class TestExportAsync:
    """Tests that export_async dispatches Celery task and returns job_id."""

    @pytest.mark.asyncio
    async def test_returns_uuid_job_id(self, exporter: AuditPDFExporter) -> None:
        """export_async returns a valid UUID string as job_id."""
        mock_session = AsyncMock()
        mock_task = MagicMock()
        mock_task.apply_async = MagicMock()

        with patch.dict(
            "sys.modules",
            {"alcoabase.tasks.audit_export_tasks": MagicMock(export_audit_pdf_task=mock_task)},
        ):
            job_id = await exporter.export_async(
                session=mock_session,
                company_id=1,
                filters=AuditTrailFilters(record_type="documents"),
                search_query=None,
                requesting_user_id=42,
            )

        assert isinstance(job_id, str)
        assert len(job_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_dispatches_celery_task(self, exporter: AuditPDFExporter) -> None:
        """export_async calls apply_async on the Celery task."""
        mock_session = AsyncMock()
        mock_task = MagicMock()
        mock_task.apply_async = MagicMock()

        with patch.dict(
            "sys.modules",
            {"alcoabase.tasks.audit_export_tasks": MagicMock(export_audit_pdf_task=mock_task)},
        ):
            job_id = await exporter.export_async(
                session=mock_session,
                company_id=5,
                filters=AuditTrailFilters(operation_type="DELETE"),
                search_query="test search",
                requesting_user_id=10,
            )

        mock_task.apply_async.assert_called_once()
        call_kwargs = mock_task.apply_async.call_args
        task_kwargs = call_kwargs.kwargs.get("kwargs") or call_kwargs[1].get("kwargs")
        assert task_kwargs["job_id"] == job_id
        assert task_kwargs["company_id"] == 5
        assert task_kwargs["search_query"] == "test search"
        assert task_kwargs["requesting_user_id"] == 10

    @pytest.mark.asyncio
    async def test_task_id_matches_job_id(self, exporter: AuditPDFExporter) -> None:
        """export_async sets task_id equal to job_id for tracking."""
        mock_session = AsyncMock()
        mock_task = MagicMock()
        mock_task.apply_async = MagicMock()

        with patch.dict(
            "sys.modules",
            {"alcoabase.tasks.audit_export_tasks": MagicMock(export_audit_pdf_task=mock_task)},
        ):
            job_id = await exporter.export_async(
                session=mock_session,
                company_id=1,
                filters=None,
                search_query=None,
                requesting_user_id=1,
            )

        call_kwargs = mock_task.apply_async.call_args
        task_id = call_kwargs.kwargs.get("task_id") or call_kwargs[1].get("task_id")
        assert task_id == job_id


# ---------------------------------------------------------------------------
# get_export_status: returns correct status for pending/completed/failed jobs
# ---------------------------------------------------------------------------


class TestGetExportStatus:
    """Tests that get_export_status returns correct status."""

    def test_pending_status(self, exporter: AuditPDFExporter) -> None:
        """get_export_status returns 'pending' for PENDING tasks."""
        mock_result = MagicMock()
        mock_result.state = "PENDING"

        with patch("celery.result.AsyncResult", return_value=mock_result):
            with patch.dict(
                "sys.modules",
                {"alcoabase.tasks.celery_app": MagicMock(celery_app=MagicMock())},
            ):
                status = exporter.get_export_status("test-job-id")

        assert isinstance(status, ExportStatusResponse)
        assert status.job_id == "test-job-id"
        assert status.status == "pending"
        assert status.download_url is None
        assert status.error_message is None

    def test_processing_status(self, exporter: AuditPDFExporter) -> None:
        """get_export_status returns 'processing' for STARTED tasks."""
        mock_result = MagicMock()
        mock_result.state = "STARTED"

        with patch("celery.result.AsyncResult", return_value=mock_result):
            with patch.dict(
                "sys.modules",
                {"alcoabase.tasks.celery_app": MagicMock(celery_app=MagicMock())},
            ):
                status = exporter.get_export_status("test-job-id")

        assert status.status == "processing"

    def test_completed_status_with_download_url(self, exporter: AuditPDFExporter) -> None:
        """get_export_status returns 'completed' with download_url for SUCCESS tasks."""
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.result = {
            "status": "completed",
            "download_url": "https://minio.local/exports/audit-trail/abc.pdf",
        }

        with patch("celery.result.AsyncResult", return_value=mock_result):
            with patch.dict(
                "sys.modules",
                {"alcoabase.tasks.celery_app": MagicMock(celery_app=MagicMock())},
            ):
                status = exporter.get_export_status("test-job-id")

        assert status.status == "completed"
        assert status.download_url == "https://minio.local/exports/audit-trail/abc.pdf"

    def test_failed_status_from_task_result(self, exporter: AuditPDFExporter) -> None:
        """get_export_status returns 'failed' when task result indicates failure."""
        mock_result = MagicMock()
        mock_result.state = "SUCCESS"
        mock_result.result = {
            "status": "failed",
            "error_message": "Export timed out after 300 seconds",
        }

        with patch("celery.result.AsyncResult", return_value=mock_result):
            with patch.dict(
                "sys.modules",
                {"alcoabase.tasks.celery_app": MagicMock(celery_app=MagicMock())},
            ):
                status = exporter.get_export_status("test-job-id")

        assert status.status == "failed"
        assert status.error_message == "Export timed out after 300 seconds"

    def test_failed_status_from_celery_failure(self, exporter: AuditPDFExporter) -> None:
        """get_export_status returns 'failed' for FAILURE state tasks."""
        mock_result = MagicMock()
        mock_result.state = "FAILURE"
        mock_result.result = Exception("Connection refused")

        with patch("celery.result.AsyncResult", return_value=mock_result):
            with patch.dict(
                "sys.modules",
                {"alcoabase.tasks.celery_app": MagicMock(celery_app=MagicMock())},
            ):
                status = exporter.get_export_status("test-job-id")

        assert status.status == "failed"
        assert "Connection refused" in status.error_message
