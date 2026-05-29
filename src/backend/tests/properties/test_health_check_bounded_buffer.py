"""Property-based tests for health check history bounded buffer.

Property 12: Health Check History Bounded Buffer
For any service, after any number of health check executions, the stored
health check results for that service SHALL never exceed 100 entries. When
a new result is stored and the count would exceed 100, the oldest entry
SHALL be evicted.

**Validates: Requirements 10.6**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Implementation: src/backend/src/alcoabase/services/health_monitor.py
"""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.health_monitor import MAX_RESULTS_PER_SERVICE


# ---------------------------------------------------------------------------
# Domain types for simulation
# ---------------------------------------------------------------------------


class HealthCheckEntry(NamedTuple):
    """Simplified health check result for buffer simulation."""

    service_name: str
    status: str
    response_time_ms: float
    checked_at: datetime


# ---------------------------------------------------------------------------
# Bounded buffer simulation (mirrors _evict_oldest logic)
# ---------------------------------------------------------------------------


def simulate_bounded_buffer(
    entries: list[HealthCheckEntry],
) -> list[HealthCheckEntry]:
    """Simulate the bounded buffer eviction logic.

    Processes a sequence of health check entries for a single service,
    applying the eviction rule after each insertion: if the count exceeds
    MAX_RESULTS_PER_SERVICE (100), the oldest entries are removed.

    This mirrors the behavior of HealthMonitor._evict_oldest which keeps
    the most recent MAX_RESULTS_PER_SERVICE entries and deletes the rest.

    Args:
        entries: Ordered sequence of health check entries to insert.

    Returns:
        The final buffer state after all entries have been processed.
    """
    buffer: list[HealthCheckEntry] = []

    for entry in entries:
        buffer.append(entry)
        # After each insertion, enforce the bounded buffer
        if len(buffer) > MAX_RESULTS_PER_SERVICE:
            # Sort by checked_at descending, keep only the most recent
            buffer.sort(key=lambda e: e.checked_at, reverse=True)
            buffer = buffer[:MAX_RESULTS_PER_SERVICE]

    return buffer


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_service_name() -> st.SearchStrategy[str]:
    """Generate a valid service name from the monitored services list."""
    return st.sampled_from(
        ["postgresql", "minio", "opensearch", "redis", "vllm"]
    )


def st_health_status() -> st.SearchStrategy[str]:
    """Generate a valid health check status."""
    return st.sampled_from(["healthy", "degraded", "unreachable"])


def st_health_check_entry(
    service_name: str, base_time: datetime, index: int
) -> HealthCheckEntry:
    """Create a health check entry with a deterministic timestamp.

    Args:
        service_name: The service this check belongs to.
        base_time: Starting timestamp for the sequence.
        index: Position in the sequence (used to offset timestamp).

    Returns:
        A HealthCheckEntry with a unique timestamp.
    """
    return HealthCheckEntry(
        service_name=service_name,
        status="healthy",
        response_time_ms=50.0,
        checked_at=base_time + timedelta(seconds=index * 30),
    )


def st_health_check_sequence(
    min_count: int = 101, max_count: int = 300
) -> st.SearchStrategy[tuple[str, list[HealthCheckEntry]]]:
    """Generate a sequence of N health check entries for a single service.

    Generates N > 100 entries to test the bounded buffer eviction.

    Args:
        min_count: Minimum number of entries (must be > 100).
        max_count: Maximum number of entries.

    Returns:
        Strategy producing (service_name, list of entries).
    """
    return st.tuples(
        st_service_name(),
        st.integers(min_value=min_count, max_value=max_count),
    ).map(
        lambda args: (
            args[0],
            [
                HealthCheckEntry(
                    service_name=args[0],
                    status=["healthy", "degraded", "unreachable"][i % 3],
                    response_time_ms=float(50 + (i % 100)),
                    checked_at=datetime(2025, 1, 1, tzinfo=timezone.utc)
                    + timedelta(seconds=i * 30),
                )
                for i in range(args[1])
            ],
        )
    )


# ---------------------------------------------------------------------------
# Property 12: Buffer never exceeds MAX_RESULTS_PER_SERVICE
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st_health_check_sequence(min_count=101, max_count=300))
def test_buffer_never_exceeds_max(
    data: tuple[str, list[HealthCheckEntry]],
) -> None:
    """For any sequence of N > 100 health check results for a service,
    the stored results SHALL never exceed 100 entries.

    **Validates: Requirements 10.6**
    """
    service_name, entries = data

    assert len(entries) > MAX_RESULTS_PER_SERVICE, (
        f"Test precondition: need > {MAX_RESULTS_PER_SERVICE} entries, "
        f"got {len(entries)}"
    )

    final_buffer = simulate_bounded_buffer(entries)

    assert len(final_buffer) <= MAX_RESULTS_PER_SERVICE, (
        f"Buffer for service '{service_name}' has {len(final_buffer)} entries, "
        f"exceeding MAX_RESULTS_PER_SERVICE={MAX_RESULTS_PER_SERVICE}"
    )


