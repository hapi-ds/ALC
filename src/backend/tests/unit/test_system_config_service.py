"""Unit tests for SystemConfigurationService.

Tests the core service methods: get_config, update_config, rollback_to_snapshot,
snapshot history/diff, restart_vllm_service, and validate_model_path.

Requirements: 1.3, 1.4, 2.1–2.7, 3.1–3.6, 4.1–4.5, 14.1–14.7
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.system_config import (
    ConfigurationSnapshot,
    SystemConfiguration,
)
from alcoabase.schemas.system_config import ConfigDiffItem
from alcoabase.services.system_config import (
    ConfigUpdateResult,
    RollbackResult,
    ServiceRestartResult,
    SystemConfigurationService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> SystemConfigurationService:
    """Create a SystemConfigurationService instance."""
    return SystemConfigurationService()


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings with default AI hardware values."""
    settings = MagicMock()
    settings.model_chat_name = "TestChat/Model"
    settings.model_chat_path = "/models/test-chat"
    settings.model_chat_max_gpu_memory_gb = 24
    settings.model_embedding_name = "TestEmbed/Model"
    settings.model_embedding_path = "/models/test-embed"
    settings.model_embedding_dimension = 768
    settings.model_ocr_name = "TestOCR/Model"
    settings.model_ocr_path = "/models/test-ocr"
    settings.model_manager_mode = "mock"
    settings.gpu_device_id = 0
    settings.vllm_base_url = "http://localhost:8000"
    settings.vllm_embedding_url = "http://localhost:8001"
    return settings


# ---------------------------------------------------------------------------
# Tests: get_config merges DB values over .env defaults
# ---------------------------------------------------------------------------


