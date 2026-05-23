"""Knowledge Service for document indexing, embedding, and hybrid search.

This module provides:
- Document text extraction (PDF, DOCX, plain text)
- Scanned PDF detection with OCR delegation
- Text chunking with configurable overlap
- Multilingual vector embedding generation via vLLM
- OCR text extraction from scanned PDFs via vision model
- OpenSearch indexing (placeholder)
- Hybrid search combining BM25 lexical + kNN semantic (placeholder)
- ABAC filtering and CSV record exclusion on search results

References:
    - Task 12: Knowledge Service (Document Indexing + Search)
    - Requirement 13: Document Indexing and Vector Embedding
    - Requirement 14: Semantic and Hybrid Search
"""

from __future__ import annotations

import base64
import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import fitz  # PyMuPDF
from docx import Document as DocxDocument

from alcoabase.config import get_settings

if TYPE_CHECKING:
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.model_manager import ModelManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A single search result from hybrid search.

    Attributes:
        document_uuid: The Document-UUID of the matched document.
        title: Document title.
        version: Document version string (e.g., "1.0").
        excerpt: Matching text excerpt/chunk.
        relevance_score: Combined relevance score (0.0 to 1.0).
        metadata: Additional metadata (tags, language, etc.).
        document_type: Document type category (e.g., "SOP", "Policy").
        status: Document lifecycle status (e.g., "Draft", "Active").
        tags: Document tags list.
        created_at: Creation timestamp (ISO 8601 string or None).
        updated_at: Last update timestamp (ISO 8601 string or None).
    """

    document_uuid: str
    title: str
    version: str
    excerpt: str
    relevance_score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    document_type: str | None = None
    status: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class IndexedDocument:
    """Represents a document stored in the in-memory index (placeholder).

    Attributes:
        document_uuid: The Document-UUID.
        version: Version string.
        chunks: Text chunks extracted from the document.
        embeddings: Vector embeddings for each chunk.
        metadata: Document metadata (title, tags, etc.).
        is_csv_validation_record: Whether this is a CSV validation record.
        permitted_user_ids: Set of user IDs with access (for ABAC filtering).
    """

    document_uuid: str
    version: str
    chunks: list[str]
    embeddings: list[list[float]]
    metadata: dict[str, Any] = field(default_factory=dict)
    is_csv_validation_record: bool = False
    permitted_user_ids: set[int] | None = None  # None means all users


# ---------------------------------------------------------------------------
# Knowledge Service
# ---------------------------------------------------------------------------


class KnowledgeService:
    """Service for document indexing, embedding generation, and hybrid search.

    Provides text extraction from multiple formats, chunking, embedding
    generation via vLLM (or mock random vectors), OpenSearch indexing
    (placeholder), and hybrid search with ABAC filtering.

    Args:
        model_manager: ModelManager for ensuring the embedding model is loaded.
            If None, mock mode random vector generation is used.
        inference_client: InferenceClient for vLLM HTTP communication.
            If None, mock mode random vector generation is used.

    Attributes:
        _index: In-memory document index (placeholder for OpenSearch).
        _embedding_dimension: Dimension of embedding vectors from config.
    """

    def __init__(
        self,
        model_manager: ModelManager | None = None,
        inference_client: InferenceClient | None = None,
    ) -> None:
        """Initialize KnowledgeService with settings and in-memory index.

        Args:
            model_manager: Optional ModelManager for model loading.
            inference_client: Optional InferenceClient for vLLM API calls.
        """
        self._settings = get_settings()
        self._embedding_dimension: int = self._settings.model_embedding_dimension
        self._index: dict[str, IndexedDocument] = {}
        self._model_manager = model_manager
        self._inference_client = inference_client

    # -----------------------------------------------------------------------
    # Text Extraction (Task 12.1)
    # -----------------------------------------------------------------------

    def extract_text(self, file_bytes: bytes, content_type: str) -> str:
        """Extract text content from a document file.

        Supports digital PDF (PyMuPDF), DOCX (python-docx), and plain text.

        Args:
            file_bytes: Raw file content as bytes.
            content_type: MIME type of the file (e.g., "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain").

        Returns:
            Extracted text content as a string.

        Raises:
            ValueError: If the content type is not supported.
        """
        if content_type == "application/pdf":
            return self._extract_pdf_text(file_bytes)
        elif content_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/docx",
        ):
            return self._extract_docx_text(file_bytes)
        elif content_type.startswith("text/"):
            return file_bytes.decode("utf-8", errors="replace")
        else:
            raise ValueError(f"Unsupported content type: {content_type}")

    def _extract_pdf_text(self, file_bytes: bytes) -> str:
        """Extract text from a digital PDF using PyMuPDF.

        Args:
            file_bytes: Raw PDF file content.

        Returns:
            Concatenated text from all PDF pages.
        """
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text_parts: list[str] = []
        for page in doc:
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(page_text)
        doc.close()
        return "\n".join(text_parts)

    def _extract_docx_text(self, file_bytes: bytes) -> str:
        """Extract text from a DOCX file using python-docx.

        Args:
            file_bytes: Raw DOCX file content.

        Returns:
            Concatenated text from all paragraphs.
        """
        import io

        doc = DocxDocument(io.BytesIO(file_bytes))
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        return "\n".join(paragraphs)

    # -----------------------------------------------------------------------
    # Scanned PDF Detection (Task 12.2)
    # -----------------------------------------------------------------------

    def is_scanned_pdf(self, file_bytes: bytes) -> bool:
        """Detect if a PDF is scanned (image-based) with no extractable text.

        Checks each page for extractable text. If no pages contain text,
        the PDF is considered scanned.

        Args:
            file_bytes: Raw PDF file content.

        Returns:
            True if the PDF appears to be scanned (no extractable text).
        """
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        has_text = False
        for page in doc:
            page_text = page.get_text().strip()
            if page_text:
                has_text = True
                break
        doc.close()
        return not has_text

    async def extract_text_with_ocr_fallback(
        self, file_bytes: bytes, content_type: str
    ) -> str:
        """Extract text with OCR fallback for scanned PDFs.

        If the PDF is scanned (no extractable text), delegates to the
        vision model for OCR text extraction. In mock mode, returns a
        placeholder string.

        Args:
            file_bytes: Raw file content.
            content_type: MIME type of the file.

        Returns:
            Extracted text content.
        """
        if content_type == "application/pdf" and self.is_scanned_pdf(file_bytes):
            logger.info("Scanned PDF detected, delegating to OCR vision model")
            return await self._ocr_extract_text(file_bytes)
        return self.extract_text(file_bytes, content_type)

    async def _ocr_extract_text(self, file_bytes: bytes) -> str:
        """Extract text from scanned PDF pages via vision model.

        In gpu/cpu mode, converts each PDF page to a PNG image at 300 DPI,
        sends each page image to the vLLM multimodal chat completion endpoint
        sequentially, and concatenates successful page texts.

        In mock mode, returns the existing placeholder text unchanged.

        Args:
            file_bytes: Raw PDF file content.

        Returns:
            Extracted text from all successful pages concatenated with
            newline separators, or empty string if all pages fail or
            the PDF has zero pages.
        """
        # Mock mode: return placeholder text without HTTP calls
        if (
            self._model_manager is None
            or self._inference_client is None
            or self._model_manager.mode not in ("gpu", "cpu")
        ):
            logger.warning(
                "OCR in mock mode. Returning placeholder for scanned PDF."
            )
            return "[OCR_PENDING: Scanned PDF text extraction requires Model_Manager]"

        from alcoabase.services.inference_client import (
            InferenceConnectionError,
            InferenceError,
            InferenceTimeoutError,
        )
        from alcoabase.services.model_manager import ModelRole

        # Open the PDF and check page count
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(doc)

        if page_count == 0:
            logger.warning("PDF has zero pages, returning empty string")
            doc.close()
            return ""

        # Limit to 500 pages maximum
        max_pages = min(page_count, 500)
        if page_count > 500:
            logger.warning(
                "PDF has %d pages, processing only first 500", page_count
            )

        # Ensure OCR model is loaded
        await self._model_manager.ensure_model(ModelRole.OCR)

        model_name = self._settings.model_ocr_name
        successful_texts: list[str] = []
        failed_count = 0

        # Process pages sequentially (one at a time)
        for page_idx in range(max_pages):
            page = doc[page_idx]

            try:
                # Convert page to PNG at 300 DPI
                pixmap = page.get_pixmap(dpi=300)
                png_bytes = pixmap.tobytes("png")

                # Base64 encode the PNG image
                b64_image = base64.b64encode(png_bytes).decode("utf-8")

                # Build multimodal message for OCR
                messages: list[dict[str, Any]] = [
                    {
                        "role": "system",
                        "content": (
                            "Extract all visible text from this document page image. "
                            "Preserve the original layout and formatting as much as "
                            "possible. Output only the extracted text, nothing else."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64_image}",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Extract all text from this page.",
                            },
                        ],
                    },
                ]

                # Send to vLLM with 90s timeout, max_tokens=4096, temperature=0.1
                page_text = await self._inference_client.chat_completion(
                    model=model_name,
                    messages=messages,
                    max_tokens=4096,
                    temperature=0.1,
                    timeout=90.0,
                )

                if page_text and page_text.strip():
                    successful_texts.append(page_text)

            except InferenceTimeoutError:
                failed_count += 1
                logger.warning(
                    "OCR timeout for page %d (90s exceeded), skipping",
                    page_idx + 1,
                )
                continue
            except (InferenceError, InferenceConnectionError) as e:
                failed_count += 1
                status_code = getattr(e, "status_code", None)
                logger.warning(
                    "OCR failed for page %d: status=%s, skipping",
                    page_idx + 1,
                    status_code,
                )
                continue
            except Exception as e:
                failed_count += 1
                logger.warning(
                    "OCR unexpected error for page %d: %s, skipping",
                    page_idx + 1,
                    str(e),
                )
                continue

        doc.close()

        # If all pages failed, return empty string and log error
        if not successful_texts and max_pages > 0:
            logger.error(
                "Complete OCR failure: all %d pages failed for document",
                max_pages,
            )
            return ""

        return "\n".join(successful_texts)

    # -----------------------------------------------------------------------
    # Text Chunking (Task 12.3)
    # -----------------------------------------------------------------------

    def chunk_text(
        self, text: str, chunk_size: int = 512, overlap: int = 50
    ) -> list[str]:
        """Split text into overlapping chunks for embedding generation.

        Uses whitespace-aware token approximation (splitting on whitespace).
        Each chunk contains approximately `chunk_size` tokens with `overlap`
        tokens of overlap between consecutive chunks.

        Args:
            text: Input text to chunk.
            chunk_size: Target number of tokens per chunk (default 512).
            overlap: Number of overlapping tokens between chunks (default 50).

        Returns:
            List of text chunks. Returns empty list for empty/whitespace input.

        Raises:
            ValueError: If overlap >= chunk_size.
        """
        if overlap >= chunk_size:
            raise ValueError(
                f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
            )

        if not text or not text.strip():
            return []

        # Approximate tokens by splitting on whitespace
        tokens = text.split()

        if len(tokens) <= chunk_size:
            return [text.strip()]

        chunks: list[str] = []
        step = chunk_size - overlap
        i = 0

        while i < len(tokens):
            chunk_tokens = tokens[i : i + chunk_size]
            chunk_text = " ".join(chunk_tokens)
            chunks.append(chunk_text)

            if i + chunk_size >= len(tokens):
                break
            i += step

        return chunks

    # -----------------------------------------------------------------------
    # Embedding Generation (Task 12.4)
    # -----------------------------------------------------------------------

    async def generate_embeddings(self, chunks: list[str]) -> list[list[float]]:
        """Generate multilingual vector embeddings for text chunks.

        In gpu/cpu mode, calls the vLLM embedding endpoint via InferenceClient
        with batches of up to 32 chunks per request. In mock mode, returns
        random normalized vectors of the correct dimension.

        Args:
            chunks: List of text chunks to embed.

        Returns:
            List of embedding vectors, one per chunk. Each vector has
            dimension equal to `model_embedding_dimension` from settings.

        Raises:
            ValueError: If a returned embedding vector has incorrect dimensions.
            InferenceError: If the vLLM server returns an HTTP error.
            InferenceTimeoutError: If the vLLM server does not respond within 30s.
        """
        if not chunks:
            return []

        # Determine mode: use real inference if model_manager is available
        # and mode is gpu/cpu
        if (
            self._model_manager is not None
            and self._inference_client is not None
            and self._model_manager.mode in ("gpu", "cpu")
        ):
            return await self._generate_embeddings_real(chunks)

        # Mock mode: generate random normalized vectors
        return self._generate_embeddings_mock(chunks)

    async def _generate_embeddings_real(
        self, chunks: list[str]
    ) -> list[list[float]]:
        """Generate embeddings via vLLM inference in gpu/cpu mode.

        Batches chunks into groups of 32, processes sequentially, and
        concatenates results in input order.

        Args:
            chunks: Non-empty list of text chunks to embed.

        Returns:
            List of embedding vectors in input order.

        Raises:
            ValueError: If a returned embedding vector has incorrect dimensions.
            InferenceError: If the vLLM server returns an HTTP error.
            InferenceTimeoutError: If the vLLM server does not respond within 30s.
        """
        from alcoabase.services.model_manager import ModelRole

        # Ensure embedding model is loaded
        await self._model_manager.ensure_model(ModelRole.EMBEDDING)  # type: ignore[union-attr]

        batch_size = 32
        model_name = self._settings.model_embedding_name
        all_embeddings: list[list[float]] = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]

            try:
                batch_embeddings = await self._inference_client.create_embeddings(  # type: ignore[union-attr]
                    model=model_name,
                    inputs=batch,
                )
            except Exception as e:
                # Log and re-raise for HTTP errors and timeouts
                logger.error(
                    "Embedding generation failed for batch %d-%d: %s",
                    i,
                    i + len(batch),
                    str(e),
                )
                raise

            # Validate dimensions for each vector in the batch
            for j, vector in enumerate(batch_embeddings):
                if len(vector) != self._embedding_dimension:
                    raise ValueError(
                        f"Embedding dimension mismatch: expected "
                        f"{self._embedding_dimension}, got {len(vector)} "
                        f"(chunk index {i + j})"
                    )

            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def _generate_embeddings_mock(self, chunks: list[str]) -> list[list[float]]:
        """Generate mock random normalized embedding vectors.

        Used in mock mode for development/testing without GPU hardware.

        Args:
            chunks: List of text chunks to embed.

        Returns:
            List of random normalized vectors of configured dimension.
        """
        embeddings: list[list[float]] = []
        for _ in chunks:
            # Generate a random unit vector of the correct dimension
            vec = [random.gauss(0, 1) for _ in range(self._embedding_dimension)]
            # Normalize to unit length
            magnitude = sum(v * v for v in vec) ** 0.5
            if magnitude > 0:
                vec = [v / magnitude for v in vec]
            embeddings.append(vec)
        return embeddings

    # -----------------------------------------------------------------------
    # OpenSearch Indexing (Task 12.5 - Placeholder)
    # -----------------------------------------------------------------------

    def index_document(
        self,
        document_uuid: str,
        version: str,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Index document chunks and embeddings in OpenSearch.

        Placeholder implementation that stores in memory. Will be replaced
        with actual OpenSearch client calls when infrastructure is ready.

        Args:
            document_uuid: The Document-UUID to index.
            version: Document version string (e.g., "1.0").
            chunks: Text chunks extracted from the document.
            embeddings: Vector embeddings for each chunk.
            metadata: Optional metadata (title, tags, language, etc.).
        """
        if metadata is None:
            metadata = {}

        index_key = f"{document_uuid}:{version}"

        indexed_doc = IndexedDocument(
            document_uuid=document_uuid,
            version=version,
            chunks=chunks,
            embeddings=embeddings,
            metadata=metadata,
            is_csv_validation_record=metadata.get("is_csv_validation_record", False),
            permitted_user_ids=metadata.get("permitted_user_ids"),
        )

        self._index[index_key] = indexed_doc
        logger.info(
            "Indexed document %s v%s with %d chunks (placeholder)",
            document_uuid,
            version,
            len(chunks),
        )

    # -----------------------------------------------------------------------
    # Hybrid Search (Task 12.7 - Placeholder)
    # -----------------------------------------------------------------------

    def hybrid_search(
        self,
        query: str,
        user_id: int,
        limit: int = 20,
        filters: dict[str, list[str]] | None = None,
        offset: int = 0,
        sort_by: str = "relevance",
    ) -> tuple[list[SearchResult], int]:
        """Perform hybrid search with filtering, sorting, and pagination.

        Placeholder implementation that performs simple keyword matching
        against the in-memory index. Will be replaced with actual OpenSearch
        hybrid query when infrastructure is ready.

        Applies ABAC filtering, CSV record exclusion, metadata filters,
        sorting, and offset/limit slicing.

        Args:
            query: Search query string.
            user_id: ID of the user performing the search (for ABAC filtering).
            limit: Maximum number of results to return (default 20).
            filters: Optional dict of filter category → list of values.
                AND logic between categories, OR logic within a category.
            offset: Number of results to skip for pagination (default 0).
            sort_by: Sort order — "relevance" or "date" (default "relevance").

        Returns:
            Tuple of (paginated results list, total_available count before
            pagination).
        """
        query_lower = query.lower()
        results: list[SearchResult] = []

        for _key, doc in self._index.items():
            # Task 12.9: Exclude CSV validation records
            if doc.is_csv_validation_record:
                continue

            # Task 12.8: ABAC filtering
            if doc.permitted_user_ids is not None and user_id not in doc.permitted_user_ids:
                continue

            # Simple keyword matching (placeholder for BM25 + kNN)
            for i, chunk in enumerate(doc.chunks):
                if query_lower in chunk.lower():
                    # Calculate a simple relevance score
                    score = chunk.lower().count(query_lower) / max(len(chunk.split()), 1)
                    results.append(
                        SearchResult(
                            document_uuid=doc.document_uuid,
                            title=doc.metadata.get("title", "Untitled"),
                            version=doc.version,
                            excerpt=chunk[:200],
                            relevance_score=min(score, 1.0),
                            metadata=doc.metadata,
                            document_type=doc.metadata.get("document_type"),
                            status=doc.metadata.get("status"),
                            tags=doc.metadata.get("tags", []),
                            created_at=doc.metadata.get("created_at"),
                            updated_at=doc.metadata.get("updated_at"),
                        )
                    )

        # Apply metadata filters (AND between categories, OR within a category)
        filtered_results = self._apply_filters(results, filters)

        # Apply sorting
        if sort_by == "date":
            # Sort by updated_at descending; None values go to the end
            filtered_results.sort(
                key=lambda r: r.updated_at or "",
                reverse=True,
            )
        else:
            # Sort by relevance_score descending
            filtered_results.sort(
                key=lambda r: r.relevance_score,
                reverse=True,
            )

        # Compute total_available before pagination
        total_available = len(filtered_results)

        # Apply pagination (offset + limit slice)
        paginated_results = filtered_results[offset : offset + limit]

        return paginated_results, total_available

    def _apply_filters(
        self,
        results: list[SearchResult],
        filters: dict[str, list[str]] | None,
    ) -> list[SearchResult]:
        """Apply metadata filters to search results.

        Uses AND logic between categories and OR logic within a category.
        A document matches if it satisfies ALL non-empty filter categories,
        where satisfying a category means the document's value for that field
        is in the filter list.

        Args:
            results: List of search results to filter.
            filters: Dict of filter category → list of acceptable values.
                If None or all lists are empty, returns all results unfiltered.

        Returns:
            Filtered list of search results.
        """
        if not filters:
            return results

        # Build active filters (only categories with non-empty value lists)
        active_filters: dict[str, list[str]] = {
            k: v for k, v in filters.items() if v
        }

        if not active_filters:
            return results

        filtered: list[SearchResult] = []
        for result in results:
            if self._matches_all_filters(result, active_filters):
                filtered.append(result)

        return filtered

    def _matches_all_filters(
        self,
        result: SearchResult,
        active_filters: dict[str, list[str]],
    ) -> bool:
        """Check if a result matches all active filter categories.

        Args:
            result: A single search result to check.
            active_filters: Dict of category → list of acceptable values
                (only non-empty categories).

        Returns:
            True if the result matches at least one value in every
            active filter category.
        """
        for category, values in active_filters.items():
            if category == "document_type":
                if result.document_type not in values:
                    return False
            elif category == "status":
                if result.status not in values:
                    return False
            elif category == "tags":
                # OR within tags: result must have at least one matching tag
                if not any(tag in values for tag in result.tags):
                    return False
        return True
