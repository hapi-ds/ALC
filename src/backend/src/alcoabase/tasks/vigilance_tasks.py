"""Celery tasks for Medical Device Vigilance & Post-Market Surveillance (Phase 9.5).

Implements the asynchronous task layer for:
- execute_vigilance_search: Scheduled/manual vigilance literature searches
- execute_signal_detection: AI-driven signal analysis of ingested records
- escalate_critical_signal: Critical signal escalation (impact analysis, notifications)
- generate_periodic_report: Periodic safety report generation
- register_vigilance_schedules: Dynamic Celery beat registration on startup/restart

All tasks use asyncio.run() for async service operations from synchronous
Celery workers (consistent with literature_ingestion_tasks.py pattern).

References:
    - Requirements 4.1, 4.6, 4.8, 5.1, 5.7, 7.1, 8.1, 13.1, 13.2, 13.3, 13.4, 13.5, 13.7
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
    - Task 10.1: Implement vigilance_tasks.py
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.literature.vigilance.audit import log_retry_attempt
from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Retry backoff schedules (seconds)
# ---------------------------------------------------------------------------

_SEARCH_RETRY_BACKOFF: list[int] = [300, 900, 3600]  # 5min, 15min, 60min
_SIGNAL_RETRY_BACKOFF: list[int] = [30, 120, 600]  # 30s, 2min, 10min
_ESCALATION_RETRY_BACKOFF: list[int] = [60, 300, 900]  # 1min, 5min, 15min


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


def _get_vigilance_monitor_service():
    """Instantiate VigilanceMonitorService with all dependencies.

    Returns:
        Configured VigilanceMonitorService.
    """
    from alcoabase.config import get_settings
    from alcoabase.literature.ingestion.services.ingestion_pipeline_service import (
        IngestionPipelineService,
    )
    from alcoabase.literature.services.literature_gateway_service import (
        LiteratureGatewayService,
    )
    from alcoabase.literature.vigilance.services.vigilance_monitor_service import (
        VigilanceMonitorService,
    )

    settings = get_settings()
    session_factory = _get_session_factory()

    literature_gateway = LiteratureGatewayService(
        session_factory=session_factory,
    )
    ingestion_pipeline = IngestionPipelineService(
        session_factory=session_factory,
    )

    return VigilanceMonitorService(
        session_factory=session_factory,
        literature_gateway=literature_gateway,
        ingestion_pipeline=ingestion_pipeline,
        search_queue=settings.vigilance_search_queue,
        execution_timeout=settings.vigilance_search_timeout,
    )


def _get_signal_analyzer():
    """Instantiate VigilanceSignalAnalyzer with all dependencies.

    Returns:
        Configured VigilanceSignalAnalyzer.
    """
    from alcoabase.config import get_settings
    from alcoabase.literature.vigilance.services.vigilance_signal_analyzer import (
        VigilanceSignalAnalyzer,
    )

    settings = get_settings()
    session_factory = _get_session_factory()
    inference_client = _get_inference_client()
    agent_registry = _get_agent_registry()

    return VigilanceSignalAnalyzer(
        session_factory=session_factory,
        inference_client=inference_client,
        agent_registry=agent_registry,
        model_name=settings.model_chat_name,
        confidence_threshold=settings.vigilance_signal_confidence_threshold,
        batch_size=settings.vigilance_signal_batch_size,
    )


def _get_escalation_service():
    """Instantiate VigilanceEscalationService with all dependencies.

    Returns:
        Configured VigilanceEscalationService.
    """
    from alcoabase.config import get_settings
    from alcoabase.literature.review.services.contradiction_detection_service import (
        ContradictionDetectionService,
    )
    from alcoabase.literature.vigilance.services.vigilance_escalation_service import (
        VigilanceEscalationService,
    )
    from alcoabase.services.impact_analysis import ImpactAnalysisService
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.knowledge_service import KnowledgeService

    settings = get_settings()
    session_factory = _get_session_factory()

    # Impact Analysis Service
    chat_client = InferenceClient(
        base_url=settings.vllm_base_url,
        embedding_base_url=settings.vllm_embedding_url,
    )
    knowledge_service = KnowledgeService()
    impact_service = ImpactAnalysisService(
        knowledge_service=knowledge_service,
        inference_client=chat_client,
        agent_registry=None,
        session_factory=session_factory,
        job_tracker=None,
    )

    # Contradiction Detection Service (minimal construction for escalation)
    contradiction_service = ContradictionDetectionService(
        session_factory=session_factory,
        hybrid_query_engine=None,
        inference_client=chat_client,
        impact_analysis_service=impact_service,
        model_name=settings.model_chat_name,
    )

    # SLR Review Service placeholder (imported at runtime if available)
    slr_review_service = None
    try:
        from alcoabase.literature.review.services.slr_review_service import (
            SLRReviewService,
        )

        slr_review_service = SLRReviewService(
            session_factory=session_factory,
        )
    except (ImportError, Exception):
        logger.debug("SLRReviewService not available; SLR inclusion disabled.")

    return VigilanceEscalationService(
        session_factory=session_factory,
        impact_analysis_service=impact_service,
        contradiction_detection_service=contradiction_service,
        slr_review_service=slr_review_service,
        escalation_retries=settings.vigilance_escalation_retries,
    )


def _get_periodic_report_service():
    """Instantiate PeriodicReportService.

    Returns:
        Configured PeriodicReportService.
    """
    from alcoabase.literature.vigilance.services.periodic_report_service import (
        PeriodicReportService,
    )

    return PeriodicReportService()


def _get_profile_service():
    """Instantiate VigilanceSearchProfileService.

    Returns:
        Configured VigilanceSearchProfileService.
    """
    from alcoabase.literature.vigilance.services.vigilance_search_profile_service import (
        VigilanceSearchProfileService,
    )

    session_factory = _get_session_factory()
    return VigilanceSearchProfileService(session_factory=session_factory)


# ---------------------------------------------------------------------------
# Task 1: execute_vigilance_search
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.vigilance_tasks.execute_vigilance_search",
    queue="literature_ingestion",
    priority=5,
    max_retries=3,
    soft_time_limit=3600,
    acks_late=True,
)
def execute_vigilance_search(
    self,
    *,
    profile_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Execute a vigilance search for a given profile.

    Loads the VigilanceSearchProfile, instantiates VigilanceMonitorService,
    executes the search (with idempotency check), and on completion dispatches
    signal detection tasks for ingested records in configurable batches.

    Retry policy: exponential backoff at 5min, 15min, 60min.

    Args:
        self: Celery task instance (bound for retry support).
        profile_id: VigilanceSearchProfile ID to execute.
        company_id: Tenant scope (company isolation).

    Returns:
        Dict with execution result: status, counts, dispatched batches.

    References:
        - Requirements 4.1, 4.6, 4.8, 13.1, 13.2, 13.4, 13.5
    """
    attempt = self.request.retries + 1
    logger.info(
        "execute_vigilance_search: profile_id=%d, company_id=%d, attempt=%d/%d",
        profile_id,
        company_id,
        attempt,
        self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            _run_vigilance_search(
                profile_id=profile_id,
                company_id=company_id,
            )
        )

        logger.info(
            "execute_vigilance_search completed: profile_id=%d, "
            "status=%s, ingested=%d, batches_dispatched=%d",
            profile_id,
            result.get("status", "unknown"),
            result.get("results_ingested", 0),
            result.get("batches_dispatched", 0),
        )
        return result

    except Exception as exc:
        from alcoabase.literature.vigilance.exceptions import (
            DuplicateExecutionError,
        )

        # Idempotency: skip if already running (do NOT retry)
        if isinstance(exc, DuplicateExecutionError):
            logger.warning(
                "execute_vigilance_search skipped: profile_id=%d already running "
                "(existing_execution_id=%d)",
                profile_id,
                exc.existing_execution_id,
            )
            return {
                "status": "skipped",
                "reason": "duplicate_execution",
                "profile_id": profile_id,
                "existing_execution_id": exc.existing_execution_id,
            }

        # Determine backoff for retry
        retry_delay = (
            _SEARCH_RETRY_BACKOFF[self.request.retries]
            if self.request.retries < len(_SEARCH_RETRY_BACKOFF)
            else _SEARCH_RETRY_BACKOFF[-1]
        )

        # Structured audit log for retry attempt (Requirement 13.7)
        log_retry_attempt(
            task_type="search_execution",
            attempt_number=attempt,
            error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            backoff_duration_s=retry_delay,
            entity_ids={"profile_id": profile_id, "company_id": company_id},
        )

        logger.error(
            "execute_vigilance_search failed: profile_id=%d, attempt=%d, "
            "error=%s: %s. Retrying in %ds.",
            profile_id,
            attempt,
            type(exc).__name__,
            str(exc)[:500],
            retry_delay,
        )

        raise self.retry(exc=exc, countdown=retry_delay)


