"""Backup service for managing PostgreSQL database backups.

Handles backup triggering, scheduling, retention policies, and cleanup.
Backups are executed as Celery tasks, stored in MinIO, and tracked via
BackupRecord entries in PostgreSQL.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements 7.1–7.5: Backup schedule configuration
    - Requirements 8.1–8.5: Backup retention policy
    - Requirements 9.1–9.6: Manual trigger and history
"""

import uuid
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.models.system_config import BackupRecord, SystemConfiguration

# ---------------------------------------------------------------------------
# Cron field definitions: (name, min_value, max_value)
# ---------------------------------------------------------------------------

_CRON_FIELDS: list[tuple[str, int, int]] = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day-of-month", 1, 31),
    ("month", 1, 12),
    ("day-of-week", 0, 7),  # 0 and 7 both represent Sunday
]

class BackupService:
    """Manages database backups via pg_dump, uploads to MinIO, and handles retention.

    Provides methods for triggering manual backups, managing backup schedules
    via cron expressions, configuring retention policies, and cleaning up
    expired backups while retaining at least one.

    Attributes:
        _settings: Application settings instance.
    """

    def __init__(self) -> None:
        """Initialize the backup service with application settings."""
        self._settings = get_settings()

    async def trigger_backup(
        self, user_id: int, reason: str, session: AsyncSession
    ) -> BackupRecord:
        """Trigger a manual database backup.

        Checks if a backup is already running, creates a BackupRecord with
        status="queued", dispatches a Celery task, and returns the record.

        Args:
            user_id: ID of the user triggering the backup.
            reason: Audit reason for the backup (X-Change-Reason).
            session: Active database session.

        Returns:
            The created BackupRecord with status "queued".

        Raises:
            BackupAlreadyRunningError: If a backup is already queued or running.
        """
        if await self.is_backup_running(session):
            raise BackupAlreadyRunningError(
                "A backup is already in progress. Cannot trigger concurrent backups."
            )

        task_id = str(uuid.uuid4())
        record = BackupRecord(
            task_id=task_id,
            backup_type="manual",
            status="queued",
            triggered_by=user_id,
        )
        session.add(record)
        await session.flush()

        # Dispatch Celery task (import here to avoid circular imports)
        from alcoabase.tasks.celery_app import celery_app

        celery_app.send_task(
            "alcoabase.tasks.system_config_tasks.run_backup",
            kwargs={"user_id": user_id, "backup_type": "manual"},
            task_id=task_id,
        )

        return record

    async def is_backup_running(self, session: AsyncSession) -> bool:
        """Check if a backup is currently queued or running.

        Args:
            session: Active database session.

        Returns:
            True if a backup with status "queued" or "running" exists.
        """
        result = await session.execute(
            select(BackupRecord).where(
                BackupRecord.status.in_(["queued", "running"])
            )
        )
        return result.scalars().first() is not None

    async def get_backup_history(self, session: AsyncSession) -> list[BackupRecord]:
        """Return all backup records ordered by creation time descending.

        Args:
            session: Active database session.

        Returns:
            List of BackupRecord instances, most recent first.
        """
        result = await session.execute(
            select(BackupRecord).order_by(BackupRecord.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_backup_status(
        self, task_id: str, session: AsyncSession
    ) -> BackupRecord | None:
        """Get the current status of a backup by its task ID.

        Args:
            task_id: The Celery task ID of the backup.
            session: Active database session.

        Returns:
            The BackupRecord if found, None otherwise.
        """
        result = await session.execute(
            select(BackupRecord).where(BackupRecord.task_id == task_id)
        )
        return result.scalars().first()

    @staticmethod
    def validate_cron_expression(expression: str) -> bool:
        """Validate a 5-field cron expression.

        Validates syntax and range for each field:
        - minute: 0-59
        - hour: 0-23
        - day-of-month: 1-31
        - month: 1-12
        - day-of-week: 0-7 (0 and 7 are Sunday)

        Supports wildcards (*), ranges (1-5), steps (*/2), and lists (1,3,5).

        Args:
            expression: The cron expression string to validate.

        Returns:
            True if the expression is a valid 5-field cron expression.
        """
        if not expression or not isinstance(expression, str):
            return False

        expression = expression.strip()
        fields = expression.split()

        if len(fields) != 5:
            return False

        for i, field in enumerate(fields):
            _, min_val, max_val = _CRON_FIELDS[i]
            if not _validate_cron_field(field, min_val, max_val):
                return False

        return True

    @staticmethod
    def cron_to_human_readable(expression: str) -> str:
        """Convert a cron expression to a human-readable description.

        Handles common patterns and provides a generic fallback for
        complex expressions.

        Args:
            expression: A valid 5-field cron expression.

        Returns:
            Human-readable description (e.g., "Daily at 02:00 UTC").
        """
        if not expression or not isinstance(expression, str):
            return "Invalid cron expression"

        expression = expression.strip()
        fields = expression.split()

        if len(fields) != 5:
            return "Invalid cron expression"

        minute, hour, dom, month, dow = fields

        # Every minute
        if all(f == "*" for f in fields):
            return "Every minute"

        # Every N minutes: */N * * * *
        if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
            interval = minute[2:]
            return f"Every {interval} minutes"

        # Hourly: 0 * * * * or N * * * *
        if minute.isdigit() and hour == "*" and dom == "*" and month == "*" and dow == "*":
            return f"Every hour at minute {minute}"

        # Daily: N N * * *
        if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow == "*":
            return f"Daily at {int(hour):02d}:{int(minute):02d} UTC"

        # Weekly: N N * * N
        if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow.isdigit():
            day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_idx = int(dow)
            if 0 <= day_idx <= 7:
                day_name = day_names[day_idx]
                return f"Weekly on {day_name} at {int(hour):02d}:{int(minute):02d} UTC"

        # Monthly: N N N * *
        if minute.isdigit() and hour.isdigit() and dom.isdigit() and month == "*" and dow == "*":
            return f"Monthly on day {dom} at {int(hour):02d}:{int(minute):02d} UTC"

        # Fallback: show the raw cron expression
        return f"Custom schedule ({expression})"

    async def update_schedule(
        self, cron_expr: str, session: AsyncSession
    ) -> None:
        """Update the backup schedule with a new cron expression.

        Validates the cron expression, updates the SystemConfiguration
        "backup_schedule" category, and registers with Celery beat.

        Args:
            cron_expr: A valid 5-field cron expression.
            session: Active database session.

        Raises:
            InvalidCronExpressionError: If the cron expression is invalid.
        """
        if not self.validate_cron_expression(cron_expr):
            raise InvalidCronExpressionError(
                f"Invalid cron expression: '{cron_expr}'. "
                "Expected 5-field format: minute hour day-of-month month day-of-week"
            )

        # Update SystemConfiguration
        result = await session.execute(
            select(SystemConfiguration).where(
                SystemConfiguration.category == "backup_schedule"
            )
        )
        config = result.scalars().first()

        schedule_data = {
            "cron_expression": cron_expr,
            "human_readable": self.cron_to_human_readable(cron_expr),
        }

        if config:
            config.config_values = schedule_data
        else:
            config = SystemConfiguration(
                category="backup_schedule",
                config_values=schedule_data,
            )
            session.add(config)

        await session.flush()

        # Register with Celery beat
        _register_backup_schedule_with_celery(cron_expr)

    async def update_retention(
        self, days: int, session: AsyncSession
    ) -> None:
        """Update the backup retention policy.

        Validates the retention period is within 1-365 days and updates
        the SystemConfiguration "backup_retention" category.

        Args:
            days: Retention period in days (1-365).
            session: Active database session.

        Raises:
            InvalidRetentionPeriodError: If days is outside 1-365 range.
        """
        if not isinstance(days, int) or days < 1 or days > 365:
            raise InvalidRetentionPeriodError(
                f"Retention period must be between 1 and 365 days, got {days}."
            )

        result = await session.execute(
            select(SystemConfiguration).where(
                SystemConfiguration.category == "backup_retention"
            )
        )
        config = result.scalars().first()

        retention_data = {"retention_days": days}

        if config:
            config.config_values = retention_data
        else:
            config = SystemConfiguration(
                category="backup_retention",
                config_values=retention_data,
            )
            session.add(config)

        await session.flush()

    async def cleanup_expired_backups(self, session: AsyncSession) -> int:
        """Delete backups older than the retention period.

        Queries backups older than the configured retention period, deletes
        them from MinIO and removes the BackupRecords. Always retains at
        least one backup regardless of age to prevent complete data loss.

        Args:
            session: Active database session.

        Returns:
            Number of backups deleted.
        """
        # Load retention config
        result = await session.execute(
            select(SystemConfiguration).where(
                SystemConfiguration.category == "backup_retention"
            )
        )
        config = result.scalars().first()
        retention_days = 30  # Default if not configured
        if config and config.config_values:
            retention_days = config.config_values.get("retention_days", 30)

        # Get all completed backups ordered by creation time (newest first)
        result = await session.execute(
            select(BackupRecord)
            .where(BackupRecord.status == "completed")
            .order_by(BackupRecord.created_at.desc())
        )
        all_backups = list(result.scalars().all())

        if len(all_backups) <= 1:
            # Retain at least one backup regardless of age
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        expired_backups = [
            b for b in all_backups
            if b.created_at is not None and b.created_at < cutoff
        ]

        # Ensure at least one backup is retained
        # If all backups are expired, keep the newest one
        if len(expired_backups) == len(all_backups):
            expired_backups = expired_backups[1:]  # Keep the first (newest)

        deleted_count = 0
        for backup in expired_backups:
            # Delete from MinIO if storage_path exists
            if backup.storage_path:
                await self._delete_from_minio(backup.storage_path)

            await session.delete(backup)
            deleted_count += 1

        await session.flush()
        return deleted_count

    async def _delete_from_minio(self, storage_path: str) -> None:
        """Delete a backup file from MinIO.

        Args:
            storage_path: The object key in MinIO to delete.
        """
        try:
            minio_session = aioboto3.Session()
            protocol = "https" if self._settings.minio_use_ssl else "http"
            endpoint_url = f"{protocol}://{self._settings.minio_endpoint}"

            async with minio_session.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=self._settings.minio_access_key,
                aws_secret_access_key=self._settings.minio_secret_key,
                use_ssl=self._settings.minio_use_ssl,
            ) as client:
                await client.delete_object(
                    Bucket=self._settings.minio_bucket,
                    Key=storage_path,
                )
        except ClientError:
            # Log but don't fail cleanup if MinIO delete fails
            pass


# ---------------------------------------------------------------------------
# Cron validation helpers
# ---------------------------------------------------------------------------


def _validate_cron_field(field: str, min_val: int, max_val: int) -> bool:
    """Validate a single cron field.

    Supports: wildcard (*), numbers, ranges (N-M), steps (*/N or N-M/N),
    and comma-separated lists of any of the above.

    Args:
        field: The cron field string to validate.
        min_val: Minimum allowed value for this field.
        max_val: Maximum allowed value for this field.

    Returns:
        True if the field is valid.
    """
    if not field:
        return False

    # Handle comma-separated lists
    parts = field.split(",")
    for part in parts:
        if not _validate_cron_part(part, min_val, max_val):
            return False

    return True


def _validate_cron_part(part: str, min_val: int, max_val: int) -> bool:
    """Validate a single part of a cron field (no commas).

    Args:
        part: A single cron field part (e.g., "5", "1-10", "*/2", "1-5/2").
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.

    Returns:
        True if the part is valid.
    """
    if not part:
        return False

    # Handle step notation: base/step
    if "/" in part:
        segments = part.split("/")
        if len(segments) != 2:
            return False
        base, step = segments

        # Validate step is a positive integer
        if not step.isdigit() or int(step) == 0:
            return False

        # Validate base (can be * or a range)
        if base == "*":
            return True
        return _validate_cron_range_or_value(base, min_val, max_val)

    # Handle range or single value
    return _validate_cron_range_or_value(part, min_val, max_val)


def _validate_cron_range_or_value(part: str, min_val: int, max_val: int) -> bool:
    """Validate a cron range (N-M) or single value.

    Args:
        part: A range like "1-5" or a single value like "3" or "*".
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.

    Returns:
        True if valid.
    """
    if part == "*":
        return True

    if "-" in part:
        segments = part.split("-")
        if len(segments) != 2:
            return False
        start_str, end_str = segments
        if not start_str.isdigit() or not end_str.isdigit():
            return False
        start, end = int(start_str), int(end_str)
        if start > end:
            return False
        if start < min_val or end > max_val:
            return False
        return True

    # Single value
    if not part.isdigit():
        return False
    val = int(part)
    return min_val <= val <= max_val


# ---------------------------------------------------------------------------
# Celery beat schedule registration
# ---------------------------------------------------------------------------


def _register_backup_schedule_with_celery(cron_expr: str) -> None:
    """Register or update the backup schedule in Celery beat.

    Parses the cron expression and updates the Celery beat schedule
    dynamically.

    Args:
        cron_expr: A valid 5-field cron expression.
    """
    from celery.schedules import crontab

    from alcoabase.tasks.celery_app import celery_app

    fields = cron_expr.strip().split()
    minute, hour, dom, month, dow = fields

    schedule = crontab(
        minute=minute,
        hour=hour,
        day_of_month=dom,
        month_of_year=month,
        day_of_week=dow,
    )

    celery_app.conf.beat_schedule["run-scheduled-backup"] = {
        "task": "alcoabase.tasks.system_config_tasks.run_backup",
        "schedule": schedule,
        "kwargs": {"user_id": None, "backup_type": "scheduled"},
        "options": {"queue": "default"},
    }


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class BackupAlreadyRunningError(Exception):
    """Raised when a backup trigger is attempted while another is active."""

    pass


class InvalidCronExpressionError(ValueError):
    """Raised when an invalid cron expression is provided."""

    pass


class InvalidRetentionPeriodError(ValueError):
    """Raised when a retention period outside 1-365 days is provided."""

    pass
