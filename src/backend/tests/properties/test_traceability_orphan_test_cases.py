"""Property-based tests for orphan test case identification in OrphanDetectionService.

Property 5: Orphan Test Case Identification

Generate random test cases and links with various confidence scores, verify:
- Orphan set = test cases with zero links >= 0.5
- Count = total_test_cases - linked_test_cases

**Validates: Requirements 3.1**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/orphan_detection.py
"""

from __future__ import annotations

import asyncio

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.orphan_detection import OrphanDetectionService
from alcoabase.services.traceability_matrix import CandidateLink, ExtractedTestCase


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LINK_CONFIDENCE_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Test case IDs matching expected patterns
TC_ID_STRATEGY = st.one_of(
    st.integers(min_value=1, max_value=999).map(lambda n: f"TC-{n:03d}"),
    st.integers(min_value=1, max_value=999).map(lambda n: f"IQ-{n:03d}"),
    st.integers(min_value=1, max_value=999).map(lambda n: f"OQ-{n:03d}"),
    st.integers(min_value=1, max_value=999).map(lambda n: f"PQ-{n:03d}"),
)

# Requirement IDs for links
REQ_ID_STRATEGY = st.integers(min_value=1, max_value=999).map(
    lambda n: f"REQ-{n:03d}"
)

# Document UUIDs (12-char hex strings)
DOC_UUID = st.text(
    alphabet="abcdef0123456789",
    min_size=12,
    max_size=12,
)

# Section headings
SECTION = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
)

# Simple text for test case descriptions
SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    min_size=5,
    max_size=100,
)

# Confidence scores above threshold (test case is linked)
ABOVE_THRESHOLD = st.floats(
    min_value=0.5,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Confidence scores below threshold (test case is NOT linked)
BELOW_THRESHOLD = st.floats(
    min_value=0.0,
    max_value=0.4999999,
    allow_nan=False,
    allow_infinity=False,
)

# Any confidence score
ANY_CONFIDENCE = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Link methods
LINK_METHOD = st.sampled_from(["exact_id_match", "cross_reference", "semantic_match"])


@st.composite
def st_test_case(draw: st.DrawFn, tc_id: str | None = None) -> ExtractedTestCase:
    """Generate a random ExtractedTestCase with an optional fixed ID."""
    return ExtractedTestCase(
        test_case_id=tc_id if tc_id is not None else draw(TC_ID_STRATEGY),
        test_case_text=draw(SAFE_TEXT),
        target_document_uuid=draw(DOC_UUID),
        target_section=draw(SECTION),
        expected_result=None,
    )


@st.composite
def st_candidate_link(
    draw: st.DrawFn,
    test_case_id: str | None = None,
    confidence: st.SearchStrategy[float] | None = None,
) -> CandidateLink:
    """Generate a random CandidateLink with optional fixed test_case_id and confidence."""
    return CandidateLink(
        requirement_id=draw(REQ_ID_STRATEGY),
        requirement_text=draw(SAFE_TEXT),
        source_document_uuid=draw(DOC_UUID),
        source_section=draw(SECTION),
        test_case_id=test_case_id if test_case_id is not None else draw(TC_ID_STRATEGY),
        test_case_text=draw(SAFE_TEXT),
        target_document_uuid=draw(DOC_UUID),
        target_section=draw(SECTION),
        link_confidence=draw(confidence if confidence is not None else ANY_CONFIDENCE),
        link_method=draw(LINK_METHOD),
    )


@st.composite
def st_test_cases_and_links(draw: st.DrawFn) -> tuple[
    list[ExtractedTestCase],
    list[CandidateLink],
]:
    """Generate a set of test cases and links with various confidence scores.

    Some test cases will have links above threshold (linked), some below
    threshold only (orphans), and some with no links at all (orphans).
    """
    # Generate unique test case IDs
    num_test_cases = draw(st.integers(min_value=1, max_value=15))
    tc_ids = [f"TC-{i:04d}" for i in range(num_test_cases)]

    # Generate test cases
    test_cases = [draw(st_test_case(tc_id=tc_id)) for tc_id in tc_ids]

    # Decide which test cases get links above threshold
    num_linked = draw(st.integers(min_value=0, max_value=num_test_cases))
    linked_ids = tc_ids[:num_linked]
    unlinked_ids = tc_ids[num_linked:]

    links: list[CandidateLink] = []

    # Create links above threshold for linked test cases
    for tc_id in linked_ids:
        num_links = draw(st.integers(min_value=1, max_value=3))
        for _ in range(num_links):
            link = draw(st_candidate_link(test_case_id=tc_id, confidence=ABOVE_THRESHOLD))
            links.append(link)

    # Optionally create links below threshold for some unlinked test cases
    for tc_id in unlinked_ids:
        has_below_threshold_link = draw(st.booleans())
        if has_below_threshold_link:
            link = draw(
                st_candidate_link(test_case_id=tc_id, confidence=BELOW_THRESHOLD)
            )
            links.append(link)

    return test_cases, links


# ---------------------------------------------------------------------------
# Property 5a: Orphan set equals test cases with zero links >= 0.5
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_test_cases_and_links())
def test_orphan_set_equals_test_cases_with_no_links_above_threshold(
    data: tuple[list[ExtractedTestCase], list[CandidateLink]],
) -> None:
    """A test case SHALL be classified as orphan if and only if it has
    zero Traceability_Links with link_confidence >= 0.5.

    **Validates: Requirements 3.1**
    """
    test_cases, links = data

    service = OrphanDetectionService()
    orphans = asyncio.run(
        service.identify_orphan_test_cases(test_cases, links)
    )

    # Compute expected orphan IDs: test cases with no link >= 0.5
    linked_tc_ids: set[str] = set()
    for link in links:
        if link.link_confidence >= _LINK_CONFIDENCE_THRESHOLD:
            linked_tc_ids.add(link.test_case_id)

    expected_orphan_ids = {
        tc.test_case_id for tc in test_cases if tc.test_case_id not in linked_tc_ids
    }

    actual_orphan_ids = {orphan.test_case_id for orphan in orphans}

    assert actual_orphan_ids == expected_orphan_ids


