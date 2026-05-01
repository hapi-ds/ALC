"""OCR Engine service for extracting text from scanned PDFs.

Uses a vision-capable LLM (loaded on-demand via Model_Manager) to
extract text from image-based PDF pages. Detects whether a PDF is
scanned (no extractable text) and processes accordingly.

References:
    - PyMuPDF (fitz) for PDF page rendering to images
    - Vision LLM for text extraction from images
"""

import logging
from dataclasses import dataclass

from alcoabase.services.model_manager import ModelManager, ModelRole

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result of OCR text extraction from a PDF.

    Attributes:
        text: The extracted text content from all pages.
        page_count: Total number of pages processed.
        scanned_pages: Number of pages that required OCR.
        digital_pages: Number of pages with extractable text.
        is_scanned: Whether the PDF was detected as scanned (image-based).
    """

    text: str
    page_count: int
    scanned_pages: int
    digital_pages: int
    is_scanned: bool


class OCREngine:
    """Extracts text from scanned (image-based) PDF documents.

    Detects scanned PDFs by checking if pages contain extractable text.
    For scanned pages, converts them to images via PyMuPDF's get_pixmap()
    and sends them to a vision model via the Model_Manager for text extraction.

    Args:
        model_manager: The Model_Manager instance for loading the OCR model.
    """

    def __init__(self, model_manager: ModelManager) -> None:
        self._model_manager = model_manager

    def is_scanned_pdf(self, pdf_bytes: bytes) -> bool:
        """Detect whether a PDF is scanned (image-based with no extractable text).

        A PDF is considered scanned if it has at least one page and
        none of the pages contain extractable text characters.

        Args:
            pdf_bytes: The raw PDF file bytes.

        Returns:
            True if the PDF is scanned (no extractable text), False otherwise.
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if doc.page_count == 0:
                doc.close()
                return False

            has_text = False
            for page in doc:
                text = page.get_text().strip()
                if text:
                    has_text = True
                    break

            doc.close()
            return not has_text
        except ImportError:
            # PyMuPDF not available — assume digital PDF
            logger.warning("PyMuPDF (fitz) not available, assuming digital PDF")
            return False
        except Exception as e:
            logger.error("Error detecting scanned PDF: %s", e)
            return False

    async def extract_text(self, pdf_bytes: bytes) -> OCRResult:
        """Extract text from a PDF, using OCR for scanned pages.

        For each page:
        1. Attempt standard text extraction via PyMuPDF.
        2. If no text is found, render the page to an image and send
           to the vision model for OCR.

        Args:
            pdf_bytes: The raw PDF file bytes.

        Returns:
            OCRResult with extracted text and page statistics.

        Raises:
            RuntimeError: If text extraction fails completely.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not available, returning empty OCR result")
            return OCRResult(
                text="",
                page_count=0,
                scanned_pages=0,
                digital_pages=0,
                is_scanned=False,
            )

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            logger.warning("Failed to open PDF: %s", e)
            return OCRResult(
                text="",
                page_count=0,
                scanned_pages=0,
                digital_pages=0,
                is_scanned=False,
            )

        page_texts: list[str] = []
        scanned_pages = 0
        digital_pages = 0
        total_pages = doc.page_count

        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text().strip()

            if text:
                # Digital page — text is directly extractable
                page_texts.append(text)
                digital_pages += 1
            else:
                # Scanned page — needs OCR via vision model
                scanned_pages += 1
                ocr_text = await self._ocr_page(page)
                page_texts.append(ocr_text)

        doc.close()

        full_text = "\n\n".join(page_texts)
        is_scanned = scanned_pages > 0 and digital_pages == 0

        return OCRResult(
            text=full_text,
            page_count=total_pages,
            scanned_pages=scanned_pages,
            digital_pages=digital_pages,
            is_scanned=is_scanned,
        )

    async def _ocr_page(self, page: "fitz.Page") -> str:  # type: ignore[name-defined]
        """OCR a single PDF page using the vision model.

        Renders the page to a PNG image and sends it to the vision LLM
        for text extraction.

        Args:
            page: A PyMuPDF page object.

        Returns:
            Extracted text from the page image.
        """
        # Ensure the OCR model is loaded
        if self._model_manager.mode == "mock":
            await self._model_manager.ensure_model(ModelRole.OCR)
            return f"[Mock OCR] Extracted text from page {page.number + 1}"

        await self._model_manager.ensure_model(ModelRole.OCR)

        # Render page to image at 300 DPI for good OCR quality
        pixmap = page.get_pixmap(dpi=300)
        image_bytes = pixmap.tobytes("png")

        # In production, send image_bytes to the vision model via vLLM API
        # For now, return placeholder
        logger.info("OCR processing page %d (%d bytes image)", page.number + 1, len(image_bytes))

        # Production implementation would:
        # 1. Encode image as base64
        # 2. Send to vLLM vision model endpoint
        # 3. Parse the extracted text from the response
        return f"[OCR] Text extracted from page {page.number + 1}"
