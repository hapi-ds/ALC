"""Unit tests for OCR text extraction in KnowledgeService.

Tests multimodal message format, sequential page processing,
page failure skipping, all-pages-fail behavior, zero-page PDF,
500-page limit, 90s per-page timeout, and mock mode.

References:
    - Task 7.4: Write unit tests for OCR extraction
    - Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.inference_client import (
    InferenceError,
    InferenceTimeoutError,
)
from alcoabase.services.knowledge_service import KnowledgeService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_page(text: str = "") -> MagicMock:
    """Create a mock fitz page with get_text and get_pixmap."""
    page = MagicMock()
    page.get_text.return_value = text

    # Mock pixmap that returns PNG bytes
    pixmap = MagicMock()
    pixmap.tobytes.return_value = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    page.get_pixmap.return_value = pixmap

    return page


def _make_mock_doc(page_count: int, has_text: bool = False) -> MagicMock:
    """Create a mock fitz document with the given number of pages.

    Args:
        page_count: Number of pages in the mock document.
        has_text: If True, pages return extractable text (not scanned).
    """
    doc = MagicMock()
    doc.__len__ = MagicMock(return_value=page_count)

    pages = []
    for _ in range(page_count):
        page_text = "Some text" if has_text else ""
        pages.append(_make_mock_page(page_text))

    doc.__getitem__ = MagicMock(side_effect=lambda idx: pages[idx])
    doc.__iter__ = MagicMock(return_value=iter(pages))
    doc.close = MagicMock()

    return doc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_model_manager() -> MagicMock:
    """Create a mock ModelManager in gpu mode."""
    mm = MagicMock()
    mm.mode = "gpu"
    mm.ensure_model = AsyncMock(return_value="http://localhost:8000")
    return mm


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient that returns OCR text."""
    client = AsyncMock()

    async def _chat_completion(
        model: str,
        messages: list,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        timeout: float = 60.0,
    ) -> str:
        """Return a simple extracted text response."""
        return "Extracted text from page"

    client.chat_completion = AsyncMock(side_effect=_chat_completion)
    return client


