"""Unit tests for ExportService (Phase 9.6 — Literature Search Results Export).

Covers:
- CSV export: correct columns, semicolon-separated arrays
- PDF export: StreamingResponse with application/pdf content-type
- PDF export with include_prisma_flow=True includes PRISMA section
- Validation: neither search_execution_id nor saved_search_id → ValueError
- Cross-company reference → ExportReferenceNotFoundError
- Audit event recorded on export

References:
    - Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
"""

from __future__ import annotations

import csv
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.search.exceptions import ExportReferenceNotFoundError
from alcoabase.literature.search.services.export_service import ExportService


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def sample_results() -> list[dict]:
    """Sample search results for testing exports."""
    return [
        {
            "title": "Effect of Drug X on Biomarker Y",
            "authors": ["Smith J", "Doe A", "Johnson B"],
            "publication_date": "2024-03-15",
            "journal": "Journal of Clinical Research",
            "source": "pubmed",
            "publication_type": "research_article",
            "doi": "10.1234/jcr.2024.001",
            "abstract": "This study examines the effect of Drug X on Biomarker Y in a randomized controlled trial.",
            "relevance_score": 0.92,
            "provenance": "external",
            "mesh_terms": ["Biomarkers", "Drug Therapy", "Randomized Controlled Trial"],
        },
        {
            "title": "Safety Profile of Drug X: A Meta-Analysis",
            "authors": ["Lee C", "Park D"],
            "publication_date": "2023-11-20",
            "journal": "Drug Safety Reports",
            "source": "embase",
            "publication_type": "meta_analysis",
            "doi": "10.5678/dsr.2023.042",
            "abstract": "A comprehensive meta-analysis of safety data for Drug X across 12 clinical trials.",
            "relevance_score": 0.87,
            "provenance": "external",
            "mesh_terms": ["Meta-Analysis", "Drug Safety"],
        },
    ]


def _make_execution_log(company_id: int = 1) -> MagicMock:
    """Create a mock SearchExecutionLog with standard attributes."""
    log = MagicMock()
    log.id = 10
    log.company_id = company_id
    log.user_id = 5
    log.query_text = "Drug X biomarker"
    log.filters = {"journals": ["Journal of Clinical Research"]}
    log.search_mode = "hybrid"
    log.include_internal = False
    log.total_results = 2
    log.sources_queried = ["pubmed", "embase"]
    log.execution_duration_ms = 245
    return log


def _make_saved_search(company_id: int = 1) -> MagicMock:
    """Create a mock SavedSearch with standard attributes."""
    search = MagicMock()
    search.id = 20
    search.company_id = company_id
    search.user_id = 5
    search.name = "My Saved Search"
    search.query_text = "Drug X safety"
    search.filters = {}
    search.search_mode = "keyword"
    search.include_internal = True
    return search


def _mock_scalar_one_or_none(obj):
    """Create a mock execute result that returns obj via scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


# ===========================================================================
# CSV Export Tests
# ===========================================================================


class TestGenerateCsvExport:
    """Tests for ExportService.generate_csv_export."""

    @pytest.mark.asyncio
    async def test_csv_export_correct_columns(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """CSV export produces correct column headers."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response = await service.generate_csv_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
            )

        assert response.media_type == "text/csv"

        # Read CSV content from the streaming response body
        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        reader = csv.reader(io.StringIO(body.decode()))
        header = next(reader)

        expected_columns = [
            "title",
            "authors",
            "publication_date",
            "journal",
            "source",
            "publication_type",
            "doi",
            "abstract",
            "relevance_score",
            "provenance",
            "mesh_terms",
        ]
        assert header == expected_columns

    @pytest.mark.asyncio
    async def test_csv_export_semicolon_separated_arrays(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """CSV export uses semicolons to separate authors and mesh_terms."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response = await service.generate_csv_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
            )

        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        reader = csv.reader(io.StringIO(body.decode()))
        _header = next(reader)
        first_row = next(reader)

        # authors column (index 1) should be semicolon-separated
        authors_field = first_row[1]
        assert authors_field == "Smith J;Doe A;Johnson B"

        # mesh_terms column (index 10) should be semicolon-separated
        mesh_terms_field = first_row[10]
        assert mesh_terms_field == "Biomarkers;Drug Therapy;Randomized Controlled Trial"

    @pytest.mark.asyncio
    async def test_csv_export_correct_data_rows(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """CSV export includes all result rows with correct data."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response = await service.generate_csv_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
            )

        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        reader = csv.reader(io.StringIO(body.decode()))
        rows = list(reader)

        # 1 header + 2 data rows
        assert len(rows) == 3
        # Verify first data row title
        assert rows[1][0] == "Effect of Drug X on Biomarker Y"
        # Verify second data row title
        assert rows[2][0] == "Safety Profile of Drug X: A Meta-Analysis"


