"""Property-based tests for Content-Type Disposition Classification.

Tests Property 2 from the document-content-viewer design document, validating that
`is_previewable()` correctly classifies MIME type strings as inline (previewable)
vs. attachment (non-previewable).

**Validates: Requirements 2.4**

References:
    - Design: .kiro/specs/document-content-viewer/design.md (Correctness Property 2)
    - Requirements: .kiro/specs/document-content-viewer/requirements.md (Requirement 2.4)
"""

import hypothesis.strategies as st
from hypothesis import assume, given, settings

from alcoabase.services.content_type_utils import PREVIEWABLE_TYPES, is_previewable


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_previewable_type(draw: st.DrawFn) -> str:
    """Generate a MIME type from the PREVIEWABLE_TYPES set.

    Returns:
        A string that is a member of PREVIEWABLE_TYPES.
    """
    return draw(st.sampled_from(sorted(PREVIEWABLE_TYPES)))


@st.composite
def st_random_mime_type(draw: st.DrawFn) -> str:
    """Generate a random MIME type string in the format 'type/subtype'.

    Generates realistic MIME type structures with a primary type and subtype
    separated by a forward slash.

    Returns:
        A random MIME type string.
    """
    primary_types = [
        "application",
        "audio",
        "font",
        "image",
        "message",
        "model",
        "multipart",
        "text",
        "video",
    ]
    primary = draw(st.sampled_from(primary_types))

    # Generate a random subtype with alphanumeric chars, dots, dashes, and plus signs
    subtype = draw(
        st.text(
            alphabet=st.sampled_from(
                list("abcdefghijklmnopqrstuvwxyz0123456789.-+")
            ),
            min_size=1,
            max_size=50,
        )
    )

    return f"{primary}/{subtype}"


@st.composite
def st_non_previewable_mime_type(draw: st.DrawFn) -> str:
    """Generate a random MIME type that is NOT in PREVIEWABLE_TYPES.

    Returns:
        A MIME type string guaranteed not to be in PREVIEWABLE_TYPES.
    """
    mime_type = draw(st_random_mime_type())
    assume(mime_type not in PREVIEWABLE_TYPES)
    return mime_type


# ---------------------------------------------------------------------------
# Property 2: Content-Type Disposition Classification
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 2: Content-Type Disposition Classification
@settings(max_examples=200)
@given(content_type=st_previewable_type())
def test_previewable_types_return_true(content_type: str) -> None:
    """For any MIME type in PREVIEWABLE_TYPES, `is_previewable()` SHALL return True,
    indicating the content should be served with Content-Disposition: inline.

    **Validates: Requirements 2.4**
    """
    assert is_previewable(content_type) is True, (
        f"Expected is_previewable('{content_type}') to return True "
        f"since it is in PREVIEWABLE_TYPES"
    )


# Feature: document-content-viewer, Property 2: Content-Type Disposition Classification
@settings(max_examples=200)
@given(content_type=st_non_previewable_mime_type())
def test_non_previewable_types_return_false(content_type: str) -> None:
    """For any MIME type NOT in PREVIEWABLE_TYPES, `is_previewable()` SHALL return
    False, indicating the content should be served with Content-Disposition: attachment.

    **Validates: Requirements 2.4**
    """
    assert is_previewable(content_type) is False, (
        f"Expected is_previewable('{content_type}') to return False "
        f"since it is not in PREVIEWABLE_TYPES"
    )


# Feature: document-content-viewer, Property 2: Content-Type Disposition Classification
@settings(max_examples=200)
@given(content_type=st_random_mime_type())
def test_is_previewable_is_deterministic(content_type: str) -> None:
    """For any MIME type string, calling `is_previewable()` multiple times with the
    same input SHALL always produce the same output (determinism).

    **Validates: Requirements 2.4**
    """
    result_1 = is_previewable(content_type)
    result_2 = is_previewable(content_type)
    result_3 = is_previewable(content_type)

    assert result_1 == result_2 == result_3, (
        f"is_previewable('{content_type}') returned inconsistent results: "
        f"{result_1}, {result_2}, {result_3}"
    )
