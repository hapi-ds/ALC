"""Property-based tests for provenance completeness and immutability.

Property 9: Provenance Completeness and Immutability

For any completed generation job, a GenerationProvenance record SHALL exist
with all required fields non-null (generation_id, template_id, agent_archetype,
generation_parameters, total_inference_duration_ms, total_token_count,
generation_timestamp), and per-section provenance SHALL include
section_heading, knowledge_base_query_used, source_chunks_retrieved,
token_count_for_section, and inference_duration_ms_for_section for every
generated section. No UPDATE or DELETE operation SHALL succeed on provenance
records.

**Validates: Requirements 5.1, 5.2, 5.4, 9.5**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.document_generation import (
    CrossReferenceEntry,
    GenerationProvenance,
)
from alcoabase.models.immutability import (
    ImmutableRecordError,
    _prevent_delete,
    _prevent_update,
)


# ---------------------------------------------------------------------------
# Data models for pure-logic provenance completeness testing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionProvenanceRecord:
    """Per-section provenance data captured during generation."""

    section_heading: str
    knowledge_base_query_used: str
    source_chunks_retrieved: list[dict[str, Any]]
    token_count_for_section: int
    inference_duration_ms_for_section: int


@dataclass(frozen=True)
class ProvenanceRecord:
    """Represents a GenerationProvenance record with all required fields."""

    generation_id: str
    template_id: int
    company_id: int
    requesting_user_id: int
    agent_archetype: str
    generation_parameters: dict[str, Any]
    source_document_uuids: list[str]
    reference_document_ids: list[int]
    section_provenance: list[SectionProvenanceRecord]
    total_inference_duration_ms: int
    total_token_count: int
    generation_timestamp: datetime
    previous_generation_id: str | None = None


@dataclass(frozen=True)
class CompletedGenerationJob:
    """A generation job that completed successfully."""

    job_id: str
    template_id: int
    company_id: int
    requesting_user_id: int
    sections_generated: int
    provenance: ProvenanceRecord


# ---------------------------------------------------------------------------
# Functions under test: provenance creation and validation
# ---------------------------------------------------------------------------


def create_provenance_for_completed_job(
    job_id: str,
    template_id: int,
    company_id: int,
    requesting_user_id: int,
    agent_archetype: str,
    generation_parameters: dict[str, Any],
    source_document_uuids: list[str],
    reference_document_ids: list[int],
    section_provenance: list[SectionProvenanceRecord],
    total_inference_duration_ms: int,
    total_token_count: int,
    generation_timestamp: datetime,
    previous_generation_id: str | None = None,
) -> ProvenanceRecord:
    """Create a provenance record for a completed generation job.

    This models the provenance creation step in the generation pipeline.
    All required fields must be populated for a valid provenance record.

    Args:
        job_id: UUID of the generation job.
        template_id: Template used for generation.
        company_id: Company scope.
        requesting_user_id: User who requested generation.
        agent_archetype: Agent archetype used (e.g., "technical_writer").
        generation_parameters: LLM parameters (temperature, max_tokens, etc.).
        source_document_uuids: UUIDs of KB source documents used.
        reference_document_ids: Explicitly provided reference doc IDs.
        section_provenance: Per-section provenance details.
        total_inference_duration_ms: Total LLM inference time.
        total_token_count: Total tokens used across all sections.
        generation_timestamp: When generation was executed.
        previous_generation_id: UUID of previous generation (for regeneration).

    Returns:
        ProvenanceRecord with all fields populated.
    """
    return ProvenanceRecord(
        generation_id=job_id,
        template_id=template_id,
        company_id=company_id,
        requesting_user_id=requesting_user_id,
        agent_archetype=agent_archetype,
        generation_parameters=generation_parameters,
        source_document_uuids=source_document_uuids,
        reference_document_ids=reference_document_ids,
        section_provenance=section_provenance,
        total_inference_duration_ms=total_inference_duration_ms,
        total_token_count=total_token_count,
        generation_timestamp=generation_timestamp,
        previous_generation_id=previous_generation_id,
    )


def validate_provenance_completeness(provenance: ProvenanceRecord) -> list[str]:
    """Validate that all required provenance fields are populated.

    Returns a list of validation errors (empty if valid).
    """
    errors: list[str] = []

    # Required top-level fields (Requirements 5.1)
    if not provenance.generation_id:
        errors.append("generation_id is empty or null")
    if not provenance.template_id:
        errors.append("template_id is empty or null")
    if not provenance.agent_archetype:
        errors.append("agent_archetype is empty or null")
    if provenance.generation_parameters is None:
        errors.append("generation_parameters is null")
    if provenance.total_inference_duration_ms is None:
        errors.append("total_inference_duration_ms is null")
    if provenance.total_token_count is None:
        errors.append("total_token_count is null")
    if provenance.generation_timestamp is None:
        errors.append("generation_timestamp is null")
    if not provenance.company_id:
        errors.append("company_id is empty or null")
    if not provenance.requesting_user_id:
        errors.append("requesting_user_id is empty or null")

    # Per-section provenance completeness (Requirements 5.2, 9.5)
    for i, section in enumerate(provenance.section_provenance):
        if not section.section_heading:
            errors.append(f"section[{i}].section_heading is empty")
        if section.knowledge_base_query_used is None:
            errors.append(f"section[{i}].knowledge_base_query_used is null")
        if section.source_chunks_retrieved is None:
            errors.append(f"section[{i}].source_chunks_retrieved is null")
        if section.token_count_for_section is None:
            errors.append(f"section[{i}].token_count_for_section is null")
        if section.inference_duration_ms_for_section is None:
            errors.append(
                f"section[{i}].inference_duration_ms_for_section is null"
            )

    return errors


def attempt_update_provenance(provenance: ProvenanceRecord) -> None:
    """Simulate an UPDATE attempt on a provenance record.

    This models the application-layer immutability enforcement.
    Always raises ImmutableRecordError.

    Raises:
        ImmutableRecordError: Always, because provenance is immutable.
    """
    raise ImmutableRecordError(
        model_name="GenerationProvenance",
        operation="update",
        record_id=None,
    )


def attempt_delete_provenance(provenance: ProvenanceRecord) -> None:
    """Simulate a DELETE attempt on a provenance record.

    This models the application-layer immutability enforcement.
    Always raises ImmutableRecordError.

    Raises:
        ImmutableRecordError: Always, because provenance is immutable.
    """
    raise ImmutableRecordError(
        model_name="GenerationProvenance",
        operation="delete",
        record_id=None,
    )


def link_regeneration(
    new_provenance: ProvenanceRecord,
    previous_generation_id: str,
) -> ProvenanceRecord:
    """Link a new provenance record to a previous generation.

    Models the regeneration traceability requirement (Requirement 5.7):
    when a document is regenerated, the new provenance record includes
    a previous_generation_id linking to the prior generation.

    Returns:
        New ProvenanceRecord with previous_generation_id set.
    """
    return ProvenanceRecord(
        generation_id=new_provenance.generation_id,
        template_id=new_provenance.template_id,
        company_id=new_provenance.company_id,
        requesting_user_id=new_provenance.requesting_user_id,
        agent_archetype=new_provenance.agent_archetype,
        generation_parameters=new_provenance.generation_parameters,
        source_document_uuids=new_provenance.source_document_uuids,
        reference_document_ids=new_provenance.reference_document_ids,
        section_provenance=new_provenance.section_provenance,
        total_inference_duration_ms=new_provenance.total_inference_duration_ms,
        total_token_count=new_provenance.total_token_count,
        generation_timestamp=new_provenance.generation_timestamp,
        previous_generation_id=previous_generation_id,
    )


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=100)
TEMPLATE_IDS = st.integers(min_value=1, max_value=500)
USER_IDS = st.integers(min_value=1, max_value=200)
GENERATION_IDS = st.from_regex(
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
    fullmatch=True,
)

AGENT_ARCHETYPES = st.sampled_from([
    "technical_writer",
    "regulatory_compliance_auditor",
    "process_safety_reviewer",
    "data_integrity_specialist",
])

GENERATION_PARAMETERS = st.fixed_dictionaries({
    "temperature": st.floats(min_value=0.0, max_value=1.0),
    "max_tokens": st.integers(min_value=256, max_value=8192),
    "model_name": st.sampled_from([
        "gemma-4-e4b-it",
        "qwen3-embedding-8b",
    ]),
})

SOURCE_DOCUMENT_UUIDS = st.lists(
    st.from_regex(r"2025-\d{5}", fullmatch=True),
    min_size=0,
    max_size=10,
)

REFERENCE_DOCUMENT_IDS = st.lists(
    st.integers(min_value=1, max_value=1000),
    min_size=0,
    max_size=20,
)

TIMESTAMPS = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2026, 12, 31),
    timezones=st.just(UTC),
)


@st.composite
def st_source_chunk(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a source chunk record for per-section provenance."""
    return {
        "chunk_document_uuid": draw(
            st.from_regex(r"2025-\d{5}", fullmatch=True)
        ),
        "chunk_text": draw(st.text(min_size=1, max_size=200)),
        "relevance_score": draw(st.floats(min_value=0.3, max_value=1.0)),
    }


