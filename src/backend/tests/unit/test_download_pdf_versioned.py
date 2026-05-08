"""Unit tests for the version-aware PDF download endpoint.

Tests that the download_pdf endpoint correctly:
- Uses the active version when available (Requirement 13.1, 13.2)
- Includes version number in filename (Requirement 12.3)
- Supports historical version download with watermark (Requirement 13.5)
- Falls back to non-versioned behavior when no versions exist

References:
    - Requirements 12.3: Version number in PDF filename
    - Requirements 13.1, 13.2: Active version enforcement for PDF download
    - Requirements 13.5: Historical version watermark annotation
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from alcoabase.api.templates import download_pdf
from alcoabase.services.pdf_generator import PDFGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockTemplate:
    """Mock Template for testing."""

    def __init__(
        self,
        id: int = 1,
        document_uuid: str = "2026-00001",
        name: str = "Batch Release Form",
        status: str = "ReadOnly",
    ) -> None:
        self.id = id
        self.document_uuid = document_uuid
        self.name = name
        self.status = status
        self.fields = [
            MagicMock(
                field_uuid="FLD-AAAAAAAA",
                field_type="Text",
                field_label="Field 1",
                field_order=0,
            )
        ]


class MockTemplateVersion:
    """Mock TemplateVersion for testing."""

    def __init__(
        self,
        version_number: int = 1,
        is_active: bool = True,
    ) -> None:
        self.version_number = version_number
        self.is_active = is_active


# ---------------------------------------------------------------------------
# Tests: Version-aware filename
# ---------------------------------------------------------------------------


class TestDownloadPdfVersionFilename:
    """Tests for version-aware PDF filename generation.

    Validates: Requirement 12.3
    """

    @pytest.mark.asyncio
    async def test_filename_includes_version_when_active_version_exists(
        self,
    ) -> None:
        """Filename follows {name}_{uuid}_v{version}.pdf when active version exists."""
        template = MockTemplate(name="Batch Release Form", document_uuid="2026-00001")
        active_version = MockTemplateVersion(version_number=3, is_active=True)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_active_version = AsyncMock(return_value=active_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        response = await download_pdf(
            document_uuid="2026-00001",
            version=None,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        content_disposition = response.headers["content-disposition"]
        assert 'filename="Batch_Release_Form_2026-00001_v3.pdf"' in content_disposition

    @pytest.mark.asyncio
    async def test_filename_includes_specific_version_number(self) -> None:
        """Filename uses the requested version number when specified."""
        template = MockTemplate(name="Test Template", document_uuid="2026-00042")
        specific_version = MockTemplateVersion(version_number=2, is_active=False)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_version = AsyncMock(return_value=specific_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        response = await download_pdf(
            document_uuid="2026-00042",
            version=2,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        content_disposition = response.headers["content-disposition"]
        assert 'filename="Test_Template_2026-00042_v2.pdf"' in content_disposition

    @pytest.mark.asyncio
    async def test_filename_without_version_when_no_versions_exist(self) -> None:
        """Filename omits version when template has no versions."""
        template = MockTemplate(name="Legacy Template", document_uuid="2026-00099")

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_active_version = AsyncMock(return_value=None)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        response = await download_pdf(
            document_uuid="2026-00099",
            version=None,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        content_disposition = response.headers["content-disposition"]
        assert 'filename="Legacy_Template_2026-00099.pdf"' in content_disposition

    @pytest.mark.asyncio
    async def test_filename_sanitizes_spaces_in_name(self) -> None:
        """Spaces in template name are replaced with underscores."""
        template = MockTemplate(
            name="My Complex Template Name", document_uuid="2026-00001"
        )
        active_version = MockTemplateVersion(version_number=1, is_active=True)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_active_version = AsyncMock(return_value=active_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        response = await download_pdf(
            document_uuid="2026-00001",
            version=None,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        content_disposition = response.headers["content-disposition"]
        assert "My_Complex_Template_Name_2026-00001_v1.pdf" in content_disposition


# ---------------------------------------------------------------------------
# Tests: Active version usage
# ---------------------------------------------------------------------------


class TestDownloadPdfActiveVersion:
    """Tests for active version enforcement in PDF download.

    Validates: Requirements 13.1, 13.2
    """

    @pytest.mark.asyncio
    async def test_uses_active_version_when_no_version_specified(self) -> None:
        """Downloads active version when no specific version is requested."""
        template = MockTemplate()
        active_version = MockTemplateVersion(version_number=5, is_active=True)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_active_version = AsyncMock(return_value=active_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        await download_pdf(
            document_uuid="2026-00001",
            version=None,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        # Verify generate_offline_pdf was called with version_number=5
        pdf_gen.generate_offline_pdf.assert_called_once_with(
            template,
            version_number=5,
            is_historical=False,
        )

    @pytest.mark.asyncio
    async def test_calls_get_version_when_specific_version_requested(self) -> None:
        """Calls get_version (not get_active_version) when version param is set."""
        template = MockTemplate()
        specific_version = MockTemplateVersion(version_number=2, is_active=False)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_version = AsyncMock(return_value=specific_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        await download_pdf(
            document_uuid="2026-00001",
            version=2,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        service.get_version.assert_called_once()
        service.get_active_version.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Historical version watermark
# ---------------------------------------------------------------------------


class TestDownloadPdfHistoricalWatermark:
    """Tests for historical version watermark annotation.

    Validates: Requirement 13.5
    """

    @pytest.mark.asyncio
    async def test_historical_version_passes_is_historical_true(self) -> None:
        """Non-active version download passes is_historical=True to PDF generator."""
        template = MockTemplate()
        historical_version = MockTemplateVersion(version_number=1, is_active=False)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_version = AsyncMock(return_value=historical_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        await download_pdf(
            document_uuid="2026-00001",
            version=1,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        pdf_gen.generate_offline_pdf.assert_called_once_with(
            template,
            version_number=1,
            is_historical=True,
        )

    @pytest.mark.asyncio
    async def test_active_version_passes_is_historical_false(self) -> None:
        """Active version download passes is_historical=False to PDF generator."""
        template = MockTemplate()
        active_version = MockTemplateVersion(version_number=3, is_active=True)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_active_version = AsyncMock(return_value=active_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        await download_pdf(
            document_uuid="2026-00001",
            version=None,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        pdf_gen.generate_offline_pdf.assert_called_once_with(
            template,
            version_number=3,
            is_historical=False,
        )

    @pytest.mark.asyncio
    async def test_specific_active_version_passes_is_historical_false(self) -> None:
        """Requesting a specific version that is active passes is_historical=False."""
        template = MockTemplate()
        active_version = MockTemplateVersion(version_number=3, is_active=True)

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_version = AsyncMock(return_value=active_version)

        pdf_gen = MagicMock()
        pdf_gen.generate_offline_pdf.return_value = b"%PDF-1.4 fake content"

        storage = AsyncMock()

        await download_pdf(
            document_uuid="2026-00001",
            version=3,
            session=AsyncMock(),
            service=service,
            pdf_gen=pdf_gen,
            storage=storage,
            tenant=MagicMock(),
        )

        pdf_gen.generate_offline_pdf.assert_called_once_with(
            template,
            version_number=3,
            is_historical=False,
        )


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestDownloadPdfErrors:
    """Tests for error handling in version-aware PDF download."""

    @pytest.mark.asyncio
    async def test_returns_404_when_template_not_found(self) -> None:
        """Returns HTTP 404 when template does not exist."""
        service = AsyncMock()
        service.get_template = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_pdf(
                document_uuid="2026-99999",
                version=None,
                session=AsyncMock(),
                service=service,
                pdf_gen=MagicMock(),
                storage=AsyncMock(),
                tenant=MagicMock(),
            )

        assert exc_info.value.status_code == 404
        assert "Template not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_400_when_template_not_readonly(self) -> None:
        """Returns HTTP 400 when template is not in ReadOnly status."""
        template = MockTemplate(status="Draft")

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)

        with pytest.raises(HTTPException) as exc_info:
            await download_pdf(
                document_uuid="2026-00001",
                version=None,
                session=AsyncMock(),
                service=service,
                pdf_gen=MagicMock(),
                storage=AsyncMock(),
                tenant=MagicMock(),
            )

        assert exc_info.value.status_code == 400
        assert "ReadOnly" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_404_when_specific_version_not_found(self) -> None:
        """Returns HTTP 404 when requested version number does not exist."""
        template = MockTemplate()

        service = AsyncMock()
        service.get_template = AsyncMock(return_value=template)
        service.get_version = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await download_pdf(
                document_uuid="2026-00001",
                version=99,
                session=AsyncMock(),
                service=service,
                pdf_gen=MagicMock(),
                storage=AsyncMock(),
                tenant=MagicMock(),
            )

        assert exc_info.value.status_code == 404
        assert "Version 99 not found" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: PDFGenerator watermark rendering
# ---------------------------------------------------------------------------


class TestPdfGeneratorWatermark:
    """Tests for PDFGenerator historical watermark rendering.

    Validates: Requirement 13.5
    """

    def test_generate_pdf_with_version_number_in_header(self) -> None:
        """PDF generation includes version number in title when provided."""
        template = MockTemplate()
        generator = PDFGenerator()

        # Should not raise - generates PDF with version in header
        pdf_bytes = generator.generate_offline_pdf(
            template, version_number=2, is_historical=False
        )

        assert len(pdf_bytes) > 0
        assert pdf_bytes[:5] == b"%PDF-"

    def test_generate_pdf_with_historical_watermark(self) -> None:
        """PDF generation with is_historical=True produces valid PDF."""
        template = MockTemplate()
        generator = PDFGenerator()

        # Should not raise - generates PDF with watermark
        pdf_bytes = generator.generate_offline_pdf(
            template, version_number=1, is_historical=True
        )

        assert len(pdf_bytes) > 0
        assert pdf_bytes[:5] == b"%PDF-"

    def test_generate_pdf_without_version(self) -> None:
        """PDF generation without version_number works (backward compatible)."""
        template = MockTemplate()
        generator = PDFGenerator()

        # Should not raise - backward compatible call
        pdf_bytes = generator.generate_offline_pdf(template)

        assert len(pdf_bytes) > 0
        assert pdf_bytes[:5] == b"%PDF-"

    def test_historical_pdf_larger_than_non_historical(self) -> None:
        """Historical PDF with watermark is larger due to watermark content."""
        template = MockTemplate()
        generator = PDFGenerator()

        normal_pdf = generator.generate_offline_pdf(
            template, version_number=1, is_historical=False
        )
        historical_pdf = generator.generate_offline_pdf(
            template, version_number=1, is_historical=True
        )

        # Historical PDF should be larger due to watermark text
        assert len(historical_pdf) > len(normal_pdf)
