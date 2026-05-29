"""Property-based tests for X-Change-Reason header validation.

Property 2: X-Change-Reason Header Validation
For any string submitted as the X-Change-Reason header on a mutation endpoint,
the request SHALL be accepted if and only if the string is non-empty (after
trimming whitespace) and contains at most 500 characters. Empty strings,
whitespace-only strings, and strings exceeding 500 characters SHALL be rejected.

**Validates: Requirements 1.3**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Middleware: src/backend/src/alcoabase/middleware/audit_middleware.py
"""

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Validation function under test
# ---------------------------------------------------------------------------


def validate_change_reason(header_value: str | None) -> bool:
    """Validate the X-Change-Reason header value.

    Mirrors the combined validation logic from:
    1. AuditMiddleware: rejects None, empty, and whitespace-only values
    2. ConfigurationSnapshot.change_reason: String(500) column constraint

    The header is accepted if and only if:
    - It is not None
    - After trimming whitespace, it is non-empty
    - After trimming whitespace, its length is at most 500 characters

    Args:
        header_value: The raw X-Change-Reason header value.

    Returns:
        True if the header value is valid (accepted), False otherwise.
    """
    if not header_value or not header_value.strip():
        return False
    if len(header_value.strip()) > 500:
        return False
    return True


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_valid_change_reason() -> st.SearchStrategy[str]:
    """Generate valid X-Change-Reason header values.

    Valid values are non-empty after trimming and at most 500 chars after trim.
    May include leading/trailing whitespace as long as the trimmed content
    is between 1 and 500 characters.
    """
    # Generate the core content (1-500 non-whitespace-containing chars)
    core = st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            min_codepoint=32,
            max_codepoint=126,
        ),
        min_size=1,
        max_size=500,
    ).filter(lambda s: 0 < len(s.strip()) <= 500)

    # Optionally wrap with leading/trailing whitespace
    return st.builds(
        lambda prefix, content, suffix: prefix + content + suffix,
        prefix=st.text(
            alphabet=st.sampled_from(" \t"),
            min_size=0,
            max_size=5,
        ),
        content=core,
        suffix=st.text(
            alphabet=st.sampled_from(" \t"),
            min_size=0,
            max_size=5,
        ),
    ).filter(lambda s: 0 < len(s.strip()) <= 500)


def st_whitespace_only() -> st.SearchStrategy[str]:
    """Generate strings containing only whitespace characters."""
    return st.text(
        alphabet=st.sampled_from(" \t\n\r\v\f"),
        min_size=1,
        max_size=50,
    )


def st_too_long_after_trim() -> st.SearchStrategy[str]:
    """Generate strings that exceed 500 characters after trimming."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S"),
            min_codepoint=33,
            max_codepoint=126,
        ),
        min_size=501,
        max_size=600,
    )


# ---------------------------------------------------------------------------
# Property 2: Valid change reasons are accepted
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(reason=st_valid_change_reason())
def test_valid_change_reason_accepted(reason: str) -> None:
    """For any non-empty string (after trim) with at most 500 characters,
    the X-Change-Reason header SHALL be accepted.

    **Validates: Requirements 1.3**
    """
    result = validate_change_reason(reason)
    assert result is True, (
        f"Expected valid for reason {reason!r} "
        f"(trimmed length={len(reason.strip())})"
    )


# ---------------------------------------------------------------------------
# Property 2: Empty strings are rejected
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_empty_string_rejected(data: st.DataObject) -> None:
    """An empty string X-Change-Reason header SHALL be rejected.

    **Validates: Requirements 1.3**
    """
    result = validate_change_reason("")
    assert result is False, "Expected rejection for empty string"


# ---------------------------------------------------------------------------
# Property 2: Whitespace-only strings are rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(reason=st_whitespace_only())
def test_whitespace_only_rejected(reason: str) -> None:
    """For any whitespace-only string, the X-Change-Reason header SHALL
    be rejected.

    **Validates: Requirements 1.3**
    """
    result = validate_change_reason(reason)
    assert result is False, (
        f"Expected rejection for whitespace-only input {reason!r}"
    )


# ---------------------------------------------------------------------------
# Property 2: Strings exceeding 500 chars (after trim) are rejected
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(reason=st_too_long_after_trim())
def test_too_long_rejected(reason: str) -> None:
    """For any string exceeding 500 characters after trimming, the
    X-Change-Reason header SHALL be rejected.

    **Validates: Requirements 1.3**
    """
    result = validate_change_reason(reason)
    assert result is False, (
        f"Expected rejection for too-long input "
        f"(trimmed length={len(reason.strip())})"
    )


# ---------------------------------------------------------------------------
# Property 2: None is rejected
# ---------------------------------------------------------------------------


@settings(max_examples=5)
@given(data=st.data())
def test_none_rejected(data: st.DataObject) -> None:
    """A None X-Change-Reason header SHALL be rejected.

    **Validates: Requirements 1.3**
    """
    result = validate_change_reason(None)
    assert result is False, "Expected rejection for None"


# ---------------------------------------------------------------------------
# Property 2: Boundary — exactly 500 chars after trim is accepted
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    char=st.characters(
        whitelist_categories=("L", "N"),
        min_codepoint=65,
        max_codepoint=90,
    )
)
def test_exactly_500_chars_accepted(char: str) -> None:
    """A string of exactly 500 characters (after trim) SHALL be accepted.

    **Validates: Requirements 1.3**
    """
    reason = char * 500
    result = validate_change_reason(reason)
    assert result is True, (
        f"Expected valid for exactly 500 chars, got rejected"
    )


# ---------------------------------------------------------------------------
# Property 2: Boundary — exactly 501 chars after trim is rejected
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    char=st.characters(
        whitelist_categories=("L", "N"),
        min_codepoint=65,
        max_codepoint=90,
    )
)
def test_exactly_501_chars_rejected(char: str) -> None:
    """A string of exactly 501 characters (after trim) SHALL be rejected.

    **Validates: Requirements 1.3**
    """
    reason = char * 501
    result = validate_change_reason(reason)
    assert result is False, (
        f"Expected rejection for 501 chars, got accepted"
    )


# ---------------------------------------------------------------------------
# Property 2: Comprehensive — acceptance iff non-empty and ≤500 after trim
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(reason=st.text(min_size=0, max_size=600))
def test_acceptance_iff_nonempty_and_within_limit(reason: str) -> None:
    """For any random string, the X-Change-Reason header is accepted if and
    only if the trimmed string is non-empty and at most 500 characters.

    This is the core property: accepted ⟺ (0 < len(trim(reason)) ≤ 500).

    **Validates: Requirements 1.3**
    """
    trimmed = reason.strip()
    expected_valid = 0 < len(trimmed) <= 500

    result = validate_change_reason(reason)
    assert result == expected_valid, (
        f"For input {reason!r} (trimmed length={len(trimmed)}): "
        f"expected {'accepted' if expected_valid else 'rejected'}, "
        f"got {'accepted' if result else 'rejected'}"
    )