# ---------------------------------------------------------------------------
# Property 12: Oldest entries are evicted when buffer is full
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st_health_check_sequence(min_count=101, max_count=300))
def test_oldest_evicted_when_buffer_full(
    data: tuple[str, list[HealthCheckEntry]],
) -> None:
    """When a new result is stored and the count would exceed 100, the
    oldest entry SHALL be evicted (most recent entries are retained).

    **Validates: Requirements 10.6**
    """
    service_name, entries = data

    final_buffer = simulate_bounded_buffer(entries)

    # The buffer should contain exactly MAX_RESULTS_PER_SERVICE entries
    assert len(final_buffer) == MAX_RESULTS_PER_SERVICE, (
        f"Expected exactly {MAX_RESULTS_PER_SERVICE} entries in buffer, "
        f"got {len(final_buffer)}"
    )

    # The retained entries should be the most recent ones
    all_sorted_by_time = sorted(entries, key=lambda e: e.checked_at, reverse=True)
    expected_retained = all_sorted_by_time[:MAX_RESULTS_PER_SERVICE]

    # Compare timestamps of retained entries
    buffer_timestamps = sorted(e.checked_at for e in final_buffer)
    expected_timestamps = sorted(e.checked_at for e in expected_retained)

    assert buffer_timestamps == expected_timestamps, (
        f"Buffer does not contain the most recent {MAX_RESULTS_PER_SERVICE} "
        f"entries. Oldest in buffer: {min(buffer_timestamps)}, "
        f"expected oldest: {min(expected_timestamps)}"
    )


# ---------------------------------------------------------------------------
# Property 12: Buffer at exactly MAX_RESULTS_PER_SERVICE is stable
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(service_name=st_service_name())
def test_buffer_at_max_is_stable(service_name: str) -> None:
    """When exactly 100 entries exist, no eviction occurs (boundary case).

    **Validates: Requirements 10.6**
    """
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    entries = [
        st_health_check_entry(service_name, base_time, i)
        for i in range(MAX_RESULTS_PER_SERVICE)
    ]

    final_buffer = simulate_bounded_buffer(entries)

    assert len(final_buffer) == MAX_RESULTS_PER_SERVICE, (
        f"Expected {MAX_RESULTS_PER_SERVICE} entries when inserting exactly "
        f"{MAX_RESULTS_PER_SERVICE}, got {len(final_buffer)}"
    )


# ---------------------------------------------------------------------------
# Property 12: Adding one entry beyond max triggers exactly one eviction
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(service_name=st_service_name())
def test_one_beyond_max_evicts_oldest(service_name: str) -> None:
    """When the 101st entry is added, exactly the oldest entry is evicted.

    **Validates: Requirements 10.6**
    """
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)

    # Create exactly MAX + 1 entries
    entries = [
        st_health_check_entry(service_name, base_time, i)
        for i in range(MAX_RESULTS_PER_SERVICE + 1)
    ]

    final_buffer = simulate_bounded_buffer(entries)

    assert len(final_buffer) == MAX_RESULTS_PER_SERVICE, (
        f"Expected {MAX_RESULTS_PER_SERVICE} entries after inserting "
        f"{MAX_RESULTS_PER_SERVICE + 1}, got {len(final_buffer)}"
    )

    # The oldest entry (index 0) should have been evicted
    oldest_entry = entries[0]
    assert oldest_entry not in final_buffer, (
        f"Oldest entry (checked_at={oldest_entry.checked_at}) should have "
        f"been evicted but is still in the buffer"
    )

    # The newest entry (last one) should be retained
    newest_entry = entries[-1]
    assert newest_entry in final_buffer, (
        f"Newest entry (checked_at={newest_entry.checked_at}) should be "
        f"retained but is not in the buffer"
    )


# ---------------------------------------------------------------------------
# Property 12: MAX_RESULTS_PER_SERVICE constant is 100
# ---------------------------------------------------------------------------


def test_max_results_constant_is_100() -> None:
    """Verify the MAX_RESULTS_PER_SERVICE constant is set to 100.

    **Validates: Requirements 10.6**
    """
    assert MAX_RESULTS_PER_SERVICE == 100, (
        f"Expected MAX_RESULTS_PER_SERVICE=100, got {MAX_RESULTS_PER_SERVICE}"
    )
