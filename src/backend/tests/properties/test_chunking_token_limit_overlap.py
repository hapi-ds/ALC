"""Property-based tests for ChunkingPipeline token limit and overlap.

Property 1: Chunking token limit and overlap
- Every chunk has ≤ chunk_size whitespace-delimited tokens
- Consecutive chunks share exactly overlap tokens at boundaries

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.embedding.services.chunking_pipeline import ChunkingPipeline


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate chunk_size in valid range
st_chunk_size = st.integers(min_value=128, max_value=2048)

# Generate text with enough words to produce multiple chunks
st_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z"), exclude_characters="\x00"),
    min_size=10,
    max_size=5000,
).filter(lambda t: len(t.split()) >= 1)


@st.composite
def st_chunking_params(draw: st.DrawFn) -> tuple[int, int]:
    """Generate valid (chunk_size, overlap) pairs where overlap < chunk_size."""
    chunk_size = draw(st_chunk_size)
    overlap = draw(st.integers(min_value=0, max_value=min(256, chunk_size - 1)))
    return (chunk_size, overlap)


# ---------------------------------------------------------------------------
# Property 1: Chunking token limit and overlap
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    text=st_text,
    params=st_chunking_params(),
)
def test_chunk_token_limit(text: str, params: tuple[int, int]) -> None:
    """Every chunk produced by _chunk_text has at most chunk_size
    whitespace-delimited tokens.

    **Validates: Requirements 1.3, 2.1**
    """
    chunk_size, overlap = params
    pipeline = ChunkingPipeline(
        chunk_size_tokens=chunk_size,
        chunk_overlap_tokens=overlap,
    )

    chunks = pipeline._chunk_text(text)

    for i, chunk in enumerate(chunks):
        token_count = len(chunk.split())
        assert token_count <= chunk_size, (
            f"Chunk {i} has {token_count} tokens, exceeds chunk_size={chunk_size}.\n"
            f"Chunk text (first 100 chars): {chunk[:100]!r}"
        )


@settings(max_examples=100)
@given(
    text=st_text,
    params=st_chunking_params(),
)
def test_consecutive_chunks_share_overlap_tokens(
    text: str, params: tuple[int, int]
) -> None:
    """Consecutive chunks share exactly overlap tokens at boundaries.

    For any two adjacent chunks, the last `overlap` tokens of chunk[i]
    must equal the first `overlap` tokens of chunk[i+1].

    **Validates: Requirements 1.3, 2.1**
    """
    chunk_size, overlap = params
    pipeline = ChunkingPipeline(
        chunk_size_tokens=chunk_size,
        chunk_overlap_tokens=overlap,
    )

    chunks = pipeline._chunk_text(text)

    if overlap == 0 or len(chunks) <= 1:
        # No overlap to verify when overlap=0 or single/no chunks
        return

    for i in range(len(chunks) - 1):
        current_tokens = chunks[i].split()
        next_tokens = chunks[i + 1].split()

        # The last `overlap` tokens of the current chunk should equal
        # the first `overlap` tokens of the next chunk
        tail_of_current = current_tokens[-overlap:]
        head_of_next = next_tokens[:overlap]

        assert tail_of_current == head_of_next, (
            f"Overlap mismatch between chunk {i} and chunk {i + 1}.\n"
            f"Expected overlap of {overlap} tokens.\n"
            f"Tail of chunk {i} (last {overlap} tokens): {tail_of_current}\n"
            f"Head of chunk {i + 1} (first {overlap} tokens): {head_of_next}\n"
            f"Chunk {i} token count: {len(current_tokens)}\n"
            f"Chunk {i + 1} token count: {len(next_tokens)}"
        )
