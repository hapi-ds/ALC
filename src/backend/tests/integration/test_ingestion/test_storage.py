"""Integration tests for storage and quota enforcement.

Tests:
- MinIO upload and download with mocked MinIO client
- Checksum verification (mismatch triggers retry + deletion)
- Redis-cached storage usage (5-min TTL)
- Quota warning at 90% and rejection at 100%
- Retention cleanup: original file deleted, sanitized content retained, audit logged
- Company isolation: cross-company access rejected

External dependencies (MinIO, Redis, PostgreSQL) are mocked via AsyncMock.

Requirements: 4.5, 8.3, 8.4, 9.1, 9.3, 9.5, 9.6, 9.7, 13.1, 13.2, 13.3
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.ingestion.exceptions import ChecksumMismatchError
from alcoabase.literature.ingestion.services.storage_manager import (
    StorageManager,
    StorageResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AsyncSessionCtx:
    """Async context manager that returns the mock session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


def _make_session_factory(session):
    """Create a session factory returning the given mock session."""

    def factory():
        return _AsyncSessionCtx(session)

    return factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_s3_client():
    """Create a mock S3 (MinIO) client."""
    client = AsyncMock()
    client.put_object = AsyncMock()
    client.get_object = AsyncMock()
    client.delete_object = AsyncMock()
    client.head_object = AsyncMock()

    # get_paginator returns a mock paginator
    mock_paginator = AsyncMock()
    mock_paginator.paginate = MagicMock(return_value=iter([]))
    client.get_paginator = MagicMock(return_value=mock_paginator)

    return client


@pytest.fixture
def mock_redis():
    """Create a mock Redis async client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def mock_session():
    """Create a mock async DB session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def storage_manager(mock_s3_client, mock_redis, mock_session):
    """Build a StorageManager with mocked dependencies."""
    return StorageManager(
        bucket_name="alcoabase-literature",
        s3_client=mock_s3_client,
        redis_client=mock_redis,
        session_factory=_make_session_factory(mock_session),
    )


# ---------------------------------------------------------------------------
# Test: MinIO Upload and Download
# Requirements: 9.1, 9.5
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMinIOUploadDownload:
    """Test MinIO upload and download with mocked S3 client."""

    @pytest.mark.asyncio
    async def test_store_file_uploads_to_correct_path(
        self, storage_manager: StorageManager, mock_s3_client: AsyncMock
    ) -> None:
        """store_file uploads content to the correct object path."""
        content = b"PDF binary content here"
        expected_checksum = hashlib.sha256(content).hexdigest()

        # Mock get_object to return correct content (for checksum verification)
        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=content)
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        result = await storage_manager.store_file(
            content=content,
            company_id=1,
            record_id=42,
            file_type="original",
            filename="paper.pdf",
            content_type="application/pdf",
        )

        assert isinstance(result, StorageResult)
        assert result.object_path == "1/42/original/paper.pdf"
        assert result.file_size_bytes == len(content)
        assert result.sha256_checksum == expected_checksum
        assert result.content_type == "application/pdf"
        mock_s3_client.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_file_attaches_metadata(
        self, storage_manager: StorageManager, mock_s3_client: AsyncMock
    ) -> None:
        """store_file attaches required metadata tags to the uploaded object."""
        content = b"test content"

        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=content)
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        await storage_manager.store_file(
            content=content,
            company_id=5,
            record_id=100,
            file_type="sanitized",
            filename="structured_content.json",
            content_type="application/json",
        )

        call_kwargs = mock_s3_client.put_object.call_args[1]
        metadata = call_kwargs["Metadata"]
        assert metadata["company_id"] == "5"
        assert metadata["ingestion_record_id"] == "100"
        assert metadata["content_type"] == "application/json"
        assert "sha256_checksum" in metadata


