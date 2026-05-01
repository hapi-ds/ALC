"""Celery tasks for asynchronous document indexing.

Handles background document text extraction, chunking, embedding generation,
and OpenSearch indexing with retry on model unavailability.

References:
    - Task 12.6: Create Celery task for async document indexing
    - Requirement 13: Document Indexing and Vector Embedding
"""

import logging
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger

from alcoabase.services.knowledge_service import KnowledgeService

logger = get_task_logger(__name__)

# Module-level service instance (reused across task invocations)
_knowledge_service: KnowledgeService | None = None


def _get_knowledge_service() -> KnowledgeService:
    """Get or create the KnowledgeService singleton for task workers.

    Returns:
        KnowledgeService: The service instance.
    """
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service


class ModelUnavailableError(Exception):
    """Raised when the embedding model is not available for inference."""

    pass


@shared_task(
    bind=True,
    name="alcoabase.tasks.index_document",
    autoretry_for=(ModelUnavailableError, ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=10,
    acks_late=True,
)
def index_document_task(
    self: Any,
    document_uuid: str,
    version: str,
    file_bytes_hex: str,
    content_type: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Asynchronously index a document for search.

    Extracts text, chunks it, generates embeddings, and stores in the
    search index. Retries with exponential backoff on model unavailability.

    Args:
        self: Celery task instance (bound).
        document_uuid: The Document-UUID to index.
        version: Document version string (e.g., "1.0").
        file_bytes_hex: Hex-encoded file content (for JSON serialization).
        content_type: MIME type of the file.
        metadata: Optional document metadata (title, tags, etc.).

    Returns:
        Dict with indexing results (chunk_count, status).

    Raises:
        ModelUnavailableError: If embedding model is not available (triggers retry).
    """
    if metadata is None:
        metadata = {}

    service = _get_knowledge_service()

    # Decode file bytes from hex string (Celery JSON serialization)
    file_bytes = bytes.fromhex(file_bytes_hex)

    logger.info(
        "Starting indexing for document %s v%s (content_type=%s)",
        document_uuid,
        version,
        content_type,
    )

    # Step 1: Extract text (with OCR fallback for scanned PDFs)
    try:
        text = service.extract_text_with_ocr_fallback(file_bytes, content_type)
    except Exception as exc:
        logger.error(
            "Text extraction failed for %s v%s: %s",
            document_uuid,
            version,
            exc,
        )
        raise

    if not text or not text.strip():
        logger.warning(
            "No text extracted from document %s v%s", document_uuid, version
        )
        return {
            "document_uuid": document_uuid,
            "version": version,
            "status": "no_text",
            "chunk_count": 0,
        }

    # Step 2: Chunk text
    chunks = service.chunk_text(text)
    logger.info(
        "Document %s v%s chunked into %d segments",
        document_uuid,
        version,
        len(chunks),
    )

    # Step 3: Generate embeddings (placeholder - will use Model_Manager)
    try:
        embeddings = service.generate_embeddings(chunks)
    except Exception as exc:
        logger.error(
            "Embedding generation failed for %s v%s: %s",
            document_uuid,
            version,
            exc,
        )
        # Treat as model unavailability for retry
        raise ModelUnavailableError(
            f"Embedding generation failed: {exc}"
        ) from exc

    # Step 4: Index in OpenSearch (placeholder)
    service.index_document(
        document_uuid=document_uuid,
        version=version,
        chunks=chunks,
        embeddings=embeddings,
        metadata=metadata,
    )

    logger.info(
        "Successfully indexed document %s v%s (%d chunks)",
        document_uuid,
        version,
        len(chunks),
    )

    return {
        "document_uuid": document_uuid,
        "version": version,
        "status": "indexed",
        "chunk_count": len(chunks),
    }
