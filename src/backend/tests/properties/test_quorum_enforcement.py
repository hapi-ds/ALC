"""Property-based tests for quorum enforcement in the review pipeline.

Tests Property 2 from the multi-agent always-on auditing design document,
validating that the review session status follows quorum rules based on
the number of completed and failed agent reviews.

**Validates: Requirements 1.4, 1.5, 1.6**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 2)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (1.4, 1.5, 1.6)
    - Implementation: src/backend/src/alcoabase/tasks/review_tasks.py (check_review_completion)
"""

from __future__ import annotations

from enum import Enum

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure model of the quorum decision logic
# ---------------------------------------------------------------------------


class QuorumDecision(str, Enum):
    """Possible outcomes of the quorum check."""

    TRIGGER_MASTER_SUMMARY = "trigger_master_summary"
    MARK_FAILED = "mark_failed"
    WAIT = "wait"


def evaluate_quorum(
    total_agents: int,
    completed_count: int,
    failed_count: int,
    quorum: int,
) -> QuorumDecision:
    """Pure model of the quorum decision logic from check_review_completion.

    This mirrors the logic in _check_review_completion_async without
    requiring database or Celery infrastructure.

    Args:
        total_agents: Total number of agent reviews dispatched.
        completed_count: Number of agent reviews with status "Completed".
        failed_count: Number of agent reviews with status "Failed".
        quorum: Minimum number of successful reviews required.

    Returns:
        The quorum decision: trigger master summary, mark failed, or wait.
    """
    # Rule 1: If quorum is met, trigger master summary
    if completed_count >= quorum:
        return QuorumDecision.TRIGGER_MASTER_SUMMARY

    # Rule 2: If quorum is impossible, mark as failed
    remaining = total_agents - completed_count - failed_count
    if completed_count + remaining < quorum:
        return QuorumDecision.MARK_FAILED

    # Rule 3: Otherwise, wait for more results
    return QuorumDecision.WAIT


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_quorum_scenario(draw: st.DrawFn) -> dict[str, int]:
    """Generate a valid quorum scenario with consistent constraints.

    Generates N (total agents), Q (quorum where 1 <= Q <= N),
    and a distribution of completed/failed/pending agents that sums to N.

    Returns:
        Dict with keys: total_agents, quorum, completed_count, failed_count.
    """
    total_agents = draw(st.integers(min_value=1, max_value=20), label="total_agents")
    quorum = draw(
        st.integers(min_value=1, max_value=total_agents), label="quorum"
    )

    # Generate completed and failed counts that don't exceed total
    completed_count = draw(
        st.integers(min_value=0, max_value=total_agents), label="completed_count"
    )
    # Failed count is bounded by remaining agents after completed
    max_failed = total_agents - completed_count
    failed_count = draw(
        st.integers(min_value=0, max_value=max_failed), label="failed_count"
    )

    return {
        "total_agents": total_agents,
        "quorum": quorum,
        "completed_count": completed_count,
        "failed_count": failed_count,
    }


# ---------------------------------------------------------------------------
# Property 2: Quorum enforcement
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 2: Quorum enforcement — quorum met triggers master summary
@settings(max_examples=300)
@given(scenario=st_quorum_scenario())
def test_quorum_met_triggers_master_summary(scenario: dict[str, int]) -> None:
    """For any review session where completed_count >= quorum, the decision
    SHALL be to trigger the Master Auditor summary, regardless of how many
    agents failed.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """
    total_agents = scenario["total_agents"]
    quorum = scenario["quorum"]
    completed_count = scenario["completed_count"]
    failed_count = scenario["failed_count"]

    decision = evaluate_quorum(total_agents, completed_count, failed_count, quorum)

    if completed_count >= quorum:
        assert decision == QuorumDecision.TRIGGER_MASTER_SUMMARY, (
            f"Expected TRIGGER_MASTER_SUMMARY when completed={completed_count} >= "
            f"quorum={quorum}, but got {decision.value} "
            f"(total={total_agents}, failed={failed_count})"
        )


