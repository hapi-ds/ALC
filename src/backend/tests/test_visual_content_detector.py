"""Unit tests for the VisualContentDetector service.

Tests visual page detection, classification, and cap enforcement
for PDF and DOCX documents.

References:
    - Task 3.1: Implement VisualContentDetector class
    - Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""

import io

import pytest

from alcoabase.services.visual_content_detector import (
    VisualContentDetector,
    VisualPageInfo,
    VisualType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def detector() -> VisualContentDetector:
    """Create a VisualContentDetector with default settings."""
    return VisualContentDetector()


@pytest.fixture
def small_cap_detector() -> VisualContentDetector:
    """Create a VisualContentDetector with a small cap for testing."""
    return VisualContentDetector(max_visual_pages=2)


def _create_text_heavy_pdf() -> bytes:
    """Create a PDF with lots of text (high text_area_ratio)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        # Fill the page with text
        y = 750
        for i in range(40):
            c.drawString(50, y, f"This is line {i} of text content that fills the page with extractable text data.")
            y -= 18
        c.showPage()
        c.save()
        return buffer.getvalue()
    except ImportError:
        pytest.skip("ReportLab not available for PDF generation")


def _create_image_pdf() -> bytes:
    """Create a PDF with an image and minimal text (low text_area_ratio)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from PIL import Image

        # Create a large test image
        img = Image.new("RGB", (500, 500), color="blue")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        # Draw a large image covering most of the page
        c.drawImage(ImageReader(img_buffer), 50, 100, width=500, height=600)
        c.showPage()
        c.save()
        return buffer.getvalue()
    except ImportError:
        pytest.skip("ReportLab or Pillow not available for PDF generation")


def _create_multi_page_image_pdf(num_pages: int) -> bytes:
    """Create a multi-page PDF where each page has an image."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from PIL import Image

        img = Image.new("RGB", (400, 400), color="green")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        for _ in range(num_pages):
            img_buffer.seek(0)
            c.drawImage(ImageReader(img_buffer), 50, 200, width=400, height=400)
            c.showPage()
        c.save()
        return buffer.getvalue()
    except ImportError:
        pytest.skip("ReportLab or Pillow not available for PDF generation")


# ---------------------------------------------------------------------------
# Tests: Basic Detection
# ---------------------------------------------------------------------------


class TestBasicDetection:
    """Tests for basic visual page detection logic."""

    def test_text_heavy_page_not_detected_as_visual(
        self, detector: VisualContentDetector
    ) -> None:
        """A page with high text_area_ratio should not be classified as visual."""
        pdf_bytes = _create_text_heavy_pdf()
        results = detector.detect_visual_pages(pdf_bytes, "application/pdf")
        assert results == []

    def test_image_page_detected_as_visual(
        self, detector: VisualContentDetector
    ) -> None:
        """A page with an image and low text should be classified as visual."""
        pdf_bytes = _create_image_pdf()
        results = detector.detect_visual_pages(pdf_bytes, "application/pdf")
        assert len(results) >= 1
        assert all(isinstance(r, VisualPageInfo) for r in results)
        assert all(r.text_area_ratio < 0.3 for r in results)

    def test_empty_bytes_returns_empty(
        self, detector: VisualContentDetector
    ) -> None:
        """Empty bytes should return empty list without crashing."""
        results = detector.detect_visual_pages(b"", "application/pdf")
        assert results == []

    def test_invalid_pdf_returns_empty(
        self, detector: VisualContentDetector
    ) -> None:
        """Invalid PDF content should return empty list gracefully."""
        results = detector.detect_visual_pages(b"not a pdf", "application/pdf")
        assert results == []

    def test_unsupported_content_type_returns_empty(
        self, detector: VisualContentDetector
    ) -> None:
        """Unsupported content type should return empty list."""
        results = detector.detect_visual_pages(b"data", "text/plain")
        assert results == []


# ---------------------------------------------------------------------------
# Tests: Visual Page Cap (Req 1.5)
# ---------------------------------------------------------------------------


class TestVisualPageCap:
    """Tests for the max_visual_pages cap enforcement."""

    def test_cap_enforced_at_max_visual_pages(
        self, small_cap_detector: VisualContentDetector
    ) -> None:
        """Should return at most max_visual_pages results."""
        pdf_bytes = _create_multi_page_image_pdf(5)
        results = small_cap_detector.detect_visual_pages(
            pdf_bytes, "application/pdf"
        )
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# Tests: VisualPageInfo Structure
# ---------------------------------------------------------------------------


class TestVisualPageInfoStructure:
    """Tests for the structure of returned VisualPageInfo objects."""

    def test_visual_page_info_has_required_fields(
        self, detector: VisualContentDetector
    ) -> None:
        """VisualPageInfo should have all required fields populated."""
        pdf_bytes = _create_image_pdf()
        results = detector.detect_visual_pages(pdf_bytes, "application/pdf")

        if results:
            info = results[0]
            assert info.page_number >= 0
            assert isinstance(info.visual_type, VisualType)
            assert info.width > 0
            assert info.height > 0
            assert 0.0 <= info.text_area_ratio <= 1.0

    def test_visual_type_is_valid_enum(
        self, detector: VisualContentDetector
    ) -> None:
        """Visual type should be a valid VisualType enum value."""
        pdf_bytes = _create_image_pdf()
        results = detector.detect_visual_pages(pdf_bytes, "application/pdf")

        for info in results:
            assert info.visual_type in (
                VisualType.FLOWCHART,
                VisualType.CHART,
                VisualType.DIAGRAM,
                VisualType.MIXED,
            )


# ---------------------------------------------------------------------------
# Tests: Constructor Parameters
# ---------------------------------------------------------------------------


class TestConstructorParameters:
    """Tests for constructor parameter handling."""

    def test_default_parameters(self) -> None:
        """Default parameters should be 100 max pages and 30s timeout."""
        detector = VisualContentDetector()
        assert detector._max_visual_pages == 100
        assert detector._page_timeout_seconds == 30.0

    def test_custom_parameters(self) -> None:
        """Custom parameters should be stored correctly."""
        detector = VisualContentDetector(
            max_visual_pages=50, page_timeout_seconds=15.0
        )
        assert detector._max_visual_pages == 50
        assert detector._page_timeout_seconds == 15.0


# ---------------------------------------------------------------------------
# Tests: Classification Logic
# ---------------------------------------------------------------------------


class TestClassificationLogic:
    """Tests for the _classify_page method."""

    def test_page_with_only_images_classified_as_diagram(
        self, detector: VisualContentDetector
    ) -> None:
        """A page with images but no specific drawing patterns → diagram."""
        pdf_bytes = _create_image_pdf()
        results = detector.detect_visual_pages(pdf_bytes, "application/pdf")

        # Image-only pages should be classified as DIAGRAM
        for info in results:
            assert info.visual_type == VisualType.DIAGRAM
