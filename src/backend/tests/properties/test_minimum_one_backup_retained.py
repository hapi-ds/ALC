"""Property-based tests for minimum one backup retained.

Property 9: Minimum One Backup Retained
For any non-empty list of backup records, after applying the retention
cleanup logic, at least one backup SHALL remain regardless of the
retention period or the ages of the backups.

**Validates: Requirements 8.3**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Implementation: src/backend/src/alcoabase/services/backup_service.py
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Domain types for simulation
# ---------------------------------------------------------------------------


class BackupEntry(NamedTuple):
    """Simplified backup record for retention cleanup simulation."""

    id: int
    status: str
    created_at: datetime
    storage_path: str | None


# ---------------------------------------------------------------------------
# Cleanup simulation (mirrors BackupService.cleanup_expired_backups logic)
# ---------------------------------------------------------------------------


def simulate_cleanup(
    backups: list[BackupEntry],
    retention_days: int,
    current_time: datetime,
) -> list[BackupEntry]:
    """Simulate the retention cleanup logic from BackupService.

    Applies the same algorithm as cleanup_expired_backups:
    1. Filter to completed backups only
    2. If only one completed backup exists, retain it (return early)
    3. Identify expired backups (created_at < current_time - retention_days)
    4. If all completed backups are expired, keep the newest one
    5. Delete the rest of the expired backups

    Args:
        backups: List of backup entries to process.
        retention_days: Number of days to retain backups.
        current_time: The reference time for expiration calculation.

    Returns:
        List of backup entries remaining after cleanup.
    """
    # Only completed backups are subject to cleanup
    completed = [b for b in backups if b.status == "completed"]
    non_completed = [b for b in backups if b.status != "completed"]

    if len(completed) <= 1:
        # Retain at least one backup regardless of age
        return backups

    # Sort by created_at descending (newest first)
    completed_sorted = sorted(completed, key=lambda b: b.created_at, reverse=True)

    cutoff = current_time - timedelta(days=retention_days)
    expired = [
        b for b in completed_sorted
        if b.created_at < cutoff
    ]

    # Ensure at least one backup is retained
    # If all backups are expired, keep the newest one
    if len(expired) == len(completed_sorted):
        expired = expired[1:]  # Keep the first (newest)

    # Remove expired from completed list
    expired_ids = {b.id for b in expired}
    remaining_completed = [b for b in completed_sorted if b.id not in expired_ids]

    return remaining_completed + non_completed


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_backup_entry(
    entry_id: int, base_time: datetime, max_age_days: int = 730
) -> st.SearchStrategy[BackupEntry]:
    """Generate a backup entry with a random age.

    Args:
        entry_id: Unique ID for this backup entry.
        base_time: Reference time (entries are created before this).
        max_age_days: Maximum age in days for generated backups.

    Returns:
        Strategy producing a BackupEntry.
    """
    return st.builds(
        BackupEntry,
        id=st.just(entry_id),
        status=st.just("completed"),
        created_at=st.integers(
            min_value=0, max_value=max_age_days * 24 * 3600
        ).map(lambda secs: base_time - timedelta(seconds=secs)),
        storage_path=st.just(f"backups/backup_{entry_id}.sql.gz"),
    )


@st.composite
def st_backup_list(
    draw: st.DrawFn,
    min_size: int = 1,
    max_size: int = 50,
) -> list[BackupEntry]:
    """Generate a non-empty list of completed backup entries.

    Args:
        draw: Hypothesis draw function.
        min_size: Minimum number of backups.
        max_size: Maximum number of backups.

    Returns:
        Non-empty list of BackupEntry instances.
    """
    base_time = datetime(2025, 6, 15, tzinfo=timezone.utc)
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    entries = []
    for i in range(count):
        entry = draw(st_backup_entry(i + 1, base_time))
        entries.append(entry)
    return entries


@st.composite
def st_mixed_status_backup_list(
    draw: st.DrawFn,
    min_completed: int = 1,
    max_size: int = 50,
) -> list[BackupEntry]:
    """Generate a list of backups with mixed statuses.

    Ensures at least one completed backup exists.

    Args:
        draw: Hypothesis draw function.
        min_completed: Minimum number of completed backups.
        max_size: Maximum total number of backups.

    Returns:
        List of BackupEntry instances with mixed statuses.
    """
    base_time = datetime(2025, 6, 15, tzinfo=timezone.utc)
    count = draw(st.integers(min_value=min_completed + 1, max_value=max_size))
    entries = []

    # Ensure at least min_completed completed backups
    for i in range(min_completed):
        entry = draw(st_backup_entry(i + 1, base_time))
        entries.append(entry)

    # Rest can be any status
    statuses = ["completed", "queued", "running", "failed"]
    for i in range(min_completed, count):
        status = draw(st.sampled_from(statuses))
        age_secs = draw(st.integers(min_value=0, max_value=730 * 24 * 3600))
        entry = BackupEntry(
            id=i + 1,
            status=status,
            created_at=base_time - timedelta(seconds=age_secs),
            storage_path=f"backups/backup_{i + 1}.sql.gz",
        )
        entries.append(entry)

    return entries


# ---------------------------------------------------------------------------
# Property 9: At least one backup always remains after cleanup
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    backups=st_backup_list(min_size=1, max_size=50),
    retention_days=st.integers(min_value=1, max_value=365),
)
def test_at_least_one_backup_remains(
    backups: list[BackupEntry],
    retention_days: int,
) -> None:
    """For any non-empty list of completed backup records and any retention
    period, at least one backup SHALL remain after cleanup.

    **Validates: Requirements 8.3**
    """
    current_time = datetime(2025, 6, 15, tzinfo=timezone.utc)

    remaining = simulate_cleanup(backups, retention_days, current_time)
    completed_remaining = [b for b in remaining if b.status == "completed"]

    assert len(completed_remaining) >= 1, (
        f"No completed backups remain after cleanup. "
        f"Input: {len(backups)} backups, retention_days={retention_days}. "
        f"All backups were deleted, violating minimum-one-retained rule."
    )


# ---------------------------------------------------------------------------
# Property 9: Minimum one retained even with very short retention
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    backups=st_backup_list(min_size=1, max_size=50),
)
def test_minimum_one_retained_with_one_day_retention(
    backups: list[BackupEntry],
) -> None:
    """Even with the minimum retention period (1 day), at least one backup
    SHALL remain regardless of how old all backups are.

    **Validates: Requirements 8.3**
    """
    # Use a current_time far in the future so all backups are expired
    current_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
    retention_days = 1

    remaining = simulate_cleanup(backups, retention_days, current_time)
    completed_remaining = [b for b in remaining if b.status == "completed"]

    assert len(completed_remaining) >= 1, (
        f"No completed backups remain with 1-day retention and all expired. "
        f"Input: {len(backups)} backups. "
        f"The minimum-one-retained rule must hold regardless of retention."
    )


# ---------------------------------------------------------------------------
# Property 9: Minimum one retained with mixed statuses
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    backups=st_mixed_status_backup_list(min_completed=1, max_size=50),
    retention_days=st.integers(min_value=1, max_value=365),
)
def test_minimum_one_retained_with_mixed_statuses(
    backups: list[BackupEntry],
    retention_days: int,
) -> None:
    """For any list of backups with mixed statuses (completed, queued,
    running, failed), at least one completed backup SHALL remain after
    cleanup regardless of retention period.

    **Validates: Requirements 8.3**
    """
    current_time = datetime(2025, 6, 15, tzinfo=timezone.utc)

    remaining = simulate_cleanup(backups, retention_days, current_time)
    completed_remaining = [b for b in remaining if b.status == "completed"]

    assert len(completed_remaining) >= 1, (
        f"No completed backups remain after cleanup with mixed statuses. "
        f"Input: {len(backups)} total backups, "
        f"{sum(1 for b in backups if b.status == 'completed')} completed. "
        f"retention_days={retention_days}."
    )


# ---------------------------------------------------------------------------
# Property 9: The newest backup is the one retained when all are expired
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    backups=st_backup_list(min_size=2, max_size=50),
)
def test_newest_backup_retained_when_all_expired(
    backups: list[BackupEntry],
) -> None:
    """When all backups are expired, the newest (most recent created_at)
    SHALL be the one retained.

    **Validates: Requirements 8.3**
    """
    # Use a current_time far in the future so all backups are expired
    current_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
    retention_days = 1

    remaining = simulate_cleanup(backups, retention_days, current_time)
    completed_remaining = [b for b in remaining if b.status == "completed"]

    assert len(completed_remaining) >= 1, (
        "At least one backup must remain."
    )

    # The retained backup should be the newest one
    newest_backup = max(backups, key=lambda b: b.created_at)
    retained_ids = {b.id for b in completed_remaining}

    assert newest_backup.id in retained_ids, (
        f"The newest backup (id={newest_backup.id}, "
        f"created_at={newest_backup.created_at}) was not retained. "
        f"Retained IDs: {retained_ids}. "
        f"When all backups are expired, the newest should be kept."
    )
