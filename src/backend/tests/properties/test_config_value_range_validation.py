"""Property-based tests for configuration value range validation.

Property 3: Configuration Value Range Validation
For any integer value submitted for a range-constrained configuration field,
the system SHALL accept the value if and only if it falls within the defined bounds:
- GPU memory: 1 ≤ value (gt=0, no upper bound in schema)
- Alert threshold: 1 ≤ value ≤ 99
- Retention days: 1 ≤ value ≤ 365
- Health polling interval: 10 ≤ value ≤ 300
- Degraded threshold: 1 ≤ value ≤ 30
- Unreachable timeout: 5 ≤ value ≤ 60

**Validates: Requirements 3.3, 6.2, 8.1, 10.2, 15.1, 15.2, 15.3**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from alcoabase.schemas.system_config import (
    AIHardwareConfigUpdate,
    HealthCheckConfigUpdate,
    RetentionPolicyUpdate,
    StorageQuotaUpdate,
)


# ---------------------------------------------------------------------------
# Property 3: GPU Memory — Valid values accepted (gt=0)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=1, max_value=10000))
def test_gpu_memory_accepts_valid_positive_integers(value: int) -> None:
    """AIHardwareConfigUpdate SHALL accept model_chat_max_gpu_memory_gb
    when value > 0.

    **Validates: Requirements 3.3**
    """
    config = AIHardwareConfigUpdate(model_chat_max_gpu_memory_gb=value)
    assert config.model_chat_max_gpu_memory_gb == value


# ---------------------------------------------------------------------------
# Property 3: GPU Memory — Invalid values rejected (≤ 0)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-10000, max_value=0))
def test_gpu_memory_rejects_non_positive_integers(value: int) -> None:
    """AIHardwareConfigUpdate SHALL reject model_chat_max_gpu_memory_gb
    when value ≤ 0 with a ValidationError.

    **Validates: Requirements 3.3**
    """
    with pytest.raises(ValidationError):
        AIHardwareConfigUpdate(model_chat_max_gpu_memory_gb=value)


# ---------------------------------------------------------------------------
# Property 3: Alert Threshold — Valid values accepted (1 ≤ value ≤ 99)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=1, max_value=99))
def test_alert_threshold_accepts_valid_range(value: int) -> None:
    """StorageQuotaUpdate SHALL accept alert_threshold_pct when 1 ≤ value ≤ 99.

    **Validates: Requirements 6.2**
    """
    config = StorageQuotaUpdate(alert_threshold_pct=value)
    assert config.alert_threshold_pct == value


# ---------------------------------------------------------------------------
# Property 3: Alert Threshold — Invalid values rejected (< 1 or > 99)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-1000, max_value=0))
def test_alert_threshold_rejects_below_minimum(value: int) -> None:
    """StorageQuotaUpdate SHALL reject alert_threshold_pct when value < 1
    with a ValidationError.

    **Validates: Requirements 6.2**
    """
    with pytest.raises(ValidationError):
        StorageQuotaUpdate(alert_threshold_pct=value)


@settings(max_examples=50)
@given(value=st.integers(min_value=100, max_value=1000))
def test_alert_threshold_rejects_above_maximum(value: int) -> None:
    """StorageQuotaUpdate SHALL reject alert_threshold_pct when value > 99
    with a ValidationError.

    **Validates: Requirements 6.2**
    """
    with pytest.raises(ValidationError):
        StorageQuotaUpdate(alert_threshold_pct=value)


# ---------------------------------------------------------------------------
# Property 3: Retention Days — Valid values accepted (1 ≤ value ≤ 365)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=1, max_value=365))
def test_retention_days_accepts_valid_range(value: int) -> None:
    """RetentionPolicyUpdate SHALL accept retention_days when 1 ≤ value ≤ 365.

    **Validates: Requirements 8.1**
    """
    config = RetentionPolicyUpdate(retention_days=value)
    assert config.retention_days == value


# ---------------------------------------------------------------------------
# Property 3: Retention Days — Invalid values rejected (< 1 or > 365)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-1000, max_value=0))
def test_retention_days_rejects_below_minimum(value: int) -> None:
    """RetentionPolicyUpdate SHALL reject retention_days when value < 1
    with a ValidationError.

    **Validates: Requirements 8.1**
    """
    with pytest.raises(ValidationError):
        RetentionPolicyUpdate(retention_days=value)


@settings(max_examples=50)
@given(value=st.integers(min_value=366, max_value=10000))
def test_retention_days_rejects_above_maximum(value: int) -> None:
    """RetentionPolicyUpdate SHALL reject retention_days when value > 365
    with a ValidationError.

    **Validates: Requirements 8.1**
    """
    with pytest.raises(ValidationError):
        RetentionPolicyUpdate(retention_days=value)


# ---------------------------------------------------------------------------
# Property 3: Polling Interval — Valid values accepted (10 ≤ value ≤ 300)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=10, max_value=300))
def test_polling_interval_accepts_valid_range(value: int) -> None:
    """HealthCheckConfigUpdate SHALL accept polling_interval_seconds
    when 10 ≤ value ≤ 300.

    **Validates: Requirements 15.1**
    """
    config = HealthCheckConfigUpdate(
        polling_interval_seconds=value,
        degraded_threshold_seconds=5,
        unreachable_timeout_seconds=10,
    )
    assert config.polling_interval_seconds == value


# ---------------------------------------------------------------------------
# Property 3: Polling Interval — Invalid values rejected (< 10 or > 300)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-1000, max_value=9))
def test_polling_interval_rejects_below_minimum(value: int) -> None:
    """HealthCheckConfigUpdate SHALL reject polling_interval_seconds
    when value < 10 with a ValidationError.

    **Validates: Requirements 15.1**
    """
    with pytest.raises(ValidationError):
        HealthCheckConfigUpdate(
            polling_interval_seconds=value,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )


@settings(max_examples=50)
@given(value=st.integers(min_value=301, max_value=10000))
def test_polling_interval_rejects_above_maximum(value: int) -> None:
    """HealthCheckConfigUpdate SHALL reject polling_interval_seconds
    when value > 300 with a ValidationError.

    **Validates: Requirements 15.1**
    """
    with pytest.raises(ValidationError):
        HealthCheckConfigUpdate(
            polling_interval_seconds=value,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )


# ---------------------------------------------------------------------------
# Property 3: Degraded Threshold — Valid values accepted (1 ≤ value ≤ 30)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=1, max_value=30))
def test_degraded_threshold_accepts_valid_range(value: int) -> None:
    """HealthCheckConfigUpdate SHALL accept degraded_threshold_seconds
    when 1 ≤ value ≤ 30.

    **Validates: Requirements 15.2**
    """
    config = HealthCheckConfigUpdate(
        polling_interval_seconds=30,
        degraded_threshold_seconds=value,
        unreachable_timeout_seconds=10,
    )
    assert config.degraded_threshold_seconds == value


# ---------------------------------------------------------------------------
# Property 3: Degraded Threshold — Invalid values rejected (< 1 or > 30)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-1000, max_value=0))
def test_degraded_threshold_rejects_below_minimum(value: int) -> None:
    """HealthCheckConfigUpdate SHALL reject degraded_threshold_seconds
    when value < 1 with a ValidationError.

    **Validates: Requirements 15.2**
    """
    with pytest.raises(ValidationError):
        HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=value,
            unreachable_timeout_seconds=10,
        )


@settings(max_examples=50)
@given(value=st.integers(min_value=31, max_value=10000))
def test_degraded_threshold_rejects_above_maximum(value: int) -> None:
    """HealthCheckConfigUpdate SHALL reject degraded_threshold_seconds
    when value > 30 with a ValidationError.

    **Validates: Requirements 15.2**
    """
    with pytest.raises(ValidationError):
        HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=value,
            unreachable_timeout_seconds=10,
        )


# ---------------------------------------------------------------------------
# Property 3: Unreachable Timeout — Valid values accepted (5 ≤ value ≤ 60)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=5, max_value=60))
def test_unreachable_timeout_accepts_valid_range(value: int) -> None:
    """HealthCheckConfigUpdate SHALL accept unreachable_timeout_seconds
    when 5 ≤ value ≤ 60.

    **Validates: Requirements 15.3**
    """
    config = HealthCheckConfigUpdate(
        polling_interval_seconds=30,
        degraded_threshold_seconds=5,
        unreachable_timeout_seconds=value,
    )
    assert config.unreachable_timeout_seconds == value


# ---------------------------------------------------------------------------
# Property 3: Unreachable Timeout — Invalid values rejected (< 5 or > 60)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-1000, max_value=4))
def test_unreachable_timeout_rejects_below_minimum(value: int) -> None:
    """HealthCheckConfigUpdate SHALL reject unreachable_timeout_seconds
    when value < 5 with a ValidationError.

    **Validates: Requirements 15.3**
    """
    with pytest.raises(ValidationError):
        HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=value,
        )


@settings(max_examples=50)
@given(value=st.integers(min_value=61, max_value=10000))
def test_unreachable_timeout_rejects_above_maximum(value: int) -> None:
    """HealthCheckConfigUpdate SHALL reject unreachable_timeout_seconds
    when value > 60 with a ValidationError.

    **Validates: Requirements 15.3**
    """
    with pytest.raises(ValidationError):
        HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=value,
        )


# ---------------------------------------------------------------------------
# Property 3: Combined — All HealthCheckConfig fields valid simultaneously
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    polling=st.integers(min_value=10, max_value=300),
    degraded=st.integers(min_value=1, max_value=30),
    unreachable=st.integers(min_value=5, max_value=60),
)
def test_health_check_config_accepts_all_valid_fields(
    polling: int,
    degraded: int,
    unreachable: int,
) -> None:
    """HealthCheckConfigUpdate SHALL accept all fields simultaneously when
    each is within its defined bounds.

    **Validates: Requirements 10.2, 15.1, 15.2, 15.3**
    """
    config = HealthCheckConfigUpdate(
        polling_interval_seconds=polling,
        degraded_threshold_seconds=degraded,
        unreachable_timeout_seconds=unreachable,
    )
    assert config.polling_interval_seconds == polling
    assert config.degraded_threshold_seconds == degraded
    assert config.unreachable_timeout_seconds == unreachable
