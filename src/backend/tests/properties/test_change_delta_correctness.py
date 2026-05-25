"""Property-based tests for change delta correctness.

Property 7: Change Delta Correctness

For any two consecutive document versions, the computed Change_Delta SHALL
correctly partition all sections into exactly one of: sections_added (present
in new, absent in old), sections_modified (present in both with different
content), or sections_deleted (present in old, absent in new). The union of
these three sets SHALL equal the symmetric difference of sections between the
two versions.

**Validates: Requirements 2.6**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_analysis.py
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.impact_analysis import ImpactAnalysisService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Section titles: realistic document section headings
SECTION_TITLES = st.from_regex(
    r"[A-Z][a-z]{2,10}( [A-Z][a-z]{2,10}){0,3}", fullmatch=True
)

# Section content: non-empty text representing section body
SECTION_CONTENT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=200,
)

# Generate a sections dict (title -> content) representing a document version
SECTIONS_DICT = st.dictionaries(
    keys=SECTION_TITLES,
    values=SECTION_CONTENT,
    min_size=0,
    max_size=15,
)


@st.composite
def st_section_pairs(draw: st.DrawFn) -> tuple[dict[str, str], dict[str, str]]:
    """Generate a pair of old_sections and new_sections dicts.

    Ensures a mix of added, modified, deleted, and unchanged sections
    by drawing two independent section dicts.
    """
    old_sections = draw(SECTIONS_DICT)
    new_sections = draw(SECTIONS_DICT)
    return old_sections, new_sections


@st.composite
def st_section_pairs_with_overlap(
    draw: st.DrawFn,
) -> tuple[dict[str, str], dict[str, str]]:
    """Generate section pairs with guaranteed overlap (some shared titles).

    This ensures we test the modified-section detection path where
    sections exist in both versions but with different content.
    """
    # Generate a base set of shared titles
    shared_titles = draw(
        st.lists(SECTION_TITLES, min_size=1, max_size=5, unique=True)
    )

    # Generate old content for shared titles
    old_sections: dict[str, str] = {}
    for title in shared_titles:
        old_sections[title] = draw(SECTION_CONTENT)

    # Generate new content for shared titles (may differ)
    new_sections: dict[str, str] = {}
    for title in shared_titles:
        new_sections[title] = draw(SECTION_CONTENT)

    # Add some unique sections to old only (will be deleted)
    old_only_count = draw(st.integers(min_value=0, max_value=3))
    for _ in range(old_only_count):
        title = draw(SECTION_TITLES.filter(lambda t: t not in old_sections and t not in new_sections))
        old_sections[title] = draw(SECTION_CONTENT)

    # Add some unique sections to new only (will be added)
    new_only_count = draw(st.integers(min_value=0, max_value=3))
    for _ in range(new_only_count):
        title = draw(SECTION_TITLES.filter(lambda t: t not in old_sections and t not in new_sections))
        new_sections[title] = draw(SECTION_CONTENT)

    return old_sections, new_sections


# ---------------------------------------------------------------------------
# Helper: instantiate the service for pure-logic testing
# ---------------------------------------------------------------------------


def compute_diff(
    old_sections: dict[str, str], new_sections: dict[str, str]
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Call _compute_section_diff on the ImpactAnalysisService.

    Instantiates the service without dependencies (no DB, no inference)
    since _compute_section_diff is a pure function.
    """
    service = ImpactAnalysisService()
    return service._compute_section_diff(old_sections, new_sections)


