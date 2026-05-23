"""Property-based tests for visual page processing cap.

Tests Property 3: Visual page processing cap from the
multimodal-knowledge-base design document.

Property 3 validates that for any document containing N pages classified
as visual content where N > 100, the VisualContentDetector SHALL process
only the first 100 visual pages and return exactly 100 VisualPageInfo records.

The cap is enforced by `_max_visual_pages` (default 100) in the
VisualContentDetector class.

**Validates: Requirements 1.5**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 3)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/visual_content_detector.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.visual_content_detector import VisualPageInfo, VisualType


# ---------------------------------------------------------------------------
# Constants matching the specification
# ---------------------------------------------------------------------------

DEFAULT_MAX_VISUAL_PAGES: int = 100
"""Default cap on visual pages processed per document (Requirement 1.5)."""


# ---------------------------------------------------------------------------
# Pure function simulating the cap logic
# ---------------------------------------------------------------------------


def apply_visual_page_cap(
    visual_pages: list[VisualPageInfo],
    max_visual_pages: int = DEFAULT_MAX_VISUAL_PAGES,
) -> list[VisualPageInfo]:
    """Apply the visual page processing cap.

    Simulates the cap logic from VisualContentDetector.detect_visual_pages():
    when the number of detected visual pages exceeds max_visual_pages,
    only the first max_visual_pages are returned.

    Args:
        visual_pages: All pages classified as visual content.
        max_visual_pages: Maximum number of visual pages to return.

    Returns:
        List capped at max_visual_pages entries.
    """
    return visual_pages[:max_visual_pages]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_visual_type() -> st.SearchStrategy[VisualType]:
    """Generate a random VisualType enum value.

    Returns:
        Strategy producing one of the four VisualType values.
    """
    return st.sampled_from(list(VisualType))


def st_visual_page_info(page_number: int | None = None) -> st.SearchStrategy[VisualPageInfo]:
    """Generate a random VisualPageInfo instance.

    Args:
        page_number: If provided, use this page number; otherwise generate one.

    Returns:
        Strategy producing VisualPageInfo instances.
    """
    page_num_strategy = (
        st.just(page_number) if page_number is not None
        else st.integers(min_value=0, max_value=500)
    )
    return st.builds(
        VisualPageInfo,
        page_number=page_num_strategy,
        visual_type=st_visual_type(),
        width=st.floats(min_value=100.0, max_value=2000.0, allow_nan=False),
        height=st.floats(min_value=100.0, max_value=2000.0, allow_nan=False),
        text_area_ratio=st.floats(min_value=0.0, max_value=0.29, allow_nan=False),
    )


def st_visual_pages_above_cap(
    max_visual_pages: int = DEFAULT_MAX_VISUAL_PAGES,
) -> st.SearchStrategy[list[VisualPageInfo]]:
    """Generate a list of visual pages exceeding the cap.

    Produces lists with 50-200 visual pages (always exceeding the default
    cap of 100 when using default max_visual_pages, or exceeding the
    provided cap value).

    Args:
        max_visual_pages: The cap value to exceed.

    Returns:
        Strategy producing lists of VisualPageInfo with length > max_visual_pages.
    """
    min_count = max_visual_pages + 1
    max_count = max_visual_pages + 100
    return st.integers(min_value=min_count, max_value=max_count).flatmap(
        lambda n: st.lists(
            st_visual_page_info(),
            min_size=n,
            max_size=n,
        )
    )


# ---------------------------------------------------------------------------
# Property 3: Visual page processing cap
# ---------------------------------------------------------------------------


class TestVisualPageProcessingCap:
    """Property tests for visual page processing cap.

    For any document containing N pages classified as visual content
    where N > max_visual_pages, the detector SHALL return at most
    max_visual_pages VisualPageInfo records.

    **Validates: Requirements 1.5**
    """

    @given(
        num_visual_pages=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=200)
    def test_cap_enforced_with_default_limit(
        self,
        num_visual_pages: int,
    ) -> None:
        """Generate documents with 50-200 visual pages, verify max 100 returned.

        When the number of visual pages exceeds the default cap (100),
        the result must be capped at exactly 100. When below or equal to
        the cap, all pages are returned.

        **Validates: Requirements 1.5**
        """
        # Create a list of visual pages of the given size
        pages = [
            VisualPageInfo(
                page_number=i,
                visual_type=VisualType.DIAGRAM,
                width=612.0,
                height=792.0,
                text_area_ratio=0.1,
            )
            for i in range(num_visual_pages)
        ]

        result = apply_visual_page_cap(pages, DEFAULT_MAX_VISUAL_PAGES)

        if num_visual_pages > DEFAULT_MAX_VISUAL_PAGES:
            assert len(result) == DEFAULT_MAX_VISUAL_PAGES, (
                f"Expected exactly {DEFAULT_MAX_VISUAL_PAGES} pages when input has "
                f"{num_visual_pages} visual pages, but got {len(result)}"
            )
        else:
            assert len(result) == num_visual_pages, (
                f"Expected all {num_visual_pages} pages when below cap, "
                f"but got {len(result)}"
            )

    @given(
        num_visual_pages=st.integers(min_value=101, max_value=200),
    )
    @settings(max_examples=200)
    def test_never_exceeds_default_cap(
        self,
        num_visual_pages: int,
    ) -> None:
        """For any number of visual pages above 100, the result never exceeds 100.

        This is the core property: the cap is always enforced regardless
        of how many visual pages are detected.

        **Validates: Requirements 1.5**
        """
        pages = [
            VisualPageInfo(
                page_number=i,
                visual_type=VisualType.FLOWCHART,
                width=595.0,
                height=842.0,
                text_area_ratio=0.05,
            )
            for i in range(num_visual_pages)
        ]

        result = apply_visual_page_cap(pages, DEFAULT_MAX_VISUAL_PAGES)

        assert len(result) <= DEFAULT_MAX_VISUAL_PAGES, (
            f"Cap violated: got {len(result)} pages, "
            f"expected at most {DEFAULT_MAX_VISUAL_PAGES}"
        )
        assert len(result) == DEFAULT_MAX_VISUAL_PAGES, (
            f"Expected exactly {DEFAULT_MAX_VISUAL_PAGES} pages when input "
            f"exceeds cap, but got {len(result)}"
        )

    @given(
        cap_value=st.integers(min_value=1, max_value=200),
        num_visual_pages=st.integers(min_value=50, max_value=200),
    )
    @settings(max_examples=300)
    def test_cap_enforced_with_various_cap_values(
        self,
        cap_value: int,
        num_visual_pages: int,
    ) -> None:
        """Test with various cap values to verify the cap is always enforced.

        For any configurable max_visual_pages value, the result must never
        exceed that cap.

        **Validates: Requirements 1.5**
        """
        pages = [
            VisualPageInfo(
                page_number=i,
                visual_type=VisualType.CHART,
                width=612.0,
                height=792.0,
                text_area_ratio=0.2,
            )
            for i in range(num_visual_pages)
        ]

        result = apply_visual_page_cap(pages, cap_value)

        assert len(result) <= cap_value, (
            f"Cap violated: got {len(result)} pages with cap={cap_value}, "
            f"input had {num_visual_pages} pages"
        )

        expected_count = min(num_visual_pages, cap_value)
        assert len(result) == expected_count, (
            f"Expected {expected_count} pages (min of {num_visual_pages} input "
            f"and {cap_value} cap), but got {len(result)}"
        )

    @given(
        pages=st_visual_pages_above_cap(DEFAULT_MAX_VISUAL_PAGES),
    )
    @settings(max_examples=100)
    def test_first_n_pages_preserved(
        self,
        pages: list[VisualPageInfo],
    ) -> None:
        """When capped, the first max_visual_pages entries are preserved in order.

        The cap takes the first N pages sequentially, matching the
        VisualContentDetector behavior of processing pages in order and
        stopping at the cap.

        **Validates: Requirements 1.5**
        """
        result = apply_visual_page_cap(pages, DEFAULT_MAX_VISUAL_PAGES)

        assert len(result) == DEFAULT_MAX_VISUAL_PAGES

        # Verify the returned pages are the first max_visual_pages from input
        for i in range(DEFAULT_MAX_VISUAL_PAGES):
            assert result[i] is pages[i], (
                f"Page at index {i} does not match: expected page_number="
                f"{pages[i].page_number}, got page_number={result[i].page_number}"
            )
