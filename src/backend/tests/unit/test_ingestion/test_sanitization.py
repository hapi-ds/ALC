"""Unit tests for the sanitization pipeline (PDF, HTML, XML/JATS).

Tests:
    - PDF sanitizer: valid PDF → StructuredContent, scanned-only → ocr_required
    - HTML sanitizer: valid article → clean text, malicious elements stripped
    - XML/JATS sanitizer: valid JATS → correct field mapping, malformed → parse_error
    - SanitizationPipeline dispatcher routes by content_type
    - Unsupported content_type raises UnsupportedContentTypeError

Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.5, 6.6
"""

from unittest.mock import AsyncMock

import fitz
import pytest

from alcoabase.literature.ingestion.exceptions import (
    SanitizationError,
    UnsupportedContentTypeError,
)
from alcoabase.literature.ingestion.schemas.structured_content import (
    SourceFormat,
    StructuredContent,
)
from alcoabase.literature.ingestion.services.sanitization.html_sanitizer import (
    HTMLSanitizer,
)
from alcoabase.literature.ingestion.services.sanitization.pdf_sanitizer import (
    PDFSanitizer,
)
from alcoabase.literature.ingestion.services.sanitization.pipeline import (
    SanitizationPipeline,
)
from alcoabase.literature.ingestion.services.sanitization.xml_sanitizer import (
    XMLJATSSanitizer,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_pdf_with_text(text: str) -> bytes:
    """Create a minimal PDF with text content using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _make_scanned_pdf() -> bytes:
    """Create a PDF with no extractable text (simulates scanned-only)."""
    doc = fitz.open()
    page = doc.new_page()
    # Draw a filled rectangle to simulate a scanned image, but insert no text
    rect = fitz.Rect(50, 50, 200, 200)
    page.draw_rect(rect, color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ─── PDF Sanitizer Tests ─────────────────────────────────────────────────────


class TestPDFSanitizer:
    """Test PDF sanitizer behavior."""

    @pytest.mark.asyncio
    async def test_valid_pdf_produces_structured_content(self) -> None:
        """A PDF with text produces StructuredContent with sections."""
        sanitizer = PDFSanitizer()
        pdf_bytes = _make_pdf_with_text("Title of Paper\n\nThis is the body text.")

        result = await sanitizer.sanitize(pdf_bytes, "application/pdf")

        assert isinstance(result, StructuredContent)
        assert result.source_format == SourceFormat.PDF
        assert result.word_count > 0
        assert len(result.raw_plaintext) > 0

    @pytest.mark.asyncio
    async def test_scanned_only_pdf_raises_ocr_required(self) -> None:
        """A scanned-only PDF (no text) raises SanitizationError with ocr_required."""
        sanitizer = PDFSanitizer()
        pdf_bytes = _make_scanned_pdf()

        with pytest.raises(SanitizationError) as exc_info:
            await sanitizer.sanitize(pdf_bytes, "application/pdf")

        assert exc_info.value.error_type == "ocr_required"

    @pytest.mark.asyncio
    async def test_corrupted_pdf_raises_sanitization_error(self) -> None:
        """Invalid/corrupted bytes raise SanitizationError."""
        sanitizer = PDFSanitizer()

        with pytest.raises(SanitizationError):
            await sanitizer.sanitize(b"not a pdf", "application/pdf")


# ─── HTML Sanitizer Tests ────────────────────────────────────────────────────


class TestHTMLSanitizer:
    """Test HTML sanitizer behavior."""

    @pytest.mark.asyncio
    async def test_valid_article_produces_structured_content(self) -> None:
        """Valid HTML article produces clean StructuredContent."""
        sanitizer = HTMLSanitizer()
        html = b"""<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
<article>
    <h1>Research Title</h1>
    <div class="abstract"><p>This is the abstract of the paper.</p></div>
    <h2>Introduction</h2>
    <p>This is the introduction section with some content.</p>
    <h2>Methods</h2>
    <p>Methodology details are described here.</p>
</article>
</body>
</html>"""

        result = await sanitizer.sanitize(html, "text/html")

        assert isinstance(result, StructuredContent)
        assert result.source_format == SourceFormat.HTML
        assert "Research Title" in result.extracted_title
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_malicious_elements_stripped(self) -> None:
        """Script, iframe, object, embed, form are removed."""
        sanitizer = HTMLSanitizer()
        html = b"""<html><body>
<article>
    <h1>Safe Title</h1>
    <script>alert('xss')</script>
    <iframe src="evil.com"></iframe>
    <object data="malware.swf"></object>
    <embed src="bad.swf">
    <form action="phish.com"><input></form>
    <p>Safe content here.</p>
</article>
</body></html>"""

        result = await sanitizer.sanitize(html, "text/html")

        assert "alert" not in result.raw_plaintext
        assert "evil.com" not in result.raw_plaintext
        assert "malware" not in result.raw_plaintext
        assert "phish" not in result.raw_plaintext
        assert "Safe content" in result.raw_plaintext

    @pytest.mark.asyncio
    async def test_dangerous_attributes_stripped(self) -> None:
        """onclick, onerror, onload, onmouseover and javascript: URLs removed."""
        sanitizer = HTMLSanitizer()
        html = b"""<html><body>
<article>
    <h1>Article Title</h1>
    <p onclick="evil()" onerror="hack()">Paragraph text.</p>
    <a href="javascript:alert('xss')">Click me</a>
    <img src="javascript:void(0)" onload="steal()">
</article>
</body></html>"""

        result = await sanitizer.sanitize(html, "text/html")

        assert "onclick" not in result.raw_plaintext
        assert "javascript:" not in result.raw_plaintext
        assert "Paragraph text" in result.raw_plaintext

    @pytest.mark.asyncio
    async def test_encoding_detection_utf8(self) -> None:
        """UTF-8 content is properly decoded."""
        sanitizer = HTMLSanitizer()
        html = """<html><body>
<article><h1>Ünîcödé Tîtlé</h1><p>Content with accents: café résumé.</p></article>
</body></html>""".encode("utf-8")

        result = await sanitizer.sanitize(html, "text/html; charset=utf-8")

        assert "Ünîcödé" in result.extracted_title
        assert "café" in result.raw_plaintext

    @pytest.mark.asyncio
    async def test_encoding_detection_from_meta_tag(self) -> None:
        """Encoding is detected from <meta charset>."""
        sanitizer = HTMLSanitizer()
        html = b"""<html><head><meta charset="utf-8"></head><body>
<article><h1>Test Title</h1><p>Hello world.</p></article>
</body></html>"""

        result = await sanitizer.sanitize(html, "text/html")
        assert "Test Title" in result.extracted_title


# ─── XML/JATS Sanitizer Tests ────────────────────────────────────────────────


class TestXMLJATSSanitizer:
    """Test XML/JATS sanitizer behavior."""

    @pytest.mark.asyncio
    async def test_valid_jats_produces_structured_content(self) -> None:
        """Valid JATS XML maps to correct StructuredContent fields."""
        sanitizer = XMLJATSSanitizer()
        jats_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<article>
    <front>
        <article-meta>
            <title-group>
                <article-title>JATS Article Title</article-title>
            </title-group>
            <abstract><p>This is the article abstract.</p></abstract>
        </article-meta>
    </front>
    <body>
        <sec>
            <title>Introduction</title>
            <p>Introduction paragraph text.</p>
        </sec>
        <sec>
            <title>Methods</title>
            <p>Methods paragraph text.</p>
        </sec>
    </body>
    <back>
        <ref-list>
            <ref><mixed-citation>Author A. Title. Journal. 2020.</mixed-citation></ref>
            <ref><mixed-citation>Author B. Title. Journal. 2021.</mixed-citation></ref>
        </ref-list>
    </back>
</article>"""

        result = await sanitizer.sanitize(jats_xml, "application/xml")

        assert isinstance(result, StructuredContent)
        assert result.source_format == SourceFormat.XML
        assert result.extracted_title == "JATS Article Title"
        assert "article abstract" in result.extracted_abstract
        assert len(result.body_sections) == 2
        assert result.body_sections[0].heading == "Introduction"
        assert "Introduction paragraph" in result.body_sections[0].text
        assert len(result.references) == 2
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_malformed_xml_raises_parse_error(self) -> None:
        """Malformed XML raises SanitizationError with parse_error."""
        sanitizer = XMLJATSSanitizer()
        bad_xml = b"<article><unclosed-tag></article>"

        with pytest.raises(SanitizationError) as exc_info:
            await sanitizer.sanitize(bad_xml, "application/xml")

        assert exc_info.value.error_type == "parse_error"

    @pytest.mark.asyncio
    async def test_encoding_normalization(self) -> None:
        """XML with non-UTF-8 encoding is properly normalized."""
        sanitizer = XMLJATSSanitizer()
        jats_xml = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<article><front><article-meta><title-group><article-title>Caf\xe9 Title</article-title></title-group><abstract><p>Abstract</p></abstract></article-meta></front><body><sec><title>Body</title><p>Text</p></sec></body></article>'.encode(
            "iso-8859-1"
        )

        result = await sanitizer.sanitize(jats_xml, "application/xml")

        assert "Café Title" in result.extracted_title


