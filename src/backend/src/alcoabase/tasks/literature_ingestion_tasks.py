"""Celery tasks for the automated literature ingestion pipeline.

Implements the asynchronous task layer for the dual-stage ingestion pipeline:
- Stage 1: Metadata and abstract ingestion (high priority)
- Stage 2: Full-text download via Unpaywall (low priority)
- Sanitization: Content extraction and normalization (medium priority)
- Retention cleanup: Periodic file purging (beat schedule)

All tasks use the dedicated ``literature_ingestion`` queue and follow the
pattern of running async database operations via ``asyncio.run()`` from
synchronous Celery task functions.

References:
    - Requirements 1.1–1.5, 12.1–12.7, 13.1–13.6
    - Design: .kiro/specs/Step_9-2_automated-ingestion-pipeline/design.md
    - Task 12.1: Stage 1 metadata ingestion task
    - Task 12.2: Stage 2 download task
    - Task 12.3: Sanitization task
    - Task 12.4: Retention cleanup periodic task
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# Stage 1: Metadata Ingestion Task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.literature_ingestion_tasks.ingest_stage1_metadata",
    queue="literature_ingestion",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    priority=1,
)
def ingest_stage1_metadata(
    self,
    *,
    record_id: int,
    company_id: int,
    user_id: int,
    batch_id: str,
) -> dict[str, Any]:
    """Stage 1: Process metadata and abstract for an IngestionRecord.

    Retrieves the IngestionRecord from the database, verifies it has a
    non-empty abstract (transitioning to abstract_indexed if applicable),
    and dispatches Stage 2 download task when full-text retrieval is
    enabled and the record has a DOI.

    Args:
        self: Celery task instance (bound for retry support).
        record_id: ID of the IngestionRecord to process.
        company_id: Company scope (tenant isolation).
        user_id: User who triggered the ingestion.
        batch_id: Batch UUID for grouping related records.

    Returns:
        Dict with processing result status and transitions made.

    Raises:
        self.retry(): On unhandled exceptions when retries remain.
    """
    logger.info(
        "Stage 1 metadata ingestion: record_id=%d, company_id=%d, "
        "batch_id=%s, attempt=%d",
        record_id,
        company_id,
        batch_id,
        self.request.retries + 1,
    )

    try:
        result = asyncio.run(
            _process_stage1_metadata(
                record_id=record_id,
                company_id=company_id,
                user_id=user_id,
                batch_id=batch_id,
            )
        )
        logger.info(
            "Stage 1 completed for record_id=%d: %s",
            record_id,
            result.get("status", "unknown"),
        )
        return result

    except Exception as exc:
        logger.error(
            "Stage 1 failed for record_id=%d: %s: %s",
            record_id,
            type(exc).__name__,
            str(exc)[:500],
        )

        # Attempt to transition record to FAILED state
        try:
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="stage1_processing_error",
                    error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                    triggering_event="stage1_unhandled_exception",
                )
            )
        except Exception as fail_exc:
            logger.error(
                "Failed to transition record_id=%d to FAILED: %s",
                record_id,
                str(fail_exc)[:200],
            )

        # Retry if attempts remain
        raise self.retry(exc=exc)


async def _process_stage1_metadata(
    *,
    record_id: int,
    company_id: int,
    user_id: int,
    batch_id: str,
) -> dict[str, Any]:
    """Async implementation of Stage 1 metadata processing.

    Logic:
    1. Retrieve the IngestionRecord from the database.
    2. If record has a non-empty abstract and is in metadata_only state,
       transition to abstract_indexed.
    3. Check if company config has full_text_retrieval_enabled AND record
       has a DOI.
    4. If yes, transition to full_text_pending and dispatch Stage 2.
    5. Log audit entries for each transition.

    Args:
        record_id: ID of the IngestionRecord.
        company_id: Company scope.
        user_id: Triggering user.
        batch_id: Batch grouping UUID.

    Returns:
        Dict describing the outcome of processing.
    """
    from sqlalchemy import select

    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionAuditLog,
        IngestionConfiguration,
        IngestionRecord,
    )
    from alcoabase.literature.ingestion.services.state_machine import (
        IngestionState,
        is_valid_transition,
    )

    session_factory = _get_session_factory()

    async with session_factory() as session:
        # Step 1: Retrieve the IngestionRecord
        record = await session.get(IngestionRecord, record_id)
        if record is None:
            logger.warning("Record %d not found. Skipping.", record_id)
            return {"status": "skipped", "reason": "record_not_found"}

        if record.company_id != company_id:
            logger.warning(
                "Company mismatch for record %d: expected %d, got %d.",
                record_id,
                company_id,
                record.company_id,
            )
            return {"status": "skipped", "reason": "company_mismatch"}

        current_state = IngestionState(record.state)
        transitions_made: list[str] = []

        # Step 2: Transition metadata_only → abstract_indexed if abstract present
        if (
            current_state == IngestionState.METADATA_ONLY
            and record.abstract
            and record.abstract.strip()
        ):
            target_state = IngestionState.ABSTRACT_INDEXED

            if is_valid_transition(current_state, target_state):
                previous_state = record.state
                record.state = target_state.value

                # Record state history
                history_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "from_state": previous_state,
                    "to_state": target_state.value,
                    "triggering_event": "stage1_abstract_indexed",
                }
                current_history = list(record.state_history or [])
                current_history.append(history_entry)
                record.state_history = current_history

                # Audit log
                audit_entry = IngestionAuditLog(
                    company_id=company_id,
                    ingestion_record_id=record_id,
                    event_type="state_transition",
                    details={
                        "from_state": previous_state,
                        "to_state": target_state.value,
                        "triggering_event": "stage1_abstract_indexed",
                        "batch_id": batch_id,
                    },
                    user_id=user_id,
                )
                session.add(audit_entry)

                current_state = target_state
                transitions_made.append(
                    f"{previous_state} → {target_state.value}"
                )

                logger.info(
                    "Record %d transitioned: %s → %s",
                    record_id,
                    previous_state,
                    target_state.value,
                )

        # Step 3: Check if full-text retrieval should be dispatched
        dispatch_stage2 = False
        if (
            current_state == IngestionState.ABSTRACT_INDEXED
            and record.doi
            and record.doi.strip()
        ):
            # Check company ingestion configuration
            config_stmt = select(IngestionConfiguration).where(
                IngestionConfiguration.company_id == company_id
            )
            config_result = await session.execute(config_stmt)
            config = config_result.scalar_one_or_none()

            # Default: full_text_retrieval_enabled=True when no config exists
            full_text_enabled = (
                config.full_text_retrieval_enabled if config else True
            )

            if full_text_enabled:
                target_state = IngestionState.FULL_TEXT_PENDING

                if is_valid_transition(current_state, target_state):
                    previous_state = record.state
                    record.state = target_state.value

                    # Record state history
                    history_entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "from_state": previous_state,
                        "to_state": target_state.value,
                        "triggering_event": "stage1_dispatch_download",
                    }
                    current_history = list(record.state_history or [])
                    current_history.append(history_entry)
                    record.state_history = current_history

                    # Audit log
                    audit_entry = IngestionAuditLog(
                        company_id=company_id,
                        ingestion_record_id=record_id,
                        event_type="state_transition",
                        details={
                            "from_state": previous_state,
                            "to_state": target_state.value,
                            "triggering_event": "stage1_dispatch_download",
                            "doi": record.doi,
                            "batch_id": batch_id,
                        },
                        user_id=user_id,
                    )
                    session.add(audit_entry)

                    transitions_made.append(
                        f"{previous_state} → {target_state.value}"
                    )
                    dispatch_stage2 = True

                    logger.info(
                        "Record %d transitioned: %s → %s (DOI: %s)",
                        record_id,
                        previous_state,
                        target_state.value,
                        record.doi,
                    )

        await session.commit()

    # Step 4: Dispatch Stage 2 download task (outside DB session)
    if dispatch_stage2:
        celery_app.send_task(
            "alcoabase.tasks.literature_ingestion_tasks.ingest_stage2_download",
            kwargs={
                "record_id": record_id,
                "company_id": company_id,
            },
            queue="literature_ingestion",
            priority=9,  # Low priority for downloads
        )
        logger.info(
            "Dispatched Stage 2 download task for record_id=%d",
            record_id,
        )

    return {
        "status": "completed",
        "record_id": record_id,
        "transitions": transitions_made,
        "stage2_dispatched": dispatch_stage2,
    }


async def _transition_to_failed(
    *,
    record_id: int,
    company_id: int,
    error_type: str,
    error_message: str,
    triggering_event: str,
) -> None:
    """Transition an IngestionRecord to the FAILED state.

    Used by task error handlers to record failure details before retrying.
    Only transitions if the current state allows moving to FAILED.

    Args:
        record_id: ID of the IngestionRecord.
        company_id: Company scope.
        error_type: Classification of the failure.
        error_message: Human-readable error description.
        triggering_event: What caused the failure.
    """
    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionAuditLog,
        IngestionRecord,
    )
    from alcoabase.literature.ingestion.services.state_machine import (
        IngestionState,
        is_valid_transition,
    )

    session_factory = _get_session_factory()

    async with session_factory() as session:
        record = await session.get(IngestionRecord, record_id)
        if record is None:
            return

        current_state = IngestionState(record.state)
        target_state = IngestionState.FAILED

        # Only transition if valid (not all states can move to FAILED)
        if not is_valid_transition(current_state, target_state):
            logger.warning(
                "Cannot transition record %d from %s to FAILED.",
                record_id,
                current_state.value,
            )
            return

        previous_state = record.state
        record.state = target_state.value
        record.failed_from_state = previous_state
        record.error_type = error_type
        record.error_message = error_message

        # Record state history
        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_state": previous_state,
            "to_state": target_state.value,
            "triggering_event": triggering_event,
            "error_type": error_type,
        }
        current_history = list(record.state_history or [])
        current_history.append(history_entry)
        record.state_history = current_history

        # Audit log
        audit_entry = IngestionAuditLog(
            company_id=company_id,
            ingestion_record_id=record_id,
            event_type="state_transition_failed",
            details={
                "from_state": previous_state,
                "to_state": target_state.value,
                "triggering_event": triggering_event,
                "error_type": error_type,
                "error_message": error_message[:500],
            },
        )
        session.add(audit_entry)

        await session.commit()

    logger.info(
        "Record %d transitioned to FAILED (from %s, error_type=%s).",
        record_id,
        previous_state,
        error_type,
    )


# ---------------------------------------------------------------------------
# Stage 2: Full-Text Download Task
# ---------------------------------------------------------------------------

# Allowed content types for full-text downloads
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset({
    "application/pdf",
    "text/html",
    "application/xml",
    "text/xml",
    "application/jats+xml",
})

# Maximum file size: 100 MB in bytes
_MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024

# Retry backoff schedule for Stage 2 (seconds)
_STAGE2_RETRY_BACKOFF: list[int] = [5, 15, 45]

# Semaphore requeue delay when concurrency limit reached (seconds)
_SEMAPHORE_REQUEUE_DELAY: int = 30

# Content type to file extension mapping
_CONTENT_TYPE_EXTENSIONS: dict[str, str] = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/jats+xml": ".xml",
}


def _acquire_download_semaphore(
    redis_client,
    company_id: int,
    max_concurrent: int,
) -> bool:
    """Attempt to acquire a download semaphore for a company.

    Uses Redis INCR on key ``semaphore:download:{company_id}``.
    If the incremented value exceeds max_concurrent, it decrements
    and returns False (semaphore not acquired).

    Args:
        redis_client: Synchronous Redis client.
        company_id: Company ID for the semaphore scope.
        max_concurrent: Maximum concurrent downloads allowed.

    Returns:
        True if the semaphore was acquired, False otherwise.
    """
    key = f"semaphore:download:{company_id}"
    current = redis_client.incr(key)

    # Set TTL as safety net to prevent stale semaphores (5 minutes)
    if current == 1:
        redis_client.expire(key, 300)

    if current > max_concurrent:
        # Could not acquire — decrement back
        redis_client.decr(key)
        return False

    return True


def _release_download_semaphore(redis_client, company_id: int) -> None:
    """Release a download semaphore for a company.

    Decrements the counter and ensures it never goes below 0.

    Args:
        redis_client: Synchronous Redis client.
        company_id: Company ID for the semaphore scope.
    """
    key = f"semaphore:download:{company_id}"
    new_val = redis_client.decr(key)
    if new_val < 0:
        redis_client.set(key, 0)


def _redact_download_url(url: str) -> str:
    """Redact authentication tokens and sensitive params from a download URL.

    Replaces query parameter values that look like tokens with [REDACTED].

    Args:
        url: The URL to redact.

    Returns:
        URL with sensitive parameters redacted.
    """
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(url)
    if not parsed.query:
        return url

    params = parse_qs(parsed.query, keep_blank_values=True)
    sensitive_keys = {"token", "key", "api_key", "apikey", "auth", "access_token"}

    redacted_params = {}
    for key, values in params.items():
        if key.lower() in sensitive_keys:
            redacted_params[key] = ["[REDACTED]"]
        else:
            redacted_params[key] = values

    redacted_query = urlencode(redacted_params, doseq=True)
    return urlunparse(parsed._replace(query=redacted_query))


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.literature_ingestion_tasks.ingest_stage2_download",
    queue="literature_ingestion",
    max_retries=3,
    acks_late=True,
    priority=9,
)
def ingest_stage2_download(
    self,
    *,
    record_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Stage 2: Download full-text content via Unpaywall.

    Acquires a Redis semaphore per company for concurrency control,
    resolves the DOI via the Unpaywall adapter, downloads the content
    from the best open-access URL, validates content_type and size
    (≤100MB), computes SHA-256, stores in MinIO, transitions to
    ``full_text_downloaded``, and dispatches the sanitization task.

    Includes a User-Agent header with version and company contact email
    for publisher compliance.

    Task Settings:
        - queue: literature_ingestion
        - priority: 9 (low)
        - max_retries: 3
        - retry backoff: [5, 15, 45] seconds

    Args:
        self: Celery task instance (bound for retry support).
        record_id: ID of the IngestionRecord to process.
        company_id: Company scope (tenant isolation).

    Returns:
        Dict with download result status.

    References:
        - Requirements 3.5, 4.1–4.9, 12.2, 12.4, 12.5
    """
    import hashlib

    import redis as sync_redis

    from alcoabase.config import get_settings

    settings = get_settings()
    redis_client = sync_redis.from_url(settings.redis_url)
    semaphore_acquired = False

    logger.info(
        "Stage 2 download: record_id=%d, company_id=%d, attempt=%d",
        record_id,
        company_id,
        self.request.retries + 1,
    )

    try:
        # Step 1: Fetch record and company config
        record_data, config_data = _get_stage2_record_and_config(
            record_id, company_id
        )

        if record_data is None:
            logger.error(
                "Record %d not found. Aborting Stage 2 download.", record_id
            )
            return {"status": "error", "message": "Record not found"}

        # Step 2: Verify state is full_text_pending
        if record_data["state"] != "full_text_pending":
            logger.warning(
                "Record %d is in state '%s', expected 'full_text_pending'. "
                "Skipping.",
                record_id,
                record_data["state"],
            )
            return {
                "status": "skipped",
                "reason": f"unexpected_state:{record_data['state']}",
            }

        # Step 3: Acquire Redis semaphore for company concurrency control
        max_concurrent = config_data.get("max_concurrent_downloads", 5)
        semaphore_acquired = _acquire_download_semaphore(
            redis_client, company_id, max_concurrent
        )

        if not semaphore_acquired:
            logger.info(
                "Semaphore unavailable for company %d (max=%d). "
                "Requeuing record %d with %ds delay.",
                company_id,
                max_concurrent,
                record_id,
                _SEMAPHORE_REQUEUE_DELAY,
            )
            raise self.retry(countdown=_SEMAPHORE_REQUEUE_DELAY)

        # Step 4: Get unpaywall_email from company config
        unpaywall_email = config_data.get("unpaywall_email")
        if not unpaywall_email:
            logger.error(
                "No unpaywall_email configured for company %d. "
                "Cannot resolve DOI.",
                company_id,
            )
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="configuration_error",
                    error_message="No unpaywall_email configured for company.",
                    triggering_event="stage2_missing_email_config",
                )
            )
            return {"status": "failed", "message": "Missing unpaywall_email config"}

        doi = record_data["doi"]
        if not doi:
            logger.error("Record %d has no DOI. Cannot resolve.", record_id)
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="doi_not_found",
                    error_message="Record has no DOI for Unpaywall resolution.",
                    triggering_event="stage2_missing_doi",
                )
            )
            return {"status": "failed", "message": "No DOI on record"}

        # Step 5: Resolve DOI via Unpaywall adapter
        logger.info(
            "Resolving DOI '%s' for record %d via Unpaywall.", doi, record_id
        )
        unpaywall_result = asyncio.run(
            _resolve_doi_unpaywall(
                doi=doi,
                email=unpaywall_email,
                company_id=company_id,
            )
        )

        best_url = unpaywall_result.best_url
        if not best_url:
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="no_oa_available",
                    error_message=f"No open-access URL found for DOI: {doi}",
                    triggering_event="stage2_no_oa_url",
                )
            )
            return {"status": "failed", "message": "No OA URL available"}

        # Step 6: Download content from best_url with User-Agent header
        user_agent = (
            f"{settings.ingestion_user_agent} "
            f"(mailto:{unpaywall_email})"
        )
        logger.info(
            "Downloading from %s for record %d.",
            best_url[:100],
            record_id,
        )

        content, response_content_type = _download_fulltext(
            url=best_url,
            user_agent=user_agent,
            record_id=record_id,
            company_id=company_id,
        )

        # Step 7: Validate content_type (strip parameters like charset)
        base_content_type = response_content_type.split(";")[0].strip().lower()
        if base_content_type not in _ALLOWED_CONTENT_TYPES:
            logger.warning(
                "Unsupported content type '%s' for record %d.",
                response_content_type,
                record_id,
            )
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="unsupported_content_type",
                    error_message=(
                        f"Content-Type '{response_content_type}' is not in "
                        f"allowed set: {sorted(_ALLOWED_CONTENT_TYPES)}"
                    ),
                    triggering_event="stage2_unsupported_content_type",
                )
            )
            return {
                "status": "failed",
                "message": f"Unsupported content type: {response_content_type}",
            }

        # Step 8: Validate file size (≤100 MB)
        file_size = len(content)
        if file_size > _MAX_FILE_SIZE_BYTES:
            logger.warning(
                "File too large (%d bytes) for record %d. Max: %d bytes.",
                file_size,
                record_id,
                _MAX_FILE_SIZE_BYTES,
            )
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="file_too_large",
                    error_message=(
                        f"File size {file_size} bytes exceeds maximum "
                        f"of {_MAX_FILE_SIZE_BYTES} bytes (100 MB)."
                    ),
                    triggering_event="stage2_file_too_large",
                )
            )
            return {"status": "failed", "message": "File too large"}

        # Step 9: Compute SHA-256 checksum
        sha256_checksum = hashlib.sha256(content).hexdigest()

        # Step 10: Store in MinIO via StorageManager
        extension = _CONTENT_TYPE_EXTENSIONS.get(base_content_type, ".bin")
        filename = f"original{extension}"

        storage_result = asyncio.run(
            _store_download_in_minio(
                content=content,
                company_id=company_id,
                record_id=record_id,
                filename=filename,
                content_type=base_content_type,
            )
        )

        # Step 11: Update record with storage details
        redacted_url = _redact_download_url(best_url)

        asyncio.run(
            _update_record_download_fields(
                record_id=record_id,
                storage_path=storage_result["object_path"],
                file_size_bytes=file_size,
                content_type=base_content_type,
                sha256_checksum=sha256_checksum,
                download_url=redacted_url,
            )
        )

        # Step 12: Transition to full_text_downloaded
        asyncio.run(
            _transition_download_complete(
                record_id=record_id,
                company_id=company_id,
            )
        )

        # Step 13: Dispatch sanitization task
        celery_app.send_task(
            "alcoabase.tasks.literature_ingestion_tasks.ingest_sanitize",
            kwargs={
                "record_id": record_id,
                "company_id": company_id,
            },
            queue="literature_ingestion",
            priority=5,
        )

        logger.info(
            "Stage 2 download complete for record %d. "
            "Size: %d bytes, SHA-256: %s, path: %s",
            record_id,
            file_size,
            sha256_checksum[:16] + "...",
            storage_result["object_path"],
        )

        return {
            "status": "completed",
            "record_id": record_id,
            "file_size_bytes": file_size,
            "content_type": base_content_type,
            "sha256_checksum": sha256_checksum,
            "storage_path": storage_result["object_path"],
        }

    except Exception as exc:
        # Let Celery Retry exceptions propagate
        from celery.exceptions import Retry

        if isinstance(exc, Retry):
            raise

        # Handle specific ingestion exceptions
        from alcoabase.literature.ingestion.exceptions import (
            AdapterTimeoutError,
            DOINotFoundError,
            NoOpenAccessError,
        )

        if isinstance(exc, DOINotFoundError):
            logger.warning(
                "DOI not found for record %d: %s", record_id, str(exc)
            )
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="doi_not_found",
                    error_message=str(exc)[:500],
                    triggering_event="stage2_doi_not_found",
                )
            )
            return {"status": "failed", "message": "DOI not found"}

        if isinstance(exc, NoOpenAccessError):
            logger.warning(
                "No open access for record %d: %s", record_id, str(exc)
            )
            asyncio.run(
                _transition_to_failed(
                    record_id=record_id,
                    company_id=company_id,
                    error_type="no_oa_available",
                    error_message=str(exc)[:500],
                    triggering_event="stage2_no_oa",
                )
            )
            return {"status": "failed", "message": "No OA available"}

        if isinstance(exc, (AdapterTimeoutError, ConnectionError, TimeoutError)):
            # Retry with backoff
            retry_num = self.request.retries
            countdown = (
                _STAGE2_RETRY_BACKOFF[retry_num]
                if retry_num < len(_STAGE2_RETRY_BACKOFF)
                else _STAGE2_RETRY_BACKOFF[-1]
            )
            logger.warning(
                "Timeout/connection error for record %d (attempt %d/%d). "
                "Retrying in %ds: %s",
                record_id,
                retry_num + 1,
                self.max_retries,
                countdown,
                str(exc)[:200],
            )
            raise self.retry(exc=exc, countdown=countdown)

        # Unhandled exception — retry with backoff if attempts remain
        retry_num = self.request.retries
        if retry_num < self.max_retries:
            countdown = (
                _STAGE2_RETRY_BACKOFF[retry_num]
                if retry_num < len(_STAGE2_RETRY_BACKOFF)
                else _STAGE2_RETRY_BACKOFF[-1]
            )
            logger.exception(
                "Unhandled error in Stage 2 for record %d (attempt %d/%d). "
                "Retrying in %ds.",
                record_id,
                retry_num + 1,
                self.max_retries,
                countdown,
            )
            raise self.retry(exc=exc, countdown=countdown)

        # All retries exhausted — transition to failed permanently
        logger.exception(
            "Stage 2 failed permanently for record %d after %d retries.",
            record_id,
            self.max_retries,
        )
        asyncio.run(
            _transition_to_failed(
                record_id=record_id,
                company_id=company_id,
                error_type="download_failed",
                error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                triggering_event="stage2_max_retries_exceeded",
            )
        )
        return {"status": "failed", "message": str(exc)[:500]}

    finally:
        # Step 14: Always release the semaphore if acquired
        if semaphore_acquired:
            _release_download_semaphore(redis_client, company_id)


