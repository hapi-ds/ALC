"""Unit tests for system configuration Pydantic schemas.

Tests validation rules for AIHardwareConfigUpdate, StorageQuotaUpdate,
BackupScheduleUpdate, RetentionPolicyUpdate, and HealthCheckConfigUpdate.

References:
    - Requirements 3.2: inference_mode Literal validation
    - Requirements 3.3: gpu_memory gt=0
    - Requirements 6.2: alert_threshold 1-99
    - Requirements 8.1: retention_days 1-365
    - Requirements 15.1: polling_interval 10-300
    - Requirements 15.2: degraded_threshold 1-30
    - Requirements 15.3: unreachable_timeout 5-60
"""

import pytest
from pydantic import ValidationError

from alcoabase.schemas.system_config import (
    AIHardwareConfigUpdate,
    BackupScheduleUpdate,
    HealthCheckConfigUpdate,
    RetentionPolicyUpdate,
    StorageQuotaUpdate,
)


# ---------------------------------------------------------------------------
# AIHardwareConfigUpdate Tests
# ---------------------------------------------------------------------------


class TestAIHardwareConfigUpdate:
    """Tests for AIHardwareConfigUpdate validation."""

    def test_valid_full_update(self) -> None:
        req = AIHardwareConfigUpdate(
            model_chat_name="gemma-4",
            model_chat_path="/models/gemma-4",
            model_chat_max_gpu_memory_gb=24,
            model_embedding_name="bge-small",
            model_embedding_path="/models/bge-small",
            model_embedding_dimension=384,
            model_ocr_name="ocr-model",
            model_ocr_path="/models/ocr",
            inference_mode="gpu",
            gpu_device_id=0,
        )
        assert req.model_chat_name == "gemma-4"
        assert req.model_chat_max_gpu_memory_gb == 24
        assert req.inference_mode == "gpu"

    def test_all_fields_optional(self) -> None:
        req = AIHardwareConfigUpdate()
        assert req.model_chat_name is None
        assert req.model_chat_path is None
        assert req.model_chat_max_gpu_memory_gb is None
        assert req.model_embedding_name is None
        assert req.model_embedding_path is None
        assert req.model_embedding_dimension is None
        assert req.model_ocr_name is None
        assert req.model_ocr_path is None
        assert req.inference_mode is None
        assert req.gpu_device_id is None

    def test_partial_update_single_field(self) -> None:
        req = AIHardwareConfigUpdate(model_chat_name="new-model")
        assert req.model_chat_name == "new-model"
        assert req.model_chat_path is None

    # --- inference_mode Literal validation (Requirement 3.2) ---

    def test_inference_mode_gpu_accepted(self) -> None:
        req = AIHardwareConfigUpdate(inference_mode="gpu")
        assert req.inference_mode == "gpu"

    def test_inference_mode_cpu_accepted(self) -> None:
        req = AIHardwareConfigUpdate(inference_mode="cpu")
        assert req.inference_mode == "cpu"

    def test_inference_mode_mock_accepted(self) -> None:
        req = AIHardwareConfigUpdate(inference_mode="mock")
        assert req.inference_mode == "mock"

    def test_inference_mode_invalid_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(inference_mode="tpu")  # type: ignore[arg-type]

    def test_inference_mode_empty_string_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(inference_mode="")  # type: ignore[arg-type]

    def test_inference_mode_uppercase_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(inference_mode="GPU")  # type: ignore[arg-type]

    def test_inference_mode_mixed_case_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(inference_mode="Gpu")  # type: ignore[arg-type]

    # --- gpu_memory gt=0 (Requirement 3.3) ---

    def test_gpu_memory_positive_accepted(self) -> None:
        req = AIHardwareConfigUpdate(model_chat_max_gpu_memory_gb=1)
        assert req.model_chat_max_gpu_memory_gb == 1

    def test_gpu_memory_large_value_accepted(self) -> None:
        req = AIHardwareConfigUpdate(model_chat_max_gpu_memory_gb=80)
        assert req.model_chat_max_gpu_memory_gb == 80

    def test_gpu_memory_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(model_chat_max_gpu_memory_gb=0)

    def test_gpu_memory_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(model_chat_max_gpu_memory_gb=-1)

    # --- embedding_dimension gt=0 ---

    def test_embedding_dimension_positive_accepted(self) -> None:
        req = AIHardwareConfigUpdate(model_embedding_dimension=768)
        assert req.model_embedding_dimension == 768

    def test_embedding_dimension_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(model_embedding_dimension=0)

    def test_embedding_dimension_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(model_embedding_dimension=-512)

    # --- gpu_device_id ge=0 ---

    def test_gpu_device_id_zero_accepted(self) -> None:
        req = AIHardwareConfigUpdate(gpu_device_id=0)
        assert req.gpu_device_id == 0

    def test_gpu_device_id_positive_accepted(self) -> None:
        req = AIHardwareConfigUpdate(gpu_device_id=3)
        assert req.gpu_device_id == 3

    def test_gpu_device_id_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AIHardwareConfigUpdate(gpu_device_id=-1)

    # --- Serialization ---

    def test_serialization_round_trip(self) -> None:
        req = AIHardwareConfigUpdate(
            model_chat_name="gemma-4",
            model_chat_max_gpu_memory_gb=24,
            inference_mode="gpu",
            gpu_device_id=0,
        )
        data = req.model_dump()
        restored = AIHardwareConfigUpdate(**data)
        assert restored == req

    def test_json_serialization_round_trip(self) -> None:
        req = AIHardwareConfigUpdate(
            model_chat_name="test-model",
            model_chat_path="/models/test",
            inference_mode="mock",
        )
        json_str = req.model_dump_json()
        restored = AIHardwareConfigUpdate.model_validate_json(json_str)
        assert restored == req

    def test_model_dump_excludes_none(self) -> None:
        req = AIHardwareConfigUpdate(inference_mode="cpu")
        data = req.model_dump(exclude_none=True)
        assert "inference_mode" in data
        assert "model_chat_name" not in data


