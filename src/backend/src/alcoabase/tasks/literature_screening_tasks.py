"""Celery tasks for literature screening execution.

Implements the asynchronous task layer for:
- Batch screening of ingested literature via the Literature Screener Agent
- Cross-reference analysis of newly indexed papers against internal docs
- Auto-screening dispatch upon paper indexing (when company config enables it)

All tasks use the ``ai_operations`` queue and follow the pattern of running
async service operations via ``asyncio.run()`` from synchronous Celery workers.

References:
    - Requirements 3.3, 3.4, 3.5, 3.7, 3.8, 5.1, 5.8, 11.2, 13.1, 13.4, 13.5, 13.6
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Retry backoff schedules (seconds)
# ---------------------------------------------------------------------------

_SCREENING_RETRY_BACKOFF: list[int] = [30, 120, 600]
_CROSS_REFERENCE_RETRY_BACKOFF: list[int] = [30, 120, 600]


# ---------------------------------------------------------------------------
# Helpers — Lazy service factory (Celery workers don't share FastAPI lifespan)
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


def _get_inference_client():
    """Create an InferenceClient for vLLM chat completion.

    Returns:
        Configured InferenceClient instance.
    """
    from alcoabase.config import get_settings
    from alcoabase.services.inference_client import InferenceClient

    settings = get_settings()
    return InferenceClient(
        base_url=settings.vllm_base_url,
        embedding_base_url=settings.vllm_embedding_url,
    )


def _get_agent_registry():
    """Get an AgentRegistryService instance for task workers.

    Returns:
        Configured AgentRegistryService.
    """
    from pathlib import Path

    from alcoabase.config import get_settings
    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.schema_validator import SchemaValidator

    settings = get_settings()
    session_factory = _get_session_factory()

    agents_dir = (
        Path(settings.agents_dir)
        if hasattr(settings, "agents_dir")
        else Path("/app/agents/examples")
    )
    archetypes_dir = (
        Path(settings.archetypes_dir)
        if hasattr(settings, "archetypes_dir")
        else Path("/app/agents/archetypes")
    )

    schema_validator = SchemaValidator(
        schema_dir=(
            Path(settings.agent_schema_dir)
            if hasattr(settings, "agent_schema_dir")
            else Path("/app/agents/schema")
        )
    )

    return AgentRegistryService(
        session_factory=session_factory,
        schema_validator=schema_validator,
        agents_dir=agents_dir,
        archetypes_dir=archetypes_dir,
    )


def _get_screener_runner():
    """Instantiate LiteratureScreenerAgentRunner with all dependencies.

    Returns:
        Configured LiteratureScreenerAgentRunner.
    """
    from alcoabase.config import get_settings
    from alcoabase.literature.review.services.screener_agent_runner import (
        LiteratureScreenerAgentRunner,
    )

    settings = get_settings()
    inference_client = _get_inference_client()
    agent_registry = _get_agent_registry()

    return LiteratureScreenerAgentRunner(
        inference_client=inference_client,
        agent_registry=agent_registry,
        model_name=settings.model_chat_name,
    )


def _get_contradiction_detection_service():
    """Instantiate ContradictionDetectionService with all dependencies.

    Returns:
        Configured ContradictionDetectionService.
    """
    from opensearchpy import AsyncOpenSearch

    from alcoabase.config import get_settings
    from alcoabase.literature.embedding.services.hybrid_query_engine import (
        HybridQueryEngine,
    )
    from alcoabase.literature.embedding.services.index_manager import (
        LiteratureIndexManager,
    )
    from alcoabase.literature.review.services.contradiction_detection_service import (
        ContradictionDetectionService,
    )
    from alcoabase.services.impact_analysis import ImpactAnalysisService
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.knowledge_service import KnowledgeService
    from alcoabase.services.model_manager import ModelManager

    settings = get_settings()
    session_factory = _get_session_factory()

    # Chat inference client
    chat_client = InferenceClient(
        base_url=settings.vllm_base_url,
        embedding_base_url=settings.vllm_embedding_url,
    )

    # Embedding inference client for HybridQueryEngine
    embedding_client = InferenceClient(
        base_url=settings.vllm_embedding_url,
    )
    model_manager = ModelManager(inference_client=embedding_client)

    # OpenSearch client
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
    )

    hybrid_query_engine = HybridQueryEngine(
        index_manager=index_manager,
        inference_client=embedding_client,
        model_manager=model_manager,
        model_name=settings.model_embedding_name,
    )

    # ImpactAnalysisService (minimal deps for contradiction escalation)
    knowledge_service = KnowledgeService()
    impact_service = ImpactAnalysisService(
        knowledge_service=knowledge_service,
        inference_client=chat_client,
        agent_registry=None,
        session_factory=session_factory,
        job_tracker=None,
    )

    return ContradictionDetectionService(
        session_factory=session_factory,
        hybrid_query_engine=hybrid_query_engine,
        inference_client=chat_client,
        impact_analysis_service=impact_service,
        model_name=settings.model_chat_name,
        similarity_threshold=settings.contradiction_similarity_threshold,
        confidence_threshold=settings.contradiction_confidence_threshold,
        max_candidates=settings.contradiction_max_candidates,
    )


# ---------------------------------------------------------------------------
# Task 1: execute_screening_batch
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="literature.execute_screening_batch",
    queue="ai_operations",
    priority=5,
    max_retries=3,
    soft_time_limit=1800,
    acks_late=True,
)
def execute_screening_batch(
    self,
    *,
    screening_run_id: int,
    review_id: int,
    protocol_id: int,
    company_id: int,
    batch_size: int = 20,
    re_screen_uncertain: bool = False,
) -> dict[str, Any]:
    """Execute a screening batch for an SLR Review.

    Loads protocol criteria, instantiates LiteratureScreenerAgentRunner,
    processes records via screen_batch(), persists ScreeningDecisions,
    and updates ScreeningRun progress. Idempotent: skips records with
    existing decisions in this run.

    On completion, updates SLR_Review PRISMA stats and checks
    auto-completion conditions.

    Args:
        self: Celery task instance (bound for retry support).
        screening_run_id: The ScreeningRun record ID.
        review_id: Parent SLR Review ID.
        protocol_id: ScreeningProtocol to apply.
        company_id: Tenant scope.
        batch_size: Records per batch.
        re_screen_uncertain: Whether to only re-screen uncertain records.

    Returns:
        Dict with execution status, counts, and timing.

    Raises:
        self.retry(): On unhandled exceptions when retries remain.
    """
    logger.info(
        "execute_screening_batch: run_id=%d, review_id=%d, "
        "protocol_id=%d, company_id=%d, batch_size=%d, re_screen=%s, "
        "attempt=%d/%d",
        screening_run_id,
        review_id,
        protocol_id,
        company_id,
        batch_size,
        re_screen_uncertain,
        self.request.retries + 1,
        self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            _process_screening_batch(
                screening_run_id=screening_run_id,
                review_id=review_id,
                protocol_id=protocol_id,
                company_id=company_id,
                batch_size=batch_size,
                re_screen_uncertain=re_screen_uncertain,
            )
        )
        logger.info(
            "execute_screening_batch completed: run_id=%d, screened=%d, "
            "include=%d, exclude=%d, uncertain=%d",
            screening_run_id,
            result.get("screened_count", 0),
            result.get("include_count", 0),
            result.get("exclude_count", 0),
            result.get("uncertain_count", 0),
        )
        return result

    except Exception as exc:
        from celery.exceptions import Retry

        if isinstance(exc, Retry):
            raise

        logger.error(
            "execute_screening_batch failed: run_id=%d, error=%s: %s",
            screening_run_id,
            type(exc).__name__,
            str(exc)[:500],
        )

        # Mark run as failed if retries exhausted
        if self.request.retries >= self.max_retries:
            try:
                asyncio.run(
                    _mark_screening_run_failed(
                        screening_run_id=screening_run_id,
                        error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                    )
                )
            except Exception as fail_exc:
                logger.error(
                    "Failed to mark run %d as failed: %s",
                    screening_run_id,
                    str(fail_exc)[:200],
                )

        # Exponential backoff retry
        backoff = _SCREENING_RETRY_BACKOFF
        countdown = backoff[min(self.request.retries, len(backoff) - 1)]
        raise self.retry(exc=exc, countdown=countdown)


async def _process_screening_batch(
    *,
    screening_run_id: int,
    review_id: int,
    protocol_id: int,
    company_id: int,
    batch_size: int,
    re_screen_uncertain: bool,
) -> dict[str, Any]:
    """Async implementation of screening batch processing.

    Steps:
    1. Load ScreeningRun, verify status
    2. Load ScreeningProtocol criteria
    3. Resolve records to screen (idempotent: skip already-decided)
    4. Process records in batches via LiteratureScreenerAgentRunner
    5. Persist ScreeningDecisions
    6. Update ScreeningRun progress after each batch
    7. On completion: update SLR_Review PRISMA stats, check auto-completion

    Args:
        screening_run_id: ScreeningRun record ID.
        review_id: Parent SLR Review ID.
        protocol_id: ScreeningProtocol ID.
        company_id: Tenant scope.
        batch_size: Records per batch.
        re_screen_uncertain: Only re-screen uncertain records.

    Returns:
        Dict with status, counts, and duration.
    """
    from sqlalchemy import and_, select

    from alcoabase.literature.review.models.screening_config import (
        ScreeningConfiguration,
    )
    from alcoabase.literature.review.models.screening_decision import (
        ScreeningDecision,
    )
    from alcoabase.literature.review.models.screening_protocol import (
        ScreeningProtocol,
    )
    from alcoabase.literature.review.models.screening_run import ScreeningRun
    from alcoabase.literature.review.models.slr_review import SLRReview

    session_factory = _get_session_factory()
    start_time = time.perf_counter()

    async with session_factory() as session:
        # Step 1: Load and verify ScreeningRun
        run = await session.get(ScreeningRun, screening_run_id)
        if run is None:
            logger.warning("ScreeningRun %d not found. Aborting.", screening_run_id)
            return {"status": "error", "reason": "screening_run_not_found"}

        if run.company_id != company_id:
            logger.warning(
                "Company mismatch for run %d: expected %d, got %d.",
                screening_run_id,
                company_id,
                run.company_id,
            )
            return {"status": "error", "reason": "company_mismatch"}

        # Transition to in_progress if queued
        if run.status == "queued":
            run.status = "in_progress"
            run.started_at = datetime.now(timezone.utc)

        # Step 2: Load ScreeningProtocol criteria
        protocol = await session.get(ScreeningProtocol, protocol_id)
        if protocol is None:
            logger.error("ScreeningProtocol %d not found.", protocol_id)
            run.status = "failed"
            await session.commit()
            return {"status": "error", "reason": "protocol_not_found"}

        protocol_criteria = _extract_protocol_criteria(protocol)

        # Step 3: Resolve records to screen (load SLR Review record_filter)
        review = await session.get(SLRReview, review_id)
        if review is None:
            logger.error("SLRReview %d not found.", review_id)
            run.status = "failed"
            await session.commit()
            return {"status": "error", "reason": "review_not_found"}

        # Get record IDs from the review's record_filter
        record_ids = await _resolve_record_ids(
            session, review, company_id, re_screen_uncertain, screening_run_id
        )

        if not record_ids:
            logger.info(
                "No records to screen for run %d (all already decided or empty set).",
                screening_run_id,
            )
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.total_duration_ms = int(
                (time.perf_counter() - start_time) * 1000
            )
            await session.commit()
            return {"status": "completed", "screened_count": 0, "reason": "no_records"}

        # Update run totals
        run.total_records = len(record_ids)
        run.batch_size = batch_size
        run.total_batches = math.ceil(len(record_ids) / batch_size)
        await session.commit()

    # Step 4: Process records in batches
    screener = _get_screener_runner()
    total_screened = 0
    total_include = 0
    total_exclude = 0
    total_uncertain = 0
    total_failed = 0

    num_batches = math.ceil(len(record_ids) / batch_size)

    for batch_idx in range(num_batches):
        batch_start = batch_idx * batch_size
        batch_end = batch_start + batch_size
        batch_record_ids = record_ids[batch_start:batch_end]

        # Load record data for this batch
        async with session_factory() as session:
            records_data = await _load_records_for_screening(
                session, batch_record_ids, company_id
            )

            # Idempotency check: skip records with existing decisions in this run
            existing_stmt = select(ScreeningDecision.ingestion_record_id).where(
                and_(
                    ScreeningDecision.screening_run_id == screening_run_id,
                    ScreeningDecision.ingestion_record_id.in_(batch_record_ids),
                )
            )
            existing_result = await session.execute(existing_stmt)
            already_decided = set(existing_result.scalars().all())

        # Filter out already-decided records
        records_to_screen = [
            r for r in records_data if r["record_id"] not in already_decided
        ]

        if not records_to_screen:
            logger.info(
                "Batch %d/%d: all records already decided, skipping.",
                batch_idx + 1,
                num_batches,
            )
            continue

        # Run screening via LiteratureScreenerAgentRunner
        batch_results = await screener.screen_batch(
            records=records_to_screen,
            protocol_criteria=protocol_criteria,
        )

        # Step 5: Persist ScreeningDecisions
        batch_include = 0
        batch_exclude = 0
        batch_uncertain = 0

        async with session_factory() as session:
            for record_id, screening_result in batch_results:
                decision = ScreeningDecision(
                    screening_run_id=screening_run_id,
                    ingestion_record_id=record_id,
                    protocol_id=protocol_id,
                    company_id=company_id,
                    verdict=screening_result.verdict,
                    confidence=screening_result.confidence,
                    rationale=screening_result.rationale[:2000],
                    matched_inclusion_criteria=screening_result.matched_inclusion_criteria,
                    matched_exclusion_criteria=screening_result.matched_exclusion_criteria,
                    screening_duration_ms=screening_result.screening_duration_ms,
                )
                session.add(decision)

                if screening_result.verdict == "include":
                    batch_include += 1
                elif screening_result.verdict == "exclude":
                    batch_exclude += 1
                else:
                    batch_uncertain += 1

            await session.commit()

        total_screened += len(batch_results)
        total_include += batch_include
        total_exclude += batch_exclude
        total_uncertain += batch_uncertain

        # Step 6: Update ScreeningRun progress
        async with session_factory() as session:
            run = await session.get(ScreeningRun, screening_run_id)
            if run is not None:
                run.screened_count = total_screened
                run.include_count = total_include
                run.exclude_count = total_exclude
                run.uncertain_count = total_uncertain
                run.failed_count = total_failed
                run.current_batch = batch_idx + 1
                await session.commit()

        logger.info(
            "Batch %d/%d complete: screened=%d, include=%d, exclude=%d, uncertain=%d",
            batch_idx + 1,
            num_batches,
            len(batch_results),
            batch_include,
            batch_exclude,
            batch_uncertain,
        )

    # Step 7: Mark run as completed, update SLR Review PRISMA stats
    duration_ms = int((time.perf_counter() - start_time) * 1000)

    async with session_factory() as session:
        run = await session.get(ScreeningRun, screening_run_id)
        if run is not None:
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.total_duration_ms = duration_ms

        # Update SLR Review PRISMA stats (records_identified is already set)
        review = await session.get(SLRReview, review_id)
        if review is not None:
            # Update timestamp to reflect latest activity
            review.updated_at = datetime.now(timezone.utc)

        # Check auto-completion conditions
        config_stmt = select(ScreeningConfiguration).where(
            ScreeningConfiguration.company_id == company_id
        )
        config_result = await session.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        confidence_threshold = (
            config.confidence_threshold_for_auto_include if config else 0.8
        )

        if review is not None:
            auto_complete = await _check_auto_completion(
                session, review_id, company_id, confidence_threshold
            )
            if auto_complete and review.status == "screening_in_progress":
                review.status = "screening_complete"
                logger.info(
                    "SLR Review %d auto-transitioned to screening_complete.",
                    review_id,
                )

        await session.commit()

    return {
        "status": "completed",
        "screening_run_id": screening_run_id,
        "screened_count": total_screened,
        "include_count": total_include,
        "exclude_count": total_exclude,
        "uncertain_count": total_uncertain,
        "failed_count": total_failed,
        "total_duration_ms": duration_ms,
    }


def _extract_protocol_criteria(protocol) -> dict[str, Any]:
    """Extract screening criteria from a ScreeningProtocol model instance.

    Args:
        protocol: ScreeningProtocol ORM instance.

    Returns:
        Dict with pico, inclusion, exclusion, date range, types, languages.
    """
    return {
        "pico": {
            "population": protocol.pico_population,
            "intervention": protocol.pico_intervention,
            "comparison": protocol.pico_comparison,
            "outcome": protocol.pico_outcome,
        },
        "inclusion_criteria": protocol.inclusion_criteria or [],
        "exclusion_criteria": protocol.exclusion_criteria or [],
        "publication_date_from": protocol.publication_date_from,
        "publication_date_to": protocol.publication_date_to,
        "allowed_publication_types": protocol.allowed_publication_types or [],
        "allowed_languages": protocol.allowed_languages or [],
    }


async def _resolve_record_ids(
    session,
    review,
    company_id: int,
    re_screen_uncertain: bool,
    screening_run_id: int,
) -> list[int]:
    """Resolve which IngestionRecord IDs should be screened.

    Uses the SLR Review's record_filter to determine the candidate set,
    then applies idempotency (skip records already decided in this run)
    and re_screen_uncertain logic.

    Args:
        session: Active async DB session.
        review: SLRReview model instance.
        company_id: Tenant scope.
        re_screen_uncertain: If True, only re-screen uncertain records.
        screening_run_id: Current run ID for idempotency check.

    Returns:
        List of IngestionRecord IDs to screen.
    """
    from sqlalchemy import and_, select

    from alcoabase.literature.ingestion.models.ingestion import IngestionRecord
    from alcoabase.literature.review.models.screening_decision import (
        ScreeningDecision,
    )

    record_filter = review.record_filter or {}

    # If explicit record IDs are specified in the filter
    if "ingestion_record_ids" in record_filter and record_filter["ingestion_record_ids"]:
        candidate_ids = record_filter["ingestion_record_ids"]
    else:
        # Query based on company_id and optional state filter
        stmt = select(IngestionRecord.id).where(
            IngestionRecord.company_id == company_id,
        )
        if "state" in record_filter and record_filter["state"]:
            stmt = stmt.where(IngestionRecord.state == record_filter["state"])

        result = await session.execute(stmt)
        candidate_ids = list(result.scalars().all())

    if not candidate_ids:
        return []

    if re_screen_uncertain:
        # Only re-screen records with previous "uncertain" verdict
        uncertain_stmt = select(ScreeningDecision.ingestion_record_id).where(
            and_(
                ScreeningDecision.ingestion_record_id.in_(candidate_ids),
                ScreeningDecision.company_id == company_id,
                ScreeningDecision.verdict == "uncertain",
            )
        )
        result = await session.execute(uncertain_stmt)
        candidate_ids = list(result.scalars().all())

    # Idempotency: exclude records already decided in this specific run
    if candidate_ids:
        existing_stmt = select(ScreeningDecision.ingestion_record_id).where(
            and_(
                ScreeningDecision.screening_run_id == screening_run_id,
                ScreeningDecision.ingestion_record_id.in_(candidate_ids),
            )
        )
        existing_result = await session.execute(existing_stmt)
        already_decided = set(existing_result.scalars().all())
        candidate_ids = [rid for rid in candidate_ids if rid not in already_decided]

    return candidate_ids


async def _load_records_for_screening(
    session,
    record_ids: list[int],
    company_id: int,
) -> list[dict[str, Any]]:
    """Load IngestionRecord data needed for screening.

    Args:
        session: Active async DB session.
        record_ids: IDs of records to load.
        company_id: Tenant scope.

    Returns:
        List of dicts with record_id, title, abstract, body_sections.
    """
    from sqlalchemy import select

    from alcoabase.literature.ingestion.models.ingestion import IngestionRecord

    stmt = select(IngestionRecord).where(
        IngestionRecord.id.in_(record_ids),
        IngestionRecord.company_id == company_id,
    )
    result = await session.execute(stmt)
    records = result.scalars().all()

    records_data = []
    for record in records:
        records_data.append({
            "record_id": record.id,
            "title": record.title or "",
            "abstract": record.abstract or "",
            "body_sections": record.body_sections if hasattr(record, "body_sections") else None,
        })

    return records_data


async def _check_auto_completion(
    session,
    review_id: int,
    company_id: int,
    confidence_threshold: float,
) -> bool:
    """Check if all records in a review have been resolved.

    A record is resolved if it has:
    - A human override verdict, OR
    - An uncontested AI verdict with confidence >= threshold

    Args:
        session: Active async DB session.
        review_id: SLR Review ID.
        company_id: Tenant scope.
        confidence_threshold: Min confidence for auto-include.

    Returns:
        True if all records are resolved (review can auto-complete).
    """
    from sqlalchemy import and_, func, select

    from alcoabase.literature.review.models.screening_decision import (
        ScreeningDecision,
    )
    from alcoabase.literature.review.models.screening_run import ScreeningRun
    from alcoabase.literature.review.models.slr_review import SLRReview

    # Get the review to know total records
    review = await session.get(SLRReview, review_id)
    if review is None or review.records_identified == 0:
        return False

    # Get all runs for this review
    runs_stmt = select(ScreeningRun.id).where(
        and_(
            ScreeningRun.review_id == review_id,
            ScreeningRun.company_id == company_id,
        )
    )
    runs_result = await session.execute(runs_stmt)
    run_ids = list(runs_result.scalars().all())

    if not run_ids:
        return False

    # Count resolved decisions:
    # - Has human_verdict set, OR
    # - verdict in (include, exclude) AND confidence >= threshold
    resolved_stmt = select(
        func.count(func.distinct(ScreeningDecision.ingestion_record_id))
    ).where(
        and_(
            ScreeningDecision.screening_run_id.in_(run_ids),
            ScreeningDecision.company_id == company_id,
            # A decision is resolved if human override exists or
            # AI verdict is definitive with high confidence
            (
                (ScreeningDecision.human_verdict.isnot(None))
                | (
                    (ScreeningDecision.verdict.in_(["include", "exclude"]))
                    & (ScreeningDecision.confidence >= confidence_threshold)
                )
            ),
        )
    )
    resolved_result = await session.execute(resolved_stmt)
    resolved_count = resolved_result.scalar() or 0

    return resolved_count >= review.records_identified


async def _mark_screening_run_failed(
    screening_run_id: int,
    error_message: str,
) -> None:
    """Mark a ScreeningRun as failed.

    Args:
        screening_run_id: The run to mark as failed.
        error_message: Error description.
    """
    from alcoabase.literature.review.models.screening_run import ScreeningRun

    session_factory = _get_session_factory()

    async with session_factory() as session:
        run = await session.get(ScreeningRun, screening_run_id)
        if run is not None:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            logger.error(
                "ScreeningRun %d marked as failed: %s",
                screening_run_id,
                error_message[:200],
            )
        await session.commit()


# ---------------------------------------------------------------------------
# Task 2: execute_cross_reference
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="literature.execute_cross_reference",
    queue="ai_operations",
    priority=4,
    max_retries=3,
    soft_time_limit=600,
    acks_late=True,
)
def execute_cross_reference(
    self,
    *,
    record_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Cross-reference a newly indexed record against internal documents.

    Instantiates ContradictionDetectionService and calls analyze_record()
    to detect contradictions and novelty. Does NOT affect IngestionRecord
    state on failure.

    Args:
        self: Celery task instance (bound for retry support).
        record_id: IngestionRecord ID to analyze.
        company_id: Tenant scope.

    Returns:
        Dict with analysis results (contradiction_count, novelty_flagged, etc).

    Raises:
        self.retry(): On unhandled exceptions when retries remain.
    """
    logger.info(
        "execute_cross_reference: record_id=%d, company_id=%d, attempt=%d/%d",
        record_id,
        company_id,
        self.request.retries + 1,
        self.max_retries + 1,
    )

    try:
        cds = _get_contradiction_detection_service()
        result = asyncio.run(
            cds.analyze_record(
                record_id=record_id,
                company_id=company_id,
            )
        )
        logger.info(
            "execute_cross_reference completed: record_id=%d, "
            "contradictions=%d, novelty=%s, alerts=%d, duration_ms=%d",
            record_id,
            result.get("contradiction_count", 0),
            result.get("novelty_flagged", False),
            result.get("alerts_created", 0),
            result.get("analysis_duration_ms", 0),
        )
        return result

    except Exception as exc:
        from celery.exceptions import Retry

        if isinstance(exc, Retry):
            raise

        logger.error(
            "execute_cross_reference failed: record_id=%d, error=%s: %s",
            record_id,
            type(exc).__name__,
            str(exc)[:500],
        )

        # NOTE: Does NOT affect IngestionRecord state on failure (per requirements)
        # Exponential backoff retry
        backoff = _CROSS_REFERENCE_RETRY_BACKOFF
        countdown = backoff[min(self.request.retries, len(backoff) - 1)]
        raise self.retry(exc=exc, countdown=countdown)


