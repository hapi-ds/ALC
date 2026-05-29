"""Unit tests for HealthMonitor service.

Tests the core health monitoring methods: check_service, classify_status,
check_all_services, bounded buffer eviction, transition detection,
get_uptime_percentage, and get_current_status aggregation.

Requirements: 10.1–10.9, 11.1–11.6
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.system_config import HealthCheckResult
from alcoabase.services.health_monitor import (
    DEFAULT_DEGRADED_THRESHOLD_MS,
    DEFAULT_TIMEOUT_MS,
    MAX_RESULTS_PER_SERVICE,
    HealthMonitor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def monitor() -> HealthMonitor:
    """Create a HealthMonitor with default thresholds."""
    return HealthMonitor()


@pytest.fixture
def custom_monitor() -> HealthMonitor:
    """Create a HealthMonitor with custom thresholds for testing."""
    return HealthMonitor(degraded_threshold_ms=100.0, timeout_ms=500.0)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests: classify_status pure function with boundary values
# ---------------------------------------------------------------------------


class TestClassifyStatus:
    """Tests for classify_status pure function."""

    def test_healthy_below_degraded_threshold(self, monitor: HealthMonitor) -> None:
        """Response time below degraded threshold returns 'healthy'."""
        result = monitor.classify_status(100.0, 5000.0, 10000.0)
        assert result == "healthy"

    def test_healthy_at_zero_response_time(self, monitor: HealthMonitor) -> None:
        """Zero response time returns 'healthy'."""
        result = monitor.classify_status(0.0, 5000.0, 10000.0)
        assert result == "healthy"

    def test_degraded_at_exact_threshold(self, monitor: HealthMonitor) -> None:
        """Response time exactly at degraded threshold returns 'degraded'."""
        result = monitor.classify_status(5000.0, 5000.0, 10000.0)
        assert result == "degraded"

    def test_degraded_between_thresholds(self, monitor: HealthMonitor) -> None:
        """Response time between degraded and timeout returns 'degraded'."""
        result = monitor.classify_status(7500.0, 5000.0, 10000.0)
        assert result == "degraded"

    def test_unreachable_at_exact_timeout(self, monitor: HealthMonitor) -> None:
        """Response time exactly at timeout returns 'unreachable'."""
        result = monitor.classify_status(10000.0, 5000.0, 10000.0)
        assert result == "unreachable"

    def test_unreachable_above_timeout(self, monitor: HealthMonitor) -> None:
        """Response time above timeout returns 'unreachable'."""
        result = monitor.classify_status(15000.0, 5000.0, 10000.0)
        assert result == "unreachable"

    def test_boundary_just_below_degraded(self, monitor: HealthMonitor) -> None:
        """Response time just below degraded threshold returns 'healthy'."""
        result = monitor.classify_status(4999.99, 5000.0, 10000.0)
        assert result == "healthy"

    def test_boundary_just_below_timeout(self, monitor: HealthMonitor) -> None:
        """Response time just below timeout returns 'degraded'."""
        result = monitor.classify_status(9999.99, 5000.0, 10000.0)
        assert result == "degraded"

    def test_custom_thresholds(self) -> None:
        """Works with custom threshold values."""
        result = HealthMonitor.classify_status(50.0, 100.0, 500.0)
        assert result == "healthy"

        result = HealthMonitor.classify_status(200.0, 100.0, 500.0)
        assert result == "degraded"

        result = HealthMonitor.classify_status(600.0, 100.0, 500.0)
        assert result == "unreachable"


# ---------------------------------------------------------------------------
# Tests: check_service for each service type with mocked connections
# ---------------------------------------------------------------------------


class TestCheckService:
    """Tests for check_service with mocked connections."""

    @pytest.mark.asyncio
    async def test_postgresql_healthy(self, custom_monitor: HealthMonitor) -> None:
        """PostgreSQL check returns healthy when connection succeeds quickly."""
        with patch.object(
            custom_monitor, "_check_postgresql", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = None  # Succeeds instantly
            result = await custom_monitor.check_service("postgresql")

        assert result["status"] == "healthy"
        assert result["response_time_ms"] is not None
        assert "error_message" not in result

    @pytest.mark.asyncio
    async def test_minio_healthy(self, custom_monitor: HealthMonitor) -> None:
        """MinIO check returns healthy when list_buckets succeeds."""
        with patch.object(
            custom_monitor, "_check_minio", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = None
            result = await custom_monitor.check_service("minio")

        assert result["status"] == "healthy"
        assert result["response_time_ms"] is not None

    @pytest.mark.asyncio
    async def test_opensearch_healthy(self, custom_monitor: HealthMonitor) -> None:
        """OpenSearch check returns healthy when cluster health succeeds."""
        with patch.object(
            custom_monitor, "_check_opensearch", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = None
            result = await custom_monitor.check_service("opensearch")

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_redis_healthy(self, custom_monitor: HealthMonitor) -> None:
        """Redis check returns healthy when PING succeeds."""
        with patch.object(
            custom_monitor, "_check_redis", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = None
            result = await custom_monitor.check_service("redis")

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_vllm_healthy(self, custom_monitor: HealthMonitor) -> None:
        """vLLM check returns healthy when /health endpoint responds."""
        with patch.object(
            custom_monitor, "_check_vllm", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = None
            result = await custom_monitor.check_service("vllm")

        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_service_degraded_slow_response(
        self, custom_monitor: HealthMonitor
    ) -> None:
        """Service returns degraded when response is slow but within timeout."""

        async def slow_check():
            await asyncio.sleep(0.15)  # 150ms > 100ms degraded threshold

        with patch.object(custom_monitor, "_check_postgresql", new=slow_check):
            result = await custom_monitor.check_service("postgresql")

        assert result["status"] == "degraded"
        assert result["response_time_ms"] >= 100.0

    @pytest.mark.asyncio
    async def test_service_unreachable_on_connection_error(
        self, custom_monitor: HealthMonitor
    ) -> None:
        """Service returns unreachable when connection raises an exception."""
        with patch.object(
            custom_monitor, "_check_postgresql", new_callable=AsyncMock
        ) as mock_check:
            mock_check.side_effect = ConnectionRefusedError("Connection refused")
            result = await custom_monitor.check_service("postgresql")

        assert result["status"] == "unreachable"
        assert result["error_message"] == "Connection refused"
        assert result["response_time_ms"] is not None

    @pytest.mark.asyncio
    async def test_service_unreachable_on_timeout(
        self, custom_monitor: HealthMonitor
    ) -> None:
        """Service returns unreachable when response exceeds timeout."""

        async def very_slow_check():
            await asyncio.sleep(0.6)  # 600ms > 500ms timeout

        with patch.object(custom_monitor, "_check_redis", new=very_slow_check):
            result = await custom_monitor.check_service("redis")

        assert result["status"] == "unreachable"
        assert result["response_time_ms"] >= 500.0

    @pytest.mark.asyncio
    async def test_unknown_service_raises_value_error(
        self, monitor: HealthMonitor
    ) -> None:
        """Unknown service name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown service"):
            await monitor.check_service("unknown_service")


