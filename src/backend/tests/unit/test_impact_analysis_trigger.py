"""Unit tests for the impact analysis event trigger.

Tests the SQLAlchemy after_insert listener on DocumentVersion that
conditionally enqueues the analyze_change_impact Celery task.

Covers:
- Document filtering (Draft status, CSV validation records)
- Conflict detection with staleness threshold
- Celery broker unavailability handling
- Successful enqueue path

References:
    - Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 2.9
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from alcoabase.services.impact_analysis_trigger import (
    IMPACT_ANALYSIS_OPERATION,
    STALENESS_THRESHOLD_SECONDS,
    _enqueue_impact_analysis,
    _is_eligible_for_analysis,
    _has_active_non_stale_job,
    _on_document_version_after_insert,
    register_impact_analysis_trigger,
)


# ---------------------------------------------------------------------------
# Helpers: Mock objects
# ---------------------------------------------------------------------------


def _make_document(
    document_uuid: str = "2024-00001",
    current_status: str = "Approved",
    is_csv_validation_record: bool = False,
    company_id: int = 1,
) -> MagicMock:
    """Create a mock Document instance."""
    doc = MagicMock()
    doc.document_uuid = document_uuid
    doc.current_status = current_status
    doc.is_csv_validation_record = is_csv_validation_record
    doc.company_id = company_id
    return doc


def _make_document_version(
    id: int = 10,
    document_id: int = 1,
    uploaded_by: int = 5,
) -> MagicMock:
    """Create a mock DocumentVersion instance."""
    version = MagicMock()
    version.id = id
    version.document_id = document_id
    version.uploaded_by = uploaded_by
    return version


# ---------------------------------------------------------------------------
# Tests: _is_eligible_for_analysis
# ---------------------------------------------------------------------------


class TestIsEligibleForAnalysis:
    """Tests for the document eligibility filter."""

    def test_approved_document_is_eligible(self) -> None:
        """Approved, non-CSV documents should be eligible."""
        doc = _make_document(current_status="Approved")
        assert _is_eligible_for_analysis(doc) is True

    def test_active_document_is_eligible(self) -> None:
        """Active documents should be eligible."""
        doc = _make_document(current_status="Active")
        assert _is_eligible_for_analysis(doc) is True

    def test_draft_document_is_not_eligible(self) -> None:
        """Draft documents should be excluded."""
        doc = _make_document(current_status="Draft")
        assert _is_eligible_for_analysis(doc) is False

    def test_csv_validation_record_is_not_eligible(self) -> None:
        """CSV validation records should be excluded."""
        doc = _make_document(is_csv_validation_record=True)
        assert _is_eligible_for_analysis(doc) is False

    def test_draft_csv_record_is_not_eligible(self) -> None:
        """Documents that are both Draft and CSV should be excluded."""
        doc = _make_document(
            current_status="Draft", is_csv_validation_record=True
        )
        assert _is_eligible_for_analysis(doc) is False

    def test_review_status_is_eligible(self) -> None:
        """Documents in Review status should be eligible."""
        doc = _make_document(current_status="Review")
        assert _is_eligible_for_analysis(doc) is True


# ---------------------------------------------------------------------------
# Tests: _has_active_non_stale_job
# ---------------------------------------------------------------------------


class TestHasActiveNonStaleJob:
    """Tests for conflict detection with staleness threshold."""

    def test_no_active_job_returns_none(self) -> None:
        """When no processing job exists, returns None."""
        session = MagicMock()
        result_mock = MagicMock()
        result_mock.first.return_value = None
        session.execute.return_value = result_mock

        result = _has_active_non_stale_job(session, document_id=1)
        assert result is None

    def test_active_recent_job_returns_job_id(self) -> None:
        """When a recent processing job exists, returns its job_id."""
        session = MagicMock()
        result_mock = MagicMock()
        # Job started 60 seconds ago (well within threshold)
        recent_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        result_mock.first.return_value = ("job-123", recent_time)
        session.execute.return_value = result_mock

        result = _has_active_non_stale_job(session, document_id=1)
        assert result == "job-123"

    def test_stale_job_returns_none(self) -> None:
        """When a stale processing job exists (>600s), returns None."""
        session = MagicMock()
        result_mock = MagicMock()
        # Job started 700 seconds ago (beyond threshold)
        stale_time = datetime.now(timezone.utc) - timedelta(seconds=700)
        result_mock.first.return_value = ("job-old", stale_time)
        session.execute.return_value = result_mock

        result = _has_active_non_stale_job(session, document_id=1)
        assert result is None

    def test_job_at_exact_threshold_returns_none(self) -> None:
        """A job exactly at the threshold boundary is considered stale."""
        session = MagicMock()
        result_mock = MagicMock()
        # Job started exactly at threshold
        threshold_time = datetime.now(timezone.utc) - timedelta(
            seconds=STALENESS_THRESHOLD_SECONDS
        )
        result_mock.first.return_value = ("job-boundary", threshold_time)
        session.execute.return_value = result_mock

        result = _has_active_non_stale_job(session, document_id=1)
        assert result is None

    def test_naive_datetime_handled(self) -> None:
        """Handles naive datetime from DB by treating as UTC."""
        session = MagicMock()
        result_mock = MagicMock()
        # Naive datetime (no tzinfo) — 60 seconds ago
        naive_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=60
        )
        result_mock.first.return_value = ("job-naive", naive_time)
        session.execute.return_value = result_mock

        result = _has_active_non_stale_job(session, document_id=1)
        assert result == "job-naive"


# ---------------------------------------------------------------------------
# Tests: _enqueue_impact_analysis
# ---------------------------------------------------------------------------


class TestEnqueueImpactAnalysis:
    """Tests for the Celery task enqueue logic."""

    @patch("alcoabase.tasks.celery_app.celery_app")
    def test_successful_enqueue(self, mock_celery_app: MagicMock) -> None:
        """Successfully enqueues the task with correct parameters."""
        _enqueue_impact_analysis(
            document_uuid="2024-00001",
            document_id=1,
            version_id=10,
            company_id=1,
            uploaded_by=5,
        )

        mock_celery_app.send_task.assert_called_once_with(
            "alcoabase.tasks.impact_analysis_tasks.analyze_change_impact",
            kwargs={
                "document_uuid": "2024-00001",
                "document_id": 1,
                "version_id": 10,
                "company_id": 1,
                "uploaded_by": 5,
            },
            queue="ai_operations",
        )

    @patch("alcoabase.tasks.celery_app.celery_app")
    def test_broker_unavailable_does_not_raise(
        self, mock_celery_app: MagicMock
    ) -> None:
        """When Celery broker is unavailable, logs error but does not raise."""
        mock_celery_app.send_task.side_effect = ConnectionError(
            "Redis connection refused"
        )

        # Should not raise
        _enqueue_impact_analysis(
            document_uuid="2024-00001",
            document_id=1,
            version_id=10,
            company_id=1,
            uploaded_by=5,
        )

    @patch("alcoabase.tasks.celery_app.celery_app")
    def test_generic_exception_does_not_raise(
        self, mock_celery_app: MagicMock
    ) -> None:
        """Any exception during enqueue is caught and logged."""
        mock_celery_app.send_task.side_effect = RuntimeError("Unexpected error")

        # Should not raise
        _enqueue_impact_analysis(
            document_uuid="2024-00001",
            document_id=1,
            version_id=10,
            company_id=1,
            uploaded_by=5,
        )


# ---------------------------------------------------------------------------
# Tests: _on_document_version_after_insert (integration of all logic)
# ---------------------------------------------------------------------------


class TestOnDocumentVersionAfterInsert:
    """Tests for the full after_insert event handler."""

    @patch("alcoabase.services.impact_analysis_trigger._enqueue_impact_analysis")
    @patch("alcoabase.services.impact_analysis_trigger._has_active_non_stale_job")
    @patch("alcoabase.services.impact_analysis_trigger.Session")
    def test_eligible_document_triggers_enqueue(
        self,
        mock_session_cls: MagicMock,
        mock_has_active: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        """An eligible document version triggers task enqueue."""
        doc = _make_document(
            document_uuid="2024-00001",
            current_status="Approved",
            company_id=1,
        )
        version = _make_document_version(id=10, document_id=1, uploaded_by=5)

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = doc
        mock_has_active.return_value = None

        _on_document_version_after_insert(
            mapper=MagicMock(),
            connection=MagicMock(),
            target=version,
        )

        mock_enqueue.assert_called_once_with(
            document_uuid="2024-00001",
            document_id=1,
            version_id=10,
            company_id=1,
            uploaded_by=5,
        )
        mock_session.close.assert_called_once()

    @patch("alcoabase.services.impact_analysis_trigger._enqueue_impact_analysis")
    @patch("alcoabase.services.impact_analysis_trigger.Session")
    def test_draft_document_does_not_trigger(
        self,
        mock_session_cls: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        """A Draft document does not trigger task enqueue."""
        doc = _make_document(current_status="Draft")
        version = _make_document_version()

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = doc

        _on_document_version_after_insert(
            mapper=MagicMock(),
            connection=MagicMock(),
            target=version,
        )

        mock_enqueue.assert_not_called()
        mock_session.close.assert_called_once()

    @patch("alcoabase.services.impact_analysis_trigger._enqueue_impact_analysis")
    @patch("alcoabase.services.impact_analysis_trigger.Session")
    def test_csv_record_does_not_trigger(
        self,
        mock_session_cls: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        """A CSV validation record does not trigger task enqueue."""
        doc = _make_document(is_csv_validation_record=True)
        version = _make_document_version()

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = doc

        _on_document_version_after_insert(
            mapper=MagicMock(),
            connection=MagicMock(),
            target=version,
        )

        mock_enqueue.assert_not_called()
        mock_session.close.assert_called_once()

    @patch("alcoabase.services.impact_analysis_trigger._enqueue_impact_analysis")
    @patch("alcoabase.services.impact_analysis_trigger._has_active_non_stale_job")
    @patch("alcoabase.services.impact_analysis_trigger.Session")
    def test_active_job_conflict_does_not_trigger(
        self,
        mock_session_cls: MagicMock,
        mock_has_active: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        """An active non-stale job prevents new task enqueue."""
        doc = _make_document(current_status="Approved")
        version = _make_document_version()

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = doc
        mock_has_active.return_value = "existing-job-id"

        _on_document_version_after_insert(
            mapper=MagicMock(),
            connection=MagicMock(),
            target=version,
        )

        mock_enqueue.assert_not_called()
        mock_session.close.assert_called_once()

    @patch("alcoabase.services.impact_analysis_trigger._enqueue_impact_analysis")
    @patch("alcoabase.services.impact_analysis_trigger.Session")
    def test_missing_document_does_not_trigger(
        self,
        mock_session_cls: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        """If the parent document is not found, does not trigger."""
        version = _make_document_version()

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.return_value = None  # Document not found

        _on_document_version_after_insert(
            mapper=MagicMock(),
            connection=MagicMock(),
            target=version,
        )

        mock_enqueue.assert_not_called()
        mock_session.close.assert_called_once()

    @patch("alcoabase.services.impact_analysis_trigger._enqueue_impact_analysis")
    @patch("alcoabase.services.impact_analysis_trigger.Session")
    def test_exception_in_handler_does_not_propagate(
        self,
        mock_session_cls: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        """Exceptions in the handler are caught and do not propagate."""
        version = _make_document_version()

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.get.side_effect = RuntimeError("DB error")

        # Should not raise
        _on_document_version_after_insert(
            mapper=MagicMock(),
            connection=MagicMock(),
            target=version,
        )

        mock_enqueue.assert_not_called()
        mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: register_impact_analysis_trigger
# ---------------------------------------------------------------------------


class TestRegisterImpactAnalysisTrigger:
    """Tests for the listener registration function."""

    @patch("alcoabase.services.impact_analysis_trigger.event")
    def test_registers_after_insert_listener(
        self, mock_event: MagicMock
    ) -> None:
        """Verifies after_insert listener is registered on DocumentVersion."""
        from alcoabase.models.document import DocumentVersion as DV

        register_impact_analysis_trigger()

        mock_event.listen.assert_called_once_with(
            DV,
            "after_insert",
            _on_document_version_after_insert,
        )


# ---------------------------------------------------------------------------
# Tests: Constants
# ---------------------------------------------------------------------------


class TestConstants:
    """Tests for module-level constants."""

    def test_staleness_threshold_is_600_seconds(self) -> None:
        """Staleness threshold should be 600 seconds per requirements."""
        assert STALENESS_THRESHOLD_SECONDS == 600

    def test_operation_name(self) -> None:
        """Operation name should be 'change_impact_analysis'."""
        assert IMPACT_ANALYSIS_OPERATION == "change_impact_analysis"
