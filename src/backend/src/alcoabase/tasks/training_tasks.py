"""Celery tasks for AI-enhanced training ecosystem async operations.

Implements background tasks for:
- Training schedule generation via Educational Specialist archetype
- Training material generation from document content
- Comprehension question generation with difficulty distribution
- Role-play response evaluation with 3-dimension scoring
- Skill gap recalculation across company users
- Legacy training content generation (backward compatibility)

All tasks route to the "ai_operations" queue with:
- soft_time_limit=600 (10 minutes)
- max_retries=3
- Exponential backoff with jitter on retryable errors
- Job tracker integration for progress reporting

References:
    - Requirements 12.1–12.10: Celery Task Definitions for Async AI Operations
    - Design doc Section 8: Celery Tasks
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Retryable exception types
# ---------------------------------------------------------------------------

RETRYABLE_EXCEPTIONS = (ConnectionError, OSError)


# ---------------------------------------------------------------------------
# Helper: run async code in sync Celery worker context
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """Run an async coroutine in a new event loop (for Celery workers).

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Helper: get services for task workers
# ---------------------------------------------------------------------------


def _get_session_factory():
    """Get or create an async session factory for Celery task workers."""
    from alcoabase.config import get_settings
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

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


def _get_inference_client():
    """Get the shared InferenceClient singleton."""
    from alcoabase.services.service_factory import get_inference_client

    return get_inference_client()


def _get_agent_registry():
    """Get an AgentRegistryService instance for task workers."""
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


def _get_storage_service():
    """Get a StorageService instance."""
    from alcoabase.services.storage_service import StorageService

    return StorageService()


def _get_job_tracker():
    """Get a JobTracker instance."""
    from alcoabase.services.job_tracker import JobTracker

    return JobTracker()


def _retry_countdown(retries: int) -> float:
    """Compute exponential backoff with jitter.

    Args:
        retries: Current retry count (0-based).

    Returns:
        Countdown in seconds before next retry.
    """
    return 30 * (2 ** retries) + random.uniform(0, 5)


# ---------------------------------------------------------------------------
# Task: generate_training_schedule
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.training_tasks.generate_training_schedule",
    soft_time_limit=600,
    max_retries=3,
    default_retry_delay=30,
    queue="ai_operations",
)
def generate_training_schedule(
    self,
    user_id: int,
    company_id: int,
    job_id: str,
) -> dict[str, Any]:
    """Generate a personalized training schedule via Educational Specialist.

    Retrieves user role and assigned documents, constructs a schedule
    generation prompt using the Educational Specialist archetype, calls
    InferenceClient, parses the response into a TrainingSchedule, and
    persists to the database.

    Args:
        self: Celery task instance (bound).
        user_id: ID of the user to generate a schedule for.
        company_id: Company ID for tenant isolation.
        job_id: Job tracker ID for progress reporting.

    Returns:
        Dict with schedule generation results.
    """
    return _run_async(
        _generate_training_schedule_async(self, user_id, company_id, job_id)
    )


