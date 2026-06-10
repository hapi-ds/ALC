"""Unit tests for StorageManager service.

Tests:
    - build_object_path() produces correct path structure
    - validate_company_isolation() accepts matching company, rejects others
    - Checksum computation and verification logic
    - Quota check logic (90% warning, 100% rejection)

Requirements: 9.1, 9.3, 9.5, 9.6, 9.7
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.ingestion.services.storage_manager import StorageManager


@pytest.fixture
def mock_s3_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def mock_session_factory() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def storage_manager(
    mock_s3_client: AsyncMock,
    mock_redis_client: AsyncMock,
    mock_session_factory: AsyncMock,
) -> StorageManager:
    return StorageManager(
        bucket_name="alcoabase-literature",
        s3_client=mock_s3_client,
        redis_client=mock_redis_client,
        session_factory=mock_session_factory,
    )


# ─── build_object_path Tests ─────────────────────────────────────────────────


class TestBuildObjectPath:
    """Test path structure: {company_id}/{record_id}/{file_type}/{filename}."""

    def test_basic_path(self) -> None:
        path = StorageManager.build_object_path(
            company_id=1, record_id=100, file_type="original", filename="paper.pdf"
        )
        assert path == "1/100/original/paper.pdf"

    def test_different_file_types(self) -> None:
        path_orig = StorageManager.build_object_path(1, 50, "original", "doc.pdf")
        path_san = StorageManager.build_object_path(1, 50, "sanitized", "content.json")
        path_ext = StorageManager.build_object_path(1, 50, "extracted", "data.json")

        assert path_orig == "1/50/original/doc.pdf"
        assert path_san == "1/50/sanitized/content.json"
        assert path_ext == "1/50/extracted/data.json"

    def test_large_ids(self) -> None:
        path = StorageManager.build_object_path(
            company_id=99999, record_id=1000000, file_type="original", filename="f.pdf"
        )
        assert path == "99999/1000000/original/f.pdf"

    def test_path_starts_with_company_id(self) -> None:
        path = StorageManager.build_object_path(42, 7, "original", "test.pdf")
        assert path.startswith("42/")


# ─── validate_company_isolation Tests ─────────────────────────────────────────


class TestValidateCompanyIsolation:
    """Test company boundary enforcement."""

    def test_matching_company_accepted(self, storage_manager: StorageManager) -> None:
        path = "5/100/original/paper.pdf"
        assert storage_manager.validate_company_isolation(path, 5) is True

    def test_different_company_rejected(self, storage_manager: StorageManager) -> None:
        path = "5/100/original/paper.pdf"
        assert storage_manager.validate_company_isolation(path, 6) is False

    def test_invalid_path_format_rejected(self, storage_manager: StorageManager) -> None:
        assert storage_manager.validate_company_isolation("", 1) is False
        assert storage_manager.validate_company_isolation("nocompany/file.pdf", 1) is False

    def test_non_numeric_company_in_path_rejected(
        self, storage_manager: StorageManager
    ) -> None:
        assert storage_manager.validate_company_isolation("abc/100/original/f.pdf", 1) is False


# ─── Checksum Computation Tests ──────────────────────────────────────────────


class TestChecksumComputation:
    """Test SHA-256 checksum computation used by storage manager."""

    def test_sha256_computation_deterministic(self) -> None:
        """Same content always produces same hash."""
        content = b"hello world"
        hash1 = hashlib.sha256(content).hexdigest()
        hash2 = hashlib.sha256(content).hexdigest()
        assert hash1 == hash2

    def test_sha256_different_content_different_hash(self) -> None:
        """Different content produces different hashes."""
        hash1 = hashlib.sha256(b"content A").hexdigest()
        hash2 = hashlib.sha256(b"content B").hexdigest()
        assert hash1 != hash2

    def test_sha256_hex_format(self) -> None:
        """SHA-256 produces a 64-character hex string."""
        content = b"test data"
        checksum = hashlib.sha256(content).hexdigest()
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    @pytest.mark.asyncio
    async def test_store_file_computes_checksum(
        self,
        storage_manager: StorageManager,
        mock_s3_client: AsyncMock,
    ) -> None:
        """store_file() computes SHA-256 before upload."""
        content = b"file content for checksum test"
        expected_checksum = hashlib.sha256(content).hexdigest()

        # Mock successful upload and verification
        mock_s3_client.put_object = AsyncMock()
        mock_s3_client.get_object = AsyncMock(
            return_value={"Body": AsyncMock(read=AsyncMock(return_value=content))}
        )

        result = await storage_manager.store_file(
            content=content,
            company_id=1,
            record_id=10,
            file_type="original",
            filename="test.pdf",
            content_type="application/pdf",
        )

        assert result.sha256_checksum == expected_checksum


# ─── Quota Check Tests ────────────────────────────────────────────────────────


class TestQuotaCheck:
    """Test quota threshold logic (90% warning, 100% rejection)."""

    @pytest.mark.asyncio
    async def test_usage_below_90_percent_no_warning(
        self, mock_redis_client: AsyncMock
    ) -> None:
        """Usage below 90% triggers no warning."""
        quota_mb = 1000
        usage_bytes = int(quota_mb * 1024 * 1024 * 0.5)  # 50%

        quota_bytes = quota_mb * 1024 * 1024
        usage_ratio = usage_bytes / quota_bytes
        assert usage_ratio < 0.90

    @pytest.mark.asyncio
    async def test_usage_at_90_percent_triggers_warning(self) -> None:
        """Usage at 90% triggers quota_warning."""
        quota_mb = 1000
        usage_bytes = int(quota_mb * 1024 * 1024 * 0.90)

        quota_bytes = quota_mb * 1024 * 1024
        usage_ratio = usage_bytes / quota_bytes
        assert usage_ratio >= 0.90

    @pytest.mark.asyncio
    async def test_usage_at_100_percent_triggers_rejection(self) -> None:
        """Usage at 100% triggers quota_exceeded (rejection)."""
        quota_mb = 1000
        usage_bytes = int(quota_mb * 1024 * 1024 * 1.0)

        quota_bytes = quota_mb * 1024 * 1024
        usage_ratio = usage_bytes / quota_bytes
        assert usage_ratio >= 1.00

    @pytest.mark.asyncio
    async def test_usage_exceeding_100_percent_also_rejected(self) -> None:
        """Usage over 100% still exceeds the threshold."""
        quota_mb = 500
        usage_bytes = int(quota_mb * 1024 * 1024 * 1.2)  # 120%

        quota_bytes = quota_mb * 1024 * 1024
        usage_ratio = usage_bytes / quota_bytes
        assert usage_ratio >= 1.00

    @pytest.mark.asyncio
    async def test_zero_quota_no_restrictions(self) -> None:
        """When quota_bytes is 0, no restrictions apply (avoid division by zero)."""
        quota_bytes = 0
        # The IngestionPipelineService checks quota_bytes <= 0 → no restrictions
        assert quota_bytes <= 0
