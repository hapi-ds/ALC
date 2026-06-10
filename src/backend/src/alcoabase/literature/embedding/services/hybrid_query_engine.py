"""Hybrid search combining BM25 keyword + kNN semantic with RRF fusion.

Executes dual queries against OpenSearch, merges results via reciprocal
rank fusion, applies partition filters, and handles graceful degradation.

References:
    - Requirements 6, 7, 10
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from alcoabase.literature.embedding.exceptions import SearchServiceUnavailableError

if TYPE_CHECKING:
    from alcoabase.literature.embedding.services.index_manager import (
        LiteratureIndexManager,
    )
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.model_manager import ModelManager

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HybridSearchRequest:
    """Validated search request parameters.

    Attributes:
        query: Search query text (1-1000 chars).
        company_id: Requesting company (from X-Company-Id header).
        user_id: Requesting user.
        partition_filter: 'public_literature', 'private_knowledge', or 'all'.
        semantic_weight: Float 0.0-1.0 (default 0.5).
        rrf_k: RRF k parameter (default 60).
        page: Page number (1-based, default 1).
        page_size: Results per page (1-100, default 20).
        literature_boost: Boost for literature results (default 1.0).
        internal_boost: Boost for internal results (default 1.0).
        date_range_start: Optional start date filter (ISO-8601).
        date_range_end: Optional end date filter (ISO-8601).
        source_id: Optional source filter.
        authors: Optional author filter list.
        publication_type: Optional type filter.
        include_internal: Whether to include internal docs (unified only).
    """

    query: str
    company_id: int
    user_id: int
    partition_filter: str = "all"
    semantic_weight: float = 0.5
    rrf_k: int = 60
    page: int = 1
    page_size: int = 20
    literature_boost: float = 1.0
    internal_boost: float = 1.0
    date_range_start: str | None = None
    date_range_end: str | None = None
    source_id: str | None = None
    authors: list[str] = field(default_factory=list)
    publication_type: str | None = None
    include_internal: bool = False


@dataclass
class HybridSearchResult:
    """A single search result with RRF-fused relevance score.

    Attributes:
        chunk_text: The text content of the matched chunk.
        title: Document title.
        authors: List of author names.
        doi: Digital Object Identifier (optional).
        publication_date: ISO-8601 date string (optional).
        source_id: Source adapter identifier (optional).
        relevance_score: RRF-fused relevance score (0.0-1.0).
        partition_tag: 'public_literature' or 'private_knowledge'.
        section_heading: Source section heading.
        ingestion_record_id: FK to IngestionRecord.
    """

    chunk_text: str
    title: str
    authors: list[str]
    doi: str | None
    publication_date: str | None
    source_id: str | None
    relevance_score: float
    partition_tag: str
    section_heading: str
    ingestion_record_id: int


@dataclass
class HybridSearchResponse:
    """Complete search response with metadata.

    Attributes:
        results: Paginated list of search results.
        total_count: Total number of matching results (before pagination).
        page: Current page number (1-based).
        page_size: Results per page.
        degraded_mode: True if BM25-only fallback due to vLLM unavailability.
        partial_results: True if one index was unreachable in unified search.
        unavailable_index: Name of the unreachable index (if partial).
    """

    results: list[HybridSearchResult]
    total_count: int
    page: int
    page_size: int
    degraded_mode: bool = False
    partial_results: bool = False
    unavailable_index: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid Query Engine
# ─────────────────────────────────────────────────────────────────────────────

# Internal document index naming pattern (matches KnowledgeService convention)
_INTERNAL_INDEX_PREFIX = "knowledge"


class HybridQueryEngine:
    """Executes hybrid BM25 + kNN searches with RRF fusion.

    Handles:
        - Query embedding generation via InferenceClient
        - Dual-query execution (BM25 + kNN) against OpenSearch
        - Reciprocal rank fusion scoring
        - Partition filtering and boosting
        - Graceful degradation (BM25-only fallback)
        - Unified search across literature + internal indices
    """

    def __init__(
        self,
        index_manager: LiteratureIndexManager,
        inference_client: InferenceClient,
        model_manager: ModelManager,
        model_name: str,
        default_rrf_k: int = 60,
    ) -> None:
        """Initialize with dependencies.

        Args:
            index_manager: LiteratureIndexManager for OpenSearch operations.
            inference_client: InferenceClient for vLLM embedding generation.
            model_manager: ModelManager to ensure embedding model is loaded.
            model_name: Name of the embedding model for query vectors.
            default_rrf_k: Default RRF k parameter (default 60).
        """
        self._index_manager = index_manager
        self._inference_client = inference_client
        self._model_manager = model_manager
        self._model_name = model_name
        self._default_rrf_k = default_rrf_k

    async def search(
        self,
        request: HybridSearchRequest,
    ) -> HybridSearchResponse:
        """Execute a hybrid search request.

        Steps:
            1. Generate query embedding (or fallback to BM25-only)
            2. Build BM25 query and kNN query
            3. Execute both against company index
            4. Apply RRF fusion with semantic_weight
            5. Apply pagination

        Args:
            request: Validated search parameters.

        Returns:
            HybridSearchResponse with fused results.

        Raises:
            SearchServiceUnavailableError: If OpenSearch unreachable.
        """
        degraded_mode = False
        query_vector: list[float] | None = None

        # Step 1: Generate query embedding (graceful degradation on failure)
        if request.semantic_weight > 0.0:
            query_vector = await self._generate_query_embedding(request.query)
            if query_vector is None:
                degraded_mode = True
                logger.warning(
                    "vLLM unavailable for query embedding. "
                    "Falling back to BM25-only search for company %d.",
                    request.company_id,
                )

        # Build filters dict
        filters = self._build_filters(request)

        # Step 2: Execute queries against OpenSearch
        index_name = self._index_manager._index_name(request.company_id)

        try:
            # Execute BM25 query
            bm25_query = self._build_bm25_query(
                request.query, request.company_id, filters
            )
            bm25_results = await self._execute_search(
                index_name, bm25_query, size=100
            )

            # Execute kNN query (if not degraded)
            knn_results: list[dict[str, Any]] = []
            if query_vector is not None and not degraded_mode:
                knn_query = self._build_knn_query(
                    query_vector, request.company_id, filters
                )
                knn_results = await self._execute_search(
                    index_name, knn_query, size=100
                )

        except Exception as e:
            logger.error(
                "OpenSearch query failed for company %d: %s",
                request.company_id,
                str(e),
            )
            raise SearchServiceUnavailableError(
                "Search service is temporarily unavailable.",
                company_id=request.company_id,
                index_name=index_name,
            ) from e

        # Step 3: Apply RRF fusion
        if degraded_mode or not knn_results:
            # BM25-only: use BM25 ranks as sole scoring
            fused_results = self._apply_rrf(
                bm25_results, [], request.rrf_k, 0.0
            )
        else:
            fused_results = self._apply_rrf(
                bm25_results, knn_results, request.rrf_k, request.semantic_weight
            )

        # Step 4: Paginate
        total_count = len(fused_results)
        start_idx = (request.page - 1) * request.page_size
        end_idx = start_idx + request.page_size
        paginated = fused_results[start_idx:end_idx]

        # Step 5: Convert to HybridSearchResult objects
        results = [self._to_search_result(item) for item in paginated]

        return HybridSearchResponse(
            results=results,
            total_count=total_count,
            page=request.page,
            page_size=request.page_size,
            degraded_mode=degraded_mode,
        )

    async def unified_search(
        self,
        request: HybridSearchRequest,
    ) -> HybridSearchResponse:
        """Execute unified search across literature + internal indices.

        Queries both the literature index and the internal document index,
        applies ABAC for internal docs, merges results with RRF, and
        applies partition boosting.

        Args:
            request: Search parameters with include_internal=True.

        Returns:
            HybridSearchResponse with merged results from both indices.
        """
        degraded_mode = False
        partial_results = False
        unavailable_index: str | None = None
        query_vector: list[float] | None = None

        # Generate query embedding
        if request.semantic_weight > 0.0:
            query_vector = await self._generate_query_embedding(request.query)
            if query_vector is None:
                degraded_mode = True
                logger.warning(
                    "vLLM unavailable for unified search query embedding. "
                    "Falling back to BM25-only for company %d.",
                    request.company_id,
                )

        filters = self._build_filters(request)
        literature_index = self._index_manager._index_name(request.company_id)
        internal_index = f"{_INTERNAL_INDEX_PREFIX}-{request.company_id}"

        # Query literature index
        literature_results: list[dict[str, Any]] = []
        literature_bm25: list[dict[str, Any]] = []
        literature_knn: list[dict[str, Any]] = []
        try:
            bm25_query = self._build_bm25_query(
                request.query, request.company_id, filters
            )
            literature_bm25 = await self._execute_search(
                literature_index, bm25_query, size=100
            )

            if query_vector is not None and not degraded_mode:
                knn_query = self._build_knn_query(
                    query_vector, request.company_id, filters
                )
                literature_knn = await self._execute_search(
                    literature_index, knn_query, size=100
                )

            # Apply RRF to literature results
            effective_weight = 0.0 if degraded_mode else request.semantic_weight
            literature_results = self._apply_rrf(
                literature_bm25, literature_knn, request.rrf_k, effective_weight
            )
            # Tag as public_literature if not already tagged
            for r in literature_results:
                if "partition_tag" not in r or not r.get("partition_tag"):
                    r["partition_tag"] = "public_literature"

        except Exception as e:
            logger.error(
                "Literature index query failed for company %d: %s",
                request.company_id,
                str(e),
            )
            partial_results = True
            unavailable_index = literature_index

        # Query internal index (if include_internal is True)
        internal_results: list[dict[str, Any]] = []
        internal_bm25: list[dict[str, Any]] = []
        internal_knn: list[dict[str, Any]] = []
        if request.include_internal:
            try:
                bm25_query = self._build_bm25_query(
                    request.query, request.company_id, filters
                )
                internal_bm25 = await self._execute_search(
                    internal_index, bm25_query, size=100
                )

                if query_vector is not None and not degraded_mode:
                    knn_query = self._build_knn_query(
                        query_vector, request.company_id, filters
                    )
                    internal_knn = await self._execute_search(
                        internal_index, knn_query, size=100
                    )

                # Apply RRF to internal results
                effective_weight = 0.0 if degraded_mode else request.semantic_weight
                internal_results = self._apply_rrf(
                    internal_bm25, internal_knn, request.rrf_k, effective_weight
                )
                # Tag as private_knowledge if not already tagged
                for r in internal_results:
                    if "partition_tag" not in r or not r.get("partition_tag"):
                        r["partition_tag"] = "private_knowledge"

                # Apply ABAC filtering for internal documents
                internal_results = self._apply_abac_filter(
                    internal_results, request.user_id
                )

            except Exception as e:
                logger.error(
                    "Internal index query failed for company %d: %s",
                    request.company_id,
                    str(e),
                )
                partial_results = True
                unavailable_index = internal_index

        # If both indices failed, raise
        if not literature_results and not internal_results and partial_results:
            raise SearchServiceUnavailableError(
                "Search service is temporarily unavailable.",
                company_id=request.company_id,
            )

        # Merge results from both indices with partition boosting
        merged = self._merge_with_boosting(
            literature_results=literature_results,
            internal_results=internal_results,
            literature_boost=request.literature_boost,
            internal_boost=request.internal_boost,
        )

        # Paginate
        total_count = len(merged)
        start_idx = (request.page - 1) * request.page_size
        end_idx = start_idx + request.page_size
        paginated = merged[start_idx:end_idx]

        results = [self._to_search_result(item) for item in paginated]

        return HybridSearchResponse(
            results=results,
            total_count=total_count,
            page=request.page,
            page_size=request.page_size,
            degraded_mode=degraded_mode,
            partial_results=partial_results,
            unavailable_index=unavailable_index,
        )

    # ─────────────────────────────────────────────────────────────────────
    # RRF Fusion
    # ─────────────────────────────────────────────────────────────────────

    def _apply_rrf(
        self,
        bm25_results: list[dict[str, Any]],
        knn_results: list[dict[str, Any]],
        k: int,
        semantic_weight: float,
    ) -> list[dict[str, Any]]:
        """Apply reciprocal rank fusion to merge two result lists.

        RRF score = (1-w) * 1/(k + bm25_rank) + w * 1/(k + knn_rank)

        Where w = semantic_weight and ranks are 1-based positions.
        Documents appearing in only one list get 0 contribution from
        the other list.

        Args:
            bm25_results: BM25-ranked results (list of dicts with '_id' key).
            knn_results: kNN-ranked results (list of dicts with '_id' key).
            k: RRF k parameter (default 60).
            semantic_weight: Weight for semantic score (0.0-1.0).

        Returns:
            Merged list sorted by RRF score descending, each with
            'relevance_score' field added.
        """
        # Build rank maps (1-based rank)
        bm25_rank_map: dict[str, int] = {}
        for rank, doc in enumerate(bm25_results, start=1):
            doc_id = doc.get("_id", str(rank))
            bm25_rank_map[doc_id] = rank

        knn_rank_map: dict[str, int] = {}
        for rank, doc in enumerate(knn_results, start=1):
            doc_id = doc.get("_id", str(rank))
            knn_rank_map[doc_id] = rank

        # Collect all unique doc IDs
        all_doc_ids = set(bm25_rank_map.keys()) | set(knn_rank_map.keys())

        # Build a map of doc_id to source document data
        doc_data_map: dict[str, dict[str, Any]] = {}
        for doc in bm25_results:
            doc_id = doc.get("_id", "")
            if doc_id not in doc_data_map:
                doc_data_map[doc_id] = doc
        for doc in knn_results:
            doc_id = doc.get("_id", "")
            if doc_id not in doc_data_map:
                doc_data_map[doc_id] = doc

        # Compute RRF scores
        scored_results: list[dict[str, Any]] = []
        for doc_id in all_doc_ids:
            bm25_contribution = 0.0
            knn_contribution = 0.0

            if doc_id in bm25_rank_map:
                bm25_rank = bm25_rank_map[doc_id]
                bm25_contribution = (1.0 - semantic_weight) * (
                    1.0 / (k + bm25_rank)
                )

            if doc_id in knn_rank_map:
                knn_rank = knn_rank_map[doc_id]
                knn_contribution = semantic_weight * (1.0 / (k + knn_rank))

            rrf_score = bm25_contribution + knn_contribution

            # Get the source document data
            doc = doc_data_map.get(doc_id, {})
            result = {**doc, "relevance_score": rrf_score, "_id": doc_id}
            scored_results.append(result)

        # Sort by RRF score descending
        scored_results.sort(key=lambda x: x["relevance_score"], reverse=True)

        return scored_results

    # ─────────────────────────────────────────────────────────────────────
    # Query Builders
    # ─────────────────────────────────────────────────────────────────────

    def _build_bm25_query(
        self,
        query_text: str,
        company_id: int,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """Build OpenSearch BM25 query with mandatory company_id filter.

        Searches chunk_text and title fields using multi_match.
        Always includes a bool filter for company_id (defense-in-depth).

        Args:
            query_text: User's search query.
            company_id: Tenant scope (mandatory filter).
            filters: Additional filters (partition_tag, date_range, etc.).

        Returns:
            OpenSearch query DSL dict.
        """
        # Mandatory company_id filter (defense-in-depth)
        filter_clauses: list[dict[str, Any]] = [
            {"term": {"company_id": company_id}}
        ]

        # Add optional filters
        filter_clauses.extend(self._build_filter_clauses(filters))

        query: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query_text,
                                "fields": ["chunk_text", "title"],
                                "type": "best_fields",
                            }
                        }
                    ],
                    "filter": filter_clauses,
                }
            }
        }

        return query

    def _build_knn_query(
        self,
        query_vector: list[float],
        company_id: int,
        filters: dict[str, Any],
        k: int = 100,
    ) -> dict[str, Any]:
        """Build OpenSearch kNN query with mandatory company_id filter.

        Args:
            query_vector: Query embedding vector.
            company_id: Tenant scope (mandatory filter).
            filters: Additional filters.
            k: Number of nearest neighbors to retrieve.

        Returns:
            OpenSearch kNN query DSL dict.
        """
        # Mandatory company_id filter (defense-in-depth)
        filter_clauses: list[dict[str, Any]] = [
            {"term": {"company_id": company_id}}
        ]

        # Add optional filters
        filter_clauses.extend(self._build_filter_clauses(filters))

        query: dict[str, Any] = {
            "size": k,
            "query": {
                "knn": {
                    "embedding_vector": {
                        "vector": query_vector,
                        "k": k,
                        "filter": {
                            "bool": {
                                "filter": filter_clauses,
                            }
                        },
                    }
                }
            },
        }

        return query

    # ─────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _generate_query_embedding(
        self,
        query: str,
    ) -> list[float] | None:
        """Generate an embedding vector for the query text.

        Returns None if vLLM is unavailable (graceful degradation).

        Args:
            query: User's search query text.

        Returns:
            Embedding vector, or None if generation failed.
        """
        try:
            from alcoabase.services.model_manager import ModelRole

            await self._model_manager.ensure_model(ModelRole.EMBEDDING)
            embeddings = await self._inference_client.create_embeddings(
                model=self._model_name,
                inputs=[query],
            )
            if embeddings and len(embeddings) > 0:
                return embeddings[0]
            return None
        except Exception as e:
            logger.warning(
                "Failed to generate query embedding: %s. "
                "Falling back to BM25-only search.",
                str(e),
            )
            return None

    async def _execute_search(
        self,
        index_name: str,
        query: dict[str, Any],
        size: int = 100,
    ) -> list[dict[str, Any]]:
        """Execute a search query against OpenSearch.

        Args:
            index_name: Target OpenSearch index.
            query: Query DSL dict.
            size: Maximum number of results to return.

        Returns:
            List of hit documents with _id and _source fields flattened.
        """
        # Add size to query if not already present
        search_body = {**query}
        if "size" not in search_body:
            search_body["size"] = size

        response = await self._index_manager._client.search(
            index=index_name,
            body=search_body,
        )

        hits = response.get("hits", {}).get("hits", [])
        results: list[dict[str, Any]] = []
        for hit in hits:
            doc = {**hit.get("_source", {})}
            doc["_id"] = hit.get("_id", "")
            doc["_score"] = hit.get("_score", 0.0)
            results.append(doc)

        return results

    def _build_filters(self, request: HybridSearchRequest) -> dict[str, Any]:
        """Extract filter parameters from a search request.

        Args:
            request: The search request.

        Returns:
            Dict of filter keys to their values.
        """
        filters: dict[str, Any] = {}

        if request.partition_filter and request.partition_filter != "all":
            filters["partition_tag"] = request.partition_filter

        if request.date_range_start or request.date_range_end:
            filters["date_range"] = {
                "start": request.date_range_start,
                "end": request.date_range_end,
            }

        if request.source_id:
            filters["source_id"] = request.source_id

        if request.authors:
            filters["authors"] = request.authors

        if request.publication_type:
            filters["publication_type"] = request.publication_type

        return filters

    def _build_filter_clauses(
        self, filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Convert filter dict to OpenSearch bool filter clauses.

        Args:
            filters: Dict of filter keys to values.

        Returns:
            List of OpenSearch filter clause dicts.
        """
        clauses: list[dict[str, Any]] = []

        if "partition_tag" in filters:
            clauses.append({"term": {"partition_tag": filters["partition_tag"]}})

        if "date_range" in filters:
            date_range = filters["date_range"]
            range_clause: dict[str, Any] = {}
            if date_range.get("start"):
                range_clause["gte"] = date_range["start"]
            if date_range.get("end"):
                range_clause["lte"] = date_range["end"]
            if range_clause:
                clauses.append({"range": {"publication_date": range_clause}})

        if "source_id" in filters:
            clauses.append({"term": {"source_id": filters["source_id"]}})

        if "authors" in filters:
            clauses.append({"terms": {"authors": filters["authors"]}})

        if "publication_type" in filters:
            clauses.append(
                {"term": {"publication_type": filters["publication_type"]}}
            )

        return clauses

    def _to_search_result(self, doc: dict[str, Any]) -> HybridSearchResult:
        """Convert a raw document dict to a HybridSearchResult.

        Args:
            doc: Raw document dict from OpenSearch with relevance_score.

        Returns:
            HybridSearchResult dataclass.
        """
        return HybridSearchResult(
            chunk_text=doc.get("chunk_text", ""),
            title=doc.get("title", ""),
            authors=doc.get("authors", []),
            doi=doc.get("doi"),
            publication_date=doc.get("publication_date"),
            source_id=doc.get("source_id"),
            relevance_score=doc.get("relevance_score", 0.0),
            partition_tag=doc.get("partition_tag", "public_literature"),
            section_heading=doc.get("section_heading", ""),
            ingestion_record_id=doc.get("ingestion_record_id", 0),
        )

    def _apply_abac_filter(
        self,
        results: list[dict[str, Any]],
        user_id: int,
    ) -> list[dict[str, Any]]:
        """Apply attribute-based access control filtering for internal docs.

        Filters internal documents based on the user's access permissions.
        If a document has permitted_user_ids, only users in that list can
        see it. Documents without explicit access restrictions are visible
        to all company members.

        Args:
            results: List of internal document results.
            user_id: Requesting user's ID.

        Returns:
            Filtered list respecting ABAC permissions.
        """
        filtered: list[dict[str, Any]] = []
        for doc in results:
            permitted_users = doc.get("permitted_user_ids")
            if permitted_users is None:
                # No explicit restriction - visible to all company members
                filtered.append(doc)
            elif user_id in permitted_users:
                filtered.append(doc)
            else:
                logger.debug(
                    "ABAC filter: user %d denied access to doc %s",
                    user_id,
                    doc.get("_id", "unknown"),
                )
        return filtered

    def _merge_with_boosting(
        self,
        literature_results: list[dict[str, Any]],
        internal_results: list[dict[str, Any]],
        literature_boost: float,
        internal_boost: float,
    ) -> list[dict[str, Any]]:
        """Merge results from literature and internal indices with boosting.

        Applies boost factors to RRF scores before merging and re-sorting.

        Args:
            literature_results: RRF-scored results from literature index.
            internal_results: RRF-scored results from internal index.
            literature_boost: Multiplier for literature scores (0.1-10.0).
            internal_boost: Multiplier for internal scores (0.1-10.0).

        Returns:
            Merged list sorted by boosted relevance score descending.
        """
        merged: list[dict[str, Any]] = []

        for doc in literature_results:
            boosted_doc = {**doc}
            boosted_doc["relevance_score"] = (
                doc.get("relevance_score", 0.0) * literature_boost
            )
            merged.append(boosted_doc)

        for doc in internal_results:
            boosted_doc = {**doc}
            boosted_doc["relevance_score"] = (
                doc.get("relevance_score", 0.0) * internal_boost
            )
            merged.append(boosted_doc)

        # Sort by boosted relevance score descending
        merged.sort(key=lambda x: x.get("relevance_score", 0.0), reverse=True)

        return merged
