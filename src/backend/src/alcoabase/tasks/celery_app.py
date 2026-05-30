"""Celery application configuration for AlcoaBase background tasks.

Configures the Celery app with Redis as broker and result backend,
including task routing, retry policies, and periodic beat schedules.

References:
    - Task 12.6: Celery task for async document indexing
    - Requirement 8.1: Anomaly detection periodic task (every 15 minutes)
"""

from celery import Celery
from celery.schedules import crontab

from alcoabase.config import get_settings

settings = get_settings()

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
}

# Auto-discover tasks in the tasks package
celery_app.autodiscover_tasks(["alcoabase.tasks"])
