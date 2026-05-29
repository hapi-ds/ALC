"""Storage quota service for managing per-company MinIO storage usage and quotas.

Queries MinIO for per-company storage usage via aioboto3 list_objects_v2 with
prefix aggregation. Manages advisory quota limits and alert thresholds.
Caches usage data in Redis for 60 seconds to reduce MinIO load.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 5.1–5.6, 6.1–6.6
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Literal

import aioboto3
import redis.asyncio as aioredis
from botocore.exceptions import ClientError, ConnectTimeoutError, ReadTimeoutError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.models.company import Company
from alcoabase.models.system_config import StorageQuota

logger = logging.getLogger(__name__)

# Redis cache key and TTL
CACHE_KEY = "storage_quota:usage_per_company"
CACHE_TTL_SECONDS = 60

# MinIO operation timeout
MINIO_TIMEOUT_SECONDS = 10

QuotaStatus = Literal["normal", "quota_warning", "quota_exceeded"]


@dataclass
class CompanyStorageUsage:
    """Storage usage data for a single company.

    Attributes:
        company_id: Company database ID.
        company_name: Company display name.
        usage_bytes: Current storage usage in bytes.
        human_readable: Human-readable storage usage string.
        quota_status: Current quota status classification.
        quota_limit_bytes: Configured quota limit (None if unlimited).
        alert_threshold_pct: Configured alert threshold percentage.
    """

    company_id: int
    company_name: str
    usage_bytes: int
    human_readable: str
    quota_status: QuotaStatus
    quota_limit_bytes: int | None = None
    alert_threshold_pct: int | None = None


@dataclass
class StorageTotals:
    """Aggregate storage usage across all companies.

    Attributes:
        total_used_bytes: Total storage used across all companies.
        total_capacity_bytes: Total available MinIO storage capacity.
        human_readable_used: Human-readable total usage.
        human_readable_capacity: Human-readable total capacity.
        is_stale: Whether the data was served from stale cache.
        last_updated: Unix timestamp of last successful data retrieval.
    """

    total_used_bytes: int
    total_capacity_bytes: int
    human_readable_used: str
    human_readable_capacity: str
    is_stale: bool = False
    last_updated: float | None = None


class StorageQuotaService:
    """Service for managing per-company MinIO storage usage and quotas.

    Queries MinIO for storage usage per company prefix, caches results
    in Redis for 60 seconds, and manages advisory quota limits and
    alert thresholds.

    The service handles MinIO timeouts gracefully by returning cached
    data with a staleness indicator when MinIO is unreachable.
    """

    def __init__(self) -> None:
        """Initialize the storage quota service with settings from environment."""
        settings = get_settings()
        self._session = aioboto3.Session()
        self._bucket = settings.minio_bucket
        protocol = "https" if settings.minio_use_ssl else "http"
        self._endpoint_url = f"{protocol}://{settings.minio_endpoint}"
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._use_ssl = settings.minio_use_ssl
        self._redis_url = settings.redis_url

    def _s3_client_kwargs(self) -> dict:
        """Return common kwargs for creating an S3 client.

        Returns:
            Dictionary of connection parameters for aioboto3 client.
        """
        return {
            "service_name": "s3",
            "endpoint_url": self._endpoint_url,
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "use_ssl": self._use_ssl,
        }

    async def _get_redis(self) -> aioredis.Redis:
        """Create an async Redis client.

        Returns:
            An async Redis client instance.
        """
        return aioredis.from_url(self._redis_url, decode_responses=True)

    async def _get_cached_usage(self) -> tuple[list[dict] | None, float | None]:
        """Retrieve cached usage data from Redis.

        Returns:
            Tuple of (cached_data, last_updated_timestamp) or (None, None) if no cache.
        """
        try:
            redis_client = await self._get_redis()
            try:
                cached = await redis_client.get(CACHE_KEY)
                if cached:
                    data = json.loads(cached)
                    return data.get("usage", []), data.get("last_updated")
                return None, None
            finally:
                await redis_client.aclose()
        except Exception:
            logger.warning("Failed to read from Redis cache", exc_info=True)
            return None, None

    async def _set_cached_usage(self, usage_data: list[dict]) -> None:
        """Store usage data in Redis cache with TTL.

        Args:
            usage_data: List of company usage dictionaries to cache.
        """
        try:
            redis_client = await self._get_redis()
            try:
                cache_payload = json.dumps({
                    "usage": usage_data,
                    "last_updated": time.time(),
                })
                await redis_client.setex(CACHE_KEY, CACHE_TTL_SECONDS, cache_payload)
            finally:
                await redis_client.aclose()
        except Exception:
            logger.warning("Failed to write to Redis cache", exc_info=True)

    async def _fetch_usage_from_minio(self) -> dict[str, int]:
        """Fetch storage usage per company prefix from MinIO.

        Lists all objects in the bucket and aggregates sizes by the
        top-level prefix (company slug).

        Returns:
            Dictionary mapping company prefix to total bytes used.

        Raises:
            asyncio.TimeoutError: If MinIO does not respond within timeout.
            ClientError: If MinIO returns an error.
        """
        usage_by_prefix: dict[str, int] = {}

        async with self._session.client(**self._s3_client_kwargs()) as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self._bucket):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    size = obj["Size"]
                    # Extract company prefix (first path segment)
                    prefix = key.split("/")[0] if "/" in key else key
                    usage_by_prefix[prefix] = usage_by_prefix.get(prefix, 0) + size

        return usage_by_prefix

    async def get_usage_per_company(
        self, session: AsyncSession
    ) -> tuple[list[CompanyStorageUsage], bool]:
        """Get storage usage per company with quota status.

        Queries MinIO for object sizes aggregated by company prefix.
        Results are cached in Redis for 60 seconds. If MinIO is
        unreachable within 10 seconds, returns cached data with
        staleness indicator.

        Args:
            session: SQLAlchemy async session for database queries.

        Returns:
            Tuple of (list of CompanyStorageUsage, is_stale flag).
            is_stale is True when data was served from expired cache
            due to MinIO timeout.
        """
        # Try to fetch fresh data from MinIO with timeout
        is_stale = False
        usage_by_prefix: dict[str, int] | None = None

        try:
            usage_by_prefix = await asyncio.wait_for(
                self._fetch_usage_from_minio(),
                timeout=MINIO_TIMEOUT_SECONDS,
            )
        except (
            asyncio.TimeoutError,
            ClientError,
            ConnectTimeoutError,
            ReadTimeoutError,
            OSError,
        ):
            logger.warning(
                "MinIO timeout or error fetching storage usage, using cached data",
                exc_info=True,
            )

        # If MinIO fetch failed, try cache
        if usage_by_prefix is None:
            cached_data, _ = await self._get_cached_usage()
            if cached_data:
                # Reconstruct CompanyStorageUsage from cached data
                result = [
                    CompanyStorageUsage(
                        company_id=item["company_id"],
                        company_name=item["company_name"],
                        usage_bytes=item["usage_bytes"],
                        human_readable=item["human_readable"],
                        quota_status=item["quota_status"],
                        quota_limit_bytes=item.get("quota_limit_bytes"),
                        alert_threshold_pct=item.get("alert_threshold_pct"),
                    )
                    for item in cached_data
                ]
                return result, True
            # No cache available either
            return [], True

        # Load companies and quotas from database
        companies_result = await session.execute(select(Company).where(Company.is_active == True))  # noqa: E712
        companies = companies_result.scalars().all()

        quotas_result = await session.execute(select(StorageQuota))
        quotas = {q.company_id: q for q in quotas_result.scalars().all()}

        # Build usage list
        result: list[CompanyStorageUsage] = []
        for company in companies:
            # Match company to prefix by slug
            usage_bytes = usage_by_prefix.get(company.slug, 0)
            quota = quotas.get(company.id)

            quota_limit = quota.quota_limit_bytes if quota else None
            threshold_pct = quota.alert_threshold_pct if quota else None

            quota_status = self.compute_quota_status(
                usage_bytes, quota_limit, threshold_pct
            )

            result.append(
                CompanyStorageUsage(
                    company_id=company.id,
                    company_name=company.display_name,
                    usage_bytes=usage_bytes,
                    human_readable=self.format_bytes_human_readable(usage_bytes),
                    quota_status=quota_status,
                    quota_limit_bytes=quota_limit,
                    alert_threshold_pct=threshold_pct,
                )
            )

        # Cache the results
        cache_data = [
            {
                "company_id": u.company_id,
                "company_name": u.company_name,
                "usage_bytes": u.usage_bytes,
                "human_readable": u.human_readable,
                "quota_status": u.quota_status,
                "quota_limit_bytes": u.quota_limit_bytes,
                "alert_threshold_pct": u.alert_threshold_pct,
            }
            for u in result
        ]
        await self._set_cached_usage(cache_data)

        return result, is_stale

    async def get_total_usage(self, session: AsyncSession) -> StorageTotals:
        """Get aggregate storage usage across all companies.

        Aggregates all company usage and reports total MinIO capacity.
        Uses the same cached data as get_usage_per_company.

        Args:
            session: SQLAlchemy async session for database queries.

        Returns:
            StorageTotals with total used, capacity, and human-readable formats.
        """
        usage_list, is_stale = await self.get_usage_per_company(session)

        total_used = sum(u.usage_bytes for u in usage_list)

        # Get total MinIO capacity (disk space available to the bucket)
        total_capacity = await self._get_minio_capacity()

        return StorageTotals(
            total_used_bytes=total_used,
            total_capacity_bytes=total_capacity,
            human_readable_used=self.format_bytes_human_readable(total_used),
            human_readable_capacity=self.format_bytes_human_readable(total_capacity),
            is_stale=is_stale,
            last_updated=time.time(),
        )

    async def _get_minio_capacity(self) -> int:
        """Get total MinIO storage capacity.

        MinIO does not expose a standard S3 API for disk capacity.
        Returns a configured default capacity value. In production,
        this could be obtained from MinIO admin API.

        Returns:
            Total capacity in bytes (default 500 GB).
        """
        # MinIO doesn't expose capacity via S3 API.
        # Default to 500 GB; can be overridden via configuration.
        default_capacity_gb = 500
        return default_capacity_gb * 1024 * 1024 * 1024

    async def set_quota(
        self, company_id: int, limit_bytes: int, session: AsyncSession
    ) -> StorageQuota:
        """Set or update the storage quota limit for a company.

        Upserts the StorageQuota record for the given company.

        Args:
            company_id: The company's database ID.
            limit_bytes: Quota limit in bytes.
            session: SQLAlchemy async session.

        Returns:
            The updated StorageQuota record.
        """
        result = await session.execute(
            select(StorageQuota).where(StorageQuota.company_id == company_id)
        )
        quota = result.scalar_one_or_none()

        if quota is None:
            quota = StorageQuota(
                company_id=company_id,
                quota_limit_bytes=limit_bytes,
            )
            session.add(quota)
        else:
            quota.quota_limit_bytes = limit_bytes

        await session.flush()
        return quota

    async def set_alert_threshold(
        self, company_id: int, threshold_pct: int, session: AsyncSession
    ) -> StorageQuota:
        """Set or update the alert threshold for a company.

        Validates that the threshold is between 1 and 99 (inclusive),
        then upserts the StorageQuota record.

        Args:
            company_id: The company's database ID.
            threshold_pct: Alert threshold as a percentage (1-99).
            session: SQLAlchemy async session.

        Returns:
            The updated StorageQuota record.

        Raises:
            ValueError: If threshold_pct is not between 1 and 99.
        """
        if not (1 <= threshold_pct <= 99):
            raise ValueError(
                f"Alert threshold must be between 1 and 99, got {threshold_pct}"
            )

        result = await session.execute(
            select(StorageQuota).where(StorageQuota.company_id == company_id)
        )
        quota = result.scalar_one_or_none()

        if quota is None:
            quota = StorageQuota(
                company_id=company_id,
                alert_threshold_pct=threshold_pct,
            )
            session.add(quota)
        else:
            quota.alert_threshold_pct = threshold_pct

        await session.flush()
        return quota

    @staticmethod
    def compute_quota_status(
        usage_bytes: int,
        quota_bytes: int | None,
        threshold_pct: int | None,
    ) -> QuotaStatus:
        """Compute the quota status for a company based on usage and limits.

        Pure function that classifies storage status into one of three
        mutually exclusive states.

        Args:
            usage_bytes: Current storage usage in bytes.
            quota_bytes: Configured quota limit in bytes (None = no quota).
            threshold_pct: Alert threshold as percentage of quota (None = no threshold).

        Returns:
            "normal" if no quota or usage ≤ threshold% × quota,
            "quota_warning" if usage > threshold% × quota AND ≤ quota,
            "quota_exceeded" if usage > quota.
        """
        # No quota configured means always normal
        if quota_bytes is None:
            return "normal"

        # Usage exceeds quota
        if usage_bytes > quota_bytes:
            return "quota_exceeded"

        # Check threshold warning
        if threshold_pct is not None:
            threshold_bytes = (threshold_pct / 100.0) * quota_bytes
            if usage_bytes > threshold_bytes:
                return "quota_warning"

        return "normal"

    @staticmethod
    def format_bytes_human_readable(size_bytes: int) -> str:
        """Convert bytes to human-readable binary units.

        Uses binary units (KB, MB, GB, TB) with values rounded to
        2 decimal places. Returns "0 B" for zero bytes.

        Args:
            size_bytes: Size in bytes (non-negative integer).

        Returns:
            Human-readable string (e.g., "1.23 GB", "456.78 MB").
        """
        if size_bytes == 0:
            return "0 B"

        units = [
            ("TB", 1024**4),
            ("GB", 1024**3),
            ("MB", 1024**2),
            ("KB", 1024**1),
        ]

        for unit_name, unit_factor in units:
            if size_bytes >= unit_factor:
                value = size_bytes / unit_factor
                return f"{value:.2f} {unit_name}"

        return f"{size_bytes} B"