# ---------------------------------------------------------------------------
# StorageQuotaUpdate Tests
# ---------------------------------------------------------------------------


class TestStorageQuotaUpdate:
    """Tests for StorageQuotaUpdate validation."""

    def test_valid_full_update(self) -> None:
        req = StorageQuotaUpdate(
            quota_limit_bytes=1073741824,
            alert_threshold_pct=80,
        )
        assert req.quota_limit_bytes == 1073741824
        assert req.alert_threshold_pct == 80

    def test_all_fields_optional(self) -> None:
        req = StorageQuotaUpdate()
        assert req.quota_limit_bytes is None
        assert req.alert_threshold_pct is None

    # --- quota_limit_bytes gt=0 ---

    def test_quota_limit_positive_accepted(self) -> None:
        req = StorageQuotaUpdate(quota_limit_bytes=1)
        assert req.quota_limit_bytes == 1

    def test_quota_limit_large_value_accepted(self) -> None:
        req = StorageQuotaUpdate(quota_limit_bytes=10_000_000_000_000)
        assert req.quota_limit_bytes == 10_000_000_000_000

    def test_quota_limit_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StorageQuotaUpdate(quota_limit_bytes=0)

    def test_quota_limit_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StorageQuotaUpdate(quota_limit_bytes=-100)

    # --- alert_threshold_pct 1-99 (Requirement 6.2) ---

    def test_alert_threshold_lower_bound_accepted(self) -> None:
        req = StorageQuotaUpdate(alert_threshold_pct=1)
        assert req.alert_threshold_pct == 1

    def test_alert_threshold_upper_bound_accepted(self) -> None:
        req = StorageQuotaUpdate(alert_threshold_pct=99)
        assert req.alert_threshold_pct == 99

    def test_alert_threshold_mid_value_accepted(self) -> None:
        req = StorageQuotaUpdate(alert_threshold_pct=50)
        assert req.alert_threshold_pct == 50

    def test_alert_threshold_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StorageQuotaUpdate(alert_threshold_pct=0)

    def test_alert_threshold_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StorageQuotaUpdate(alert_threshold_pct=100)

    def test_alert_threshold_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StorageQuotaUpdate(alert_threshold_pct=-1)

    # --- Serialization ---

    def test_serialization_round_trip(self) -> None:
        req = StorageQuotaUpdate(quota_limit_bytes=5000, alert_threshold_pct=75)
        data = req.model_dump()
        restored = StorageQuotaUpdate(**data)
        assert restored == req

    def test_json_serialization_round_trip(self) -> None:
        req = StorageQuotaUpdate(alert_threshold_pct=90)
        json_str = req.model_dump_json()
        restored = StorageQuotaUpdate.model_validate_json(json_str)
        assert restored == req


