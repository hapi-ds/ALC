"""Unit tests for RAG Pipeline service.

Tests cover:
- Citation extraction from search results
- Grounding enforcement (no content found case)
- ABAC filtering on RAG queries
- Conversation context management

References:
    - Task 13.7: Unit tests for citation extraction, grounding enforcement, and ABAC filtering
"""

import pytest

from alcoabase.services.knowledge_service import KnowledgeService, SearchResult
from alcoabase.services.rag_pipeline import RAGPipeline, SourceCitation


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def knowledge_service() -> KnowledgeService:
    """Create a KnowledgeService with test data indexed."""
    service = KnowledgeService()
    return service


@pytest.fixture
def knowledge_service_with_data() -> KnowledgeService:
    """Create a KnowledgeService with indexed test documents."""
    service = KnowledgeService()

    # Index a test document with searchable content
    service.index_document(
        document_uuid="2024-00001",
        version="1.0",
        chunks=[
            "The standard operating procedure for cleaning requires all personnel to wear PPE.",
            "Safety protocols must be followed at all times during the cleaning process.",
            "Documentation of cleaning activities must be completed before end of shift.",
        ],
        embeddings=service.generate_embeddings(["chunk1", "chunk2", "chunk3"]),
        metadata={
            "title": "Cleaning SOP",
            "tags": ["SOP", "Cleaning"],
            "page": 1,
        },
    )

    # Index another document with restricted access
    service.index_document(
        document_uuid="2024-00002",
        version="2.0",
        chunks=[
            "Restricted document about cleaning validation protocols.",
        ],
        embeddings=service.generate_embeddings(["chunk1"]),
        metadata={
            "title": "Cleaning Validation Protocol",
            "tags": ["Protocol", "Validation"],
            "permitted_user_ids": {10, 20},  # Only users 10 and 20 can access
            "is_csv_validation_record": False,
        },
    )

    # Index a document accessible to all
    service.index_document(
        document_uuid="2024-00003",
        version="1.0",
        chunks=[
            "General safety guidelines for all cleaning operations.",
        ],
        embeddings=service.generate_embeddings(["chunk1"]),
        metadata={
            "title": "Safety Guidelines",
            "tags": ["Safety"],
            "section": "Section 2.1",
        },
    )

    return service


@pytest.fixture
def rag_pipeline(knowledge_service_with_data: KnowledgeService) -> RAGPipeline:
    """Create a RAGPipeline with test data."""
    return RAGPipeline(knowledge_service=knowledge_service_with_data, top_k=5)


# ---------------------------------------------------------------------------
# Citation Extraction Tests (Task 13.2)
# ---------------------------------------------------------------------------


