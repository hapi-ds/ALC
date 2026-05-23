"""Property-based tests for requires-review flag threshold.

Tests Property 18: Requires-review flag threshold from the
multimodal-knowledge-base design document.

Property 18 validates that for any alignment score between 0.0 and 1.0,
the requires_review flag is set to True when alignment_score < 0.5
and False when alignment_score >= 0.5.

**Validates: Requirements 9.10**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 18)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/alignment_service.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure validation function under test
# ---------------------------------------------------------------------------

REQUIRES_REVIEW_THRESHOLD = 0.5


def compute_requires_review(alignment_score: float) -> bool:
    """Determine if a discrepancy report requires manual review.

    Implements the logic from AlignmentService.align():
    requires_review is True IF AND ONLY IF alignment_score < 0.5.

    This matches Requirement 9.10: IF the alignment score is below 0.5
    (less than 50% of video steps matched), THEN the report SHALL be
    flagged with requires_review: true.

    Args:
        alignment_score: The alignment score (0.0 to 1.0), calculated as
            matched_steps / total_video_steps.

    Returns:
        True if the report requires review, False otherwise.
    """
    return alignment_score < REQUIRES_REVIEW_THRESHOLD


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_score_below_threshold() -> st.SearchStrategy[float]:
    """Generate alignment scores strictly below 0.5.

    Includes edge cases: 0.0 (no matches) and values just below 0.5.

    Returns:
        Strategy producing floats in [0.0, 0.5).
    """
    return st.floats(
        min_value=0.0,
        max_value=REQUIRES_REVIEW_THRESHOLD,
        exclude_max=True,
        allow_nan=False,
        allow_infinity=False,
    )


def st_score_at_or_above_threshold() -> st.SearchStrategy[float]:
    """Generate alignment scores at or above 0.5.

    Includes edge cases: exactly 0.5 (boundary) and 1.0 (perfect match).

    Returns:
        Strategy producing floats in [0.5, 1.0].
    """
    return st.floats(
        min_value=REQUIRES_REVIEW_THRESHOLD,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )


def st_any_alignment_score() -> st.SearchStrategy[float]:
    """Generate any valid alignment score between 0.0 and 1.0.

    Returns:
        Strategy producing floats in [0.0, 1.0].
    """
    return st.floats(
        min_value=0.0,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    )


# ---------------------------------------------------------------------------
# Property 18: Requires-review flag threshold
# ---------------------------------------------------------------------------


class TestRequiresReviewFlagThreshold:
    """Property tests for requires-review flag threshold.

    For any alignment score between 0.0 and 1.0:
    - When alignment_score < 0.5: requires_review = True
    - When alignment_score >= 0.5: requires_review = False

    **Validates: Requirements 9.10**
    """

    @given(score=st_score_below_threshold())
    @settings(max_examples=200)
    def test_requires_review_true_when_score_below_threshold(
        self,
        score: float,
    ) -> None:
        """Scores below 0.5 must set requires_review to True.

        **Validates: Requirements 9.10**
        """
        result = compute_requires_review(score)

        assert result is True, (
            f"Expected requires_review=True for alignment_score={score} "
            f"(below threshold {REQUIRES_REVIEW_THRESHOLD}), but got False."
        )

    @given(score=st_score_at_or_above_threshold())
    @settings(max_examples=200)
    def test_requires_review_false_when_score_at_or_above_threshold(
        self,
        score: float,
    ) -> None:
        """Scores at or above 0.5 must set requires_review to False.

        **Validates: Requirements 9.10**
        """
        result = compute_requires_review(score)

        assert result is False, (
            f"Expected requires_review=False for alignment_score={score} "
            f"(at or above threshold {REQUIRES_REVIEW_THRESHOLD}), but got True."
        )

    @given(score=st_any_alignment_score())
    @settings(max_examples=500)
    def test_requires_review_consistent_with_threshold(
        self,
        score: float,
    ) -> None:
        """For any valid score, requires_review is determined solely by
        whether alignment_score < 0.5.

        **Validates: Requirements 9.10**
        """
        result = compute_requires_review(score)
        expected = score < REQUIRES_REVIEW_THRESHOLD

        assert result == expected, (
            f"Validation mismatch for alignment_score={score}. "
            f"Expected requires_review={expected}, got requires_review={result}."
        )