# ---------------------------------------------------------------------------
# BackupScheduleUpdate Tests
# ---------------------------------------------------------------------------


class TestBackupScheduleUpdate:
    """Tests for BackupScheduleUpdate validation."""

    def test_valid_cron_expression(self) -> None:
        req = BackupScheduleUpdate(cron_expression="0 2 * * *")
        assert req.cron_expression == "0 2 * * *"

    def test_valid_complex_cron(self) -> None:
        req = BackupScheduleUpdate(cron_expression="30 1 */2 * 1-5")
        assert req.cron_expression == "30 1 */2 * 1-5"

    def test_cron_min_length_9_accepted(self) -> None:
        # Minimum valid: "* * * * *" is 9 chars
        req = BackupScheduleUpdate(cron_expression="* * * * *")
        assert req.cron_expression == "* * * * *"

    def test_cron_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BackupScheduleUpdate(cron_expression="0 2 * *")  # 7 chars

    def test_cron_max_length_100_accepted(self) -> None:
        # Pad a valid cron with spaces to reach 100 chars
        cron = "0 2 * * *" + " " * 91
        req = BackupScheduleUpdate(cron_expression=cron)
        assert len(req.cron_expression) == 100

    def test_cron_exceeds_100_rejected(self) -> None:
        cron = "0 2 * * *" + " " * 92  # 101 chars
        with pytest.raises(ValidationError):
            BackupScheduleUpdate(cron_expression=cron)

    def test_cron_empty_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BackupScheduleUpdate(cron_expression="")

    def test_cron_required_field(self) -> None:
        with pytest.raises(ValidationError):
            BackupScheduleUpdate()  # type: ignore[call-arg]

    # --- Serialization ---

    def test_serialization_round_trip(self) -> None:
        req = BackupScheduleUpdate(cron_expression="0 3 * * 0")
        data = req.model_dump()
        restored = BackupScheduleUpdate(**data)
        assert restored == req

    def test_json_serialization_round_trip(self) -> None:
        req = BackupScheduleUpdate(cron_expression="0 2 * * *")
        json_str = req.model_dump_json()
        restored = BackupScheduleUpdate.model_validate_json(json_str)
        assert restored == req


# ---------------------------------------------------------------------------
# RetentionPolicyUpdate Tests
# ---------------------------------------------------------------------------


class TestRetentionPolicyUpdate:
    """Tests for RetentionPolicyUpdate validation."""

    # --- retention_days 1-365 (Requirement 8.1) ---

    def test_retention_days_lower_bound_accepted(self) -> None:
        req = RetentionPolicyUpdate(retention_days=1)
        assert req.retention_days == 1

    def test_retention_days_upper_bound_accepted(self) -> None:
        req = RetentionPolicyUpdate(retention_days=365)
        assert req.retention_days == 365

    def test_retention_days_mid_value_accepted(self) -> None:
        req = RetentionPolicyUpdate(retention_days=30)
        assert req.retention_days == 30

    def test_retention_days_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicyUpdate(retention_days=0)

    def test_retention_days_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicyUpdate(retention_days=-1)

    def test_retention_days_366_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicyUpdate(retention_days=366)

    def test_retention_days_large_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicyUpdate(retention_days=1000)

    def test_retention_days_required(self) -> None:
        with pytest.raises(ValidationError):
            RetentionPolicyUpdate()  # type: ignore[call-arg]

    # --- Serialization ---

    def test_serialization_round_trip(self) -> None:
        req = RetentionPolicyUpdate(retention_days=90)
        data = req.model_dump()
        restored = RetentionPolicyUpdate(**data)
        assert restored == req

    def test_json_serialization_round_trip(self) -> None:
        req = RetentionPolicyUpdate(retention_days=180)
        json_str = req.model_dump_json()
        restored = RetentionPolicyUpdate.model_validate_json(json_str)
        assert restored == req


