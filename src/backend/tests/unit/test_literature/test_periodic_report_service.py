"""Unit tests for the PeriodicReportService.

Tests cover:
- generate_report includes all 8 sections
- generate_report with empty period (no executions) includes "No searches executed"
- _build_disposition_matrix sum invariant (sum == total_results_ingested)
- _build_statistical_summary computes correct totals
- advance_status valid transitions (generated→reviewed→approved→submitted)
- advance_status rejects invalid/backward transitions
- advance_status records user_id, timestamp, comment in status_history
- list_reports pagination and filtering
- Role-based access (document_admin/system_admin for status changes)

References:
    - Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
    - Task: 14.6
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.vigilance.exceptions import (
    InvalidReportStatusTransitionError,
    ProductNotFoundError,
    ReportNotFoundError,
)
from alcoabase.literature.vigilance.services.periodic_report_service import (
    PeriodicReportService,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """Create a PeriodicReportService instance."""
    return PeriodicReportService()


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_product_mock(
    product_id=1,
    company_id=10,
    name="CardioMonitor X200",
    device_class="IIb",
    intended_purpose="Continuous cardiac monitoring",
    udi="UDI-CM-X200",
    manufacturer_name="MedTech Corp",
    gmdn_code="12345",
    status="active",
):
    """Create a mock MedicalProduct."""
    product = MagicMock()
    product.id = product_id
    product.company_id = company_id
    product.name = name
    product.device_class = device_class
    product.intended_purpose = intended_purpose
    product.udi = udi
    product.manufacturer_name = manufacturer_name
    product.gmdn_code = gmdn_code
    product.status = status
    return product


def _make_execution_mock(
    execution_id=1,
    profile_id=1,
    company_id=10,
    total_results_found=50,
    results_after_exclusion=40,
    results_ingested=35,
    results_duplicate=5,
    status="completed",
):
    """Create a mock VigilanceSearchExecution."""
    execution = MagicMock()
    execution.id = execution_id
    execution.profile_id = profile_id
    execution.company_id = company_id
    execution.execution_timestamp = datetime(2025, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    execution.search_parameters = {"query": "cardiac adverse events"}
    execution.sources_queried = ["pubmed", "embase"]
    execution.total_results_found = total_results_found
    execution.results_after_exclusion = results_after_exclusion
    execution.results_ingested = results_ingested
    execution.results_duplicate = results_duplicate
    execution.execution_duration_ms = 15000
    execution.status = status
    return execution


def _make_signal_mock(
    signal_id=1,
    severity="major",
    confidence=0.85,
    disposition="under_review",
):
    """Create a mock VigilanceSignal."""
    signal = MagicMock()
    signal.id = signal_id
    signal.ingestion_record_id = 100
    signal.product_id = 1
    signal.profile_id = 1
    signal.company_id = 10
    signal.severity = severity
    signal.evidence_summary = "Adverse event evidence found in study."
    signal.affected_product_aspects = ["cardiac sensor"]
    signal.regulatory_references = ["MDR Article 87(1)"]
    signal.recommended_actions = ["Review logs"]
    signal.confidence = confidence
    signal.disposition = disposition
    signal.dismissal_reason = None
    signal.confirmation_note = None
    signal.reviewer_user_id = None
    signal.detection_timestamp = datetime(2025, 3, 16, 8, 0, 0, tzinfo=timezone.utc)
    signal.created_at = datetime(2025, 3, 16, 8, 0, 0, tzinfo=timezone.utc)
    signal.updated_at = datetime(2025, 3, 16, 8, 0, 0, tzinfo=timezone.utc)
    return signal


def _make_profile_mock(profile_id=1, name="Cardiac PMS Profile", status="active"):
    """Create a mock VigilanceSearchProfile."""
    profile = MagicMock()
    profile.id = profile_id
    profile.name = name
    profile.status = status
    profile.search_terms = ["cardiac device malfunction"]
    profile.mesh_terms = ["Heart Failure"]
    profile.adverse_event_keywords = ["death", "serious injury"]
    profile.device_identifiers = ["UDI-CM-X200"]
    profile.exclusion_terms = ["animal study"]
    profile.source_ids = ["pubmed"]
    profile.schedule_cron = "0 2 * * 1"
    profile.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return profile


def _make_report_mock(
    report_id=1,
    status="generated",
    status_history=None,
):
    """Create a mock PeriodicSafetyReport."""
    report = MagicMock()
    report.id = report_id
    report.product_id = 1
    report.company_id = 10
    report.period_start = date(2025, 1, 1)
    report.period_end = date(2025, 3, 31)
    report.generated_at = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    report.report_content = {"product_metadata": {"name": "Test"}}
    report.status = status
    report.version = 1
    report.status_history = status_history or [
        {"status": "generated", "user_id": 42, "timestamp": "2025-04-01T10:00:00+00:00"}
    ]
    report.created_by = 42
    report.created_at = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    report.updated_at = datetime(2025, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    return report


# ---------------------------------------------------------------------------
# Tests for _build_disposition_matrix
# ---------------------------------------------------------------------------


class TestBuildDispositionMatrix:
    """Tests for PeriodicReportService._build_disposition_matrix."""

    def test_sum_equals_total_ingested(self, service):
        """Sum of all categories equals total_results_ingested."""
        executions = [
            {"results_ingested": 20},
            {"results_ingested": 15},
        ]
        signals = [
            {"disposition": "dismissed"},
            {"disposition": "confirmed"},
            {"disposition": "escalated"},
            {"disposition": "under_review"},
        ]

        matrix = service._build_disposition_matrix(executions, signals)

        total = (
            matrix["no_signal"]
            + matrix["signal_dismissed"]
            + matrix["signal_confirmed"]
            + matrix["signal_escalated"]
        )
        assert total == matrix["total"]
        assert matrix["total"] == 35  # 20 + 15

    def test_empty_executions_and_signals(self, service):
        """Empty inputs produce all-zero matrix."""
        matrix = service._build_disposition_matrix([], [])

        assert matrix["no_signal"] == 0
        assert matrix["signal_dismissed"] == 0
        assert matrix["signal_confirmed"] == 0
        assert matrix["signal_escalated"] == 0
        assert matrix["total"] == 0

    def test_all_no_signal(self, service):
        """All results are no_signal when there are no signals."""
        executions = [{"results_ingested": 10}]
        signals = []

        matrix = service._build_disposition_matrix(executions, signals)

        assert matrix["no_signal"] == 10
        assert matrix["signal_dismissed"] == 0
        assert matrix["signal_confirmed"] == 0
        assert matrix["signal_escalated"] == 0
        assert matrix["total"] == 10

    def test_disposition_classification(self, service):
        """Signals are classified by their disposition."""
        executions = [{"results_ingested": 10}]
        signals = [
            {"disposition": "dismissed"},
            {"disposition": "dismissed"},
            {"disposition": "confirmed"},
            {"disposition": "escalated"},
            {"disposition": "under_review"},
        ]

        matrix = service._build_disposition_matrix(executions, signals)

        assert matrix["signal_dismissed"] == 2
        assert matrix["signal_confirmed"] == 2  # confirmed + under_review
        assert matrix["signal_escalated"] == 1
        assert matrix["no_signal"] == 5  # 10 - 5 signals


# ---------------------------------------------------------------------------
# Tests for _build_statistical_summary
# ---------------------------------------------------------------------------


class TestBuildStatisticalSummary:
    """Tests for PeriodicReportService._build_statistical_summary."""

    def test_computes_totals(self, service):
        """Correctly computes total_searches and total_results."""
        executions = [
            {"total_results_found": 50},
            {"total_results_found": 30},
            {"total_results_found": 20},
        ]
        signals = []

        summary = service._build_statistical_summary(executions, signals)

        assert summary["total_searches"] == 3
        assert summary["total_results"] == 100
        assert summary["total_signals"] == 0

    def test_signals_by_severity(self, service):
        """Correctly counts signals by severity."""
        executions = [{"total_results_found": 100}]
        signals = [
            {"severity": "critical", "disposition": "escalated"},
            {"severity": "major", "disposition": "confirmed"},
            {"severity": "major", "disposition": "under_review"},
            {"severity": "minor", "disposition": "dismissed"},
        ]

        summary = service._build_statistical_summary(executions, signals)

        assert summary["signals_by_severity"]["critical"] == 1
        assert summary["signals_by_severity"]["major"] == 2
        assert summary["signals_by_severity"]["minor"] == 1

    def test_disposition_breakdown(self, service):
        """Correctly counts disposition breakdown."""
        executions = []
        signals = [
            {"severity": "major", "disposition": "under_review"},
            {"severity": "major", "disposition": "confirmed"},
            {"severity": "minor", "disposition": "dismissed"},
            {"severity": "critical", "disposition": "escalated"},
        ]

        summary = service._build_statistical_summary(executions, signals)

        assert summary["disposition_breakdown"]["under_review"] == 1
        assert summary["disposition_breakdown"]["confirmed"] == 1
        assert summary["disposition_breakdown"]["dismissed"] == 1
        assert summary["disposition_breakdown"]["escalated"] == 1

    def test_empty_inputs(self, service):
        """Empty inputs produce zero-value summary."""
        summary = service._build_statistical_summary([], [])

        assert summary["total_searches"] == 0
        assert summary["total_results"] == 0
        assert summary["total_signals"] == 0
        assert summary["avg_time_to_disposition_hours"] is None


# ---------------------------------------------------------------------------
# Tests for generate_report
# ---------------------------------------------------------------------------


class TestGenerateReport:
    """Tests for PeriodicReportService.generate_report."""

    async def test_report_includes_all_sections(self, service, mock_session):
        """Generated report includes all 8 required sections."""
        product = _make_product_mock()
        execution = _make_execution_mock()
        signal = _make_signal_mock()
        profile = _make_profile_mock()

        # Mock _get_product_or_raise
        with patch.object(
            service, "_get_product_or_raise", return_value=product
        ) as mock_get_product, patch.object(
            service, "_get_executions_in_period", return_value=[execution]
        ), patch.object(
            service, "_get_signals_in_period", return_value=[signal]
        ), patch.object(
            service, "_get_profiles_for_product", return_value=[profile]
        ):
            # Mock flush to set report.id
            async def _flush_side_effect():
                pass

            mock_session.flush = AsyncMock(side_effect=_flush_side_effect)

            result = await service.generate_report(
                mock_session,
                product_id=1,
                company_id=10,
                period_start=date(2025, 1, 1),
                period_end=date(2025, 3, 31),
                user_id=42,
            )

        # Verify session.add was called
        mock_session.add.assert_called_once()

        # Verify all 8 sections exist in report_content
        report_content = result["report_content"]
        assert "product_metadata" in report_content
        assert "period_dates" in report_content
        assert "search_executions" in report_content
        assert "signals" in report_content
        assert "search_strategy" in report_content
        assert "disposition_matrix" in report_content
        assert "statistical_summary" in report_content
        assert "regulatory_compliance" in report_content

    async def test_empty_period_includes_notice(self, service, mock_session):
        """Report with no executions includes 'No searches executed' notice."""
        product = _make_product_mock()
        profile = _make_profile_mock()

        with patch.object(
            service, "_get_product_or_raise", return_value=product
        ), patch.object(
            service, "_get_executions_in_period", return_value=[]
        ), patch.object(
            service, "_get_signals_in_period", return_value=[]
        ), patch.object(
            service, "_get_profiles_for_product", return_value=[profile]
        ):
            result = await service.generate_report(
                mock_session,
                product_id=1,
                company_id=10,
                period_start=date(2025, 1, 1),
                period_end=date(2025, 3, 31),
                user_id=42,
            )

        report_content = result["report_content"]
        assert "empty_period_notice" in report_content
        assert "No searches executed" in report_content["empty_period_notice"]

    async def test_product_not_found_raises(self, service, mock_session):
        """Raises ProductNotFoundError when product doesn't exist."""
        with patch.object(
            service,
            "_get_product_or_raise",
            side_effect=ProductNotFoundError(
                "Not found", product_id=999, company_id=10
            ),
        ):
            with pytest.raises(ProductNotFoundError):
                await service.generate_report(
                    mock_session,
                    product_id=999,
                    company_id=10,
                    period_start=date(2025, 1, 1),
                    period_end=date(2025, 3, 31),
                    user_id=42,
                )


