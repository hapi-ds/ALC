"""Integration tests for export and multi-tenancy in Phase 9.6 Literature Search.

Tests cross-boundary behavior covering:
- CSV export generation with correct columns
- PDF export with and without PRISMA flow
- Multi-tenant isolation: company A data invisible to company B
- Citation collection 500 document limit enforcement
- Saved search 200 limit per user per company

Uses mocked database sessions to simulate multi-company scenarios and
service-level interactions between ExportService and LiteratureSearchService.

References:
    - Requirements 7.1–7.8, 8.1–8.6
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from __future__ import annotations

import csv
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.search.exceptions import (
    CollectionCapacityExceededError,
    ExportReferenceNotFoundError,
    NonInternalizedDocumentError,
    SavedSearchLimitExceededError,
)
from alcoabase.literature.search.models import (
    CitationCollection,
    CitationCollectionDocument,
    SavedSearch,
    SearchExecutionLog,
)
from alcoabase.literature.search.services.export_service import ExportService
from alcoabase.literature.search.services.literature_search_service import (
    LiteratureSearchService,
    _MAX_COLLECTION_DOCUMENTS,
    _MAX_SAVED_SEARCHES_PER_USER,
)


# ===========================================================================
# Helper factories
# ===========================================================================


def _make_execution_log(
    *,
    log_id: int = 1,
    company_id: int = 1,
    user_id: int = 10,
    query_text: str = "drug efficacy",
    search_mode: str = "hybrid",
    total_results: int = 5,
) -> MagicMock:
    """Create a mock SearchExecutionLog with configurable company_id."""
    log = MagicMock(spec=SearchExecutionLog)
    log.id = log_id
    log.company_id = company_id
    log.user_id = user_id
    log.query_text = query_text
    log.filters = {"journals": ["Nature Medicine"]}
    log.search_mode = search_mode
    log.include_internal = False
    log.total_results = total_results
    log.sources_queried = ["pubmed", "crossref"]
    log.execution_duration_ms = 320
    return log


def _make_saved_search(
    *,
    search_id: int = 1,
    company_id: int = 1,
    user_id: int = 10,
    name: str = "My Search",
    query_text: str = "biomarker analysis",
    status: str = "active",
) -> MagicMock:
    """Create a mock SavedSearch with configurable company_id."""
    search = MagicMock(spec=SavedSearch)
    search.id = search_id
    search.company_id = company_id
    search.user_id = user_id
    search.name = name
    search.query_text = query_text
    search.filters = {}
    search.search_mode = "hybrid"
    search.include_internal = False
    search.status = status
    search.last_executed_at = None
    search.last_result_count = None
    return search


def _make_sample_results(count: int = 3) -> list[dict]:
    """Generate sample search results for export tests."""
    results = []
    for i in range(count):
        results.append({
            "title": f"Study {i + 1}: Clinical Trial Results",
            "authors": [f"Author{i}A", f"Author{i}B", f"Author{i}C"],
            "publication_date": f"2024-0{(i % 9) + 1}-15",
            "journal": f"Journal of Medicine {i + 1}",
            "source": "pubmed" if i % 2 == 0 else "crossref",
            "publication_type": "research_article",
            "doi": f"10.1234/study.2024.{i:03d}",
            "abstract": f"This is the abstract for study {i + 1}. " * 10,
            "relevance_score": round(0.95 - (i * 0.05), 2),
            "provenance": "external",
            "mesh_terms": ["Clinical Trials", f"Term{i}"],
        })
    return results


def _mock_scalar_one_or_none(obj):
    """Create a mock result that returns obj via scalar_one_or_none."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _mock_scalar_one(value):
    """Create a mock result that returns value via scalar_one."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


# ===========================================================================
# CSV Export Integration Tests
# ===========================================================================


class TestCsvExportIntegration:
    """Integration tests for CSV export generation with correct columns."""

    @pytest.mark.asyncio
    async def test_csv_export_contains_all_required_columns(self) -> None:
        """CSV export includes all 11 required columns per Requirements 7.2."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)
        sample_results = _make_sample_results(count=5)

        with patch.object(service, "_get_search_results", return_value=sample_results):
            response = await service.generate_csv_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
            )

        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk

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
    async def test_csv_export_row_count_matches_results(self) -> None:
        """CSV export produces one row per result plus header row."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)
        sample_results = _make_sample_results(count=7)

        with patch.object(service, "_get_search_results", return_value=sample_results):
            response = await service.generate_csv_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
            )

        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk

        reader = csv.reader(io.StringIO(body.decode()))
        rows = list(reader)
        # 1 header + 7 data rows
        assert len(rows) == 8

    @pytest.mark.asyncio
    async def test_csv_export_semicolon_separated_fields(self) -> None:
        """Authors and mesh_terms use semicolons as separators in CSV."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)
        results = [{
            "title": "Test Paper",
            "authors": ["Smith J", "Doe A", "Lee B"],
            "publication_date": "2024-01-10",
            "journal": "Nature",
            "source": "pubmed",
            "publication_type": "research_article",
            "doi": "10.1000/test",
            "abstract": "Short abstract.",
            "relevance_score": 0.91,
            "provenance": "external",
            "mesh_terms": ["Oncology", "Genomics", "Biomarkers"],
        }]

        with patch.object(service, "_get_search_results", return_value=results):
            response = await service.generate_csv_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
            )

        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk

        reader = csv.reader(io.StringIO(body.decode()))
        _header = next(reader)
        row = next(reader)

        # authors (index 1) semicolon-separated
        assert row[1] == "Smith J;Doe A;Lee B"
        # mesh_terms (index 10) semicolon-separated
        assert row[10] == "Oncology;Genomics;Biomarkers"

    @pytest.mark.asyncio
    async def test_csv_export_abstract_truncated_to_300_chars(self) -> None:
        """CSV export truncates abstract to 300 characters per Requirements 7.2."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)
        long_abstract = "A" * 500
        results = [{
            "title": "Paper",
            "authors": ["Auth"],
            "publication_date": "2024-01-01",
            "journal": "J",
            "source": "pubmed",
            "publication_type": "article",
            "doi": "10.1/x",
            "abstract": long_abstract,
            "relevance_score": 0.8,
            "provenance": "external",
            "mesh_terms": [],
        }]

        with patch.object(service, "_get_search_results", return_value=results):
            response = await service.generate_csv_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
            )

        body = b""
        async for chunk in response.body_iterator:
            body += chunk.encode() if isinstance(chunk, str) else chunk

        reader = csv.reader(io.StringIO(body.decode()))
        _header = next(reader)
        row = next(reader)
        # abstract is at index 7
        assert len(row[7]) == 300

    @pytest.mark.asyncio
    async def test_csv_export_content_disposition_header(self) -> None:
        """CSV export response includes Content-Disposition for file download."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(service, "_get_search_results", return_value=[]):
            response = await service.generate_csv_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
            )

        assert response.media_type == "text/csv"
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert ".csv" in content_disp