# ---------------------------------------------------------------------------
# Property 7: Change Delta Correctness — Correct Partitioning
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_added_sections_present_in_new_absent_in_old(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """Every section in sections_added SHALL be present in new_sections
    and absent from old_sections.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    for item in added:
        title = item["title"]
        assert title in new_sections, (
            f"Added section '{title}' not found in new_sections"
        )
        assert title not in old_sections, (
            f"Added section '{title}' should not be in old_sections"
        )


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_deleted_sections_present_in_old_absent_in_new(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """Every section in sections_deleted SHALL be present in old_sections
    and absent from new_sections.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    for item in deleted:
        title = item["title"]
        assert title in old_sections, (
            f"Deleted section '{title}' not found in old_sections"
        )
        assert title not in new_sections, (
            f"Deleted section '{title}' should not be in new_sections"
        )


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_modified_sections_present_in_both_with_different_content(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """Every section in sections_modified SHALL be present in both
    old_sections and new_sections with different content.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    for item in modified:
        title = item["title"]
        assert title in old_sections, (
            f"Modified section '{title}' not found in old_sections"
        )
        assert title in new_sections, (
            f"Modified section '{title}' not found in new_sections"
        )
        assert old_sections[title] != new_sections[title], (
            f"Modified section '{title}' has identical content in both versions"
        )


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_sections_partitioned_into_exactly_one_category(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """Each section title that appears in either version SHALL appear in
    exactly one of: sections_added, sections_modified, or sections_deleted.
    No section title SHALL appear in more than one category.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    added_titles = {item["title"] for item in added}
    modified_titles = {item["title"] for item in modified}
    deleted_titles = {item["title"] for item in deleted}

    # No overlap between categories
    assert added_titles.isdisjoint(modified_titles), (
        f"Overlap between added and modified: {added_titles & modified_titles}"
    )
    assert added_titles.isdisjoint(deleted_titles), (
        f"Overlap between added and deleted: {added_titles & deleted_titles}"
    )
    assert modified_titles.isdisjoint(deleted_titles), (
        f"Overlap between modified and deleted: {modified_titles & deleted_titles}"
    )


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_union_equals_symmetric_difference_plus_modified(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """The union of sections_added titles and sections_deleted titles SHALL
    equal the symmetric difference of section titles between old and new.
    The sections_modified titles SHALL be a subset of the intersection of
    old and new section titles.

    Together, added + modified + deleted covers all sections that changed.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    old_titles = set(old_sections.keys())
    new_titles = set(new_sections.keys())

    added_titles = {item["title"] for item in added}
    modified_titles = {item["title"] for item in modified}
    deleted_titles = {item["title"] for item in deleted}

    # Added + deleted = symmetric difference of titles
    symmetric_diff = old_titles ^ new_titles
    assert added_titles | deleted_titles == symmetric_diff, (
        f"Added ∪ Deleted ({added_titles | deleted_titles}) != "
        f"symmetric difference ({symmetric_diff})"
    )

    # Modified titles must be a subset of the intersection
    intersection = old_titles & new_titles
    assert modified_titles <= intersection, (
        f"Modified titles ({modified_titles}) not subset of "
        f"intersection ({intersection})"
    )


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_unchanged_sections_not_in_any_category(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """Sections present in both old and new with identical content SHALL NOT
    appear in any of the three categories (added, modified, deleted).

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    added_titles = {item["title"] for item in added}
    modified_titles = {item["title"] for item in modified}
    deleted_titles = {item["title"] for item in deleted}

    all_categorized = added_titles | modified_titles | deleted_titles

    # Find unchanged sections (same title, same content)
    old_titles = set(old_sections.keys())
    new_titles = set(new_sections.keys())
    common_titles = old_titles & new_titles
    unchanged_titles = {
        title for title in common_titles
        if old_sections[title] == new_sections[title]
    }

    # Unchanged sections must not appear in any category
    assert unchanged_titles.isdisjoint(all_categorized), (
        f"Unchanged sections found in categories: "
        f"{unchanged_titles & all_categorized}"
    )


@settings(max_examples=100)
@given(sections=st_section_pairs_with_overlap())
def test_content_preserved_in_added_sections(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """For each section in sections_added, the content field SHALL match
    the content from new_sections.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    for item in added:
        title = item["title"]
        assert item["content"] == new_sections[title], (
            f"Added section '{title}' content mismatch"
        )


@settings(max_examples=100)
@given(sections=st_section_pairs_with_overlap())
def test_content_preserved_in_deleted_sections(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """For each section in sections_deleted, the content field SHALL match
    the content from old_sections.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    for item in deleted:
        title = item["title"]
        assert item["content"] == old_sections[title], (
            f"Deleted section '{title}' content mismatch"
        )


@settings(max_examples=100)
@given(sections=st_section_pairs_with_overlap())
def test_content_preserved_in_modified_sections(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """For each section in sections_modified, the content field SHALL match
    the new content and previous_content SHALL match the old content.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    for item in modified:
        title = item["title"]
        assert item["content"] == new_sections[title], (
            f"Modified section '{title}' new content mismatch"
        )
        assert item["previous_content"] == old_sections[title], (
            f"Modified section '{title}' previous content mismatch"
        )


@settings(max_examples=100)
@given(sections=st_section_pairs())
def test_completeness_all_changed_sections_accounted_for(
    sections: tuple[dict[str, str], dict[str, str]],
) -> None:
    """The total number of sections in added + modified + deleted SHALL
    account for all sections that differ between old and new versions.
    Specifically: |added| + |deleted| + |modified| == |symmetric_diff| + |modified|.

    **Validates: Requirements 2.6**
    """
    old_sections, new_sections = sections
    added, modified, deleted = compute_diff(old_sections, new_sections)

    old_titles = set(old_sections.keys())
    new_titles = set(new_sections.keys())

    # Expected counts
    expected_added = len(new_titles - old_titles)
    expected_deleted = len(old_titles - new_titles)
    expected_modified = sum(
        1 for title in (old_titles & new_titles)
        if old_sections[title] != new_sections[title]
    )

    assert len(added) == expected_added, (
        f"Expected {expected_added} added sections, got {len(added)}"
    )
    assert len(deleted) == expected_deleted, (
        f"Expected {expected_deleted} deleted sections, got {len(deleted)}"
    )
    assert len(modified) == expected_modified, (
        f"Expected {expected_modified} modified sections, got {len(modified)}"
    )