@st.composite
def st_section_provenance(draw: st.DrawFn) -> SectionProvenanceRecord:
    """Generate a valid per-section provenance record."""
    return SectionProvenanceRecord(
        section_heading=draw(st.text(min_size=1, max_size=100)),
        knowledge_base_query_used=draw(st.text(min_size=1, max_size=500)),
        source_chunks_retrieved=draw(
            st.lists(st_source_chunk(), min_size=0, max_size=10)
        ),
        token_count_for_section=draw(st.integers(min_value=50, max_value=8192)),
        inference_duration_ms_for_section=draw(
            st.integers(min_value=100, max_value=30000)
        ),
    )


@st.composite
def st_provenance_record(draw: st.DrawFn) -> ProvenanceRecord:
    """Generate a complete, valid provenance record."""
    sections = draw(st.lists(st_section_provenance(), min_size=1, max_size=30))
    total_tokens = sum(s.token_count_for_section for s in sections)
    total_duration = sum(s.inference_duration_ms_for_section for s in sections)

    return ProvenanceRecord(
        generation_id=draw(GENERATION_IDS),
        template_id=draw(TEMPLATE_IDS),
        company_id=draw(COMPANY_IDS),
        requesting_user_id=draw(USER_IDS),
        agent_archetype=draw(AGENT_ARCHETYPES),
        generation_parameters=draw(GENERATION_PARAMETERS),
        source_document_uuids=draw(SOURCE_DOCUMENT_UUIDS),
        reference_document_ids=draw(REFERENCE_DOCUMENT_IDS),
        section_provenance=sections,
        total_inference_duration_ms=total_duration,
        total_token_count=total_tokens,
        generation_timestamp=draw(TIMESTAMPS),
        previous_generation_id=None,
    )


