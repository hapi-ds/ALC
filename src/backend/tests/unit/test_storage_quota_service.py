"""Unit tests for StorageQuotaService.

Tests the pure functions (compute_quota_status, format_bytes_human_readable)
and the async methods with mocked aioboto3 and Redis dependencies.

Requirements: 5.1–5.6, 6.1–6.6
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.storage_quota import (
    CompanyStorageUsage,
    StorageQuotaService,
)


class TestComputeQuotaStatus:
    """Tests for the compute_quota_status pure function."""

    def test_no_quota_returns_normal(self) -> None:
        """When quota_bytes is None, status is always normal."""
        assert StorageQuotaService.compute_quota_status(1000, None, None) == "normal"
        assert StorageQuotaService.compute_quota_status(0, None, 80) == "normal"
        assert StorageQuotaService.compute_quota_status(999999, None, 50) == "normal"

    def test_usage_exceeds_quota_returns_exceeded(self) -> None:
        """When usage > quota, status is quota_exceeded."""
        assert (
            StorageQuotaService.compute_quota_status(1001, 1000, 80)
            == "quota_exceeded"
        )
        assert (
            StorageQuotaService.compute_quota_status(2000, 1000, None)
            == "quota_exceeded"
        )

    def test_usage_at_quota_boundary_returns_normal_or_warning(self) -> None:
        """When usage == quota, status is NOT exceeded (≤ quota)."""
        # usage == quota, threshold 80% → usage > threshold → warning
        assert (
            StorageQuotaService.compute_quota_status(1000, 1000, 80)
            == "quota_warning"
        )
        # usage == quota, no threshold → normal
        assert StorageQuotaService.compute_quota_status(1000, 1000, None) == "normal"

    def test_usage_above_threshold_returns_warning(self) -> None:
        """When usage > threshold% × quota AND ≤ quota, status is quota_warning."""
        # 81% of 1000 = 810, usage 850 > 810 → warning
        assert (
            StorageQuotaService.compute_quota_status(850, 1000, 80)
            == "quota_warning"
        )
        # 50% of 2000 = 1000, usage 1500 > 1000 → warning
        assert (
            StorageQuotaService.compute_quota_status(1500, 2000, 50)
            == "quota_warning"
        )

    def test_usage_at_threshold_boundary_returns_normal(self) -> None:
        """When usage == threshold% × quota exactly, status is normal (≤ threshold)."""
        # 80% of 1000 = 800, usage 800 → normal (not > threshold)
        assert StorageQuotaService.compute_quota_status(800, 1000, 80) == "normal"

    def test_usage_below_threshold_returns_normal(self) -> None:
        """When usage ≤ threshold% × quota, status is normal."""
        assert StorageQuotaService.compute_quota_status(500, 1000, 80) == "normal"
        assert StorageQuotaService.compute_quota_status(0, 1000, 50) == "normal"

    def test_zero_usage_always_normal(self) -> None:
        """Zero usage is always normal regardless of quota/threshold."""
        assert StorageQuotaService.compute_quota_status(0, 1000, 80) == "normal"
        assert StorageQuotaService.compute_quota_status(0, None, None) == "normal"

    def test_no_threshold_with_quota_only_checks_exceeded(self) -> None:
        """When threshold is None but quota exists, only exceeded is possible."""
        # Below quota → normal
        assert StorageQuotaService.compute_quota_status(500, 1000, None) == "normal"
        # At quota → normal (not exceeded)
        assert StorageQuotaService.compute_quota_status(1000, 1000, None) == "normal"
        # Above quota → exceeded
        assert (
            StorageQuotaService.compute_quota_status(1001, 1000, None)
            == "quota_exceeded"
        )


class TestFormatBytesHumanReadable:
    """Tests for the format_bytes_human_readable static function."""

    def test_zero_bytes(self) -> None:
        """Zero bytes returns '0 B'."""
        assert StorageQuotaService.format_bytes_human_readable(0) == "0 B"

    def test_bytes_below_kb(self) -> None:
        """Values below 1 KB return raw bytes."""
        assert StorageQuotaService.format_bytes_human_readable(512) == "512 B"
        assert StorageQuotaService.format_bytes_human_readable(1) == "1 B"
        assert StorageQuotaService.format_bytes_human_readable(1023) == "1023 B"

    def test_kilobytes(self) -> None:
        """Values in KB range."""
        assert StorageQuotaService.format_bytes_human_readable(1024) == "1.00 KB"
        assert StorageQuotaService.format_bytes_human_readable(1536) == "1.50 KB"
        assert StorageQuotaService.format_bytes_human_readable(1024 * 500) == "500.00 KB"

    def test_megabytes(self) -> None:
        """Values in MB range."""
        assert StorageQuotaService.format_bytes_human_readable(1024**2) == "1.00 MB"
        assert StorageQuotaService.format_bytes_human_readable(int(1.5 * 1024**2)) == "1.50 MB"

    def test_gigabytes(self) -> None:
        """Values in GB range."""
        assert StorageQuotaService.format_bytes_human_readable(1024**3) == "1.00 GB"
        assert StorageQuotaService.format_bytes_human_readable(int(2.5 * 1024**3)) == "2.50 GB"

    def test_terabytes(self) -> None:
        """Values in TB range."""
        assert StorageQuotaService.format_bytes_human_readable(1024**4) == "1.00 TB"
        assert StorageQuotaService.format_bytes_human_readable(int(1.75 * 1024**4)) == "1.75 TB"

    def test_rounding_to_two_decimals(self) -> None:
        """Values are rounded to 2 decimal places."""
        # 1024 + 1 byte = 1.000976... KB → rounds to 1.00
        result = StorageQuotaService.format_bytes_human_readable(1025)
        assert result == "1.00 KB"

    def test_large_values(self) -> None:
        """Very large values use TB."""
        # 10 TB
        result = StorageQuotaService.format_bytes_human_readable(10 * 1024**4)
        assert result == "10.00 TB"


class TestGetUsagePerCompany:
    """Tests for get_usage_per_company with mocked dependencies."""

    @pytest.fixture
    def service(self) -> StorageQuotaService:
        """Create a StorageQuotaService instance."""
        with patch("alcoabase.services.storage_quota.get_settings") as mock_settings:
            settings = MagicMock()
            settings.minio_bucket = "alcoabase"
            settings.minio_endpoint = "localhost:9000"
            settings.minio_access_key = "test"
            settings.minio_secret_key = "test"
            settings.minio_use_ssl = False
            settings.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = settings
            return StorageQuotaService()

    @pytest.mark.asyncio
    async def test_returns_usage_for_multiple_companies(self, service: StorageQuotaService) -> None:
        """Returns usage data for all active companies."""
        # Mock companies
        company1 = MagicMock()
        company1.id = 1
        company1.slug = "acme"
        company1.display_name = "Acme Corp"
        company1.is_active = True

        company2 = MagicMock()
        company2.id = 2
        company2.slug = "globex"
        company2.display_name = "Globex Inc"
        company2.is_active = True

        # Mock session
        session = AsyncMock()
        companies_result = MagicMock()
        companies_result.scalars.return_value.all.return_value = [company1, company2]

        quotas_result = MagicMock()
        quotas_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[companies_result, quotas_result])

        # Mock MinIO response
        minio_usage = {"acme": 1024 * 1024, "globex": 2048 * 1024}

        with patch.object(service, "_fetch_usage_from_minio", return_value=minio_usage):
            with patch.object(service, "_set_cached_usage", new_callable=AsyncMock):
                result, is_stale = await service.get_usage_per_company(session)

        assert len(result) == 2
        assert not is_stale

        acme = next(u for u in result if u.company_id == 1)
        assert acme.usage_bytes == 1024 * 1024
        assert acme.human_readable == "1.00 MB"
        assert acme.quota_status == "normal"

        globex = next(u for u in result if u.company_id == 2)
        assert globex.usage_bytes == 2048 * 1024
        assert globex.human_readable == "2.00 MB"

    @pytest.mark.asyncio
    async def test_empty_bucket_returns_zero_usage(self, service: StorageQuotaService) -> None:
        """When bucket is empty, all companies show 0 usage."""
        company = MagicMock()
        company.id = 1
        company.slug = "acme"
        company.display_name = "Acme Corp"
        company.is_active = True

        session = AsyncMock()
        companies_result = MagicMock()
        companies_result.scalars.return_value.all.return_value = [company]
        quotas_result = MagicMock()
        quotas_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[companies_result, quotas_result])

        with patch.object(service, "_fetch_usage_from_minio", return_value={}):
            with patch.object(service, "_set_cached_usage", new_callable=AsyncMock):
                result, is_stale = await service.get_usage_per_company(session)

        assert len(result) == 1
        assert result[0].usage_bytes == 0
        assert result[0].human_readable == "0 B"
        assert not is_stale

    @pytest.mark.asyncio
    async def test_minio_timeout_returns_cached_data(self, service: StorageQuotaService) -> None:
        """When MinIO times out, returns cached data with staleness flag."""
        cached_data = [
            {
                "company_id": 1,
                "company_name": "Acme Corp",
                "usage_bytes": 5000,
                "human_readable": "4.88 KB",
                "quota_status": "normal",
                "quota_limit_bytes": None,
                "alert_threshold_pct": None,
            }
        ]

        with patch.object(
            service,
            "_fetch_usage_from_minio",
            side_effect=asyncio.TimeoutError(),
        ):
            with patch.object(
                service,
                "_get_cached_usage",
                return_value=(cached_data, 1000.0),
            ):
                session = AsyncMock()
                result, is_stale = await service.get_usage_per_company(session)

        assert is_stale is True
        assert len(result) == 1
        assert result[0].company_id == 1
        assert result[0].usage_bytes == 5000

    @pytest.mark.asyncio
    async def test_minio_timeout_no_cache_returns_empty(self, service: StorageQuotaService) -> None:
        """When MinIO times out and no cache exists, returns empty list."""
        with patch.object(
            service,
            "_fetch_usage_from_minio",
            side_effect=asyncio.TimeoutError(),
        ):
            with patch.object(
                service,
                "_get_cached_usage",
                return_value=(None, None),
            ):
                session = AsyncMock()
                result, is_stale = await service.get_usage_per_company(session)

        assert is_stale is True
        assert result == []

    @pytest.mark.asyncio
    async def test_quota_status_applied_per_company(self, service: StorageQuotaService) -> None:
        """Quota status is correctly computed for each company based on their quota config."""
        company1 = MagicMock()
        company1.id = 1
        company1.slug = "acme"
        company1.display_name = "Acme Corp"
        company1.is_active = True

        company2 = MagicMock()
        company2.id = 2
        company2.slug = "globex"
        company2.display_name = "Globex Inc"
        company2.is_active = True

        # Company 1 has a quota of 1 MB with 80% threshold, usage is 900 KB (above threshold)
        quota1 = MagicMock()
        quota1.company_id = 1
        quota1.quota_limit_bytes = 1024 * 1024  # 1 MB
        quota1.alert_threshold_pct = 80

        # Company 2 has a quota of 1 MB, usage exceeds it
        quota2 = MagicMock()
        quota2.company_id = 2
        quota2.quota_limit_bytes = 1024 * 1024  # 1 MB
        quota2.alert_threshold_pct = 90

        session = AsyncMock()
        companies_result = MagicMock()
        companies_result.scalars.return_value.all.return_value = [company1, company2]

        quotas_result = MagicMock()
        quotas_result.scalars.return_value.all.return_value = [quota1, quota2]

        session.execute = AsyncMock(side_effect=[companies_result, quotas_result])

        # acme: 900 KB (above 80% of 1 MB = 819 KB) → warning
        # globex: 2 MB (above 1 MB quota) → exceeded
        minio_usage = {"acme": 900 * 1024, "globex": 2 * 1024 * 1024}

        with patch.object(service, "_fetch_usage_from_minio", return_value=minio_usage):
            with patch.object(service, "_set_cached_usage", new_callable=AsyncMock):
                result, is_stale = await service.get_usage_per_company(session)

        assert len(result) == 2
        acme = next(u for u in result if u.company_id == 1)
        assert acme.quota_status == "quota_warning"
        assert acme.quota_limit_bytes == 1024 * 1024
        assert acme.alert_threshold_pct == 80

        globex = next(u for u in result if u.company_id == 2)
        assert globex.quota_status == "quota_exceeded"


class TestSetQuota:
    """Tests for set_quota upsert behavior."""

    @pytest.fixture
    def service(self) -> StorageQuotaService:
        """Create a StorageQuotaService instance."""
        with patch("alcoabase.services.storage_quota.get_settings") as mock_settings:
            settings = MagicMock()
            settings.minio_bucket = "alcoabase"
            settings.minio_endpoint = "localhost:9000"
            settings.minio_access_key = "test"
            settings.minio_secret_key = "test"
            settings.minio_use_ssl = False
            settings.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = settings
            return StorageQuotaService()

    @pytest.mark.asyncio
    async def test_creates_new_quota_when_none_exists(self, service: StorageQuotaService) -> None:
        """Creates a new StorageQuota record when company has no quota."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.set_quota(1, 1024 * 1024 * 1024, session)

        session.add.assert_called_once()
        assert result.quota_limit_bytes == 1024 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_updates_existing_quota(self, service: StorageQuotaService) -> None:
        """Updates existing StorageQuota record."""
        existing_quota = MagicMock()
        existing_quota.company_id = 1
        existing_quota.quota_limit_bytes = 500

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing_quota
        session.execute = AsyncMock(return_value=result_mock)
        session.flush = AsyncMock()

        result = await service.set_quota(1, 1000, session)

        assert result.quota_limit_bytes == 1000


