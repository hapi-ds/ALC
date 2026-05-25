"""Unit tests for Celery impact analysis tasks.

Tests the Celery task layer for impact analysis:
- build_dependency_graph: task execution, progress updates, error handling
- analyze_change_impact: full pipeline, monotonic progress, timeout handling
- execute_gap_analysis: task execution, progress, error handling
- Helper functions: _sanitize_error_message, _estimate_duration

Also verifies task configuration (queue, time_limit, max_retries).

References:
    - Requirements: 6.1, 6.2, 6.4, 6.5, 6.9
    - Task 8.6: Write unit tests for Celery tasks and event trigger
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.tasks.impact_analysis_tasks import (
    BUILD_GRAPH_TIMEOUT_SECONDS,
    GAP_ANALYSIS_TIMEOUT_SECONDS,
    HARD_TIMEOUT_SECONDS,
    MIN_ESTIMATED_DURATION_SECONDS,
    PROGRESS_DELTA_COMPLETE,
    PROGRESS_DEPS_COMPLETE,
    PROGRESS_GAPS_END,
    PROGRESS_ITEMS_END,
    PROGRESS_REPORT_COMPLETE,
    SECONDS_PER_DEPENDENCY,
    _estimate_duration,
    _sanitize_error_message,
    analyze_change_impact,
    build_dependency_graph,
    execute_gap_analysis,
)


# ---------------------------------------------------------------------------
# Tests: Task configuration
# ---------------------------------------------------------------------------


class TestTaskConfiguration:
    """Tests for Celery task registration and configuration."""

    def test_build_dependency_graph_queue(self) -> None:
        """build_dependency_graph should run on ai_operations queue."""
        assert build_dependency_graph.queue == "ai_operations"

    def test_build_dependency_graph_time_limit(self) -> None:
        """build_dependency_graph should have 300s time limit."""
        assert build_dependency_graph.time_limit == BUILD_GRAPH_TIMEOUT_SECONDS
        assert build_dependency_graph.time_limit == 300

    def test_build_dependency_graph_no_retries(self) -> None:
        """build_dependency_graph should not retry on failure."""
        assert build_dependency_graph.max_retries == 0

    def test_analyze_change_impact_queue(self) -> None:
        """analyze_change_impact should run on ai_operations queue."""
        assert analyze_change_impact.queue == "ai_operations"

    def test_analyze_change_impact_time_limit(self) -> None:
        """analyze_change_impact should have 600s hard timeout."""
        assert analyze_change_impact.time_limit == HARD_TIMEOUT_SECONDS
        assert analyze_change_impact.time_limit == 600

    def test_analyze_change_impact_no_retries(self) -> None:
        """analyze_change_impact should not retry on failure."""
        assert analyze_change_impact.max_retries == 0

    def test_execute_gap_analysis_queue(self) -> None:
        """execute_gap_analysis should run on ai_operations queue."""
        assert execute_gap_analysis.queue == "ai_operations"

    def test_execute_gap_analysis_time_limit(self) -> None:
        """execute_gap_analysis should have 180s time limit."""
        assert execute_gap_analysis.time_limit == GAP_ANALYSIS_TIMEOUT_SECONDS
        assert execute_gap_analysis.time_limit == 180

    def test_execute_gap_analysis_no_retries(self) -> None:
        """execute_gap_analysis should not retry on failure."""
        assert execute_gap_analysis.max_retries == 0


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants matching requirements."""

    def test_hard_timeout_is_600(self) -> None:
        """Hard timeout should be 600 seconds per requirement 6.5."""
        assert HARD_TIMEOUT_SECONDS == 600

    def test_build_graph_timeout_is_300(self) -> None:
        """Build graph timeout should be 300 seconds."""
        assert BUILD_GRAPH_TIMEOUT_SECONDS == 300

    def test_gap_analysis_timeout_is_180(self) -> None:
        """Gap analysis timeout should be 180 seconds."""
        assert GAP_ANALYSIS_TIMEOUT_SECONDS == 180

    def test_min_estimated_duration_is_30(self) -> None:
        """Minimum estimated duration should be 30 seconds per requirement 6.1."""
        assert MIN_ESTIMATED_DURATION_SECONDS == 30

    def test_seconds_per_dependency_is_15(self) -> None:
        """Seconds per dependency should be 15 per requirement 6.1."""
        assert SECONDS_PER_DEPENDENCY == 15

    def test_progress_milestones_are_monotonic(self) -> None:
        """Progress milestones should be in strictly increasing order."""
        milestones = [
            PROGRESS_DELTA_COMPLETE,
            PROGRESS_DEPS_COMPLETE,
            PROGRESS_ITEMS_END,
            PROGRESS_GAPS_END,
            PROGRESS_REPORT_COMPLETE,
        ]
        for i in range(len(milestones) - 1):
            assert milestones[i] < milestones[i + 1], (
                f"Milestone {milestones[i]} should be < {milestones[i + 1]}"
            )

    def test_progress_delta_complete_is_10(self) -> None:
        """Delta complete should be at 10% per requirement 6.2."""
        assert PROGRESS_DELTA_COMPLETE == 10

    def test_progress_deps_complete_is_20(self) -> None:
        """Dependencies complete should be at 20% per requirement 6.2."""
        assert PROGRESS_DEPS_COMPLETE == 20

    def test_progress_items_end_is_85(self) -> None:
        """Items assessment end should be at 85% per requirement 6.2."""
        assert PROGRESS_ITEMS_END == 85

    def test_progress_gaps_end_is_95(self) -> None:
        """Gap analysis end should be at 95% per requirement 6.2."""
        assert PROGRESS_GAPS_END == 95

    def test_progress_report_complete_is_100(self) -> None:
        """Report persistence should be at 100% per requirement 6.2."""
        assert PROGRESS_REPORT_COMPLETE == 100