# ===========================================================================
# PDF Export Tests
# ===========================================================================


class TestGeneratePdfExport:
    """Tests for ExportService.generate_pdf_export."""

    @pytest.mark.asyncio
    async def test_pdf_export_produces_streaming_response(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """PDF export returns a StreamingResponse with application/pdf content-type."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response = await service.generate_pdf_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
                include_prisma_flow=False,
            )

        assert response.media_type == "application/pdf"

        # Verify Content-Disposition header includes .pdf filename
        content_disp = response.headers.get("content-disposition", "")
        assert ".pdf" in content_disp
        assert "attachment" in content_disp

    @pytest.mark.asyncio
    async def test_pdf_export_generates_valid_pdf_bytes(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """PDF export generates non-empty PDF content starting with %PDF magic bytes."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response = await service.generate_pdf_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
                include_prisma_flow=False,
            )

        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        # PDF files start with %PDF magic bytes
        assert body[:4] == b"%PDF"
        assert len(body) > 100  # Non-trivial content

    @pytest.mark.asyncio
    async def test_pdf_export_with_prisma_flow(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """PDF export with include_prisma_flow=True generates a valid PDF (PRISMA section included)."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response = await service.generate_pdf_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
                include_prisma_flow=True,
            )

        assert response.media_type == "application/pdf"

        body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                body += chunk.encode()
            else:
                body += chunk

        # Valid PDF with PRISMA content will be larger than without
        assert body[:4] == b"%PDF"
        assert len(body) > 100

    @pytest.mark.asyncio
    async def test_pdf_export_with_prisma_flow_is_larger(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """PDF with PRISMA flow is larger than without (proving PRISMA section is included)."""
        execution_log = _make_execution_log(company_id=1)

        service = ExportService(session=mock_session, query_engine=None)

        # Generate without PRISMA
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)
        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response_no_prisma = await service.generate_pdf_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
                include_prisma_flow=False,
            )

        body_no_prisma = b""
        async for chunk in response_no_prisma.body_iterator:
            if isinstance(chunk, str):
                body_no_prisma += chunk.encode()
            else:
                body_no_prisma += chunk

        # Generate with PRISMA
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)
        with patch.object(
            service, "_get_search_results", return_value=sample_results
        ):
            response_prisma = await service.generate_pdf_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
                include_prisma_flow=True,
            )

        body_prisma = b""
        async for chunk in response_prisma.body_iterator:
            if isinstance(chunk, str):
                body_prisma += chunk.encode()
            else:
                body_prisma += chunk

        assert len(body_prisma) > len(body_no_prisma)


# ===========================================================================
# Validation Tests
# ===========================================================================


class TestValidation:
    """Tests for validation: missing reference params raise ValueError."""

    @pytest.mark.asyncio
    async def test_csv_export_no_reference_raises_value_error(
        self, mock_session: AsyncMock
    ) -> None:
        """generate_csv_export raises ValueError when neither ID is provided."""
        service = ExportService(session=mock_session)

        with pytest.raises(ValueError, match="At least one of"):
            await service.generate_csv_export(
                search_execution_id=None,
                saved_search_id=None,
                company_id=1,
                user_id=5,
            )

    @pytest.mark.asyncio
    async def test_pdf_export_no_reference_raises_value_error(
        self, mock_session: AsyncMock
    ) -> None:
        """generate_pdf_export raises ValueError when neither ID is provided."""
        service = ExportService(session=mock_session)

        with pytest.raises(ValueError, match="At least one of"):
            await service.generate_pdf_export(
                search_execution_id=None,
                saved_search_id=None,
                company_id=1,
                user_id=5,
            )


# ===========================================================================
# Cross-Company Access Tests
# ===========================================================================


class TestCrossCompanyAccess:
    """Tests for cross-company reference → ExportReferenceNotFoundError."""

    @pytest.mark.asyncio
    async def test_csv_cross_company_execution_log_raises_error(
        self, mock_session: AsyncMock
    ) -> None:
        """CSV export with execution log from different company raises ExportReferenceNotFoundError."""
        # Execution log belongs to company_id=99, but request is for company_id=1
        execution_log = _make_execution_log(company_id=99)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session)

        with pytest.raises(ExportReferenceNotFoundError):
            await service.generate_csv_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
            )

    @pytest.mark.asyncio
    async def test_csv_nonexistent_execution_log_raises_error(
        self, mock_session: AsyncMock
    ) -> None:
        """CSV export with nonexistent execution log raises ExportReferenceNotFoundError."""
        mock_session.execute.return_value = _mock_scalar_one_or_none(None)

        service = ExportService(session=mock_session)

        with pytest.raises(ExportReferenceNotFoundError):
            await service.generate_csv_export(
                search_execution_id=999,
                company_id=1,
                user_id=5,
            )

    @pytest.mark.asyncio
    async def test_pdf_cross_company_saved_search_raises_error(
        self, mock_session: AsyncMock
    ) -> None:
        """PDF export with saved search from different company raises ExportReferenceNotFoundError."""
        saved_search = _make_saved_search(company_id=99)
        mock_session.execute.return_value = _mock_scalar_one_or_none(saved_search)

        service = ExportService(session=mock_session)

        with pytest.raises(ExportReferenceNotFoundError):
            await service.generate_pdf_export(
                saved_search_id=20,
                company_id=1,
                user_id=5,
            )

    @pytest.mark.asyncio
    async def test_pdf_nonexistent_saved_search_raises_error(
        self, mock_session: AsyncMock
    ) -> None:
        """PDF export with nonexistent saved search raises ExportReferenceNotFoundError."""
        mock_session.execute.return_value = _mock_scalar_one_or_none(None)

        service = ExportService(session=mock_session)

        with pytest.raises(ExportReferenceNotFoundError):
            await service.generate_pdf_export(
                saved_search_id=999,
                company_id=1,
                user_id=5,
            )


# ===========================================================================
# Audit Event Tests
# ===========================================================================


class TestAuditEventRecording:
    """Tests that audit events are recorded on export generation."""

    @pytest.mark.asyncio
    async def test_csv_export_records_audit_event(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """CSV export calls _record_audit_event with correct params."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with (
            patch.object(
                service, "_get_search_results", return_value=sample_results
            ),
            patch.object(
                service, "_record_audit_event", new_callable=AsyncMock
            ) as mock_audit,
        ):
            await service.generate_csv_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
            )

        mock_audit.assert_called_once_with(
            export_format="csv",
            search_execution_id=10,
            saved_search_id=None,
            company_id=1,
            user_id=5,
            result_count=2,
        )

    @pytest.mark.asyncio
    async def test_pdf_export_records_audit_event(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """PDF export calls _record_audit_event with correct params."""
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with (
            patch.object(
                service, "_get_search_results", return_value=sample_results
            ),
            patch.object(
                service, "_record_audit_event", new_callable=AsyncMock
            ) as mock_audit,
        ):
            await service.generate_pdf_export(
                search_execution_id=10,
                company_id=1,
                user_id=5,
                include_prisma_flow=False,
            )

        mock_audit.assert_called_once_with(
            export_format="pdf",
            search_execution_id=10,
            saved_search_id=None,
            company_id=1,
            user_id=5,
            result_count=2,
        )

    @pytest.mark.asyncio
    async def test_audit_event_includes_saved_search_id(
        self, mock_session: AsyncMock, sample_results: list[dict]
    ) -> None:
        """Audit event includes saved_search_id when exporting from saved search."""
        saved_search = _make_saved_search(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(saved_search)

        service = ExportService(session=mock_session, query_engine=None)

        with (
            patch.object(
                service, "_get_search_results", return_value=sample_results
            ),
            patch.object(
                service, "_record_audit_event", new_callable=AsyncMock
            ) as mock_audit,
        ):
            await service.generate_csv_export(
                saved_search_id=20,
                company_id=1,
                user_id=5,
            )

        mock_audit.assert_called_once_with(
            export_format="csv",
            search_execution_id=None,
            saved_search_id=20,
            company_id=1,
            user_id=5,
            result_count=2,
        )
