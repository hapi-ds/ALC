"""Unit tests for the centralized vigilance audit logging module.

Verifies that all audit helper functions emit structured log entries
with the correct event type, required fields, and never log prohibited
content (full literature text, LLM prompts/responses).

References:
    - Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.7
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from alcoabase.literature.vigilance.audit import (
    EVENT_ESCALATION_TRIGGERED,
    EVENT_PRODUCT_CREATED,
    EVENT_PRODUCT_STATUS_CHANGED,
    EVENT_PRODUCT_UPDATED,
    EVENT_PROFILE_CREATED,
    EVENT_PROFILE_STATUS_CHANGED,
    EVENT_PROFILE_UPDATED,
    EVENT_REPORT_GENERATED,
    EVENT_REPORT_STATUS_CHANGED,
    EVENT_RETRY_ATTEMPT,
    EVENT_SEARCH_EXECUTION_COMPLETED,
    EVENT_SIGNAL_CREATED,
    EVENT_SIGNAL_DISPOSITION_CHANGED,
    audit_logger,
    log_entity_event,
    log_escalation,
    log_report_event,
    log_retry_attempt,
    log_search_execution,
    log_signal_created,
    log_signal_disposition_changed,
)


class TestLogSearchExecution:
    """Tests for log_search_execution (Requirement 12.1)."""

    def test_emits_structured_audit_entry(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_search_execution(
                execution_id=1,
                profile_id=10,
                product_id=100,
                company_id=5,
                sources_queried=["pubmed", "crossref"],
                total_results_found=42,
                results_ingested=30,
                execution_duration_ms=12500,
                status="completed",
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.event_type == EVENT_SEARCH_EXECUTION_COMPLETED
        assert record.execution_id == 1
        assert record.profile_id == 10
        assert record.product_id == 100
        assert record.company_id == 5
        assert record.sources_queried == ["pubmed", "crossref"]
        assert record.total_results_found == 42
        assert record.results_ingested == 30
        assert record.execution_duration_ms == 12500
        assert record.status == "completed"
        assert "timestamp" in record.__dict__

    def test_logs_failed_status(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_search_execution(
                execution_id=2,
                profile_id=11,
                product_id=101,
                company_id=5,
                sources_queried=[],
                total_results_found=0,
                results_ingested=0,
                execution_duration_ms=3600000,
                status="failed",
            )

        record = caplog.records[0]
        assert record.status == "failed"


class TestLogSignalCreated:
    """Tests for log_signal_created (Requirement 12.2)."""

    def test_emits_structured_audit_entry(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_signal_created(
                signal_id=7,
                ingestion_record_id=200,
                product_id=100,
                profile_id=10,
                company_id=5,
                severity="critical",
                confidence=0.92,
                detection_duration_ms=4500,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.event_type == EVENT_SIGNAL_CREATED
        assert record.signal_id == 7
        assert record.ingestion_record_id == 200
        assert record.product_id == 100
        assert record.profile_id == 10
        assert record.company_id == 5
        assert record.severity == "critical"
        assert record.confidence == 0.92
        assert record.detection_duration_ms == 4500
        assert "timestamp" in record.__dict__


class TestLogSignalDispositionChanged:
    """Tests for log_signal_disposition_changed (Requirement 12.3)."""

    def test_confirmed_disposition(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_signal_disposition_changed(
                signal_id=7,
                company_id=5,
                previous_disposition="under_review",
                new_disposition="confirmed",
                acting_user_id=42,
                confirmation_note="Confirmed genuine safety signal per MDR Art 87.",
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_SIGNAL_DISPOSITION_CHANGED
        assert record.signal_id == 7
        assert record.previous_disposition == "under_review"
        assert record.new_disposition == "confirmed"
        assert record.acting_user_id == 42
        assert "Confirmed genuine" in record.confirmation_note

    def test_dismissed_disposition(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_signal_disposition_changed(
                signal_id=8,
                company_id=5,
                previous_disposition="under_review",
                new_disposition="dismissed",
                acting_user_id=43,
                dismissal_reason="False positive - unrelated product.",
            )

        record = caplog.records[0]
        assert record.new_disposition == "dismissed"
        assert record.dismissal_reason == "False positive - unrelated product."

    def test_truncates_long_notes(self, caplog: pytest.LogCaptureFixture) -> None:
        """Ensures notes are truncated to 500 chars (never log excessive text)."""
        long_note = "X" * 1000
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_signal_disposition_changed(
                signal_id=9,
                company_id=5,
                previous_disposition="under_review",
                new_disposition="confirmed",
                acting_user_id=44,
                confirmation_note=long_note,
            )

        record = caplog.records[0]
        assert len(record.confirmation_note) == 500


class TestLogEscalation:
    """Tests for log_escalation (Requirement 12.4)."""

    def test_emits_structured_escalation_entry(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_escalation(
                signal_id=7,
                company_id=5,
                escalation_type="impact_analysis",
                target_service_invoked="ImpactAnalysisService",
                success=True,
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_ESCALATION_TRIGGERED
        assert record.signal_id == 7
        assert record.escalation_type == "impact_analysis"
        assert record.target_service_invoked == "ImpactAnalysisService"
        assert record.success is True

    def test_logs_failed_escalation(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_escalation(
                signal_id=7,
                company_id=5,
                escalation_type="contradiction_check",
                target_service_invoked="ContradictionDetectionService",
                success=False,
            )

        record = caplog.records[0]
        assert record.success is False


class TestLogReportEvent:
    """Tests for log_report_event (Requirement 12.5)."""

    def test_report_generated(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_report_event(
                report_id=50,
                product_id=100,
                company_id=5,
                period_start="2024-01-01",
                period_end="2024-03-31",
                action="generated",
                new_status="generated",
                acting_user_id=None,
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_REPORT_GENERATED
        assert record.report_id == 50
        assert record.action == "generated"
        assert record.acting_user_id is None

    def test_report_status_change(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_report_event(
                report_id=50,
                product_id=100,
                company_id=5,
                period_start="2024-01-01",
                period_end="2024-03-31",
                action="status_change",
                new_status="approved",
                acting_user_id=42,
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_REPORT_STATUS_CHANGED
        assert record.new_status == "approved"
        assert record.acting_user_id == 42


class TestLogEntityEvent:
    """Tests for log_entity_event (Requirement 12.6)."""

    def test_product_created(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_entity_event(
                entity_type="product",
                entity_id=100,
                company_id=5,
                action="create",
                acting_user_id=42,
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_PRODUCT_CREATED
        assert record.entity_type == "product"
        assert record.entity_id == 100
        assert record.action == "create"
        assert record.changed_fields == []

    def test_profile_updated_with_changed_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_entity_event(
                entity_type="profile",
                entity_id=10,
                company_id=5,
                action="update",
                acting_user_id=42,
                changed_fields=["name", "schedule_cron", "search_terms"],
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_PROFILE_UPDATED
        assert record.changed_fields == ["name", "schedule_cron", "search_terms"]

    def test_product_status_change(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_entity_event(
                entity_type="product",
                entity_id=100,
                company_id=5,
                action="status_change",
                acting_user_id=42,
                changed_fields=["status"],
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_PRODUCT_STATUS_CHANGED


class TestLogRetryAttempt:
    """Tests for log_retry_attempt (Requirement 13.7)."""

    def test_emits_retry_entry(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_retry_attempt(
                task_type="search_execution",
                attempt_number=2,
                error_message="ConnectionError: gateway timeout",
                backoff_duration_s=900,
                entity_ids={"profile_id": 10, "company_id": 5},
            )

        record = caplog.records[0]
        assert record.event_type == EVENT_RETRY_ATTEMPT
        assert record.task_type == "search_execution"
        assert record.attempt_number == 2
        assert record.backoff_duration_s == 900
        assert record.entity_ids == {"profile_id": 10, "company_id": 5}
        assert "gateway timeout" in record.error_message

    def test_truncates_long_error_messages(self, caplog: pytest.LogCaptureFixture) -> None:
        """Ensures error messages are capped at 500 chars (never log full tracebacks)."""
        long_error = "E" * 1000
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_retry_attempt(
                task_type="signal_detection",
                attempt_number=3,
                error_message=long_error,
                backoff_duration_s=600,
                entity_ids={"execution_id": 1},
            )

        record = caplog.records[0]
        assert len(record.error_message) == 500


class TestAuditLoggerNeverLogsProhibitedContent:
    """Verify the audit module never logs prohibited content (Requirement 12.7)."""

    def test_signal_creation_does_not_log_literature_content(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Signal creation logs metadata only, no paper body."""
        with caplog.at_level(logging.INFO, logger="alcoabase.audit.vigilance"):
            log_signal_created(
                signal_id=1,
                ingestion_record_id=200,
                product_id=100,
                profile_id=10,
                company_id=5,
                severity="major",
                confidence=0.85,
                detection_duration_ms=3000,
            )

        record = caplog.records[0]
        # The log entry should contain only identifiers and metrics
        log_text = str(record.__dict__)
        # Should NOT contain words like "abstract", "body", "prompt"
        assert "abstract" not in log_text.lower()
        assert "body_text" not in log_text.lower()
        assert "prompt" not in log_text.lower()

    def test_event_type_constants_defined(self) -> None:
        """All required event types are defined as module constants."""
        assert EVENT_SEARCH_EXECUTION_COMPLETED == "vigilance.search_execution_completed"
        assert EVENT_SIGNAL_CREATED == "vigilance.signal_created"
        assert EVENT_SIGNAL_DISPOSITION_CHANGED == "vigilance.signal_disposition_changed"
        assert EVENT_ESCALATION_TRIGGERED == "vigilance.escalation_triggered"
        assert EVENT_REPORT_GENERATED == "vigilance.report_generated"
        assert EVENT_REPORT_STATUS_CHANGED == "vigilance.report_status_changed"
        assert EVENT_PRODUCT_CREATED == "vigilance.product_created"
        assert EVENT_PRODUCT_UPDATED == "vigilance.product_updated"
        assert EVENT_PRODUCT_STATUS_CHANGED == "vigilance.product_status_changed"
        assert EVENT_PROFILE_CREATED == "vigilance.profile_created"
        assert EVENT_PROFILE_UPDATED == "vigilance.profile_updated"
        assert EVENT_PROFILE_STATUS_CHANGED == "vigilance.profile_status_changed"
        assert EVENT_RETRY_ATTEMPT == "vigilance.retry_attempt"

    def test_audit_logger_uses_dedicated_namespace(self) -> None:
        """The audit logger is independent from application loggers."""
        assert audit_logger.name == "alcoabase.audit.vigilance"