async def _generate_training_schedule_async(
    task,
    user_id: int,
    company_id: int,
    job_id: str,
) -> dict[str, Any]:
    """Async implementation of generate_training_schedule."""
    from alcoabase.config import get_settings
    from alcoabase.models.document import Document
    from alcoabase.models.training import TrainingRecord, TrainingTask
    from alcoabase.models.training_ecosystem import TrainingSchedule
    from alcoabase.models.user import User
    from alcoabase.services.inference_client import (
        InferenceConnectionError,
        InferenceError,
        InferenceTimeoutError,
    )
    from alcoabase.services.job_tracker import JobTracker
    from sqlalchemy import select

    settings = get_settings()
    session_factory = _get_session_factory()
    inference_client = _get_inference_client()
    agent_registry = _get_agent_registry()
    job_tracker = JobTracker()

    # Create job tracking entry
    async with session_factory() as session:
        try:
            await job_tracker.create_job(
                session, str(user_id), "generate_schedule",
                estimated_duration_seconds=120, company_id=company_id,
            )
            await session.commit()
        except Exception:
            # Job may already exist from service layer dispatch
            await session.rollback()

    try:
        # Step 1: Retrieve user info and assigned documents
        async with session_factory() as session:
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                raise ValueError(f"User not found: {user_id}")

            # Get assigned training tasks (for context)
            tasks_result = await session.execute(
                select(TrainingTask).where(
                    TrainingTask.assigned_user_id == user_id,
                    TrainingTask.company_id == company_id,
                )
            )
            tasks_result.scalars().all()  # Validate query succeeds

            # Get documents requiring training
            docs_result = await session.execute(
                select(Document).where(
                    Document.company_id == company_id,
                    Document.current_status.in_(
                        ["InTraining", "Active", "Approved"]
                    ),
                )
            )
            documents = list(docs_result.scalars().all())

            # Get completed training records
            records_result = await session.execute(
                select(TrainingRecord).where(
                    TrainingRecord.user_id == user_id,
                    TrainingRecord.company_id == company_id,
                    TrainingRecord.is_valid.is_(True),
                )
            )
            completed_records = list(records_result.scalars().all())

            await job_tracker.update_progress(session, job_id, 20)
            await session.commit()

        # Step 2: Get Educational Specialist archetype
        archetype_config = agent_registry._load_archetype_raw(
            "Educational Specialist"
        )
        system_prompt = (
            archetype_config.get("system_prompt", "")
            if archetype_config
            else "You are an Educational Specialist for regulated industries."
        )

        # Step 3: Construct schedule generation prompt
        completed_uuids = {r.sop_document_uuid for r in completed_records}
        pending_docs = [
            d for d in documents if d.document_uuid not in completed_uuids
        ]

        doc_list = "\n".join(
            f"- {d.title} (status: {d.current_status})"
            for d in pending_docs[:50]  # Limit to avoid context overflow
        )

        user_prompt = (
            f"Generate a personalized training schedule for user "
            f"'{user.full_name}' (role: {getattr(user, 'role', 'trainee')}).\n\n"
            f"Documents requiring training ({len(pending_docs)} total):\n"
            f"{doc_list}\n\n"
            f"Already completed: {len(completed_records)} documents.\n\n"
            "Respond with a JSON object containing:\n"
            '- "items": array of training items, each with:\n'
            '  - "document_title": string\n'
            '  - "priority": "Critical"|"High"|"Medium"|"Low"\n'
            '  - "suggested_deadline_days": integer (days from now)\n'
            '  - "rationale": string explaining the ordering\n'
            '- "total_items": integer count\n'
            '- "recommendations": string with overall recommendations\n'
        )

        # Step 4: Call InferenceClient
        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 40)
            await session.commit()

        response_text = await inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=4096,
            timeout=120.0,
        )

        # Step 5: Parse response into schedule data
        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 70)
            await session.commit()

        try:
            schedule_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            import re
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                schedule_data = json.loads(json_match.group())
            else:
                schedule_data = {
                    "items": [
                        {"document_title": d.title, "priority": "Medium",
                         "suggested_deadline_days": 30, "rationale": "Auto-assigned"}
                        for d in pending_docs
                    ],
                    "total_items": len(pending_docs),
                    "recommendations": response_text[:500],
                }

        total_items = len(pending_docs)
        completed_items = len(completed_records)
        from alcoabase.services.training_planner import compute_compliance_percentage
        compliance = compute_compliance_percentage(
            completed_items, total_items + completed_items
        )

        # Step 6: Persist TrainingSchedule to DB
        now = datetime.now(UTC)
        async with session_factory() as session:
            # Upsert: check if schedule exists
            existing_result = await session.execute(
                select(TrainingSchedule).where(
                    TrainingSchedule.user_id == user_id,
                    TrainingSchedule.company_id == company_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                existing.schedule_data = schedule_data
                existing.compliance_percentage = compliance
                existing.total_items = total_items
                existing.completed_items = completed_items
                existing.generated_at = now
                existing.last_recalculated_at = now
            else:
                schedule = TrainingSchedule(
                    user_id=user_id,
                    company_id=company_id,
                    schedule_data=schedule_data,
                    compliance_percentage=compliance,
                    total_items=total_items,
                    completed_items=completed_items,
                    generated_at=now,
                    last_recalculated_at=now,
                )
                session.add(schedule)

            await job_tracker.update_progress(session, job_id, 90)
            await session.commit()

        # Step 7: Complete job
        async with session_factory() as session:
            await job_tracker.complete_job(session, job_id)
            await session.commit()

        logger.info(
            "Generated training schedule for user %d, company %d (job=%s)",
            user_id, company_id, job_id,
        )

        return {
            "job_id": job_id,
            "user_id": user_id,
            "company_id": company_id,
            "total_items": total_items,
            "completed_items": completed_items,
            "compliance_percentage": compliance,
            "status": "completed",
        }

    except SoftTimeLimitExceeded:
        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, "timeout")
            await session.commit()
        logger.error("Schedule generation timed out for user %d", user_id)
        return {"job_id": job_id, "status": "failed", "reason": "timeout"}

    except (InferenceTimeoutError, InferenceConnectionError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Inference unavailable after retries: {exc}",
                )
                await session.commit()
            return {"job_id": job_id, "status": "failed", "reason": str(exc)}

    except (ConnectionError, OSError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Connection error after retries: {exc}",
                )
                await session.commit()
            return {"job_id": job_id, "status": "failed", "reason": str(exc)}

    except (InferenceError, ValueError) as exc:
        # Non-retryable errors
        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, str(exc))
            await session.commit()
        logger.error("Schedule generation failed: %s", exc)
        return {"job_id": job_id, "status": "failed", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Task: generate_training_materials
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.training_tasks.generate_training_materials",
    soft_time_limit=600,
    max_retries=3,
    default_retry_delay=30,
    queue="ai_operations",
)
def generate_training_materials(
    self,
    document_id: int,
    document_version_id: int,
    company_id: int,
    material_types: list[str],
    job_id: str,
) -> dict[str, Any]:
    """Generate training materials for each requested type.

    Retrieves document content from MinIO via StorageService, generates
    each material type via InferenceClient, persists TrainingMaterial
    records with status=pending_review, and records inference_duration_ms.

    Args:
        self: Celery task instance (bound).
        document_id: Source document ID.
        document_version_id: Specific version to generate materials from.
        company_id: Company ID for tenant isolation.
        material_types: List of material type strings to generate.
        job_id: Job tracker ID for progress reporting.

    Returns:
        Dict with generation results.
    """
    return _run_async(
        _generate_training_materials_async(
            self, document_id, document_version_id,
            company_id, material_types, job_id,
        )
    )


