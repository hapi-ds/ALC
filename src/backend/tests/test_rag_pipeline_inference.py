"""Unit tests for RAG pipeline inference with real vLLM integration.

Tests cover:
- System prompt contains all grounding rules
- Message array structure (system, history, context, question)
- History limited to last 6 messages
- NO_CONTENT_MESSAGE returned with grounded=false when no results
- Error propagation from ModelManagerError
- Timeout handling (60s exceeded)
- Mock mode returns placeholder without HTTP calls

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 7.1, 7.2, 7.3
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.inference_client import (
    InferenceError,
    InferenceTimeoutError,
)
from alcoabase.services.knowledge_service import KnowledgeService, SearchResult
from alcoabase.services.model_manager import ModelManager, ModelManagerError, ModelRole
from alcoabase.services.rag_pipeline import (
    ConversationMessage,
    RAGPipeline,
    _MAX_HISTORY_MESSAGES,
    _SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class MockSettings:
    """Mock settings for testing without real environment variables."""

    model_chat_name = "test-chat-model"
    model_chat_path = "/models/test-chat"
    model_chat_max_gpu_memory_gb = 60
    model_embedding_name = "test-embedding-model"
    model_embedding_path = "/models/test-embedding"
    model_embedding_dimension = 1024
    model_ocr_name = "test-ocr-model"
    model_ocr_path = "/models/test-ocr"
    gpu_device_id = 0
    model_manager_mode = "gpu"
    vllm_base_url = "http://localhost:8000"
    vllm_embedding_url = "http://localhost:8001"


class MockSettingsMock:
    """Mock settings with mock mode enabled."""

    model_chat_name = "test-chat-model"
    model_chat_path = "/models/test-chat"
    model_chat_max_gpu_memory_gb = 60
    model_embedding_name = "test-embedding-model"
    model_embedding_path = "/models/test-embedding"
    model_embedding_dimension = 1024
    model_ocr_name = "test-ocr-model"
    model_ocr_path = "/models/test-ocr"
    gpu_device_id = 0
    model_manager_mode = "mock"
    vllm_base_url = "http://localhost:8000"
    vllm_embedding_url = "http://localhost:8001"


@pytest.fixture
def mock_model_manager() -> AsyncMock:
    """Create a mock ModelManager."""
    mm = AsyncMock(spec=ModelManager)
    mm.ensure_model = AsyncMock(return_value="http://localhost:8000")
    return mm


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient."""
    client = AsyncMock()
    client.chat_completion = AsyncMock(
        return_value="This is a test response based on [Source 1]."
    )
    return client


@pytest.fixture
def mock_knowledge_service() -> MagicMock:
    """Create a mock KnowledgeService with search results."""
    ks = MagicMock(spec=KnowledgeService)
    ks.hybrid_search = MagicMock(
        return_value=(
            [
                SearchResult(
                    document_uuid="2024-00001",
                    title="Cleaning SOP",
                    version="1.0",
                    excerpt="All personnel must wear PPE during cleaning.",
                    relevance_score=0.9,
                    metadata={"page": 1},
                ),
                SearchResult(
                    document_uuid="2024-00002",
                    title="Safety Protocol",
                    version="2.0",
                    excerpt="Safety protocols must be followed at all times.",
                    relevance_score=0.7,
                    metadata={"section": "Section 3"},
                ),
            ],
            2,
        )
    )
    return ks


@pytest.fixture
def mock_knowledge_service_empty() -> MagicMock:
    """Create a mock KnowledgeService that returns no results."""
    ks = MagicMock(spec=KnowledgeService)
    ks.hybrid_search = MagicMock(return_value=([], 0))
    return ks


@pytest.fixture
def rag_pipeline_gpu(
    mock_knowledge_service: MagicMock,
    mock_model_manager: AsyncMock,
    mock_inference_client: AsyncMock,
) -> RAGPipeline:
    """Create a RAGPipeline configured for gpu mode with mocked dependencies."""
    with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
        mock_get.return_value = MockSettings()
        pipeline = RAGPipeline(
            knowledge_service=mock_knowledge_service,
            model_manager=mock_model_manager,
            inference_client=mock_inference_client,
            top_k=5,
        )
    return pipeline


@pytest.fixture
def rag_pipeline_mock_mode(
    mock_knowledge_service: MagicMock,
) -> RAGPipeline:
    """Create a RAGPipeline in mock mode (no model_manager/inference_client)."""
    with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
        mock_get.return_value = MockSettingsMock()
        pipeline = RAGPipeline(
            knowledge_service=mock_knowledge_service,
            model_manager=None,
            inference_client=None,
            top_k=5,
        )
    return pipeline


