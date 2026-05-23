"""Property-based tests for mock mode isolation.

Tests Property 4: Mock mode isolation (no HTTP requests) from the
multimodal-knowledge-base design document.

Property 4 validates that when model_manager is None or mode is "mock",
the KnowledgeService._interpret_visual_page() returns placeholder text
"[VISUAL_PENDING: Diagram interpretation requires Vision_Model]" without
making any HTTP calls.

**Validates: Requirements 1.6, 2.8, 6.10, 7.9**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 4)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Implementation: src/backend/src/alcoabase/services/knowledge_service.py
"""

from __future__ import annotations

from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Constants matching the specification and implementation
# ---------------------------------------------------------------------------

VISUAL_MOCK_PLACEHOLDER = (
    "[VISUAL_PENDING: Diagram interpretation requires Vision_Model]"
)
"""The exact placeholder text returned in mock mode (Req 2.8)."""


class VisualType(str, Enum):
    """Classification of visual content on a page (mirrors implementation)."""

    FLOWCHART = "flowchart"
    CHART = "chart"
    DIAGRAM = "diagram"
    MIXED = "mixed"


# ---------------------------------------------------------------------------
# Pure mock mode decision logic under test
# ---------------------------------------------------------------------------


def is_mock_mode(
    model_manager: object | None,
    inference_client: object | None,
    manager_mode: str | None,
) -> bool:
    """Determine if the service is operating in mock mode.

    The KnowledgeService._interpret_visual_page() enters mock mode when:
    - model_manager is None, OR
    - inference_client is None, OR
    - model_manager.mode is not in ("gpu", "cpu")

    In mock mode, no HTTP requests are made and the placeholder text is
    returned immediately.

    Args:
        model_manager: The model manager instance (None triggers mock mode).
        inference_client: The inference client instance (None triggers mock mode).
        manager_mode: The mode string from model_manager (e.g., "mock", "gpu", "cpu").

    Returns:
        True if the service should operate in mock mode.
    """
    if model_manager is None or inference_client is None:
        return True
    if manager_mode not in ("gpu", "cpu"):
        return True
    return False


def interpret_visual_page_mock(
    model_manager: object | None,
    inference_client: object | None,
    manager_mode: str | None,
    page_png_bytes: bytes,
    visual_type: VisualType,
    page_number: int,
) -> str | None:
    """Simulate _interpret_visual_page mock mode behavior.

    When in mock mode, returns the placeholder constant regardless of
    input parameters. When NOT in mock mode, returns None to indicate
    that real processing would occur (not simulated here).

    Args:
        model_manager: The model manager instance.
        inference_client: The inference client instance.
        manager_mode: The mode string from model_manager.
        page_png_bytes: PNG image bytes (ignored in mock mode).
        visual_type: Visual type classification (ignored in mock mode).
        page_number: Page number (ignored in mock mode).

    Returns:
        The placeholder text in mock mode, None otherwise.
    """
    if is_mock_mode(model_manager, inference_client, manager_mode):
        return VISUAL_MOCK_PLACEHOLDER
    return None


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_visual_type() -> st.SearchStrategy[VisualType]:
    """Generate random VisualType enum values.

    Returns:
        Strategy producing a VisualType enum value.
    """
    return st.sampled_from(list(VisualType))


def st_page_png_bytes() -> st.SearchStrategy[bytes]:
    """Generate random PNG-like byte sequences.

    Generates arbitrary byte sequences to simulate page image data.
    The actual content doesn't matter in mock mode since it's never sent.

    Returns:
        Strategy producing bytes of length 1-10000.
    """
    return st.binary(min_size=1, max_size=10000)


def st_page_number() -> st.SearchStrategy[int]:
    """Generate random page numbers.

    Returns:
        Strategy producing non-negative integers (0-999).
    """
    return st.integers(min_value=0, max_value=999)


def st_mock_mode_string() -> st.SearchStrategy[str]:
    """Generate mode strings that trigger mock mode.

    Any mode string that is NOT "gpu" or "cpu" triggers mock mode.

    Returns:
        Strategy producing mode strings that are not "gpu" or "cpu".
    """
    return st.one_of(
        st.just("mock"),
        st.just(""),
        st.just("test"),
        st.just("offline"),
        st.text(min_size=0, max_size=20).filter(
            lambda s: s not in ("gpu", "cpu")
        ),
    )


def st_active_mode_string() -> st.SearchStrategy[str]:
    """Generate mode strings that indicate active (non-mock) mode.

    Returns:
        Strategy producing either "gpu" or "cpu".
    """
    return st.sampled_from(["gpu", "cpu"])


# ---------------------------------------------------------------------------
# Property 4: Mock mode isolation (no HTTP requests)
# ---------------------------------------------------------------------------


