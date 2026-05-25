"""Celery tasks for template-based AI document generation.

Implements async tasks for:
- analyze_template_task: Template structure extraction and analysis
- generate_document_task: Full document generation pipeline execution

Both tasks run on the ai_operations queue with appropriate timeouts
and retry strategies for transient vs. permanent failures.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 1.2, 1.8, 1.12, 2.2, 2.9, 7.1, 7.2, 7.5, 7.7
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Retryable exception tuple for exponential backoff
# ---------------------------------------------------------------------------

# Imported lazily inside tasks to avoid circular imports at module level.
# These are transient errors that may resolve on retry:
#   - ConnectionError: network issues
#   - OSError: filesystem/IO issues
#   - InferenceTimeoutError: vLLM timeout
#   - InferenceConnectionError: vLLM unreachable


def _get_retryable_exceptions() -> tuple[type[Exception], ...]:
    """Get the tuple of retryable exception types.

    Returns:
        Tuple of exception classes that warrant a Celery-level retry.
    """
    from alcoabase.services.inference_client import (
        InferenceConnectionError,
        InferenceTimeoutError,
    )

    return (ConnectionError, OSError, InferenceTimeoutError, InferenceConnectionError)


# ---------------------------------------------------------------------------
# Helper: Async session factory for Celery workers
# ---------------------------------------------------------------------------


def _get_async_session_factory():
    """Get the async session factory for DB access in Celery tasks.

    Creates a standalone async engine and session factory since Celery
    workers don't share the FastAPI application's DB lifecycle.

    Returns:
        async_sessionmaker bound to a fresh async engine.
    """
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
    )
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _get_storage_service():
    """Get a StorageService instance for Celery workers.

    Returns:
        StorageService instance.
    """
    from alcoabase.services.storage_service import StorageService

    return StorageService()


def _get_job_tracker():
    """Get a JobTracker instance for Celery workers.

    Returns:
        JobTracker instance.
    """
    from alcoabase.services.job_tracker import JobTracker

    return JobTracker()


# ---------------------------------------------------------------------------
# Task: analyze_template_task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    soft_time_limit=120,
    max_retries=2,
    default_retry_delay=10,
    queue="ai_operations",
    name="alcoabase.tasks.document_generation_tasks.analyze_template_task",
)
def analyze_template_task(
    self: Task,
    document_id: int,
    document_version_id: int,
    template_name: str,
    document_type_target: str,
    registered_by: int,
    company_id: int,
    job_id: str,
) -> dict[str, Any]:
    """Analyze a .docx template structure.

    Pipeline:
    1. Download .docx from MinIO via StorageService
    2. Validate file is .docx format
    3. Extract structural layout via python-docx
    4. Detect placeholder markers
    5. Persist Template_Analysis JSON to DocumentTemplate record
    6. Complete job via JobTracker

    Args:
        self: Celery task instance (bound).
        document_id: Source document ID.
        document_version_id: Specific version to analyze.
        template_name: Human-readable name for the template.
        document_type_target: Target document type (e.g., "URS", "MVP").
        registered_by: User ID who registered the template.
        company_id: Company scope for tenant isolation.
        job_id: Job ID for tracking via JobTracker.

    Returns:
        Dict with analysis results (template_id, total_sections, status).

    Raises:
        Retry: On retryable transient errors (ConnectionError, OSError,
            InferenceTimeoutError, InferenceConnectionError).
    """
    try:
        result = asyncio.run(
            _analyze_template_async(
                document_id=document_id,
                document_version_id=document_version_id,
                template_name=template_name,
                document_type_target=document_type_target,
                registered_by=registered_by,
                company_id=company_id,
                job_id=job_id,
            )
        )
        return result

    except SoftTimeLimitExceeded:
        # Non-retryable: mark job as failed with timeout reason
        logger.error(
            "analyze_template_task timed out for document_version_id=%d, job_id=%s",
            document_version_id,
            job_id,
        )
        asyncio.run(
            _fail_analysis_job(
                job_id=job_id,
                document_version_id=document_version_id,
                company_id=company_id,
                error_message="Template analysis timed out (exceeded 120s limit)",
            )
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "error": "Template analysis timed out (exceeded 120s limit)",
        }

    except ValueError as exc:
        # Non-retryable: validation or parsing error
        logger.error(
            "analyze_template_task failed with ValueError for "
            "document_version_id=%d, job_id=%s: %s",
            document_version_id,
            job_id,
            exc,
        )
        asyncio.run(
            _fail_analysis_job(
                job_id=job_id,
                document_version_id=document_version_id,
                company_id=company_id,
                error_message=str(exc)[:500],
            )
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(exc)[:500],
        }

    except Exception as exc:
        # Check if retryable
        if _is_retryable(exc):
            logger.warning(
                "analyze_template_task retrying for document_version_id=%d, "
                "job_id=%s (attempt %d): %s",
                document_version_id,
                job_id,
                self.request.retries + 1,
                exc,
            )
            raise self.retry(
                exc=exc,
                countdown=10 * (2**self.request.retries),
            )

        # Non-retryable unexpected error: mark as failed
        logger.exception(
            "analyze_template_task unexpected error for "
            "document_version_id=%d, job_id=%s",
            document_version_id,
            job_id,
        )
        asyncio.run(
            _fail_analysis_job(
                job_id=job_id,
                document_version_id=document_version_id,
                company_id=company_id,
                error_message=f"Unexpected error: {str(exc)[:400]}",
            )
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "error": f"Unexpected error: {str(exc)[:400]}",
        }


async def _analyze_template_async(
    document_id: int,
    document_version_id: int,
    template_name: str,
    document_type_target: str,
    registered_by: int,
    company_id: int,
    job_id: str,
) -> dict[str, Any]:
    """Async implementation of the template analysis pipeline.

    Args:
        document_id: Source document ID.
        document_version_id: Specific version to analyze.
        template_name: Human-readable name for the template.
        document_type_target: Target document type.
        registered_by: User ID who registered the template.
        company_id: Company scope for tenant isolation.
        job_id: Job ID for tracking.

    Returns:
        Dict with analysis results.
    """
    from dataclasses import asdict as _asdict

    from sqlalchemy import select

    from alcoabase.models.document import DocumentVersion
    from alcoabase.models.document_generation import DocumentTemplate
    from alcoabase.services.template_analysis import TemplateAnalysisService

    session_factory = _get_async_session_factory()
    storage_service = _get_storage_service()
    job_tracker = _get_job_tracker()

    # Instantiate the analysis service
    template_analysis_service = TemplateAnalysisService(
        session_factory=session_factory,
        storage_service=storage_service,
        job_tracker=job_tracker,
    )

    # 1. Download .docx from MinIO
    async with session_factory() as session:
        version_result = await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == document_version_id,
                DocumentVersion.document_id == document_id,
            )
        )
        version = version_result.scalar_one_or_none()

        if version is None:
            raise ValueError(
                f"Document version {document_version_id} not found "
                f"for document {document_id}"
            )

        storage_key = version.storage_key

    # Validate .docx extension
    if not template_analysis_service.validate_docx_extension(storage_key):
        raise ValueError(
            f"Only .docx files can be registered as templates. "
            f"File has storage key: {storage_key}"
        )

    # Download file bytes from MinIO
    docx_bytes = await storage_service.download_file(storage_key)

    # 2. Extract structural layout via python-docx
    template_analysis = template_analysis_service.analyze_template(docx_bytes)

    # 3. Serialize TemplateAnalysis to JSON-compatible dict
    analysis_dict = _serialize_template_analysis(template_analysis)

    # 4. Persist Template_Analysis to DocumentTemplate record
    async with session_factory() as session:
        template_result = await session.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.document_version_id == document_version_id,
                DocumentTemplate.company_id == company_id,
            )
        )
        template_record = template_result.scalar_one_or_none()

        if template_record is None:
            raise ValueError(
                f"DocumentTemplate record not found for version "
                f"{document_version_id} company {company_id}"
            )

        template_record.template_analysis = analysis_dict
        template_record.status = "active"
        await session.commit()
        template_id = template_record.id

    # 5. Complete job via JobTracker
    async with session_factory() as session:
        await job_tracker.complete_job(
            session=session,
            job_id=job_id,
            result_reference=f"template_id:{template_id}",
        )
        await session.commit()

    logger.info(
        "Template analysis completed: template_id=%d, sections=%d, "
        "placeholders=%d, job_id=%s",
        template_id,
        template_analysis.total_sections,
        len(template_analysis.placeholder_markers),
        job_id,
    )

    return {
        "status": "completed",
        "template_id": template_id,
        "job_id": job_id,
        "total_sections": template_analysis.total_sections,
        "placeholder_count": len(template_analysis.placeholder_markers),
        "numbering_scheme": template_analysis.numbering_scheme,
    }


def _serialize_template_analysis(template_analysis) -> dict[str, Any]:
    """Serialize a TemplateAnalysis dataclass to a JSON-compatible dict.

    Converts TemplateSection dataclass instances to plain dicts.

    Args:
        template_analysis: TemplateAnalysis instance to serialize.

    Returns:
        JSON-serializable dictionary.
    """
    section_hierarchy = []
    for section in template_analysis.section_hierarchy:
        section_hierarchy.append({
            "heading": section.heading,
            "level": section.level,
            "position": section.position,
            "has_placeholder": section.has_placeholder,
            "placeholder_markers": section.placeholder_markers,
            "has_table": section.has_table,
            "table_columns": section.table_columns,
        })

    return {
        "section_hierarchy": section_hierarchy,
        "numbering_scheme": template_analysis.numbering_scheme,
        "paragraph_styles": template_analysis.paragraph_styles,
        "table_structures": template_analysis.table_structures,
        "header_footer_patterns": template_analysis.header_footer_patterns,
        "placeholder_markers": template_analysis.placeholder_markers,
        "total_sections": template_analysis.total_sections,
        "has_toc": template_analysis.has_toc,
        "page_layout": template_analysis.page_layout,
    }


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is retryable (transient error).

    Retryable exceptions are transient errors that may resolve on retry:
    - ConnectionError: network issues
    - OSError: filesystem/IO issues
    - InferenceTimeoutError: vLLM timeout
    - InferenceConnectionError: vLLM unreachable

    Non-retryable exceptions (permanent failures):
    - InferenceError (4xx client errors)
    - ValueError (validation errors)
    - SoftTimeLimitExceeded (task timeout)

    Args:
        exc: The exception to check.

    Returns:
        True if the exception is retryable, False otherwise.
    """
    retryable = _get_retryable_exceptions()
    return isinstance(exc, retryable)