async def _generate_training_materials_async(
    task,
    document_id: int,
    document_version_id: int,
    company_id: int,
    material_types: list[str],
    job_id: str,
) -> dict[str, Any]:
    """Async implementation of generate_training_materials."""
    from alcoabase.models.document import Document, DocumentVersion
    from alcoabase.models.training_ecosystem import (
        ContentStatus,
        TrainingMaterial,
    )
    from alcoabase.services.inference_client import (
        InferenceConnectionError,
        InferenceError,
        InferenceTimeoutError,
    )
    from alcoabase.services.job_tracker import JobTracker
    from sqlalchemy import select

    session_factory = _get_session_factory()
    inference_client = _get_inference_client()
    agent_registry = _get_agent_registry()
    storage_service = _get_storage_service()
    job_tracker = JobTracker()

    # Create job tracking entry
    async with session_factory() as session:
        try:
            await job_tracker.create_job(
                session, str(document_id), "generate_materials",
                estimated_duration_seconds=300, company_id=company_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()

    records_created = 0

    try:
        # Step 1: Retrieve document content from MinIO
        async with session_factory() as session:
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = doc_result.scalar_one_or_none()
            if document is None:
                raise ValueError(f"Document not found: {document_id}")

            version_result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.id == document_version_id
                )
            )
            version = version_result.scalar_one_or_none()
            if version is None:
                raise ValueError(
                    f"Document version not found: {document_version_id}"
                )

            await job_tracker.update_progress(session, job_id, 10)
            await session.commit()

        # Retrieve file content from MinIO
        storage_key = (
            f"documents/{document.document_uuid}/"
            f"v{version.major_version}.{version.minor_version}"
        )
        try:
            file_bytes = await storage_service.download_file(storage_key)
            document_content = file_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            # Try alternative key patterns
            try:
                alt_key = f"documents/{document.document_uuid}/content"
                file_bytes = await storage_service.download_file(alt_key)
                document_content = file_bytes.decode("utf-8", errors="replace")
            except Exception:
                raise OSError(
                    f"Failed to retrieve document content from storage: {exc}"
                ) from exc

        # Step 2: Get Educational Specialist archetype (used by mat_service)
        # The TrainingMaterialGeneratorService handles archetype loading internally

        # Step 3: Generate each material type
        total_types = len(material_types)
        for i, material_type in enumerate(material_types):
            start_time = time.perf_counter()

            progress = 10 + int((i / total_types) * 80)
            async with session_factory() as session:
                await job_tracker.update_progress(session, job_id, progress)
                await session.commit()

            try:
                from alcoabase.services.training_material_generator import (
                    TrainingMaterialGeneratorService,
                )

                # Use the service's generation logic
                mat_service = TrainingMaterialGeneratorService(
                    session_factory=session_factory,
                    inference_client=inference_client,
                    agent_registry=agent_registry,
                    storage_service=storage_service,
                )
                content_result = await mat_service.generate_material_content(
                    document_content=document_content,
                    material_type=material_type,
                )

                inference_duration_ms = int(
                    (time.perf_counter() - start_time) * 1000
                )

                # Persist TrainingMaterial record
                async with session_factory() as session:
                    material = TrainingMaterial(
                        document_id=document_id,
                        document_version_id=document_version_id,
                        company_id=company_id,
                        material_type=material_type,
                        content_data=content_result.get("content", {}),
                        learning_objectives=content_result.get(
                            "learning_objectives", []
                        ),
                        estimated_duration_minutes=content_result.get(
                            "estimated_duration_minutes", 10
                        ),
                        status=ContentStatus.PENDING_REVIEW.value,
                        generated_by_agent_id="Educational Specialist",
                        inference_duration_ms=inference_duration_ms,
                    )
                    session.add(material)
                    await session.commit()

                records_created += 1
                logger.info(
                    "Generated %s material for doc %d (duration=%dms)",
                    material_type, document_id, inference_duration_ms,
                )

            except (InferenceTimeoutError, InferenceConnectionError) as exc:
                # Retryable — but preserve partial records
                if records_created > 0:
                    async with session_factory() as session:
                        await job_tracker.fail_job(
                            session, job_id,
                            f"Partial completion ({records_created}/{total_types} "
                            f"materials): {exc}",
                        )
                        await session.commit()
                    return {
                        "job_id": job_id,
                        "status": "failed",
                        "records_created": records_created,
                        "reason": str(exc),
                    }
                # No partial records — retry the whole task
                try:
                    task.retry(
                        exc=exc,
                        countdown=_retry_countdown(task.request.retries),
                    )
                except task.MaxRetriesExceededError:
                    async with session_factory() as session:
                        await job_tracker.fail_job(
                            session, job_id,
                            f"Inference unavailable after retries: {exc}",
                        )
                        await session.commit()
                    return {
                        "job_id": job_id,
                        "status": "failed",
                        "reason": str(exc),
                    }

            except (InferenceError, ValueError) as exc:
                # Non-retryable — preserve partial records
                logger.warning(
                    "Failed to generate %s material: %s",
                    material_type, exc,
                )
                if records_created > 0:
                    async with session_factory() as session:
                        await job_tracker.fail_job(
                            session, job_id,
                            f"Partial completion ({records_created}/{total_types} "
                            f"materials): {exc}",
                        )
                        await session.commit()
                    return {
                        "job_id": job_id,
                        "status": "failed",
                        "records_created": records_created,
                        "reason": str(exc),
                    }
                async with session_factory() as session:
                    await job_tracker.fail_job(session, job_id, str(exc))
                    await session.commit()
                return {
                    "job_id": job_id,
                    "status": "failed",
                    "reason": str(exc),
                }

        # All materials generated successfully
        async with session_factory() as session:
            await job_tracker.complete_job(session, job_id)
            await session.commit()

        logger.info(
            "Generated %d materials for document %d (job=%s)",
            records_created, document_id, job_id,
        )

        return {
            "job_id": job_id,
            "document_id": document_id,
            "records_created": records_created,
            "status": "completed",
        }

    except SoftTimeLimitExceeded:
        async with session_factory() as session:
            msg = "timeout"
            if records_created > 0:
                msg = (
                    f"timeout (partial: {records_created}/{len(material_types)} "
                    f"materials created)"
                )
            await job_tracker.fail_job(session, job_id, msg)
            await session.commit()
        return {
            "job_id": job_id,
            "status": "failed",
            "records_created": records_created,
            "reason": "timeout",
        }

    except (ConnectionError, OSError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Connection error after retries: {exc}",
                )
                await session.commit()
            return {
                "job_id": job_id,
                "status": "failed",
                "records_created": records_created,
                "reason": str(exc),
            }


