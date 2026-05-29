"""Property-based tests for link deduplication in TraceabilityMatrixService.

Property 2: Link Deduplication

Generate sets of candidate links with duplicate (requirement_id, test_case_id)
pairs via different methods, verify single link retained with highest confidence
and all methods recorded in link_methods array.

**Validates: Requirements 1.7**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/traceability_matrix.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.traceability_matrix import (
    CandidateLink,
    TraceabilityMatrixService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Valid link methods as defined in the design
LINK_METHODS = st.sampled_from(["exact_id_match", "cross_reference", "semantic_match"])

# Confidence scores in valid range (0.0 to 1.0)
CONFIDENCE_SCORES = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Requirement IDs following patterns from the spec
REQUIREMENT_IDS = st.from_regex(r"REQ-[0-9]{3}", fullmatch=True)

# Test case IDs following patterns from the spec
TEST_CASE_IDS = st.from_regex(r"TC-[0-9]{3}", fullmatch=True)

# Document UUIDs (12-char strings)
DOCUMENT_UUIDS = st.from_regex(r"2025-[0-9]{5}", fullmatch=True)

# Section identifiers
SECTIONS = st.from_regex(r"Section [1-9]\.[0-9]", fullmatch=True)


@st.composite
def st_candidate_link(
    draw: st.DrawFn,
    requirement_id: st.SearchStrategy[str] | None = None,
    test_case_id: st.SearchStrategy[str] | None = None,
) -> CandidateLink:
    """Generate a single CandidateLink with optional fixed IDs.

    Args:
        draw: Hypothesis draw function.
        requirement_id: Optional strategy for requirement_id (fixed for duplication).
        test_case_id: Optional strategy for test_case_id (fixed for duplication).

    Returns:
        A CandidateLink instance.
    """
    req_id = draw(requirement_id if requirement_id is not None else REQUIREMENT_IDS)
    tc_id = draw(test_case_id if test_case_id is not None else TEST_CASE_IDS)

    return CandidateLink(
        requirement_id=req_id,
        requirement_text=f"Requirement text for {req_id}",
        source_document_uuid=draw(DOCUMENT_UUIDS),
        source_section=draw(SECTIONS),
        test_case_id=tc_id,
        test_case_text=f"Test case text for {tc_id}",
        target_document_uuid=draw(DOCUMENT_UUIDS),
        target_section=draw(SECTIONS),
        link_confidence=draw(CONFIDENCE_SCORES),
        link_method=draw(LINK_METHODS),
    )


@st.composite
def st_duplicate_link_set(draw: st.DrawFn) -> list[CandidateLink]:
    """Generate a set of candidate links with guaranteed duplicates.

    Creates 2-5 links sharing the same (requirement_id, test_case_id) pair
    but with different methods and confidence scores.

    Returns:
        List of CandidateLink instances with at least one duplicate pair.
    """
    # Fix the requirement_id and test_case_id for the duplicate group
    req_id = draw(REQUIREMENT_IDS)
    tc_id = draw(TEST_CASE_IDS)

    # Generate 2-5 duplicates for this pair
    num_duplicates = draw(st.integers(min_value=2, max_value=5))
    duplicates: list[CandidateLink] = []

    for _ in range(num_duplicates):
        link = draw(
            st_candidate_link(
                requirement_id=st.just(req_id),
                test_case_id=st.just(tc_id),
            )
        )
        duplicates.append(link)

    return duplicates


@st.composite
def st_mixed_link_set(draw: st.DrawFn) -> list[CandidateLink]:
    """Generate a mixed set of candidate links with some duplicates and some unique.

    Returns:
        List of CandidateLink instances with a mix of unique and duplicate pairs.
    """
    links: list[CandidateLink] = []

    # Generate 1-3 duplicate groups
    num_groups = draw(st.integers(min_value=1, max_value=3))
    for _ in range(num_groups):
        group = draw(st_duplicate_link_set())
        links.extend(group)

    # Generate 0-3 unique links (different pairs)
    num_unique = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_unique):
        link = draw(st_candidate_link())
        links.append(link)

    return links


# ---------------------------------------------------------------------------
# Property 2: Link Deduplication — Unique Pair Guarantee
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(links=st_mixed_link_set())
def test_each_pair_appears_exactly_once_after_deduplication(
    links: list[CandidateLink],
) -> None:
    """After deduplication, each unique (requirement_id, test_case_id) pair
    SHALL appear exactly once in the output.

    **Validates: Requirements 1.7**
    """
    service = TraceabilityMatrixService()
    deduplicated = service.deduplicate_links(links)

    # Collect all (req_id, tc_id) pairs in output
    output_pairs = [(link.requirement_id, link.test_case_id) for link in deduplicated]

    # Each pair should be unique
    assert len(output_pairs) == len(set(output_pairs))


# ---------------------------------------------------------------------------
# Property 2: Link Deduplication — Highest Confidence Retained
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(links=st_duplicate_link_set())
def test_retained_link_has_highest_confidence(
    links: list[CandidateLink],
) -> None:
    """For duplicate (requirement_id, test_case_id) pairs, the retained link
    SHALL have the highest confidence score among all duplicates for that pair.

    **Validates: Requirements 1.7**
    """
    service = TraceabilityMatrixService()
    deduplicated = service.deduplicate_links(links)

    # All links share the same pair, so output should be exactly 1
    assert len(deduplicated) == 1

    retained = deduplicated[0]
    max_confidence = max(link.link_confidence for link in links)

    assert retained.link_confidence == max_confidence


# ---------------------------------------------------------------------------
# Property 2: Link Deduplication — All Methods Recorded
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(links=st_duplicate_link_set())
def test_all_detection_methods_recorded_in_methods_list(
    links: list[CandidateLink],
) -> None:
    """All detection methods from duplicates SHALL be recorded in the
    link_methods list for that pair.

    **Validates: Requirements 1.7**
    """
    service = TraceabilityMatrixService()
    deduplicated = service.deduplicate_links(links)

    assert len(deduplicated) == 1
    retained = deduplicated[0]

    # Get the methods list via get_link_methods
    methods = service.get_link_methods(retained.requirement_id, retained.test_case_id)

    # All unique methods from input should be present
    input_methods = set(link.link_method for link in links)
    assert input_methods == set(methods)


# ---------------------------------------------------------------------------
# Property 2: Link Deduplication — Output Length <= Input Length
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(links=st_mixed_link_set())
def test_output_length_is_at_most_input_length(
    links: list[CandidateLink],
) -> None:
    """The deduplicated output length SHALL be <= the input length.

    **Validates: Requirements 1.7**
    """
    service = TraceabilityMatrixService()
    deduplicated = service.deduplicate_links(links)

    assert len(deduplicated) <= len(links)


# ---------------------------------------------------------------------------
# Property 2: Link Deduplication — No Pairs Lost
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(links=st_mixed_link_set())
def test_no_unique_pairs_lost_during_deduplication(
    links: list[CandidateLink],
) -> None:
    """All unique (requirement_id, test_case_id) pairs from the input SHALL
    appear in the output. No links are lost.

    **Validates: Requirements 1.7**
    """
    service = TraceabilityMatrixService()
    deduplicated = service.deduplicate_links(links)

    # Collect all unique pairs from input
    input_pairs = set(
        (link.requirement_id, link.test_case_id) for link in links
    )

    # Collect all pairs from output
    output_pairs = set(
        (link.requirement_id, link.test_case_id) for link in deduplicated
    )

    # Every input pair must appear in output
    assert input_pairs == output_pairs
