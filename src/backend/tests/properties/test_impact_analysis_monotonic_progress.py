"""Property-based tests for impact analysis job progress monotonicity.

Tests Property 12 from the AI-Driven Change Impact Analysis design document,
validating that progress updates during an impact analysis job are
monotonically non-decreasing.

Progress follows the pipeline phases:
    10% → 20% → (20-85% proportional to items) → 95% → 100%

Each update must be >= the previous value. The _update_progress helper
in the Celery task enforces this by only accepting values strictly greater
than the current progress.

**Validates: Requirements 6.2**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md (Property 12)
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md (6.2)
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Constants (mirrored from impact_analysis_tasks.py)
# ---------------------------------------------------------------------------

PROGRESS_DELTA_COMPLETE = 10
PROGRESS_DEPS_COMPLETE = 20
PROGRESS_ITEMS_START = 20
PROGRESS_ITEMS_END = 85
PROGRESS_GAPS_START = 85
PROGRESS_GAPS_END = 95
PROGRESS_REPORT_COMPLETE = 100


# ---------------------------------------------------------------------------
# Pure logic: monotonic progress tracker (mirrors _update_progress helper)
# ---------------------------------------------------------------------------


class MonotonicProgressTracker:
    """Models the monotonic progress enforcement from the Celery task.

    The tracker only accepts progress values strictly greater than the
    current value, ensuring progress never decreases.
    """

    def __init__(self) -> None:
        """Initialize tracker with progress at 0."""
        self.current_progress: int = 0
        self.history: list[int] = [0]

    def update(self, target: int) -> bool:
        """Attempt to update progress to target value.

        Only updates if target > current_progress (monotonic enforcement).

        Args:
            target: The desired progress value.

        Returns:
            True if progress was updated, False if rejected.
        """
        if target > self.current_progress:
            self.current_progress = target
            self.history.append(target)
            return True
        return False


def compute_impact_analysis_progress_sequence(
    num_affected_items: int,
) -> list[int]:
    """Compute the full progress sequence for an impact analysis pipeline.

    Mirrors the logic in _analyze_change_impact_async:
    - 10%: after Change_Delta computation
    - 20%: after Dependency_Graph query
    - 20-85%: proportional across affected items
    - 95%: after gap analysis phase
    - 100%: after Impact_Report persistence

    Args:
        num_affected_items: Number of affected items to assess (>= 0).

    Returns:
        Ordered list of progress percentages for the full pipeline.
    """
    progress_values: list[int] = []

    # Phase 1: Delta computation complete
    progress_values.append(PROGRESS_DELTA_COMPLETE)

    # Phase 2: Dependency query complete
    progress_values.append(PROGRESS_DEPS_COMPLETE)

    # Phase 3: Affected item assessment (20% → 85%)
    if num_affected_items > 0:
        for idx in range(num_affected_items):
            item_progress = PROGRESS_ITEMS_START + int(
                (idx + 1) / num_affected_items
                * (PROGRESS_ITEMS_END - PROGRESS_ITEMS_START)
            )
            progress_values.append(item_progress)
    else:
        # No items: jump directly to items end
        progress_values.append(PROGRESS_ITEMS_END)

    # Phase 4: Gap analysis complete
    progress_values.append(PROGRESS_GAPS_END)

    # Phase 5: Report persistence complete
    progress_values.append(PROGRESS_REPORT_COMPLETE)

    return progress_values


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_affected_item_count(draw: st.DrawFn) -> int:
    """Generate a valid affected item count.

    Impact analysis can have 0 to 50 affected items (50 is the max
    per the candidate prioritization limit).

    Returns:
        Integer item count between 0 and 50.
    """
    return draw(st.integers(min_value=0, max_value=50))


@st.composite
def st_random_progress_sequence(draw: st.DrawFn) -> list[int]:
    """Generate a random sequence of progress update attempts.

    Simulates arbitrary progress values being submitted to the
    monotonic tracker, including values that should be rejected
    (decreasing or equal).

    Returns:
        List of random progress values (0-100) of length 2-20.
    """
    length = draw(st.integers(min_value=2, max_value=20))
    return draw(
        st.lists(
            st.integers(min_value=0, max_value=100),
            min_size=length,
            max_size=length,
        )
    )


@st.composite
def st_partial_pipeline_scenario(draw: st.DrawFn) -> dict:
    """Generate a scenario where the pipeline stops at an arbitrary phase.

    Simulates a pipeline that may stop early (e.g., due to timeout),
    producing a prefix of the full progress sequence.

    Returns:
        Dictionary with:
        - num_items: number of affected items
        - stop_after: how many progress updates to include
        - progress_sequence: the resulting progress values
    """
    num_items = draw(st.integers(min_value=0, max_value=50))
    full_sequence = compute_impact_analysis_progress_sequence(num_items)
    stop_after = draw(st.integers(min_value=1, max_value=len(full_sequence)))
    partial_sequence = full_sequence[:stop_after]

    return {
        "num_items": num_items,
        "stop_after": stop_after,
        "progress_sequence": partial_sequence,
    }


# ---------------------------------------------------------------------------
# Property 12: Monotonic Progress
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(num_items=st_affected_item_count())
def test_impact_analysis_progress_is_monotonically_non_decreasing(
    num_items: int,
) -> None:
    """For any number of affected items, the full impact analysis progress
    sequence SHALL be monotonically non-decreasing (each value >= previous).

    **Validates: Requirements 6.2**
    """
    progress_sequence = compute_impact_analysis_progress_sequence(num_items)

    for i in range(1, len(progress_sequence)):
        assert progress_sequence[i] >= progress_sequence[i - 1], (
            f"Progress decreased at index {i}: "
            f"{progress_sequence[i - 1]} → {progress_sequence[i]} "
            f"(num_affected_items={num_items})"
        )


@settings(max_examples=100)
@given(attempts=st_random_progress_sequence())
def test_monotonic_tracker_never_decreases(
    attempts: list[int],
) -> None:
    """For any random sequence of progress update attempts, the tracker's
    recorded history SHALL be strictly non-decreasing. Progress SHALL
    never decrease from a previously reported value.

    **Validates: Requirements 6.2**
    """
    tracker = MonotonicProgressTracker()

    for value in attempts:
        tracker.update(value)

    # Verify the recorded history is monotonically non-decreasing
    for i in range(1, len(tracker.history)):
        assert tracker.history[i] >= tracker.history[i - 1], (
            f"Tracker history decreased at index {i}: "
            f"{tracker.history[i - 1]} → {tracker.history[i]} "
            f"(attempts={attempts})"
        )


@settings(max_examples=100)
@given(attempts=st_random_progress_sequence())
def test_monotonic_tracker_rejects_non_increasing_values(
    attempts: list[int],
) -> None:
    """For any random sequence of progress update attempts, the tracker
    SHALL reject values that are less than or equal to the current progress.
    Only strictly greater values SHALL be accepted.

    **Validates: Requirements 6.2**
    """
    tracker = MonotonicProgressTracker()

    for value in attempts:
        prev = tracker.current_progress
        accepted = tracker.update(value)

        if value > prev:
            assert accepted, (
                f"Tracker rejected value {value} which is greater than "
                f"current {prev}"
            )
            assert tracker.current_progress == value
        else:
            assert not accepted, (
                f"Tracker accepted value {value} which is not greater than "
                f"current {prev}"
            )
            assert tracker.current_progress == prev


@settings(max_examples=100)
@given(num_items=st_affected_item_count())
def test_impact_analysis_progress_ends_at_100(
    num_items: int,
) -> None:
    """The impact analysis progress sequence SHALL always end at 100%
    upon successful completion.

    **Validates: Requirements 6.2**
    """
    progress_sequence = compute_impact_analysis_progress_sequence(num_items)

    assert progress_sequence[-1] == PROGRESS_REPORT_COMPLETE, (
        f"Progress does not end at 100: ends at {progress_sequence[-1]} "
        f"(num_affected_items={num_items})"
    )


@settings(max_examples=100)
@given(num_items=st_affected_item_count())
def test_impact_analysis_progress_within_bounds(
    num_items: int,
) -> None:
    """All progress values SHALL be within [0, 100].

    **Validates: Requirements 6.2**
    """
    progress_sequence = compute_impact_analysis_progress_sequence(num_items)

    for i, value in enumerate(progress_sequence):
        assert 0 <= value <= 100, (
            f"Progress value {value} at index {i} is out of bounds [0, 100] "
            f"(num_affected_items={num_items})"
        )


@settings(max_examples=100)
@given(scenario=st_partial_pipeline_scenario())
def test_partial_pipeline_progress_is_monotonically_non_decreasing(
    scenario: dict,
) -> None:
    """Even when the pipeline stops early (e.g., timeout producing
    partial_success), the partial progress sequence SHALL be
    monotonically non-decreasing.

    **Validates: Requirements 6.2**
    """
    progress_sequence = scenario["progress_sequence"]

    for i in range(1, len(progress_sequence)):
        assert progress_sequence[i] >= progress_sequence[i - 1], (
            f"Progress decreased at index {i}: "
            f"{progress_sequence[i - 1]} → {progress_sequence[i]} "
            f"(num_items={scenario['num_items']}, "
            f"stopped after {scenario['stop_after']} updates)"
        )


@settings(max_examples=100)
@given(num_items=st.integers(min_value=1, max_value=50))
def test_item_progress_stays_within_20_to_85_range(
    num_items: int,
) -> None:
    """Item-level progress updates (phase 3) SHALL produce values in the
    range [20, 85], maintaining monotonicity with the preceding dependency
    query phase (20%) and not exceeding the gap analysis phase (95%).

    **Validates: Requirements 6.2**
    """
    progress_sequence = compute_impact_analysis_progress_sequence(num_items)

    # Item progress values are at indices 2 through 2+num_items-1
    # (after 10, 20 and before 95, 100)
    item_progress_values = progress_sequence[2 : 2 + num_items]

    for i, value in enumerate(item_progress_values):
        assert value >= PROGRESS_ITEMS_START, (
            f"Item progress value {value} at item {i} is below "
            f"{PROGRESS_ITEMS_START} (num_items={num_items})"
        )
        assert value <= PROGRESS_ITEMS_END, (
            f"Item progress value {value} at item {i} exceeds "
            f"{PROGRESS_ITEMS_END} (num_items={num_items})"
        )


@settings(max_examples=100)
@given(num_items=st.integers(min_value=1, max_value=50))
def test_last_item_progress_is_exactly_85(
    num_items: int,
) -> None:
    """The last affected item's progress SHALL be exactly 85%, ensuring
    a clean transition to the gap analysis phase at 95%.

    **Validates: Requirements 6.2**
    """
    progress_sequence = compute_impact_analysis_progress_sequence(num_items)

    # The last item progress is at index 1 + num_items
    # (indices: 0=10%, 1=20%, 2..1+num_items=items, then 95, 100)
    last_item_index = 1 + num_items
    last_item_progress = progress_sequence[last_item_index]

    assert last_item_progress == PROGRESS_ITEMS_END, (
        f"Last item progress is {last_item_progress}, expected "
        f"{PROGRESS_ITEMS_END} (num_items={num_items})"
    )
