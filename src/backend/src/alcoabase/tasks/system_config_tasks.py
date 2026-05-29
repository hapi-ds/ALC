"""Celery tasks for system configuration: health checks, backups, and metrics.

Implements periodic background tasks for:
- Health monitoring of all infrastructure services
- Database backup execution (pg_dump → compress → upload to MinIO)
- Expired backup cleanup with retention policy enforcement
- Resource utilization metrics collection from Docker containers

All tasks run in Celery workers and store results in PostgreSQL.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 7.3, 8.2, 8.3, 9.1, 9.2, 9.3, 9.5, 10.1, 10.2, 10.7, 13.1, 13.2
"""

import asyncio
import gzip
import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import aioboto3
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.config import get_settings
from alcoabase.models.system_config import (
    BackupRecord,
    ResourceMetricPoint,
    SystemConfiguration,
)

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Async session helper for Celery tasks
# ---------------------------------------------------------------------------


def _get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create an async session factory for use within Celery tasks.

    Celery tasks run outside the FastAPI lifecycle, so they need their own
    engine and session factory.

    Returns:
        async_sessionmaker bound to a fresh async engine.
    """
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _run_async(coro):
    """Run an async coroutine in a new event loop.

    Celery workers are synchronous, so we need to create a new event loop
    for each task invocation to run async code.

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
# Health Check Task
# ---------------------------------------------------------------------------


@shared_task(
    name="alcoabase.tasks.system_config_tasks.run_health_checks",
    acks_late=True,
    ignore_result=True,
)
def run_health_checks() -> dict:
    """Periodic task: check all services, store results, detect transitions.

    Instantiates HealthMonitor with current configuration from the database,
    runs check_all_services, and stores results. Runs at a configurable
    interval (default 30s).

    Returns:
        Dictionary with check results summary.
    """
    return _run_async(_run_health_checks_async())


async def _run_health_checks_async() -> dict:
    """Async implementation of the health check task."""
    from alcoabase.services.health_monitor import HealthMonitor

    session_factory = _get_async_session_factory()

    async with session_factory() as session:
        try:
            # Load health check configuration from DB
            config = await _get_health_check_config(session)
            degraded_threshold_ms = config.get("degraded_threshold_seconds", 5) * 1000
            timeout_ms = config.get("unreachable_timeout_seconds", 10) * 1000

            monitor = HealthMonitor(
                degraded_threshold_ms=degraded_threshold_ms,
                timeout_ms=timeout_ms,
            )

            results = await monitor.check_all_services(session)
            await session.commit()

            summary = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "services_checked": len(results),
                "results": [
                    {
                        "service": r.service_name,
                        "status": r.status,
                        "response_time_ms": r.response_time_ms,
                        "is_transition": r.is_transition,
                    }
                    for r in results
                ],
            }

            logger.info(
                "Health checks completed: %d services checked",
                len(results),
            )
            return summary

        except Exception as exc:
            await session.rollback()
            logger.error("Health check task failed: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Backup Task
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="alcoabase.tasks.system_config_tasks.run_backup",
    acks_late=True,
    time_limit=3600,  # 1 hour hard limit
    soft_time_limit=3300,  # 55 min soft limit
)
def run_backup(self, user_id: int | None = None, backup_type: str = "manual") -> dict:
    """Execute pg_dump, compress, upload to MinIO, update BackupRecord.

    Updates the BackupRecord status through its lifecycle:
    queued → running → completed/failed.

    Args:
        user_id: ID of the user who triggered the backup (None for scheduled).
        backup_type: Type of backup ("manual" or "scheduled").

    Returns:
        Dictionary with backup result metadata.
    """
    return _run_async(_run_backup_async(self.request.id, user_id, backup_type))


