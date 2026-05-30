"""Celery task for asynchronous audit trail PDF export.

Handles large PDF exports (>10,000 events) by running in the background.
Fetches all matching events, generates a PDF via AuditPDFExporter,
uploads to MinIO with a 72-hour presigned URL, and logs the export
via AuditAccessLogger.

References:
    - Design doc: Celery Task (tasks/audit_export_tasks.py)
    - Requirements 7.5, 7.9, 7.10: Async export, error handling, 72-hour retention
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from alcoabase.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# PDF expiry in seconds (72 hours)
_PDF_EXPIRY_SECONDS = 72 * 60 * 60


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


def _get_storage_client_kwargs() -> dict[str, Any]:
    """Get connection kwargs for creating an aioboto3 S3 client.

    Returns:
        Dictionary of connection parameters for aioboto3 client.
    """
    from alcoabase.config import get_settings

    settings = get_settings()
    protocol = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{protocol}://{settings.minio_endpoint}"

    return {
        "service_name": "s3",
        "endpoint_url": endpoint_url,
        "aws_access_key_id": settings.minio_access_key,
        "aws_secret_access_key": settings.minio_secret_key,
        "use_ssl": settings.minio_use_ssl,
    }


def _get_bucket_name() -> str:
    """Get the configured MinIO bucket name.

    Returns:
        The bucket name from settings.
    """
    from alcoabase.config import get_settings

    return get_settings().minio_bucket


@celery_app.task(
    bind=True,
    soft_time_limit=300,
    max_retries=0,
    queue="default",
    name="alcoabase.tasks.audit_export_tasks.export_audit_pdf_task",
)
def export_audit_pdf_task(
    self: Task,
    job_id: str,
    company_id: int,
    filters: dict | None,
    search_query: str | None,
    requesting_user_id: int,
) -> dict[str, Any]:
    """Generate PDF export asynchronously for large datasets.

    Pipeline:
    1. Create async DB session
    2. Fetch all matching events (iterate through all pages)
    3. Resolve company name and requesting user name for metadata
    4. Generate PDF via AuditPDFExporter.generate_pdf
    5. Upload PDF to MinIO under exports/audit-trail/{job_id}.pdf
    6. Generate presigned URL with 72-hour expiry
    7. Log export event via AuditAccessLogger

    Args:
        self: Celery task instance (bound).
        job_id: UUID of the export job.
        company_id: Company ID for tenant scoping.
        filters: Serialized filter criteria (dict or None).
        search_query: Optional search query string.
        requesting_user_id: ID of the user who requested the export.

    Returns:
        Dict with status and download_url on success, or status and
        error_message on failure.
    """
    try:
        result = asyncio.run(
            _export_audit_pdf_async(
                job_id=job_id,
                company_id=company_id,
                filters=filters,
                search_query=search_query,
                requesting_user_id=requesting_user_id,
            )
        )
        return result

    except SoftTimeLimitExceeded:
        logger.error(
            "export_audit_pdf_task timed out for job_id=%s", job_id
        )
        # Ensure no partial PDF is stored
        asyncio.run(_cleanup_partial_pdf(job_id))
        return {
            "status": "failed",
            "error_message": "Export timed out after 300 seconds",
        }

    except Exception as exc:
        logger.exception(
            "export_audit_pdf_task failed for job_id=%s: %s", job_id, exc
        )
        # Ensure no partial PDF is stored
        asyncio.run(_cleanup_partial_pdf(job_id))
        return {
            "status": "failed",
            "error_message": str(exc),
        }


async def _export_audit_pdf_async(
    job_id: str,
    company_id: int,
    filters: dict | None,
    search_query: str | None,
    requesting_user_id: int,
) -> dict[str, Any]:
    """Async implementation of the PDF export pipeline.

    Args:
        job_id: UUID of the export job.
        company_id: Company ID for tenant scoping.
        filters: Serialized filter criteria (dict or None).
        search_query: Optional search query string.
        requesting_user_id: ID of the user who requested the export.

    Returns:
        Dict with status="completed" and download_url on success.
    """
    import aioboto3
    from sqlalchemy import select

    from alcoabase.models.company import Company
    from alcoabase.models.user import User
    from alcoabase.schemas.audit_trail import (
        AuditEvent,
        AuditTrailFilters,
        ExportMetadata,
    )
    from alcoabase.services.audit_access_logger import AuditAccessLogger
    from alcoabase.services.audit_pdf_exporter import AuditPDFExporter
    from alcoabase.services.audit_trail_service import AuditTrailService

    session_factory = _get_async_session_factory()
    audit_service = AuditTrailService()
    pdf_exporter = AuditPDFExporter()
    access_logger = AuditAccessLogger()

    # Deserialize filters
    effective_filters = AuditTrailFilters(**(filters or {}))

    async with session_factory() as session:
        # 1. Fetch all matching events (iterate through all pages)
        all_events: list[AuditEvent] = []
        cursor: str | None = None

        while True:
            page = await audit_service.list_events(
                session=session,
                company_id=company_id,
                filters=effective_filters,
                search_query=search_query,
                cursor=cursor,
                page_size=200,
            )
            all_events.extend(page.events)
            cursor = page.next_cursor
            if cursor is None:
                break

        total_event_count = len(all_events)

        if total_event_count == 0:
            return {
                "status": "failed",
                "error_message": "No events match the current filters",
            }

        # 2. Resolve company name
        company_result = await session.execute(
            select(Company).where(Company.id == company_id)
        )
        company = company_result.scalar_one_or_none()
        company_name = company.display_name if company else f"Company {company_id}"

        # 3. Resolve requesting user name
        user_result = await session.execute(
            select(User).where(User.id == requesting_user_id)
        )
        user = user_result.scalar_one_or_none()
        requesting_user_name = (
            user.full_name if user else f"User {requesting_user_id}"
        )

        # 4. Build metadata and generate PDF
        export_metadata = ExportMetadata(
            company_name=company_name,
            export_timestamp=datetime.now(timezone.utc),
            filters_applied=effective_filters,
            total_event_count=total_event_count,
            requesting_user_name=requesting_user_name,
        )

        pdf_bytes = pdf_exporter.generate_pdf(all_events, export_metadata)

        # 5. Upload PDF to MinIO
        object_key = f"exports/audit-trail/{job_id}.pdf"
        bucket = _get_bucket_name()
        client_kwargs = _get_storage_client_kwargs()

        session_boto = aioboto3.Session()
        async with session_boto.client(**client_kwargs) as s3_client:
            # Ensure bucket exists
            try:
                await s3_client.head_bucket(Bucket=bucket)
            except Exception:
                await s3_client.create_bucket(Bucket=bucket)

            # Upload PDF
            await s3_client.put_object(
                Bucket=bucket,
                Key=object_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )

            # 6. Generate presigned URL with 72-hour expiry
            presigned_url = await s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": object_key},
                ExpiresIn=_PDF_EXPIRY_SECONDS,
            )

        # 7. Log export event via AuditAccessLogger
        filters_dict = effective_filters.model_dump(
            mode="json", exclude_none=True
        )
        await access_logger.log_access(
            session=session,
            user_id=requesting_user_id,
            company_id=company_id,
            action="export",
            filters_applied=filters_dict if filters_dict else None,
            event_count=total_event_count,
        )

    logger.info(
        "PDF export completed: job_id=%s, company_id=%d, events=%d",
        job_id,
        company_id,
        total_event_count,
    )

    return {
        "status": "completed",
        "download_url": presigned_url,
    }


async def _cleanup_partial_pdf(job_id: str) -> None:
    """Remove any partially uploaded PDF from MinIO.

    Called on error or timeout to ensure no partial/corrupted PDF
    is left in storage.

    Args:
        job_id: The export job ID used as the object key.
    """
    import aioboto3

    object_key = f"exports/audit-trail/{job_id}.pdf"
    bucket = _get_bucket_name()
    client_kwargs = _get_storage_client_kwargs()

    try:
        session_boto = aioboto3.Session()
        async with session_boto.client(**client_kwargs) as s3_client:
            await s3_client.delete_object(Bucket=bucket, Key=object_key)
    except Exception:
        # Best-effort cleanup — don't fail the error handler
        logger.warning(
            "Failed to clean up partial PDF for job_id=%s", job_id
        )