# ---------------------------------------------------------------------------
# Tests: check_all_services concurrent execution within 10s
# ---------------------------------------------------------------------------


class TestCheckAllServices:
    """Tests for check_all_services concurrent execution."""

    @pytest.mark.asyncio
    async def test_checks_all_services_concurrently(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """All 5 services are checked and results stored."""
        # Mock check_service to return healthy for all
        async def mock_check(service_name):
            return {"status": "healthy", "response_time_ms": 10.0}

        # Mock _detect_transition to do nothing
        # Mock _evict_oldest to do nothing
        with patch.object(monitor, "_check_and_build_result", side_effect=mock_check):
            with patch.object(
                monitor, "_detect_transition", new_callable=AsyncMock
            ):
                with patch.object(
                    monitor, "_evict_oldest", new_callable=AsyncMock
                ):
                    results = await monitor.check_all_services(mock_session)

        assert len(results) == 5
        assert mock_session.add.call_count == 5
        for result in results:
            assert result.status == "healthy"

    @pytest.mark.asyncio
    async def test_handles_individual_check_exception(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Individual check exceptions result in unreachable status."""
        call_count = 0

        async def mock_check(service_name):
            nonlocal call_count
            call_count += 1
            if service_name == "vllm":
                raise ConnectionError("vLLM down")
            return {"status": "healthy", "response_time_ms": 5.0}

        with patch.object(monitor, "_check_and_build_result", side_effect=mock_check):
            with patch.object(
                monitor, "_detect_transition", new_callable=AsyncMock
            ):
                with patch.object(
                    monitor, "_evict_oldest", new_callable=AsyncMock
                ):
                    results = await monitor.check_all_services(mock_session)

        assert len(results) == 5
        vllm_result = next(r for r in results if r.service_name == "vllm")
        assert vllm_result.status == "unreachable"

    @pytest.mark.asyncio
    async def test_total_timeout_marks_all_unreachable(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """When the 10s total timeout is exceeded, all services are unreachable."""
        import alcoabase.services.health_monitor as hm_module

        original_wait_for = asyncio.wait_for

        async def raising_wait_for(*args, **kwargs):
            raise asyncio.TimeoutError()

        # Monkeypatch asyncio.wait_for to simulate total timeout
        hm_module.asyncio.wait_for = raising_wait_for
        try:
            with patch.object(
                monitor, "_detect_transition", new_callable=AsyncMock
            ):
                with patch.object(
                    monitor, "_evict_oldest", new_callable=AsyncMock
                ):
                    results = await monitor.check_all_services(mock_session)
        finally:
            hm_module.asyncio.wait_for = original_wait_for

        # All services should be marked unreachable on total timeout
        assert len(results) == 5
        for result in results:
            assert result.status == "unreachable"


# ---------------------------------------------------------------------------
# Tests: Bounded buffer eviction logic
# ---------------------------------------------------------------------------


class TestBoundedBufferEviction:
    """Tests for bounded buffer eviction logic."""

    @pytest.mark.asyncio
    async def test_no_eviction_when_under_limit(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """No eviction occurs when count is at or below MAX_RESULTS_PER_SERVICE."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 99  # Under limit
        mock_session.execute = AsyncMock(return_value=count_result)

        await monitor._evict_oldest("postgresql", mock_session)

        # Only the count query should have been executed
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_eviction_when_over_limit(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Oldest entries are evicted when count exceeds MAX_RESULTS_PER_SERVICE."""
        # First call: count query returns over limit
        count_result = MagicMock()
        count_result.scalar_one.return_value = 105

        # Second call: keep query returns IDs to keep
        keep_result = MagicMock()
        keep_result.all.return_value = [(i,) for i in range(1, 101)]

        # Third call: delete statement
        delete_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[count_result, keep_result, delete_result]
        )

        await monitor._evict_oldest("postgresql", mock_session)

        # Count + keep + delete = 3 execute calls
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_eviction_at_exact_limit(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """No eviction when count is exactly MAX_RESULTS_PER_SERVICE."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = MAX_RESULTS_PER_SERVICE
        mock_session.execute = AsyncMock(return_value=count_result)

        await monitor._evict_oldest("postgresql", mock_session)

        # Only the count query
        assert mock_session.execute.call_count == 1


# ---------------------------------------------------------------------------
# Tests: Transition detection
# ---------------------------------------------------------------------------


class TestTransitionDetection:
    """Tests for health status transition detection."""

    @pytest.mark.asyncio
    async def test_healthy_to_degraded_is_transition(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Transition from healthy to degraded sets is_transition=True."""
        previous = MagicMock(spec=HealthCheckResult)
        previous.status = "healthy"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        current = HealthCheckResult(
            service_name="postgresql",
            status="degraded",
            response_time_ms=6000.0,
            checked_at=datetime.now(timezone.utc),
        )

        await monitor._detect_transition(current, mock_session)

        assert current.is_transition is True
        assert current.previous_status == "healthy"

    @pytest.mark.asyncio
    async def test_healthy_to_unreachable_is_transition(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Transition from healthy to unreachable sets is_transition=True."""
        previous = MagicMock(spec=HealthCheckResult)
        previous.status = "healthy"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        current = HealthCheckResult(
            service_name="redis",
            status="unreachable",
            response_time_ms=None,
            error_message="Connection refused",
            checked_at=datetime.now(timezone.utc),
        )

        await monitor._detect_transition(current, mock_session)

        assert current.is_transition is True
        assert current.previous_status == "healthy"

    @pytest.mark.asyncio
    async def test_degraded_to_healthy_no_transition(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Transition from degraded to healthy does NOT set is_transition=True."""
        previous = MagicMock(spec=HealthCheckResult)
        previous.status = "degraded"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        current = HealthCheckResult(
            service_name="postgresql",
            status="healthy",
            response_time_ms=50.0,
            checked_at=datetime.now(timezone.utc),
        )

        await monitor._detect_transition(current, mock_session)

        assert current.is_transition is False
        assert current.previous_status == "degraded"

    @pytest.mark.asyncio
    async def test_degraded_to_unreachable_no_transition(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Transition from degraded to unreachable does NOT set is_transition."""
        previous = MagicMock(spec=HealthCheckResult)
        previous.status = "degraded"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        current = HealthCheckResult(
            service_name="minio",
            status="unreachable",
            response_time_ms=None,
            error_message="Timeout",
            checked_at=datetime.now(timezone.utc),
        )

        await monitor._detect_transition(current, mock_session)

        assert current.is_transition is False
        assert current.previous_status == "degraded"

    @pytest.mark.asyncio
    async def test_same_status_no_transition(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Same status as previous does NOT set is_transition."""
        previous = MagicMock(spec=HealthCheckResult)
        previous.status = "healthy"

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = previous
        mock_session.execute = AsyncMock(return_value=result_mock)

        current = HealthCheckResult(
            service_name="redis",
            status="healthy",
            response_time_ms=10.0,
            checked_at=datetime.now(timezone.utc),
        )

        await monitor._detect_transition(current, mock_session)

        assert current.is_transition is False
        assert current.previous_status == "healthy"

    @pytest.mark.asyncio
    async def test_no_previous_result_no_transition(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """First check for a service (no previous) does NOT set is_transition."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        current = HealthCheckResult(
            service_name="vllm",
            status="healthy",
            response_time_ms=20.0,
            checked_at=datetime.now(timezone.utc),
        )

        await monitor._detect_transition(current, mock_session)

        assert current.is_transition is False
        assert current.previous_status is None


# ---------------------------------------------------------------------------
# Tests: get_uptime_percentage calculation
# ---------------------------------------------------------------------------


class TestGetUptimePercentage:
    """Tests for get_uptime_percentage calculation."""

    @pytest.mark.asyncio
    async def test_all_healthy_returns_100(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """All healthy checks in period returns 100.0%."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 10

        healthy_result = MagicMock()
        healthy_result.scalar_one.return_value = 10

        mock_session.execute = AsyncMock(
            side_effect=[total_result, healthy_result]
        )

        pct = await monitor.get_uptime_percentage("postgresql", 24, mock_session)
        assert pct == 100.0

    @pytest.mark.asyncio
    async def test_no_checks_returns_zero(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """No checks in period returns 0.0%."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0

        mock_session.execute = AsyncMock(return_value=total_result)

        pct = await monitor.get_uptime_percentage("postgresql", 24, mock_session)
        assert pct == 0.0

    @pytest.mark.asyncio
    async def test_partial_uptime_calculation(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Mixed healthy/unhealthy checks returns correct percentage."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 20

        healthy_result = MagicMock()
        healthy_result.scalar_one.return_value = 15

        mock_session.execute = AsyncMock(
            side_effect=[total_result, healthy_result]
        )

        pct = await monitor.get_uptime_percentage("redis", 24, mock_session)
        assert pct == 75.0

    @pytest.mark.asyncio
    async def test_uptime_percentage_rounded_to_two_decimals(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Uptime percentage is rounded to 2 decimal places."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 3

        healthy_result = MagicMock()
        healthy_result.scalar_one.return_value = 1

        mock_session.execute = AsyncMock(
            side_effect=[total_result, healthy_result]
        )

        pct = await monitor.get_uptime_percentage("minio", 24, mock_session)
        assert pct == 33.33  # 1/3 * 100 rounded to 2 decimals


# ---------------------------------------------------------------------------
# Tests: get_current_status aggregation with avg_response_time_5min
# ---------------------------------------------------------------------------


class TestGetCurrentStatus:
    """Tests for get_current_status aggregation."""

    @pytest.mark.asyncio
    async def test_returns_status_for_all_services(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Returns status entries for all monitored services."""
        # Mock latest result for each service
        latest = MagicMock(spec=HealthCheckResult)
        latest.status = "healthy"
        latest.response_time_ms = 25.0
        latest.checked_at = datetime.now(timezone.utc)

        latest_result = MagicMock()
        latest_result.scalar_one_or_none.return_value = latest

        mock_session.execute = AsyncMock(return_value=latest_result)

        with patch.object(
            monitor, "get_uptime_percentage", new_callable=AsyncMock
        ) as mock_uptime:
            mock_uptime.return_value = 99.5
            with patch.object(
                monitor, "_get_avg_response_time", new_callable=AsyncMock
            ) as mock_avg:
                mock_avg.return_value = 30.5
                statuses = await monitor.get_current_status(mock_session)

        assert len(statuses) == 5
        for status in statuses:
            assert status["status"] == "healthy"
            assert status["uptime_pct_24h"] == 99.5
            assert status["avg_response_time_5min"] == 30.5

    @pytest.mark.asyncio
    async def test_no_results_returns_unreachable_defaults(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Service with no check results returns unreachable with defaults."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        statuses = await monitor.get_current_status(mock_session)

        assert len(statuses) == 5
        for status in statuses:
            assert status["status"] == "unreachable"
            assert status["response_time_ms"] is None
            assert status["last_checked"] is None
            assert status["uptime_pct_24h"] == 0.0
            assert status["avg_response_time_5min"] is None

    @pytest.mark.asyncio
    async def test_avg_response_time_none_when_no_data(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """avg_response_time_5min is None when no recent data exists."""
        latest = MagicMock(spec=HealthCheckResult)
        latest.status = "degraded"
        latest.response_time_ms = 6000.0
        latest.checked_at = datetime.now(timezone.utc)

        latest_result = MagicMock()
        latest_result.scalar_one_or_none.return_value = latest
        mock_session.execute = AsyncMock(return_value=latest_result)

        with patch.object(
            monitor, "get_uptime_percentage", new_callable=AsyncMock
        ) as mock_uptime:
            mock_uptime.return_value = 80.0
            with patch.object(
                monitor, "_get_avg_response_time", new_callable=AsyncMock
            ) as mock_avg:
                mock_avg.return_value = None
                statuses = await monitor.get_current_status(mock_session)

        for status in statuses:
            assert status["avg_response_time_5min"] is None


# ---------------------------------------------------------------------------
# Tests: _get_avg_response_time
# ---------------------------------------------------------------------------


class TestGetAvgResponseTime:
    """Tests for _get_avg_response_time helper."""

    @pytest.mark.asyncio
    async def test_returns_average_when_data_exists(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Returns rounded average when data points exist."""
        avg_result = MagicMock()
        avg_result.scalar_one.return_value = 45.678
        mock_session.execute = AsyncMock(return_value=avg_result)

        avg = await monitor._get_avg_response_time("postgresql", 5, mock_session)
        assert avg == 45.68

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(
        self, monitor: HealthMonitor, mock_session: AsyncMock
    ) -> None:
        """Returns None when no response time data exists."""
        avg_result = MagicMock()
        avg_result.scalar_one.return_value = None
        mock_session.execute = AsyncMock(return_value=avg_result)

        avg = await monitor._get_avg_response_time("postgresql", 5, mock_session)
        assert avg is None
