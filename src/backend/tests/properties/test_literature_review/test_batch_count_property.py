"""Property-based test: Screening batch count computation.

Property 5: Screening batch count computation
For any set of N record IDs (1–500) and batch_size B (1–100), the batching
logic SHALL:
    1. Produce exactly ceil(N / B) batches
    2. Each batch contains at most B record IDs
    3. The union of all batch record IDs equals the original set
    4. No duplicates or omissions across batches

This tests the pure batching function used by the screening Celery tasks
to split record sets into manageable chunks for the vLLM inference queue.

**Validates: Requirements 3.3**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

import math

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure helper function: batch computation
# ---------------------------------------------------------------------------


def compute_batches(record_ids: list[int], batch_size: int) -> list[list[int]]:
    """Split record_ids into batches of at most batch_size.

    This pure function mirrors the batching logic used in
    literature_screening_tasks.execute_screening_batch to partition
    record sets into chunks dispatched as individual Celery tasks.

    Args:
        record_ids: List of ingestion record IDs to batch.
        batch_size: Maximum number of records per batch (1–100).

    Returns:
        List of batches, where each batch is a list of record IDs.
    """
    batches = []
    for i in range(0, len(record_ids), batch_size):
        batches.append(record_ids[i : i + batch_size])
    return batches


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Record IDs: unique integers (1–500 records)
record_ids_strategy = st.lists(
    st.integers(min_value=1, max_value=100_000),
    min_size=1,
    max_size=500,
    unique=True,
)

# Batch size: integer in valid configuration range
batch_size_strategy = st.integers(min_value=1, max_value=100)


# ---------------------------------------------------------------------------
# Property 5: Screening batch count computation
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    record_ids=record_ids_strategy,
    batch_size=batch_size_strategy,
)
def test_batch_count_equals_ceil_n_over_b(
    record_ids: list[int],
    batch_size: int,
) -> None:
    """The system SHALL dispatch exactly ceil(N / B) batch tasks.

    For any N record IDs and batch_size B, the number of batches produced
    must equal the mathematical ceiling of N divided by B.

    **Validates: Requirements 3.3**
    """
    batches = compute_batches(record_ids, batch_size)

    expected_count = math.ceil(len(record_ids) / batch_size)

    assert len(batches) == expected_count, (
        f"Expected {expected_count} batches for {len(record_ids)} records "
        f"with batch_size {batch_size}, got {len(batches)}"
    )


@settings(max_examples=200)
@given(
    record_ids=record_ids_strategy,
    batch_size=batch_size_strategy,
)
def test_each_batch_contains_at_most_b_records(
    record_ids: list[int],
    batch_size: int,
) -> None:
    """Each batch SHALL contain at most B record IDs.

    No batch may exceed the configured batch_size limit, ensuring
    the vLLM instance is not overwhelmed by oversized requests.

    **Validates: Requirements 3.3**
    """
    batches = compute_batches(record_ids, batch_size)

    for idx, batch in enumerate(batches):
        assert len(batch) <= batch_size, (
            f"Batch {idx} contains {len(batch)} records, "
            f"exceeding batch_size limit of {batch_size}"
        )


@settings(max_examples=200)
@given(
    record_ids=record_ids_strategy,
    batch_size=batch_size_strategy,
)
def test_union_of_batches_equals_original_set(
    record_ids: list[int],
    batch_size: int,
) -> None:
    """The union of all batch record IDs SHALL equal the original set.

    No record IDs may be omitted or lost during the batching process.
    Every record submitted for screening must appear in exactly one batch.

    **Validates: Requirements 3.3**
    """
    batches = compute_batches(record_ids, batch_size)

    # Flatten all batches into a single list
    all_batched_ids = [rid for batch in batches for rid in batch]

    assert set(all_batched_ids) == set(record_ids), (
        f"Union of batched IDs does not match original set. "
        f"Missing: {set(record_ids) - set(all_batched_ids)}, "
        f"Extra: {set(all_batched_ids) - set(record_ids)}"
    )


@settings(max_examples=200)
@given(
    record_ids=record_ids_strategy,
    batch_size=batch_size_strategy,
)
def test_no_duplicates_across_batches(
    record_ids: list[int],
    batch_size: int,
) -> None:
    """There SHALL be no duplicate record IDs across batches.

    Each record ID must appear in exactly one batch. Duplicates would
    cause redundant screening decisions, violating the append-only model.

    **Validates: Requirements 3.3**
    """
    batches = compute_batches(record_ids, batch_size)

    # Flatten and check for duplicates
    all_batched_ids = [rid for batch in batches for rid in batch]

    assert len(all_batched_ids) == len(set(all_batched_ids)), (
        f"Duplicate record IDs found across batches. "
        f"Total items: {len(all_batched_ids)}, "
        f"Unique items: {len(set(all_batched_ids))}"
    )

    # Additionally verify total count matches input
    assert len(all_batched_ids) == len(record_ids), (
        f"Total batched records ({len(all_batched_ids)}) does not match "
        f"input record count ({len(record_ids)})"
    )