# ---------------------------------------------------------------------------
# Task 3: auto_screen_on_index
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="literature.auto_screen_on_index",
    queue="ai_operations",
    priority=6,
    max_retries=1,
    acks_late=True,
)
def auto_screen_on_index(
    self,
    *,
    record_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Auto-screen a newly indexed record if company config enables it.

    Checks the company's ScreeningConfiguration for auto_screen_on_index=True.
    If enabled, creates a ScreeningRun for each active ScreeningProtocol and
    dispatches execute_screening_batch tasks.

    Args:
        self: Celery task instance (bound for retry support).
        record_id: The newly indexed IngestionRecord ID.
        company_id: Tenant scope.

    Returns:
        Dict with status and number of screening tasks dispatched.

    Raises:
        self.retry(): On unhandled exceptions when retries remain.
    """
    logger.info(
        "auto_screen_on_index: record_id=%d, company_id=%d, attempt=%d/%d",
        record_id,
        company_id,
        self.request.retries + 1,
        self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            _process_auto_screen_on_index(
                record_id=record_id,
                company_id=company_id,
            )
        )
        logger.info(
            "auto_screen_on_index completed: record_id=%d, dispatched=%d",
            record_id,
            result.get("tasks_dispatched", 0),
        )
        return result

    except Exception as exc:
        from celery.exceptions import Retry

        if isinstance(exc, Retry):
            raise

        logger.error(
            "auto_screen_on_index failed: record_id=%d, error=%s: %s",
            record_id,
            type(exc).__name__,
            str(exc)[:500],
        )
        raise self.retry(exc=exc, countdown=30)


async def _process_auto_screen_on_index(
    *,
    record_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Async implementation of auto-screen-on-index.

    Steps:
    1. Check company ScreeningConfiguration.auto_screen_on_index
    2. If disabled, return early
    3. Find all active ScreeningProtocols for the company
    4. For each active protocol, find or create an SLR Review
    5. Create a ScreeningRun and dispatch execute_screening_batch

    Args:
        record_id: Newly indexed IngestionRecord ID.
        company_id: Tenant scope.

    Returns:
        Dict with status and tasks_dispatched count.
    """
    import uuid

    from sqlalchemy import and_, select

    from alcoabase.literature.review.models.screening_config import (
        ScreeningConfiguration,
    )
    from alcoabase.literature.review.models.screening_protocol import (
        ScreeningProtocol,
    )
    from alcoabase.literature.review.models.screening_run import ScreeningRun
    from alcoabase.literature.review.models.slr_review import SLRReview

    session_factory = _get_session_factory()

    async with session_factory() as session:
        # Step 1: Check company config
        config_stmt = select(ScreeningConfiguration).where(
            ScreeningConfiguration.company_id == company_id
        )
        config_result = await session.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if config is None or not config.auto_screen_on_index:
            logger.info(
                "auto_screen_on_index disabled for company %d. Skipping.",
                company_id,
            )
            return {"status": "skipped", "reason": "auto_screen_disabled", "tasks_dispatched": 0}

        batch_size = config.default_batch_size

        # Step 2: Find all active protocols for this company
        protocols_stmt = select(ScreeningProtocol).where(
            and_(
                ScreeningProtocol.company_id == company_id,
                ScreeningProtocol.status == "active",
            )
        )
        protocols_result = await session.execute(protocols_stmt)
        active_protocols = list(protocols_result.scalars().all())

        if not active_protocols:
            logger.info(
                "No active protocols for company %d. Skipping auto-screen.",
                company_id,
            )
            return {"status": "skipped", "reason": "no_active_protocols", "tasks_dispatched": 0}

        # Step 3: For each active protocol, create a ScreeningRun and dispatch
        tasks_dispatched = 0

        for protocol in active_protocols:
            # Find an existing in-progress review for this protocol, or create one
            review_stmt = select(SLRReview).where(
                and_(
                    SLRReview.company_id == company_id,
                    SLRReview.protocol_id == protocol.id,
                    SLRReview.status.in_(["protocol_defined", "screening_in_progress"]),
                )
            ).limit(1)
            review_result = await session.execute(review_stmt)
            review = review_result.scalar_one_or_none()

            if review is None:
                # Create a new auto-generated review
                review = SLRReview(
                    company_id=company_id,
                    protocol_id=protocol.id,
                    name=f"Auto-screen: {protocol.name}",
                    description="Automatically created for auto-screen-on-index.",
                    status="screening_in_progress",
                    record_filter={"ingestion_record_ids": [record_id]},
                    created_by=0,  # System-generated
                    records_identified=1,
                )
                session.add(review)
                await session.flush()
            else:
                # Append record_id to existing review's record_filter
                current_filter = review.record_filter or {}
                current_ids = current_filter.get("ingestion_record_ids", [])
                if record_id not in current_ids:
                    current_ids.append(record_id)
                    review.record_filter = {
                        **current_filter,
                        "ingestion_record_ids": current_ids,
                    }
                    review.records_identified = len(current_ids)

                # Ensure review is in screening_in_progress
                if review.status == "protocol_defined":
                    review.status = "screening_in_progress"

            # Create a ScreeningRun
            celery_task_id = str(uuid.uuid4())
            screening_run = ScreeningRun(
                review_id=review.id,
                protocol_id=protocol.id,
                company_id=company_id,
                status="queued",
                total_records=1,
                batch_size=batch_size,
                total_batches=1,
                celery_task_id=celery_task_id,
            )
            session.add(screening_run)
            await session.flush()

            # Dispatch the screening batch task
            execute_screening_batch.apply_async(
                kwargs={
                    "screening_run_id": screening_run.id,
                    "review_id": review.id,
                    "protocol_id": protocol.id,
                    "company_id": company_id,
                    "batch_size": batch_size,
                    "re_screen_uncertain": False,
                },
                queue="ai_operations",
                priority=5,
                task_id=celery_task_id,
            )

            tasks_dispatched += 1
            logger.info(
                "Dispatched screening batch for protocol %d (review %d, run %d)",
                protocol.id,
                review.id,
                screening_run.id,
            )

        await session.commit()

    return {
        "status": "completed",
        "record_id": record_id,
        "company_id": company_id,
        "tasks_dispatched": tasks_dispatched,
        "protocols_processed": len(active_protocols),
    }
