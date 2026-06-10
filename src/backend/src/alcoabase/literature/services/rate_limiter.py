"""Redis-backed hierarchical rate limiter using sliding window algorithm.

Enforces request rate limits at three levels:
1. System-wide per-source (requests per second) — protects external APIs
2. Per-company across all sources (requests per minute) — ensures fair sharing
3. Per-company per-source (requests per minute) — granular tenant control

Uses Redis sorted sets with timestamps as scores to implement a precise
sliding window counter. All operations are atomic via Redis pipelines.

References:
    - Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
    - Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6

See also:
    https://redis.io/commands/zadd
    https://redis.io/commands/zrangebyscore
    https://redis.io/commands/zremrangebyscore
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum

import redis.asyncio as aioredis

from alcoabase.literature.exceptions import QueueFullError, RateLimitExceededError

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Default system-level rate limits per source (requests per second).
# Based on published API policies:
#   PubMed: 10 RPS without API key, 100 RPS with key
#   Crossref: 50 RPS (polite pool)
#   arXiv: 1 request per 3 seconds ≈ 0.33 RPS, rounded to 1 RPS minimum
DEFAULT_SYSTEM_LIMITS: dict[str, int] = {
    "pubmed": 10,
    "crossref": 50,
    "arxiv": 1,
}

# Maximum queued requests per source before rejection.
MAX_QUEUE_SIZE: int = 500

# Sliding window durations.
SYSTEM_WINDOW_SECONDS: float = 1.0  # 1-second window for system RPS
COMPANY_WINDOW_SECONDS: float = 60.0  # 60-second window for company RPM

# Redis key prefixes.
KEY_PREFIX = "lit:ratelimit"


# ─────────────────────────────────────────────────────────────────────────────
# Enums and Data Classes
# ─────────────────────────────────────────────────────────────────────────────


class RateLimitScope(StrEnum):
    """Scope at which rate limiting is applied."""

    SYSTEM_PER_SOURCE = "system_per_source"
    COMPANY_ALL_SOURCES = "company_all_sources"
    COMPANY_PER_SOURCE = "company_per_source"


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: Whether the request is permitted.
        remaining: Requests remaining in current window.
        retry_after_seconds: Seconds until next window (if not allowed).
        queued: Whether the request was queued for later execution.
        queue_position: Position in queue (if queued).
    """

    allowed: bool
    remaining: int
    retry_after_seconds: float | None = None
    queued: bool = False
    queue_position: int | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter Service
# ─────────────────────────────────────────────────────────────────────────────


