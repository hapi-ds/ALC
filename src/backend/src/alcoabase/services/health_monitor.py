"""Health monitoring service for infrastructure services.

Performs periodic health checks against all monitored infrastructure services
(PostgreSQL, MinIO, OpenSearch, Redis, vLLM), classifies their status, stores
results with bounded history, and detects status transitions.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 10.1–10.9, 11.1–11.6
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import aioboto3
import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.models.system_config import HealthCheckResult

# Maximum number of health check results stored per service
MAX_RESULTS_PER_SERVICE = 100

# List of infrastructure services monitored by health checks
MONITORED_SERVICES = ["postgresql", "minio", "opensearch", "redis", "vllm"]

# Default thresholds (in milliseconds)
DEFAULT_DEGRADED_THRESHOLD_MS = 5000.0
DEFAULT_TIMEOUT_MS = 10000.0


class HealthMonitor:
    """Performs periodic health checks and stores results.

    Checks all monitored infrastructure services concurrently, classifies
    their status based on response time thresholds, stores results in the
    database with a bounded buffer (max 100 per service), and detects
    status transitions.

    Attributes:
        MONITORED_SERVICES: List of service names to check.
    """

    MONITORED_SERVICES = MONITORED_SERVICES

    def __init__(
        self,
        degraded_threshold_ms: float = DEFAULT_DEGRADED_THRESHOLD_MS,
        timeout_ms: float = DEFAULT_TIMEOUT_MS,
    ) -> None:
        """Initialize the HealthMonitor with configurable thresholds.

        Args:
            degraded_threshold_ms: Response time threshold (ms) above which
                a service is classified as "degraded".
            timeout_ms: Response time threshold (ms) above which a service
                is classified as "unreachable".
        """
        self.degraded_threshold_ms = degraded_threshold_ms
        self.timeout_ms = timeout_ms

    async def check_all_services(
        self, session: AsyncSession
    ) -> list[HealthCheckResult]:
        """Execute health checks for all monitored services concurrently.

        Runs all service checks in parallel with a 10-second total timeout.
        Stores results in the database, detects status transitions, and
        enforces the bounded buffer (max 100 results per service).

        Args:
            session: Active async database session.

        Returns:
            List of HealthCheckResult objects for all checked services.
        """
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[
                        self._check_and_build_result(service_name)
                        for service_name in self.MONITORED_SERVICES
                    ],
                    return_exceptions=True,
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            # If the entire gather times out, mark all services as unreachable
            results = [
                self._build_unreachable_result(service_name, "Health check cycle timeout (10s)")
                for service_name in self.MONITORED_SERVICES
            ]

        health_check_results: list[HealthCheckResult] = []

        for i, result in enumerate(results):
            service_name = self.MONITORED_SERVICES[i]
            if isinstance(result, Exception):
                # Individual check raised an exception
                check_result = self._build_unreachable_result(
                    service_name, str(result)
                )
            elif isinstance(result, dict):
                check_result = HealthCheckResult(
                    service_name=service_name,
                    status=result["status"],
                    response_time_ms=result["response_time_ms"],
                    error_message=result.get("error_message"),
                    checked_at=datetime.now(timezone.utc),
                )
            else:
                check_result = self._build_unreachable_result(
                    service_name, "Unexpected result type"
                )

            # Detect status transitions
            await self._detect_transition(check_result, session)

            session.add(check_result)
            health_check_results.append(check_result)

        await session.flush()

        # Enforce bounded buffer for each service
        for service_name in self.MONITORED_SERVICES:
            await self._evict_oldest(service_name, session)

        return health_check_results

    async def check_service(self, service_name: str) -> dict[str, Any]:
        """Perform a connection-level health check for a specific service.

        Executes a lightweight check appropriate for the service type:
        - postgresql: SELECT 1
        - minio: list_buckets
        - opensearch: cluster health
        - redis: PING
        - vllm: GET /health

        Args:
            service_name: Name of the service to check.

        Returns:
            Dictionary with keys: status, response_time_ms, error_message (optional).

        Raises:
            ValueError: If service_name is not in MONITORED_SERVICES.
        """
        if service_name not in self.MONITORED_SERVICES:
            raise ValueError(
                f"Unknown service: {service_name}. "
                f"Must be one of {self.MONITORED_SERVICES}"
            )

        check_fn = {
            "postgresql": self._check_postgresql,
            "minio": self._check_minio,
            "opensearch": self._check_opensearch,
            "redis": self._check_redis,
            "vllm": self._check_vllm,
        }[service_name]

        start_time = time.perf_counter()
        try:
            await check_fn()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            status = self.classify_status(
                elapsed_ms, self.degraded_threshold_ms, self.timeout_ms
            )
            return {
                "status": status,
                "response_time_ms": round(elapsed_ms, 2),
            }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return {
                "status": "unreachable",
                "response_time_ms": round(elapsed_ms, 2),
                "error_message": str(e),
            }

    @staticmethod
    def classify_status(
        response_time_ms: float,
        degraded_threshold_ms: float,
        timeout_ms: float,
    ) -> str:
        """Classify service health status based on response time.

        Pure function that determines the health classification based on
        measured response time relative to configured thresholds.

        Args:
            response_time_ms: Measured response time in milliseconds.
            degraded_threshold_ms: Threshold above which status is "degraded".
            timeout_ms: Threshold above which status is "unreachable".

        Returns:
            One of "healthy", "degraded", or "unreachable".
        """
        if response_time_ms < degraded_threshold_ms:
            return "healthy"
        elif response_time_ms < timeout_ms:
            return "degraded"
        else:
            return "unreachable"

    async def get_current_status(
        self, session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Return the latest health check result per service with metrics.

        For each monitored service, returns the most recent health check
        result along with:
        - uptime_pct_24h: Percentage of "healthy" checks in the last 24 hours.
        - avg_response_time_5min: Average response time over the last 5 minutes.

        Args:
            session: Active async database session.

        Returns:
            List of dictionaries with service health status and metrics.
        """
        statuses: list[dict[str, Any]] = []

        for service_name in self.MONITORED_SERVICES:
            # Get latest result
            latest_query = (
                select(HealthCheckResult)
                .where(HealthCheckResult.service_name == service_name)
                .order_by(HealthCheckResult.checked_at.desc())
                .limit(1)
            )
            result = await session.execute(latest_query)
            latest = result.scalar_one_or_none()

            if latest is None:
                statuses.append({
                    "service_name": service_name,
                    "status": "unreachable",
                    "response_time_ms": None,
                    "last_checked": None,
                    "uptime_pct_24h": 0.0,
                    "avg_response_time_5min": None,
                })
                continue

            # Calculate uptime percentage over last 24 hours
            uptime_pct = await self.get_uptime_percentage(
                service_name, hours=24, session=session
            )

            # Calculate average response time over last 5 minutes
            avg_response_time = await self._get_avg_response_time(
                service_name, minutes=5, session=session
            )

            statuses.append({
                "service_name": service_name,
                "status": latest.status,
                "response_time_ms": latest.response_time_ms,
                "last_checked": latest.checked_at,
                "uptime_pct_24h": uptime_pct,
                "avg_response_time_5min": avg_response_time,
            })

        return statuses

    async def get_service_history(
        self,
        service_name: str,
        limit: int,
        session: AsyncSession,
    ) -> list[HealthCheckResult]:
        """Return the last N health check results for a service.

        Args:
            service_name: Name of the service to query.
            limit: Maximum number of results to return (capped at 100).
            session: Active async database session.

        Returns:
            List of HealthCheckResult objects ordered by checked_at descending.
        """
        capped_limit = min(limit, MAX_RESULTS_PER_SERVICE)
        query = (
            select(HealthCheckResult)
            .where(HealthCheckResult.service_name == service_name)
            .order_by(HealthCheckResult.checked_at.desc())
            .limit(capped_limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_uptime_percentage(
        self,
        service_name: str,
        hours: int,
        session: AsyncSession,
    ) -> float:
        """Calculate the percentage of "healthy" checks over a time period.

        Args:
            service_name: Name of the service to calculate uptime for.
            hours: Number of hours to look back.
            session: Active async database session.

        Returns:
            Percentage of healthy checks (0.0 to 100.0). Returns 0.0 if
            no checks exist in the time period.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Count total checks in the period
        total_query = (
            select(func.count(HealthCheckResult.id))
            .where(HealthCheckResult.service_name == service_name)
            .where(HealthCheckResult.checked_at >= cutoff)
        )
        total_result = await session.execute(total_query)
        total_count = total_result.scalar_one()

        if total_count == 0:
            return 0.0

        # Count healthy checks in the period
        healthy_query = (
            select(func.count(HealthCheckResult.id))
            .where(HealthCheckResult.service_name == service_name)
            .where(HealthCheckResult.checked_at >= cutoff)
            .where(HealthCheckResult.status == "healthy")
        )
        healthy_result = await session.execute(healthy_query)
        healthy_count = healthy_result.scalar_one()

        return round((healthy_count / total_count) * 100.0, 2)

    # ─────────────────────────────────────────────────────────────────────
    # Private helper methods
    # ─────────────────────────────────────────────────────────────────────

    async def _check_and_build_result(self, service_name: str) -> dict[str, Any]:
        """Run check_service and return the result dict.

        Args:
            service_name: Name of the service to check.

        Returns:
            Dictionary with status, response_time_ms, and optional error_message.
        """
        return await self.check_service(service_name)

    def _build_unreachable_result(
        self, service_name: str, error_message: str
    ) -> HealthCheckResult:
        """Build an unreachable HealthCheckResult for a service.

        Args:
            service_name: Name of the service.
            error_message: Description of the error.

        Returns:
            HealthCheckResult with status "unreachable".
        """
        return HealthCheckResult(
            service_name=service_name,
            status="unreachable",
            response_time_ms=None,
            error_message=error_message,
            checked_at=datetime.now(timezone.utc),
        )

    async def _detect_transition(
        self, current_result: HealthCheckResult, session: AsyncSession
    ) -> None:
        """Detect and record status transitions.

        Compares the current check result with the previous result for the
        same service. Sets is_transition=True and records previous_status
        when transitioning from "healthy" to "degraded" or "unreachable".

        Args:
            current_result: The new health check result to evaluate.
            session: Active async database session.
        """
        # Get the most recent previous result for this service
        prev_query = (
            select(HealthCheckResult)
            .where(HealthCheckResult.service_name == current_result.service_name)
            .order_by(HealthCheckResult.checked_at.desc())
            .limit(1)
        )
        result = await session.execute(prev_query)
        previous = result.scalar_one_or_none()

        if previous is not None:
            current_result.previous_status = previous.status
            # Transition is recorded when moving from "healthy" to degraded/unreachable
            if (
                previous.status == "healthy"
                and current_result.status in ("degraded", "unreachable")
            ):
                current_result.is_transition = True
            else:
                current_result.is_transition = False
        else:
            current_result.previous_status = None
            current_result.is_transition = False

    async def _evict_oldest(
        self, service_name: str, session: AsyncSession
    ) -> None:
        """Enforce bounded buffer by evicting oldest results beyond limit.

        After storing a new result, if the count exceeds MAX_RESULTS_PER_SERVICE
        (100), the oldest entries are deleted.

        Args:
            service_name: Name of the service to enforce the buffer for.
            session: Active async database session.
        """
        # Count current results for this service
        count_query = select(func.count(HealthCheckResult.id)).where(
            HealthCheckResult.service_name == service_name
        )
        count_result = await session.execute(count_query)
        count = count_result.scalar_one()

        if count > MAX_RESULTS_PER_SERVICE:
            # Find the IDs to keep (most recent MAX_RESULTS_PER_SERVICE)
            keep_query = (
                select(HealthCheckResult.id)
                .where(HealthCheckResult.service_name == service_name)
                .order_by(HealthCheckResult.checked_at.desc())
                .limit(MAX_RESULTS_PER_SERVICE)
            )
            keep_result = await session.execute(keep_query)
            keep_ids = [row[0] for row in keep_result.all()]

            # Delete all results not in the keep set
            delete_stmt = delete(HealthCheckResult).where(
                HealthCheckResult.service_name == service_name,
                HealthCheckResult.id.notin_(keep_ids),
            )
            await session.execute(delete_stmt)

    async def _get_avg_response_time(
        self,
        service_name: str,
        minutes: int,
        session: AsyncSession,
    ) -> float | None:
        """Calculate average response time over a time window.

        Args:
            service_name: Name of the service.
            minutes: Number of minutes to look back.
            session: Active async database session.

        Returns:
            Average response time in milliseconds, or None if no data.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        avg_query = (
            select(func.avg(HealthCheckResult.response_time_ms))
            .where(HealthCheckResult.service_name == service_name)
            .where(HealthCheckResult.checked_at >= cutoff)
            .where(HealthCheckResult.response_time_ms.isnot(None))
        )
        result = await session.execute(avg_query)
        avg_value = result.scalar_one()

        if avg_value is None:
            return None
        return round(float(avg_value), 2)

    # ─────────────────────────────────────────────────────────────────────
    # Service-specific health check implementations
    # ─────────────────────────────────────────────────────────────────────

    async def _check_postgresql(self) -> None:
        """Check PostgreSQL connectivity by executing SELECT 1.

        Uses a separate short-lived connection to avoid interfering with
        the application's connection pool.

        Raises:
            Exception: If the connection or query fails.
        """
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text

        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=1,
            max_overflow=0,
            pool_timeout=5,
        )
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        finally:
            await engine.dispose()

    async def _check_minio(self) -> None:
        """Check MinIO connectivity by listing buckets.

        Raises:
            Exception: If the connection or list_buckets call fails.
        """
        settings = get_settings()
        minio_session = aioboto3.Session()
        protocol = "https" if settings.minio_use_ssl else "http"
        endpoint_url = f"{protocol}://{settings.minio_endpoint}"

        async with minio_session.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            use_ssl=settings.minio_use_ssl,
        ) as client:
            await client.list_buckets()

    async def _check_opensearch(self) -> None:
        """Check OpenSearch connectivity via cluster health endpoint.

        Raises:
            Exception: If the HTTP request fails or returns non-2xx.
        """
        settings = get_settings()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.opensearch_url}/_cluster/health"
            )
            response.raise_for_status()

    async def _check_redis(self) -> None:
        """Check Redis connectivity by sending PING command.

        Raises:
            Exception: If the connection or PING fails.
        """
        import redis.asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(
            settings.redis_url,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    async def _check_vllm(self) -> None:
        """Check vLLM connectivity via GET /health endpoint.

        Raises:
            Exception: If the HTTP request fails or returns non-2xx.
        """
        settings = get_settings()
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.vllm_base_url}/health")
            response.raise_for_status()
