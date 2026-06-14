"""Property-based tests for Response Header Correctness.

Tests Property 1 from the document-content-viewer design document, validating
that `build_content_disposition()` produces valid RFC 6266 Content-Disposition
headers for any combination of disposition types and filenames (including
Unicode, special characters, and long strings).

**Validates: Requirements 1.1, 2.1, 5.3**

References:
    - Design: .kiro/specs/document-content-viewer/design.md (Correctness Property 1)
    - Requirements: .kiro/specs/document-content-viewer/requirements.md
"""

import re

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.content_type_utils import build_content_disposition


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Disposition types used in the application
st_disposition = st.sampled_from(["inline", "attachment"])

# Filenames: Unicode text including special chars and long strings
st_filename = st.text(min_size=1, max_size=300)

# Pattern to detect raw non-ASCII characters (bytes > 0x7F)
RAW_NON_ASCII_PATTERN = re.compile(r"[^\x00-\x7f]")


# ---------------------------------------------------------------------------
# Property 1: Response Header Correctness
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 1: Response Header Correctness
@settings(max_examples=200, deadline=None)
@given(disposition=st_disposition, filename=st_filename)
def test_header_starts_with_disposition_type(
    disposition: str, filename: str
) -> None:
    """For any disposition type and filename, the result SHALL always start
    with the disposition type.

    **Validates: Requirements 1.1, 2.1, 5.3**
    """
    result = build_content_disposition(disposition, filename)
    assert result.startswith(disposition), (
        f"Header does not start with '{disposition}': {result!r}"
    )


# Feature: document-content-viewer, Property 1: Response Header Correctness
@settings(max_examples=200, deadline=None)
@given(disposition=st_disposition, filename=st_filename)
def test_header_contains_filename_parameters(
    disposition: str, filename: str
) -> None:
    """For any disposition type and filename, the result SHALL always contain
    both `filename=` and `filename*=UTF-8''` parameters.

    **Validates: Requirements 1.1, 2.1, 5.3**
    """
    result = build_content_disposition(disposition, filename)
    assert 'filename="' in result, (
        f"Header missing filename= parameter: {result!r}"
    )
    assert "filename*=UTF-8''" in result, (
        f"Header missing filename*=UTF-8'' parameter: {result!r}"
    )


# Feature: document-content-viewer, Property 1: Response Header Correctness
@settings(max_examples=200, deadline=None)
@given(disposition=st_disposition, filename=st_filename)
def test_header_filename_star_has_no_raw_non_ascii(
    disposition: str, filename: str
) -> None:
    """For any disposition type and filename, the filename* part SHALL use
    proper percent-encoding with no raw non-ASCII characters.

    **Validates: Requirements 1.1, 2.1, 5.3**
    """
    result = build_content_disposition(disposition, filename)

    # Extract the filename* value (everything after "filename*=UTF-8''")
    marker = "filename*=UTF-8''"
    idx = result.find(marker)
    assert idx != -1, f"Could not find {marker} in: {result!r}"
    filename_star_value = result[idx + len(marker):]

    # The percent-encoded filename must contain no raw non-ASCII characters
    assert not RAW_NON_ASCII_PATTERN.search(filename_star_value), (
        f"filename* contains raw non-ASCII characters: {filename_star_value!r}"
    )


# Feature: document-content-viewer, Property 1: Response Header Correctness
@settings(max_examples=200, deadline=None)
@given(disposition=st_disposition, filename=st_filename)
def test_header_is_never_empty(disposition: str, filename: str) -> None:
    """For any disposition type and filename, the result SHALL never be empty.

    **Validates: Requirements 1.1, 2.1, 5.3**
    """
    result = build_content_disposition(disposition, filename)
    assert result, "build_content_disposition returned an empty string"
    assert len(result) > 0, "build_content_disposition returned an empty string"


# Feature: document-content-viewer, Property 1: Response Header Correctness
@settings(max_examples=200, deadline=None)
@given(disposition=st_disposition, filename=st_filename)
def test_header_structure_is_well_formed(
    disposition: str, filename: str
) -> None:
    """For any disposition type and filename, the result SHALL have the
    well-formed structure: `{disposition}; filename="..."; filename*=UTF-8''...`

    **Validates: Requirements 1.1, 2.1, 5.3**
    """
    result = build_content_disposition(disposition, filename)

    # Must contain the semicolons separating the parameters
    parts = result.split("; ")
    assert len(parts) >= 3, (
        f"Expected at least 3 semicolon-separated parts, got {len(parts)}: {result!r}"
    )
    assert parts[0] == disposition, (
        f"First part should be disposition type '{disposition}', got '{parts[0]}'"
    )
    assert parts[1].startswith('filename="'), (
        f"Second part should start with 'filename=\"', got '{parts[1]}'"
    )
    # The filename* part may contain "; " in the percent-encoded value,
    # so rejoin the remaining parts and check
    remaining = "; ".join(parts[2:])
    assert remaining.startswith("filename*=UTF-8''"), (
        f"Third+ part should start with \"filename*=UTF-8''\", got '{remaining}'"
    )
