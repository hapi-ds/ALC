"""Property-based test: Non-empty input produces chunks; whitespace produces none.

Tests that the ChunkingPipeline._chunk_text() method correctly handles:
- Any input with at least one non-whitespace character produces ≥1 chunk
- Empty or whitespace-only input produces 0 chunks

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

# Strings guaranteed to have at least one non-whitespace character.
# We draw arbitrary text and ensure at least one non-whitespace char exists.
st_nonempty_text = st.text(min_size=1, max_size=5000).filter(
    lambda s: s.strip() != ""
)

# Whitespace-only strings: combinations of spaces, tabs, newlines
st_whitespace_only = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\x0b", "\x0c"]),
    min_size=0,
    max_size=500,
)


# ---------------------------------------------------------------------------
# Property 3: Non-empty input produces chunks; whitespace produces none
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(text=st_nonempty_text)
def test_nonempty_input_produces_at_least_one_chunk(text: str) -> None:
    """For any string containing at least one non-whitespace character,
    ChunkingPipeline._chunk_text() SHALL produce at least one chunk.

    **Validates: Requirements 2.6**
    """
    pipeline = ChunkingPipeline(
        chunk_size_tokens=512,
        chunk_overlap_tokens=50,
        max_context_tokens=64,
    )

    chunks = pipeline._chunk_text(text)

    assert len(chunks) >= 1, (
        f"Expected at least 1 chunk for non-empty input, got 0.\n"
        f"Input text (first 200 chars): {text[:200]!r}\n"
        f"Input length: {len(text)}\n"
        f"Stripped length: {len(text.strip())}"
    )


@settings(max_examples=100)
@given(text=st_whitespace_only)
def test_whitespace_only_input_produces_zero_chunks(text: str) -> None:
    """For any string consisting solely of whitespace characters (or empty),
    ChunkingPipeline._chunk_text() SHALL produce zero chunks.

    **Validates: Requirements 2.6**
    """
    pipeline = ChunkingPipeline(
        chunk_size_tokens=512,
        chunk_overlap_tokens=50,
        max_context_tokens=64,
    )

    chunks = pipeline._chunk_text(text)

    assert len(chunks) == 0, (
        f"Expected 0 chunks for whitespace-only input, got {len(chunks)}.\n"
        f"Input text repr: {text!r}\n"
        f"Chunks: {chunks}"
    )
