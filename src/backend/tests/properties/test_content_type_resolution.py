"""Property-based tests for Content-Type Resolution.

Tests Property 4 from the document-content-viewer design document, validating that:
1. If a stored content_type value is present and non-empty, the resolved content
   type equals the stored value (stripped).
2. If no stored value exists, the resolved type matches the extension-to-MIME
   mapping for the storage key's extension.
3. If neither stored nor extension match, the result is "application/octet-stream".
4. The result is never empty.

**Validates: Requirements 5.1, 5.2**

References:
    - Design: .kiro/specs/document-content-viewer/design.md (Correctness Property 4)
    - Requirements: .kiro/specs/document-content-viewer/requirements.md (Requirements 5.1, 5.2)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.content_type_utils import EXTENSION_MIME_MAP, resolve_content_type


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FALLBACK_CONTENT_TYPE = "application/octet-stream"

KNOWN_EXTENSIONS = list(EXTENSION_MIME_MAP.keys())


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Non-empty MIME-type-like strings to simulate stored content types
st_stored_content_types = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        whitelist_characters="/.-+;= ",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())

# Storage keys with known extensions (to test extension mapping)
st_storage_keys_with_known_ext = st.tuples(
    st.text(
        alphabet=st.characters(codec="ascii", whitelist_categories=("L", "N", "P")),
        min_size=1,
        max_size=80,
    ),
    st.sampled_from(KNOWN_EXTENSIONS),
).map(lambda t: f"documents/{t[0]}/file{t[1]}")

# Storage keys with unknown or no extension
st_storage_keys_without_known_ext = st.one_of(
    # No extension at all
    st.text(
        alphabet=st.characters(codec="ascii", whitelist_categories=("L", "N")),
        min_size=1,
        max_size=80,
    ).map(lambda s: f"documents/{s}/document"),
    # Unknown extension
    st.text(
        alphabet=st.characters(codec="ascii", whitelist_categories=("L",)),
        min_size=2,
        max_size=10,
    ).filter(
        lambda ext: f".{ext.lower()}" not in EXTENSION_MIME_MAP
    ).map(lambda ext: f"documents/file.{ext}"),
)

# Any storage key (mix of known and unknown extensions)
st_any_storage_key = st.one_of(
    st_storage_keys_with_known_ext,
    st_storage_keys_without_known_ext,
)


# ---------------------------------------------------------------------------
# Property 4: Content-Type Resolution — Stored value takes priority
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 4: Content-Type Resolution
@settings(max_examples=200)
@given(
    stored_type=st_stored_content_types,
    storage_key=st_any_storage_key,
)
def test_stored_content_type_takes_priority(
    stored_type: str, storage_key: str
) -> None:
    """If a stored content_type value is present and non-empty, the resolved
    content type SHALL equal the stored value (stripped).

    **Validates: Requirements 5.1, 5.2**
    """
    result = resolve_content_type(stored_type, storage_key)

    assert result == stored_type.strip(), (
        f"Expected stored type {stored_type.strip()!r} but got {result!r} "
        f"for stored_type={stored_type!r}, storage_key={storage_key!r}"
    )


# ---------------------------------------------------------------------------
# Property 4: Content-Type Resolution — Extension mapping fallback
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 4: Content-Type Resolution
@settings(max_examples=200)
@given(storage_key=st_storage_keys_with_known_ext)
def test_extension_mapping_when_no_stored_type(storage_key: str) -> None:
    """If no stored content_type exists, the resolved type SHALL match the
    extension-to-MIME mapping for the storage key's extension.

    **Validates: Requirements 5.1, 5.2**
    """
    # Test with None
    result_none = resolve_content_type(None, storage_key)

    # Extract extension from the storage key
    ext = "." + storage_key.rsplit(".", 1)[-1]
    expected = EXTENSION_MIME_MAP[ext.lower()]

    assert result_none == expected, (
        f"Expected {expected!r} from extension mapping but got {result_none!r} "
        f"for storage_key={storage_key!r} with stored_type=None"
    )

    # Test with empty string
    result_empty = resolve_content_type("", storage_key)
    assert result_empty == expected, (
        f"Expected {expected!r} from extension mapping but got {result_empty!r} "
        f"for storage_key={storage_key!r} with stored_type=''"
    )


# ---------------------------------------------------------------------------
# Property 4: Content-Type Resolution — Octet-stream fallback
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 4: Content-Type Resolution
@settings(max_examples=200)
@given(storage_key=st_storage_keys_without_known_ext)
def test_fallback_to_octet_stream(storage_key: str) -> None:
    """If neither stored content type nor extension mapping exists, the
    result SHALL be "application/octet-stream".

    **Validates: Requirements 5.1, 5.2**
    """
    result_none = resolve_content_type(None, storage_key)

    assert result_none == FALLBACK_CONTENT_TYPE, (
        f"Expected {FALLBACK_CONTENT_TYPE!r} fallback but got {result_none!r} "
        f"for storage_key={storage_key!r} with stored_type=None"
    )

    result_empty = resolve_content_type("", storage_key)
    assert result_empty == FALLBACK_CONTENT_TYPE, (
        f"Expected {FALLBACK_CONTENT_TYPE!r} fallback but got {result_empty!r} "
        f"for storage_key={storage_key!r} with stored_type=''"
    )


# ---------------------------------------------------------------------------
# Property 4: Content-Type Resolution — Result never empty
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 4: Content-Type Resolution
@settings(max_examples=200)
@given(
    stored_type=st.one_of(st.none(), st.text(max_size=100)),
    storage_key=st_any_storage_key,
)
def test_result_is_never_empty(
    stored_type: str | None, storage_key: str
) -> None:
    """For any combination of stored_type and storage_key, the resolved
    content type SHALL never be an empty string.

    **Validates: Requirements 5.1, 5.2**
    """
    result = resolve_content_type(stored_type, storage_key)

    assert result, (
        f"resolve_content_type returned empty/falsy result for "
        f"stored_type={stored_type!r}, storage_key={storage_key!r}"
    )
    assert isinstance(result, str), (
        f"resolve_content_type returned non-string {type(result)} for "
        f"stored_type={stored_type!r}, storage_key={storage_key!r}"
    )