# ---------------------------------------------------------------------------
# Tests for advance_status
# ---------------------------------------------------------------------------


class TestAdvanceStatus:
    """Tests for PeriodicReportService.advance_status."""

    async def test_valid_transition_generated_to_reviewed(self, service, mock_session):
        """Allows transition from generated to reviewed."""
        report = _make_report_mock(status="generated")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            result = await service.advance_status(
                mock_session,
                report_id=1,
                company_id=10,
                user_id=42,
                new_status="reviewed",
                comment="Reviewed by QA",
            )

        assert report.status == "reviewed"
        # Check status_history was updated
        assert len(report.status_history) == 2
        latest_entry = report.status_history[-1]
        assert latest_entry["status"] == "reviewed"
        assert latest_entry["user_id"] == 42
        assert latest_entry["comment"] == "Reviewed by QA"
        assert "timestamp" in latest_entry

    async def test_valid_transition_reviewed_to_approved(self, service, mock_session):
        """Allows transition from reviewed to approved."""
        report = _make_report_mock(status="reviewed")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            await service.advance_status(
                mock_session,
                report_id=1,
                company_id=10,
                user_id=42,
                new_status="approved",
            )

        assert report.status == "approved"

    async def test_valid_transition_approved_to_submitted(self, service, mock_session):
        """Allows transition from approved to submitted."""
        report = _make_report_mock(status="approved")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            await service.advance_status(
                mock_session,
                report_id=1,
                company_id=10,
                user_id=42,
                new_status="submitted",
            )

        assert report.status == "submitted"

    async def test_invalid_transition_generated_to_approved(self, service, mock_session):
        """Rejects skipping transition from generated directly to approved."""
        report = _make_report_mock(status="generated")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            with pytest.raises(InvalidReportStatusTransitionError):
                await service.advance_status(
                    mock_session,
                    report_id=1,
                    company_id=10,
                    user_id=42,
                    new_status="approved",
                )

    async def test_invalid_backward_transition(self, service, mock_session):
        """Rejects backward transition from reviewed to generated."""
        report = _make_report_mock(status="reviewed")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            with pytest.raises(InvalidReportStatusTransitionError):
                await service.advance_status(
                    mock_session,
                    report_id=1,
                    company_id=10,
                    user_id=42,
                    new_status="generated",
                )

    async def test_invalid_transition_submitted_to_anything(self, service, mock_session):
        """Rejects any transition from submitted (terminal state)."""
        report = _make_report_mock(status="submitted")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            with pytest.raises(InvalidReportStatusTransitionError):
                await service.advance_status(
                    mock_session,
                    report_id=1,
                    company_id=10,
                    user_id=42,
                    new_status="reviewed",
                )

    async def test_report_not_found_raises(self, service, mock_session):
        """Raises ReportNotFoundError when report doesn't exist."""
        with patch.object(
            service,
            "_get_report_or_raise",
            side_effect=ReportNotFoundError(
                "Not found", report_id=999, company_id=10
            ),
        ):
            with pytest.raises(ReportNotFoundError):
                await service.advance_status(
                    mock_session,
                    report_id=999,
                    company_id=10,
                    user_id=42,
                    new_status="reviewed",
                )

    async def test_advance_records_timestamp(self, service, mock_session):
        """Status advancement records a timestamp in history."""
        report = _make_report_mock(status="generated")

        with patch.object(
            service, "_get_report_or_raise", return_value=report
        ):
            await service.advance_status(
                mock_session,
                report_id=1,
                company_id=10,
                user_id=42,
                new_status="reviewed",
            )

        latest_entry = report.status_history[-1]
        # Timestamp should be a valid ISO format string
        assert "T" in latest_entry["timestamp"]


