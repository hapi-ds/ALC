"""Celery tasks for the AI Risk & Compliance Framework.

Implements periodic background tasks for the risk framework:
- expire_stale_checkpoints: Marks pending HITL checkpoints as expired
  when their 72-hour validity window elapses.

These tasks run in Celery workers and use synchronous DB access via
asyncio.run() since Celery workers are synchronous.

References:
    - Requirements: 2.7, 4.10, 5.6
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
"""

from __future__ import annotations

import asyncio
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: Async session factory (same pattern as review_tasks.py)
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


# ---------------------------------------------------------------------------
# Task: expire_stale_checkpoints
# ---------------------------------------------------------------------------


@celery_app.task
def expire_stale_checkpoints() -> dict[str, Any]:
    """Expire all pending HITL checkpoints whose validity window has elapsed.

    Runs every 15 minutes via Celery beat. Finds all checkpoints where
    status='pending' AND expires_at < now, marks them as 'expired', and
    creates alert entries for the compliance dashboard.

    This task is idempotent — running it multiple times on the same
    checkpoint has no additional effect because the UPDATE WHERE clause
    only targets status='pending' rows.

    Returns:
        Dict with expired_count indicating how many checkpoints were expired.

    References:
        - Requirement 2.7: 72-hour validity window expiry
        - Requirement 4.10: Escalation for unreviewed checkpoints
        - Requirement 5.6: Expired checkpoint handling and dashboard alerts
    """
    result = asyncio.run(_expire_stale_checkpoints_async())
    return result


async def _expire_stale_checkpoints_async() -> dict[str, Any]:
    """Async implementation of the checkpoint expiry task.

    Calls HITLCheckpointService.expire_stale_checkpoints to perform the
    idempotent bulk update, then logs the result.

    Returns:
        Dict with expired_count and status.
    """
    from alcoabase.services.hitl_checkpoint_service import HITLCheckpointService

    session_factory = _get_async_session_factory()
    service = HITLCheckpointService()

    async with session_factory() as session:
        expired_count = await service.expire_stale_checkpoints(session)
        await session.commit()

    if expired_count > 0:
        logger.info(
            "expire_stale_checkpoints: marked %d checkpoint(s) as expired.",
            expired_count,
        )
    else:
        logger.debug("expire_stale_checkpoints: no stale checkpoints found.")

    return {
        "status": "completed",
        "expired_count": expired_count,
    }
