"""Visual Content Detector service for identifying visual pages in documents.

Analyzes PDF and DOCX document pages to detect pages containing diagrams,
flowcharts, charts, and other visual elements that warrant vision model
interpretation. Uses text-area ratio heuristics and image/drawing object
detection to classify pages.

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md
    - Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
    - PyMuPDF (fitz) for PDF page analysis and rendering
    - python-docx for DOCX image detection
"""

import logging
import signal
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import fitz

logger = logging.getLogger(__name__)


class VisualType(str, Enum):
    """Classification of visual content on a page."""

    FLOWCHART = "flowchart"
    CHART = "chart"
    DIAGRAM = "diagram"
    MIXED = "mixed"


@dataclass
class VisualPageInfo:
    """Metadata about a detected visual page.

    Attributes:
        page_number: 0-indexed page number in the document.
        visual_type: Classification of the visual content.
        width: Page width in points.
        height: Page height in points.
        text_area_ratio: Ratio of text area to total page area (0.0-1.0).
    """

    page_number: int
    visual_type: VisualType
    width: float
    height: float
    text_area_ratio: float


class _PageTimeoutError(Exception):
    """Raised when page processing exceeds the timeout."""


def _timeout_handler(signum: int, frame: object) -> None:
    """Signal handler for page processing timeout."""
    raise _PageTimeoutError("Page processing timed out")