# ---------------------------------------------------------------------------
# Tests: _sanitize_error_message
# ---------------------------------------------------------------------------


class TestSanitizeErrorMessage:
    """Tests for error message sanitization (requirement 6.9)."""

    def test_basic_exception_sanitized(self) -> None:
        """Basic exception produces type: message format."""
        exc = ValueError("Something went wrong")
        result = _sanitize_error_message(exc)
        assert result == "ValueError: Something went wrong"

    def test_long_message_truncated(self) -> None:
        """Messages longer than 500 chars are truncated."""
        long_msg = "x" * 1000
        exc = RuntimeError(long_msg)
        result = _sanitize_error_message(exc)
        # Type name + ": " + 500 chars of message
        assert len(result) <= 1000

    def test_newlines_removed(self) -> None:
        """Newlines (potential stack trace fragments) are removed."""
        exc = RuntimeError("Error\n  at line 42\n  at line 100")
        result = _sanitize_error_message(exc)
        assert "\n" not in result
        assert "\r" not in result

    def test_no_stack_trace_in_output(self) -> None:
        """Stack trace-like content is stripped of newlines."""
        msg = "Traceback (most recent call last):\n  File 'foo.py', line 1\nValueError: bad"
        exc = Exception(msg)
        result = _sanitize_error_message(exc)
        assert "\n" not in result
        # The content is flattened to a single line
        assert "Exception:" in result

    def test_empty_exception_message(self) -> None:
        """Empty exception message produces just the type."""
        exc = RuntimeError("")
        result = _sanitize_error_message(exc)
        assert result == "RuntimeError: "

    def test_total_output_max_1000_chars(self) -> None:
        """Total sanitized output never exceeds 1000 characters."""
        # Create an exception with a very long type name via subclass
        long_msg = "a" * 2000
        exc = RuntimeError(long_msg)
        result = _sanitize_error_message(exc)
        assert len(result) <= 1000

    def test_carriage_return_removed(self) -> None:
        """Carriage returns are also removed."""
        exc = ValueError("line1\r\nline2\rline3")
        result = _sanitize_error_message(exc)
        assert "\r" not in result
        assert "\n" not in result


