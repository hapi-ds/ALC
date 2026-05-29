"""Property-based tests for backup expiration logic.

Property 8: Backup Expiration Logic
For any backup record with a creation timestamp and for any retention period
in days, the backup SHALL be marked as expired if and only if the current
time minus the backup creation timestamp exceeds the retention period in days.

**Validates: Requirements 8.2**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Implementation: src/backend/src/alcoabase/services/backup_service.py
"""

from datetime import datetime, timedelta, timezone

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure expiration logic (mirrors cleanup_expired_backups cutoff calculation)
# ---------------------------------------------------------------------------


def is_backup_expired(
    created_at: datetime,
    current_time: datetime,
    retention_days: int,
) -> bool:
    """Determine if a backup is expired based on retention policy.

    A backup is expired if the elapsed time since creation exceeds the
    retention period. This mirrors the cutoff logic in
    BackupService.cleanup_expired_backups:
        cutoff = current_time - timedelta(days=retention_days)
        expired = created_at < cutoff

    Args:
        created_at: Timestamp when the backup was created.
        current_time: The reference "now" time for expiration check.
        retention_days: Number of days to retain backups.

    Returns:
        True if the backup is expired, False otherwise.
    """
    cutoff = current_time - timedelta(days=retention_days)
    return created_at < cutoff


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_retention_days() -> st.SearchStrategy[int]:
    """Generate valid retention periods (1-365 days per Requirements 8.1)."""
    return st.integers(min_value=1, max_value=365)


def st_aware_datetime() -> st.SearchStrategy[datetime]:
    """Generate timezone-aware datetimes within a reasonable range."""
    return st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    )


def st_current_time_after(created_at: datetime) -> st.SearchStrategy[datetime]:
    """Generate a current_time that is after the created_at timestamp.

    Args:
        created_at: The backup creation time (current_time must be >= this).

    Returns:
        Strategy producing datetimes after created_at.
    """
    # Generate an offset of 0 to ~2 years in seconds
    max_offset_seconds = 365 * 2 * 24 * 3600
    return st.integers(min_value=0, max_value=max_offset_seconds).map(
        lambda offset: created_at + timedelta(seconds=offset)
    )


# ---------------------------------------------------------------------------
# Property 8: Backup expired iff current_time - created_at > retention_days
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    created_at=st_aware_datetime(),
    retention_days=st_retention_days(),
    elapsed_seconds=st.integers(min_value=0, max_value=365 * 2 * 24 * 3600),
)
def test_backup_expired_iff_elapsed_exceeds_retention(
    created_at: datetime,
    retention_days: int,
    elapsed_seconds: int,
) -> None:
    """A backup is expired if and only if current_time - created_at > retention_days.

    **Validates: Requirements 8.2**
    """
    current_time = created_at + timedelta(seconds=elapsed_seconds)
    retention_duration = timedelta(days=retention_days)

    expired = is_backup_expired(created_at, current_time, retention_days)
    elapsed_duration = current_time - created_at

    if elapsed_duration > retention_duration:
        assert expired, (
            f"Backup created at {created_at} should be expired: "
            f"elapsed={elapsed_duration} > retention={retention_duration}"
        )
    else:
        assert not expired, (
            f"Backup created at {created_at} should NOT be expired: "
            f"elapsed={elapsed_duration} <= retention={retention_duration}"
        )


# ---------------------------------------------------------------------------
# Property 8: Boundary - backup at exactly retention_days is NOT expired
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    created_at=st_aware_datetime(),
    retention_days=st_retention_days(),
)
def test_backup_at_exact_retention_boundary_not_expired(
    created_at: datetime,
    retention_days: int,
) -> None:
    """A backup whose age equals exactly the retention period is NOT expired.

    The condition is strictly greater-than (created_at < cutoff means
    current_time - created_at > retention_days), so equality means not expired.

    **Validates: Requirements 8.2**
    """
    current_time = created_at + timedelta(days=retention_days)

    expired = is_backup_expired(created_at, current_time, retention_days)

    assert not expired, (
        f"Backup at exactly retention boundary should NOT be expired: "
        f"created_at={created_at}, current_time={current_time}, "
        f"retention_days={retention_days}"
    )


# ---------------------------------------------------------------------------
# Property 8: Backup one second past retention IS expired
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    created_at=st_aware_datetime(),
    retention_days=st_retention_days(),
)
def test_backup_one_second_past_retention_is_expired(
    created_at: datetime,
    retention_days: int,
) -> None:
    """A backup one second older than the retention period IS expired.

    **Validates: Requirements 8.2**
    """
    current_time = created_at + timedelta(days=retention_days, seconds=1)

    expired = is_backup_expired(created_at, current_time, retention_days)

    assert expired, (
        f"Backup one second past retention should be expired: "
        f"created_at={created_at}, current_time={current_time}, "
        f"retention_days={retention_days}"
    )


# ---------------------------------------------------------------------------
# Property 8: Fresh backup (age=0) is never expired
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    created_at=st_aware_datetime(),
    retention_days=st_retention_days(),
)
def test_fresh_backup_never_expired(
    created_at: datetime,
    retention_days: int,
) -> None:
    """A backup checked at its creation time is never expired.

    **Validates: Requirements 8.2**
    """
    current_time = created_at  # Zero elapsed time

    expired = is_backup_expired(created_at, current_time, retention_days)

    assert not expired, (
        f"Fresh backup (age=0) should never be expired: "
        f"retention_days={retention_days}"
    )


# ---------------------------------------------------------------------------
# Property 8: Expiration is monotonic with time
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    created_at=st_aware_datetime(),
    retention_days=st_retention_days(),
    elapsed_seconds_1=st.integers(min_value=0, max_value=365 * 2 * 24 * 3600),
    additional_seconds=st.integers(min_value=0, max_value=365 * 24 * 3600),
)
def test_expiration_monotonic_with_time(
    created_at: datetime,
    retention_days: int,
    elapsed_seconds_1: int,
    additional_seconds: int,
) -> None:
    """If a backup is expired at time T, it remains expired at any time T' > T.

    Expiration is monotonic: once expired, always expired.

    **Validates: Requirements 8.2**
    """
    time_1 = created_at + timedelta(seconds=elapsed_seconds_1)
    time_2 = time_1 + timedelta(seconds=additional_seconds)

    expired_at_t1 = is_backup_expired(created_at, time_1, retention_days)
    expired_at_t2 = is_backup_expired(created_at, time_2, retention_days)

    if expired_at_t1:
        assert expired_at_t2, (
            f"Backup expired at t1={time_1} must remain expired at t2={time_2} "
            f"(t2 > t1). retention_days={retention_days}"
        )
