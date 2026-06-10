"""Celery tasks for literature embedding generation and re-indexing.

Implements the asynchronous task layer for:
- Embedding generation: Dispatched when an IngestionRecord transitions to
  ``sanitized``, generates embeddings via vLLM and indexes into OpenSearch.
- Batch re-indexing: Processes a batch of records during a company-wide
  re-indexing operation, dispatching subsequent batches as each completes.

Both tasks use the dedicated ``literature_ingestion`` queue and call async
EmbeddingService methods via ``asyncio.run()`` from synchronous Celery task
functions.

References:
    - Requirements 1.8, 8.2, 8.9, 12.1, 12.6
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Task 9.1: literature_embedding_tasks.py implementation
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_session_factory = None


def _get_session_factory():
    """Get or create an async session factory for Celery worker DB access.

    Celery workers do not share the FastAPI lifespan, so we create a
    standalone async engine and session factory lazily per worker process.

    Returns:
        async_sessionmaker bound to a freshly-created async engine.
    """
    global _session_factory
    if _session_factory is None:
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        from alcoabase.config import get_settings

        settings = get_settings()
        engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def _build_embedding_service():
    """Construct an EmbeddingService instance for use in Celery workers.

    Lazily imports and wires dependencies to avoid import-time side effects.

    Returns:
        Configured EmbeddingService instance.
    """
    from alcoabase.config import get_settings
    from alcoabase.literature.embedding.services.chunking_pipeline import (
        ChunkingPipeline,
    )
    from alcoabase.literature.embedding.services.embedding_service import (
        EmbeddingService,
    )
    from alcoabase.literature.embedding.services.index_manager import (
        LiteratureIndexManager,
    )
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.model_manager import ModelManager

    settings = get_settings()
    session_factory = _get_session_factory()

    # Build dependencies
    inference_client = InferenceClient(
        base_url=settings.vllm_embedding_url,
    )
    model_manager = ModelManager(
        inference_client=inference_client,
    )

    # OpenSearch client
    from opensearchpy import AsyncOpenSearch

    opensearch_client = AsyncOpenSearch(
        hosts=[settings.opensearch_url],
        use_ssl=False,
        verify_certs=False,
    )

    index_manager = LiteratureIndexManager(
        opensearch_client=opensearch_client,
        embedding_dimension=settings.model_embedding_dimension,
        shards=settings.literature_index_shards,
        replicas=settings.literature_index_replicas,
        hnsw_ef_construction=settings.literature_hnsw_ef_construction,
        hnsw_m=settings.literature_hnsw_m,
    )

    chunking_pipeline = ChunkingPipeline()

    return EmbeddingService(
        session_factory=session_factory,
        inference_client=inference_client,
        model_manager=model_manager,
        index_manager=index_manager,
        chunking_pipeline=chunking_pipeline,
    )


# Exponential backoff schedule for generate_embeddings retries (seconds)
_EMBEDDING_RETRY_BACKOFF: list[int] = [30, 120, 600]


# ---------------------------------------------------------------------------
# Task: generate_embeddings
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.literature_embedding_tasks.generate_embeddings",
    queue="literature_ingestion",
    priority=5,
    max_retries=3,
    soft_time_limit=600,
    acks_late=True,
)
def generate_embeddings(
    self,
    *,
    record_id: int,
    company_id: int,
    user_id: int | None = None,
    triggering_event: str = "auto",
) -> dict[str, Any]:
    """Generate embeddings for an IngestionRecord and index into OpenSearch.

    Dispatched automatically when an IngestionRecord transitions to the
    ``sanitized`` state (if auto_embed_on_ingest is enabled), or manually
    via the embedding generation API endpoint.

    Uses exponential backoff on retry: 30s, 120s, 600s.

    Task Settings:
        - queue: literature_ingestion
        - priority: 5 (medium)
        - max_retries: 3
        - soft_time_limit: 600s (10 minutes)
        - acks_late: True (message re-delivered on worker crash)

    Args:
        self: Celery task instance (bound for retry support).
        record_id: ID of the IngestionRecord to process.
        company_id: Company scope (tenant isolation).
        user_id: User who triggered the embedding (None for automated).
        triggering_event: 'auto' (state transition) or 'manual' (API).

    Returns:
        Dict with embedding result status, chunk_count, and duration_ms.

    References:
        - Requirements 1.8, 12.1, 12.6
    """
    logger.info(
        "generate_embeddings: record_id=%d, company_id=%d, "
        "triggering_event=%s, attempt=%d/%d",
        record_id,
        company_id,
        triggering_event,
        self.request.retries + 1,
        self.max_retries + 1,
    )

    try:
        embedding_service = _build_embedding_service()
        result = asyncio.run(
            embedding_service.generate_and_index_embeddings(
                record_id=record_id,
                company_id=company_id,
                user_id=user_id,
                triggering_event=triggering_event,
            )
        )
        logger.info(
            "generate_embeddings completed for record_id=%d: status=%s, "
            "chunks=%d, duration=%dms",
            record_id,
            result.get("status", "unknown"),
            result.get("chunk_count", 0),
            result.get("duration_ms", 0),
        )
        return result

    except Exception as exc:
        # Let Celery Retry exceptions propagate
        from celery.exceptions import Retry, SoftTimeLimitExceeded

        if isinstance(exc, Retry):
            raise

        # Log the failure
        logger.error(
            "generate_embeddings failed for record_id=%d, company_id=%d: "
            "%s: %s",
            record_id,
            company_id,
            type(exc).__name__,
            str(exc)[:500],
        )

        # Handle soft time limit exceeded — no retry
        if isinstance(exc, SoftTimeLimitExceeded):
            logger.error(
                "generate_embeddings timed out for record_id=%d "
                "(soft_time_limit=600s). Not retrying.",
                record_id,
            )
            return {
                "status": "timeout",
                "record_id": record_id,
                "error": "Soft time limit exceeded (600s)",
            }

        # Compute backoff for retry
        retry_number = self.request.retries
        if retry_number < len(_EMBEDDING_RETRY_BACKOFF):
            countdown = _EMBEDDING_RETRY_BACKOFF[retry_number]
        else:
            countdown = _EMBEDDING_RETRY_BACKOFF[-1]

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=countdown)


# ---------------------------------------------------------------------------
# Task: reindex_batch
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.literature_embedding_tasks.reindex_batch",
    queue="literature_ingestion",
    priority=7,
    max_retries=0,
    soft_time_limit=600,
    acks_late=True,
)
def reindex_batch(
    self,
    *,
    task_id: str,
    company_id: int,
    batch_number: int,
    state_filter: list[str] | None = None,
    record_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Process a single batch of records during a company-wide re-indexing.

    Loads the batch of IngestionRecords, re-generates embeddings for each,
    updates the ReindexJob progress, and dispatches the next batch if the
    job is not cancelled or complete.

    Task Settings:
        - queue: literature_ingestion
        - priority: 7 (lower than embedding generation)
        - max_retries: 0 (no automatic retries; failures tracked in ReindexJob)
        - soft_time_limit: 600s (10 minutes per batch)
        - acks_late: True (message re-delivered on worker crash)

    Args:
        self: Celery task instance (bound).
        task_id: UUID of the parent ReindexJob for progress tracking.
        company_id: Company scope (tenant isolation).
        batch_number: 1-based batch index being processed.
        state_filter: Optional list of states to include.
        record_ids: Optional specific record IDs to re-index.

    Returns:
        Dict with batch processing result.

    References:
        - Requirements 8.2, 8.9, 12.1, 12.6
    """
    logger.info(
        "reindex_batch: task_id=%s, company_id=%d, batch=%d",
        task_id,
        company_id,
        batch_number,
    )

    try:
        result = asyncio.run(
            _process_reindex_batch(
                task_id=task_id,
                company_id=company_id,
                batch_number=batch_number,
                state_filter=state_filter,
                record_ids=record_ids,
            )
        )
        logger.info(
            "reindex_batch completed: task_id=%s, batch=%d, "
            "processed=%d, failed=%d",
            task_id,
            batch_number,
            result.get("records_processed", 0),
            result.get("records_failed", 0),
        )
        return result

    except Exception as exc:
        from celery.exceptions import SoftTimeLimitExceeded

        if isinstance(exc, SoftTimeLimitExceeded):
            logger.error(
                "reindex_batch timed out: task_id=%s, batch=%d "
                "(soft_time_limit=600s).",
                task_id,
                batch_number,
            )
            # Mark batch as failed in the ReindexJob
            asyncio.run(
                _mark_batch_failed(
                    task_id=task_id,
                    company_id=company_id,
                    batch_number=batch_number,
                    error_message="Batch timed out (soft_time_limit=600s)",
                )
            )
            # Dispatch next batch despite timeout
            asyncio.run(
                _dispatch_next_batch(
                    task_id=task_id,
                    company_id=company_id,
                    batch_number=batch_number,
                    state_filter=state_filter,
                    record_ids=record_ids,
                )
            )
            return {
                "status": "timeout",
                "task_id": task_id,
                "batch_number": batch_number,
            }

        logger.error(
            "reindex_batch failed: task_id=%s, batch=%d: %s: %s",
            task_id,
            batch_number,
            type(exc).__name__,
            str(exc)[:500],
        )
        # Mark batch as failed and attempt to continue with next batch
        try:
            asyncio.run(
                _mark_batch_failed(
                    task_id=task_id,
                    company_id=company_id,
                    batch_number=batch_number,
                    error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                )
            )
            asyncio.run(
                _dispatch_next_batch(
                    task_id=task_id,
                    company_id=company_id,
                    batch_number=batch_number,
                    state_filter=state_filter,
                    record_ids=record_ids,
                )
            )
        except Exception as inner_exc:
            logger.error(
                "Failed to dispatch next batch after error: %s",
                str(inner_exc)[:200],
            )

        return {
            "status": "failed",
            "task_id": task_id,
            "batch_number": batch_number,
            "error": str(exc)[:500],
        }