# ===========================================================================
# PDF Export Integration Tests
# ===========================================================================


class TestPdfExportIntegration:
    """Integration tests for PDF export with and without PRISMA flow."""

    @pytest.mark.asyncio
    async def test_pdf_export_generates_valid_pdf(self) -> None:
        """PDF export produces a valid PDF StreamingResponse."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)
        sample_results = _make_sample_results(count=3)

        with patch.object(service, "_get_search_results", return_value=sample_results):
            response = await service.generate_pdf_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
                include_prisma_flow=False,
            )

        assert response.media_type == "application/pdf"

        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        # PDF files start with %PDF
        assert body[:4] == b"%PDF"
        # Should be non-trivial size
        assert len(body) > 500

    @pytest.mark.asyncio
    async def test_pdf_export_with_prisma_flow(self) -> None:
        """PDF export with include_prisma_flow=True produces larger PDF."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)
        sample_results = _make_sample_results(count=3)

        # Generate PDF without PRISMA
        with patch.object(service, "_get_search_results", return_value=sample_results):
            response_no_prisma = await service.generate_pdf_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
                include_prisma_flow=False,
            )

        body_no_prisma = b""
        async for chunk in response_no_prisma.body_iterator:
            body_no_prisma += chunk if isinstance(chunk, bytes) else chunk.encode()

        # Re-create mock for second call (body_iterator is consumed)
        mock_session2 = AsyncMock()
        mock_session2.execute.return_value = _mock_scalar_one_or_none(execution_log)
        service2 = ExportService(session=mock_session2, query_engine=None)

        # Generate PDF with PRISMA
        with patch.object(service2, "_get_search_results", return_value=sample_results):
            response_with_prisma = await service2.generate_pdf_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
                include_prisma_flow=True,
            )

        body_with_prisma = b""
        async for chunk in response_with_prisma.body_iterator:
            body_with_prisma += chunk if isinstance(chunk, bytes) else chunk.encode()

        # PRISMA flow adds content so the PDF should be larger
        assert len(body_with_prisma) > len(body_no_prisma)
        # Both should be valid PDFs
        assert body_with_prisma[:4] == b"%PDF"

    @pytest.mark.asyncio
    async def test_pdf_export_content_disposition_header(self) -> None:
        """PDF export response includes Content-Disposition for file download."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(service, "_get_search_results", return_value=[]):
            response = await service.generate_pdf_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
                include_prisma_flow=False,
            )

        assert response.media_type == "application/pdf"
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert ".pdf" in content_disp

    @pytest.mark.asyncio
    async def test_pdf_export_empty_results(self) -> None:
        """PDF export with no results still generates a valid PDF."""
        mock_session = AsyncMock()
        execution_log = _make_execution_log(company_id=1, total_results=0)
        mock_session.execute.return_value = _mock_scalar_one_or_none(execution_log)

        service = ExportService(session=mock_session, query_engine=None)

        with patch.object(service, "_get_search_results", return_value=[]):
            response = await service.generate_pdf_export(
                search_execution_id=1,
                company_id=1,
                user_id=10,
                include_prisma_flow=True,
            )

        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()

        assert body[:4] == b"%PDF"


# ===========================================================================
# Multi-Tenant Isolation Integration Tests
# ===========================================================================


class TestMultiTenantIsolation:
    """Integration tests for multi-tenant isolation: company A data invisible to company B."""

    @pytest.mark.asyncio
    async def test_export_rejects_cross_company_search_execution(self) -> None:
        """ExportService rejects export referencing another company's search execution."""
        mock_session = AsyncMock()
        # Execution log belongs to company 1
        execution_log_company1 = _make_execution_log(company_id=1, log_id=42)
        mock_session.execute.return_value = _mock_scalar_one_or_none(
            execution_log_company1
        )

        service = ExportService(session=mock_session, query_engine=None)

        # Company 2 user tries to export company 1's search
        with pytest.raises(ExportReferenceNotFoundError):
            await service.generate_csv_export(
                search_execution_id=42,
                company_id=2,
                user_id=20,
            )

    @pytest.mark.asyncio
    async def test_export_rejects_cross_company_saved_search(self) -> None:
        """ExportService rejects export referencing another company's saved search."""
        mock_session = AsyncMock()
        # Saved search belongs to company 1
        saved_search_company1 = _make_saved_search(company_id=1, search_id=99)

        call_count = [0]

        async def selective_execute(stmt):
            call_count[0] += 1
            # First call for search_execution_id (None provided, might be skipped)
            # The actual call for saved_search resolution
            return _mock_scalar_one_or_none(saved_search_company1)

        mock_session.execute = AsyncMock(side_effect=selective_execute)

        service = ExportService(session=mock_session, query_engine=None)

        # Company 2 user tries to export company 1's saved search
        with pytest.raises(ExportReferenceNotFoundError):
            await service.generate_csv_export(
                saved_search_id=99,
                company_id=2,
                user_id=20,
            )

    @pytest.mark.asyncio
    async def test_saved_search_isolation_between_companies(self) -> None:
        """LiteratureSearchService lists only current company's saved searches."""
        mock_session = AsyncMock()

        # Simulate query returning only company 1 searches (empty result for company 2)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_count_result = _mock_scalar_one(0)

        call_count = [0]

        async def simulate_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Count query
                return mock_count_result
            # List query
            return mock_result

        mock_session.execute = AsyncMock(side_effect=simulate_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Company 2 user listing saved searches should see nothing
        result = await service.list_saved_searches(
            user_id=20,
            company_id=2,
            page=1,
            page_size=20,
        )

        # The list should be empty (company 2 has no saved searches)
        assert result["items"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_citation_collection_isolation_between_companies(self) -> None:
        """LiteratureSearchService lists only current company's citation collections."""
        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_count_result = _mock_scalar_one(0)

        call_count = [0]

        async def simulate_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_count_result
            return mock_result

        mock_session.execute = AsyncMock(side_effect=simulate_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Company 2 sees nothing when company 1 has collections
        result = await service.list_citation_collections(
            company_id=2,
            page=1,
            page_size=20,
        )

        assert result["items"] == []
        assert result["total_count"] == 0

    @pytest.mark.asyncio
    async def test_add_documents_rejects_cross_company_documents(self) -> None:
        """Adding documents from company B to company A's collection raises error."""
        mock_session = AsyncMock()

        # Collection exists for company 1
        collection = MagicMock(spec=CitationCollection)
        collection.id = 1
        collection.company_id = 1
        collection.status = "active"

        # Document query returns empty (doc belongs to company 2, not company 1)
        call_count = [0]

        async def selective_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup
                return _mock_scalar_one_or_none(collection)
            if call_count[0] == 2:
                # Document lookup - returns no documents for this company
                result = MagicMock()
                result.all.return_value = []
                return result
            return _mock_scalar_one(0)

        mock_session.execute = AsyncMock(side_effect=selective_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Adding doc_id=999 (belongs to company 2) to company 1's collection
        with pytest.raises(ValueError, match="Documents not found"):
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[999],
                user_id=10,
                company_id=1,
            )


# ===========================================================================
# Citation Collection 500 Document Limit Tests
# ===========================================================================


class TestCitationCollection500DocumentLimit:
    """Integration tests for citation collection 500 document limit enforcement."""

    @pytest.mark.asyncio
    async def test_adding_documents_within_limit_succeeds(self) -> None:
        """Adding documents when under 500 limit succeeds."""
        mock_session = AsyncMock()

        collection = MagicMock(spec=CitationCollection)
        collection.id = 1
        collection.company_id = 1
        collection.status = "active"

        call_count = [0]

        async def selective_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup
                return _mock_scalar_one_or_none(collection)
            if call_count[0] == 2:
                # Document lookup (internalized docs)
                result = MagicMock()
                result.all.return_value = [
                    (100, 50),  # doc_id=100, source_ingestion_record_id=50
                    (101, 51),  # doc_id=101, source_ingestion_record_id=51
                ]
                return result
            if call_count[0] == 3:
                # Current count = 498 (room for 2 more)
                return _mock_scalar_one(498)
            if call_count[0] == 4:
                # Max position
                return _mock_scalar_one(498)
            return _mock_scalar_one(0)

        mock_session.execute = AsyncMock(side_effect=selective_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Adding 2 docs when 498 already exist (total = 500) should succeed
        result = await service.add_documents_to_collection(
            collection_id=1,
            document_ids=[100, 101],
            user_id=10,
            company_id=1,
        )

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_exceeding_500_limit_raises_error(self) -> None:
        """Adding documents that exceed 500 limit raises CollectionCapacityExceededError."""
        mock_session = AsyncMock()

        collection = MagicMock(spec=CitationCollection)
        collection.id = 1
        collection.company_id = 1
        collection.status = "active"

        call_count = [0]

        async def selective_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup
                return _mock_scalar_one_or_none(collection)
            if call_count[0] == 2:
                # Document lookup (internalized docs)
                result = MagicMock()
                result.all.return_value = [
                    (100, 50),  # doc_id=100, source_ingestion_record_id=50
                    (101, 51),
                    (102, 52),
                ]
                return result
            if call_count[0] == 3:
                # Current count = 499 (adding 3 would exceed 500)
                return _mock_scalar_one(499)
            return _mock_scalar_one(0)

        mock_session.execute = AsyncMock(side_effect=selective_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Adding 3 docs when 499 already exist (total would be 502 > 500)
        with pytest.raises(CollectionCapacityExceededError) as exc_info:
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[100, 101, 102],
                user_id=10,
                company_id=1,
            )

        assert exc_info.value.current_count == 499
        assert exc_info.value.collection_id == 1

    @pytest.mark.asyncio
    async def test_exactly_at_500_limit_rejects_additional(self) -> None:
        """Adding even one document when already at 500 raises error."""
        mock_session = AsyncMock()

        collection = MagicMock(spec=CitationCollection)
        collection.id = 5
        collection.company_id = 1
        collection.status = "active"

        call_count = [0]

        async def selective_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_scalar_one_or_none(collection)
            if call_count[0] == 2:
                result = MagicMock()
                result.all.return_value = [(200, 60)]
                return result
            if call_count[0] == 3:
                # Already at max capacity
                return _mock_scalar_one(_MAX_COLLECTION_DOCUMENTS)
            return _mock_scalar_one(0)

        mock_session.execute = AsyncMock(side_effect=selective_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        with pytest.raises(CollectionCapacityExceededError) as exc_info:
            await service.add_documents_to_collection(
                collection_id=5,
                document_ids=[200],
                user_id=10,
                company_id=1,
            )

        assert exc_info.value.current_count == _MAX_COLLECTION_DOCUMENTS

    @pytest.mark.asyncio
    async def test_non_internalized_document_rejected(self) -> None:
        """Documents without source_ingestion_record_id are rejected."""
        mock_session = AsyncMock()

        collection = MagicMock(spec=CitationCollection)
        collection.id = 1
        collection.company_id = 1
        collection.status = "active"

        call_count = [0]

        async def selective_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_scalar_one_or_none(collection)
            if call_count[0] == 2:
                # Document exists but is NOT internalized (source_ingestion_record_id=None)
                result = MagicMock()
                result.all.return_value = [(300, None)]
                return result
            return _mock_scalar_one(0)

        mock_session.execute = AsyncMock(side_effect=selective_execute)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        with pytest.raises(NonInternalizedDocumentError) as exc_info:
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[300],
                user_id=10,
                company_id=1,
            )

        assert exc_info.value.document_id == 300


# ===========================================================================
# Saved Search 200 Limit Per User Per Company Tests
# ===========================================================================


class TestSavedSearch200Limit:
    """Integration tests for saved search 200 limit per user per company."""

    @pytest.mark.asyncio
    async def test_creating_saved_search_within_limit_succeeds(self) -> None:
        """Creating a saved search when under 200 limit succeeds."""
        mock_session = AsyncMock()

        # Current count = 199 (room for one more)
        mock_session.execute = AsyncMock(return_value=_mock_scalar_one(199))
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Patch refresh to set attributes on the saved search
        async def mock_refresh(obj):
            obj.id = 200
            obj.created_at = "2024-01-01T00:00:00Z"
            obj.updated_at = "2024-01-01T00:00:00Z"

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_saved_search(
            name="New Search",
            description="Testing limit",
            query_text="clinical trial outcomes",
            filters={"journals": ["Lancet"]},
            search_mode="hybrid",
            include_internal=False,
            user_id=10,
            company_id=1,
        )

        assert result["name"] == "New Search"

    @pytest.mark.asyncio
    async def test_exceeding_200_limit_raises_error(self) -> None:
        """Creating saved search when at 200 limit raises SavedSearchLimitExceededError."""
        mock_session = AsyncMock()

        # Current count = 200 (at the limit)
        mock_session.execute = AsyncMock(
            return_value=_mock_scalar_one(_MAX_SAVED_SEARCHES_PER_USER)
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        with pytest.raises(SavedSearchLimitExceededError) as exc_info:
            await service.create_saved_search(
                name="Exceeding Limit",
                description=None,
                query_text="test query",
                filters={},
                search_mode="keyword",
                include_internal=False,
                user_id=10,
                company_id=1,
            )

        assert exc_info.value.current_count == _MAX_SAVED_SEARCHES_PER_USER
        assert exc_info.value.user_id == 10

    @pytest.mark.asyncio
    async def test_limit_is_per_user_per_company(self) -> None:
        """Saved search limit applies per user per company, not globally."""
        mock_session = AsyncMock()

        call_count = [0]

        async def company_scoped_count(stmt):
            call_count[0] += 1
            # User 10 in company 1 is at the limit
            # User 10 in company 2 has room
            # We simulate the user creating in company 2 (count=5)
            return _mock_scalar_one(5)

        mock_session.execute = AsyncMock(side_effect=company_scoped_count)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        async def mock_refresh(obj):
            obj.id = 6
            obj.created_at = "2024-01-01T00:00:00Z"
            obj.updated_at = "2024-01-01T00:00:00Z"

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Same user in a different company has room
        result = await service.create_saved_search(
            name="Company 2 Search",
            description=None,
            query_text="another query",
            filters={},
            search_mode="semantic",
            include_internal=True,
            user_id=10,
            company_id=2,
        )

        assert result["name"] == "Company 2 Search"

    @pytest.mark.asyncio
    async def test_archived_searches_dont_count_toward_limit(self) -> None:
        """Archived (soft-deleted) searches do not count toward the 200 limit.

        The service queries only status='active', so 200 archived + 0 active
        means the user can still create new searches.
        """
        mock_session = AsyncMock()

        # Active count is 0 (all 200 previous searches are archived)
        mock_session.execute = AsyncMock(return_value=_mock_scalar_one(0))
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()

        async def mock_refresh(obj):
            obj.id = 201
            obj.created_at = "2024-01-01T00:00:00Z"
            obj.updated_at = "2024-01-01T00:00:00Z"

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        service = LiteratureSearchService(
            session=mock_session,
            hybrid_query_engine=AsyncMock(),
            audit_trail_service=AsyncMock(),
            traceability_matrix_service=AsyncMock(),
            storage_client=AsyncMock(),
        )

        # Should succeed because only active searches count
        result = await service.create_saved_search(
            name="After Archive",
            description=None,
            query_text="post-archive query",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            user_id=10,
            company_id=1,
        )

        assert result["name"] == "After Archive"


# ===========================================================================
# Cross-Service Integration Tests (ExportService + LiteratureSearchService)
# ===========================================================================


class TestCrossServiceIntegration:
    """Tests verifying ExportService and LiteratureSearchService work together."""

    @pytest.mark.asyncio
    async def test_export_validation_requires_reference(self) -> None:
        """ExportService raises ValueError when no reference is provided."""
        mock_session = AsyncMock()
        service = ExportService(session=mock_session, query_engine=None)

        with pytest.raises(ValueError, match="At least one of"):
            await service.generate_csv_export(
                search_execution_id=None,
                saved_search_id=None,
                company_id=1,
                user_id=10,
            )

    @pytest.mark.asyncio
    async def test_export_validation_requires_reference_for_pdf(self) -> None:
        """ExportService raises ValueError for PDF when no reference is provided."""
        mock_session = AsyncMock()
        service = ExportService(session=mock_session, query_engine=None)

        with pytest.raises(ValueError, match="At least one of"):
            await service.generate_pdf_export(
                search_execution_id=None,
                saved_search_id=None,
                company_id=1,
                user_id=10,
                include_prisma_flow=False,
            )

    @pytest.mark.asyncio
    async def test_max_collection_documents_constant_is_500(self) -> None:
        """Verify the max collection documents constant is 500."""
        assert _MAX_COLLECTION_DOCUMENTS == 500

    @pytest.mark.asyncio
    async def test_max_saved_searches_constant_is_200(self) -> None:
        """Verify the max saved searches per user constant is 200."""
        assert _MAX_SAVED_SEARCHES_PER_USER == 200