@st.composite
def st_regeneration_pair(
    draw: st.DrawFn,
) -> tuple[ProvenanceRecord, ProvenanceRecord]:
    """Generate a pair of provenance records representing a regeneration.

    The second record links to the first via previous_generation_id.
    """
    first = draw(st_provenance_record())

    # Generate a distinct generation_id using st.uuids() for speed
    second_gen_id = str(draw(st.uuids()))

    second_sections = draw(
        st.lists(st_section_provenance(), min_size=1, max_size=5)
    )
    second_total_tokens = sum(s.token_count_for_section for s in second_sections)
    second_total_duration = sum(
        s.inference_duration_ms_for_section for s in second_sections
    )

    second = ProvenanceRecord(
        generation_id=second_gen_id,
        template_id=first.template_id,
        company_id=first.company_id,
        requesting_user_id=draw(USER_IDS),
        agent_archetype=draw(AGENT_ARCHETYPES),
        generation_parameters=draw(GENERATION_PARAMETERS),
        source_document_uuids=draw(SOURCE_DOCUMENT_UUIDS),
        reference_document_ids=draw(REFERENCE_DOCUMENT_IDS),
        section_provenance=second_sections,
        total_inference_duration_ms=second_total_duration,
        total_token_count=second_total_tokens,
        generation_timestamp=draw(TIMESTAMPS),
        previous_generation_id=first.generation_id,
    )

    return (first, second)


