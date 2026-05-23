"""Document service for CRUD operations, versioning, and search.

Provides document lifecycle management including creation with UUID
generation, version management (major/minor), retrieval, and search
with pagination. Supports video file uploads with ffprobe metadata
extraction.

References:
    - Design doc Section 3: Document Service
    - Requirements 1, 2: Document creation, versioning, retrieval, search
    - Requirements 4.1-4.7: Video file upload and storage
"""

import asyncio
import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.config import get_settings
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.video import VideoMetadata
from alcoabase.services.storage_service import StorageService
from alcoabase.services.uuid_service import UUIDService

logger = logging.getLogger(__name__)

# Supported video content types (Requirement 4.1)
VIDEO_CONTENT_TYPES: set[str] = {
    "video/mp4",
    "video/x-msvideo",
    "video/quicktime",
    "video/webm",
}


class DocumentService:
    """Service for document CRUD operations, versioning, and search.

    Coordinates between PostgreSQL (metadata), MinIO (file storage),
    and the UUID service to provide transactional document management.

    Attributes:
        _storage: StorageService instance for MinIO operations.
        _uuid_service: UUIDService instance for Document-UUID generation.
    """

    def __init__(
        self,
        storage_service: StorageService | None = None,
        uuid_service: UUIDService | None = None,
    ) -> None:
        """Initialize the document service.

        Args:
            storage_service: Optional StorageService instance (creates default if None).
            uuid_service: Optional UUIDService instance (creates default if None).
        """
        self._storage = storage_service or StorageService()
        self._uuid_service = uuid_service or UUIDService()

    async def create_document(
        self,
        session: AsyncSession,
        file_data: bytes,
        title: str,
        folder_path: str,
        document_type: str,
        tags: list[str],
        user_id: int,
        content_type: str = "application/octet-stream",
        company_id: int | None = None,
    ) -> Document:
        """Create a new document with UUID, store file, and persist metadata.

        Generates a Document-UUID, uploads the file to MinIO, and persists
        metadata in PostgreSQL within a single logical transaction. If the
        MinIO upload fails, no partial metadata record is created.

        Args:
            session: Active async database session.
            file_data: The file content as bytes.
            title: Document title.
            folder_path: Logical folder path for organization.
            document_type: Classification type (SOP, Report, Template, etc.).
            tags: List of classification tags.
            user_id: ID of the creating user.
            content_type: MIME type of the file.

        Returns:
            The created Document instance with tags and initial version.

        Raises:
            Exception: If MinIO upload fails (no partial DB record created).
        """
        # Generate Document-UUID
        document_uuid = await self._uuid_service.generate_document_uuid(session)

        # Compute file hash
        file_hash = hashlib.sha512(file_data).hexdigest()

        # Build storage key: documents/{uuid}/1.0/{filename}
        storage_key = f"documents/{document_uuid}/1.0/document"

        # Upload to MinIO first — if this fails, we don't create DB records
        await self._storage.upload_file(storage_key, file_data, content_type)

        try:
            # Create document record
            document = Document(
                document_uuid=document_uuid,
                title=title,
                folder_path=folder_path,
                document_type=document_type,
                current_status="Draft",
                created_by=user_id,
                company_id=company_id,
            )
            session.add(document)
            await session.flush()

            # Create tags
            for tag_name in tags:
                tag = DocumentTag(document_id=document.id, tag=tag_name)
                session.add(tag)

            # Create initial version (1.0)
            version = DocumentVersion(
                document_id=document.id,
                major_version=1,
                minor_version=0,
                storage_key=storage_key,
                file_hash=file_hash,
                uploaded_by=user_id,
                change_reason="Initial version",
            )
            session.add(version)
            await session.flush()

            return document

        except Exception:
            # Rollback MinIO upload on DB failure
            try:
                await self._storage.delete_file(storage_key)
            except Exception:
                pass  # Best-effort cleanup
            raise

    def _is_video_content_type(self, content_type: str) -> bool:
        """Check if the content type is a supported video format.

        Args:
            content_type: MIME type to check.

        Returns:
            True if the content type is a supported video format.
        """
        return content_type in VIDEO_CONTENT_TYPES

    def _validate_video_upload(
        self, file_data: bytes, content_type: str
    ) -> str | None:
        """Validate video file size and content type.

        Args:
            file_data: The uploaded file bytes.
            content_type: MIME type of the uploaded file.

        Returns:
            Error message string if validation fails, None if valid.
        """
        settings = get_settings()

        if content_type not in VIDEO_CONTENT_TYPES:
            supported = ", ".join(sorted(VIDEO_CONTENT_TYPES))
            return (
                f"Unsupported video content type: '{content_type}'. "
                f"Supported types: {supported}"
            )

        file_size = len(file_data)
        if file_size == 0:
            return "Video file size must be greater than 0 bytes."

        if file_size > settings.video_max_file_size_bytes:
            max_gb = settings.video_max_file_size_bytes / (1024 * 1024 * 1024)
            return (
                f"Video file size ({file_size} bytes) exceeds maximum "
                f"allowed size ({max_gb:.1f} GB)."
            )

        return None

    async def _extract_video_metadata(
        self, file_data: bytes
    ) -> dict[str, Any]:
        """Extract video metadata using ffprobe with a 30-second timeout.

        Writes file data to a temporary file, runs ffprobe, and parses
        the JSON output to extract duration, resolution, frame count,
        and codec information.

        Args:
            file_data: The video file bytes.

        Returns:
            Dictionary with keys: duration_seconds, resolution_width,
            resolution_height, frame_count, codec. Values are None if
            extraction fails.
        """
        import tempfile
        import os

        settings = get_settings()
        null_metadata: dict[str, Any] = {
            "duration_seconds": None,
            "resolution_width": None,
            "resolution_height": None,
            "frame_count": None,
            "codec": None,
        }

        # Write to temp file for ffprobe to read
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".video"
            ) as tmp:
                tmp.write(file_data)
                tmp_path = tmp.name

            # Run ffprobe with JSON output and 30s timeout
            cmd = [
                settings.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-select_streams", "v:0",
                tmp_path,
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30.0
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.warning(
                    "ffprobe timed out after 30 seconds for video upload"
                )
                return null_metadata

            if process.returncode != 0:
                logger.warning(
                    "ffprobe failed with return code %d: %s",
                    process.returncode,
                    stderr.decode(errors="replace")[:500],
                )
                return null_metadata

            # Parse ffprobe JSON output
            probe_data = json.loads(stdout.decode())
            streams = probe_data.get("streams", [])
            format_info = probe_data.get("format", {})

            if not streams:
                logger.warning("ffprobe found no video streams")
                return null_metadata

            video_stream = streams[0]

            # Extract duration from format (more reliable) or stream
            duration_str = format_info.get(
                "duration", video_stream.get("duration")
            )
            duration_seconds: float | None = None
            if duration_str is not None:
                try:
                    duration_seconds = float(duration_str)
                except (ValueError, TypeError):
                    pass

            # Extract resolution
            resolution_width: int | None = video_stream.get("width")
            resolution_height: int | None = video_stream.get("height")

            # Extract frame count
            frame_count: int | None = None
            nb_frames = video_stream.get("nb_frames")
            if nb_frames is not None:
                try:
                    frame_count = int(nb_frames)
                except (ValueError, TypeError):
                    pass

            # Extract codec
            codec: str | None = video_stream.get("codec_name")

            return {
                "duration_seconds": duration_seconds,
                "resolution_width": resolution_width,
                "resolution_height": resolution_height,
                "frame_count": frame_count,
                "codec": codec,
            }

        except (json.JSONDecodeError, OSError) as e:
            logger.warning("ffprobe metadata extraction failed: %s", e)
            return null_metadata
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def create_video_document(
        self,
        session: AsyncSession,
        file_data: bytes,
        title: str,
        folder_path: str,
        tags: list[str],
        user_id: int,
        content_type: str,
        company_id: int | None = None,
    ) -> Document:
        """Create a new video document with metadata extraction.

        Validates the video file, uploads to MinIO, extracts metadata
        via ffprobe, stores video metadata in the video_metadata table,
        and sets document_type to "Training Video". Does NOT auto-trigger
        frame extraction (Requirement 4.7).

        Args:
            session: Active async database session.
            file_data: The video file content as bytes.
            title: Document title.
            folder_path: Logical folder path for organization.
            tags: List of classification tags.
            user_id: ID of the creating user.
            content_type: MIME type of the video file.
            company_id: Optional company ID for tenant scoping.

        Returns:
            The created Document instance.

        Raises:
            ValueError: If video validation fails (size or content type).
        """
        # Validate video file (Requirements 4.1, 4.2)
        validation_error = self._validate_video_upload(file_data, content_type)
        if validation_error:
            raise ValueError(validation_error)

        # Extract video metadata via ffprobe (Requirements 4.3, 4.4, 4.5)
        metadata = await self._extract_video_metadata(file_data)

        # Create the document with document_type "Training Video" (Req 4.1)
        document = await self.create_document(
            session=session,
            file_data=file_data,
            title=title,
            folder_path=folder_path,
            document_type="Training Video",
            tags=tags,
            user_id=user_id,
            content_type=content_type,
            company_id=company_id,
        )

        # Store video metadata in video_metadata table (Req 4.3)
        video_meta = VideoMetadata(
            document_id=document.id,
            duration_seconds=metadata["duration_seconds"],
            resolution_width=metadata["resolution_width"],
            resolution_height=metadata["resolution_height"],
            frame_count=metadata["frame_count"],
            codec=metadata["codec"],
        )
        session.add(video_meta)
        await session.flush()

        # Do NOT auto-trigger frame extraction (Requirement 4.7)
        return document

    async def create_version(
        self,
        session: AsyncSession,
        document_uuid: str,
        file_data: bytes,
        version_type: str,
        change_reason: str,
        user_id: int,
        content_type: str = "application/octet-stream",
    ) -> DocumentVersion:
        """Create a new version of an existing document.

        Increments major or minor version, stores the new file in MinIO,
        and retains all previous versions.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID of the target document.
            file_data: The new file content as bytes.
            version_type: Either "major" or "minor".
            change_reason: User-provided reason for the version change.
            user_id: ID of the uploading user.
            content_type: MIME type of the file.

        Returns:
            The created DocumentVersion instance.

        Raises:
            ValueError: If document not found or invalid version_type.
        """
        # Find the document
        result = await session.execute(
            select(Document).where(Document.document_uuid == document_uuid)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document not found: {document_uuid}")

        # Get the latest version
        latest_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(
                DocumentVersion.major_version.desc(),
                DocumentVersion.minor_version.desc(),
            )
            .limit(1)
        )
        latest_version = latest_result.scalar_one_or_none()

        # Calculate new version numbers
        if latest_version is None:
            major, minor = 1, 0
        elif version_type == "major":
            major = latest_version.major_version + 1
            minor = 0
        elif version_type == "minor":
            major = latest_version.major_version
            minor = latest_version.minor_version + 1
        else:
            raise ValueError(f"Invalid version_type: {version_type}. Must be 'major' or 'minor'.")

        # Compute file hash
        file_hash = hashlib.sha512(file_data).hexdigest()

        # Build storage key
        storage_key = f"documents/{document_uuid}/{major}.{minor}/document"

        # Upload to MinIO
        await self._storage.upload_file(storage_key, file_data, content_type)

        try:
            # Create version record
            version = DocumentVersion(
                document_id=document.id,
                major_version=major,
                minor_version=minor,
                storage_key=storage_key,
                file_hash=file_hash,
                uploaded_by=user_id,
                change_reason=change_reason,
            )
            session.add(version)
            await session.flush()

            return version

        except Exception:
            try:
                await self._storage.delete_file(storage_key)
            except Exception:
                pass
            raise

    async def get_document(
        self, session: AsyncSession, document_uuid: str
    ) -> Document | None:
        """Retrieve a document by its Document-UUID.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID to look up.

        Returns:
            The Document instance with tags and versions loaded, or None.
        """
        result = await session.execute(
            select(Document)
            .where(Document.document_uuid == document_uuid)
            .options(
                selectinload(Document.tags),
                selectinload(Document.versions),
            )
        )
        return result.scalar_one_or_none()

    async def get_version(
        self,
        session: AsyncSession,
        document_uuid: str,
        major_version: int,
        minor_version: int,
    ) -> DocumentVersion | None:
        """Retrieve a specific version of a document.

        Args:
            session: Active async database session.
            document_uuid: The Document-UUID of the document.
            major_version: Major version number.
            minor_version: Minor version number.

        Returns:
            The DocumentVersion instance, or None if not found.
        """
        result = await session.execute(
            select(DocumentVersion)
            .join(Document)
            .where(
                Document.document_uuid == document_uuid,
                DocumentVersion.major_version == major_version,
                DocumentVersion.minor_version == minor_version,
            )
        )
        return result.scalar_one_or_none()

    async def search_documents(
        self,
        session: AsyncSession,
        tag: str | None = None,
        folder_path: str | None = None,
        document_uuid: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search documents with filtering and pagination.

        Args:
            session: Active async database session.
            tag: Optional tag to filter by.
            folder_path: Optional folder path to filter by.
            document_uuid: Optional Document-UUID to filter by.
            offset: Number of results to skip (pagination).
            limit: Maximum number of results to return.

        Returns:
            Dictionary with 'items' (list of Documents) and 'total' count.
        """
        query = select(Document).options(
            selectinload(Document.tags),
            selectinload(Document.versions),
        )

        if tag:
            query = query.join(DocumentTag).where(DocumentTag.tag == tag)

        if folder_path:
            query = query.where(Document.folder_path == folder_path)

        if document_uuid:
            query = query.where(Document.document_uuid == document_uuid)

        # Get total count
        from sqlalchemy import func

        count_query = select(func.count()).select_from(Document)
        if tag:
            count_query = count_query.join(DocumentTag).where(DocumentTag.tag == tag)
        if folder_path:
            count_query = count_query.where(Document.folder_path == folder_path)
        if document_uuid:
            count_query = count_query.where(Document.document_uuid == document_uuid)

        total_result = await session.execute(count_query)
        total = total_result.scalar_one()

        # Apply pagination
        query = query.offset(offset).limit(limit).order_by(Document.created_at.desc())

        result = await session.execute(query)
        items = list(result.scalars().unique().all())

        return {"items": items, "total": total}
