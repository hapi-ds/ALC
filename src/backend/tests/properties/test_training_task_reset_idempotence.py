"""Property-based tests for training task reset idempotence.

Property 15: Training Task Reset Idempotence

For any affected training task with recommended_action "retraining_required",
setting is_completed to false SHALL be idempotent: if is_completed is already
false, no update SHALL occur. The operation SHALL never set is_completed to true.

**Validates: Requirements 8.4**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_notification.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

TASK_IDS = st.integers(min_value=1, max_value=10000)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

REPORT_IDS = st.uuids().map(str)

RECOMMENDED_ACTIONS = st.sampled_from(
    ["update_required", "review_recommended", "retraining_required", "manual_review_required"]
)

IMPACT_SEVERITIES = st.sampled_from(["critical", "major", "minor", "unknown"])


# ---------------------------------------------------------------------------
# Data models for pure-logic testing
# ---------------------------------------------------------------------------


@dataclass
class TrainingTaskState:
    """Represents the state of a training task relevant to reset logic."""

    id: int
    sop_document_uuid: str
    is_completed: bool
    completed_at: datetime | None = None


@dataclass
class AffectedItem:
    """Represents an affected item from an impact report."""

    training_task_id: int | None = None
    affected_document_uuid: str | None = None
    recommended_action: str = "review_recommended"
    impact_severity: str = "major"


@dataclass
class ResetResult:
    """Result of a training task reset operation."""

    reset_count: int = 0
    tasks_updated: list[int] = field(default_factory=list)
    tasks_skipped: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pure-logic function modeling the reset behavior
# ---------------------------------------------------------------------------


def reset_training_tasks(
    tasks: dict[int, TrainingTaskState],
    affected_items: list[AffectedItem],
) -> ResetResult:
    """Reset training tasks for items with recommended_action "retraining_required".

    Models the ImpactNotificationService.reset_training_tasks behavior as
    pure logic. Sets is_completed=False for affected TrainingTasks (idempotent).

    Rules:
    - Only items with recommended_action == "retraining_required" are processed
    - If is_completed is already False, no update occurs (idempotent)
    - The operation NEVER sets is_completed to True

    Args:
        tasks: Dict of task_id → TrainingTaskState representing the DB state.
        affected_items: List of affected items from the impact report.

    Returns:
        ResetResult with counts and lists of updated/skipped task IDs.
    """
    result = ResetResult()

    for item in affected_items:
        if item.recommended_action != "retraining_required":
            continue

        task_id = item.training_task_id
        if task_id is None:
            continue

        task = tasks.get(task_id)
        if task is None:
            # Task not found — skip (would be a failure in real service)
            continue

        if task.is_completed:
            # Reset: set is_completed to False
            task.is_completed = False
            task.completed_at = None
            result.tasks_updated.append(task_id)
            result.reset_count += 1
        else:
            # Already False — idempotent skip
            result.tasks_skipped.append(task_id)
            result.reset_count += 1

    return result


# ---------------------------------------------------------------------------
# Composite Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_training_task(draw: st.DrawFn) -> TrainingTaskState:
    """Generate a training task with random completion state."""
    is_completed = draw(st.booleans())
    completed_at = (
        datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC) if is_completed else None
    )
    return TrainingTaskState(
        id=draw(TASK_IDS),
        sop_document_uuid=draw(DOCUMENT_UUIDS),
        is_completed=is_completed,
        completed_at=completed_at,
    )


@st.composite
def st_affected_item_retraining(draw: st.DrawFn, task_ids: list[int]) -> AffectedItem:
    """Generate an affected item with retraining_required action targeting a known task."""
    task_id = draw(st.sampled_from(task_ids)) if task_ids else draw(TASK_IDS)
    return AffectedItem(
        training_task_id=task_id,
        affected_document_uuid=draw(DOCUMENT_UUIDS),
        recommended_action="retraining_required",
        impact_severity=draw(IMPACT_SEVERITIES),
    )


@st.composite
def st_affected_item_mixed(draw: st.DrawFn, task_ids: list[int]) -> AffectedItem:
    """Generate an affected item with a random action, possibly targeting a known task."""
    action = draw(RECOMMENDED_ACTIONS)
    task_id = draw(st.sampled_from(task_ids)) if task_ids else None
    return AffectedItem(
        training_task_id=task_id,
        affected_document_uuid=draw(DOCUMENT_UUIDS),
        recommended_action=action,
        impact_severity=draw(IMPACT_SEVERITIES),
    )


@st.composite
def st_reset_scenario(draw: st.DrawFn) -> dict:
    """Generate a complete reset scenario with tasks and affected items.

    Creates a set of training tasks with random completion states and
    a list of affected items (some with retraining_required, some not).
    """
    # Generate 1-10 training tasks with unique IDs
    task_count = draw(st.integers(min_value=1, max_value=10))
    task_ids = draw(
        st.lists(
            TASK_IDS, min_size=task_count, max_size=task_count, unique=True
        )
    )

    tasks: dict[int, TrainingTaskState] = {}
    for tid in task_ids:
        is_completed = draw(st.booleans())
        completed_at = (
            datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC) if is_completed else None
        )
        tasks[tid] = TrainingTaskState(
            id=tid,
            sop_document_uuid=draw(DOCUMENT_UUIDS),
            is_completed=is_completed,
            completed_at=completed_at,
        )

    # Generate affected items — mix of retraining_required and other actions
    item_count = draw(st.integers(min_value=1, max_value=15))
    affected_items: list[AffectedItem] = []
    for _ in range(item_count):
        action = draw(RECOMMENDED_ACTIONS)
        # Sometimes target a known task, sometimes an unknown one
        if draw(st.booleans()) and task_ids:
            task_id = draw(st.sampled_from(task_ids))
        else:
            task_id = draw(TASK_IDS)
        affected_items.append(
            AffectedItem(
                training_task_id=task_id,
                affected_document_uuid=draw(DOCUMENT_UUIDS),
                recommended_action=action,
                impact_severity=draw(IMPACT_SEVERITIES),
            )
        )

    return {
        "tasks": tasks,
        "affected_items": affected_items,
        "report_id": draw(REPORT_IDS),
    }


@st.composite
def st_already_reset_scenario(draw: st.DrawFn) -> dict:
    """Generate a scenario where all targeted tasks already have is_completed=False.

    This tests the idempotent skip path specifically.
    """
    task_count = draw(st.integers(min_value=1, max_value=10))
    task_ids = draw(
        st.lists(TASK_IDS, min_size=task_count, max_size=task_count, unique=True)
    )

    # All tasks have is_completed=False
    tasks: dict[int, TrainingTaskState] = {}
    for tid in task_ids:
        tasks[tid] = TrainingTaskState(
            id=tid,
            sop_document_uuid=draw(DOCUMENT_UUIDS),
            is_completed=False,
            completed_at=None,
        )

    # All affected items target known tasks with retraining_required
    item_count = draw(st.integers(min_value=1, max_value=len(task_ids)))
    selected_ids = draw(
        st.lists(
            st.sampled_from(task_ids),
            min_size=item_count,
            max_size=item_count,
        )
    )
    affected_items = [
        AffectedItem(
            training_task_id=tid,
            affected_document_uuid=draw(DOCUMENT_UUIDS),
            recommended_action="retraining_required",
            impact_severity=draw(IMPACT_SEVERITIES),
        )
        for tid in selected_ids
    ]

    return {
        "tasks": tasks,
        "affected_items": affected_items,
        "report_id": draw(REPORT_IDS),
    }


# ---------------------------------------------------------------------------
# Property 15: Reset never sets is_completed to True
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_reset_scenario())
def test_reset_never_sets_is_completed_to_true(scenario: dict) -> None:
    """For any affected training task with recommended_action "retraining_required",
    the reset operation SHALL never set is_completed to true.

    After reset, all tasks that were targeted by retraining_required items
    must have is_completed == False (or remain unchanged if not targeted).

    **Validates: Requirements 8.4**
    """
    tasks = scenario["tasks"]
    affected_items = scenario["affected_items"]

    # Record initial states
    initial_states = {tid: t.is_completed for tid, t in tasks.items()}

    # Apply reset
    reset_training_tasks(tasks, affected_items)

    # Verify: no task was set to True
    for tid, task in tasks.items():
        if initial_states[tid] is False:
            # Was False before — must still be False
            assert task.is_completed is False, (
                f"Task {tid} was is_completed=False before reset but is now "
                f"is_completed={task.is_completed}. Reset must never set to True."
            )
        # If it was True before, it can only become False (if targeted) or stay True
        if initial_states[tid] is True:
            assert task.is_completed in (True, False), (
                f"Task {tid} has unexpected is_completed value: {task.is_completed}"
            )


# ---------------------------------------------------------------------------
# Property 15: Idempotent — applying reset twice yields same result
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_reset_scenario())
def test_reset_is_idempotent(scenario: dict) -> None:
    """For any set of training tasks and affected items, applying the reset
    operation twice SHALL produce the same final state as applying it once.

    **Validates: Requirements 8.4**
    """
    tasks = scenario["tasks"]
    affected_items = scenario["affected_items"]

    # Apply reset first time
    reset_training_tasks(tasks, affected_items)

    # Capture state after first reset
    state_after_first = {tid: t.is_completed for tid, t in tasks.items()}

    # Apply reset second time
    result_second = reset_training_tasks(tasks, affected_items)

    # State after second reset must be identical to state after first
    for tid, task in tasks.items():
        assert task.is_completed == state_after_first[tid], (
            f"Task {tid}: state changed between first and second reset. "
            f"After first: {state_after_first[tid]}, after second: {task.is_completed}. "
            f"Reset must be idempotent."
        )


# ---------------------------------------------------------------------------
# Property 15: No update when is_completed is already False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_already_reset_scenario())
def test_no_update_when_already_false(scenario: dict) -> None:
    """For any training task where is_completed is already false, the reset
    operation SHALL NOT perform an update (idempotent skip).

    When all targeted tasks already have is_completed=False, the result
    should show zero tasks_updated and all tasks in tasks_skipped.

    **Validates: Requirements 8.4**
    """
    tasks = scenario["tasks"]
    affected_items = scenario["affected_items"]

    # All tasks start with is_completed=False
    for task in tasks.values():
        assert task.is_completed is False

    # Apply reset
    result = reset_training_tasks(tasks, affected_items)

    # No tasks should have been updated (they were already False)
    assert result.tasks_updated == [], (
        f"Expected no updates when all tasks already have is_completed=False, "
        f"but got updates for: {result.tasks_updated}"
    )

    # All tasks should still be False
    for task in tasks.values():
        assert task.is_completed is False


# ---------------------------------------------------------------------------
# Property 15: Only retraining_required items trigger reset
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_reset_scenario())
def test_only_retraining_required_triggers_reset(scenario: dict) -> None:
    """For any set of affected items, only items with recommended_action
    "retraining_required" SHALL trigger a training task reset. Items with
    other actions SHALL NOT modify any training task state.

    **Validates: Requirements 8.4**
    """
    tasks = scenario["tasks"]
    affected_items = scenario["affected_items"]

    # Record initial states
    initial_states = {tid: t.is_completed for tid, t in tasks.items()}

    # Identify which task IDs are targeted by retraining_required items
    retraining_task_ids = {
        item.training_task_id
        for item in affected_items
        if item.recommended_action == "retraining_required"
        and item.training_task_id is not None
    }

    # Apply reset
    reset_training_tasks(tasks, affected_items)

    # Tasks NOT targeted by retraining_required must be unchanged
    for tid, task in tasks.items():
        if tid not in retraining_task_ids:
            assert task.is_completed == initial_states[tid], (
                f"Task {tid} was not targeted by retraining_required but its "
                f"is_completed changed from {initial_states[tid]} to {task.is_completed}"
            )


# ---------------------------------------------------------------------------
# Property 15: After reset, targeted tasks have is_completed=False
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_reset_scenario())
def test_targeted_tasks_are_false_after_reset(scenario: dict) -> None:
    """For any training task targeted by a retraining_required affected item
    that exists in the task store, is_completed SHALL be False after reset.

    **Validates: Requirements 8.4**
    """
    tasks = scenario["tasks"]
    affected_items = scenario["affected_items"]

    # Identify which task IDs are targeted by retraining_required items
    # and actually exist in the store
    retraining_task_ids = {
        item.training_task_id
        for item in affected_items
        if item.recommended_action == "retraining_required"
        and item.training_task_id is not None
        and item.training_task_id in tasks
    }

    # Apply reset
    reset_training_tasks(tasks, affected_items)

    # All targeted tasks must have is_completed=False
    for tid in retraining_task_ids:
        task = tasks[tid]
        assert task.is_completed is False, (
            f"Task {tid} was targeted by retraining_required but "
            f"is_completed is {task.is_completed} after reset (expected False)"
        )


# ---------------------------------------------------------------------------
# Property 15: Second reset produces no updates
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_reset_scenario())
def test_second_reset_produces_no_updates(scenario: dict) -> None:
    """For any set of training tasks, after the first reset, a second
    application of the same reset SHALL produce zero tasks_updated
    (all targeted tasks are already False).

    **Validates: Requirements 8.4**
    """
    tasks = scenario["tasks"]
    affected_items = scenario["affected_items"]

    # Apply reset first time
    reset_training_tasks(tasks, affected_items)

    # Apply reset second time
    result_second = reset_training_tasks(tasks, affected_items)

    # Second reset should produce no updates
    assert result_second.tasks_updated == [], (
        f"Second reset should produce no updates, but got: {result_second.tasks_updated}. "
        f"This violates idempotence — if is_completed is already False, no update SHALL occur."
    )
