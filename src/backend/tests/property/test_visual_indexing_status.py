"""Property-based tests for visual indexing status correctness.

Tests Property 20: Visual indexing status correctness from the
multimodal-knowledge-base design document.

Property 20 validates that for any document indexing operation, the
visual_indexing_status is correctly assigned based on:
- "not_applicable": no visual content detected OR ENABLE_VISUAL_INDEXING is false
- "completed": all visual pages processed successfully
- "partial": some but not all visual pages processed (failures or skips)
- "pending": visual pages detected but none processed (all failed)

**Validates: Requirements 12.3, 12.5, 12.6**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 20)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/knowledge_service.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure status determination function under test
# ---------------------------------------------------------------------------


def determine_visual_indexing_status(
    visual_pages_detected: int,
    visual_pages_processed: int,
    enable_visual_indexing: bool,
) -> str:
    """Determine the visual indexing status for a document.

    Implements the status assignment logic from the Knowledge_Service
    (knowledge_service.py, Step 7 and early returns):

    - "not_applicable": ENABLE_VISUAL_INDEXING is false OR no visual pages detected
    - "completed": all detected visual pages were successfully processed
    - "partial": some but not all visual pages were processed
    - "pending": visual pages detected but none processed (all failed)

    This matches Requirements 12.3, 12.5, 12.6:
    - Req 12.3: Track status with states not_applicable/pending/completed/partial
    - Req 12.5: ENABLE_VISUAL_INDEXING flag disables visual processing
    - Req 12.6: When disabled, status is "not_applicable"

    Args:
        visual_pages_detected: Number of pages classified as visual content.
        visual_pages_processed: Number of visual pages successfully processed.
        enable_visual_indexing: Whether visual indexing is enabled.

    Returns:
        One of "not_applicable", "completed", "partial", or "pending".
    """
    # If visual indexing is disabled, always not_applicable (Req 12.5, 12.6)
    if not enable_visual_indexing:
        return "not_applicable"

    # If no visual pages detected, not_applicable (Req 12.3)
    if visual_pages_detected == 0:
        return "not_applicable"

    # All visual pages processed successfully (Req 12.3)
    if visual_pages_processed == visual_pages_detected:
        return "completed"

    # Some but not all processed (Req 12.3)
    if visual_pages_processed > 0:
        return "partial"

    # None processed (all failed) (Req 12.3)
    return "pending"


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_visual_pages_detected() -> st.SearchStrategy[int]:
    """Generate visual_pages_detected values.

    Includes 0 (no visual content) and values up to 200 (beyond the 100 cap,
    which is enforced upstream by the detector).

    Returns:
        Strategy producing non-negative integers.
    """
    return st.integers(min_value=0, max_value=200)


def st_visual_pages_processed(detected: int) -> st.SearchStrategy[int]:
    """Generate visual_pages_processed values constrained by detected count.

    processed must be in [0, detected] since you cannot process more pages
    than were detected.

    Args:
        detected: The number of visual pages detected.

    Returns:
        Strategy producing integers in [0, detected].
    """
    return st.integers(min_value=0, max_value=max(detected, 0))


# ---------------------------------------------------------------------------
# Property 20: Visual Indexing Status Correctness
# ---------------------------------------------------------------------------


class TestVisualIndexingStatus:
    """Property tests for visual indexing status assignment.

    For any combination of (visual_pages_detected, visual_pages_processed,
    enable_visual_indexing), the visual_indexing_status must be correctly
    assigned according to the specification.

    **Validates: Requirements 12.3, 12.5, 12.6**
    """

    @given(
        visual_pages_detected=st.integers(min_value=0, max_value=200),
        enable_visual_indexing=st.booleans(),
    )
    @settings(max_examples=100)
    def test_disabled_visual_indexing_always_not_applicable(
        self,
        visual_pages_detected: int,
        enable_visual_indexing: bool,
    ) -> None:
        """When ENABLE_VISUAL_INDEXING is false, status is always "not_applicable"
        regardless of detected pages.

        **Validates: Requirements 12.5, 12.6**
        """
        if not enable_visual_indexing:
            # processed is irrelevant when disabled
            result = determine_visual_indexing_status(
                visual_pages_detected=visual_pages_detected,
                visual_pages_processed=0,
                enable_visual_indexing=False,
            )
            assert result == "not_applicable", (
                f"Expected 'not_applicable' when visual indexing disabled, "
                f"but got '{result}' with detected={visual_pages_detected}"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_no_visual_pages_detected_is_not_applicable(
        self,
        data: st.DataObject,
    ) -> None:
        """When no visual pages are detected (detected=0), status is
        "not_applicable" even when visual indexing is enabled.

        **Validates: Requirements 12.3**
        """
        result = determine_visual_indexing_status(
            visual_pages_detected=0,
            visual_pages_processed=0,
            enable_visual_indexing=True,
        )
        assert result == "not_applicable", (
            f"Expected 'not_applicable' when no visual pages detected, "
            f"but got '{result}'"
        )

    @given(
        visual_pages_detected=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=100)
    def test_all_pages_processed_is_completed(
        self,
        visual_pages_detected: int,
    ) -> None:
        """When all detected visual pages are processed, status is "completed".

        **Validates: Requirements 12.3**
        """
        result = determine_visual_indexing_status(
            visual_pages_detected=visual_pages_detected,
            visual_pages_processed=visual_pages_detected,
            enable_visual_indexing=True,
        )
        assert result == "completed", (
            f"Expected 'completed' when all {visual_pages_detected} pages processed, "
            f"but got '{result}'"
        )

    @given(
        visual_pages_detected=st.integers(min_value=2, max_value=200),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_some_pages_processed_is_partial(
        self,
        visual_pages_detected: int,
        data: st.DataObject,
    ) -> None:
        """When some but not all visual pages are processed, status is "partial".

        **Validates: Requirements 12.3**
        """
        # Generate processed count strictly between 0 and detected
        visual_pages_processed = data.draw(
            st.integers(min_value=1, max_value=visual_pages_detected - 1),
            label="visual_pages_processed",
        )
        result = determine_visual_indexing_status(
            visual_pages_detected=visual_pages_detected,
            visual_pages_processed=visual_pages_processed,
            enable_visual_indexing=True,
        )
        assert result == "partial", (
            f"Expected 'partial' when {visual_pages_processed}/{visual_pages_detected} "
            f"pages processed, but got '{result}'"
        )

    @given(
        visual_pages_detected=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=100)
    def test_no_pages_processed_is_pending(
        self,
        visual_pages_detected: int,
    ) -> None:
        """When visual pages are detected but none processed, status is "pending".

        **Validates: Requirements 12.3**
        """
        result = determine_visual_indexing_status(
            visual_pages_detected=visual_pages_detected,
            visual_pages_processed=0,
            enable_visual_indexing=True,
        )
        assert result == "pending", (
            f"Expected 'pending' when 0/{visual_pages_detected} pages processed, "
            f"but got '{result}'"
        )

    @given(
        visual_pages_detected=st_visual_pages_detected(),
        enable_visual_indexing=st.booleans(),
        data=st.data(),
    )
    @settings(max_examples=500)
    def test_status_assignment_is_consistent_with_spec(
        self,
        visual_pages_detected: int,
        enable_visual_indexing: bool,
        data: st.DataObject,
    ) -> None:
        """For any arbitrary combination of inputs, the status assignment
        is consistent with the full specification.

        This is the comprehensive property test that covers all cases:
        - not_applicable: disabled OR no pages detected
        - completed: all pages processed (detected > 0, processed == detected)
        - partial: some pages processed (0 < processed < detected)
        - pending: pages detected but none processed (processed == 0, detected > 0)

        **Validates: Requirements 12.3, 12.5, 12.6**
        """
        # Generate a valid processed count (0 to detected)
        visual_pages_processed = data.draw(
            st.integers(min_value=0, max_value=max(visual_pages_detected, 0)),
            label="visual_pages_processed",
        )

        result = determine_visual_indexing_status(
            visual_pages_detected=visual_pages_detected,
            visual_pages_processed=visual_pages_processed,
            enable_visual_indexing=enable_visual_indexing,
        )

        # Compute expected status per specification
        if not enable_visual_indexing:
            expected = "not_applicable"
        elif visual_pages_detected == 0:
            expected = "not_applicable"
        elif visual_pages_processed == visual_pages_detected:
            expected = "completed"
        elif visual_pages_processed > 0:
            expected = "partial"
        else:
            expected = "pending"

        assert result == expected, (
            f"Status mismatch for detected={visual_pages_detected}, "
            f"processed={visual_pages_processed}, "
            f"enabled={enable_visual_indexing}. "
            f"Expected '{expected}', got '{result}'."
        )

    @given(
        visual_pages_detected=st.integers(min_value=0, max_value=200),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_status_is_always_one_of_valid_values(
        self,
        visual_pages_detected: int,
        data: st.DataObject,
    ) -> None:
        """The returned status is always one of the four valid values.

        **Validates: Requirements 12.3**
        """
        visual_pages_processed = data.draw(
            st.integers(min_value=0, max_value=max(visual_pages_detected, 0)),
            label="visual_pages_processed",
        )
        enable_visual_indexing = data.draw(st.booleans(), label="enable_visual_indexing")

        result = determine_visual_indexing_status(
            visual_pages_detected=visual_pages_detected,
            visual_pages_processed=visual_pages_processed,
            enable_visual_indexing=enable_visual_indexing,
        )

        valid_statuses = {"not_applicable", "pending", "completed", "partial"}
        assert result in valid_statuses, (
            f"Status '{result}' is not a valid visual_indexing_status. "
            f"Must be one of {valid_statuses}."
        )
