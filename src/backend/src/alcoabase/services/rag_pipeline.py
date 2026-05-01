"""RAG Pipeline for conversational knowledge queries.

This module provides:
- Retrieval-augmented generation using KnowledgeService for chunk retrieval
- Source citation extraction (Document-UUID, title, version, page/section)
- Grounded response enforcement (no hallucination without context)
- Conversation context management for follow-up questions
- ABAC enforcement on retrieved chunks

References:
    - Task 13: RAG Pipeline (Conversational Knowledge Queries)
    - Design doc Section 9: Knowledge Service / RAG Pipeline
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from alcoabase.services.knowledge_service import KnowledgeService, SearchResult

logger = logging.getLogger(__name__)


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
    """

    document_uuid: str
    title: str
    version: str
    page_or_section: str


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
    as context to an LLM (placeholder), and generates grounded responses
    with source citations.

    Attributes:
        _knowledge_service: Service for document retrieval and search.
        _conversations: In-memory conversation history store.
        _top_k: Number of chunks to retrieve per query.
    """

    NO_CONTENT_MESSAGE = (
        "No matching content found in the knowledge base for your query. "
        "Please try rephrasing your question or check that relevant "
        "documents have been indexed."
    )

    def __init__(
        self,
        knowledge_service: KnowledgeService | None = None,
        top_k: int = 5,
    ) -> None:
        """Initialize the RAG pipeline.

        Args:
            knowledge_service: KnowledgeService instance for retrieval.
                Creates a new instance if not provided.
            top_k: Number of top chunks to retrieve per query.
        """
        self._knowledge_service = knowledge_service or KnowledgeService()
        self._conversations: dict[str, list[ConversationMessage]] = {}
        self._top_k = top_k

    # -----------------------------------------------------------------------
    # Core Query (Task 13.1)
    # -----------------------------------------------------------------------

    async def query(
        self,
        question: str,
        user_id: int,
        conversation_id: str | None = None,
    ) -> RAGResponse:
        """Retrieve relevant chunks and generate a grounded answer.

        1. Retrieve top-k chunks from KnowledgeService (ABAC-filtered)
        2. Build prompt with retrieved context + conversation history
        3. Generate response via LLM (placeholder)
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
        search_results = self._knowledge_service.hybrid_search(
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

        # Step 4: Generate response via LLM (placeholder)
        context_text = self._build_context(search_results)
        history_text = self._format_history(history)
        answer = self._generate_response(question, context_text, history_text)

        # Step 5: Record in conversation history (Task 13.4)
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

        Each citation includes Document-UUID, title, version, and
        page/section information.

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

            citations.append(
                SourceCitation(
                    document_uuid=result.document_uuid,
                    title=result.title,
                    version=result.version,
                    page_or_section=str(page_or_section),
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
    # LLM Response Generation (Placeholder)
    # -----------------------------------------------------------------------

    def _build_context(self, search_results: list[SearchResult]) -> str:
        """Build context text from search results for LLM prompt.

        Args:
            search_results: Retrieved document chunks.

        Returns:
            Formatted context string with source references.
        """
        context_parts: list[str] = []
        for i, result in enumerate(search_results, 1):
            context_parts.append(
                f"[Source {i}: {result.title} v{result.version} "
                f"({result.document_uuid})]\n{result.excerpt}"
            )
        return "\n\n".join(context_parts)

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
        for msg in history[-6:]:  # Keep last 6 messages for context
            parts.append(f"{msg.role.capitalize()}: {msg.content}")
        return "\n".join(parts)

    def _generate_response(
        self, question: str, context: str, history: str
    ) -> str:
        """Generate a response using the LLM (placeholder).

        This is a placeholder that returns a formatted response based on
        the retrieved context. The Model_Manager (Task 18) will provide
        real LLM inference.

        Args:
            question: The user's question.
            context: Retrieved document context.
            history: Formatted conversation history.

        Returns:
            Generated answer text.
        """
        # Placeholder: return a structured response based on context
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
