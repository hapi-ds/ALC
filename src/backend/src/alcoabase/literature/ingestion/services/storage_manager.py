"""Storage manager for MinIO operations in the literature ingestion pipeline.

Handles file upload with SHA-256 checksum verification, path construction
with company-level isolation, Redis-cached quota tracking, and retention
cleanup of expired original files.

References:
    - Requirements 4.4, 4.5, 4.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7,
      13.1, 13.2, 13.3
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from alcoabase.literature.ingestion.exceptions import ChecksumMismatchError

if TYPE_CHECKING:
    import redis.asyncio as redis
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StorageResult:
    """Result of a file storage operation.

    Attributes:
        object_path: Full MinIO object key.
        file_size_bytes: Size of the stored file.
        sha256_checksum: Hex-encoded SHA-256 hash.
        content_type: MIME type of the stored file.
        upload_timestamp: When the file was stored (UTC ISO 8601).
    """

    object_path: str
    file_size_bytes: int
    sha256_checksum: str
    content_type: str
    upload_timestamp: str


class StorageManager:
    """Manages MinIO operations for the literature object store.

    All paths are constructed as:
    {company_id}/{record_id}/{file_type}/{filename}

    Where file_type is one of: original, sanitized, extracted.

    Args:
        bucket_name: MinIO bucket (from ALC_LITERATURE_BUCKET env var).
        s3_client: aioboto3 S3 client for MinIO operations.
        redis_client: For quota caching (5-min TTL).
        session_factory: SQLAlchemy async session factory for DB queries.
    """

    _USAGE_CACHE_TTL_SECONDS: int = 300  # 5 minutes

    def __init__(
        self,
        bucket_name: str,
        s3_client: object,
        redis_client: "redis.Redis",
        session_factory: "async_sessionmaker",
    ) -> None:
        """Initialize storage manager.

        Args:
            bucket_name: MinIO bucket name for literature storage.
            s3_client: aioboto3 S3 client resource.
            redis_client: Redis async client for caching.
            session_factory: Async session factory for database queries.
        """
        self._bucket_name = bucket_name
        self._s3_client = s3_client
        self._redis_client = redis_client
        self._session_factory = session_factory

    @staticmethod
    def build_object_path(
        company_id: int,
        record_id: int,
        file_type: str,
        filename: str,
    ) -> str:
        """Construct the MinIO object path with company isolation.

        Args:
            company_id: Tenant scope.
            record_id: IngestionRecord ID.
            file_type: One of 'original', 'sanitized', 'extracted'.
            filename: File name with extension.

        Returns:
            Full object key string in the format
            ``{company_id}/{record_id}/{file_type}/{filename}``.
        """
        return f"{company_id}/{record_id}/{file_type}/{filename}"

    async def store_file(
        self,
        content: bytes,
        company_id: int,
        record_id: int,
        file_type: str,
        filename: str,
        content_type: str,
        retention_expiry_date: datetime | None = None,
    ) -> StorageResult:
        """Store a file in MinIO with checksum verification.

        Computes SHA-256 before upload, uploads to MinIO via aioboto3,
        then verifies the checksum post-upload. Attaches metadata tags
        for auditing and retention enforcement.

        On checksum mismatch, deletes the corrupted object and retries
        the upload once. If the retry also fails, raises
        ``ChecksumMismatchError``.

        Args:
            content: File bytes to store.
            company_id: Tenant scope (included in path and metadata).
            record_id: IngestionRecord ID.
            file_type: 'original', 'sanitized', or 'extracted'.
            filename: Target filename.
            content_type: MIME type.
            retention_expiry_date: When original file should be purged.

        Returns:
            StorageResult with path, size, checksum, and timestamp.

        Raises:
            ChecksumMismatchError: If post-upload verification fails
                after one retry attempt.
        """
        object_path = self.build_object_path(
            company_id, record_id, file_type, filename
        )
        sha256_checksum = hashlib.sha256(content).hexdigest()
        upload_timestamp = datetime.now(UTC).isoformat()

        metadata = {
            "company_id": str(company_id),
            "ingestion_record_id": str(record_id),
            "content_type": content_type,
            "sha256_checksum": sha256_checksum,
            "ingestion_timestamp": upload_timestamp,
            "retention_expiry_date": (
                retention_expiry_date.isoformat()
                if retention_expiry_date
                else ""
            ),
        }

        # Attempt upload with one retry on checksum mismatch
        for attempt in range(2):
            await self._upload_object(
                object_path=object_path,
                content=content,
                content_type=content_type,
                metadata=metadata,
            )

            # Verify checksum post-upload
            verified = await self._verify_checksum(object_path, sha256_checksum)
            if verified:
                # Invalidate usage cache on successful upload
                await self._invalidate_usage_cache(company_id)

                return StorageResult(
                    object_path=object_path,
                    file_size_bytes=len(content),
                    sha256_checksum=sha256_checksum,
                    content_type=content_type,
                    upload_timestamp=upload_timestamp,
                )

            # Checksum mismatch — delete corrupted object
            logger.warning(
                "Checksum mismatch for object %s (attempt %d), "
                "deleting corrupted object",
                object_path,
                attempt + 1,
            )
            await self.delete_object(object_path)

            if attempt == 0:
                # Will retry on next iteration
                continue

        # Both attempts failed
        raise ChecksumMismatchError(
            "SHA-256 checksum mismatch detected after upload and retry.",
            company_id=company_id,
            record_id=record_id,
            expected_checksum=sha256_checksum,
            actual_checksum="<verification failed>",
        )

    def validate_company_isolation(
        self,
        object_path: str,
        requesting_company_id: int,
    ) -> bool:
        """Validate that an object path belongs to the requesting company.

        Extracts the company_id from the first path segment and compares
        it against the requesting company.

        Args:
            object_path: MinIO object key.
            requesting_company_id: Company making the request.

        Returns:
            True if the path's company_id matches the requesting company.
        """
        try:
            path_company_id = int(object_path.split("/")[0])
        except (ValueError, IndexError):
            return False
        return path_company_id == requesting_company_id

    async def get_company_usage_bytes(self, company_id: int) -> int:
        """Get total storage usage for a company with Redis caching.

        Checks Redis cache first (key: ``storage:usage:{company_id}``,
        TTL: 300s). On cache miss, queries MinIO by listing objects
        under the company prefix and summing their sizes.

        Args:
            company_id: Tenant scope.

        Returns:
            Total bytes stored for this company.
        """
        cache_key = f"storage:usage:{company_id}"

        # Check Redis cache
        cached_value = await self._redis_client.get(cache_key)
        if cached_value is not None:
            return int(cached_value)

        # Cache miss — compute from MinIO
        total_bytes = 0
        prefix = f"{company_id}/"

        paginator = self._s3_client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(
            Bucket=self._bucket_name, Prefix=prefix
        ):
            for obj in page.get("Contents", []):
                total_bytes += obj.get("Size", 0)

        # Cache the result with TTL
        await self._redis_client.set(
            cache_key,
            str(total_bytes),
            ex=self._USAGE_CACHE_TTL_SECONDS,
        )

        return total_bytes

    async def delete_object(self, object_path: str) -> bool:
        """Delete an object from MinIO.

        Args:
            object_path: Full object key to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        try:
            await self._s3_client.delete_object(
                Bucket=self._bucket_name, Key=object_path
            )
            return True
        except Exception:
            logger.exception("Failed to delete object: %s", object_path)
            return False

    async def cleanup_expired_files(self, batch_size: int = 100) -> int:
        """Delete original files past their retention expiry.

        Queries the database for IngestionRecords with a
        ``retention_expiry_date`` in the past that have not yet been
        purged. Deletes the original file from MinIO, retains sanitized
        content, and updates the record.

        Processes up to ``batch_size`` records per invocation.

        Args:
            batch_size: Maximum records to process per run.

        Returns:
            Number of files successfully deleted.
        """
        from alcoabase.literature.ingestion.models.ingestion import (
            IngestionRecord,
        )

        now = datetime.now(UTC)
        deleted_count = 0

        async with self._session_factory() as session:
            # Find expired records that haven't been purged yet
            stmt = (
                select(IngestionRecord)
                .where(
                    IngestionRecord.retention_expiry_date <= now,
                    IngestionRecord.original_file_purged.is_(False),
                    IngestionRecord.storage_path.isnot(None),
                )
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            for record in records:
                # Delete original file from MinIO
                success = await self.delete_object(record.storage_path)
                if success:
                    # Update record to reflect purge
                    await session.execute(
                        update(IngestionRecord)
                        .where(IngestionRecord.id == record.id)
                        .values(
                            original_file_purged=True,
                            purge_timestamp=now,
                        )
                    )
                    deleted_count += 1

                    # Invalidate usage cache for the company
                    await self._invalidate_usage_cache(record.company_id)

                    logger.info(
                        "Purged expired file for record %d (company %d): %s",
                        record.id,
                        record.company_id,
                        record.storage_path,
                    )
                else:
                    logger.error(
                        "Failed to purge expired file for record %d: %s",
                        record.id,
                        record.storage_path,
                    )

            await session.commit()

        return deleted_count

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _upload_object(
        self,
        object_path: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        """Upload bytes to MinIO with metadata tags.

        Args:
            object_path: Target object key.
            content: File bytes.
            content_type: MIME type for Content-Type.
            metadata: Key-value metadata tags to attach.
        """
        await self._s3_client.put_object(
            Bucket=self._bucket_name,
            Key=object_path,
            Body=io.BytesIO(content),
            ContentType=content_type,
            ContentLength=len(content),
            Metadata=metadata,
        )

    async def _verify_checksum(
        self,
        object_path: str,
        expected_checksum: str,
    ) -> bool:
        """Verify SHA-256 checksum of an uploaded object.

        Downloads the object and recomputes its SHA-256 hash, comparing
        against the expected value.

        Args:
            object_path: Object key to verify.
            expected_checksum: Expected SHA-256 hex digest.

        Returns:
            True if checksums match, False otherwise.
        """
        try:
            response = await self._s3_client.get_object(
                Bucket=self._bucket_name, Key=object_path
            )
            body = await response["Body"].read()
            actual_checksum = hashlib.sha256(body).hexdigest()
            return actual_checksum == expected_checksum
        except Exception:
            logger.exception(
                "Failed to verify checksum for object: %s", object_path
            )
            return False

    async def _invalidate_usage_cache(self, company_id: int) -> None:
        """Invalidate the Redis usage cache for a company.

        Args:
            company_id: Company whose cache entry should be removed.
        """
        cache_key = f"storage:usage:{company_id}"
        await self._redis_client.delete(cache_key)
