"""Property-based tests for health status classification.

Property 11: Health Status Classification
For any measured response time (in milliseconds), degraded threshold, and
unreachable timeout, the classify_status function SHALL return:
- "healthy" if response_time < degraded_threshold
- "degraded" if degraded_threshold ≤ response_time < timeout
- "unreachable" if response_time ≥ timeout or a connection error occurred

These three states are mutually exclusive and exhaustive.

**Validates: Requirements 10.3, 10.4, 10.5**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import assume, given, settings

from alcoabase.services.health_monitor import HealthMonitor


# Strategy for valid threshold pairs where degraded < timeout
# This ensures the thresholds define a valid classification space.
valid_thresholds = st.tuples(
    st.floats(min_value=1.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=100000.0, allow_nan=False, allow_infinity=False),
).filter(lambda t: t[0] < t[1])


# ---------------------------------------------------------------------------
# Property 11: Healthy classification — response_time < degraded_threshold
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    thresholds=valid_thresholds,
    response_time=st.floats(
        min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_classify_status_returns_healthy_when_below_degraded_threshold(
    thresholds: tuple[float, float],
    response_time: float,
) -> None:
    """classify_status SHALL return "healthy" when response_time_ms is
    strictly less than degraded_threshold_ms.

    **Validates: Requirements 10.3**
    """
    degraded_threshold_ms, timeout_ms = thresholds
    assume(response_time < degraded_threshold_ms)

    result = HealthMonitor.classify_status(response_time, degraded_threshold_ms, timeout_ms)
    assert result == "healthy"


# ---------------------------------------------------------------------------
# Property 11: Degraded classification — degraded_threshold ≤ response_time < timeout
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    thresholds=valid_thresholds,
    response_time=st.floats(
        min_value=0.0, max_value=100000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_classify_status_returns_degraded_when_between_thresholds(
    thresholds: tuple[float, float],
    response_time: float,
) -> None:
    """classify_status SHALL return "degraded" when degraded_threshold_ms ≤
    response_time_ms < timeout_ms.

    **Validates: Requirements 10.4**
    """
    degraded_threshold_ms, timeout_ms = thresholds
    assume(degraded_threshold_ms <= response_time < timeout_ms)

    result = HealthMonitor.classify_status(response_time, degraded_threshold_ms, timeout_ms)
    assert result == "degraded"


# ---------------------------------------------------------------------------
# Property 11: Unreachable classification — response_time ≥ timeout
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    thresholds=valid_thresholds,
    response_time=st.floats(
        min_value=0.0, max_value=200000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_classify_status_returns_unreachable_when_at_or_above_timeout(
    thresholds: tuple[float, float],
    response_time: float,
) -> None:
    """classify_status SHALL return "unreachable" when response_time_ms ≥
    timeout_ms.

    **Validates: Requirements 10.5**
    """
    degraded_threshold_ms, timeout_ms = thresholds
    assume(response_time >= timeout_ms)

    result = HealthMonitor.classify_status(response_time, degraded_threshold_ms, timeout_ms)
    assert result == "unreachable"


# ---------------------------------------------------------------------------
# Property 11: Mutual exclusivity — exactly one status returned
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    thresholds=valid_thresholds,
    response_time=st.floats(
        min_value=0.0, max_value=200000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_classify_status_returns_exactly_one_valid_state(
    thresholds: tuple[float, float],
    response_time: float,
) -> None:
    """classify_status SHALL always return exactly one of "healthy",
    "degraded", or "unreachable" — states are mutually exclusive and
    exhaustive.

    **Validates: Requirements 10.3, 10.4, 10.5**
    """
    degraded_threshold_ms, timeout_ms = thresholds

    result = HealthMonitor.classify_status(response_time, degraded_threshold_ms, timeout_ms)

    valid_states = {"healthy", "degraded", "unreachable"}
    assert result in valid_states


# ---------------------------------------------------------------------------
# Property 11: Exhaustiveness — classification covers all response times
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    thresholds=valid_thresholds,
    response_time=st.floats(
        min_value=0.0, max_value=200000.0, allow_nan=False, allow_infinity=False
    ),
)
def test_classify_status_classification_is_exhaustive(
    thresholds: tuple[float, float],
    response_time: float,
) -> None:
    """For any valid response_time and threshold pair, classify_status SHALL
    produce a classification consistent with the threshold boundaries:
    - healthy iff response_time < degraded_threshold
    - degraded iff degraded_threshold ≤ response_time < timeout
    - unreachable iff response_time ≥ timeout

    **Validates: Requirements 10.3, 10.4, 10.5**
    """
    degraded_threshold_ms, timeout_ms = thresholds

    result = HealthMonitor.classify_status(response_time, degraded_threshold_ms, timeout_ms)

    if response_time < degraded_threshold_ms:
        assert result == "healthy"
    elif response_time < timeout_ms:
        assert result == "degraded"
    else:
        assert result == "unreachable"
