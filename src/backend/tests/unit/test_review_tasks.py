"""Unit tests for Celery review tasks.

Tests the review task functions including response parsing, failure handling,
quorum checking, and master summary execution.

References:
    - Task 5.2: Implement Celery review tasks
    - Requirements: 1.4, 1.5, 1.6, 1.7, 2.1–2.7, 3.1–3.8
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.tasks.review_tasks import (
    _count_findings_from_reports,
    _get_master_auditor_system_prompt,
    _parse_review_response,
    check_review_completion,
    execute_agent_review,
    execute_master_summary,
    scan_anomalies_periodic,
)


# ---------------------------------------------------------------------------
# Tests for _parse_review_response
# ---------------------------------------------------------------------------


class TestParseReviewResponse:
    """Tests for the LLM response parsing function."""

    def test_valid_json_response(self):
        """Parse a well-formed JSON response."""
        response = json.dumps({
            "overall_status": "Pass with Findings",
            "findings": [
                {
                    "severity": "Major",
                    "chapter": "Section 3",
                    "description": "Missing validation step",
                    "recommendation": "Add input validation",
                }
            ],
            "chapter_results": [
                {"chapter_name": "Introduction", "present": True, "complete": True}
            ],
            "summary": "Document has minor issues.",
        })
        result = _parse_review_response(response)
        assert result is not None
        assert result["overall_status"] == "Pass with Findings"
        assert len(result["findings"]) == 1
        assert result["findings"][0]["severity"] == "Major"

    def test_json_wrapped_in_code_block(self):
        """Parse JSON wrapped in markdown code blocks."""
        inner = json.dumps({
            "overall_status": "Pass",
            "findings": [],
            "summary": "All good.",
        })
        response = f"```json\n{inner}\n```"
        result = _parse_review_response(response)
        assert result is not None
        assert result["overall_status"] == "Pass"

    def test_json_with_surrounding_text(self):
        """Parse JSON embedded in surrounding text."""
        inner = json.dumps({
            "overall_status": "Fail",
            "findings": [{"severity": "Critical", "chapter": "Ch1", "description": "Bad"}],
            "summary": "Critical issues found.",
        })
        response = f"Here is my analysis:\n{inner}\nEnd of review."
        result = _parse_review_response(response)
        assert result is not None
        assert result["overall_status"] == "Fail"

    def test_invalid_json_returns_none(self):
        """Return None for completely invalid responses."""
        result = _parse_review_response("This is not JSON at all.")
        assert result is None

    def test_empty_string_returns_none(self):
        """Return None for empty string."""
        result = _parse_review_response("")
        assert result is None

    def test_missing_findings_key_adds_empty_list(self):
        """Add empty findings list if key is missing."""
        response = json.dumps({
            "overall_status": "Pass",
            "summary": "No issues.",
        })
        result = _parse_review_response(response)
        assert result is not None
        assert result["findings"] == []

    def test_findings_not_list_replaced_with_empty(self):
        """Replace non-list findings with empty list."""
        response = json.dumps({
            "overall_status": "Pass",
            "findings": "none",
            "summary": "Clean.",
        })
        result = _parse_review_response(response)
        assert result is not None
        assert result["findings"] == []

    def test_code_block_without_json_label(self):
        """Parse JSON in code block without json label."""
        inner = json.dumps({"overall_status": "Pass", "findings": [], "summary": "OK"})
        response = f"```\n{inner}\n```"
        result = _parse_review_response(response)
        assert result is not None
        assert result["overall_status"] == "Pass"


# ---------------------------------------------------------------------------
# Tests for _count_findings_from_reports
# ---------------------------------------------------------------------------


class TestCountFindingsFromReports:
    """Tests for finding count aggregation across reports."""

    def test_empty_reports(self):
        """Return zero counts for empty report list."""
        result = _count_findings_from_reports([])
        assert result == {
            "Critical": 0,
            "Major": 0,
            "Minor": 0,
            "Informational": 0,
        }

    def test_single_report_with_findings(self):
        """Count findings from a single report."""
        reports = [
            {
                "findings": [
                    {"severity": "Critical", "chapter": "Ch1"},
                    {"severity": "Major", "chapter": "Ch2"},
                    {"severity": "Major", "chapter": "Ch3"},
                    {"severity": "Minor", "chapter": "Ch4"},
                ]
            }
        ]
        result = _count_findings_from_reports(reports)
        assert result["Critical"] == 1
        assert result["Major"] == 2
        assert result["Minor"] == 1
        assert result["Informational"] == 0

    def test_multiple_reports(self):
        """Aggregate findings across multiple reports."""
        reports = [
            {"findings": [{"severity": "Critical", "chapter": "Ch1"}]},
            {"findings": [{"severity": "Critical", "chapter": "Ch1"}, {"severity": "Minor", "chapter": "Ch2"}]},
            {"findings": [{"severity": "Informational", "chapter": "Ch3"}]},
        ]
        result = _count_findings_from_reports(reports)
        assert result["Critical"] == 2
        assert result["Minor"] == 1
        assert result["Informational"] == 1

    def test_report_without_findings_key(self):
        """Handle reports missing the findings key."""
        reports = [{"summary": "No findings"}]
        result = _count_findings_from_reports(reports)
        assert result == {
            "Critical": 0,
            "Major": 0,
            "Minor": 0,
            "Informational": 0,
        }

    def test_unknown_severity_ignored(self):
        """Ignore findings with unknown severity values."""
        reports = [
            {"findings": [{"severity": "Unknown", "chapter": "Ch1"}]}
        ]
        result = _count_findings_from_reports(reports)
        assert all(v == 0 for v in result.values())


# ---------------------------------------------------------------------------
# Tests for _get_master_auditor_system_prompt
# ---------------------------------------------------------------------------


class TestGetMasterAuditorSystemPrompt:
    """Tests for loading the Master Auditor system prompt."""

    def test_returns_non_empty_string(self):
        """System prompt should be a non-empty string."""
        prompt = _get_master_auditor_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_contains_key_instructions(self):
        """System prompt should contain key Master Auditor instructions."""
        prompt = _get_master_auditor_system_prompt()
        assert "Master Auditor" in prompt


# ---------------------------------------------------------------------------
# Tests for execute_agent_review task
# ---------------------------------------------------------------------------


class TestExecuteAgentReviewTask:
    """Tests for the execute_agent_review Celery task."""

    def test_task_has_correct_time_limit(self):
        """Task should have time_limit=1800 (30 minutes)."""
        assert execute_agent_review.time_limit == 1800

    def test_task_has_max_retries_zero(self):
        """Task should not retry on failure."""
        assert execute_agent_review.max_retries == 0

    def test_task_is_bound(self):
        """Task should be bound (receives self)."""
        # Bound tasks have a 'request' attribute accessible via the task
        assert hasattr(execute_agent_review, "request")


# ---------------------------------------------------------------------------
# Tests for execute_master_summary task
# ---------------------------------------------------------------------------


class TestExecuteMasterSummaryTask:
    """Tests for the execute_master_summary Celery task."""

    def test_task_has_max_retries_one(self):
        """Task should retry at most once."""
        assert execute_master_summary.max_retries == 1


# ---------------------------------------------------------------------------
# Tests for check_review_completion task
# ---------------------------------------------------------------------------


class TestCheckReviewCompletionTask:
    """Tests for the check_review_completion Celery task."""

    def test_task_is_registered(self):
        """Task should be registered with Celery."""
        assert check_review_completion.name is not None


# ---------------------------------------------------------------------------
# Tests for scan_anomalies_periodic task
# ---------------------------------------------------------------------------


class TestScanAnomaliesPeriodicTask:
    """Tests for the scan_anomalies_periodic Celery task."""

    def test_task_is_registered(self):
        """Task should be registered with Celery."""
        assert scan_anomalies_periodic.name == (
            "alcoabase.tasks.review_tasks.scan_anomalies_periodic"
        )

    def test_beat_schedule_configured(self):
        """Celery beat should schedule the task every 15 minutes."""
        from alcoabase.tasks.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "scan-anomalies-every-15-minutes" in schedule

        entry = schedule["scan-anomalies-every-15-minutes"]
        assert entry["task"] == "alcoabase.tasks.review_tasks.scan_anomalies_periodic"

    @patch("alcoabase.tasks.review_tasks._scan_anomalies_periodic_async")
    def test_task_calls_async_implementation(self, mock_async):
        """Task should delegate to the async implementation."""
        mock_async.return_value = {
            "total_companies": 2,
            "total_alerts": 3,
            "companies": {"1": 2, "2": 1},
        }

        result = scan_anomalies_periodic()

        assert result["total_companies"] == 2
        assert result["total_alerts"] == 3
        assert result["companies"]["1"] == 2
        assert result["companies"]["2"] == 1

    @patch("alcoabase.tasks.review_tasks._scan_anomalies_periodic_async")
    def test_task_handles_no_companies(self, mock_async):
        """Task should handle case with no active companies."""
        mock_async.return_value = {
            "total_companies": 0,
            "total_alerts": 0,
            "companies": {},
        }

        result = scan_anomalies_periodic()

        assert result["total_companies"] == 0
        assert result["total_alerts"] == 0
        assert result["companies"] == {}
