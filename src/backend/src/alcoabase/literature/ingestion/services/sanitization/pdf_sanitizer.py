"""PyMuPDF-based PDF text and structure extraction.

Extracts: title, abstract, section headings, body paragraphs,
figure/table captions, reference lists. Strips headers, footers,
page numbers, watermarks.

References:
    - Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from alcoabase.literature.ingestion.exceptions import SanitizationError
from alcoabase.literature.ingestion.schemas.structured_content import (
    BodySection,
    SourceFormat,
    StructuredContent,
)
from alcoabase.literature.ingestion.services.sanitization.pipeline import (
    BaseSanitizer,
)

logger = logging.getLogger(__name__)


# ─── Internal Data Structures ─────────────────────────────────────────────────


@dataclass
class _TextBlock:
    """A single text block extracted from a PDF page.

    Attributes:
        text: The text content of the block.
        font_size: The predominant font size in the block.
        is_bold: Whether the predominant font style is bold.
        page_num: Zero-based page number where the block appears.
        y_position: Vertical position on the page (top of block).
    """

    text: str
    font_size: float
    is_bold: bool
    page_num: int
    y_position: float


@dataclass
class _ExtractedSections:
    """Container for sections identified during PDF parsing.

    Attributes:
        title: Extracted document title.
        abstract: Extracted abstract text.
        headings_and_body: List of (heading, body_text) pairs.
        references: List of reference strings.
        figure_captions: Lines identified as figure captions.
        table_captions: Lines identified as table captions.
    """

    title: str = ""
    abstract: str = ""
    headings_and_body: list[tuple[str, str]] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    figure_captions: list[str] = field(default_factory=list)
    table_captions: list[str] = field(default_factory=list)


# ─── Regex Patterns ───────────────────────────────────────────────────────────

_ABSTRACT_HEADER_RE = re.compile(r"^\s*abstract\s*$", re.IGNORECASE)
_REFERENCES_HEADER_RE = re.compile(
    r"^\s*(references|bibliography|works cited)\s*$", re.IGNORECASE
)
_FIGURE_CAPTION_RE = re.compile(r"^\s*(figure|fig\.?)\s*\d+", re.IGNORECASE)
_TABLE_CAPTION_RE = re.compile(r"^\s*table\s*\d+", re.IGNORECASE)
_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*$")
_HEADING_ALL_CAPS_RE = re.compile(r"^[A-Z\s\d.:&\-]+$")


# ─── PDFSanitizer ─────────────────────────────────────────────────────────────


class PDFSanitizer(BaseSanitizer):
    """PyMuPDF-based PDF text and structure extraction.

    Uses heuristic font-size analysis to identify structural elements:
    title, abstract, section headings, body paragraphs, figure/table
    captions, and reference lists. Strips common artifacts like headers,
    footers, page numbers, and watermarks.
    """

    async def sanitize(
        self,
        content: bytes,
        content_type: str,
    ) -> StructuredContent:
        """Extract structured content from a PDF file.

        Args:
            content: Raw PDF bytes.
            content_type: Expected to be 'application/pdf'.

        Returns:
            StructuredContent with extracted sections and metadata.

        Raises:
            SanitizationError: If the PDF cannot be processed or is
                scanned-only (no extractable text).
        """
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise SanitizationError(
                f"Failed to open PDF: {exc}",
                error_type="corrupt_file",
                content_type=content_type,
            ) from exc

        try:
            blocks = self._extract_text_blocks(doc)

            # Check for scanned-only PDFs (no extractable text)
            if not blocks:
                raise SanitizationError(
                    "PDF contains no extractable text (scanned-only). "
                    "OCR processing required.",
                    error_type="ocr_required",
                    content_type=content_type,
                )

            # Strip artifacts (repeated headers/footers, page numbers)
            blocks = self._strip_artifacts(blocks, doc.page_count)

            # Parse structure
            sections = self._identify_sections(blocks, doc.page_count)

            # Build StructuredContent
            return self._build_structured_content(sections)
        finally:
            doc.close()

    # ── Private Extraction Methods ────────────────────────────────────────────

    def _extract_text_blocks(self, doc: fitz.Document) -> list[_TextBlock]:
        """Extract text blocks with font metadata from all pages.

        Args:
            doc: Opened PyMuPDF document.

        Returns:
            List of _TextBlock objects preserving reading order.
        """
        blocks: list[_TextBlock] = []

        for page_num in range(doc.page_count):
            page = doc[page_num]
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

            for block in page_dict.get("blocks", []):
                # Skip image blocks
                if block.get("type") != 0:
                    continue

                block_text_parts: list[str] = []
                font_sizes: list[float] = []
                bold_counts = 0
                total_spans = 0

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "").strip()
                        if span_text:
                            block_text_parts.append(span_text)
                            font_sizes.append(span.get("size", 12.0))
                            total_spans += 1
                            if "bold" in span.get("font", "").lower():
                                bold_counts += 1

                combined_text = " ".join(block_text_parts).strip()
                if not combined_text:
                    continue

                avg_font_size = (
                    sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
                )
                is_bold = bold_counts > total_spans / 2 if total_spans > 0 else False
                y_position = block.get("bbox", [0, 0, 0, 0])[1]

                blocks.append(
                    _TextBlock(
                        text=combined_text,
                        font_size=avg_font_size,
                        is_bold=is_bold,
                        page_num=page_num,
                        y_position=y_position,
                    )
                )

        return blocks

    def _strip_artifacts(
        self, blocks: list[_TextBlock], page_count: int
    ) -> list[_TextBlock]:
        """Remove repeated headers, footers, page numbers, and watermarks.

        Heuristic: if a short text appears on more than half the pages at
        a similar vertical position, it is likely a header or footer.

        Args:
            blocks: All extracted text blocks.
            page_count: Total number of pages in the document.

        Returns:
            Filtered list with artifacts removed.
        """
        if page_count < 2:
            # For single-page documents, only strip obvious page numbers
            return [b for b in blocks if not _PAGE_NUMBER_RE.match(b.text)]

        # Identify repeated short text (potential headers/footers)
        short_text_counter: Counter[str] = Counter()
        for block in blocks:
            stripped = block.text.strip()
            # Headers/footers are typically short
            if len(stripped) < 80:
                short_text_counter[stripped] += 1

        # Texts appearing on more than half the pages are likely artifacts
        threshold = max(2, page_count // 2)
        artifact_texts: set[str] = set()
        for text, count in short_text_counter.items():
            if count >= threshold:
                artifact_texts.add(text)

        filtered: list[_TextBlock] = []
        for block in blocks:
            stripped = block.text.strip()

            # Remove page numbers (standalone digits)
            if _PAGE_NUMBER_RE.match(stripped):
                continue

            # Remove repeated header/footer text
            if stripped in artifact_texts:
                continue

            filtered.append(block)

        return filtered

    def _identify_sections(
        self, blocks: list[_TextBlock], page_count: int
    ) -> _ExtractedSections:
        """Identify document structure from text blocks using font heuristics.

        Uses font size distribution to determine what constitutes a heading
        vs body text. Detects special sections (abstract, references) by
        keyword matching.

        Args:
            blocks: Artifact-stripped text blocks.
            page_count: Total number of pages (for context).

        Returns:
            _ExtractedSections with all identified content.
        """
        sections = _ExtractedSections()

        if not blocks:
            return sections

        # Determine font size thresholds
        all_font_sizes = [b.font_size for b in blocks]
        median_font_size = sorted(all_font_sizes)[len(all_font_sizes) // 2]
        heading_threshold = median_font_size * 1.15

        # Title: first block with significantly larger font on first page
        title_detected = False
        for block in blocks:
            if block.page_num == 0 and block.font_size > heading_threshold:
                sections.title = block.text.strip()
                title_detected = True
                break

        # If no large-font title found, use the first line of the document
        if not title_detected and blocks:
            sections.title = blocks[0].text.strip()

        # State machine for parsing body structure
        current_heading = ""
        current_body_parts: list[str] = []
        in_abstract = False
        in_references = False
        abstract_parts: list[str] = []

        for block in blocks:
            text = block.text.strip()

            # Skip the title block
            if text == sections.title and block.page_num == 0:
                continue

            # Check for figure/table captions
            if _FIGURE_CAPTION_RE.match(text):
                sections.figure_captions.append(text)
                continue
            if _TABLE_CAPTION_RE.match(text):
                sections.table_captions.append(text)
                continue

            # Check for abstract header
            if _ABSTRACT_HEADER_RE.match(text):
                in_abstract = True
                in_references = False
                continue

            # Check for references header
            if _REFERENCES_HEADER_RE.match(text):
                # Flush current section
                if current_heading or current_body_parts:
                    sections.headings_and_body.append(
                        (current_heading, " ".join(current_body_parts))
                    )
                    current_heading = ""
                    current_body_parts = []
                in_abstract = False
                in_references = True
                continue

            # If in abstract section
            if in_abstract:
                # Detect end of abstract (next heading)
                if self._is_heading(block, heading_threshold):
                    in_abstract = False
                    sections.abstract = " ".join(abstract_parts).strip()
                    # This block is a heading
                    if current_heading or current_body_parts:
                        sections.headings_and_body.append(
                            (current_heading, " ".join(current_body_parts))
                        )
                    current_heading = text
                    current_body_parts = []
                else:
                    abstract_parts.append(text)
                continue

            # If in references section
            if in_references:
                sections.references.append(text)
                continue

            # Detect headings by font size or formatting
            if self._is_heading(block, heading_threshold):
                # Flush previous section
                if current_heading or current_body_parts:
                    sections.headings_and_body.append(
                        (current_heading, " ".join(current_body_parts))
                    )
                current_heading = text
                current_body_parts = []
            else:
                current_body_parts.append(text)

        # Flush any remaining content
        if in_abstract and abstract_parts:
            sections.abstract = " ".join(abstract_parts).strip()
        if current_heading or current_body_parts:
            sections.headings_and_body.append(
                (current_heading, " ".join(current_body_parts))
            )

        return sections

    def _is_heading(self, block: _TextBlock, heading_threshold: float) -> bool:
        """Determine if a text block is a section heading.

        A block is considered a heading if:
        - Its font size exceeds the heading threshold, OR
        - It is bold and relatively short (< 100 chars), OR
        - It is ALL CAPS and short (< 80 chars)

        Args:
            block: The text block to evaluate.
            heading_threshold: Font size threshold for headings.

        Returns:
            True if the block appears to be a heading.
        """
        text = block.text.strip()

        if block.font_size > heading_threshold:
            return True

        if block.is_bold and len(text) < 100:
            return True

        if len(text) < 80 and _HEADING_ALL_CAPS_RE.match(text) and len(text) > 2:
            return True

        return False

    def _build_structured_content(
        self, sections: _ExtractedSections
    ) -> StructuredContent:
        """Construct a StructuredContent model from extracted sections.

        Assembles the raw_plaintext by joining title, abstract, and body
        section texts with newlines. Computes word_count from the result.

        Args:
            sections: Extracted document sections.

        Returns:
            Validated StructuredContent instance.

        Raises:
            SanitizationError: If the resulting content has zero words.
        """
        body_sections = [
            BodySection(heading=heading, text=body_text)
            for heading, body_text in sections.headings_and_body
            if body_text.strip()
        ]

        # Build raw_plaintext as per StructuredContent contract:
        # "\n".join([title, abstract, *body_section_texts])
        raw_parts = [
            sections.title,
            sections.abstract,
            *[s.text for s in body_sections],
        ]
        raw_plaintext = "\n".join(raw_parts)
        word_count = len(raw_plaintext.split())

        if word_count == 0:
            raise SanitizationError(
                "PDF extraction produced zero words after processing.",
                error_type="ocr_required",
                content_type="application/pdf",
            )

        return StructuredContent(
            source_format=SourceFormat.PDF,
            extracted_title=sections.title,
            extracted_abstract=sections.abstract,
            body_sections=body_sections,
            references=sections.references,
            figure_count=len(sections.figure_captions),
            table_count=len(sections.table_captions),
            word_count=word_count,
            raw_plaintext=raw_plaintext,
        )