# ---------------------------------------------------------------------------
# Tests: System Prompt Contains All Grounding Rules (Req 7.1)
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Tests for system prompt grounding rules."""

    def test_system_prompt_contains_context_only_rule(self) -> None:
        """System prompt instructs model to answer only from context."""
        assert "ONLY based on the provided context" in _SYSTEM_PROMPT

    def test_system_prompt_contains_citation_rule(self) -> None:
        """System prompt instructs model to cite sources using [Source N]."""
        assert "[Source N]" in _SYSTEM_PROMPT

    def test_system_prompt_contains_insufficient_info_rule(self) -> None:
        """System prompt instructs model to state when info is insufficient."""
        assert "do not contain enough information" in _SYSTEM_PROMPT

    def test_system_prompt_contains_no_fabrication_rule(self) -> None:
        """System prompt instructs model to never fabricate information."""
        assert "Never fabricate" in _SYSTEM_PROMPT

    def test_system_prompt_contains_precision_rule(self) -> None:
        """System prompt instructs model to be precise and factual."""
        assert "precise and factual" in _SYSTEM_PROMPT

    def test_build_system_prompt_returns_constant(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """_build_system_prompt returns the expected system prompt."""
        result = rag_pipeline_gpu._build_system_prompt()
        assert result == _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tests: Message Array Structure (Req 2.2)
# ---------------------------------------------------------------------------


class TestMessageArrayStructure:
    """Tests for chat completion message array construction."""

    def test_messages_start_with_system_prompt(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """First message in array is the system prompt."""
        messages = rag_pipeline_gpu._build_messages(
            question="What is PPE?",
            context="[Source 1: Cleaning SOP v1.0]\nAll personnel must wear PPE.",
            history=[],
        )
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == _SYSTEM_PROMPT

    def test_messages_end_with_user_question(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """Last message in array is the user's question."""
        messages = rag_pipeline_gpu._build_messages(
            question="What is PPE?",
            context="[Source 1: Cleaning SOP v1.0]\nAll personnel must wear PPE.",
            history=[],
        )
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "What is PPE?"

    def test_messages_contain_context_before_question(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """Context is included as a user message before the question."""
        context = "[Source 1: Cleaning SOP v1.0]\nAll personnel must wear PPE."
        messages = rag_pipeline_gpu._build_messages(
            question="What is PPE?",
            context=context,
            history=[],
        )
        # Context is the second-to-last message
        context_msg = messages[-2]
        assert context_msg["role"] == "user"
        assert "Context documents:" in context_msg["content"]
        assert context in context_msg["content"]

    def test_messages_include_history_between_system_and_context(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """History messages appear between system prompt and context."""
        history = [
            ConversationMessage(role="user", content="Previous question"),
            ConversationMessage(role="assistant", content="Previous answer"),
        ]
        messages = rag_pipeline_gpu._build_messages(
            question="Follow-up?",
            context="Some context",
            history=history,
        )
        # Structure: system, history_user, history_assistant, context, question
        assert len(messages) == 5
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Previous question"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Previous answer"
        assert messages[3]["role"] == "user"  # context
        assert messages[4]["role"] == "user"  # question

    def test_messages_without_history(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """Without history, messages are: system, context, question."""
        messages = rag_pipeline_gpu._build_messages(
            question="What is PPE?",
            context="Some context",
            history=[],
        )
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"  # context
        assert messages[2]["role"] == "user"  # question


# ---------------------------------------------------------------------------
# Tests: History Limited to Last 6 Messages (Req 2.2)
# ---------------------------------------------------------------------------


class TestHistoryLimit:
    """Tests for conversation history truncation to last 6 messages."""

    def test_history_limited_to_six_messages(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """Only the last 6 messages from history are included."""
        # Create 10 messages (5 user + 5 assistant)
        history = [
            ConversationMessage(role="user", content=f"Question {i}")
            if i % 2 == 0
            else ConversationMessage(role="assistant", content=f"Answer {i}")
            for i in range(10)
        ]
        messages = rag_pipeline_gpu._build_messages(
            question="Current question",
            context="Some context",
            history=history,
        )
        # Should be: system + 6 history + context + question = 9
        history_messages = [
            m for m in messages[1:-2]  # exclude system, context, question
        ]
        assert len(history_messages) == _MAX_HISTORY_MESSAGES

    def test_history_under_limit_included_fully(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """History with fewer than 6 messages is included in full."""
        history = [
            ConversationMessage(role="user", content="Q1"),
            ConversationMessage(role="assistant", content="A1"),
        ]
        messages = rag_pipeline_gpu._build_messages(
            question="Q2",
            context="Context",
            history=history,
        )
        # system + 2 history + context + question = 5
        assert len(messages) == 5

    def test_history_exactly_six_included_fully(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """History with exactly 6 messages is included in full."""
        history = [
            ConversationMessage(
                role="user" if i % 2 == 0 else "assistant",
                content=f"Msg {i}",
            )
            for i in range(6)
        ]
        messages = rag_pipeline_gpu._build_messages(
            question="Q",
            context="C",
            history=history,
        )
        # system + 6 history + context + question = 9
        assert len(messages) == 9


# ---------------------------------------------------------------------------
# Tests: NO_CONTENT_MESSAGE with grounded=false (Req 7.3)
# ---------------------------------------------------------------------------


class TestNoContentMessage:
    """Tests for no-content response when no search results found."""

    @pytest.mark.asyncio
    async def test_no_results_returns_no_content_message(
        self, mock_knowledge_service_empty: MagicMock
    ) -> None:
        """Returns NO_CONTENT_MESSAGE when hybrid_search returns empty."""
        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettings()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service_empty,
                model_manager=AsyncMock(),
                inference_client=AsyncMock(),
                top_k=5,
            )

        response = await pipeline.query(question="Unknown topic", user_id=1)

        assert response.answer == RAGPipeline.NO_CONTENT_MESSAGE
        assert response.grounded is False
        assert response.citations == []

    @pytest.mark.asyncio
    async def test_no_results_does_not_call_inference(
        self, mock_knowledge_service_empty: MagicMock
    ) -> None:
        """No inference call is made when no search results found."""
        mock_client = AsyncMock()
        mock_mm = AsyncMock()

        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettings()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service_empty,
                model_manager=mock_mm,
                inference_client=mock_client,
                top_k=5,
            )

        await pipeline.query(question="Unknown topic", user_id=1)

        mock_mm.ensure_model.assert_not_called()
        mock_client.chat_completion.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Error Propagation from ModelManagerError (Req 2.8)
# ---------------------------------------------------------------------------


class TestModelManagerErrorPropagation:
    """Tests for ModelManagerError propagation from ensure_model."""

    @pytest.mark.asyncio
    async def test_model_manager_error_propagates(
        self,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """ModelManagerError from ensure_model propagates to caller."""
        mock_mm = AsyncMock()
        mock_mm.ensure_model = AsyncMock(
            side_effect=ModelManagerError(
                "Model test-chat-model for role chat failed to load: "
                "health check timeout after 120.0s"
            )
        )

        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettings()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service,
                model_manager=mock_mm,
                inference_client=mock_inference_client,
                top_k=5,
            )

        with pytest.raises(ModelManagerError, match="health check timeout"):
            await pipeline.query(question="What is PPE?", user_id=1)

    @pytest.mark.asyncio
    async def test_model_manager_error_no_inference_call(
        self,
        mock_knowledge_service: MagicMock,
        mock_inference_client: AsyncMock,
    ) -> None:
        """No chat_completion call is made when ensure_model fails."""
        mock_mm = AsyncMock()
        mock_mm.ensure_model = AsyncMock(
            side_effect=ModelManagerError("Server unreachable")
        )

        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettings()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service,
                model_manager=mock_mm,
                inference_client=mock_inference_client,
                top_k=5,
            )

        with pytest.raises(ModelManagerError):
            await pipeline.query(question="What is PPE?", user_id=1)

        mock_inference_client.chat_completion.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Timeout Handling (Req 2.6)
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    """Tests for 60s timeout handling on chat completion."""

    @pytest.mark.asyncio
    async def test_timeout_error_propagates(
        self,
        mock_knowledge_service: MagicMock,
        mock_model_manager: AsyncMock,
    ) -> None:
        """InferenceTimeoutError propagates when vLLM exceeds 60s."""
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            side_effect=InferenceTimeoutError(
                "Request to http://localhost:8000/v1/chat/completions "
                "timed out after 60.0s",
                endpoint="http://localhost:8000/v1/chat/completions",
            )
        )

        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettings()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service,
                model_manager=mock_model_manager,
                inference_client=mock_client,
                top_k=5,
            )

        with pytest.raises(InferenceTimeoutError, match="timed out"):
            await pipeline.query(question="What is PPE?", user_id=1)

    @pytest.mark.asyncio
    async def test_inference_error_propagates(
        self,
        mock_knowledge_service: MagicMock,
        mock_model_manager: AsyncMock,
    ) -> None:
        """InferenceError propagates when vLLM returns HTTP error."""
        mock_client = AsyncMock()
        mock_client.chat_completion = AsyncMock(
            side_effect=InferenceError(
                "Request to http://localhost:8000/v1/chat/completions "
                "failed: HTTP 500 - Internal Server Error",
                status_code=500,
                endpoint="http://localhost:8000/v1/chat/completions",
            )
        )

        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettings()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service,
                model_manager=mock_model_manager,
                inference_client=mock_client,
                top_k=5,
            )

        with pytest.raises(InferenceError, match="HTTP 500"):
            await pipeline.query(question="What is PPE?", user_id=1)


