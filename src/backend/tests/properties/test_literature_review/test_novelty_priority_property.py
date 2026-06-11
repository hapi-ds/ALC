"""Property-based tests for novelty flag creation and priority classification.

Property 12: Novelty flag creation and priority classification

For any relevance_score in the range [0.0, 1.0], the classify_priority function
SHALL return True if and only if relevance_score >= 0.8, and False otherwise.

Additionally, a NoveltyFlag SHALL be created when zero internal documents are
found with similarity >= threshold during cross-reference analysis.

**Validates: Requirements 5.7, 7.1, 7.3**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.review.services.contradiction_detection_service import (
    classify_priority,
)


# ---------------------------------------------------------------------------
# Property 12: relevance_score >= 0.8 → high_priority is True
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    relevance_score=st.floats(
        min_value=0.8, max_value=1.0, allow_nan=False, allow_infinity=False
    )
)
def test_high_priority_when_score_at_or_above_threshold(
    relevance_score: float,
) -> None:
    """classify_priority SHALL return True when relevance_score >= 0.8.

    **Validates: Requirements 5.7, 7.1, 7.3**
    """
    result = classify_priority(relevance_score)
    assert result is True, (
        f"Expected high_priority=True for relevance_score={relevance_score}, "
        f"got {result}"
    )


# ---------------------------------------------------------------------------
# Property 12: relevance_score < 0.8 → high_priority is False
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    relevance_score=st.floats(
        min_value=0.0,
        max_value=0.7999999999,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_not_high_priority_when_score_below_threshold(
    relevance_score: float,
) -> None:
    """classify_priority SHALL return False when relevance_score < 0.8.

    **Validates: Requirements 5.7, 7.1, 7.3**
    """
    result = classify_priority(relevance_score)
    assert result is False, (
        f"Expected high_priority=False for relevance_score={relevance_score}, "
        f"got {result}"
    )


# ---------------------------------------------------------------------------
# Property 12: Boundary test — exactly 0.8 is high priority
# ---------------------------------------------------------------------------


def test_boundary_exactly_0_8_is_high_priority() -> None:
    """classify_priority SHALL return True for relevance_score exactly 0.8.

    **Validates: Requirements 5.7, 7.1, 7.3**
    """
    result = classify_priority(0.8)
    assert result is True, (
        "Expected high_priority=True for relevance_score=0.8 (boundary)"
    )


# ---------------------------------------------------------------------------
# Property 12: Biconditional — high_priority ↔ relevance_score >= 0.8
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(
    relevance_score=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    )
)
def test_biconditional_priority_classification(
    relevance_score: float,
) -> None:
    """classify_priority result SHALL be True iff relevance_score >= 0.8.

    This is the biconditional form: for any score in [0.0, 1.0],
    high_priority == (relevance_score >= 0.8).

    **Validates: Requirements 5.7, 7.1, 7.3**
    """
    result = classify_priority(relevance_score)
    expected = relevance_score >= 0.8
    assert result == expected, (
        f"classify_priority({relevance_score}) returned {result}, "
        f"expected {expected}"
    )
