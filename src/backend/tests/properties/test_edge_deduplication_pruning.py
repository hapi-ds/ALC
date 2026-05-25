"""Property-based tests for edge deduplication and pruning.

Property 4: Edge Deduplication and Pruning

For any sequence of dependency edge insertions where the same
(source_document_uuid, target_document_uuid, dependency_type, company_id)
tuple appears multiple times, exactly one edge SHALL exist with the most
recently computed confidence_score, detected_references, and last_verified_at.
Additionally, for any incremental build where a document's content no longer
contains a previously detected reference, the corresponding edge SHALL be
removed.

**Validates: Requirements 1.13, 1.14**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/dependency_graph.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=10)

DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

DEPENDENCY_TYPES = st.sampled_from(
    ["validates", "references", "implements", "trains_on", "derived_from"]
)

CONFIDENCE_SCORES = st.floats(min_value=0.5, max_value=1.0, allow_nan=False)

REFERENCE_IDS = st.from_regex(r"REF-[A-Z]{2}-\d{3}", fullmatch=True)

TIMESTAMPS = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)


# ---------------------------------------------------------------------------
# Data models for pure-logic testing
# ---------------------------------------------------------------------------


@dataclass
class EdgeRecord:
    """Represents a dependency edge record in the graph store."""

    source_document_uuid: str
    target_document_uuid: str
    dependency_type: str
    company_id: int
    confidence_score: float
    detected_references: list[str]
    last_verified_at: datetime


@dataclass
class EdgeInsertion:
    """Represents a single edge insertion request."""

    source_document_uuid: str
    target_document_uuid: str
    dependency_type: str
    company_id: int
    confidence_score: float
    detected_references: list[str]
    last_verified_at: datetime


# ---------------------------------------------------------------------------
# Pure-logic functions modeling the deduplication and pruning behavior
# ---------------------------------------------------------------------------


def upsert_edge(
    store: dict[tuple[str, str, str, int], EdgeRecord],
    insertion: EdgeInsertion,
) -> None:
    """Upsert an edge into the store.

    Models the PostgreSQL INSERT...ON CONFLICT DO UPDATE behavior from
    DependencyGraphService._upsert_edge. If an edge with the same
    (source_document_uuid, target_document_uuid, dependency_type, company_id)
    already exists, updates confidence_score, detected_references, and
    last_verified_at with the new values.

    Args:
        store: Dict keyed by (source, target, type, company_id) → EdgeRecord.
        insertion: The edge insertion request.
    """
    key = (
        insertion.source_document_uuid,
        insertion.target_document_uuid,
        insertion.dependency_type,
        insertion.company_id,
    )
    store[key] = EdgeRecord(
        source_document_uuid=insertion.source_document_uuid,
        target_document_uuid=insertion.target_document_uuid,
        dependency_type=insertion.dependency_type,
        company_id=insertion.company_id,
        confidence_score=insertion.confidence_score,
        detected_references=insertion.detected_references,
        last_verified_at=insertion.last_verified_at,
    )


def prune_stale_edges(
    store: dict[tuple[str, str, str, int], EdgeRecord],
    source_document_uuid: str,
    company_id: int,
    current_reference_ids: set[str],
) -> int:
    """Prune stale edges from a modified document.

    Models the DependencyGraphService._prune_stale_edges behavior.
    Removes edges originating from the document whose detected_references
    are no longer present in the document's current content.

    Edges with special prefixes (TrainingTask:, GenerationProvenance:,
    semantic:) are skipped (DB-linked or semantic edges are not pruned
    based on text content).

    Args:
        store: Dict keyed by (source, target, type, company_id) → EdgeRecord.
        source_document_uuid: UUID of the modified document.
        company_id: Company ID for tenant scoping.
        current_reference_ids: Set of reference identifiers currently present
            in the document's content.

    Returns:
        Number of edges pruned.
    """
    keys_to_remove: list[tuple[str, str, str, int]] = []

    for key, edge in store.items():
        # Only consider edges from this document in this company
        if edge.source_document_uuid != source_document_uuid:
            continue
        if edge.company_id != company_id:
            continue

        # Skip DB-linked and semantic edges
        detected_refs = edge.detected_references or []
        if any(
            ref.startswith("TrainingTask:")
            or ref.startswith("GenerationProvenance:")
            or ref.startswith("semantic:")
            for ref in detected_refs
        ):
            continue

        # Check if any detected reference is still present
        if detected_refs:
            still_present = any(ref in current_reference_ids for ref in detected_refs)
            if not still_present:
                keys_to_remove.append(key)

    for key in keys_to_remove:
        del store[key]

    return len(keys_to_remove)


# ---------------------------------------------------------------------------
# Composite Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_edge_insertion(draw: st.DrawFn) -> EdgeInsertion:
    """Generate a single edge insertion request."""
    return EdgeInsertion(
        source_document_uuid=draw(DOCUMENT_UUIDS),
        target_document_uuid=draw(DOCUMENT_UUIDS),
        dependency_type=draw(DEPENDENCY_TYPES),
        company_id=draw(COMPANY_IDS),
        confidence_score=draw(CONFIDENCE_SCORES),
        detected_references=draw(
            st.lists(REFERENCE_IDS, min_size=1, max_size=5, unique=True)
        ),
        last_verified_at=draw(TIMESTAMPS),
    )


@st.composite
def st_duplicate_edge_sequence(draw: st.DrawFn) -> list[EdgeInsertion]:
    """Generate a sequence of edge insertions with guaranteed duplicates.

    Creates a base edge key and generates multiple insertions with the same
    (source, target, type, company_id) but different confidence_score,
    detected_references, and last_verified_at values.
    """
    source_uuid = draw(DOCUMENT_UUIDS)
    target_uuid = draw(DOCUMENT_UUIDS)
    dep_type = draw(DEPENDENCY_TYPES)
    company_id = draw(COMPANY_IDS)

    # Generate 2-10 insertions with the same key but different values
    count = draw(st.integers(min_value=2, max_value=10))
    insertions: list[EdgeInsertion] = []

    for _ in range(count):
        insertions.append(
            EdgeInsertion(
                source_document_uuid=source_uuid,
                target_document_uuid=target_uuid,
                dependency_type=dep_type,
                company_id=company_id,
                confidence_score=draw(CONFIDENCE_SCORES),
                detected_references=draw(
                    st.lists(REFERENCE_IDS, min_size=1, max_size=5, unique=True)
                ),
                last_verified_at=draw(TIMESTAMPS),
            )
        )

    return insertions


@st.composite
def st_mixed_edge_sequence(draw: st.DrawFn) -> list[EdgeInsertion]:
    """Generate a mixed sequence of edge insertions with some duplicates.

    Produces a sequence where some edges share the same key (duplicates)
    and some are unique, simulating a realistic build scenario.
    """
    # Generate some unique edges
    unique_count = draw(st.integers(min_value=1, max_value=5))
    unique_edges = [draw(st_edge_insertion()) for _ in range(unique_count)]

    # Generate duplicate sequences for some of the unique edges
    dup_count = draw(st.integers(min_value=1, max_value=3))
    dup_sequences: list[EdgeInsertion] = []
    for _ in range(dup_count):
        seq = draw(st_duplicate_edge_sequence())
        dup_sequences.extend(seq)

    # Interleave them
    all_insertions = unique_edges + dup_sequences
    # Shuffle using hypothesis
    shuffled = draw(st.permutations(all_insertions))
    return list(shuffled)


@st.composite
def st_pruning_scenario(draw: st.DrawFn) -> dict:
    """Generate a pruning scenario with edges and current references.

    Creates a set of edges from a document, then generates a subset of
    references that are "still present" — edges whose references are not
    in this subset should be pruned.
    """
    source_uuid = draw(DOCUMENT_UUIDS)
    company_id = draw(COMPANY_IDS)

    # Generate edges from this document (explicit cross-reference edges)
    edge_count = draw(st.integers(min_value=2, max_value=8))
    edges: list[EdgeInsertion] = []
    all_refs: list[str] = []

    for _ in range(edge_count):
        refs = draw(st.lists(REFERENCE_IDS, min_size=1, max_size=3, unique=True))
        all_refs.extend(refs)
        edges.append(
            EdgeInsertion(
                source_document_uuid=source_uuid,
                target_document_uuid=draw(DOCUMENT_UUIDS),
                dependency_type=draw(DEPENDENCY_TYPES),
                company_id=company_id,
                confidence_score=draw(CONFIDENCE_SCORES),
                detected_references=refs,
                last_verified_at=draw(TIMESTAMPS),
            )
        )

    # Select a subset of references that are "still present"
    unique_refs = list(set(all_refs))
    if unique_refs:
        keep_count = draw(st.integers(min_value=0, max_value=len(unique_refs)))
        current_refs = set(draw(st.sampled_from(
            [frozenset(combo) for combo in _combinations(unique_refs, keep_count)]
        ))) if keep_count > 0 else set()
    else:
        current_refs = set()

    return {
        "source_uuid": source_uuid,
        "company_id": company_id,
        "edges": edges,
        "current_reference_ids": current_refs,
    }


def _combinations(items: list[str], count: int) -> list[list[str]]:
    """Generate all combinations of items with given count (simple helper)."""
    if count == 0:
        return [[]]
    if count >= len(items):
        return [items]
    # Just take the first `count` items for simplicity in strategy
    return [items[:count]]


@st.composite
def st_pruning_scenario_simple(draw: st.DrawFn) -> dict:
    """Generate a simpler pruning scenario.

    Creates edges with known references, then removes some references
    from the "current" set to verify pruning behavior.
    """
    source_uuid = draw(DOCUMENT_UUIDS)
    company_id = draw(COMPANY_IDS)

    # Generate a pool of reference IDs
    all_ref_ids = draw(
        st.lists(REFERENCE_IDS, min_size=3, max_size=10, unique=True)
    )

    # Create edges, each with a subset of references
    edge_count = draw(st.integers(min_value=2, max_value=5))
    edges: list[EdgeInsertion] = []

    for i in range(edge_count):
        # Each edge gets 1-3 references from the pool
        ref_count = draw(st.integers(min_value=1, max_value=min(3, len(all_ref_ids))))
        refs = draw(
            st.lists(
                st.sampled_from(all_ref_ids),
                min_size=ref_count,
                max_size=ref_count,
                unique=True,
            )
        )
        edges.append(
            EdgeInsertion(
                source_document_uuid=source_uuid,
                target_document_uuid=draw(DOCUMENT_UUIDS),
                dependency_type=draw(DEPENDENCY_TYPES),
                company_id=company_id,
                confidence_score=draw(CONFIDENCE_SCORES),
                detected_references=refs,
                last_verified_at=draw(TIMESTAMPS),
            )
        )

    # Decide which references are "still present" in the document
    current_refs = set(
        draw(
            st.lists(
                st.sampled_from(all_ref_ids),
                min_size=0,
                max_size=len(all_ref_ids),
                unique=True,
            )
        )
    )

    return {
        "source_uuid": source_uuid,
        "company_id": company_id,
        "edges": edges,
        "current_reference_ids": current_refs,
    }


# ---------------------------------------------------------------------------
# Property 4: Edge Deduplication — Exactly one edge per unique key
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(insertions=st_duplicate_edge_sequence())
def test_duplicate_insertions_produce_single_edge(
    insertions: list[EdgeInsertion],
) -> None:
    """For any sequence of dependency edge insertions where the same
    (source_document_uuid, target_document_uuid, dependency_type, company_id)
    tuple appears multiple times, exactly one edge SHALL exist after all
    insertions are processed.

    **Validates: Requirements 1.13**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    for insertion in insertions:
        upsert_edge(store, insertion)

    # All insertions share the same key, so exactly one edge should exist
    assert len(store) == 1


