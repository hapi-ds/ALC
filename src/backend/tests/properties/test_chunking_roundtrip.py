"""Property-based test: Chunking completeness round-trip (Property 2).

Validates that the ChunkingPipeline._chunk_text() method produces chunks
whose non-overlapping portions, when concatenated, reconstruct the original
input text without omission or reordering.

Tokens are whitespace-delimited words. The non-overlapping portion of each
chunk is derived by removing the overlap tokens shared with the previous chunk.

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md

**Validates: Requirements 2.7**
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.embedding.services.chunking_pipeline import ChunkingPipeline


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate text with at least one non-whitespace character, using words
# separated by single spaces to match whitespace-split token semantics.
st_word = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P", "S"),
        exclude_characters=" \t\n\r",
    ),
    min_size=1,
    max_size=20,
)

st_text_input = st.lists(st_word, min_size=1, max_size=300).map(" ".join)

# Chunk size range: 128-2048 per spec, overlap: 0-256 where overlap < chunk_size
st_chunk_size = st.integers(min_value=128, max_value=2048)
st_overlap = st.integers(min_value=0, max_value=256)


@st.composite
def st_chunking_params(draw: st.DrawFn) -> tuple[str, int, int]:
    """Generate valid (text, chunk_size, overlap) triples.

    Ensures overlap < chunk_size per ChunkingPipeline constraint.
    """
    text = draw(st_text_input)
    chunk_size = draw(st_chunk_size)
    # Overlap must be strictly less than chunk_size
    max_overlap = min(256, chunk_size - 1)
    overlap = draw(st.integers(min_value=0, max_value=max_overlap))
    return (text, chunk_size, overlap)


# ---------------------------------------------------------------------------
# Property 2: Round-trip consistency
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(params=st_chunking_params())
def test_chunking_roundtrip_consistency(params: tuple[str, int, int]) -> None:
    """For any non-empty text input, chunking with _chunk_text() and then
    extracting the unique (non-overlapping) portion from each consecutive
    chunk reconstructs the original text without omission or reordering.

    The non-overlapping portion of chunk[0] is the entire chunk.
    For chunk[i] (i > 0), the non-overlapping portion is the tokens
    after the first `overlap` tokens (which were shared with chunk[i-1]).

    Concatenating all non-overlapping portions with spaces reproduces
    the normalized (whitespace-collapsed) original text.

    **Validates: Requirements 2.7**
    """
    text, chunk_size, overlap = params

    pipeline = ChunkingPipeline(
        chunk_size_tokens=chunk_size,
        chunk_overlap_tokens=overlap,
    )

    chunks = pipeline._chunk_text(text)

    # If text is empty/whitespace-only, chunks should be empty
    if not text or not text.strip():
        assert chunks == [], (
            f"Expected no chunks for whitespace/empty input, got {len(chunks)}"
        )
        return

    # At least one chunk for non-empty input
    assert len(chunks) >= 1, (
        f"Expected at least one chunk for non-empty input, got 0.\n"
        f"Input: {text!r}"
    )

    # Extract non-overlapping portions from each chunk
    unique_portions: list[str] = []

    for i, chunk in enumerate(chunks):
        chunk_tokens = chunk.split()

        if i == 0:
            # First chunk: all tokens are unique
            unique_portions.append(chunk)
        else:
            # Subsequent chunks: skip the overlap tokens at the start
            # These overlap tokens were already included in the previous chunk
            if overlap > 0 and len(chunk_tokens) > overlap:
                non_overlapping = " ".join(chunk_tokens[overlap:])
                unique_portions.append(non_overlapping)
            elif overlap == 0:
                # No overlap: entire chunk is unique
                unique_portions.append(chunk)
            # If chunk has <= overlap tokens, it's fully overlapping
            # (edge case for the last chunk that's smaller than overlap)

    # Reconstruct text from non-overlapping portions
    reconstructed = " ".join(unique_portions)

    # Normalize original: collapse whitespace and strip
    normalized_original = " ".join(text.split())

    assert reconstructed == normalized_original, (
        f"Round-trip reconstruction failed.\n"
        f"Original (normalized): {normalized_original!r}\n"
        f"Reconstructed: {reconstructed!r}\n"
        f"Chunks ({len(chunks)}): {chunks}\n"
        f"chunk_size={chunk_size}, overlap={overlap}"
    )