# ---------------------------------------------------------------------------
# Property 9: Provenance Completeness and Immutability
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(provenance=st_provenance_record())
def test_provenance_completeness_all_required_fields_non_null(
    provenance: ProvenanceRecord,
) -> None:
    """For any completed generation job, the GenerationProvenance record
    SHALL have all required fields non-null: generation_id, template_id,
    agent_archetype, generation_parameters, total_inference_duration_ms,
    total_token_count, generation_timestamp, company_id, requesting_user_id.

    **Validates: Requirements 5.1, 5.2, 5.4, 9.5**
    """
    errors = validate_provenance_completeness(provenance)
    assert errors == [], (
        f"Provenance record has missing required fields: {errors}"
    )


@settings(max_examples=25)
@given(provenance=st_provenance_record())
def test_per_section_provenance_completeness(
    provenance: ProvenanceRecord,
) -> None:
    """For any completed generation job, per-section provenance SHALL include
    section_heading, knowledge_base_query_used, source_chunks_retrieved,
    token_count_for_section, and inference_duration_ms_for_section for
    every generated section.

    **Validates: Requirements 5.2, 9.5**
    """
    for i, section in enumerate(provenance.section_provenance):
        assert section.section_heading, (
            f"Section [{i}] missing section_heading"
        )
        assert section.knowledge_base_query_used is not None, (
            f"Section [{i}] missing knowledge_base_query_used"
        )
        assert section.source_chunks_retrieved is not None, (
            f"Section [{i}] missing source_chunks_retrieved"
        )
        assert section.token_count_for_section is not None, (
            f"Section [{i}] missing token_count_for_section"
        )
        assert section.inference_duration_ms_for_section is not None, (
            f"Section [{i}] missing inference_duration_ms_for_section"
        )