@settings(max_examples=100)
@given(insertions=st_duplicate_edge_sequence())
def test_duplicate_insertions_retain_last_values(
    insertions: list[EdgeInsertion],
) -> None:
    """For any sequence of duplicate edge insertions, the surviving edge
    SHALL have the most recently computed confidence_score,
    detected_references, and last_verified_at (i.e., the values from
    the last insertion in the sequence).

    **Validates: Requirements 1.13**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    for insertion in insertions:
        upsert_edge(store, insertion)

    # The last insertion's values should be retained
    last = insertions[-1]
    key = (
        last.source_document_uuid,
        last.target_document_uuid,
        last.dependency_type,
        last.company_id,
    )
    edge = store[key]

    assert edge.confidence_score == last.confidence_score
    assert edge.detected_references == last.detected_references
    assert edge.last_verified_at == last.last_verified_at


@settings(max_examples=100)
@given(insertions=st_mixed_edge_sequence())
def test_mixed_insertions_deduplicate_correctly(
    insertions: list[EdgeInsertion],
) -> None:
    """For any mixed sequence of edge insertions (some duplicates, some unique),
    the final store SHALL contain exactly one edge per unique
    (source_document_uuid, target_document_uuid, dependency_type, company_id)
    tuple.

    **Validates: Requirements 1.13**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    for insertion in insertions:
        upsert_edge(store, insertion)

    # Count unique keys in the input
    unique_keys = set()
    for ins in insertions:
        key = (
            ins.source_document_uuid,
            ins.target_document_uuid,
            ins.dependency_type,
            ins.company_id,
        )
        unique_keys.add(key)

    assert len(store) == len(unique_keys)