@pytest.fixture
def knowledge_service(
    mock_model_manager: MagicMock,
    mock_inference_client: AsyncMock,
) -> KnowledgeService:
    """Create a KnowledgeService with mocked dependencies in gpu mode."""
    with patch("alcoabase.services.knowledge_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.model_embedding_dimension = 1024
        settings.model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        settings.model_ocr_name = "google/gemma-4-E4B-it"
        mock_settings.return_value = settings

        svc = KnowledgeService(
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
        )
    return svc


@pytest.fixture
def mock_knowledge_service() -> KnowledgeService:
    """Create a KnowledgeService in mock mode (no model_manager)."""
    with patch("alcoabase.services.knowledge_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.model_embedding_dimension = 1024
        settings.model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        settings.model_ocr_name = "google/gemma-4-E4B-it"
        mock_settings.return_value = settings

        svc = KnowledgeService(model_manager=None, inference_client=None)
    return svc


# ---------------------------------------------------------------------------
# Tests: Multimodal message format
# ---------------------------------------------------------------------------


class TestMultimodalMessageFormat:
    """Tests for OCR multimodal message structure (Requirement 4.2)."""

    @pytest.mark.asyncio
    async def test_message_contains_system_prompt(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Messages should include a system prompt for text extraction."""
        mock_doc = _make_mock_doc(page_count=1)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        call_args = mock_inference_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1]["messages"]

        # First message should be system role
        assert messages[0]["role"] == "system"
        assert "Extract all visible text" in messages[0]["content"]

    @pytest.mark.asyncio
    async def test_message_contains_base64_image(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """User message should contain base64-encoded image URL."""
        mock_doc = _make_mock_doc(page_count=1)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        call_args = mock_inference_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1]["messages"]

        # Second message should be user role with multimodal content
        user_msg = messages[1]
        assert user_msg["role"] == "user"
        assert isinstance(user_msg["content"], list)

        # Find image_url content part
        image_part = next(
            (p for p in user_msg["content"] if p["type"] == "image_url"), None
        )
        assert image_part is not None
        assert image_part["image_url"]["url"].startswith("data:image/png;base64,")

    @pytest.mark.asyncio
    async def test_message_contains_text_instruction(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """User message should contain text instruction for extraction."""
        mock_doc = _make_mock_doc(page_count=1)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        call_args = mock_inference_client.chat_completion.call_args
        messages = call_args.kwargs.get("messages") or call_args[1]["messages"]

        user_msg = messages[1]
        text_part = next(
            (p for p in user_msg["content"] if p["type"] == "text"), None
        )
        assert text_part is not None
        assert "Extract all text" in text_part["text"]

    @pytest.mark.asyncio
    async def test_ocr_request_params(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """OCR request should use correct model, max_tokens, temperature, timeout."""
        mock_doc = _make_mock_doc(page_count=1)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        call_args = mock_inference_client.chat_completion.call_args
        kwargs = call_args.kwargs if call_args.kwargs else {}

        assert kwargs.get("model") == "google/gemma-4-E4B-it"
        assert kwargs.get("max_tokens") == 4096
        assert kwargs.get("temperature") == 0.1
        assert kwargs.get("timeout") == 90.0


# ---------------------------------------------------------------------------
# Tests: Sequential page processing
# ---------------------------------------------------------------------------


class TestSequentialPageProcessing:
    """Tests for sequential page-by-page OCR processing (Requirement 4.6)."""

    @pytest.mark.asyncio
    async def test_chat_completion_called_once_per_page(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """chat_completion should be called exactly once per page."""
        mock_doc = _make_mock_doc(page_count=3)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert mock_inference_client.chat_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_pages_processed_in_order(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Pages should be processed sequentially in page order."""
        call_order: list[int] = []

        async def _track_calls(
            model: str,
            messages: list,
            max_tokens: int = 2048,
            temperature: float = 0.3,
            timeout: float = 60.0,
        ) -> str:
            call_order.append(len(call_order))
            return f"Page {len(call_order)} text"

        mock_inference_client.chat_completion = AsyncMock(side_effect=_track_calls)
        mock_doc = _make_mock_doc(page_count=4)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert call_order == [0, 1, 2, 3]
        assert "Page 1 text" in result
        assert "Page 4 text" in result

    @pytest.mark.asyncio
    async def test_successful_pages_concatenated_with_newlines(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Successful page texts should be joined with newline separators."""
        page_texts = ["First page", "Second page", "Third page"]
        call_idx = [0]

        async def _return_page_text(
            model: str,
            messages: list,
            max_tokens: int = 2048,
            temperature: float = 0.3,
            timeout: float = 60.0,
        ) -> str:
            idx = call_idx[0]
            call_idx[0] += 1
            return page_texts[idx]

        mock_inference_client.chat_completion = AsyncMock(side_effect=_return_page_text)
        mock_doc = _make_mock_doc(page_count=3)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert result == "First page\nSecond page\nThird page"


# ---------------------------------------------------------------------------
# Tests: Page failure skipping with warning log
# ---------------------------------------------------------------------------


class TestPageFailureSkipping:
    """Tests for skipping failed pages with warning (Requirement 4.4)."""

    @pytest.mark.asyncio
    async def test_failed_page_skipped_continues_processing(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """A failed page should be skipped; remaining pages still processed."""
        call_idx = [0]

        async def _fail_second_page(
            model: str,
            messages: list,
            max_tokens: int = 2048,
            temperature: float = 0.3,
            timeout: float = 60.0,
        ) -> str:
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 1:
                raise InferenceError(
                    "HTTP 500 error",
                    status_code=500,
                    endpoint="http://localhost:8000/v1/chat/completions",
                )
            return f"Page {idx + 1} text"

        mock_inference_client.chat_completion = AsyncMock(
            side_effect=_fail_second_page
        )
        mock_doc = _make_mock_doc(page_count=3)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        # Page 2 failed, so result should have page 1 and page 3 only
        assert "Page 1 text" in result
        assert "Page 3 text" in result
        assert mock_inference_client.chat_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_failed_page_logs_warning(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Failed pages should produce a warning log with page number."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=[
                "Page 1 text",
                InferenceError("HTTP 500", status_code=500, endpoint="test"),
                "Page 3 text",
            ]
        )
        mock_doc = _make_mock_doc(page_count=3)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            with patch(
                "alcoabase.services.knowledge_service.logger"
            ) as mock_logger:
                await knowledge_service._ocr_extract_text(b"fake pdf bytes")

                # Should have at least one warning call about the failed page
                warning_calls = mock_logger.warning.call_args_list
                warning_messages = [
                    str(call) for call in warning_calls
                ]
                assert any("2" in msg for msg in warning_messages)


# ---------------------------------------------------------------------------
# Tests: All pages fail returns empty string
# ---------------------------------------------------------------------------


class TestAllPagesFail:
    """Tests for complete OCR failure (Requirement 4.5)."""

    @pytest.mark.asyncio
    async def test_all_pages_fail_returns_empty_string(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """If all pages fail OCR, return empty string."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceError(
                "HTTP 500 error",
                status_code=500,
                endpoint="http://localhost:8000/v1/chat/completions",
            )
        )
        mock_doc = _make_mock_doc(page_count=3)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert result == ""

    @pytest.mark.asyncio
    async def test_all_pages_fail_logs_error(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Complete OCR failure should log an error."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceError(
                "HTTP 500 error",
                status_code=500,
                endpoint="test",
            )
        )
        mock_doc = _make_mock_doc(page_count=2)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            with patch(
                "alcoabase.services.knowledge_service.logger"
            ) as mock_logger:
                result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

                assert result == ""
                mock_logger.error.assert_called_once()
                error_msg = str(mock_logger.error.call_args)
                assert "OCR failure" in error_msg or "failed" in error_msg.lower()


# ---------------------------------------------------------------------------
# Tests: Zero-page PDF returns empty string
# ---------------------------------------------------------------------------


class TestZeroPagePDF:
    """Tests for zero-page PDF handling (Requirement 4.9)."""

    @pytest.mark.asyncio
    async def test_zero_page_pdf_returns_empty_string(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """A PDF with zero pages should return empty string."""
        mock_doc = _make_mock_doc(page_count=0)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert result == ""
        mock_inference_client.chat_completion.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_page_pdf_logs_warning(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Zero-page PDF should log a warning."""
        mock_doc = _make_mock_doc(page_count=0)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            with patch(
                "alcoabase.services.knowledge_service.logger"
            ) as mock_logger:
                await knowledge_service._ocr_extract_text(b"fake pdf bytes")

                mock_logger.warning.assert_called()
                warning_msg = str(mock_logger.warning.call_args)
                assert "zero" in warning_msg.lower() or "0" in warning_msg


# ---------------------------------------------------------------------------
# Tests: 500-page limit
# ---------------------------------------------------------------------------


class TestPageLimit:
    """Tests for 500-page maximum processing limit (Requirement 4.1)."""

    @pytest.mark.asyncio
    async def test_600_page_pdf_only_processes_500(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """A 600-page PDF should only process the first 500 pages."""
        mock_doc = _make_mock_doc(page_count=600)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert mock_inference_client.chat_completion.call_count == 500

    @pytest.mark.asyncio
    async def test_500_page_pdf_processes_all(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """A 500-page PDF should process all 500 pages."""
        mock_doc = _make_mock_doc(page_count=500)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert mock_inference_client.chat_completion.call_count == 500

    @pytest.mark.asyncio
    async def test_page_limit_logs_warning(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Exceeding 500 pages should log a warning."""
        mock_doc = _make_mock_doc(page_count=600)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            with patch(
                "alcoabase.services.knowledge_service.logger"
            ) as mock_logger:
                await knowledge_service._ocr_extract_text(b"fake pdf bytes")

                warning_calls = [
                    str(call) for call in mock_logger.warning.call_args_list
                ]
                assert any(
                    "500" in msg and "600" in msg for msg in warning_calls
                )


# ---------------------------------------------------------------------------
# Tests: 90s per-page timeout handling
# ---------------------------------------------------------------------------


class TestPerPageTimeout:
    """Tests for 90s per-page timeout (Requirement 4.7)."""

    @pytest.mark.asyncio
    async def test_timeout_page_skipped_others_continue(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """A page that times out should be skipped; others still processed."""
        call_idx = [0]

        async def _timeout_second_page(
            model: str,
            messages: list,
            max_tokens: int = 2048,
            temperature: float = 0.3,
            timeout: float = 60.0,
        ) -> str:
            idx = call_idx[0]
            call_idx[0] += 1
            if idx == 1:
                raise InferenceTimeoutError(
                    "Request timed out after 90.0s",
                    endpoint="http://localhost:8000/v1/chat/completions",
                )
            return f"Page {idx + 1} text"

        mock_inference_client.chat_completion = AsyncMock(
            side_effect=_timeout_second_page
        )
        mock_doc = _make_mock_doc(page_count=3)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            result = await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert "Page 1 text" in result
        assert "Page 3 text" in result

    @pytest.mark.asyncio
    async def test_timeout_logs_warning_with_page_number(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Timeout should log a warning mentioning the page number."""
        mock_inference_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError(
                "Request timed out after 90.0s",
                endpoint="http://localhost:8000/v1/chat/completions",
            )
        )
        mock_doc = _make_mock_doc(page_count=1)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            with patch(
                "alcoabase.services.knowledge_service.logger"
            ) as mock_logger:
                await knowledge_service._ocr_extract_text(b"fake pdf bytes")

                warning_calls = mock_logger.warning.call_args_list
                assert len(warning_calls) >= 1
                # Should mention timeout and page number
                warning_msg = str(warning_calls[0])
                assert "timeout" in warning_msg.lower() or "90" in warning_msg

    @pytest.mark.asyncio
    async def test_timeout_uses_90s(
        self,
        knowledge_service: KnowledgeService,
        mock_inference_client: AsyncMock,
    ) -> None:
        """chat_completion should be called with timeout=90.0 for OCR."""
        mock_doc = _make_mock_doc(page_count=1)

        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            await knowledge_service._ocr_extract_text(b"fake pdf bytes")

        call_args = mock_inference_client.chat_completion.call_args
        kwargs = call_args.kwargs if call_args.kwargs else {}
        assert kwargs.get("timeout") == 90.0


# ---------------------------------------------------------------------------
# Tests: Mock mode returns placeholder text
# ---------------------------------------------------------------------------


class TestMockMode:
    """Tests for mock mode OCR behavior (Requirement 4.8)."""

    @pytest.mark.asyncio
    async def test_mock_mode_returns_placeholder_text(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode should return the placeholder OCR text."""
        result = await mock_knowledge_service._ocr_extract_text(b"fake pdf bytes")

        assert result == (
            "[OCR_PENDING: Scanned PDF text extraction requires Model_Manager]"
        )

    @pytest.mark.asyncio
    async def test_mock_mode_no_fitz_calls(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode should not open the PDF or process pages."""
        with patch("alcoabase.services.knowledge_service.fitz") as mock_fitz:
            await mock_knowledge_service._ocr_extract_text(b"fake pdf bytes")
            mock_fitz.open.assert_not_called()

    @pytest.mark.asyncio
    async def test_mock_mode_no_inference_client_needed(
        self,
        mock_knowledge_service: KnowledgeService,
    ) -> None:
        """Mock mode should work without inference_client."""
        assert mock_knowledge_service._inference_client is None
        assert mock_knowledge_service._model_manager is None

        # Should not raise
        result = await mock_knowledge_service._ocr_extract_text(b"fake pdf bytes")
        assert "[OCR_PENDING" in result
