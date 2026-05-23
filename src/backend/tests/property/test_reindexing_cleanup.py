"""Property-based tests for re-indexing cleanup of stale Visual_Chunks.

Tests Property 21: Re-indexing removes stale Visual_Chunks from the
multimodal-knowledge-base design document.

Property 21 validates that when a document is re-indexed, the
_remove_visual_chunks() method removes all previous Visual_Chunks for
that document_uuid and version before new ones are created, and that
other documents' visual chunks are not affected.

**Validates: Requirements 12.4**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 21)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/knowledge_service.py
"""

from dataclasses import field

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import (
    IndexedDocument,
    KnowledgeService,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_document_uuid() -> st.SearchStrategy[str]:
    """Generate random document UUIDs (simplified UUID-like strings).

    Returns:
        Strategy producing UUID-like strings.
    """
    return st.uuids().map(str)


def st_version() -> st.SearchStrategy[str]:
    """Generate random version strings like '1.0', '2.3', etc.

    Returns:
        Strategy producing version strings.
    """
    return st.builds(
        lambda major, minor: f"{major}.{minor}",
        major=st.integers(min_value=1, max_value=20),
        minor=st.integers(min_value=0, max_value=9),
    )


def st_visual_chunk_count() -> st.SearchStrategy[int]:
    """Generate random visual chunk counts (1-20).

    Returns:
        Strategy producing chunk counts.
    """
    return st.integers(min_value=1, max_value=20)


def st_page_number() -> st.SearchStrategy[int]:
    """Generate random page numbers (0-indexed).

    Returns:
        Strategy producing page numbers.
    """
    return st.integers(min_value=0, max_value=99)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _make_visual_index_key(document_uuid: str, version: str, page: int, index: int) -> str:
    """Create a visual chunk index key matching the production format.

    Args:
        document_uuid: Document UUID.
        version: Document version.
        page: Page number.
        index: Chunk index within the page.

    Returns:
        Index key string in the format "{document_uuid}:{version}:visual:{page}:{index}".
    """
    return f"{document_uuid}:{version}:visual:{page}:{index}"


def _make_text_index_key(document_uuid: str, version: str) -> str:
    """Create a text chunk index key matching the production format.

    Args:
        document_uuid: Document UUID.
        version: Document version.

    Returns:
        Index key string in the format "{document_uuid}:{version}".
    """
    return f"{document_uuid}:{version}"


def _create_dummy_indexed_document(document_uuid: str, version: str) -> IndexedDocument:
    """Create a minimal IndexedDocument for testing.

    Args:
        document_uuid: Document UUID.
        version: Document version.

    Returns:
        An IndexedDocument with placeholder data.
    """
    return IndexedDocument(
        document_uuid=document_uuid,
        version=version,
        chunks=["dummy chunk text"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadata={"content_type": "visual", "is_visual": True},
    )


def _populate_visual_chunks(
    service: KnowledgeService,
    document_uuid: str,
    version: str,
    num_chunks: int,
    pages: list[int] | None = None,
) -> list[str]:
    """Populate the service index with visual chunks for a document.

    Args:
        service: KnowledgeService instance.
        document_uuid: Document UUID.
        version: Document version.
        num_chunks: Number of visual chunks to create.
        pages: Optional list of page numbers to distribute chunks across.

    Returns:
        List of index keys that were created.
    """
    keys_created = []
    if pages is None:
        pages = list(range(num_chunks))

    for i in range(num_chunks):
        page = pages[i % len(pages)]
        key = _make_visual_index_key(document_uuid, version, page, i)
        service._index[key] = _create_dummy_indexed_document(document_uuid, version)
        keys_created.append(key)

    return keys_created


# ---------------------------------------------------------------------------
# Property 21: Re-indexing removes stale Visual_Chunks
# ---------------------------------------------------------------------------


class TestReindexingCleanup:
    """Property tests for re-indexing cleanup of stale Visual_Chunks.

    Verifies that _remove_visual_chunks() correctly removes all visual
    chunks for a given document_uuid+version, and does not affect other
    documents' visual chunks.

    **Validates: Requirements 12.4**
    """

    @given(
        document_uuid=st_document_uuid(),
        version=st_version(),
        num_chunks=st_visual_chunk_count(),
    )
    @settings(max_examples=200)
    def test_all_visual_chunks_removed_for_target_document(
        self,
        document_uuid: str,
        version: str,
        num_chunks: int,
    ) -> None:
        """After _remove_visual_chunks(), no old visual chunks remain for
        the target document_uuid+version.

        **Validates: Requirements 12.4**
        """
        service = KnowledgeService()

        # Populate visual chunks for the target document
        _populate_visual_chunks(service, document_uuid, version, num_chunks)

        # Verify chunks exist before removal
        visual_keys_before = [
            k for k in service._index
            if k.startswith(f"{document_uuid}:{version}:visual:")
        ]
        assert len(visual_keys_before) == num_chunks

        # Perform removal
        service._remove_visual_chunks(document_uuid, version)

        # Verify no visual chunks remain for this document+version
        visual_keys_after = [
            k for k in service._index
            if k.startswith(f"{document_uuid}:{version}:visual:")
        ]
        assert visual_keys_after == [], (
            f"Expected no visual chunks for {document_uuid}:{version} after removal, "
            f"but found {len(visual_keys_after)} keys: {visual_keys_after}"
        )

    @given(
        target_uuid=st_document_uuid(),
        target_version=st_version(),
        target_chunks=st_visual_chunk_count(),
        other_uuid=st_document_uuid(),
        other_version=st_version(),
        other_chunks=st_visual_chunk_count(),
    )
    @settings(max_examples=200)
    def test_other_documents_visual_chunks_not_affected(
        self,
        target_uuid: str,
        target_version: str,
        target_chunks: int,
        other_uuid: str,
        other_version: str,
        other_chunks: int,
    ) -> None:
        """Other documents' visual chunks are not affected by removal.

        **Validates: Requirements 12.4**
        """
        # Ensure the two documents are distinct
        if target_uuid == other_uuid and target_version == other_version:
            other_version = target_version + ".1"

        service = KnowledgeService()

        # Populate visual chunks for both documents
        _populate_visual_chunks(service, target_uuid, target_version, target_chunks)
        other_keys = _populate_visual_chunks(
            service, other_uuid, other_version, other_chunks
        )

        # Perform removal on target only
        service._remove_visual_chunks(target_uuid, target_version)

        # Verify other document's chunks are intact
        remaining_other_keys = [
            k for k in service._index
            if k.startswith(f"{other_uuid}:{other_version}:visual:")
        ]
        assert len(remaining_other_keys) == other_chunks, (
            f"Expected {other_chunks} visual chunks for other document "
            f"{other_uuid}:{other_version}, but found {len(remaining_other_keys)}"
        )

        # Verify each specific key still exists
        for key in other_keys:
            assert key in service._index, (
                f"Other document's visual chunk key '{key}' was incorrectly removed"
            )

    @given(
        document_uuid=st_document_uuid(),
        version=st_version(),
        num_visual_chunks=st_visual_chunk_count(),
    )
    @settings(max_examples=200)
    def test_text_chunks_not_affected_by_visual_removal(
        self,
        document_uuid: str,
        version: str,
        num_visual_chunks: int,
    ) -> None:
        """Text chunks for the same document are not affected by visual removal.

        **Validates: Requirements 12.4**
        """
        service = KnowledgeService()

        # Add text chunk for the document (key format: "{uuid}:{version}")
        text_key = _make_text_index_key(document_uuid, version)
        service._index[text_key] = IndexedDocument(
            document_uuid=document_uuid,
            version=version,
            chunks=["text content here"],
            embeddings=[[0.5, 0.6, 0.7]],
            metadata={"content_type": "text"},
        )

        # Add visual chunks for the same document
        _populate_visual_chunks(service, document_uuid, version, num_visual_chunks)

        # Perform visual chunk removal
        service._remove_visual_chunks(document_uuid, version)

        # Verify text chunk is still present
        assert text_key in service._index, (
            f"Text chunk key '{text_key}' was incorrectly removed during "
            f"visual chunk cleanup"
        )
        assert service._index[text_key].chunks == ["text content here"]

    @given(
        document_uuid=st_document_uuid(),
        version=st_version(),
    )
    @settings(max_examples=100)
    def test_removal_on_empty_index_is_safe(
        self,
        document_uuid: str,
        version: str,
    ) -> None:
        """Calling _remove_visual_chunks() when no visual chunks exist does not error.

        **Validates: Requirements 12.4**
        """
        service = KnowledgeService()

        # Should not raise any exception
        service._remove_visual_chunks(document_uuid, version)

        # Index should remain empty
        assert len(service._index) == 0
