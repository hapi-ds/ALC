"""Main orchestrator for the ingestion pipeline.

Coordinates batch ingestion submission, deduplication, state transitions,
retry logic, storage quota enforcement, and audit logging. Dispatches
Celery tasks for asynchronous processing of each pipeline stage.

References:
    - Requirements 1.1–1.8, 2.1–2.7, 8.3, 8.4
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, or_, select

from alcoabase.literature.ingestion.exceptions import (
    BatchTooLargeError,
    MaxRetriesExceededError,
    StorageQuotaExceededError,
)
from alcoabase.literature.ingestion.models.ingestion import (
    IngestionAuditLog,
    IngestionConfiguration,
    IngestionRecord,
)
from alcoabase.literature.ingestion.schemas.ingestion import (
    BatchIngestionResponse,
    LiteratureSearchResultInput,
)
from alcoabase.literature.ingestion.services.state_machine import (
    IngestionState,
    is_valid_retry_transition,
    is_valid_transition,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from alcoabase.literature.ingestion.adapters.unpaywall_adapter import (
        UnpaywallAdapter,
    )
    from alcoabase.literature.ingestion.services.sanitization.pipeline import (
        SanitizationPipeline,
    )
    from alcoabase.literature.ingestion.services.storage_manager import (
        StorageManager,
    )
    from alcoabase.literature.services.audit_logger import AuditLogger
    from alcoabase.literature.services.circuit_breaker import CircuitBreaker
    from alcoabase.literature.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Maximum batch size for ingestion submissions
MAX_BATCH_SIZE = 100

# Maximum retry attempts before failing permanently
MAX_RETRIES = 3

# Storage quota thresholds (as fractions)
QUOTA_WARNING_THRESHOLD = 0.90
QUOTA_EXCEEDED_THRESHOLD = 1.00


class IngestionPipelineService:
    """Orchestrates the dual-stage ingestion pipeline.

    Responsibilities:
        - Accept LiteratureSearchResult submissions in batches
        - Deduplicate against existing records per company
        - Create IngestionRecords and enforce state transitions
        - Dispatch Celery tasks per pipeline stage
        - Coordinate with storage manager for quota enforcement
        - Log all actions via audit logger

    Args:
        session_factory: SQLAlchemy async session factory.
        storage_manager: MinIO storage operations.
        unpaywall_adapter: DOI resolution via Unpaywall API.
        sanitization_pipeline: Format-specific content extraction.
        audit_logger: Audit trail recording.
        rate_limiter: Unpaywall rate limiting.
        circuit_breaker: Unpaywall circuit breaker.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        storage_manager: StorageManager,
        unpaywall_adapter: UnpaywallAdapter,
        sanitization_pipeline: SanitizationPipeline,
        audit_logger: AuditLogger,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
    ) -> None:
        """Initialize with all required dependencies.

        Args:
            session_factory: SQLAlchemy async session factory.
            storage_manager: MinIO storage operations.
            unpaywall_adapter: DOI resolution.
            sanitization_pipeline: Format-specific content extraction.
            audit_logger: Audit trail recording.
            rate_limiter: Unpaywall rate limiting.
            circuit_breaker: Unpaywall circuit breaker.
        """
        self._session_factory = session_factory
        self._storage_manager = storage_manager
        self._unpaywall_adapter = unpaywall_adapter
        self._sanitization_pipeline = sanitization_pipeline
        self._audit_logger = audit_logger
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker

    async def submit_batch(
        self,
        results: list[LiteratureSearchResultInput],
        company_id: int,
        user_id: int,
    ) -> BatchIngestionResponse:
        """Submit a batch of search results for ingestion.

        Creates IngestionRecords for non-duplicate items, deduplicates
        against existing records, and dispatches Stage 1 Celery tasks.

        Args:
            results: Up to 100 LiteratureSearchResult-compatible objects.
            company_id: Requesting company (tenant scope).
            user_id: Requesting user (audit attribution).

        Returns:
            BatchIngestionResponse with batch_id and per-item status.

        Raises:
            BatchTooLargeError: If more than 100 results submitted.
            StorageQuotaExceededError: If company storage quota is exceeded.
        """
        if len(results) > MAX_BATCH_SIZE:
            raise BatchTooLargeError(
                f"Batch size {len(results)} exceeds maximum of {MAX_BATCH_SIZE}.",
                company_id=company_id,
                batch_size=len(results),
                max_batch_size=MAX_BATCH_SIZE,
            )

        # Check storage quota before processing
        quota_warning, quota_exceeded = await self.check_quota(company_id)
        if quota_exceeded:
            raise StorageQuotaExceededError(
                "Company storage quota exceeded. Cannot accept new submissions.",
                company_id=company_id,
            )

        batch_id = str(uuid4())
        duplicate_count = 0
        created_ids: list[int] = []

        async with self._session_factory() as session:
            for result in results:
                # Check for duplicate
                existing_id = await self._check_duplicate_in_session(
                    session,
                    company_id=company_id,
                    doi=result.doi,
                    source_id=result.source_id,
                    external_id=result.external_id,
                )

                if existing_id is not None:
                    duplicate_count += 1
                    continue

                # Determine initial state based on abstract presence
                initial_state = (
                    IngestionState.ABSTRACT_INDEXED
                    if result.abstract
                    else IngestionState.METADATA_ONLY
                )

                # Create IngestionRecord
                record = IngestionRecord(
                    company_id=company_id,
                    batch_id=batch_id,
                    state=initial_state.value,
                    title=result.title,
                    authors=result.authors,
                    doi=result.doi,
                    publication_date=result.publication_date,
                    journal_or_venue=result.journal_or_venue,
                    publication_type=result.publication_type,
                    external_id=result.external_id,
                    source_id=result.source_id,
                    url=result.url,
                    abstract=result.abstract,
                    state_history=[
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "from_state": None,
                            "to_state": initial_state.value,
                            "triggering_event": "batch_submission",
                        }
                    ],
                )
                session.add(record)
                await session.flush()
                created_ids.append(record.id)

                # Log creation audit event
                audit_entry = IngestionAuditLog(
                    company_id=company_id,
                    ingestion_record_id=record.id,
                    event_type="record_created",
                    details={
                        "batch_id": batch_id,
                        "initial_state": initial_state.value,
                        "doi": result.doi,
                        "external_id": result.external_id,
                        "source_id": result.source_id,
                    },
                    user_id=user_id,
                )
                session.add(audit_entry)

            await session.commit()

        # Dispatch Stage 1 Celery tasks for created records
        # Reference task by name to avoid circular imports
        self._dispatch_stage1_tasks(created_ids, company_id, user_id, batch_id)

        if quota_warning:
            logger.warning(
                "Company %d storage quota at >= 90%%. "
                "Batch %s submitted with %d records.",
                company_id,
                batch_id,
                len(created_ids),
            )

        return BatchIngestionResponse(
            batch_id=batch_id,
            submitted_count=len(results),
            duplicate_count=duplicate_count,
            created_ids=created_ids,
        )

    async def check_duplicate(
        self,
        company_id: int,
        doi: str | None,
        source_id: str | None,
        external_id: str | None,
    ) -> int | None:
        """Check if an equivalent IngestionRecord already exists.

        Deduplication key: (company_id + DOI) OR
        (company_id + source_id + external_id).

        Args:
            company_id: Tenant scope.
            doi: Digital Object Identifier (may be None).
            source_id: Source adapter name.
            external_id: Source-specific identifier.

        Returns:
            Existing IngestionRecord ID if duplicate found, None otherwise.
        """
        async with self._session_factory() as session:
            return await self._check_duplicate_in_session(
                session,
                company_id=company_id,
                doi=doi,
                source_id=source_id,
                external_id=external_id,
            )

    async def transition_state(
        self,
        record_id: int,
        target_state: IngestionState,
        company_id: int,
        triggering_event: str,
        error_details: dict | None = None,
    ) -> bool:
        """Validate and persist a state transition for an IngestionRecord.

        Enforces valid transitions via the state machine, persists the
        new state, records transition history, and logs the audit event.

        Args:
            record_id: The IngestionRecord to transition.
            target_state: Desired next state.
            company_id: Tenant scope for validation.
            triggering_event: Description of what caused this transition.
            error_details: Optional dict with error_type and error_message
                when transitioning to FAILED.

        Returns:
            True if the transition succeeded, False if invalid.
        """
        async with self._session_factory() as session:
            record = await session.get(IngestionRecord, record_id)
            if record is None:
                logger.warning(
                    "Record %d not found for state transition.", record_id
                )
                return False

            if record.company_id != company_id:
                logger.warning(
                    "Company mismatch for record %d: expected %d, got %d.",
                    record_id,
                    record.company_id,
                    company_id,
                )
                return False

            current_state = IngestionState(record.state)

            if not is_valid_transition(current_state, target_state):
                logger.warning(
                    "Invalid state transition for record %d: %s → %s "
                    "(triggered by: %s).",
                    record_id,
                    current_state.value,
                    target_state.value,
                    triggering_event,
                )
                return False

            # Persist the transition
            previous_state = record.state
            record.state = target_state.value

            # Handle FAILED state details
            if target_state == IngestionState.FAILED:
                record.failed_from_state = previous_state
                if error_details:
                    record.error_type = error_details.get("error_type")
                    record.error_message = error_details.get("error_message")

            # Append to state history
            history_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_state": previous_state,
                "to_state": target_state.value,
                "triggering_event": triggering_event,
            }
            current_history = list(record.state_history or [])
            current_history.append(history_entry)
            record.state_history = current_history

            # Log audit event
            audit_entry = IngestionAuditLog(
                company_id=company_id,
                ingestion_record_id=record_id,
                event_type="state_transition",
                details={
                    "from_state": previous_state,
                    "to_state": target_state.value,
                    "triggering_event": triggering_event,
                    **(
                        {"error_details": error_details}
                        if error_details
                        else {}
                    ),
                },
            )
            session.add(audit_entry)

            await session.commit()

        logger.info(
            "Record %d transitioned: %s → %s (event: %s).",
            record_id,
            previous_state,
            target_state.value,
            triggering_event,
        )

        # Phase 9.4: Dispatch cross-reference and auto-screening tasks on indexed
        if target_state == IngestionState.INDEXED:
            await self._dispatch_phase94_tasks(record_id, company_id)
            # Phase 9.5: Dispatch vigilance signal detection for vigilance-linked records
            await self._dispatch_phase95_vigilance_tasks(record_id, company_id)

        return True

    async def retry_failed_record(
        self,
        record_id: int,
        company_id: int,
        user_id: int,
    ) -> bool:
        """Retry a failed ingestion record from its last successful state.

        Validates that the record is in FAILED state, that retries have
        not been exhausted, and dispatches the appropriate Celery task
        to reprocess from the failed_from_state.

        Args:
            record_id: The IngestionRecord to retry.
            company_id: Tenant scope for validation.
            user_id: User triggering the retry (audit attribution).

        Returns:
            True if the retry was initiated.

        Raises:
            MaxRetriesExceededError: If retry_count >= 3.
        """
        async with self._session_factory() as session:
            record = await session.get(IngestionRecord, record_id)
            if record is None:
                logger.warning(
                    "Record %d not found for retry.", record_id
                )
                return False

            if record.company_id != company_id:
                logger.warning(
                    "Company mismatch for record %d retry.", record_id
                )
                return False

            current_state = IngestionState(record.state)
            if current_state != IngestionState.FAILED:
                logger.warning(
                    "Record %d is in state '%s', not FAILED. Cannot retry.",
                    record_id,
                    current_state.value,
                )
                return False

            if record.retry_count >= MAX_RETRIES:
                raise MaxRetriesExceededError(
                    f"Record {record_id} has exhausted all {MAX_RETRIES} retry attempts.",
                    company_id=company_id,
                    record_id=record_id,
                    retry_count=record.retry_count,
                    max_retries=MAX_RETRIES,
                    last_error=record.error_message,
                )

            # Determine target state from failed_from_state
            failed_from = record.failed_from_state
            if failed_from is None:
                logger.warning(
                    "Record %d has no failed_from_state. Cannot retry.",
                    record_id,
                )
                return False

            target_state = IngestionState(failed_from)

            # Validate retry transition
            if not is_valid_retry_transition(current_state, target_state):
                logger.warning(
                    "Invalid retry transition for record %d: FAILED → %s.",
                    record_id,
                    target_state.value,
                )
                return False

            # Increment retry count and transition state
            record.retry_count += 1
            record.state = target_state.value
            record.error_type = None
            record.error_message = None
            record.failed_from_state = None

            # Append to state history
            history_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_state": IngestionState.FAILED.value,
                "to_state": target_state.value,
                "triggering_event": f"manual_retry_by_user_{user_id}",
            }
            current_history = list(record.state_history or [])
            current_history.append(history_entry)
            record.state_history = current_history

            # Log audit event
            audit_entry = IngestionAuditLog(
                company_id=company_id,
                ingestion_record_id=record_id,
                event_type="retry_initiated",
                details={
                    "retry_count": record.retry_count,
                    "target_state": target_state.value,
                    "previous_error_type": record.error_type,
                },
                user_id=user_id,
            )
            session.add(audit_entry)

            await session.commit()

        # Dispatch appropriate Celery task based on target state
        self._dispatch_retry_task(record_id, target_state, company_id)

        logger.info(
            "Record %d retry initiated: FAILED → %s (attempt %d).",
            record_id,
            target_state.value,
            record.retry_count,
        )
        return True

    async def get_state_counts(self, company_id: int) -> dict[str, int]:
        """Get aggregated counts of records per state for a company.

        Args:
            company_id: Tenant scope.

        Returns:
            Dictionary mapping state names to record counts.
        """
        async with self._session_factory() as session:
            stmt = (
                select(
                    IngestionRecord.state,
                    func.count(IngestionRecord.id),
                )
                .where(IngestionRecord.company_id == company_id)
                .group_by(IngestionRecord.state)
            )
            result = await session.execute(stmt)
            rows = result.all()

        # Build counts dict with all states initialized to 0
        counts: dict[str, int] = {state.value: 0 for state in IngestionState}
        for state_value, count in rows:
            counts[state_value] = count

        return counts

    async def check_quota(self, company_id: int) -> tuple[bool, bool]:
        """Check company storage quota status.

        Compares current usage against the company's configured quota.
        Returns warning flag (>=90%) and exceeded flag (>=100%).

        Args:
            company_id: Tenant scope.

        Returns:
            Tuple of (quota_warning, quota_exceeded) booleans.
        """
        usage_bytes = await self._storage_manager.get_company_usage_bytes(
            company_id
        )
        quota_mb = await self._get_company_quota_mb(company_id)
        quota_bytes = quota_mb * 1024 * 1024

        if quota_bytes <= 0:
            # No quota configured — no restrictions
            return False, False

        usage_ratio = usage_bytes / quota_bytes
        quota_warning = usage_ratio >= QUOTA_WARNING_THRESHOLD
        quota_exceeded = usage_ratio >= QUOTA_EXCEEDED_THRESHOLD

        return quota_warning, quota_exceeded

    # ─────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _check_duplicate_in_session(
        self,
        session: object,
        *,
        company_id: int,
        doi: str | None,
        source_id: str | None,
        external_id: str | None,
    ) -> int | None:
        """Check for duplicates within an existing session.

        Args:
            session: Active SQLAlchemy async session.
            company_id: Tenant scope.
            doi: Digital Object Identifier (may be None).
            source_id: Source adapter name.
            external_id: Source-specific identifier.

        Returns:
            Existing IngestionRecord ID if duplicate found, None otherwise.
        """
        conditions = []

        # DOI-based deduplication (only if DOI is provided)
        if doi:
            conditions.append(
                (IngestionRecord.company_id == company_id)
                & (IngestionRecord.doi == doi)
            )

        # Source + external_id deduplication
        if source_id and external_id:
            conditions.append(
                (IngestionRecord.company_id == company_id)
                & (IngestionRecord.source_id == source_id)
                & (IngestionRecord.external_id == external_id)
            )

        if not conditions:
            return None

        stmt = select(IngestionRecord.id).where(or_(*conditions)).limit(1)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def _get_company_quota_mb(self, company_id: int) -> int:
        """Retrieve the storage quota in MB for a company.

        Falls back to the default (10240 MB) if no configuration exists.

        Args:
            company_id: Tenant scope.

        Returns:
            Storage quota in megabytes.
        """
        async with self._session_factory() as session:
            stmt = select(IngestionConfiguration.storage_quota_mb).where(
                IngestionConfiguration.company_id == company_id
            )
            result = await session.execute(stmt)
            quota = result.scalar_one_or_none()

        # Default to 10 GB if no config exists
        return quota if quota is not None else 10240

    def _dispatch_stage1_tasks(
        self,
        record_ids: list[int],
        company_id: int,
        user_id: int,
        batch_id: str,
    ) -> None:
        """Dispatch Stage 1 Celery tasks for newly created records.

        Uses send_task by name to avoid circular imports with the
        Celery task module.

        Args:
            record_ids: List of IngestionRecord IDs to process.
            company_id: Tenant scope.
            user_id: Requesting user.
            batch_id: Batch UUID for grouping.
        """
        from alcoabase.tasks.celery_app import celery_app

        for record_id in record_ids:
            celery_app.send_task(
                "alcoabase.tasks.literature_ingestion_tasks.ingest_stage1_metadata",
                kwargs={
                    "record_id": record_id,
                    "company_id": company_id,
                    "user_id": user_id,
                    "batch_id": batch_id,
                },
                queue="literature_ingestion",
                priority=1,  # High priority
            )

    def _dispatch_retry_task(
        self,
        record_id: int,
        target_state: IngestionState,
        company_id: int,
    ) -> None:
        """Dispatch the appropriate Celery task for a retry operation.

        Selects the task based on which state the record is retrying from.

        Args:
            record_id: The IngestionRecord to retry.
            target_state: The state being retried.
            company_id: Tenant scope.
        """
        from alcoabase.tasks.celery_app import celery_app

        task_name_map: dict[IngestionState, str] = {
            IngestionState.FULL_TEXT_PENDING: (
                "alcoabase.tasks.literature_ingestion_tasks.ingest_stage2_download"
            ),
            IngestionState.FULL_TEXT_DOWNLOADED: (
                "alcoabase.tasks.literature_ingestion_tasks.ingest_sanitize"
            ),
            IngestionState.SANITIZED: (
                "alcoabase.tasks.literature_ingestion_tasks.ingest_sanitize"
            ),
        }

        task_name = task_name_map.get(target_state)
        if task_name is None:
            logger.warning(
                "No retry task mapped for target state '%s' on record %d.",
                target_state.value,
                record_id,
            )
            return

        celery_app.send_task(
            task_name,
            kwargs={
                "record_id": record_id,
                "company_id": company_id,
            },
            queue="literature_ingestion",
        )

    async def _dispatch_phase94_tasks(
        self,
        record_id: int,
        company_id: int,
    ) -> None:
        """Dispatch Phase 9.4 tasks when a record transitions to indexed.

        Checks the company's ScreeningConfiguration to determine which
        tasks to fire:
        - If contradiction_detection_enabled: dispatch execute_cross_reference
        - If auto_screen_on_index: dispatch auto_screen_on_index

        Both dispatches are fire-and-forget and do not block the pipeline.
        If no ScreeningConfiguration exists, defaults are used:
        contradiction_detection_enabled=True, auto_screen_on_index=False.

        Args:
            record_id: The IngestionRecord that reached indexed state.
            company_id: Tenant scope.

        References:
            - Requirements 5.1, 11.2, 11.3
        """
        from sqlalchemy import select

        from alcoabase.literature.review.models.screening_config import (
            ScreeningConfiguration,
        )
        from alcoabase.tasks.literature_screening_tasks import (
            auto_screen_on_index,
            execute_cross_reference,
        )

        # Load company screening configuration (or use defaults)
        contradiction_detection_enabled = True
        auto_screen_on_index_enabled = False

        async with self._session_factory() as session:
            stmt = select(ScreeningConfiguration).where(
                ScreeningConfiguration.company_id == company_id
            )
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()

            if config is not None:
                contradiction_detection_enabled = config.contradiction_detection_enabled
                auto_screen_on_index_enabled = config.auto_screen_on_index

        # Dispatch cross-reference task if contradiction detection is enabled
        if contradiction_detection_enabled:
            execute_cross_reference.delay(
                record_id=record_id,
                company_id=company_id,
            )
            logger.info(
                "Dispatched execute_cross_reference for record %d (company %d).",
                record_id,
                company_id,
            )

        # Dispatch auto-screen task if auto-screening is enabled
        if auto_screen_on_index_enabled:
            auto_screen_on_index.delay(
                record_id=record_id,
                company_id=company_id,
            )
            logger.info(
                "Dispatched auto_screen_on_index for record %d (company %d).",
                record_id,
                company_id,
            )

    async def _dispatch_phase95_vigilance_tasks(
        self,
        record_id: int,
        company_id: int,
    ) -> None:
        """Dispatch Phase 9.5 signal detection when a vigilance-linked record is indexed.

        Checks whether the record has a vigilance_execution_id linkage. If so,
        loads the associated profile and product metadata, batches records per
        `vigilance_signal_batch_size`, and dispatches execute_signal_detection
        tasks on the ai_operations queue.

        Only dispatches for records actually linked to a VigilanceSearchExecution
        (not regular ingestion records).

        Args:
            record_id: The IngestionRecord that reached indexed state.
            company_id: Tenant scope.

        References:
            - Requirements 5.1, 5.7
        """
        from sqlalchemy import select

        from alcoabase.config import get_settings
        from alcoabase.literature.ingestion.models.ingestion import (
            IngestionRecord,
        )
        from alcoabase.literature.vigilance.models.vigilance_search_execution import (
            VigilanceSearchExecution,
        )
        from alcoabase.tasks.vigilance_tasks import execute_signal_detection

        async with self._session_factory() as session:
            # Load the record and check for vigilance linkage
            record = await session.get(IngestionRecord, record_id)
            if record is None or record.vigilance_execution_id is None:
                return

            execution_id = record.vigilance_execution_id

            # Load the execution to get profile_id
            execution = await session.get(
                VigilanceSearchExecution, execution_id
            )
            if execution is None:
                logger.warning(
                    "VigilanceSearchExecution %d not found for record %d. "
                    "Skipping signal detection dispatch.",
                    execution_id,
                    record_id,
                )
                return

            profile_id = execution.profile_id

            # Load profile to get product_id
            from alcoabase.literature.vigilance.models.vigilance_search_profile import (
                VigilanceSearchProfile,
            )

            profile = await session.get(VigilanceSearchProfile, profile_id)
            if profile is None:
                logger.warning(
                    "VigilanceSearchProfile %d not found for execution %d. "
                    "Skipping signal detection dispatch.",
                    profile_id,
                    execution_id,
                )
                return

            product_id = profile.product_id

            # Collect all indexed records for this execution that haven't
            # been dispatched yet. Batching groups records from the same
            # execution to send them together.
            settings = get_settings()
            batch_size = settings.vigilance_signal_batch_size

            stmt = select(IngestionRecord.id).where(
                IngestionRecord.company_id == company_id,
                IngestionRecord.vigilance_execution_id == execution_id,
                IngestionRecord.state == "indexed",
            )
            result = await session.execute(stmt)
            indexed_record_ids = [row[0] for row in result.fetchall()]

        # Dispatch in batches
        if not indexed_record_ids:
            return

        for i in range(0, len(indexed_record_ids), batch_size):
            batch = indexed_record_ids[i : i + batch_size]
            execute_signal_detection.apply_async(
                kwargs={
                    "record_ids": batch,
                    "product_id": product_id,
                    "profile_id": profile_id,
                    "execution_id": execution_id,
                    "company_id": company_id,
                },
                queue=settings.vigilance_signal_queue,
            )
            logger.info(
                "Dispatched execute_signal_detection for %d records "
                "(execution_id=%d, product_id=%d, company_id=%d, batch %d).",
                len(batch),
                execution_id,
                product_id,
                company_id,
                (i // batch_size) + 1,
            )
