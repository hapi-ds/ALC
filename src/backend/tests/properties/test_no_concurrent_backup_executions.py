"""Property-based tests for no concurrent backup executions.

Property 10: No Concurrent Backup Executions
For any sequence of backup trigger requests, if a backup is currently in
"queued" or "running" status, all subsequent trigger requests SHALL be
rejected until the active backup reaches "completed" or "failed" status.

**Validates: Requirements 9.6**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Implementation: src/backend/src/alcoabase/services/backup_service.py
"""

from enum import Enum
from typing import NamedTuple

import hypothesis.strategies as st
from hypothesis import given, settings
from hypothesis.stateful import Bundle, RuleBasedStateMachine, rule


# ---------------------------------------------------------------------------
# Domain types for simulation
# ---------------------------------------------------------------------------


class BackupStatus(str, Enum):
    """Possible backup record statuses."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE_STATUSES = {BackupStatus.QUEUED, BackupStatus.RUNNING}
TERMINAL_STATUSES = {BackupStatus.COMPLETED, BackupStatus.FAILED}


class TriggerResult(NamedTuple):
    """Result of a backup trigger attempt."""

    accepted: bool
    reason: str


class BackupRecord(NamedTuple):
    """Simplified backup record for simulation."""

    task_id: str
    status: BackupStatus


# ---------------------------------------------------------------------------
# Concurrent backup guard simulation (mirrors BackupService logic)
# ---------------------------------------------------------------------------


def is_backup_running(records: list[BackupRecord]) -> bool:
    """Check if any backup is currently in an active state.

    Mirrors BackupService.is_backup_running which queries for records
    with status in ("queued", "running").

    Args:
        records: Current list of backup records.

    Returns:
        True if any record has an active status.
    """
    return any(r.status in ACTIVE_STATUSES for r in records)


def attempt_trigger(records: list[BackupRecord], task_id: str) -> TriggerResult:
    """Attempt to trigger a new backup.

    Mirrors BackupService.trigger_backup which checks is_backup_running
    before creating a new record.

    Args:
        records: Current list of backup records.
        task_id: Unique task ID for the new backup.

    Returns:
        TriggerResult indicating whether the trigger was accepted or rejected.
    """
    if is_backup_running(records):
        return TriggerResult(
            accepted=False,
            reason="A backup is already in progress. Cannot trigger concurrent backups.",
        )
    return TriggerResult(accepted=True, reason="Backup queued successfully.")


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_backup_status() -> st.SearchStrategy[BackupStatus]:
    """Generate a random backup status."""
    return st.sampled_from(list(BackupStatus))


def st_active_status() -> st.SearchStrategy[BackupStatus]:
    """Generate an active backup status (queued or running)."""
    return st.sampled_from([BackupStatus.QUEUED, BackupStatus.RUNNING])


def st_terminal_status() -> st.SearchStrategy[BackupStatus]:
    """Generate a terminal backup status (completed or failed)."""
    return st.sampled_from([BackupStatus.COMPLETED, BackupStatus.FAILED])


def st_task_id() -> st.SearchStrategy[str]:
    """Generate a unique task ID."""
    return st.uuids().map(str)


def st_backup_record(
    status_strategy: st.SearchStrategy[BackupStatus] | None = None,
) -> st.SearchStrategy[BackupRecord]:
    """Generate a backup record with optional status constraint.

    Args:
        status_strategy: Strategy for status. Defaults to any status.

    Returns:
        Strategy producing BackupRecord instances.
    """
    if status_strategy is None:
        status_strategy = st_backup_status()
    return st.builds(
        BackupRecord,
        task_id=st_task_id(),
        status=status_strategy,
    )


# ---------------------------------------------------------------------------
# Property 10: Trigger rejected when active backup exists
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    active_status=st_active_status(),
    other_records=st.lists(
        st_backup_record(status_strategy=st_terminal_status()),
        min_size=0,
        max_size=10,
    ),
    new_task_id=st_task_id(),
)
def test_trigger_rejected_when_active_backup_exists(
    active_status: BackupStatus,
    other_records: list[BackupRecord],
    new_task_id: str,
) -> None:
    """When a backup is in "queued" or "running" status, subsequent trigger
    requests SHALL be rejected.

    **Validates: Requirements 9.6**
    """
    # Create an active backup record
    active_record = BackupRecord(task_id="active-task", status=active_status)
    records = [active_record] + other_records

    result = attempt_trigger(records, new_task_id)

    assert not result.accepted, (
        f"Trigger should be rejected when a backup with status "
        f"'{active_status.value}' exists, but it was accepted. "
        f"Records: {[r.status.value for r in records]}"
    )


# ---------------------------------------------------------------------------
# Property 10: Trigger accepted when no active backup exists
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    records=st.lists(
        st_backup_record(status_strategy=st_terminal_status()),
        min_size=0,
        max_size=20,
    ),
    new_task_id=st_task_id(),
)
def test_trigger_accepted_when_no_active_backup(
    records: list[BackupRecord],
    new_task_id: str,
) -> None:
    """When no backup is in "queued" or "running" status, trigger requests
    SHALL be accepted.

    **Validates: Requirements 9.6**
    """
    # Precondition: no active backups
    assert not is_backup_running(records), (
        "Test precondition violated: records should only contain terminal statuses"
    )

    result = attempt_trigger(records, new_task_id)

    assert result.accepted, (
        f"Trigger should be accepted when no active backup exists, "
        f"but it was rejected. Records: {[r.status.value for r in records]}"
    )


# ---------------------------------------------------------------------------
# Property 10: Trigger accepted on empty history
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(new_task_id=st_task_id())
def test_trigger_accepted_on_empty_history(new_task_id: str) -> None:
    """When no backup records exist at all, trigger requests SHALL be accepted.

    **Validates: Requirements 9.6**
    """
    records: list[BackupRecord] = []

    result = attempt_trigger(records, new_task_id)

    assert result.accepted, (
        "Trigger should be accepted when backup history is empty, "
        "but it was rejected."
    )


# ---------------------------------------------------------------------------
# Property 10: Sequential trigger behavior across state transitions
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    sequence=st.lists(
        st.tuples(
            st.sampled_from(["trigger", "complete", "fail"]),
            st_task_id(),
        ),
        min_size=2,
        max_size=30,
    ),
)
def test_sequential_trigger_behavior(
    sequence: list[tuple[str, str]],
) -> None:
    """For any sequence of trigger/complete/fail actions, triggers are
    rejected if and only if an active backup exists at that moment.

    **Validates: Requirements 9.6**
    """
    records: list[BackupRecord] = []
    active_task_id: str | None = None

    for action, task_id in sequence:
        if action == "trigger":
            has_active = is_backup_running(records)
            result = attempt_trigger(records, task_id)

            if has_active:
                assert not result.accepted, (
                    f"Trigger should be rejected when active backup exists. "
                    f"Active task: {active_task_id}, "
                    f"statuses: {[r.status.value for r in records]}"
                )
            else:
                assert result.accepted, (
                    f"Trigger should be accepted when no active backup. "
                    f"Statuses: {[r.status.value for r in records]}"
                )
                # If accepted, add the new record as queued
                records.append(BackupRecord(task_id=task_id, status=BackupStatus.QUEUED))
                active_task_id = task_id

        elif action == "complete" and active_task_id is not None:
            # Transition active backup to completed
            records = [
                BackupRecord(task_id=r.task_id, status=BackupStatus.COMPLETED)
                if r.task_id == active_task_id
                else r
                for r in records
            ]
            active_task_id = None

        elif action == "fail" and active_task_id is not None:
            # Transition active backup to failed
            records = [
                BackupRecord(task_id=r.task_id, status=BackupStatus.FAILED)
                if r.task_id == active_task_id
                else r
                for r in records
            ]
            active_task_id = None


# ---------------------------------------------------------------------------
# Property 10: Multiple active statuses all block triggers
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    active_statuses=st.lists(
        st_active_status(),
        min_size=1,
        max_size=3,
    ),
    terminal_records=st.lists(
        st_backup_record(status_strategy=st_terminal_status()),
        min_size=0,
        max_size=5,
    ),
    new_task_id=st_task_id(),
)
def test_multiple_active_statuses_block_trigger(
    active_statuses: list[BackupStatus],
    terminal_records: list[BackupRecord],
    new_task_id: str,
) -> None:
    """Even if multiple records are in active states (edge case from
    incomplete transitions), triggers SHALL still be rejected.

    **Validates: Requirements 9.6**
    """
    active_records = [
        BackupRecord(task_id=f"active-{i}", status=status)
        for i, status in enumerate(active_statuses)
    ]
    records = active_records + terminal_records

    result = attempt_trigger(records, new_task_id)

    assert not result.accepted, (
        f"Trigger should be rejected when {len(active_records)} active "
        f"backup(s) exist with statuses "
        f"{[r.status.value for r in active_records]}"
    )