class RateLimiter:
    """Hierarchical rate limiter with Redis-backed sliding windows.

    Enforces limits at three levels (all must pass for a request to proceed):
    1. System-wide per-source (requests/second)
    2. Per-company across all sources (requests/minute)
    3. Per-company per-source (requests/minute)

    The sliding window uses Redis sorted sets where each member is a unique
    request ID and the score is the Unix timestamp of the request. Expired
    entries are pruned on each check.

    Example:
        >>> limiter = RateLimiter("redis://localhost:6379/0")
        >>> result = await limiter.check_and_consume("pubmed", company_id=1)
        >>> if result.allowed:
        ...     # proceed with request
        ...     pass
    """

    def __init__(self, redis_url: str) -> None:
        """Initialize with Redis connection.

        Args:
            redis_url: Redis connection URL for counter storage.
        """
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=True
        )

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.aclose()

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    async def check_and_consume(
        self,
        source_name: str,
        company_id: int,
    ) -> RateLimitResult:
        """Check all rate limit levels and consume a token if allowed.

        Checks are performed in order:
        1. System per-source (RPS)
        2. Company all-sources (RPM)
        3. Company per-source (RPM)

        If the system limit is reached but the queue is not full, the
        request is queued rather than rejected immediately.

        Args:
            source_name: The adapter name being called.
            company_id: The requesting company's ID.

        Returns:
            RateLimitResult indicating whether the request can proceed.

        Raises:
            QueueFullError: If the per-source queue is at max capacity.
            RateLimitExceededError: If company-level rate limit is exceeded.
        """
        now = time.time()
        request_id = str(uuid.uuid4())

        # ── Check 1: System per-source (RPS) ─────────────────────────────
        system_limit = await self.get_system_limit(source_name)
        system_key = self._system_window_key(source_name)

        system_count = await self._get_window_count(
            system_key, now, SYSTEM_WINDOW_SECONDS
        )

        if system_count >= system_limit:
            # System limit reached — attempt to queue
            queue_key = self._queue_key(source_name)
            queue_size = await self._redis.zcard(queue_key)

            if queue_size >= MAX_QUEUE_SIZE:
                # Queue is full — estimate wait time based on drain rate
                estimated_wait = self._estimate_wait_time(
                    queue_size, system_limit
                )
                raise QueueFullError(
                    f"Request queue for source '{source_name}' is full "
                    f"({MAX_QUEUE_SIZE} queued requests).",
                    source_adapter_name=source_name,
                    queue_size=MAX_QUEUE_SIZE,
                    estimated_wait_seconds=estimated_wait,
                )

            # Queue the request
            await self._redis.zadd(queue_key, {request_id: now})
            queue_position = int(queue_size) + 1
            retry_after = SYSTEM_WINDOW_SECONDS / system_limit

            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=retry_after,
                queued=True,
                queue_position=queue_position,
            )

        # ── Check 2: Company all-sources (RPM) ───────────────────────────
        company_all_key = self._company_all_sources_key(company_id)
        company_all_limit = await self._get_company_all_sources_limit(
            company_id, source_name
        )
        company_all_count = await self._get_window_count(
            company_all_key, now, COMPANY_WINDOW_SECONDS
        )

        if company_all_count >= company_all_limit:
            # Calculate retry_after as remaining time in the window
            oldest_score = await self._get_oldest_score(company_all_key)
            retry_after = self._calculate_retry_after(
                oldest_score, now, COMPANY_WINDOW_SECONDS
            )
            raise RateLimitExceededError(
                f"Company {company_id} all-sources rate limit exceeded "
                f"({company_all_limit} RPM).",
                retry_after_seconds=retry_after,
                company_id=company_id,
            )

        # ── Check 3: Company per-source (RPM) ────────────────────────────
        company_source_key = self._company_per_source_key(company_id, source_name)
        company_source_limit = await self._get_company_per_source_limit(
            company_id, source_name
        )
        company_source_count = await self._get_window_count(
            company_source_key, now, COMPANY_WINDOW_SECONDS
        )

        if company_source_count >= company_source_limit:
            oldest_score = await self._get_oldest_score(company_source_key)
            retry_after = self._calculate_retry_after(
                oldest_score, now, COMPANY_WINDOW_SECONDS
            )
            raise RateLimitExceededError(
                f"Company {company_id} per-source rate limit exceeded "
                f"for '{source_name}' ({company_source_limit} RPM).",
                source_adapter_name=source_name,
                retry_after_seconds=retry_after,
                company_id=company_id,
            )

        # ── All checks pass — consume tokens at all levels ───────────────
        pipe = self._redis.pipeline()

        # Add to system window
        pipe.zadd(system_key, {request_id: now})
        pipe.expire(system_key, int(SYSTEM_WINDOW_SECONDS) + 1)

        # Add to company all-sources window
        pipe.zadd(company_all_key, {request_id: now})
        pipe.expire(company_all_key, int(COMPANY_WINDOW_SECONDS) + 1)

        # Add to company per-source window
        pipe.zadd(company_source_key, {request_id: now})
        pipe.expire(company_source_key, int(COMPANY_WINDOW_SECONDS) + 1)

        await pipe.execute()

        # Increment usage counter
        await self._increment_usage(company_id, "requests_made")

        remaining = system_limit - system_count - 1
        return RateLimitResult(
            allowed=True,
            remaining=max(0, remaining),
        )

    async def get_system_limit(self, source_name: str) -> int:
        """Get the current system-level rate limit for a source.

        Falls back to defaults if no custom limit is configured.

        Args:
            source_name: Adapter name.

        Returns:
            Requests per second allowed at system level.
        """
        key = f"{KEY_PREFIX}:system:{source_name}:limit"
        value = await self._redis.get(key)
        if value is not None:
            return int(value)
        return DEFAULT_SYSTEM_LIMITS.get(source_name, 10)

    async def set_system_limit(self, source_name: str, rps: int) -> None:
        """Update the system-level rate limit for a source.

        The new limit is applied immediately (within the next check).

        Args:
            source_name: Adapter name.
            rps: New requests-per-second limit (1–1000).

        Raises:
            ValueError: If rps is outside the valid range [1, 1000].
        """
        if not (1 <= rps <= 1000):
            raise ValueError(
                f"Rate limit must be between 1 and 1000 RPS, got {rps}."
            )
        key = f"{KEY_PREFIX}:system:{source_name}:limit"
        await self._redis.set(key, str(rps))
        logger.info(
            "Updated system rate limit for '%s' to %d RPS.", source_name, rps
        )

    async def get_company_usage(self, company_id: int) -> dict[str, int]:
        """Get usage metrics for a company.

        Args:
            company_id: Company to query.

        Returns:
            Dict with keys: requests_made, requests_queued, requests_rate_limited.
        """
        prefix = f"{KEY_PREFIX}:usage:{company_id}"
        pipe = self._redis.pipeline()
        pipe.get(f"{prefix}:requests_made")
        pipe.get(f"{prefix}:requests_queued")
        pipe.get(f"{prefix}:requests_rate_limited")
        results = await pipe.execute()

        return {
            "requests_made": int(results[0] or 0),
            "requests_queued": int(results[1] or 0),
            "requests_rate_limited": int(results[2] or 0),
        }

    def calculate_default_company_limit(
        self, system_limit: int, active_company_count: int
    ) -> int:
        """Calculate the default per-company limit.

        Formula: max(5, system_limit // active_company_count)

        This is a pure function with no side effects.

        Args:
            system_limit: System-level limit for the source (RPS or RPM).
            active_company_count: Number of active companies (must be ≥ 1).

        Returns:
            Per-company requests-per-minute limit (minimum 5).
        """
        if active_company_count < 1:
            active_company_count = 1
        return max(5, system_limit // active_company_count)

    # ─────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _get_window_count(
        self, key: str, now: float, window_seconds: float
    ) -> int:
        """Count requests in the sliding window and prune expired entries.

        Args:
            key: Redis sorted set key.
            now: Current Unix timestamp.
            window_seconds: Window duration.

        Returns:
            Number of requests currently in the window.
        """
        window_start = now - window_seconds

        # Remove expired entries
        await self._redis.zremrangebyscore(key, "-inf", window_start)

        # Count remaining entries in window
        count = await self._redis.zcard(key)
        return int(count)

    async def _get_oldest_score(self, key: str) -> float | None:
        """Get the timestamp of the oldest entry in the sorted set.

        Args:
            key: Redis sorted set key.

        Returns:
            Oldest timestamp score, or None if set is empty.
        """
        result = await self._redis.zrange(key, 0, 0, withscores=True)
        if result:
            return result[0][1]
        return None

    def _calculate_retry_after(
        self, oldest_score: float | None, now: float, window_seconds: float
    ) -> float:
        """Calculate seconds until the next request slot opens.

        Args:
            oldest_score: Timestamp of the oldest request in window.
            now: Current Unix timestamp.
            window_seconds: Window duration.

        Returns:
            Seconds to wait before retrying.
        """
        if oldest_score is None:
            return window_seconds
        # The oldest entry will expire at oldest_score + window_seconds
        retry_after = (oldest_score + window_seconds) - now
        return max(0.1, retry_after)  # At least 100ms

    def _estimate_wait_time(self, queue_size: int, system_limit: int) -> float:
        """Estimate wait time based on current queue size and drain rate.

        Args:
            queue_size: Number of requests currently in the queue.
            system_limit: System RPS for the source (drain rate).

        Returns:
            Estimated seconds until a queue slot opens.
        """
        if system_limit <= 0:
            return 60.0
        return queue_size / system_limit

    async def _get_company_all_sources_limit(
        self, company_id: int, source_name: str
    ) -> int:
        """Get the company-wide all-sources RPM limit.

        Checks for a custom limit first, then falls back to the calculated
        default based on system limit and active company count.

        Args:
            company_id: Company ID to check.
            source_name: Source name (for system limit lookup).

        Returns:
            Requests per minute allowed for the company across all sources.
        """
        # Check for custom company-wide limit
        custom_key = f"{KEY_PREFIX}:company:{company_id}:all_sources:limit"
        custom_value = await self._redis.get(custom_key)
        if custom_value is not None:
            return int(custom_value)

        # Calculate default: based on system limit and company count
        system_limit = await self.get_system_limit(source_name)
        active_count = await self._get_active_company_count()
        # Convert system RPS to RPM for company-level comparison
        system_rpm = system_limit * 60
        return self.calculate_default_company_limit(system_rpm, active_count)

    async def _get_company_per_source_limit(
        self, company_id: int, source_name: str
    ) -> int:
        """Get the per-company per-source RPM limit.

        Checks for a custom limit first, then falls back to the calculated
        default.

        Args:
            company_id: Company ID to check.
            source_name: Source adapter name.

        Returns:
            Requests per minute allowed for the company for this source.
        """
        # Check for custom per-source limit
        custom_key = (
            f"{KEY_PREFIX}:company:{company_id}:source:{source_name}:limit"
        )
        custom_value = await self._redis.get(custom_key)
        if custom_value is not None:
            return int(custom_value)

        # Calculate default
        system_limit = await self.get_system_limit(source_name)
        active_count = await self._get_active_company_count()
        # Convert system RPS to RPM for per-source company limit
        system_rpm = system_limit * 60
        return self.calculate_default_company_limit(system_rpm, active_count)

    async def _get_active_company_count(self) -> int:
        """Get the number of active companies from Redis cache.

        Falls back to 1 if not set (single-tenant default).

        Returns:
            Number of active companies.
        """
        key = f"{KEY_PREFIX}:active_company_count"
        value = await self._redis.get(key)
        if value is not None:
            return max(1, int(value))
        return 1

    async def set_active_company_count(self, count: int) -> None:
        """Set the active company count in Redis.

        Called by the application when company state changes.

        Args:
            count: Number of currently active companies.
        """
        key = f"{KEY_PREFIX}:active_company_count"
        await self._redis.set(key, str(max(1, count)))

    async def set_company_all_sources_limit(
        self, company_id: int, rpm: int
    ) -> None:
        """Set a custom all-sources RPM limit for a company.

        Args:
            company_id: Company to configure.
            rpm: Requests per minute limit.
        """
        key = f"{KEY_PREFIX}:company:{company_id}:all_sources:limit"
        await self._redis.set(key, str(rpm))

    async def set_company_per_source_limit(
        self, company_id: int, source_name: str, rpm: int
    ) -> None:
        """Set a custom per-source RPM limit for a company.

        Args:
            company_id: Company to configure.
            source_name: Source adapter name.
            rpm: Requests per minute limit.
        """
        key = f"{KEY_PREFIX}:company:{company_id}:source:{source_name}:limit"
        await self._redis.set(key, str(rpm))

    async def _increment_usage(self, company_id: int, metric: str) -> None:
        """Increment a usage metric counter for a company.

        Counters expire after 24 hours to auto-reset daily.

        Args:
            company_id: Company to track.
            metric: Metric name (requests_made, requests_queued, requests_rate_limited).
        """
        key = f"{KEY_PREFIX}:usage:{company_id}:{metric}"
        pipe = self._redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)  # 24-hour TTL
        await pipe.execute()

    # ─────────────────────────────────────────────────────────────────────
    # Redis Key Builders
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _system_window_key(source_name: str) -> str:
        """Build Redis key for system-level per-source sliding window.

        Args:
            source_name: Adapter name.

        Returns:
            Redis key string.
        """
        return f"{KEY_PREFIX}:system:{source_name}:window"

    @staticmethod
    def _queue_key(source_name: str) -> str:
        """Build Redis key for per-source request queue.

        Args:
            source_name: Adapter name.

        Returns:
            Redis key string.
        """
        return f"{KEY_PREFIX}:system:{source_name}:queue"

    @staticmethod
    def _company_all_sources_key(company_id: int) -> str:
        """Build Redis key for company-wide all-sources sliding window.

        Args:
            company_id: Company ID.

        Returns:
            Redis key string.
        """
        return f"{KEY_PREFIX}:company:{company_id}:all_sources:window"

    @staticmethod
    def _company_per_source_key(company_id: int, source_name: str) -> str:
        """Build Redis key for company per-source sliding window.

        Args:
            company_id: Company ID.
            source_name: Adapter name.

        Returns:
            Redis key string.
        """
        return f"{KEY_PREFIX}:company:{company_id}:source:{source_name}:window"
