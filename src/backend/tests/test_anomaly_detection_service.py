"""Tests for AnomalyDetectionService.

Covers:
- Task 8.1: Implement AnomalyDetectionService
- Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.anomaly import AnomalyAlert
from alcoabase.services.anomaly_detection import AnomalyDetectionService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.expunge = MagicMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    """Create a session factory that returns the mock session as async context manager.

    Mimics async_sessionmaker behavior: factory() returns an async context manager.
    """

    class _MockContextManager:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    def factory():
        return _MockContextManager()

    return factory


@pytest.fixture
def service(mock_session_factory):
    """Create an AnomalyDetectionService with mocked session factory."""
    return AnomalyDetectionService(session_factory=mock_session_factory)


# ---------------------------------------------------------------------------
# scan_for_anomalies Tests
# ---------------------------------------------------------------------------


class TestScanForAnomalies:
    """Tests for the scan_for_anomalies orchestrator method."""

    @pytest.mark.asyncio
    async def test_calls_all_detectors(self, service):
        """scan_for_anomalies should call all five detection methods."""
        with (
            patch.object(
                service, "_detect_backdated_signatures", new_callable=AsyncMock
            ) as mock_backdated,
            patch.object(
                service, "_detect_workflow_bypasses", new_callable=AsyncMock
            ) as mock_bypasses,
            patch.object(
                service, "_detect_bulk_approvals", new_callable=AsyncMock
            ) as mock_bulk,
            patch.object(
                service, "_detect_off_hours_mutations", new_callable=AsyncMock
            ) as mock_off_hours,
            patch.object(
                service, "_detect_rapid_version_churn", new_callable=AsyncMock
            ) as mock_churn,
        ):
            mock_backdated.return_value = []
            mock_bypasses.return_value = []
            mock_bulk.return_value = []
            mock_off_hours.return_value = []
            mock_churn.return_value = []

            result = await service.scan_for_anomalies(company_id=1)

            mock_backdated.assert_called_once()
            mock_bypasses.assert_called_once()
            mock_bulk.assert_called_once()
            mock_off_hours.assert_called_once()
            mock_churn.assert_called_once()
            assert result == []

    @pytest.mark.asyncio
    async def test_aggregates_alerts_from_all_detectors(self, service):
        """scan_for_anomalies should aggregate alerts from all detectors."""
        alert1 = MagicMock(spec=AnomalyAlert)
        alert2 = MagicMock(spec=AnomalyAlert)

        with (
            patch.object(
                service, "_detect_backdated_signatures", new_callable=AsyncMock
            ) as mock_backdated,
            patch.object(
                service, "_detect_workflow_bypasses", new_callable=AsyncMock
            ) as mock_bypasses,
            patch.object(
                service, "_detect_bulk_approvals", new_callable=AsyncMock
            ) as mock_bulk,
            patch.object(
                service, "_detect_off_hours_mutations", new_callable=AsyncMock
            ) as mock_off_hours,
            patch.object(
                service, "_detect_rapid_version_churn", new_callable=AsyncMock
            ) as mock_churn,
        ):
            mock_backdated.return_value = [alert1]
            mock_bypasses.return_value = [alert2]
            mock_bulk.return_value = []
            mock_off_hours.return_value = []
            mock_churn.return_value = []

            result = await service.scan_for_anomalies(company_id=1)

            assert len(result) == 2
            assert alert1 in result
            assert alert2 in result

    @pytest.mark.asyncio
    async def test_continues_on_detector_failure(self, service):
        """scan_for_anomalies should continue if one detector raises."""
        alert = MagicMock(spec=AnomalyAlert)

        with (
            patch.object(
                service, "_detect_backdated_signatures", new_callable=AsyncMock
            ) as mock_backdated,
            patch.object(
                service, "_detect_workflow_bypasses", new_callable=AsyncMock
            ) as mock_bypasses,
            patch.object(
                service, "_detect_bulk_approvals", new_callable=AsyncMock
            ) as mock_bulk,
            patch.object(
                service, "_detect_off_hours_mutations", new_callable=AsyncMock
            ) as mock_off_hours,
            patch.object(
                service, "_detect_rapid_version_churn", new_callable=AsyncMock
            ) as mock_churn,
        ):
            mock_backdated.side_effect = RuntimeError("DB error")
            mock_bypasses.return_value = [alert]
            mock_bulk.return_value = []
            mock_off_hours.return_value = []
            mock_churn.return_value = []

            result = await service.scan_for_anomalies(company_id=1)

            assert len(result) == 1
            assert alert in result

    @pytest.mark.asyncio
    async def test_uses_custom_hours_parameter(self, service):
        """scan_for_anomalies should pass the hours parameter correctly."""
        with (
            patch.object(
                service, "_detect_backdated_signatures", new_callable=AsyncMock
            ) as mock_backdated,
            patch.object(
                service, "_detect_workflow_bypasses", new_callable=AsyncMock
            ) as mock_bypasses,
            patch.object(
                service, "_detect_bulk_approvals", new_callable=AsyncMock
            ) as mock_bulk,
            patch.object(
                service, "_detect_off_hours_mutations", new_callable=AsyncMock
            ) as mock_off_hours,
            patch.object(
                service, "_detect_rapid_version_churn", new_callable=AsyncMock
            ) as mock_churn,
        ):
            mock_backdated.return_value = []
            mock_bypasses.return_value = []
            mock_bulk.return_value = []
            mock_off_hours.return_value = []
            mock_churn.return_value = []

            await service.scan_for_anomalies(company_id=1, hours=48)

            # Verify the 'since' parameter is approximately 48 hours ago
            call_args = mock_backdated.call_args
            since_arg = call_args[0][1]  # second positional arg
            expected_since = datetime.now(timezone.utc) - timedelta(hours=48)
            # Allow 5 seconds tolerance
            assert abs((since_arg - expected_since).total_seconds()) < 5


# ---------------------------------------------------------------------------
# list_alerts Tests
# ---------------------------------------------------------------------------


class TestListAlerts:
    """Tests for the list_alerts method."""

    @pytest.mark.asyncio
    async def test_list_alerts_no_filters(self, service, mock_session):
        """list_alerts with no filters returns all alerts for company."""
        mock_alert = MagicMock(spec=AnomalyAlert)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_alert]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await service.list_alerts(company_id=1)

        assert len(result) == 1
        mock_session.expunge.assert_called_once_with(mock_alert)

    @pytest.mark.asyncio
    async def test_list_alerts_with_type_filter(self, service, mock_session):
        """list_alerts with anomaly_type filter."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.list_alerts(company_id=1, anomaly_type="bulk_approval")

        # Verify execute was called (filter applied in the query)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_alerts_with_all_filters(self, service, mock_session):
        """list_alerts with all filters applied."""
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        await service.list_alerts(
            company_id=1,
            anomaly_type="backdated_signature",
            severity="Critical",
            is_resolved=False,
        )

        mock_session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_alert Tests