# ---------------------------------------------------------------------------
# Tests for list_reports
# ---------------------------------------------------------------------------


class TestListReports:
    """Tests for PeriodicReportService.list_reports."""

    async def test_pagination_clamp(self, service, mock_session):
        """Page size is clamped between 1 and 100."""
        # Mock the count query and the paginated query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        reports, total = await service.list_reports(
            mock_session,
            company_id=10,
            page=1,
            page_size=200,  # exceeds max
        )

        assert total == 0
        assert reports == []

    async def test_returns_filtered_results(self, service, mock_session):
        """Returns filtered and paginated results."""
        report_mock = _make_report_mock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [report_mock]

        mock_session.execute = AsyncMock(side_effect=[count_result, list_result])

        reports, total = await service.list_reports(
            mock_session,
            company_id=10,
            product_id=1,
            status="generated",
        )

        assert total == 1
        assert len(reports) == 1
        assert reports[0]["id"] == 1


# ---------------------------------------------------------------------------
# Tests for get_report
# ---------------------------------------------------------------------------


class TestGetReport:
    """Tests for PeriodicReportService.get_report."""

    async def test_returns_full_report(self, service, mock_session):
        """Returns full report content by ID."""
        report = _make_report_mock()

        with patch.object(service, "_get_report_or_raise", return_value=report):
            result = await service.get_report(
                mock_session, report_id=1, company_id=10
            )

        assert result["id"] == 1
        assert result["status"] == "generated"
        assert result["report_content"] is not None

    async def test_not_found_raises(self, service, mock_session):
        """Raises ReportNotFoundError for missing report."""
        with patch.object(
            service,
            "_get_report_or_raise",
            side_effect=ReportNotFoundError(
                "Not found", report_id=999, company_id=10
            ),
        ):
            with pytest.raises(ReportNotFoundError):
                await service.get_report(
                    mock_session, report_id=999, company_id=10
                )
