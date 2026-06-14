"""Unit tests for the document content download and preview endpoints.

Tests the download and content endpoints for correct error handling,
RBAC enforcement, storage failure responses, and response headers.

References:
    - Requirements 1.1, 1.2, 1.3, 1.4: Download endpoint behavior
    - Requirements 2.1, 2.4, 2.5: Content preview endpoint behavior
    - Design doc: Error Handling table and Correctness Properties 1–3
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from alcoabase.api.documents import download_document_version, get_document_content
from alcoabase.dependencies.tenant import TenantContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(user_id: int = 1, company_id: int = 1) -> TenantContext:
    """Create a TenantContext for testing."""
    return TenantContext(
        company_id=company_id,
        company_slug="test-company",
        user_id=user_id,
        membership_role="admin",
    )


def _make_document(title: str = "Test Document", document_uuid: str = "2025-00001"):
    """Create a mock document object."""
    doc = MagicMock()
    doc.title = title
    doc.document_uuid = document_uuid
    return doc


def _make_version(
    storage_key: str = "documents/2025-00001/1.0/report.pdf",
    content_type: str = "application/pdf",
):
    """Create a mock document version object."""
    version = MagicMock()
    version.storage_key = storage_key
    version.content_type = content_type
    return version


# ---------------------------------------------------------------------------
# Tests: Download endpoint — error cases
# ---------------------------------------------------------------------------


class TestDownloadDocumentVersion404:
    """Tests for 404 responses from the download endpoint.

    Validates: Requirements 1.2
    """

    @pytest.mark.asyncio
    async def test_returns_404_when_document_not_found(self) -> None:
        """Returns HTTP 404 when get_document returns None."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_document_version(
                document_uuid="2025-99999",
                major_version=1,
                minor_version=0,
                session=AsyncMock(),
                service=service,
                storage=AsyncMock(),
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_returns_404_when_version_not_found(self) -> None:
        """Returns HTTP 404 when get_version returns None."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_document_version(
                document_uuid="2025-00001",
                major_version=2,
                minor_version=5,
                session=AsyncMock(),
                service=service,
                storage=AsyncMock(),
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 404
        assert "2.5" in exc_info.value.detail


class TestDownloadDocumentVersion403:
    """Tests for 403 responses from the download endpoint.

    Validates: Requirements 1.4
    """

    @pytest.mark.asyncio
    async def test_returns_403_when_access_denied(self) -> None:
        """Returns HTTP 403 when check_document_access returns False."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=_make_version())
        service.check_document_access = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await download_document_version(
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                session=AsyncMock(),
                service=service,
                storage=AsyncMock(),
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 403
        assert "permission" in exc_info.value.detail.lower()


class TestDownloadDocumentVersion502:
    """Tests for 502 responses from the download endpoint.

    Validates: Requirements 2.5
    """

    @pytest.mark.asyncio
    async def test_returns_502_when_storage_fails(self) -> None:
        """Returns HTTP 502 when StorageService.download_file raises."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=_make_version())
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(side_effect=RuntimeError("connection lost"))

        with pytest.raises(HTTPException) as exc_info:
            await download_document_version(
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                session=AsyncMock(),
                service=service,
                storage=storage,
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 502
        assert "storage" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Tests: Download endpoint — success with correct headers
# ---------------------------------------------------------------------------


class TestDownloadDocumentVersionSuccess:
    """Tests for successful download responses with correct headers.

    Validates: Requirements 1.1
    """

    @pytest.mark.asyncio
    @patch("alcoabase.api.documents.log_document_access", new_callable=AsyncMock)
    async def test_200_with_correct_headers(self, mock_audit: AsyncMock) -> None:
        """Returns 200 with correct Content-Type, Disposition, and Length."""
        file_content = b"Hello, this is a test PDF file content"
        document = _make_document(title="My Report")
        version = _make_version(
            storage_key="documents/2025-00001/1.0/report.pdf",
            content_type="application/pdf",
        )

        service = AsyncMock()
        service.get_document = AsyncMock(return_value=document)
        service.get_version = AsyncMock(return_value=version)
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(return_value=file_content)

        response = await download_document_version(
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            session=AsyncMock(),
            service=service,
            storage=storage,
            tenant=_make_tenant(),
        )

        assert response.media_type == "application/pdf"
        assert response.headers["content-length"] == str(len(file_content))

        disposition = response.headers["content-disposition"]
        assert "attachment" in disposition
        assert "My Report" in disposition or "My%20Report" in disposition

    @pytest.mark.asyncio
    @patch("alcoabase.api.documents.log_document_access", new_callable=AsyncMock)
    async def test_content_type_from_stored_value(self, mock_audit: AsyncMock) -> None:
        """Uses stored content_type when available."""
        version = _make_version(
            storage_key="documents/2025-00001/1.0/file",
            content_type="text/plain",
        )

        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=version)
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(return_value=b"plain text content")

        response = await download_document_version(
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            session=AsyncMock(),
            service=service,
            storage=storage,
            tenant=_make_tenant(),
        )

        assert response.media_type == "text/plain"


# ---------------------------------------------------------------------------
# Tests: Content endpoint — error cases
# ---------------------------------------------------------------------------


class TestGetDocumentContent404:
    """Tests for 404 responses from the content endpoint.

    Validates: Requirements 1.2
    """

    @pytest.mark.asyncio
    async def test_returns_404_when_document_not_found(self) -> None:
        """Returns HTTP 404 when get_document returns None."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_document_content(
                document_uuid="2025-99999",
                major_version=1,
                minor_version=0,
                session=AsyncMock(),
                service=service,
                storage=AsyncMock(),
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_when_version_not_found(self) -> None:
        """Returns HTTP 404 when get_version returns None."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_document_content(
                document_uuid="2025-00001",
                major_version=3,
                minor_version=1,
                session=AsyncMock(),
                service=service,
                storage=AsyncMock(),
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 404


class TestGetDocumentContent403:
    """Tests for 403 responses from the content endpoint.

    Validates: Requirements 1.4
    """

    @pytest.mark.asyncio
    async def test_returns_403_when_access_denied(self) -> None:
        """Returns HTTP 403 when check_document_access returns False."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=_make_version())
        service.check_document_access = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc_info:
            await get_document_content(
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                session=AsyncMock(),
                service=service,
                storage=AsyncMock(),
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 403


class TestGetDocumentContent502:
    """Tests for 502 responses from the content endpoint.

    Validates: Requirements 2.5
    """

    @pytest.mark.asyncio
    async def test_returns_502_when_storage_fails(self) -> None:
        """Returns HTTP 502 when StorageService.download_file raises."""
        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=_make_version())
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(
            side_effect=ConnectionError("MinIO unreachable")
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_document_content(
                document_uuid="2025-00001",
                major_version=1,
                minor_version=0,
                session=AsyncMock(),
                service=service,
                storage=storage,
                tenant=_make_tenant(),
            )

        assert exc_info.value.status_code == 502
        assert "storage" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Tests: Content endpoint — success with correct headers
# ---------------------------------------------------------------------------


class TestGetDocumentContentSuccess:
    """Tests for successful content responses with correct headers.

    Validates: Requirements 2.1, 2.4
    """

    @pytest.mark.asyncio
    @patch("alcoabase.api.documents.log_document_access", new_callable=AsyncMock)
    async def test_inline_disposition_for_previewable_pdf(
        self, mock_audit: AsyncMock
    ) -> None:
        """Content-Disposition is inline for PDF content type."""
        file_content = b"%PDF-1.4 fake pdf bytes"
        version = _make_version(
            storage_key="documents/2025-00001/1.0/report.pdf",
            content_type="application/pdf",
        )

        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=version)
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(return_value=file_content)

        response = await get_document_content(
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            session=AsyncMock(),
            service=service,
            storage=storage,
            tenant=_make_tenant(),
        )

        assert response.media_type == "application/pdf"
        assert "inline" in response.headers["content-disposition"]
        assert response.headers["content-length"] == str(len(file_content))

    @pytest.mark.asyncio
    @patch("alcoabase.api.documents.log_document_access", new_callable=AsyncMock)
    async def test_attachment_disposition_for_non_previewable_docx(
        self, mock_audit: AsyncMock
    ) -> None:
        """Content-Disposition is attachment for non-previewable DOCX type."""
        file_content = b"PK\x03\x04 fake docx content"
        docx_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        version = _make_version(
            storage_key="documents/2025-00001/1.0/manual.docx",
            content_type=docx_type,
        )

        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=version)
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(return_value=file_content)

        response = await get_document_content(
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            session=AsyncMock(),
            service=service,
            storage=storage,
            tenant=_make_tenant(),
        )

        assert response.media_type == docx_type
        assert "attachment" in response.headers["content-disposition"]

    @pytest.mark.asyncio
    @patch("alcoabase.api.documents.log_document_access", new_callable=AsyncMock)
    async def test_markdown_gets_charset_utf8(self, mock_audit: AsyncMock) -> None:
        """Markdown content type includes charset=utf-8 override."""
        file_content = b"# Hello World\n\nSome markdown content."
        version = _make_version(
            storage_key="documents/2025-00001/1.0/readme.md",
            content_type="text/markdown",
        )

        service = AsyncMock()
        service.get_document = AsyncMock(return_value=_make_document())
        service.get_version = AsyncMock(return_value=version)
        service.check_document_access = AsyncMock(return_value=True)

        storage = AsyncMock()
        storage.download_file = AsyncMock(return_value=file_content)

        response = await get_document_content(
            document_uuid="2025-00001",
            major_version=1,
            minor_version=0,
            session=AsyncMock(),
            service=service,
            storage=storage,
            tenant=_make_tenant(),
        )

        assert response.media_type == "text/markdown; charset=utf-8"
        assert "inline" in response.headers["content-disposition"]
        assert response.headers["content-length"] == str(len(file_content))