class TestSetAlertThreshold:
    """Tests for set_alert_threshold validation and upsert."""

    @pytest.fixture
    def service(self) -> StorageQuotaService:
        """Create a StorageQuotaService instance."""
        with patch("alcoabase.services.storage_quota.get_settings") as mock_settings:
            settings = MagicMock()
            settings.minio_bucket = "alcoabase"
            settings.minio_endpoint = "localhost:9000"
            settings.minio_access_key = "test"
            settings.minio_secret_key = "test"
            settings.minio_use_ssl = False
            settings.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = settings
            return StorageQuotaService()

    @pytest.mark.asyncio
    async def test_rejects_threshold_below_1(self, service: StorageQuotaService) -> None:
        """Threshold below 1 raises ValueError."""
        session = AsyncMock()
        with pytest.raises(ValueError, match="between 1 and 99"):
            await service.set_alert_threshold(1, 0, session)

    @pytest.mark.asyncio
    async def test_rejects_threshold_above_99(self, service: StorageQuotaService) -> None:
        """Threshold above 99 raises ValueError."""
        session = AsyncMock()
        with pytest.raises(ValueError, match="between 1 and 99"):
            await service.set_alert_threshold(1, 100, session)

    @pytest.mark.asyncio
    async def test_accepts_valid_threshold(self, service: StorageQuotaService) -> None:
        """Valid threshold (1-99) is accepted and stored."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.set_alert_threshold(1, 80, session)

        session.add.assert_called_once()
        assert result.alert_threshold_pct == 80

    @pytest.mark.asyncio
    async def test_accepts_boundary_values(self, service: StorageQuotaService) -> None:
        """Boundary values 1 and 99 are accepted."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Test lower boundary
        result = await service.set_alert_threshold(1, 1, session)
        assert result.alert_threshold_pct == 1

        # Reset mock for upper boundary
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()

        result = await service.set_alert_threshold(1, 99, session)
        assert result.alert_threshold_pct == 99

    @pytest.mark.asyncio
    async def test_updates_existing_threshold(self, service: StorageQuotaService) -> None:
        """Updates existing StorageQuota record's alert threshold."""
        existing_quota = MagicMock()
        existing_quota.company_id = 1
        existing_quota.alert_threshold_pct = 50

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing_quota
        session.execute = AsyncMock(return_value=result_mock)
        session.flush = AsyncMock()

        result = await service.set_alert_threshold(1, 80, session)

        assert result.alert_threshold_pct == 80
        # Should not call session.add for existing record
        session.add.assert_not_called()