# ---------------------------------------------------------------------------
# Tests: Mock Mode Returns Placeholder Without HTTP Calls (Req 2.7)
# ---------------------------------------------------------------------------


class TestMockMode:
    """Tests for mock mode placeholder behavior."""

    @pytest.mark.asyncio
    async def test_mock_mode_returns_placeholder_response(
        self, rag_pipeline_mock_mode: RAGPipeline
    ) -> None:
        """Mock mode returns placeholder text without real inference."""
        response = await rag_pipeline_mock_mode.query(
            question="What is PPE?", user_id=1
        )

        assert response.grounded is True
        assert "Placeholder response" in response.answer or "placeholder" in response.answer.lower()

    @pytest.mark.asyncio
    async def test_mock_mode_no_model_manager_no_http(
        self, mock_knowledge_service: MagicMock
    ) -> None:
        """Mock mode with no model_manager/inference_client makes no HTTP calls."""
        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettingsMock()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service,
                model_manager=None,
                inference_client=None,
                top_k=5,
            )

        response = await pipeline.query(question="What is PPE?", user_id=1)

        # Should succeed without errors (no HTTP calls attempted)
        assert response.answer is not None
        assert len(response.answer) > 0

    @pytest.mark.asyncio
    async def test_mock_mode_with_model_manager_set_to_mock(
        self, mock_knowledge_service: MagicMock
    ) -> None:
        """Even with model_manager provided, mock mode uses placeholder."""
        mock_mm = AsyncMock()
        mock_client = AsyncMock()

        with patch("alcoabase.services.rag_pipeline.get_settings") as mock_get:
            mock_get.return_value = MockSettingsMock()
            pipeline = RAGPipeline(
                knowledge_service=mock_knowledge_service,
                model_manager=mock_mm,
                inference_client=mock_client,
                top_k=5,
            )

        response = await pipeline.query(question="What is PPE?", user_id=1)

        # ensure_model and chat_completion should NOT be called in mock mode
        mock_mm.ensure_model.assert_not_called()
        mock_client.chat_completion.assert_not_called()
        assert response.grounded is True

    @pytest.mark.asyncio
    async def test_mock_mode_grounded_true_with_context(
        self, rag_pipeline_mock_mode: RAGPipeline
    ) -> None:
        """Mock mode sets grounded=true when context chunks are available."""
        response = await rag_pipeline_mock_mode.query(
            question="cleaning", user_id=1
        )

        assert response.grounded is True