# ---------------------------------------------------------------------------
# Async helpers for reindex_batch
# ---------------------------------------------------------------------------


async def _process_reindex_batch(
    *,
    task_id: str,
    company_id: int,
    batch_number: int,
    state_filter: list[str] | None = None,
    record_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Async implementation of batch re-indexing logic.

    Steps:
        1. Load the ReindexJob and check it's not cancelled.
        2. Query the batch of IngestionRecords for this batch_number.
        3. Re-generate embeddings for each record in the batch.
        4. Update ReindexJob progress counters.
        5. Dispatch next batch or mark job as completed.

    Args:
        task_id: UUID of the ReindexJob.
        company_id: Company scope.
        batch_number: 1-based batch index.
        state_filter: Optional state filter for target records.
        record_ids: Optional specific record IDs.

    Returns:
        Dict with batch processing results.
    """
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.literature.embedding.models.reindex_job import ReindexJob

    settings = get_settings()
    session_factory = _get_session_factory()
    batch_size = settings.reindex_batch_size

    async with session_factory() as session:
        # Step 1: Load ReindexJob and verify status
        stmt = select(ReindexJob).where(
            ReindexJob.task_id == task_id,
            ReindexJob.company_id == company_id,
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            logger.error("ReindexJob %s not found.", task_id)
            return {"status": "error", "reason": "job_not_found"}

        if job.status == "cancelled":
            logger.info(
                "ReindexJob %s is cancelled. Stopping batch processing.",
                task_id,
            )
            return {"status": "cancelled", "task_id": task_id}

        # Transition to in_progress on first batch
        if job.status == "queued":
            job.status = "in_progress"

        job.current_batch = batch_number

    # Step 2: Query target records for this batch
    records_in_batch = await _get_batch_records(
        company_id=company_id,
        batch_number=batch_number,
        batch_size=batch_size,
        state_filter=state_filter,
        record_ids=record_ids,
    )

    if not records_in_batch:
        # No more records — mark job as completed
        await _complete_reindex_job(task_id=task_id, company_id=company_id)
        return {
            "status": "completed",
            "task_id": task_id,
            "batch_number": batch_number,
            "records_processed": 0,
            "records_failed": 0,
        }

    # Step 3: Process each record in the batch
    embedding_service = _build_embedding_service()
    processed = 0
    failed = 0

    for record_id in records_in_batch:
        try:
            await embedding_service.generate_and_index_embeddings(
                record_id=record_id,
                company_id=company_id,
                triggering_event="reindex",
            )
            processed += 1
        except Exception as exc:
            logger.warning(
                "Reindex failed for record_id=%d in batch %d: %s: %s",
                record_id,
                batch_number,
                type(exc).__name__,
                str(exc)[:200],
            )
            failed += 1

    # Step 4: Update progress counters
    async with session_factory() as session:
        stmt = select(ReindexJob).where(
            ReindexJob.task_id == task_id,
            ReindexJob.company_id == company_id,
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is not None:
            job.records_processed = (job.records_processed or 0) + processed
            job.records_failed = (job.records_failed or 0) + failed
            job.current_batch = batch_number
            await session.commit()

    # Step 5: Dispatch next batch or complete
    await _dispatch_next_batch(
        task_id=task_id,
        company_id=company_id,
        batch_number=batch_number,
        state_filter=state_filter,
        record_ids=record_ids,
    )

    return {
        "status": "batch_completed",
        "task_id": task_id,
        "batch_number": batch_number,
        "records_processed": processed,
        "records_failed": failed,
    }


async def _get_batch_records(
    *,
    company_id: int,
    batch_number: int,
    batch_size: int,
    state_filter: list[str] | None = None,
    record_ids: list[int] | None = None,
) -> list[int]:
    """Query IngestionRecord IDs for the given batch slice.

    Uses OFFSET/LIMIT pagination based on batch_number and batch_size.

    Args:
        company_id: Company scope.
        batch_number: 1-based batch index.
        batch_size: Number of records per batch.
        state_filter: Optional state filter.
        record_ids: Optional specific record IDs.

    Returns:
        List of IngestionRecord IDs for this batch.
    """
    from sqlalchemy import select

    from alcoabase.literature.ingestion.models.ingestion import IngestionRecord

    session_factory = _get_session_factory()
    offset = (batch_number - 1) * batch_size

    async with session_factory() as session:
        stmt = select(IngestionRecord.id).where(
            IngestionRecord.company_id == company_id,
        )

        # Apply state filter
        if state_filter:
            stmt = stmt.where(IngestionRecord.state.in_(state_filter))
        else:
            # Default: re-index records that are already indexed
            stmt = stmt.where(
                IngestionRecord.state.in_(["indexed", "abstract_indexed"])
            )

        # Apply specific record ID filter
        if record_ids:
            stmt = stmt.where(IngestionRecord.id.in_(record_ids))

        # Order by ID for deterministic batching
        stmt = stmt.order_by(IngestionRecord.id).offset(offset).limit(batch_size)

        result = await session.execute(stmt)
        return list(result.scalars().all())


async def _dispatch_next_batch(
    *,
    task_id: str,
    company_id: int,
    batch_number: int,
    state_filter: list[str] | None = None,
    record_ids: list[int] | None = None,
) -> None:
    """Dispatch the next batch or mark the job as completed.

    Checks if the job is cancelled before dispatching. If all batches
    are processed, transitions the job to 'completed' status.

    Args:
        task_id: UUID of the ReindexJob.
        company_id: Company scope.
        batch_number: Just-completed batch number.
        state_filter: State filter to pass to next batch.
        record_ids: Record IDs filter to pass to next batch.
    """
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.literature.embedding.models.reindex_job import ReindexJob

    settings = get_settings()
    session_factory = _get_session_factory()

    async with session_factory() as session:
        stmt = select(ReindexJob).where(
            ReindexJob.task_id == task_id,
            ReindexJob.company_id == company_id,
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            return

        # Don't dispatch if cancelled
        if job.status == "cancelled":
            logger.info(
                "ReindexJob %s cancelled. Not dispatching batch %d.",
                task_id,
                batch_number + 1,
            )
            return

        # Check if all batches are done
        if batch_number >= job.total_batches:
            job.status = "completed"
            await session.commit()
            logger.info(
                "ReindexJob %s completed: %d records processed, %d failed.",
                task_id,
                job.records_processed or 0,
                job.records_failed or 0,
            )
            return

        await session.commit()

    # Dispatch next batch
    next_batch = batch_number + 1
    celery_app.send_task(
        "alcoabase.tasks.literature_embedding_tasks.reindex_batch",
        kwargs={
            "task_id": task_id,
            "company_id": company_id,
            "batch_number": next_batch,
            "state_filter": state_filter,
            "record_ids": record_ids,
        },
        queue=settings.literature_embedding_queue,
    )
    logger.info(
        "Dispatched reindex_batch: task_id=%s, batch=%d",
        task_id,
        next_batch,
    )


async def _complete_reindex_job(
    *,
    task_id: str,
    company_id: int,
) -> None:
    """Mark a ReindexJob as completed.

    Args:
        task_id: UUID of the ReindexJob.
        company_id: Company scope.
    """
    from sqlalchemy import select

    from alcoabase.literature.embedding.models.reindex_job import ReindexJob

    session_factory = _get_session_factory()

    async with session_factory() as session:
        stmt = select(ReindexJob).where(
            ReindexJob.task_id == task_id,
            ReindexJob.company_id == company_id,
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is not None:
            job.status = "completed"
            await session.commit()
            logger.info("ReindexJob %s marked as completed.", task_id)


async def _mark_batch_failed(
    *,
    task_id: str,
    company_id: int,
    batch_number: int,
    error_message: str,
) -> None:
    """Record a batch failure in the ReindexJob progress.

    Increments the records_failed counter but does NOT halt the job.
    The job continues with subsequent batches.

    Args:
        task_id: UUID of the ReindexJob.
        company_id: Company scope.
        batch_number: Failed batch number.
        error_message: Description of the failure.
    """
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.literature.embedding.models.reindex_job import ReindexJob

    settings = get_settings()
    session_factory = _get_session_factory()
    batch_size = settings.reindex_batch_size

    async with session_factory() as session:
        stmt = select(ReindexJob).where(
            ReindexJob.task_id == task_id,
            ReindexJob.company_id == company_id,
        )
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is not None:
            # Count entire batch as failed since we couldn't process it
            job.records_failed = (job.records_failed or 0) + batch_size
            job.current_batch = batch_number
            await session.commit()

    logger.warning(
        "Batch %d marked as failed for ReindexJob %s: %s",
        batch_number,
        task_id,
        error_message[:200],
    )