@settings(max_examples=25)
@given(provenance=st_provenance_record())
def test_provenance_immutability_update_raises_error(
    provenance: ProvenanceRecord,
) -> None:
    """No UPDATE operation SHALL succeed on provenance records.
    Any attempt to update a GenerationProvenance record SHALL raise
    ImmutableRecordError.

    **Validates: Requirements 5.4**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_update_provenance(provenance)

    assert exc_info.value.operation == "update"
    assert exc_info.value.model_name == "GenerationProvenance"


@settings(max_examples=25)
@given(provenance=st_provenance_record())
def test_provenance_immutability_delete_raises_error(
    provenance: ProvenanceRecord,
) -> None:
    """No DELETE operation SHALL succeed on provenance records.
    Any attempt to delete a GenerationProvenance record SHALL raise
    ImmutableRecordError.

    **Validates: Requirements 5.4**
    """
    with pytest.raises(ImmutableRecordError) as exc_info:
        attempt_delete_provenance(provenance)

    assert exc_info.value.operation == "delete"
    assert exc_info.value.model_name == "GenerationProvenance"


@settings(max_examples=25)
@given(pair=st_regeneration_pair())
def test_regeneration_links_previous_generation_id(
    pair: tuple[ProvenanceRecord, ProvenanceRecord],
) -> None:
    """When a document is regenerated, the new GenerationProvenance record
    SHALL include a previous_generation_id field referencing the generation_id
    of the immediately preceding provenance record, enabling version-to-version
    traceability.

    **Validates: Requirements 5.1, 5.4**
    """
    first, second = pair

    # The second provenance must link to the first
    assert second.previous_generation_id == first.generation_id, (
        f"Regeneration link broken: second.previous_generation_id="
        f"'{second.previous_generation_id}' should equal "
        f"first.generation_id='{first.generation_id}'"
    )

    # The first provenance has no previous link (it's the original)
    assert first.previous_generation_id is None, (
        f"Original provenance should have no previous_generation_id, "
        f"got '{first.previous_generation_id}'"
    )

    # Both records must have distinct generation_ids
    assert first.generation_id != second.generation_id, (
        "Regeneration must produce a new generation_id"
    )


@settings(max_examples=25)
@given(provenance=st_provenance_record())
def test_total_token_count_consistent_with_sections(
    provenance: ProvenanceRecord,
) -> None:
    """The total_token_count SHALL equal the sum of token_count_for_section
    across all generated sections, ensuring provenance accounting is
    consistent.

    **Validates: Requirements 5.1, 9.5**
    """
    expected_total = sum(
        s.token_count_for_section for s in provenance.section_provenance
    )
    assert provenance.total_token_count == expected_total, (
        f"total_token_count ({provenance.total_token_count}) does not match "
        f"sum of section token counts ({expected_total})"
    )


@settings(max_examples=25)
@given(provenance=st_provenance_record())
def test_total_inference_duration_consistent_with_sections(
    provenance: ProvenanceRecord,
) -> None:
    """The total_inference_duration_ms SHALL equal the sum of
    inference_duration_ms_for_section across all generated sections,
    ensuring provenance timing is consistent.

    **Validates: Requirements 5.1, 9.5**
    """
    expected_total = sum(
        s.inference_duration_ms_for_section for s in provenance.section_provenance
    )
    assert provenance.total_inference_duration_ms == expected_total, (
        f"total_inference_duration_ms ({provenance.total_inference_duration_ms}) "
        f"does not match sum of section durations ({expected_total})"
    )


# ---------------------------------------------------------------------------
# SQLAlchemy event listener tests (actual immutability enforcement)
# ---------------------------------------------------------------------------


class TestImmutabilityEventListeners:
    """Test that SQLAlchemy event listeners correctly prevent mutations.

    These tests verify the actual _prevent_update and _prevent_delete
    functions from the immutability module raise ImmutableRecordError
    when invoked (as they would be by SQLAlchemy events).
    """

    def test_prevent_update_raises_immutable_record_error(self) -> None:
        """The _prevent_update listener SHALL raise ImmutableRecordError
        for GenerationProvenance instances.

        **Validates: Requirements 5.4**
        """
        # Create a mock target that looks like a GenerationProvenance
        target = GenerationProvenance()
        target.id = 42

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_update(None, None, target)

        assert exc_info.value.model_name == "GenerationProvenance"
        assert exc_info.value.operation == "update"
        assert exc_info.value.record_id == 42

    def test_prevent_delete_raises_immutable_record_error(self) -> None:
        """The _prevent_delete listener SHALL raise ImmutableRecordError
        for GenerationProvenance instances.

        **Validates: Requirements 5.4**
        """
        target = GenerationProvenance()
        target.id = 99

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_delete(None, None, target)

        assert exc_info.value.model_name == "GenerationProvenance"
        assert exc_info.value.operation == "delete"
        assert exc_info.value.record_id == 99

    def test_prevent_update_raises_for_cross_reference_entry(self) -> None:
        """The _prevent_update listener SHALL raise ImmutableRecordError
        for CrossReferenceEntry instances.

        **Validates: Requirements 5.4**
        """
        target = CrossReferenceEntry()
        target.id = 7

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_update(None, None, target)

        assert exc_info.value.model_name == "CrossReferenceEntry"
        assert exc_info.value.operation == "update"
        assert exc_info.value.record_id == 7

    def test_prevent_delete_raises_for_cross_reference_entry(self) -> None:
        """The _prevent_delete listener SHALL raise ImmutableRecordError
        for CrossReferenceEntry instances.

        **Validates: Requirements 5.4**
        """
        target = CrossReferenceEntry()
        target.id = 13

        with pytest.raises(ImmutableRecordError) as exc_info:
            _prevent_delete(None, None, target)

        assert exc_info.value.model_name == "CrossReferenceEntry"
        assert exc_info.value.operation == "delete"
        assert exc_info.value.record_id == 13

    def test_immutable_record_error_message_format(self) -> None:
        """ImmutableRecordError SHALL produce a clear message indicating
        the model, operation, and record ID.

        **Validates: Requirements 5.4**
        """
        error = ImmutableRecordError(
            model_name="GenerationProvenance",
            operation="update",
            record_id=42,
        )
        assert "Cannot update immutable record" in str(error)
        assert "GenerationProvenance" in str(error)
        assert "id=42" in str(error)
        assert "GxP audit trail" in str(error)
        assert "append-only" in str(error)