# ---------------------------------------------------------------------------
# Task: generate_questions
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.training_tasks.generate_questions",
    soft_time_limit=600,
    max_retries=3,
    default_retry_delay=30,
    queue="ai_operations",
)
def generate_questions(
    self,
    document_id: int,
    document_version_id: int,
    company_id: int,
    question_count: int,
    difficulty_distribution: dict[str, float],
    job_id: str,
) -> dict[str, Any]:
    """Generate comprehension questions with validated answers.

    Retrieves document content, generates questions with difficulty
    distribution, validates no duplicate (section_ref, type) pairs,
    and persists GeneratedQuestion records with status=pending_review.

    Args:
        self: Celery task instance (bound).
        document_id: Source document ID.
        document_version_id: Specific version to generate questions from.
        company_id: Company ID for tenant isolation.
        question_count: Number of questions to generate (5–20).
        difficulty_distribution: Distribution across difficulty levels.
        job_id: Job tracker ID for progress reporting.

    Returns:
        Dict with generation results.
    """
    return _run_async(
        _generate_questions_async(
            self, document_id, document_version_id,
            company_id, question_count, difficulty_distribution, job_id,
        )
    )


async def _generate_questions_async(
    task,
    document_id: int,
    document_version_id: int,
    company_id: int,
    question_count: int,
    difficulty_distribution: dict[str, float],
    job_id: str,
) -> dict[str, Any]:
    """Async implementation of generate_questions."""
    from alcoabase.config import get_settings
    from alcoabase.models.document import Document, DocumentVersion
    from alcoabase.models.training_ecosystem import (
        ContentStatus,
        GeneratedQuestion,
    )
    from alcoabase.services.inference_client import (
        InferenceConnectionError,
        InferenceError,
        InferenceTimeoutError,
    )
    from alcoabase.services.job_tracker import JobTracker
    from sqlalchemy import select

    settings = get_settings()
    session_factory = _get_session_factory()
    inference_client = _get_inference_client()
    agent_registry = _get_agent_registry()
    storage_service = _get_storage_service()
    job_tracker = JobTracker()

    # Create job tracking entry
    async with session_factory() as session:
        try:
            await job_tracker.create_job(
                session, str(document_id), "generate_questions",
                estimated_duration_seconds=180, company_id=company_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()

    records_created = 0

    try:
        # Step 1: Retrieve document content
        async with session_factory() as session:
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = doc_result.scalar_one_or_none()
            if document is None:
                raise ValueError(f"Document not found: {document_id}")

            version_result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.id == document_version_id
                )
            )
            version = version_result.scalar_one_or_none()
            if version is None:
                raise ValueError(
                    f"Document version not found: {document_version_id}"
                )

            await job_tracker.update_progress(session, job_id, 10)
            await session.commit()

        # Retrieve file content from MinIO
        storage_key = (
            f"documents/{document.document_uuid}/"
            f"v{version.major_version}.{version.minor_version}"
        )
        try:
            file_bytes = await storage_service.download_file(storage_key)
            document_content = file_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            try:
                alt_key = f"documents/{document.document_uuid}/content"
                file_bytes = await storage_service.download_file(alt_key)
                document_content = file_bytes.decode("utf-8", errors="replace")
            except Exception:
                raise OSError(
                    f"Failed to retrieve document content: {exc}"
                ) from exc

        # Step 2: Get Educational Specialist archetype
        archetype_config = agent_registry._load_archetype_raw(
            "Educational Specialist"
        )
        system_prompt = (
            archetype_config.get("system_prompt", "")
            if archetype_config
            else (
                "You are an Educational Specialist creating comprehension "
                "assessments for regulated industries. Always respond with "
                "valid JSON."
            )
        )

        # Step 3: Compute difficulty counts from distribution
        basic_count = max(1, int(question_count * difficulty_distribution.get("basic", 0.4)))
        intermediate_count = max(1, int(question_count * difficulty_distribution.get("intermediate", 0.4)))
        advanced_count = question_count - basic_count - intermediate_count
        # Ensure advanced doesn't exceed 30%
        max_advanced = int(question_count * 0.3)
        if advanced_count > max_advanced:
            overflow = advanced_count - max_advanced
            advanced_count = max_advanced
            basic_count += overflow

        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 30)
            await session.commit()

        # Step 4: Generate questions via InferenceClient
        user_prompt = (
            f"Generate exactly {question_count} comprehension questions from "
            f"the following document content. Distribution:\n"
            f"- {basic_count} basic questions\n"
            f"- {intermediate_count} intermediate questions\n"
            f"- {advanced_count} advanced questions\n\n"
            "Question types to use: multiple_choice, true_false, "
            "scenario_based, fill_in_blank.\n\n"
            "IMPORTANT: No two questions should reference the same "
            "sop_section_ref with the same question_type.\n\n"
            "Respond with a JSON object containing a 'questions' array. "
            "Each question must have:\n"
            '- "question_text": string (max 1000 chars)\n'
            '- "question_type": "multiple_choice"|"true_false"|'
            '"scenario_based"|"fill_in_blank"\n'
            '- "correct_answer": string (max 500 chars)\n'
            '- "distractors": array of strings (for multiple_choice, '
            "exactly 3 wrong options)\n"
            '- "explanation": string (max 500 chars)\n'
            '- "difficulty_level": "basic"|"intermediate"|"advanced"\n'
            '- "bloom_taxonomy_level": "remember"|"understand"|"apply"|'
            '"analyze"\n'
            '- "sop_section_ref": string (section reference in document)\n\n'
            f"Document content:\n{document_content[:20000]}"
        )

        response_text = await inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            max_tokens=8192,
            timeout=120.0,
        )

        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 60)
            await session.commit()

        # Step 5: Parse response
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                raise ValueError(
                    "Failed to parse question generation response as JSON"
                )

        questions_data = parsed.get("questions", [])
        if not questions_data:
            raise ValueError(
                "No questions generated from document content"
            )

        # Step 6: Validate no duplicate (section_ref, type) pairs
        seen_pairs: set[tuple[str, str]] = set()
        valid_questions: list[dict] = []

        for q in questions_data:
            section_ref = q.get("sop_section_ref", "")
            q_type = q.get("question_type", "")
            pair = (section_ref, q_type)

            if pair in seen_pairs and section_ref:
                # Skip duplicate pair
                logger.debug(
                    "Skipping duplicate (section_ref=%s, type=%s)",
                    section_ref, q_type,
                )
                continue

            if section_ref:
                seen_pairs.add(pair)
            valid_questions.append(q)

        # Step 7: Persist GeneratedQuestion records
        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 80)

            for q in valid_questions[:question_count]:
                try:
                    question_type_val = q.get("question_type", "multiple_choice")
                    difficulty_val = q.get("difficulty_level", "basic")

                    question = GeneratedQuestion(
                        document_id=document_id,
                        document_version_id=document_version_id,
                        company_id=company_id,
                        question_text=q.get("question_text", "")[:1000],
                        question_type=question_type_val,
                        correct_answer=q.get("correct_answer", "")[:500],
                        distractors=q.get("distractors"),
                        explanation=q.get("explanation", "")[:500],
                        difficulty_level=difficulty_val,
                        bloom_taxonomy_level=q.get(
                            "bloom_taxonomy_level", "remember"
                        ),
                        sop_section_ref=q.get("sop_section_ref", "")[:500],
                        status=ContentStatus.PENDING_REVIEW.value,
                    )
                    session.add(question)
                    records_created += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to persist question: %s", exc
                    )

            await session.commit()

        # Step 8: Complete job
        async with session_factory() as session:
            await job_tracker.complete_job(session, job_id)
            await session.commit()

        logger.info(
            "Generated %d questions for document %d (job=%s)",
            records_created, document_id, job_id,
        )

        return {
            "job_id": job_id,
            "document_id": document_id,
            "records_created": records_created,
            "status": "completed",
        }

    except SoftTimeLimitExceeded:
        async with session_factory() as session:
            msg = "timeout"
            if records_created > 0:
                msg = (
                    f"timeout (partial: {records_created} questions created)"
                )
            await job_tracker.fail_job(session, job_id, msg)
            await session.commit()
        return {
            "job_id": job_id,
            "status": "failed",
            "records_created": records_created,
            "reason": "timeout",
        }

    except (InferenceTimeoutError, InferenceConnectionError) as exc:
        if records_created > 0:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Partial completion ({records_created} questions): {exc}",
                )
                await session.commit()
            return {
                "job_id": job_id,
                "status": "failed",
                "records_created": records_created,
                "reason": str(exc),
            }
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Inference unavailable after retries: {exc}",
                )
                await session.commit()
            return {"job_id": job_id, "status": "failed", "reason": str(exc)}

    except (ConnectionError, OSError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Connection error after retries: {exc}",
                )
                await session.commit()
            return {
                "job_id": job_id,
                "status": "failed",
                "records_created": records_created,
                "reason": str(exc),
            }

    except (InferenceError, ValueError) as exc:
        async with session_factory() as session:
            msg = str(exc)
            if records_created > 0:
                msg = f"Partial ({records_created} questions): {exc}"
            await job_tracker.fail_job(session, job_id, msg)
            await session.commit()
        return {
            "job_id": job_id,
            "status": "failed",
            "records_created": records_created,
            "reason": str(exc),
        }


