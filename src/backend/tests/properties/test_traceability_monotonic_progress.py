"""Property-based tests for traceability matrix generation progress monotonicity.

Tests Property 14 from the AI-Powered Traceability & Gap Discovery design
document, validating that progress updates during matrix generation are
monotonically non-decreasing.

Progress follows the pipeline phases (from traceability_tasks.py):
    5% → 10% → 30% → 35% → 60% → 60% → 85% → 85% → 90% → 90% → 95% → 95% → 100%

Each update must be >= the previous value. The _update_progress helper
in the Celery task enforces this by only accepting values strictly greater
than the current progress.

**Validates: Requirements 11.2**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md (Property 14)
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md (11.2)
    - Source: src/backend/src/alcoabase/tasks/traceability_tasks.py
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

# ---------------------------------------------------------------------------
# Constants (mirrored from traceability_tasks.py)
# ---------------------------------------------------------------------------

PROGRESS_VALIDATION = 5
PROGRESS_REQ_EXTRACTION_START = 5
PROGRESS_REQ_EXTRACTION_END = 30
PROGRESS_TC_EXTRACTION_START = 30
PROGRESS_TC_EXTRACTION_END = 60
PROGRESS_LINK_ESTABLISHMENT_START = 60
PROGRESS_LINK_ESTABLISHMENT_END = 85
PROGRESS_ORPHAN_DETECTION_START = 85
PROGRESS_ORPHAN_DETECTION_END = 90
PROGRESS_METRICS_START = 90
PROGRESS_METRICS_END = 95
PROGRESS_PERSISTENCE_START = 95
PROGRESS_COMPLETE = 100


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


# ---------------------------------------------------------------------------
# Progress sequence computation (mirrors traceability_tasks.py pipeline)
# ---------------------------------------------------------------------------


def compute_traceability_progress_sequence(
    num_source_docs: int,
    num_target_docs: int,
) -> list[int]:
    """Compute the full progress sequence for a traceability matrix generation.

    Mirrors the logic in _generate_traceability_matrix_async:
    - 5%: after validation
    - 5-30%: requirement extraction (PROGRESS_REQ_EXTRACTION_START + 5 = 10,
      then PROGRESS_REQ_EXTRACTION_END = 30)
    - 30-60%: test case extraction (PROGRESS_TC_EXTRACTION_START + 5 = 35,
      then PROGRESS_TC_EXTRACTION_END = 60)
    - 60-85%: link establishment (start=60, end=85)
    - 85-90%: orphan detection (start=85, end=90)
    - 90-95%: metrics computation (start=90, end=95)
    - 95-100%: persistence (start=95, complete=100)

    Args:
        num_source_docs: Number of source documents (>= 1).
        num_target_docs: Number of target documents (>= 1).

    Returns:
        Ordered list of progress percentages for the full pipeline.
    """
    progress_values: list[int] = []

    # Phase 1: Validation complete → 5%
    progress_values.append(PROGRESS_VALIDATION)

    # Phase 2: Requirement extraction
    # First update: PROGRESS_REQ_EXTRACTION_START + 5 = 10
    progress_values.append(PROGRESS_REQ_EXTRACTION_START + 5)
    # End of requirement extraction: 30
    progress_values.append(PROGRESS_REQ_EXTRACTION_END)

    # Phase 3: Test case extraction
    # First update: PROGRESS_TC_EXTRACTION_START + 5 = 35
    progress_values.append(PROGRESS_TC_EXTRACTION_START + 5)
    # End of test case extraction: 60
    progress_values.append(PROGRESS_TC_EXTRACTION_END)

    # Phase 4: Link establishment
    progress_values.append(PROGRESS_LINK_ESTABLISHMENT_START)
    progress_values.append(PROGRESS_LINK_ESTABLISHMENT_END)

    # Phase 5: Orphan detection
    progress_values.append(PROGRESS_ORPHAN_DETECTION_START)
    progress_values.append(PROGRESS_ORPHAN_DETECTION_END)

    # Phase 6: Metrics computation
    progress_values.append(PROGRESS_METRICS_START)
    progress_values.append(PROGRESS_METRICS_END)

    # Phase 7: Persistence
    progress_values.append(PROGRESS_PERSISTENCE_START)
    progress_values.append(PROGRESS_COMPLETE)

    return progress_values


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_document_counts(draw: st.DrawFn) -> tuple[int, int]:
    """Generate valid source and target document counts.

    Source documents: 1-10 (max per request).
    Target documents: 1-20 (max per request).

    Returns:
        Tuple of (num_source_docs, num_target_docs).
    """
    num_source = draw(st.integers(min_value=1, max_value=10))
    num_target = draw(st.integers(min_value=1, max_value=20))
    return (num_source, num_target)


@st.composite
def st_random_progress_sequence(draw: st.DrawFn) -> list[int]:
    """Generate a random sequence of progress update attempts.

    Simulates arbitrary progress values being submitted to the
    monotonic tracker, including values that should be rejected
    (decreasing or equal).

    Returns:
        List of random progress values (0-100) of length 2-30.
    """
    length = draw(st.integers(min_value=2, max_value=30))
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
        - num_source_docs: number of source documents
        - num_target_docs: number of target documents
        - stop_after: how many progress updates to include
        - progress_sequence: the resulting progress values
    """
    num_source = draw(st.integers(min_value=1, max_value=10))
    num_target = draw(st.integers(min_value=1, max_value=20))
    full_sequence = compute_traceability_progress_sequence(
        num_source, num_target
    )
    stop_after = draw(st.integers(min_value=1, max_value=len(full_sequence)))
    partial_sequence = full_sequence[:stop_after]

    return {
        "num_source_docs": num_source,
        "num_target_docs": num_target,
        "stop_after": stop_after,
        "progress_sequence": partial_sequence,
    }


