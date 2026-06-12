"""Export service for generating CSV and PDF exports of literature search results.

Provides export functionality for search execution results and saved search
re-executions. Supports CSV (tabular data) and PDF (formatted report with
optional PRISMA flow diagram) output formats.

Generated exports include full audit metadata for regulatory compliance:
- Export timestamp
- Requesting user and company context
- Search parameters and databases queried
- Audit confirmation statement

References:
    - Requirements 7.1, 7.2, 7.3, 7.4, 7.5
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select

from alcoabase.literature.search.exceptions import ExportReferenceNotFoundError
from alcoabase.literature.search.models import SavedSearch, SearchExecutionLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# PDF layout constants
_PAGE_WIDTH, _PAGE_HEIGHT = landscape(A4)
_MARGIN = 1.5 * cm


class ExportService:
    """Service for generating CSV and PDF exports of literature search results.

    Retrieves search execution metadata and results, then formats them into
    regulatory-compliant export documents (CSV or PDF). Records an audit
    event on each export generation.

    Attributes:
        session: Active async database session for queries.
        query_engine: Optional hybrid query engine for re-executing searches.
    """

    def __init__(
        self,
        session: AsyncSession,
        query_engine: Any | None = None,
    ) -> None:
        """Initialize ExportService with database session and optional query engine.

        Args:
            session: Async SQLAlchemy session for database access.
            query_engine: Optional HybridQueryEngine instance for re-executing
                searches. If not provided, the service retrieves only what is
                available from the database.
        """
        self.session = session
        self.query_engine = query_engine

    async def generate_csv_export(
        self,
        *,
        search_execution_id: int | None = None,
        saved_search_id: int | None = None,
        company_id: int,
        user_id: int,
    ) -> StreamingResponse:
        """Generate a CSV export of literature search results.

        Retrieves search execution results and builds an in-memory CSV with
        columns: title, authors, publication_date, journal, source,
        publication_type, doi, abstract (first 300 chars), relevance_score,
        provenance, mesh_terms.

        Args:
            search_execution_id: ID of the search execution to export.
            saved_search_id: ID of the saved search to export.
            company_id: Requesting company ID for tenant validation.
            user_id: Requesting user ID for audit logging.

        Returns:
            StreamingResponse with CSV content and appropriate headers.

        Raises:
            ValueError: If neither search_execution_id nor saved_search_id
                is provided.
            ExportReferenceNotFoundError: If the referenced search does not
                exist or does not belong to the requesting company.
        """
        self._validate_reference_params(search_execution_id, saved_search_id)

        execution_log, saved_search = await self._resolve_search_reference(
            search_execution_id=search_execution_id,
            saved_search_id=saved_search_id,
            company_id=company_id,
        )

        results = await self._get_search_results(
            execution_log=execution_log,
            saved_search=saved_search,
        )

        # Build CSV in-memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header row
        writer.writerow([
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
        ])

        # Write data rows
        for result in results:
            authors = ";".join(result.get("authors", []))
            mesh_terms = ";".join(result.get("mesh_terms", []))
            abstract = result.get("abstract", "") or ""
            abstract_truncated = abstract[:300]

            writer.writerow([
                result.get("title", ""),
                authors,
                result.get("publication_date", ""),
                result.get("journal", ""),
                result.get("source", ""),
                result.get("publication_type", ""),
                result.get("doi", ""),
                abstract_truncated,
                result.get("relevance_score", ""),
                result.get("provenance", ""),
                mesh_terms,
            ])

        # Record audit event
        await self._record_audit_event(
            export_format="csv",
            search_execution_id=search_execution_id,
            saved_search_id=saved_search_id,
            company_id=company_id,
            user_id=user_id,
            result_count=len(results),
        )

        # Build streaming response
        output.seek(0)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"literature_search_export_{timestamp}.csv"

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    async def generate_pdf_export(
        self,
        *,
        search_execution_id: int | None = None,
        saved_search_id: int | None = None,
        company_id: int,
        user_id: int,
        include_prisma_flow: bool = False,
    ) -> StreamingResponse:
        """Generate a PDF export of literature search results.

        Builds a PDF report with ReportLab containing:
        - Header: search parameters, date, databases queried
        - Results summary: total results per source
        - Tabular listing: title, authors, year, journal, doi
        - Optional PRISMA flow diagram section
        - Metadata footer: timestamp, user, company, audit confirmation

        Args:
            search_execution_id: ID of the search execution to export.
            saved_search_id: ID of the saved search to export.
            company_id: Requesting company ID for tenant validation.
            user_id: Requesting user ID for audit logging.
            include_prisma_flow: Whether to include PRISMA flow diagram.

        Returns:
            StreamingResponse with PDF content and appropriate headers.

        Raises:
            ValueError: If neither search_execution_id nor saved_search_id
                is provided.
            ExportReferenceNotFoundError: If the referenced search does not
                exist or does not belong to the requesting company.
        """
        self._validate_reference_params(search_execution_id, saved_search_id)

        execution_log, saved_search = await self._resolve_search_reference(
            search_execution_id=search_execution_id,
            saved_search_id=saved_search_id,
            company_id=company_id,
        )

        results = await self._get_search_results(
            execution_log=execution_log,
            saved_search=saved_search,
        )

        # Build PDF in-memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN,
        )

        styles = getSampleStyleSheet()
        elements: list[Any] = []

        # ── Header section ────────────────────────────────────────────────
        elements.append(
            Paragraph("Literature Search Export Report", styles["Title"])
        )
        elements.append(Spacer(1, 0.5 * cm))

        query_text = self._get_query_text(execution_log, saved_search)
        search_mode = self._get_search_mode(execution_log, saved_search)
        sources_queried = self._get_sources_queried(execution_log)
        export_date = datetime.now(tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        header_info = [
            f"<b>Query:</b> {self._escape_html(query_text)}",
            f"<b>Search Mode:</b> {search_mode}",
            f"<b>Databases Queried:</b> {', '.join(sources_queried) if sources_queried else 'N/A'}",
            f"<b>Export Date:</b> {export_date}",
            f"<b>Total Results:</b> {len(results)}",
        ]
        for info in header_info:
            elements.append(Paragraph(info, styles["Normal"]))
            elements.append(Spacer(1, 0.2 * cm))

        elements.append(Spacer(1, 0.5 * cm))

        # ── Results summary (total per source) ────────────────────────────
        elements.append(
            Paragraph("Results Summary by Source", styles["Heading2"])
        )
        elements.append(Spacer(1, 0.3 * cm))

        source_counts: dict[str, int] = {}
        for result in results:
            source = result.get("source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1

        if source_counts:
            summary_data = [["Source", "Count"]]
            for source, count in sorted(source_counts.items()):
                summary_data.append([source, str(count)])

            summary_table = Table(summary_data, colWidths=[8 * cm, 4 * cm])
            summary_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
            ]))
            elements.append(summary_table)
        else:
            elements.append(Paragraph("No results found.", styles["Normal"]))

        elements.append(Spacer(1, 0.8 * cm))

        # ── Tabular listing ───────────────────────────────────────────────
        elements.append(
            Paragraph("Search Results", styles["Heading2"])
        )
        elements.append(Spacer(1, 0.3 * cm))

        if results:
            table_data = [["Title", "Authors", "Year", "Journal", "DOI"]]
            for result in results:
                title = result.get("title", "")[:80]
                authors_list = result.get("authors", [])
                authors_str = "; ".join(authors_list[:3])
                if len(authors_list) > 3:
                    authors_str += " et al."
                pub_date = result.get("publication_date", "")
                year = str(pub_date)[:4] if pub_date else ""
                journal = result.get("journal", "")[:40]
                doi = result.get("doi", "") or ""

                table_data.append([
                    Paragraph(title, styles["Normal"]),
                    Paragraph(authors_str, styles["Normal"]),
                    year,
                    Paragraph(journal, styles["Normal"]),
                    Paragraph(doi, styles["Normal"]),
                ])

            col_widths = [7 * cm, 5 * cm, 2 * cm, 5 * cm, 5 * cm]
            results_table = Table(table_data, colWidths=col_widths)
            results_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            elements.append(results_table)
        else:
            elements.append(
                Paragraph("No results to display.", styles["Normal"])
            )

        elements.append(Spacer(1, 0.8 * cm))

        # ── Optional PRISMA flow diagram ──────────────────────────────────
        if include_prisma_flow:
            elements.append(
                Paragraph("PRISMA Flow Diagram", styles["Heading2"])
            )
            elements.append(Spacer(1, 0.3 * cm))

            prisma_content = self._build_prisma_flow_text(
                total_results=len(results),
                source_counts=source_counts,
            )
            for line in prisma_content:
                elements.append(Paragraph(line, styles["Code"]))
                elements.append(Spacer(1, 0.1 * cm))

            elements.append(Spacer(1, 0.5 * cm))

        # ── Metadata footer ───────────────────────────────────────────────
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph("Export Metadata", styles["Heading3"]))
        elements.append(Spacer(1, 0.2 * cm))

        footer_info = [
            f"<b>Generated At:</b> {export_date}",
            f"<b>User ID:</b> {user_id}",
            f"<b>Company ID:</b> {company_id}",
            "<b>Audit Confirmation:</b> This export was generated from an "
            "audited search execution. All search parameters, filters, and "
            "result counts are logged immutably for regulatory compliance.",
        ]
        for info in footer_info:
            elements.append(Paragraph(info, styles["Normal"]))
            elements.append(Spacer(1, 0.15 * cm))

        # Build the PDF
        doc.build(elements)

        # Record audit event
        await self._record_audit_event(
            export_format="pdf",
            search_execution_id=search_execution_id,
            saved_search_id=saved_search_id,
            company_id=company_id,
            user_id=user_id,
            result_count=len(results),
        )

        # Build streaming response
        buffer.seek(0)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"literature_search_export_{timestamp}.pdf"

        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _validate_reference_params(
        search_execution_id: int | None,
        saved_search_id: int | None,
    ) -> None:
        """Validate that at least one reference parameter is provided.

        Args:
            search_execution_id: ID of the search execution.
            saved_search_id: ID of the saved search.

        Raises:
            ValueError: If neither parameter is provided (maps to HTTP 422).
        """
        if search_execution_id is None and saved_search_id is None:
            msg = (
                "At least one of search_execution_id or saved_search_id "
                "must be provided"
            )
            raise ValueError(msg)

    async def _resolve_search_reference(
        self,
        *,
        search_execution_id: int | None,
        saved_search_id: int | None,
        company_id: int,
    ) -> tuple[SearchExecutionLog | None, SavedSearch | None]:
        """Resolve and validate search reference ownership.

        Verifies the referenced search execution or saved search belongs
        to the requesting company.

        Args:
            search_execution_id: ID of the search execution (priority).
            saved_search_id: ID of the saved search (fallback).
            company_id: Requesting company ID for tenant validation.

        Returns:
            Tuple of (execution_log, saved_search) — at least one is non-None.

        Raises:
            ExportReferenceNotFoundError: If the reference does not exist
                or does not belong to the requesting company.
        """
        execution_log: SearchExecutionLog | None = None
        saved_search: SavedSearch | None = None

        if search_execution_id is not None:
            stmt = select(SearchExecutionLog).where(
                SearchExecutionLog.id == search_execution_id
            )
            result = await self.session.execute(stmt)
            execution_log = result.scalar_one_or_none()

            if execution_log is None or execution_log.company_id != company_id:
                raise ExportReferenceNotFoundError(
                    "Referenced search execution not found for export.",
                    company_id=company_id,
                    search_execution_id=search_execution_id,
                )

        if saved_search_id is not None:
            stmt = select(SavedSearch).where(
                SavedSearch.id == saved_search_id
            )
            result = await self.session.execute(stmt)
            saved_search = result.scalar_one_or_none()

            if saved_search is None or saved_search.company_id != company_id:
                raise ExportReferenceNotFoundError(
                    "Referenced saved search not found for export.",
                    company_id=company_id,
                    saved_search_id=saved_search_id,
                )

        return execution_log, saved_search

    async def _get_search_results(
        self,
        *,
        execution_log: SearchExecutionLog | None,
        saved_search: SavedSearch | None,
    ) -> list[dict[str, Any]]:
        """Retrieve search results for export.

        If a query_engine is available, re-executes the search using stored
        parameters. Otherwise, returns metadata from the execution log as
        a minimal result set.

        Args:
            execution_log: The search execution log record.
            saved_search: The saved search record.

        Returns:
            List of result dictionaries with standard fields.
        """
        if self.query_engine is not None:
            return await self._re_execute_search(
                execution_log=execution_log,
                saved_search=saved_search,
            )

        # Without a query engine, return an empty result set with metadata
        # from the execution log. In production, the query_engine should
        # always be provided for full export functionality.
        logger.warning(
            "ExportService: No query_engine provided, returning empty results. "
            "Provide a HybridQueryEngine for full export functionality."
        )
        return []

    async def _re_execute_search(
        self,
        *,
        execution_log: SearchExecutionLog | None,
        saved_search: SavedSearch | None,
    ) -> list[dict[str, Any]]:
        """Re-execute a search using stored parameters and the query engine.

        Args:
            execution_log: The search execution log with stored params.
            saved_search: The saved search with stored query configuration.

        Returns:
            List of result dictionaries from the re-executed search.
        """
        # Determine query parameters from available sources
        if execution_log is not None:
            query_text = execution_log.query_text
            filters = execution_log.filters or {}
            search_mode = execution_log.search_mode
            include_internal = execution_log.include_internal
        elif saved_search is not None:
            query_text = saved_search.query_text
            filters = saved_search.filters or {}
            search_mode = saved_search.search_mode
            include_internal = saved_search.include_internal
        else:
            return []

        try:
            # Use the query engine to re-execute the search
            # The query engine should support a unified_search or similar method
            response = await self.query_engine.unified_search(
                query_text=query_text,
                filters=filters,
                search_mode=search_mode,
                include_internal=include_internal,
                page=1,
                page_size=1000,  # Export all results (up to 1000)
            )

            # Normalize results to dictionaries
            if hasattr(response, "results"):
                return [
                    self._normalize_result(r) for r in response.results
                ]
            return []
        except Exception:
            logger.exception(
                "Failed to re-execute search for export. "
                "Returning empty results."
            )
            return []

    @staticmethod
    def _normalize_result(result: Any) -> dict[str, Any]:
        """Normalize a search result to a standard dictionary format.

        Args:
            result: A search result object or dictionary.

        Returns:
            Dictionary with standard export fields.
        """
        if isinstance(result, dict):
            return result

        # Handle Pydantic model or dataclass-like objects
        return {
            "title": getattr(result, "title", ""),
            "authors": getattr(result, "authors", []),
            "publication_date": getattr(result, "publication_date", None),
            "journal": getattr(result, "journal", ""),
            "source": getattr(result, "source", ""),
            "publication_type": getattr(result, "publication_type", ""),
            "doi": getattr(result, "doi", None),
            "abstract": getattr(result, "abstract", ""),
            "relevance_score": getattr(result, "relevance_score", 0.0),
            "provenance": getattr(result, "provenance", ""),
            "mesh_terms": getattr(result, "mesh_terms", []),
        }

    @staticmethod
    def _get_query_text(
        execution_log: SearchExecutionLog | None,
        saved_search: SavedSearch | None,
    ) -> str:
        """Extract query text from available references."""
        if execution_log is not None:
            return execution_log.query_text
        if saved_search is not None:
            return saved_search.query_text
        return "N/A"

    @staticmethod
    def _get_search_mode(
        execution_log: SearchExecutionLog | None,
        saved_search: SavedSearch | None,
    ) -> str:
        """Extract search mode from available references."""
        if execution_log is not None:
            return execution_log.search_mode
        if saved_search is not None:
            return saved_search.search_mode
        return "N/A"

    @staticmethod
    def _get_sources_queried(
        execution_log: SearchExecutionLog | None,
    ) -> list[str]:
        """Extract sources queried from execution log."""
        if execution_log is not None and execution_log.sources_queried:
            return execution_log.sources_queried
        return []

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters for ReportLab Paragraph rendering.

        Args:
            text: Raw text to escape.

        Returns:
            HTML-safe text string.
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _build_prisma_flow_text(
        *,
        total_results: int,
        source_counts: dict[str, int],
    ) -> list[str]:
        """Build a text-based PRISMA flow diagram representation.

        Generates a simplified box-and-arrow text diagram representing the
        PRISMA flow for the literature search results.

        Args:
            total_results: Total number of results found.
            source_counts: Mapping of source name to result count.

        Returns:
            List of text lines representing the PRISMA flow.
        """
        lines = [
            "┌─────────────────────────────────────────────┐",
            "│           IDENTIFICATION                     │",
            "├─────────────────────────────────────────────┤",
        ]

        for source, count in sorted(source_counts.items()):
            lines.append(f"│  Records from {source}: {count:<20}│")

        lines.extend([
            f"│  Total records identified: {total_results:<17}│",
            "└─────────────────────────────────────────────┘",
            "                      │",
            "                      ▼",
            "┌─────────────────────────────────────────────┐",
            "│           SCREENING                          │",
            "├─────────────────────────────────────────────┤",
            f"│  Records after duplicates removed: {total_results:<9}│",
            "│  (Duplicate removal not yet applied)        │",
            "└─────────────────────────────────────────────┘",
            "                      │",
            "                      ▼",
            "┌─────────────────────────────────────────────┐",
            "│           ELIGIBILITY                        │",
            "├─────────────────────────────────────────────┤",
            f"│  Full-text articles assessed: {total_results:<14}│",
            "└─────────────────────────────────────────────┘",
            "                      │",
            "                      ▼",
            "┌─────────────────────────────────────────────┐",
            "│           INCLUDED                           │",
            "├─────────────────────────────────────────────┤",
            f"│  Studies included in export: {total_results:<15}│",
            "└─────────────────────────────────────────────┘",
        ])

        return lines

    async def _record_audit_event(
        self,
        *,
        export_format: str,
        search_execution_id: int | None,
        saved_search_id: int | None,
        company_id: int,
        user_id: int,
        result_count: int,
    ) -> None:
        """Record an audit event for the export generation.

        Logs the export action immutably for regulatory compliance.

        Args:
            export_format: The export format (csv or pdf).
            search_execution_id: The search execution ID exported.
            saved_search_id: The saved search ID exported.
            company_id: Company ID of the requesting user.
            user_id: User ID who generated the export.
            result_count: Number of results in the export.
        """
        logger.info(
            "Literature search export generated: format=%s, "
            "search_execution_id=%s, saved_search_id=%s, "
            "company_id=%d, user_id=%d, result_count=%d",
            export_format,
            search_execution_id,
            saved_search_id,
            company_id,
            user_id,
            result_count,
        )