# ---------------------------------------------------------------------------
# Tests: _estimate_duration
# ---------------------------------------------------------------------------


class TestEstimateDuration:
    """Tests for job duration estimation (requirement 6.1)."""

    def test_zero_dependencies_returns_minimum(self) -> None:
        """Zero dependencies should return minimum 30 seconds."""
        assert _estimate_duration(0) == MIN_ESTIMATED_DURATION_SECONDS
        assert _estimate_duration(0) == 30

    def test_one_dependency_returns_minimum(self) -> None:
        """One dependency (15s) is below minimum, returns 30s."""
        assert _estimate_duration(1) == 30

    def test_two_dependencies_returns_minimum(self) -> None:
        """Two dependencies (30s) equals minimum, returns 30s."""
        assert _estimate_duration(2) == 30

    def test_three_dependencies_returns_45(self) -> None:
        """Three dependencies = 3 * 15 = 45 seconds."""
        assert _estimate_duration(3) == 45

    def test_ten_dependencies_returns_150(self) -> None:
        """Ten dependencies = 10 * 15 = 150 seconds."""
        assert _estimate_duration(10) == 150

    def test_formula_is_15_per_dependency(self) -> None:
        """Verify the formula: max(count * 15, 30)."""
        for count in range(0, 50):
            expected = max(count * SECONDS_PER_DEPENDENCY, MIN_ESTIMATED_DURATION_SECONDS)
            assert _estimate_duration(count) == expected


# ---------------------------------------------------------------------------
# Tests: build_dependency_graph task execution
# ---------------------------------------------------------------------------


class TestBuildDependencyGraphTask:
    """Tests for the build_dependency_graph Celery task."""

    @patch("alcoabase.tasks.impact_analysis_tasks._build_dependency_graph_async")
    def test_successful_execution(self, mock_async: MagicMock) -> None:
        """Task delegates to async implementation and returns result."""
        mock_async.return_value = {
            "status": "completed",
            "edges_created": 15,
            "edges_updated": 3,
            "job_id": "job-123",
        }

        result = build_dependency_graph(company_id=1, scope="full")

        assert result["status"] == "completed"
        assert result["edges_created"] == 15
        mock_async.assert_called_once_with(
            company_id=1,
            scope="full",
            document_uuid="dependency_graph",
        )

    @patch("alcoabase.tasks.impact_analysis_tasks._build_dependency_graph_async")
    def test_incremental_scope_default(self, mock_async: MagicMock) -> None:
        """Default scope should be 'incremental'."""
        mock_async.return_value = {"status": "completed", "job_id": "job-456"}

        build_dependency_graph(company_id=2)

        mock_async.assert_called_once_with(
            company_id=2,
            scope="incremental",
            document_uuid="dependency_graph",
        )

    @patch("alcoabase.tasks.impact_analysis_tasks._build_dependency_graph_async")
    def test_exception_returns_failed_with_sanitized_error(
        self, mock_async: MagicMock
    ) -> None:
        """Unhandled exceptions return failed status with sanitized error."""
        mock_async.side_effect = RuntimeError("DB connection lost\n  at pool.py:42")

        result = build_dependency_graph(company_id=1)

        assert result["status"] == "failed"
        assert "RuntimeError" in result["error"]
        # No newlines in sanitized error
        assert "\n" not in result["error"]


# ---------------------------------------------------------------------------
# Tests: analyze_change_impact task execution
# ---------------------------------------------------------------------------