class TestGetTotalUsage:
    """Tests for get_total_usage aggregation."""

    @pytest.fixture
    def service(self) -> StorageQuotaService:
        """Create a StorageQuotaService instance."""
        with patch("alcoabase.services.storage_quota.get_settings") as mock_settings:
            settings = MagicMock()
            settings.minio_bucket = "alcoabase"
            settings.minio_endpoint = "localhost:9000"
            settings.minio_access_key = "test"
            settings.minio_secret_key = "test"
            settings.minio_use_ssl = False
            settings.redis_url = "redis://localhost:6379/0"
            mock_settings.return_value = settings
            return StorageQuotaService()

    @pytest.mark.asyncio
    async def test_aggregates_all_company_usage(self, service: StorageQuotaService) -> None:
        """Total usage sums all company usage bytes."""
        usage_list = [
            CompanyStorageUsage(
                company_id=1,
                company_name="A",
                usage_bytes=1000,
                human_readable="1000 B",
                quota_status="normal",
            ),
            CompanyStorageUsage(
                company_id=2,
                company_name="B",
                usage_bytes=2000,
                human_readable="1.95 KB",
                quota_status="normal",
            ),
        ]

        with patch.object(
            service, "get_usage_per_company", return_value=(usage_list, False)
        ):
            with patch.object(
                service, "_get_minio_capacity", return_value=500 * 1024**3
            ):
                session = AsyncMock()
                result = await service.get_total_usage(session)

        assert result.total_used_bytes == 3000
        assert result.total_capacity_bytes == 500 * 1024**3
        assert result.is_stale is False

    @pytest.mark.asyncio
    async def test_stale_flag_propagated_from_usage(self, service: StorageQuotaService) -> None:
        """When usage data is stale (from cache), total usage reflects staleness."""
        usage_list = [
            CompanyStorageUsage(
                company_id=1,
                company_name="A",
                usage_bytes=500,
                human_readable="500 B",
                quota_status="normal",
            ),
        ]

        with patch.object(
            service, "get_usage_per_company", return_value=(usage_list, True)
        ):
            with patch.object(
                service, "_get_minio_capacity", return_value=100 * 1024**3
            ):
                session = AsyncMock()
                result = await service.get_total_usage(session)

        assert result.total_used_bytes == 500
        assert result.is_stale is True

    @pytest.mark.asyncio
    async def test_empty_usage_returns_zero_total(self, service: StorageQuotaService) -> None:
        """When no companies have usage, total is zero."""
        with patch.object(
            service, "get_usage_per_company", return_value=([], False)
        ):
            with patch.object(
                service, "_get_minio_capacity", return_value=500 * 1024**3
            ):
                session = AsyncMock()
                result = await service.get_total_usage(session)

        assert result.total_used_bytes == 0
        assert result.human_readable_used == "0 B"
        assert result.total_capacity_bytes == 500 * 1024**3

    @pytest.mark.asyncio
    async def test_human_readable_fields_populated(self, service: StorageQuotaService) -> None:
        """Total usage includes human-readable formatted strings."""
        usage_list = [
            CompanyStorageUsage(
                company_id=1,
                company_name="A",
                usage_bytes=5 * 1024**3,  # 5 GB
                human_readable="5.00 GB",
                quota_status="normal",
            ),
        ]

        with patch.object(
            service, "get_usage_per_company", return_value=(usage_list, False)
        ):
            with patch.object(
                service, "_get_minio_capacity", return_value=500 * 1024**3
            ):
                session = AsyncMock()
                result = await service.get_total_usage(session)

        assert result.human_readable_used == "5.00 GB"
        assert result.human_readable_capacity == "500.00 GB"
        assert result.last_updated is not None
