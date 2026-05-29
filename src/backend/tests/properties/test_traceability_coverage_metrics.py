"""Property-based tests for coverage metrics computation.

Property 11: Coverage Metrics Computation

Generate random requirement/link sets, verify:
- coverage_percentage = covered/total * 100 (2 decimal places)
- average_link_confidence = mean of all confidences (2 decimal places)
- Handle zero-total edge case (0.00 when no requirements or no links)

**Validates: Requirements 7.1**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/coverage_metrics.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.coverage_metrics import compute_coverage_metrics
from alcoabase.services.traceability_matrix import (
    CandidateLink,
    ExtractedRequirement,
    ExtractedTestCase,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

DOC_UUID = st.text(
    alphabet="abcdef0123456789",
    min_size=12,
    max_size=12,
)

SECTION = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
)

SAFE_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    min_size=5,
    max_size=80,
)

# Link confidence values in valid range [0.0, 1.0]
CONFIDENCE = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
)

LINK_METHOD = st.sampled_from(["exact_id_match", "cross_reference", "semantic_match"])


@st.composite
def st_requirement(draw: st.DrawFn, doc_uuid: str | None = None) -> ExtractedRequirement:
    """Generate a random ExtractedRequirement."""
    return ExtractedRequirement(
        requirement_id=draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"REQ-{n:03d}")),
        requirement_text=draw(SAFE_TEXT),
        source_document_uuid=doc_uuid or draw(DOC_UUID),
        source_section=draw(SECTION),
        acceptance_criteria=None,
    )


@st.composite
def st_test_case(draw: st.DrawFn, doc_uuid: str | None = None) -> ExtractedTestCase:
    """Generate a random ExtractedTestCase."""
    return ExtractedTestCase(
        test_case_id=draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"TC-{n:03d}")),
        test_case_text=draw(SAFE_TEXT),
        target_document_uuid=doc_uuid or draw(DOC_UUID),
        target_section=draw(SECTION),
        expected_result=None,
    )


@st.composite
def st_candidate_link(
    draw: st.DrawFn,
    requirement_ids: list[str] | None = None,
    test_case_ids: list[str] | None = None,
) -> CandidateLink:
    """Generate a random CandidateLink referencing given IDs if provided."""
    req_id = draw(st.sampled_from(requirement_ids)) if requirement_ids else draw(
        st.integers(min_value=1, max_value=9999).map(lambda n: f"REQ-{n:03d}")
    )
    tc_id = draw(st.sampled_from(test_case_ids)) if test_case_ids else draw(
        st.integers(min_value=1, max_value=9999).map(lambda n: f"TC-{n:03d}")
    )
    return CandidateLink(
        requirement_id=req_id,
        requirement_text=draw(SAFE_TEXT),
        source_document_uuid=draw(DOC_UUID),
        source_section=draw(SECTION),
        test_case_id=tc_id,
        test_case_text=draw(SAFE_TEXT),
        target_document_uuid=draw(DOC_UUID),
        target_section=draw(SECTION),
        link_confidence=draw(CONFIDENCE),
        link_method=draw(LINK_METHOD),
    )


# ---------------------------------------------------------------------------
# Property 11a: coverage_percentage = covered/total * 100 (2 decimal places)
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_coverage_percentage_formula(data: st.DataObject) -> None:
    """coverage_percentage SHALL equal (covered_requirements / total_requirements) * 100,
    rounded to 2 decimal places. A requirement is "covered" if it has at least one
    link with link_confidence >= 0.5.

    **Validates: Requirements 7.1**
    """
    # Generate 1-20 requirements with unique IDs
    num_reqs = data.draw(st.integers(min_value=1, max_value=20))
    src_uuid = data.draw(DOC_UUID)
    requirements = [
        ExtractedRequirement(
            requirement_id=f"REQ-{i:03d}",
            requirement_text=f"Requirement {i}",
            source_document_uuid=src_uuid,
            source_section="Section 1",
            acceptance_criteria=None,
        )
        for i in range(num_reqs)
    ]

    # Generate 1-10 test cases
    num_tcs = data.draw(st.integers(min_value=1, max_value=10))
    tgt_uuid = data.draw(DOC_UUID)
    test_cases = [
        ExtractedTestCase(
            test_case_id=f"TC-{i:03d}",
            test_case_text=f"Test case {i}",
            target_document_uuid=tgt_uuid,
            target_section="Section 2",
            expected_result=None,
        )
        for i in range(num_tcs)
    ]

    # Generate random links referencing the requirement/test case IDs
    req_ids = [r.requirement_id for r in requirements]
    tc_ids = [tc.test_case_id for tc in test_cases]
    num_links = data.draw(st.integers(min_value=0, max_value=30))
    links = [
        data.draw(st_candidate_link(requirement_ids=req_ids, test_case_ids=tc_ids))
        for _ in range(num_links)
    ]

    source_docs = [{"document_uuid": src_uuid}]
    target_docs = [{"document_uuid": tgt_uuid}]

    metrics = compute_coverage_metrics(requirements, test_cases, links, source_docs, target_docs)

    # Manually compute expected coverage
    covered_ids: set[str] = set()
    for link in links:
        if link.link_confidence >= 0.5:
            covered_ids.add(link.requirement_id)

    total = len(requirements)
    covered = len(covered_ids)
    expected_percentage = round((covered / total) * 100, 2)

    assert metrics["coverage_percentage"] == expected_percentage
    assert metrics["total_requirements"] == total
    assert metrics["covered_requirements"] == covered
    assert metrics["orphan_requirements_count"] == total - covered


# ---------------------------------------------------------------------------
# Property 11b: average_link_confidence = mean of all confidences (2 decimals)
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_average_link_confidence_formula(data: st.DataObject) -> None:
    """average_link_confidence SHALL equal the arithmetic mean of all
    link_confidence values across established links, rounded to 2 decimal
    places.

    **Validates: Requirements 7.1**
    """
    # Generate at least 1 link to test the mean computation
    num_links = data.draw(st.integers(min_value=1, max_value=50))
    src_uuid = data.draw(DOC_UUID)
    tgt_uuid = data.draw(DOC_UUID)

    requirements = [
        ExtractedRequirement(
            requirement_id="REQ-001",
            requirement_text="Requirement 1",
            source_document_uuid=src_uuid,
            source_section="Section 1",
        )
    ]
    test_cases = [
        ExtractedTestCase(
            test_case_id="TC-001",
            test_case_text="Test case 1",
            target_document_uuid=tgt_uuid,
            target_section="Section 2",
        )
    ]

    links = [
        data.draw(st_candidate_link(requirement_ids=["REQ-001"], test_case_ids=["TC-001"]))
        for _ in range(num_links)
    ]

    source_docs = [{"document_uuid": src_uuid}]
    target_docs = [{"document_uuid": tgt_uuid}]

    metrics = compute_coverage_metrics(requirements, test_cases, links, source_docs, target_docs)

    # Manually compute expected average
    expected_avg = round(sum(link.link_confidence for link in links) / len(links), 2)

    assert metrics["average_link_confidence"] == expected_avg


# ---------------------------------------------------------------------------
# Property 11c: Zero-total edge case — 0.00 when no requirements
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    tgt_uuid=DOC_UUID,
    src_uuid=DOC_UUID,
)
def test_zero_requirements_yields_zero_coverage(tgt_uuid: str, src_uuid: str) -> None:
    """When total_requirements is 0, coverage_percentage SHALL be 0.00
    (avoiding division by zero).

    **Validates: Requirements 7.1**
    """
    requirements: list[ExtractedRequirement] = []
    test_cases = [
        ExtractedTestCase(
            test_case_id="TC-001",
            test_case_text="Test case 1",
            target_document_uuid=tgt_uuid,
            target_section="Section 1",
        )
    ]
    links: list[CandidateLink] = []

    source_docs = [{"document_uuid": src_uuid}]
    target_docs = [{"document_uuid": tgt_uuid}]

    metrics = compute_coverage_metrics(requirements, test_cases, links, source_docs, target_docs)

    assert metrics["coverage_percentage"] == 0.00
    assert metrics["total_requirements"] == 0
    assert metrics["covered_requirements"] == 0
    assert metrics["orphan_requirements_count"] == 0


# ---------------------------------------------------------------------------
# Property 11d: Zero links — average_link_confidence is 0.00
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(data=st.data())
def test_zero_links_yields_zero_average_confidence(data: st.DataObject) -> None:
    """When no links exist, average_link_confidence SHALL be 0.00
    (avoiding division by zero).

    **Validates: Requirements 7.1**
    """
    src_uuid = data.draw(DOC_UUID)
    tgt_uuid = data.draw(DOC_UUID)
    num_reqs = data.draw(st.integers(min_value=1, max_value=10))

    requirements = [
        ExtractedRequirement(
            requirement_id=f"REQ-{i:03d}",
            requirement_text=f"Requirement {i}",
            source_document_uuid=src_uuid,
            source_section="Section 1",
        )
        for i in range(num_reqs)
    ]
    test_cases = [
        ExtractedTestCase(
            test_case_id="TC-001",
            test_case_text="Test case 1",
            target_document_uuid=tgt_uuid,
            target_section="Section 2",
        )
    ]
    links: list[CandidateLink] = []

    source_docs = [{"document_uuid": src_uuid}]
    target_docs = [{"document_uuid": tgt_uuid}]

    metrics = compute_coverage_metrics(requirements, test_cases, links, source_docs, target_docs)

    assert metrics["average_link_confidence"] == 0.00
    # All requirements are orphans when no links exist
    assert metrics["orphan_requirements_count"] == num_reqs
    assert metrics["coverage_percentage"] == 0.00


# ---------------------------------------------------------------------------
# Property 11e: Both zero requirements and zero links
# ---------------------------------------------------------------------------


@settings(max_examples=30)
@given(
    src_uuid=DOC_UUID,
    tgt_uuid=DOC_UUID,
)
def test_empty_inputs_yield_all_zeros(src_uuid: str, tgt_uuid: str) -> None:
    """When both requirements and links are empty, all coverage metrics
    SHALL be 0 or 0.00.

    **Validates: Requirements 7.1**
    """
    requirements: list[ExtractedRequirement] = []
    test_cases: list[ExtractedTestCase] = []
    links: list[CandidateLink] = []

    source_docs = [{"document_uuid": src_uuid}]
    target_docs = [{"document_uuid": tgt_uuid}]

    metrics = compute_coverage_metrics(requirements, test_cases, links, source_docs, target_docs)

    assert metrics["total_requirements"] == 0
    assert metrics["covered_requirements"] == 0
    assert metrics["orphan_requirements_count"] == 0
    assert metrics["coverage_percentage"] == 0.00
    assert metrics["total_test_cases"] == 0
    assert metrics["linked_test_cases"] == 0
    assert metrics["orphan_test_cases_count"] == 0
    assert metrics["average_link_confidence"] == 0.00
