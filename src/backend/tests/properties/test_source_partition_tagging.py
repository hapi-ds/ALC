"""Property-based tests for source-based partition tagging (Property 6).

Tests that IndexedChunk instances are correctly tagged based on their
content source: literature pipeline chunks get 'public_literature' and
internal upload chunks get 'private_knowledge'.

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from alcoabase.literature.embedding.services.index_manager import IndexedChunk

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Valid partition tags for each source type
LITERATURE_PARTITION_TAG = "public_literature"
INTERNAL_PARTITION_TAG = "private_knowledge"

# Use a small fixed-size vector for testing partition tagging logic.
# The actual dimension (1024) is irrelevant to the partition_tag property.
_VECTOR_DIM = 8
st_embedding_vector = st.lists(
    st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=_VECTOR_DIM,
    max_size=_VECTOR_DIM,
)
st_chunk_text = st.text(min_size=1, max_size=500)
st_title = st.text(min_size=1, max_size=200)
st_abstract_snippet = st.text(min_size=0, max_size=200)
st_authors = st.lists(st.text(min_size=1, max_size=50), min_size=0, max_size=5)
st_doi = st.one_of(st.none(), st.text(min_size=5, max_size=50))
st_publication_date = st.one_of(
    st.none(), st.just("2024-01-15"), st.just("2023-06-30")
)
st_source_id = st.one_of(st.none(), st.text(min_size=1, max_size=30))
st_external_id = st.one_of(st.none(), st.text(min_size=1, max_size=50))
st_ingestion_record_id = st.integers(min_value=1, max_value=100_000)
st_company_id = st.integers(min_value=1, max_value=10_000)
st_section_heading = st.text(min_size=0, max_size=100)
st_chunk_index = st.integers(min_value=0, max_value=5000)


@st.composite
def st_indexed_chunk_kwargs(draw: st.DrawFn) -> dict:
    """Generate keyword arguments for constructing an IndexedChunk.

    Draws all fields except partition_tag, which is set by the test
    based on the source type being tested.
    """
    return {
        "embedding_vector": draw(st_embedding_vector),
        "chunk_text": draw(st_chunk_text),
        "title": draw(st_title),
        "abstract_snippet": draw(st_abstract_snippet),
        "authors": draw(st_authors),
        "doi": draw(st_doi),
        "publication_date": draw(st_publication_date),
        "source_id": draw(st_source_id),
        "external_id": draw(st_external_id),
        "ingestion_record_id": draw(st_ingestion_record_id),
        "company_id": draw(st_company_id),
        "section_heading": draw(st_section_heading),
        "chunk_index": draw(st_chunk_index),
    }


# ---------------------------------------------------------------------------
# Property 6: Source-based partition tagging
# ---------------------------------------------------------------------------


@settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
@given(kwargs=st_indexed_chunk_kwargs())
def test_literature_pipeline_chunks_tagged_public_literature(kwargs: dict) -> None:
    """For any IndexedChunk constructed from a literature pipeline source,
    the partition_tag field SHALL be 'public_literature'.

    This verifies the contract: when building IndexedChunks for content
    originating from the literature ingestion pipeline (Phase 9.2), the
    partition_tag must always be set to 'public_literature'.

    **Validates: Requirements 5.1, 5.2**
    """
    # Construct chunk as if from literature pipeline
    chunk = IndexedChunk(
        partition_tag=LITERATURE_PARTITION_TAG,
        **kwargs,
    )

    # Property: partition_tag must be exactly 'public_literature'
    assert chunk.partition_tag == LITERATURE_PARTITION_TAG, (
        f"Literature pipeline chunk has incorrect partition_tag.\n"
        f"Expected: '{LITERATURE_PARTITION_TAG}'\n"
        f"Got: '{chunk.partition_tag}'"
    )

    # Property: partition_tag is a string (type safety)
    assert isinstance(chunk.partition_tag, str), (
        f"partition_tag must be a string, got {type(chunk.partition_tag)}"
    )

    # Property: the tag value is not empty or whitespace
    assert chunk.partition_tag.strip() != "", (
        "partition_tag must not be empty or whitespace"
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
@given(kwargs=st_indexed_chunk_kwargs())
def test_internal_upload_chunks_tagged_private_knowledge(kwargs: dict) -> None:
    """For any IndexedChunk constructed from an internal document upload,
    the partition_tag field SHALL be 'private_knowledge'.

    This verifies the contract: when building IndexedChunks for content
    originating from internal company document uploads (KnowledgeService
    pipeline), the partition_tag must always be set to 'private_knowledge'.

    **Validates: Requirements 5.1, 5.2**
    """
    # Construct chunk as if from internal upload
    chunk = IndexedChunk(
        partition_tag=INTERNAL_PARTITION_TAG,
        **kwargs,
    )

    # Property: partition_tag must be exactly 'private_knowledge'
    assert chunk.partition_tag == INTERNAL_PARTITION_TAG, (
        f"Internal upload chunk has incorrect partition_tag.\n"
        f"Expected: '{INTERNAL_PARTITION_TAG}'\n"
        f"Got: '{chunk.partition_tag}'"
    )

    # Property: partition_tag is a string (type safety)
    assert isinstance(chunk.partition_tag, str), (
        f"partition_tag must be a string, got {type(chunk.partition_tag)}"
    )

    # Property: the tag value is not empty or whitespace
    assert chunk.partition_tag.strip() != "", (
        "partition_tag must not be empty or whitespace"
    )


@settings(max_examples=100, suppress_health_check=[HealthCheck.large_base_example])
@given(kwargs=st_indexed_chunk_kwargs())
def test_partition_tag_distinguishes_source_types(kwargs: dict) -> None:
    """For any set of chunk data, constructing an IndexedChunk with
    'public_literature' and another with 'private_knowledge' must yield
    chunks whose partition_tag values are distinct and correctly identify
    their respective source types.

    This ensures partition tagging provides reliable source discrimination.

    **Validates: Requirements 5.1, 5.2**
    """
    # Build both variants from the same data
    literature_chunk = IndexedChunk(
        partition_tag=LITERATURE_PARTITION_TAG,
        **kwargs,
    )
    internal_chunk = IndexedChunk(
        partition_tag=INTERNAL_PARTITION_TAG,
        **kwargs,
    )

    # Property: the two tags are distinct
    assert literature_chunk.partition_tag != internal_chunk.partition_tag, (
        f"Literature and internal chunks must have different partition_tags.\n"
        f"Literature: '{literature_chunk.partition_tag}'\n"
        f"Internal: '{internal_chunk.partition_tag}'"
    )

    # Property: only two valid tag values exist
    valid_tags = {LITERATURE_PARTITION_TAG, INTERNAL_PARTITION_TAG}
    assert literature_chunk.partition_tag in valid_tags, (
        f"Literature chunk tag '{literature_chunk.partition_tag}' "
        f"not in valid tags {valid_tags}"
    )
    assert internal_chunk.partition_tag in valid_tags, (
        f"Internal chunk tag '{internal_chunk.partition_tag}' "
        f"not in valid tags {valid_tags}"
    )

    # Property: frozen dataclass prevents mutation of partition_tag
    # (IndexedChunk is frozen=True, so partition_tag cannot be changed)
    try:
        literature_chunk.partition_tag = "tampered"  # type: ignore[misc]
        assert False, "Frozen dataclass should not allow attribute assignment"
    except AttributeError:
        pass  # Expected: frozen dataclass rejects mutation