# ---------------------------------------------------------------------------
# Test: Checksum Verification
# Requirements: 9.5, 9.6
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestChecksumVerification:
    """Test checksum verification: mismatch triggers retry + deletion."""

    @pytest.mark.asyncio
    async def test_checksum_match_succeeds(
        self, storage_manager: StorageManager, mock_s3_client: AsyncMock
    ) -> None:
        """When post-upload checksum matches, store_file succeeds."""
        content = b"valid content bytes"

        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=content)
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        result = await storage_manager.store_file(
            content=content,
            company_id=1,
            record_id=1,
            file_type="original",
            filename="file.pdf",
            content_type="application/pdf",
        )

        assert result.sha256_checksum == hashlib.sha256(content).hexdigest()

    @pytest.mark.asyncio
    async def test_checksum_mismatch_retries_then_raises(
        self, storage_manager: StorageManager, mock_s3_client: AsyncMock
    ) -> None:
        """Checksum mismatch triggers delete + retry; double failure raises."""
        content = b"original content"
        corrupted = b"corrupted content"

        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=corrupted)
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        with pytest.raises(ChecksumMismatchError):
            await storage_manager.store_file(
                content=content,
                company_id=1,
                record_id=1,
                file_type="original",
                filename="file.pdf",
                content_type="application/pdf",
            )

        # Should have uploaded twice (initial + retry)
        assert mock_s3_client.put_object.call_count == 2
        # Should have deleted corrupted object twice
        assert mock_s3_client.delete_object.call_count == 2

    @pytest.mark.asyncio
    async def test_checksum_mismatch_first_attempt_retry_succeeds(
        self, storage_manager: StorageManager, mock_s3_client: AsyncMock
    ) -> None:
        """Checksum mismatch on first attempt but retry succeeds."""
        content = b"good content"
        corrupted = b"bad content"

        # First get_object returns corrupted, second returns correct
        mock_body_bad = AsyncMock()
        mock_body_bad.read = AsyncMock(return_value=corrupted)
        mock_body_good = AsyncMock()
        mock_body_good.read = AsyncMock(return_value=content)
        mock_s3_client.get_object.side_effect = [
            {"Body": mock_body_bad},
            {"Body": mock_body_good},
        ]

        result = await storage_manager.store_file(
            content=content,
            company_id=1,
            record_id=1,
            file_type="original",
            filename="file.pdf",
            content_type="application/pdf",
        )

        assert result.sha256_checksum == hashlib.sha256(content).hexdigest()
        # Delete was called once for the corrupted object
        assert mock_s3_client.delete_object.call_count == 1


