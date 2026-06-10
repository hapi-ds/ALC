"""Embedding generation orchestrator for literature content.

Coordinates chunking, vLLM inference, OpenSearch indexing, state transitions,
and audit logging. Entry point for both automatic (Celery task) and manual
(API-triggered) embedding operations.

Handles:
    - Single-record embedding generation and indexing
    - Batch re-indexing with progress tracking
    - Per-company EmbeddingConfiguration respect
    - Dimension validation, retry logic, idempotent indexing
    - Audit trail for all operations

References:
    - Requirements 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 8.1–8.10, 9.2–9.6, 12.1, 12.4, 12.6–12.8
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.literature.embedding.exceptions import (
    EmbeddingDimensionMismatchError,
    EmbeddingGenerationError,
    IndexingUnavailableError,
    ReindexAlreadyActiveError,
)
from alcoabase.literature.embedding.models.embedding_config import (
    EmbeddingConfiguration,
)
from alcoabase.literature.embedding.models.reindex_job import ReindexJob
from alcoabase.literature.embedding.services.chunking_pipeline import (
    ChunkingPipeline,
    ContentChunk,
)
from alcoabase.literature.embedding.services.index_manager import (
    IndexedChunk,
    LiteratureIndexManager,
)
from alcoabase.literature.ingestion.models.ingestion import (
    IngestionAuditLog,
    IngestionRecord,
)
from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.model_manager import ModelManager, ModelRole

logger = logging.getLogger(__name__)

# Embedding batch size: 32 chunks per vLLM request
_EMBEDDING_BATCH_SIZE = 32

# Retry backoff schedule in seconds: 30s, 2min, 10min
_RETRY_DELAYS_SECONDS = [30, 120, 600]

# Maximum retries for embedding generation
_MAX_RETRIES = 3

# Maximum retries for idempotent insert after delete
_MAX_INSERT_RETRIES = 2


class EmbeddingService:
    """Orchestrates embedding generation and indexing for literature content.

    Responsibilities:
        - Generate embeddings for IngestionRecords (abstract or full-text)
        - Respect per-company EmbeddingConfiguration settings
        - Manage batch re-indexing operations with progress tracking
        - Enforce idempotent indexing (delete-then-insert per record)
        - Validate embedding dimensions before indexing
        - Handle retries and state transitions on failure
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        inference_client: InferenceClient,
        model_manager: ModelManager,
        index_manager: LiteratureIndexManager,
        chunking_pipeline: ChunkingPipeline,
    ) -> None:
        """Initialize with all required dependencies.

        Args:
            session_factory: Async SQLAlchemy session factory for DB access.
            inference_client: Client for vLLM embedding requests.
            model_manager: Manages model loading/readiness.
            index_manager: OpenSearch index operations.
            chunking_pipeline: Text chunking for embedding.
        """
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._model_manager = model_manager
        self._index_manager = index_manager
        self._chunking_pipeline = chunking_pipeline

    async def generate_and_index_embeddings(
        self,
        record_id: int,
        company_id: int,
        user_id: int | None = None,
        triggering_event: str = "auto",
    ) -> dict[str, Any]:
        """Generate embeddings for an IngestionRecord and index into OpenSearch.

        Steps:
            1. Load IngestionRecord and EmbeddingConfiguration
            2. Determine content source (abstract or full-text)
            3. Chunk content via ChunkingPipeline
            4. Generate embeddings in batches of 32 via InferenceClient
            5. Validate all vectors have correct dimension
            6. Delete existing chunks for this record (idempotent)
            7. Bulk index new chunks into OpenSearch
            8. Transition state to 'indexed'
            9. Write audit log entries

        Args:
            record_id: IngestionRecord to process.
            company_id: Tenant scope.
            user_id: Triggering user (None for automated).
            triggering_event: 'auto' or 'manual'.

        Returns:
            Dict with status, chunk_count, duration_ms.

        Raises:
            EmbeddingDimensionMismatchError: If vectors have wrong dimension.
            EmbeddingGenerationError: If vLLM fails after retries.
            IndexingUnavailableError: If OpenSearch fails after retries.
        """
        start_time = time.time()

        async with self._session_factory() as session:
            # Step 1: Load IngestionRecord
            record = await self._load_record(session, record_id, company_id)
            if record is None:
                logger.error(
                    "IngestionRecord %d not found for company %d.",
                    record_id,
                    company_id,
                )
                return {"status": "not_found", "chunk_count": 0, "duration_ms": 0}

            # Step 1b: Load EmbeddingConfiguration (or use defaults)
            config = await self._load_config(session, company_id)

            # Check auto_embed_on_ingest for auto-triggered events
            if triggering_event == "auto" and not config.auto_embed_on_ingest:
                logger.info(
                    "Auto-embed disabled for company %d. Skipping record %d.",
                    company_id,
                    record_id,
                )
                return {
                    "status": "skipped_auto_disabled",
                    "chunk_count": 0,
                    "duration_ms": 0,
                }

            # Step 2: Determine content and chunk
            chunks = self._get_chunks(record, config)

            if not chunks:
                # No content to embed (e.g., abstract-only mode with no abstract)
                logger.info(
                    "No chunks produced for record %d. Skipping.",
                    record_id,
                )
                await self._write_audit_log(
                    session,
                    company_id=company_id,
                    record_id=record_id,
                    event_type="embedding_skipped",
                    details={
                        "reason": "no_chunks_produced",
                        "embed_abstract_only": config.embed_abstract_only,
                    },
                    user_id=user_id,
                )
                await session.commit()
                return {
                    "status": "skipped_no_content",
                    "chunk_count": 0,
                    "duration_ms": int((time.time() - start_time) * 1000),
                }

            # Step 3: Apply max_chunks_per_document truncation
            truncated = False
            original_chunk_count = len(chunks)
            if len(chunks) > config.max_chunks_per_document:
                chunks = chunks[: config.max_chunks_per_document]
                truncated = True
                logger.info(
                    "Truncated chunks for record %d from %d to %d (max_chunks=%d).",
                    record_id,
                    original_chunk_count,
                    len(chunks),
                    config.max_chunks_per_document,
                )

        # Step 4: Generate embeddings in batches of 32 with retry
        try:
            embeddings = await self._generate_embeddings_with_retry(
                chunks, record_id, company_id
            )
        except EmbeddingGenerationError:
            # Transition to failed state
            async with self._session_factory() as session:
                await self._transition_to_failed(
                    session,
                    record_id=record_id,
                    company_id=company_id,
                    error_type="embedding_generation_error",
                    error_message="vLLM embedding generation failed after retries.",
                    user_id=user_id,
                    retry_attempt=_MAX_RETRIES,
                )
                await session.commit()
            raise

        # Step 5: Validate dimensions
        expected_dim = self._index_manager._embedding_dimension
        for i, vec in enumerate(embeddings):
            if len(vec) != expected_dim:
                async with self._session_factory() as session:
                    await self._transition_to_failed(
                        session,
                        record_id=record_id,
                        company_id=company_id,
                        error_type="embedding_dimension_mismatch",
                        error_message=(
                            f"Vector {i} has dimension {len(vec)}, "
                            f"expected {expected_dim}."
                        ),
                        user_id=user_id,
                        retry_attempt=0,
                    )
                    await session.commit()
                raise EmbeddingDimensionMismatchError(
                    f"Embedding vector dimension mismatch at index {i}: "
                    f"got {len(vec)}, expected {expected_dim}.",
                    company_id=company_id,
                    expected_dimension=expected_dim,
                    actual_dimension=len(vec),
                    record_id=record_id,
                )

        # Step 6 & 7: Idempotent indexing (delete-then-insert with retry)
        async with self._session_factory() as session:
            record = await self._load_record(session, record_id, company_id)
            if record is None:
                return {"status": "not_found", "chunk_count": 0, "duration_ms": 0}

            indexed_chunks = self._build_indexed_chunks(
                record, chunks, embeddings, company_id
            )

            indexing_start = time.time()
            indexed_count = await self._idempotent_index(
                company_id=company_id,
                record_id=record_id,
                chunks=indexed_chunks,
            )
            indexing_duration_ms = int((time.time() - indexing_start) * 1000)

            # Step 8: Transition state to 'indexed'
            await self._transition_to_indexed(session, record, user_id)

            # Step 9: Write audit log — embedding generation event (Req 11.1)
            duration_ms = int((time.time() - start_time) * 1000)
            await self._write_audit_log(
                session,
                company_id=company_id,
                record_id=record_id,
                event_type="embedding_generated",
                details={
                    "chunk_count": indexed_count,
                    "dimension": expected_dim,
                    "model_name": self._get_model_name(),
                    "duration_ms": duration_ms,
                    "triggering_event": triggering_event,
                    "truncated": truncated,
                    "original_chunk_count": original_chunk_count,
                },
                user_id=user_id,
            )

            # Indexing event audit log (Req 11.2)
            index_name = self._index_manager._index_name(company_id)
            partition_tag = (
                indexed_chunks[0].partition_tag if indexed_chunks else "public_literature"
            )
            await self._write_audit_log(
                session,
                company_id=company_id,
                record_id=record_id,
                event_type="chunks_indexed",
                details={
                    "index_name": index_name,
                    "chunks_indexed": indexed_count,
                    "duration_ms": indexing_duration_ms,
                    "partition_tag": partition_tag,
                },
                user_id=user_id,
            )

            if truncated:
                await self._write_audit_log(
                    session,
                    company_id=company_id,
                    record_id=record_id,
                    event_type="chunks_truncated",
                    details={
                        "total_chunks_produced": original_chunk_count,
                        "max_chunks_applied": config.max_chunks_per_document,
                    },
                    user_id=user_id,
                )

            await session.commit()

        return {
            "status": "indexed",
            "chunk_count": indexed_count,
            "duration_ms": duration_ms,
        }

    async def initiate_reindex(
        self,
        company_id: int,
        user_id: int,
        reason: str,
        state_filter: list[str] | None = None,
        record_ids: list[int] | None = None,
    ) -> str:
        """Initiate a batch re-indexing job for a company.

        Creates a ReindexJob record and dispatches the first batch via Celery.

        Args:
            company_id: Company to re-index.
            user_id: Initiating admin.
            reason: X-Change-Reason value.
            state_filter: Optional list of states to include (e.g., ['indexed', 'abstract_indexed']).
            record_ids: Optional specific record IDs to re-index.

        Returns:
            task_id (UUID string) for progress tracking.

        Raises:
            ReindexAlreadyActiveError: If a job is already running for this company.
        """
        async with self._session_factory() as session:
            # Check for existing active job
            existing_job = await self._get_active_reindex_job(session, company_id)
            if existing_job is not None:
                progress = self._compute_progress(existing_job)
                raise ReindexAlreadyActiveError(
                    f"A re-indexing job is already active for company {company_id}.",
                    company_id=company_id,
                    active_task_id=existing_job.task_id,
                    progress_percent=progress,
                )

            # Count target records
            total_records = await self._count_target_records(
                session, company_id, state_filter, record_ids
            )

            # Import settings for batch size
            from alcoabase.config import get_settings

            settings = get_settings()
            batch_size = settings.reindex_batch_size
            total_batches = math.ceil(total_records / batch_size) if total_records > 0 else 0

            # Create ReindexJob
            task_id = str(uuid.uuid4())
            job = ReindexJob(
                task_id=task_id,
                company_id=company_id,
                status="queued",
                total_records=total_records,
                total_batches=total_batches,
                current_batch=0,
                records_processed=0,
                records_failed=0,
            )
            session.add(job)

            # Write audit log for re-index initiation
            await self._write_audit_log(
                session,
                company_id=company_id,
                record_id=None,
                event_type="reindex_initiated",
                details={
                    "task_id": task_id,
                    "total_records": total_records,
                    "total_batches": total_batches,
                    "batch_size": batch_size,
                    "state_filter": state_filter,
                    "record_ids": record_ids,
                    "reason": reason,
                },
                user_id=user_id,
            )

            await session.commit()

        # Dispatch first batch via Celery (import here to avoid circular imports)
        if total_records > 0:
            from alcoabase.tasks.celery_app import celery_app

            celery_app.send_task(
                "alcoabase.tasks.literature_embedding_tasks.reindex_batch",
                kwargs={
                    "task_id": task_id,
                    "company_id": company_id,
                    "batch_number": 1,
                    "state_filter": state_filter,
                    "record_ids": record_ids,
                },
                queue=settings.literature_embedding_queue,
            )

        return task_id

    async def cancel_reindex(
        self,
        task_id: str,
        company_id: int,
        user_id: int,
    ) -> bool:
        """Cancel an active re-indexing job.

        Sets status to 'cancelled', stops dispatching new batches.
        Allows the currently executing batch to complete.

        Args:
            task_id: UUID of the re-indexing job.
            company_id: Tenant scope.
            user_id: Requesting admin.

        Returns:
            True if cancellation was recorded.
        """
        async with self._session_factory() as session:
            stmt = select(ReindexJob).where(
                ReindexJob.task_id == task_id,
                ReindexJob.company_id == company_id,
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()

            if job is None:
                logger.warning(
                    "ReindexJob %s not found for company %d.",
                    task_id,
                    company_id,
                )
                return False

            if job.status in ("completed", "cancelled", "failed"):
                logger.info(
                    "ReindexJob %s already in terminal state: %s.",
                    task_id,
                    job.status,
                )
                return False

            job.status = "cancelled"
            job.cancelled_by = user_id
            job.cancel_reason = "User-requested cancellation"

            await self._write_audit_log(
                session,
                company_id=company_id,
                record_id=None,
                event_type="reindex_cancelled",
                details={
                    "task_id": task_id,
                    "cancelled_by": user_id,
                },
                user_id=user_id,
            )

            await session.commit()

        logger.info(
            "ReindexJob %s cancelled by user %d.", task_id, user_id
        )
        return True

    async def get_reindex_progress(
        self,
        task_id: str,
        company_id: int,
    ) -> dict[str, Any]:
        """Get progress information for a re-indexing job.

        Args:
            task_id: UUID of the re-indexing job.
            company_id: Tenant scope.

        Returns:
            Dict with percentage, records_processed, records_failed,
            estimated_remaining_seconds, status.
        """
        async with self._session_factory() as session:
            stmt = select(ReindexJob).where(
                ReindexJob.task_id == task_id,
                ReindexJob.company_id == company_id,
            )
            result = await session.execute(stmt)
            job = result.scalar_one_or_none()

            if job is None:
                return {
                    "status": "not_found",
                    "percentage": 0,
                    "records_processed": 0,
                    "records_failed": 0,
                    "estimated_remaining_seconds": 0,
                }

            percentage = self._compute_progress(job)
            estimated_remaining = self._estimate_remaining_time(job)

            return {
                "status": job.status,
                "percentage": percentage,
                "records_processed": job.records_processed,
                "records_failed": job.records_failed,
                "estimated_remaining_seconds": estimated_remaining,
                "total_records": job.total_records,
                "current_batch": job.current_batch,
                "total_batches": job.total_batches,
            }

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _load_record(
        self,
        session: AsyncSession,
        record_id: int,
        company_id: int,
    ) -> IngestionRecord | None:
        """Load an IngestionRecord scoped to the company.

        Args:
            session: Active database session.
            record_id: Record primary key.
            company_id: Tenant scope.

        Returns:
            IngestionRecord or None if not found.
        """
        stmt = select(IngestionRecord).where(
            IngestionRecord.id == record_id,
            IngestionRecord.company_id == company_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_config(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> EmbeddingConfiguration:
        """Load or create default EmbeddingConfiguration for a company.

        Args:
            session: Active database session.
            company_id: Tenant scope.

        Returns:
            EmbeddingConfiguration instance (DB record or defaults).
        """
        stmt = select(EmbeddingConfiguration).where(
            EmbeddingConfiguration.company_id == company_id,
        )
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()

        if config is not None:
            return config

        # Return a transient object with defaults (don't persist automatically)
        return EmbeddingConfiguration(
            company_id=company_id,
            chunk_size_tokens=512,
            chunk_overlap_tokens=50,
            auto_embed_on_ingest=True,
            embed_abstract_only=False,
            max_chunks_per_document=500,
        )

    def _get_chunks(
        self,
        record: IngestionRecord,
        config: EmbeddingConfiguration,
    ) -> list[ContentChunk]:
        """Get content chunks from the record using the chunking pipeline.

        Respects embed_abstract_only configuration.

        Args:
            record: The IngestionRecord to chunk.
            config: Per-company embedding configuration.

        Returns:
            List of ContentChunks.
        """
        # Configure chunking pipeline with company settings
        pipeline = ChunkingPipeline(
            chunk_size_tokens=config.chunk_size_tokens,
            chunk_overlap_tokens=config.chunk_overlap_tokens,
        )

        # If embed_abstract_only, only chunk the abstract
        if config.embed_abstract_only:
            if not record.abstract or not record.abstract.strip():
                return []
            return pipeline.chunk_abstract(
                abstract=record.abstract,
                title=record.title or "",
            )

        # Try to load StructuredContent from the sanitized_storage_path
        # If not available, fall back to abstract
        if record.sanitized_storage_path:
            # Load StructuredContent - in production this would load from MinIO
            # For now, construct from available fields
            structured_content = self._load_structured_content(record)
            if structured_content is not None:
                return pipeline.chunk_structured_content(
                    content=structured_content,
                    max_chunks=config.max_chunks_per_document,
                    embed_abstract_only=config.embed_abstract_only,
                )

        # Fall back to abstract-only chunking
        if record.abstract and record.abstract.strip():
            return pipeline.chunk_abstract(
                abstract=record.abstract,
                title=record.title or "",
            )

        return []

    def _load_structured_content(
        self,
        record: IngestionRecord,
    ) -> Any:
        """Load StructuredContent from MinIO storage.

        In production, this reads the JSON file from MinIO and parses it.
        The Celery task context provides the MinIO client.

        Args:
            record: IngestionRecord with sanitized_storage_path.

        Returns:
            StructuredContent instance or None if unavailable.
        """
        # NOTE: Full MinIO loading is handled at the task level.
        # This method serves as a hook for the service layer.
        # The Celery task pre-loads and passes StructuredContent to the service
        # via a different code path. For direct service usage, we fall back
        # to abstract-only if the file can't be loaded synchronously.
        return None

    async def _generate_embeddings_with_retry(
        self,
        chunks: list[ContentChunk],
        record_id: int,
        company_id: int,
    ) -> list[list[float]]:
        """Generate embeddings in batches of 32 with exponential backoff retry.

        Retry schedule: 30s, 2min, 10min (3 attempts total).

        Args:
            chunks: Content chunks to embed.
            record_id: For error context.
            company_id: For error context.

        Returns:
            List of embedding vectors aligned with chunks.

        Raises:
            EmbeddingGenerationError: If all retries exhausted.
        """
        import asyncio

        # Ensure embedding model is ready
        from alcoabase.config import get_settings

        settings = get_settings()
        model_name = settings.model_embedding_name

        await self._model_manager.ensure_model(ModelRole.EMBEDDING)

        # Prepare text inputs
        texts = [chunk.text for chunk in chunks]

        all_embeddings: list[list[float]] = []
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                all_embeddings = []
                # Process in batches of 32
                for batch_start in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
                    batch_texts = texts[batch_start : batch_start + _EMBEDDING_BATCH_SIZE]
                    batch_embeddings = await self._inference_client.create_embeddings(
                        model=model_name,
                        inputs=batch_texts,
                    )
                    all_embeddings.extend(batch_embeddings)

                return all_embeddings

            except Exception as e:
                last_error = e
                logger.warning(
                    "Embedding generation attempt %d/%d failed for record %d: %s",
                    attempt + 1,
                    _MAX_RETRIES,
                    record_id,
                    str(e),
                )
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_DELAYS_SECONDS[attempt]
                    logger.info(
                        "Retrying embedding generation in %ds...", delay
                    )
                    await asyncio.sleep(delay)

        raise EmbeddingGenerationError(
            f"Embedding generation failed after {_MAX_RETRIES} retries "
            f"for record {record_id}: {last_error}",
            company_id=company_id,
            record_id=record_id,
            retry_count=_MAX_RETRIES,
            last_error=str(last_error) if last_error else None,
        )

    def _build_indexed_chunks(
        self,
        record: IngestionRecord,
        chunks: list[ContentChunk],
        embeddings: list[list[float]],
        company_id: int,
    ) -> list[IndexedChunk]:
        """Build IndexedChunk documents from content chunks and embeddings.

        Args:
            record: Source IngestionRecord for metadata.
            chunks: Content chunks.
            embeddings: Corresponding embedding vectors.
            company_id: Tenant identifier.

        Returns:
            List of IndexedChunk dataclass instances ready for OpenSearch.
        """
        abstract_snippet = ""
        if record.abstract:
            abstract_snippet = record.abstract[:200]

        authors = record.authors if isinstance(record.authors, list) else []
        # Extract author names if authors are dicts
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                name = author.get("name", author.get("full_name", ""))
                author_names.append(name)
            elif isinstance(author, str):
                author_names.append(author)

        pub_date = None
        if record.publication_date:
            pub_date = record.publication_date.isoformat()

        indexed_chunks: list[IndexedChunk] = []
        for chunk, embedding in zip(chunks, embeddings):
            indexed_chunks.append(
                IndexedChunk(
                    embedding_vector=embedding,
                    chunk_text=chunk.text,
                    title=record.title or "",
                    abstract_snippet=abstract_snippet,
                    authors=author_names,
                    doi=record.doi,
                    publication_date=pub_date,
                    source_id=record.source_id,
                    external_id=record.external_id,
                    ingestion_record_id=record.id,
                    company_id=company_id,
                    partition_tag="public_literature",
                    section_heading=chunk.section_heading,
                    chunk_index=chunk.chunk_index,
                )
            )

        return indexed_chunks

    async def _idempotent_index(
        self,
        company_id: int,
        record_id: int,
        chunks: list[IndexedChunk],
    ) -> int:
        """Delete existing chunks then insert new ones with retry on insert failure.

        Implements idempotent indexing: delete-then-insert per record.
        If deletion succeeds but insertion fails, retries the full sequence
        up to 2 times before marking as failed.

        Args:
            company_id: Tenant scope.
            record_id: IngestionRecord ID.
            chunks: New IndexedChunks to insert.

        Returns:
            Number of chunks successfully indexed.

        Raises:
            IndexingUnavailableError: If all insert retries fail.
        """
        import asyncio

        last_error: Exception | None = None

        for attempt in range(_MAX_INSERT_RETRIES + 1):
            try:
                # Delete existing chunks for this record
                await self._index_manager.delete_record_chunks(
                    company_id=company_id,
                    ingestion_record_id=record_id,
                )

                # Bulk index new chunks
                indexed_count = await self._index_manager.bulk_index_chunks(
                    company_id=company_id,
                    chunks=chunks,
                )

                return indexed_count

            except IndexingUnavailableError:
                raise
            except Exception as e:
                last_error = e
                logger.warning(
                    "Idempotent index attempt %d/%d failed for record %d: %s",
                    attempt + 1,
                    _MAX_INSERT_RETRIES + 1,
                    record_id,
                    str(e),
                )
                if attempt < _MAX_INSERT_RETRIES:
                    await asyncio.sleep(5)

        raise IndexingUnavailableError(
            f"Insert failed after {_MAX_INSERT_RETRIES + 1} attempts "
            f"for record {record_id}: {last_error}",
            company_id=company_id,
            record_id=record_id,
            index_name=self._index_manager._index_name(company_id),
            retry_count=_MAX_INSERT_RETRIES + 1,
        )

    async def _transition_to_indexed(
        self,
        session: AsyncSession,
        record: IngestionRecord,
        user_id: int | None,
    ) -> None:
        """Transition an IngestionRecord state to 'indexed'.

        Updates both state and state_history JSONB.

        Args:
            session: Active database session.
            record: IngestionRecord to transition.
            user_id: Triggering user.
        """
        previous_state = record.state
        record.state = "indexed"

        # Append to state_history JSONB
        history_entry = {
            "from_state": previous_state,
            "to_state": "indexed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "event": "embedding_generation_complete",
        }

        # Make a copy of state_history to trigger SQLAlchemy change detection
        updated_history = list(record.state_history or [])
        updated_history.append(history_entry)
        record.state_history = updated_history

        # Write state_transition audit log
        await self._write_audit_log(
            session,
            company_id=record.company_id,
            record_id=record.id,
            event_type="state_transition",
            details={
                "from_state": previous_state,
                "to_state": "indexed",
            },
            user_id=user_id,
        )

    async def _transition_to_failed(
        self,
        session: AsyncSession,
        record_id: int,
        company_id: int,
        error_type: str,
        error_message: str,
        user_id: int | None,
        retry_attempt: int | None = None,
    ) -> None:
        """Transition an IngestionRecord to 'failed' state.

        Args:
            session: Active database session.
            record_id: IngestionRecord ID.
            company_id: Tenant scope.
            error_type: Classification of the failure.
            error_message: Human-readable error description.
            user_id: Triggering user.
            retry_attempt: Number of retry attempts before failure (Req 11.4).
        """
        record = await self._load_record(session, record_id, company_id)
        if record is None:
            return

        previous_state = record.state
        record.state = "failed"
        record.failed_from_state = previous_state
        record.error_type = error_type
        record.error_message = error_message[:2000] if error_message else None

        # Append to state_history
        history_entry = {
            "from_state": previous_state,
            "to_state": "failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "error_type": error_type,
        }
        updated_history = list(record.state_history or [])
        updated_history.append(history_entry)
        record.state_history = updated_history

        # Write audit log for state transition
        await self._write_audit_log(
            session,
            company_id=company_id,
            record_id=record_id,
            event_type="state_transition",
            details={
                "from_state": previous_state,
                "to_state": "failed",
                "error_type": error_type,
                "error_message": error_message[:2000] if error_message else None,
            },
            user_id=user_id,
        )

        # Write separate failure audit log entry (Req 11.4)
        await self._write_audit_log(
            session,
            company_id=company_id,
            record_id=record_id,
            event_type="embedding_failure",
            details={
                "error_type": error_type,
                "error_message": error_message[:2000] if error_message else None,
                "retry_attempt": retry_attempt,
            },
            user_id=user_id,
        )

    async def _write_audit_log(
        self,
        session: AsyncSession,
        company_id: int,
        record_id: int | None,
        event_type: str,
        details: dict[str, Any],
        user_id: int | None,
    ) -> None:
        """Write an audit log entry.

        Args:
            session: Active database session.
            company_id: Tenant scope.
            record_id: Optional IngestionRecord reference.
            event_type: Type of audit event.
            details: JSONB dict with event-specific metadata.
            user_id: User who triggered the event.
        """
        log_entry = IngestionAuditLog(
            company_id=company_id,
            ingestion_record_id=record_id,
            event_type=event_type,
            details=details,
            user_id=user_id,
        )
        session.add(log_entry)

    async def _get_active_reindex_job(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> ReindexJob | None:
        """Check if there's an active re-index job for the company.

        Args:
            session: Active database session.
            company_id: Tenant scope.

        Returns:
            Active ReindexJob or None.
        """
        stmt = select(ReindexJob).where(
            ReindexJob.company_id == company_id,
            ReindexJob.status.in_(["queued", "in_progress"]),
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _count_target_records(
        self,
        session: AsyncSession,
        company_id: int,
        state_filter: list[str] | None,
        record_ids: list[int] | None,
    ) -> int:
        """Count records targeted for re-indexing.

        Args:
            session: Active database session.
            company_id: Tenant scope.
            state_filter: Optional states to include.
            record_ids: Optional specific IDs.

        Returns:
            Total count of target records.
        """
        from sqlalchemy import func as sql_func

        stmt = select(sql_func.count(IngestionRecord.id)).where(
            IngestionRecord.company_id == company_id,
        )

        if state_filter:
            stmt = stmt.where(IngestionRecord.state.in_(state_filter))
        else:
            # Default: re-index records in 'indexed' state
            stmt = stmt.where(IngestionRecord.state == "indexed")

        if record_ids:
            stmt = stmt.where(IngestionRecord.id.in_(record_ids))

        result = await session.execute(stmt)
        return result.scalar_one() or 0

    def _compute_progress(self, job: ReindexJob) -> float:
        """Compute percentage progress for a re-index job.

        Args:
            job: ReindexJob instance.

        Returns:
            Progress percentage (0-100).
        """
        if job.total_records == 0:
            return 100.0 if job.status == "completed" else 0.0
        processed = job.records_processed + job.records_failed
        return min(100.0, (processed / job.total_records) * 100.0)

    def _estimate_remaining_time(self, job: ReindexJob) -> int:
        """Estimate remaining time for a re-index job in seconds.

        Uses elapsed time per record to extrapolate remaining.

        Args:
            job: ReindexJob instance.

        Returns:
            Estimated remaining seconds (0 if completed or no data).
        """
        if job.status in ("completed", "cancelled", "failed"):
            return 0

        processed = job.records_processed + job.records_failed
        if processed == 0:
            return 0

        remaining = job.total_records - processed
        if remaining <= 0:
            return 0

        # Calculate elapsed time
        now = datetime.now(timezone.utc)
        started = job.started_at
        if started is None:
            return 0

        # Handle timezone-naive started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        elapsed_seconds = (now - started).total_seconds()
        if elapsed_seconds <= 0:
            return 0

        rate = processed / elapsed_seconds  # records per second
        if rate <= 0:
            return 0

        return int(remaining / rate)

    def _get_model_name(self) -> str:
        """Get the configured embedding model name.

        Returns:
            Model name string.
        """
        from alcoabase.config import get_settings

        return get_settings().model_embedding_name