# ---------------------------------------------------------------------------
# Stage 2 Helper Functions
# ---------------------------------------------------------------------------


def _get_stage2_record_and_config(
    record_id: int,
    company_id: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Synchronous wrapper for fetching record and config.

    Runs the async version in a new event loop for Celery workers.

    Args:
        record_id: The IngestionRecord ID.
        company_id: The company ID.

    Returns:
        Tuple of (record_dict, config_dict).
    """
    from sqlalchemy import select

    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionConfiguration,
        IngestionRecord,
    )

    async def _fetch():
        session_factory = _get_session_factory()
        async with session_factory() as session:
            record = await session.get(IngestionRecord, record_id)
            if record is None:
                return None, {}

            record_data = {
                "id": record.id,
                "company_id": record.company_id,
                "state": record.state,
                "doi": record.doi,
                "title": record.title,
            }

            stmt = select(IngestionConfiguration).where(
                IngestionConfiguration.company_id == company_id
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config:
                config_data = {
                    "unpaywall_email": config.unpaywall_email,
                    "max_concurrent_downloads": config.max_concurrent_downloads,
                    "full_text_retrieval_enabled": config.full_text_retrieval_enabled,
                }
            else:
                config_data = {
                    "unpaywall_email": None,
                    "max_concurrent_downloads": 5,
                    "full_text_retrieval_enabled": True,
                }

            return record_data, config_data

    return asyncio.run(_fetch())


async def _resolve_doi_unpaywall(
    doi: str,
    email: str,
    company_id: int,
):
    """Resolve a DOI to an open-access URL via the Unpaywall adapter.

    Instantiates the required infrastructure services (RateLimiter,
    CircuitBreaker, ProxyManager, AuditLogger) and calls the adapter.

    Args:
        doi: The DOI to resolve.
        email: Contact email for Unpaywall API fair use policy.
        company_id: Company ID for rate limiting and audit.

    Returns:
        UnpaywallResult dataclass with best_url, content_type, etc.

    Raises:
        DOINotFoundError: If DOI not found in Unpaywall.
        NoOpenAccessError: If no OA version available.
        AdapterTimeoutError: If request times out.
    """
    from alcoabase.config import get_settings
    from alcoabase.literature.ingestion.adapters.unpaywall_adapter import (
        UnpaywallAdapter,
    )
    from alcoabase.literature.services.audit_logger import AuditLogger
    from alcoabase.literature.services.circuit_breaker import CircuitBreaker
    from alcoabase.literature.services.proxy_manager import ProxyManager
    from alcoabase.literature.services.rate_limiter import RateLimiter

    settings = get_settings()

    rate_limiter = RateLimiter(settings.redis_url)
    circuit_breaker = CircuitBreaker(settings.redis_url)
    audit_logger = AuditLogger()
    proxy_manager = ProxyManager()

    adapter = UnpaywallAdapter(
        base_url=settings.ingestion_unpaywall_api_url,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        proxy_manager=proxy_manager,
        audit_logger=audit_logger,
        user_agent=settings.ingestion_user_agent,
    )

    return await adapter.resolve_doi(
        doi=doi,
        email=email,
        company_id=company_id,
    )


def _download_fulltext(
    url: str,
    user_agent: str,
    record_id: int,
    company_id: int,
    timeout: float = 60.0,
) -> tuple[bytes, str]:
    """Download full-text content from a publisher URL.

    Uses httpx synchronous client with User-Agent header containing
    version and company contact email. Validates Content-Length before
    downloading if header is present.

    Args:
        url: The URL to download from.
        user_agent: User-Agent header value (version + mailto:email).
        record_id: For logging context.
        company_id: For logging context.
        timeout: Request timeout in seconds (default 60s per Req 4.1).

    Returns:
        Tuple of (content_bytes, content_type_header).

    Raises:
        AdapterTimeoutError: On HTTP timeout.
        ConnectionError: On network failure or HTTP error.
        FileTooLargeError: If Content-Length exceeds limit.
    """
    import httpx

    from alcoabase.config import get_settings
    from alcoabase.literature.ingestion.exceptions import (
        AdapterTimeoutError,
        FileTooLargeError,
    )

    settings = get_settings()
    proxy_url = settings.literature_proxy_url

    headers = {"User-Agent": user_agent}

    try:
        with httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

            # Check Content-Length header before reading full body
            content_length_header = response.headers.get("content-length")
            if (
                content_length_header
                and int(content_length_header) > _MAX_FILE_SIZE_BYTES
            ):
                raise FileTooLargeError(
                    f"Content-Length {content_length_header} exceeds "
                    f"{_MAX_FILE_SIZE_BYTES} bytes.",
                    company_id=company_id,
                    file_size_bytes=int(content_length_header),
                    max_size_bytes=_MAX_FILE_SIZE_BYTES,
                    record_id=record_id,
                )

            content = response.content
            content_type = response.headers.get(
                "content-type", "application/octet-stream"
            )

            return content, content_type

    except httpx.TimeoutException as exc:
        raise AdapterTimeoutError(
            f"Download timed out after {timeout}s for URL: {url[:100]}",
            company_id=company_id,
            source_adapter_name="publisher_download",
            timeout_seconds=timeout,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectionError(
            f"Connection failed for URL: {url[:100]}: {exc}"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectionError(
            f"HTTP {exc.response.status_code} from publisher: {url[:100]}"
        ) from exc


async def _store_download_in_minio(
    content: bytes,
    company_id: int,
    record_id: int,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    """Store downloaded content in MinIO via StorageManager.

    Creates the required S3 client and StorageManager, then delegates
    to store_file() which handles checksum verification.

    Args:
        content: File bytes.
        company_id: Company scope for path construction.
        record_id: IngestionRecord ID for path construction.
        filename: Target filename (e.g., "original.pdf").
        content_type: MIME type of the content.

    Returns:
        Dict with object_path, file_size_bytes, sha256_checksum.
    """
    import aioboto3
    import redis.asyncio as aioredis

    from alcoabase.config import get_settings
    from alcoabase.literature.ingestion.services.storage_manager import (
        StorageManager,
    )

    settings = get_settings()
    protocol = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{protocol}://{settings.minio_endpoint}"

    redis_client = aioredis.from_url(settings.redis_url)

    try:
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
        ) as s3_client:
            storage_manager = StorageManager(
                bucket_name=settings.ingestion_literature_bucket,
                s3_client=s3_client,
                redis_client=redis_client,
                session_factory=_get_session_factory(),
            )

            result = await storage_manager.store_file(
                content=content,
                company_id=company_id,
                record_id=record_id,
                file_type="original",
                filename=filename,
                content_type=content_type,
            )

            return {
                "object_path": result.object_path,
                "file_size_bytes": result.file_size_bytes,
                "sha256_checksum": result.sha256_checksum,
            }
    finally:
        await redis_client.aclose()


async def _update_record_download_fields(
    record_id: int,
    storage_path: str,
    file_size_bytes: int,
    content_type: str,
    sha256_checksum: str,
    download_url: str,
) -> None:
    """Update IngestionRecord with download result fields.

    Args:
        record_id: The IngestionRecord ID.
        storage_path: MinIO object path where file was stored.
        file_size_bytes: Size of the downloaded file.
        content_type: MIME type of the downloaded file.
        sha256_checksum: SHA-256 hex digest of the file.
        download_url: URL from which the file was downloaded (redacted).
    """
    from sqlalchemy import update

    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionRecord,
    )

    session_factory = _get_session_factory()
    async with session_factory() as session:
        stmt = (
            update(IngestionRecord)
            .where(IngestionRecord.id == record_id)
            .values(
                storage_path=storage_path,
                file_size_bytes=file_size_bytes,
                content_type=content_type,
                sha256_checksum=sha256_checksum,
                download_url=download_url,
                download_timestamp=datetime.now(timezone.utc),
            )
        )
        await session.execute(stmt)
        await session.commit()


async def _transition_download_complete(
    record_id: int,
    company_id: int,
) -> None:
    """Transition IngestionRecord from full_text_pending to full_text_downloaded.

    Records state history and creates an audit log entry.

    Args:
        record_id: The IngestionRecord ID.
        company_id: Company scope.
    """
    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionAuditLog,
        IngestionRecord,
    )
    from alcoabase.literature.ingestion.services.state_machine import (
        IngestionState,
        is_valid_transition,
    )

    session_factory = _get_session_factory()
    async with session_factory() as session:
        record = await session.get(IngestionRecord, record_id)
        if record is None:
            return

        current_state = IngestionState(record.state)
        target_state = IngestionState.FULL_TEXT_DOWNLOADED

        if not is_valid_transition(current_state, target_state):
            logger.warning(
                "Cannot transition record %d from %s to %s.",
                record_id,
                current_state.value,
                target_state.value,
            )
            return

        previous_state = record.state
        record.state = target_state.value

        # Append to state history
        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from_state": previous_state,
            "to_state": target_state.value,
            "triggering_event": "stage2_download_complete",
        }
        current_history = list(record.state_history or [])
        current_history.append(history_entry)
        record.state_history = current_history

        # Audit log entry
        audit_entry = IngestionAuditLog(
            company_id=company_id,
            ingestion_record_id=record_id,
            event_type="state_transition",
            details={
                "from_state": previous_state,
                "to_state": target_state.value,
                "triggering_event": "stage2_download_complete",
                "file_size_bytes": record.file_size_bytes,
                "content_type": record.content_type,
                "sha256_checksum": record.sha256_checksum,
            },
        )
        session.add(audit_entry)
        await session.commit()

    logger.info(
        "Record %d transitioned: %s → %s.",
        record_id,
        previous_state,
        target_state.value,
    )


# ---------------------------------------------------------------------------
# Sanitization Task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.literature_ingestion_tasks.ingest_sanitize",
    queue="literature_ingestion",
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
    priority=5,
)
def ingest_sanitize(
    self,
    *,
    record_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Sanitize downloaded content into StructuredContent format.

    Reads original file from MinIO, dispatches to the SanitizationPipeline,
    stores structured_content.json in MinIO under the sanitized prefix,
    updates the record with sanitized_storage_path and word_count,
    transitions to sanitized, and then to indexed (with optional
    dual_uuid_extract dispatch if enabled).

    Args:
        self: Celery task instance (bound for retry support).
        record_id: ID of the IngestionRecord to process.
        company_id: Company scope (tenant isolation).

    Returns:
        Dict with sanitization result status.

    References:
        - Requirements 5.1, 6.1, 6.2, 12.3, 16.2
    """
    logger.info(
        "Sanitization task: record_id=%d, company_id=%d, attempt=%d",
        record_id,
        company_id,
        self.request.retries + 1,
    )

    try:
        result = asyncio.run(
            _process_sanitization(
                record_id=record_id,
                company_id=company_id,
            )
        )
        logger.info(
            "Sanitization completed for record_id=%d: %s",
            record_id,
            result.get("status", "unknown"),
        )
        return result

    except Exception as exc:
        from alcoabase.literature.ingestion.exceptions import SanitizationError

        error_message = f"{type(exc).__name__}: {str(exc)[:500]}"
        logger.error(
            "Sanitization failed for record_id=%d: %s",
            record_id,
            error_message,
        )

        # SanitizationError: transition to failed immediately (no retry)
        if isinstance(exc, SanitizationError):
            try:
                asyncio.run(
                    _transition_to_failed(
                        record_id=record_id,
                        company_id=company_id,
                        error_type=exc.error_type or "sanitization_error",
                        error_message=exc.message,
                        triggering_event="sanitization_failed",
                    )
                )
            except Exception as fail_exc:
                logger.error(
                    "Failed to transition record_id=%d to FAILED: %s",
                    record_id,
                    str(fail_exc)[:200],
                )
            return {
                "status": "failed",
                "record_id": record_id,
                "error_type": exc.error_type,
                "error_message": exc.message,
            }

        # Other errors: retry with backoff, then fail permanently
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error(
                "Max retries exceeded for record_id=%d sanitization. "
                "Transitioning to failed.",
                record_id,
            )
            try:
                asyncio.run(
                    _transition_to_failed(
                        record_id=record_id,
                        company_id=company_id,
                        error_type="unexpected_error",
                        error_message=error_message,
                        triggering_event="sanitization_max_retries_exceeded",
                    )
                )
            except Exception as fail_exc:
                logger.error(
                    "Failed to transition record_id=%d to FAILED: %s",
                    record_id,
                    str(fail_exc)[:200],
                )
            return {
                "status": "failed",
                "record_id": record_id,
                "error_type": "unexpected_error",
                "error_message": error_message,
            }


async def _process_sanitization(
    *,
    record_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Async implementation of the sanitization task.

    Logic:
    1. Get record from DB, verify state is full_text_downloaded.
    2. Read original file from MinIO (s3_client.get_object with record.storage_path).
    3. Call sanitization_pipeline.process(content, content_type, record_id).
    4. Serialize StructuredContent to JSON (model_dump_json()).
    5. Store JSON in MinIO via storage_manager.store_file().
    6. Update record: sanitized_storage_path, word_count from StructuredContent.
    7. Transition to sanitized.
    8. Check if company config has dual_uuid_integration_enabled.
    9. If dual_uuid disabled, transition directly to indexed.

    Args:
        record_id: ID of the IngestionRecord.
        company_id: Company scope.

    Returns:
        Dict describing the outcome of processing.

    Raises:
        SanitizationError: If the sanitization pipeline fails.
        Exception: For any other unexpected errors.
    """
    import aioboto3
    import redis.asyncio as redis
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionAuditLog,
        IngestionConfiguration,
        IngestionRecord,
    )
    from alcoabase.literature.ingestion.services.sanitization.html_sanitizer import (
        HTMLSanitizer,
    )
    from alcoabase.literature.ingestion.services.sanitization.pdf_sanitizer import (
        PDFSanitizer,
    )
    from alcoabase.literature.ingestion.services.sanitization.pipeline import (
        SanitizationPipeline,
    )
    from alcoabase.literature.ingestion.services.sanitization.xml_sanitizer import (
        XMLJATSSanitizer,
    )
    from alcoabase.literature.ingestion.services.state_machine import (
        IngestionState,
    )
    from alcoabase.literature.ingestion.services.storage_manager import (
        StorageManager,
    )

    settings = get_settings()
    session_factory = _get_session_factory()

    # Build sanitization pipeline
    sanitization_pipeline = SanitizationPipeline(
        pdf_sanitizer=PDFSanitizer(),
        html_sanitizer=HTMLSanitizer(),
        xml_sanitizer=XMLJATSSanitizer(),
    )

    # Step 1: Load the record and verify state
    async with session_factory() as session:
        record = await session.get(IngestionRecord, record_id)
        if record is None:
            logger.warning("Record %d not found. Skipping.", record_id)
            return {"status": "skipped", "reason": "record_not_found"}

        if record.company_id != company_id:
            logger.warning(
                "Company mismatch for record %d: expected %d, got %d.",
                record_id,
                company_id,
                record.company_id,
            )
            return {"status": "skipped", "reason": "company_mismatch"}

        current_state = IngestionState(record.state)
        if current_state != IngestionState.FULL_TEXT_DOWNLOADED:
            logger.warning(
                "Record %d is in state '%s', expected 'full_text_downloaded'.",
                record_id,
                current_state.value,
            )
            return {
                "status": "skipped",
                "reason": f"unexpected_state:{current_state.value}",
            }

        storage_path = record.storage_path
        content_type = record.content_type

    if not storage_path:
        logger.error(
            "Record %d has no storage_path. Cannot sanitize.", record_id
        )
        return {"status": "skipped", "reason": "no_storage_path"}

    # Step 2: Read original file from MinIO
    protocol = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{protocol}://{settings.minio_endpoint}"

    redis_client = redis.from_url(settings.redis_url)

    try:
        aioboto3_session = aioboto3.Session()
        async with aioboto3_session.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        ) as s3_client:
            logger.info(
                "Reading file from MinIO for record %d: %s",
                record_id,
                storage_path,
            )

            response = await s3_client.get_object(
                Bucket=settings.ingestion_literature_bucket,
                Key=storage_path,
            )
            content = await response["Body"].read()

            # Step 3: Dispatch to sanitization pipeline
            logger.info(
                "Sanitizing record %d (content_type=%s, size=%d bytes).",
                record_id,
                content_type,
                len(content),
            )

            structured_content = await sanitization_pipeline.process(
                content=content,
                content_type=content_type,
                record_id=record_id,
            )

            # Step 4: Serialize StructuredContent to JSON
            json_bytes = structured_content.model_dump_json().encode("utf-8")

            # Step 5: Store JSON in MinIO under sanitized prefix
            storage_manager = StorageManager(
                bucket_name=settings.ingestion_literature_bucket,
                s3_client=s3_client,
                redis_client=redis_client,
                session_factory=session_factory,
            )

            storage_result = await storage_manager.store_file(
                content=json_bytes,
                company_id=company_id,
                record_id=record_id,
                file_type="sanitized",
                filename="structured_content.json",
                content_type="application/json",
            )

        # Step 6 & 7: Update record and transition to sanitized
        async with session_factory() as session:
            record = await session.get(IngestionRecord, record_id)
            record.sanitized_storage_path = storage_result.object_path
            record.word_count = structured_content.word_count

            previous_state = record.state
            record.state = IngestionState.SANITIZED.value

            # Append to state history
            history_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_state": previous_state,
                "to_state": IngestionState.SANITIZED.value,
                "triggering_event": "sanitization_complete",
            }
            current_history = list(record.state_history or [])
            current_history.append(history_entry)
            record.state_history = current_history

            # Audit log for sanitization
            audit_entry = IngestionAuditLog(
                company_id=company_id,
                ingestion_record_id=record_id,
                event_type="sanitization_complete",
                details={
                    "input_content_type": content_type,
                    "output_word_count": structured_content.word_count,
                    "sanitized_storage_path": storage_result.object_path,
                    "file_size_bytes": storage_result.file_size_bytes,
                },
            )
            session.add(audit_entry)
            await session.commit()

        logger.info(
            "Record %d sanitized: word_count=%d, path=%s.",
            record_id,
            structured_content.word_count,
            storage_result.object_path,
        )

        # Step 8: Check auto_embed_on_ingest from EmbeddingConfiguration
        # and dual_uuid_integration_enabled from IngestionConfiguration
        from alcoabase.literature.embedding.models.embedding_config import (
            EmbeddingConfiguration,
        )

        async with session_factory() as session:
            config_stmt = select(IngestionConfiguration).where(
                IngestionConfiguration.company_id == company_id
            )
            config_result = await session.execute(config_stmt)
            config = config_result.scalar_one_or_none()

            dual_uuid_enabled = (
                config.dual_uuid_integration_enabled if config else False
            )

            # Query embedding configuration for auto_embed_on_ingest
            embed_config_stmt = select(EmbeddingConfiguration).where(
                EmbeddingConfiguration.company_id == company_id
            )
            embed_config_result = await session.execute(embed_config_stmt)
            embed_config = embed_config_result.scalar_one_or_none()

            # Default: auto_embed_on_ingest=True when no config exists
            auto_embed_on_ingest = (
                embed_config.auto_embed_on_ingest if embed_config else True
            )

        if dual_uuid_enabled:
            # In a full implementation, this would dispatch a dual_uuid_extract task.
            # For now, log and continue.
            logger.info(
                "Record %d: dual_uuid_integration enabled for company %d. "
                "(dual_uuid_extract not yet implemented).",
                record_id,
                company_id,
            )

        # Step 9: Dispatch embedding generation or transition to indexed
        if auto_embed_on_ingest:
            # Dispatch generate_embeddings task to handle embedding
            # and the sanitized → indexed state transition
            from alcoabase.config import get_settings as _get_settings

            _settings = _get_settings()
            celery_app.send_task(
                "alcoabase.tasks.literature_embedding_tasks.generate_embeddings",
                kwargs={
                    "record_id": record_id,
                    "company_id": company_id,
                    "triggering_event": "auto",
                },
                queue=_settings.literature_embedding_queue,
                priority=5,
            )
            logger.info(
                "Dispatched generate_embeddings task for record_id=%d, "
                "company_id=%d (auto_embed_on_ingest=True).",
                record_id,
                company_id,
            )
        else:
            # No auto-embedding: transition directly to indexed
            async with session_factory() as session:
                record = await session.get(IngestionRecord, record_id)
                previous_state = record.state
                record.state = IngestionState.INDEXED.value

                triggering_event = (
                    "dual_uuid_skipped"
                    if not dual_uuid_enabled
                    else "dual_uuid_complete"
                )

                history_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "from_state": previous_state,
                    "to_state": IngestionState.INDEXED.value,
                    "triggering_event": triggering_event,
                }
                current_history = list(record.state_history or [])
                current_history.append(history_entry)
                record.state_history = current_history

                audit_entry = IngestionAuditLog(
                    company_id=company_id,
                    ingestion_record_id=record_id,
                    event_type="state_transition",
                    details={
                        "from_state": previous_state,
                        "to_state": IngestionState.INDEXED.value,
                        "triggering_event": triggering_event,
                    },
                )
                session.add(audit_entry)
                await session.commit()

            logger.info(
                "Record %d transitioned to indexed "
                "(auto_embed_on_ingest=False, manual trigger via API).",
                record_id,
            )

        return {
            "status": "completed",
            "record_id": record_id,
            "word_count": structured_content.word_count,
            "sanitized_path": storage_result.object_path,
            "dual_uuid_enabled": dual_uuid_enabled,
            "embedding_dispatched": auto_embed_on_ingest,
        }

    finally:
        await redis_client.aclose()


# ---------------------------------------------------------------------------
# Retention Cleanup Periodic Task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="alcoabase.tasks.literature_ingestion_tasks.retention_cleanup_task",
    queue="literature_ingestion",
)
def retention_cleanup_task() -> dict[str, Any]:
    """Periodic task: clean up files past their retention expiry date.

    Identifies IngestionRecords with original files past retention_expiry_date,
    deletes original files from MinIO (retains sanitized content), updates
    records with original_file_purged=True and purge_timestamp, and logs
    audit events for each purge.

    Records with retention_days=0 (indefinite retention) have a NULL
    retention_expiry_date and are never selected for cleanup.

    Processes in batches of 100 per execution to avoid overwhelming
    MinIO with bulk deletions.

    Returns:
        Dict with cleanup results (files_deleted, audit_entries_created).

    References:
        - Requirements 13.1, 13.2, 13.3, 13.4, 13.5, 13.6
    """
    result = asyncio.run(_retention_cleanup_async())
    return result


async def _retention_cleanup_async() -> dict[str, Any]:
    """Async implementation of the retention cleanup logic.

    1. Creates StorageManager with MinIO client inside async context
    2. Calls storage_manager.cleanup_expired_files(batch_size=100)
    3. Logs the number of files deleted
    4. Queries recently purged records and creates IngestionAuditLog entries

    Returns:
        Dict with files_deleted count and audit_entries_created count.
    """
    from datetime import timedelta

    import aioboto3
    import redis.asyncio as redis
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.literature.ingestion.models.ingestion import (
        IngestionAuditLog,
        IngestionRecord,
    )
    from alcoabase.literature.ingestion.services.storage_manager import (
        StorageManager,
    )

    settings = get_settings()
    session_factory = _get_session_factory()

    # Build MinIO endpoint URL following existing project patterns
    protocol = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{protocol}://{settings.minio_endpoint}"

    redis_client = redis.from_url(settings.redis_url)

    minio_session = aioboto3.Session()
    async with minio_session.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        use_ssl=settings.minio_use_ssl,
    ) as s3_client:
        storage_manager = StorageManager(
            bucket_name=settings.ingestion_literature_bucket,
            s3_client=s3_client,
            redis_client=redis_client,
            session_factory=session_factory,
        )

        # Step 1: Run cleanup of expired files (batch of 100)
        deleted_count = await storage_manager.cleanup_expired_files(batch_size=100)

    logger.info(
        "retention_cleanup_task: deleted %d expired original files",
        deleted_count,
    )

    # Step 2: Create audit log entries for recently purged records
    audit_entries_created = 0

    if deleted_count > 0:
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        async with session_factory() as session:
            # Query records that were just purged (purge_timestamp within last hour)
            stmt = (
                select(IngestionRecord)
                .where(
                    IngestionRecord.original_file_purged.is_(True),
                    IngestionRecord.purge_timestamp >= one_hour_ago,
                )
                .limit(100)
            )
            result = await session.execute(stmt)
            purged_records = result.scalars().all()

            for record in purged_records:
                audit_entry = IngestionAuditLog(
                    company_id=record.company_id,
                    ingestion_record_id=record.id,
                    event_type="retention_purge",
                    details={
                        "action": "original_file_purged",
                        "file_path": record.storage_path,
                        "file_size_bytes": record.file_size_bytes,
                        "retention_policy_applied": True,
                        "purge_timestamp": (
                            record.purge_timestamp.isoformat()
                            if record.purge_timestamp
                            else None
                        ),
                        "retention_expiry_date": (
                            record.retention_expiry_date.isoformat()
                            if record.retention_expiry_date
                            else None
                        ),
                    },
                    user_id=None,  # System-initiated cleanup
                )
                session.add(audit_entry)
                audit_entries_created += 1

            await session.commit()

        logger.info(
            "retention_cleanup_task: created %d audit log entries for purged files",
            audit_entries_created,
        )

    await redis_client.aclose()

    return {
        "files_deleted": deleted_count,
        "audit_entries_created": audit_entries_created,
    }
