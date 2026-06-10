"""Property-based tests for embedding configuration range validation.

Property 16: Configuration range validation
- Generate config values outside valid ranges.
- Assert HTTP 422 rejection for out-of-range values.
- Assert acceptance for in-range values.
- Also test the overlap < chunk_size model validator.

**Validates: Requirements 9.9**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from alcoabase.literature.embedding.schemas.configuration import (
    EmbeddingConfigurationUpdateSchema,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Valid ranges per Requirement 9.1 / 9.9:
# chunk_size_tokens: 128–2048
# chunk_overlap_tokens: 0–256
# max_chunks_per_document: 1–5000

VALID_CHUNK_SIZE = st.integers(min_value=128, max_value=2048)
VALID_OVERLAP = st.integers(min_value=0, max_value=256)
VALID_MAX_CHUNKS = st.integers(min_value=1, max_value=5000)

INVALID_CHUNK_SIZE_BELOW = st.integers(min_value=-10000, max_value=127)
INVALID_CHUNK_SIZE_ABOVE = st.integers(min_value=2049, max_value=100000)

INVALID_OVERLAP_BELOW = st.integers(min_value=-10000, max_value=-1)
INVALID_OVERLAP_ABOVE = st.integers(min_value=257, max_value=100000)

INVALID_MAX_CHUNKS_BELOW = st.integers(min_value=-10000, max_value=0)
INVALID_MAX_CHUNKS_ABOVE = st.integers(min_value=5001, max_value=100000)


# ---------------------------------------------------------------------------
# Property 16a: chunk_size_tokens — Valid range accepted (128–2048)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=VALID_CHUNK_SIZE)
def test_chunk_size_accepts_valid_range(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL accept chunk_size_tokens
    when 128 ≤ value ≤ 2048.

    **Validates: Requirements 9.9**
    """
    config = EmbeddingConfigurationUpdateSchema(chunk_size_tokens=value)
    assert config.chunk_size_tokens == value


# ---------------------------------------------------------------------------
# Property 16b: chunk_size_tokens — Below minimum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=INVALID_CHUNK_SIZE_BELOW)
def test_chunk_size_rejects_below_minimum(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject chunk_size_tokens
    when value < 128 with a ValidationError.

    **Validates: Requirements 9.9**
    """
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpdateSchema(chunk_size_tokens=value)


# ---------------------------------------------------------------------------
# Property 16c: chunk_size_tokens — Above maximum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=INVALID_CHUNK_SIZE_ABOVE)
def test_chunk_size_rejects_above_maximum(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject chunk_size_tokens
    when value > 2048 with a ValidationError.

    **Validates: Requirements 9.9**
    """
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpdateSchema(chunk_size_tokens=value)


# ---------------------------------------------------------------------------
# Property 16d: chunk_overlap_tokens — Valid range accepted (0–256)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=VALID_OVERLAP)
def test_overlap_accepts_valid_range(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL accept chunk_overlap_tokens
    when 0 ≤ value ≤ 256.

    **Validates: Requirements 9.9**
    """
    config = EmbeddingConfigurationUpdateSchema(chunk_overlap_tokens=value)
    assert config.chunk_overlap_tokens == value


# ---------------------------------------------------------------------------
# Property 16e: chunk_overlap_tokens — Below minimum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=INVALID_OVERLAP_BELOW)
def test_overlap_rejects_below_minimum(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject chunk_overlap_tokens
    when value < 0 with a ValidationError.

    **Validates: Requirements 9.9**
    """
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpdateSchema(chunk_overlap_tokens=value)


# ---------------------------------------------------------------------------
# Property 16f: chunk_overlap_tokens — Above maximum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=INVALID_OVERLAP_ABOVE)
def test_overlap_rejects_above_maximum(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject chunk_overlap_tokens
    when value > 256 with a ValidationError.

    **Validates: Requirements 9.9**
    """
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpdateSchema(chunk_overlap_tokens=value)


# ---------------------------------------------------------------------------
# Property 16g: max_chunks_per_document — Valid range accepted (1–5000)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=VALID_MAX_CHUNKS)
def test_max_chunks_accepts_valid_range(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL accept max_chunks_per_document
    when 1 ≤ value ≤ 5000.

    **Validates: Requirements 9.9**
    """
    config = EmbeddingConfigurationUpdateSchema(max_chunks_per_document=value)
    assert config.max_chunks_per_document == value


# ---------------------------------------------------------------------------
# Property 16h: max_chunks_per_document — Below minimum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=INVALID_MAX_CHUNKS_BELOW)
def test_max_chunks_rejects_below_minimum(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject max_chunks_per_document
    when value < 1 with a ValidationError.

    **Validates: Requirements 9.9**
    """
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpdateSchema(max_chunks_per_document=value)


# ---------------------------------------------------------------------------
# Property 16i: max_chunks_per_document — Above maximum rejected
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(value=INVALID_MAX_CHUNKS_ABOVE)
def test_max_chunks_rejects_above_maximum(value: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject max_chunks_per_document
    when value > 5000 with a ValidationError.

    **Validates: Requirements 9.9**
    """
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpdateSchema(max_chunks_per_document=value)


# ---------------------------------------------------------------------------
# Property 16j: overlap < chunk_size model validator
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    chunk_size=VALID_CHUNK_SIZE,
    overlap=VALID_OVERLAP,
)
def test_overlap_must_be_less_than_chunk_size(chunk_size: int, overlap: int) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL reject when
    chunk_overlap_tokens >= chunk_size_tokens.

    When overlap < chunk_size, the configuration SHALL be accepted.
    When overlap >= chunk_size, the configuration SHALL be rejected.

    **Validates: Requirements 9.9**
    """
    if overlap < chunk_size:
        config = EmbeddingConfigurationUpdateSchema(
            chunk_size_tokens=chunk_size,
            chunk_overlap_tokens=overlap,
        )
        assert config.chunk_size_tokens == chunk_size
        assert config.chunk_overlap_tokens == overlap
    else:
        with pytest.raises(ValidationError):
            EmbeddingConfigurationUpdateSchema(
                chunk_size_tokens=chunk_size,
                chunk_overlap_tokens=overlap,
            )


# ---------------------------------------------------------------------------
# Property 16k: All fields valid simultaneously
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    chunk_size=VALID_CHUNK_SIZE,
    overlap=VALID_OVERLAP,
    max_chunks=VALID_MAX_CHUNKS,
    auto_embed=st.booleans(),
    abstract_only=st.booleans(),
)
def test_all_valid_fields_accepted_simultaneously(
    chunk_size: int,
    overlap: int,
    max_chunks: int,
    auto_embed: bool,
    abstract_only: bool,
) -> None:
    """EmbeddingConfigurationUpdateSchema SHALL accept all fields simultaneously
    when each is within its defined bounds and overlap < chunk_size.

    **Validates: Requirements 9.9**
    """
    # Ensure overlap < chunk_size for the model validator
    if overlap >= chunk_size:
        overlap = chunk_size - 1

    config = EmbeddingConfigurationUpdateSchema(
        chunk_size_tokens=chunk_size,
        chunk_overlap_tokens=overlap,
        auto_embed_on_ingest=auto_embed,
        embed_abstract_only=abstract_only,
        max_chunks_per_document=max_chunks,
    )
    assert config.chunk_size_tokens == chunk_size
    assert config.chunk_overlap_tokens == overlap
    assert config.auto_embed_on_ingest == auto_embed
    assert config.embed_abstract_only == abstract_only
    assert config.max_chunks_per_document == max_chunks