class TestCitationExtraction:
    """Tests for source citation extraction."""

    def test_citations_extracted_from_search_results(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """Citations include Document-UUID, title, version, and page/section."""
        results = [
            SearchResult(
                document_uuid="2024-00001",
                title="Cleaning SOP",
                version="1.0",
                excerpt="Some text",
                relevance_score=0.9,
                metadata={"page": 3},
            ),
            SearchResult(
                document_uuid="2024-00002",
                title="Validation Protocol",
                version="2.0",
                excerpt="Other text",
                relevance_score=0.7,
                metadata={"section": "Section 4.2"},
            ),
        ]

        citations = rag_pipeline._extract_citations(results)

        assert len(citations) == 2
        assert citations[0].document_uuid == "2024-00001"
        assert citations[0].title == "Cleaning SOP"
        assert citations[0].version == "1.0"
        assert citations[0].page_or_section == "Page 3"
        assert citations[1].document_uuid == "2024-00002"
        assert citations[1].page_or_section == "Section 4.2"

    def test_citations_deduplicated_by_document_version(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """Multiple chunks from same document produce only one citation."""
        results = [
            SearchResult(
                document_uuid="2024-00001",
                title="Cleaning SOP",
                version="1.0",
                excerpt="Chunk 1",
                relevance_score=0.9,
                metadata={"page": 1},
            ),
            SearchResult(
                document_uuid="2024-00001",
                title="Cleaning SOP",
                version="1.0",
                excerpt="Chunk 2",
                relevance_score=0.8,
                metadata={"page": 2},
            ),
        ]

        citations = rag_pipeline._extract_citations(results)

        assert len(citations) == 1
        assert citations[0].document_uuid == "2024-00001"

    def test_citations_empty_for_no_results(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """No citations when no search results."""
        citations = rag_pipeline._extract_citations([])
        assert citations == []

    def test_citation_page_or_section_defaults_to_na(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """Page/section defaults to N/A when not in metadata."""
        results = [
            SearchResult(
                document_uuid="2024-00001",
                title="Test Doc",
                version="1.0",
                excerpt="Text",
                relevance_score=0.5,
                metadata={},
            ),
        ]

        citations = rag_pipeline._extract_citations(results)
        assert citations[0].page_or_section == "N/A"


# ---------------------------------------------------------------------------
# Grounding Enforcement Tests (Task 13.3)
# ---------------------------------------------------------------------------


class TestGroundingEnforcement:
    """Tests for grounded response enforcement."""

    @pytest.mark.asyncio
    async def test_no_content_message_when_no_chunks(
        self, knowledge_service: KnowledgeService
    ) -> None:
        """Returns 'no matching content' when no relevant chunks found."""
        pipeline = RAGPipeline(knowledge_service=knowledge_service, top_k=5)

        response = await pipeline.query(
            question="What is the meaning of life?",
            user_id=1,
        )

        assert response.grounded is False
        assert "No matching content found" in response.answer
        assert response.citations == []

    @pytest.mark.asyncio
    async def test_grounded_response_when_chunks_found(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """Returns grounded response when relevant chunks are found."""
        response = await rag_pipeline.query(
            question="cleaning",
            user_id=1,
        )

        assert response.grounded is True
        assert len(response.citations) > 0
        assert response.answer != RAGPipeline.NO_CONTENT_MESSAGE


# ---------------------------------------------------------------------------
# ABAC Filtering Tests (Task 13.5)
# ---------------------------------------------------------------------------


class TestABACFiltering:
    """Tests for ABAC enforcement on RAG queries."""

    @pytest.mark.asyncio
    async def test_abac_filters_restricted_documents(
        self, knowledge_service_with_data: KnowledgeService
    ) -> None:
        """User without permission does not see restricted document chunks."""
        pipeline = RAGPipeline(
            knowledge_service=knowledge_service_with_data, top_k=10
        )

        # User 1 should not see document 2024-00002 (restricted to users 10, 20)
        response = await pipeline.query(
            question="cleaning validation",
            user_id=1,
        )

        # Should not contain citations from the restricted document
        restricted_uuids = [
            c.document_uuid for c in response.citations
            if c.document_uuid == "2024-00002"
        ]
        assert len(restricted_uuids) == 0

    @pytest.mark.asyncio
    async def test_abac_permits_authorized_user(
        self, knowledge_service_with_data: KnowledgeService
    ) -> None:
        """User with permission can see restricted document chunks."""
        pipeline = RAGPipeline(
            knowledge_service=knowledge_service_with_data, top_k=10
        )

        # User 10 should see document 2024-00002
        response = await pipeline.query(
            question="cleaning validation",
            user_id=10,
        )

        # Should contain citation from the restricted document
        has_restricted = any(
            c.document_uuid == "2024-00002" for c in response.citations
        )
        assert has_restricted is True


# ---------------------------------------------------------------------------
# Conversation Context Tests (Task 13.4)
# ---------------------------------------------------------------------------


class TestConversationContext:
    """Tests for conversation context management."""

    @pytest.mark.asyncio
    async def test_conversation_id_generated_on_first_query(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """First query generates a new conversation ID."""
        response = await rag_pipeline.query(
            question="cleaning",
            user_id=1,
        )

        assert response.conversation_id is not None
        assert len(response.conversation_id) > 0

    @pytest.mark.asyncio
    async def test_conversation_history_maintained(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """Follow-up queries maintain conversation history."""
        # First query
        response1 = await rag_pipeline.query(
            question="cleaning",
            user_id=1,
        )
        conv_id = response1.conversation_id

        # Follow-up query
        response2 = await rag_pipeline.query(
            question="safety",
            user_id=1,
            conversation_id=conv_id,
        )

        assert response2.conversation_id == conv_id

        # Check history has both exchanges
        history = rag_pipeline.get_conversation(conv_id)
        assert len(history) == 4  # 2 user + 2 assistant messages

    @pytest.mark.asyncio
    async def test_clear_conversation(
        self, rag_pipeline: RAGPipeline
    ) -> None:
        """Clearing conversation removes history."""
        response = await rag_pipeline.query(
            question="cleaning",
            user_id=1,
        )
        conv_id = response.conversation_id

        rag_pipeline.clear_conversation(conv_id)

        history = rag_pipeline.get_conversation(conv_id)
        assert history == []
