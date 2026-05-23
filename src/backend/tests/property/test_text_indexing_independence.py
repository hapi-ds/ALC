"""Property-based tests for text indexing independence from visual processing.

Tests Property 19: Text indexing independence from visual processing from the
multimodal-knowledge-base design document.

Property 19 validates that for any document submitted for indexing, text chunks
SHALL always be successfully indexed regardless of whether visual content
detection or Vision_Model interpretation succeeds or fails. Visual processing
failures SHALL not prevent or delay text chunk indexing.

**Validates: Requirements 12.1, 12.2**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 19)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/knowledge_service.py
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import KnowledgeService
from alcoabase.services.visual_content_detector import VisualPageInfo, VisualType


# ---------------------------------------------------------------------------
# Patch target: VisualContentDetector is imported locally inside the method
# from alcoabase.services.visual_content_detector, so we patch at source.
# ---------------------------------------------------------------------------

_VCD_PATCH_TARGET = (
    "alcoabase.services.visual_content_detector.VisualContentDetector"
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_document_text() -> st.SearchStrategy[str]:
    """Generate non-empty document text with at least one word.

    Returns:
        Strategy producing non-empty text strings.
    """
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=10,
        max_size=2000,
    ).filter(lambda t: len(t.split()) >= 1)


def st_visual_page_count() -> st.SearchStrategy[int]:
    """Generate number of visual pages detected (1-10).

    Returns:
        Strategy producing integer page counts.
    """
    return st.integers(min_value=1, max_value=10)


def st_document_uuid() -> st.SearchStrategy[str]:
    """Generate document UUID strings."""
    return st.uuids().map(str)


def st_version() -> st.SearchStrategy[str]:
    """Generate version strings like '1.0', '2.3'."""
    return st.from_regex(r"[1-9]\.[0-9]", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_visual_pages(count: int) -> list[VisualPageInfo]:
    """Create a list of VisualPageInfo objects for testing."""
    return [
        VisualPageInfo(
            page_number=i,
            visual_type=VisualType.DIAGRAM,
            width=612.0,
            height=792.0,
            text_area_ratio=0.1,
        )
        for i in range(count)
    ]


def _run_async(coro):
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Property 19: Text Indexing Independence from Visual Processing
# ---------------------------------------------------------------------------


class TestTextIndexingIndependence:
    """Property tests for text indexing independence from visual processing.

    For any document submitted for indexing:
    - text_chunks_count is always > 0 for non-empty documents
    - Text chunks are indexed even when visual processing fails completely
    - The IndexingResult always has text_chunks_count reflecting actual chunks

    **Validates: Requirements 12.1, 12.2**
    """

    @given(
        document_text=st_document_text(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_page_count=st_visual_page_count(),
    )
    @settings(max_examples=100)
    def test_text_chunks_indexed_when_visual_interpretation_fails(
        self,
        document_text: str,
        document_uuid: str,
        version: str,
        visual_page_count: int,
    ) -> None:
        """Text chunks are always indexed even when all visual page
        interpretations fail (return None).

        **Validates: Requirements 12.1, 12.2**
        """
        service = KnowledgeService(model_manager=None, inference_client=None)
        visual_pages = _make_visual_pages(visual_page_count)

        with (
            patch.object(
                service,
                "extract_text_with_ocr_fallback",
                new=AsyncMock(return_value=document_text),
            ),
            patch.object(
                service,
                "_interpret_visual_page",
                new=AsyncMock(return_value=None),
            ),
            patch(_VCD_PATCH_TARGET) as mock_detector_cls,
            patch.object(
                service, "_render_page_png", return_value=b"fake_png"
            ),
        ):
            mock_detector = MagicMock()
            mock_detector.detect_visual_pages.return_value = visual_pages
            mock_detector_cls.return_value = mock_detector

            result = _run_async(
                service.index_document_with_visuals(
                    file_bytes=b"fake document content",
                    content_type="application/pdf",
                    document_uuid=document_uuid,
                    version=version,
                )
            )

        expected_chunks = service.chunk_text(document_text)
        assert result.text_chunks_count == len(expected_chunks), (
            f"Expected text_chunks_count={len(expected_chunks)}, "
            f"got {result.text_chunks_count}. "
            f"Text indexing must succeed regardless of visual failures."
        )
        assert result.text_chunks_count > 0
        assert result.visual_chunks_count == 0

    @given(
        document_text=st_document_text(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_page_count=st_visual_page_count(),
    )
    @settings(max_examples=100)
    def test_text_chunks_indexed_when_visual_interpretation_raises(
        self,
        document_text: str,
        document_uuid: str,
        version: str,
        visual_page_count: int,
    ) -> None:
        """Text chunks are always indexed even when visual page interpretation
        raises exceptions.

        **Validates: Requirements 12.1, 12.2**
        """
        service = KnowledgeService(model_manager=None, inference_client=None)
        visual_pages = _make_visual_pages(visual_page_count)

        with (
            patch.object(
                service,
                "extract_text_with_ocr_fallback",
                new=AsyncMock(return_value=document_text),
            ),
            patch.object(
                service,
                "_interpret_visual_page",
                new=AsyncMock(
                    side_effect=RuntimeError("Vision model crashed")
                ),
            ),
            patch(_VCD_PATCH_TARGET) as mock_detector_cls,
            patch.object(
                service, "_render_page_png", return_value=b"fake_png"
            ),
        ):
            mock_detector = MagicMock()
            mock_detector.detect_visual_pages.return_value = visual_pages
            mock_detector_cls.return_value = mock_detector

            result = _run_async(
                service.index_document_with_visuals(
                    file_bytes=b"fake document content",
                    content_type="application/pdf",
                    document_uuid=document_uuid,
                    version=version,
                )
            )

        expected_chunks = service.chunk_text(document_text)
        assert result.text_chunks_count == len(expected_chunks), (
            f"Expected text_chunks_count={len(expected_chunks)}, "
            f"got {result.text_chunks_count}. "
            f"Visual exceptions must not prevent text indexing."
        )
        assert result.text_chunks_count > 0
        assert result.visual_indexing_status in ("pending", "partial"), (
            f"Expected 'pending' or 'partial' when visual processing fails, "
            f"got '{result.visual_indexing_status}'"
        )

    @given(
        document_text=st_document_text(),
        document_uuid=st_document_uuid(),
        version=st_version(),
        visual_page_count=st_visual_page_count(),
    )
    @settings(max_examples=100)
    def test_text_chunks_indexed_when_render_page_raises(
        self,
        document_text: str,
        document_uuid: str,
        version: str,
        visual_page_count: int,
    ) -> None:
        """Text chunks are always indexed even when page rendering fails.

        **Validates: Requirements 12.1, 12.2**
        """
        service = KnowledgeService(model_manager=None, inference_client=None)
        visual_pages = _make_visual_pages(visual_page_count)

        with (
            patch.object(
                service,
                "extract_text_with_ocr_fallback",
                new=AsyncMock(return_value=document_text),
            ),
            patch.object(
                service,
                "_render_page_png",
                side_effect=RuntimeError("Page render failed"),
            ),
            patch(_VCD_PATCH_TARGET) as mock_detector_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.detect_visual_pages.return_value = visual_pages
            mock_detector_cls.return_value = mock_detector

            result = _run_async(
                service.index_document_with_visuals(
                    file_bytes=b"fake document content",
                    content_type="application/pdf",
                    document_uuid=document_uuid,
                    version=version,
                )
            )

        expected_chunks = service.chunk_text(document_text)
        assert result.text_chunks_count == len(expected_chunks), (
            f"Expected text_chunks_count={len(expected_chunks)}, "
            f"got {result.text_chunks_count}. "
            f"Render failures must not prevent text indexing."
        )
        assert result.text_chunks_count > 0

    @given(
        document_text=st_document_text(),
        document_uuid=st_document_uuid(),
        version=st_version(),
    )
    @settings(max_examples=100)
    def test_text_chunks_indexed_when_visual_detection_raises(
        self,
        document_text: str,
        document_uuid: str,
        version: str,
    ) -> None:
        """Text chunks are always indexed even when visual content detection
        itself raises an exception.

        Text indexing happens BEFORE visual detection in the pipeline,
        so text is already stored even if detection crashes.

        **Validates: Requirements 12.1, 12.2**
        """
        service = KnowledgeService(model_manager=None, inference_client=None)

        with (
            patch.object(
                service,
                "extract_text_with_ocr_fallback",
                new=AsyncMock(return_value=document_text),
            ),
            patch(_VCD_PATCH_TARGET) as mock_detector_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.detect_visual_pages.side_effect = RuntimeError(
                "Detection crashed"
            )
            mock_detector_cls.return_value = mock_detector

            # Text is indexed BEFORE visual detection runs.
            # If detection raises, text should already be stored.
            try:
                result = _run_async(
                    service.index_document_with_visuals(
                        file_bytes=b"fake document content",
                        content_type="application/pdf",
                        document_uuid=document_uuid,
                        version=version,
                    )
                )
                expected_chunks = service.chunk_text(document_text)
                assert result.text_chunks_count == len(expected_chunks)
                assert result.text_chunks_count > 0
            except RuntimeError:
                # Even if the method raises, text chunks are already
                # in the index because text indexing happens first
                index_key = f"{document_uuid}:{version}"
                assert index_key in service._index, (
                    "Text chunks must be indexed before visual detection. "
                    "Even if detection raises, text should be stored."
                )
                expected_chunks = service.chunk_text(document_text)
                assert len(service._index[index_key].chunks) == len(
                    expected_chunks
                )

    @given(
        document_text=st_document_text(),
        document_uuid=st_document_uuid(),
        version=st_version(),
    )
    @settings(max_examples=100)
    def test_text_chunks_count_reflects_actual_chunks(
        self,
        document_text: str,
        document_uuid: str,
        version: str,
    ) -> None:
        """The IndexingResult.text_chunks_count always reflects the actual
        number of text chunks created from the document content.

        **Validates: Requirements 12.1, 12.2**
        """
        service = KnowledgeService(model_manager=None, inference_client=None)

        with (
            patch.object(
                service,
                "extract_text_with_ocr_fallback",
                new=AsyncMock(return_value=document_text),
            ),
            patch(_VCD_PATCH_TARGET) as mock_detector_cls,
        ):
            mock_detector = MagicMock()
            mock_detector.detect_visual_pages.return_value = []
            mock_detector_cls.return_value = mock_detector

            result = _run_async(
                service.index_document_with_visuals(
                    file_bytes=b"fake document content",
                    content_type="application/pdf",
                    document_uuid=document_uuid,
                    version=version,
                )
            )

        expected_chunks = service.chunk_text(document_text)
        assert result.text_chunks_count == len(expected_chunks), (
            f"text_chunks_count ({result.text_chunks_count}) must equal "
            f"actual chunk count ({len(expected_chunks)}) from chunk_text()"
        )
        assert result.text_chunks_count > 0, (
            "Non-empty document must always produce at least one text chunk."
        )
