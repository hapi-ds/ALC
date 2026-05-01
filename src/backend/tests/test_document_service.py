"""Unit tests for DocumentService.

Tests document creation, versioning, search, and error handling
on storage failure.

References:
    - Task 4.10: Unit tests for DocumentService
    - Requirements 1, 2: Document CRUD and versioning
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.document_service import DocumentService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage_service() -> AsyncMock:
    """Create a mock StorageService."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value="documents/2025-00001/1.0/document")
    storage.download_file = AsyncMock(return_value=b"file content")
    storage.delete_file = AsyncMock()
    return storage


@pytest.fixture
def mock_uuid_service() -> AsyncMock:
    """Create a mock UUIDService."""
    uuid_svc = AsyncMock()
    uuid_svc.generate_document_uuid = AsyncMock(return_value="2025-00001")
    return uuid_svc


@pytest.fixture
def document_service(mock_storage_service: AsyncMock, mock_uuid_service: AsyncMock) -> DocumentService:
    """Create a DocumentService with mocked dependencies."""
    return DocumentService(
        storage_service=mock_storage_service,
        uuid_service=mock_uuid_service,
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession with flush support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    # Mock execute for queries
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Test: Document Creation
# ---------------------------------------------------------------------------


class TestCreateDocument:
    """Tests for DocumentService.create_document()."""

    @pytest.mark.asyncio
    async def test_create_document_generates_uuid(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
        mock_uuid_service: AsyncMock,
    ) -> None:
        """create_document() generates a Document-UUID via UUIDService."""
        await document_service.create_document(
            session=mock_session,
            file_data=b"test content",
            title="Test Document",
            folder_path="/sops",
            document_type="SOP",
            tags=["SOP"],
            user_id=1,
        )

        mock_uuid_service.generate_document_uuid.assert_called_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_create_document_uploads_to_storage(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
        mock_storage_service: AsyncMock,
    ) -> None:
        """create_document() uploads the file to MinIO storage."""
        file_data = b"test content"

        await document_service.create_document(
            session=mock_session,
            file_data=file_data,
            title="Test Document",
            folder_path="/sops",
            document_type="SOP",
            tags=["SOP"],
            user_id=1,
        )

        mock_storage_service.upload_file.assert_called_once_with(
            "documents/2025-00001/1.0/document",
            file_data,
            "application/octet-stream",
        )

    @pytest.mark.asyncio
    async def test_create_document_persists_metadata(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """create_document() adds document, tags, and version to session."""
        await document_service.create_document(
            session=mock_session,
            file_data=b"test content",
            title="Test Document",
            folder_path="/sops",
            document_type="SOP",
            tags=["SOP", "Lab-A"],
            user_id=1,
        )

        # Document + 2 tags + 1 version = 4 add calls
        assert mock_session.add.call_count == 4

    @pytest.mark.asyncio
    async def test_create_document_returns_document_with_uuid(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """create_document() returns a Document with the generated UUID."""
        result = await document_service.create_document(
            session=mock_session,
            file_data=b"test content",
            title="Test Document",
            folder_path="/sops",
            document_type="SOP",
            tags=[],
            user_id=1,
        )

        assert result.document_uuid == "2025-00001"
        assert result.title == "Test Document"
        assert result.current_status == "Draft"

    @pytest.mark.asyncio
    async def test_create_document_initial_version_is_1_0(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """create_document() creates an initial version 1.0."""
        await document_service.create_document(
            session=mock_session,
            file_data=b"test content",
            title="Test Document",
            folder_path="/sops",
            document_type="SOP",
            tags=[],
            user_id=1,
        )

        # Find the DocumentVersion that was added
        from alcoabase.models.document import DocumentVersion

        version_calls = [
            call
            for call in mock_session.add.call_args_list
            if isinstance(call[0][0], DocumentVersion)
        ]
        assert len(version_calls) == 1
        version = version_calls[0][0][0]
        assert version.major_version == 1
        assert version.minor_version == 0

    @pytest.mark.asyncio
    async def test_create_document_computes_sha512_hash(
        self,
        document_service: DocumentService,
        mock_session: AsyncMock,
    ) -> None:
        """create_document() computes SHA-512 hash of file content."""
        file_data = b"test content"
        expected_hash = hashlib.sha512(file_data).hexdigest()

        await document_service.create_document(
            session=mock_session,
            file_data=file_data,
            title="Test Document",
            folder_path="/sops",
            document_type="SOP",
            tags=[],
            user_id=1,
        )

        from alcoabase.models.document import DocumentVersion

        version_calls = [
            call
            for call in mock_session.add.call_args_list
            if isinstance(call[0][0], DocumentVersion)
        ]
        version = version_calls[0][0][0]
        assert version.file_hash == expected_hash


class TestCreateDocumentStorageFailure:
    """Tests for error handling when storage fails."""

    @pytest.mark.asyncio
    async def test_storage_failure_raises_exception(
        self,
        mock_storage_service: AsyncMock,
        mock_uuid_service: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """If MinIO upload fails, exception is raised and no DB record created."""
        mock_storage_service.upload_file.side_effect = Exception("MinIO unavailable")

        service = DocumentService(
            storage_service=mock_storage_service,
            uuid_service=mock_uuid_service,
        )

        with pytest.raises(Exception, match="MinIO unavailable"):
            await service.create_document(
                session=mock_session,
                file_data=b"test content",
                title="Test Document",
                folder_path="/sops",
                document_type="SOP",
                tags=[],
                user_id=1,
            )

        # No DB records should be added
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_failure_cleans_up_storage(
        self,
        mock_storage_service: AsyncMock,
        mock_uuid_service: AsyncMock,
    ) -> None:
        """If DB flush fails after upload, storage file is cleaned up."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock(side_effect=Exception("DB error"))

        service = DocumentService(
            storage_service=mock_storage_service,
            uuid_service=mock_uuid_service,
        )

        with pytest.raises(Exception, match="DB error"):
            await service.create_document(
                session=session,
                file_data=b"test content",
                title="Test Document",
                folder_path="/sops",
                document_type="SOP",
                tags=[],
                user_id=1,
            )

        # Storage cleanup should be attempted
        mock_storage_service.delete_file.assert_called_once()


# ---------------------------------------------------------------------------
# Test: Document Versioning
# ---------------------------------------------------------------------------


class TestCreateVersion:
    """Tests for DocumentService.create_version()."""

    @pytest.fixture
    def mock_session_with_document(self) -> AsyncMock:
        """Create a mock session that returns a document and latest version."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # Mock document lookup
        from alcoabase.models.document import Document, DocumentVersion

        mock_doc = Document(
            id=1,
            document_uuid="2025-00001",
            title="Test",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
        )

        mock_version = DocumentVersion(
            id=1,
            document_id=1,
            major_version=1,
            minor_version=0,
            storage_key="documents/2025-00001/1.0/document",
            file_hash="abc123",
            uploaded_by=1,
        )

        # First execute returns document, second returns latest version
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = mock_version

        session.execute = AsyncMock(side_effect=[doc_result, version_result])
        return session

    @pytest.mark.asyncio
    async def test_major_version_increments_major(
        self,
        document_service: DocumentService,
        mock_session_with_document: AsyncMock,
    ) -> None:
        """create_version() with 'major' increments major and resets minor."""
        result = await document_service.create_version(
            session=mock_session_with_document,
            document_uuid="2025-00001",
            file_data=b"new content",
            version_type="major",
            change_reason="Major update",
            user_id=1,
        )

        assert result.major_version == 2
        assert result.minor_version == 0

    @pytest.mark.asyncio
    async def test_minor_version_increments_minor(
        self,
        document_service: DocumentService,
        mock_session_with_document: AsyncMock,
    ) -> None:
        """create_version() with 'minor' increments minor, keeps major."""
        result = await document_service.create_version(
            session=mock_session_with_document,
            document_uuid="2025-00001",
            file_data=b"new content",
            version_type="minor",
            change_reason="Minor fix",
            user_id=1,
        )

        assert result.major_version == 1
        assert result.minor_version == 1

    @pytest.mark.asyncio
    async def test_version_uploads_to_storage(
        self,
        document_service: DocumentService,
        mock_session_with_document: AsyncMock,
        mock_storage_service: AsyncMock,
    ) -> None:
        """create_version() uploads the new file to MinIO."""
        await document_service.create_version(
            session=mock_session_with_document,
            document_uuid="2025-00001",
            file_data=b"new content",
            version_type="major",
            change_reason="Major update",
            user_id=1,
        )

        mock_storage_service.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_version_not_found_raises_error(
        self,
        document_service: DocumentService,
    ) -> None:
        """create_version() raises ValueError if document not found."""
        session = AsyncMock()
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=doc_result)

        with pytest.raises(ValueError, match="Document not found"):
            await document_service.create_version(
                session=session,
                document_uuid="9999-99999",
                file_data=b"content",
                version_type="major",
                change_reason="Update",
                user_id=1,
            )

    @pytest.mark.asyncio
    async def test_invalid_version_type_raises_error(
        self,
        document_service: DocumentService,
        mock_session_with_document: AsyncMock,
    ) -> None:
        """create_version() raises ValueError for invalid version_type."""
        with pytest.raises(ValueError, match="Invalid version_type"):
            await document_service.create_version(
                session=mock_session_with_document,
                document_uuid="2025-00001",
                file_data=b"content",
                version_type="patch",
                change_reason="Update",
                user_id=1,
            )


# ---------------------------------------------------------------------------
# Test: Document Search
# ---------------------------------------------------------------------------


class TestSearchDocuments:
    """Tests for DocumentService.search_documents()."""

    @pytest.mark.asyncio
    async def test_search_returns_items_and_total(
        self,
        document_service: DocumentService,
    ) -> None:
        """search_documents() returns dict with 'items' and 'total'."""
        session = AsyncMock()

        # Mock count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        # Mock items query
        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await document_service.search_documents(session=session)

        assert "items" in result
        assert "total" in result
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_search_with_tag_filter(
        self,
        document_service: DocumentService,
    ) -> None:
        """search_documents() accepts tag filter parameter."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await document_service.search_documents(
            session=session, tag="SOP"
        )

        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_with_pagination(
        self,
        document_service: DocumentService,
    ) -> None:
        """search_documents() respects offset and limit parameters."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 50

        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = []
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await document_service.search_documents(
            session=session, offset=10, limit=5
        )

        assert result["total"] == 50
