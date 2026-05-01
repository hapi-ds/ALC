"""Unit tests for the OCR Engine service.

Tests scanned vs. digital PDF detection and text extraction.

References:
    - Task 18.15: Write unit tests for OCR_Engine correctly detects
      scanned vs. digital PDFs, extracts text from scanned pages
"""

import pytest

from alcoabase.services.model_manager import ModelManager, ModelRole
from alcoabase.services.ocr_engine import OCREngine, OCRResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockSettings:
    """Mock settings for testing."""

    model_chat_name = "test-chat-model"
    model_chat_path = "/models/test-chat"
    model_chat_max_gpu_memory_gb = 60
    model_embedding_name = "test-embedding-model"
    model_embedding_path = "/models/test-embedding"
    model_embedding_dimension = 1024
    model_ocr_name = "test-ocr-model"
    model_ocr_path = "/models/test-ocr"
    gpu_device_id = 0
    model_manager_mode = "mock"
    vllm_base_url = "http://localhost:8000"


@pytest.fixture
def model_manager() -> ModelManager:
    """Create a ModelManager in mock mode."""
    return ModelManager(settings=MockSettings())


@pytest.fixture
def ocr_engine(model_manager: ModelManager) -> OCREngine:
    """Create an OCREngine with mock ModelManager."""
    return OCREngine(model_manager=model_manager)


def _create_digital_pdf() -> bytes:
    """Create a simple digital PDF with extractable text using ReportLab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        import io

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.drawString(100, 700, "This is a digital PDF with extractable text.")
        c.drawString(100, 680, "It contains multiple lines of content.")
        c.showPage()
        c.save()
        return buffer.getvalue()
    except ImportError:
        pytest.skip("ReportLab not available for PDF generation")


def _create_image_only_pdf() -> bytes:
    """Create a PDF that contains only an image (simulating a scanned document).

    Uses ReportLab to embed a small image into a PDF without any text layer.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        import io
        from PIL import Image

        # Create a small test image
        img = Image.new("RGB", (200, 100), color="white")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format="PNG")
        img_buffer.seek(0)

        # Create PDF with only the image (no text)
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        c.drawImage(ImageReader(img_buffer), 100, 600, width=200, height=100)
        c.showPage()
        c.save()
        return pdf_buffer.getvalue()
    except ImportError:
        pytest.skip("ReportLab or Pillow not available for PDF generation")


# ---------------------------------------------------------------------------
# Tests: Scanned PDF Detection
# ---------------------------------------------------------------------------


class TestScannedPDFDetection:
    """Tests for is_scanned_pdf detection logic."""

    def test_digital_pdf_detected_as_not_scanned(
        self, ocr_engine: OCREngine
    ) -> None:
        """A PDF with extractable text should not be detected as scanned."""
        pdf_bytes = _create_digital_pdf()
        assert ocr_engine.is_scanned_pdf(pdf_bytes) is False

    def test_image_only_pdf_detected_as_scanned(
        self, ocr_engine: OCREngine
    ) -> None:
        """A PDF with only images (no text) should be detected as scanned."""
        pdf_bytes = _create_image_only_pdf()
        assert ocr_engine.is_scanned_pdf(pdf_bytes) is True

    def test_empty_bytes_returns_false(self, ocr_engine: OCREngine) -> None:
        """Empty/invalid bytes should return False (not crash)."""
        assert ocr_engine.is_scanned_pdf(b"") is False

    def test_invalid_pdf_returns_false(self, ocr_engine: OCREngine) -> None:
        """Invalid PDF content should return False gracefully."""
        assert ocr_engine.is_scanned_pdf(b"not a pdf file") is False


# ---------------------------------------------------------------------------
# Tests: Text Extraction
# ---------------------------------------------------------------------------


class TestTextExtraction:
    """Tests for extract_text functionality."""

    @pytest.mark.asyncio
    async def test_extract_text_from_digital_pdf(
        self, ocr_engine: OCREngine
    ) -> None:
        """Should extract text directly from a digital PDF."""
        pdf_bytes = _create_digital_pdf()
        result = await ocr_engine.extract_text(pdf_bytes)

        assert isinstance(result, OCRResult)
        assert result.page_count == 1
        assert result.digital_pages == 1
        assert result.scanned_pages == 0
        assert result.is_scanned is False
        assert "digital PDF" in result.text

    @pytest.mark.asyncio
    async def test_extract_text_from_scanned_pdf_uses_ocr(
        self, ocr_engine: OCREngine
    ) -> None:
        """Should use OCR (mock) for scanned PDF pages."""
        pdf_bytes = _create_image_only_pdf()
        result = await ocr_engine.extract_text(pdf_bytes)

        assert isinstance(result, OCRResult)
        assert result.page_count == 1
        assert result.scanned_pages == 1
        assert result.digital_pages == 0
        assert result.is_scanned is True
        # Mock OCR returns placeholder text
        assert "Mock OCR" in result.text

    @pytest.mark.asyncio
    async def test_extract_text_empty_pdf(
        self, ocr_engine: OCREngine
    ) -> None:
        """Should handle empty/invalid PDF gracefully."""
        result = await ocr_engine.extract_text(b"")

        # Should return empty result without crashing
        assert isinstance(result, OCRResult)
        assert result.text == ""


# ---------------------------------------------------------------------------
# Tests: Model Manager Integration
# ---------------------------------------------------------------------------


class TestModelManagerIntegration:
    """Tests for OCR Engine integration with Model Manager."""

    @pytest.mark.asyncio
    async def test_ocr_loads_ocr_model_via_model_manager(
        self, ocr_engine: OCREngine, model_manager: ModelManager
    ) -> None:
        """OCR should request the OCR model from Model Manager."""
        pdf_bytes = _create_image_only_pdf()
        await ocr_engine.extract_text(pdf_bytes)

        # After OCR, the model manager should have loaded the OCR model
        assert model_manager._current_role == ModelRole.OCR
        assert model_manager._is_ready is True

    @pytest.mark.asyncio
    async def test_digital_pdf_does_not_load_ocr_model(
        self, ocr_engine: OCREngine, model_manager: ModelManager
    ) -> None:
        """Digital PDF extraction should not load the OCR model."""
        pdf_bytes = _create_digital_pdf()
        await ocr_engine.extract_text(pdf_bytes)

        # No OCR model should be loaded for digital PDFs
        assert model_manager._current_role is None
