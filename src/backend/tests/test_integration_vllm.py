"""Integration tests verifying end-to-end flow with mocked HTTP.

Tests wire up real service classes (ModelManager, KnowledgeService,
RAGPipeline, InferenceClient) but mock the HTTP layer to verify
the full flow works end-to-end.

Flows tested:
- RAG query: query → ensure_model → chat_completion → response
- Embedding: chunks → ensure_model → create_embeddings → vectors
- OCR: PDF bytes → ensure_model → multimodal chat → text
- Mock mode: all operations without HTTP calls

Requirements: 2.1, 3.1, 4.1, 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.knowledge_service import KnowledgeService, SearchResult
from alcoabase.services.model_manager import ModelManager, ModelRole
from alcoabase.services.rag_pipeline import RAGPipeline


# ---------------------------------------------------------------------------
# Shared Mock Settings
# ---------------------------------------------------------------------------


class _GpuSettings:
    """Settings configured for gpu mode integration tests."""

    model_chat_name = "test-chat-model"
    model_chat_path = "/models/test-chat"
    model_chat_max_gpu_memory_gb = 24
    model_embedding_name = "test-embedding-model"
    model_embedding_path = "/models/test-embedding"
    model_embedding_dimension = 1024
    model_ocr_name = "test-ocr-model"
    model_ocr_path = "/models/test-ocr"
    gpu_device_id = 0
    model_manager_mode = "gpu"
    vllm_base_url = "http://localhost:8000"
    vllm_embedding_url = "http://localhost:8001"


class _MockSettings:
    """Settings configured for mock mode integration tests."""

    model_chat_name = "test-chat-model"
    model_chat_path = "/models/test-chat"
    model_chat_max_gpu_memory_gb = 24
    model_embedding_name = "test-embedding-model"
    model_embedding_path = "/models/test-embedding"
    model_embedding_dimension = 1024
    model_ocr_name = "test-ocr-model"
    model_ocr_path = "/models/test-ocr"
    gpu_device_id = 0
    model_manager_mode = "mock"
    vllm_base_url = "http://localhost:8000"
    vllm_embedding_url = "http://localhost:8001"


# ---------------------------------------------------------------------------
# Integration Test: Full RAG Query Flow
# ---------------------------------------------------------------------------


class TestRAGQueryIntegration:
    """End-to-end RAG query: query → ensure_model → chat_completion → response.

    Validates: Requirements 2.1, 5.3
    """

    @pytest.mark.asyncio
    async def test_full_rag_query_flow(self) -> None:
        """Full RAG flow wires ModelManager, KnowledgeService, and RAGPipeline."""
        # Create a real InferenceClient but mock its internal httpx client
        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        # Mock the InferenceClient methods at the HTTP boundary
        client.chat_completion = AsyncMock(
            return_value="Based on [Source 1], all personnel must wear PPE during cleaning."
        )
        client.list_models = AsyncMock(return_value=["test-chat-model"])
        client.health_check = AsyncMock(return_value=True)

        # Create real ModelManager with the mocked client
        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        # Create real KnowledgeService with search results pre-indexed
        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        # Index a document so hybrid_search returns results
        # Note: hybrid_search uses simple keyword matching (query in chunk)
        knowledge_service.index_document(
            document_uuid="2024-00001",
            version="1.0",
            chunks=["All personnel must wear PPE during cleaning operations."],
            embeddings=[[0.1] * 1024],
            metadata={"title": "Cleaning SOP", "document_type": "SOP"},
        )

        # Create real RAGPipeline
        with patch("alcoabase.services.rag_pipeline.get_settings", return_value=_GpuSettings()):
            pipeline = RAGPipeline(
                knowledge_service=knowledge_service,
                model_manager=model_manager,
                inference_client=client,
                top_k=5,
            )

        # Execute the full flow (query must match indexed chunk via keyword)
        response = await pipeline.query(
            question="PPE",
            user_id=1,
        )

        # Verify end-to-end result
        assert response.answer == "Based on [Source 1], all personnel must wear PPE during cleaning."
        assert response.grounded is True
        assert len(response.citations) == 1
        assert response.citations[0].document_uuid == "2024-00001"
        assert response.citations[0].title == "Cleaning SOP"
        assert response.conversation_id is not None

        # Verify ensure_model was called (model was already listed)
        client.list_models.assert_called()
        client.chat_completion.assert_called_once()

        # Verify chat_completion was called with correct model and structure
        call_kwargs = client.chat_completion.call_args[1]
        assert call_kwargs["model"] == "test-chat-model"
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 2048
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert "PPE" in messages[-1]["content"] or "ppe" in messages[-1]["content"].lower()

    @pytest.mark.asyncio
    async def test_rag_query_no_results_returns_no_content(self) -> None:
        """RAG flow returns NO_CONTENT_MESSAGE when no search results found."""
        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        client.chat_completion = AsyncMock()
        client.list_models = AsyncMock(return_value=["test-chat-model"])
        client.health_check = AsyncMock(return_value=True)

        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        # Empty knowledge service (no indexed documents)
        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        with patch("alcoabase.services.rag_pipeline.get_settings", return_value=_GpuSettings()):
            pipeline = RAGPipeline(
                knowledge_service=knowledge_service,
                model_manager=model_manager,
                inference_client=client,
                top_k=5,
            )

        response = await pipeline.query(
            question="Something not indexed",
            user_id=1,
        )

        assert response.answer == RAGPipeline.NO_CONTENT_MESSAGE
        assert response.grounded is False
        assert response.citations == []
        # No chat_completion call should be made
        client.chat_completion.assert_not_called()


# ---------------------------------------------------------------------------
# Integration Test: Full Embedding Flow
# ---------------------------------------------------------------------------


class TestEmbeddingIntegration:
    """End-to-end embedding: chunks → ensure_model → create_embeddings → vectors.

    Validates: Requirements 3.1, 5.2
    """

    @pytest.mark.asyncio
    async def test_full_embedding_flow(self) -> None:
        """Full embedding flow generates vectors via InferenceClient."""
        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        # Mock create_embeddings to return vectors of correct dimension
        expected_vectors = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        client.create_embeddings = AsyncMock(return_value=expected_vectors)
        client.health_check = AsyncMock(return_value=True)
        client.list_models = AsyncMock(return_value=["test-embedding-model"])

        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        # Execute the full embedding flow
        chunks = [
            "First chunk of text about cleaning.",
            "Second chunk about safety protocols.",
            "Third chunk about equipment maintenance.",
        ]
        vectors = await knowledge_service.generate_embeddings(chunks)

        # Verify results
        assert len(vectors) == 3
        assert all(len(v) == 1024 for v in vectors)
        assert vectors == expected_vectors

        # Verify create_embeddings was called with correct parameters
        client.create_embeddings.assert_called_once()
        call_kwargs = client.create_embeddings.call_args[1]
        assert call_kwargs["model"] == "test-embedding-model"
        assert call_kwargs["inputs"] == chunks

    @pytest.mark.asyncio
    async def test_embedding_flow_batching(self) -> None:
        """Embedding flow batches chunks into groups of 32."""
        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        # 50 chunks → 2 batches (32 + 18)
        batch1_vectors = [[0.1] * 1024] * 32
        batch2_vectors = [[0.2] * 1024] * 18
        client.create_embeddings = AsyncMock(
            side_effect=[batch1_vectors, batch2_vectors]
        )
        client.health_check = AsyncMock(return_value=True)
        client.list_models = AsyncMock(return_value=["test-embedding-model"])

        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        chunks = [f"Chunk {i}" for i in range(50)]
        vectors = await knowledge_service.generate_embeddings(chunks)

        # Verify all 50 vectors returned
        assert len(vectors) == 50
        # Verify 2 batch calls were made
        assert client.create_embeddings.call_count == 2
        # First batch has 32 chunks
        first_call = client.create_embeddings.call_args_list[0][1]
        assert len(first_call["inputs"]) == 32
        # Second batch has 18 chunks
        second_call = client.create_embeddings.call_args_list[1][1]
        assert len(second_call["inputs"]) == 18

    @pytest.mark.asyncio
    async def test_embedding_empty_input_no_http(self) -> None:
        """Empty input returns empty list without any HTTP calls."""
        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        client.create_embeddings = AsyncMock()
        client.health_check = AsyncMock(return_value=True)

        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        vectors = await knowledge_service.generate_embeddings([])

        assert vectors == []
        client.create_embeddings.assert_not_called()


# ---------------------------------------------------------------------------
# Integration Test: Full OCR Flow
# ---------------------------------------------------------------------------


class TestOCRIntegration:
    """End-to-end OCR: PDF bytes → ensure_model → multimodal chat → text.

    Validates: Requirements 4.1, 5.4
    """

    @pytest.mark.asyncio
    async def test_full_ocr_flow(self) -> None:
        """Full OCR flow extracts text from scanned PDF pages via vision model."""
        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        # Mock chat_completion to return OCR text for each page
        client.chat_completion = AsyncMock(
            side_effect=[
                "Page 1: Standard Operating Procedure for Cleaning",
                "Page 2: All personnel must wear appropriate PPE",
            ]
        )
        client.list_models = AsyncMock(return_value=["test-ocr-model"])
        client.health_check = AsyncMock(return_value=True)

        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        # Create a mock PDF with 2 pages (scanned — no extractable text)
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = ""  # Scanned page, no text
        mock_page1.get_pixmap.return_value = MagicMock(
            tobytes=MagicMock(return_value=b"fake_png_bytes_page1")
        )

        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = ""  # Scanned page, no text
        mock_page2.get_pixmap.return_value = MagicMock(
            tobytes=MagicMock(return_value=b"fake_png_bytes_page2")
        )

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page1, mock_page2]))
        mock_doc.__getitem__ = MagicMock(side_effect=[mock_page1, mock_page2])
        mock_doc.close = MagicMock()

        with patch("alcoabase.services.knowledge_service.fitz.open", return_value=mock_doc):
            result = await knowledge_service.extract_text_with_ocr_fallback(
                file_bytes=b"fake_pdf_bytes",
                content_type="application/pdf",
            )

        # Verify OCR text was extracted and concatenated
        assert "Page 1: Standard Operating Procedure for Cleaning" in result
        assert "Page 2: All personnel must wear appropriate PPE" in result

        # Verify chat_completion was called for each page with multimodal messages
        assert client.chat_completion.call_count == 2

        # Verify the first call used OCR model and multimodal format
        first_call_kwargs = client.chat_completion.call_args_list[0][1]
        assert first_call_kwargs["model"] == "test-ocr-model"
        assert first_call_kwargs["max_tokens"] == 4096
        assert first_call_kwargs["temperature"] == 0.1
        messages = first_call_kwargs["messages"]
        # System message with OCR instructions
        assert messages[0]["role"] == "system"
        assert "Extract all visible text" in messages[0]["content"]
        # User message with image
        assert messages[1]["role"] == "user"
        assert isinstance(messages[1]["content"], list)

    @pytest.mark.asyncio
    async def test_ocr_skips_failed_pages(self) -> None:
        """OCR flow skips pages that fail and returns text from successful ones."""
        from alcoabase.services.inference_client import InferenceError

        with patch("alcoabase.services.inference_client.httpx.AsyncClient"):
            client = InferenceClient(
                base_url="http://localhost:8000",
                embedding_base_url="http://localhost:8001",
            )

        # First page succeeds, second page fails
        client.chat_completion = AsyncMock(
            side_effect=[
                "Page 1 text extracted successfully",
                InferenceError("Server error", status_code=500, endpoint="/v1/chat/completions"),
            ]
        )
        client.list_models = AsyncMock(return_value=["test-ocr-model"])
        client.health_check = AsyncMock(return_value=True)

        with patch("alcoabase.services.model_manager.get_settings", return_value=_GpuSettings()):
            model_manager = ModelManager(
                settings=_GpuSettings(),
                inference_client=client,
            )

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_GpuSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=client,
            )

        # Mock 2-page scanned PDF
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = ""
        mock_page1.get_pixmap.return_value = MagicMock(
            tobytes=MagicMock(return_value=b"png1")
        )

        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = ""
        mock_page2.get_pixmap.return_value = MagicMock(
            tobytes=MagicMock(return_value=b"png2")
        )

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=2)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page1, mock_page2]))
        mock_doc.__getitem__ = MagicMock(side_effect=[mock_page1, mock_page2])
        mock_doc.close = MagicMock()

        with patch("alcoabase.services.knowledge_service.fitz.open", return_value=mock_doc):
            result = await knowledge_service.extract_text_with_ocr_fallback(
                file_bytes=b"fake_pdf",
                content_type="application/pdf",
            )

        # Only page 1 text should be present
        assert "Page 1 text extracted successfully" in result
        # No exception raised despite page 2 failure


# ---------------------------------------------------------------------------
# Integration Test: Mock Mode End-to-End
# ---------------------------------------------------------------------------


class TestMockModeIntegration:
    """End-to-end mock mode: all operations without HTTP calls.

    Validates: Requirements 5.1, 5.2, 5.3, 5.4
    """

    @pytest.mark.asyncio
    async def test_mock_mode_rag_query_no_http(self) -> None:
        """Mock mode RAG query completes without any HTTP calls."""
        with patch("alcoabase.services.model_manager.get_settings", return_value=_MockSettings()):
            model_manager = ModelManager(settings=_MockSettings(), inference_client=None)

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_MockSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=None,
            )

        # Index a document for search
        knowledge_service.index_document(
            document_uuid="2024-00001",
            version="1.0",
            chunks=["Mock document content about safety procedures."],
            embeddings=[[0.5] * 1024],
            metadata={"title": "Safety Doc"},
        )

        with patch("alcoabase.services.rag_pipeline.get_settings", return_value=_MockSettings()):
            pipeline = RAGPipeline(
                knowledge_service=knowledge_service,
                model_manager=model_manager,
                inference_client=None,
                top_k=5,
            )

        response = await pipeline.query(
            question="safety procedures",
            user_id=1,
        )

        # Mock mode returns placeholder response with grounded=true
        assert response.answer is not None
        assert len(response.answer) > 0
        assert response.grounded is True
        assert response.conversation_id is not None

    @pytest.mark.asyncio
    async def test_mock_mode_embeddings_no_http(self) -> None:
        """Mock mode embedding generation returns random vectors without HTTP."""
        with patch("alcoabase.services.model_manager.get_settings", return_value=_MockSettings()):
            model_manager = ModelManager(settings=_MockSettings(), inference_client=None)

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_MockSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=None,
            )

        chunks = ["First chunk", "Second chunk", "Third chunk"]
        vectors = await knowledge_service.generate_embeddings(chunks)

        # Verify correct number of vectors with correct dimensions
        assert len(vectors) == 3
        assert all(len(v) == 1024 for v in vectors)
        # Vectors should be normalized (approximately unit length)
        for vec in vectors:
            magnitude = sum(x * x for x in vec) ** 0.5
            assert abs(magnitude - 1.0) < 0.01

    @pytest.mark.asyncio
    async def test_mock_mode_ocr_no_http(self) -> None:
        """Mock mode OCR returns placeholder text without HTTP calls."""
        with patch("alcoabase.services.model_manager.get_settings", return_value=_MockSettings()):
            model_manager = ModelManager(settings=_MockSettings(), inference_client=None)

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_MockSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=None,
            )

        # Mock a scanned PDF (no extractable text)
        mock_page = MagicMock()
        mock_page.get_text.return_value = ""

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        mock_doc.close = MagicMock()

        with patch("alcoabase.services.knowledge_service.fitz.open", return_value=mock_doc):
            result = await knowledge_service.extract_text_with_ocr_fallback(
                file_bytes=b"fake_scanned_pdf",
                content_type="application/pdf",
            )

        # Mock mode returns the placeholder text
        assert "[OCR_PENDING:" in result
        assert "Model_Manager" in result

    @pytest.mark.asyncio
    async def test_mock_mode_model_manager_state(self) -> None:
        """Mock mode ModelManager updates state without HTTP calls."""
        with patch("alcoabase.services.model_manager.get_settings", return_value=_MockSettings()):
            model_manager = ModelManager(settings=_MockSettings(), inference_client=None)

        # Ensure model in mock mode
        url = await model_manager.ensure_model(ModelRole.CHAT)

        assert url == "http://localhost:8000"

        status = await model_manager.get_status()
        assert status.current_role == ModelRole.CHAT
        assert status.current_model_name == "test-chat-model"
        assert status.is_ready is True
        assert status.gpu_memory_used_gb == 0.0
        assert status.mode == "mock"
        assert status.vllm_reachable is None

    @pytest.mark.asyncio
    async def test_mock_mode_full_pipeline_no_network(self) -> None:
        """Complete pipeline in mock mode makes zero network calls."""
        # Track that no InferenceClient is ever used
        with patch("alcoabase.services.model_manager.get_settings", return_value=_MockSettings()):
            model_manager = ModelManager(settings=_MockSettings(), inference_client=None)

        with patch("alcoabase.services.knowledge_service.get_settings", return_value=_MockSettings()):
            knowledge_service = KnowledgeService(
                model_manager=model_manager,
                inference_client=None,
            )

        # Generate embeddings (mock)
        chunks = ["Test content for embedding"]
        vectors = await knowledge_service.generate_embeddings(chunks)
        assert len(vectors) == 1
        assert len(vectors[0]) == 1024

        # Index document
        knowledge_service.index_document(
            document_uuid="2024-00001",
            version="1.0",
            chunks=chunks,
            embeddings=vectors,
            metadata={"title": "Test Doc"},
        )

        # Query via RAG pipeline (mock)
        with patch("alcoabase.services.rag_pipeline.get_settings", return_value=_MockSettings()):
            pipeline = RAGPipeline(
                knowledge_service=knowledge_service,
                model_manager=model_manager,
                inference_client=None,
                top_k=5,
            )

        response = await pipeline.query(
            question="Test content",
            user_id=1,
        )

        assert response.grounded is True
        assert response.answer is not None