@settings(max_examples=100)
@given(insertions=st_mixed_edge_sequence())
def test_each_edge_has_last_insertion_values(
    insertions: list[EdgeInsertion],
) -> None:
    """For any mixed sequence of edge insertions, each edge in the final store
    SHALL have the confidence_score, detected_references, and last_verified_at
    from the last insertion with that key.

    **Validates: Requirements 1.13**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    for insertion in insertions:
        upsert_edge(store, insertion)

    # Compute expected last values per key
    last_values: dict[tuple[str, str, str, int], EdgeInsertion] = {}
    for ins in insertions:
        key = (
            ins.source_document_uuid,
            ins.target_document_uuid,
            ins.dependency_type,
            ins.company_id,
        )
        last_values[key] = ins

    for key, expected in last_values.items():
        edge = store[key]
        assert edge.confidence_score == expected.confidence_score
        assert edge.detected_references == expected.detected_references
        assert edge.last_verified_at == expected.last_verified_at


# ---------------------------------------------------------------------------
# Property 4: Edge Pruning — Stale edges removed
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(scenario=st_pruning_scenario_simple())
def test_edges_with_no_current_references_are_pruned(
    scenario: dict,
) -> None:
    """For any incremental build where a document's content no longer contains
    a previously detected reference, the corresponding edge SHALL be removed.

    An edge is pruned when NONE of its detected_references are present in
    the document's current reference set.

    **Validates: Requirements 1.14**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}
    source_uuid = scenario["source_uuid"]
    company_id = scenario["company_id"]
    edges = scenario["edges"]
    current_refs = scenario["current_reference_ids"]

    # Insert all edges
    for edge_ins in edges:
        upsert_edge(store, edge_ins)

    # Prune stale edges
    prune_stale_edges(store, source_uuid, company_id, current_refs)

    # Verify: every remaining edge from this source/company must have at least
    # one detected_reference that is in current_refs (or have empty refs)
    for key, edge in store.items():
        if edge.source_document_uuid != source_uuid:
            continue
        if edge.company_id != company_id:
            continue
        # If edge has detected_references, at least one must be current
        if edge.detected_references:
            assert any(
                ref in current_refs for ref in edge.detected_references
            ), (
                f"Edge {key} has stale references {edge.detected_references} "
                f"but was not pruned. Current refs: {current_refs}"
            )