async def _run_backup_async(
    task_id: str, user_id: int | None, backup_type: str
) -> dict:
    """Async implementation of the backup task."""
    settings = get_settings()
    session_factory = _get_async_session_factory()
    start_time = time.monotonic()

    async with session_factory() as session:
        # Find or create the BackupRecord
        result = await session.execute(
            select(BackupRecord).where(BackupRecord.task_id == task_id)
        )
        record = result.scalars().first()

        if record is None:
            # For scheduled backups, create the record
            record = BackupRecord(
                task_id=task_id,
                backup_type=backup_type,
                status="queued",
                triggered_by=user_id,
            )
            session.add(record)
            await session.flush()

        # Update status to running
        record.status = "running"
        record.started_at = datetime.now(timezone.utc)
        await session.commit()

    # Execute pg_dump outside the session context
    try:
        compressed_path, file_size = await _execute_pg_dump(settings)
        storage_path = await _upload_to_minio(compressed_path, task_id, settings)
        duration = time.monotonic() - start_time

        # Update record with success
        async with session_factory() as session:
            result = await session.execute(
                select(BackupRecord).where(BackupRecord.task_id == task_id)
            )
            record = result.scalars().first()
            if record:
                record.status = "completed"
                record.completed_at = datetime.now(timezone.utc)
                record.file_size_bytes = file_size
                record.storage_path = storage_path
                record.duration_seconds = round(duration, 2)
                await session.commit()

        logger.info(
            "Backup completed: task_id=%s, size=%d bytes, duration=%.2fs",
            task_id,
            file_size,
            duration,
        )

        return {
            "task_id": task_id,
            "status": "completed",
            "file_size_bytes": file_size,
            "storage_path": storage_path,
            "duration_seconds": round(duration, 2),
        }

    except Exception as exc:
        duration = time.monotonic() - start_time
        error_message = str(exc)

        # Update record with failure
        async with session_factory() as session:
            result = await session.execute(
                select(BackupRecord).where(BackupRecord.task_id == task_id)
            )
            record = result.scalars().first()
            if record:
                record.status = "failed"
                record.completed_at = datetime.now(timezone.utc)
                record.duration_seconds = round(duration, 2)
                record.error_message = error_message[:500]
                await session.commit()

        logger.error("Backup failed: task_id=%s, error=%s", task_id, error_message)

        return {
            "task_id": task_id,
            "status": "failed",
            "error_message": error_message,
            "duration_seconds": round(duration, 2),
        }

    finally:
        # Clean up temp file if it exists
        if "compressed_path" in locals() and os.path.exists(compressed_path):
            os.unlink(compressed_path)


async def _execute_pg_dump(settings) -> tuple[str, int]:
    """Execute pg_dump and compress the output.

    Parses the database URL to extract connection parameters, runs pg_dump
    as a subprocess, and compresses the output with gzip.

    Args:
        settings: Application settings with database_url.

    Returns:
        Tuple of (compressed_file_path, file_size_bytes).

    Raises:
        RuntimeError: If pg_dump fails.
    """
    # Parse the async database URL to get connection params
    # Format: postgresql+asyncpg://user:pass@host:port/dbname
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(db_url)

    pg_host = parsed.hostname or "localhost"
    pg_port = str(parsed.port or 5432)
    pg_user = parsed.username or "alcoabase"
    pg_password = parsed.password or ""
    pg_dbname = parsed.path.lstrip("/") or "alcoabase"

    # Create temp file for the dump
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    temp_dir = tempfile.gettempdir()
    dump_path = os.path.join(temp_dir, f"alcoabase_backup_{timestamp}.sql")
    compressed_path = f"{dump_path}.gz"

    # Set PGPASSWORD environment variable for pg_dump
    env = os.environ.copy()
    env["PGPASSWORD"] = pg_password

    # Run pg_dump
    cmd = [
        "pg_dump",
        "-h", pg_host,
        "-p", pg_port,
        "-U", pg_user,
        "-d", pg_dbname,
        "--format=custom",
        "--compress=0",
        "-f", dump_path,
    ]

    logger.info("Executing pg_dump for database '%s'", pg_dbname)

    proc = subprocess.run(
        cmd,
        env=env,
        capture_output=True,
        text=True,
        timeout=3000,  # 50 min timeout for large databases
    )

    if proc.returncode != 0:
        error_msg = proc.stderr.strip() if proc.stderr else "pg_dump failed with no error output"
        raise RuntimeError(f"pg_dump failed (exit code {proc.returncode}): {error_msg}")

    # Compress the dump file
    try:
        with open(dump_path, "rb") as f_in:
            with gzip.open(compressed_path, "wb", compresslevel=6) as f_out:
                while chunk := f_in.read(8192):
                    f_out.write(chunk)
    finally:
        # Remove uncompressed dump
        if os.path.exists(dump_path):
            os.unlink(dump_path)

    file_size = os.path.getsize(compressed_path)
    return compressed_path, file_size


