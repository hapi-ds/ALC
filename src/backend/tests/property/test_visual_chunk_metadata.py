"""Property-based tests for Visual_Chunk metadata correctness.

Tests Property 6: Visual_Chunk metadata correctness from the
multimodal-knowledge-base design document.

Property 6 validates that for any generated (description, document_uuid,
version, visual_type, source_page) combination, the _create_visual_chunks()
method produces VisualChunk objects with all required metadata fields
present and correct.

**Validates: Requirements 2.3, 2.5**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 6)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/knowledge_service.py
"""

import uuid

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import KnowledgeService, VisualChunk
from alcoabase.services.visual_content_detector import VisualType


# ---------------------------------------------------------------------------
# Required metadata fields per Requirements 2.3 and 2.5
# ---------------------------------------------------------------------------

REQUIRED_METADATA_FIELDS: set[str] = {
    "content_type",
    "is_visual",
    "visual_type",
    "source_page",
    "document_uuid",
    "version",
}
"""All metadata dict keys that must be present on every VisualChunk."""


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_description() -> st.SearchStrategy[str]:
    """Generate non-empty description strings of varying lengths.

    Descriptions must be non-empty (the method receives already-validated
    descriptions that passed the 20-char minimum check upstream).
    We generate descriptions long enough to potentially produce multiple chunks.

    Returns:
        Strategy producing non-empty text strings.
    """
    return st.one_of(
        # Short descriptions (single chunk)
        st.text(
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
            min_size=25,
            max_size=100,
        ),
        # Medium descriptions (likely single chunk)
        st.text(
            alphabet=st.characters(categories=("L", "N", "P", "Z")),
            min_size=100,
            max_size=500,
        ),
        # Long descriptions with spaces (may produce multiple chunks)
        st.lists(
            st.text(
                alphabet=st.characters(categories=("L", "N")),
                min_size=3,
                max_size=10,
            ),
            min_size=100,
            max_size=600,
        ).map(lambda words: " ".join(words)),
    )


def st_document_uuid() -> st.SearchStrategy[str]:
    """Generate valid UUID strings for document_uuid.

    Returns:
        Strategy producing UUID4 strings.
    """
    return st.uuids(version=4).map(str)


def st_version() -> st.SearchStrategy[str]:
    """Generate version strings in common formats.

    Returns:
        Strategy producing version strings like "1.0", "2.3", "10.1".
    """
    return st.one_of(
        st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True),
        st.just("1.0"),
        st.just("1"),
        st.just("2.5"),
        st.just("10.0"),
    )


def st_visual_type() -> st.SearchStrategy[VisualType]:
    """Generate VisualType enum values.

    Returns:
        Strategy producing one of the four VisualType enum members.
    """
    return st.sampled_from(list(VisualType))


def st_source_page() -> st.SearchStrategy[int]:
    """Generate valid source page numbers (0-indexed).

    Returns:
        Strategy producing non-negative integers for page numbers.
    """
    return st.integers(min_value=0, max_value=999)


# ---------------------------------------------------------------------------
# Property 6: Visual_Chunk Metadata Correctness
# ---------------------------------------------------------------------------


