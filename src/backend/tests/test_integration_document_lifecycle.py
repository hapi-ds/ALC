"""Integration tests for complete document lifecycle.

Tests the full flow: create → version → search → retrieve.

References:
    - Task 22.2: Integration tests for document lifecycle
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.services.document_service import DocumentService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_service() -> AsyncMock:
    """Mock storage service for integration tests."""
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value="documents/2025-00001/1.0/doc.pdf")
    storage.download_file = AsyncMock(return_value=b"file content")
    storage.delete_file = AsyncMock()
    return storage


@pytest.fixture
def uuid_service() -> AsyncMock:
    """Mock UUID service with incrementing UUIDs."""
    svc = AsyncMock()
    counter = {"val": 0}

    async def gen_uuid(session):
        counter["val"] += 1
        return f"2025-{counter['val']:05d}"

    svc.generate_document_uuid = gen_uuid
    return svc


@pytest.fixture
def document_service(storage_service, uuid_service) -> DocumentService:
    """DocumentService with mocked dependencies."""
    return DocumentService(
        storage_service=storage_service,
        uuid_service=uuid_service,
    )


# ---------------------------------------------------------------------------
# Integration Tests: Document Lifecycle
# ---------------------------------------------------------------------------


class TestDocumentLifecycle:
    """Integration tests for the complete document lifecycle."""

    @pytest.mark.asyncio
    async def test_create_document_full_flow(self, document_service, storage_service):
        """Create a document: generates UUID, uploads to storage, persists metadata."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        doc = await document_service.create_document(
            session=session,
            file_data=b"SOP content here",
            title="SOP-001 Lab Procedure",
            folder_path="/sops/lab",
            document_type="SOP",
            tags=["SOP", "Lab-A"],
            user_id=1,
        )

        assert doc.document_uuid == "2025-00001"
        assert doc.title == "SOP-001 Lab Procedure"
        assert doc.current_status == "Draft"
        storage_service.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_version_after_document(self, document_service, storage_service):
        """Create a new version of an existing document."""
        # Setup: mock session that returns existing document
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        existing_doc = Document(
            id=1,
            document_uuid="2025-00001",
            title="Test",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
        )
        existing_version = DocumentVersion(
            id=1,
            document_id=1,
            major_version=1,
            minor_version=0,
            storage_key="documents/2025-00001/1.0/doc.pdf",
            file_hash="abc",
            uploaded_by=1,
        )

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = existing_doc
        ver_result = MagicMock()
        ver_result.scalar_one_or_none.return_value = existing_version
        session.execute = AsyncMock(side_effect=[doc_result, ver_result])

        # Create new major version
        storage_service.upload_file = AsyncMock(
            return_value="documents/2025-00001/2.0/doc.pdf"
        )

        version = await document_service.create_version(
            session=session,
            document_uuid="2025-00001",
            file_data=b"updated content",
            version_type="major",
            change_reason="Major revision",
            user_id=1,
        )

        assert version.major_version == 2
        assert version.minor_version == 0
        assert version.change_reason == "Major revision"

    @pytest.mark.asyncio
    async def test_search_documents_returns_results(self, document_service):
        """Search documents with tag filter returns matching results."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        doc1 = Document(
            id=1,
            document_uuid="2025-00001",
            title="SOP 1",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
        )
        doc2 = Document(
            id=2,
            document_uuid="2025-00002",
            title="SOP 2",
            folder_path="/sops",
            document_type="SOP",
            current_status="Approved",
            created_by=1,
        )

        items_result = MagicMock()
        scalars_mock = MagicMock()
        unique_mock = MagicMock()
        unique_mock.all.return_value = [doc1, doc2]
        scalars_mock.unique.return_value = unique_mock
        items_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, items_result])

        result = await document_service.search_documents(
            session=session, tag="SOP"
        )

        assert result["total"] == 2
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_document_retrieves_by_uuid(self, document_service):
        """Get document by UUID returns the correct document."""
        session = AsyncMock()

        doc = Document(
            id=1,
            document_uuid="2025-00001",
            title="Test SOP",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            created_by=1,
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = doc
        session.execute = AsyncMock(return_value=result_mock)

        retrieved = await document_service.get_document(session, "2025-00001")

        assert retrieved is not None
        assert retrieved.document_uuid == "2025-00001"
        assert retrieved.title == "Test SOP"
