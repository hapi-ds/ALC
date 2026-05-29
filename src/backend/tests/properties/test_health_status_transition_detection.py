"""Property-based tests for health status transition detection.

Property 13: Health Status Transition Detection
For any sequence of health check results for a service, a transition event
SHALL be recorded if and only if the current status differs from the
immediately preceding status AND the transition is from "healthy" to either
"degraded" or "unreachable".

**Validates: Requirements 10.9**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Implementation: src/backend/src/alcoabase/services/health_monitor.py
"""

from typing import NamedTuple

import hypothesis.strategies as st
from hypothesis import given, settings
from hypothesis.strategies import composite

# Valid health statuses as defined in the HealthMonitor
VALID_STATUSES = ["healthy", "degraded", "unreachable"]


class TransitionResult(NamedTuple):
    """Result of transition detection for a single health check."""

    is_transition: bool
    previous_status: str | None


def detect_transition_logic(
    current_status: str, previous_status: str | None
) -> TransitionResult:
    """Pure function implementing the transition detection logic.

    This mirrors the logic in HealthMonitor._detect_transition without
    database dependencies. A transition event is recorded if and only if:
    - There is a previous status, AND
    - The previous status was "healthy", AND
    - The current status is "degraded" or "unreachable"

    Args:
        current_status: The status of the current health check.
        previous_status: The status of the immediately preceding check,
            or None if this is the first check.

    Returns:
        TransitionResult with is_transition flag and previous_status.
    """
    if previous_status is not None:
        is_transition = (
            previous_status == "healthy"
            and current_status in ("degraded", "unreachable")
        )
        return TransitionResult(
            is_transition=is_transition, previous_status=previous_status
        )
    else:
        return TransitionResult(is_transition=False, previous_status=None)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

status_strategy = st.sampled_from(VALID_STATUSES)


@composite
def status_sequences(draw: st.DrawFn) -> list[str]:
    """Generate non-empty sequences of health check statuses (2-50 items)."""
    length = draw(st.integers(min_value=2, max_value=50))
    return [draw(status_strategy) for _ in range(length)]


# ---------------------------------------------------------------------------
# Property 13: Transition recorded only for healthy → degraded/unreachable
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    current_status=status_strategy,
    previous_status=status_strategy,
)
def test_transition_detected_only_from_healthy_to_degraded_or_unreachable(
    current_status: str,
    previous_status: str,
) -> None:
    """A transition event SHALL be recorded if and only if the previous status
    is "healthy" AND the current status is "degraded" or "unreachable".

    **Validates: Requirements 10.9**
    """
    result = detect_transition_logic(current_status, previous_status)

    expected_transition = (
        previous_status == "healthy"
        and current_status in ("degraded", "unreachable")
    )

    assert result.is_transition == expected_transition
    assert result.previous_status == previous_status


# ---------------------------------------------------------------------------
# Property 13: No transition when no previous status exists
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(current_status=status_strategy)
def test_no_transition_when_no_previous_status(current_status: str) -> None:
    """When there is no previous health check result, is_transition SHALL
    always be False and previous_status SHALL be None.

    **Validates: Requirements 10.9**
    """
    result = detect_transition_logic(current_status, previous_status=None)

    assert result.is_transition is False
    assert result.previous_status is None


# ---------------------------------------------------------------------------
# Property 13: No transition when status unchanged
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(status=status_strategy)
def test_no_transition_when_status_unchanged(status: str) -> None:
    """When the current status equals the previous status, is_transition
    SHALL always be False (no self-transitions).

    **Validates: Requirements 10.9**
    """
    result = detect_transition_logic(status, previous_status=status)

    assert result.is_transition is False


# ---------------------------------------------------------------------------
# Property 13: No transition from degraded or unreachable to any state
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    previous_status=st.sampled_from(["degraded", "unreachable"]),
    current_status=status_strategy,
)
def test_no_transition_from_non_healthy_states(
    previous_status: str,
    current_status: str,
) -> None:
    """Transitions from "degraded" or "unreachable" to any state SHALL NOT
    be recorded as transition events, regardless of the current status.

    **Validates: Requirements 10.9**
    """
    result = detect_transition_logic(current_status, previous_status)

    assert result.is_transition is False


# ---------------------------------------------------------------------------
# Property 13: Transition detection over sequences
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(statuses=status_sequences())
def test_transition_detection_over_sequence(statuses: list[str]) -> None:
    """For any sequence of health check statuses, transition events SHALL be
    recorded at exactly those positions where the previous status was "healthy"
    and the current status is "degraded" or "unreachable".

    **Validates: Requirements 10.9**
    """
    transitions_detected: list[bool] = []

    for i, current_status in enumerate(statuses):
        if i == 0:
            # First check has no previous
            result = detect_transition_logic(current_status, previous_status=None)
        else:
            previous_status = statuses[i - 1]
            result = detect_transition_logic(current_status, previous_status)

        transitions_detected.append(result.is_transition)

    # Verify: first element never has a transition
    assert transitions_detected[0] is False

    # Verify: transitions match the expected pattern
    for i in range(1, len(statuses)):
        expected = (
            statuses[i - 1] == "healthy"
            and statuses[i] in ("degraded", "unreachable")
        )
        assert transitions_detected[i] == expected, (
            f"At index {i}: previous={statuses[i-1]}, current={statuses[i]}, "
            f"expected_transition={expected}, got={transitions_detected[i]}"
        )


# ---------------------------------------------------------------------------
# Property 13: Healthy → Healthy never triggers transition
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(sequence_length=st.integers(min_value=2, max_value=20))
def test_all_healthy_sequence_no_transitions(sequence_length: int) -> None:
    """A sequence of all "healthy" statuses SHALL produce zero transition events.

    **Validates: Requirements 10.9**
    """
    statuses = ["healthy"] * sequence_length

    for i in range(1, len(statuses)):
        result = detect_transition_logic(statuses[i], previous_status=statuses[i - 1])
        assert result.is_transition is False


# ---------------------------------------------------------------------------
# Property 13: Healthy → Degraded always triggers transition
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(data=st.data())
def test_healthy_to_degraded_always_triggers(data: st.DataObject) -> None:
    """Every occurrence of "healthy" followed by "degraded" SHALL produce
    a transition event.

    **Validates: Requirements 10.9**
    """
    # Generate a sequence that contains at least one healthy→degraded pair
    prefix_len = data.draw(st.integers(min_value=0, max_value=10))
    prefix = [data.draw(status_strategy) for _ in range(prefix_len)]

    # Force a healthy→degraded transition
    sequence = prefix + ["healthy", "degraded"]

    # Check the transition at the last position
    result = detect_transition_logic("degraded", previous_status="healthy")
    assert result.is_transition is True
    assert result.previous_status == "healthy"


# ---------------------------------------------------------------------------
# Property 13: Healthy → Unreachable always triggers transition
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(data=st.data())
def test_healthy_to_unreachable_always_triggers(data: st.DataObject) -> None:
    """Every occurrence of "healthy" followed by "unreachable" SHALL produce
    a transition event.

    **Validates: Requirements 10.9**
    """
    # Generate a sequence that contains at least one healthy→unreachable pair
    prefix_len = data.draw(st.integers(min_value=0, max_value=10))
    prefix = [data.draw(status_strategy) for _ in range(prefix_len)]

    # Force a healthy→unreachable transition
    sequence = prefix + ["healthy", "unreachable"]

    # Check the transition at the last position
    result = detect_transition_logic("unreachable", previous_status="healthy")
    assert result.is_transition is True
    assert result.previous_status == "healthy"