@settings(max_examples=100)
@given(scenario=st_pruning_scenario_simple())
def test_edges_with_current_references_are_retained(
    scenario: dict,
) -> None:
    """For any incremental build, edges whose detected_references still appear
    in the document's current content SHALL NOT be removed.

    **Validates: Requirements 1.14**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}
    source_uuid = scenario["source_uuid"]
    company_id = scenario["company_id"]
    edges = scenario["edges"]
    current_refs = scenario["current_reference_ids"]

    # Insert all edges
    for edge_ins in edges:
        upsert_edge(store, edge_ins)

    # Count edges that should survive (have at least one current ref)
    edges_before = {
        k: v for k, v in store.items()
        if v.source_document_uuid == source_uuid and v.company_id == company_id
    }
    expected_survivors = {
        k: v for k, v in edges_before.items()
        if any(ref in current_refs for ref in v.detected_references)
    }

    # Prune
    prune_stale_edges(store, source_uuid, company_id, current_refs)

    # All expected survivors should still be present
    for key in expected_survivors:
        assert key in store, (
            f"Edge {key} had current references but was incorrectly pruned"
        )


@settings(max_examples=100)
@given(scenario=st_pruning_scenario_simple())
def test_pruning_count_matches_removed_edges(
    scenario: dict,
) -> None:
    """The prune_stale_edges function SHALL return the exact count of edges
    that were removed from the store.

    **Validates: Requirements 1.14**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}
    source_uuid = scenario["source_uuid"]
    company_id = scenario["company_id"]
    edges = scenario["edges"]
    current_refs = scenario["current_reference_ids"]

    # Insert all edges
    for edge_ins in edges:
        upsert_edge(store, edge_ins)

    edges_before_count = len(store)

    # Prune
    pruned_count = prune_stale_edges(store, source_uuid, company_id, current_refs)

    edges_after_count = len(store)

    # The pruned count should equal the difference
    assert pruned_count == edges_before_count - edges_after_count