async def _upload_to_minio(
    file_path: str, task_id: str, settings
) -> str:
    """Upload a compressed backup file to MinIO.

    Uploads to the `backups/` prefix in the configured MinIO bucket.

    Args:
        file_path: Path to the compressed backup file.
        task_id: Celery task ID (used in the object key).
        settings: Application settings with MinIO configuration.

    Returns:
        The MinIO object key (storage_path).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    storage_path = f"backups/{timestamp}_{task_id}.sql.gz"

    protocol = "https" if settings.minio_use_ssl else "http"
    endpoint_url = f"{protocol}://{settings.minio_endpoint}"

    minio_session = aioboto3.Session()
    async with minio_session.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        use_ssl=settings.minio_use_ssl,
    ) as client:
        with open(file_path, "rb") as f:
            await client.upload_fileobj(
                f,
                settings.minio_bucket,
                storage_path,
            )

    logger.info("Backup uploaded to MinIO: %s", storage_path)
    return storage_path


# ---------------------------------------------------------------------------
# Cleanup Expired Backups Task
# ---------------------------------------------------------------------------


@shared_task(
    name="alcoabase.tasks.system_config_tasks.cleanup_expired_backups",
    acks_late=True,
    ignore_result=True,
)
def cleanup_expired_backups() -> dict:
    """Delete backups older than retention period, keeping at least one.

    Loads retention configuration from the database, queries expired backups,
    deletes them from MinIO and removes the database records. Always retains
    at least one backup regardless of age.

    Runs daily at 03:00 UTC via Celery beat.

    Returns:
        Dictionary with cleanup results.
    """
    return _run_async(_cleanup_expired_backups_async())


async def _cleanup_expired_backups_async() -> dict:
    """Async implementation of the cleanup task."""
    from alcoabase.services.backup_service import BackupService

    session_factory = _get_async_session_factory()
    backup_service = BackupService()

    async with session_factory() as session:
        try:
            deleted_count = await backup_service.cleanup_expired_backups(session)
            await session.commit()

            logger.info("Backup cleanup completed: %d backups deleted", deleted_count)
            return {
                "status": "completed",
                "deleted_count": deleted_count,
                "cleaned_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            await session.rollback()
            logger.error("Backup cleanup failed: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Resource Metrics Collection Task
# ---------------------------------------------------------------------------


@shared_task(
    name="alcoabase.tasks.system_config_tasks.collect_resource_metrics",
    acks_late=True,
    ignore_result=True,
)
def collect_resource_metrics() -> dict:
    """Collect CPU/memory stats from Docker for all containers.

    Instantiates ServiceRegistry, collects stats for all running containers,
    and stores ResourceMetricPoint records in the database. Runs at the
    health check interval (default 30s).

    Returns:
        Dictionary with collection results.
    """
    return _run_async(_collect_resource_metrics_async())


async def _collect_resource_metrics_async() -> dict:
    """Async implementation of the resource metrics collection task."""
    from alcoabase.services.service_registry import ServiceRegistry

    session_factory = _get_async_session_factory()
    registry = ServiceRegistry()

    try:
        metrics = await registry.get_resource_utilization()
    except Exception as exc:
        logger.error("Failed to collect resource metrics from Docker: %s", exc)
        return {
            "status": "failed",
            "error": str(exc),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    if not metrics:
        logger.info("No resource metrics collected (no running containers)")
        return {
            "status": "completed",
            "metrics_count": 0,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    async with session_factory() as session:
        try:
            now = datetime.now(timezone.utc)
            for metric in metrics:
                point = ResourceMetricPoint(
                    service_name=metric.service_name,
                    cpu_percent=metric.cpu_percent,
                    memory_used_mb=metric.memory_used_mb,
                    memory_limit_mb=metric.memory_limit_mb,
                    recorded_at=now,
                )
                session.add(point)

            await session.commit()

            logger.info(
                "Resource metrics collected: %d data points", len(metrics)
            )
            return {
                "status": "completed",
                "metrics_count": len(metrics),
                "collected_at": now.isoformat(),
            }

        except Exception as exc:
            await session.rollback()
            logger.error("Failed to store resource metrics: %s", exc)
            raise


# ---------------------------------------------------------------------------
# Helper: Load health check config from DB
# ---------------------------------------------------------------------------


async def _get_health_check_config(session: AsyncSession) -> dict:
    """Load health check configuration from the database.

    Falls back to defaults if no configuration is stored.

    Args:
        session: Active async database session.

    Returns:
        Dictionary with health check configuration values.
    """
    result = await session.execute(
        select(SystemConfiguration).where(
            SystemConfiguration.category == "health_check"
        )
    )
    config = result.scalars().first()

    defaults = {
        "polling_interval_seconds": 30,
        "degraded_threshold_seconds": 5,
        "unreachable_timeout_seconds": 10,
    }

    if config and config.config_values:
        defaults.update(config.config_values)

    return defaults


# ---------------------------------------------------------------------------
# Dynamic Schedule Update
# ---------------------------------------------------------------------------


def get_dynamic_health_check_interval() -> float:
    """Read polling_interval from DB config for dynamic beat schedule updates.

    Called on each beat cycle to allow runtime configuration changes to
    take effect without restarting the beat scheduler.

    Returns:
        Polling interval in seconds (default 30.0).
    """
    try:
        settings = get_settings()
        engine = create_async_engine(settings.database_url, pool_size=1)
        factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

        async def _fetch():
            async with factory() as session:
                result = await session.execute(
                    select(SystemConfiguration).where(
                        SystemConfiguration.category == "health_check"
                    )
                )
                config = result.scalars().first()
                if config and config.config_values:
                    return float(config.config_values.get("polling_interval_seconds", 30))
                return 30.0

        loop = asyncio.new_event_loop()
        try:
            interval = loop.run_until_complete(_fetch())
        finally:
            loop.close()
            # Dispose the temporary engine
            asyncio.new_event_loop().run_until_complete(engine.dispose())

        return interval
    except Exception:
        logger.warning("Failed to read dynamic health check interval, using default 30s")
        return 30.0


# ---------------------------------------------------------------------------
# Register tasks in Celery Beat Schedule
# ---------------------------------------------------------------------------


def register_system_config_beat_schedule() -> None:
    """Register all system configuration tasks in the Celery beat schedule.

    Adds health checks, resource metrics collection, and backup cleanup
    to the beat schedule with appropriate intervals. The backup schedule
    itself is dynamically registered from DB config via BackupService.
    """
    from celery.schedules import crontab

    from alcoabase.tasks.celery_app import celery_app

    # Health checks — default 30s, dynamically updated from DB config
    celery_app.conf.beat_schedule["run-health-checks"] = {
        "task": "alcoabase.tasks.system_config_tasks.run_health_checks",
        "schedule": 30.0,
        "options": {"queue": "default"},
    }

    # Resource metrics collection — matches health check interval
    celery_app.conf.beat_schedule["collect-resource-metrics"] = {
        "task": "alcoabase.tasks.system_config_tasks.collect_resource_metrics",
        "schedule": 30.0,
        "options": {"queue": "default"},
    }

    # Cleanup expired backups — daily at 03:00 UTC
    celery_app.conf.beat_schedule["cleanup-expired-backups-daily"] = {
        "task": "alcoabase.tasks.system_config_tasks.cleanup_expired_backups",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "default"},
    }


# Register the beat schedule when this module is imported by Celery autodiscover
register_system_config_beat_schedule()