# ---------------------------------------------------------------------------
# Task: evaluate_roleplay_response
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.training_tasks.evaluate_roleplay_response",
    soft_time_limit=600,
    max_retries=3,
    default_retry_delay=30,
    queue="ai_operations",
)
def evaluate_roleplay_response(
    self,
    session_id: int,
    response_text: str,
    job_id: str,
) -> dict[str, Any]:
    """Evaluate user response and generate next auditor question.

    Evaluates the user response on 3 dimensions (factual_accuracy,
    completeness, document_reference_quality), generates the next
    question or computes session summary, and updates VirtualAuditSession.

    Args:
        self: Celery task instance (bound).
        session_id: Virtual audit session ID.
        response_text: User's response text.
        job_id: Job tracker ID for progress reporting.

    Returns:
        Dict with evaluation results.
    """
    return _run_async(
        _evaluate_roleplay_response_async(
            self, session_id, response_text, job_id,
        )
    )


async def _evaluate_roleplay_response_async(
    task,
    session_id: int,
    response_text: str,
    job_id: str,
) -> dict[str, Any]:
    """Async implementation of evaluate_roleplay_response."""
    from alcoabase.config import get_settings
    from alcoabase.models.document import Document
    from alcoabase.models.training_ecosystem import (
        SessionStatus,
        VirtualAuditSession,
    )
    from alcoabase.services.inference_client import (
        InferenceConnectionError,
        InferenceError,
        InferenceTimeoutError,
    )
    from alcoabase.services.job_tracker import JobTracker
    from alcoabase.services.roleplay_engine import (
        compute_session_score,
        determine_pass_fail,
    )
    from sqlalchemy import select

    settings = get_settings()
    session_factory = _get_session_factory()
    inference_client = _get_inference_client()
    job_tracker = JobTracker()

    # Create job tracking entry
    async with session_factory() as session:
        try:
            await job_tracker.create_job(
                session, str(session_id), "evaluate_response",
                estimated_duration_seconds=60, company_id=0,
            )
            await session.commit()
        except Exception:
            await session.rollback()

    try:
        # Step 1: Retrieve session
        async with session_factory() as session:
            result = await session.execute(
                select(VirtualAuditSession).where(
                    VirtualAuditSession.id == session_id
                )
            )
            audit_session = result.scalar_one_or_none()
            if audit_session is None:
                raise ValueError(f"Session not found: {session_id}")

            if audit_session.status != SessionStatus.IN_PROGRESS:
                raise ValueError(
                    f"Session {session_id} is not in progress "
                    f"(status: {audit_session.status})"
                )

            # Get document info for context
            doc_result = await session.execute(
                select(Document).where(
                    Document.id == audit_session.document_id
                )
            )
            document = doc_result.scalar_one_or_none()
            doc_title = document.title if document else "Unknown Document"

            await job_tracker.update_progress(session, job_id, 20)
            await session.commit()

        # Step 2: Construct evaluation prompt
        system_prompt = (
            "You are a compliance auditor evaluating an employee's response "
            "during a virtual audit session. Evaluate the response on three "
            "dimensions and generate the next question.\n\n"
            "Respond with a JSON object containing:\n"
            '- "evaluation": {\n'
            '    "factual_accuracy": float 0.0-1.0,\n'
            '    "completeness": float 0.0-1.0,\n'
            '    "document_reference_quality": float 0.0-1.0\n'
            "  }\n"
            '- "next_question": string (the next auditor question, or null '
            "if session is complete)\n"
            '- "feedback": string (brief feedback on the response)\n'
        )

        # Build conversation context from session_data
        session_data = audit_session.session_data or {"turns": []}
        turns = session_data.get("turns", [])
        current_turn = audit_session.turns_completed

        # Get the last question asked
        last_question = ""
        if turns and len(turns) > current_turn - 1 and current_turn > 0:
            last_turn = turns[-1]
            last_question = last_turn.get("question", "")
        elif turns:
            last_question = turns[-1].get("question", "")

        # Determine difficulty level for next question
        total_turns = audit_session.total_turns
        next_turn = current_turn + 1
        if next_turn <= int(total_turns * 0.4):
            difficulty = "foundational"
        elif next_turn <= int(total_turns * 0.75):
            difficulty = "applied"
        else:
            difficulty = "analytical"

        is_final_turn = (next_turn >= total_turns)

        user_prompt = (
            f"Document: {doc_title}\n"
            f"Turn {current_turn + 1} of {total_turns}\n"
            f"Previous question: {last_question}\n"
            f"Employee response: {response_text}\n\n"
        )
        if not is_final_turn:
            user_prompt += (
                f"Generate a {difficulty}-level follow-up question about "
                f"the document content.\n"
            )
        else:
            user_prompt += (
                "This is the final turn. Evaluate the response and set "
                '"next_question" to null.\n'
            )

        # Step 3: Call InferenceClient for evaluation
        async with session_factory() as session:
            await job_tracker.update_progress(session, job_id, 50)
            await session.commit()

        eval_response = await inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=1024,
            timeout=60.0,
        )

        # Step 4: Parse evaluation response
        try:
            eval_data = json.loads(eval_response)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"\{.*\}", eval_response, re.DOTALL)
            if json_match:
                eval_data = json.loads(json_match.group())
            else:
                # Fallback evaluation
                eval_data = {
                    "evaluation": {
                        "factual_accuracy": 0.5,
                        "completeness": 0.5,
                        "document_reference_quality": 0.5,
                    },
                    "next_question": None if is_final_turn else (
                        "Can you elaborate on the key procedures "
                        "described in this document?"
                    ),
                    "feedback": "Response evaluated.",
                }

        evaluation = eval_data.get("evaluation", {})
        next_question = eval_data.get("next_question")
        feedback = eval_data.get("feedback", "")

        # Ensure evaluation has all required fields
        factual_accuracy = float(evaluation.get("factual_accuracy", 0.5))
        completeness = float(evaluation.get("completeness", 0.5))
        doc_ref_quality = float(
            evaluation.get("document_reference_quality", 0.5)
        )

        # Clamp values to [0.0, 1.0]
        factual_accuracy = max(0.0, min(1.0, factual_accuracy))
        completeness = max(0.0, min(1.0, completeness))
        doc_ref_quality = max(0.0, min(1.0, doc_ref_quality))

        # Step 5: Update VirtualAuditSession
        turn_data = {
            "turn_number": current_turn + 1,
            "question": last_question,
            "response": response_text,
            "factual_accuracy": factual_accuracy,
            "completeness": completeness,
            "document_reference_quality": doc_ref_quality,
            "feedback": feedback,
        }
        if next_question:
            turn_data["next_question"] = next_question

        async with session_factory() as session:
            result = await session.execute(
                select(VirtualAuditSession).where(
                    VirtualAuditSession.id == session_id
                )
            )
            audit_session = result.scalar_one()

            # Append turn to session_data
            session_data = dict(audit_session.session_data or {"turns": []})
            turns = session_data.get("turns", [])
            turns.append(turn_data)
            session_data["turns"] = turns

            audit_session.session_data = session_data
            audit_session.turns_completed = current_turn + 1

            # Check if session is complete
            session_complete = is_final_turn or next_question is None
            if session_complete:
                # Compute overall score
                overall_score = compute_session_score(turns)
                passed = determine_pass_fail(
                    overall_score, audit_session.turns_completed
                )

                audit_session.status = SessionStatus.COMPLETED
                audit_session.overall_score = overall_score
                audit_session.passed = passed
                audit_session.completed_at = datetime.now(UTC)
                audit_session.summary_data = {
                    "overall_score": overall_score,
                    "passed": passed,
                    "turns_completed": audit_session.turns_completed,
                    "total_turns": total_turns,
                    "feedback": feedback,
                }

            await job_tracker.update_progress(session, job_id, 90)
            await session.commit()

        # Step 6: Complete job
        async with session_factory() as session:
            await job_tracker.complete_job(session, job_id)
            await session.commit()

        current_score = compute_session_score(turns)

        logger.info(
            "Evaluated roleplay response for session %d, turn %d/%d",
            session_id, current_turn + 1, total_turns,
        )

        return {
            "job_id": job_id,
            "session_id": session_id,
            "evaluation": {
                "factual_accuracy": factual_accuracy,
                "completeness": completeness,
                "document_reference_quality": doc_ref_quality,
            },
            "next_question": next_question,
            "session_complete": session_complete,
            "current_score": current_score,
            "status": "completed",
        }

    except SoftTimeLimitExceeded:
        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, "timeout")
            await session.commit()
        return {"job_id": job_id, "status": "failed", "reason": "timeout"}

    except (InferenceTimeoutError, InferenceConnectionError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Inference unavailable after retries: {exc}",
                )
                await session.commit()
            return {"job_id": job_id, "status": "failed", "reason": str(exc)}

    except (ConnectionError, OSError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            async with session_factory() as session:
                await job_tracker.fail_job(
                    session, job_id,
                    f"Connection error after retries: {exc}",
                )
                await session.commit()
            return {"job_id": job_id, "status": "failed", "reason": str(exc)}

    except (InferenceError, ValueError) as exc:
        async with session_factory() as session:
            await job_tracker.fail_job(session, job_id, str(exc))
            await session.commit()
        return {"job_id": job_id, "status": "failed", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Task: recalculate_skill_gaps
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.training_tasks.recalculate_skill_gaps",
    soft_time_limit=600,
    max_retries=3,
    default_retry_delay=30,
    queue="ai_operations",
)
def recalculate_skill_gaps(
    self,
    company_id: int | None = None,
) -> dict[str, Any]:
    """Recalculate all skill gaps for a company (or all companies).

    Compares required vs completed training for all users in the company,
    creates new SkillGap records for missing training, and resolves gaps
    where training has been completed.

    Args:
        self: Celery task instance (bound).
        company_id: Company ID to recalculate for. If None, runs for all.

    Returns:
        Dict with recalculation results.
    """
    return _run_async(
        _recalculate_skill_gaps_async(self, company_id)
    )


async def _recalculate_skill_gaps_async(
    task,
    company_id: int | None,
) -> dict[str, Any]:
    """Async implementation of recalculate_skill_gaps."""
    from alcoabase.models.company import Company  # noqa: F401
    from alcoabase.services.training_planner import TrainingPlannerService
    from sqlalchemy import select

    session_factory = _get_session_factory()
    inference_client = _get_inference_client()
    agent_registry = _get_agent_registry()

    try:
        # Determine which companies to process
        if company_id is not None:
            company_ids = [company_id]
        else:
            async with session_factory() as session:
                result = await session.execute(select(Company.id))
                company_ids = [row[0] for row in result.all()]

        total_changes = 0

        planner = TrainingPlannerService(
            session_factory=session_factory,
            inference_client=inference_client,
            agent_registry=agent_registry,
        )

        for cid in company_ids:
            try:
                changes = await planner.recalculate_gaps(cid)
                total_changes += changes
                logger.info(
                    "Recalculated gaps for company %d: %d changes",
                    cid, changes,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to recalculate gaps for company %d: %s",
                    cid, exc,
                )

        logger.info(
            "Skill gap recalculation complete: %d total changes "
            "across %d companies",
            total_changes, len(company_ids),
        )

        return {
            "status": "completed",
            "companies_processed": len(company_ids),
            "total_changes": total_changes,
        }

    except SoftTimeLimitExceeded:
        logger.error("Skill gap recalculation timed out")
        return {"status": "failed", "reason": "timeout"}

    except (ConnectionError, OSError) as exc:
        try:
            task.retry(
                exc=exc,
                countdown=_retry_countdown(task.request.retries),
            )
        except task.MaxRetriesExceededError:
            logger.error(
                "Skill gap recalculation failed after retries: %s", exc
            )
            return {"status": "failed", "reason": str(exc)}


# ---------------------------------------------------------------------------
# Task: abandon_stale_sessions (periodic)
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="alcoabase.tasks.training_tasks.abandon_stale_sessions",
    soft_time_limit=120,
    max_retries=1,
    queue="ai_operations",
)
def abandon_stale_sessions(self) -> dict[str, Any]:
    """Mark virtual audit sessions inactive for 60+ minutes as abandoned.

    Finds all in-progress sessions that haven't received a response in
    60 minutes, marks them as abandoned, and computes scores on completed
    turns.

    Returns:
        Dict with count of abandoned sessions.
    """
    return _run_async(_abandon_stale_sessions_async())