# ---------------------------------------------------------------------------
# HealthCheckConfigUpdate Tests
# ---------------------------------------------------------------------------


class TestHealthCheckConfigUpdate:
    """Tests for HealthCheckConfigUpdate validation."""

    def test_valid_full_config(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )
        assert req.polling_interval_seconds == 30
        assert req.degraded_threshold_seconds == 5
        assert req.unreachable_timeout_seconds == 10

    # --- polling_interval_seconds 10-300 (Requirement 15.1) ---

    def test_polling_interval_lower_bound_accepted(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=10,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )
        assert req.polling_interval_seconds == 10

    def test_polling_interval_upper_bound_accepted(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=300,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )
        assert req.polling_interval_seconds == 300

    def test_polling_interval_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=9,
                degraded_threshold_seconds=5,
                unreachable_timeout_seconds=10,
            )

    def test_polling_interval_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=301,
                degraded_threshold_seconds=5,
                unreachable_timeout_seconds=10,
            )

    # --- degraded_threshold_seconds 1-30 (Requirement 15.2) ---

    def test_degraded_threshold_lower_bound_accepted(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=1,
            unreachable_timeout_seconds=10,
        )
        assert req.degraded_threshold_seconds == 1

    def test_degraded_threshold_upper_bound_accepted(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=30,
            unreachable_timeout_seconds=10,
        )
        assert req.degraded_threshold_seconds == 30

    def test_degraded_threshold_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=30,
                degraded_threshold_seconds=0,
                unreachable_timeout_seconds=10,
            )

    def test_degraded_threshold_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=30,
                degraded_threshold_seconds=31,
                unreachable_timeout_seconds=10,
            )

    # --- unreachable_timeout_seconds 5-60 (Requirement 15.3) ---

    def test_unreachable_timeout_lower_bound_accepted(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=5,
        )
        assert req.unreachable_timeout_seconds == 5

    def test_unreachable_timeout_upper_bound_accepted(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=60,
        )
        assert req.unreachable_timeout_seconds == 60

    def test_unreachable_timeout_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=30,
                degraded_threshold_seconds=5,
                unreachable_timeout_seconds=4,
            )

    def test_unreachable_timeout_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=30,
                degraded_threshold_seconds=5,
                unreachable_timeout_seconds=61,
            )

    # --- All fields required ---

    def test_missing_all_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate()  # type: ignore[call-arg]

    def test_missing_polling_interval_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                degraded_threshold_seconds=5,
                unreachable_timeout_seconds=10,
            )  # type: ignore[call-arg]

    def test_missing_degraded_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=30,
                unreachable_timeout_seconds=10,
            )  # type: ignore[call-arg]

    def test_missing_unreachable_timeout_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HealthCheckConfigUpdate(
                polling_interval_seconds=30,
                degraded_threshold_seconds=5,
            )  # type: ignore[call-arg]

    # --- Serialization ---

    def test_serialization_round_trip(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=60,
            degraded_threshold_seconds=10,
            unreachable_timeout_seconds=30,
        )
        data = req.model_dump()
        restored = HealthCheckConfigUpdate(**data)
        assert restored == req

    def test_json_serialization_round_trip(self) -> None:
        req = HealthCheckConfigUpdate(
            polling_interval_seconds=120,
            degraded_threshold_seconds=15,
            unreachable_timeout_seconds=45,
        )
        json_str = req.model_dump_json()
        restored = HealthCheckConfigUpdate.model_validate_json(json_str)
        assert restored == req