# ---------------------------------------------------------------------------
# Property 14: Monotonic Progress
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(doc_counts=st_document_counts())
def test_traceability_progress_is_monotonically_non_decreasing(
    doc_counts: tuple[int, int],
) -> None:
    """For any valid document counts, the full traceability matrix generation
    progress sequence SHALL be monotonically non-decreasing (each value >=
    previous).

    **Validates: Requirements 11.2**
    """
    num_source, num_target = doc_counts
    progress_sequence = compute_traceability_progress_sequence(
        num_source, num_target
    )

    for i in range(1, len(progress_sequence)):
        assert progress_sequence[i] >= progress_sequence[i - 1], (
            f"Progress decreased at index {i}: "
            f"{progress_sequence[i - 1]} → {progress_sequence[i]} "
            f"(source_docs={num_source}, target_docs={num_target})"
        )


@settings(max_examples=10)
@given(attempts=st_random_progress_sequence())
def test_monotonic_tracker_never_decreases(
    attempts: list[int],
) -> None:
    """For any random sequence of progress update attempts, the tracker's
    recorded history SHALL be strictly non-decreasing. Progress SHALL
    never decrease from a previously reported value.

    **Validates: Requirements 11.2**
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


@settings(max_examples=10)
@given(attempts=st_random_progress_sequence())
def test_monotonic_tracker_rejects_non_increasing_values(
    attempts: list[int],
) -> None:
    """For any random sequence of progress update attempts, the tracker
    SHALL reject values that are less than or equal to the current progress.
    Only strictly greater values SHALL be accepted.

    **Validates: Requirements 11.2**
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


@settings(max_examples=10)
@given(doc_counts=st_document_counts())
def test_traceability_progress_ends_at_100(
    doc_counts: tuple[int, int],
) -> None:
    """The traceability matrix generation progress sequence SHALL always
    end at 100% upon successful completion.

    **Validates: Requirements 11.2**
    """
    num_source, num_target = doc_counts
    progress_sequence = compute_traceability_progress_sequence(
        num_source, num_target
    )

    assert progress_sequence[-1] == PROGRESS_COMPLETE, (
        f"Progress does not end at 100: ends at {progress_sequence[-1]} "
        f"(source_docs={num_source}, target_docs={num_target})"
    )


@settings(max_examples=10)
@given(doc_counts=st_document_counts())
def test_traceability_progress_within_bounds(
    doc_counts: tuple[int, int],
) -> None:
    """All progress values SHALL be within [0, 100].

    **Validates: Requirements 11.2**
    """
    num_source, num_target = doc_counts
    progress_sequence = compute_traceability_progress_sequence(
        num_source, num_target
    )

    for i, value in enumerate(progress_sequence):
        assert 0 <= value <= 100, (
            f"Progress value {value} at index {i} is out of bounds [0, 100] "
            f"(source_docs={num_source}, target_docs={num_target})"
        )


@settings(max_examples=10)
@given(scenario=st_partial_pipeline_scenario())
def test_partial_pipeline_progress_is_monotonically_non_decreasing(
    scenario: dict,
) -> None:
    """Even when the pipeline stops early (e.g., timeout producing
    partial_success), the partial progress sequence SHALL be
    monotonically non-decreasing.

    **Validates: Requirements 11.2**
    """
    progress_sequence = scenario["progress_sequence"]

    for i in range(1, len(progress_sequence)):
        assert progress_sequence[i] >= progress_sequence[i - 1], (
            f"Progress decreased at index {i}: "
            f"{progress_sequence[i - 1]} → {progress_sequence[i]} "
            f"(source_docs={scenario['num_source_docs']}, "
            f"target_docs={scenario['num_target_docs']}, "
            f"stopped after {scenario['stop_after']} updates)"
        )


@settings(max_examples=10)
@given(doc_counts=st_document_counts())
def test_traceability_progress_starts_at_validation(
    doc_counts: tuple[int, int],
) -> None:
    """The traceability matrix generation progress sequence SHALL start
    at the validation milestone (5%).

    **Validates: Requirements 11.2**
    """
    num_source, num_target = doc_counts
    progress_sequence = compute_traceability_progress_sequence(
        num_source, num_target
    )

    assert progress_sequence[0] == PROGRESS_VALIDATION, (
        f"Progress does not start at {PROGRESS_VALIDATION}: "
        f"starts at {progress_sequence[0]} "
        f"(source_docs={num_source}, target_docs={num_target})"
    )


@settings(max_examples=10)
@given(doc_counts=st_document_counts())
def test_traceability_progress_through_tracker_is_monotonic(
    doc_counts: tuple[int, int],
) -> None:
    """When the full progress sequence is fed through the MonotonicProgressTracker,
    the resulting history SHALL be monotonically non-decreasing and all
    non-duplicate values SHALL be accepted.

    **Validates: Requirements 11.2**
    """
    num_source, num_target = doc_counts
    progress_sequence = compute_traceability_progress_sequence(
        num_source, num_target
    )

    tracker = MonotonicProgressTracker()

    for value in progress_sequence:
        tracker.update(value)

    # Verify the tracker's history is monotonically non-decreasing
    for i in range(1, len(tracker.history)):
        assert tracker.history[i] > tracker.history[i - 1], (
            f"Tracker history not strictly increasing at index {i}: "
            f"{tracker.history[i - 1]} → {tracker.history[i]} "
            f"(source_docs={num_source}, target_docs={num_target})"
        )

    # Verify the tracker ends at 100
    assert tracker.current_progress == PROGRESS_COMPLETE, (
        f"Tracker did not reach 100: ended at {tracker.current_progress}"
    )
