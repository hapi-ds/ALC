"""Property-based tests for context prepending in ChunkingPipeline (Property 4).

Validates that the _prepend_context() method bounds prepended context to at most
64 whitespace-delimited tokens and truncates at word boundaries.

**Validates: Requirements 2.5**

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from alcoabase.literature.embedding.services.chunking_pipeline import ChunkingPipeline


# ─── Strategies ───────────────────────────────────────────────────────────────

# Generate non-trivial strings that may contain many words to test truncation.
# Include realistic word-like tokens.
st_title = st.text(
    alphabet=st.characters(
        categories=("L", "N", "Z"),  # Letters, Numbers, Separators
        include_characters=" -_",
    ),
    min_size=0,
    max_size=500,
)

st_section_heading = st.text(
    alphabet=st.characters(
        categories=("L", "N", "Z"),
        include_characters=" -_",
    ),
    min_size=0,
    max_size=500,
)

st_chunk_text = st.text(
    alphabet=st.characters(categories=("L", "N", "Z"), include_characters=" .,!?"),
    min_size=1,
    max_size=200,
)

# Strategy for max_context_tokens — always 64 for this property but allow variation
# to ensure the property generalizes.
st_max_context_tokens = st.just(64)


# ─── Property 4: Context prepending bounded at 64 tokens ─────────────────────


@settings(max_examples=100)
@given(
    title=st_title,
    section_heading=st_section_heading,
    chunk_text=st_chunk_text,
)
def test_property_4_context_prepending_bounded_at_64_tokens(
    title: str,
    section_heading: str,
    chunk_text: str,
) -> None:
    """For any title and section_heading, the prepended context portion
    (the part before the final ' | chunk_text') is at most 64
    whitespace-delimited tokens.

    **Validates: Requirements 2.5**
    """
    pipeline = ChunkingPipeline(
        chunk_size_tokens=512,
        chunk_overlap_tokens=50,
        max_context_tokens=64,
    )

    result = pipeline._prepend_context(chunk_text, title, section_heading)

    # If both title and section_heading are empty/whitespace, the result
    # is just the chunk_text with no context prepended.
    title_stripped = title.strip()
    heading_stripped = section_heading.strip()

    if not title_stripped and not heading_stripped:
        # No context prepended — result should be the original chunk_text
        assert result == chunk_text, (
            f"Expected no context prepended for empty title/heading.\n"
            f"Got: {result!r}\nExpected: {chunk_text!r}"
        )
        return

    # Context was prepended — format is "context | chunk_text"
    # The context is everything before the last " | " that precedes chunk_text.
    # Since the format is "title | heading | chunk_text" or "title | chunk_text",
    # we need to find where the prepended context ends and chunk_text begins.
    # The result always ends with " | {chunk_text}"
    suffix = f" | {chunk_text}"
    assert result.endswith(suffix), (
        f"Expected result to end with ' | <chunk_text>'.\n"
        f"Result: {result!r}\nExpected suffix: {suffix!r}"
    )

    # Extract just the context portion
    context_portion = result[: -len(suffix)]
    context_tokens = context_portion.split()

    # Property: context tokens ≤ 64
    assert len(context_tokens) <= 64, (
        f"Context portion has {len(context_tokens)} tokens, exceeding 64.\n"
        f"Title: {title!r}\nHeading: {section_heading!r}\n"
        f"Context: {context_portion!r}"
    )


@settings(max_examples=100)
@given(
    title=st_title,
    section_heading=st_section_heading,
    chunk_text=st_chunk_text,
)
def test_property_4_context_truncation_at_word_boundary(
    title: str,
    section_heading: str,
    chunk_text: str,
) -> None:
    """When context is truncated, it happens at a word boundary — the context
    never contains a partial word cut mid-token.

    **Validates: Requirements 2.5**
    """
    pipeline = ChunkingPipeline(
        chunk_size_tokens=512,
        chunk_overlap_tokens=50,
        max_context_tokens=64,
    )

    result = pipeline._prepend_context(chunk_text, title, section_heading)

    title_stripped = title.strip()
    heading_stripped = section_heading.strip()

    if not title_stripped and not heading_stripped:
        # No context, nothing to check
        return

    # Extract context portion
    suffix = f" | {chunk_text}"
    assert result.endswith(suffix)
    context_portion = result[: -len(suffix)]

    # Build the full (untruncated) context for comparison
    parts = [p for p in [title_stripped, heading_stripped] if p]
    full_context = " | ".join(parts)
    full_context_tokens = full_context.split()

    if len(full_context_tokens) <= 64:
        # No truncation needed — context should be the full context
        assert context_portion == full_context, (
            f"Expected full context (no truncation needed).\n"
            f"Got: {context_portion!r}\nExpected: {full_context!r}"
        )
    else:
        # Truncation happened — verify it's at a word boundary.
        # The truncated context should be exactly the first 64 tokens rejoined.
        expected_truncated = " ".join(full_context_tokens[:64])
        assert context_portion == expected_truncated, (
            f"Truncated context does not match expected word-boundary truncation.\n"
            f"Got: {context_portion!r}\n"
            f"Expected: {expected_truncated!r}\n"
            f"Full context tokens: {len(full_context_tokens)}"
        )

        # Verify no partial words: each token in context must be a complete token
        # from the original full_context token list
        context_tokens = context_portion.split()
        for i, token in enumerate(context_tokens):
            assert token == full_context_tokens[i], (
                f"Token at position {i} is a partial word.\n"
                f"Got: {token!r}\nExpected: {full_context_tokens[i]!r}"
            )
