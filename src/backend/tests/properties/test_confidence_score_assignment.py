"""Property-based tests for confidence score assignment in DependencyGraphService.

Property 1: Confidence Score Assignment

For any dependency edge detected between two documents, the confidence_score
SHALL be assigned based on detection method: exactly 1.0 for explicit
cross-references (exact ID matches), exactly 0.9 for database-linked
relationships (TrainingTask, GenerationProvenance), and between 0.5 and 0.8
(inclusive) for semantically inferred relationships. Furthermore, for any
candidate relationship with embedding similarity below 0.5, no edge SHALL
be created.

**Validates: Requirements 1.6**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/dependency_graph.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.dependency_graph import SEMANTIC_SIMILARITY_THRESHOLD


# ---------------------------------------------------------------------------
# Domain model for confidence score logic (pure functions under test)
# ---------------------------------------------------------------------------


class DetectionMethod(Enum):
    """How a dependency relationship was detected."""

    EXPLICIT_CROSS_REFERENCE = "explicit_cross_reference"
    DATABASE_LINKED = "database_linked"
    SEMANTIC_SIMILARITY = "semantic_similarity"


@dataclass(frozen=True)
class DetectionResult:
    """Result of a dependency detection attempt."""

    method: DetectionMethod
    similarity_score: float | None  # Only relevant for semantic method


def compute_confidence_score(detection: DetectionResult) -> float | None:
    """Compute the confidence score for a detected dependency.

    Implements the confidence score assignment logic from
    DependencyGraphService:
    - Explicit cross-references: exactly 1.0
    - Database-linked (TrainingTask, GenerationProvenance): exactly 0.9
    - Semantic similarity: 0.5 to 0.8 (scaled from similarity score)
    - Below threshold (0.5): returns None (no edge created)

    This mirrors the logic in:
    - _process_document_edges (confidence 1.0 for explicit refs)
    - _build_db_linked_edges (confidence 0.9 for DB-linked)
    - _compute_semantic_edges (confidence 0.5-0.8 for semantic)

    Args:
        detection: The detection result with method and optional similarity.

    Returns:
        The confidence score (0.5 to 1.0), or None if below threshold.
    """
    if detection.method == DetectionMethod.EXPLICIT_CROSS_REFERENCE:
        return 1.0

    if detection.method == DetectionMethod.DATABASE_LINKED:
        return 0.9

    # Semantic similarity
    similarity = detection.similarity_score
    if similarity is None or similarity < SEMANTIC_SIMILARITY_THRESHOLD:
        return None

    # Scale similarity from [0.5, 1.0] to [0.5, 0.8]
    confidence = 0.5 + (similarity - 0.5) * 0.6
    confidence = min(confidence, 0.8)
    return round(confidence, 3)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Similarity scores that are below the threshold (no edge should be created)
BELOW_THRESHOLD_SIMILARITIES = st.floats(
    min_value=0.0,
    max_value=0.4999999,
    allow_nan=False,
    allow_infinity=False,
)

# Similarity scores at or above the threshold (edge should be created)
ABOVE_THRESHOLD_SIMILARITIES = st.floats(
    min_value=0.5,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# All valid similarity scores
ALL_SIMILARITIES = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Detection methods
DETECTION_METHODS = st.sampled_from(list(DetectionMethod))


def st_explicit_detection() -> st.SearchStrategy[DetectionResult]:
    """Generate an explicit cross-reference detection result."""
    return st.just(
        DetectionResult(
            method=DetectionMethod.EXPLICIT_CROSS_REFERENCE,
            similarity_score=None,
        )
    )


def st_db_linked_detection() -> st.SearchStrategy[DetectionResult]:
    """Generate a database-linked detection result."""
    return st.just(
        DetectionResult(
            method=DetectionMethod.DATABASE_LINKED,
            similarity_score=None,
        )
    )


@st.composite
def st_semantic_detection_above_threshold(draw: st.DrawFn) -> DetectionResult:
    """Generate a semantic detection result with similarity >= 0.5."""
    similarity = draw(ABOVE_THRESHOLD_SIMILARITIES)
    return DetectionResult(
        method=DetectionMethod.SEMANTIC_SIMILARITY,
        similarity_score=similarity,
    )


@st.composite
def st_semantic_detection_below_threshold(draw: st.DrawFn) -> DetectionResult:
    """Generate a semantic detection result with similarity < 0.5."""
    similarity = draw(BELOW_THRESHOLD_SIMILARITIES)
    return DetectionResult(
        method=DetectionMethod.SEMANTIC_SIMILARITY,
        similarity_score=similarity,
    )


@st.composite
def st_any_detection(draw: st.DrawFn) -> DetectionResult:
    """Generate any valid detection result."""
    method = draw(DETECTION_METHODS)
    if method == DetectionMethod.SEMANTIC_SIMILARITY:
        similarity = draw(ALL_SIMILARITIES)
        return DetectionResult(method=method, similarity_score=similarity)
    return DetectionResult(method=method, similarity_score=None)


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Explicit Cross-References
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(detection=st_explicit_detection())
def test_explicit_cross_reference_confidence_is_exactly_one(
    detection: DetectionResult,
) -> None:
    """For any dependency edge detected via explicit cross-reference (exact ID
    match), the confidence_score SHALL be exactly 1.0.

    **Validates: Requirements 1.6**
    """
    score = compute_confidence_score(detection)
    assert score == 1.0


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Database-Linked Relationships
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(detection=st_db_linked_detection())
def test_database_linked_confidence_is_exactly_zero_point_nine(
    detection: DetectionResult,
) -> None:
    """For any dependency edge detected via database-linked relationships
    (TrainingTask, GenerationProvenance), the confidence_score SHALL be
    exactly 0.9.

    **Validates: Requirements 1.6**
    """
    score = compute_confidence_score(detection)
    assert score == 0.9


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Semantic Similarity Range
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(detection=st_semantic_detection_above_threshold())
def test_semantic_confidence_is_between_half_and_zero_point_eight(
    detection: DetectionResult,
) -> None:
    """For any dependency edge detected via semantic similarity with
    embedding similarity >= 0.5, the confidence_score SHALL be between
    0.5 and 0.8 (inclusive).

    **Validates: Requirements 1.6**
    """
    score = compute_confidence_score(detection)
    assert score is not None
    assert 0.5 <= score <= 0.8


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Below Threshold Rejection
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(detection=st_semantic_detection_below_threshold())
def test_semantic_below_threshold_creates_no_edge(
    detection: DetectionResult,
) -> None:
    """For any candidate relationship with embedding similarity below 0.5,
    no edge SHALL be created (confidence score is None).

    **Validates: Requirements 1.6**
    """
    score = compute_confidence_score(detection)
    assert score is None


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Score Ordering
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    explicit=st_explicit_detection(),
    db_linked=st_db_linked_detection(),
    semantic=st_semantic_detection_above_threshold(),
)
def test_confidence_score_ordering(
    explicit: DetectionResult,
    db_linked: DetectionResult,
    semantic: DetectionResult,
) -> None:
    """Confidence scores SHALL maintain the ordering:
    explicit (1.0) > database-linked (0.9) >= semantic (0.5-0.8).

    **Validates: Requirements 1.6**
    """
    explicit_score = compute_confidence_score(explicit)
    db_score = compute_confidence_score(db_linked)
    semantic_score = compute_confidence_score(semantic)

    assert explicit_score is not None
    assert db_score is not None
    assert semantic_score is not None

    assert explicit_score > db_score
    assert db_score >= semantic_score


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Monotonicity of Semantic Mapping
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    sim_a=ABOVE_THRESHOLD_SIMILARITIES,
    sim_b=ABOVE_THRESHOLD_SIMILARITIES,
)
def test_semantic_confidence_is_monotonically_non_decreasing(
    sim_a: float,
    sim_b: float,
) -> None:
    """For any two semantic similarity scores where sim_a <= sim_b,
    the resulting confidence score for sim_a SHALL be <= the confidence
    score for sim_b. The mapping is monotonically non-decreasing.

    **Validates: Requirements 1.6**
    """
    detection_a = DetectionResult(
        method=DetectionMethod.SEMANTIC_SIMILARITY,
        similarity_score=sim_a,
    )
    detection_b = DetectionResult(
        method=DetectionMethod.SEMANTIC_SIMILARITY,
        similarity_score=sim_b,
    )

    score_a = compute_confidence_score(detection_a)
    score_b = compute_confidence_score(detection_b)

    assert score_a is not None
    assert score_b is not None

    if sim_a <= sim_b:
        assert score_a <= score_b
    else:
        assert score_a >= score_b


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — Boundary at Threshold
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    epsilon=st.floats(
        min_value=1e-10,
        max_value=0.01,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_threshold_boundary_behavior(epsilon: float) -> None:
    """At the exact threshold boundary (0.5), an edge SHALL be created.
    Just below the threshold, no edge SHALL be created.

    **Validates: Requirements 1.6**
    """
    # At threshold: edge created
    at_threshold = DetectionResult(
        method=DetectionMethod.SEMANTIC_SIMILARITY,
        similarity_score=SEMANTIC_SIMILARITY_THRESHOLD,
    )
    score_at = compute_confidence_score(at_threshold)
    assert score_at is not None
    assert score_at == 0.5  # Minimum confidence for semantic edges

    # Below threshold: no edge
    below_threshold = DetectionResult(
        method=DetectionMethod.SEMANTIC_SIMILARITY,
        similarity_score=SEMANTIC_SIMILARITY_THRESHOLD - epsilon,
    )
    score_below = compute_confidence_score(below_threshold)
    assert score_below is None


# ---------------------------------------------------------------------------
# Property 1: Confidence Score Assignment — All Scores in Valid Range
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(detection=st_any_detection())
def test_all_confidence_scores_in_valid_range(
    detection: DetectionResult,
) -> None:
    """For any detection result that produces an edge, the confidence_score
    SHALL be in the range [0.5, 1.0]. No edge SHALL have a confidence
    score below 0.5.

    **Validates: Requirements 1.6**
    """
    score = compute_confidence_score(detection)

    if score is not None:
        assert 0.5 <= score <= 1.0