class TestGetConfig:
    """Tests for get_config merging DB values over .env defaults."""

    @pytest.mark.asyncio
    async def test_returns_env_defaults_when_no_db_row(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """When no DB row exists, returns only .env defaults."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            config = await service.get_config("ai_hardware", session)

        assert config["model_chat_name"] == "TestChat/Model"
        assert config["inference_mode"] == "mock"
        assert config["gpu_device_id"] == 0

    @pytest.mark.asyncio
    async def test_db_values_override_env_defaults(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """DB values take precedence over .env defaults."""
        db_row = MagicMock(spec=SystemConfiguration)
        db_row.config_values = {
            "model_chat_name": "OverriddenChat/Model",
            "inference_mode": "gpu",
        }

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = db_row
        session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            config = await service.get_config("ai_hardware", session)

        # DB overrides
        assert config["model_chat_name"] == "OverriddenChat/Model"
        assert config["inference_mode"] == "gpu"
        # .env defaults preserved for non-overridden keys
        assert config["model_embedding_name"] == "TestEmbed/Model"
        assert config["gpu_device_id"] == 0

    @pytest.mark.asyncio
    async def test_db_row_with_empty_values_returns_defaults(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """DB row with empty/None values dict returns .env defaults."""
        db_row = MagicMock(spec=SystemConfiguration)
        db_row.config_values = {}

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = db_row
        session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            config = await service.get_config("ai_hardware", session)

        assert config["model_chat_name"] == "TestChat/Model"

    @pytest.mark.asyncio
    async def test_backup_schedule_defaults(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Backup schedule category returns correct defaults."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            config = await service.get_config("backup_schedule", session)

        assert config["cron_expression"] == "0 2 * * *"

    @pytest.mark.asyncio
    async def test_health_check_defaults(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Health check category returns correct defaults."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            config = await service.get_config("health_check", session)

        assert config["polling_interval_seconds"] == 30
        assert config["degraded_threshold_seconds"] == 5
        assert config["unreachable_timeout_seconds"] == 10


# ---------------------------------------------------------------------------
# Tests: update_config creates snapshot before applying changes
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    """Tests for update_config creating snapshots and applying changes."""

    @pytest.mark.asyncio
    async def test_creates_snapshot_before_update(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """update_config creates a pre-change snapshot before applying."""
        snapshot_mock = MagicMock(spec=ConfigurationSnapshot)
        snapshot_mock.id = 42

        session = AsyncMock()
        # First execute: create_snapshot queries all categories
        # Second execute: get_config for each category in create_snapshot
        # Then: select config row for update
        config_row = MagicMock(spec=SystemConfiguration)
        config_row.config_values = {"retention_days": 30}

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = config_row
        session.execute = AsyncMock(return_value=result_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                service,
                "create_snapshot",
                return_value=snapshot_mock,
            ) as mock_create_snapshot:
                result = await service.update_config(
                    "backup_retention",
                    {"retention_days": 60},
                    user_id=1,
                    reason="Increase retention",
                    session=session,
                )

        # Snapshot was created before the update
        mock_create_snapshot.assert_called_once_with(
            session, user_id=1, reason="Increase retention"
        )
        assert result.snapshot_id == 42
        assert result.category == "backup_retention"

    @pytest.mark.asyncio
    async def test_restart_required_for_ai_hardware_fields(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Updating AI hardware fields sets restart_required=True."""
        snapshot_mock = MagicMock(spec=ConfigurationSnapshot)
        snapshot_mock.id = 1

        config_row = MagicMock(spec=SystemConfiguration)
        config_row.config_values = {"inference_mode": "mock"}

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = config_row
        session.execute = AsyncMock(return_value=result_mock)
        session.flush = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                service, "create_snapshot", return_value=snapshot_mock
            ):
                with patch.object(
                    service, "validate_model_path", return_value=True
                ):
                    result = await service.update_config(
                        "ai_hardware",
                        {"inference_mode": "gpu"},
                        user_id=1,
                        reason="Switch to GPU",
                        session=session,
                    )

        assert result.restart_required is True

    @pytest.mark.asyncio
    async def test_no_restart_for_non_ai_fields(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Updating non-AI fields does not require restart."""
        snapshot_mock = MagicMock(spec=ConfigurationSnapshot)
        snapshot_mock.id = 1

        config_row = MagicMock(spec=SystemConfiguration)
        config_row.config_values = {"retention_days": 30}

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = config_row
        session.execute = AsyncMock(return_value=result_mock)
        session.flush = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                service, "create_snapshot", return_value=snapshot_mock
            ):
                result = await service.update_config(
                    "backup_retention",
                    {"retention_days": 60},
                    user_id=1,
                    reason="Update retention",
                    session=session,
                )

        assert result.restart_required is False

    @pytest.mark.asyncio
    async def test_creates_new_row_when_none_exists(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Creates a new SystemConfiguration row when category has no DB row."""
        snapshot_mock = MagicMock(spec=ConfigurationSnapshot)
        snapshot_mock.id = 1

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                service, "create_snapshot", return_value=snapshot_mock
            ):
                result = await service.update_config(
                    "backup_retention",
                    {"retention_days": 90},
                    user_id=1,
                    reason="Set retention",
                    session=session,
                )

        session.add.assert_called()
        assert result.updated_values["retention_days"] == 90

    @pytest.mark.asyncio
    async def test_validation_failure_raises_value_error(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Invalid field values raise ValueError before snapshot creation."""
        session = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with pytest.raises(ValueError, match="retention_days"):
                await service.update_config(
                    "backup_retention",
                    {"retention_days": 999},  # exceeds 365
                    user_id=1,
                    reason="Bad value",
                    session=session,
                )


# ---------------------------------------------------------------------------
# Tests: rollback_to_snapshot restores all categories atomically
# ---------------------------------------------------------------------------


class TestRollbackToSnapshot:
    """Tests for rollback_to_snapshot atomic restoration."""

    @pytest.mark.asyncio
    async def test_restores_all_categories_from_snapshot(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Rollback restores all categories to snapshot state."""
        target_snapshot = MagicMock(spec=ConfigurationSnapshot)
        target_snapshot.id = 10
        target_snapshot.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        target_snapshot.snapshot_data = {
            "ai_hardware": {"inference_mode": "mock", "gpu_device_id": 0},
            "backup_schedule": {"cron_expression": "0 2 * * *"},
            "backup_retention": {"retention_days": 30},
            "health_check": {
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        }

        rollback_snapshot = MagicMock(spec=ConfigurationSnapshot)
        rollback_snapshot.id = 11

        session = AsyncMock()

        # Mock: load target snapshot
        snapshot_result = MagicMock()
        snapshot_result.scalar_one_or_none.return_value = target_snapshot

        # Mock: config rows for each category
        config_row = MagicMock(spec=SystemConfiguration)
        config_row.config_values = {}
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config_row

        # Mock: user lookup
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = "Admin User"

        session.execute = AsyncMock(
            side_effect=[snapshot_result] + [config_result] * 4 + [user_result]
        )
        session.flush = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                service, "get_config", return_value={"inference_mode": "gpu"}
            ):
                with patch.object(
                    service,
                    "create_snapshot",
                    return_value=rollback_snapshot,
                ):
                    with patch.object(
                        service, "_validate_snapshot_values", return_value={}
                    ):
                        result = await service.rollback_to_snapshot(
                            snapshot_id=10,
                            user_id=1,
                            reason="Rollback to previous state",
                            session=session,
                        )

        assert result.snapshot_id == 10
        assert result.acting_user == "Admin User"
        assert result.new_snapshot_id == 11

    @pytest.mark.asyncio
    async def test_snapshot_not_found_raises_error(
        self, service: SystemConfigurationService
    ) -> None:
        """Rollback raises ValueError when snapshot doesn't exist."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(ValueError, match="not found"):
            await service.rollback_to_snapshot(
                snapshot_id=999,
                user_id=1,
                reason="Rollback",
                session=session,
            )

    @pytest.mark.asyncio
    async def test_rollback_rejected_on_validation_failure(
        self, service: SystemConfigurationService
    ) -> None:
        """Rollback is rejected entirely when validation fails (no partial)."""
        target_snapshot = MagicMock(spec=ConfigurationSnapshot)
        target_snapshot.id = 10
        target_snapshot.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        target_snapshot.snapshot_data = {
            "ai_hardware": {"gpu_device_id": -5},  # Invalid
            "backup_retention": {"retention_days": 999},  # Invalid
            "health_check": {"polling_interval_seconds": 30},
        }

        session = AsyncMock()
        snapshot_result = MagicMock()
        snapshot_result.scalar_one_or_none.return_value = target_snapshot
        session.execute = AsyncMock(return_value=snapshot_result)

        with pytest.raises(ValueError, match="Rollback rejected"):
            await service.rollback_to_snapshot(
                snapshot_id=10,
                user_id=1,
                reason="Rollback",
                session=session,
            )

    @pytest.mark.asyncio
    async def test_rollback_creates_new_snapshot_with_reference(
        self, service: SystemConfigurationService, mock_settings: MagicMock
    ) -> None:
        """Rollback creates a new snapshot referencing the target."""
        target_snapshot = MagicMock(spec=ConfigurationSnapshot)
        target_snapshot.id = 5
        target_snapshot.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        target_snapshot.snapshot_data = {
            "ai_hardware": {"inference_mode": "mock", "gpu_device_id": 0},
            "backup_schedule": {"cron_expression": "0 2 * * *"},
            "backup_retention": {"retention_days": 30},
            "health_check": {
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        }

        rollback_snapshot = MagicMock(spec=ConfigurationSnapshot)
        rollback_snapshot.id = 6

        session = AsyncMock()
        snapshot_result = MagicMock()
        snapshot_result.scalar_one_or_none.return_value = target_snapshot

        config_row = MagicMock(spec=SystemConfiguration)
        config_row.config_values = {}
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config_row

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = "Test User"

        session.execute = AsyncMock(
            side_effect=[snapshot_result] + [config_result] * 4 + [user_result]
        )
        session.flush = AsyncMock()

        with patch(
            "alcoabase.services.system_config.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                service, "get_config", return_value={"inference_mode": "gpu"}
            ):
                with patch.object(
                    service, "_validate_snapshot_values", return_value={}
                ):
                    with patch.object(
                        service,
                        "create_snapshot",
                        return_value=rollback_snapshot,
                    ) as mock_snap:
                        result = await service.rollback_to_snapshot(
                            snapshot_id=5,
                            user_id=1,
                            reason="Undo changes",
                            session=session,
                        )

        # Verify create_snapshot was called with rollback params
        mock_snap.assert_called_once_with(
            session,
            user_id=1,
            reason="Undo changes",
            is_rollback=True,
            rollback_target_id=5,
        )
        assert result.new_snapshot_id == 6


# ---------------------------------------------------------------------------
# Tests: Snapshot history pagination and diff computation
# ---------------------------------------------------------------------------


class TestSnapshotHistory:
    """Tests for get_snapshot_history pagination."""

    @pytest.mark.asyncio
    async def test_pagination_returns_correct_metadata(
        self, service: SystemConfigurationService
    ) -> None:
        """Pagination metadata is computed correctly."""
        session = AsyncMock()

        # Mock count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 45

        # Mock snapshot query
        snapshot1 = MagicMock(spec=ConfigurationSnapshot)
        snapshot1.id = 1
        snapshot1.created_at = datetime(2025, 1, 15, tzinfo=UTC)
        snapshot1.change_reason = "Update config"
        snapshot1.is_rollback = False
        snapshot1.changed_keys = ["ai_hardware.inference_mode"]

        rows_result = MagicMock()
        rows_result.all.return_value = [(snapshot1, "Admin User")]

        session.execute = AsyncMock(
            side_effect=[count_result, rows_result]
        )

        result = await service.get_snapshot_history(
            page=1, page_size=20, session=session
        )

        assert result.total == 45
        assert result.page == 1
        assert result.page_size == 20
        assert result.total_pages == 3  # ceil(45/20) = 3
        assert len(result.items) == 1
        assert result.items[0]["created_by_name"] == "Admin User"

    @pytest.mark.asyncio
    async def test_empty_history_returns_one_page(
        self, service: SystemConfigurationService
    ) -> None:
        """Empty history returns total_pages=1."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        rows_result = MagicMock()
        rows_result.all.return_value = []

        session.execute = AsyncMock(
            side_effect=[count_result, rows_result]
        )

        result = await service.get_snapshot_history(
            page=1, page_size=20, session=session
        )

        assert result.total == 0
        assert result.total_pages == 1
        assert result.items == []

    @pytest.mark.asyncio
    async def test_session_required(
        self, service: SystemConfigurationService
    ) -> None:
        """Raises ValueError when session is None."""
        with pytest.raises(ValueError, match="Session is required"):
            await service.get_snapshot_history(page=1, page_size=20, session=None)


class TestSnapshotDiff:
    """Tests for get_snapshot_diff and _compute_diff."""

    def test_compute_diff_detects_changed_values(
        self, service: SystemConfigurationService
    ) -> None:
        """Diff returns keys with different values."""
        snapshot_data = {
            "ai_hardware": {"inference_mode": "mock", "gpu_device_id": 0},
        }
        current_data = {
            "ai_hardware": {"inference_mode": "gpu", "gpu_device_id": 0},
        }

        diff = service._compute_diff(snapshot_data, current_data)

        assert len(diff) == 1
        assert diff[0].key == "ai_hardware.inference_mode"
        assert diff[0].old_value == "mock"
        assert diff[0].new_value == "gpu"

    def test_compute_diff_includes_keys_in_one_state_only(
        self, service: SystemConfigurationService
    ) -> None:
        """Keys present in one state but not the other are included."""
        snapshot_data = {
            "ai_hardware": {"inference_mode": "mock"},
        }
        current_data = {
            "ai_hardware": {"inference_mode": "mock", "new_key": "value"},
        }

        diff = service._compute_diff(snapshot_data, current_data)

        assert len(diff) == 1
        assert diff[0].key == "ai_hardware.new_key"
        assert diff[0].old_value is None
        assert diff[0].new_value == "value"

    def test_compute_diff_excludes_identical_values(
        self, service: SystemConfigurationService
    ) -> None:
        """Keys with identical values are not included in diff."""
        snapshot_data = {
            "ai_hardware": {"inference_mode": "mock", "gpu_device_id": 0},
            "backup_retention": {"retention_days": 30},
        }
        current_data = {
            "ai_hardware": {"inference_mode": "mock", "gpu_device_id": 0},
            "backup_retention": {"retention_days": 30},
        }

        diff = service._compute_diff(snapshot_data, current_data)
        assert diff == []

    def test_compute_diff_handles_missing_categories(
        self, service: SystemConfigurationService
    ) -> None:
        """Diff handles categories present in one state but not the other."""
        snapshot_data = {
            "ai_hardware": {"inference_mode": "mock"},
        }
        current_data = {
            "ai_hardware": {"inference_mode": "mock"},
            "backup_retention": {"retention_days": 60},
        }

        diff = service._compute_diff(snapshot_data, current_data)

        assert len(diff) == 1
        assert diff[0].key == "backup_retention.retention_days"
        assert diff[0].old_value is None
        assert diff[0].new_value == 60


# ---------------------------------------------------------------------------
# Tests: restart_vllm_service with mocked Docker SDK
# ---------------------------------------------------------------------------


class TestRestartVllmService:
    """Tests for restart_vllm_service with mocked Docker SDK."""

    @pytest.mark.asyncio
    async def test_successful_restart(
        self, service: SystemConfigurationService
    ) -> None:
        """Successful Docker restart returns success result."""
        mock_container = MagicMock()
        mock_container.restart = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch.dict(
            "sys.modules", {"docker": MagicMock()}
        ):
            with patch(
                "docker.DockerClient", return_value=mock_client
            ):
                result = await service.restart_vllm_service(
                    user_id=1, reason="Apply config changes"
                )

        assert result.success is True
        assert "successfully" in result.message

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(
        self, service: SystemConfigurationService
    ) -> None:
        """Docker timeout returns failure result with error message."""
        mock_container = MagicMock()
        mock_container.restart.side_effect = Exception(
            "Container restart timed out after 180s"
        )

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        with patch.dict("sys.modules", {"docker": MagicMock()}):
            with patch(
                "docker.DockerClient", return_value=mock_client
            ):
                result = await service.restart_vllm_service(
                    user_id=1, reason="Apply config"
                )

        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_docker_sdk_not_available(
        self, service: SystemConfigurationService
    ) -> None:
        """When docker package is not installed, returns failure."""
        # Simulate ImportError by patching the import inside the method
        with patch.dict("sys.modules", {"docker": None}):
            result = await service.restart_vllm_service(
                user_id=1, reason="Test"
            )

        assert result.success is False
        assert "not available" in result.message or result.error is not None


# ---------------------------------------------------------------------------
# Tests: validate_model_path
# ---------------------------------------------------------------------------


class TestValidateModelPath:
    """Tests for validate_model_path with existing and non-existing paths."""

    def test_existing_path_returns_true(self, tmp_path) -> None:
        """Returns True for a path that exists on the filesystem."""
        model_dir = tmp_path / "models" / "test-model"
        model_dir.mkdir(parents=True)

        assert SystemConfigurationService.validate_model_path(
            str(model_dir)
        ) is True

    def test_existing_file_returns_true(self, tmp_path) -> None:
        """Returns True for a file path that exists."""
        model_file = tmp_path / "model.safetensors"
        model_file.write_text("fake model data")

        assert SystemConfigurationService.validate_model_path(
            str(model_file)
        ) is True

    def test_nonexistent_path_returns_false(self) -> None:
        """Returns False for a path that does not exist."""
        assert SystemConfigurationService.validate_model_path(
            "/nonexistent/path/to/model"
        ) is False

    def test_deeply_nested_nonexistent_path_returns_false(self) -> None:
        """Returns False for a deeply nested path that does not exist."""
        assert SystemConfigurationService.validate_model_path(
            "/tmp/nonexistent/deeply/nested/model/weights"
        ) is False


# ---------------------------------------------------------------------------
# Tests: _validate_snapshot_values
# ---------------------------------------------------------------------------


class TestValidateSnapshotValues:
    """Tests for _validate_snapshot_values rejecting invalid data."""

    def test_valid_snapshot_returns_no_errors(
        self, service: SystemConfigurationService
    ) -> None:
        """Valid snapshot data returns empty error dict."""
        snapshot_data = {
            "ai_hardware": {
                "inference_mode": "gpu",
                "gpu_device_id": 0,
                "model_chat_max_gpu_memory_gb": 24,
                "model_embedding_dimension": 768,
            },
            "backup_retention": {"retention_days": 30},
            "health_check": {
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
        }

        errors = service._validate_snapshot_values(snapshot_data)
        assert errors == {}

    def test_invalid_gpu_device_id(
        self, service: SystemConfigurationService
    ) -> None:
        """Negative gpu_device_id is rejected."""
        snapshot_data = {
            "ai_hardware": {"gpu_device_id": -1},
        }

        errors = service._validate_snapshot_values(snapshot_data)
        assert "ai_hardware.gpu_device_id" in errors

    def test_invalid_inference_mode(
        self, service: SystemConfigurationService
    ) -> None:
        """Invalid inference_mode string is rejected."""
        snapshot_data = {
            "ai_hardware": {"inference_mode": "invalid_mode"},
        }

        errors = service._validate_snapshot_values(snapshot_data)
        assert "ai_hardware.inference_mode" in errors

    def test_invalid_retention_days(
        self, service: SystemConfigurationService
    ) -> None:
        """Retention days outside 1-365 is rejected."""
        snapshot_data = {
            "backup_retention": {"retention_days": 0},
        }
        errors = service._validate_snapshot_values(snapshot_data)
        assert "backup_retention.retention_days" in errors

        snapshot_data = {
            "backup_retention": {"retention_days": 400},
        }
        errors = service._validate_snapshot_values(snapshot_data)
        assert "backup_retention.retention_days" in errors

    def test_invalid_health_check_values(
        self, service: SystemConfigurationService
    ) -> None:
        """Health check values outside valid ranges are rejected."""
        snapshot_data = {
            "health_check": {
                "polling_interval_seconds": 5,  # min is 10
                "degraded_threshold_seconds": 50,  # max is 30
                "unreachable_timeout_seconds": 3,  # min is 5
            },
        }

        errors = service._validate_snapshot_values(snapshot_data)
        assert "health_check.polling_interval_seconds" in errors
        assert "health_check.degraded_threshold_seconds" in errors
        assert "health_check.unreachable_timeout_seconds" in errors

    def test_multiple_errors_reported(
        self, service: SystemConfigurationService
    ) -> None:
        """Multiple validation errors are all reported."""
        snapshot_data = {
            "ai_hardware": {
                "gpu_device_id": -1,
                "model_chat_max_gpu_memory_gb": -5,
            },
            "backup_retention": {"retention_days": 999},
        }

        errors = service._validate_snapshot_values(snapshot_data)
        assert len(errors) >= 3
