"""Unit tests for BackupService.

Tests backup triggering, concurrent rejection, cron validation,
human-readable conversion, schedule/retention updates, cleanup logic,
and history/status lookups.

Requirements: 7.1–7.5, 8.1–8.5, 9.1–9.6
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.system_config import BackupRecord, SystemConfiguration
from alcoabase.services.backup_service import (
    BackupAlreadyRunningError,
    BackupService,
    InvalidCronExpressionError,
    InvalidRetentionPeriodError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> BackupService:
    """Create a BackupService instance with mocked settings."""
    with patch("alcoabase.services.backup_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.minio_endpoint = "localhost:9000"
        settings.minio_access_key = "testkey"
        settings.minio_secret_key = "testsecret"
        settings.minio_bucket = "backups"
        settings.minio_use_ssl = False
        mock_settings.return_value = settings
        yield BackupService()


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests: trigger_backup creates record and dispatches Celery task
# ---------------------------------------------------------------------------


class TestTriggerBackup:
    """Tests for trigger_backup method."""

    @pytest.mark.asyncio
    async def test_creates_record_and_dispatches_task(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """trigger_backup creates a BackupRecord and dispatches Celery task."""
        # No running backup
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_celery = MagicMock()
        mock_celery.send_task = MagicMock()
        with patch(
            "alcoabase.tasks.celery_app.celery_app", mock_celery
        ):
            record = await service.trigger_backup(1, "Manual backup", mock_session)

        assert record.backup_type == "manual"
        assert record.status == "queued"
        assert record.triggered_by == 1
        assert record.task_id is not None
        mock_session.add.assert_called_once_with(record)
        mock_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_dispatches_celery_task_with_correct_params(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Celery task is dispatched with correct task name and kwargs."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_celery = MagicMock()
        mock_celery.send_task = MagicMock()
        with patch(
            "alcoabase.tasks.celery_app.celery_app", mock_celery
        ):
            record = await service.trigger_backup(42, "Pre-deploy backup", mock_session)

        mock_celery.send_task.assert_called_once_with(
            "alcoabase.tasks.system_config_tasks.run_backup",
            kwargs={"user_id": 42, "backup_type": "manual"},
            task_id=record.task_id,
        )


# ---------------------------------------------------------------------------
# Tests: Concurrent backup rejection (409)
# ---------------------------------------------------------------------------


class TestConcurrentBackupRejection:
    """Tests for concurrent backup rejection."""

    @pytest.mark.asyncio
    async def test_rejects_when_backup_queued(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Raises BackupAlreadyRunningError when a backup is queued."""
        existing = BackupRecord(
            task_id="existing-task", backup_type="manual", status="queued"
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(BackupAlreadyRunningError):
            await service.trigger_backup(1, "Another backup", mock_session)

    @pytest.mark.asyncio
    async def test_rejects_when_backup_running(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Raises BackupAlreadyRunningError when a backup is running."""
        existing = BackupRecord(
            task_id="running-task", backup_type="scheduled", status="running"
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(BackupAlreadyRunningError):
            await service.trigger_backup(1, "Concurrent attempt", mock_session)

    @pytest.mark.asyncio
    async def test_allows_when_no_active_backup(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Allows trigger when no backup is queued or running."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_celery = MagicMock()
        mock_celery.send_task = MagicMock()
        with patch(
            "alcoabase.tasks.celery_app.celery_app", mock_celery
        ):
            record = await service.trigger_backup(1, "OK", mock_session)

        assert record.status == "queued"


# ---------------------------------------------------------------------------
# Tests: validate_cron_expression with valid and invalid expressions
# ---------------------------------------------------------------------------


class TestValidateCronExpression:
    """Tests for validate_cron_expression static method."""

    @pytest.mark.parametrize(
        "expr",
        [
            "0 2 * * *",       # Daily at 02:00
            "*/15 * * * *",    # Every 15 minutes
            "0 0 1 * *",      # Monthly on 1st at midnight
            "30 4 * * 1",     # Weekly Monday at 04:30
            "0 0 * * 0",      # Weekly Sunday at midnight
            "0 0 * * 7",      # Weekly Sunday (7 = Sunday)
            "5,10,15 * * * *", # Minutes 5, 10, 15
            "0 1-5 * * *",    # Hours 1 through 5
            "0 */2 * * *",    # Every 2 hours
            "0 0 1-15/2 * *", # Every 2nd day from 1-15
        ],
    )
    def test_valid_expressions(self, expr: str) -> None:
        """Valid cron expressions return True."""
        assert BackupService.validate_cron_expression(expr) is True

    @pytest.mark.parametrize(
        "expr",
        [
            "",                # Empty string
            "* * *",          # Only 3 fields
            "* * * * * *",    # 6 fields (too many)
            "60 * * * *",     # Minute out of range (0-59)
            "* 24 * * *",     # Hour out of range (0-23)
            "* * 32 * *",     # Day out of range (1-31)
            "* * 0 * *",     # Day 0 invalid (1-31)
            "* * * 13 *",     # Month out of range (1-12)
            "* * * 0 *",     # Month 0 invalid (1-12)
            "* * * * 8",      # Day-of-week out of range (0-7)
            "abc * * * *",    # Non-numeric field
            "1-60 * * * *",   # Range end out of bounds
            "5-3 * * * *",    # Range start > end
            "*/0 * * * *",    # Step of 0 invalid
            None,             # None input
        ],
    )
    def test_invalid_expressions(self, expr) -> None:
        """Invalid cron expressions return False."""
        assert BackupService.validate_cron_expression(expr) is False

    def test_whitespace_trimmed(self) -> None:
        """Leading/trailing whitespace is trimmed before validation."""
        assert BackupService.validate_cron_expression("  0 2 * * *  ") is True


# ---------------------------------------------------------------------------
# Tests: cron_to_human_readable conversion
# ---------------------------------------------------------------------------


class TestCronToHumanReadable:
    """Tests for cron_to_human_readable static method."""

    def test_daily_schedule(self) -> None:
        """Daily cron produces 'Daily at HH:MM UTC'."""
        result = BackupService.cron_to_human_readable("0 2 * * *")
        assert result == "Daily at 02:00 UTC"

    def test_every_minute(self) -> None:
        """All wildcards produces 'Every minute'."""
        result = BackupService.cron_to_human_readable("* * * * *")
        assert result == "Every minute"

    def test_every_n_minutes(self) -> None:
        """Step in minute field produces 'Every N minutes'."""
        result = BackupService.cron_to_human_readable("*/15 * * * *")
        assert result == "Every 15 minutes"

    def test_hourly_schedule(self) -> None:
        """Minute-only with wildcard hour produces hourly description."""
        result = BackupService.cron_to_human_readable("30 * * * *")
        assert result == "Every hour at minute 30"

    def test_weekly_schedule(self) -> None:
        """Day-of-week specified produces weekly description."""
        result = BackupService.cron_to_human_readable("0 3 * * 1")
        assert result == "Weekly on Monday at 03:00 UTC"

    def test_weekly_sunday_zero(self) -> None:
        """Day-of-week 0 is Sunday."""
        result = BackupService.cron_to_human_readable("0 6 * * 0")
        assert result == "Weekly on Sunday at 06:00 UTC"

    def test_monthly_schedule(self) -> None:
        """Day-of-month specified produces monthly description."""
        result = BackupService.cron_to_human_readable("0 1 15 * *")
        assert result == "Monthly on day 15 at 01:00 UTC"

    def test_complex_expression_fallback(self) -> None:
        """Complex expressions fall back to 'Custom schedule (expr)'."""
        result = BackupService.cron_to_human_readable("0 2 1-15 1,6 *")
        assert result == "Custom schedule (0 2 1-15 1,6 *)"

    def test_invalid_expression_returns_invalid_message(self) -> None:
        """Invalid expression returns 'Invalid cron expression'."""
        result = BackupService.cron_to_human_readable("")
        assert result == "Invalid cron expression"

        result = BackupService.cron_to_human_readable("bad")
        assert result == "Invalid cron expression"


# ---------------------------------------------------------------------------
# Tests: update_schedule validates cron before persisting
# ---------------------------------------------------------------------------


class TestUpdateSchedule:
    """Tests for update_schedule method."""

    @pytest.mark.asyncio
    async def test_rejects_invalid_cron(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Raises InvalidCronExpressionError for invalid cron."""
        with pytest.raises(InvalidCronExpressionError):
            await service.update_schedule("bad cron", mock_session)

        # Session should not have been queried
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_updates_existing_config(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Updates existing SystemConfiguration row for backup_schedule."""
        existing_config = SystemConfiguration(
            category="backup_schedule",
            config_values={"cron_expression": "0 0 * * *", "human_readable": "Daily at 00:00 UTC"},
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = existing_config
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.backup_service._register_backup_schedule_with_celery"
        ):
            await service.update_schedule("0 2 * * *", mock_session)

        assert existing_config.config_values["cron_expression"] == "0 2 * * *"
        assert existing_config.config_values["human_readable"] == "Daily at 02:00 UTC"
        mock_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_creates_config_when_not_exists(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Creates new SystemConfiguration row if none exists."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.backup_service._register_backup_schedule_with_celery"
        ):
            await service.update_schedule("*/30 * * * *", mock_session)

        mock_session.add.assert_called_once()
        added_config = mock_session.add.call_args[0][0]
        assert added_config.category == "backup_schedule"
        assert added_config.config_values["cron_expression"] == "*/30 * * * *"

    @pytest.mark.asyncio
    async def test_registers_with_celery_beat(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Registers the schedule with Celery beat after persisting."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.backup_service._register_backup_schedule_with_celery"
        ) as mock_register:
            await service.update_schedule("0 3 * * *", mock_session)

        mock_register.assert_called_once_with("0 3 * * *")


# ---------------------------------------------------------------------------
# Tests: update_retention validates range 1-365
# ---------------------------------------------------------------------------


class TestUpdateRetention:
    """Tests for update_retention method."""

    @pytest.mark.asyncio
    async def test_rejects_zero_days(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Raises InvalidRetentionPeriodError for 0 days."""
        with pytest.raises(InvalidRetentionPeriodError):
            await service.update_retention(0, mock_session)

    @pytest.mark.asyncio
    async def test_rejects_negative_days(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Raises InvalidRetentionPeriodError for negative days."""
        with pytest.raises(InvalidRetentionPeriodError):
            await service.update_retention(-1, mock_session)

    @pytest.mark.asyncio
    async def test_rejects_over_365_days(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Raises InvalidRetentionPeriodError for >365 days."""
        with pytest.raises(InvalidRetentionPeriodError):
            await service.update_retention(366, mock_session)

    @pytest.mark.asyncio
    async def test_accepts_boundary_1_day(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Accepts minimum retention of 1 day."""
        existing_config = SystemConfiguration(
            category="backup_retention", config_values={"retention_days": 30}
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = existing_config
        mock_session.execute = AsyncMock(return_value=result_mock)

        await service.update_retention(1, mock_session)
        assert existing_config.config_values["retention_days"] == 1

    @pytest.mark.asyncio
    async def test_accepts_boundary_365_days(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Accepts maximum retention of 365 days."""
        existing_config = SystemConfiguration(
            category="backup_retention", config_values={"retention_days": 30}
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = existing_config
        mock_session.execute = AsyncMock(return_value=result_mock)

        await service.update_retention(365, mock_session)
        assert existing_config.config_values["retention_days"] == 365

    @pytest.mark.asyncio
    async def test_creates_config_when_not_exists(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Creates new SystemConfiguration row if none exists."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        await service.update_retention(90, mock_session)

        mock_session.add.assert_called_once()
        added_config = mock_session.add.call_args[0][0]
        assert added_config.category == "backup_retention"
        assert added_config.config_values["retention_days"] == 90


# ---------------------------------------------------------------------------
# Tests: cleanup_expired_backups deletes old but retains at least one
# ---------------------------------------------------------------------------


class TestCleanupExpiredBackups:
    """Tests for cleanup_expired_backups method."""

    @pytest.mark.asyncio
    async def test_retains_at_least_one_backup(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Always retains at least one backup even if all are expired."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=100)

        # All backups are expired
        backups = [
            BackupRecord(
                id=i,
                task_id=f"task-{i}",
                backup_type="scheduled",
                status="completed",
                created_at=old_time - timedelta(days=i),
                storage_path=f"backups/backup-{i}.gz",
            )
            for i in range(3)
        ]

        # First call: get retention config
        config_result = MagicMock()
        retention_config = SystemConfiguration(
            category="backup_retention", config_values={"retention_days": 7}
        )
        config_result.scalars.return_value.first.return_value = retention_config

        # Second call: get all completed backups (newest first)
        backups_result = MagicMock()
        backups_result.scalars.return_value.all.return_value = backups

        mock_session.execute = AsyncMock(
            side_effect=[config_result, backups_result]
        )

        with patch.object(service, "_delete_from_minio", new_callable=AsyncMock):
            deleted = await service.cleanup_expired_backups(mock_session)

        # Should delete all but one (the newest)
        assert deleted == 2

    @pytest.mark.asyncio
    async def test_no_deletion_when_single_backup(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Does not delete when only one backup exists."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=100)

        backups = [
            BackupRecord(
                id=1,
                task_id="task-1",
                backup_type="manual",
                status="completed",
                created_at=old_time,
                storage_path="backups/backup-1.gz",
            )
        ]

        config_result = MagicMock()
        retention_config = SystemConfiguration(
            category="backup_retention", config_values={"retention_days": 7}
        )
        config_result.scalars.return_value.first.return_value = retention_config

        backups_result = MagicMock()
        backups_result.scalars.return_value.all.return_value = backups

        mock_session.execute = AsyncMock(
            side_effect=[config_result, backups_result]
        )

        deleted = await service.cleanup_expired_backups(mock_session)
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_deletes_only_expired_backups(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Deletes only backups older than retention period."""
        now = datetime.now(timezone.utc)

        backups = [
            BackupRecord(
                id=1,
                task_id="task-new",
                backup_type="manual",
                status="completed",
                created_at=now - timedelta(days=1),
                storage_path="backups/new.gz",
            ),
            BackupRecord(
                id=2,
                task_id="task-mid",
                backup_type="scheduled",
                status="completed",
                created_at=now - timedelta(days=15),
                storage_path="backups/mid.gz",
            ),
            BackupRecord(
                id=3,
                task_id="task-old",
                backup_type="scheduled",
                status="completed",
                created_at=now - timedelta(days=40),
                storage_path="backups/old.gz",
            ),
        ]

        config_result = MagicMock()
        retention_config = SystemConfiguration(
            category="backup_retention", config_values={"retention_days": 30}
        )
        config_result.scalars.return_value.first.return_value = retention_config

        backups_result = MagicMock()
        backups_result.scalars.return_value.all.return_value = backups

        mock_session.execute = AsyncMock(
            side_effect=[config_result, backups_result]
        )

        with patch.object(service, "_delete_from_minio", new_callable=AsyncMock):
            deleted = await service.cleanup_expired_backups(mock_session)

        # Only the 40-day-old backup exceeds 30-day retention
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_uses_default_retention_when_not_configured(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Uses 30-day default retention when no config exists."""
        now = datetime.now(timezone.utc)

        backups = [
            BackupRecord(
                id=1,
                task_id="task-new",
                backup_type="manual",
                status="completed",
                created_at=now - timedelta(days=10),
                storage_path="backups/new.gz",
            ),
            BackupRecord(
                id=2,
                task_id="task-old",
                backup_type="scheduled",
                status="completed",
                created_at=now - timedelta(days=35),
                storage_path="backups/old.gz",
            ),
        ]

        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None  # No config

        backups_result = MagicMock()
        backups_result.scalars.return_value.all.return_value = backups

        mock_session.execute = AsyncMock(
            side_effect=[config_result, backups_result]
        )

        with patch.object(service, "_delete_from_minio", new_callable=AsyncMock):
            deleted = await service.cleanup_expired_backups(mock_session)

        # 35-day-old backup exceeds default 30-day retention
        assert deleted == 1

    @pytest.mark.asyncio
    async def test_calls_minio_delete_for_expired(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Calls _delete_from_minio for each expired backup with storage_path."""
        now = datetime.now(timezone.utc)

        backups = [
            BackupRecord(
                id=1,
                task_id="task-new",
                backup_type="manual",
                status="completed",
                created_at=now - timedelta(days=1),
                storage_path="backups/new.gz",
            ),
            BackupRecord(
                id=2,
                task_id="task-old",
                backup_type="scheduled",
                status="completed",
                created_at=now - timedelta(days=50),
                storage_path="backups/old.gz",
            ),
        ]

        config_result = MagicMock()
        retention_config = SystemConfiguration(
            category="backup_retention", config_values={"retention_days": 7}
        )
        config_result.scalars.return_value.first.return_value = retention_config

        backups_result = MagicMock()
        backups_result.scalars.return_value.all.return_value = backups

        mock_session.execute = AsyncMock(
            side_effect=[config_result, backups_result]
        )

        with patch.object(
            service, "_delete_from_minio", new_callable=AsyncMock
        ) as mock_delete:
            await service.cleanup_expired_backups(mock_session)

        mock_delete.assert_awaited_once_with("backups/old.gz")


# ---------------------------------------------------------------------------
# Tests: get_backup_history ordering, get_backup_status lookup
# ---------------------------------------------------------------------------


class TestBackupHistoryAndStatus:
    """Tests for get_backup_history and get_backup_status."""

    @pytest.mark.asyncio
    async def test_get_backup_history_returns_ordered_list(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """get_backup_history returns records ordered by created_at desc."""
        now = datetime.now(timezone.utc)
        records = [
            BackupRecord(
                id=3,
                task_id="task-3",
                backup_type="manual",
                status="completed",
                created_at=now,
            ),
            BackupRecord(
                id=2,
                task_id="task-2",
                backup_type="scheduled",
                status="completed",
                created_at=now - timedelta(hours=1),
            ),
            BackupRecord(
                id=1,
                task_id="task-1",
                backup_type="manual",
                status="failed",
                created_at=now - timedelta(hours=2),
            ),
        ]

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = records
        mock_session.execute = AsyncMock(return_value=result_mock)

        history = await service.get_backup_history(mock_session)

        assert len(history) == 3
        assert history[0].task_id == "task-3"
        assert history[1].task_id == "task-2"
        assert history[2].task_id == "task-1"

    @pytest.mark.asyncio
    async def test_get_backup_history_empty(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """get_backup_history returns empty list when no records exist."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        history = await service.get_backup_history(mock_session)
        assert history == []

    @pytest.mark.asyncio
    async def test_get_backup_status_found(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """get_backup_status returns the record when task_id exists."""
        record = BackupRecord(
            id=1,
            task_id="abc-123",
            backup_type="manual",
            status="running",
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.get_backup_status("abc-123", mock_session)

        assert result is not None
        assert result.task_id == "abc-123"
        assert result.status == "running"

    @pytest.mark.asyncio
    async def test_get_backup_status_not_found(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """get_backup_status returns None when task_id does not exist."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await service.get_backup_status("nonexistent", mock_session)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: is_backup_running
# ---------------------------------------------------------------------------


class TestIsBackupRunning:
    """Tests for is_backup_running method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_queued_exists(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Returns True when a queued backup exists."""
        existing = BackupRecord(
            task_id="task-q", backup_type="manual", status="queued"
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = existing
        mock_session.execute = AsyncMock(return_value=result_mock)

        assert await service.is_backup_running(mock_session) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_active(
        self, service: BackupService, mock_session: AsyncMock
    ) -> None:
        """Returns False when no queued or running backup exists."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        assert await service.is_backup_running(mock_session) is False