async def _run_vigilance_search(
    *,
    profile_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Async implementation of the vigilance search execution.

    Executes the search via VigilanceMonitorService, then dispatches
    signal detection for ingested records in batches.

    Args:
        profile_id: VigilanceSearchProfile to execute.
        company_id: Tenant scope.

    Returns:
        Dict with execution results and batch dispatch info.
    """
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.literature.vigilance.models.vigilance_search_profile import (
        VigilanceSearchProfile,
    )

    settings = get_settings()
    monitor_service = _get_vigilance_monitor_service()

    # Execute the search
    execution_result = await monitor_service.execute_search(
        profile_id=profile_id,
        company_id=company_id,
    )

    # Dispatch signal detection for ingested records in batches
    batches_dispatched = 0
    if execution_result.results_ingested > 0:
        session_factory = _get_session_factory()
        batch_size = settings.vigilance_signal_batch_size

        async with session_factory() as session:
            # Load profile to get product_id
            profile = await session.get(VigilanceSearchProfile, profile_id)
            product_id = profile.product_id if profile else 0

            # Get ingested record IDs from this execution
            # Records linked to this execution that were successfully ingested
            from alcoabase.literature.ingestion.models.ingestion import (
                IngestionRecord,
            )

            stmt = select(IngestionRecord.id).where(
                IngestionRecord.company_id == company_id,
                IngestionRecord.vigilance_execution_id
                == execution_result.execution_id,
            )
            result = await session.execute(stmt)
            ingested_record_ids = [row[0] for row in result.fetchall()]

        # Dispatch in batches
        for i in range(0, len(ingested_record_ids), batch_size):
            batch = ingested_record_ids[i : i + batch_size]
            execute_signal_detection.apply_async(
                kwargs={
                    "record_ids": batch,
                    "product_id": product_id,
                    "profile_id": profile_id,
                    "execution_id": execution_result.execution_id,
                    "company_id": company_id,
                },
                queue=settings.vigilance_signal_queue,
            )
            batches_dispatched += 1

        logger.info(
            "Dispatched %d signal detection batches for execution_id=%d "
            "(%d records total)",
            batches_dispatched,
            execution_result.execution_id,
            len(ingested_record_ids),
        )

    return {
        "status": execution_result.status,
        "execution_id": execution_result.execution_id,
        "total_results_found": execution_result.total_results_found,
        "results_after_exclusion": execution_result.results_after_exclusion,
        "results_ingested": execution_result.results_ingested,
        "results_duplicate": execution_result.results_duplicate,
        "execution_duration_ms": execution_result.execution_duration_ms,
        "batches_dispatched": batches_dispatched,
    }


# ---------------------------------------------------------------------------
# Task 2: execute_signal_detection
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.vigilance_tasks.execute_signal_detection",
    queue="ai_operations",
    priority=4,
    max_retries=3,
    soft_time_limit=1800,
    acks_late=True,
)
def execute_signal_detection(
    self,
    *,
    record_ids: list[int],
    product_id: int,
    profile_id: int,
    execution_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Execute signal detection analysis on a batch of ingestion records.

    Instantiates VigilanceSignalAnalyzer, calls analyze_batch(), and for
    any critical signals dispatches escalate_critical_signal. Idempotent:
    skips records already analyzed for this execution.

    Retry policy: exponential backoff at 30s, 2min, 10min.

    Args:
        self: Celery task instance (bound for retry support).
        record_ids: List of IngestionRecord IDs to analyze.
        product_id: Associated MedicalProduct ID.
        profile_id: Originating VigilanceSearchProfile ID.
        execution_id: VigilanceSearchExecution ID for idempotency tracking.
        company_id: Tenant scope.

    Returns:
        Dict with analysis summary: total analyzed, signals created, critical count.

    References:
        - Requirements 5.1, 5.7, 7.1, 13.3, 13.7
    """
    attempt = self.request.retries + 1
    logger.info(
        "execute_signal_detection: %d records, product_id=%d, "
        "profile_id=%d, execution_id=%d, company_id=%d, attempt=%d/%d",
        len(record_ids),
        product_id,
        profile_id,
        execution_id,
        company_id,
        attempt,
        self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            _run_signal_detection(
                record_ids=record_ids,
                product_id=product_id,
                profile_id=profile_id,
                execution_id=execution_id,
                company_id=company_id,
            )
        )

        logger.info(
            "execute_signal_detection completed: execution_id=%d, "
            "analyzed=%d, signals_created=%d, critical=%d",
            execution_id,
            result.get("records_analyzed", 0),
            result.get("signals_created", 0),
            result.get("critical_signals", 0),
        )
        return result

    except Exception as exc:
        retry_delay = (
            _SIGNAL_RETRY_BACKOFF[self.request.retries]
            if self.request.retries < len(_SIGNAL_RETRY_BACKOFF)
            else _SIGNAL_RETRY_BACKOFF[-1]
        )

        # Structured audit log for retry attempt (Requirement 13.7)
        log_retry_attempt(
            task_type="signal_detection",
            attempt_number=attempt,
            error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            backoff_duration_s=retry_delay,
            entity_ids={
                "execution_id": execution_id,
                "record_ids": record_ids[:10],  # Limit to avoid large payloads
                "product_id": product_id,
                "company_id": company_id,
            },
        )

        logger.error(
            "execute_signal_detection failed: execution_id=%d, attempt=%d, "
            "error=%s: %s. Retrying in %ds.",
            execution_id,
            attempt,
            type(exc).__name__,
            str(exc)[:500],
            retry_delay,
        )

        raise self.retry(exc=exc, countdown=retry_delay)


async def _run_signal_detection(
    *,
    record_ids: list[int],
    product_id: int,
    profile_id: int,
    execution_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Async implementation of signal detection batch processing.

    Filters out records already analyzed for this execution (idempotency),
    then runs analyze_batch. For critical signals, dispatches escalation tasks.

    Args:
        record_ids: IngestionRecord IDs to analyze.
        product_id: Associated product.
        profile_id: Originating profile.
        execution_id: Execution ID for idempotency.
        company_id: Tenant scope.

    Returns:
        Dict with analysis results.
    """
    from sqlalchemy import select

    from alcoabase.literature.vigilance.models.vigilance_signal import (
        VigilanceSignal,
    )

    session_factory = _get_session_factory()
    analyzer = _get_signal_analyzer()

    # Idempotency: filter out records already analyzed for this execution
    records_to_analyze = record_ids
    async with session_factory() as session:
        stmt = select(VigilanceSignal.ingestion_record_id).where(
            VigilanceSignal.profile_id == profile_id,
            VigilanceSignal.company_id == company_id,
            VigilanceSignal.ingestion_record_id.in_(record_ids),
        )
        result = await session.execute(stmt)
        already_analyzed = {row[0] for row in result.fetchall()}

    if already_analyzed:
        records_to_analyze = [
            rid for rid in record_ids if rid not in already_analyzed
        ]
        logger.info(
            "Idempotency filter: skipping %d already-analyzed records "
            "(execution_id=%d)",
            len(already_analyzed),
            execution_id,
        )

    if not records_to_analyze:
        return {
            "status": "completed",
            "records_analyzed": 0,
            "records_skipped": len(record_ids),
            "signals_created": 0,
            "critical_signals": 0,
        }

    # Run batch analysis
    batch_results = await analyzer.analyze_batch(
        record_ids=records_to_analyze,
        product_id=product_id,
        profile_id=profile_id,
        company_id=company_id,
    )

    # Count signals and dispatch escalation for critical ones
    signals_created = 0
    critical_signals = 0

    for record_id, analysis_result in batch_results:
        if analysis_result.signal_detected and analysis_result.confidence >= 0.7:
            signals_created += 1

            if analysis_result.severity == "critical":
                critical_signals += 1
                # Dispatch escalation task for critical signals
                # Find the signal_id that was just created
                async with session_factory() as session:
                    stmt = select(VigilanceSignal.id).where(
                        VigilanceSignal.ingestion_record_id == record_id,
                        VigilanceSignal.profile_id == profile_id,
                        VigilanceSignal.company_id == company_id,
                        VigilanceSignal.severity == "critical",
                    ).order_by(VigilanceSignal.id.desc()).limit(1)
                    result = await session.execute(stmt)
                    signal_row = result.scalar_one_or_none()

                if signal_row:
                    escalate_critical_signal.apply_async(
                        kwargs={
                            "signal_id": signal_row,
                            "company_id": company_id,
                        },
                        queue="ai_operations",
                        priority=9,
                    )
                    logger.info(
                        "Dispatched escalation for critical signal_id=%d "
                        "(record_id=%d)",
                        signal_row,
                        record_id,
                    )

    return {
        "status": "completed",
        "records_analyzed": len(records_to_analyze),
        "records_skipped": len(already_analyzed) if already_analyzed else 0,
        "signals_created": signals_created,
        "critical_signals": critical_signals,
    }


# ---------------------------------------------------------------------------
# Task 3: escalate_critical_signal
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.vigilance_tasks.escalate_critical_signal",
    queue="ai_operations",
    priority=9,
    max_retries=3,
    soft_time_limit=600,
    acks_late=True,
)
def escalate_critical_signal(
    self,
    *,
    signal_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Escalate a critical vigilance signal through all escalation pathways.

    Instantiates VigilanceEscalationService and calls escalate_signal().
    Each sub-task (impact analysis, contradiction detection, notification,
    SLR inclusion) is independent — failure in one does not block others.

    Priority 9 (highest) for patient safety.

    Args:
        self: Celery task instance (bound for retry support).
        signal_id: VigilanceSignal ID to escalate.
        company_id: Tenant scope.

    Returns:
        Dict with escalation results per sub-task.

    References:
        - Requirements 7.1, 13.8
    """
    attempt = self.request.retries + 1
    logger.info(
        "escalate_critical_signal: signal_id=%d, company_id=%d, attempt=%d/%d",
        signal_id,
        company_id,
        attempt,
        self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            _run_escalation(
                signal_id=signal_id,
                company_id=company_id,
            )
        )

        logger.info(
            "escalate_critical_signal completed: signal_id=%d, "
            "failed_subtasks=%s",
            signal_id,
            result.get("failed_subtasks", []),
        )
        return result

    except Exception as exc:
        retry_delay = (
            _ESCALATION_RETRY_BACKOFF[self.request.retries]
            if self.request.retries < len(_ESCALATION_RETRY_BACKOFF)
            else _ESCALATION_RETRY_BACKOFF[-1]
        )

        # Structured audit log for retry attempt (Requirement 13.7)
        log_retry_attempt(
            task_type="escalation",
            attempt_number=attempt,
            error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            backoff_duration_s=retry_delay,
            entity_ids={"signal_id": signal_id, "company_id": company_id},
        )

        logger.error(
            "escalate_critical_signal failed: signal_id=%d, attempt=%d, "
            "error=%s: %s. Retrying in %ds.",
            signal_id,
            attempt,
            type(exc).__name__,
            str(exc)[:500],
            retry_delay,
        )

        raise self.retry(exc=exc, countdown=retry_delay)


async def _run_escalation(
    *,
    signal_id: int,
    company_id: int,
) -> dict[str, Any]:
    """Async implementation of critical signal escalation.

    Args:
        signal_id: VigilanceSignal to escalate.
        company_id: Tenant scope.

    Returns:
        Escalation result dict from VigilanceEscalationService.
    """
    escalation_service = _get_escalation_service()

    result = await escalation_service.escalate_signal(
        signal_id=signal_id,
        company_id=company_id,
    )

    return result


# ---------------------------------------------------------------------------
# Task 4: generate_periodic_report
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.vigilance_tasks.generate_periodic_report",
    queue="literature_ingestion",
    priority=3,
    max_retries=2,
    soft_time_limit=1800,
    acks_late=True,
)
def generate_periodic_report(
    self,
    *,
    product_id: int,
    company_id: int,
    period_start: str,
    period_end: str,
    user_id: int,
) -> dict[str, Any]:
    """Generate a Periodic Safety Report for a product within a date range.

    Instantiates PeriodicReportService and calls generate_report() with
    the specified product and period boundaries.

    Args:
        self: Celery task instance (bound for retry support).
        product_id: MedicalProduct ID.
        company_id: Tenant scope.
        period_start: ISO-8601 date string (YYYY-MM-DD).
        period_end: ISO-8601 date string (YYYY-MM-DD).
        user_id: User who triggered the generation.

    Returns:
        Dict with report_id, status, and period info.

    References:
        - Requirements 8.1, 13.5
    """
    attempt = self.request.retries + 1
    logger.info(
        "generate_periodic_report: product_id=%d, company_id=%d, "
        "period=%s to %s, user_id=%d, attempt=%d/%d",
        product_id,
        company_id,
        period_start,
        period_end,
        user_id,
        attempt,
        self.max_retries + 1,
    )

    try:
        result = asyncio.run(
            _run_report_generation(
                product_id=product_id,
                company_id=company_id,
                period_start=period_start,
                period_end=period_end,
                user_id=user_id,
            )
        )

        logger.info(
            "generate_periodic_report completed: product_id=%d, "
            "report_id=%s, status=%s",
            product_id,
            result.get("report_id", "unknown"),
            result.get("status", "unknown"),
        )
        return result

    except Exception as exc:
        retry_delay = 300  # 5 minutes between retries for report generation

        # Structured audit log for retry attempt (Requirement 13.7)
        log_retry_attempt(
            task_type="report_generation",
            attempt_number=attempt,
            error_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            backoff_duration_s=retry_delay,
            entity_ids={
                "product_id": product_id,
                "company_id": company_id,
            },
        )

        logger.error(
            "generate_periodic_report failed: product_id=%d, attempt=%d, "
            "error=%s: %s. Retrying in %ds.",
            product_id,
            attempt,
            type(exc).__name__,
            str(exc)[:500],
            retry_delay,
        )

        raise self.retry(exc=exc, countdown=retry_delay)


async def _run_report_generation(
    *,
    product_id: int,
    company_id: int,
    period_start: str,
    period_end: str,
    user_id: int,
) -> dict[str, Any]:
    """Async implementation of periodic report generation.

    Args:
        product_id: Target MedicalProduct.
        company_id: Tenant scope.
        period_start: ISO-8601 date string.
        period_end: ISO-8601 date string.
        user_id: Acting user.

    Returns:
        Dict with report details.
    """
    report_service = _get_periodic_report_service()
    session_factory = _get_session_factory()

    # Parse date strings
    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)

    async with session_factory() as session:
        result = await report_service.generate_report(
            session,
            product_id=product_id,
            company_id=company_id,
            period_start=start_date,
            period_end=end_date,
            user_id=user_id,
        )

    return result


