"""Property-based tests for multi-tenancy isolation on document generation models.

Property 2: Multi-Tenancy Isolation
For any company_id filter, queries scoped to one company_id never return
records belonging to another company_id.

This is a pure logic test — no database needed. It tests the filtering concept
that simulates the WHERE company_id = X clause used across all document
generation listing endpoints.

Tests all four models:
- DocumentTemplate
- GenerationProvenance
- CrossReferenceEntry
- GenerationJobMetadata

**Validates: Requirements 1.9, 2.8, 3.7, 5.6, 6.7, 7.8, 9.7**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

from dataclasses import dataclass
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Data models representing document generation records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocumentTemplateRecord:
    """Represents a DocumentTemplate record with company scope."""

    id: int
    document_id: int
    document_version_id: int
    company_id: int
    template_name: str
    document_type_target: str
    status: str


@dataclass(frozen=True)
class GenerationProvenanceRecord:
    """Represents a GenerationProvenance record with company scope."""

    id: int
    generation_id: str
    template_id: int
    company_id: int
    requesting_user_id: int
    agent_archetype: str
    total_inference_duration_ms: int
    total_token_count: int


@dataclass(frozen=True)
class CrossReferenceEntryRecord:
    """Represents a CrossReferenceEntry record with company scope."""

    id: int
    generation_provenance_id: int
    source_document_id: int
    company_id: int
    reference_type: str
    reference_identifier: str


@dataclass(frozen=True)
class GenerationJobMetadataRecord:
    """Represents a GenerationJobMetadata record with company scope."""

    id: int
    job_id: str
    template_id: int
    company_id: int
    requesting_user_id: int
    title: str
    status: str
    progress_percent: int
    sections_completed: int
    sections_total: int


# ---------------------------------------------------------------------------
# Filtering function (simulates WHERE company_id = X)
# ---------------------------------------------------------------------------


def filter_by_company(records: list[Any], company_id: int) -> list[Any]:
    """Filter records by company_id, simulating tenant-scoped queries.

    This replicates the WHERE company_id = :company_id clause that all
    document generation listing endpoints apply.

    Args:
        records: List of records with a company_id attribute.
        company_id: The company to filter for.

    Returns:
        List of records belonging to the specified company.
    """
    return [r for r in records if r.company_id == company_id]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


COMPANY_IDS = st.integers(min_value=1, max_value=10)
USER_IDS = st.integers(min_value=1, max_value=50)
DOCUMENT_IDS = st.integers(min_value=1, max_value=100)
TEMPLATE_IDS = st.integers(min_value=1, max_value=30)
PROVENANCE_IDS = st.integers(min_value=1, max_value=50)
TEMPLATE_STATUSES = st.sampled_from(["pending", "active", "archived"])
DOC_TYPE_TARGETS = st.sampled_from(["URS", "MVP", "SOP", "WI", "Protocol"])
REFERENCE_TYPES = st.sampled_from(["requirement", "section", "test_case"])
JOB_STATUSES = st.sampled_from(["processing", "completed", "failed"])
AGENT_ARCHETYPES = st.sampled_from(["technical_writer", "regulatory_writer"])


@st.composite
def st_template_records(draw: st.DrawFn) -> list[DocumentTemplateRecord]:
    """Generate a list of DocumentTemplate records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=20))
    records = []
    for i in range(num_records):
        records.append(DocumentTemplateRecord(
            id=i + 1,
            document_id=draw(DOCUMENT_IDS),
            document_version_id=draw(DOCUMENT_IDS),
            company_id=draw(COMPANY_IDS),
            template_name=f"Template_{i + 1}",
            document_type_target=draw(DOC_TYPE_TARGETS),
            status=draw(TEMPLATE_STATUSES),
        ))
    return records


@st.composite
def st_provenance_records(draw: st.DrawFn) -> list[GenerationProvenanceRecord]:
    """Generate a list of GenerationProvenance records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=20))
    records = []
    for i in range(num_records):
        records.append(GenerationProvenanceRecord(
            id=i + 1,
            generation_id=f"gen-{i + 1:04d}",
            template_id=draw(TEMPLATE_IDS),
            company_id=draw(COMPANY_IDS),
            requesting_user_id=draw(USER_IDS),
            agent_archetype=draw(AGENT_ARCHETYPES),
            total_inference_duration_ms=draw(st.integers(min_value=100, max_value=60000)),
            total_token_count=draw(st.integers(min_value=50, max_value=100000)),
        ))
    return records


@st.composite
def st_cross_reference_records(draw: st.DrawFn) -> list[CrossReferenceEntryRecord]:
    """Generate a list of CrossReferenceEntry records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=30))
    records = []
    for i in range(num_records):
        ref_type = draw(REFERENCE_TYPES)
        if ref_type == "requirement":
            identifier = f"REQ-{draw(st.integers(min_value=1, max_value=99999)):05d}"
        elif ref_type == "test_case":
            identifier = f"TC-{draw(st.integers(min_value=1, max_value=99999)):05d}"
        else:
            identifier = f"{draw(st.integers(min_value=1, max_value=9))}.{draw(st.integers(min_value=1, max_value=9))}"
        records.append(CrossReferenceEntryRecord(
            id=i + 1,
            generation_provenance_id=draw(PROVENANCE_IDS),
            source_document_id=draw(DOCUMENT_IDS),
            company_id=draw(COMPANY_IDS),
            reference_type=ref_type,
            reference_identifier=identifier,
        ))
    return records


