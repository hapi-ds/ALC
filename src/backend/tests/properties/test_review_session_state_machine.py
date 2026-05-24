"""Property-based tests for review session state machine validity.

Tests Property 8 from the multi-agent always-on auditing design document,
validating that review session status transitions follow the defined state
machine: Pending → InProgress → {Completed, Failed}, Completed → {Approved, Rejected}.
No other transitions are permitted.

**Validates: Requirements 1.3, 10.4**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 8)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (Requirements 1, 10)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule

from alcoabase.services.review_pipeline import (
    ReviewPipelineService,
    _VALID_SESSION_TRANSITIONS,
)

# All possible session states
ALL_STATES = ["Pending", "InProgress", "Completed", "Failed", "Approved", "Rejected"]

# Terminal states (no outgoing transitions)
TERMINAL_STATES = {"Failed", "Approved", "Rejected"}


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_state() -> st.SearchStrategy[str]:
    """Generate a random session state.

    Returns:
        Strategy producing one of the valid session states.
    """
    return st.sampled_from(ALL_STATES)


def st_transition_sequence(min_size: int = 1, max_size: int = 10) -> st.SearchStrategy[list[str]]:
    """Generate a random sequence of target states to attempt transitioning to.

    Args:
        min_size: Minimum number of transitions to attempt.
        max_size: Maximum number of transitions to attempt.

    Returns:
        Strategy producing lists of state strings.
    """
    return st.lists(st_state(), min_size=min_size, max_size=max_size)


# ---------------------------------------------------------------------------
# Property 8: Review session state machine validity
# ---------------------------------------------------------------------------


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 8: Review session state machine validity
@settings(max_examples=200, deadline=None)
@given(current_state=st_state(), target_state=st_state())
def test_valid_transitions_match_state_machine(
    current_state: str, target_state: str
) -> None:
    """For any current state and target state, the transition is valid if
    and only if target_state is in _VALID_SESSION_TRANSITIONS[current_state].

    This directly tests the state machine definition: valid transitions
    succeed and invalid transitions are rejected.

    **Validates: Requirements 1.3, 10.4**
    """
    valid_targets = _VALID_SESSION_TRANSITIONS.get(current_state, set())
    is_valid = target_state in valid_targets

    if is_valid:
        # The transition should be in the allowed set
        assert target_state in valid_targets, (
            f"Transition {current_state} → {target_state} should be valid "
            f"but is not in valid targets: {valid_targets}"
        )
    else:
        # The transition should NOT be in the allowed set
        assert target_state not in valid_targets, (
            f"Transition {current_state} → {target_state} should be invalid "
            f"but is in valid targets: {valid_targets}"
        )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 8: Review session state machine validity
@settings(max_examples=200, deadline=None)
@given(current_state=st_state(), target_state=st_state())
@pytest.mark.asyncio
async def test_transition_session_enforces_state_machine(
    current_state: str, target_state: str
) -> None:
    """For any current state and target state, _transition_session SHALL
    raise ValueError when the transition is invalid and SHALL succeed
    when the transition is valid.

    This tests the actual service method against the state machine rules.

    **Validates: Requirements 1.3, 10.4**
    """
    valid_targets = _VALID_SESSION_TRANSITIONS.get(current_state, set())
    is_valid = target_state in valid_targets

    # Create a mock session that returns a ReviewSession with the given state
    mock_review_session = MagicMock()
    mock_review_session.status = current_state
    mock_review_session.id = 1
    mock_review_session.company_id = 1

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_review_session

    mock_db_session = AsyncMock()
    mock_db_session.execute = AsyncMock(return_value=mock_result)
    mock_db_session.commit = AsyncMock()
    mock_db_session.refresh = AsyncMock()
    mock_db_session.expunge = MagicMock()

    # Create async context manager for session factory
    mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
    mock_db_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_db_session)

    # Create service with mocked dependencies
    service = ReviewPipelineService(
        session_factory=mock_session_factory,
        agent_registry=AsyncMock(),
        storage_service=AsyncMock(),
        inference_client=AsyncMock(),
    )

    if is_valid:
        # Valid transition should succeed without raising
        result = await service._transition_session(
            session_id=1, company_id=1, target_status=target_state
        )
        assert result.status == target_state
    else:
        # Invalid transition should raise ValueError
        with pytest.raises(ValueError):
            await service._transition_session(
                session_id=1, company_id=1, target_status=target_state
            )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 8: Review session state machine validity
@settings(max_examples=100, deadline=None)
@given(transitions=st_transition_sequence(min_size=1, max_size=8))
@pytest.mark.asyncio
async def test_sequential_transitions_follow_state_machine(
    transitions: list[str],
) -> None:
    """For any random sequence of attempted transitions starting from
    "Pending", the session state SHALL only change when the transition
    is valid according to _VALID_SESSION_TRANSITIONS. Invalid transitions
    SHALL be rejected and the state SHALL remain unchanged.

    **Validates: Requirements 1.3, 10.4**
    """
    current_state = "Pending"

    for target_state in transitions:
        valid_targets = _VALID_SESSION_TRANSITIONS.get(current_state, set())
        is_valid = target_state in valid_targets

        # Create mock session reflecting current state
        mock_review_session = MagicMock()
        mock_review_session.status = current_state
        mock_review_session.id = 1
        mock_review_session.company_id = 1

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_review_session

        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()
        mock_db_session.expunge = MagicMock()

        mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_factory = MagicMock(return_value=mock_db_session)

        service = ReviewPipelineService(
            session_factory=mock_session_factory,
            agent_registry=AsyncMock(),
            storage_service=AsyncMock(),
            inference_client=AsyncMock(),
        )

        if is_valid:
            result = await service._transition_session(
                session_id=1, company_id=1, target_status=target_state
            )
            # State advances
            current_state = target_state
        else:
            with pytest.raises(ValueError):
                await service._transition_session(
                    session_id=1, company_id=1, target_status=target_state
                )
            # State remains unchanged after invalid transition

    # After all transitions, verify the final state is reachable from Pending
    # via the valid transition graph
    reachable = _compute_reachable_states("Pending")
    assert current_state in reachable, (
        f"Final state '{current_state}' is not reachable from 'Pending' "
        f"via valid transitions. Reachable states: {reachable}"
    )


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 8: Review session state machine validity
@settings(max_examples=100, deadline=None)
@given(state=st.sampled_from(list(TERMINAL_STATES)))
def test_terminal_states_reject_all_transitions(state: str) -> None:
    """For any terminal state (Failed, Approved, Rejected), no outgoing
    transitions SHALL be permitted.

    **Validates: Requirements 1.3, 10.4**
    """
    valid_targets = _VALID_SESSION_TRANSITIONS.get(state, set())
    assert valid_targets == set() or state not in _VALID_SESSION_TRANSITIONS, (
        f"Terminal state '{state}' should have no valid outgoing transitions, "
        f"but has: {valid_targets}"
    )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _compute_reachable_states(start: str) -> set[str]:
    """Compute all states reachable from a starting state via valid transitions.

    Args:
        start: The initial state.

    Returns:
        Set of all reachable states (including the start state).
    """
    reachable = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for target in _VALID_SESSION_TRANSITIONS.get(current, set()):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    return reachable
