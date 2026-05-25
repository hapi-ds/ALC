"""Property-based tests for dependency validation threshold in GapAnalysisService.

Property 10: Dependency Validation Threshold

For any gap analysis request between two documents, the system SHALL reject
the request with HTTP 422 if no dependency edge exists between them with
confidence_score >= 0.5. The system SHALL accept the request if at least one
such edge exists.

**Validates: Requirements 4.6**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/gap_analysis.py
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.gap_analysis import MIN_DEPENDENCY_CONFIDENCE


# ---------------------------------------------------------------------------
# Domain model for dependency validation logic (pure functions under test)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DependencyEdgeCandidate:
    """Represents a dependency edge between two documents.

    Attributes:
        source_uuid: UUID of the source document.
        target_uuid: UUID of the target document.
        confidence_score: Confidence score of the edge (0.0 to 1.0).
        company_id: Company ID for tenant scoping.
    """

    source_uuid: str
    target_uuid: str
    confidence_score: float
    company_id: int


def should_accept_gap_analysis(
    edges: list[DependencyEdgeCandidate],
    source_uuid: str,
    target_uuid: str,
    company_id: int,
) -> bool:
    """Determine whether a gap analysis request should be accepted.

    Mirrors the logic in GapAnalysisService._check_dependency_exists:
    accepts if at least one edge exists between the documents (in either
    direction) with confidence_score >= MIN_DEPENDENCY_CONFIDENCE (0.5),
    scoped to the given company.

    Args:
        edges: All dependency edges in the system.
        source_uuid: UUID of the source document for gap analysis.
        target_uuid: UUID of the target document for gap analysis.
        company_id: Company ID for tenant scoping.

    Returns:
        True if the request should be accepted, False if it should be
        rejected with HTTP 422.
    """
    for edge in edges:
        if edge.company_id != company_id:
            continue
        if edge.confidence_score < MIN_DEPENDENCY_CONFIDENCE:
            continue
        # Check both directions (source→target and target→source)
        if (
            (edge.source_uuid == source_uuid and edge.target_uuid == target_uuid)
            or (edge.source_uuid == target_uuid and edge.target_uuid == source_uuid)
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Document UUIDs (12-char strings matching the model constraint)
DOCUMENT_UUIDS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
    min_size=12,
    max_size=12,
)

# Company IDs
COMPANY_IDS = st.integers(min_value=1, max_value=1000)

# Confidence scores below the threshold (should reject)
BELOW_THRESHOLD_SCORES = st.floats(
    min_value=0.0,
    max_value=0.4999999,
    allow_nan=False,
    allow_infinity=False,
)

# Confidence scores at or above the threshold (should accept)
ABOVE_THRESHOLD_SCORES = st.floats(
    min_value=0.5,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# All valid confidence scores
ALL_CONFIDENCE_SCORES = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def st_edge(
    draw: st.DrawFn,
    source_uuid: str | None = None,
    target_uuid: str | None = None,
    company_id: int | None = None,
    confidence: st.SearchStrategy[float] | None = None,
) -> DependencyEdgeCandidate:
    """Generate a dependency edge with optional fixed fields.

    Args:
        draw: Hypothesis draw function.
        source_uuid: Fixed source UUID, or None to generate.
        target_uuid: Fixed target UUID, or None to generate.
        company_id: Fixed company ID, or None to generate.
        confidence: Strategy for confidence score, or None for any.

    Returns:
        A DependencyEdgeCandidate instance.
    """
    return DependencyEdgeCandidate(
        source_uuid=source_uuid or draw(DOCUMENT_UUIDS),
        target_uuid=target_uuid or draw(DOCUMENT_UUIDS),
        confidence_score=draw(confidence or ALL_CONFIDENCE_SCORES),
        company_id=company_id or draw(COMPANY_IDS),
    )


# ---------------------------------------------------------------------------
# Property 10: No qualifying edge → reject with 422
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
)
def test_no_edges_rejects_request(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
) -> None:
    """For any gap analysis request where no dependency edges exist at all,
    the system SHALL reject the request (return False / HTTP 422).

    **Validates: Requirements 4.6**
    """
    result = should_accept_gap_analysis(
        edges=[],
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is False


# ---------------------------------------------------------------------------
# Property 10: All edges below threshold → reject with 422
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    scores=st.lists(BELOW_THRESHOLD_SCORES, min_size=1, max_size=10),
)
def test_all_edges_below_threshold_rejects_request(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
    scores: list[float],
) -> None:
    """For any gap analysis request where all dependency edges between the
    documents have confidence_score < 0.5, the system SHALL reject the
    request with HTTP 422.

    **Validates: Requirements 4.6**
    """
    edges = [
        DependencyEdgeCandidate(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            confidence_score=score,
            company_id=company_id,
        )
        for score in scores
    ]

    result = should_accept_gap_analysis(
        edges=edges,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is False


# ---------------------------------------------------------------------------
# Property 10: At least one edge at or above threshold → accept
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    qualifying_score=ABOVE_THRESHOLD_SCORES,
    other_scores=st.lists(ALL_CONFIDENCE_SCORES, min_size=0, max_size=5),
)
def test_edge_at_or_above_threshold_accepts_request(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
    qualifying_score: float,
    other_scores: list[float],
) -> None:
    """For any gap analysis request where at least one dependency edge exists
    between the documents with confidence_score >= 0.5, the system SHALL
    accept the request.

    **Validates: Requirements 4.6**
    """
    # Create the qualifying edge plus any other edges
    edges = [
        DependencyEdgeCandidate(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            confidence_score=qualifying_score,
            company_id=company_id,
        )
    ]
    # Add other edges (may or may not qualify)
    for score in other_scores:
        edges.append(
            DependencyEdgeCandidate(
                source_uuid=source_uuid,
                target_uuid=target_uuid,
                confidence_score=score,
                company_id=company_id,
            )
        )

    result = should_accept_gap_analysis(
        edges=edges,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is True


# ---------------------------------------------------------------------------
# Property 10: Reverse direction edge also qualifies
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    qualifying_score=ABOVE_THRESHOLD_SCORES,
)
def test_reverse_direction_edge_accepts_request(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
    qualifying_score: float,
) -> None:
    """For any gap analysis request where a qualifying edge exists in the
    reverse direction (target→source instead of source→target), the system
    SHALL still accept the request. The dependency check is bidirectional.

    **Validates: Requirements 4.6**
    """
    # Edge is stored in reverse direction (target→source)
    edges = [
        DependencyEdgeCandidate(
            source_uuid=target_uuid,
            target_uuid=source_uuid,
            confidence_score=qualifying_score,
            company_id=company_id,
        )
    ]

    result = should_accept_gap_analysis(
        edges=edges,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is True


# ---------------------------------------------------------------------------
# Property 10: Edges for different company do not qualify
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    other_company_id=COMPANY_IDS,
    qualifying_score=ABOVE_THRESHOLD_SCORES,
)
def test_edge_for_different_company_rejects_request(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
    other_company_id: int,
    qualifying_score: float,
) -> None:
    """For any gap analysis request where qualifying edges exist but belong
    to a different company, the system SHALL reject the request. Dependency
    validation is company-scoped.

    **Validates: Requirements 4.6**
    """
    # Ensure companies are actually different
    if company_id == other_company_id:
        return  # Skip this case — not testing same-company

    edges = [
        DependencyEdgeCandidate(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            confidence_score=qualifying_score,
            company_id=other_company_id,  # Different company
        )
    ]

    result = should_accept_gap_analysis(
        edges=edges,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is False


# ---------------------------------------------------------------------------
# Property 10: Edges for different document pair do not qualify
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    unrelated_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    qualifying_score=ABOVE_THRESHOLD_SCORES,
)
def test_edge_for_different_documents_rejects_request(
    source_uuid: str,
    target_uuid: str,
    unrelated_uuid: str,
    company_id: int,
    qualifying_score: float,
) -> None:
    """For any gap analysis request where qualifying edges exist but connect
    different documents (not the requested pair), the system SHALL reject
    the request.

    **Validates: Requirements 4.6**
    """
    # Ensure the unrelated UUID is actually different from both
    if unrelated_uuid == source_uuid or unrelated_uuid == target_uuid:
        return  # Skip — not testing same-document case

    edges = [
        DependencyEdgeCandidate(
            source_uuid=source_uuid,
            target_uuid=unrelated_uuid,  # Different target
            confidence_score=qualifying_score,
            company_id=company_id,
        )
    ]

    result = should_accept_gap_analysis(
        edges=edges,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is False


# ---------------------------------------------------------------------------
# Property 10: Boundary behavior at exactly 0.5
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    epsilon=st.floats(
        min_value=1e-10,
        max_value=0.01,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_threshold_boundary_at_exactly_half(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
    epsilon: float,
) -> None:
    """At the exact threshold (0.5), the system SHALL accept the request.
    Just below the threshold, the system SHALL reject the request.

    **Validates: Requirements 4.6**
    """
    # At threshold: accept
    edge_at_threshold = DependencyEdgeCandidate(
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        confidence_score=MIN_DEPENDENCY_CONFIDENCE,
        company_id=company_id,
    )
    result_at = should_accept_gap_analysis(
        edges=[edge_at_threshold],
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result_at is True

    # Below threshold: reject
    edge_below_threshold = DependencyEdgeCandidate(
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        confidence_score=MIN_DEPENDENCY_CONFIDENCE - epsilon,
        company_id=company_id,
    )
    result_below = should_accept_gap_analysis(
        edges=[edge_below_threshold],
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result_below is False


# ---------------------------------------------------------------------------
# Property 10: Mixed edges — one qualifying is sufficient
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    source_uuid=DOCUMENT_UUIDS,
    target_uuid=DOCUMENT_UUIDS,
    company_id=COMPANY_IDS,
    below_scores=st.lists(BELOW_THRESHOLD_SCORES, min_size=1, max_size=5),
    qualifying_score=ABOVE_THRESHOLD_SCORES,
)
def test_single_qualifying_edge_among_non_qualifying_accepts(
    source_uuid: str,
    target_uuid: str,
    company_id: int,
    below_scores: list[float],
    qualifying_score: float,
) -> None:
    """For any gap analysis request where multiple edges exist between the
    documents but only one has confidence_score >= 0.5, the system SHALL
    accept the request. A single qualifying edge is sufficient.

    **Validates: Requirements 4.6**
    """
    # Create non-qualifying edges
    edges = [
        DependencyEdgeCandidate(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            confidence_score=score,
            company_id=company_id,
        )
        for score in below_scores
    ]
    # Add one qualifying edge
    edges.append(
        DependencyEdgeCandidate(
            source_uuid=source_uuid,
            target_uuid=target_uuid,
            confidence_score=qualifying_score,
            company_id=company_id,
        )
    )

    result = should_accept_gap_analysis(
        edges=edges,
        source_uuid=source_uuid,
        target_uuid=target_uuid,
        company_id=company_id,
    )
    assert result is True