# ─── SanitizationPipeline Dispatcher Tests ───────────────────────────────────


class TestSanitizationPipeline:
    """Test the dispatcher routes by content_type correctly."""

    @pytest.fixture
    def mock_pdf_sanitizer(self) -> AsyncMock:
        sanitizer = AsyncMock()
        sanitizer.sanitize = AsyncMock(
            return_value=StructuredContent(
                source_format=SourceFormat.PDF,
                extracted_title="PDF Title",
                extracted_abstract="PDF abstract",
                body_sections=[],
                references=[],
                figure_count=0,
                table_count=0,
                word_count=4,
                raw_plaintext="PDF Title\nPDF abstract",
            )
        )
        return sanitizer

    @pytest.fixture
    def mock_html_sanitizer(self) -> AsyncMock:
        sanitizer = AsyncMock()
        sanitizer.sanitize = AsyncMock(
            return_value=StructuredContent(
                source_format=SourceFormat.HTML,
                extracted_title="HTML Title",
                extracted_abstract="HTML abstract",
                body_sections=[],
                references=[],
                figure_count=0,
                table_count=0,
                word_count=4,
                raw_plaintext="HTML Title\nHTML abstract",
            )
        )
        return sanitizer

    @pytest.fixture
    def mock_xml_sanitizer(self) -> AsyncMock:
        sanitizer = AsyncMock()
        sanitizer.sanitize = AsyncMock(
            return_value=StructuredContent(
                source_format=SourceFormat.XML,
                extracted_title="XML Title",
                extracted_abstract="XML abstract",
                body_sections=[],
                references=[],
                figure_count=0,
                table_count=0,
                word_count=4,
                raw_plaintext="XML Title\nXML abstract",
            )
        )
        return sanitizer

    @pytest.fixture
    def pipeline(
        self,
        mock_pdf_sanitizer: AsyncMock,
        mock_html_sanitizer: AsyncMock,
        mock_xml_sanitizer: AsyncMock,
    ) -> SanitizationPipeline:
        return SanitizationPipeline(
            pdf_sanitizer=mock_pdf_sanitizer,
            html_sanitizer=mock_html_sanitizer,
            xml_sanitizer=mock_xml_sanitizer,
        )

    @pytest.mark.asyncio
    async def test_routes_pdf(
        self, pipeline: SanitizationPipeline, mock_pdf_sanitizer: AsyncMock
    ) -> None:
        await pipeline.process(b"pdf bytes", "application/pdf", record_id=1)
        mock_pdf_sanitizer.sanitize.assert_called_once_with(b"pdf bytes", "application/pdf")

    @pytest.mark.asyncio
    async def test_routes_html(
        self, pipeline: SanitizationPipeline, mock_html_sanitizer: AsyncMock
    ) -> None:
        await pipeline.process(b"html bytes", "text/html", record_id=2)
        mock_html_sanitizer.sanitize.assert_called_once_with(b"html bytes", "text/html")

    @pytest.mark.asyncio
    async def test_routes_application_xml(
        self, pipeline: SanitizationPipeline, mock_xml_sanitizer: AsyncMock
    ) -> None:
        await pipeline.process(b"xml bytes", "application/xml", record_id=3)
        mock_xml_sanitizer.sanitize.assert_called_once_with(b"xml bytes", "application/xml")

    @pytest.mark.asyncio
    async def test_routes_text_xml(
        self, pipeline: SanitizationPipeline, mock_xml_sanitizer: AsyncMock
    ) -> None:
        await pipeline.process(b"xml bytes", "text/xml", record_id=4)
        mock_xml_sanitizer.sanitize.assert_called_once_with(b"xml bytes", "text/xml")

    @pytest.mark.asyncio
    async def test_routes_jats_xml(
        self, pipeline: SanitizationPipeline, mock_xml_sanitizer: AsyncMock
    ) -> None:
        await pipeline.process(b"jats bytes", "application/jats+xml", record_id=5)
        mock_xml_sanitizer.sanitize.assert_called_once_with(
            b"jats bytes", "application/jats+xml"
        )

    @pytest.mark.asyncio
    async def test_unsupported_content_type_raises(
        self, pipeline: SanitizationPipeline
    ) -> None:
        with pytest.raises(UnsupportedContentTypeError) as exc_info:
            await pipeline.process(b"zip bytes", "application/zip", record_id=6)

        assert exc_info.value.content_type == "application/zip"
        assert exc_info.value.record_id == 6
