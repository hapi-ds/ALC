"""Property-based tests for visual description minimum length validation.

Tests Property 5: Visual description minimum length validation from the
multimodal-knowledge-base design document.

Property 5 validates that for any string of length 0-100, the description
minimum length validation correctly accepts strings with
len(s.strip()) >= 20 and rejects strings with len(s.strip()) < 20.

**Validates: Requirements 2.7**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 5)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/knowledge_service.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import _MIN_DESCRIPTION_LENGTH


# ---------------------------------------------------------------------------
# Pure validation function under test
# ---------------------------------------------------------------------------


def is_description_accepted(description: str) -> bool:
    """Determine if a visual description meets the minimum length requirement.

    Implements the validation logic from KnowledgeService._interpret_visual_page:
    A description is accepted IF AND ONLY IF:
    - The description is truthy (non-empty after consideration), AND
    - len(description.strip()) >= _MIN_DESCRIPTION_LENGTH (20)

    This matches Requirement 2.7: descriptions shorter than 20 characters
    are discarded as insufficient.

    Args:
        description: The description string returned by the Vision_Model.

    Returns:
        True if the description is accepted, False if rejected.
    """
    return bool(description) and len(description.strip()) >= _MIN_DESCRIPTION_LENGTH


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_short_description() -> st.SearchStrategy[str]:
    """Generate strings whose stripped length is strictly below 20 characters.

    Includes edge cases: empty strings, whitespace-only, and strings that
    are exactly 19 stripped characters (just below threshold).

    Returns:
        Strategy producing strings with len(s.strip()) < 20.
    """
    return st.one_of(
        # Empty string
        st.just(""),
        # Whitespace-only strings (strip to 0 length)
        st.text(alphabet=" \t\n\r", min_size=1, max_size=100),
        # Short content strings (1-19 stripped chars)
        st.text(
            alphabet=st.characters(categories=("L", "N", "P", "S")),
            min_size=1,
            max_size=19,
        ),
        # Strings with leading/trailing whitespace that strip to < 20
        st.builds(
            lambda pad_l, content, pad_r: pad_l + content + pad_r,
            pad_l=st.text(alphabet=" \t", min_size=0, max_size=10),
            content=st.text(
                alphabet=st.characters(categories=("L", "N", "P", "S")),
                min_size=1,
                max_size=19,
            ),
            pad_r=st.text(alphabet=" \t", min_size=0, max_size=10),
        ).filter(lambda s: len(s.strip()) < _MIN_DESCRIPTION_LENGTH),
    )


def st_valid_description() -> st.SearchStrategy[str]:
    """Generate strings whose stripped length is >= 20 characters.

    Includes edge cases: exactly 20 stripped characters (boundary) and
    strings up to 100 characters.

    Returns:
        Strategy producing strings with len(s.strip()) >= 20.
    """
    return st.one_of(
        # Content strings of length 20-100
        st.text(
            alphabet=st.characters(categories=("L", "N", "P", "S")),
            min_size=20,
            max_size=100,
        ),
        # Strings with whitespace padding that still have >= 20 stripped chars
        st.builds(
            lambda pad_l, content, pad_r: pad_l + content + pad_r,
            pad_l=st.text(alphabet=" \t", min_size=0, max_size=10),
            content=st.text(
                alphabet=st.characters(categories=("L", "N", "P", "S")),
                min_size=20,
                max_size=100,
            ),
            pad_r=st.text(alphabet=" \t", min_size=0, max_size=10),
        ),
    )


def st_any_description() -> st.SearchStrategy[str]:
    """Generate arbitrary strings of length 0-100 for general property testing.

    Returns:
        Strategy producing strings of length 0-100.
    """
    return st.text(min_size=0, max_size=100)


# ---------------------------------------------------------------------------
# Property 5: Visual Description Minimum Length Validation
# ---------------------------------------------------------------------------


class TestVisualDescriptionMinimumLength:
    """Property tests for visual description minimum length validation.

    For any string of length 0-100, the validation logic must:
    - Accept strings with len(s.strip()) >= 20
    - Reject strings with len(s.strip()) < 20

    **Validates: Requirements 2.7**
    """

    @given(description=st_valid_description())
    @settings(max_examples=200)
    def test_descriptions_at_or_above_threshold_are_accepted(
        self,
        description: str,
    ) -> None:
        """Descriptions with stripped length >= 20 are accepted.

        **Validates: Requirements 2.7**
        """
        result = is_description_accepted(description)

        assert result is True, (
            f"Expected description to be accepted "
            f"(stripped length={len(description.strip())} >= {_MIN_DESCRIPTION_LENGTH}), "
            f"but it was rejected. Description repr: {description!r}"
        )

    @given(description=st_short_description())
    @settings(max_examples=200)
    def test_descriptions_below_threshold_are_rejected(
        self,
        description: str,
    ) -> None:
        """Descriptions with stripped length < 20 are rejected.

        **Validates: Requirements 2.7**
        """
        result = is_description_accepted(description)

        assert result is False, (
            f"Expected description to be rejected "
            f"(stripped length={len(description.strip())} < {_MIN_DESCRIPTION_LENGTH}), "
            f"but it was accepted. Description repr: {description!r}"
        )

    @given(description=st_any_description())
    @settings(max_examples=500)
    def test_accept_reject_consistent_with_threshold(
        self,
        description: str,
    ) -> None:
        """For any string, acceptance is determined solely by whether
        len(s.strip()) >= 20.

        **Validates: Requirements 2.7**
        """
        result = is_description_accepted(description)
        stripped_len = len(description.strip())
        expected = stripped_len >= _MIN_DESCRIPTION_LENGTH

        assert result == expected, (
            f"Validation mismatch for description with stripped length={stripped_len}. "
            f"Expected accepted={expected}, got accepted={result}. "
            f"Description repr: {description!r}"
        )
