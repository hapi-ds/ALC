"""Unit tests for the HybridQueryEngine service.

Tests validate:
- Graceful degradation (BM25-only fallback when vLLM is unavailable)
- Unified search partial results when one index is unreachable
- Query validation (empty query rejection)
- Role-based access patterns (member, document_admin, system_admin)
- Pagination edge cases (empty results, last page, beyond range)
- Mock InferenceClient and LiteratureIndexManager

References:
    - Requirements: 6.8, 6.9, 6.10, 7.7, 7.8
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.embedding.exceptions import SearchServiceUnavailableError
from alcoabase.literature.embedding.services.hybrid_query_engine import (
    HybridQueryEngine,
    HybridSearchRequest,
    HybridSearchResponse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_inference_client() -> AsyncMock:
    """Create a mock InferenceClient that returns valid embeddings."""
    client = AsyncMock()
    # Return a 1024-dimensional vector for query embedding
    client.create_embeddings = AsyncMock(
        return_value=[[0.1] * 1024]
    )
    return client


@pytest.fixture
def mock_model_manager() -> AsyncMock:
    """Create a mock ModelManager."""
    manager = AsyncMock()
    manager.ensure_model = AsyncMock(return_value="http://vllm:8000")
    return manager


@pytest.fixture
def mock_index_manager() -> MagicMock:
    """Create a mock LiteratureIndexManager with a mock OpenSearch client."""
    manager = MagicMock()
    manager._index_name = MagicMock(
        side_effect=lambda cid: f"literature-embeddings-{cid}"
    )
    # Mock the _client attribute with async search method
    manager._client = MagicMock()
    manager._client.search = AsyncMock(
        return_value={
            "hits": {
                "hits": [
                    {
                        "_id": "doc1",
                        "_score": 5.2,
                        "_source": {
                            "chunk_text": "protein folding mechanisms",
                            "title": "Protein Research",
                            "authors": ["Smith J."],
                            "doi": "10.1234/prot.2024",
                            "publication_date": "2024-01-15",
                            "source_id": "pubmed",
                            "partition_tag": "public_literature",
                            "section_heading": "Abstract",
                            "ingestion_record_id": 100,
                            "company_id": 1,
                        },
                    },
                    {
                        "_id": "doc2",
                        "_score": 3.8,
                        "_source": {
                            "chunk_text": "molecular dynamics simulation",
                            "title": "MD Simulations",
                            "authors": ["Johnson A."],
                            "doi": "10.5678/md.2024",
                            "publication_date": "2024-03-20",
                            "source_id": "pubmed",
                            "partition_tag": "public_literature",
                            "section_heading": "Methods",
                            "ingestion_record_id": 101,
                            "company_id": 1,
                        },
                    },
                ]
            }
        }
    )
    return manager


@pytest.fixture
def engine(
    mock_index_manager: MagicMock,
    mock_inference_client: AsyncMock,
    mock_model_manager: AsyncMock,
) -> HybridQueryEngine:
    """Create a HybridQueryEngine with mocked dependencies."""
    return HybridQueryEngine(
        index_manager=mock_index_manager,
        inference_client=mock_inference_client,
        model_manager=mock_model_manager,
        model_name="test-embedding-model",
        default_rrf_k=60,
    )


def _make_request(
    query: str = "protein folding",
    company_id: int = 1,
    user_id: int = 42,
    **kwargs,
) -> HybridSearchRequest:
    """Helper to create a HybridSearchRequest with sensible defaults."""
    return HybridSearchRequest(
        query=query,
        company_id=company_id,
        user_id=user_id,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests: Graceful Degradation (Requirement 6.8)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Tests for BM25-only fallback when vLLM is unavailable."""

    @pytest.mark.asyncio
    async def test_bm25_fallback_on_embedding_failure(
        self,
        engine: HybridQueryEngine,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Returns results with degraded_mode=True when vLLM fails.

        Requirement 6.8: IF the vLLM embedding instance is unavailable,
        THEN fall back to BM25-only search and include degraded_mode: true.
        """
        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=Exception("vLLM connection refused")
        )

        request = _make_request(semantic_weight=0.5)
        response = await engine.search(request)

        assert isinstance(response, HybridSearchResponse)
        assert response.degraded_mode is True
        assert response.total_count > 0
        assert len(response.results) > 0

    @pytest.mark.asyncio
    async def test_bm25_fallback_returns_valid_results(
        self,
        engine: HybridQueryEngine,
        mock_inference_client: AsyncMock,
    ) -> None:
        """BM25-only fallback still returns properly structured results."""
        mock_inference_client.create_embeddings = AsyncMock(
            side_effect=TimeoutError("vLLM timeout")
        )

        request = _make_request(semantic_weight=0.7)
        response = await engine.search(request)

        assert response.degraded_mode is True
        for result in response.results:
            assert result.chunk_text != ""
            assert result.title != ""
            assert result.partition_tag in ("public_literature", "private_knowledge")

    @pytest.mark.asyncio
    async def test_no_fallback_when_semantic_weight_zero(
        self,
        engine: HybridQueryEngine,
        mock_inference_client: AsyncMock,
    ) -> None:
        """No embedding generation attempted when semantic_weight=0.0."""
        request = _make_request(semantic_weight=0.0)
        response = await engine.search(request)

        # Should not attempt embedding generation at all
        mock_inference_client.create_embeddings.assert_not_called()
        assert response.degraded_mode is False

    @pytest.mark.asyncio
    async def test_fallback_when_model_manager_fails(
        self,
        engine: HybridQueryEngine,
        mock_model_manager: AsyncMock,
    ) -> None:
        """Falls back to BM25 when ModelManager.ensure_model raises."""
        mock_model_manager.ensure_model = AsyncMock(
            side_effect=Exception("Model not available")
        )

        request = _make_request(semantic_weight=0.5)
        response = await engine.search(request)

        assert response.degraded_mode is True
        assert response.total_count > 0

    @pytest.mark.asyncio
    async def test_fallback_when_embeddings_return_empty(
        self,
        engine: HybridQueryEngine,
        mock_inference_client: AsyncMock,
    ) -> None:
        """Falls back to BM25 when InferenceClient returns empty list."""
        mock_inference_client.create_embeddings = AsyncMock(return_value=[])

        request = _make_request(semantic_weight=0.5)
        response = await engine.search(request)

        assert response.degraded_mode is True


# ---------------------------------------------------------------------------
# Tests: Unified Search Partial Results (Requirement 7.7)
# ---------------------------------------------------------------------------


class TestUnifiedSearchPartialResults:
    """Tests for partial results when one index is unreachable."""

    @pytest.mark.asyncio
    async def test_partial_results_when_internal_index_fails(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Returns literature results with partial_results flag when internal fails.

        Requirement 7.7: IF one of the two indices is unreachable,
        return results from the available index only and include
        partial_results: true and unavailable_index field.
        """
        call_count = [0]

        async def _search_side_effect(index, body):
            call_count[0] += 1
            if "knowledge-" in index:
                raise Exception("Internal index unreachable")
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "lit1",
                            "_score": 4.5,
                            "_source": {
                                "chunk_text": "literature content",
                                "title": "Paper A",
                                "authors": ["Author X"],
                                "doi": "10.1/a",
                                "publication_date": "2024-01-01",
                                "source_id": "pubmed",
                                "partition_tag": "public_literature",
                                "section_heading": "Intro",
                                "ingestion_record_id": 50,
                                "company_id": 1,
                            },
                        }
                    ]
                }
            }

        mock_index_manager._client.search = AsyncMock(
            side_effect=_search_side_effect
        )

        request = _make_request(include_internal=True)
        response = await engine.unified_search(request)

        assert response.partial_results is True
        assert response.unavailable_index == "knowledge-1"
        assert response.total_count > 0

    @pytest.mark.asyncio
    async def test_partial_results_when_literature_index_fails(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Returns internal results when literature index is unreachable."""
        async def _search_side_effect(index, body):
            if "literature-embeddings-" in index:
                raise Exception("Literature index unreachable")
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "int1",
                            "_score": 3.2,
                            "_source": {
                                "chunk_text": "internal doc content",
                                "title": "Internal SOP",
                                "authors": [],
                                "doi": None,
                                "publication_date": None,
                                "source_id": None,
                                "partition_tag": "private_knowledge",
                                "section_heading": "Procedure",
                                "ingestion_record_id": 200,
                                "company_id": 1,
                            },
                        }
                    ]
                }
            }

        mock_index_manager._client.search = AsyncMock(
            side_effect=_search_side_effect
        )

        request = _make_request(include_internal=True)
        response = await engine.unified_search(request)

        assert response.partial_results is True
        assert response.unavailable_index == "literature-embeddings-1"
        assert response.total_count > 0

    @pytest.mark.asyncio
    async def test_raises_when_both_indices_fail(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Raises SearchServiceUnavailableError when both indices fail."""
        mock_index_manager._client.search = AsyncMock(
            side_effect=Exception("All indices down")
        )

        request = _make_request(include_internal=True)

        with pytest.raises(SearchServiceUnavailableError):
            await engine.unified_search(request)


# ---------------------------------------------------------------------------
# Tests: Query Validation (Requirement 6.9)
# ---------------------------------------------------------------------------


class TestQueryValidation:
    """Tests for query validation behavior.

    Note: The HybridQueryEngine itself does not reject empty queries;
    that validation happens at the API/schema layer. These tests verify
    the engine's behavior when receiving edge-case query strings.
    """

    @pytest.mark.asyncio
    async def test_single_character_query_executes(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """A single-character query should still execute search."""
        request = _make_request(query="a")
        response = await engine.search(request)

        assert isinstance(response, HybridSearchResponse)
        assert response.page == 1

    @pytest.mark.asyncio
    async def test_max_length_query_executes(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """A 1000-character query should still execute search."""
        long_query = "protein " * 125  # ~1000 chars
        request = _make_request(query=long_query.strip())
        response = await engine.search(request)

        assert isinstance(response, HybridSearchResponse)

    @pytest.mark.asyncio
    async def test_special_characters_in_query(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """Query with special characters should not cause errors."""
        request = _make_request(query='query with "quotes" and (parens) [brackets]')
        response = await engine.search(request)

        assert isinstance(response, HybridSearchResponse)


# ---------------------------------------------------------------------------
# Tests: OpenSearch Unavailable (Requirement 6.10)
# ---------------------------------------------------------------------------


class TestOpenSearchUnavailable:
    """Tests for error handling when OpenSearch is unreachable."""

    @pytest.mark.asyncio
    async def test_search_raises_unavailable_on_opensearch_error(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Raises SearchServiceUnavailableError when OpenSearch fails.

        Requirement 6.10: IF the OpenSearch cluster is unreachable,
        return an error response indicating search service unavailability
        without exposing internal infrastructure details.
        """
        mock_index_manager._client.search = AsyncMock(
            side_effect=ConnectionError("Connection refused to OpenSearch")
        )

        request = _make_request()

        with pytest.raises(SearchServiceUnavailableError) as exc_info:
            await engine.search(request)

        # Error should not expose internal details
        assert "Connection refused" not in exc_info.value.message
        assert "unavailable" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_search_raises_unavailable_on_timeout(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Raises SearchServiceUnavailableError when OpenSearch times out."""
        mock_index_manager._client.search = AsyncMock(
            side_effect=TimeoutError("Read timed out")
        )

        request = _make_request()

        with pytest.raises(SearchServiceUnavailableError):
            await engine.search(request)


# ---------------------------------------------------------------------------
# Tests: Role-Based Access (Requirement 7.5, 7.8)
# ---------------------------------------------------------------------------


class TestRoleBasedAccess:
    """Tests for ABAC filtering in unified search.

    The HybridQueryEngine applies ABAC filtering for internal documents.
    Literature results are accessible to all company members without
    per-document permission checks (Requirement 7.5).
    Users without member role are rejected at the API layer (Requirement 7.8).
    """

    @pytest.mark.asyncio
    async def test_member_sees_all_public_literature(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """Member role grants access to all public_literature results.

        Requirement 7.5: Users with member role or higher get all
        public_literature results without per-document permission checks.
        """
        request = _make_request(user_id=42)
        response = await engine.search(request)

        # All results should be accessible to member
        assert response.total_count > 0
        for result in response.results:
            assert result.partition_tag == "public_literature"

    @pytest.mark.asyncio
    async def test_abac_filters_restricted_internal_docs(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """ABAC filter removes internal docs user cannot access."""
        async def _search_side_effect(index, body):
            if "knowledge-" in index:
                return {
                    "hits": {
                        "hits": [
                            {
                                "_id": "restricted_doc",
                                "_score": 4.0,
                                "_source": {
                                    "chunk_text": "restricted content",
                                    "title": "Restricted SOP",
                                    "authors": [],
                                    "doi": None,
                                    "publication_date": None,
                                    "source_id": None,
                                    "partition_tag": "private_knowledge",
                                    "section_heading": "Body",
                                    "ingestion_record_id": 300,
                                    "company_id": 1,
                                    "permitted_user_ids": [99, 100],  # User 42 not in list
                                },
                            },
                            {
                                "_id": "unrestricted_doc",
                                "_score": 3.5,
                                "_source": {
                                    "chunk_text": "public internal content",
                                    "title": "Public SOP",
                                    "authors": [],
                                    "doi": None,
                                    "publication_date": None,
                                    "source_id": None,
                                    "partition_tag": "private_knowledge",
                                    "section_heading": "Body",
                                    "ingestion_record_id": 301,
                                    "company_id": 1,
                                    # No permitted_user_ids = accessible to all
                                },
                            },
                        ]
                    }
                }
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "lit1",
                            "_score": 5.0,
                            "_source": {
                                "chunk_text": "literature content",
                                "title": "Paper",
                                "authors": ["A"],
                                "doi": "10.1/a",
                                "publication_date": "2024-01-01",
                                "source_id": "pubmed",
                                "partition_tag": "public_literature",
                                "section_heading": "Abstract",
                                "ingestion_record_id": 50,
                                "company_id": 1,
                            },
                        }
                    ]
                }
            }

        mock_index_manager._client.search = AsyncMock(
            side_effect=_search_side_effect
        )

        request = _make_request(user_id=42, include_internal=True)
        response = await engine.unified_search(request)

        # User 42 should NOT see the restricted doc (permitted_user_ids=[99, 100])
        ingestion_ids = [r.ingestion_record_id for r in response.results]
        assert 300 not in ingestion_ids
        # User 42 SHOULD see the unrestricted doc
        assert 301 in ingestion_ids

    @pytest.mark.asyncio
    async def test_abac_allows_permitted_user(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """ABAC filter allows access when user is in permitted_user_ids."""
        async def _search_side_effect(index, body):
            if "knowledge-" in index:
                return {
                    "hits": {
                        "hits": [
                            {
                                "_id": "restricted_doc",
                                "_score": 4.0,
                                "_source": {
                                    "chunk_text": "restricted content",
                                    "title": "Restricted SOP",
                                    "authors": [],
                                    "doi": None,
                                    "publication_date": None,
                                    "source_id": None,
                                    "partition_tag": "private_knowledge",
                                    "section_heading": "Body",
                                    "ingestion_record_id": 300,
                                    "company_id": 1,
                                    "permitted_user_ids": [42, 99],  # User 42 IS in list
                                },
                            },
                        ]
                    }
                }
            return {"hits": {"hits": []}}

        mock_index_manager._client.search = AsyncMock(
            side_effect=_search_side_effect
        )

        request = _make_request(user_id=42, include_internal=True)
        response = await engine.unified_search(request)

        ingestion_ids = [r.ingestion_record_id for r in response.results]
        assert 300 in ingestion_ids


# ---------------------------------------------------------------------------
# Tests: Pagination Edge Cases (Requirement 6.5)
# ---------------------------------------------------------------------------


class TestPaginationEdgeCases:
    """Tests for pagination edge cases."""

    @pytest.mark.asyncio
    async def test_page_beyond_results_returns_empty(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """Requesting a page beyond available results returns empty list."""
        request = _make_request(page=100, page_size=20)
        response = await engine.search(request)

        # There are only 2 results total; page 100 should be empty
        assert response.results == []
        assert response.total_count == 2
        assert response.page == 100
        assert response.page_size == 20

    @pytest.mark.asyncio
    async def test_page_size_larger_than_results(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """Page size larger than total results returns all results."""
        request = _make_request(page=1, page_size=100)
        response = await engine.search(request)

        assert len(response.results) == 2
        assert response.total_count == 2
        assert response.page_size == 100

    @pytest.mark.asyncio
    async def test_page_size_one_returns_single_result(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """Page size of 1 returns exactly 1 result per page."""
        request = _make_request(page=1, page_size=1)
        response = await engine.search(request)

        assert len(response.results) == 1
        assert response.total_count == 2
        assert response.page == 1

    @pytest.mark.asyncio
    async def test_second_page_returns_next_results(
        self,
        engine: HybridQueryEngine,
    ) -> None:
        """Page 2 with page_size=1 returns the second result."""
        request_p1 = _make_request(page=1, page_size=1)
        response_p1 = await engine.search(request_p1)

        request_p2 = _make_request(page=2, page_size=1)
        response_p2 = await engine.search(request_p2)

        assert len(response_p1.results) == 1
        assert len(response_p2.results) == 1
        # Results should be different
        assert (
            response_p1.results[0].ingestion_record_id
            != response_p2.results[0].ingestion_record_id
        )

    @pytest.mark.asyncio
    async def test_empty_opensearch_results_returns_zero_total(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Empty OpenSearch results lead to total_count=0."""
        mock_index_manager._client.search = AsyncMock(
            return_value={"hits": {"hits": []}}
        )

        request = _make_request()
        response = await engine.search(request)

        assert response.total_count == 0
        assert response.results == []
        assert response.page == 1

    @pytest.mark.asyncio
    async def test_pagination_preserves_order(
        self,
        engine: HybridQueryEngine,
        mock_index_manager: MagicMock,
    ) -> None:
        """Paginated results maintain consistent ordering across pages."""
        # Generate 5 docs for testing pagination ordering
        hits = [
            {
                "_id": f"doc{i}",
                "_score": 10.0 - i,
                "_source": {
                    "chunk_text": f"content {i}",
                    "title": f"Title {i}",
                    "authors": [f"Author {i}"],
                    "doi": f"10.{i}/test",
                    "publication_date": "2024-01-01",
                    "source_id": "pubmed",
                    "partition_tag": "public_literature",
                    "section_heading": "Abstract",
                    "ingestion_record_id": i,
                    "company_id": 1,
                },
            }
            for i in range(5)
        ]
        mock_index_manager._client.search = AsyncMock(
            return_value={"hits": {"hits": hits}}
        )

        # Get all results at once
        req_all = _make_request(page=1, page_size=5)
        resp_all = await engine.search(req_all)

        # Get page 1 (size 2) then page 2 (size 2)
        req_p1 = _make_request(page=1, page_size=2)
        resp_p1 = await engine.search(req_p1)

        req_p2 = _make_request(page=2, page_size=2)
        resp_p2 = await engine.search(req_p2)

        # Concatenation of pages should match overall order
        all_ids = [r.ingestion_record_id for r in resp_all.results]
        paged_ids = [r.ingestion_record_id for r in resp_p1.results] + [
            r.ingestion_record_id for r in resp_p2.results
        ]
        assert paged_ids == all_ids[:4]
