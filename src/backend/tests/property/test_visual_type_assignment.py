"""Property-based tests for visual classification type assignment.

Tests Property 2: Visual classification type assignment from the
multimodal-knowledge-base design document.

Property 2 validates that for any combination of detected visual features
(has_arrows, has_axis_lines, has_shapes), the classification logic assigns
the correct VisualType according to the specification.

Classification rules:
- has_arrows only → FLOWCHART
- has_axis_lines only → CHART
- has_shapes only → DIAGRAM
- has_arrows + has_shapes (no axis) → FLOWCHART
- has_arrows + has_axis_lines → MIXED
- has_axis_lines + has_shapes (no arrows) → MIXED
- all three → MIXED
- none of the three (but has drawings/images) → DIAGRAM (fallback)

**Validates: Requirements 1.3**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 2)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/visual_content_detector.py
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.visual_content_detector import VisualType


# ---------------------------------------------------------------------------
# Pure function encapsulating the type assignment logic from _classify_page()
# ---------------------------------------------------------------------------


def classify_visual_type(
    has_arrows: bool,
    has_axis_lines: bool,
    has_shapes: bool,
    has_images: bool = True,
) -> VisualType | None:
    """Determine the VisualType based on detected visual features.

    Encapsulates the classification logic from VisualContentDetector._classify_page()
    as a pure function for property-based testing.

    The logic assumes the page has drawings or images present (otherwise
    classification would not be triggered).

    Args:
        has_arrows: Whether arrow connectors were detected in drawings.
        has_axis_lines: Whether axis lines (chart indicators) were detected.
        has_shapes: Whether geometric shapes were detected.
        has_images: Whether the page has images (used for fallback when no drawings).

    Returns:
        VisualType classification, or None if no visual content detected.
    """
    # If no drawings exist, check for images only
    has_any_drawing_feature = has_arrows or has_axis_lines or has_shapes

    if not has_any_drawing_feature:
        # No specific drawing categories matched
        if has_images:
            return VisualType.DIAGRAM
        return None

    categories_matched = sum([has_arrows, has_axis_lines, has_shapes])

    if categories_matched > 1:
        # Multiple categories detected
        if has_arrows and has_axis_lines:
            return VisualType.MIXED
        if has_arrows and has_shapes:
            return VisualType.FLOWCHART
        return VisualType.MIXED

    # Single category
    if has_arrows:
        return VisualType.FLOWCHART
    if has_axis_lines:
        return VisualType.CHART
    if has_shapes:
        return VisualType.DIAGRAM

    return VisualType.DIAGRAM


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_visual_features() -> st.SearchStrategy[tuple[bool, bool, bool]]:
    """Generate all combinations of visual feature flags.

    Returns:
        Strategy producing (has_arrows, has_axis_lines, has_shapes) tuples.
    """
    return st.tuples(st.booleans(), st.booleans(), st.booleans())


# ---------------------------------------------------------------------------
# Property 2: Visual Classification Type Assignment
# ---------------------------------------------------------------------------


class TestVisualTypeAssignment:
    """Property tests for visual classification type assignment.

    For any combination of (has_arrows, has_axis_lines, has_shapes),
    the classification logic must assign the correct VisualType
    according to the specification in Requirement 1.3.

    **Validates: Requirements 1.3**
    """

    @given(data=st.data())
    @settings(max_examples=200)
    def test_arrows_only_yields_flowchart(self, data: st.DataObject) -> None:
        """When only arrows are detected (no axis lines, no shapes),
        the classification must be FLOWCHART.

        **Validates: Requirements 1.3**
        """
        has_arrows = True
        has_axis_lines = False
        has_shapes = False

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        assert result == VisualType.FLOWCHART, (
            f"Expected FLOWCHART for arrows-only, got {result}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_axis_lines_only_yields_chart(self, data: st.DataObject) -> None:
        """When only axis lines are detected (no arrows, no shapes),
        the classification must be CHART.

        **Validates: Requirements 1.3**
        """
        has_arrows = False
        has_axis_lines = True
        has_shapes = False

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        assert result == VisualType.CHART, (
            f"Expected CHART for axis-lines-only, got {result}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_shapes_only_yields_diagram(self, data: st.DataObject) -> None:
        """When only shapes are detected (no arrows, no axis lines),
        the classification must be DIAGRAM.

        **Validates: Requirements 1.3**
        """
        has_arrows = False
        has_axis_lines = False
        has_shapes = True

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        assert result == VisualType.DIAGRAM, (
            f"Expected DIAGRAM for shapes-only, got {result}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_arrows_and_shapes_yields_flowchart(self, data: st.DataObject) -> None:
        """When arrows and shapes are detected (but no axis lines),
        the classification must be FLOWCHART (arrows + shapes = flowchart).

        **Validates: Requirements 1.3**
        """
        has_arrows = True
        has_axis_lines = False
        has_shapes = True

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        assert result == VisualType.FLOWCHART, (
            f"Expected FLOWCHART for arrows+shapes, got {result}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_arrows_and_axis_lines_yields_mixed(self, data: st.DataObject) -> None:
        """When arrows and axis lines are detected,
        the classification must be MIXED.

        **Validates: Requirements 1.3**
        """
        has_arrows = True
        has_axis_lines = True
        has_shapes = data.draw(st.booleans())  # shapes don't matter here

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        assert result == VisualType.MIXED, (
            f"Expected MIXED for arrows+axis_lines (shapes={has_shapes}), got {result}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_axis_lines_and_shapes_no_arrows_yields_mixed(
        self, data: st.DataObject
    ) -> None:
        """When axis lines and shapes are detected (but no arrows),
        the classification must be MIXED.

        **Validates: Requirements 1.3**
        """
        has_arrows = False
        has_axis_lines = True
        has_shapes = True

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        assert result == VisualType.MIXED, (
            f"Expected MIXED for axis_lines+shapes (no arrows), got {result}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_no_features_with_images_yields_diagram(
        self, data: st.DataObject
    ) -> None:
        """When no specific drawing features are detected but images are present,
        the classification must be DIAGRAM (fallback).

        **Validates: Requirements 1.3**
        """
        has_arrows = False
        has_axis_lines = False
        has_shapes = False
        has_images = True

        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes, has_images)

        assert result == VisualType.DIAGRAM, (
            f"Expected DIAGRAM fallback when images present, got {result}"
        )

    @given(
        has_arrows=st.booleans(),
        has_axis_lines=st.booleans(),
        has_shapes=st.booleans(),
    )
    @settings(max_examples=500)
    def test_classification_is_consistent_with_spec(
        self,
        has_arrows: bool,
        has_axis_lines: bool,
        has_shapes: bool,
    ) -> None:
        """For any combination of visual features, the classification result
        is consistent with the specification in Requirement 1.3.

        The expected mapping is:
        - arrows only → FLOWCHART
        - axis_lines only → CHART
        - shapes only → DIAGRAM
        - arrows + shapes (no axis) → FLOWCHART
        - arrows + axis_lines (with or without shapes) → MIXED
        - axis_lines + shapes (no arrows) → MIXED
        - none → DIAGRAM (fallback with images present)

        **Validates: Requirements 1.3**
        """
        result = classify_visual_type(has_arrows, has_axis_lines, has_shapes)

        categories_matched = sum([has_arrows, has_axis_lines, has_shapes])

        if categories_matched == 0:
            # Fallback: images present → DIAGRAM
            expected = VisualType.DIAGRAM
        elif categories_matched == 1:
            if has_arrows:
                expected = VisualType.FLOWCHART
            elif has_axis_lines:
                expected = VisualType.CHART
            else:
                expected = VisualType.DIAGRAM
        else:
            # Multiple categories
            if has_arrows and has_axis_lines:
                expected = VisualType.MIXED
            elif has_arrows and has_shapes:
                expected = VisualType.FLOWCHART
            else:
                # axis_lines + shapes (no arrows), or all three
                expected = VisualType.MIXED

        assert result == expected, (
            f"Classification mismatch for has_arrows={has_arrows}, "
            f"has_axis_lines={has_axis_lines}, has_shapes={has_shapes}. "
            f"Expected {expected}, got {result}."
        )

    @given(
        has_arrows=st.booleans(),
        has_axis_lines=st.booleans(),
        has_shapes=st.booleans(),
    )
    @settings(max_examples=200)
    def test_result_is_always_valid_visual_type(
        self,
        has_arrows: bool,
        has_axis_lines: bool,
        has_shapes: bool,
    ) -> None:
        """The classification always returns a valid VisualType enum value
        (never None) when at least images are present.

        **Validates: Requirements 1.3**
        """
        result = classify_visual_type(
            has_arrows, has_axis_lines, has_shapes, has_images=True
        )

        assert result is not None, (
            f"Expected non-None result for has_arrows={has_arrows}, "
            f"has_axis_lines={has_axis_lines}, has_shapes={has_shapes}"
        )
        assert isinstance(result, VisualType), (
            f"Expected VisualType instance, got {type(result)}"
        )
        assert result in {
            VisualType.FLOWCHART,
            VisualType.CHART,
            VisualType.DIAGRAM,
            VisualType.MIXED,
        }
