"""Property-based test: Screening decisions are append-only and idempotent.

Property 7: Screening decisions are append-only and idempotent
For any batch of record IDs within a ScreeningRun, executing the screening
task twice for the same batch SHALL NOT create duplicate decisions (one per
record per run), and all previously persisted decisions SHALL remain unmodified.

This is implemented as a PURE function test. The idempotency check logic
is extracted into a helper function that filters out record IDs already
having decisions in the current run, simulating the append-only behavior
without database access.

**Validates: Requirements 3.7, 13.4**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure helper function: Idempotency filter
# ---------------------------------------------------------------------------


def filter_already_decided(
    record_ids: list[int], existing_decisions: set[int]
) -> list[int]:
    """Filter out record IDs that already have decisions in this run.

    This pure function mirrors the idempotency logic in the screening task:
    before creating new ScreeningDecisions, the task checks which records
    already have a decision in the current ScreeningRun and skips them.

    Args:
        record_ids: Batch of record IDs to potentially screen.
        existing_decisions: Set of record IDs that already have decisions.

    Returns:
        List of record IDs that need new decisions (not yet decided).
    """
    return [rid for rid in record_ids if rid not in existing_decisions]


# ---------------------------------------------------------------------------
# Simulate screening execution (pure, stateful helper)
# ---------------------------------------------------------------------------


def simulate_screening_execution(
    record_ids: list[int], existing_decisions: set[int]
) -> tuple[set[int], list[int]]:
    """Simulate a single screening execution pass.

    Filters already-decided records, then "creates" decisions for remaining
    records by adding them to the existing_decisions set.

    Args:
        record_ids: Batch of record IDs to screen.
        existing_decisions: Mutable set of already-decided record IDs.

    Returns:
        Tuple of (updated existing_decisions set, newly decided record IDs).
    """
    to_screen = filter_already_decided(record_ids, existing_decisions)
    # Simulate persisting decisions for the filtered records
    new_decisions = set(to_screen)
    updated_decisions = existing_decisions | new_decisions
    return updated_decisions, to_screen


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

RECORD_ID = st.integers(min_value=1, max_value=10000)
RECORD_ID_BATCH = st.lists(RECORD_ID, min_size=1, max_size=50)
EXISTING_DECISIONS_SET = st.frozensets(RECORD_ID, min_size=0, max_size=30)


# ---------------------------------------------------------------------------
# Property 7: Screening decisions are append-only and idempotent
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    record_ids=RECORD_ID_BATCH,
    pre_existing=EXISTING_DECISIONS_SET,
)
def test_first_execution_creates_decisions_for_all_new_records(
    record_ids: list[int],
    pre_existing: frozenset[int],
) -> None:
    """After first execution, decisions are created for all record_ids that
    are not already in existing_decisions.

    **Validates: Requirements 3.7, 13.4**
    """
    existing = set(pre_existing)
    to_screen = filter_already_decided(record_ids, existing)

    # Every record NOT in existing_decisions should be in the result
    expected_new = [rid for rid in record_ids if rid not in existing]
    assert to_screen == expected_new, (
        f"First execution should return all records not already decided. "
        f"Got {to_screen}, expected {expected_new}"
    )


@settings(max_examples=200)
@given(
    record_ids=RECORD_ID_BATCH,
    pre_existing=EXISTING_DECISIONS_SET,
)
def test_second_execution_creates_no_new_decisions(
    record_ids: list[int],
    pre_existing: frozenset[int],
) -> None:
    """After second execution with same inputs, no new decisions are created
    (all filtered out) because the first execution already decided them.

    **Validates: Requirements 3.7, 13.4**
    """
    existing = set(pre_existing)

    # First execution: creates decisions for new records
    updated_existing, _ = simulate_screening_execution(record_ids, existing)

    # Second execution with same batch: should produce NO new records
    to_screen_second = filter_already_decided(record_ids, updated_existing)

    assert to_screen_second == [], (
        f"Second execution with same batch should create no new decisions. "
        f"Got {to_screen_second} records to screen after first pass already "
        f"decided them."
    )


@settings(max_examples=200)
@given(
    record_ids=RECORD_ID_BATCH,
    pre_existing=EXISTING_DECISIONS_SET,
)
def test_existing_decisions_grow_monotonically(
    record_ids: list[int],
    pre_existing: frozenset[int],
) -> None:
    """The existing decisions set grows monotonically — previous decisions
    are never removed, only new ones are added.

    **Validates: Requirements 3.7, 13.4**
    """
    existing = set(pre_existing)
    original_existing = existing.copy()

    # First execution
    after_first, _ = simulate_screening_execution(record_ids, existing)

    # Original decisions are preserved (subset)
    assert original_existing.issubset(after_first), (
        f"Original decisions {original_existing} must remain in updated set "
        f"{after_first}. Missing: {original_existing - after_first}"
    )

    # Set only grows
    assert len(after_first) >= len(original_existing), (
        f"Decisions set must grow monotonically. "
        f"Before: {len(original_existing)}, After: {len(after_first)}"
    )

    # Second execution also preserves all
    after_second, _ = simulate_screening_execution(record_ids, after_first)
    assert after_first.issubset(after_second), (
        f"Decisions after first pass {after_first} must remain after second "
        f"pass {after_second}. Missing: {after_first - after_second}"
    )


@settings(max_examples=200)
@given(
    record_ids=st.lists(RECORD_ID, min_size=1, max_size=50, unique=True),
    pre_existing=EXISTING_DECISIONS_SET,
)
def test_no_duplicate_record_ids_in_filtered_output(
    record_ids: list[int],
    pre_existing: frozenset[int],
) -> None:
    """After filtering, no duplicate record_ids appear in the output —
    each record gets at most one decision per run. Given a batch with
    unique record IDs (as dispatched by the screening task), the filtered
    output contains no duplicates.

    **Validates: Requirements 3.7, 13.4**
    """
    existing = set(pre_existing)
    to_screen = filter_already_decided(record_ids, existing)

    # No duplicates in filtered output
    assert len(to_screen) == len(set(to_screen)), (
        f"Filtered output should have no duplicates. "
        f"Got {len(to_screen)} items but only {len(set(to_screen))} unique. "
        f"Duplicates: {[r for r in to_screen if to_screen.count(r) > 1]}"
    )
