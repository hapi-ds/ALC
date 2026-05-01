"""Storage service wrapping MinIO (S3-compatible) via aioboto3.

Provides async file upload, download, and delete operations against
the configured MinIO bucket. Creates the bucket on first use if it
does not already exist.

References:
    - Design doc Section 3: Document Service
    - Requirements 1.5, 1.6: File storage in MinIO_Store
"""

from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from alcoabase.config import get_settings


class StorageService:
    """Async S3-compatible storage service backed by MinIO.

    Wraps aioboto3 to provide upload, download, and delete operations.
    Automatically creates the configured bucket on first use.

    Attributes:
        _session: The aioboto3 session for creating S3 clients.
        _bucket: The target bucket name from settings.
        _bucket_ensured: Whether the bucket has been verified/created.
    """

    def __init__(self) -> None:
        """Initialize the storage service with settings from environment."""
        settings = get_settings()
        self._session = aioboto3.Session()
        self._bucket = settings.minio_bucket
        self._endpoint_url = self._build_endpoint_url(settings)
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._use_ssl = settings.minio_use_ssl
        self._bucket_ensured = False

    @staticmethod
    def _build_endpoint_url(settings: Any) -> str:
        """Build the endpoint URL from settings.

        Args:
            settings: Application settings instance.

        Returns:
            Full endpoint URL with protocol prefix.
        """
        protocol = "https" if settings.minio_use_ssl else "http"
        return f"{protocol}://{settings.minio_endpoint}"

    def _client_kwargs(self) -> dict[str, Any]:
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

    async def _ensure_bucket(self, client: Any) -> None:
        """Create the bucket if it doesn't exist (idempotent).

        Args:
            client: An active aioboto3 S3 client.
        """
        if self._bucket_ensured:
            return

        try:
            await client.head_bucket(Bucket=self._bucket)
        except ClientError:
            await client.create_bucket(Bucket=self._bucket)

        self._bucket_ensured = True

    async def upload_file(
        self, key: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """Upload a file to MinIO.

        Args:
            key: The object key (path) in the bucket.
            data: The file content as bytes.
            content_type: MIME type of the file.

        Returns:
            The object key that was stored.

        Raises:
            ClientError: If the upload fails due to connectivity or permissions.
        """
        async with self._session.client(**self._client_kwargs()) as client:
            await self._ensure_bucket(client)
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        return key

    async def download_file(self, key: str) -> bytes:
        """Download a file from MinIO.

        Args:
            key: The object key (path) in the bucket.

        Returns:
            The file content as bytes.

        Raises:
            ClientError: If the file does not exist or download fails.
        """
        async with self._session.client(**self._client_kwargs()) as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            async with response["Body"] as stream:
                return await stream.read()

    async def delete_file(self, key: str) -> None:
        """Delete a file from MinIO.

        Args:
            key: The object key (path) in the bucket.

        Raises:
            ClientError: If the deletion fails.
        """
        async with self._session.client(**self._client_kwargs()) as client:
            await client.delete_object(Bucket=self._bucket, Key=key)
