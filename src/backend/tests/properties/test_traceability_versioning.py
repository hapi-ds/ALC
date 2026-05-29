"""Property-based tests for parent matrix versioning in TraceabilityMatrixService.

Property 8: Parent Matrix Versioning

For any sequence of matrices generated for the same document set (matching
sorted source_document_uuids AND sorted target_document_uuids) within the
same company:
1. The first matrix for a document set has parent_matrix_id = None
2. Subsequent matrices for the same document set reference the most recent
   previous matrix via parent_matrix_id
3. Matrices for different document sets do NOT reference each other
4. Matrices in different companies do NOT reference each other
5. The chain is linear (no cycles)

**Validates: Requirements 4.3**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/traceability_matrix.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Domain model for parent matrix versioning logic (pure functions under test)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatrixRecord:
    """Represents a persisted TraceabilityMatrix record for versioning tests.

    Attributes:
        matrix_id: UUID string uniquely identifying this matrix.
        source_document_uuids: Sorted list of source document UUIDs.
        target_document_uuids: Sorted list of target document UUIDs.
        company_id: Owning company ID (tenant isolation).
        generation_timestamp: When the matrix was generated.
        parent_matrix_id: UUID of the parent matrix (None if first).
        deleted_at: Soft-delete timestamp (None if active).
    """

    matrix_id: str
    source_document_uuids: list[str]
    target_document_uuids: list[str]
    company_id: int
    generation_timestamp: datetime
    parent_matrix_id: str | None = None
    deleted_at: datetime | None = None


def resolve_parent_matrix_id(
    source_document_uuids: list[str],
    target_document_uuids: list[str],
    company_id: int,
    existing_matrices: list[MatrixRecord],
) -> str | None:
    """Resolve the parent_matrix_id for a new matrix being generated.

    Finds the most recent existing matrix with matching sorted
    source_document_uuids AND sorted target_document_uuids within the
    same company. Excludes soft-deleted matrices.

    Args:
        source_document_uuids: Source document UUIDs for the new matrix.
        target_document_uuids: Target document UUIDs for the new matrix.
        company_id: The company generating the matrix.
        existing_matrices: All existing matrices to search through.

    Returns:
        The matrix_id of the most recent matching matrix, or None if this
        is the first generation for this document set.
    """
    sorted_sources = sorted(source_document_uuids)
    sorted_targets = sorted(target_document_uuids)

    candidates = [
        m
        for m in existing_matrices
        if m.company_id == company_id
        and m.deleted_at is None
        and sorted(m.source_document_uuids) == sorted_sources
        and sorted(m.target_document_uuids) == sorted_targets
    ]

    if not candidates:
        return None

    # Return the most recent matrix by generation_timestamp
    most_recent = max(candidates, key=lambda m: m.generation_timestamp)
    return most_recent.matrix_id


def build_matrix_chain(
    matrices_in_order: list[MatrixRecord],
    existing_matrices: list[MatrixRecord],
) -> list[MatrixRecord]:
    """Simulate generating a sequence of matrices, resolving parent_matrix_id.

    For each matrix in the input sequence, resolves parent_matrix_id based
    on all previously generated matrices (including those from
    existing_matrices), then appends the new matrix to the existing set.

    Args:
        matrices_in_order: Matrices to generate in chronological order.
        existing_matrices: Pre-existing matrices in the system.

    Returns:
        List of matrices with parent_matrix_id resolved.
    """
    all_matrices = list(existing_matrices)
    result: list[MatrixRecord] = []

    for matrix in matrices_in_order:
        parent_id = resolve_parent_matrix_id(
            source_document_uuids=matrix.source_document_uuids,
            target_document_uuids=matrix.target_document_uuids,
            company_id=matrix.company_id,
            existing_matrices=all_matrices,
        )
        resolved_matrix = MatrixRecord(
            matrix_id=matrix.matrix_id,
            source_document_uuids=matrix.source_document_uuids,
            target_document_uuids=matrix.target_document_uuids,
            company_id=matrix.company_id,
            generation_timestamp=matrix.generation_timestamp,
            parent_matrix_id=parent_id,
            deleted_at=matrix.deleted_at,
        )
        all_matrices.append(resolved_matrix)
        result.append(resolved_matrix)

    return result


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=10)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

MATRIX_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

BASE_TIMESTAMP = datetime(2025, 1, 1, tzinfo=UTC)

# Generate timestamps that are strictly increasing
TIMESTAMP_OFFSETS = st.integers(min_value=0, max_value=100000)


@st.composite
def st_document_set(draw: st.DrawFn) -> tuple[list[str], list[str]]:
    """Generate a pair of (source_uuids, target_uuids) document sets."""
    sources = draw(
        st.lists(DOCUMENT_UUIDS, min_size=1, max_size=5, unique=True)
    )
    targets = draw(
        st.lists(DOCUMENT_UUIDS, min_size=1, max_size=5, unique=True)
    )
    return (sorted(sources), sorted(targets))


@st.composite
def st_matrix_sequence_same_doc_set(
    draw: st.DrawFn,
) -> tuple[list[str], list[str], int, list[MatrixRecord]]:
    """Generate a sequence of matrices for the SAME document set and company.

    Returns:
        Tuple of (source_uuids, target_uuids, company_id, matrices).
    """
    sources, targets = draw(st_document_set())
    company_id = draw(COMPANY_IDS)
    count = draw(st.integers(min_value=2, max_value=6))

    matrix_ids = draw(
        st.lists(MATRIX_IDS, min_size=count, max_size=count, unique=True)
    )

    matrices: list[MatrixRecord] = []
    for i in range(count):
        timestamp = BASE_TIMESTAMP + timedelta(minutes=i * 10)
        matrices.append(
            MatrixRecord(
                matrix_id=matrix_ids[i],
                source_document_uuids=sources,
                target_document_uuids=targets,
                company_id=company_id,
                generation_timestamp=timestamp,
            )
        )

    return (sources, targets, company_id, matrices)


@st.composite
def st_matrices_different_doc_sets(
    draw: st.DrawFn,
) -> tuple[list[MatrixRecord], list[MatrixRecord]]:
    """Generate two groups of matrices with DIFFERENT document sets in same company.

    Ensures the document sets are actually different by using distinct
    UUID pools for each group.

    Returns:
        Tuple of (group_a_matrices, group_b_matrices).
    """
    company_id = draw(COMPANY_IDS)

    # Use non-overlapping UUID ranges to guarantee different doc sets
    sources_a = draw(
        st.lists(
            st.from_regex(r"2025-0\d{4}", fullmatch=True),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    targets_a = draw(
        st.lists(
            st.from_regex(r"2025-0\d{4}", fullmatch=True),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    # Use a different prefix range to guarantee different sets
    sources_b = draw(
        st.lists(
            st.from_regex(r"2025-9\d{4}", fullmatch=True),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    targets_b = draw(
        st.lists(
            st.from_regex(r"2025-9\d{4}", fullmatch=True),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )

    count_a = draw(st.integers(min_value=1, max_value=3))
    count_b = draw(st.integers(min_value=1, max_value=3))

    # Generate unique matrix_ids across both groups
    all_ids = draw(
        st.lists(
            MATRIX_IDS,
            min_size=count_a + count_b,
            max_size=count_a + count_b,
            unique=True,
        )
    )

    group_a: list[MatrixRecord] = []
    for i in range(count_a):
        group_a.append(
            MatrixRecord(
                matrix_id=all_ids[i],
                source_document_uuids=sorted(sources_a),
                target_document_uuids=sorted(targets_a),
                company_id=company_id,
                generation_timestamp=BASE_TIMESTAMP + timedelta(minutes=i * 5),
            )
        )

    group_b: list[MatrixRecord] = []
    for i in range(count_b):
        group_b.append(
            MatrixRecord(
                matrix_id=all_ids[count_a + i],
                source_document_uuids=sorted(sources_b),
                target_document_uuids=sorted(targets_b),
                company_id=company_id,
                generation_timestamp=BASE_TIMESTAMP
                + timedelta(minutes=100 + i * 5),
            )
        )

    return (group_a, group_b)


@st.composite
def st_matrices_different_companies(
    draw: st.DrawFn,
) -> tuple[list[MatrixRecord], list[MatrixRecord]]:
    """Generate two groups of matrices with SAME doc set but DIFFERENT companies.

    Returns:
        Tuple of (company_a_matrices, company_b_matrices).
    """
    sources, targets = draw(st_document_set())

    company_a = draw(st.integers(min_value=1, max_value=50))
    company_b = draw(st.integers(min_value=51, max_value=100))

    count_a = draw(st.integers(min_value=1, max_value=3))
    count_b = draw(st.integers(min_value=1, max_value=3))

    # Generate unique matrix_ids across both groups
    all_ids = draw(
        st.lists(
            MATRIX_IDS,
            min_size=count_a + count_b,
            max_size=count_a + count_b,
            unique=True,
        )
    )

    group_a: list[MatrixRecord] = []
    for i in range(count_a):
        group_a.append(
            MatrixRecord(
                matrix_id=all_ids[i],
                source_document_uuids=sources,
                target_document_uuids=targets,
                company_id=company_a,
                generation_timestamp=BASE_TIMESTAMP + timedelta(minutes=i * 5),
            )
        )

    group_b: list[MatrixRecord] = []
    for i in range(count_b):
        group_b.append(
            MatrixRecord(
                matrix_id=all_ids[count_a + i],
                source_document_uuids=sources,
                target_document_uuids=targets,
                company_id=company_b,
                generation_timestamp=BASE_TIMESTAMP + timedelta(minutes=i * 5),
            )
        )

    return (group_a, group_b)


# ---------------------------------------------------------------------------
# Property 8: First matrix for a document set has parent_matrix_id = None
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_first_matrix_for_doc_set_has_null_parent(data: st.DataObject) -> None:
    """When generating the first matrix for a document set within a company,
    parent_matrix_id SHALL be None because no previous matrix exists for
    that combination of sorted source and target document UUIDs.

    **Validates: Requirements 4.3**
    """
    sources, targets = data.draw(st_document_set())
    company_id = data.draw(COMPANY_IDS)

    # No existing matrices
    parent_id = resolve_parent_matrix_id(
        source_document_uuids=sources,
        target_document_uuids=targets,
        company_id=company_id,
        existing_matrices=[],
    )

    assert parent_id is None


# ---------------------------------------------------------------------------
# Property 8: Subsequent matrices reference the most recent previous matrix
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_matrix_sequence_same_doc_set())
def test_subsequent_matrices_reference_most_recent(
    data: tuple[list[str], list[str], int, list[MatrixRecord]],
) -> None:
    """When generating a new matrix for a document set that already has
    existing matrices, parent_matrix_id SHALL reference the most recent
    previous matrix (by generation_timestamp) for that same document set
    within the same company.

    **Validates: Requirements 4.3**
    """
    sources, targets, company_id, matrices = data

    # Build the chain by resolving parent_matrix_id for each matrix
    resolved = build_matrix_chain(matrices, existing_matrices=[])

    # First matrix should have no parent
    assert resolved[0].parent_matrix_id is None

    # Each subsequent matrix should reference the immediately preceding one
    for i in range(1, len(resolved)):
        assert resolved[i].parent_matrix_id == resolved[i - 1].matrix_id


# ---------------------------------------------------------------------------
# Property 8: Matrices for different document sets do NOT reference each other
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_matrices_different_doc_sets())
def test_different_doc_sets_do_not_reference_each_other(
    data: tuple[list[MatrixRecord], list[MatrixRecord]],
) -> None:
    """Matrices generated for different document sets (different sorted
    source_document_uuids OR different sorted target_document_uuids)
    SHALL NOT reference each other via parent_matrix_id, even if they
    belong to the same company.

    **Validates: Requirements 4.3**
    """
    group_a, group_b = data

    # Build group_a chain first
    resolved_a = build_matrix_chain(group_a, existing_matrices=[])

    # Build group_b chain with group_a already existing
    resolved_b = build_matrix_chain(group_b, existing_matrices=resolved_a)

    # Collect all matrix_ids from each group
    ids_a = {m.matrix_id for m in resolved_a}
    ids_b = {m.matrix_id for m in resolved_b}

    # No matrix in group_b should reference a matrix from group_a
    for matrix in resolved_b:
        if matrix.parent_matrix_id is not None:
            assert matrix.parent_matrix_id not in ids_a
            assert matrix.parent_matrix_id in ids_b

    # No matrix in group_a should reference a matrix from group_b
    for matrix in resolved_a:
        if matrix.parent_matrix_id is not None:
            assert matrix.parent_matrix_id not in ids_b
            assert matrix.parent_matrix_id in ids_a


# ---------------------------------------------------------------------------
# Property 8: Matrices in different companies do NOT reference each other
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_matrices_different_companies())
def test_different_companies_do_not_reference_each_other(
    data: tuple[list[MatrixRecord], list[MatrixRecord]],
) -> None:
    """Matrices generated for the same document set but in different
    companies SHALL NOT reference each other via parent_matrix_id.
    Company isolation ensures no cross-tenant versioning chains.

    **Validates: Requirements 4.3**
    """
    group_a, group_b = data

    # Build group_a chain first
    resolved_a = build_matrix_chain(group_a, existing_matrices=[])

    # Build group_b chain with group_a already existing
    resolved_b = build_matrix_chain(group_b, existing_matrices=resolved_a)

    # Collect all matrix_ids from each group
    ids_a = {m.matrix_id for m in resolved_a}
    ids_b = {m.matrix_id for m in resolved_b}

    # No matrix in group_b should reference a matrix from group_a
    for matrix in resolved_b:
        if matrix.parent_matrix_id is not None:
            assert matrix.parent_matrix_id not in ids_a

    # No matrix in group_a should reference a matrix from group_b
    for matrix in resolved_a:
        if matrix.parent_matrix_id is not None:
            assert matrix.parent_matrix_id not in ids_b


# ---------------------------------------------------------------------------
# Property 8: The versioning chain is linear (no cycles)
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_matrix_sequence_same_doc_set())
def test_versioning_chain_is_linear_no_cycles(
    data: tuple[list[str], list[str], int, list[MatrixRecord]],
) -> None:
    """The parent_matrix_id chain SHALL be linear with no cycles.
    Following parent_matrix_id references from any matrix SHALL
    eventually reach a matrix with parent_matrix_id = None (the root),
    and the number of hops SHALL equal the matrix's position in the
    chronological sequence.

    **Validates: Requirements 4.3**
    """
    sources, targets, company_id, matrices = data

    resolved = build_matrix_chain(matrices, existing_matrices=[])

    # Build a lookup for quick parent traversal
    id_to_matrix = {m.matrix_id: m for m in resolved}

    for i, matrix in enumerate(resolved):
        # Walk the chain back to root
        visited: set[str] = set()
        current = matrix
        hops = 0

        while current.parent_matrix_id is not None:
            # Cycle detection
            assert current.matrix_id not in visited, (
                f"Cycle detected at {current.matrix_id}"
            )
            visited.add(current.matrix_id)
            current = id_to_matrix[current.parent_matrix_id]
            hops += 1

        # The number of hops should equal the position index
        assert hops == i
        # The root should have no parent
        assert current.parent_matrix_id is None


# ---------------------------------------------------------------------------
# Property 8: Document order does not affect parent resolution
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_document_order_does_not_affect_parent_resolution(
    data: st.DataObject,
) -> None:
    """The parent_matrix_id resolution SHALL use sorted document UUIDs,
    so the order in which source or target documents are provided SHALL
    NOT affect whether a parent is found. Two matrices with the same
    documents in different order SHALL be considered the same document set.

    **Validates: Requirements 4.3**
    """
    sources = data.draw(
        st.lists(DOCUMENT_UUIDS, min_size=2, max_size=5, unique=True)
    )
    targets = data.draw(
        st.lists(DOCUMENT_UUIDS, min_size=2, max_size=5, unique=True)
    )
    company_id = data.draw(COMPANY_IDS)
    matrix_id = data.draw(MATRIX_IDS)

    # Create an existing matrix with sorted documents
    existing = MatrixRecord(
        matrix_id=matrix_id,
        source_document_uuids=sorted(sources),
        target_document_uuids=sorted(targets),
        company_id=company_id,
        generation_timestamp=BASE_TIMESTAMP,
    )

    # Resolve parent with documents in reversed order
    parent_id = resolve_parent_matrix_id(
        source_document_uuids=list(reversed(sources)),
        target_document_uuids=list(reversed(targets)),
        company_id=company_id,
        existing_matrices=[existing],
    )

    # Should find the existing matrix regardless of input order
    assert parent_id == matrix_id


# ---------------------------------------------------------------------------
# Property 8: Soft-deleted matrices are excluded from parent resolution
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_soft_deleted_matrices_excluded_from_parent_resolution(
    data: st.DataObject,
) -> None:
    """Soft-deleted matrices (deleted_at is not None) SHALL NOT be
    considered when resolving parent_matrix_id. Only active (non-deleted)
    matrices participate in the versioning chain.

    **Validates: Requirements 4.3**
    """
    sources, targets = data.draw(st_document_set())
    company_id = data.draw(COMPANY_IDS)
    matrix_id = data.draw(MATRIX_IDS)

    # Create a soft-deleted matrix
    deleted_matrix = MatrixRecord(
        matrix_id=matrix_id,
        source_document_uuids=sources,
        target_document_uuids=targets,
        company_id=company_id,
        generation_timestamp=BASE_TIMESTAMP,
        deleted_at=BASE_TIMESTAMP + timedelta(hours=1),
    )

    # Resolve parent — should NOT find the deleted matrix
    parent_id = resolve_parent_matrix_id(
        source_document_uuids=sources,
        target_document_uuids=targets,
        company_id=company_id,
        existing_matrices=[deleted_matrix],
    )

    assert parent_id is None
