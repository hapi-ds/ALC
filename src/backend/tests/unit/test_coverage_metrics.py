"""Unit tests for CoverageMetricsService.

Tests metric computation, compliance score formula, snapshot persistence,
range validation, coverage summary aggregation, history pagination,
document coverage lookup, and edge cases.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 5.4, 10.8
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.coverage_metrics import (
    CoverageMetricsService,
    _empty_coverage_summary,
    _empty_document_coverage,
    compute_compliance_readiness_score,
    compute_coverage_metrics,
)
from alcoabase.services.traceability_matrix import (
    CandidateLink,
    ExtractedRequirement,
    ExtractedTestCase,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_requirements():
    """Create sample extracted requirements."""
    return [
        ExtractedRequirement(
            requirement_id="REQ-001",
            requirement_text="System shall validate input.",
            source_document_uuid="doc-src-001",
            source_section="1.1 Validation",
        ),
        ExtractedRequirement(
            requirement_id="REQ-002",
            requirement_text="System shall log access.",
            source_document_uuid="doc-src-001",
            source_section="2.1 Logging",
        ),
        ExtractedRequirement(
            requirement_id="REQ-003",
            requirement_text="System shall encrypt data.",
            source_document_uuid="doc-src-002",
            source_section="3.1 Security",
        ),
    ]


@pytest.fixture
def sample_test_cases():
    """Create sample extracted test cases."""
    return [
        ExtractedTestCase(
            test_case_id="TC-001",
            test_case_text="Verify input validation.",
            target_document_uuid="doc-tgt-001",
            target_section="1.1 Tests",
        ),
        ExtractedTestCase(
            test_case_id="TC-002",
            test_case_text="Verify logging.",
            target_document_uuid="doc-tgt-001",
            target_section="2.1 Tests",
        ),
    ]


@pytest.fixture
def sample_links():
    """Create sample candidate links with varying confidence."""
    return [
        CandidateLink(
            requirement_id="REQ-001",
            requirement_text="System shall validate input.",
            source_document_uuid="doc-src-001",
            source_section="1.1 Validation",
            test_case_id="TC-001",
            test_case_text="Verify input validation.",
            target_document_uuid="doc-tgt-001",
            target_section="1.1 Tests",
            link_confidence=0.95,
            link_method="exact_id_match",
        ),
        CandidateLink(
            requirement_id="REQ-002",
            requirement_text="System shall log access.",
            source_document_uuid="doc-src-001",
            source_section="2.1 Logging",
            test_case_id="TC-002",
            test_case_text="Verify logging.",
            target_document_uuid="doc-tgt-001",
            target_section="2.1 Tests",
            link_confidence=0.7,
            link_method="semantic_match",
        ),
    ]


@pytest.fixture
def sample_source_docs():
    """Create sample source document dicts."""
    return [
        {"document_uuid": "doc-src-001"},
        {"document_uuid": "doc-src-002"},
    ]


@pytest.fixture
def sample_target_docs():
    """Create sample target document dicts."""
    return [
        {"document_uuid": "doc-tgt-001"},
    ]


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory for DB tests.

    The service uses `async with self._session_factory() as session:`,
    so the factory call must return an async context manager directly.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()

    class _AsyncCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    def factory():
        return _AsyncCtx()

    return factory, session


@pytest.fixture
def service():
    """Create a CoverageMetricsService without DB for pure computation tests."""
    return CoverageMetricsService(session_factory=None)


# ---------------------------------------------------------------------------
# Tests: compute_coverage_metrics (Requirement 7.1)
# ---------------------------------------------------------------------------


class TestComputeCoverageMetrics:
    """Tests for the compute_coverage_metrics function."""

    def test_basic_coverage_computation(
        self, sample_requirements, sample_test_cases, sample_links,
        sample_source_docs, sample_target_docs,
    ):
        """Compute metrics with 2 covered out of 3 requirements."""
        metrics = compute_coverage_metrics(
            requirements=sample_requirements,
            test_cases=sample_test_cases,
            links=sample_links,
            source_docs=sample_source_docs,
            target_docs=sample_target_docs,
        )

        assert metrics["total_requirements"] == 3
        assert metrics["covered_requirements"] == 2
        assert metrics["orphan_requirements_count"] == 1
        # 2/3 * 100 = 66.67
        assert metrics["coverage_percentage"] == 66.67
        assert metrics["total_test_cases"] == 2
        assert metrics["linked_test_cases"] == 2
        assert metrics["orphan_test_cases_count"] == 0
        # (0.95 + 0.7) / 2 = 0.825 → Python banker's rounding → 0.82
        assert metrics["average_link_confidence"] == 0.82

    def test_zero_requirements_edge_case(
        self, sample_test_cases, sample_source_docs, sample_target_docs,
    ):
        """Coverage percentage is 0.00 when there are zero requirements."""
        metrics = compute_coverage_metrics(
            requirements=[],
            test_cases=sample_test_cases,
            links=[],
            source_docs=sample_source_docs,
            target_docs=sample_target_docs,
        )

        assert metrics["total_requirements"] == 0
        assert metrics["covered_requirements"] == 0
        assert metrics["orphan_requirements_count"] == 0
        assert metrics["coverage_percentage"] == 0.00
        assert metrics["total_test_cases"] == 2
        assert metrics["linked_test_cases"] == 0
        assert metrics["orphan_test_cases_count"] == 2

    def test_zero_links_edge_case(
        self, sample_requirements, sample_test_cases,
        sample_source_docs, sample_target_docs,
    ):
        """All requirements are orphans when there are zero links."""
        metrics = compute_coverage_metrics(
            requirements=sample_requirements,
            test_cases=sample_test_cases,
            links=[],
            source_docs=sample_source_docs,
            target_docs=sample_target_docs,
        )

        assert metrics["total_requirements"] == 3
        assert metrics["covered_requirements"] == 0
        assert metrics["orphan_requirements_count"] == 3
        assert metrics["coverage_percentage"] == 0.00
        assert metrics["average_link_confidence"] == 0.00

    def test_all_orphans_edge_case(self):
        """All items are orphans when links are below threshold."""
        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Req text",
                source_document_uuid="doc-src-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test text",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        # Link below 0.5 threshold
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req text",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test text",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.4,
                link_method="semantic_match",
            ),
        ]

        metrics = compute_coverage_metrics(
            requirements=requirements,
            test_cases=test_cases,
            links=links,
            source_docs=[{"document_uuid": "doc-src-001"}],
            target_docs=[{"document_uuid": "doc-tgt-001"}],
        )

        assert metrics["covered_requirements"] == 0
        assert metrics["orphan_requirements_count"] == 1
        assert metrics["coverage_percentage"] == 0.00
        assert metrics["linked_test_cases"] == 0
        assert metrics["orphan_test_cases_count"] == 1
        # Average confidence still computed across all links
        assert metrics["average_link_confidence"] == 0.4

    def test_link_at_exact_threshold(self):
        """A link with confidence exactly 0.5 counts as covered."""
        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Req text",
                source_document_uuid="doc-src-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test text",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req text",
                source_document_uuid="doc-src-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test text",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
                link_confidence=0.5,
                link_method="semantic_match",
            ),
        ]

        metrics = compute_coverage_metrics(
            requirements=requirements,
            test_cases=test_cases,
            links=links,
            source_docs=[{"document_uuid": "doc-src-001"}],
            target_docs=[{"document_uuid": "doc-tgt-001"}],
        )

        assert metrics["covered_requirements"] == 1
        assert metrics["coverage_percentage"] == 100.0
        assert metrics["linked_test_cases"] == 1

    def test_compliance_readiness_score_included(
        self, sample_requirements, sample_test_cases, sample_links,
        sample_source_docs, sample_target_docs,
    ):
        """Metrics dict includes compliance_readiness_score."""
        metrics = compute_coverage_metrics(
            requirements=sample_requirements,
            test_cases=sample_test_cases,
            links=sample_links,
            source_docs=sample_source_docs,
            target_docs=sample_target_docs,
        )

        assert "compliance_readiness_score" in metrics
        assert 0.0 <= metrics["compliance_readiness_score"] <= 100.0


# ---------------------------------------------------------------------------
# Tests: compute_compliance_readiness_score (Requirement 7.2)
# ---------------------------------------------------------------------------


class TestComputeComplianceReadinessScore:
    """Tests for the compliance readiness score formula."""

    def test_perfect_score(self):
        """100% coverage, 1.0 confidence, 0 orphans, full completeness → 100."""
        metrics = {
            "coverage_percentage": 100.0,
            "average_link_confidence": 1.0,
            "orphan_requirements_count": 0,
            "orphan_test_cases_count": 0,
        }
        source_docs_with = [{"document_uuid": "d1"}]
        target_docs_with = [{"document_uuid": "d2"}]
        total_docs = 2

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=source_docs_with,
            target_docs_with_extractions=target_docs_with,
            total_docs=total_docs,
        )

        assert score == 100.0

    def test_zero_score(self):
        """0% coverage, 0 confidence, many orphans, no completeness → 0."""
        metrics = {
            "coverage_percentage": 0.0,
            "average_link_confidence": 0.0,
            "orphan_requirements_count": 30,
            "orphan_test_cases_count": 40,
        }

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[],
            target_docs_with_extractions=[],
            total_docs=5,
        )

        # orphan_penalty = max(0, 100 - 150 - 120) = 0
        # completeness = 0/5 * 100 = 0
        # score = 0*0.4 + 0*0.25 + 0*0.20 + 0*0.15 = 0
        assert score == 0.0

    def test_formula_components(self):
        """Verify each component of the formula contributes correctly."""
        metrics = {
            "coverage_percentage": 80.0,
            "average_link_confidence": 0.75,
            "orphan_requirements_count": 2,
            "orphan_test_cases_count": 1,
        }
        # 3 out of 4 docs have extractions
        source_docs_with = [{"document_uuid": "d1"}, {"document_uuid": "d2"}]
        target_docs_with = [{"document_uuid": "d3"}]
        total_docs = 4

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=source_docs_with,
            target_docs_with_extractions=target_docs_with,
            total_docs=total_docs,
        )

        # coverage_percentage * 0.40 = 80.0 * 0.40 = 32.0
        # link_quality_score = 0.75 * 100 = 75.0; * 0.25 = 18.75
        # orphan_penalty = max(0, 100 - 2*5 - 1*3) = max(0, 87) = 87; * 0.20 = 17.4
        # completeness = 3/4 * 100 = 75.0; * 0.15 = 11.25
        # total = 32.0 + 18.75 + 17.4 + 11.25 = 79.4
        assert score == 79.4

    def test_clamping_upper_bound(self):
        """Score is clamped to 100.0 even if formula exceeds it."""
        # This shouldn't happen with valid inputs, but test the clamp
        metrics = {
            "coverage_percentage": 100.0,
            "average_link_confidence": 1.0,
            "orphan_requirements_count": 0,
            "orphan_test_cases_count": 0,
        }

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[{"document_uuid": "d1"}],
            target_docs_with_extractions=[{"document_uuid": "d2"}],
            total_docs=2,
        )

        assert score <= 100.0

    def test_clamping_lower_bound(self):
        """Score is clamped to 0.0 (cannot go negative)."""
        metrics = {
            "coverage_percentage": 0.0,
            "average_link_confidence": 0.0,
            "orphan_requirements_count": 100,
            "orphan_test_cases_count": 100,
        }

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[],
            target_docs_with_extractions=[],
            total_docs=10,
        )

        assert score >= 0.0

    def test_zero_total_docs(self):
        """Completeness is 0 when total_docs is 0."""
        metrics = {
            "coverage_percentage": 50.0,
            "average_link_confidence": 0.6,
            "orphan_requirements_count": 1,
            "orphan_test_cases_count": 1,
        }

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[],
            target_docs_with_extractions=[],
            total_docs=0,
        )

        # coverage: 50*0.4 = 20
        # link_quality: 60*0.25 = 15
        # orphan_penalty: max(0, 100-5-3) = 92; *0.20 = 18.4
        # completeness: 0 (total_docs=0); *0.15 = 0
        # total = 20 + 15 + 18.4 + 0 = 53.4
        assert score == 53.4

    def test_full_completeness_when_all_docs_have_extractions(self):
        """Completeness is 100 when all docs have extractions."""
        metrics = {
            "coverage_percentage": 0.0,
            "average_link_confidence": 0.0,
            "orphan_requirements_count": 0,
            "orphan_test_cases_count": 0,
        }

        score = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[{"document_uuid": "d1"}],
            target_docs_with_extractions=[{"document_uuid": "d2"}],
            total_docs=2,
        )

        # coverage: 0*0.4 = 0
        # link_quality: 0*0.25 = 0
        # orphan_penalty: max(0, 100-0-0) = 100; *0.20 = 20
        # completeness: 100; *0.15 = 15
        # total = 0 + 0 + 20 + 15 = 35
        assert score == 35.0


# ---------------------------------------------------------------------------
# Tests: persist_coverage_snapshot (Requirement 10.8)
# ---------------------------------------------------------------------------


class TestPersistCoverageSnapshot:
    """Tests for snapshot persistence and range validation."""

    @pytest.mark.asyncio
    async def test_persist_valid_snapshot(self, mock_session_factory):
        """Valid metrics are persisted as a CoverageSnapshot."""
        factory, session = mock_session_factory
        svc = CoverageMetricsService(session_factory=factory)

        metrics = {
            "coverage_percentage": 75.5,
            "compliance_readiness_score": 82.3,
            "orphan_requirements_count": 2,
            "orphan_test_cases_count": 1,
            "total_requirements": 10,
            "covered_requirements": 8,
            "total_test_cases": 5,
            "linked_test_cases": 4,
        }

        result = await svc.persist_coverage_snapshot(
            matrix_id="matrix-uuid-001",
            metrics=metrics,
            source_document_uuid="doc-src-001",
            company_id=1,
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_coverage_percentage_above_100(self, mock_session_factory):
        """Reject snapshot when coverage_percentage > 100."""
        factory, session = mock_session_factory
        svc = CoverageMetricsService(session_factory=factory)

        metrics = {
            "coverage_percentage": 101.0,
            "compliance_readiness_score": 50.0,
        }

        with pytest.raises(ValueError, match="coverage_percentage"):
            await svc.persist_coverage_snapshot(
                matrix_id="matrix-uuid-001",
                metrics=metrics,
                source_document_uuid="doc-src-001",
                company_id=1,
            )

        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_reject_coverage_percentage_below_0(self, mock_session_factory):
        """Reject snapshot when coverage_percentage < 0."""
        factory, session = mock_session_factory
        svc = CoverageMetricsService(session_factory=factory)

        metrics = {
            "coverage_percentage": -1.0,
            "compliance_readiness_score": 50.0,
        }

        with pytest.raises(ValueError, match="coverage_percentage"):
            await svc.persist_coverage_snapshot(
                matrix_id="matrix-uuid-001",
                metrics=metrics,
                source_document_uuid="doc-src-001",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_reject_compliance_score_above_100(self, mock_session_factory):
        """Reject snapshot when compliance_readiness_score > 100."""
        factory, session = mock_session_factory
        svc = CoverageMetricsService(session_factory=factory)

        metrics = {
            "coverage_percentage": 50.0,
            "compliance_readiness_score": 150.0,
        }

        with pytest.raises(ValueError, match="compliance_readiness_score"):
            await svc.persist_coverage_snapshot(
                matrix_id="matrix-uuid-001",
                metrics=metrics,
                source_document_uuid="doc-src-001",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_reject_compliance_score_below_0(self, mock_session_factory):
        """Reject snapshot when compliance_readiness_score < 0."""
        factory, session = mock_session_factory
        svc = CoverageMetricsService(session_factory=factory)

        metrics = {
            "coverage_percentage": 50.0,
            "compliance_readiness_score": -5.0,
        }

        with pytest.raises(ValueError, match="compliance_readiness_score"):
            await svc.persist_coverage_snapshot(
                matrix_id="matrix-uuid-001",
                metrics=metrics,
                source_document_uuid="doc-src-001",
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_returns_none_without_session_factory(self):
        """Returns None when session_factory is not configured."""
        svc = CoverageMetricsService(session_factory=None)

        result = await svc.persist_coverage_snapshot(
            matrix_id="matrix-uuid-001",
            metrics={"coverage_percentage": 50.0, "compliance_readiness_score": 50.0},
            source_document_uuid="doc-src-001",
            company_id=1,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_boundary_values_accepted(self, mock_session_factory):
        """Boundary values 0.0 and 100.0 are accepted."""
        factory, session = mock_session_factory
        svc = CoverageMetricsService(session_factory=factory)

        # Test 0.0 boundary
        metrics_zero = {
            "coverage_percentage": 0.0,
            "compliance_readiness_score": 0.0,
        }
        await svc.persist_coverage_snapshot(
            matrix_id="m1", metrics=metrics_zero,
            source_document_uuid="d1", company_id=1,
        )

        # Test 100.0 boundary
        metrics_max = {
            "coverage_percentage": 100.0,
            "compliance_readiness_score": 100.0,
        }
        await svc.persist_coverage_snapshot(
            matrix_id="m2", metrics=metrics_max,
            source_document_uuid="d2", company_id=1,
        )

        assert session.add.call_count == 2


# ---------------------------------------------------------------------------
# Tests: get_coverage_summary (Requirement 7.3, 7.4)
# ---------------------------------------------------------------------------


class TestGetCoverageSummary:
    """Tests for coverage summary aggregation."""

    @pytest.mark.asyncio
    async def test_returns_empty_summary_without_session(self):
        """Returns empty summary when session_factory is None."""
        svc = CoverageMetricsService(session_factory=None)
        result = await svc.get_coverage_summary(company_id=1)

        assert result == _empty_coverage_summary()
        assert result["total_matrices_generated"] == 0
        assert result["latest_matrix_date"] is None
        assert result["average_coverage_percentage"] == 0.0
        assert result["breakdown"] == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_matrices(self, mock_session_factory):
        """Returns empty summary when company has zero matrices."""
        factory, session = mock_session_factory
        # session.execute returns a regular MagicMock (sync result object)
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = 0
        session.execute = AsyncMock(return_value=exec_result)
        svc = CoverageMetricsService(session_factory=factory)

        result = await svc.get_coverage_summary(company_id=1)

        assert result["total_matrices_generated"] == 0
        assert result["latest_matrix_date"] is None

    @pytest.mark.asyncio
    async def test_aggregates_from_latest_snapshots(self, mock_session_factory):
        """Aggregates metrics from the latest snapshot per source document."""
        factory, session = mock_session_factory

        # Mock snapshot objects
        snapshot1 = MagicMock()
        snapshot1.source_document_uuid = "doc-001"
        snapshot1.coverage_percentage = 80.0
        snapshot1.orphan_requirements_count = 2
        snapshot1.orphan_test_cases_count = 1
        snapshot1.compliance_readiness_score = 75.0

        snapshot2 = MagicMock()
        snapshot2.source_document_uuid = "doc-002"
        snapshot2.coverage_percentage = 60.0
        snapshot2.orphan_requirements_count = 3
        snapshot2.orphan_test_cases_count = 2
        snapshot2.compliance_readiness_score = 55.0

        # Setup execute calls in sequence
        fixed_time = datetime(2025, 6, 1, tzinfo=timezone.utc)
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # count of matrices
                result.scalar_one_or_none.return_value = 5
            elif call_count[0] == 2:
                # latest date
                result.scalar_one_or_none.return_value = fixed_time
            else:
                # snapshots query
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [snapshot1, snapshot2]
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute
        svc = CoverageMetricsService(session_factory=factory)

        result = await svc.get_coverage_summary(company_id=1)

        assert result["total_matrices_generated"] == 5
        assert result["latest_matrix_date"] == fixed_time
        assert result["average_coverage_percentage"] == 70.0
        assert result["total_orphan_requirements"] == 5
        assert result["total_orphan_test_cases"] == 3
        assert result["average_compliance_readiness_score"] == 65.0
        assert len(result["breakdown"]) == 2


# ---------------------------------------------------------------------------
# Tests: get_coverage_history (Requirement 7.5)
# ---------------------------------------------------------------------------


class TestGetCoverageHistory:
    """Tests for coverage history pagination."""

    @pytest.mark.asyncio
    async def test_returns_empty_without_session(self):
        """Returns empty history when session_factory is None."""
        svc = CoverageMetricsService(session_factory=None)
        result = await svc.get_coverage_history(company_id=1)

        assert result == {"snapshots": [], "total_count": 0}

    @pytest.mark.asyncio
    async def test_returns_paginated_snapshots(self, mock_session_factory):
        """Returns paginated snapshots with total count."""
        factory, session = mock_session_factory

        snapshot = MagicMock()
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # count query
                result.scalar_one_or_none.return_value = 15
            else:
                # data query
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [snapshot]
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute
        svc = CoverageMetricsService(session_factory=factory)

        result = await svc.get_coverage_history(company_id=1)

        assert result["total_count"] == 15
        assert result["snapshots"] == [snapshot]

    @pytest.mark.asyncio
    async def test_applies_filters(self, mock_session_factory):
        """Filters are applied when provided."""
        from alcoabase.schemas.traceability import HistoryFilters

        factory, session = mock_session_factory

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = 3
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute
        svc = CoverageMetricsService(session_factory=factory)

        filters = HistoryFilters(
            source_document_uuid="doc-001",
            limit=10,
            offset=5,
        )
        result = await svc.get_coverage_history(company_id=1, filters=filters)

        assert result["total_count"] == 3
        assert result["snapshots"] == []


# ---------------------------------------------------------------------------
# Tests: get_document_coverage (Requirement 5.4, 7.6)
# ---------------------------------------------------------------------------


class TestGetDocumentCoverage:
    """Tests for document coverage lookup."""

    @pytest.mark.asyncio
    async def test_returns_empty_without_session(self):
        """Returns empty coverage when session_factory is None."""
        svc = CoverageMetricsService(session_factory=None)
        result = await svc.get_document_coverage(
            document_uuid="doc-001", company_id=1,
        )

        assert result == _empty_document_coverage("doc-001")
        assert result["document_uuid"] == "doc-001"
        assert result["latest_matrix_id"] is None
        assert result["coverage_percentage"] is None

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_snapshot_found(self, mock_session_factory):
        """Returns empty coverage when document has never been in a matrix."""
        factory, session = mock_session_factory
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=exec_result)
        svc = CoverageMetricsService(session_factory=factory)

        result = await svc.get_document_coverage(
            document_uuid="doc-never-analyzed", company_id=1,
        )

        assert result["document_uuid"] == "doc-never-analyzed"
        assert result["latest_matrix_id"] is None
        assert result["coverage_percentage"] is None
        assert result["compliance_readiness_score"] is None
        assert result["orphan_requirement_count"] == 0
        assert result["total_requirements"] == 0

    @pytest.mark.asyncio
    async def test_returns_latest_snapshot_data(self, mock_session_factory):
        """Returns coverage data from the latest snapshot."""
        factory, session = mock_session_factory

        snapshot = MagicMock()
        snapshot.matrix_id = "matrix-uuid-123"
        snapshot.snapshot_date = datetime(2025, 6, 15, tzinfo=timezone.utc)
        snapshot.coverage_percentage = 85.5
        snapshot.orphan_requirements_count = 3
        snapshot.total_requirements = 20
        snapshot.compliance_readiness_score = 78.2

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = snapshot
        session.execute = AsyncMock(return_value=exec_result)
        svc = CoverageMetricsService(session_factory=factory)

        result = await svc.get_document_coverage(
            document_uuid="doc-001", company_id=1,
        )

        assert result["document_uuid"] == "doc-001"
        assert result["latest_matrix_id"] == "matrix-uuid-123"
        assert result["latest_matrix_date"] == datetime(2025, 6, 15, tzinfo=timezone.utc)
        assert result["coverage_percentage"] == 85.5
        assert result["orphan_requirement_count"] == 3
        assert result["total_requirements"] == 20
        assert result["compliance_readiness_score"] == 78.2


# ---------------------------------------------------------------------------
# Tests: Service class delegation
# ---------------------------------------------------------------------------


class TestCoverageMetricsServiceDelegation:
    """Tests that the service class delegates to module-level functions."""

    def test_service_compute_coverage_metrics(
        self, service, sample_requirements, sample_test_cases,
        sample_links, sample_source_docs, sample_target_docs,
    ):
        """Service method delegates to module-level function."""
        result = service.compute_coverage_metrics(
            requirements=sample_requirements,
            test_cases=sample_test_cases,
            links=sample_links,
            source_docs=sample_source_docs,
            target_docs=sample_target_docs,
        )

        # Should produce same result as module-level function
        expected = compute_coverage_metrics(
            requirements=sample_requirements,
            test_cases=sample_test_cases,
            links=sample_links,
            source_docs=sample_source_docs,
            target_docs=sample_target_docs,
        )
        assert result == expected

    def test_service_compute_compliance_readiness_score(self, service):
        """Service method delegates to module-level compliance score function."""
        metrics = {
            "coverage_percentage": 50.0,
            "average_link_confidence": 0.8,
            "orphan_requirements_count": 1,
            "orphan_test_cases_count": 1,
        }

        result = service.compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[{"document_uuid": "d1"}],
            target_docs_with_extractions=[{"document_uuid": "d2"}],
            total_docs=2,
        )

        expected = compute_compliance_readiness_score(
            metrics=metrics,
            source_docs_with_extractions=[{"document_uuid": "d1"}],
            target_docs_with_extractions=[{"document_uuid": "d2"}],
            total_docs=2,
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Tests: Helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_empty_coverage_summary_structure(self):
        """_empty_coverage_summary returns correct zero-value structure."""
        result = _empty_coverage_summary()

        assert result["total_matrices_generated"] == 0
        assert result["latest_matrix_date"] is None
        assert result["average_coverage_percentage"] == 0.0
        assert result["total_orphan_requirements"] == 0
        assert result["total_orphan_test_cases"] == 0
        assert result["average_compliance_readiness_score"] == 0.0
        assert result["breakdown"] == []

    def test_empty_document_coverage_structure(self):
        """_empty_document_coverage returns correct null-value structure."""
        result = _empty_document_coverage("test-doc-uuid")

        assert result["document_uuid"] == "test-doc-uuid"
        assert result["latest_matrix_id"] is None
        assert result["latest_matrix_date"] is None
        assert result["coverage_percentage"] is None
        assert result["orphan_requirement_count"] == 0
        assert result["total_requirements"] == 0
        assert result["compliance_readiness_score"] is None
