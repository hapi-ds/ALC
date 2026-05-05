"""Property-based tests for Slug Validity.

Tests Property 6 from the setup-wizard design document, validating that:
1. For any display name string, the auto-generated slug is non-empty and matches
   the valid slug pattern.
2. For any explicitly provided slug, the validator accepts it if and only if it
   matches the pattern `^[a-z0-9]+(-[a-z0-9]+)*$`.

**Validates: Requirements 4.2, 4.3**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 6)
    - Requirements: .kiro/specs/setup-wizard/requirements.md (Requirements 4.2, 4.3)
"""

import re

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.slug_generator import SlugGenerator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Unicode text of varying lengths for slug generation testing
st_unicode_display_names = st.text(
    alphabet=st.characters(),
    min_size=0,
    max_size=200,
)

# ASCII strings for slug validation testing
st_ascii_strings = st.text(
    alphabet=st.characters(codec="ascii"),
    min_size=0,
    max_size=100,
)


# ---------------------------------------------------------------------------
# Property 6: Slug Validity — Generation
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 6: Slug Validity
@settings(max_examples=100)
@given(display_name=st_unicode_display_names)
def test_slug_generation_always_valid(display_name: str) -> None:
    """For any unicode display name string, the auto-generated slug SHALL
    contain only lowercase letters, digits, and hyphens, and SHALL NOT be empty.

    **Validates: Requirements 4.2, 4.3**
    """
    generator = SlugGenerator()
    slug = generator.generate(display_name)

    # Property: generated slug is never empty
    assert slug, (
        f"Generated slug is empty for display_name={display_name!r}"
    )

    # Property: generated slug matches the valid pattern
    assert VALID_SLUG_PATTERN.match(slug), (
        f"Generated slug {slug!r} from display_name={display_name!r} "
        f"does not match pattern ^[a-z0-9]+(-[a-z0-9]+)*$"
    )


# ---------------------------------------------------------------------------
# Property 6: Slug Validity — Validation
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 6: Slug Validity
@settings(max_examples=100)
@given(candidate=st_ascii_strings)
def test_slug_validator_accepts_iff_pattern_matches(candidate: str) -> None:
    """For any ASCII string, the validator SHALL accept it if and only if
    the string matches the pattern `^[a-z0-9]+(-[a-z0-9]+)*$`.

    **Validates: Requirements 4.2, 4.3**
    """
    generator = SlugGenerator()
    is_valid = generator.validate(candidate)
    pattern_matches = bool(VALID_SLUG_PATTERN.match(candidate))

    # Property: validator agrees with the regex pattern
    assert is_valid == pattern_matches, (
        f"Slug validator disagreement for candidate={candidate!r}: "
        f"validate() returned {is_valid}, "
        f"but pattern match is {pattern_matches}"
    )