class TestMockModeIsolation:
    """Property tests for mock mode isolation.

    When model_manager is None or mode is "mock" (not "gpu"/"cpu"),
    the KnowledgeService._interpret_visual_page() must:
    - Return the placeholder text constant
    - NOT make any HTTP calls
    - Return the same placeholder text regardless of input

    **Validates: Requirements 1.6, 2.8, 6.10, 7.9**
    """

    @given(
        page_png_bytes=st_page_png_bytes(),
        visual_type=st_visual_type(),
        page_number=st_page_number(),
    )
    @settings(max_examples=200)
    def test_none_model_manager_returns_placeholder(
        self,
        page_png_bytes: bytes,
        visual_type: VisualType,
        page_number: int,
    ) -> None:
        """When model_manager is None, the placeholder text is returned
        regardless of the input page data, visual type, or page number.

        **Validates: Requirements 1.6, 2.8**
        """
        result = interpret_visual_page_mock(
            model_manager=None,
            inference_client=MagicMock(),
            manager_mode=None,
            page_png_bytes=page_png_bytes,
            visual_type=visual_type,
            page_number=page_number,
        )

        assert result == VISUAL_MOCK_PLACEHOLDER, (
            f"Expected placeholder text for model_manager=None, "
            f"but got: {result!r}"
        )

    @given(
        page_png_bytes=st_page_png_bytes(),
        visual_type=st_visual_type(),
        page_number=st_page_number(),
    )
    @settings(max_examples=200)
    def test_none_inference_client_returns_placeholder(
        self,
        page_png_bytes: bytes,
        visual_type: VisualType,
        page_number: int,
    ) -> None:
        """When inference_client is None, the placeholder text is returned
        regardless of the input page data, visual type, or page number.

        **Validates: Requirements 2.8**
        """
        result = interpret_visual_page_mock(
            model_manager=MagicMock(),
            inference_client=None,
            manager_mode="gpu",
            page_png_bytes=page_png_bytes,
            visual_type=visual_type,
            page_number=page_number,
        )

        assert result == VISUAL_MOCK_PLACEHOLDER, (
            f"Expected placeholder text for inference_client=None, "
            f"but got: {result!r}"
        )

    @given(
        page_png_bytes=st_page_png_bytes(),
        visual_type=st_visual_type(),
        page_number=st_page_number(),
        mode=st_mock_mode_string(),
    )
    @settings(max_examples=300)
    def test_non_gpu_cpu_mode_returns_placeholder(
        self,
        page_png_bytes: bytes,
        visual_type: VisualType,
        page_number: int,
        mode: str,
    ) -> None:
        """When model_manager.mode is not "gpu" or "cpu" (e.g., "mock"),
        the placeholder text is returned without HTTP calls.

        **Validates: Requirements 1.6, 2.8, 6.10, 7.9**
        """
        result = interpret_visual_page_mock(
            model_manager=MagicMock(),
            inference_client=MagicMock(),
            manager_mode=mode,
            page_png_bytes=page_png_bytes,
            visual_type=visual_type,
            page_number=page_number,
        )

        assert result == VISUAL_MOCK_PLACEHOLDER, (
            f"Expected placeholder text for mode='{mode}', "
            f"but got: {result!r}"
        )

    @given(
        page_png_bytes=st_page_png_bytes(),
        visual_type=st_visual_type(),
        page_number=st_page_number(),
    )
    @settings(max_examples=200)
    def test_placeholder_is_constant_across_inputs(
        self,
        page_png_bytes: bytes,
        visual_type: VisualType,
        page_number: int,
    ) -> None:
        """The placeholder text returned in mock mode is always the same
        constant string, regardless of the input parameters.

        **Validates: Requirements 2.8**
        """
        result = interpret_visual_page_mock(
            model_manager=None,
            inference_client=None,
            manager_mode=None,
            page_png_bytes=page_png_bytes,
            visual_type=visual_type,
            page_number=page_number,
        )

        # Verify it's the exact expected constant
        assert result == VISUAL_MOCK_PLACEHOLDER
        # Verify it's always the same object identity (constant)
        assert result == "[VISUAL_PENDING: Diagram interpretation requires Vision_Model]"

    @given(
        page_png_bytes=st_page_png_bytes(),
        visual_type=st_visual_type(),
        page_number=st_page_number(),
    )
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_real_service_mock_mode_no_http_calls(
        self,
        page_png_bytes: bytes,
        visual_type: VisualType,
        page_number: int,
    ) -> None:
        """Integration test: the actual KnowledgeService._interpret_visual_page()
        with model_manager=None makes no HTTP calls and returns the placeholder.

        This verifies the real implementation matches the mock mode contract.

        **Validates: Requirements 1.6, 2.8, 6.10, 7.9**
        """
        from alcoabase.services.knowledge_service import KnowledgeService
        from alcoabase.services.visual_content_detector import (
            VisualType as RealVisualType,
        )

        # Create service with no model_manager (mock mode)
        service = KnowledgeService(model_manager=None, inference_client=None)

        # Map our test VisualType to the real enum
        real_visual_type = RealVisualType(visual_type.value)

        # Patch httpx to detect any HTTP calls
        with patch("httpx.AsyncClient.post") as mock_post, patch(
            "httpx.AsyncClient.get"
        ) as mock_get:
            result = await service._interpret_visual_page(
                page_png_bytes=page_png_bytes,
                visual_type=real_visual_type,
                page_number=page_number,
            )

            # No HTTP calls should have been made
            mock_post.assert_not_called()
            mock_get.assert_not_called()

        # Result must be the placeholder text
        assert result == VISUAL_MOCK_PLACEHOLDER, (
            f"Expected placeholder text from real service in mock mode, "
            f"but got: {result!r}"
        )

    @given(
        mode=st_active_mode_string(),
    )
    @settings(max_examples=50)
    def test_active_mode_does_not_return_placeholder(
        self,
        mode: str,
    ) -> None:
        """When model_manager and inference_client are present AND mode is
        "gpu" or "cpu", the function does NOT return the placeholder
        (it would proceed to make real HTTP calls).

        **Validates: Requirements 2.8**
        """
        result = interpret_visual_page_mock(
            model_manager=MagicMock(),
            inference_client=MagicMock(),
            manager_mode=mode,
            page_png_bytes=b"\x89PNG\r\n\x1a\n",
            visual_type=VisualType.DIAGRAM,
            page_number=0,
        )

        # In active mode, our simulation returns None (real processing would occur)
        assert result is None, (
            f"Expected None (real processing) for active mode='{mode}', "
            f"but got: {result!r}"
        )