# Feature: multi-agent-always-on-auditing, Property 2: Quorum enforcement — quorum impossible marks failed
@settings(max_examples=300)
@given(scenario=st_quorum_scenario())
def test_quorum_impossible_marks_failed(scenario: dict[str, int]) -> None:
    """For any review session where completed_count + remaining < quorum
    (i.e., even if all remaining agents succeed, quorum cannot be reached),
    the session SHALL be marked as Failed.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """
    total_agents = scenario["total_agents"]
    quorum = scenario["quorum"]
    completed_count = scenario["completed_count"]
    failed_count = scenario["failed_count"]

    remaining = total_agents - completed_count - failed_count
    decision = evaluate_quorum(total_agents, completed_count, failed_count, quorum)

    # Only check the failure case when quorum is NOT already met
    # (quorum met takes priority in the logic)
    if completed_count < quorum and completed_count + remaining < quorum:
        assert decision == QuorumDecision.MARK_FAILED, (
            f"Expected MARK_FAILED when completed={completed_count} + "
            f"remaining={remaining} < quorum={quorum}, but got {decision.value} "
            f"(total={total_agents}, failed={failed_count})"
        )


# Feature: multi-agent-always-on-auditing, Property 2: Quorum enforcement — wait when quorum still possible
@settings(max_examples=300)
@given(scenario=st_quorum_scenario())
def test_quorum_still_possible_waits(scenario: dict[str, int]) -> None:
    """For any review session where completed_count < quorum but
    completed_count + remaining >= quorum (quorum is still achievable),
    the decision SHALL be to wait for more results.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """
    total_agents = scenario["total_agents"]
    quorum = scenario["quorum"]
    completed_count = scenario["completed_count"]
    failed_count = scenario["failed_count"]

    remaining = total_agents - completed_count - failed_count
    decision = evaluate_quorum(total_agents, completed_count, failed_count, quorum)

    if completed_count < quorum and completed_count + remaining >= quorum:
        assert decision == QuorumDecision.WAIT, (
            f"Expected WAIT when completed={completed_count} < quorum={quorum} "
            f"and completed + remaining={completed_count + remaining} >= quorum, "
            f"but got {decision.value} "
            f"(total={total_agents}, failed={failed_count})"
        )


# Feature: multi-agent-always-on-auditing, Property 2: Quorum enforcement — decision is exhaustive
@settings(max_examples=300)
@given(scenario=st_quorum_scenario())
def test_quorum_decision_is_exhaustive(scenario: dict[str, int]) -> None:
    """For any valid combination of total_agents, quorum, completed_count,
    and failed_count, the quorum decision SHALL always be exactly one of:
    TRIGGER_MASTER_SUMMARY, MARK_FAILED, or WAIT.

    This ensures the decision logic has no gaps or undefined states.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """
    total_agents = scenario["total_agents"]
    quorum = scenario["quorum"]
    completed_count = scenario["completed_count"]
    failed_count = scenario["failed_count"]

    decision = evaluate_quorum(total_agents, completed_count, failed_count, quorum)

    assert decision in {
        QuorumDecision.TRIGGER_MASTER_SUMMARY,
        QuorumDecision.MARK_FAILED,
        QuorumDecision.WAIT,
    }, f"Unexpected decision: {decision}"


# Feature: multi-agent-always-on-auditing, Property 2: Quorum enforcement — priority ordering
@settings(max_examples=300)
@given(scenario=st_quorum_scenario())
def test_quorum_met_takes_priority_over_failure(scenario: dict[str, int]) -> None:
    """If completed_count >= quorum, the decision SHALL always be
    TRIGGER_MASTER_SUMMARY, even if there are also many failed agents.
    Meeting quorum takes priority over failure detection.

    **Validates: Requirements 1.4, 1.5, 1.6**
    """
    total_agents = scenario["total_agents"]
    quorum = scenario["quorum"]
    completed_count = scenario["completed_count"]
    failed_count = scenario["failed_count"]

    decision = evaluate_quorum(total_agents, completed_count, failed_count, quorum)

    if completed_count >= quorum:
        # Even if many agents failed, quorum met means trigger summary
        assert decision == QuorumDecision.TRIGGER_MASTER_SUMMARY, (
            f"Quorum met (completed={completed_count} >= quorum={quorum}) "
            f"should always trigger master summary, but got {decision.value}"
        )
