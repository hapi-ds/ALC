"""Property-based tests for action item status transitions.

Tests Property 9 from the multi-agent always-on auditing design document,
validating that only valid status transitions succeed and invalid transitions
are rejected. Resolved and Dismissed are terminal states with no outgoing
transitions.

**Validates: Requirements 5.4**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 9)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (Requirement 5)
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.review_pipeline import _VALID_ACTION_ITEM_TRANSITIONS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_STATUSES = ["Open", "InProgress", "Resolved", "Dismissed"]
TERMINAL_STATUSES = ["Resolved", "Dismissed"]
NON_TERMINAL_STATUSES = ["Open", "InProgress"]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_valid_transition() -> st.SearchStrategy[tuple[str, str]]:
    """Generate a valid (from_status, to_status) transition pair.

    Returns:
        Strategy producing tuples where the transition is allowed by
        _VALID_ACTION_ITEM_TRANSITIONS.
    """
    valid_pairs: list[tuple[str, str]] = []
    for from_status, targets in _VALID_ACTION_ITEM_TRANSITIONS.items():
        for to_status in targets:
            valid_pairs.append((from_status, to_status))
    return st.sampled_from(valid_pairs)


def st_invalid_transition() -> st.SearchStrategy[tuple[str, str]]:
    """Generate an invalid (from_status, to_status) transition pair.

    Returns:
        Strategy producing tuples where the transition is NOT allowed.
        This includes transitions from terminal states and transitions
        to states not in the valid set for the source.
    """
    invalid_pairs: list[tuple[str, str]] = []
    for from_status in ALL_STATUSES:
        valid_targets = _VALID_ACTION_ITEM_TRANSITIONS.get(from_status, set())
        for to_status in ALL_STATUSES:
            if to_status not in valid_targets:
                invalid_pairs.append((from_status, to_status))
    return st.sampled_from(invalid_pairs)


def st_transition_sequence(
    min_size: int = 1, max_size: int = 10
) -> st.SearchStrategy[list[str]]:
    """Generate a random sequence of target statuses to attempt.

    Args:
        min_size: Minimum sequence length.
        max_size: Maximum sequence length.

    Returns:
        Strategy producing lists of status strings representing
        a sequence of attempted transitions.
    """
    return st.lists(
        st.sampled_from(ALL_STATUSES),
        min_size=min_size,
        max_size=max_size,
    )


# ---------------------------------------------------------------------------
# Helper: simulate transition logic
# ---------------------------------------------------------------------------


def attempt_transition(current_status: str, target_status: str) -> tuple[bool, str]:
    """Simulate the action item transition logic.

    Applies the same validation as ReviewPipelineService.update_action_item
    without requiring database access.

    Args:
        current_status: The current status of the action item.
        target_status: The desired new status.

    Returns:
        Tuple of (success, resulting_status). If the transition is valid,
        returns (True, target_status). If invalid, returns (False, current_status).
    """
    valid_targets = _VALID_ACTION_ITEM_TRANSITIONS.get(current_status, set())
    if target_status in valid_targets:
        return True, target_status
    return False, current_status


# ---------------------------------------------------------------------------
# Property 9: Action item status transitions
# ---------------------------------------------------------------------------


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 9: Action item status transitions
@settings(max_examples=200, deadline=None)
@given(transition=st_valid_transition())
def test_valid_transitions_always_succeed(
    transition: tuple[str, str],
) -> None:
    """For any valid (from_status, to_status) pair defined in
    _VALID_ACTION_ITEM_TRANSITIONS, the transition SHALL succeed.

    Valid transitions are:
    - Open → {InProgress, Resolved, Dismissed}
    - InProgress → {Resolved, Dismissed, Open}

    **Validates: Requirements 5.4**
    """
    from_status, to_status = transition
    success, resulting_status = attempt_transition(from_status, to_status)

    assert success, (
        f"Transition from '{from_status}' to '{to_status}' should be valid "
        f"but was rejected"
    )
    assert resulting_status == to_status, (
        f"After valid transition, status should be '{to_status}' "
        f"but got '{resulting_status}'"
    )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 9: Action item status transitions
@settings(max_examples=200, deadline=None)
@given(transition=st_invalid_transition())
def test_invalid_transitions_always_rejected(
    transition: tuple[str, str],
) -> None:
    """For any invalid (from_status, to_status) pair NOT in
    _VALID_ACTION_ITEM_TRANSITIONS, the transition SHALL be rejected
    and the status SHALL remain unchanged.

    Invalid transitions include:
    - Resolved → anything (terminal state)
    - Dismissed → anything (terminal state)
    - Open → Open (self-transition not allowed)
    - InProgress → InProgress (self-transition not allowed)

    **Validates: Requirements 5.4**
    """
    from_status, to_status = transition
    success, resulting_status = attempt_transition(from_status, to_status)

    assert not success, (
        f"Transition from '{from_status}' to '{to_status}' should be invalid "
        f"but was accepted"
    )
    assert resulting_status == from_status, (
        f"After rejected transition, status should remain '{from_status}' "
        f"but got '{resulting_status}'"
    )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 9: Action item status transitions
@settings(max_examples=200, deadline=None)
@given(transition_sequence=st_transition_sequence(min_size=1, max_size=15))
def test_terminal_states_have_no_outgoing_transitions(
    transition_sequence: list[str],
) -> None:
    """For any sequence of transitions starting from 'Open', once a
    terminal state (Resolved or Dismissed) is reached, ALL subsequent
    transitions SHALL be rejected.

    This validates that Resolved and Dismissed are truly terminal —
    no sequence of operations can escape them.

    **Validates: Requirements 5.4**
    """
    current_status = "Open"
    reached_terminal = False

    for target_status in transition_sequence:
        if reached_terminal:
            # Once terminal, every transition must fail
            success, new_status = attempt_transition(current_status, target_status)
            assert not success, (
                f"Terminal state '{current_status}' should reject transition "
                f"to '{target_status}', but it was accepted"
            )
            assert new_status == current_status, (
                f"Status should remain '{current_status}' after rejected "
                f"transition, but got '{new_status}'"
            )
        else:
            success, new_status = attempt_transition(current_status, target_status)
            if success:
                current_status = new_status
                if current_status in TERMINAL_STATUSES:
                    reached_terminal = True
            # If not successful, status stays the same


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 9: Action item status transitions
@settings(max_examples=200, deadline=None)
@given(
    data=st.data(),
    initial_status=st.sampled_from(NON_TERMINAL_STATUSES),
)
def test_random_transition_sequences_follow_state_machine(
    data: st.DataObject,
    initial_status: str,
) -> None:
    """For any starting non-terminal status and any random sequence of
    attempted transitions, the resulting status SHALL always be consistent
    with the state machine rules:
    - Valid transitions change the status to the target
    - Invalid transitions leave the status unchanged
    - The final status is always one of the four valid statuses

    **Validates: Requirements 5.4**
    """
    sequence = data.draw(
        st_transition_sequence(min_size=1, max_size=20),
        label="transition_sequence",
    )

    current_status = initial_status

    for target_status in sequence:
        valid_targets = _VALID_ACTION_ITEM_TRANSITIONS.get(current_status, set())
        success, new_status = attempt_transition(current_status, target_status)

        if target_status in valid_targets:
            # Should succeed
            assert success, (
                f"Valid transition from '{current_status}' to '{target_status}' "
                f"was unexpectedly rejected"
            )
            assert new_status == target_status
        else:
            # Should fail
            assert not success, (
                f"Invalid transition from '{current_status}' to '{target_status}' "
                f"was unexpectedly accepted"
            )
            assert new_status == current_status

        current_status = new_status

    # Final status must always be a valid status
    assert current_status in ALL_STATUSES, (
        f"Final status '{current_status}' is not a valid action item status"
    )