class TestVisualChunkMetadataCorrectness:
    """Property tests for Visual_Chunk metadata correctness.

    For any (description, document_uuid, version, visual_type, source_page),
    the _create_visual_chunks() method must produce VisualChunk objects where:
    - content_type == "visual"
    - is_visual == True
    - visual_type matches the input visual_type value
    - source_page matches the input source_page
    - document_uuid matches the input document_uuid
    - version matches the input version
    - metadata dict contains all required fields with correct values

    **Validates: Requirements 2.3, 2.5**
    """

    def _create_service(self) -> KnowledgeService:
        """Create a KnowledgeService in mock mode (no external deps)."""
        return KnowledgeService(model_manager=None, inference_client=None)

    @given(
        description=st_description(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_type=st_visual_type(),
        source_page=st_source_page(),
    )
    @settings(max_examples=200)
    def test_all_chunks_have_content_type_visual(
        self,
        description: str,
        document_uuid: str,
        version: str,
        visual_type: VisualType,
        source_page: int,
    ) -> None:
        """Every VisualChunk produced must have content_type="visual".

        **Validates: Requirements 2.3, 2.5**
        """
        service = self._create_service()
        chunks = service._create_visual_chunks(
            description=description,
            document_uuid=document_uuid,
            version=version,
            visual_type=visual_type,
            source_page=source_page,
        )

        for chunk in chunks:
            assert chunk.content_type == "visual", (
                f"Expected content_type='visual', got '{chunk.content_type}'"
            )

    @given(
        description=st_description(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_type=st_visual_type(),
        source_page=st_source_page(),
    )
    @settings(max_examples=200)
    def test_all_chunks_have_is_visual_true(
        self,
        description: str,
        document_uuid: str,
        version: str,
        visual_type: VisualType,
        source_page: int,
    ) -> None:
        """Every VisualChunk produced must have is_visual=True.

        **Validates: Requirements 2.5**
        """
        service = self._create_service()
        chunks = service._create_visual_chunks(
            description=description,
            document_uuid=document_uuid,
            version=version,
            visual_type=visual_type,
            source_page=source_page,
        )

        for chunk in chunks:
            assert chunk.is_visual is True, (
                f"Expected is_visual=True, got {chunk.is_visual}"
            )

    @given(
        description=st_description(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_type=st_visual_type(),
        source_page=st_source_page(),
    )
    @settings(max_examples=200)
    def test_all_chunks_have_correct_visual_type_source_page_uuid_version(
        self,
        description: str,
        document_uuid: str,
        version: str,
        visual_type: VisualType,
        source_page: int,
    ) -> None:
        """Every VisualChunk must have the correct visual_type, source_page,
        document_uuid, and version matching the inputs.

        **Validates: Requirements 2.3, 2.5**
        """
        service = self._create_service()
        chunks = service._create_visual_chunks(
            description=description,
            document_uuid=document_uuid,
            version=version,
            visual_type=visual_type,
            source_page=source_page,
        )

        for chunk in chunks:
            assert chunk.visual_type == visual_type.value, (
                f"Expected visual_type='{visual_type.value}', "
                f"got '{chunk.visual_type}'"
            )
            assert chunk.source_page == source_page, (
                f"Expected source_page={source_page}, "
                f"got {chunk.source_page}"
            )
            assert chunk.document_uuid == document_uuid, (
                f"Expected document_uuid='{document_uuid}', "
                f"got '{chunk.document_uuid}'"
            )
            assert chunk.version == version, (
                f"Expected version='{version}', got '{chunk.version}'"
            )

    @given(
        description=st_description(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_type=st_visual_type(),
        source_page=st_source_page(),
    )
    @settings(max_examples=200)
    def test_metadata_dict_contains_all_required_fields(
        self,
        description: str,
        document_uuid: str,
        version: str,
        visual_type: VisualType,
        source_page: int,
    ) -> None:
        """Every VisualChunk's metadata dict must contain all required fields
        with correct values.

        Required fields: content_type, is_visual, visual_type, source_page,
        document_uuid, version.

        **Validates: Requirements 2.3, 2.5**
        """
        service = self._create_service()
        chunks = service._create_visual_chunks(
            description=description,
            document_uuid=document_uuid,
            version=version,
            visual_type=visual_type,
            source_page=source_page,
        )

        for chunk in chunks:
            # Check all required fields are present
            missing_fields = REQUIRED_METADATA_FIELDS - set(chunk.metadata.keys())
            assert not missing_fields, (
                f"Missing metadata fields: {missing_fields}. "
                f"Got keys: {set(chunk.metadata.keys())}"
            )

            # Check field values are correct
            assert chunk.metadata["content_type"] == "visual", (
                f"metadata['content_type'] expected 'visual', "
                f"got '{chunk.metadata['content_type']}'"
            )
            assert chunk.metadata["is_visual"] is True, (
                f"metadata['is_visual'] expected True, "
                f"got {chunk.metadata['is_visual']}"
            )
            assert chunk.metadata["visual_type"] == visual_type.value, (
                f"metadata['visual_type'] expected '{visual_type.value}', "
                f"got '{chunk.metadata['visual_type']}'"
            )
            assert chunk.metadata["source_page"] == source_page, (
                f"metadata['source_page'] expected {source_page}, "
                f"got {chunk.metadata['source_page']}"
            )
            assert chunk.metadata["document_uuid"] == document_uuid, (
                f"metadata['document_uuid'] expected '{document_uuid}', "
                f"got '{chunk.metadata['document_uuid']}'"
            )
            assert chunk.metadata["version"] == version, (
                f"metadata['version'] expected '{version}', "
                f"got '{chunk.metadata['version']}'"
            )