@settings(max_examples=50)
@given(
    source_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    target_uuid=DOCUMENT_UUIDS,
    dep_type=DEPENDENCY_TYPES,
    confidence=CONFIDENCE_SCORES,
    timestamp=TIMESTAMPS,
)
def test_db_linked_edges_not_pruned(
    source_uuid: str,
    company_id: int,
    target_uuid: str,
    dep_type: str,
    confidence: float,
    timestamp: datetime,
) -> None:
    """Edges with detected_references prefixed with 'TrainingTask:',
    'GenerationProvenance:', or 'semantic:' SHALL NOT be pruned regardless
    of whether their references appear in the current document content.

    These represent DB-linked or semantic relationships that are not
    derived from text content.

    **Validates: Requirements 1.14**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    # Create edges with special prefixes
    db_linked_refs = [
        [f"TrainingTask:{source_uuid}"],
        [f"GenerationProvenance:gen-001"],
        [f"semantic:{source_uuid}->{target_uuid}"],
    ]

    for i, refs in enumerate(db_linked_refs):
        insertion = EdgeInsertion(
            source_document_uuid=source_uuid,
            target_document_uuid=f"{target_uuid}{i}",  # unique targets
            dependency_type=dep_type,
            company_id=company_id,
            confidence_score=confidence,
            detected_references=refs,
            last_verified_at=timestamp,
        )
        upsert_edge(store, insertion)

    edges_before = len(store)

    # Prune with empty current references (nothing is "current")
    pruned = prune_stale_edges(store, source_uuid, company_id, set())

    # No DB-linked edges should be pruned
    assert pruned == 0
    assert len(store) == edges_before


@settings(max_examples=50)
@given(
    source_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
)
def test_pruning_does_not_affect_other_documents(
    source_uuid: str,
    company_id: int,
) -> None:
    """Pruning SHALL only affect edges originating from the specified
    source_document_uuid within the specified company_id. Edges from
    other documents or other companies SHALL remain unchanged.

    **Validates: Requirements 1.14**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    # Create an edge from the target document
    other_source = "2025-99999"
    other_company = company_id + 1

    # Edge from another document (same company)
    upsert_edge(
        store,
        EdgeInsertion(
            source_document_uuid=other_source,
            target_document_uuid="2025-00001",
            dependency_type="references",
            company_id=company_id,
            confidence_score=0.8,
            detected_references=["REF-XX-001"],
            last_verified_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )

    # Edge from same document but different company
    upsert_edge(
        store,
        EdgeInsertion(
            source_document_uuid=source_uuid,
            target_document_uuid="2025-00002",
            dependency_type="validates",
            company_id=other_company,
            confidence_score=0.9,
            detected_references=["REF-YY-002"],
            last_verified_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )

    # Edge from the target document+company (should be pruned)
    upsert_edge(
        store,
        EdgeInsertion(
            source_document_uuid=source_uuid,
            target_document_uuid="2025-00003",
            dependency_type="references",
            company_id=company_id,
            confidence_score=0.7,
            detected_references=["REF-ZZ-003"],
            last_verified_at=datetime(2025, 1, 1, tzinfo=UTC),
        ),
    )

    assert len(store) == 3

    # Prune with empty current refs — only the matching edge should be removed
    pruned = prune_stale_edges(store, source_uuid, company_id, set())

    assert pruned == 1
    assert len(store) == 2

    # Verify the other edges are still present
    assert (other_source, "2025-00001", "references", company_id) in store
    assert (source_uuid, "2025-00002", "validates", other_company) in store


@settings(max_examples=50)
@given(
    source_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    refs=st.lists(REFERENCE_IDS, min_size=2, max_size=5, unique=True),
    target_uuid=DOCUMENT_UUIDS,
    dep_type=DEPENDENCY_TYPES,
    confidence=CONFIDENCE_SCORES,
    timestamp=TIMESTAMPS,
)
def test_edge_retained_if_any_reference_still_present(
    source_uuid: str,
    company_id: int,
    refs: list[str],
    target_uuid: str,
    dep_type: str,
    confidence: float,
    timestamp: datetime,
) -> None:
    """An edge SHALL NOT be pruned if at least one of its detected_references
    is still present in the document's current content, even if other
    references from the same edge have been removed.

    **Validates: Requirements 1.14**
    """
    store: dict[tuple[str, str, str, int], EdgeRecord] = {}

    upsert_edge(
        store,
        EdgeInsertion(
            source_document_uuid=source_uuid,
            target_document_uuid=target_uuid,
            dependency_type=dep_type,
            company_id=company_id,
            confidence_score=confidence,
            detected_references=refs,
            last_verified_at=timestamp,
        ),
    )

    # Keep only the first reference as "current"
    current_refs = {refs[0]}

    pruned = prune_stale_edges(store, source_uuid, company_id, current_refs)

    # Edge should NOT be pruned because one reference is still present
    assert pruned == 0
    assert len(store) == 1