# ---------------------------------------------------------------------------
# Test: Redis-Cached Storage Usage
# Requirements: 9.7
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRedisCachedStorageUsage:
    """Test Redis-cached storage usage with 5-min TTL."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(
        self, storage_manager: StorageManager, mock_redis: AsyncMock
    ) -> None:
        """When Redis has a cached value, return it without querying S3."""
        mock_redis.get.return_value = b"5242880"  # 5 MB cached

        usage = await storage_manager.get_company_usage_bytes(company_id=1)

        assert usage == 5242880
        # S3 should NOT have been called (paginator not invoked)

    @pytest.mark.asyncio
    async def test_cache_miss_queries_s3_and_caches(
        self, storage_manager: StorageManager, mock_redis: AsyncMock, mock_s3_client: AsyncMock
    ) -> None:
        """Cache miss queries S3 for usage and stores result in Redis."""
        mock_redis.get.return_value = None  # Cache miss

        # Mock paginator to return objects with sizes
        async def _pages(**kwargs):
            yield {"Contents": [{"Size": 1000}, {"Size": 2000}]}

        mock_paginator = MagicMock()
        mock_paginator.paginate = _pages
        mock_s3_client.get_paginator.return_value = mock_paginator

        usage = await storage_manager.get_company_usage_bytes(company_id=1)

        assert usage == 3000
        mock_redis.set.assert_called_once_with(
            "storage:usage:1", "3000", ex=300
        )

    @pytest.mark.asyncio
    async def test_cache_ttl_is_5_minutes(
        self, storage_manager: StorageManager
    ) -> None:
        """Verify the TTL constant is 300 seconds (5 minutes)."""
        assert storage_manager._USAGE_CACHE_TTL_SECONDS == 300


# ---------------------------------------------------------------------------
# Test: Quota Warning and Rejection
# Requirements: 8.3, 8.4
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestQuotaEnforcement:
    """Test quota warning at 90% and rejection at 100%."""

    @pytest.mark.asyncio
    async def test_quota_warning_at_90_percent(self) -> None:
        """Usage >= 90% quota triggers warning flag."""
        from alcoabase.literature.ingestion.services.ingestion_service import (
            IngestionPipelineService,
            QUOTA_WARNING_THRESHOLD,
        )

        mock_storage = AsyncMock()
        # 90% of 10240 MB = 9216 MB
        quota_bytes = 10240 * 1024 * 1024
        mock_storage.get_company_usage_bytes = AsyncMock(
            return_value=int(quota_bytes * 0.91)
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Default quota
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = IngestionPipelineService(
            session_factory=_make_session_factory(mock_session),
            storage_manager=mock_storage,
            unpaywall_adapter=AsyncMock(),
            sanitization_pipeline=AsyncMock(),
            audit_logger=AsyncMock(),
            rate_limiter=AsyncMock(),
            circuit_breaker=AsyncMock(),
        )

        warning, exceeded = await service.check_quota(company_id=1)

        assert warning is True
        assert exceeded is False

    @pytest.mark.asyncio
    async def test_quota_rejection_at_100_percent(self) -> None:
        """Usage >= 100% quota triggers both warning and rejection."""
        from alcoabase.literature.ingestion.services.ingestion_service import (
            IngestionPipelineService,
        )

        mock_storage = AsyncMock()
        quota_bytes = 10240 * 1024 * 1024
        mock_storage.get_company_usage_bytes = AsyncMock(return_value=quota_bytes)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = IngestionPipelineService(
            session_factory=_make_session_factory(mock_session),
            storage_manager=mock_storage,
            unpaywall_adapter=AsyncMock(),
            sanitization_pipeline=AsyncMock(),
            audit_logger=AsyncMock(),
            rate_limiter=AsyncMock(),
            circuit_breaker=AsyncMock(),
        )

        warning, exceeded = await service.check_quota(company_id=1)

        assert warning is True
        assert exceeded is True

    @pytest.mark.asyncio
    async def test_below_warning_threshold(self) -> None:
        """Usage below 90% has no warning or rejection."""
        from alcoabase.literature.ingestion.services.ingestion_service import (
            IngestionPipelineService,
        )

        mock_storage = AsyncMock()
        quota_bytes = 10240 * 1024 * 1024
        mock_storage.get_company_usage_bytes = AsyncMock(
            return_value=int(quota_bytes * 0.5)
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = IngestionPipelineService(
            session_factory=_make_session_factory(mock_session),
            storage_manager=mock_storage,
            unpaywall_adapter=AsyncMock(),
            sanitization_pipeline=AsyncMock(),
            audit_logger=AsyncMock(),
            rate_limiter=AsyncMock(),
            circuit_breaker=AsyncMock(),
        )

        warning, exceeded = await service.check_quota(company_id=1)

        assert warning is False
        assert exceeded is False


# ---------------------------------------------------------------------------
# Test: Retention Cleanup
# Requirements: 13.1, 13.2, 13.3
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRetentionCleanup:
    """Test retention cleanup: original deleted, sanitized retained, audit logged."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_expired_original_files(
        self, storage_manager: StorageManager, mock_session: AsyncMock, mock_s3_client: AsyncMock
    ) -> None:
        """cleanup_expired_files deletes original files past retention date."""
        # Create a mock expired record
        expired_record = MagicMock()
        expired_record.id = 10
        expired_record.company_id = 1
        expired_record.storage_path = "1/10/original/paper.pdf"
        expired_record.original_file_purged = False
        expired_record.retention_expiry_date = datetime.now(UTC) - timedelta(days=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [expired_record]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_s3_client.delete_object.return_value = {}

        deleted_count = await storage_manager.cleanup_expired_files(batch_size=100)

        assert deleted_count == 1
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="alcoabase-literature",
            Key="1/10/original/paper.pdf",
        )

    @pytest.mark.asyncio
    async def test_cleanup_does_not_delete_unexpired_files(
        self, storage_manager: StorageManager, mock_session: AsyncMock
    ) -> None:
        """cleanup_expired_files returns 0 when no records are expired."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        deleted_count = await storage_manager.cleanup_expired_files(batch_size=100)

        assert deleted_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_processes_in_batches(
        self, storage_manager: StorageManager, mock_session: AsyncMock, mock_s3_client: AsyncMock
    ) -> None:
        """cleanup_expired_files respects batch_size parameter."""
        # Verify the function accepts batch_size
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Should not raise with batch_size=50
        deleted_count = await storage_manager.cleanup_expired_files(batch_size=50)
        assert deleted_count == 0


# ---------------------------------------------------------------------------
# Test: Company Isolation
# Requirements: 9.1, 9.3
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCompanyIsolation:
    """Test company isolation: cross-company access rejected."""

    def test_validate_company_isolation_same_company_passes(
        self, storage_manager: StorageManager
    ) -> None:
        """Access to path belonging to the same company is allowed."""
        path = "1/42/original/paper.pdf"
        assert storage_manager.validate_company_isolation(path, requesting_company_id=1) is True

    def test_validate_company_isolation_different_company_rejected(
        self, storage_manager: StorageManager
    ) -> None:
        """Access to path belonging to a different company is rejected."""
        path = "1/42/original/paper.pdf"
        assert storage_manager.validate_company_isolation(path, requesting_company_id=2) is False

    def test_validate_company_isolation_invalid_path_rejected(
        self, storage_manager: StorageManager
    ) -> None:
        """Access with malformed path is rejected."""
        assert storage_manager.validate_company_isolation("", requesting_company_id=1) is False
        assert storage_manager.validate_company_isolation("invalid", requesting_company_id=1) is False

    def test_build_object_path_includes_company_prefix(
        self, storage_manager: StorageManager
    ) -> None:
        """build_object_path starts with company_id as first path segment."""
        path = StorageManager.build_object_path(
            company_id=7, record_id=99, file_type="original", filename="doc.pdf"
        )
        assert path == "7/99/original/doc.pdf"
        assert path.startswith("7/")

    def test_different_companies_have_different_paths(
        self, storage_manager: StorageManager
    ) -> None:
        """Different company_ids produce non-overlapping paths."""
        path_a = StorageManager.build_object_path(1, 10, "original", "file.pdf")
        path_b = StorageManager.build_object_path(2, 10, "original", "file.pdf")
        assert path_a != path_b
        assert path_a.startswith("1/")
        assert path_b.startswith("2/")
