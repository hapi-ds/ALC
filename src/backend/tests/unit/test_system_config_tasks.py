"""Unit tests for Celery tasks in system_config_tasks.

Tests the periodic background tasks for health checks, backups,
expired backup cleanup, resource metrics collection, and dynamic
schedule updates.

Requirements: 7.3, 8.2, 8.3, 9.1–9.5, 10.1, 10.2, 13.1, 13.2
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.system_config import (
    BackupRecord,
    HealthCheckResult,
    ResourceMetricPoint,
    SystemConfiguration,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory for Celery tasks."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    return factory, session


@pytest.fixture
def mock_settings():
    """Create mock application settings."""
    settings = MagicMock()
    settings.database_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
    settings.minio_endpoint = "localhost:9000"
    settings.minio_access_key = "testkey"
    settings.minio_secret_key = "testsecret"
    settings.minio_bucket = "backups"
    settings.minio_use_ssl = False
    settings.redis_url = "redis://localhost:6379/0"
    return settings


# ---------------------------------------------------------------------------
# Tests: run_health_checks stores results and detects transitions
# ---------------------------------------------------------------------------


class TestRunHealthChecks:
    """Tests for the run_health_checks Celery task."""

    @pytest.mark.asyncio
    async def test_stores_health_check_results(
        self, mock_session_factory, mock_settings
    ) -> None:
        """run_health_checks stores results for all monitored services."""
        factory, session = mock_session_factory

        # Mock health check config query
        config_result = MagicMock()
        config_obj = SystemConfiguration(
            category="health_check",
            config_values={
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        )
        config_result.scalars.return_value.first.return_value = config_obj
        session.execute = AsyncMock(return_value=config_result)

        # Mock HealthMonitor
        mock_results = [
            HealthCheckResult(
                service_name="postgresql",
                status="healthy",
                response_time_ms=15.0,
                checked_at=datetime.now(timezone.utc),
                is_transition=False,
            ),
            HealthCheckResult(
                service_name="redis",
                status="healthy",
                response_time_ms=5.0,
                checked_at=datetime.now(timezone.utc),
                is_transition=False,
            ),
        ]

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.health_monitor.HealthMonitor.check_all_services",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _run_health_checks_async,
            )

            result = await _run_health_checks_async()

        assert result["services_checked"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["service"] == "postgresql"
        assert result["results"][0]["status"] == "healthy"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_detects_transitions(
        self, mock_session_factory, mock_settings
    ) -> None:
        """run_health_checks detects status transitions in results."""
        factory, session = mock_session_factory

        config_result = MagicMock()
        config_obj = SystemConfiguration(
            category="health_check",
            config_values={
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        )
        config_result.scalars.return_value.first.return_value = config_obj
        session.execute = AsyncMock(return_value=config_result)

        # Simulate a transition: postgresql went from healthy to degraded
        mock_results = [
            HealthCheckResult(
                service_name="postgresql",
                status="degraded",
                response_time_ms=6000.0,
                checked_at=datetime.now(timezone.utc),
                is_transition=True,
                previous_status="healthy",
            ),
        ]

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.health_monitor.HealthMonitor.check_all_services",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _run_health_checks_async,
            )

            result = await _run_health_checks_async()

        assert result["results"][0]["is_transition"] is True
        assert result["results"][0]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_uses_default_config_when_not_in_db(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Falls back to default thresholds when no DB config exists."""
        factory, session = mock_session_factory

        # No config in DB
        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=config_result)

        mock_results = [
            HealthCheckResult(
                service_name="redis",
                status="healthy",
                response_time_ms=2.0,
                checked_at=datetime.now(timezone.utc),
                is_transition=False,
            ),
        ]

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.health_monitor.HealthMonitor.check_all_services",
                new_callable=AsyncMock,
                return_value=mock_results,
            ),
            patch(
                "alcoabase.services.health_monitor.HealthMonitor.__init__",
                return_value=None,
            ) as mock_init,
        ):
            from alcoabase.tasks.system_config_tasks import (
                _run_health_checks_async,
            )

            await _run_health_checks_async()

        # Default thresholds: 5s degraded (5000ms), 10s timeout (10000ms)
        mock_init.assert_called_once_with(
            degraded_threshold_ms=5000.0,
            timeout_ms=10000.0,
        )

    @pytest.mark.asyncio
    async def test_rolls_back_on_error(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Rolls back session and re-raises on HealthMonitor failure."""
        factory, session = mock_session_factory

        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=config_result)

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.health_monitor.HealthMonitor.check_all_services",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Connection refused"),
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _run_health_checks_async,
            )

            with pytest.raises(RuntimeError, match="Connection refused"):
                await _run_health_checks_async()

        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: run_backup lifecycle (queued→running→completed, queued→running→failed)
# ---------------------------------------------------------------------------


class TestRunBackup:
    """Tests for the run_backup Celery task."""

    @pytest.mark.asyncio
    async def test_successful_backup_lifecycle(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Backup transitions: queued→running→completed with metadata."""
        factory, session = mock_session_factory
        task_id = "test-task-123"

        # Mock the BackupRecord query
        record = BackupRecord(
            id=1,
            task_id=task_id,
            backup_type="manual",
            status="queued",
            triggered_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        session.execute = AsyncMock(return_value=result_mock)

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._execute_pg_dump",
                new_callable=AsyncMock,
                return_value=("/tmp/backup.sql.gz", 1024000),
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._upload_to_minio",
                new_callable=AsyncMock,
                return_value="backups/20250101_120000_test-task-123.sql.gz",
            ),
            patch("os.path.exists", return_value=False),
        ):
            from alcoabase.tasks.system_config_tasks import _run_backup_async

            result = await _run_backup_async(task_id, 1, "manual")

        assert result["task_id"] == task_id
        assert result["status"] == "completed"
        assert result["file_size_bytes"] == 1024000
        assert "backups/" in result["storage_path"]
        assert result["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_failed_backup_lifecycle(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Backup transitions: queued→running→failed with error message."""
        factory, session = mock_session_factory
        task_id = "test-task-fail"

        record = BackupRecord(
            id=2,
            task_id=task_id,
            backup_type="manual",
            status="queued",
            triggered_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        session.execute = AsyncMock(return_value=result_mock)

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._execute_pg_dump",
                new_callable=AsyncMock,
                side_effect=RuntimeError("pg_dump failed (exit code 1): connection refused"),
            ),
        ):
            from alcoabase.tasks.system_config_tasks import _run_backup_async

            result = await _run_backup_async(task_id, 1, "manual")

        assert result["task_id"] == task_id
        assert result["status"] == "failed"
        assert "pg_dump failed" in result["error_message"]
        assert result["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_creates_record_for_scheduled_backup(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Creates a new BackupRecord when none exists (scheduled backup)."""
        factory, session = mock_session_factory
        task_id = "scheduled-task-001"

        # First query: no existing record
        no_record_result = MagicMock()
        no_record_result.scalars.return_value.first.return_value = None

        # Subsequent queries: return the newly created record
        new_record = BackupRecord(
            id=3,
            task_id=task_id,
            backup_type="scheduled",
            status="queued",
            triggered_by=None,
        )
        found_result = MagicMock()
        found_result.scalars.return_value.first.return_value = new_record

        session.execute = AsyncMock(
            side_effect=[no_record_result, found_result]
        )

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._execute_pg_dump",
                new_callable=AsyncMock,
                return_value=("/tmp/backup.sql.gz", 512000),
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._upload_to_minio",
                new_callable=AsyncMock,
                return_value="backups/scheduled.sql.gz",
            ),
            patch("os.path.exists", return_value=False),
        ):
            from alcoabase.tasks.system_config_tasks import _run_backup_async

            result = await _run_backup_async(task_id, None, "scheduled")

        assert result["status"] == "completed"
        # Verify a record was added to the session
        session.add.assert_called()

    @pytest.mark.asyncio
    async def test_updates_status_to_running(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Backup record status is set to 'running' before pg_dump."""
        factory, session = mock_session_factory
        task_id = "test-running-status"

        record = BackupRecord(
            id=4,
            task_id=task_id,
            backup_type="manual",
            status="queued",
            triggered_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = record
        session.execute = AsyncMock(return_value=result_mock)

        # Track status changes
        status_changes = []

        original_commit = session.commit

        async def track_commit():
            status_changes.append(record.status)
            await original_commit()

        session.commit = track_commit

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._execute_pg_dump",
                new_callable=AsyncMock,
                return_value=("/tmp/backup.sql.gz", 2048),
            ),
            patch(
                "alcoabase.tasks.system_config_tasks._upload_to_minio",
                new_callable=AsyncMock,
                return_value="backups/test.sql.gz",
            ),
            patch("os.path.exists", return_value=False),
        ):
            from alcoabase.tasks.system_config_tasks import _run_backup_async

            await _run_backup_async(task_id, 1, "manual")

        # First commit sets status to "running", second to "completed"
        assert "running" in status_changes


# ---------------------------------------------------------------------------
# Tests: cleanup_expired_backups respects retention and minimum-one-backup
# ---------------------------------------------------------------------------


class TestCleanupExpiredBackups:
    """Tests for the cleanup_expired_backups Celery task."""

    @pytest.mark.asyncio
    async def test_delegates_to_backup_service(
        self, mock_session_factory, mock_settings
    ) -> None:
        """cleanup_expired_backups delegates to BackupService.cleanup_expired_backups."""
        factory, session = mock_session_factory

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.backup_service.BackupService.cleanup_expired_backups",
                new_callable=AsyncMock,
                return_value=3,
            ) as mock_cleanup,
        ):
            from alcoabase.tasks.system_config_tasks import (
                _cleanup_expired_backups_async,
            )

            result = await _cleanup_expired_backups_async()

        assert result["status"] == "completed"
        assert result["deleted_count"] == 3
        mock_cleanup.assert_awaited_once_with(session)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_zero_deletions_when_all_within_retention(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Returns deleted_count=0 when no backups are expired."""
        factory, session = mock_session_factory

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.backup_service.BackupService.cleanup_expired_backups",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _cleanup_expired_backups_async,
            )

            result = await _cleanup_expired_backups_async()

        assert result["status"] == "completed"
        assert result["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_rolls_back_on_cleanup_error(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Rolls back session and re-raises on cleanup failure."""
        factory, session = mock_session_factory

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.backup_service.BackupService.cleanup_expired_backups",
                new_callable=AsyncMock,
                side_effect=RuntimeError("MinIO unreachable"),
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _cleanup_expired_backups_async,
            )

            with pytest.raises(RuntimeError, match="MinIO unreachable"):
                await _cleanup_expired_backups_async()

        session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Tests: collect_resource_metrics stores data points for all containers
