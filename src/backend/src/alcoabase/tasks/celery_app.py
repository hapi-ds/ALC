"""Celery application configuration for AlcoaBase background tasks.

Configures the Celery app with Redis as broker and result backend,
including task routing and retry policies.

References:
    - Task 12.6: Celery task for async document indexing
"""

from celery import Celery

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

# Auto-discover tasks in the tasks package
celery_app.autodiscover_tasks(["alcoabase.tasks"])