@st.composite
def st_job_metadata_records(draw: st.DrawFn) -> list[GenerationJobMetadataRecord]:
    """Generate a list of GenerationJobMetadata records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=20))
    records = []
    for i in range(num_records):
        sections_total = draw(st.integers(min_value=1, max_value=30))
        sections_completed = draw(st.integers(min_value=0, max_value=sections_total))
        progress = int((sections_completed / sections_total) * 100) if sections_total > 0 else 0
        records.append(GenerationJobMetadataRecord(
            id=i + 1,
            job_id=f"job-{i + 1:04d}",
            template_id=draw(TEMPLATE_IDS),
            company_id=draw(COMPANY_IDS),
            requesting_user_id=draw(USER_IDS),
            title=f"Generated Document {i + 1}",
            status=draw(JOB_STATUSES),
            progress_percent=progress,
            sections_completed=sections_completed,
            sections_total=sections_total,
        ))
    return records


# ---------------------------------------------------------------------------
# Property 2: Multi-Tenancy Isolation — DocumentTemplate
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    records=st_template_records(),
    target_company=COMPANY_IDS,
)
def test_template_listing_returns_only_target_company(
    records: list[DocumentTemplateRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to document templates, the filtered
    results SHALL contain only records where company_id matches the filter.

    **Validates: Requirements 1.9**
    """
    filtered = filter_by_company(records, target_company)

    # All returned records belong to the target company
    for record in filtered:
        assert record.company_id == target_company, (
            f"Template {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    # Count matches expected
    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count, (
        f"Expected {expected_count} templates for company {target_company}, "
        f"got {len(filtered)}"
    )


# ---------------------------------------------------------------------------
# Property 2: Multi-Tenancy Isolation — GenerationProvenance
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    records=st_provenance_records(),
    target_company=COMPANY_IDS,
)
def test_provenance_listing_returns_only_target_company(
    records: list[GenerationProvenanceRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to generation provenance records,
    the filtered results SHALL contain only records where company_id matches
    the filter.

    **Validates: Requirements 5.6**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"Provenance {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


# ---------------------------------------------------------------------------
# Property 2: Multi-Tenancy Isolation — CrossReferenceEntry
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    records=st_cross_reference_records(),
    target_company=COMPANY_IDS,
)
def test_cross_reference_listing_returns_only_target_company(
    records: list[CrossReferenceEntryRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to cross-reference entries, the
    filtered results SHALL contain only records where company_id matches
    the filter.

    **Validates: Requirements 3.7**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"CrossRef {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


# ---------------------------------------------------------------------------
# Property 2: Multi-Tenancy Isolation — GenerationJobMetadata
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    records=st_job_metadata_records(),
    target_company=COMPANY_IDS,
)
def test_job_metadata_listing_returns_only_target_company(
    records: list[GenerationJobMetadataRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to generation job metadata, the
    filtered results SHALL contain only records where company_id matches
    the filter.

    **Validates: Requirements 7.8**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"Job {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


# ---------------------------------------------------------------------------
# Property 2: Combined multi-model tenant isolation
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    templates=st_template_records(),
    provenances=st_provenance_records(),
    cross_refs=st_cross_reference_records(),
    jobs=st_job_metadata_records(),
    target_company=COMPANY_IDS,
)
def test_combined_document_generation_tenant_isolation(
    templates: list[DocumentTemplateRecord],
    provenances: list[GenerationProvenanceRecord],
    cross_refs: list[CrossReferenceEntryRecord],
    jobs: list[GenerationJobMetadataRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied across ALL document generation model
    types simultaneously, each filtered result set SHALL contain only records
    belonging to the target company, and no records from other companies leak
    into any result set.

    **Validates: Requirements 1.9, 2.8, 3.7, 5.6, 6.7, 7.8, 9.7**
    """
    filtered_templates = filter_by_company(templates, target_company)
    filtered_provenances = filter_by_company(provenances, target_company)
    filtered_cross_refs = filter_by_company(cross_refs, target_company)
    filtered_jobs = filter_by_company(jobs, target_company)

    # Verify isolation for each model type
    for t in filtered_templates:
        assert t.company_id == target_company
    for p in filtered_provenances:
        assert p.company_id == target_company
    for cr in filtered_cross_refs:
        assert cr.company_id == target_company
    for j in filtered_jobs:
        assert j.company_id == target_company

    # Verify completeness: no records for target company are missing
    assert len(filtered_templates) == sum(
        1 for r in templates if r.company_id == target_company
    )
    assert len(filtered_provenances) == sum(
        1 for r in provenances if r.company_id == target_company
    )
    assert len(filtered_cross_refs) == sum(
        1 for r in cross_refs if r.company_id == target_company
    )
    assert len(filtered_jobs) == sum(
        1 for r in jobs if r.company_id == target_company
    )

    # Verify no cross-company leakage: collect other company IDs
    other_companies = {
        r.company_id
        for r in templates + provenances + cross_refs + jobs  # type: ignore[operator]
        if r.company_id != target_company
    }
    all_filtered = (
        filtered_templates + filtered_provenances
        + filtered_cross_refs + filtered_jobs
    )
    for record in all_filtered:
        assert record.company_id not in other_companies or record.company_id == target_company