# ---------------------------------------------------------------------------


class TestResolveAlert:
    """Tests for the resolve_alert method."""

    @pytest.mark.asyncio
    async def test_resolve_alert_success(self, service, mock_session):
        """resolve_alert should mark alert as resolved with note."""
        mock_alert = MagicMock(spec=AnomalyAlert)
        mock_alert.id = 1
        mock_alert.is_resolved = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_alert
        mock_session.execute.return_value = mock_result

        result = await service.resolve_alert(
            anomaly_id=1,
            resolution_note="Investigated and confirmed legitimate",
            company_id=1,
        )

        assert result is mock_alert
        assert mock_alert.is_resolved is True
        assert mock_alert.resolution_note == "Investigated and confirmed legitimate"
        assert mock_alert.resolved_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_alert_not_found(self, service, mock_session):
        """resolve_alert should raise ValueError if alert not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await service.resolve_alert(
                anomaly_id=999,
                resolution_note="Test",
                company_id=1,
            )


# ---------------------------------------------------------------------------
# _is_duplicate Tests
# ---------------------------------------------------------------------------


class TestIsDuplicate:
    """Tests for the _is_duplicate deduplication method."""

    @pytest.mark.asyncio
    async def test_no_duplicate_returns_false(self, service, mock_session):
        """_is_duplicate returns False when no matching alert exists."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await service._is_duplicate(
            mock_session, "backdated_signature", 1, 1
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_existing_duplicate_returns_true(self, service, mock_session):
        """_is_duplicate returns True when matching alert exists within 24h."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_session.execute.return_value = mock_result

        result = await service._is_duplicate(
            mock_session, "backdated_signature", 1, 1
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_handles_none_document_id(self, service, mock_session):
        """_is_duplicate handles None affected_document_id correctly."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await service._is_duplicate(
            mock_session, "bulk_approval", None, 1
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_none_user_id(self, service, mock_session):
        """_is_duplicate handles None affected_user_id correctly."""
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        mock_session.execute.return_value = mock_result

        result = await service._is_duplicate(
            mock_session, "workflow_bypass", 1, None
        )

        assert result is False


# ---------------------------------------------------------------------------
# Service Initialization Tests
# ---------------------------------------------------------------------------


class TestServiceInit:
    """Tests for service initialization."""

    def test_init_stores_session_factory(self, mock_session_factory):
        """Service stores the session factory."""
        service = AnomalyDetectionService(session_factory=mock_session_factory)
        assert service._session_factory is mock_session_factory