# ---------------------------------------------------------------------------
# Task 5: register_vigilance_schedules
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.vigilance_tasks.register_vigilance_schedules",
    queue="literature_ingestion",
    acks_late=True,
)
def register_vigilance_schedules(self) -> dict[str, Any]:
    """Load all active vigilance profiles and register with Celery beat.

    Called on worker startup or scheduler restart to ensure all active
    profiles have their cron schedules registered dynamically. Also
    detects in-progress executions and re-queues them.

    Args:
        self: Celery task instance (bound).

    Returns:
        Dict with schedules_registered count and re-queued execution count.

    References:
        - Requirements 4.8, 13.7
    """
    logger.info("register_vigilance_schedules: starting dynamic schedule registration")

    try:
        result = asyncio.run(_run_register_schedules())

        logger.info(
            "register_vigilance_schedules completed: registered=%d, "
            "re_queued=%d",
            result.get("schedules_registered", 0),
            result.get("executions_requeued", 0),
        )
        return result

    except Exception as exc:
        logger.error(
            "register_vigilance_schedules failed: %s: %s",
            type(exc).__name__,
            str(exc)[:500],
        )
        # Do not retry indefinitely — log and return error status
        return {
            "status": "failed",
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


async def _run_register_schedules() -> dict[str, Any]:
    """Async implementation of schedule registration and recovery.

    Steps:
        1. Load all active profiles and register with Celery beat
        2. Detect in-progress (status='running') executions
        3. Re-queue stale executions by dispatching new search tasks

    Returns:
        Dict with registration and recovery counts.
    """
    from sqlalchemy import select

    from alcoabase.literature.vigilance.models.vigilance_search_execution import (
        VigilanceSearchExecution,
    )

    profile_service = _get_profile_service()
    session_factory = _get_session_factory()

    # Step 1: Register all active schedules
    schedules_registered = await profile_service.register_all_active_schedules()

    # Step 2: Detect in-progress executions and re-queue them
    executions_requeued = 0
    async with session_factory() as session:
        stmt = select(VigilanceSearchExecution).where(
            VigilanceSearchExecution.status == "running",
        )
        result = await session.execute(stmt)
        stale_executions = result.scalars().all()

        for execution in stale_executions:
            # Mark the stale execution as failed (it was interrupted)
            execution.status = "failed"
            await session.commit()

            # Re-dispatch the search task
            execute_vigilance_search.apply_async(
                kwargs={
                    "profile_id": execution.profile_id,
                    "company_id": execution.company_id,
                },
                queue="literature_ingestion",
            )
            executions_requeued += 1
            logger.info(
                "Re-queued stale execution: execution_id=%d, "
                "profile_id=%d, company_id=%d",
                execution.id,
                execution.profile_id,
                execution.company_id,
            )

    return {
        "status": "completed",
        "schedules_registered": schedules_registered,
        "executions_requeued": executions_requeued,
    }
