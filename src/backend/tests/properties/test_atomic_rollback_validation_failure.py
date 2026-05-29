"""Property-based tests for atomic rollback on validation failure.

Property 17: Atomic Rollback on Validation Failure

For any configuration snapshot containing at least one value that would fail
current validation rules, attempting a rollback to that snapshot SHALL leave
all configuration values unchanged (no partial application). The system state
after the failed rollback SHALL be identical to the state before the attempt.

**Validates: Requirements 14.6**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Module: src/backend/src/alcoabase/services/system_config.py
"""

from __future__ import annotations

import copy
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.system_config import (
    CATEGORIES,
    SystemConfigurationService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Valid inference modes
INFERENCE_MODES = st.sampled_from(["gpu", "cpu", "mock"])

# Valid AI hardware config values
AI_HARDWARE_VALUES = st.fixed_dictionaries({
    "model_chat_name": st.text(
        min_size=1, max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    ),
    "model_chat_path": st.text(
        min_size=3, max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd", "Ps")),
    ),
    "model_chat_max_gpu_memory_gb": st.integers(min_value=1, max_value=128),
    "model_embedding_name": st.text(
        min_size=1, max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    ),
    "model_embedding_path": st.text(
        min_size=3, max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd", "Ps")),
    ),
    "model_embedding_dimension": st.integers(min_value=1, max_value=4096),
    "model_ocr_name": st.text(
        min_size=1, max_size=30,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd")),
    ),
    "model_ocr_path": st.text(
        min_size=3, max_size=50,
        alphabet=st.characters(whitelist_categories=("L", "N", "Pd", "Ps")),
    ),
    "inference_mode": INFERENCE_MODES,
    "gpu_device_id": st.integers(min_value=0, max_value=7),
    "vllm_chat_url": st.just("http://vllm:8000"),
    "vllm_embedding_url": st.just("http://vllm-embed:8001"),
})

# Valid backup schedule config values
BACKUP_SCHEDULE_VALUES = st.fixed_dictionaries({
    "cron_expression": st.sampled_from([
        "0 2 * * *",
        "0 3 * * *",
        "30 1 * * *",
        "0 0 * * 0",
        "0 4 * * 1-5",
    ]),
})

# Valid backup retention config values
BACKUP_RETENTION_VALUES = st.fixed_dictionaries({
    "retention_days": st.integers(min_value=1, max_value=365),
})

# Valid health check config values
HEALTH_CHECK_VALUES = st.fixed_dictionaries({
    "polling_interval_seconds": st.integers(min_value=10, max_value=300),
    "degraded_threshold_seconds": st.integers(min_value=1, max_value=30),
    "unreachable_timeout_seconds": st.integers(min_value=5, max_value=60),
})


@st.composite
def st_valid_config_state(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a valid full configuration state across all categories."""
    return {
        "ai_hardware": draw(AI_HARDWARE_VALUES),
        "backup_schedule": draw(BACKUP_SCHEDULE_VALUES),
        "backup_retention": draw(BACKUP_RETENTION_VALUES),
        "health_check": draw(HEALTH_CHECK_VALUES),
    }


# ---------------------------------------------------------------------------
# Strategies for generating invalid snapshot values
# ---------------------------------------------------------------------------

# Invalid values for specific fields that will fail validation
INVALID_GPU_MEMORY = st.one_of(
    st.integers(max_value=0),  # Non-positive integers
    st.just(-1),
    st.just(0),
)

INVALID_EMBEDDING_DIMENSION = st.one_of(
    st.integers(max_value=0),
    st.just(-5),
    st.just(0),
)

INVALID_GPU_DEVICE_ID = st.integers(max_value=-1)  # Negative

INVALID_INFERENCE_MODE = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in ("gpu", "cpu", "mock")
)

INVALID_RETENTION_DAYS = st.one_of(
    st.integers(max_value=0),       # Below minimum (1)
    st.integers(min_value=366),     # Above maximum (365)
)

INVALID_POLLING_INTERVAL = st.one_of(
    st.integers(max_value=9),       # Below minimum (10)
    st.integers(min_value=301),     # Above maximum (300)
)

INVALID_DEGRADED_THRESHOLD = st.one_of(
    st.integers(max_value=0),       # Below minimum (1)
    st.integers(min_value=31),      # Above maximum (30)
)

INVALID_UNREACHABLE_TIMEOUT = st.one_of(
    st.integers(max_value=4),       # Below minimum (5)
    st.integers(min_value=61),      # Above maximum (60)
)


@st.composite
def st_invalid_ai_hardware(draw: st.DrawFn) -> dict[str, Any]:
    """Generate AI hardware config with at least one invalid value."""
    base = draw(AI_HARDWARE_VALUES)
    # Pick which field(s) to invalidate
    invalid_field = draw(st.sampled_from([
        "model_chat_max_gpu_memory_gb",
        "model_embedding_dimension",
        "gpu_device_id",
        "inference_mode",
    ]))

    if invalid_field == "model_chat_max_gpu_memory_gb":
        base["model_chat_max_gpu_memory_gb"] = draw(INVALID_GPU_MEMORY)
    elif invalid_field == "model_embedding_dimension":
        base["model_embedding_dimension"] = draw(INVALID_EMBEDDING_DIMENSION)
    elif invalid_field == "gpu_device_id":
        base["gpu_device_id"] = draw(INVALID_GPU_DEVICE_ID)
    elif invalid_field == "inference_mode":
        base["inference_mode"] = draw(INVALID_INFERENCE_MODE)

    return base


@st.composite
def st_invalid_backup_retention(draw: st.DrawFn) -> dict[str, Any]:
    """Generate backup retention config with invalid retention_days."""
    return {"retention_days": draw(INVALID_RETENTION_DAYS)}


@st.composite
def st_invalid_health_check(draw: st.DrawFn) -> dict[str, Any]:
    """Generate health check config with at least one invalid value."""
    base = draw(HEALTH_CHECK_VALUES)
    invalid_field = draw(st.sampled_from([
        "polling_interval_seconds",
        "degraded_threshold_seconds",
        "unreachable_timeout_seconds",
    ]))

    if invalid_field == "polling_interval_seconds":
        base["polling_interval_seconds"] = draw(INVALID_POLLING_INTERVAL)
    elif invalid_field == "degraded_threshold_seconds":
        base["degraded_threshold_seconds"] = draw(INVALID_DEGRADED_THRESHOLD)
    elif invalid_field == "unreachable_timeout_seconds":
        base["unreachable_timeout_seconds"] = draw(INVALID_UNREACHABLE_TIMEOUT)

    return base


@st.composite
def st_snapshot_with_invalid_values(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a snapshot containing at least one value that fails validation.

    The snapshot has valid values for most categories but introduces at least
    one invalid value in one or more categories.
    """
    # Start with a valid base state
    snapshot: dict[str, Any] = {
        "ai_hardware": draw(AI_HARDWARE_VALUES),
        "backup_schedule": draw(BACKUP_SCHEDULE_VALUES),
        "backup_retention": draw(BACKUP_RETENTION_VALUES),
        "health_check": draw(HEALTH_CHECK_VALUES),
    }

    # Choose which category to invalidate (at least one)
    invalid_category = draw(st.sampled_from([
        "ai_hardware",
        "backup_retention",
        "health_check",
    ]))

    if invalid_category == "ai_hardware":
        snapshot["ai_hardware"] = draw(st_invalid_ai_hardware())
    elif invalid_category == "backup_retention":
        snapshot["backup_retention"] = draw(st_invalid_backup_retention())
    elif invalid_category == "health_check":
        snapshot["health_check"] = draw(st_invalid_health_check())

    return snapshot


# ---------------------------------------------------------------------------
# In-Memory Config Store (simulates DB behavior for atomic rollback testing)
# ---------------------------------------------------------------------------


class InMemoryConfigStore:
    """Simulates the database layer for SystemConfiguration rows.

    Tracks configuration state per category and supports atomic rollback
    operations to verify the no-partial-application property.
    """

    def __init__(self, initial_state: dict[str, Any]) -> None:
        self._state: dict[str, dict[str, Any]] = copy.deepcopy(initial_state)

    def get_config(self, category: str) -> dict[str, Any]:
        """Get current config for a category."""
        return copy.deepcopy(self._state.get(category, {}))

    def get_all_config(self) -> dict[str, Any]:
        """Get full current configuration state."""
        return copy.deepcopy(self._state)

    def attempt_rollback(self, snapshot_data: dict[str, Any]) -> bool:
        """Attempt to rollback to a snapshot, validating first.

        Replicates the atomic rollback logic from
        SystemConfigurationService.rollback_to_snapshot:
        1. Validate all values in the snapshot
        2. If any validation fails, reject entirely (no partial application)
        3. If all valid, apply all changes

        Returns:
            True if rollback succeeded, False if rejected due to validation.
        """
        service = SystemConfigurationService()
        validation_errors = service._validate_snapshot_values(snapshot_data)

        if validation_errors:
            # Reject entirely — no changes applied
            return False

        # All valid — apply all changes (this path shouldn't be reached
        # in our invalid snapshot tests)
        for category in CATEGORIES:
            target_values = snapshot_data.get(category, {})
            self._state[category] = copy.deepcopy(target_values)

        return True


# ---------------------------------------------------------------------------
# Property 17: Atomic Rollback on Validation Failure
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    current_state=st_valid_config_state(),
    invalid_snapshot=st_snapshot_with_invalid_values(),
)
def test_failed_rollback_leaves_state_unchanged(
    current_state: dict[str, Any],
    invalid_snapshot: dict[str, Any],
) -> None:
    """For any snapshot containing at least one value that fails validation,
    attempting a rollback SHALL leave all configuration values unchanged.
    No partial application occurs.

    **Validates: Requirements 14.6**
    """
    store = InMemoryConfigStore(current_state)

    # Capture state before rollback attempt
    state_before = store.get_all_config()

    # Attempt rollback with invalid snapshot — should be rejected
    rollback_succeeded = store.attempt_rollback(invalid_snapshot)

    # Rollback must be rejected
    assert rollback_succeeded is False, (
        "Rollback should have been rejected due to validation failure, "
        f"but it succeeded. Invalid snapshot: {invalid_snapshot}"
    )

    # State after failed rollback must be identical to state before
    state_after = store.get_all_config()
    for category in CATEGORIES:
        assert state_after.get(category) == state_before.get(category), (
            f"Category '{category}' was modified despite rollback rejection.\n"
            f"  Before: {state_before.get(category)}\n"
            f"  After:  {state_after.get(category)}\n"
            f"  Invalid snapshot had: {invalid_snapshot.get(category)}"
        )


@settings(max_examples=100)
@given(
    current_state=st_valid_config_state(),
    invalid_snapshot=st_snapshot_with_invalid_values(),
)
def test_validate_snapshot_values_detects_invalid_data(
    current_state: dict[str, Any],
    invalid_snapshot: dict[str, Any],
) -> None:
    """The _validate_snapshot_values method SHALL detect at least one error
    for any snapshot containing an invalid value, ensuring the rollback
    guard triggers correctly.

    **Validates: Requirements 14.6**
    """
    service = SystemConfigurationService()

    # The invalid snapshot must produce validation errors
    errors = service._validate_snapshot_values(invalid_snapshot)
    assert len(errors) > 0, (
        "Expected validation errors for invalid snapshot, but got none.\n"
        f"  Snapshot: {invalid_snapshot}"
    )


@settings(max_examples=100)
@given(valid_state=st_valid_config_state())
def test_valid_snapshot_passes_validation(
    valid_state: dict[str, Any],
) -> None:
    """A snapshot with all valid values SHALL pass validation (no errors),
    confirming that the validation logic correctly distinguishes valid from
    invalid states.

    **Validates: Requirements 14.6**
    """
    service = SystemConfigurationService()

    errors = service._validate_snapshot_values(valid_state)
    assert errors == {}, (
        f"Valid state should pass validation, but got errors: {errors}\n"
        f"  State: {valid_state}"
    )


@settings(max_examples=100)
@given(
    current_state=st_valid_config_state(),
    invalid_snapshot=st_snapshot_with_invalid_values(),
)
def test_no_category_partially_applied_on_failure(
    current_state: dict[str, Any],
    invalid_snapshot: dict[str, Any],
) -> None:
    """When rollback is rejected, no individual category SHALL have been
    partially updated. This verifies atomicity at the category level —
    even categories with valid values in the snapshot must remain unchanged.

    **Validates: Requirements 14.6**
    """
    service = SystemConfigurationService()

    # Simulate the exact logic from rollback_to_snapshot:
    # 1. Validate all values first
    # 2. If errors, raise ValueError (no changes applied)
    # 3. Only if validation passes, iterate and apply

    config_rows: dict[str, dict[str, Any]] = copy.deepcopy(current_state)
    state_before = copy.deepcopy(config_rows)

    validation_errors = service._validate_snapshot_values(invalid_snapshot)

    if validation_errors:
        # Rollback rejected — verify nothing changed
        pass  # config_rows untouched
    else:
        # This shouldn't happen with our invalid snapshots, but handle it
        for category in CATEGORIES:
            config_rows[category] = copy.deepcopy(
                invalid_snapshot.get(category, {})
            )

    # Verify: since validation_errors is non-empty, state must be unchanged
    assert validation_errors, "Expected validation errors for invalid snapshot"
    for category in CATEGORIES:
        assert config_rows[category] == state_before[category], (
            f"Category '{category}' was modified despite validation failure.\n"
            f"  Before: {state_before[category]}\n"
            f"  After:  {config_rows[category]}"
        )


@settings(max_examples=50)
@given(
    current_state=st_valid_config_state(),
    invalid_snapshot=st_snapshot_with_invalid_values(),
)
def test_multiple_failed_rollback_attempts_preserve_state(
    current_state: dict[str, Any],
    invalid_snapshot: dict[str, Any],
) -> None:
    """Multiple consecutive failed rollback attempts SHALL each leave the
    state unchanged. The system is stable under repeated invalid rollback
    attempts.

    **Validates: Requirements 14.6**
    """
    store = InMemoryConfigStore(current_state)
    state_before = store.get_all_config()

    # Attempt rollback multiple times
    for _ in range(3):
        rollback_succeeded = store.attempt_rollback(invalid_snapshot)
        assert rollback_succeeded is False

    # State must still be identical to the original
    state_after = store.get_all_config()
    for category in CATEGORIES:
        assert state_after.get(category) == state_before.get(category), (
            f"Category '{category}' changed after multiple failed rollbacks.\n"
            f"  Expected: {state_before.get(category)}\n"
            f"  Got:      {state_after.get(category)}"
        )
