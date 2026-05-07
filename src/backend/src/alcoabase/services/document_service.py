"""Document service for CRUD operations, versioning, and search.

Provides document lifecycle management including creation with UUID
generation, version management (major/minor), retrieval, and search
with pagination.

References:
    - Design doc Section 3: Document Service
    - Requirements 1, 2: Document creation, versioning, retrieval, search
"""

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.services.storage_service import StorageService
from alcoabase.services.uuid_service import UUIDService


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
