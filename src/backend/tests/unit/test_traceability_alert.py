"""Unit tests for TraceabilityAlertService and event trigger.

Tests alert creation on ImpactReport event, severity determination,
stale link marking, alert resolution, stale marker clearing,
already-resolved handling (409), event listener filtering, and
graceful failure handling.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from alcoabase.models.traceability import (
    StaleLinkMarker,
    TraceabilityAlert,
    TraceabilityMatrix,
)
from alcoabase.schemas.traceability import AlertFilters
from alcoabase.services.traceability_alert import TraceabilityAlertService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    session.rollback = AsyncMock()
    session.flush = AsyncMock()

    class _AsyncCtx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    def factory():
        return _AsyncCtx()

    return factory, session


@pytest.fixture
def sample_matrix():
    """Create a sample TraceabilityMatrix mock."""
    matrix = MagicMock(spec=TraceabilityMatrix)
    matrix.matrix_id = "matrix-uuid-001"
    matrix.company_id = 1
    matrix.source_document_uuids = ["doc-src-001", "doc-src-002"]
    matrix.traceability_links = [
        {
            "source_document_uuid": "doc-src-001",
            "requirement_id": "REQ-001",
            "test_case_id": "TC-001",
        },
        {
            "source_document_uuid": "doc-src-001",
            "requirement_id": "REQ-002",
            "test_case_id": "TC-002",
        },
        {
            "source_document_uuid": "doc-src-002",
            "requirement_id": "REQ-003",
            "test_case_id": "TC-003",
        },
    ]
    matrix.deleted_at = None
    return matrix


@pytest.fixture
def sample_alert():
    """Create a sample TraceabilityAlert mock."""
    alert = MagicMock(spec=TraceabilityAlert)
    alert.alert_id = "alert-uuid-001"
    alert.triggering_report_id = "report-uuid-001"
    alert.affected_matrix_ids = ["matrix-uuid-001"]
    alert.affected_link_count = 2
    alert.alert_severity = "critical"
    alert.is_resolved = False
    alert.resolved_at = None
    alert.resolved_by = None
    alert.resolution_action = None
    alert.resolution_note = None
    alert.company_id = 1
    alert.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return alert


# ---------------------------------------------------------------------------
# Tests: create_alert (Requirement 9.1, 9.2, 9.5, 9.7)
# ---------------------------------------------------------------------------


class TestCreateAlert:
    """Tests for TraceabilityAlertService.create_alert."""

    @pytest.mark.asyncio
    async def test_creates_alert_when_affected_matrices_found(
        self, mock_session_factory, sample_matrix,
    ):
        """Alert is created when triggering document is a source in matrices."""
        factory, session = mock_session_factory

        # Mock _find_affected_matrices returning one matrix
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sample_matrix]

        # Mock _determine_alert_severity returning "major"
        impact_report = MagicMock()
        impact_report.gap_findings = [{"severity": "major"}]
        impact_report.affected_items = []

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # _find_affected_matrices query
                result.scalars.return_value = scalars_mock
            elif call_count[0] == 2:
                # _determine_alert_severity query
                result.scalar_one_or_none.return_value = impact_report
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        # Alert should be created (session.add called)
        session.add.assert_called_once()
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_affected_matrices(
        self, mock_session_factory,
    ):
        """Returns None when no matrices contain the triggering document."""
        factory, session = mock_session_factory

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []

        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-nonexistent",
            company_id=1,
        )

        assert alert is None
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_duplicate_alert_integrity_error(
        self, mock_session_factory, sample_matrix,
    ):
        """Returns None on IntegrityError (duplicate alert for same report)."""
        factory, session = mock_session_factory

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sample_matrix]

        impact_report = MagicMock()
        impact_report.gap_findings = [{"severity": "minor"}]
        impact_report.affected_items = []

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value = scalars_mock
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = impact_report
            return result

        session.execute = mock_execute
        session.commit = AsyncMock(
            side_effect=IntegrityError("dup", {}, None)
        )

        svc = TraceabilityAlertService(session_factory=factory)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        assert alert is None
        session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_failure_logged_returns_none(self, mock_session_factory):
        """DB failure is logged and returns None without propagating."""
        factory, session = mock_session_factory

        # Simulate a general exception during execution
        session.execute = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        svc = TraceabilityAlertService(session_factory=factory)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        # Should return None without raising (Requirement 9.7)
        assert alert is None

    @pytest.mark.asyncio
    async def test_returns_none_without_session_factory(self):
        """Returns None when session_factory is not configured."""
        svc = TraceabilityAlertService(session_factory=None)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        assert alert is None

    @pytest.mark.asyncio
    async def test_severity_determined_from_critical_findings(
        self, mock_session_factory, sample_matrix,
    ):
        """Alert severity is 'critical' when report has critical findings."""
        factory, session = mock_session_factory

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sample_matrix]

        impact_report = MagicMock()
        impact_report.gap_findings = [
            {"severity": "minor"},
            {"severity": "critical"},
        ]
        impact_report.affected_items = []

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value = scalars_mock
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = impact_report
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        # The first add call is the alert; subsequent ones are stale markers
        first_add_call = session.add.call_args_list[0]
        added_alert = first_add_call[0][0]
        assert added_alert.alert_severity == "critical"

    @pytest.mark.asyncio
    async def test_severity_defaults_to_minor_when_report_not_found(
        self, mock_session_factory, sample_matrix,
    ):
        """Alert severity defaults to 'minor' when ImpactReport not found."""
        factory, session = mock_session_factory

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [sample_matrix]

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value = scalars_mock
            elif call_count[0] == 2:
                # Report not found
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        alert = await svc.create_alert(
            triggering_report_id="report-uuid-missing",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        added_alert = session.add.call_args[0][0]
        assert added_alert.alert_severity == "minor"


# ---------------------------------------------------------------------------
# Tests: mark_stale_links (Requirement 9.4)
# ---------------------------------------------------------------------------


class TestMarkStaleLinks:
    """Tests for TraceabilityAlertService.mark_stale_links."""

    @pytest.mark.asyncio
    async def test_creates_markers_for_critical_alerts(
        self, mock_session_factory, sample_alert, sample_matrix,
    ):
        """Stale link markers are created for links from changed document."""
        factory, session = mock_session_factory

        svc = TraceabilityAlertService(session_factory=factory)
        count = await svc.mark_stale_links(
            alert=sample_alert,
            affected_matrices=[sample_matrix],
            triggering_document_uuid="doc-src-001",
        )

        # doc-src-001 has 2 links in sample_matrix
        assert count == 2
        assert session.add.call_count == 2
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_unique_constraint_on_batch_insert(
        self, mock_session_factory, sample_alert, sample_matrix,
    ):
        """Falls back to individual inserts on IntegrityError."""
        factory, session = mock_session_factory

        # First commit raises IntegrityError (batch), then individual works
        session.commit = AsyncMock(
            side_effect=IntegrityError("dup", {}, None)
        )

        svc = TraceabilityAlertService(session_factory=factory)

        # Patch _insert_markers_individually to return a count
        with patch.object(
            svc, "_insert_markers_individually", new_callable=AsyncMock
        ) as mock_individual:
            mock_individual.return_value = 1
            count = await svc.mark_stale_links(
                alert=sample_alert,
                affected_matrices=[sample_matrix],
                triggering_document_uuid="doc-src-001",
            )

        assert count == 1
        session.rollback.assert_called_once()
        mock_individual.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_without_session_factory(self, sample_alert):
        """Returns 0 when session_factory is not configured."""
        svc = TraceabilityAlertService(session_factory=None)
        count = await svc.mark_stale_links(
            alert=sample_alert,
            affected_matrices=[],
            triggering_document_uuid="doc-src-001",
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_no_markers_when_no_matching_links(
        self, mock_session_factory, sample_alert, sample_matrix,
    ):
        """No markers created when document has no links in matrices."""
        factory, session = mock_session_factory

        svc = TraceabilityAlertService(session_factory=factory)
        count = await svc.mark_stale_links(
            alert=sample_alert,
            affected_matrices=[sample_matrix],
            triggering_document_uuid="doc-nonexistent",
        )

        assert count == 0
        session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: resolve_alert (Requirement 9.3, 9.6, 9.8)
# ---------------------------------------------------------------------------


class TestResolveAlert:
    """Tests for TraceabilityAlertService.resolve_alert."""

    @pytest.mark.asyncio
    async def test_resolve_success_returns_200(
        self, mock_session_factory, sample_alert,
    ):
        """Resolving an unresolved alert returns (alert, 200)."""
        factory, session = mock_session_factory

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = sample_alert
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)

        # Patch clear_stale_markers to avoid nested session usage
        with patch.object(
            svc, "clear_stale_markers", new_callable=AsyncMock
        ) as mock_clear:
            mock_clear.return_value = 2
            alert, status = await svc.resolve_alert(
                alert_id="alert-uuid-001",
                user_id=42,
                resolution_action="links_verified",
                resolution_note="Verified all links manually.",
                company_id=1,
            )

        assert status == 200
        assert sample_alert.is_resolved is True
        assert sample_alert.resolved_by == 42
        assert sample_alert.resolution_action == "links_verified"
        assert sample_alert.resolution_note == "Verified all links manually."
        session.commit.assert_called_once()
        mock_clear.assert_called_once_with(sample_alert)

    @pytest.mark.asyncio
    async def test_resolve_not_found_returns_404(self, mock_session_factory):
        """Returns (None, 404) when alert not found or wrong company."""
        factory, session = mock_session_factory

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)
        alert, status = await svc.resolve_alert(
            alert_id="nonexistent-alert",
            user_id=42,
            resolution_action="links_verified",
            resolution_note=None,
            company_id=1,
        )

        assert alert is None
        assert status == 404

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_returns_409(
        self, mock_session_factory,
    ):
        """Returns (None, 409) when alert is already resolved."""
        factory, session = mock_session_factory

        resolved_alert = MagicMock(spec=TraceabilityAlert)
        resolved_alert.alert_id = "alert-uuid-001"
        resolved_alert.is_resolved = True
        resolved_alert.company_id = 1

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = resolved_alert
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)
        alert, status = await svc.resolve_alert(
            alert_id="alert-uuid-001",
            user_id=42,
            resolution_action="no_action_needed",
            resolution_note=None,
            company_id=1,
        )

        assert alert is None
        assert status == 409
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_returns_500_without_session_factory(self):
        """Returns (None, 500) when session_factory is not configured."""
        svc = TraceabilityAlertService(session_factory=None)
        alert, status = await svc.resolve_alert(
            alert_id="alert-uuid-001",
            user_id=42,
            resolution_action="links_verified",
            resolution_note=None,
            company_id=1,
        )

        assert alert is None
        assert status == 500


# ---------------------------------------------------------------------------
# Tests: clear_stale_markers (Requirement 9.8)
# ---------------------------------------------------------------------------


class TestClearStaleMarkers:
    """Tests for TraceabilityAlertService.clear_stale_markers."""

    @pytest.mark.asyncio
    async def test_clears_markers_on_links_verified(
        self, mock_session_factory, sample_alert,
    ):
        """Markers are cleared when resolution_action is 'links_verified'."""
        factory, session = mock_session_factory
        sample_alert.resolution_action = "links_verified"

        exec_result = MagicMock()
        exec_result.rowcount = 3
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)
        cleared = await svc.clear_stale_markers(sample_alert)

        assert cleared == 3
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_clears_markers_on_matrix_regenerated(
        self, mock_session_factory, sample_alert,
    ):
        """Markers are cleared when resolution_action is 'matrix_regenerated'."""
        factory, session = mock_session_factory
        sample_alert.resolution_action = "matrix_regenerated"

        exec_result = MagicMock()
        exec_result.rowcount = 5
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)
        cleared = await svc.clear_stale_markers(sample_alert)

        assert cleared == 5
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_does_not_clear_on_no_action_needed(
        self, mock_session_factory,
    ):
        """Markers are NOT cleared when resolution_action is 'no_action_needed'.

        This tests the resolve_alert flow to ensure clear_stale_markers
        is not called for 'no_action_needed'.
        """
        factory, session = mock_session_factory

        unresolved_alert = MagicMock(spec=TraceabilityAlert)
        unresolved_alert.alert_id = "alert-uuid-002"
        unresolved_alert.is_resolved = False
        unresolved_alert.company_id = 1

        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = unresolved_alert
        session.execute = AsyncMock(return_value=exec_result)

        svc = TraceabilityAlertService(session_factory=factory)

        with patch.object(
            svc, "clear_stale_markers", new_callable=AsyncMock
        ) as mock_clear:
            alert, status = await svc.resolve_alert(
                alert_id="alert-uuid-002",
                user_id=42,
                resolution_action="no_action_needed",
                resolution_note="No changes needed.",
                company_id=1,
            )

        assert status == 200
        # clear_stale_markers should NOT be called for "no_action_needed"
        mock_clear.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_zero_without_session_factory(self, sample_alert):
        """Returns 0 when session_factory is not configured."""
        svc = TraceabilityAlertService(session_factory=None)
        cleared = await svc.clear_stale_markers(sample_alert)

        assert cleared == 0

    @pytest.mark.asyncio
    async def test_handles_db_failure_gracefully(
        self, mock_session_factory, sample_alert,
    ):
        """Returns 0 on database failure without propagating."""
        factory, session = mock_session_factory
        sample_alert.resolution_action = "links_verified"

        session.execute = AsyncMock(
            side_effect=Exception("DB connection lost")
        )

        svc = TraceabilityAlertService(session_factory=factory)
        cleared = await svc.clear_stale_markers(sample_alert)

        assert cleared == 0


# ---------------------------------------------------------------------------
# Tests: get_alerts (Requirement 9.2, 9.6)
# ---------------------------------------------------------------------------


class TestGetAlerts:
    """Tests for TraceabilityAlertService.get_alerts."""

    @pytest.mark.asyncio
    async def test_returns_empty_without_session_factory(self):
        """Returns empty list and 0 count without session_factory."""
        svc = TraceabilityAlertService(session_factory=None)
        alerts, total = await svc.get_alerts(company_id=1)

        assert alerts == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_returns_paginated_alerts(self, mock_session_factory):
        """Returns alerts with pagination and total count."""
        factory, session = mock_session_factory

        alert1 = MagicMock(spec=TraceabilityAlert)
        alert1.alert_severity = "critical"
        alert2 = MagicMock(spec=TraceabilityAlert)
        alert2.alert_severity = "major"

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # count query
                result.scalar.return_value = 5
            else:
                # data query
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [alert1, alert2]
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        alerts, total = await svc.get_alerts(company_id=1)

        assert total == 5
        assert len(alerts) == 2
        assert alerts[0].alert_severity == "critical"
        assert alerts[1].alert_severity == "major"

    @pytest.mark.asyncio
    async def test_applies_severity_filter(self, mock_session_factory):
        """Severity filter is applied when provided."""
        factory, session = mock_session_factory

        alert1 = MagicMock(spec=TraceabilityAlert)
        alert1.alert_severity = "critical"

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 1
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = [alert1]
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        filters = AlertFilters(alert_severity="critical", limit=10, offset=0)
        alerts, total = await svc.get_alerts(company_id=1, filters=filters)

        assert total == 1
        assert len(alerts) == 1

    @pytest.mark.asyncio
    async def test_company_scoping(self, mock_session_factory):
        """Alerts are scoped to the specified company_id."""
        factory, session = mock_session_factory

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 0
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        alerts, total = await svc.get_alerts(company_id=999)

        assert total == 0
        assert alerts == []

    @pytest.mark.asyncio
    async def test_default_filters_applied(self, mock_session_factory):
        """Default AlertFilters are used when none provided."""
        factory, session = mock_session_factory

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar.return_value = 0
            else:
                scalars_mock = MagicMock()
                scalars_mock.all.return_value = []
                result.scalars.return_value = scalars_mock
            return result

        session.execute = mock_execute

        svc = TraceabilityAlertService(session_factory=factory)
        # No filters passed — defaults should be used
        alerts, total = await svc.get_alerts(company_id=1, filters=None)

        assert total == 0
        assert alerts == []


# ---------------------------------------------------------------------------
# Tests: Event trigger (Requirement 9.1, 9.5, 9.7)
# ---------------------------------------------------------------------------


class TestEventTrigger:
    """Tests for the traceability alert event trigger logic."""

    def test_has_affected_matrices_returns_true_when_match_exists(self):
        """_has_affected_matrices returns True when matrix sources match."""
        from alcoabase.services.traceability_alert_trigger import (
            _has_affected_matrices,
        )

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock()  # Non-None = match found
        mock_session.execute.return_value = mock_result

        result = _has_affected_matrices(
            session=mock_session,
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

        assert result is True
        mock_session.execute.assert_called_once()

    def test_has_affected_matrices_returns_false_when_no_match(self):
        """_has_affected_matrices returns False when no matrices match."""
        from alcoabase.services.traceability_alert_trigger import (
            _has_affected_matrices,
        )

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.first.return_value = None  # No match
        mock_session.execute.return_value = mock_result

        result = _has_affected_matrices(
            session=mock_session,
            triggering_document_uuid="doc-nonexistent",
            company_id=1,
        )

        assert result is False

    def test_on_impact_report_after_insert_skips_when_no_affected_matrices(
        self,
    ):
        """Event handler skips alert creation when no matrices are affected."""
        from alcoabase.services.traceability_alert_trigger import (
            _on_impact_report_after_insert,
        )

        target = MagicMock()
        target.triggering_document_uuid = "doc-src-001"
        target.company_id = 1
        target.report_id = "report-uuid-001"

        connection = MagicMock()

        with patch(
            "alcoabase.services.traceability_alert_trigger._has_affected_matrices",
            return_value=False,
        ) as mock_check:
            with patch(
                "alcoabase.services.traceability_alert_trigger._schedule_alert_creation",
            ) as mock_schedule:
                _on_impact_report_after_insert(
                    mapper=None, connection=connection, target=target
                )

        mock_check.assert_called_once()
        mock_schedule.assert_not_called()

    def test_on_impact_report_after_insert_schedules_when_affected(self):
        """Event handler schedules alert creation when matrices are affected."""
        from alcoabase.services.traceability_alert_trigger import (
            _on_impact_report_after_insert,
        )

        target = MagicMock()
        target.triggering_document_uuid = "doc-src-001"
        target.company_id = 1
        target.report_id = "report-uuid-001"

        connection = MagicMock()

        with patch(
            "alcoabase.services.traceability_alert_trigger._has_affected_matrices",
            return_value=True,
        ) as mock_check:
            with patch(
                "alcoabase.services.traceability_alert_trigger._schedule_alert_creation",
            ) as mock_schedule:
                _on_impact_report_after_insert(
                    mapper=None, connection=connection, target=target
                )

        mock_check.assert_called_once()
        mock_schedule.assert_called_once_with(
            triggering_report_id="report-uuid-001",
            triggering_document_uuid="doc-src-001",
            company_id=1,
        )

    def test_on_impact_report_after_insert_skips_missing_fields(self):
        """Event handler skips when target has missing required fields."""
        from alcoabase.services.traceability_alert_trigger import (
            _on_impact_report_after_insert,
        )

        target = MagicMock()
        target.triggering_document_uuid = None  # Missing field
        target.company_id = 1
        target.report_id = "report-uuid-001"

        connection = MagicMock()

        with patch(
            "alcoabase.services.traceability_alert_trigger._has_affected_matrices",
        ) as mock_check:
            with patch(
                "alcoabase.services.traceability_alert_trigger._schedule_alert_creation",
            ) as mock_schedule:
                _on_impact_report_after_insert(
                    mapper=None, connection=connection, target=target
                )

        # Should not proceed to check matrices
        mock_check.assert_not_called()
        mock_schedule.assert_not_called()

    def test_on_impact_report_after_insert_graceful_failure(self):
        """Event handler catches exceptions without propagating (Req 9.7)."""
        from alcoabase.services.traceability_alert_trigger import (
            _on_impact_report_after_insert,
        )

        target = MagicMock()
        target.triggering_document_uuid = "doc-src-001"
        target.company_id = 1
        target.report_id = "report-uuid-001"

        connection = MagicMock()

        with patch(
            "alcoabase.services.traceability_alert_trigger.Session",
            side_effect=Exception("Session creation failed"),
        ):
            # Should NOT raise — graceful failure
            _on_impact_report_after_insert(
                mapper=None, connection=connection, target=target
            )

    def test_register_traceability_alert_trigger(self):
        """register_traceability_alert_trigger attaches the event listener."""
        from alcoabase.services.traceability_alert_trigger import (
            register_traceability_alert_trigger,
        )

        with patch(
            "alcoabase.services.traceability_alert_trigger.event.listen",
        ) as mock_listen:
            register_traceability_alert_trigger()

        mock_listen.assert_called_once()
        # Verify it's listening on ImpactReport for "after_insert"
        from alcoabase.models.impact_analysis import ImpactReport

        call_args = mock_listen.call_args
        assert call_args[0][0] is ImpactReport
        assert call_args[0][1] == "after_insert"