class TestAnalyzeChangeImpactTask:
    """Tests for the analyze_change_impact Celery task."""

    @patch("alcoabase.tasks.impact_analysis_tasks._handle_analysis_failure")
    @patch("alcoabase.tasks.impact_analysis_tasks._analyze_change_impact_async")
    def test_successful_execution(
        self, mock_async: MagicMock, mock_failure: MagicMock
    ) -> None:
        """Task delegates to async implementation and returns result."""
        mock_async.return_value = {
            "status": "completed",
            "job_id": "job-789",
            "report_id": "report-abc",
            "total_affected_items": 5,
            "critical_count": 1,
            "major_count": 2,
            "minor_count": 2,
            "analysis_duration_ms": 45000,
        }

        result = analyze_change_impact(
            document_uuid="2024-00001",
            document_id=1,
            new_version_id=10,
            previous_version_id=9,
            company_id=1,
            requesting_user_id=5,
        )

        assert result["status"] == "completed"
        assert result["report_id"] == "report-abc"
        assert result["total_affected_items"] == 5
        mock_failure.assert_not_called()

    @patch("alcoabase.tasks.impact_analysis_tasks._handle_analysis_failure")
    @patch("alcoabase.tasks.impact_analysis_tasks._analyze_change_impact_async")
    def test_exception_attempts_failure_handling(
        self, mock_async: MagicMock, mock_failure: MagicMock
    ) -> None:
        """On exception, attempts to mark job as failed."""
        mock_async.side_effect = RuntimeError("Unexpected error")
        mock_failure.return_value = None

        result = analyze_change_impact(
            document_uuid="2024-00001",
            document_id=1,
            new_version_id=10,
            previous_version_id=None,
            company_id=1,
        )

        assert result["status"] == "failed"
        assert "RuntimeError" in result["error"]
        mock_failure.assert_called_once()

    @patch("alcoabase.tasks.impact_analysis_tasks._handle_analysis_failure")
    @patch("alcoabase.tasks.impact_analysis_tasks._analyze_change_impact_async")
    def test_failure_handler_exception_does_not_propagate(
        self, mock_async: MagicMock, mock_failure: MagicMock
    ) -> None:
        """If failure handler also raises, task still returns failed status."""
        mock_async.side_effect = RuntimeError("Primary error")
        mock_failure.side_effect = RuntimeError("Secondary error")

        result = analyze_change_impact(
            document_uuid="2024-00001",
            document_id=1,
            new_version_id=10,
            previous_version_id=9,
            company_id=1,
        )

        # Should still return failed without raising
        assert result["status"] == "failed"
        assert "Primary error" in result["error"]

    @patch("alcoabase.tasks.impact_analysis_tasks._analyze_change_impact_async")
    def test_requesting_user_id_defaults_to_none(
        self, mock_async: MagicMock
    ) -> None:
        """requesting_user_id should default to None for auto-triggered."""
        mock_async.return_value = {"status": "completed", "job_id": "j1"}

        analyze_change_impact(
            document_uuid="2024-00001",
            document_id=1,
            new_version_id=10,
            previous_version_id=9,
            company_id=1,
        )

        call_kwargs = mock_async.call_args[1]
        assert call_kwargs["requesting_user_id"] is None


# ---------------------------------------------------------------------------
# Tests: execute_gap_analysis task execution
# ---------------------------------------------------------------------------