class VisualContentDetector:
    """Detects pages containing diagrams, flowcharts, and visual elements.

    Analyzes PDF/DOCX pages by comparing extractable text area to total
    page area. Pages with text_area_ratio < 0.3 AND containing image/drawing
    objects are classified as visual content.

    Args:
        max_visual_pages: Maximum visual pages to process per document (default 100).
        page_timeout_seconds: Timeout per page analysis in seconds (default 30).
    """

    TEXT_AREA_THRESHOLD = 0.3
    """Pages with text_area_ratio below this are candidates for visual content."""

    def __init__(
        self,
        max_visual_pages: int = 100,
        page_timeout_seconds: float = 30.0,
    ) -> None:
        self._max_visual_pages = max_visual_pages
        self._page_timeout_seconds = page_timeout_seconds

    def detect_visual_pages(
        self,
        file_bytes: bytes,
        content_type: str,
    ) -> list[VisualPageInfo]:
        """Analyze document pages for visual content.

        Processes pages sequentially after text extraction. Each page is
        analyzed within page_timeout_seconds; pages exceeding the timeout
        are skipped with a warning. Renders pages at 150 DPI for detection.

        Args:
            file_bytes: Raw document file content.
            content_type: MIME type (application/pdf or
                application/vnd.openxmlformats-officedocument.wordprocessingml.document).

        Returns:
            List of VisualPageInfo for pages classified as visual content,
            capped at max_visual_pages.
        """
        if content_type == "application/pdf":
            return self._detect_pdf_visual_pages(file_bytes)
        elif content_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/docx",
        ):
            return self._detect_docx_visual_pages(file_bytes)
        else:
            logger.warning(
                "Unsupported content type for visual detection: %s", content_type
            )
            return []

    def _detect_pdf_visual_pages(self, file_bytes: bytes) -> list[VisualPageInfo]:
        """Detect visual pages in a PDF document.

        Args:
            file_bytes: Raw PDF file bytes.

        Returns:
            List of VisualPageInfo for detected visual pages.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF (fitz) not available, skipping visual detection")
            return []

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception as e:
            logger.error("Failed to open PDF for visual detection: %s", e)
            return []

        visual_pages: list[VisualPageInfo] = []

        for page_num in range(doc.page_count):
            if len(visual_pages) >= self._max_visual_pages:
                logger.warning(
                    "Visual page cap reached (%d). Skipping remaining pages "
                    "(%d total pages in document).",
                    self._max_visual_pages,
                    doc.page_count,
                )
                break

            page = doc[page_num]
            result = self._process_pdf_page_with_timeout(page)
            if result is not None:
                visual_pages.append(result)

        doc.close()
        return visual_pages

    def _process_pdf_page_with_timeout(
        self, page: "fitz.Page"
    ) -> VisualPageInfo | None:
        """Process a single PDF page with timeout enforcement.

        Args:
            page: PyMuPDF page object.

        Returns:
            VisualPageInfo if the page is visual, None otherwise.
        """
        # Use signal-based timeout on Unix systems
        old_handler = None
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(self._page_timeout_seconds))
        except (ValueError, OSError):
            # signal.alarm not available (e.g., non-main thread or Windows)
            old_handler = None

        try:
            return self._analyze_pdf_page(page)
        except _PageTimeoutError:
            logger.warning(
                "Page %d processing timed out after %.1f seconds, skipping.",
                page.number,
                self._page_timeout_seconds,
            )
            return None
        except Exception as e:
            logger.error("Error processing page %d: %s", page.number, e)
            return None
        finally:
            try:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            except (ValueError, OSError):
                pass

    def _analyze_pdf_page(self, page: "fitz.Page") -> VisualPageInfo | None:
        """Analyze a single PDF page for visual content.

        Computes text_area_ratio and checks for image/drawing objects.
        If text_area_ratio < 0.3 AND has images/drawings, classifies the page.

        Args:
            page: PyMuPDF page object.

        Returns:
            VisualPageInfo if the page qualifies as visual, None otherwise.
        """
        rect = page.rect
        page_area = rect.width * rect.height

        if page_area <= 0:
            return None

        # Compute text area ratio by summing text block bounding boxes
        text_area = self._compute_text_area(page)
        text_area_ratio = text_area / page_area if page_area > 0 else 1.0

        # Check if page meets the low-text threshold
        if text_area_ratio >= self.TEXT_AREA_THRESHOLD:
            return None

        # Check for image or drawing objects on the page
        has_images = self._page_has_images_or_drawings(page)

        if not has_images:
            # Req 1.7: Low text but no images/drawings → skip with debug log
            logger.debug(
                "Page %d has low text ratio (%.3f) but no image/drawing objects, "
                "skipping visual classification.",
                page.number,
                text_area_ratio,
            )
            return None

        # Classify the visual content type
        visual_type = self._classify_page(page)
        if visual_type is None:
            # Fallback: if classification returns None but we have images,
            # default to DIAGRAM
            visual_type = VisualType.DIAGRAM

        return VisualPageInfo(
            page_number=page.number,
            visual_type=visual_type,
            width=rect.width,
            height=rect.height,
            text_area_ratio=text_area_ratio,
        )

    def _compute_text_area(self, page: "fitz.Page") -> float:
        """Compute the total area covered by text blocks on a page.

        Uses PyMuPDF's text extraction with "blocks" option to get
        bounding rectangles of text content.

        Args:
            page: PyMuPDF page object.

        Returns:
            Total text area in square points.
        """
        text_blocks = page.get_text("blocks")
        total_text_area = 0.0

        for block in text_blocks:
            # block format: (x0, y0, x1, y1, text, block_no, block_type)
            # block_type 0 = text, 1 = image
            if len(block) >= 7 and block[6] == 0:  # text block
                x0, y0, x1, y1 = block[0], block[1], block[2], block[3]
                block_area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
                total_text_area += block_area

        return total_text_area

    def _page_has_images_or_drawings(self, page: "fitz.Page") -> bool:
        """Check if a page contains image or drawing objects.

        Checks for embedded images via get_images() and vector drawings
        via get_drawings().

        Args:
            page: PyMuPDF page object.

        Returns:
            True if the page has at least one image or drawing object.
        """
        # Check for embedded images
        images = page.get_images(full=True)
        if images:
            return True

        # Check for vector drawings (paths, lines, curves)
        drawings = page.get_drawings()
        if drawings:
            return True

        return False

    def _classify_page(self, page: "fitz.Page") -> VisualType | None:
        """Classify a single page's visual content type.

        Returns None if the page does not meet visual content criteria.
        Classification logic:
        - "flowchart" if arrow connectors between shapes detected
        - "chart" if axis lines or data plot elements detected
        - "diagram" if shapes/images without arrow connectors
        - "mixed" if multiple categories match

        Args:
            page: PyMuPDF page object.

        Returns:
            VisualType classification or None if not visual.
        """
        drawings = page.get_drawings()
        if not drawings:
            # No drawings; if page has images only, classify as diagram
            images = page.get_images(full=True)
            if images:
                return VisualType.DIAGRAM
            return None

        has_arrows = self._detect_arrows(drawings)
        has_axis_lines = self._detect_axis_lines(drawings, page.rect)
        has_shapes = self._detect_shapes(drawings)

        categories_matched = sum([has_arrows, has_axis_lines, has_shapes])

        if categories_matched == 0:
            # Has drawings but none match specific categories
            return VisualType.DIAGRAM

        if categories_matched > 1:
            # Multiple categories detected
            if has_arrows and has_axis_lines:
                return VisualType.MIXED
            if has_arrows and has_shapes:
                return VisualType.FLOWCHART
            return VisualType.MIXED

        # Single category
        if has_arrows:
            return VisualType.FLOWCHART
        if has_axis_lines:
            return VisualType.CHART
        if has_shapes:
            return VisualType.DIAGRAM

        return VisualType.DIAGRAM

    def _detect_arrows(self, drawings: list[dict]) -> bool:
        """Detect arrow connectors in drawing objects.

        Arrows are identified by paths that end with a triangular
        arrowhead pattern (short line segments forming a V or triangle
        at the end of a longer line).

        Args:
            drawings: List of drawing dictionaries from page.get_drawings().

        Returns:
            True if arrow-like connectors are detected.
        """
        arrow_count = 0

        for drawing in drawings:
            items = drawing.get("items", [])
            if not items:
                continue

            # Look for line segments that could be arrows
            # Arrows typically have: a line segment + a small triangular head
            has_line = False
            has_short_segments = 0

            for item in items:
                if item[0] == "l":  # line segment
                    # item format: ("l", Point(start), Point(end))
                    start = item[1]
                    end = item[2]
                    length = (
                        (end.x - start.x) ** 2 + (end.y - start.y) ** 2
                    ) ** 0.5
                    if length > 20:
                        has_line = True
                    elif length > 2:
                        has_short_segments += 1

            # Arrow pattern: a line with 2+ short segments (arrowhead)
            if has_line and has_short_segments >= 2:
                arrow_count += 1

        # Consider arrows present if we find at least 2 arrow-like patterns
        return arrow_count >= 2

    def _detect_axis_lines(
        self, drawings: list[dict], page_rect: "fitz.Rect"
    ) -> bool:
        """Detect axis lines typical of charts and graphs.

        Axis lines are identified as long horizontal or vertical lines
        near the edges or center of the page, typically forming an L-shape
        (x-axis and y-axis).

        Args:
            drawings: List of drawing dictionaries from page.get_drawings().
            page_rect: The page rectangle for relative positioning.

        Returns:
            True if chart axis lines are detected.
        """
        page_width = page_rect.width
        page_height = page_rect.height
        min_axis_length = min(page_width, page_height) * 0.3

        horizontal_lines: list[tuple[float, float, float, float]] = []
        vertical_lines: list[tuple[float, float, float, float]] = []

        for drawing in drawings:
            items = drawing.get("items", [])
            for item in items:
                if item[0] == "l":  # line segment
                    start = item[1]
                    end = item[2]
                    dx = abs(end.x - start.x)
                    dy = abs(end.y - start.y)
                    length = (dx**2 + dy**2) ** 0.5

                    if length < min_axis_length:
                        continue

                    # Horizontal line (small vertical deviation)
                    if dy < 3 and dx >= min_axis_length:
                        horizontal_lines.append(
                            (start.x, start.y, end.x, end.y)
                        )
                    # Vertical line (small horizontal deviation)
                    elif dx < 3 and dy >= min_axis_length:
                        vertical_lines.append(
                            (start.x, start.y, end.x, end.y)
                        )

        # Chart pattern: at least one horizontal and one vertical axis line
        return len(horizontal_lines) >= 1 and len(vertical_lines) >= 1

    def _detect_shapes(self, drawings: list[dict]) -> bool:
        """Detect geometric shapes (rectangles, circles) in drawings.

        Shapes are identified by closed paths (rectangles via "re" items)
        or curves that form closed shapes.

        Args:
            drawings: List of drawing dictionaries from page.get_drawings().

        Returns:
            True if geometric shapes are detected (at least 3 shapes).
        """
        shape_count = 0

        for drawing in drawings:
            items = drawing.get("items", [])
            has_rect = False
            has_curve = False
            is_closed = drawing.get("closePath", False)

            for item in items:
                if item[0] == "re":  # rectangle
                    has_rect = True
                elif item[0] == "c":  # cubic bezier curve
                    has_curve = True
                elif item[0] == "qu":  # quad (filled rectangle)
                    has_rect = True

            if has_rect:
                shape_count += 1
            elif has_curve and is_closed:
                shape_count += 1

        # Consider shapes present if we find at least 3
        return shape_count >= 3

    def _detect_docx_visual_pages(self, file_bytes: bytes) -> list[VisualPageInfo]:
        """Detect visual content in a DOCX document.

        DOCX documents don't have traditional pages, so we treat each
        paragraph/section containing images as a "visual page". We detect
        inline images and drawing objects in paragraphs.

        Args:
            file_bytes: Raw DOCX file bytes.

        Returns:
            List of VisualPageInfo for detected visual content sections.
        """
        try:
            from docx import Document
            from io import BytesIO
        except ImportError:
            logger.warning("python-docx not available, skipping DOCX visual detection")
            return []

        try:
            doc = Document(BytesIO(file_bytes))
        except Exception as e:
            logger.error("Failed to open DOCX for visual detection: %s", e)
            return []

        visual_pages: list[VisualPageInfo] = []
        current_page = 0
        total_chars = 0
        image_paragraphs: list[int] = []

        # Scan paragraphs for images
        for para_idx, paragraph in enumerate(doc.paragraphs):
            total_chars += len(paragraph.text)

            # Check for inline images in runs
            has_image = self._paragraph_has_images(paragraph)
            if has_image:
                image_paragraphs.append(para_idx)

        if not image_paragraphs:
            return []

        # Estimate pages based on character count (~3000 chars per page)
        chars_per_page = 3000
        total_pages = max(1, total_chars // chars_per_page + 1)

        # Map image paragraphs to estimated page numbers
        chars_so_far = 0
        para_page_map: dict[int, int] = {}
        for para_idx, paragraph in enumerate(doc.paragraphs):
            para_page_map[para_idx] = min(
                chars_so_far // chars_per_page, total_pages - 1
            )
            chars_so_far += len(paragraph.text)

        # Group images by estimated page
        pages_with_images: set[int] = set()
        for para_idx in image_paragraphs:
            page_num = para_page_map.get(para_idx, 0)
            pages_with_images.add(page_num)

        # Create VisualPageInfo for each page with images
        for page_num in sorted(pages_with_images):
            if len(visual_pages) >= self._max_visual_pages:
                logger.warning(
                    "Visual page cap reached (%d) for DOCX document.",
                    self._max_visual_pages,
                )
                break

            # For DOCX, estimate text_area_ratio based on surrounding text
            # Pages with images typically have lower text ratios
            text_area_ratio = 0.2  # Heuristic for image-heavy pages

            visual_pages.append(
                VisualPageInfo(
                    page_number=page_num,
                    visual_type=VisualType.DIAGRAM,
                    width=612.0,  # Standard letter width in points
                    height=792.0,  # Standard letter height in points
                    text_area_ratio=text_area_ratio,
                )
            )

        return visual_pages

    def _paragraph_has_images(self, paragraph: object) -> bool:
        """Check if a DOCX paragraph contains inline images or drawings.

        Inspects the paragraph's XML for image relationships and
        drawing elements.

        Args:
            paragraph: A python-docx Paragraph object.

        Returns:
            True if the paragraph contains at least one image or drawing.
        """
        try:
            from docx.oxml.ns import qn
        except ImportError:
            return False

        # Check for inline images (blipFill elements)
        para_xml = paragraph._element  # type: ignore[attr-defined]

        # Look for drawing elements containing images
        drawings = para_xml.findall(f".//{qn('w:drawing')}")
        if drawings:
            return True

        # Look for inline shape elements (VML)
        picts = para_xml.findall(f".//{qn('w:pict')}")
        if picts:
            return True

        # Look for embedded objects
        objects = para_xml.findall(f".//{qn('w:object')}")
        if objects:
            return True

        return False
