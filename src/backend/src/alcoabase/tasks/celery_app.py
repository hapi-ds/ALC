"""Celery application configuration for AlcoaBase background tasks.

Configures the Celery app with Redis as broker and result backend,
including task routing, retry policies, and periodic beat schedules.

References:
    - Task 12.6: Celery task for async document indexing
    - Requirement 8.1: Anomaly detection periodic task (every 15 minutes)
    - Requirements 13.1–13.6: Retention cleanup periodic task
"""

from celery import Celery
from celery.schedules import crontab

from alcoabase.config import get_settings

settings = get_settings()


def _parse_cron_expression(cron_expr: str) -> crontab:
    """Parse a standard 5-field cron expression into a Celery crontab.

    Supports the format: minute hour day_of_month month_of_year day_of_week.

    Args:
        cron_expr: Standard cron expression (e.g., "0 2 * * *").

    Returns:
        Celery crontab schedule object.
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        # Fall back to default: daily at 02:00 UTC
        return crontab(minute="0", hour="2")
    return crontab(
        minute=parts[0],
        hour=parts[1],
        day_of_month=parts[2],
        month_of_year=parts[3],
        day_of_week=parts[4],
    )

celery_app = Celery(
    "alcoabase",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ---------------------------------------------------------------------------
# Celery Beat Schedule — Periodic Tasks
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    "scan-anomalies-every-15-minutes": {
        "task": "alcoabase.tasks.review_tasks.scan_anomalies_periodic",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "default"},
    },
    "recalculate-skill-gaps-every-6-hours": {
        "task": "alcoabase.tasks.training_tasks.recalculate_skill_gaps",
        "schedule": crontab(minute=0, hour="*/6"),
        "kwargs": {"company_id": None},
        "options": {"queue": "ai_operations"},
    },
    "abandon-stale-roleplay-sessions": {
        "task": "alcoabase.tasks.training_tasks.abandon_stale_sessions",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "ai_operations"},
    },
    "expire-stale-hitl-checkpoints": {
        "task": "alcoabase.tasks.risk_framework_tasks.expire_stale_checkpoints",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "default"},
    },
    "literature-retention-cleanup": {
        "task": "alcoabase.tasks.literature_ingestion_tasks.retention_cleanup_task",
        "schedule": _parse_cron_expression(settings.ingestion_cleanup_cron),
        "options": {"queue": "literature_ingestion"},
    },
}

# Auto-discover tasks in the tasks package
celery_app.autodiscover_tasks(["alcoabase.tasks"])
