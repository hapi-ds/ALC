"""Coverage Metrics Service for AI-Powered Traceability & Gap Discovery.

Computes coverage metrics, compliance readiness scores, persists immutable
coverage snapshots, and provides aggregated coverage queries for the
traceability dashboard.

The compliance_readiness_score formula:
    final = (coverage_percentage × 0.40)
          + (link_quality_score × 0.25)
          + (orphan_penalty × 0.20)
          + (completeness_score × 0.15)

Where:
    link_quality_score = average_link_confidence × 100
    orphan_penalty = max(0, 100 - (orphan_requirements_count × 5)
                                 - (orphan_test_cases_count × 3))
    completeness_score = 100 if all source docs have ≥1 requirement extracted
                         AND all target docs have ≥1 test case extracted,
                         otherwise (documents_with_extractions / total_documents × 100)

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 5.4, 10.8
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, func, select

from alcoabase.models.traceability import CoverageSnapshot, TraceabilityMatrix

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.schemas.traceability import HistoryFilters
    from alcoabase.services.traceability_matrix import (
        CandidateLink,
        ExtractedRequirement,
        ExtractedTestCase,
    )

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Pure Computation Functions (testable without DB)
# ─────────────────────────────────────────────────────────────────────────────

# Minimum link confidence for a requirement to be considered "covered"
_COVERAGE_CONFIDENCE_THRESHOLD = 0.5


def compute_coverage_metrics(
    requirements: list[ExtractedRequirement],
    test_cases: list[ExtractedTestCase],
    links: list[CandidateLink],
    source_docs: list[dict[str, Any]],
    target_docs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute coverage metrics from extraction and matching results.

    Calculates total requirements, covered requirements (those with at least
    one link with confidence >= 0.5), orphan counts, coverage percentage,
    linked test cases, average link confidence, and compliance readiness score.

    Args:
        requirements: List of extracted requirements from source documents.
        test_cases: List of extracted test cases from target documents.
        links: List of candidate links established during matching.
        source_docs: List of source document dicts (with "document_uuid" key).
        target_docs: List of target document dicts (with "document_uuid" key).

    Returns:
        Dictionary matching CoverageMetricSchema structure with keys:
            total_requirements, covered_requirements, orphan_requirements_count,
            coverage_percentage, total_test_cases, linked_test_cases,
            orphan_test_cases_count, average_link_confidence,
            compliance_readiness_score.
    """
    total_requirements = len(requirements)
    total_test_cases = len(test_cases)

    # Determine covered requirements: those with at least one link >= 0.5
    covered_requirement_ids: set[str] = set()
    for link in links:
        if link.link_confidence >= _COVERAGE_CONFIDENCE_THRESHOLD:
            covered_requirement_ids.add(link.requirement_id)

    covered_requirements = len(covered_requirement_ids)
    orphan_requirements_count = total_requirements - covered_requirements

    # Coverage percentage (Requirement 7.1)
    if total_requirements > 0:
        coverage_percentage = round(
            (covered_requirements / total_requirements) * 100, 2
        )
    else:
        coverage_percentage = 0.00

    # Determine linked test cases: those with at least one link >= 0.5
    linked_test_case_ids: set[str] = set()
    for link in links:
        if link.link_confidence >= _COVERAGE_CONFIDENCE_THRESHOLD:
            linked_test_case_ids.add(link.test_case_id)

    linked_test_cases = len(linked_test_case_ids)
    orphan_test_cases_count = total_test_cases - linked_test_cases

    # Average link confidence (Requirement 7.1)
    if links:
        average_link_confidence = round(
            sum(link.link_confidence for link in links) / len(links), 2
        )
    else:
        average_link_confidence = 0.00

    # Compute compliance readiness score (Requirement 7.2)
    # Determine which source docs had at least one requirement extracted
    source_doc_uuids_with_reqs: set[str] = {
        req.source_document_uuid for req in requirements
    }
    # Determine which target docs had at least one test case extracted
    target_doc_uuids_with_tcs: set[str] = {
        tc.target_document_uuid for tc in test_cases
    }

    source_docs_with_extractions = [
        doc
        for doc in source_docs
        if doc.get("document_uuid") in source_doc_uuids_with_reqs
    ]
    target_docs_with_extractions = [
        doc
        for doc in target_docs
        if doc.get("document_uuid") in target_doc_uuids_with_tcs
    ]

    total_docs = len(source_docs) + len(target_docs)

    metrics = {
        "total_requirements": total_requirements,
        "covered_requirements": covered_requirements,
        "orphan_requirements_count": orphan_requirements_count,
        "coverage_percentage": coverage_percentage,
        "total_test_cases": total_test_cases,
        "linked_test_cases": linked_test_cases,
        "orphan_test_cases_count": orphan_test_cases_count,
        "average_link_confidence": average_link_confidence,
    }

    compliance_score = compute_compliance_readiness_score(
        metrics=metrics,
        source_docs_with_extractions=source_docs_with_extractions,
        target_docs_with_extractions=target_docs_with_extractions,
        total_docs=total_docs,
    )
    metrics["compliance_readiness_score"] = compliance_score

    return metrics