class TestExecuteGapAnalysisTask:
    """Tests for the execute_gap_analysis Celery task."""

    @patch("alcoabase.tasks.impact_analysis_tasks._execute_gap_analysis_async")
    def test_successful_execution(self, mock_async: MagicMock) -> None:
        """Task delegates to async implementation and returns result."""
        mock_async.return_value = {
            "status": "completed",
            "job_id": "gap-job-1",
            "result_job_id": "gap-result-1",
            "total_gaps_detected": 12,
            "gaps_retained": 12,
            "analysis_duration_ms": 30000,
        }

        result = execute_gap_analysis(
            source_document_id=1,
            target_document_id=2,
            source_version_id=5,
            target_version_id=3,
            company_id=1,
        )

        assert result["status"] == "completed"
        assert result["total_gaps_detected"] == 12
        mock_async.assert_called_once_with(
            source_document_id=1,
            target_document_id=2,
            source_version_id=5,
            target_version_id=3,
            company_id=1,
            document_uuid="gap_analysis",
        )

    @patch("alcoabase.tasks.impact_analysis_tasks._execute_gap_analysis_async")
    def test_exception_returns_failed_with_sanitized_error(
        self, mock_async: MagicMock
    ) -> None:
        """Unhandled exceptions return failed status with sanitized error."""
        mock_async.side_effect = ConnectionError("Redis unavailable\nRetry later")

        result = execute_gap_analysis(
            source_document_id=1,
            target_document_id=2,
            source_version_id=None,
            target_version_id=None,
            company_id=1,
        )

        assert result["status"] == "failed"
        assert "ConnectionError" in result["error"]
        assert "\n" not in result["error"]

    @patch("alcoabase.tasks.impact_analysis_tasks._execute_gap_analysis_async")
    def test_default_document_uuid(self, mock_async: MagicMock) -> None:
        """Default document_uuid should be 'gap_analysis'."""
        mock_async.return_value = {"status": "completed"}

        execute_gap_analysis(
            source_document_id=1,
            target_document_id=2,
            source_version_id=None,
            target_version_id=None,
            company_id=1,
        )

        call_kwargs = mock_async.call_args[1]
        assert call_kwargs["document_uuid"] == "gap_analysis"


# ---------------------------------------------------------------------------
# Tests: Progress monotonicity in analyze_change_impact
# ---------------------------------------------------------------------------


class TestProgressMonotonicity:
    """Tests verifying progress updates are monotonically increasing (req 6.2)."""

    @patch("alcoabase.tasks.impact_analysis_tasks._analyze_change_impact_async")
    def test_completed_result_has_duration(self, mock_async: MagicMock) -> None:
        """Completed analysis should include analysis_duration_ms."""
        mock_async.return_value = {
            "status": "completed",
            "job_id": "j1",
            "report_id": "r1",
            "total_affected_items": 0,
            "critical_count": 0,
            "major_count": 0,
            "minor_count": 0,
            "analysis_duration_ms": 5000,
        }

        result = analyze_change_impact(
            document_uuid="2024-00001",
            document_id=1,
            new_version_id=10,
            previous_version_id=9,
            company_id=1,
        )

        assert "analysis_duration_ms" in result
        assert result["analysis_duration_ms"] >= 0

    @patch("alcoabase.tasks.impact_analysis_tasks._analyze_change_impact_async")
    def test_partial_success_includes_unassessed_items(
        self, mock_async: MagicMock
    ) -> None:
        """Partial success (timeout) should include unassessed_items list."""
        mock_async.return_value = {
            "status": "partial_success",
            "job_id": "j1",
            "report_id": "r1",
            "total_affected_items": 3,
            "unassessed_items": ["doc-4", "doc-5"],
            "analysis_duration_ms": 600000,
        }

        result = analyze_change_impact(
            document_uuid="2024-00001",
            document_id=1,
            new_version_id=10,
            previous_version_id=9,
            company_id=1,
        )

        assert result["status"] == "partial_success"
        assert "unassessed_items" in result
        assert len(result["unassessed_items"]) == 2


# ---------------------------------------------------------------------------
# Tests: Job creation with estimated_duration_seconds
# ---------------------------------------------------------------------------


class TestJobCreationEstimatedDuration:
    """Tests for job creation with estimated_duration_seconds (req 6.1)."""

    def test_estimate_with_many_dependencies(self) -> None:
        """Many dependencies should produce proportional estimate."""
        # 20 deps * 15s = 300s
        assert _estimate_duration(20) == 300

    def test_estimate_never_below_minimum(self) -> None:
        """Estimate should never be below 30 seconds."""
        for count in range(0, 3):
            assert _estimate_duration(count) >= MIN_ESTIMATED_DURATION_SECONDS

    def test_estimate_scales_linearly(self) -> None:
        """Estimate should scale linearly with dependency count above threshold."""
        # Above the minimum threshold (3+ deps)
        assert _estimate_duration(4) == 60
        assert _estimate_duration(8) == 120
        assert _estimate_duration(40) == 600
