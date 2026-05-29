"""Property-based tests for orphan requirement identification in OrphanDetectionService.

Property 4: Orphan Requirement Identification

Generate random requirements and links with various confidence scores, verify:
- orphan set = requirements with zero links >= 0.5
- count = total_requirements - covered_requirements

**Validates: Requirements 1.12, 2.1**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/orphan_detection.py
"""

from __future__ import annotations

import asyncio

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from alcoabase.services.orphan_detection import OrphanDetectionService
from alcoabase.services.traceability_matrix import (
    CandidateLink,
    ExtractedRequirement,
)


def _run_async(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Requirement IDs matching the patterns used by the traceability engine
REQ_ID_STRATEGY = st.one_of(
    st.integers(min_value=1, max_value=99999).map(lambda n: f"REQ-{n:03d}"),
    st.tuples(
        st.integers(min_value=1, max_value=999),
        st.integers(min_value=1, max_value=999),
    ).map(lambda t: f"URS-{t[0]}.{t[1]}"),
    st.tuples(
        st.integers(min_value=1, max_value=999),
        st.integers(min_value=1, max_value=999),
    ).map(lambda t: f"R.{t[0]}.{t[1]}"),
)

# Test case IDs
TC_ID_STRATEGY = st.integers(min_value=1, max_value=999).map(
    lambda n: f"TC-{n:03d}"
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

# Simple requirement text (no special keywords to avoid severity classification issues)
REQ_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    min_size=5,
    max_size=100,
)

# Confidence scores above the 0.5 threshold (requirement is covered)
ABOVE_THRESHOLD = st.floats(
    min_value=0.5,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

# Confidence scores below the 0.5 threshold (requirement is NOT covered)
BELOW_THRESHOLD = st.floats(
    min_value=0.0,
    max_value=0.4999999,
    allow_nan=False,
    allow_infinity=False,
)

# Any confidence score in [0.0, 1.0]
ANY_CONFIDENCE = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

LINK_METHOD = st.sampled_from(["exact_id_match", "cross_reference", "semantic_match"])


@st.composite
def st_requirement(draw: st.DrawFn) -> ExtractedRequirement:
    """Generate a random ExtractedRequirement with a unique ID."""
    return ExtractedRequirement(
        requirement_id=draw(REQ_ID_STRATEGY),
        requirement_text=draw(REQ_TEXT),
        source_document_uuid=draw(DOC_UUID),
        source_section=draw(SECTION),
        acceptance_criteria=None,
    )


@st.composite
def st_unique_requirements(
    draw: st.DrawFn, min_size: int = 1, max_size: int = 10
) -> list[ExtractedRequirement]:
    """Generate a list of requirements with unique IDs."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    # Use sequential IDs to guarantee uniqueness without retries
    reqs: list[ExtractedRequirement] = []
    for i in range(count):
        reqs.append(
            ExtractedRequirement(
                requirement_id=f"REQ-{i + 1:03d}",
                requirement_text=draw(REQ_TEXT),
                source_document_uuid=draw(DOC_UUID),
                source_section=draw(SECTION),
                acceptance_criteria=None,
            )
        )
    return reqs


@st.composite
def st_candidate_link(
    draw: st.DrawFn,
    requirement_id: str,
    confidence: st.SearchStrategy[float] = ANY_CONFIDENCE,
) -> CandidateLink:
    """Generate a CandidateLink for a given requirement ID with specified confidence."""
    return CandidateLink(
        requirement_id=requirement_id,
        requirement_text=draw(REQ_TEXT),
        source_document_uuid=draw(DOC_UUID),
        source_section=draw(SECTION),
        test_case_id=draw(TC_ID_STRATEGY),
        test_case_text=draw(REQ_TEXT),
        target_document_uuid=draw(DOC_UUID),
        target_section=draw(SECTION),
        link_confidence=draw(confidence),
        link_method=draw(LINK_METHOD),
    )


# ---------------------------------------------------------------------------
# Property 4a: Requirements with zero links >= 0.5 are orphans
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_requirements_with_no_links_above_threshold_are_orphans(
    data: st.DataObject,
) -> None:
    """A requirement SHALL be classified as orphan if it has zero
    Traceability_Links with link_confidence >= 0.5.

    Generate requirements with only below-threshold links and verify
    they appear in the orphan set.

    **Validates: Requirements 1.12, 2.1**
    """
    reqs = data.draw(st_unique_requirements(min_size=1, max_size=5))

    # Create links for all requirements but only with confidence < 0.5
    links: list[CandidateLink] = []
    for req in reqs:
        num_links = data.draw(st.integers(min_value=0, max_value=3))
        for _ in range(num_links):
            link = data.draw(st_candidate_link(req.requirement_id, BELOW_THRESHOLD))
            links.append(link)

    service = OrphanDetectionService()
    orphans = _run_async(service.identify_orphan_requirements(reqs, links))

    # All requirements should be orphans since no link has confidence >= 0.5
    orphan_ids = {o.requirement_id for o in orphans}
    expected_ids = {r.requirement_id for r in reqs}
    assert orphan_ids == expected_ids


# ---------------------------------------------------------------------------
# Property 4b: Requirements with at least one link >= 0.5 are NOT orphans
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_requirements_with_links_above_threshold_are_not_orphans(
    data: st.DataObject,
) -> None:
    """A requirement with at least one Traceability_Link with
    link_confidence >= 0.5 SHALL NOT be classified as orphan.

    **Validates: Requirements 1.12, 2.1**
    """
    reqs = data.draw(st_unique_requirements(min_size=1, max_size=5))

    # Create at least one link with confidence >= 0.5 for each requirement
    links: list[CandidateLink] = []
    for req in reqs:
        # One link above threshold guarantees coverage
        link = data.draw(st_candidate_link(req.requirement_id, ABOVE_THRESHOLD))
        links.append(link)
        # Optionally add more links with any confidence
        extra = data.draw(st.integers(min_value=0, max_value=2))
        for _ in range(extra):
            link = data.draw(st_candidate_link(req.requirement_id, ANY_CONFIDENCE))
            links.append(link)

    service = OrphanDetectionService()
    orphans = _run_async(service.identify_orphan_requirements(reqs, links))

    # No requirements should be orphans
    assert len(orphans) == 0


# ---------------------------------------------------------------------------
# Property 4c: Orphan count = total_requirements - covered_requirements
# ---------------------------------------------------------------------------


@settings(max_examples=10, suppress_health_check=[HealthCheck.large_base_example])
@given(data=st.data())
def test_orphan_count_equals_total_minus_covered(
    data: st.DataObject,
) -> None:
    """The number of orphan requirements SHALL equal
    total_requirements - covered_requirements, where covered_requirements
    is the count of requirements with at least one link >= 0.5.

    **Validates: Requirements 1.12, 2.1**
    """
    reqs = data.draw(st_unique_requirements(min_size=2, max_size=8))

    # Randomly decide which requirements are covered vs orphan
    links: list[CandidateLink] = []
    covered_ids: set[str] = set()

    for req in reqs:
        is_covered = data.draw(st.booleans())
        if is_covered:
            # Give this requirement at least one link >= 0.5
            link = data.draw(st_candidate_link(req.requirement_id, ABOVE_THRESHOLD))
            links.append(link)
            covered_ids.add(req.requirement_id)
        else:
            # Only give below-threshold links (or no links)
            num_links = data.draw(st.integers(min_value=0, max_value=2))
            for _ in range(num_links):
                link = data.draw(
                    st_candidate_link(req.requirement_id, BELOW_THRESHOLD)
                )
                links.append(link)

    service = OrphanDetectionService()
    orphans = _run_async(service.identify_orphan_requirements(reqs, links))

    total_requirements = len(reqs)
    covered_requirements = len(covered_ids)
    expected_orphan_count = total_requirements - covered_requirements

    assert len(orphans) == expected_orphan_count


# ---------------------------------------------------------------------------
# Property 4d: Orphan set is exactly the complement of covered set
# ---------------------------------------------------------------------------


@settings(max_examples=10, suppress_health_check=[HealthCheck.large_base_example])
@given(data=st.data())
def test_orphan_set_is_complement_of_covered_set(
    data: st.DataObject,
) -> None:
    """The orphan set SHALL be exactly the set of requirements that have
    zero links with link_confidence >= 0.5. The union of orphan IDs and
    covered IDs equals the full requirement set, with no overlap.

    **Validates: Requirements 1.12, 2.1**
    """
    reqs = data.draw(st_unique_requirements(min_size=2, max_size=8))

    # Generate links with random confidences for random requirements
    links: list[CandidateLink] = []
    for req in reqs:
        num_links = data.draw(st.integers(min_value=0, max_value=3))
        for _ in range(num_links):
            link = data.draw(st_candidate_link(req.requirement_id, ANY_CONFIDENCE))
            links.append(link)

    # Compute expected covered set manually
    covered_ids: set[str] = set()
    for link in links:
        if link.link_confidence >= 0.5:
            covered_ids.add(link.requirement_id)

    all_req_ids = {r.requirement_id for r in reqs}
    expected_orphan_ids = all_req_ids - covered_ids

    service = OrphanDetectionService()
    orphans = _run_async(service.identify_orphan_requirements(reqs, links))

    actual_orphan_ids = {o.requirement_id for o in orphans}

    # Orphan set is exactly the complement of covered set
    assert actual_orphan_ids == expected_orphan_ids
    # Union covers all requirements
    assert actual_orphan_ids | covered_ids == all_req_ids
    # No overlap
    assert actual_orphan_ids & covered_ids == set()


# ---------------------------------------------------------------------------
# Property 4e: Empty requirements produces empty orphan list
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    links=st.lists(
        st_candidate_link("REQ-001", ANY_CONFIDENCE),
        min_size=0,
        max_size=5,
    )
)
def test_empty_requirements_produces_no_orphans(
    links: list[CandidateLink],
) -> None:
    """When the requirements list is empty, the orphan list SHALL be empty
    regardless of what links exist.

    **Validates: Requirements 1.12, 2.1**
    """
    service = OrphanDetectionService()
    orphans = _run_async(service.identify_orphan_requirements([], links))

    assert orphans == []