async def _abandon_stale_sessions_async() -> dict[str, Any]:
    """Async implementation of abandon_stale_sessions."""
    from datetime import timedelta

    from alcoabase.models.training_ecosystem import (
        SessionStatus,
        VirtualAuditSession,
    )
    from alcoabase.services.roleplay_engine import (
        compute_session_score,
        determine_pass_fail,
    )
    from sqlalchemy import select

    session_factory = _get_session_factory()
    cutoff = datetime.now(UTC) - timedelta(minutes=60)
    abandoned_count = 0

    async with session_factory() as session:
        # Find stale in-progress sessions
        result = await session.execute(
            select(VirtualAuditSession).where(
                VirtualAuditSession.status == SessionStatus.IN_PROGRESS,
                VirtualAuditSession.started_at < cutoff,
            )
        )
        stale_sessions = list(result.scalars().all())

        for audit_session in stale_sessions:
            # Check if last activity was > 60 minutes ago
            session_data = audit_session.session_data or {"turns": []}
            turns = session_data.get("turns", [])

            # Compute score on completed turns
            overall_score = compute_session_score(turns)
            passed = determine_pass_fail(
                overall_score, audit_session.turns_completed
            )

            audit_session.status = SessionStatus.ABANDONED
            audit_session.overall_score = overall_score
            audit_session.passed = passed
            audit_session.completed_at = datetime.now(UTC)
            audit_session.summary_data = {
                "overall_score": overall_score,
                "passed": passed,
                "turns_completed": audit_session.turns_completed,
                "total_turns": audit_session.total_turns,
                "reason": "abandoned_timeout",
            }
            abandoned_count += 1

        await session.commit()

    if abandoned_count > 0:
        logger.info("Abandoned %d stale roleplay sessions", abandoned_count)

    return {
        "status": "completed",
        "abandoned_count": abandoned_count,
    }


