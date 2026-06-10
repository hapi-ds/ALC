"""Content chunking for literature embedding generation.

Extends the existing KnowledgeService.chunk_text() logic with literature-specific
features: section-boundary awareness, title/heading prepending, and
per-company configurable chunk sizes.

Tokens are approximated by whitespace splitting, consistent with
KnowledgeService.chunk_text().

References:
    - Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 1.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from alcoabase.literature.ingestion.schemas.structured_content import StructuredContent


@dataclass(frozen=True)
class ContentChunk:
    """A single chunk of content ready for embedding.

    Attributes:
        text: The chunk text (with prepended context).
        chunk_index: 0-based position in the document's chunk sequence.
        section_heading: Source section heading (empty for abstract).
        source_field: 'abstract' or 'body'.
    """

    text: str
    chunk_index: int
    section_heading: str
    source_field: str


# Regex pattern for heading boundaries (e.g., "## Heading" or "1. Heading")
_HEADING_PATTERN = re.compile(
    r"(?:^|\n)(?=#{1,6}\s|\d+\.\s|\d+\.\d+\s)", re.MULTILINE
)

# Sentence boundary: period, question mark, or exclamation mark followed by whitespace
_SENTENCE_BOUNDARY = re.compile(r"[.?!]\s+")


class ChunkingPipeline:
    """Segments StructuredContent into ContentChunks for embedding.

    Reuses KnowledgeService.chunk_text() logic for the core splitting algorithm,
    adding section-boundary awareness and title/heading prepending.
    """

    def __init__(
        self,
        chunk_size_tokens: int = 512,
        chunk_overlap_tokens: int = 50,
        max_context_tokens: int = 64,
    ) -> None:
        """Initialize with chunking parameters.

        Args:
            chunk_size_tokens: Maximum tokens per chunk (default 512).
            chunk_overlap_tokens: Overlap between consecutive chunks (default 50).
            max_context_tokens: Maximum tokens for prepended title/heading (default 64).

        Raises:
            ValueError: If overlap >= chunk_size_tokens.
        """
        if chunk_overlap_tokens >= chunk_size_tokens:
            raise ValueError(
                f"Overlap ({chunk_overlap_tokens}) must be less than "
                f"chunk_size ({chunk_size_tokens})"
            )
        self._chunk_size = chunk_size_tokens
        self._overlap = chunk_overlap_tokens
        self._max_context_tokens = max_context_tokens

    def chunk_structured_content(
        self,
        content: StructuredContent,
        max_chunks: int = 500,
        embed_abstract_only: bool = False,
    ) -> list[ContentChunk]:
        """Chunk a StructuredContent into ContentChunks.

        Processing order:
            1. Abstract -> chunks (always if non-empty)
            2. Body sections -> chunks (unless embed_abstract_only=True)

        Each chunk has title + section_heading prepended (max 64 tokens).
        Respects section boundaries where possible.
        Truncates to max_chunks if exceeded.

        Args:
            content: StructuredContent from Phase 9.2.
            max_chunks: Maximum chunks to produce.
            embed_abstract_only: If True, skip body sections.

        Returns:
            Ordered list of ContentChunks.
        """
        chunks: list[ContentChunk] = []
        title = content.extracted_title
        chunk_index = 0

        # 1. Process abstract
        if content.extracted_abstract and content.extracted_abstract.strip():
            abstract_chunks = self._chunk_text_with_context(
                text=content.extracted_abstract,
                title=title,
                section_heading="",
                source_field="abstract",
                start_index=chunk_index,
            )
            chunks.extend(abstract_chunks)
            chunk_index += len(abstract_chunks)

        # 2. Process body sections (unless abstract-only mode)
        if not embed_abstract_only:
            for section in content.body_sections:
                if not section.text or not section.text.strip():
                    continue

                section_chunks = self._chunk_section(
                    text=section.text,
                    title=title,
                    section_heading=section.heading,
                    start_index=chunk_index,
                )
                chunks.extend(section_chunks)
                chunk_index += len(section_chunks)

        # Truncate to max_chunks
        return chunks[:max_chunks]

    def chunk_abstract(
        self,
        abstract: str,
        title: str = "",
    ) -> list[ContentChunk]:
        """Chunk an abstract text (for abstract-only embedding).

        Used when an IngestionRecord has abstract but no full-text.

        Args:
            abstract: Abstract text.
            title: Document title for prepending.

        Returns:
            List of ContentChunks from the abstract.
        """
        if not abstract or not abstract.strip():
            return []

        return self._chunk_text_with_context(
            text=abstract,
            title=title,
            section_heading="",
            source_field="abstract",
            start_index=0,
        )

    def _prepend_context(
        self,
        chunk_text: str,
        title: str,
        section_heading: str,
    ) -> str:
        """Prepend title and section heading to a chunk.

        Context is truncated to max_context_tokens at word boundary.
        Format: "title | heading | chunk_text" (omitting empty parts).

        Args:
            chunk_text: Raw chunk text.
            title: Document title.
            section_heading: Section heading.

        Returns:
            Chunk text with prepended context.
        """
        # Build context parts
        parts = [p for p in [title.strip(), section_heading.strip()] if p]
        if not parts:
            return chunk_text

        context = " | ".join(parts)
        context_tokens = context.split()

        # Truncate to max_context_tokens at word boundary
        if len(context_tokens) > self._max_context_tokens:
            context = " ".join(context_tokens[: self._max_context_tokens])

        return f"{context} | {chunk_text}"

    def _split_at_section_boundaries(
        self,
        text: str,
    ) -> list[str]:
        """Split text at paragraph or section heading boundaries.

        Identifies boundaries as double-newlines or heading patterns
        (markdown headings, numbered headings).

        Args:
            text: Section text to split.

        Returns:
            List of paragraph/subsection texts.
        """
        # First split on double-newlines (paragraph breaks)
        paragraphs = re.split(r"\n\n+", text)

        # Further split paragraphs that contain heading patterns
        result: list[str] = []
        for para in paragraphs:
            if not para.strip():
                continue
            # Check if this paragraph contains heading patterns
            sub_parts = _HEADING_PATTERN.split(para)
            for part in sub_parts:
                stripped = part.strip()
                if stripped:
                    result.append(stripped)

        return result if result else [text.strip()] if text.strip() else []

    def _split_at_sentence_boundary(
        self,
        text: str,
        max_tokens: int,
    ) -> tuple[str, str]:
        """Split text at nearest sentence boundary within token limit.

        Falls back to word boundary if no sentence boundary found.

        Args:
            text: Text to split.
            max_tokens: Maximum tokens for the first part.

        Returns:
            Tuple of (first_part, remainder).
        """
        tokens = text.split()

        if len(tokens) <= max_tokens:
            return (text.strip(), "")

        # Look for sentence boundary within the token limit
        # Build text from tokens up to max_tokens and find last sentence end
        candidate_text = " ".join(tokens[:max_tokens])

        # Find all sentence boundaries in the candidate text
        last_boundary_pos = -1
        for match in _SENTENCE_BOUNDARY.finditer(candidate_text):
            last_boundary_pos = match.start() + 1  # Include the punctuation

        if last_boundary_pos > 0:
            # Split at the last sentence boundary
            first_part = candidate_text[:last_boundary_pos].strip()
            # Reconstruct remainder from remaining tokens
            first_token_count = len(first_part.split())
            remainder = " ".join(tokens[first_token_count:])
            return (first_part, remainder)

        # Fallback: split at word boundary (max_tokens)
        first_part = " ".join(tokens[:max_tokens])
        remainder = " ".join(tokens[max_tokens:])
        return (first_part, remainder)

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks using whitespace token approximation.

        Reuses the logic from KnowledgeService.chunk_text():
        - Tokens are whitespace-delimited words
        - Each chunk has at most chunk_size tokens
        - Consecutive chunks share overlap tokens

        Args:
            text: Input text to chunk.

        Returns:
            List of text chunks. Returns empty list for empty/whitespace input.
        """
        if not text or not text.strip():
            return []

        tokens = text.split()

        if len(tokens) <= self._chunk_size:
            return [" ".join(tokens)]

        chunks: list[str] = []
        step = self._chunk_size - self._overlap
        i = 0

        while i < len(tokens):
            chunk_tokens = tokens[i : i + self._chunk_size]
            chunks.append(" ".join(chunk_tokens))

            if i + self._chunk_size >= len(tokens):
                break
            i += step

        return chunks

    def _chunk_section(
        self,
        text: str,
        title: str,
        section_heading: str,
        start_index: int,
    ) -> list[ContentChunk]:
        """Chunk a body section respecting section boundaries.

        Strategy:
            1. Split at section boundaries (double-newlines, headings)
            2. For each paragraph that fits in chunk_size, keep as single chunk
            3. For paragraphs exceeding chunk_size, split at sentence boundary
            4. Apply overlap between chunks from the same section

        Args:
            text: Section body text.
            title: Document title for context prepending.
            section_heading: Section heading for context prepending.
            start_index: Starting chunk_index for this section.

        Returns:
            List of ContentChunks from this section.
        """
        paragraphs = self._split_at_section_boundaries(text)
        raw_chunks: list[str] = []

        for paragraph in paragraphs:
            tokens = paragraph.split()
            if len(tokens) <= self._chunk_size:
                # Paragraph fits in a single chunk
                raw_chunks.append(paragraph)
            else:
                # Paragraph exceeds chunk size — split with sentence awareness
                remaining = paragraph
                while remaining.strip():
                    first, remaining = self._split_at_sentence_boundary(
                        remaining, self._chunk_size
                    )
                    if first.strip():
                        raw_chunks.append(first)
                    if not remaining.strip():
                        break

        # Now apply overlap-aware chunking across the concatenated section text
        # to maintain overlap consistency with KnowledgeService
        section_text = " ".join(raw_chunks)
        overlapped_chunks = self._chunk_text(section_text)

        # Build ContentChunk list with prepended context
        content_chunks: list[ContentChunk] = []
        for i, chunk in enumerate(overlapped_chunks):
            prepended = self._prepend_context(chunk, title, section_heading)
            content_chunks.append(
                ContentChunk(
                    text=prepended,
                    chunk_index=start_index + i,
                    section_heading=section_heading,
                    source_field="body",
                )
            )

        return content_chunks

    def _chunk_text_with_context(
        self,
        text: str,
        title: str,
        section_heading: str,
        source_field: str,
        start_index: int,
    ) -> list[ContentChunk]:
        """Chunk text and wrap each chunk with context as a ContentChunk.

        Args:
            text: Raw text to chunk.
            title: Document title for prepending.
            section_heading: Section heading for prepending.
            source_field: 'abstract' or 'body'.
            start_index: Starting chunk_index.

        Returns:
            List of ContentChunks.
        """
        raw_chunks = self._chunk_text(text)
        content_chunks: list[ContentChunk] = []

        for i, chunk in enumerate(raw_chunks):
            prepended = self._prepend_context(chunk, title, section_heading)
            content_chunks.append(
                ContentChunk(
                    text=prepended,
                    chunk_index=start_index + i,
                    section_heading=section_heading,
                    source_field=source_field,
                )
            )

        return content_chunks
