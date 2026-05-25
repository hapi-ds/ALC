"""Property-based tests for candidate prioritization in ImpactAnalysisService.

Property 8: Candidate Prioritization

For any set of downstream dependencies exceeding 50 items, the
Impact_Analysis_Engine SHALL select exactly 50 candidates prioritized first
by confidence_score (descending) and then by dependency_type priority order
(validates > implements > references > trains_on > derived_from). The selected
set SHALL always contain the highest-priority items.

**Validates: Requirements 3.6**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_analysis.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.impact_analysis import ImpactAnalysisService


# ---------------------------------------------------------------------------
# Lightweight stand-in for DependencyEdge (avoids DB session requirement)
# ---------------------------------------------------------------------------


@dataclass
class MockDependencyEdge:
    """Lightweight mock of DependencyEdge for property testing.

    Only the attributes used by _prioritize_candidates are needed:
    confidence_score and dependency_type.
    """

    id: int
    source_document_uuid: str
    target_document_uuid: str
    dependency_type: str
    confidence_score: float
    detected_references: dict
    last_verified_at: datetime
    company_id: int


# ---------------------------------------------------------------------------
# Constants (mirrored from ImpactAnalysisService for assertions)
# ---------------------------------------------------------------------------

DEPENDENCY_TYPE_PRIORITY: dict[str, int] = {
    "validates": 0,
    "implements": 1,
    "references": 2,
    "trains_on": 3,
    "derived_from": 4,
}

VALID_DEPENDENCY_TYPES = list(DEPENDENCY_TYPE_PRIORITY.keys())

MAX_CANDIDATES = 50


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

DEPENDENCY_TYPES = st.sampled_from(VALID_DEPENDENCY_TYPES)

CONFIDENCE_SCORES = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def st_dependency_edge(draw: st.DrawFn, index: int = 0) -> MockDependencyEdge:
    """Generate a single mock DependencyEdge with random score and type."""
    return MockDependencyEdge(
        id=index,
        source_document_uuid="src_doc_uuid",
        target_document_uuid=f"tgt_{index:04d}",
        dependency_type=draw(DEPENDENCY_TYPES),
        confidence_score=draw(CONFIDENCE_SCORES),
        detected_references={},
        last_verified_at=datetime.now(timezone.utc),
        company_id=1,
    )


@st.composite
def st_edges_over_limit(draw: st.DrawFn) -> list[MockDependencyEdge]:
    """Generate a list of >50 dependency edges with random scores/types."""
    count = draw(st.integers(min_value=51, max_value=150))
    edges = []
    for i in range(count):
        edge = MockDependencyEdge(
            id=i,
            source_document_uuid="src_doc_uuid",
            target_document_uuid=f"tgt_{i:04d}",
            dependency_type=draw(DEPENDENCY_TYPES),
            confidence_score=draw(CONFIDENCE_SCORES),
            detected_references={},
            last_verified_at=datetime.now(timezone.utc),
            company_id=1,
        )
        edges.append(edge)
    return edges


@st.composite
def st_edges_at_or_under_limit(draw: st.DrawFn) -> list[MockDependencyEdge]:
    """Generate a list of <=50 dependency edges."""
    count = draw(st.integers(min_value=0, max_value=50))
    edges = []
    for i in range(count):
        edge = MockDependencyEdge(
            id=i,
            source_document_uuid="src_doc_uuid",
            target_document_uuid=f"tgt_{i:04d}",
            dependency_type=draw(DEPENDENCY_TYPES),
            confidence_score=draw(CONFIDENCE_SCORES),
            detected_references={},
            last_verified_at=datetime.now(timezone.utc),
            company_id=1,
        )
        edges.append(edge)
    return edges


# ---------------------------------------------------------------------------
# Service instance (stateless for prioritization — no dependencies needed)
# ---------------------------------------------------------------------------

_service = ImpactAnalysisService()


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Exactly 50 selected when over limit
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_over_limit())
def test_selects_exactly_50_when_over_limit(
    edges: list[MockDependencyEdge],
) -> None:
    """For any set of downstream dependencies exceeding 50 items, the
    Impact_Analysis_Engine SHALL select exactly 50 candidates.

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)

    assert len(result) == MAX_CANDIDATES


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Sorted by confidence_score desc
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_over_limit())
def test_sorted_by_confidence_score_descending(
    edges: list[MockDependencyEdge],
) -> None:
    """The selected candidates SHALL be sorted first by confidence_score
    in descending order. For any two adjacent candidates in the result,
    the first SHALL have a confidence_score >= the second (when they have
    the same dependency_type priority).

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)

    for i in range(len(result) - 1):
        current_type_priority = DEPENDENCY_TYPE_PRIORITY.get(
            result[i].dependency_type, 99
        )
        next_type_priority = DEPENDENCY_TYPE_PRIORITY.get(
            result[i + 1].dependency_type, 99
        )

        # Primary sort: confidence_score descending
        # Secondary sort: type priority ascending
        current_key = (-result[i].confidence_score, current_type_priority)
        next_key = (-result[i + 1].confidence_score, next_type_priority)

        assert current_key <= next_key, (
            f"Candidate at index {i} has sort key {current_key} but candidate "
            f"at index {i + 1} has sort key {next_key}. Results must be sorted "
            f"by (-confidence_score, type_priority)."
        )


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Type priority as tiebreaker
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_over_limit())
def test_type_priority_breaks_ties_on_same_confidence(
    edges: list[MockDependencyEdge],
) -> None:
    """When two candidates have the same confidence_score, the one with
    higher dependency_type priority (lower numeric value) SHALL appear first.
    Priority order: validates(0) > implements(1) > references(2) >
    trains_on(3) > derived_from(4).

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)

    for i in range(len(result) - 1):
        if result[i].confidence_score == result[i + 1].confidence_score:
            current_priority = DEPENDENCY_TYPE_PRIORITY.get(
                result[i].dependency_type, 99
            )
            next_priority = DEPENDENCY_TYPE_PRIORITY.get(
                result[i + 1].dependency_type, 99
            )
            assert current_priority <= next_priority, (
                f"Candidates at indices {i} and {i + 1} have the same "
                f"confidence_score ({result[i].confidence_score}) but "
                f"type '{result[i].dependency_type}' (priority "
                f"{current_priority}) appears before "
                f"'{result[i + 1].dependency_type}' (priority "
                f"{next_priority}). Lower priority number should come first."
            )


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Contains highest-priority items
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_over_limit())
def test_selected_set_contains_highest_priority_items(
    edges: list[MockDependencyEdge],
) -> None:
    """The selected set SHALL always contain the highest-priority items.
    No item excluded from the top 50 SHALL have a higher priority (lower
    sort key) than any item included in the top 50.

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)
    result_ids = {e.id for e in result}
    excluded = [e for e in edges if e.id not in result_ids]

    if not excluded or not result:
        return

    # The worst item in the result should be >= any excluded item's priority
    # (i.e., the excluded items should all have worse sort keys)
    worst_in_result = max(
        result,
        key=lambda e: (
            -e.confidence_score,
            DEPENDENCY_TYPE_PRIORITY.get(e.dependency_type, 99),
        ),
    )
    worst_key = (
        -worst_in_result.confidence_score,
        DEPENDENCY_TYPE_PRIORITY.get(worst_in_result.dependency_type, 99),
    )

    for excluded_edge in excluded:
        excluded_key = (
            -excluded_edge.confidence_score,
            DEPENDENCY_TYPE_PRIORITY.get(excluded_edge.dependency_type, 99),
        )
        assert excluded_key >= worst_key, (
            f"Excluded edge (id={excluded_edge.id}, score="
            f"{excluded_edge.confidence_score}, type="
            f"'{excluded_edge.dependency_type}') has sort key "
            f"{excluded_key} which is better than the worst included "
            f"edge (id={worst_in_result.id}, score="
            f"{worst_in_result.confidence_score}, type="
            f"'{worst_in_result.dependency_type}') with sort key "
            f"{worst_key}. The selected set must contain the "
            f"highest-priority items."
        )


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Returns all when at/under limit
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_at_or_under_limit())
def test_returns_all_when_at_or_under_limit(
    edges: list[MockDependencyEdge],
) -> None:
    """When the number of candidates is <= 50, all candidates SHALL be
    returned (still sorted by priority).

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)

    assert len(result) == len(edges)


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Result is subset of input
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_over_limit())
def test_result_is_subset_of_input(
    edges: list[MockDependencyEdge],
) -> None:
    """All selected candidates SHALL be from the original input set — no
    candidates are fabricated or modified during prioritization.

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)

    input_ids = {e.id for e in edges}
    for edge in result:
        assert edge.id in input_ids, (
            f"Result contains edge with id={edge.id} which is not in the "
            f"original input set."
        )


# ---------------------------------------------------------------------------
# Property 8: Candidate Prioritization — Under-limit still sorted
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(edges=st_edges_at_or_under_limit())
def test_under_limit_still_sorted(
    edges: list[MockDependencyEdge],
) -> None:
    """Even when candidates count is <= 50, the returned list SHALL be
    sorted by (-confidence_score, type_priority).

    **Validates: Requirements 3.6**
    """
    result = _service._prioritize_candidates(edges)

    for i in range(len(result) - 1):
        current_key = (
            -result[i].confidence_score,
            DEPENDENCY_TYPE_PRIORITY.get(result[i].dependency_type, 99),
        )
        next_key = (
            -result[i + 1].confidence_score,
            DEPENDENCY_TYPE_PRIORITY.get(result[i + 1].dependency_type, 99),
        )
        assert current_key <= next_key, (
            f"Candidate at index {i} has sort key {current_key} but "
            f"candidate at index {i + 1} has sort key {next_key}. "
            f"Results must be sorted by (-confidence_score, type_priority)."
        )
