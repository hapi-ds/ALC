"""Unit tests for ServiceRegistry service.

Tests the Docker service registry: get_all_services, get_service_stats,
restart_container, get_container_version, and Docker socket unavailability
graceful degradation.

Requirements: 12.1–12.5, 13.1–13.5
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from docker.errors import APIError, DockerException, NotFound

from alcoabase.services.service_registry import (
    CachedServiceData,
    ContainerStats,
    RestartResult,
    ServiceInfo,
    ServiceRegistry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ServiceRegistry:
    """Create a ServiceRegistry instance."""
    return ServiceRegistry()


@pytest.fixture
def mock_docker_client() -> MagicMock:
    """Create a mock Docker client."""
    client = MagicMock()
    client.ping = MagicMock(return_value=True)
    return client


@pytest.fixture
def running_container() -> MagicMock:
    """Create a mock running Docker container."""
    container = MagicMock()
    container.status = "running"
    container.attrs = {
        "State": {
            "Status": "running",
            "StartedAt": "2025-01-15T10:00:00.000000000Z",
        }
    }
    container.labels = {"org.opencontainers.image.version": "16.4"}
    container.image = MagicMock()
    container.image.tags = ["postgres:16.4-alpine"]
    return container


# ---------------------------------------------------------------------------
# Tests: get_all_services with mocked Docker SDK
# ---------------------------------------------------------------------------


class TestGetAllServices:
    """Tests for get_all_services with running, stopped, and missing containers."""

    @pytest.mark.asyncio
    async def test_running_containers_reported(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock, running_container: MagicMock
    ) -> None:
        """Running containers are reported with correct state and version."""
        mock_docker_client.containers.get = MagicMock(return_value=running_container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.get_all_services()

        assert result.is_stale is False
        assert len(result.services) == 8
        for svc in result.services:
            assert svc.running_state == "running"
            assert svc.version == "16.4"

    @pytest.mark.asyncio
    async def test_stopped_container_reported(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Stopped containers are reported with 'exited' state and 'stopped' uptime."""
        stopped_container = MagicMock()
        stopped_container.status = "exited"
        stopped_container.attrs = {
            "State": {
                "Status": "exited",
                "StartedAt": "2025-01-15T10:00:00.000000000Z",
            }
        }
        stopped_container.labels = {}
        stopped_container.image = MagicMock()
        stopped_container.image.tags = ["redis:7.2"]
        mock_docker_client.containers.get = MagicMock(return_value=stopped_container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.get_all_services()

        assert result.is_stale is False
        for svc in result.services:
            assert svc.running_state == "exited"
            assert svc.uptime == "stopped"

    @pytest.mark.asyncio
    async def test_missing_container_reported_as_not_found(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Missing containers are reported with 'not_found' state."""
        mock_docker_client.containers.get = MagicMock(
            side_effect=NotFound("Container not found")
        )

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.get_all_services()

        assert result.is_stale is False
        assert len(result.services) == 8
        for svc in result.services:
            assert svc.running_state == "not_found"
            assert svc.version == "unknown"
            assert svc.uptime == "N/A"

    @pytest.mark.asyncio
    async def test_api_error_container_reported_as_error(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Containers with API errors are reported with 'error' state."""
        mock_docker_client.containers.get = MagicMock(
            side_effect=APIError("Internal server error")
        )

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.get_all_services()

        assert result.is_stale is False
        for svc in result.services:
            assert svc.running_state == "error"
            assert svc.version == "unknown"

    @pytest.mark.asyncio
    async def test_mixed_container_states(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock, running_container: MagicMock
    ) -> None:
        """Mix of running, stopped, and missing containers handled correctly."""
        call_count = [0]

        def get_container(name):
            call_count[0] += 1
            if call_count[0] <= 3:
                return running_container
            elif call_count[0] <= 5:
                raise NotFound("Not found")
            else:
                stopped = MagicMock()
                stopped.attrs = {"State": {"Status": "exited", "StartedAt": ""}}
                stopped.labels = {}
                stopped.image = MagicMock()
                stopped.image.tags = []
                return stopped

        mock_docker_client.containers.get = MagicMock(side_effect=get_container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.get_all_services()

        running = [s for s in result.services if s.running_state == "running"]
        not_found = [s for s in result.services if s.running_state == "not_found"]
        exited = [s for s in result.services if s.running_state == "exited"]
        assert len(running) == 3
        assert len(not_found) == 2
        assert len(exited) == 3


# ---------------------------------------------------------------------------
# Tests: get_service_stats CPU/memory calculation from Docker stats JSON
# ---------------------------------------------------------------------------


class TestGetServiceStats:
    """Tests for get_service_stats CPU/memory calculation."""

    @pytest.mark.asyncio
    async def test_cpu_percent_calculation(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """CPU percent is calculated correctly from Docker stats JSON."""
        container = MagicMock()
        container.stats = MagicMock(return_value={
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200_000_000, "percpu_usage": [100_000_000, 100_000_000]},
                "system_cpu_usage": 1_000_000_000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100_000_000},
                "system_cpu_usage": 900_000_000,
            },
            "memory_stats": {
                "usage": 524_288_000,
                "limit": 1_073_741_824,
                "stats": {"cache": 0},
            },
        })
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            stats = await registry.get_service_stats("alcoabase-postgres")

        # cpu_delta = 100M, system_delta = 100M, online_cpus = 2
        # cpu_percent = (100M / 100M) * 2 * 100 = 200.0
        assert stats.cpu_percent == 200.0
        assert stats.memory_used_mb == pytest.approx(500.0, rel=0.01)
        assert stats.memory_limit_mb == pytest.approx(1024.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_memory_calculation_subtracts_cache(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Memory calculation subtracts cache from total usage."""
        container = MagicMock()
        container.stats = MagicMock(return_value={
            "cpu_stats": {
                "cpu_usage": {"total_usage": 0},
                "system_cpu_usage": 0,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 0},
                "system_cpu_usage": 0,
            },
            "memory_stats": {
                "usage": 200 * 1024 * 1024,  # 200 MB total
                "limit": 512 * 1024 * 1024,  # 512 MB limit
                "stats": {"cache": 50 * 1024 * 1024},  # 50 MB cache
            },
        })
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            stats = await registry.get_service_stats("alcoabase-redis")

        # Active memory = 200 - 50 = 150 MB
        assert stats.memory_used_mb == 150.0
        assert stats.memory_limit_mb == 512.0

    @pytest.mark.asyncio
    async def test_memory_limit_none_when_kernel_max(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Memory limit returns None when Docker reports kernel max (no limit)."""
        container = MagicMock()
        container.stats = MagicMock(return_value={
            "cpu_stats": {
                "cpu_usage": {"total_usage": 0},
                "system_cpu_usage": 0,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 0},
                "system_cpu_usage": 0,
            },
            "memory_stats": {
                "usage": 100 * 1024 * 1024,
                "limit": 9_223_372_036_854_771_712,  # Kernel max (~9 EB)
                "stats": {"cache": 0},
            },
        })
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            stats = await registry.get_service_stats("alcoabase-backend")

        assert stats.memory_limit_mb is None

    @pytest.mark.asyncio
    async def test_cpu_percent_zero_when_no_delta(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """CPU percent returns 0.0 when system_delta is zero."""
        container = MagicMock()
        container.stats = MagicMock(return_value={
            "cpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 500,  # Same as current → delta = 0
            },
            "memory_stats": {
                "usage": 0,
                "limit": 0,
                "stats": {"cache": 0},
            },
        })
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            stats = await registry.get_service_stats("alcoabase-redis")

        assert stats.cpu_percent == 0.0

    @pytest.mark.asyncio
    async def test_stats_with_empty_memory_stats(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Handles empty or missing memory_stats gracefully."""
        container = MagicMock()
        container.stats = MagicMock(return_value={
            "cpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 0},
            "precpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 0},
            "memory_stats": {},
        })
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            stats = await registry.get_service_stats("alcoabase-minio")

        assert stats.cpu_percent == 0.0
        assert stats.memory_used_mb == 0.0
        assert stats.memory_limit_mb is None


# ---------------------------------------------------------------------------
# Tests: restart_container success and timeout scenarios
# ---------------------------------------------------------------------------


class TestRestartContainer:
    """Tests for restart_container success and failure scenarios."""

    @pytest.mark.asyncio
    async def test_restart_success(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Successful restart returns success=True with duration."""
        container = MagicMock()
        container.restart = MagicMock()
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.restart_container("alcoabase-vllm", timeout=30)

        assert result.success is True
        assert result.container_name == "alcoabase-vllm"
        assert "successfully" in result.message
        assert result.duration_seconds >= 0.0
        container.restart.assert_called_once_with(timeout=30)

    @pytest.mark.asyncio
    async def test_restart_container_not_found(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Restart of non-existent container returns success=False."""
        mock_docker_client.containers.get = MagicMock(
            side_effect=NotFound("Container not found")
        )

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.restart_container("alcoabase-vllm")

        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_restart_api_error(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Restart with API error returns success=False with error message."""
        container = MagicMock()
        container.restart = MagicMock(
            side_effect=APIError("Container restart timed out")
        )
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.restart_container("alcoabase-vllm", timeout=180)

        assert result.success is False
        assert "Failed to restart" in result.message
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_restart_docker_exception(
        self, registry: ServiceRegistry
    ) -> None:
        """Restart when Docker socket unavailable returns success=False."""
        with patch.object(
            registry, "_get_client", side_effect=DockerException("Socket unavailable")
        ):
            result = await registry.restart_container("alcoabase-vllm")

        assert result.success is False
        assert "Docker error" in result.message


# ---------------------------------------------------------------------------
# Tests: get_container_version extraction from labels/tags
# ---------------------------------------------------------------------------


class TestGetContainerVersion:
    """Tests for get_container_version extraction from labels and image tags."""

    @pytest.mark.asyncio
    async def test_version_from_oci_label(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Version extracted from org.opencontainers.image.version label."""
        container = MagicMock()
        container.labels = {"org.opencontainers.image.version": "2.16.0"}
        container.image = MagicMock()
        container.image.tags = ["opensearch:2.16.0"]
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            version = await registry.get_container_version("alcoabase-opensearch")

        assert version == "2.16.0"

    @pytest.mark.asyncio
    async def test_version_from_version_label(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Version extracted from 'version' label when OCI label absent."""
        container = MagicMock()
        container.labels = {"version": "7.2.4"}
        container.image = MagicMock()
        container.image.tags = ["redis:7.2.4-alpine"]
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            version = await registry.get_container_version("alcoabase-redis")

        assert version == "7.2.4"

    @pytest.mark.asyncio
    async def test_version_from_image_tag_fallback(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Version extracted from image tag when no labels present."""
        container = MagicMock()
        container.labels = {}
        container.image = MagicMock()
        container.image.tags = ["postgres:16.4-alpine"]
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            version = await registry.get_container_version("alcoabase-postgres")

        assert version == "16.4-alpine"

    @pytest.mark.asyncio
    async def test_version_unknown_when_no_labels_or_tags(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Returns 'unknown' when no labels and no image tags available."""
        container = MagicMock()
        container.labels = {}
        container.image = MagicMock()
        container.image.tags = []
        mock_docker_client.containers.get = MagicMock(return_value=container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            version = await registry.get_container_version("alcoabase-backend")

        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_version_unknown_when_container_not_found(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock
    ) -> None:
        """Returns 'unknown' when container does not exist."""
        mock_docker_client.containers.get = MagicMock(
            side_effect=NotFound("Not found")
        )

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            version = await registry.get_container_version("alcoabase-vllm")

        assert version == "unknown"

    @pytest.mark.asyncio
    async def test_version_unknown_when_docker_unavailable(
        self, registry: ServiceRegistry
    ) -> None:
        """Returns 'unknown' when Docker socket is unavailable."""
        with patch.object(
            registry, "_get_client", side_effect=DockerException("Socket error")
        ):
            version = await registry.get_container_version("alcoabase-postgres")

        assert version == "unknown"


# ---------------------------------------------------------------------------
# Tests: Docker socket unavailable graceful degradation
# ---------------------------------------------------------------------------


class TestDockerSocketUnavailable:
    """Tests for graceful degradation when Docker socket is unavailable."""

    @pytest.mark.asyncio
    async def test_get_all_services_returns_cached_data_when_docker_down(
        self, registry: ServiceRegistry
    ) -> None:
        """get_all_services returns stale cached data when Docker is unavailable."""
        # Pre-populate cache with some data
        cached_services = [
            ServiceInfo(
                container_name="alcoabase-postgres",
                service_name="postgresql",
                running_state="running",
                version="16.4",
                uptime="2d 5h",
            )
        ]
        registry._cache = CachedServiceData(
            services=cached_services,
            cached_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            is_stale=False,
        )

        with patch.object(
            registry, "_get_client", side_effect=DockerException("Socket unavailable")
        ):
            result = await registry.get_all_services()

        assert result.is_stale is True
        assert len(result.services) == 1
        assert result.services[0].service_name == "postgresql"
        assert result.services[0].running_state == "running"

    @pytest.mark.asyncio
    async def test_get_all_services_returns_empty_cache_on_first_failure(
        self, registry: ServiceRegistry
    ) -> None:
        """get_all_services returns empty stale cache if Docker never connected."""
        with patch.object(
            registry, "_get_client", side_effect=DockerException("Socket unavailable")
        ):
            result = await registry.get_all_services()

        assert result.is_stale is True
        assert result.services == []

    @pytest.mark.asyncio
    async def test_cache_updated_on_successful_call(
        self, registry: ServiceRegistry, mock_docker_client: MagicMock, running_container: MagicMock
    ) -> None:
        """Cache is updated with fresh data on successful Docker call."""
        mock_docker_client.containers.get = MagicMock(return_value=running_container)

        with patch.object(registry, "_get_client", return_value=mock_docker_client):
            result = await registry.get_all_services()

        assert result.is_stale is False
        assert len(result.services) == 8
        # Verify cache was updated
        assert registry._cache.is_stale is False
        assert len(registry._cache.services) == 8


# ---------------------------------------------------------------------------
# Tests: Static helper methods
# ---------------------------------------------------------------------------


class TestStaticHelpers:
    """Tests for static calculation helper methods."""

    def test_calculate_cpu_percent_normal(self) -> None:
        """CPU percent calculated correctly with valid stats."""
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 500_000_000},
                "system_cpu_usage": 2_000_000_000,
                "online_cpus": 4,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 400_000_000},
                "system_cpu_usage": 1_000_000_000,
            },
        }
        # cpu_delta = 100M, system_delta = 1000M, cpus = 4
        # (100M / 1000M) * 4 * 100 = 40.0
        result = ServiceRegistry._calculate_cpu_percent(stats)
        assert result == 40.0

    def test_calculate_cpu_percent_empty_stats(self) -> None:
        """CPU percent returns 0.0 for empty stats."""
        assert ServiceRegistry._calculate_cpu_percent({}) == 0.0

    def test_calculate_cpu_percent_negative_delta(self) -> None:
        """CPU percent returns 0.0 when cpu_delta is negative."""
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 50},
                "system_cpu_usage": 200,
                "online_cpus": 1,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100},
                "system_cpu_usage": 100,
            },
        }
        result = ServiceRegistry._calculate_cpu_percent(stats)
        assert result == 0.0

    def test_calculate_memory_used_mb_with_cache(self) -> None:
        """Memory used subtracts cache from total usage."""
        stats = {
            "memory_stats": {
                "usage": 300 * 1024 * 1024,
                "stats": {"cache": 100 * 1024 * 1024},
            }
        }
        result = ServiceRegistry._calculate_memory_used_mb(stats)
        assert result == 200.0

    def test_calculate_memory_used_mb_no_cache(self) -> None:
        """Memory used returns full usage when no cache stats."""
        stats = {
            "memory_stats": {
                "usage": 256 * 1024 * 1024,
                "stats": {},
            }
        }
        result = ServiceRegistry._calculate_memory_used_mb(stats)
        assert result == 256.0

    def test_calculate_memory_used_mb_empty(self) -> None:
        """Memory used returns 0.0 for empty stats."""
        assert ServiceRegistry._calculate_memory_used_mb({}) == 0.0

    def test_calculate_memory_limit_mb_normal(self) -> None:
        """Memory limit calculated correctly."""
        stats = {"memory_stats": {"limit": 1024 * 1024 * 1024}}  # 1 GB
        result = ServiceRegistry._calculate_memory_limit_mb(stats)
        assert result == 1024.0

    def test_calculate_memory_limit_mb_no_limit(self) -> None:
        """Memory limit returns None when kernel max reported."""
        stats = {"memory_stats": {"limit": 9_223_372_036_854_771_712}}
        result = ServiceRegistry._calculate_memory_limit_mb(stats)
        assert result is None

    def test_calculate_memory_limit_mb_zero(self) -> None:
        """Memory limit returns None when limit is zero."""
        stats = {"memory_stats": {"limit": 0}}
        result = ServiceRegistry._calculate_memory_limit_mb(stats)
        assert result is None

    def test_is_memory_warning_above_threshold(self) -> None:
        """Warning flag set when usage exceeds 90% of limit."""
        assert ServiceRegistry.is_memory_warning(920.0, 1000.0) is True

    def test_is_memory_warning_below_threshold(self) -> None:
        """Warning flag not set when usage is below 90% of limit."""
        assert ServiceRegistry.is_memory_warning(800.0, 1000.0) is False

    def test_is_memory_warning_at_exactly_90_percent(self) -> None:
        """Warning flag not set at exactly 90% (must exceed)."""
        assert ServiceRegistry.is_memory_warning(900.0, 1000.0) is False

    def test_is_memory_warning_no_limit(self) -> None:
        """Warning flag not set when no memory limit."""
        assert ServiceRegistry.is_memory_warning(500.0, None) is False

    def test_is_memory_warning_zero_limit(self) -> None:
        """Warning flag not set when memory limit is zero."""
        assert ServiceRegistry.is_memory_warning(500.0, 0.0) is False


# ---------------------------------------------------------------------------
# Tests: _format_uptime
# ---------------------------------------------------------------------------


class TestFormatUptime:
    """Tests for _format_uptime helper."""

    def test_format_uptime_days_hours_minutes(self, registry: ServiceRegistry) -> None:
        """Formats uptime with days, hours, and minutes."""
        # Use a timestamp far enough in the past
        from datetime import timedelta
        past = datetime.now(timezone.utc) - timedelta(days=2, hours=5, minutes=30)
        started_at = past.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        result = registry._format_uptime(started_at)
        assert "2d" in result
        assert "5h" in result
        assert "30m" in result

    def test_format_uptime_invalid_timestamp(self, registry: ServiceRegistry) -> None:
        """Returns 'unknown' for invalid timestamp."""
        result = registry._format_uptime("not-a-timestamp")
        assert result == "unknown"

    def test_format_uptime_empty_string(self, registry: ServiceRegistry) -> None:
        """Returns 'unknown' for empty string."""
        result = registry._format_uptime("")
        assert result == "unknown"
