"""Property-based tests for Knowledge Service OCR text extraction.

Tests Properties 9 and 10 from the AI Model Integration (vLLM) design document:

- Property 9: OCR page text concatenation
  For any multi-page PDF where OCR succeeds on a subset of pages, the final
  extracted text SHALL be the concatenation of successful page texts in page
  order, separated by newline characters.

- Property 10: OCR resilience — failed pages skipped
  For any PDF with N pages where K pages fail OCR (0 ≤ K < N), the system
  SHALL successfully return text from the remaining (N - K) pages without
  raising an exception, and SHALL log a warning for each failed page.

**Validates: Requirements 4.3, 4.4**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Properties 9, 10)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (4.3, 4.4)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 9: OCR page text concatenation
# Feature: Step_4-3_ai-model-integration-vllm, Property 10: OCR resilience — failed pages skipped

import logging
import logging.handlers
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.inference_client import InferenceError
from alcoabase.services.knowledge_service import KnowledgeService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate page texts: non-empty strings representing OCR output per page
st_page_texts = st.lists(
    st.text(
        min_size=1,
        max_size=200,
        alphabet=st.characters(categories=("L", "N", "Z", "P")),
    ).filter(lambda t: t.strip()),
    min_size=1,
    max_size=20,
)

# Generate number of pages (1 to 20) and a failure pattern (list of booleans)
st_num_pages = st.integers(min_value=2, max_value=20)

# Generate failure patterns: list of booleans where True = page fails
# At least one page must succeed (K < N)
st_failure_pattern = st.lists(
    st.booleans(),
    min_size=2,
    max_size=20,
).filter(lambda pattern: not all(pattern))  # At least one success


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_manager_mock() -> AsyncMock:
    """Create a mock ModelManager in gpu mode with ensure_model returning a URL."""
    manager = AsyncMock()
    manager.mode = "gpu"
    manager.ensure_model = AsyncMock(return_value="http://localhost:8000")
    return manager


def _make_settings_mock() -> object:
    """Create a mock settings object for KnowledgeService."""

    class MockSettings:
        model_embedding_dimension = 1024
        model_embedding_name = "Qwen/Qwen3-Embedding-0.6B"
        model_ocr_name = "google/gemma-4-E4B-it"
        model_manager_mode = "gpu"
        vllm_base_url = "http://localhost:8000"
        vllm_embedding_url = "http://localhost:8001"

    return MockSettings()


def _make_mock_pdf_document(num_pages: int) -> MagicMock:
    """Create a mock fitz PDF document with N pages.

    Each page has a get_pixmap method that returns a mock pixmap
    with tobytes returning fake PNG bytes.
    """
    doc = MagicMock()
    doc.__len__ = MagicMock(return_value=num_pages)

    pages = []
    for _ in range(num_pages):
        page = MagicMock()
        pixmap = MagicMock()
        pixmap.tobytes = MagicMock(return_value=b"\x89PNG\r\n\x1a\nfake_png_data")
        page.get_pixmap = MagicMock(return_value=pixmap)
        pages.append(page)

    doc.__getitem__ = MagicMock(side_effect=lambda idx: pages[idx])
    doc.close = MagicMock()
    return doc


def _make_inference_client_for_concatenation(
    page_texts: list[str],
) -> AsyncMock:
    """Create a mock InferenceClient that returns page texts in order.

    Each call to chat_completion returns the next page text from the list.
    """
    call_index = [0]

    async def mock_chat_completion(
        model: str,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: float = 90.0,
    ) -> str:
        idx = call_index[0]
        call_index[0] += 1
        return page_texts[idx]

    client = AsyncMock()
    client.chat_completion = AsyncMock(side_effect=mock_chat_completion)
    return client


def _make_inference_client_with_failures(
    page_texts: list[str],
    failure_pattern: list[bool],
) -> AsyncMock:
    """Create a mock InferenceClient that fails on specific pages.

    Args:
        page_texts: Text to return for successful pages (in order of success).
        failure_pattern: Boolean list where True means the page fails with InferenceError.
    """
    call_index = [0]
    success_index = [0]

    async def mock_chat_completion(
        model: str,
        messages: list,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        timeout: float = 90.0,
    ) -> str:
        idx = call_index[0]
        call_index[0] += 1

        if failure_pattern[idx]:
            raise InferenceError(
                f"OCR failed for page {idx + 1}",
                status_code=500,
                endpoint="/v1/chat/completions",
            )

        text_idx = success_index[0]
        success_index[0] += 1
        return page_texts[text_idx]

    client = AsyncMock()
    client.chat_completion = AsyncMock(side_effect=mock_chat_completion)
    return client


# ---------------------------------------------------------------------------
# Property 9: OCR page text concatenation
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 9: OCR page text concatenation
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(page_texts=st_page_texts)
async def test_ocr_page_text_concatenation(page_texts: list[str]) -> None:
    """For any multi-page PDF where OCR succeeds on a subset of pages, the
    final extracted text SHALL be the concatenation of successful page texts
    in page order, separated by newline characters.

    **Validates: Requirements 4.3**
    """
    num_pages = len(page_texts)

    model_manager = _make_model_manager_mock()
    client = _make_inference_client_for_concatenation(page_texts)
    mock_doc = _make_mock_pdf_document(num_pages)

    with (
        patch(
            "alcoabase.services.knowledge_service.get_settings",
            return_value=_make_settings_mock(),
        ),
        patch(
            "alcoabase.services.knowledge_service.fitz.open",
            return_value=mock_doc,
        ),
    ):
        service = KnowledgeService(
            model_manager=model_manager,
            inference_client=client,
        )

        result = await service._ocr_extract_text(b"fake_pdf_bytes")

    # The result should be all page texts concatenated with newline separators
    expected = "\n".join(page_texts)
    assert result == expected, (
        f"Expected concatenation of {num_pages} page texts with '\\n' separator.\n"
        f"Expected: {expected!r}\n"
        f"Got: {result!r}"
    )


# ---------------------------------------------------------------------------
# Property 10: OCR resilience — failed pages skipped
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 10: OCR resilience — failed pages skipped
@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(failure_pattern=st_failure_pattern)
async def test_ocr_resilience_failed_pages_skipped(
    failure_pattern: list[bool],
) -> None:
    """For any PDF with N pages where K pages fail OCR (0 ≤ K < N), the system
    SHALL successfully return text from the remaining (N - K) pages without
    raising an exception, and SHALL log a warning for each failed page.

    **Validates: Requirements 4.4**
    """
    num_pages = len(failure_pattern)
    num_failures = sum(failure_pattern)
    num_successes = num_pages - num_failures

    # Generate unique text for each successful page
    success_texts = [f"page_text_{i}" for i in range(num_successes)]

    model_manager = _make_model_manager_mock()
    client = _make_inference_client_with_failures(success_texts, failure_pattern)
    mock_doc = _make_mock_pdf_document(num_pages)

    # Use a logging handler to capture warnings instead of caplog fixture
    log_handler = logging.handlers.MemoryHandler(capacity=1000, flushLevel=logging.CRITICAL)
    ks_logger = logging.getLogger("alcoabase.services.knowledge_service")
    ks_logger.addHandler(log_handler)
    ks_logger.setLevel(logging.WARNING)

    try:
        with (
            patch(
                "alcoabase.services.knowledge_service.get_settings",
                return_value=_make_settings_mock(),
            ),
            patch(
                "alcoabase.services.knowledge_service.fitz.open",
                return_value=mock_doc,
            ),
        ):
            service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

            # Should NOT raise an exception
            result = await service._ocr_extract_text(b"fake_pdf_bytes")

        # Verify only successful page texts are in the result
        expected = "\n".join(success_texts)
        assert result == expected, (
            f"Expected text from {num_successes} successful pages.\n"
            f"Expected: {expected!r}\n"
            f"Got: {result!r}"
        )

        # Verify a warning was logged for each failed page
        warning_records = [
            r for r in log_handler.buffer
            if r.levelno == logging.WARNING and "skipping" in r.message.lower()
        ]
        assert len(warning_records) >= num_failures, (
            f"Expected at least {num_failures} warning log entries for failed pages, "
            f"got {len(warning_records)}"
        )
    finally:
        ks_logger.removeHandler(log_handler)
        log_handler.close()