# ---------------------------------------------------------------------------
# Legacy task: generate_training_content (backward compatibility)
# ---------------------------------------------------------------------------

# Module-level service instance (reused across task invocations)
_training_content_generator = None


def _get_training_content_generator():
    """Get or create the TrainingContentGenerator singleton for task workers."""
    global _training_content_generator
    if _training_content_generator is None:
        from alcoabase.services.training_content_generator import (
            TrainingContentGenerator,
        )

        _training_content_generator = TrainingContentGenerator()
    return _training_content_generator


@shared_task(
    bind=True,
    name="alcoabase.tasks.generate_training_content",
    autoretry_for=(ConnectionError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def generate_training_content_task(
    self: Any,
    sop_document_uuid: str,
    sop_version: str,
    sop_text: str,
    previous_version_text: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Asynchronously generate training content for an SOP version.

    Legacy task maintained for backward compatibility. Triggered when
    an SOP enters InTraining status.

    Args:
        self: Celery task instance (bound).
        sop_document_uuid: Document-UUID of the SOP.
        sop_version: Version string of the SOP.
        sop_text: Full text content of the current SOP version.
        previous_version_text: Optional text of the previous version.
        user_id: ID of the user who triggered the generation.

    Returns:
        Dict with generation results (content_id, status, quiz_count).
    """
    generator = _get_training_content_generator()

    logger.info(
        "Starting training content generation for SOP %s v%s",
        sop_document_uuid,
        sop_version,
    )

    loop = asyncio.new_event_loop()
    try:
        content = loop.run_until_complete(
            generator.generate_training_content(
                sop_document_uuid=sop_document_uuid,
                sop_version=sop_version,
                sop_text=sop_text,
                previous_version_text=previous_version_text,
                user_id=user_id,
            )
        )
    finally:
        loop.close()

    logger.info(
        "Successfully generated training content %s for SOP %s v%s "
        "(%d quiz questions, %d procedural steps)",
        content.content_id,
        sop_document_uuid,
        sop_version,
        len(content.quiz_questions),
        len(content.procedural_steps),
    )

    return {
        "content_id": content.content_id,
        "sop_document_uuid": sop_document_uuid,
        "sop_version": sop_version,
        "status": content.status.value,
        "quiz_question_count": len(content.quiz_questions),
        "procedural_step_count": len(content.procedural_steps),
        "safety_point_count": len(content.safety_points),
    }
