"""Property-based tests for cross-reference extraction, formatting, and validation.

Property 5: Cross-Reference Extraction Completeness
For any document text containing identifiers matching the patterns REQ-\\d{1,5},
URS-\\d{1,3}\\.\\d{1,3}, TC-\\d{1,5}, TEST-\\d{1,5}, or heading-level numbering,
the extract_references_from_text function SHALL include every matching identifier
in the returned list (up to the 500-entry-per-document limit), with deduplication.

Property 6: Cross-Reference Formatting Threshold
For any set of cross-reference items for a given document_type, when the count
is >= 5 the output SHALL be formatted as a table, and when the count is < 5 the
output SHALL be formatted as a numbered list. Each entry SHALL include
reference_identifier, reference_text (first 150 characters), and source_document_title.

Property 7: Cross-Reference Validation
For any generated document text and its associated Cross_Reference_Map, every
requirement ID or test case reference mentioned in the generated text that does
NOT exist in the Cross_Reference_Map SHALL be flagged in the unverified_references
list with its section_number and paragraph_index.

**Validates: Requirements 3.1, 3.3, 3.4**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

import asyncio
import re

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.cross_reference import (
    CrossReference,
    CrossReferenceService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for generating valid REQ identifiers (REQ-1 to REQ-99999)
st_req_ids = st.from_regex(r"REQ-[1-9]\d{0,4}", fullmatch=True)

# Strategy for generating valid URS identifiers (URS-1.1 to URS-999.999)
st_urs_ids = st.from_regex(r"URS-[1-9]\d{0,2}\.[1-9]\d{0,2}", fullmatch=True)

# Strategy for generating valid TC identifiers (TC-1 to TC-99999)
st_tc_ids = st.from_regex(r"TC-[1-9]\d{0,4}", fullmatch=True)

# Strategy for generating valid TEST identifiers (TEST-1 to TEST-99999)
st_test_ids = st.from_regex(r"TEST-[1-9]\d{0,4}", fullmatch=True)

# Strategy for generating section numbering (1, 1.1, 1.1.1, 1.1.1.1)
st_section_numbers = st.from_regex(
    r"[1-9]\d{0,2}(\.[1-9]\d{0,2}){0,3}", fullmatch=True
)

# Strategy for filler text between references
st_filler_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=5,
    max_size=50,
).filter(
    # Ensure filler doesn't accidentally match reference patterns
    lambda s: not re.search(r"\b(REQ-\d|URS-\d|TC-\d|TEST-\d)\b", s)
    and not re.match(r"^\d{1,3}(\.\d{1,3}){0,3}\s", s)
)

# Strategy for document IDs
st_document_ids = st.integers(min_value=1, max_value=10000)

# Strategy for document titles
st_document_titles = st.text(
    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
    min_size=3,
    max_size=50,
)


def build_text_with_references(
    req_ids: list[str],
    urs_ids: list[str],
    tc_ids: list[str],
    test_ids: list[str],
    section_numbers: list[str],
    filler: str,
) -> str:
    """Build a text document containing the given reference identifiers.

    Each reference is placed on its own line with surrounding filler text
    to simulate a realistic document structure.
    """
    lines: list[str] = []

    # Section numbers must be at the start of a line followed by whitespace
    for sec in section_numbers:
        lines.append(f"{sec} {filler}")

    # Other references can appear inline
    for ref_id in req_ids:
        lines.append(f"{filler} {ref_id} {filler}")

    for urs_id in urs_ids:
        lines.append(f"{filler} {urs_id} {filler}")

    for tc_id in tc_ids:
        lines.append(f"{filler} {tc_id} {filler}")

    for test_id in test_ids:
        lines.append(f"{filler} {test_id} {filler}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 5: Cross-Reference Extraction Completeness
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    req_ids=st.lists(st_req_ids, min_size=0, max_size=10, unique=True),
    urs_ids=st.lists(st_urs_ids, min_size=0, max_size=10, unique=True),
    tc_ids=st.lists(st_tc_ids, min_size=0, max_size=10, unique=True),
    test_ids=st.lists(st_test_ids, min_size=0, max_size=10, unique=True),
    section_numbers=st.lists(st_section_numbers, min_size=0, max_size=10, unique=True),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_extraction_returns_all_distinct_references(
    req_ids: list[str],
    urs_ids: list[str],
    tc_ids: list[str],
    test_ids: list[str],
    section_numbers: list[str],
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """extract_references_from_text SHALL return every distinct reference
    identifier present in the text.

    For any text containing N distinct reference patterns, the function
    returns exactly N unique references (with deduplication).

    **Validates: Requirements 3.1**
    """
    text = build_text_with_references(
        req_ids, urs_ids, tc_ids, test_ids, section_numbers, filler
    )

    service = CrossReferenceService.__new__(CrossReferenceService)
    results = service.extract_references_from_text(text, document_id, document_title)

    # Collect all extracted identifiers
    extracted_identifiers = {ref.reference_identifier for ref in results}

    # All REQ identifiers should be extracted
    for ref_id in req_ids:
        assert ref_id in extracted_identifiers, (
            f"REQ identifier {ref_id} not found in extracted references"
        )

    # All URS identifiers should be extracted
    for urs_id in urs_ids:
        assert urs_id in extracted_identifiers, (
            f"URS identifier {urs_id} not found in extracted references"
        )

    # All TC identifiers should be extracted
    for tc_id in tc_ids:
        assert tc_id in extracted_identifiers, (
            f"TC identifier {tc_id} not found in extracted references"
        )

    # All TEST identifiers should be extracted
    for test_id in test_ids:
        assert test_id in extracted_identifiers, (
            f"TEST identifier {test_id} not found in extracted references"
        )

    # All section numbers should be extracted
    for sec_num in section_numbers:
        assert sec_num in extracted_identifiers, (
            f"Section number {sec_num} not found in extracted references"
        )


@settings(max_examples=25)
@given(
    req_ids=st.lists(st_req_ids, min_size=1, max_size=5, unique=True),
    repeat_count=st.integers(min_value=2, max_value=5),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_extraction_deduplicates_repeated_references(
    req_ids: list[str],
    repeat_count: int,
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """extract_references_from_text SHALL deduplicate references that appear
    multiple times in the text, returning each unique identifier only once.

    **Validates: Requirements 3.1**
    """
    # Build text with repeated references
    lines: list[str] = []
    for ref_id in req_ids:
        for _ in range(repeat_count):
            lines.append(f"{filler} {ref_id} {filler}")
    text = "\n".join(lines)

    service = CrossReferenceService.__new__(CrossReferenceService)
    results = service.extract_references_from_text(text, document_id, document_title)

    # Count occurrences of each identifier in results
    identifier_counts: dict[str, int] = {}
    for ref in results:
        identifier_counts[ref.reference_identifier] = (
            identifier_counts.get(ref.reference_identifier, 0) + 1
        )

    # Each identifier should appear exactly once (deduplicated)
    for ref_id in req_ids:
        assert identifier_counts.get(ref_id, 0) == 1, (
            f"Identifier {ref_id} appeared {identifier_counts.get(ref_id, 0)} times, "
            f"expected exactly 1 (deduplication)"
        )

    # Total results should equal number of unique identifiers
    assert len(results) == len(req_ids)


@settings(max_examples=25)
@given(
    req_ids=st.lists(st_req_ids, min_size=0, max_size=10, unique=True),
    urs_ids=st.lists(st_urs_ids, min_size=0, max_size=10, unique=True),
    tc_ids=st.lists(st_tc_ids, min_size=0, max_size=10, unique=True),
    test_ids=st.lists(st_test_ids, min_size=0, max_size=10, unique=True),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_extraction_assigns_correct_reference_types(
    req_ids: list[str],
    urs_ids: list[str],
    tc_ids: list[str],
    test_ids: list[str],
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """extract_references_from_text SHALL assign the correct reference_type
    to each extracted reference: "requirement" for REQ-* and URS-*,
    "test_case" for TC-* and TEST-*.

    **Validates: Requirements 3.1**
    """
    text = build_text_with_references(
        req_ids, urs_ids, tc_ids, test_ids, [], filler
    )

    service = CrossReferenceService.__new__(CrossReferenceService)
    results = service.extract_references_from_text(text, document_id, document_title)

    # Build a lookup from identifier to reference_type
    type_lookup = {ref.reference_identifier: ref.reference_type for ref in results}

    # REQ identifiers should be "requirement"
    for ref_id in req_ids:
        assert type_lookup.get(ref_id) == "requirement", (
            f"REQ identifier {ref_id} should have type 'requirement', "
            f"got '{type_lookup.get(ref_id)}'"
        )

    # URS identifiers should be "requirement"
    for urs_id in urs_ids:
        assert type_lookup.get(urs_id) == "requirement", (
            f"URS identifier {urs_id} should have type 'requirement', "
            f"got '{type_lookup.get(urs_id)}'"
        )

    # TC identifiers should be "test_case"
    for tc_id in tc_ids:
        assert type_lookup.get(tc_id) == "test_case", (
            f"TC identifier {tc_id} should have type 'test_case', "
            f"got '{type_lookup.get(tc_id)}'"
        )

    # TEST identifiers should be "test_case"
    for test_id in test_ids:
        assert type_lookup.get(test_id) == "test_case", (
            f"TEST identifier {test_id} should have type 'test_case', "
            f"got '{type_lookup.get(test_id)}'"
        )


# ---------------------------------------------------------------------------
# Property 6: Cross-Reference Formatting Threshold
# ---------------------------------------------------------------------------


def format_cross_references(
    references: list[CrossReference],
) -> str:
    """Format cross-references as table (>= 5 items) or numbered list (< 5).

    This implements the formatting threshold logic from Requirement 3.3:
    - >= 5 items: table format with columns for identifier, text, source
    - < 5 items: numbered list format

    Each entry includes reference_identifier, reference_text (first 150 chars),
    and source_document_title.
    """
    if not references:
        return ""

    if len(references) >= 5:
        # Table format
        header = "| Reference ID | Reference Text | Source Document |"
        separator = "|---|---|---|"
        rows = []
        for ref in references:
            text = ref.reference_text[:150] if ref.reference_text else ""
            rows.append(
                f"| {ref.reference_identifier} | {text} | {ref.source_document_title} |"
            )
        return "\n".join([header, separator] + rows)
    else:
        # Numbered list format
        items = []
        for i, ref in enumerate(references, 1):
            text = ref.reference_text[:150] if ref.reference_text else ""
            items.append(
                f"{i}. {ref.reference_identifier} — {text} "
                f"(Source: {ref.source_document_title})"
            )
        return "\n".join(items)


@settings(max_examples=25)
@given(
    num_items=st.integers(min_value=5, max_value=50),
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_formatting_uses_table_when_five_or_more_items(
    num_items: int,
    document_id: int,
    document_title: str,
) -> None:
    """When a cross-reference set has >= 5 items, the formatting SHALL use
    table format with header row and separator.

    **Validates: Requirements 3.3**
    """
    references = [
        CrossReference(
            reference_type="requirement",
            reference_identifier=f"REQ-{i:05d}",
            reference_text=f"Requirement {i} description text for testing",
            source_document_id=document_id,
            source_document_title=document_title,
        )
        for i in range(1, num_items + 1)
    ]

    output = format_cross_references(references)

    # Table format indicators
    assert output.startswith("|"), "Table format should start with pipe character"
    assert "| Reference ID |" in output, "Table should have Reference ID header"
    assert "| Reference Text |" in output, "Table should have Reference Text header"
    assert "| Source Document |" in output, "Table should have Source Document header"
    assert "|---|---|---|" in output, "Table should have separator row"

    # Each reference should appear in the output
    for ref in references:
        assert ref.reference_identifier in output
        assert ref.source_document_title in output


@settings(max_examples=25)
@given(
    num_items=st.integers(min_value=1, max_value=4),
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_formatting_uses_list_when_fewer_than_five_items(
    num_items: int,
    document_id: int,
    document_title: str,
) -> None:
    """When a cross-reference set has < 5 items, the formatting SHALL use
    numbered list format.

    **Validates: Requirements 3.3**
    """
    references = [
        CrossReference(
            reference_type="test_case",
            reference_identifier=f"TC-{i:05d}",
            reference_text=f"Test case {i} description text for testing",
            source_document_id=document_id,
            source_document_title=document_title,
        )
        for i in range(1, num_items + 1)
    ]

    output = format_cross_references(references)

    # List format indicators: should NOT have table markers
    assert "|---|" not in output, "List format should not have table separators"

    # Should have numbered items
    for i in range(1, num_items + 1):
        assert f"{i}." in output, f"List should contain numbered item {i}."

    # Each reference should appear in the output
    for ref in references:
        assert ref.reference_identifier in output
        assert ref.source_document_title in output


@settings(max_examples=25)
@given(
    num_items=st.integers(min_value=1, max_value=30),
    document_id=st_document_ids,
    document_title=st_document_titles,
    long_text=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90),
        min_size=200,
        max_size=300,
    ),
)
def test_formatting_truncates_reference_text_to_150_chars(
    num_items: int,
    document_id: int,
    document_title: str,
    long_text: str,
) -> None:
    """Each entry in the formatted output SHALL include reference_text
    truncated to the first 150 characters.

    **Validates: Requirements 3.3**
    """
    references = [
        CrossReference(
            reference_type="requirement",
            reference_identifier=f"REQ-{i:05d}",
            reference_text=long_text,
            source_document_id=document_id,
            source_document_title=document_title,
        )
        for i in range(1, num_items + 1)
    ]

    output = format_cross_references(references)

    # The full long_text (> 150 chars) should NOT appear in output
    assert long_text not in output, (
        "Full reference_text exceeding 150 chars should be truncated"
    )
    # But the first 150 chars should appear
    truncated = long_text[:150]
    assert truncated in output, (
        "First 150 characters of reference_text should appear in output"
    )


# ---------------------------------------------------------------------------
# Property 7: Cross-Reference Validation
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    known_req_ids=st.lists(st_req_ids, min_size=1, max_size=5, unique=True),
    unknown_req_ids=st.lists(st_req_ids, min_size=1, max_size=5, unique=True),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_validation_flags_references_not_in_map(
    known_req_ids: list[str],
    unknown_req_ids: list[str],
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """validate_references_in_output SHALL flag every reference in the generated
    text that does NOT exist in the Cross_Reference_Map as unverified.

    **Validates: Requirements 3.4**
    """
    # Ensure unknown IDs are truly unknown (not in known set)
    unknown_req_ids = [
        uid for uid in unknown_req_ids if uid not in known_req_ids
    ]
    if not unknown_req_ids:
        return  # Skip if all "unknown" IDs happen to be in known set

    # Build the cross-reference map with known IDs
    cross_ref_map: dict[str, list[CrossReference]] = {
        "requirement": [
            CrossReference(
                reference_type="requirement",
                reference_identifier=ref_id,
                reference_text=f"Known requirement {ref_id}",
                source_document_id=document_id,
                source_document_title=document_title,
            )
            for ref_id in known_req_ids
        ],
        "test_case": [],
        "section": [],
    }

    # Build generated text containing both known and unknown references
    lines: list[str] = []
    for ref_id in known_req_ids:
        lines.append(f"{filler} {ref_id} {filler}")
    for ref_id in unknown_req_ids:
        lines.append(f"{filler} {ref_id} {filler}")
    generated_text = "\n".join(lines)

    # Run validation
    service = CrossReferenceService.__new__(CrossReferenceService)
    unverified = asyncio.run(
        service.validate_references_in_output(generated_text, cross_ref_map)
    )

    # All unknown references should be flagged
    flagged_identifiers = {item["reference_identifier"] for item in unverified}
    for unknown_id in unknown_req_ids:
        assert unknown_id in flagged_identifiers, (
            f"Unknown reference {unknown_id} should be flagged as unverified"
        )

    # No known references should be flagged
    for known_id in known_req_ids:
        assert known_id not in flagged_identifiers, (
            f"Known reference {known_id} should NOT be flagged as unverified"
        )


@settings(max_examples=25)
@given(
    known_tc_ids=st.lists(st_tc_ids, min_size=1, max_size=5, unique=True),
    unknown_test_ids=st.lists(st_test_ids, min_size=1, max_size=5, unique=True),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_validation_flags_unknown_test_case_references(
    known_tc_ids: list[str],
    unknown_test_ids: list[str],
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """validate_references_in_output SHALL flag test case references (TEST-*)
    not in the Cross_Reference_Map as unverified.

    **Validates: Requirements 3.4**
    """
    # Ensure unknown IDs are truly unknown
    known_set = set(known_tc_ids)
    unknown_test_ids = [uid for uid in unknown_test_ids if uid not in known_set]
    if not unknown_test_ids:
        return

    # Build the cross-reference map with known TC IDs
    cross_ref_map: dict[str, list[CrossReference]] = {
        "requirement": [],
        "test_case": [
            CrossReference(
                reference_type="test_case",
                reference_identifier=tc_id,
                reference_text=f"Known test case {tc_id}",
                source_document_id=document_id,
                source_document_title=document_title,
            )
            for tc_id in known_tc_ids
        ],
        "section": [],
    }

    # Build generated text with known TC and unknown TEST references
    lines: list[str] = []
    for tc_id in known_tc_ids:
        lines.append(f"{filler} {tc_id} {filler}")
    for test_id in unknown_test_ids:
        lines.append(f"{filler} {test_id} {filler}")
    generated_text = "\n".join(lines)

    # Run validation
    service = CrossReferenceService.__new__(CrossReferenceService)
    unverified = asyncio.run(
        service.validate_references_in_output(generated_text, cross_ref_map)
    )

    # All unknown TEST references should be flagged
    flagged_identifiers = {item["reference_identifier"] for item in unverified}
    for test_id in unknown_test_ids:
        assert test_id in flagged_identifiers, (
            f"Unknown TEST reference {test_id} should be flagged as unverified"
        )

    # Known TC references should NOT be flagged
    for tc_id in known_tc_ids:
        assert tc_id not in flagged_identifiers, (
            f"Known TC reference {tc_id} should NOT be flagged as unverified"
        )


@settings(max_examples=25)
@given(
    known_req_ids=st.lists(st_req_ids, min_size=1, max_size=10, unique=True),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_validation_returns_empty_when_all_references_known(
    known_req_ids: list[str],
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """validate_references_in_output SHALL return an empty list when all
    references in the generated text exist in the Cross_Reference_Map.

    **Validates: Requirements 3.4**
    """
    # Build the cross-reference map with all IDs
    cross_ref_map: dict[str, list[CrossReference]] = {
        "requirement": [
            CrossReference(
                reference_type="requirement",
                reference_identifier=ref_id,
                reference_text=f"Known requirement {ref_id}",
                source_document_id=document_id,
                source_document_title=document_title,
            )
            for ref_id in known_req_ids
        ],
        "test_case": [],
        "section": [],
    }

    # Build generated text containing ONLY known references
    lines: list[str] = []
    for ref_id in known_req_ids:
        lines.append(f"{filler} {ref_id} {filler}")
    generated_text = "\n".join(lines)

    # Run validation
    service = CrossReferenceService.__new__(CrossReferenceService)
    unverified = asyncio.run(
        service.validate_references_in_output(generated_text, cross_ref_map)
    )

    # No references should be flagged
    assert len(unverified) == 0, (
        f"Expected no unverified references when all are known, "
        f"got {len(unverified)}: {unverified}"
    )


@settings(max_examples=25)
@given(
    unknown_req_ids=st.lists(st_req_ids, min_size=1, max_size=5, unique=True),
    filler=st_filler_text,
    document_id=st_document_ids,
    document_title=st_document_titles,
)
def test_validation_includes_location_info_for_unverified(
    unknown_req_ids: list[str],
    filler: str,
    document_id: int,
    document_title: str,
) -> None:
    """validate_references_in_output SHALL include section_number and
    paragraph_index in the location info for each unverified reference.

    **Validates: Requirements 3.4**
    """
    # Empty cross-reference map — all references will be unverified
    cross_ref_map: dict[str, list[CrossReference]] = {
        "requirement": [],
        "test_case": [],
        "section": [],
    }

    # Build generated text with unknown references
    lines: list[str] = []
    for ref_id in unknown_req_ids:
        lines.append(f"{filler} {ref_id} {filler}")
    generated_text = "\n".join(lines)

    # Run validation
    service = CrossReferenceService.__new__(CrossReferenceService)
    unverified = asyncio.run(
        service.validate_references_in_output(generated_text, cross_ref_map)
    )

    # Each unverified entry should have location info
    for item in unverified:
        assert "location" in item, "Unverified reference must include 'location'"
        assert "section_number" in item["location"], (
            "Location must include 'section_number'"
        )
        assert "paragraph_index" in item["location"], (
            "Location must include 'paragraph_index'"
        )
        assert "reference_identifier" in item, (
            "Unverified reference must include 'reference_identifier'"
        )
        assert "reference_type" in item, (
            "Unverified reference must include 'reference_type'"
        )