def compute_compliance_readiness_score(
    metrics: dict[str, Any],
    source_docs_with_extractions: list[dict[str, Any]],
    target_docs_with_extractions: list[dict[str, Any]],
    total_docs: int,
) -> float:
    """Compute the compliance readiness score using the weighted formula.

    Formula:
        final = (coverage_percentage × 0.40)
              + (link_quality_score × 0.25)
              + (orphan_penalty × 0.20)
              + (completeness_score × 0.15)

    Where:
        link_quality_score = average_link_confidence × 100
        orphan_penalty = max(0, 100 - (orphan_requirements_count × 5)
                                     - (orphan_test_cases_count × 3))
        completeness_score = 100 if all docs have extractions,
                             else (docs_with_extractions / total_docs × 100)

    The final score is clamped to [0.0, 100.0].

    Args:
        metrics: Dictionary with coverage_percentage, average_link_confidence,
            orphan_requirements_count, and orphan_test_cases_count.
        source_docs_with_extractions: Source docs that had ≥1 requirement extracted.
        target_docs_with_extractions: Target docs that had ≥1 test case extracted.
        total_docs: Total number of source + target documents.

    Returns:
        Compliance readiness score clamped to [0.0, 100.0], rounded to 2 decimals.
    """
    coverage_percentage = metrics.get("coverage_percentage", 0.0)
    average_link_confidence = metrics.get("average_link_confidence", 0.0)
    orphan_requirements_count = metrics.get("orphan_requirements_count", 0)
    orphan_test_cases_count = metrics.get("orphan_test_cases_count", 0)

    # link_quality_score: average_link_confidence scaled to 0-100
    link_quality_score = average_link_confidence * 100

    # orphan_penalty: penalizes orphan items
    orphan_penalty = max(
        0,
        100 - (orphan_requirements_count * 5) - (orphan_test_cases_count * 3),
    )

    # completeness_score: 100 if all docs have extractions, else proportional
    docs_with_extractions = len(source_docs_with_extractions) + len(
        target_docs_with_extractions
    )

    if total_docs > 0 and docs_with_extractions >= total_docs:
        completeness_score = 100.0
    elif total_docs > 0:
        completeness_score = (docs_with_extractions / total_docs) * 100
    else:
        completeness_score = 0.0

    # Weighted composite
    score = (
        (coverage_percentage * 0.40)
        + (link_quality_score * 0.25)
        + (orphan_penalty * 0.20)
        + (completeness_score * 0.15)
    )

    # Clamp to [0.0, 100.0]
    score = max(0.0, min(100.0, score))

    return round(score, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Service Class (DB-dependent operations)
# ─────────────────────────────────────────────────────────────────────────────


class CoverageMetricsService:
    """Service for coverage metrics computation, persistence, and querying.

    Provides pure computation functions (usable without DB) and DB-backed
    operations for persisting snapshots and querying coverage history.

    Args:
        session_factory: SQLAlchemy async session factory for DB operations.
            Optional — pure computation methods work without it.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        """Initialize CoverageMetricsService.

        Args:
            session_factory: Async session factory for database operations.
                If None, only pure computation methods are available.
        """
        self._session_factory = session_factory

    # ───────────────────────────────────────────────────────────────────────
    # Pure Computation (delegates to module-level functions)
    # ───────────────────────────────────────────────────────────────────────

    def compute_coverage_metrics(
        self,
        requirements: list[ExtractedRequirement],
        test_cases: list[ExtractedTestCase],
        links: list[CandidateLink],
        source_docs: list[dict[str, Any]],
        target_docs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute coverage metrics from extraction and matching results.

        Delegates to the module-level compute_coverage_metrics function.
        See module-level docstring for full details.

        Args:
            requirements: List of extracted requirements.
            test_cases: List of extracted test cases.
            links: List of candidate links.
            source_docs: List of source document dicts.
            target_docs: List of target document dicts.

        Returns:
            Dictionary matching CoverageMetricSchema structure.
        """
        return compute_coverage_metrics(
            requirements=requirements,
            test_cases=test_cases,
            links=links,
            source_docs=source_docs,
            target_docs=target_docs,
        )

    def compute_compliance_readiness_score(
        self,
        metrics: dict[str, Any],
        source_docs_with_extractions: list[dict[str, Any]],
        target_docs_with_extractions: list[dict[str, Any]],
        total_docs: int,
    ) -> float:
        """Compute compliance readiness score.

        Delegates to the module-level compute_compliance_readiness_score function.
        See module-level docstring for full details.

        Args:
            metrics: Dictionary with coverage metrics.
            source_docs_with_extractions: Source docs with extractions.
            target_docs_with_extractions: Target docs with extractions.
            total_docs: Total number of documents.

        Returns:
            Compliance readiness score clamped to [0.0, 100.0].
        """
        return compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=source_docs_with_extractions,
            target_docs_with_extractions=target_docs_with_extractions,
            total_docs=total_docs,
        )

    # ───────────────────────────────────────────────────────────────────────
    # Persistence (Requirement 10.8)
    # ───────────────────────────────────────────────────────────────────────

    async def persist_coverage_snapshot(
        self,
        matrix_id: str,
        metrics: dict[str, Any],
        source_document_uuid: str,
        company_id: int,
    ) -> CoverageSnapshot | None:
        """Create an immutable CoverageSnapshot record.

        Validates that coverage_percentage and compliance_readiness_score
        are within [0.0, 100.0] before persisting. Rejects records with
        values outside this range.

        Args:
            matrix_id: UUID of the matrix that generated these metrics.
            metrics: Dictionary with coverage metric values.
            source_document_uuid: UUID of the source document.
            company_id: Company ID for tenant isolation.

        Returns:
            The created CoverageSnapshot, or None if validation fails
            or session_factory is not configured.

        Raises:
            ValueError: If coverage_percentage or compliance_readiness_score
                is outside [0.0, 100.0].
        """
        if self._session_factory is None:
            logger.warning(
                "Cannot persist coverage snapshot: session_factory not configured"
            )
            return None

        # Validate ranges before persist (Requirement 10.8)
        coverage_percentage = metrics.get("coverage_percentage", 0.0)
        compliance_readiness_score = metrics.get(
            "compliance_readiness_score", 0.0
        )

        if not (0.0 <= coverage_percentage <= 100.0):
            raise ValueError(
                f"coverage_percentage must be between 0.0 and 100.0, "
                f"got {coverage_percentage}"
            )

        if not (0.0 <= compliance_readiness_score <= 100.0):
            raise ValueError(
                f"compliance_readiness_score must be between 0.0 and 100.0, "
                f"got {compliance_readiness_score}"
            )

        snapshot = CoverageSnapshot(
            matrix_id=matrix_id,
            source_document_uuid=source_document_uuid,
            coverage_percentage=coverage_percentage,
            orphan_requirements_count=metrics.get(
                "orphan_requirements_count", 0
            ),
            orphan_test_cases_count=metrics.get("orphan_test_cases_count", 0),
            compliance_readiness_score=compliance_readiness_score,
            total_requirements=metrics.get("total_requirements", 0),
            covered_requirements=metrics.get("covered_requirements", 0),
            total_test_cases=metrics.get("total_test_cases", 0),
            linked_test_cases=metrics.get("linked_test_cases", 0),
            snapshot_date=datetime.now(timezone.utc),
            company_id=company_id,
        )

        async with self._session_factory() as session:
            session.add(snapshot)
            await session.commit()
            await session.refresh(snapshot)

        logger.info(
            "Persisted coverage snapshot for matrix %s, document %s "
            "(coverage=%.2f%%, compliance=%.2f)",
            matrix_id,
            source_document_uuid,
            coverage_percentage,
            compliance_readiness_score,
        )

        return snapshot

    # ───────────────────────────────────────────────────────────────────────
    # Coverage Summary (Requirement 7.3, 7.4)
    # ───────────────────────────────────────────────────────────────────────

    async def get_coverage_summary(
        self,
        company_id: int,
    ) -> dict[str, Any]:
        """Aggregate coverage across all non-deleted matrices for a company.

        Computes total matrices generated, latest matrix date, average coverage
        percentage, total orphan counts, and average compliance readiness score
        from the most recent CoverageSnapshot per source document.

        Args:
            company_id: Company ID for tenant isolation.

        Returns:
            Dictionary matching CoverageSummaryResponse structure with keys:
                total_matrices_generated, latest_matrix_date,
                average_coverage_percentage, total_orphan_requirements,
                total_orphan_test_cases, average_compliance_readiness_score,
                breakdown.
        """
        if self._session_factory is None:
            return _empty_coverage_summary()

        async with self._session_factory() as session:
            # Count non-deleted matrices
            count_stmt = select(func.count(TraceabilityMatrix.id)).where(
                TraceabilityMatrix.company_id == company_id,
                TraceabilityMatrix.deleted_at.is_(None),
            )
            total_matrices = (
                await session.execute(count_stmt)
            ).scalar_one_or_none() or 0

            if total_matrices == 0:
                return _empty_coverage_summary()

            # Latest matrix date
            latest_date_stmt = select(
                func.max(TraceabilityMatrix.generation_timestamp)
            ).where(
                TraceabilityMatrix.company_id == company_id,
                TraceabilityMatrix.deleted_at.is_(None),
            )
            latest_matrix_date = (
                await session.execute(latest_date_stmt)
            ).scalar_one_or_none()

            # Get the latest snapshot per source document using a subquery
            # to find the most recent snapshot_date per source_document_uuid
            latest_snapshot_subq = (
                select(
                    CoverageSnapshot.source_document_uuid,
                    func.max(CoverageSnapshot.snapshot_date).label(
                        "max_date"
                    ),
                )
                .where(CoverageSnapshot.company_id == company_id)
                .group_by(CoverageSnapshot.source_document_uuid)
                .subquery()
            )

            # Join to get the actual snapshot records
            latest_snapshots_stmt = select(CoverageSnapshot).join(
                latest_snapshot_subq,
                (
                    CoverageSnapshot.source_document_uuid
                    == latest_snapshot_subq.c.source_document_uuid
                )
                & (
                    CoverageSnapshot.snapshot_date
                    == latest_snapshot_subq.c.max_date
                ),
            ).where(CoverageSnapshot.company_id == company_id)

            result = await session.execute(latest_snapshots_stmt)
            latest_snapshots = list(result.scalars().all())

            if not latest_snapshots:
                return {
                    "total_matrices_generated": total_matrices,
                    "latest_matrix_date": latest_matrix_date,
                    "average_coverage_percentage": 0.0,
                    "total_orphan_requirements": 0,
                    "total_orphan_test_cases": 0,
                    "average_compliance_readiness_score": 0.0,
                    "breakdown": [],
                }

            # Aggregate metrics from latest snapshots
            total_orphan_requirements = sum(
                s.orphan_requirements_count for s in latest_snapshots
            )
            total_orphan_test_cases = sum(
                s.orphan_test_cases_count for s in latest_snapshots
            )
            avg_coverage = round(
                sum(s.coverage_percentage for s in latest_snapshots)
                / len(latest_snapshots),
                2,
            )
            avg_compliance = round(
                sum(s.compliance_readiness_score for s in latest_snapshots)
                / len(latest_snapshots),
                2,
            )

            # Build per-document breakdown
            breakdown = [
                {
                    "document_uuid": s.source_document_uuid,
                    "document_name": s.source_document_uuid,
                    "coverage_percentage": s.coverage_percentage,
                    "orphan_count": s.orphan_requirements_count,
                }
                for s in latest_snapshots[:200]
            ]

            return {
                "total_matrices_generated": total_matrices,
                "latest_matrix_date": latest_matrix_date,
                "average_coverage_percentage": avg_coverage,
                "total_orphan_requirements": total_orphan_requirements,
                "total_orphan_test_cases": total_orphan_test_cases,
                "average_compliance_readiness_score": avg_compliance,
                "breakdown": breakdown,
            }

    # ───────────────────────────────────────────────────────────────────────
    # Coverage History (Requirement 7.5)
    # ───────────────────────────────────────────────────────────────────────

    async def get_coverage_history(
        self,
        company_id: int,
        filters: HistoryFilters | None = None,
    ) -> dict[str, Any]:
        """Return paginated CoverageSnapshots sorted by snapshot_date descending.

        Args:
            company_id: Company ID for tenant isolation.
            filters: Optional filters for source_document_uuid, date range,
                and pagination (limit/offset).

        Returns:
            Dictionary with "snapshots" (list of snapshot dicts) and
            "total_count" (int).
        """
        if self._session_factory is None:
            return {"snapshots": [], "total_count": 0}

        # Default pagination
        limit = 20
        offset = 0
        source_document_uuid = None
        start_date = None
        end_date = None

        if filters is not None:
            limit = filters.limit
            offset = filters.offset
            source_document_uuid = filters.source_document_uuid
            start_date = filters.start_date
            end_date = filters.end_date

        async with self._session_factory() as session:
            # Build base query conditions
            conditions = [CoverageSnapshot.company_id == company_id]

            if source_document_uuid:
                conditions.append(
                    CoverageSnapshot.source_document_uuid
                    == source_document_uuid
                )
            if start_date:
                conditions.append(
                    CoverageSnapshot.snapshot_date >= start_date
                )
            if end_date:
                conditions.append(
                    CoverageSnapshot.snapshot_date <= end_date
                )

            # Count total
            count_stmt = select(func.count(CoverageSnapshot.id)).where(
                *conditions
            )
            total_count = (
                await session.execute(count_stmt)
            ).scalar_one_or_none() or 0

            # Fetch paginated results
            query_stmt = (
                select(CoverageSnapshot)
                .where(*conditions)
                .order_by(desc(CoverageSnapshot.snapshot_date))
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(query_stmt)
            snapshots = list(result.scalars().all())

            return {
                "snapshots": snapshots,
                "total_count": total_count,
            }

    # ───────────────────────────────────────────────────────────────────────
    # Document Coverage (Requirement 5.4, 7.6)
    # ───────────────────────────────────────────────────────────────────────

    async def get_document_coverage(
        self,
        document_uuid: str,
        company_id: int,
    ) -> dict[str, Any]:
        """Return latest coverage for a document as source.

        Queries the most recent CoverageSnapshot for the given document UUID
        within the company scope.

        Args:
            document_uuid: UUID of the document to query coverage for.
            company_id: Company ID for tenant isolation.

        Returns:
            Dictionary matching DocumentCoverageResponse structure with keys:
                document_uuid, latest_matrix_id, latest_matrix_date,
                coverage_percentage, orphan_requirement_count,
                total_requirements, compliance_readiness_score.
            Returns null values for coverage fields if the document has never
            been included in a matrix as a source.
        """
        if self._session_factory is None:
            return _empty_document_coverage(document_uuid)

        async with self._session_factory() as session:
            # Find the latest snapshot for this document
            stmt = (
                select(CoverageSnapshot)
                .where(
                    CoverageSnapshot.source_document_uuid == document_uuid,
                    CoverageSnapshot.company_id == company_id,
                )
                .order_by(desc(CoverageSnapshot.snapshot_date))
                .limit(1)
            )
            result = await session.execute(stmt)
            snapshot = result.scalar_one_or_none()

            if snapshot is None:
                return _empty_document_coverage(document_uuid)

            return {
                "document_uuid": document_uuid,
                "latest_matrix_id": snapshot.matrix_id,
                "latest_matrix_date": snapshot.snapshot_date,
                "coverage_percentage": snapshot.coverage_percentage,
                "orphan_requirement_count": snapshot.orphan_requirements_count,
                "total_requirements": snapshot.total_requirements,
                "compliance_readiness_score": snapshot.compliance_readiness_score,
            }


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


def _empty_coverage_summary() -> dict[str, Any]:
    """Return an empty coverage summary with zero values.

    Returns:
        Dictionary matching CoverageSummaryResponse with all zero/null values.
    """
    return {
        "total_matrices_generated": 0,
        "latest_matrix_date": None,
        "average_coverage_percentage": 0.0,
        "total_orphan_requirements": 0,
        "total_orphan_test_cases": 0,
        "average_compliance_readiness_score": 0.0,
        "breakdown": [],
    }


def _empty_document_coverage(document_uuid: str) -> dict[str, Any]:
    """Return empty document coverage with null values.

    Args:
        document_uuid: UUID of the document.

    Returns:
        Dictionary matching DocumentCoverageResponse with null coverage fields.
    """
    return {
        "document_uuid": document_uuid,
        "latest_matrix_id": None,
        "latest_matrix_date": None,
        "coverage_percentage": None,
        "orphan_requirement_count": 0,
        "total_requirements": 0,
        "compliance_readiness_score": None,
    }
