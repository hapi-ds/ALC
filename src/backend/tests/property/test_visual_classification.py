"""Property-based tests for visual content classification.

Tests Property 1: Visual content classification correctness from the
multimodal-knowledge-base design document.

Property 1 validates that for any (text_area_ratio, has_images) pair,
the visual content classification logic correctly identifies visual pages
if and only if text_area_ratio < 0.3 AND has_images is True.

**Validates: Requirements 1.1, 1.2, 1.7**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 1)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/visual_content_detector.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Constants matching the specification and implementation
# ---------------------------------------------------------------------------

TEXT_AREA_THRESHOLD: float = 0.3
"""Pages with text_area_ratio below this are candidates for visual content."""


# ---------------------------------------------------------------------------
# Pure classification decision function under test
# ---------------------------------------------------------------------------


def is_visual_content(text_area_ratio: float, has_images: bool) -> bool:
    """Determine if a page should be classified as visual content.

    Implements the classification decision logic from the VisualContentDetector:
    A page is classified as visual content IF AND ONLY IF:
    - text_area_ratio < TEXT_AREA_THRESHOLD (0.3), AND
    - has_images is True (page contains at least one image or drawing object)

    This matches Requirements 1.1, 1.2, and 1.7:
    - Req 1.2: Classify as visual when ratio < 0.3 AND has image/drawing objects.
    - Req 1.7: Do NOT classify when ratio < 0.3 but no image/drawing objects.

    Args:
        text_area_ratio: Ratio of text area to total page area (0.0-1.0).
        has_images: Whether the page contains image or drawing objects.

    Returns:
        True if the page should be classified as visual content, False otherwise.
    """
    return text_area_ratio < TEXT_AREA_THRESHOLD and has_images


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_text_area_ratio() -> st.SearchStrategy[float]:
    """Generate text_area_ratio values in the valid range [0.0, 1.0].

    Includes edge cases around the threshold boundary (0.3).

    Returns:
        Strategy producing float values between 0.0 and 1.0.
    """
    return st.one_of(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        # Edge cases near the threshold
        st.just(0.0),
        st.just(0.29),
        st.just(0.2999999),
        st.just(0.3),
        st.just(0.30000001),
        st.just(0.31),
        st.just(1.0),
    )


def st_below_threshold_ratio() -> st.SearchStrategy[float]:
    """Generate text_area_ratio values strictly below the threshold (< 0.3).

    Returns:
        Strategy producing float values in [0.0, 0.3).
    """
    return st.one_of(
        st.floats(
            min_value=0.0,
            max_value=0.2999999999,
            allow_nan=False,
            allow_infinity=False,
        ),
        st.just(0.0),
        st.just(0.1),
        st.just(0.29),
        st.just(0.2999999),
    )


def st_at_or_above_threshold_ratio() -> st.SearchStrategy[float]:
    """Generate text_area_ratio values at or above the threshold (>= 0.3).

    Returns:
        Strategy producing float values in [0.3, 1.0].
    """
    return st.one_of(
        st.floats(
            min_value=0.3,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        st.just(0.3),
        st.just(0.30000001),
        st.just(0.5),
        st.just(1.0),
    )


# ---------------------------------------------------------------------------
# Property 1: Visual Content Classification Correctness
# ---------------------------------------------------------------------------


class TestVisualContentClassification:
    """Property tests for visual content classification.

    For any (text_area_ratio, has_images) pair, the classification logic must:
    - Classify as visual IF AND ONLY IF text_area_ratio < 0.3 AND has_images is True
    - NOT classify when ratio < 0.3 but has_images is False (Req 1.7)
    - NOT classify when ratio >= 0.3 regardless of has_images

    **Validates: Requirements 1.1, 1.2, 1.7**
    """

    @given(
        text_area_ratio=st_below_threshold_ratio(),
    )
    @settings(max_examples=200)
    def test_low_ratio_with_images_is_classified_as_visual(
        self,
        text_area_ratio: float,
    ) -> None:
        """Pages with text_area_ratio < 0.3 AND has_images=True are classified
        as visual content.

        **Validates: Requirements 1.1, 1.2**
        """
        result = is_visual_content(text_area_ratio, has_images=True)

        assert result is True, (
            f"Expected visual classification for text_area_ratio={text_area_ratio}, "
            f"has_images=True, but got False"
        )

    @given(
        text_area_ratio=st_below_threshold_ratio(),
    )
    @settings(max_examples=200)
    def test_low_ratio_without_images_is_not_classified(
        self,
        text_area_ratio: float,
    ) -> None:
        """Pages with text_area_ratio < 0.3 but has_images=False are NOT
        classified as visual content.

        This validates Requirement 1.7: pages with low text ratio but no
        image/drawing objects should be skipped.

        **Validates: Requirements 1.7**
        """
        result = is_visual_content(text_area_ratio, has_images=False)

        assert result is False, (
            f"Expected NO visual classification for text_area_ratio={text_area_ratio}, "
            f"has_images=False, but got True"
        )

    @given(
        text_area_ratio=st_at_or_above_threshold_ratio(),
        has_images=st.booleans(),
    )
    @settings(max_examples=200)
    def test_high_ratio_is_never_classified(
        self,
        text_area_ratio: float,
        has_images: bool,
    ) -> None:
        """Pages with text_area_ratio >= 0.3 are NEVER classified as visual
        content, regardless of whether they contain images.

        **Validates: Requirements 1.1, 1.2**
        """
        result = is_visual_content(text_area_ratio, has_images)

        assert result is False, (
            f"Expected NO visual classification for text_area_ratio={text_area_ratio}, "
            f"has_images={has_images}, but got True"
        )

    @given(
        text_area_ratio=st_text_area_ratio(),
        has_images=st.booleans(),
    )
    @settings(max_examples=500)
    def test_classification_is_consistent_with_spec(
        self,
        text_area_ratio: float,
        has_images: bool,
    ) -> None:
        """For any arbitrary (text_area_ratio, has_images) pair, the classification
        result is consistent with the specification:
        - Classify as visual iff text_area_ratio < 0.3 AND has_images is True
        - Do not classify otherwise

        **Validates: Requirements 1.1, 1.2, 1.7**
        """
        result = is_visual_content(text_area_ratio, has_images)

        expected = text_area_ratio < TEXT_AREA_THRESHOLD and has_images

        assert result == expected, (
            f"Classification mismatch for text_area_ratio={text_area_ratio}, "
            f"has_images={has_images}. "
            f"Expected is_visual={expected}, got is_visual={result}."
        )
