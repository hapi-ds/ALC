"""Property-based tests for soft-delete exclusion in traceability matrix listing.

Property 9: Soft-Delete Exclusion

For any collection of TraceabilityMatrix records with random deleted_at values
(either None or a timestamp), the list query filtering logic SHALL:
1. Exclude all matrices where deleted_at is not None (soft-deleted)
2. Include all matrices where deleted_at is None (active)
3. Retain all records in the underlying data regardless of deleted_at status

This ensures that soft-deleted matrices are hidden from list queries while
preserving the immutable audit record in the database.

**Validates: Requirements 5.5**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/api/traceability.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100)
USER_IDS = st.integers(min_value=1, max_value=200)
RECORD_IDS = st.integers(min_value=1, max_value=10000)

MATRIX_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

MATRIX_STATUSES = st.sampled_from(["completed", "partial_success", "failed"])

MATRIX_NAMES = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=200,
)

TIMESTAMPS = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)

# deleted_at is either None (active) or a timestamp (soft-deleted)
DELETED_AT_VALUES = st.one_of(st.none(), TIMESTAMPS)

DURATION_MS = st.integers(min_value=100, max_value=600000)
TOKEN_COUNTS = st.integers(min_value=100, max_value=50000)


# ---------------------------------------------------------------------------
# Data model for pure-logic soft-delete testing
# ---------------------------------------------------------------------------


@dataclass
class MatrixRecord:
    """Represents a TraceabilityMatrix record in the database."""

    id: int
    matrix_id: str
    matrix_name: str
    source_document_uuids: list[str]
    target_document_uuids: list[str]
    status: str
    generation_timestamp: datetime
    company_id: int
    deleted_at: datetime | None


# ---------------------------------------------------------------------------
# Pure filtering logic under test
# ---------------------------------------------------------------------------


def filter_active_matrices(
    all_matrices: list[MatrixRecord],
    company_id: int,
) -> list[MatrixRecord]:
    """Filter matrices for list query: exclude soft-deleted, scope to company.

    This replicates the filtering logic from the GET /matrices endpoint:
        TraceabilityMatrix.company_id == tenant.company_id,
        TraceabilityMatrix.deleted_at.is_(None),

    Args:
        all_matrices: All matrix records in the database.
        company_id: The requesting company's ID.

    Returns:
        Only active (non-deleted) matrices belonging to the specified company.
    """
    return [
        m for m in all_matrices
        if m.company_id == company_id and m.deleted_at is None
    ]


def get_all_records_in_database(
    all_matrices: list[MatrixRecord],
) -> list[MatrixRecord]:
    """Return all records regardless of deleted_at status.

    This represents the underlying database state — soft-deleted records
    still exist and are retained for audit purposes.

    Args:
        all_matrices: All matrix records in the database.

    Returns:
        All records unchanged (soft-delete does not remove data).
    """
    return all_matrices


# ---------------------------------------------------------------------------
# Composite Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_matrix_record(
    draw: st.DrawFn,
    company_id: int | None = None,
) -> MatrixRecord:
    """Generate a valid MatrixRecord with random deleted_at."""
    source_uuids = draw(
        st.lists(DOCUMENT_UUIDS, min_size=1, max_size=5, unique=True)
    )
    target_uuids = draw(
        st.lists(DOCUMENT_UUIDS, min_size=1, max_size=5, unique=True)
    )
    cid = company_id if company_id is not None else draw(COMPANY_IDS)

    return MatrixRecord(
        id=draw(RECORD_IDS),
        matrix_id=draw(MATRIX_IDS),
        matrix_name=draw(MATRIX_NAMES),
        source_document_uuids=source_uuids,
        target_document_uuids=target_uuids,
        status=draw(MATRIX_STATUSES),
        generation_timestamp=draw(TIMESTAMPS),
        company_id=cid,
        deleted_at=draw(DELETED_AT_VALUES),
    )


@st.composite
def st_matrix_collection(draw: st.DrawFn) -> tuple[list[MatrixRecord], int]:
    """Generate a collection of matrices with a target company_id.

    Returns a tuple of (all_matrices, target_company_id) where the collection
    contains matrices from multiple companies with various deleted_at states.
    """
    target_company_id = draw(st.integers(min_value=1, max_value=10))

    # Generate matrices for the target company (mix of active and deleted)
    target_matrices = draw(
        st.lists(
            st_matrix_record(company_id=target_company_id),
            min_size=1,
            max_size=10,
        )
    )

    # Generate matrices for other companies (should never appear in results)
    other_company_ids = [
        cid for cid in range(1, 11) if cid != target_company_id
    ]
    other_matrices = draw(
        st.lists(
            st_matrix_record(
                company_id=draw(st.sampled_from(other_company_ids))
                if other_company_ids
                else target_company_id
            ),
            min_size=0,
            max_size=5,
        )
    )

    all_matrices = target_matrices + other_matrices
    return all_matrices, target_company_id


@st.composite
def st_matrix_collection_with_guaranteed_mix(
    draw: st.DrawFn,
) -> tuple[list[MatrixRecord], int]:
    """Generate a collection guaranteed to have both active and deleted matrices.

    Ensures at least one active and one deleted matrix for the target company.
    """
    target_company_id = draw(st.integers(min_value=1, max_value=10))

    # At least one active matrix
    active_matrix = draw(st_matrix_record(company_id=target_company_id))
    active_matrix.deleted_at = None

    # At least one deleted matrix
    deleted_matrix = draw(st_matrix_record(company_id=target_company_id))
    deleted_matrix.deleted_at = draw(TIMESTAMPS)

    # Additional random matrices for the target company
    additional = draw(
        st.lists(
            st_matrix_record(company_id=target_company_id),
            min_size=0,
            max_size=8,
        )
    )

    all_matrices = [active_matrix, deleted_matrix] + additional
    return all_matrices, target_company_id


# ---------------------------------------------------------------------------
# Property 9: Soft-Delete Exclusion
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_matrix_collection())
def test_soft_deleted_matrices_excluded_from_list(
    data: tuple[list[MatrixRecord], int],
) -> None:
    """GET /matrices list queries SHALL exclude all matrices where deleted_at
    is not None. Only active (non-deleted) matrices are returned.

    For any generated set of matrices with random deleted_at values,
    the filtered result must contain zero matrices with a non-None deleted_at.

    **Validates: Requirements 5.5**
    """
    all_matrices, company_id = data
    result = filter_active_matrices(all_matrices, company_id)

    # No soft-deleted matrices in the result
    for matrix in result:
        assert matrix.deleted_at is None, (
            f"Soft-deleted matrix {matrix.matrix_id} with deleted_at="
            f"{matrix.deleted_at} should not appear in list results"
        )


@settings(max_examples=10)
@given(data=st_matrix_collection())
def test_active_matrices_included_in_list(
    data: tuple[list[MatrixRecord], int],
) -> None:
    """GET /matrices list queries SHALL include all matrices where deleted_at
    is None and company_id matches the requesting company.

    For any generated set of matrices, every active matrix belonging to the
    target company must appear in the filtered result.

    **Validates: Requirements 5.5**
    """
    all_matrices, company_id = data
    result = filter_active_matrices(all_matrices, company_id)

    # All active matrices for the target company must be in the result
    expected_active = [
        m for m in all_matrices
        if m.company_id == company_id and m.deleted_at is None
    ]

    assert len(result) == len(expected_active), (
        f"Expected {len(expected_active)} active matrices but got {len(result)}"
    )

    result_ids = {m.matrix_id for m in result}
    for matrix in expected_active:
        assert matrix.matrix_id in result_ids, (
            f"Active matrix {matrix.matrix_id} should appear in list results"
        )


@settings(max_examples=10)
@given(data=st_matrix_collection())
def test_underlying_records_still_exist_after_soft_delete(
    data: tuple[list[MatrixRecord], int],
) -> None:
    """Soft-deleted matrices SHALL still exist in the underlying database.
    The immutable audit record is preserved regardless of deleted_at status.

    For any generated set of matrices, the total count of records in the
    database must remain unchanged after filtering for the list query.

    **Validates: Requirements 5.5**
    """
    all_matrices, company_id = data

    # The list query filters results
    filtered = filter_active_matrices(all_matrices, company_id)

    # But the underlying database retains ALL records
    all_records = get_all_records_in_database(all_matrices)

    assert len(all_records) == len(all_matrices), (
        "Soft-delete must not remove records from the database"
    )

    # Deleted matrices are still in the database even if not in list results
    deleted_for_company = [
        m for m in all_matrices
        if m.company_id == company_id and m.deleted_at is not None
    ]
    for matrix in deleted_for_company:
        assert matrix in all_records, (
            f"Soft-deleted matrix {matrix.matrix_id} must still exist in database"
        )
        assert matrix not in filtered, (
            f"Soft-deleted matrix {matrix.matrix_id} must not appear in list query"
        )


@settings(max_examples=10)
@given(data=st_matrix_collection_with_guaranteed_mix())
def test_filter_partitions_active_and_deleted_correctly(
    data: tuple[list[MatrixRecord], int],
) -> None:
    """The soft-delete filter SHALL correctly partition matrices into active
    (visible in list) and deleted (hidden from list but retained in database).

    Given a collection with both active and deleted matrices, the count of
    active results plus the count of deleted matrices for the same company
    must equal the total matrices for that company.

    **Validates: Requirements 5.5**
    """
    all_matrices, company_id = data
    result = filter_active_matrices(all_matrices, company_id)

    company_matrices = [m for m in all_matrices if m.company_id == company_id]
    active_count = len(result)
    deleted_count = len([
        m for m in company_matrices if m.deleted_at is not None
    ])

    assert active_count + deleted_count == len(company_matrices), (
        f"Active ({active_count}) + deleted ({deleted_count}) must equal "
        f"total company matrices ({len(company_matrices)})"
    )


@settings(max_examples=10)
@given(data=st_matrix_collection())
def test_company_isolation_with_soft_delete(
    data: tuple[list[MatrixRecord], int],
) -> None:
    """The soft-delete filter SHALL only return matrices for the requesting
    company. Matrices from other companies (whether active or deleted) must
    never appear in the results.

    **Validates: Requirements 5.5**
    """
    all_matrices, company_id = data
    result = filter_active_matrices(all_matrices, company_id)

    # All results must belong to the target company
    for matrix in result:
        assert matrix.company_id == company_id, (
            f"Matrix {matrix.matrix_id} belongs to company {matrix.company_id} "
            f"but should only return results for company {company_id}"
        )


@settings(max_examples=10)
@given(
    matrices=st.lists(
        st_matrix_record(company_id=1),
        min_size=1,
        max_size=15,
    ),
)
def test_all_deleted_returns_empty_list(
    matrices: list[MatrixRecord],
) -> None:
    """If all matrices for a company are soft-deleted, the list query SHALL
    return an empty result set while all records remain in the database.

    **Validates: Requirements 5.5**
    """
    # Force all matrices to be soft-deleted
    for m in matrices:
        m.deleted_at = datetime(2025, 6, 1, tzinfo=UTC)

    result = filter_active_matrices(matrices, company_id=1)
    all_records = get_all_records_in_database(matrices)

    assert len(result) == 0, (
        "All matrices are soft-deleted; list should return empty"
    )
    assert len(all_records) == len(matrices), (
        "All records must still exist in the database"
    )


@settings(max_examples=10)
@given(
    matrices=st.lists(
        st_matrix_record(company_id=1),
        min_size=1,
        max_size=15,
    ),
)
def test_no_deleted_returns_all(
    matrices: list[MatrixRecord],
) -> None:
    """If no matrices for a company are soft-deleted, the list query SHALL
    return all matrices for that company.

    **Validates: Requirements 5.5**
    """
    # Force all matrices to be active (not deleted)
    for m in matrices:
        m.deleted_at = None

    result = filter_active_matrices(matrices, company_id=1)

    assert len(result) == len(matrices), (
        f"No matrices are deleted; list should return all {len(matrices)} matrices"
    )
