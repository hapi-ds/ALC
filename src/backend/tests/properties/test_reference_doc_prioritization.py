"""Property-based test for reference document prioritization.

Property 4: Reference Document Prioritization

**Validates: Requirements 2.5, 9.3**

When reference_document_ids are provided, their content appears BEFORE general
knowledge base results in the section generation prompt. Reference documents are
prioritized as primary source material.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.placeholder_processor import SectionGenerationContext
from alcoabase.services.template_document_generator import (
    TemplateDocumentGeneratorService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Reference document excerpt: dict with title and text
st_ref_excerpt = st.fixed_dictionaries(
    {
        "title": st.text(
            alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            min_size=3,
            max_size=40,
        ).filter(lambda s: s.strip()),
        "text": st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=10,
            max_size=200,
        ).filter(lambda s: s.strip()),
    }
)

# Knowledge base chunk: dict with title, excerpt/text, and relevance_score
st_kb_chunk = st.fixed_dictionaries(
    {
        "title": st.text(
            alphabet=st.characters(min_codepoint=65, max_codepoint=122),
            min_size=3,
            max_size=40,
        ).filter(lambda s: s.strip()),
        "excerpt": st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P", "Z"),
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=10,
            max_size=200,
        ).filter(lambda s: s.strip()),
        "relevance_score": st.floats(
            min_value=0.3, max_value=1.0, allow_nan=False
        ),
    }
)

# Section heading text
st_heading = st.text(
    alphabet=st.characters(min_codepoint=65, max_codepoint=122),
    min_size=3,
    max_size=40,
).filter(lambda s: s.strip())

# Generation instructions
st_instructions = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=10,
    max_size=100,
).filter(lambda s: s.strip())

# Document type targets
st_doc_type = st.sampled_from(["URS", "SOP", "MVP", "Protocol", "Report"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> TemplateDocumentGeneratorService:
    """Create a TemplateDocumentGeneratorService with mocked dependencies."""
    session_factory = MagicMock()
    inference_client = AsyncMock()
    knowledge_service = MagicMock()
    agent_registry = AsyncMock()
    storage_service = AsyncMock()
    job_tracker = AsyncMock()
    template_analysis_service = MagicMock()

    return TemplateDocumentGeneratorService(
        session_factory=session_factory,
        inference_client=inference_client,
        knowledge_service=knowledge_service,
        agent_registry=agent_registry,
        storage_service=storage_service,
        job_tracker=job_tracker,
        template_analysis_service=template_analysis_service,
    )


# ---------------------------------------------------------------------------
# Property 4: Reference Document Prioritization
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    ref_excerpts=st.lists(st_ref_excerpt, min_size=1, max_size=5),
    kb_chunks=st.lists(st_kb_chunk, min_size=1, max_size=10),
    heading=st_heading,
    instructions=st_instructions,
    doc_type=st_doc_type,
)
def test_reference_docs_appear_before_kb_chunks_in_prompt(
    ref_excerpts: list[dict[str, str]],
    kb_chunks: list[dict[str, Any]],
    heading: str,
    instructions: str,
    doc_type: str,
) -> None:
    """When reference_document_ids are provided, their content SHALL appear
    BEFORE general knowledge base results in the section generation prompt.
    Reference documents are prioritized as primary source material.

    **Validates: Requirements 2.5, 9.3**
    """
    service = _make_service()

    context = SectionGenerationContext(
        section_heading=heading,
        section_level=1,
        section_position=0,
        total_sections=3,
        preceding_sections_summary="",
        knowledge_base_chunks=kb_chunks,
        reference_doc_excerpts=ref_excerpts,
        placeholder_instructions=[],
        cross_reference_map={},
        generation_instructions=instructions,
        document_type_target=doc_type,
    )

    messages = service.build_section_prompt(context)

    # Extract the user message content
    user_message = next(
        (m["content"] for m in messages if m["role"] == "user"), ""
    )

    # The reference documents section header must appear in the user message
    ref_header = "Reference Documents (Primary Sources)"
    kb_header = "Knowledge Base"

    assert ref_header in user_message, (
        f"Reference Documents section header not found in user message. "
        f"User message excerpt: {user_message[:500]}"
    )
    assert kb_header in user_message, (
        f"Knowledge Base section header not found in user message. "
        f"User message excerpt: {user_message[:500]}"
    )

    # Reference Documents section MUST appear BEFORE Knowledge Base section
    ref_pos = user_message.index(ref_header)
    kb_pos = user_message.index(kb_header)

    assert ref_pos < kb_pos, (
        f"Reference Documents (position {ref_pos}) must appear BEFORE "
        f"Knowledge Base (position {kb_pos}) in the prompt. "
        f"Reference documents should be prioritized as primary source material."
    )

    # Verify that actual reference document content appears before KB content.
    # We use the section-specific title prefix format to locate each entry
    # unambiguously, since raw text could be identical across ref and KB.
    first_ref_title = ref_excerpts[0]["title"]
    first_kb_title = kb_chunks[0]["title"]

    # The prompt formats reference excerpts as "[{title}]: {text}"
    # and KB chunks as "[{title} (relevance: {score:.2f})]: {text}"
    ref_entry_marker = f"[{first_ref_title}]:"
    kb_entry_marker = f"[{first_kb_title} (relevance:"

    ref_entry_pos = user_message.find(ref_entry_marker)
    kb_entry_pos = user_message.find(kb_entry_marker)

    assert ref_entry_pos != -1, (
        f"Reference excerpt entry not found in user message. "
        f"Looking for: '{ref_entry_marker}'"
    )
    assert kb_entry_pos != -1, (
        f"KB chunk entry not found in user message. "
        f"Looking for: '{kb_entry_marker}'"
    )
    assert ref_entry_pos < kb_entry_pos, (
        f"Reference excerpt entry (position {ref_entry_pos}) must appear "
        f"before KB chunk entry (position {kb_entry_pos}) in the prompt. "
        f"Reference documents should be prioritized as primary source material."
    )


@settings(max_examples=25)
@given(
    kb_chunks=st.lists(st_kb_chunk, min_size=1, max_size=5),
    heading=st_heading,
    instructions=st_instructions,
    doc_type=st_doc_type,
)
def test_no_reference_docs_section_when_none_provided(
    kb_chunks: list[dict[str, Any]],
    heading: str,
    instructions: str,
    doc_type: str,
) -> None:
    """When no reference_document_ids are provided (empty list), the prompt
    SHALL NOT contain the Reference Documents section header, but SHALL still
    include Knowledge Base content.

    **Validates: Requirements 2.5, 9.3**
    """
    service = _make_service()

    context = SectionGenerationContext(
        section_heading=heading,
        section_level=1,
        section_position=0,
        total_sections=3,
        preceding_sections_summary="",
        knowledge_base_chunks=kb_chunks,
        reference_doc_excerpts=[],  # No reference documents
        placeholder_instructions=[],
        cross_reference_map={},
        generation_instructions=instructions,
        document_type_target=doc_type,
    )

    messages = service.build_section_prompt(context)

    # Extract the user message content
    user_message = next(
        (m["content"] for m in messages if m["role"] == "user"), ""
    )

    # Reference Documents section should NOT appear
    ref_header = "Reference Documents (Primary Sources)"
    assert ref_header not in user_message, (
        f"Reference Documents section should not appear when no reference "
        f"documents are provided. Found in: {user_message[:500]}"
    )

    # Knowledge Base section should still appear
    kb_header = "Knowledge Base"
    assert kb_header in user_message, (
        f"Knowledge Base section should still appear when KB chunks are "
        f"provided. User message: {user_message[:500]}"
    )
