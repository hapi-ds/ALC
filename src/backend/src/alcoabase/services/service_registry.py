"""Service registry for tracking Docker Compose services.

Provides container status, resource utilization metrics, version
information, and restart capabilities via the Docker SDK.

References:
    - Design doc: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 12.1–12.5, 13.1–13.5
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import docker
from docker.errors import APIError, DockerException, NotFound

logger = logging.getLogger(__name__)

# Mapping of logical service names to Docker container names
DOCKER_SERVICES: dict[str, str] = {
    "postgresql": "alcoabase-postgres",
    "minio": "alcoabase-minio",
    "opensearch": "alcoabase-opensearch",
    "redis": "alcoabase-redis",
    "vllm": "alcoabase-vllm",
    "backend": "alcoabase-backend",
    "celery-worker": "alcoabase-celery-worker",
    "frontend": "alcoabase-frontend",
}


@dataclass
class ServiceInfo:
    """Information about a running Docker service.

    Attributes:
        container_name: Docker container name.
        service_name: Logical service name (e.g., "postgresql").
        running_state: Current container state (e.g., "running", "exited").
        version: Software version extracted from labels or image tag.
        uptime: Human-readable uptime string.
    """

    container_name: str
    service_name: str
    running_state: str
    version: str
    uptime: str


@dataclass
class ContainerStats:
    """Resource utilization stats for a container.

    Attributes:
        cpu_percent: CPU usage percentage.
        memory_used_mb: Memory usage in megabytes.
        memory_limit_mb: Container memory limit in megabytes (None if unlimited).
    """

    cpu_percent: float
    memory_used_mb: float
    memory_limit_mb: float | None = None


@dataclass
class ResourceMetrics:
    """Resource utilization metrics for a service.

    Attributes:
        service_name: Logical service name.
        container_name: Docker container name.
        cpu_percent: CPU usage percentage.
        memory_used_mb: Memory usage in megabytes.
        memory_limit_mb: Container memory limit in megabytes (None if unlimited).
        recorded_at: Timestamp when the metric was recorded.
    """

    service_name: str
    container_name: str
    cpu_percent: float
    memory_used_mb: float
    memory_limit_mb: float | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RestartResult:
    """Result of a container restart operation.

    Attributes:
        success: Whether the restart completed successfully.
        container_name: Name of the restarted container.
        message: Descriptive message about the operation.
        duration_seconds: Time taken for the restart in seconds.
    """

    success: bool
    container_name: str
    message: str
    duration_seconds: float = 0.0


@dataclass
class CachedServiceData:
    """Cached service data with staleness tracking.

    Attributes:
        services: List of cached ServiceInfo objects.
        cached_at: Timestamp when the data was cached.
        is_stale: Whether the data is stale (Docker unavailable).
    """

    services: list[ServiceInfo] = field(default_factory=list)
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_stale: bool = False


class ServiceRegistry:
    """Registry for tracking Docker Compose services, versions, and resources.

    Uses the Docker SDK to communicate with the Docker daemon via the
    Unix socket. Handles Docker socket unavailability gracefully by
    returning cached data with a staleness indicator.

    Attributes:
        DOCKER_SERVICES: Mapping of logical service names to container names.
    """

    DOCKER_SERVICES = DOCKER_SERVICES

    def __init__(self) -> None:
        """Initialize the service registry with Docker client and cache."""
        self._client: docker.DockerClient | None = None
        self._cache = CachedServiceData()

    def _get_client(self) -> docker.DockerClient:
        """Get or create a Docker client connection.

        Returns:
            An active Docker client.

        Raises:
            DockerException: If the Docker socket is unavailable.
        """
        if self._client is None:
            self._client = docker.DockerClient(
                base_url="unix:///var/run/docker.sock",
                timeout=10,
            )
        # Verify connectivity
        self._client.ping()
        return self._client

    def _format_uptime(self, started_at: str) -> str:
        """Convert a container start timestamp to a human-readable uptime string.

        Args:
            started_at: ISO 8601 timestamp string from Docker.

        Returns:
            Human-readable uptime (e.g., "2d 5h 30m", "45m", "3h 12m").
        """
        try:
            # Docker returns timestamps like "2024-01-15T10:30:00.123456789Z"
            start_str = started_at.replace("Z", "+00:00")
            # Handle nanosecond precision by truncating to microseconds
            if "." in start_str:
                parts = start_str.split(".")
                frac_and_tz = parts[1]
                # Find where the timezone starts (+ or - after the dot)
                tz_idx = -1
                for i, ch in enumerate(frac_and_tz):
                    if ch in ("+", "-") and i > 0:
                        tz_idx = i
                        break
                if tz_idx > 0:
                    frac = frac_and_tz[:tz_idx][:6]  # Truncate to 6 digits
                    tz = frac_and_tz[tz_idx:]
                    start_str = f"{parts[0]}.{frac}{tz}"
                else:
                    frac = frac_and_tz[:6]
                    start_str = f"{parts[0]}.{frac}+00:00"

            start_time = datetime.fromisoformat(start_str)
            now = datetime.now(timezone.utc)
            delta = now - start_time

            total_seconds = int(delta.total_seconds())
            if total_seconds < 0:
                return "0m"

            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60

            parts_list: list[str] = []
            if days > 0:
                parts_list.append(f"{days}d")
            if hours > 0:
                parts_list.append(f"{hours}h")
            if minutes > 0 or not parts_list:
                parts_list.append(f"{minutes}m")

            return " ".join(parts_list)
        except (ValueError, TypeError):
            return "unknown"

    async def get_all_services(self) -> CachedServiceData:
        """List all Docker services matching DOCKER_SERVICES.

        Returns ServiceInfo for each service with container_name,
        running_state, version, and uptime. If Docker is unavailable,
        returns cached data with staleness indicator.

        Returns:
            CachedServiceData containing service information and staleness status.
        """
        try:
            client = self._get_client()
            services: list[ServiceInfo] = []

            for service_name, container_name in self.DOCKER_SERVICES.items():
                try:
                    container = client.containers.get(container_name)
                    attrs = container.attrs or {}
                    state = attrs.get("State", {})
                    running_state = state.get("Status", "unknown")
                    started_at = state.get("StartedAt", "")

                    version = self._extract_version(container)
                    uptime = self._format_uptime(started_at) if running_state == "running" else "stopped"

                    services.append(
                        ServiceInfo(
                            container_name=container_name,
                            service_name=service_name,
                            running_state=running_state,
                            version=version,
                            uptime=uptime,
                        )
                    )
                except NotFound:
                    services.append(
                        ServiceInfo(
                            container_name=container_name,
                            service_name=service_name,
                            running_state="not_found",
                            version="unknown",
                            uptime="N/A",
                        )
                    )
                except APIError as e:
                    logger.warning(
                        "Failed to get container info for %s: %s",
                        container_name,
                        str(e),
                    )
                    services.append(
                        ServiceInfo(
                            container_name=container_name,
                            service_name=service_name,
                            running_state="error",
                            version="unknown",
                            uptime="N/A",
                        )
                    )

            # Update cache with fresh data
            self._cache = CachedServiceData(
                services=services,
                cached_at=datetime.now(timezone.utc),
                is_stale=False,
            )
            return self._cache

        except DockerException as e:
            logger.error("Docker socket unavailable: %s", str(e))
            # Return cached data with staleness indicator
            self._cache.is_stale = True
            return self._cache

    async def get_service_stats(self, container_name: str) -> ContainerStats:
        """Get resource utilization stats for a specific container.

        Uses Docker's stats API in non-streaming mode to get a point-in-time
        snapshot of CPU and memory usage.

        Args:
            container_name: The Docker container name to query.

        Returns:
            ContainerStats with cpu_percent, memory_used_mb, memory_limit_mb.

        Raises:
            DockerException: If Docker socket is unavailable.
            NotFound: If the container does not exist.
        """
        client = self._get_client()
        container = client.containers.get(container_name)
        stats = container.stats(stream=False)

        cpu_percent = self._calculate_cpu_percent(stats)
        memory_used_mb = self._calculate_memory_used_mb(stats)
        memory_limit_mb = self._calculate_memory_limit_mb(stats)

        return ContainerStats(
            cpu_percent=cpu_percent,
            memory_used_mb=memory_used_mb,
            memory_limit_mb=memory_limit_mb,
        )

    async def get_resource_utilization(self) -> list[ResourceMetrics]:
        """Collect resource utilization stats for all Docker services.

        Iterates over all services in DOCKER_SERVICES and collects
        CPU and memory metrics for running containers.

        Returns:
            List of ResourceMetrics for all reachable containers.
        """
        metrics: list[ResourceMetrics] = []
        now = datetime.now(timezone.utc)

        try:
            client = self._get_client()

            for service_name, container_name in self.DOCKER_SERVICES.items():
                try:
                    container = client.containers.get(container_name)
                    # Only collect stats for running containers
                    if container.status != "running":
                        continue

                    stats = container.stats(stream=False)
                    cpu_percent = self._calculate_cpu_percent(stats)
                    memory_used_mb = self._calculate_memory_used_mb(stats)
                    memory_limit_mb = self._calculate_memory_limit_mb(stats)

                    metrics.append(
                        ResourceMetrics(
                            service_name=service_name,
                            container_name=container_name,
                            cpu_percent=cpu_percent,
                            memory_used_mb=memory_used_mb,
                            memory_limit_mb=memory_limit_mb,
                            recorded_at=now,
                        )
                    )
                except (NotFound, APIError) as e:
                    logger.warning(
                        "Failed to get stats for %s: %s",
                        container_name,
                        str(e),
                    )
                    continue

        except DockerException as e:
            logger.error("Docker socket unavailable for resource collection: %s", str(e))

        return metrics

    async def restart_container(
        self, container_name: str, timeout: int = 30
    ) -> RestartResult:
        """Restart a Docker container.

        Args:
            container_name: The Docker container name to restart.
            timeout: Seconds to wait for the container to stop before killing it.

        Returns:
            RestartResult indicating success/failure and duration.
        """
        start_time = time.monotonic()

        try:
            client = self._get_client()
            container = client.containers.get(container_name)
            container.restart(timeout=timeout)
            duration = time.monotonic() - start_time

            return RestartResult(
                success=True,
                container_name=container_name,
                message=f"Container {container_name} restarted successfully",
                duration_seconds=round(duration, 2),
            )

        except NotFound:
            duration = time.monotonic() - start_time
            return RestartResult(
                success=False,
                container_name=container_name,
                message=f"Container {container_name} not found",
                duration_seconds=round(duration, 2),
            )
        except APIError as e:
            duration = time.monotonic() - start_time
            return RestartResult(
                success=False,
                container_name=container_name,
                message=f"Failed to restart {container_name}: {str(e)}",
                duration_seconds=round(duration, 2),
            )
        except DockerException as e:
            duration = time.monotonic() - start_time
            return RestartResult(
                success=False,
                container_name=container_name,
                message=f"Docker error restarting {container_name}: {str(e)}",
                duration_seconds=round(duration, 2),
            )

    async def get_container_version(self, container_name: str) -> str:
        """Extract the software version from a container's labels or image tag.

        Checks container labels first (e.g., "org.opencontainers.image.version"),
        then falls back to the image tag.

        Args:
            container_name: The Docker container name to query.

        Returns:
            Version string, or "unknown" if not determinable.
        """
        try:
            client = self._get_client()
            container = client.containers.get(container_name)
            return self._extract_version(container)
        except (DockerException, NotFound, APIError):
            return "unknown"

    def _extract_version(self, container: "docker.models.containers.Container") -> str:
        """Extract version from container labels or image tag.

        Checks multiple label conventions and falls back to image tag parsing.

        Args:
            container: A Docker container object.

        Returns:
            Version string extracted from labels or image tag.
        """
        # Check common version labels
        labels = container.labels or {}
        version_labels = [
            "org.opencontainers.image.version",
            "version",
            "app.version",
        ]
        for label in version_labels:
            if label in labels:
                return labels[label]

        # Fall back to image tag
        try:
            image = container.image
            if image and image.tags:
                # Tags are like "postgres:16.4-alpine" — extract after ":"
                tag = image.tags[0]
                if ":" in tag:
                    return tag.split(":")[-1]
                return tag
        except (AttributeError, IndexError):
            pass

        return "unknown"

    @staticmethod
    def _calculate_cpu_percent(stats: dict) -> float:
        """Calculate CPU usage percentage from Docker stats JSON.

        Uses the delta between current and previous CPU readings to
        compute the percentage of available CPU time used.

        Args:
            stats: Raw stats dictionary from Docker API.

        Returns:
            CPU usage as a percentage (0.0–100.0+). Returns 0.0 if
            stats are unavailable or malformed.
        """
        try:
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})

            cpu_usage = cpu_stats.get("cpu_usage", {})
            precpu_usage = precpu_stats.get("cpu_usage", {})

            cpu_delta = cpu_usage.get("total_usage", 0) - precpu_usage.get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get(
                "system_cpu_usage", 0
            )

            if system_delta <= 0 or cpu_delta < 0:
                return 0.0

            # Number of CPUs available to the container
            online_cpus = cpu_stats.get("online_cpus")
            if not online_cpus:
                percpu = cpu_usage.get("percpu_usage")
                online_cpus = len(percpu) if percpu else 1

            cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
            return round(cpu_percent, 2)
        except (KeyError, TypeError, ZeroDivisionError):
            return 0.0

    @staticmethod
    def _calculate_memory_used_mb(stats: dict) -> float:
        """Calculate memory usage in megabytes from Docker stats.

        Uses memory_stats.usage minus cache for accurate active memory.

        Args:
            stats: Raw stats dictionary from Docker API.

        Returns:
            Memory usage in MB, rounded to 2 decimal places.
        """
        try:
            memory_stats = stats.get("memory_stats", {})
            usage = memory_stats.get("usage", 0)
            # Subtract cache if available (Linux cgroups v1)
            cache = memory_stats.get("stats", {}).get("cache", 0)
            active_usage = usage - cache
            return round(active_usage / (1024 * 1024), 2)
        except (KeyError, TypeError):
            return 0.0

    @staticmethod
    def _calculate_memory_limit_mb(stats: dict) -> float | None:
        """Calculate memory limit in megabytes from Docker stats.

        Args:
            stats: Raw stats dictionary from Docker API.

        Returns:
            Memory limit in MB, or None if no limit is set.
            A limit exceeding 1 PB is treated as "no limit" (kernel max).
        """
        try:
            memory_stats = stats.get("memory_stats", {})
            limit = memory_stats.get("limit", 0)
            if limit <= 0:
                return None
            # Docker reports kernel max (~9 exabytes) when no limit is set
            # Treat anything over 1 PB as "no limit"
            if limit > 1024**5:  # 1 PB
                return None
            return round(limit / (1024 * 1024), 2)
        except (KeyError, TypeError):
            return None

    @staticmethod
    def is_memory_warning(memory_used_mb: float, memory_limit_mb: float | None) -> bool:
        """Check if memory utilization exceeds the 90% warning threshold.

        Args:
            memory_used_mb: Current memory usage in MB.
            memory_limit_mb: Container memory limit in MB (None if unlimited).

        Returns:
            True if memory_used_mb / memory_limit_mb > 0.9, False otherwise.
        """
        if memory_limit_mb is None or memory_limit_mb <= 0:
            return False
        return (memory_used_mb / memory_limit_mb) > 0.9