# ---------------------------------------------------------------------------
# Tests: Full Query Flow in GPU Mode (Req 2.1, 2.3, 2.4)
# ---------------------------------------------------------------------------


class TestFullQueryFlow:
    """Tests for the full query flow in gpu/cpu mode."""

    @pytest.mark.asyncio
    async def test_query_calls_ensure_model_chat(
        self, rag_pipeline_gpu: RAGPipeline, mock_model_manager: AsyncMock
    ) -> None:
        """Query calls ensure_model with CHAT role."""
        await rag_pipeline_gpu.query(question="What is PPE?", user_id=1)

        mock_model_manager.ensure_model.assert_called_once_with(ModelRole.CHAT)

    @pytest.mark.asyncio
    async def test_query_calls_chat_completion(
        self,
        rag_pipeline_gpu: RAGPipeline,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Query calls chat_completion with correct parameters."""
        await rag_pipeline_gpu.query(question="What is PPE?", user_id=1)

        mock_inference_client.chat_completion.assert_called_once()
        call_kwargs = mock_inference_client.chat_completion.call_args[1]
        assert call_kwargs["model"] == "test-chat-model"
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_query_returns_llm_response(
        self, rag_pipeline_gpu: RAGPipeline
    ) -> None:
        """Query returns the response from the LLM."""
        response = await rag_pipeline_gpu.query(
            question="What is PPE?", user_id=1
        )

        assert response.answer == "This is a test response based on [Source 1]."
        assert response.grounded is True

    @pytest.mark.asyncio
    async def test_query_passes_messages_to_chat_completion(
        self,
        rag_pipeline_gpu: RAGPipeline,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Query passes properly structured messages to chat_completion."""
        await rag_pipeline_gpu.query(question="What is PPE?", user_id=1)

        call_kwargs = mock_inference_client.chat_completion.call_args[1]
        messages = call_kwargs["messages"]

        # First message is system prompt
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == _SYSTEM_PROMPT

        # Last message is the question
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "What is PPE?"

        # Second-to-last is context
        assert messages[-2]["role"] == "user"
        assert "Context documents:" in messages[-2]["content"]
