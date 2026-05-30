"""RAG Pipeline for conversational knowledge queries.

This module provides:
- Retrieval-augmented generation using KnowledgeService for chunk retrieval
- Real vLLM chat completion inference via InferenceClient
- Source citation extraction (Document-UUID, title, version, page/section)
- Grounded response enforcement (no hallucination without context)
- Context truncation by relevance score within token limits
- Conversation context management for follow-up questions
- ABAC enforcement on retrieved chunks

References:
    - Task 13: RAG Pipeline (Conversational Knowledge Queries)
    - Design doc Section 9: Knowledge Service / RAG Pipeline
    - Step 4-3: AI Model Integration (vLLM)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from alcoabase.config import get_settings
from alcoabase.services.knowledge_service import KnowledgeService, SearchResult
from alcoabase.services.risk_controlled import risk_controlled

if TYPE_CHECKING:
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.model_manager import ModelManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant for a GxP-regulated document management system.\n"
    "Answer questions ONLY based on the provided context documents.\n"
    "Rules:\n"
    "1. Only use information from the provided [Source N] references.\n"
    "2. Cite sources using [Source N] format when referencing information.\n"
    "3. If the context does not contain sufficient information, state clearly: "
    '"The available documents do not contain enough information to answer this question."\n'
    "4. Never fabricate or infer information not present in the context.\n"
    "5. Be precise and factual in your responses."
)

_MAX_CONTEXT_TOKENS = 8192
_MAX_HISTORY_MESSAGES = 6
_CHAT_TEMPERATURE = 0.3
_CHAT_MAX_TOKENS = 2048


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class SourceCitation:
    """A source citation for a referenced document chunk.

    Attributes:
        document_uuid: The Document-UUID of the source document.
        title: Document title.
        version: Document version string.
        page_or_section: Page number or section identifier.
        content_type: Type of content ("text" or "visual").
        visual_type: Visual element type when content_type is "visual"
            (flowchart, diagram, chart, mixed). None for text chunks.
    """

    document_uuid: str
    title: str
    version: str
    page_or_section: str
    content_type: str = "text"
    visual_type: str | None = None


@dataclass
class RAGResponse:
    """Response from the RAG pipeline.

    Attributes:
        answer: The generated answer text.
        citations: List of source citations referenced in the answer.
        grounded: Whether the response is grounded in retrieved content.
        conversation_id: ID of the conversation for follow-up queries.
    """

    answer: str
    citations: list[SourceCitation]
    grounded: bool
    conversation_id: str


@dataclass
class ConversationMessage:
    """A single message in a conversation history.

    Attributes:
        role: Either "user" or "assistant".
        content: The message content.
        timestamp: When the message was sent.
    """

    role: str
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# RAG Pipeline
# ---------------------------------------------------------------------------


class RAGPipeline:
    """Retrieval-Augmented Generation pipeline for knowledge queries.

    Retrieves relevant document chunks from KnowledgeService, passes them
    as context to a vLLM chat model, and generates grounded responses
    with source citations.

    In mock mode, uses placeholder logic without making HTTP calls.

    Args:
        knowledge_service: Service for document retrieval and search.
        model_manager: ModelManager for ensuring the chat model is loaded.
        inference_client: InferenceClient for vLLM HTTP communication.
        top_k: Number of chunks to retrieve per query.
    """

    NO_CONTENT_MESSAGE = (
        "No matching content found in the knowledge base for your query. "
        "Please try rephrasing your question or check that relevant "
        "documents have been indexed."
    )

    # Visual chunk retrieval constants
    VISUAL_BOOST_KEYWORDS: list[str] = [
        "process", "flow", "flowchart", "diagram", "workflow",
        "steps", "procedure", "decision tree", "sequence",
    ]
    MAX_VISUAL_CHUNKS_PER_QUERY: int = 3

    def __init__(
        self,
        knowledge_service: KnowledgeService | None = None,
        model_manager: ModelManager | None = None,
        inference_client: InferenceClient | None = None,
        top_k: int = 5,
    ) -> None:
        """Initialize the RAG pipeline.

        Args:
            knowledge_service: KnowledgeService instance for retrieval.
                Creates a new instance if not provided.
            model_manager: ModelManager for model loading. If None, mock mode
                placeholder logic is used.
            inference_client: InferenceClient for vLLM API calls. If None,
                mock mode placeholder logic is used.
            top_k: Number of top chunks to retrieve per query.
        """
        self._knowledge_service = knowledge_service or KnowledgeService()
        self._model_manager = model_manager
        self._inference_client = inference_client
        self._conversations: dict[str, list[ConversationMessage]] = {}
        self._top_k = top_k
        self._settings = get_settings()

    # -----------------------------------------------------------------------
    # Core Query (Task 13.1)
    # -----------------------------------------------------------------------

    @risk_controlled(task_type_id="rag_knowledge_query")
    async def query(
        self,
        question: str,
        user_id: int,
        conversation_id: str | None = None,
        company_id: int | None = None,
    ) -> RAGResponse:
        """Retrieve relevant chunks and generate a grounded answer.

        1. Retrieve top-k chunks from KnowledgeService (ABAC-filtered)
        2. Build prompt with retrieved context + conversation history
        3. Generate response via vLLM chat completion (or mock)
        4. Extract source citations
        5. If no relevant chunks → return grounded "no content" message

        Args:
            question: The user's question.
            user_id: ID of the user making the query (for ABAC filtering).
            conversation_id: Optional conversation ID for follow-up queries.

        Returns:
            RAGResponse with answer, citations, and grounding status.
        """
        # Resolve or create conversation
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        # Get conversation history for context
        history = self._get_conversation_history(conversation_id)

        # Step 1: Retrieve relevant chunks (ABAC-filtered via KnowledgeService)
        search_results, _total = self._knowledge_service.hybrid_search(
            query=question,
            user_id=user_id,
            limit=self._top_k,
        )

        # Step 2: Grounding enforcement (Task 13.3)
        if not search_results:
            response = RAGResponse(
                answer=self.NO_CONTENT_MESSAGE,
                citations=[],
                grounded=False,
                conversation_id=conversation_id,
            )
            # Record in conversation history
            self._add_to_history(conversation_id, "user", question)
            self._add_to_history(
                conversation_id, "assistant", self.NO_CONTENT_MESSAGE
            )
            return response

        # Step 3: Extract citations (Task 13.2)
        citations = self._extract_citations(search_results)

        # Step 3a: Apply visual boost for process-related queries
        search_results = self._apply_visual_boost(question, search_results)

        # Step 3b: Limit visual chunks and re-sort by relevance
        search_results = self._limit_visual_chunks(search_results)

        # Step 4: Truncate context to fit within token limit
        truncated_results = self._truncate_context(search_results)

        # Step 5: Generate response via LLM
        context_text = self._build_context(truncated_results)
        history_text = self._format_history(history)
        answer = await self._generate_response(question, context_text, history_text)

        # Step 6: Record in conversation history (Task 13.4)
        self._add_to_history(conversation_id, "user", question)
        self._add_to_history(conversation_id, "assistant", answer)

        return RAGResponse(
            answer=answer,
            citations=citations,
            grounded=True,
            conversation_id=conversation_id,
        )

    # -----------------------------------------------------------------------
    # Source Citation Extraction (Task 13.2)
    # -----------------------------------------------------------------------

    def _extract_citations(
        self, search_results: list[SearchResult]
    ) -> list[SourceCitation]:
        """Extract source citations from search results.

        Each citation includes Document-UUID, title, version,
        page/section information, and content_type/visual_type for
        visual chunks.

        Args:
            search_results: List of search results from KnowledgeService.

        Returns:
            List of unique SourceCitation objects.
        """
        seen: set[str] = set()
        citations: list[SourceCitation] = []

        for result in search_results:
            # Deduplicate by document_uuid + version
            key = f"{result.document_uuid}:{result.version}"
            if key in seen:
                continue
            seen.add(key)

            # Extract page/section from metadata if available
            page_or_section = result.metadata.get(
                "page", result.metadata.get("section", "N/A")
            )
            if isinstance(page_or_section, int):
                page_or_section = f"Page {page_or_section}"

            # Determine content_type and visual_type from metadata
            is_visual = result.metadata.get("is_visual", False)
            content_type_value = result.metadata.get("content_type", "text")
            if is_visual or content_type_value == "visual":
                content_type = "visual"
                visual_type = result.metadata.get("visual_type")
            else:
                content_type = "text"
                visual_type = None

            citations.append(
                SourceCitation(
                    document_uuid=result.document_uuid,
                    title=result.title,
                    version=result.version,
                    page_or_section=str(page_or_section),
                    content_type=content_type,
                    visual_type=visual_type,
                )
            )

        return citations

    # -----------------------------------------------------------------------
    # Conversation Context Management (Task 13.4)
    # -----------------------------------------------------------------------

    def _get_conversation_history(
        self, conversation_id: str
    ) -> list[ConversationMessage]:
        """Get the conversation history for a given conversation ID.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            List of conversation messages in chronological order.
        """
        return self._conversations.get(conversation_id, [])

    def _add_to_history(
        self, conversation_id: str, role: str, content: str
    ) -> None:
        """Add a message to the conversation history.

        Args:
            conversation_id: The conversation identifier.
            role: Either "user" or "assistant".
            content: The message content.
        """
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = []

        self._conversations[conversation_id].append(
            ConversationMessage(role=role, content=content)
        )

    def get_conversation(
        self, conversation_id: str
    ) -> list[ConversationMessage]:
        """Get the full conversation history.

        Args:
            conversation_id: The conversation identifier.

        Returns:
            List of conversation messages.
        """
        return self._conversations.get(conversation_id, [])

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear a conversation history.

        Args:
            conversation_id: The conversation identifier.
        """
        self._conversations.pop(conversation_id, None)

    # -----------------------------------------------------------------------
    # Visual Chunk Handling (Task 5.1)
    # -----------------------------------------------------------------------

    def _apply_visual_boost(
        self,
        query: str,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        """Boost Visual_Chunk relevance for process-related queries.

        If the query contains any VISUAL_BOOST_KEYWORDS, multiply the
        relevance_score of Visual_Chunks by the configured VISUAL_BOOST_FACTOR.

        Args:
            query: The user's search query.
            results: Search results from hybrid search.

        Returns:
            Results with boosted scores for visual chunks (if applicable).
        """
        query_lower = query.lower()
        has_keyword = any(
            keyword in query_lower for keyword in self.VISUAL_BOOST_KEYWORDS
        )

        if not has_keyword:
            return results

        boost_factor = self._settings.visual_boost_factor

        boosted: list[SearchResult] = []
        for result in results:
            is_visual = result.metadata.get("is_visual", False)
            content_type = result.metadata.get("content_type", "text")

            if is_visual or content_type == "visual":
                # Create a new SearchResult with boosted score
                boosted.append(
                    SearchResult(
                        document_uuid=result.document_uuid,
                        title=result.title,
                        version=result.version,
                        excerpt=result.excerpt,
                        relevance_score=result.relevance_score * boost_factor,
                        metadata=result.metadata,
                        document_type=result.document_type,
                        status=result.status,
                        tags=result.tags,
                        created_at=result.created_at,
                        updated_at=result.updated_at,
                    )
                )
            else:
                boosted.append(result)

        return boosted

    def _limit_visual_chunks(
        self,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        """Limit Visual_Chunks to MAX_VISUAL_CHUNKS_PER_QUERY.

        Selects the top-N highest-relevance Visual_Chunks and fills
        remaining slots (up to top_k) with text chunks. Results are
        returned sorted by relevance score descending.

        Args:
            results: Ranked search results (possibly with boosted scores).

        Returns:
            Filtered results respecting the visual chunk limit.
        """
        visual_chunks: list[SearchResult] = []
        text_chunks: list[SearchResult] = []

        for result in results:
            is_visual = result.metadata.get("is_visual", False)
            content_type = result.metadata.get("content_type", "text")

            if is_visual or content_type == "visual":
                visual_chunks.append(result)
            else:
                text_chunks.append(result)

        # Sort visual chunks by relevance (highest first) and cap at limit
        visual_chunks.sort(key=lambda r: r.relevance_score, reverse=True)
        selected_visual = visual_chunks[: self.MAX_VISUAL_CHUNKS_PER_QUERY]

        # Sort text chunks by relevance (highest first)
        text_chunks.sort(key=lambda r: r.relevance_score, reverse=True)

        # Fill remaining slots with text chunks
        remaining_slots = self._top_k - len(selected_visual)
        selected_text = text_chunks[:max(0, remaining_slots)]

        # Combine and sort by relevance score descending
        combined = selected_visual + selected_text
        combined.sort(key=lambda r: r.relevance_score, reverse=True)

        return combined

    # -----------------------------------------------------------------------
    # LLM Response Generation
    # -----------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build the grounding system prompt for the chat model.

        Returns:
            The system prompt instructing the model to answer only from
            context, cite sources, and never fabricate information.
        """
        return _SYSTEM_PROMPT

    def _build_context(self, search_results: list[SearchResult]) -> str:
        """Build context text from search results for LLM prompt.

        Formats each chunk with the source reference pattern:
        - Visual chunks: [Source N: {title} v{version} - {visual_type} on page {source_page}]
        - Text chunks: [Source N: {title} v{version}]

        Args:
            search_results: Retrieved document chunks.

        Returns:
            Formatted context string with source references.
        """
        context_parts: list[str] = []
        for i, result in enumerate(search_results, 1):
            is_visual = result.metadata.get("is_visual", False)
            content_type = result.metadata.get("content_type", "text")

            if is_visual or content_type == "visual":
                visual_type = result.metadata.get("visual_type", "diagram")
                source_page = result.metadata.get("source_page", "unknown")
                header = (
                    f"[Source {i}: {result.title} v{result.version} "
                    f"- {visual_type} on page {source_page}]"
                )
            else:
                header = f"[Source {i}: {result.title} v{result.version}]"

            context_parts.append(f"{header}\n{result.excerpt}")
        return "\n\n".join(context_parts)

    def _truncate_context(
        self,
        search_results: list[SearchResult],
        max_tokens: int = _MAX_CONTEXT_TOKENS,
    ) -> list[SearchResult]:
        """Truncate search results to fit within the token limit.

        Removes lowest-relevance chunks until the combined context is
        within the max_tokens limit (approximated by whitespace splitting).
        Always retains at least the single highest-relevance chunk.

        Args:
            search_results: List of search results sorted by relevance.
            max_tokens: Maximum number of tokens (whitespace-split words).

        Returns:
            Filtered list of SearchResult objects within the token budget.
        """
        if not search_results:
            return []

        # Find the highest-relevance chunk (must always be kept)
        highest_idx = 0
        highest_score = search_results[0].relevance_score
        for i, result in enumerate(search_results):
            if result.relevance_score > highest_score:
                highest_score = result.relevance_score
                highest_idx = i

        def _count_tokens(results: list[SearchResult]) -> int:
            """Count approximate tokens using whitespace splitting."""
            total = 0
            for i, result in enumerate(results, 1):
                # Include the source header in token count
                header = f"[Source {i}: {result.title} v{result.version}]"
                total += len(header.split())
                total += len(result.excerpt.split())
            return total

        # Start with all results
        remaining = list(search_results)

        # Remove lowest-relevance chunks until within limit
        while _count_tokens(remaining) > max_tokens and len(remaining) > 1:
            # Find the lowest-relevance chunk that is NOT the highest-relevance one
            lowest_idx = -1
            lowest_score = float("inf")
            for i, result in enumerate(remaining):
                # Never remove the highest-relevance chunk
                if result is search_results[highest_idx]:
                    continue
                if result.relevance_score < lowest_score:
                    lowest_score = result.relevance_score
                    lowest_idx = i

            if lowest_idx == -1:
                # Only the highest-relevance chunk remains
                break

            remaining.pop(lowest_idx)

        return remaining

    def _format_history(
        self, history: list[ConversationMessage]
    ) -> str:
        """Format conversation history for LLM prompt.

        Args:
            history: List of previous conversation messages.

        Returns:
            Formatted history string.
        """
        if not history:
            return ""

        parts: list[str] = []
        for msg in history[-_MAX_HISTORY_MESSAGES:]:  # Keep last 6 messages
            parts.append(f"{msg.role.capitalize()}: {msg.content}")
        return "\n".join(parts)

    def _build_messages(
        self,
        question: str,
        context: str,
        history: list[ConversationMessage],
    ) -> list[dict[str, Any]]:
        """Build the messages array for the chat completion request.

        Structure:
        1. System prompt with grounding instructions
        2. Conversation history (last 6 messages as user/assistant)
        3. Context as a user message
        4. Current question as the final user message

        Args:
            question: The user's current question.
            context: Formatted context string with source references.
            history: Conversation history messages.

        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        messages: list[dict[str, Any]] = []

        # 1. System prompt
        messages.append({
            "role": "system",
            "content": self._build_system_prompt(),
        })

        # 2. Conversation history (last 6 messages)
        for msg in history[-_MAX_HISTORY_MESSAGES:]:
            messages.append({
                "role": msg.role,
                "content": msg.content,
            })

        # 3. Context as a user message
        messages.append({
            "role": "user",
            "content": f"Context documents:\n\n{context}",
        })

        # 4. Current question as the final user message
        messages.append({
            "role": "user",
            "content": question,
        })

        return messages

    async def _generate_response(
        self, question: str, context: str, history: str
    ) -> str:
        """Generate a response using vLLM chat completion or mock.

        In gpu/cpu mode: calls ensure_model(CHAT) then sends a chat
        completion request to vLLM via InferenceClient.

        In mock mode: returns a placeholder response without HTTP calls.

        Args:
            question: The user's question.
            context: Retrieved document context.
            history: Formatted conversation history.

        Returns:
            Generated answer text.

        Raises:
            ModelManagerError: If the chat model fails to load.
            InferenceError: If the vLLM request fails.
            InferenceTimeoutError: If vLLM doesn't respond within 60s.
        """
        # Mock mode: use placeholder logic
        if (
            self._model_manager is None
            or self._inference_client is None
            or self._settings.model_manager_mode == "mock"
        ):
            return self._generate_mock_response(question, context, history)

        # Real inference mode (gpu/cpu)
        from alcoabase.services.inference_client import (
            InferenceError,
            InferenceTimeoutError,
        )
        from alcoabase.services.model_manager import ModelManagerError, ModelRole

        # Ensure chat model is loaded
        try:
            await self._model_manager.ensure_model(ModelRole.CHAT)
        except ModelManagerError:
            # Propagate ModelManagerError to caller
            raise

        # Build messages array from conversation history
        history_messages = self._get_conversation_history_from_text(history)
        messages = self._build_messages(question, context, history_messages)

        # Send chat completion request
        try:
            response = await self._inference_client.chat_completion(
                model=self._settings.model_chat_name,
                messages=messages,
                temperature=_CHAT_TEMPERATURE,
                max_tokens=_CHAT_MAX_TOKENS,
            )
            return response
        except InferenceTimeoutError:
            logger.error(
                "vLLM chat completion timed out (60s) for question: %s",
                question[:100],
            )
            raise
        except InferenceError as e:
            body = str(e)[:500]
            logger.error(
                "vLLM chat completion failed | status=%s | body=%s",
                e.status_code,
                body,
            )
            raise

    def _get_conversation_history_from_text(
        self, history_text: str
    ) -> list[ConversationMessage]:
        """Parse formatted history text back into ConversationMessage objects.

        This handles the case where history is passed as a pre-formatted
        string from the query method.

        Args:
            history_text: Formatted history string from _format_history.

        Returns:
            List of ConversationMessage objects.
        """
        if not history_text:
            return []

        messages: list[ConversationMessage] = []
        for line in history_text.split("\n"):
            if line.startswith("User: "):
                messages.append(
                    ConversationMessage(role="user", content=line[6:])
                )
            elif line.startswith("Assistant: "):
                messages.append(
                    ConversationMessage(role="assistant", content=line[11:])
                )
        return messages

    def _generate_mock_response(
        self, question: str, context: str, history: str
    ) -> str:
        """Generate a mock/placeholder response for development/testing.

        Args:
            question: The user's question.
            context: Retrieved document context.
            history: Formatted conversation history.

        Returns:
            Placeholder answer text.
        """
        logger.info(
            "Generating RAG response (placeholder) for question: %s",
            question[:100],
        )

        return (
            f"Based on the available documentation, here is what I found "
            f"regarding your question:\n\n"
            f"The knowledge base contains relevant information from the "
            f"indexed documents. [Placeholder response - real LLM inference "
            f"will be provided by Model_Manager (Task 18)]\n\n"
            f"Context used: {len(context)} characters from retrieved chunks."
        )
