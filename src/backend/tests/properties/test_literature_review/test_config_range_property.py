"""Property-based tests for screening configuration range enforcement.

Property 15: Configuration range enforcement
For any configuration value submitted to ScreeningConfigService._validate_ranges(),
the system SHALL reject values outside the defined bounds with ConfigurationRangeError
and accept values within bounds without error.

Valid ranges:
- default_batch_size: 1–100
- confidence_threshold_for_auto_include: 0.5–1.0
- max_concurrent_screening_tasks: 1–20

**Validates: Requirements 11.6**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.review.exceptions import ConfigurationRangeError
from alcoabase.literature.review.services.screening_config_service import (
    ScreeningConfigService,
)


# ---------------------------------------------------------------------------
# Property 15: default_batch_size — Valid values accepted (1 ≤ value ≤ 100)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=1, max_value=100))
def test_batch_size_accepts_valid_range(value: int) -> None:
    """_validate_ranges SHALL accept default_batch_size when 1 ≤ value ≤ 100.

    **Validates: Requirements 11.6**
    """
    data = {"default_batch_size": value}
    # Should not raise
    ScreeningConfigService._validate_ranges(data)


# ---------------------------------------------------------------------------
# Property 15: default_batch_size — Below minimum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-10000, max_value=0))
def test_batch_size_rejects_below_minimum(value: int) -> None:
    """_validate_ranges SHALL reject default_batch_size when value < 1
    with ConfigurationRangeError.

    **Validates: Requirements 11.6**
    """
    data = {"default_batch_size": value}
    with pytest.raises(ConfigurationRangeError) as exc_info:
        ScreeningConfigService._validate_ranges(data)
    assert exc_info.value.field_name == "default_batch_size"
    assert exc_info.value.value == value
    assert exc_info.value.min_value == 1
    assert exc_info.value.max_value == 100


# ---------------------------------------------------------------------------
# Property 15: default_batch_size — Above maximum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=101, max_value=10000))
def test_batch_size_rejects_above_maximum(value: int) -> None:
    """_validate_ranges SHALL reject default_batch_size when value > 100
    with ConfigurationRangeError.

    **Validates: Requirements 11.6**
    """
    data = {"default_batch_size": value}
    with pytest.raises(ConfigurationRangeError) as exc_info:
        ScreeningConfigService._validate_ranges(data)
    assert exc_info.value.field_name == "default_batch_size"
    assert exc_info.value.value == value


# ---------------------------------------------------------------------------
# Property 15: confidence_threshold — Valid values accepted (0.5 ≤ value ≤ 1.0)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.floats(min_value=0.5, max_value=1.0, allow_nan=False))
def test_confidence_threshold_accepts_valid_range(value: float) -> None:
    """_validate_ranges SHALL accept confidence_threshold_for_auto_include
    when 0.5 ≤ value ≤ 1.0.

    **Validates: Requirements 11.6**
    """
    data = {"confidence_threshold_for_auto_include": value}
    # Should not raise
    ScreeningConfigService._validate_ranges(data)


# ---------------------------------------------------------------------------
# Property 15: confidence_threshold — Below minimum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    value=st.floats(
        min_value=-100.0,
        max_value=0.4999999,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_confidence_threshold_rejects_below_minimum(value: float) -> None:
    """_validate_ranges SHALL reject confidence_threshold_for_auto_include
    when value < 0.5 with ConfigurationRangeError.

    **Validates: Requirements 11.6**
    """
    data = {"confidence_threshold_for_auto_include": value}
    with pytest.raises(ConfigurationRangeError) as exc_info:
        ScreeningConfigService._validate_ranges(data)
    assert exc_info.value.field_name == "confidence_threshold_for_auto_include"
    assert exc_info.value.value == value
    assert exc_info.value.min_value == 0.5
    assert exc_info.value.max_value == 1.0


# ---------------------------------------------------------------------------
# Property 15: confidence_threshold — Above maximum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    value=st.floats(
        min_value=1.0000001,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_confidence_threshold_rejects_above_maximum(value: float) -> None:
    """_validate_ranges SHALL reject confidence_threshold_for_auto_include
    when value > 1.0 with ConfigurationRangeError.

    **Validates: Requirements 11.6**
    """
    data = {"confidence_threshold_for_auto_include": value}
    with pytest.raises(ConfigurationRangeError) as exc_info:
        ScreeningConfigService._validate_ranges(data)
    assert exc_info.value.field_name == "confidence_threshold_for_auto_include"
    assert exc_info.value.value == value


# ---------------------------------------------------------------------------
# Property 15: max_concurrent — Valid values accepted (1 ≤ value ≤ 20)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=1, max_value=20))
def test_max_concurrent_accepts_valid_range(value: int) -> None:
    """_validate_ranges SHALL accept max_concurrent_screening_tasks
    when 1 ≤ value ≤ 20.

    **Validates: Requirements 11.6**
    """
    data = {"max_concurrent_screening_tasks": value}
    # Should not raise
    ScreeningConfigService._validate_ranges(data)


# ---------------------------------------------------------------------------
# Property 15: max_concurrent — Below minimum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=-10000, max_value=0))
def test_max_concurrent_rejects_below_minimum(value: int) -> None:
    """_validate_ranges SHALL reject max_concurrent_screening_tasks
    when value < 1 with ConfigurationRangeError.

    **Validates: Requirements 11.6**
    """
    data = {"max_concurrent_screening_tasks": value}
    with pytest.raises(ConfigurationRangeError) as exc_info:
        ScreeningConfigService._validate_ranges(data)
    assert exc_info.value.field_name == "max_concurrent_screening_tasks"
    assert exc_info.value.value == value
    assert exc_info.value.min_value == 1
    assert exc_info.value.max_value == 20


# ---------------------------------------------------------------------------
# Property 15: max_concurrent — Above maximum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(value=st.integers(min_value=21, max_value=10000))
def test_max_concurrent_rejects_above_maximum(value: int) -> None:
    """_validate_ranges SHALL reject max_concurrent_screening_tasks
    when value > 20 with ConfigurationRangeError.

    **Validates: Requirements 11.6**
    """
    data = {"max_concurrent_screening_tasks": value}
    with pytest.raises(ConfigurationRangeError) as exc_info:
        ScreeningConfigService._validate_ranges(data)
    assert exc_info.value.field_name == "max_concurrent_screening_tasks"
    assert exc_info.value.value == value


# ---------------------------------------------------------------------------
# Property 15: Combined — All fields valid simultaneously
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    batch_size=st.integers(min_value=1, max_value=100),
    confidence=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
    max_concurrent=st.integers(min_value=1, max_value=20),
)
def test_all_fields_valid_simultaneously(
    batch_size: int,
    confidence: float,
    max_concurrent: int,
) -> None:
    """_validate_ranges SHALL accept all fields when each is within bounds.

    **Validates: Requirements 11.6**
    """
    data = {
        "default_batch_size": batch_size,
        "confidence_threshold_for_auto_include": confidence,
        "max_concurrent_screening_tasks": max_concurrent,
    }
    # Should not raise
    ScreeningConfigService._validate_ranges(data)


# ---------------------------------------------------------------------------
# Property 15: None values are ignored (optional fields)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    batch_size=st.one_of(st.none(), st.integers(min_value=1, max_value=100)),
    confidence=st.one_of(
        st.none(), st.floats(min_value=0.5, max_value=1.0, allow_nan=False)
    ),
    max_concurrent=st.one_of(st.none(), st.integers(min_value=1, max_value=20)),
)
def test_none_values_are_ignored(
    batch_size: int | None,
    confidence: float | None,
    max_concurrent: int | None,
) -> None:
    """_validate_ranges SHALL skip validation for fields set to None.

    **Validates: Requirements 11.6**
    """
    data = {
        "default_batch_size": batch_size,
        "confidence_threshold_for_auto_include": confidence,
        "max_concurrent_screening_tasks": max_concurrent,
    }
    # Should not raise regardless of None values
    ScreeningConfigService._validate_ranges(data)


# ---------------------------------------------------------------------------
# Property 15: Empty data dict is accepted (no fields to validate)
# ---------------------------------------------------------------------------


def test_empty_data_accepted() -> None:
    """_validate_ranges SHALL accept an empty dict without error.

    **Validates: Requirements 11.6**
    """
    ScreeningConfigService._validate_ranges({})