# ---------------------------------------------------------------------------


class TestCollectResourceMetrics:
    """Tests for the collect_resource_metrics Celery task."""

    @pytest.mark.asyncio
    async def test_stores_metrics_for_all_containers(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Stores ResourceMetricPoint for each container returned by registry."""
        factory, session = mock_session_factory

        from alcoabase.services.service_registry import ResourceMetrics

        mock_metrics = [
            ResourceMetrics(
                service_name="postgresql",
                container_name="alcoabase-postgres",
                cpu_percent=12.5,
                memory_used_mb=256.0,
                memory_limit_mb=1024.0,
            ),
            ResourceMetrics(
                service_name="redis",
                container_name="alcoabase-redis",
                cpu_percent=2.1,
                memory_used_mb=64.0,
                memory_limit_mb=512.0,
            ),
            ResourceMetrics(
                service_name="minio",
                container_name="alcoabase-minio",
                cpu_percent=5.3,
                memory_used_mb=128.0,
                memory_limit_mb=2048.0,
            ),
        ]

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.service_registry.ServiceRegistry.get_resource_utilization",
                new_callable=AsyncMock,
                return_value=mock_metrics,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _collect_resource_metrics_async,
            )

            result = await _collect_resource_metrics_async()

        assert result["status"] == "completed"
        assert result["metrics_count"] == 3
        # Verify session.add was called for each metric
        assert session.add.call_count == 3
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stores_correct_metric_values(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Stored ResourceMetricPoint has correct cpu/memory values."""
        factory, session = mock_session_factory

        from alcoabase.services.service_registry import ResourceMetrics

        mock_metrics = [
            ResourceMetrics(
                service_name="vllm",
                container_name="alcoabase-vllm",
                cpu_percent=85.2,
                memory_used_mb=7800.0,
                memory_limit_mb=8192.0,
            ),
        ]

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.service_registry.ServiceRegistry.get_resource_utilization",
                new_callable=AsyncMock,
                return_value=mock_metrics,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _collect_resource_metrics_async,
            )

            await _collect_resource_metrics_async()

        # Check the ResourceMetricPoint that was added
        added_point = session.add.call_args[0][0]
        assert isinstance(added_point, ResourceMetricPoint)
        assert added_point.service_name == "vllm"
        assert added_point.cpu_percent == 85.2
        assert added_point.memory_used_mb == 7800.0
        assert added_point.memory_limit_mb == 8192.0

    @pytest.mark.asyncio
    async def test_handles_no_running_containers(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Returns metrics_count=0 when no containers are running."""
        factory, session = mock_session_factory

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.service_registry.ServiceRegistry.get_resource_utilization",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _collect_resource_metrics_async,
            )

            result = await _collect_resource_metrics_async()

        assert result["status"] == "completed"
        assert result["metrics_count"] == 0
        # No data points stored
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_docker_error_gracefully(
        self, mock_session_factory, mock_settings
    ) -> None:
        """Returns failed status when Docker is unavailable."""
        factory, session = mock_session_factory

        with (
            patch(
                "alcoabase.tasks.system_config_tasks._get_async_session_factory",
                return_value=factory,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.services.service_registry.ServiceRegistry.get_resource_utilization",
                new_callable=AsyncMock,
                side_effect=Exception("Docker socket unavailable"),
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                _collect_resource_metrics_async,
            )

            result = await _collect_resource_metrics_async()

        assert result["status"] == "failed"
        assert "Docker socket unavailable" in result["error"]


# ---------------------------------------------------------------------------
# Tests: Dynamic schedule update reads from DB config
# ---------------------------------------------------------------------------


class TestDynamicScheduleUpdate:
    """Tests for get_dynamic_health_check_interval."""

    def test_reads_interval_from_db(self, mock_settings) -> None:
        """Reads polling_interval_seconds from DB config."""
        config = SystemConfiguration(
            category="health_check",
            config_values={"polling_interval_seconds": 60},
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = config

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.create_async_engine",
                return_value=mock_engine,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.async_sessionmaker",
                return_value=mock_factory,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                get_dynamic_health_check_interval,
            )

            interval = get_dynamic_health_check_interval()

        assert interval == 60.0

    def test_returns_default_when_no_config(self, mock_settings) -> None:
        """Returns 30.0 when no health_check config exists in DB."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        with (
            patch(
                "alcoabase.tasks.system_config_tasks.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.create_async_engine",
                return_value=mock_engine,
            ),
            patch(
                "alcoabase.tasks.system_config_tasks.async_sessionmaker",
                return_value=mock_factory,
            ),
        ):
            from alcoabase.tasks.system_config_tasks import (
                get_dynamic_health_check_interval,
            )

            interval = get_dynamic_health_check_interval()

        assert interval == 30.0

    def test_returns_default_on_exception(self, mock_settings) -> None:
        """Returns 30.0 when DB query raises an exception."""
        with patch(
            "alcoabase.tasks.system_config_tasks.get_settings",
            side_effect=RuntimeError("Settings unavailable"),
        ):
            from alcoabase.tasks.system_config_tasks import (
                get_dynamic_health_check_interval,
            )

            interval = get_dynamic_health_check_interval()

        assert interval == 30.0