async def _fail_analysis_job(
    job_id: str,
    document_version_id: int,
    company_id: int,
    error_message: str,
) -> None:
    """Mark the analysis job as failed and update the template status.

    Args:
        job_id: Job ID to fail.
        document_version_id: The document version being analyzed.
        company_id: Company scope.
        error_message: Reason for failure.
    """
    from sqlalchemy import select

    from alcoabase.models.document_generation import DocumentTemplate

    session_factory = _get_async_session_factory()
    job_tracker = _get_job_tracker()

    # Fail the job
    async with session_factory() as session:
        await job_tracker.fail_job(
            session=session,
            job_id=job_id,
            error_message=error_message,
        )
        await session.commit()

    # Update template status to "failed"
    async with session_factory() as session:
        template_result = await session.execute(
            select(DocumentTemplate).where(
                DocumentTemplate.document_version_id == document_version_id,
                DocumentTemplate.company_id == company_id,
            )
        )
        template_record = template_result.scalar_one_or_none()
        if template_record:
            template_record.status = "failed"
            await session.commit()

    logger.warning(
        "Analysis job %s failed for version %d: %s",
        job_id,
        document_version_id,
        error_message,
    )


# ---------------------------------------------------------------------------
# Task: generate_document_task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    soft_time_limit=600,
    max_retries=2,
    default_retry_delay=30,
    queue="ai_operations",
    name="alcoabase.tasks.document_generation_tasks.generate_document_task",
)
def generate_document_task(
    self: Task,
    job_id: str,
    template_id: int,
    title: str,
    generation_instructions: str,
    output_folder_path: str,
    requesting_user_id: int,
    company_id: int,
    reference_document_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Execute full template-based document generation pipeline.

    Pipeline:
    1. Load Template_Analysis (10%)
    2. Retrieve knowledge base content + build Cross_Reference_Map (20%)
    3. Generate content section-by-section (20-90%)
       - For each section: query KB, construct prompt, call InferenceClient
       - Process placeholder markers
       - Retry once on failure, insert placeholder on second failure
    4. Assemble output .docx (95%)
    5. Store in MinIO + create DB records (100%)

    Failure modes:
    - Provenance write failure → entire job fails, no document stored
    - All KB results empty → job fails (insufficient source material)
    - Individual section failure → retry once, then placeholder
    - Timeout (600s) → job fails

    Args:
        self: Celery task instance (bound).
        job_id: UUID of the generation job.
        template_id: ID of the template to use.
        title: Title for the generated document.
        generation_instructions: User-provided instructions.
        output_folder_path: Target folder path for output.
        requesting_user_id: ID of the requesting user.
        company_id: Company ID for tenant scoping.
        reference_document_ids: Optional reference document IDs.

    Returns:
        Dict with generation results (document_id, storage_key, etc.).

    Raises:
        Retry: On retryable transient errors with exponential backoff.
    """
    try:
        result = asyncio.run(
            _generate_document_async(
                job_id=job_id,
                template_id=template_id,
                title=title,
                generation_instructions=generation_instructions,
                output_folder_path=output_folder_path,
                requesting_user_id=requesting_user_id,
                company_id=company_id,
                reference_document_ids=reference_document_ids,
            )
        )
        return result

    except SoftTimeLimitExceeded:
        # Non-retryable: mark job as failed with timeout reason
        logger.error(
            "generate_document_task timed out for job_id=%s", job_id
        )
        asyncio.run(
            _fail_generation_job(
                job_id=job_id,
                company_id=company_id,
                error_message="Generation timeout exceeded (600s limit)",
            )
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "error": "Generation timeout exceeded (600s limit)",
        }

    except ValueError as exc:
        # Non-retryable: validation error (e.g., template not found, no KB results)
        logger.error(
            "generate_document_task failed with ValueError for job_id=%s: %s",
            job_id,
            exc,
        )
        asyncio.run(
            _fail_generation_job(
                job_id=job_id,
                company_id=company_id,
                error_message=str(exc)[:500],
            )
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "error": str(exc)[:500],
        }

    except Exception as exc:
        # Check if retryable (transient errors)
        if _is_retryable(exc):
            logger.warning(
                "generate_document_task retrying for job_id=%s (attempt %d): %s",
                job_id,
                self.request.retries + 1,
                exc,
            )
            raise self.retry(
                exc=exc,
                countdown=30 * (2**self.request.retries),
            )

        # Check if it's an InferenceError (non-retryable 4xx)
        from alcoabase.services.inference_client import InferenceError

        if isinstance(exc, InferenceError):
            logger.error(
                "generate_document_task failed with InferenceError for "
                "job_id=%s: %s",
                job_id,
                exc,
            )
            asyncio.run(
                _fail_generation_job(
                    job_id=job_id,
                    company_id=company_id,
                    error_message=f"Inference error: {str(exc)[:400]}",
                )
            )
            return {
                "status": "failed",
                "job_id": job_id,
                "error": f"Inference error: {str(exc)[:400]}",
            }

        # Unexpected error: mark as failed
        logger.exception(
            "generate_document_task unexpected error for job_id=%s", job_id
        )
        asyncio.run(
            _fail_generation_job(
                job_id=job_id,
                company_id=company_id,
                error_message=f"Unexpected error: {str(exc)[:400]}",
            )
        )
        return {
            "status": "failed",
            "job_id": job_id,
            "error": f"Unexpected error: {str(exc)[:400]}",
        }


async def _generate_document_async(
    job_id: str,
    template_id: int,
    title: str,
    generation_instructions: str,
    output_folder_path: str,
    requesting_user_id: int,
    company_id: int,
    reference_document_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Async implementation of the document generation pipeline.

    Delegates to TemplateDocumentGeneratorService.execute_generation_pipeline()
    which handles the full pipeline orchestration.

    Args:
        job_id: UUID of the generation job.
        template_id: ID of the template to use.
        title: Title for the generated document.
        generation_instructions: User-provided instructions.
        output_folder_path: Target folder path for output.
        requesting_user_id: ID of the requesting user.
        company_id: Company ID for tenant scoping.
        reference_document_ids: Optional reference document IDs.

    Returns:
        Dict with generation results.
    """
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.job_tracker import JobTracker
    from alcoabase.services.knowledge_service import KnowledgeService
    from alcoabase.services.service_factory import get_inference_client
    from alcoabase.services.storage_service import StorageService
    from alcoabase.services.template_analysis import TemplateAnalysisService
    from alcoabase.services.template_document_generator import (
        TemplateDocumentGeneratorService,
    )

    session_factory = _get_async_session_factory()
    storage_service = StorageService()
    job_tracker = JobTracker()
    inference_client = get_inference_client()
    knowledge_service = KnowledgeService(session_factory=session_factory)

    template_analysis_service = TemplateAnalysisService(
        session_factory=session_factory,
        storage_service=storage_service,
        job_tracker=job_tracker,
    )

    generator_service = TemplateDocumentGeneratorService(
        session_factory=session_factory,
        inference_client=inference_client,
        knowledge_service=knowledge_service,
        agent_registry=None,  # Not needed for pipeline execution
        storage_service=storage_service,
        job_tracker=job_tracker,
        template_analysis_service=template_analysis_service,
    )

    # Execute the full generation pipeline
    result = await generator_service.execute_generation_pipeline(
        job_id=job_id,
        template_id=template_id,
        title=title,
        generation_instructions=generation_instructions,
        output_folder_path=output_folder_path,
        requesting_user_id=requesting_user_id,
        company_id=company_id,
        reference_document_ids=reference_document_ids,
    )

    logger.info(
        "Document generation completed: job_id=%s, template_id=%d, title='%s'",
        job_id,
        template_id,
        title,
    )

    return {
        "status": "completed",
        "job_id": job_id,
        **result,
    }


async def _fail_generation_job(
    job_id: str,
    company_id: int,
    error_message: str,
) -> None:
    """Mark the generation job as failed in GenerationJobMetadata.

    Updates both the GenerationJobMetadata record and the JobTracker
    processing job.

    Args:
        job_id: Job ID to fail.
        company_id: Company scope.
        error_message: Reason for failure.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from alcoabase.models.document_generation import GenerationJobMetadata

    session_factory = _get_async_session_factory()
    job_tracker = _get_job_tracker()

    # Update GenerationJobMetadata
    async with session_factory() as session:
        result = await session.execute(
            select(GenerationJobMetadata).where(
                GenerationJobMetadata.job_id == job_id,
            )
        )
        job_record = result.scalar_one_or_none()
        if job_record:
            job_record.status = "failed"
            job_record.error_message = error_message
            job_record.completed_at = datetime.now(timezone.utc)
            await session.commit()

    # Also fail the JobTracker processing job (best effort)
    try:
        async with session_factory() as session:
            await job_tracker.fail_job(
                session=session,
                job_id=job_id,
                error_message=error_message,
            )
            await session.commit()
    except Exception:
        # JobTracker failure is non-critical here since we already
        # updated GenerationJobMetadata
        logger.debug(
            "Could not update JobTracker for job %s (may not exist)", job_id
        )

    logger.warning(
        "Generation job %s failed: %s", job_id, error_message
    )
