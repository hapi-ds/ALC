"""Property-based tests for conflict detection with staleness threshold.

Property 6: Conflict Detection with Staleness

For any impact analysis trigger request where a job with status "processing"
already exists for the same document_uuid, the system SHALL return HTTP 409
with the existing job_id IF the job's last progress update is within 600
seconds. If the existing job's last update exceeds 600 seconds, the system
SHALL treat it as stale and allow a new job to be created.

**Validates: Requirements 2.5**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_analysis_trigger.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Constants matching the production implementation
# ---------------------------------------------------------------------------

STALENESS_THRESHOLD_SECONDS = 600


# ---------------------------------------------------------------------------
# Domain model for conflict detection (pure logic under test)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExistingJob:
    """Represents an existing processing job for a document.

    Attributes:
        job_id: The unique identifier of the existing job.
        started_at: The timestamp when the job started (timezone-aware UTC).
    """

    job_id: str
    started_at: datetime


def check_conflict(
    existing_job: ExistingJob | None,
    now: datetime,
) -> str | None:
    """Determine whether an existing job blocks a new trigger.

    Implements the conflict detection logic from Requirement 2.5:
    - If no existing processing job exists → allow (return None)
    - If an existing job's started_at is within STALENESS_THRESHOLD_SECONDS
      of now → conflict (return job_id, indicating 409)
    - If an existing job's started_at exceeds STALENESS_THRESHOLD_SECONDS
      → stale, allow new job (return None)

    Args:
        existing_job: The existing processing job, or None if no job exists.
        now: The current UTC timestamp for comparison.

    Returns:
        The job_id if the existing job is active (non-stale), None otherwise.
    """
    if existing_job is None:
        return None

    started_at = existing_job.started_at
    # Ensure timezone-aware comparison
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    elapsed_seconds = (now - started_at).total_seconds()

    if elapsed_seconds < STALENESS_THRESHOLD_SECONDS:
        return existing_job.job_id

    return None


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_job_id() -> st.SearchStrategy[str]:
    """Generate a random UUID-like job ID string."""
    return st.uuids().map(str)


def st_utc_now() -> st.SearchStrategy[datetime]:
    """Generate a 'current' UTC timestamp within a reasonable range."""
    return st.datetimes(
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2030, 12, 31),
        timezones=st.just(timezone.utc),
    )


def st_elapsed_seconds_non_stale() -> st.SearchStrategy[float]:
    """Generate elapsed seconds that are within the staleness threshold.

    Range: [0, 600) — job is active and should block new triggers.
    """
    return st.floats(
        min_value=0.0,
        max_value=STALENESS_THRESHOLD_SECONDS - 0.001,
        allow_nan=False,
        allow_infinity=False,
    )


def st_elapsed_seconds_stale() -> st.SearchStrategy[float]:
    """Generate elapsed seconds that exceed the staleness threshold.

    Range: [600, 86400] — job is stale and should allow new triggers.
    """
    return st.floats(
        min_value=STALENESS_THRESHOLD_SECONDS,
        max_value=86400.0,  # Up to 24 hours
        allow_nan=False,
        allow_infinity=False,
    )


@st.composite
def st_existing_job_non_stale(
    draw: st.DrawFn,
    now: datetime,
) -> ExistingJob:
    """Generate an existing job that is within the staleness threshold.

    The job's started_at will be less than 600 seconds before `now`.
    """
    job_id = draw(st_job_id())
    elapsed = draw(st_elapsed_seconds_non_stale())
    started_at = now - timedelta(seconds=elapsed)
    return ExistingJob(job_id=job_id, started_at=started_at)


@st.composite
def st_existing_job_stale(
    draw: st.DrawFn,
    now: datetime,
) -> ExistingJob:
    """Generate an existing job that exceeds the staleness threshold.

    The job's started_at will be 600 or more seconds before `now`.
    """
    job_id = draw(st_job_id())
    elapsed = draw(st_elapsed_seconds_stale())
    started_at = now - timedelta(seconds=elapsed)
    return ExistingJob(job_id=job_id, started_at=started_at)


# ---------------------------------------------------------------------------
# Property 6: No existing job → always allow new trigger
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(now=st_utc_now())
def test_no_existing_job_allows_new_trigger(now: datetime) -> None:
    """For any trigger request where no processing job exists for the same
    document_uuid, the system SHALL allow a new job to be created (no conflict).

    **Validates: Requirements 2.5**
    """
    result = check_conflict(existing_job=None, now=now)
    assert result is None, (
        f"Expected no conflict when no existing job, but got job_id={result}"
    )


# ---------------------------------------------------------------------------
# Property 6: Non-stale job → return 409 with existing job_id
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(data=st.data())
def test_non_stale_job_returns_conflict(data: st.DataObject) -> None:
    """For any trigger request where a processing job exists with
    started_at within 600 seconds of now, the system SHALL return
    HTTP 409 with the existing job_id (conflict detected).

    **Validates: Requirements 2.5**
    """
    now = data.draw(st_utc_now())
    existing_job = data.draw(st_existing_job_non_stale(now=now))

    result = check_conflict(existing_job=existing_job, now=now)

    assert result is not None, (
        f"Expected conflict (409) for non-stale job, but got None. "
        f"Job started_at={existing_job.started_at}, now={now}, "
        f"elapsed={(now - existing_job.started_at).total_seconds():.1f}s"
    )
    assert result == existing_job.job_id, (
        f"Expected job_id={existing_job.job_id}, but got {result}"
    )


# ---------------------------------------------------------------------------
# Property 6: Stale job → allow new trigger (treat as expired)
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(data=st.data())
def test_stale_job_allows_new_trigger(data: st.DataObject) -> None:
    """For any trigger request where a processing job exists with
    started_at exceeding 600 seconds from now, the system SHALL treat
    it as stale and allow a new job to be created (no conflict).

    **Validates: Requirements 2.5**
    """
    now = data.draw(st_utc_now())
    existing_job = data.draw(st_existing_job_stale(now=now))

    result = check_conflict(existing_job=existing_job, now=now)

    assert result is None, (
        f"Expected stale job to allow new trigger, but got conflict "
        f"job_id={result}. Job started_at={existing_job.started_at}, "
        f"now={now}, elapsed={(now - existing_job.started_at).total_seconds():.1f}s"
    )


# ---------------------------------------------------------------------------
# Property 6: Exact boundary at 600 seconds → stale (>= threshold)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(now=st_utc_now(), job_id=st_job_id())
def test_exact_threshold_boundary_is_stale(now: datetime, job_id: str) -> None:
    """For any trigger request where a processing job's elapsed time is
    exactly 600 seconds, the system SHALL treat it as stale and allow
    a new job (the threshold is exclusive: elapsed < 600 means active).

    **Validates: Requirements 2.5**
    """
    started_at = now - timedelta(seconds=STALENESS_THRESHOLD_SECONDS)
    existing_job = ExistingJob(job_id=job_id, started_at=started_at)

    result = check_conflict(existing_job=existing_job, now=now)

    assert result is None, (
        f"Expected job at exactly {STALENESS_THRESHOLD_SECONDS}s to be stale, "
        f"but got conflict job_id={result}"
    )


# ---------------------------------------------------------------------------
# Property 6: Staleness is monotonic — once stale, always stale
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data())
def test_staleness_is_monotonic(data: st.DataObject) -> None:
    """For any existing job, if it is stale at time T, it SHALL also be
    stale at any time T' > T. Staleness never reverses as time advances.

    **Validates: Requirements 2.5**
    """
    now = data.draw(st_utc_now())
    existing_job = data.draw(st_existing_job_stale(now=now))

    # Verify it's stale at `now`
    result_at_now = check_conflict(existing_job=existing_job, now=now)
    assert result_at_now is None, "Job should be stale at initial time"

    # Advance time by a random positive amount
    advance_seconds = data.draw(
        st.floats(min_value=0.001, max_value=3600.0, allow_nan=False, allow_infinity=False)
    )
    later = now + timedelta(seconds=advance_seconds)

    result_at_later = check_conflict(existing_job=existing_job, now=later)
    assert result_at_later is None, (
        f"Job was stale at {now} but became active at {later} "
        f"(+{advance_seconds:.1f}s). Staleness must be monotonic."
    )


# ---------------------------------------------------------------------------
# Property 6: Non-stale jobs become stale after threshold elapses
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data())
def test_non_stale_job_becomes_stale_after_threshold(data: st.DataObject) -> None:
    """For any non-stale job at time T, advancing time by at least
    (STALENESS_THRESHOLD_SECONDS - elapsed) SHALL make it stale.

    **Validates: Requirements 2.5**
    """
    now = data.draw(st_utc_now())
    existing_job = data.draw(st_existing_job_non_stale(now=now))

    # Verify it's active (non-stale) at `now`
    result_at_now = check_conflict(existing_job=existing_job, now=now)
    assert result_at_now == existing_job.job_id, "Job should be active at initial time"

    # Compute how much time needs to pass to make it stale
    elapsed_now = (now - existing_job.started_at).total_seconds()
    remaining = STALENESS_THRESHOLD_SECONDS - elapsed_now

    # Advance time past the threshold
    advance = remaining + data.draw(
        st.floats(min_value=0.001, max_value=3600.0, allow_nan=False, allow_infinity=False)
    )
    later = now + timedelta(seconds=advance)

    result_at_later = check_conflict(existing_job=existing_job, now=later)
    assert result_at_later is None, (
        f"Job should become stale after advancing {advance:.1f}s past threshold, "
        f"but still returned conflict. Total elapsed: "
        f"{(later - existing_job.started_at).total_seconds():.1f}s"
    )


# ---------------------------------------------------------------------------
# Property 6: Naive timestamps are handled correctly (treated as UTC)
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(now=st_utc_now(), job_id=st_job_id())
def test_naive_timestamp_treated_as_utc(now: datetime, job_id: str) -> None:
    """For any existing job with a naive (timezone-unaware) started_at
    timestamp, the system SHALL treat it as UTC for staleness comparison.

    **Validates: Requirements 2.5**
    """
    # Create a job that started 300 seconds ago (non-stale)
    started_at_aware = now - timedelta(seconds=300)
    started_at_naive = started_at_aware.replace(tzinfo=None)

    existing_job = ExistingJob(job_id=job_id, started_at=started_at_naive)

    result = check_conflict(existing_job=existing_job, now=now)

    # Should still detect as non-stale (300s < 600s threshold)
    assert result == job_id, (
        f"Naive timestamp should be treated as UTC. "
        f"Expected conflict for 300s elapsed, but got None."
    )


# ---------------------------------------------------------------------------
# Property 6: Conflict detection is deterministic
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data())
def test_conflict_detection_is_deterministic(data: st.DataObject) -> None:
    """For any given existing job and current time, calling check_conflict
    multiple times SHALL produce the same result.

    **Validates: Requirements 2.5**
    """
    now = data.draw(st_utc_now())
    has_job = data.draw(st.booleans())

    if has_job:
        job_id = data.draw(st_job_id())
        elapsed = data.draw(
            st.floats(min_value=0.0, max_value=1200.0, allow_nan=False, allow_infinity=False)
        )
        started_at = now - timedelta(seconds=elapsed)
        existing_job: ExistingJob | None = ExistingJob(job_id=job_id, started_at=started_at)
    else:
        existing_job = None

    result1 = check_conflict(existing_job=existing_job, now=now)
    result2 = check_conflict(existing_job=existing_job, now=now)

    assert result1 == result2, (
        f"Conflict detection must be deterministic. "
        f"Got {result1} then {result2} for same inputs."
    )