# ---------------------------------------------------------------------------
# Property 5b: Orphan count = total_test_cases - linked_test_cases
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st_test_cases_and_links())
def test_orphan_count_equals_total_minus_linked(
    data: tuple[list[ExtractedTestCase], list[CandidateLink]],
) -> None:
    """The number of orphan test cases SHALL equal total_test_cases minus
    the count of test cases that have at least one link with
    link_confidence >= 0.5.

    **Validates: Requirements 3.1**
    """
    test_cases, links = data

    service = OrphanDetectionService()
    orphans = asyncio.run(
        service.identify_orphan_test_cases(test_cases, links)
    )

    # Compute linked test case count
    linked_tc_ids: set[str] = set()
    for link in links:
        if link.link_confidence >= _LINK_CONFIDENCE_THRESHOLD:
            linked_tc_ids.add(link.test_case_id)

    # Only count test cases that actually exist in our test_cases list
    linked_count = len(
        {tc.test_case_id for tc in test_cases if tc.test_case_id in linked_tc_ids}
    )

    expected_orphan_count = len(test_cases) - linked_count
    assert len(orphans) == expected_orphan_count


# ---------------------------------------------------------------------------
# Property 5c: Test case with only below-threshold links is orphan
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    tc_id=TC_ID_STRATEGY,
    confidence=BELOW_THRESHOLD,
    data=st.data(),
)
def test_test_case_with_only_below_threshold_links_is_orphan(
    tc_id: str,
    confidence: float,
    data: st.DataObject,
) -> None:
    """A test case that has links but ALL with confidence < 0.5 SHALL
    be classified as orphan.

    **Validates: Requirements 3.1**
    """
    tc = data.draw(st_test_case(tc_id=tc_id))
    link = data.draw(st_candidate_link(test_case_id=tc_id, confidence=st.just(confidence)))

    service = OrphanDetectionService()
    orphans = asyncio.run(
        service.identify_orphan_test_cases([tc], [link])
    )

    orphan_ids = {o.test_case_id for o in orphans}
    assert tc_id in orphan_ids


# ---------------------------------------------------------------------------
# Property 5d: Test case with at least one above-threshold link is NOT orphan
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    tc_id=TC_ID_STRATEGY,
    confidence=ABOVE_THRESHOLD,
    data=st.data(),
)
def test_test_case_with_above_threshold_link_is_not_orphan(
    tc_id: str,
    confidence: float,
    data: st.DataObject,
) -> None:
    """A test case that has at least one link with confidence >= 0.5
    SHALL NOT be classified as orphan.

    **Validates: Requirements 3.1**
    """
    tc = data.draw(st_test_case(tc_id=tc_id))
    link = data.draw(st_candidate_link(test_case_id=tc_id, confidence=st.just(confidence)))

    service = OrphanDetectionService()
    orphans = asyncio.run(
        service.identify_orphan_test_cases([tc], [link])
    )

    orphan_ids = {o.test_case_id for o in orphans}
    assert tc_id not in orphan_ids


# ---------------------------------------------------------------------------
# Property 5e: Empty test cases list produces empty orphan list
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(links=st.lists(st_candidate_link(), min_size=0, max_size=5))
def test_empty_test_cases_produces_empty_orphans(
    links: list[CandidateLink],
) -> None:
    """When no test cases are provided, the orphan list SHALL be empty.

    **Validates: Requirements 3.1**
    """
    service = OrphanDetectionService()
    orphans = asyncio.run(
        service.identify_orphan_test_cases([], links)
    )

    assert orphans == []
