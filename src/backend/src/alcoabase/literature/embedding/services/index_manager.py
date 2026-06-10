"""OpenSearch operations for literature embedding indices.

Manages index lifecycle (create, delete, template), bulk indexing,
deletion, and raw query execution. Enforces company isolation at
every operation.

References:
    - Requirements 3, 4, 5, 12, 14
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from alcoabase.literature.embedding.exceptions import (
    IndexCreationError,
    IndexingUnavailableError,
    PartitionTagUpdateError,
    TenantIsolationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexedChunk:
    """A chunk document to be stored in OpenSearch.

    Attributes:
        embedding_vector: Float32 embedding vector.
        chunk_text: Raw text of the chunk.
        title: Document title.
        abstract_snippet: First 200 chars of abstract.
        authors: List of author names.
        doi: Digital Object Identifier.
        publication_date: ISO-8601 date string.
        source_id: Source adapter name.
        external_id: Source-specific identifier.
        ingestion_record_id: FK to IngestionRecord.
        company_id: Tenant identifier.
        partition_tag: 'public_literature' or 'private_knowledge'.
        section_heading: Source section heading.
        chunk_index: Position in document chunk sequence.
    """

    embedding_vector: list[float]
    chunk_text: str
    title: str
    abstract_snippet: str
    authors: list[str]
    doi: str | None
    publication_date: str | None
    source_id: str | None
    external_id: str | None
    ingestion_record_id: int
    company_id: int
    partition_tag: str
    section_heading: str
    chunk_index: int


class LiteratureIndexManager:
    """Manages OpenSearch indices for literature embeddings.

    One index per company: literature-embeddings-{company_id}.
    Uses HNSW for kNN with cosine similarity.

    Responsibilities:
        - Create/ensure per-company indices with proper mapping
        - Apply index templates for pattern matching
        - Bulk index embedding chunks with tenant isolation validation
        - Delete chunks by ingestion_record_id
        - Atomically update partition tags with rollback on failure
        - Delete entire company indices on company removal
        - Report index health and statistics
    """

    INDEX_PREFIX = "literature-embeddings"
    TEMPLATE_NAME = "literature-embeddings-template"

    # Retry configuration
    _INDEX_CREATION_MAX_RETRIES = 3
    _INDEX_CREATION_RETRY_INTERVAL_S = 10
    _INDEX_DELETION_MAX_RETRIES = 3
    _INDEX_DELETION_RETRY_INTERVAL_S = 30

    def __init__(
        self,
        opensearch_client: Any,
        embedding_dimension: int = 1024,
        shards: int = 1,
        replicas: int = 1,
        hnsw_ef_construction: int = 256,
        hnsw_m: int = 16,
    ) -> None:
        """Initialize with OpenSearch client and index settings.

        Args:
            opensearch_client: An opensearch-py AsyncOpenSearch client instance.
            embedding_dimension: Dimension of embedding vectors (default 1024).
            shards: Number of primary shards per index (default 1).
            replicas: Number of replica shards per index (default 1).
            hnsw_ef_construction: HNSW ef_construction parameter (default 256).
            hnsw_m: HNSW m parameter (default 16).
        """
        self._client = opensearch_client
        self._embedding_dimension = embedding_dimension
        self._shards = shards
        self._replicas = replicas
        self._hnsw_ef_construction = hnsw_ef_construction
        self._hnsw_m = hnsw_m

    def _index_name(self, company_id: int) -> str:
        """Construct index name for a company.

        Returns:
            'literature-embeddings-{company_id}'
        """
        return f"{self.INDEX_PREFIX}-{company_id}"

    def _build_index_mapping(self) -> dict[str, Any]:
        """Build the OpenSearch index mapping with all fields.

        Configures:
            - kNN vector field with HNSW algorithm, cosinesimil space, nmslib engine
            - BM25-analyzed text fields (chunk_text, title)
            - Keyword metadata fields (authors, doi, source_id, etc.)
            - Date fields (publication_date, created_at)
            - Integer fields (ingestion_record_id, company_id, chunk_index)

        Returns:
            Complete mapping dict for index creation.
        """
        return {
            "settings": {
                "index": {
                    "knn": True,
                    "number_of_shards": self._shards,
                    "number_of_replicas": self._replicas,
                }
            },
            "mappings": {
                "properties": {
                    "embedding_vector": {
                        "type": "knn_vector",
                        "dimension": self._embedding_dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": self._hnsw_ef_construction,
                                "m": self._hnsw_m,
                            },
                        },
                    },
                    "chunk_text": {"type": "text", "analyzer": "standard"},
                    "title": {"type": "text", "analyzer": "standard"},
                    "abstract_snippet": {"type": "text"},
                    "authors": {"type": "keyword"},
                    "doi": {"type": "keyword"},
                    "publication_date": {"type": "date"},
                    "source_id": {"type": "keyword"},
                    "external_id": {"type": "keyword"},
                    "ingestion_record_id": {"type": "integer"},
                    "company_id": {"type": "integer"},
                    "partition_tag": {"type": "keyword"},
                    "section_heading": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                    "created_at": {"type": "date"},
                }
            },
        }

    async def ensure_index_exists(self, company_id: int) -> None:
        """Create company index if it doesn't exist.

        Applies the index template mapping with kNN vector field,
        BM25 text fields, and metadata fields. Skips creation if
        the index already exists.

        Retries up to 3 times with 10s intervals on failure.

        Args:
            company_id: Company whose index to ensure.

        Raises:
            IndexCreationError: If all retries exhausted.
        """
        index_name = self._index_name(company_id)
        last_error: Exception | None = None

        for attempt in range(1, self._INDEX_CREATION_MAX_RETRIES + 1):
            try:
                exists = await self._client.indices.exists(index=index_name)
                if exists:
                    logger.debug(
                        "Index %s already exists, skipping creation.", index_name
                    )
                    return

                mapping = self._build_index_mapping()
                await self._client.indices.create(
                    index=index_name,
                    body=mapping,
                )
                logger.info(
                    "Created index %s for company %d.", index_name, company_id
                )
                return

            except Exception as e:
                last_error = e
                logger.warning(
                    "Index creation attempt %d/%d failed for %s: %s",
                    attempt,
                    self._INDEX_CREATION_MAX_RETRIES,
                    index_name,
                    str(e),
                )
                if attempt < self._INDEX_CREATION_MAX_RETRIES:
                    await asyncio.sleep(self._INDEX_CREATION_RETRY_INTERVAL_S)

        raise IndexCreationError(
            f"Failed to create index {index_name} after "
            f"{self._INDEX_CREATION_MAX_RETRIES} retries: {last_error}",
            company_id=company_id,
            index_name=index_name,
            retry_count=self._INDEX_CREATION_MAX_RETRIES,
        )

    async def apply_index_template(self) -> None:
        """Create/update the index template for literature-embeddings-* pattern.

        Configures the template so that any new index matching the
        `literature-embeddings-*` pattern automatically gets the correct
        mapping with kNN vector fields, BM25 text fields, keyword metadata,
        and date fields.
        """
        mapping = self._build_index_mapping()
        template_body = {
            "index_patterns": [f"{self.INDEX_PREFIX}-*"],
            "template": {
                "settings": mapping["settings"],
                "mappings": mapping["mappings"],
            },
            "priority": 100,
        }

        await self._client.indices.put_index_template(
            name=self.TEMPLATE_NAME,
            body=template_body,
        )
        logger.info(
            "Applied index template %s for pattern %s-*.",
            self.TEMPLATE_NAME,
            self.INDEX_PREFIX,
        )

    async def bulk_index_chunks(
        self,
        company_id: int,
        chunks: list[IndexedChunk],
    ) -> int:
        """Bulk index chunks into a company's literature index.

        Validates that every chunk's company_id matches the target company_id
        before performing any write operation (tenant isolation).

        Args:
            company_id: Target company index.
            chunks: List of IndexedChunk documents to index.

        Returns:
            Number of chunks successfully indexed.

        Raises:
            TenantIsolationError: If any chunk's company_id doesn't match.
            IndexingUnavailableError: If OpenSearch is unreachable after retries.
        """
        if not chunks:
            return 0

        # Validate tenant isolation before any write
        for chunk in chunks:
            if chunk.company_id != company_id:
                raise TenantIsolationError(
                    f"Chunk company_id {chunk.company_id} does not match "
                    f"target company_id {company_id}. Tenant isolation violated.",
                    company_id=company_id,
                    target_company_id=chunk.company_id,
                    operation="bulk_index",
                )

        index_name = self._index_name(company_id)

        # Ensure the index exists before indexing
        await self.ensure_index_exists(company_id)

        # Build bulk request body
        now = datetime.now(timezone.utc).isoformat()
        bulk_body: list[dict[str, Any]] = []
        for chunk in chunks:
            bulk_body.append({"index": {"_index": index_name}})
            bulk_body.append(
                {
                    "embedding_vector": chunk.embedding_vector,
                    "chunk_text": chunk.chunk_text,
                    "title": chunk.title,
                    "abstract_snippet": chunk.abstract_snippet,
                    "authors": chunk.authors,
                    "doi": chunk.doi,
                    "publication_date": chunk.publication_date,
                    "source_id": chunk.source_id,
                    "external_id": chunk.external_id,
                    "ingestion_record_id": chunk.ingestion_record_id,
                    "company_id": chunk.company_id,
                    "partition_tag": chunk.partition_tag,
                    "section_heading": chunk.section_heading,
                    "chunk_index": chunk.chunk_index,
                    "created_at": now,
                }
            )

        # Execute bulk index with retries
        last_error: Exception | None = None
        for attempt in range(1, self._INDEX_CREATION_MAX_RETRIES + 1):
            try:
                response = await self._client.bulk(body=bulk_body, refresh="wait_for")

                if response.get("errors"):
                    # Count successful items
                    successful = sum(
                        1
                        for item in response.get("items", [])
                        if item.get("index", {}).get("status") in (200, 201)
                    )
                    failed = len(chunks) - successful
                    if failed > 0:
                        logger.warning(
                            "Bulk index to %s had %d failures out of %d chunks.",
                            index_name,
                            failed,
                            len(chunks),
                        )
                    return successful

                return len(chunks)

            except Exception as e:
                last_error = e
                logger.warning(
                    "Bulk index attempt %d/%d failed for %s: %s",
                    attempt,
                    self._INDEX_CREATION_MAX_RETRIES,
                    index_name,
                    str(e),
                )
                if attempt < self._INDEX_CREATION_MAX_RETRIES:
                    await asyncio.sleep(self._INDEX_CREATION_RETRY_INTERVAL_S)

        raise IndexingUnavailableError(
            f"OpenSearch unreachable for bulk indexing to {index_name} "
            f"after {self._INDEX_CREATION_MAX_RETRIES} retries: {last_error}",
            company_id=company_id,
            index_name=index_name,
            retry_count=self._INDEX_CREATION_MAX_RETRIES,
        )

    async def delete_record_chunks(
        self,
        company_id: int,
        ingestion_record_id: int,
    ) -> int:
        """Delete all chunks belonging to a specific IngestionRecord.

        Uses delete-by-query with ingestion_record_id filter, scoped
        to the company's index for tenant isolation.

        Args:
            company_id: Company scope.
            ingestion_record_id: Record whose chunks to delete.

        Returns:
            Number of chunks deleted.
        """
        index_name = self._index_name(company_id)

        try:
            response = await self._client.delete_by_query(
                index=index_name,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "term": {
                                        "ingestion_record_id": ingestion_record_id
                                    }
                                },
                                {"term": {"company_id": company_id}},
                            ]
                        }
                    }
                },
                refresh=True,
            )
            deleted = response.get("deleted", 0)
            logger.info(
                "Deleted %d chunks for record %d from index %s.",
                deleted,
                ingestion_record_id,
                index_name,
            )
            return deleted

        except Exception as e:
            logger.error(
                "Failed to delete chunks for record %d from %s: %s",
                ingestion_record_id,
                index_name,
                str(e),
            )
            return 0

    async def update_partition_tags(
        self,
        company_id: int,
        ingestion_record_id: int,
        new_tag: str,
    ) -> int:
        """Atomically update partition_tag for all chunks of a record.

        Uses update-by-query with a scripted field update. Verifies that
        the expected number of documents were updated. On partial failure,
        rolls back all affected chunks to their original tag value.

        Args:
            company_id: Company scope.
            ingestion_record_id: Target record.
            new_tag: New partition_tag value ('public_literature' or 'private_knowledge').

        Returns:
            Number of chunks updated.

        Raises:
            PartitionTagUpdateError: If update fails or is partial.
        """
        index_name = self._index_name(company_id)

        # First, count how many chunks exist for this record
        try:
            count_response = await self._client.count(
                index=index_name,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "term": {
                                        "ingestion_record_id": ingestion_record_id
                                    }
                                },
                                {"term": {"company_id": company_id}},
                            ]
                        }
                    }
                },
            )
            expected_count = count_response.get("count", 0)
        except Exception as e:
            raise PartitionTagUpdateError(
                f"Failed to count chunks for record {ingestion_record_id}: {e}",
                company_id=company_id,
                record_id=ingestion_record_id,
                target_tag=new_tag,
            ) from e

        if expected_count == 0:
            return 0

        # Determine the original tag by reading one document
        try:
            search_response = await self._client.search(
                index=index_name,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "term": {
                                        "ingestion_record_id": ingestion_record_id
                                    }
                                },
                                {"term": {"company_id": company_id}},
                            ]
                        }
                    },
                    "size": 1,
                    "_source": ["partition_tag"],
                },
            )
            hits = search_response.get("hits", {}).get("hits", [])
            original_tag = (
                hits[0]["_source"]["partition_tag"] if hits else "public_literature"
            )
        except Exception as e:
            raise PartitionTagUpdateError(
                f"Failed to determine original tag for record "
                f"{ingestion_record_id}: {e}",
                company_id=company_id,
                record_id=ingestion_record_id,
                target_tag=new_tag,
            ) from e

        # Perform the scripted update-by-query
        try:
            update_response = await self._client.update_by_query(
                index=index_name,
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "term": {
                                        "ingestion_record_id": ingestion_record_id
                                    }
                                },
                                {"term": {"company_id": company_id}},
                            ]
                        }
                    },
                    "script": {
                        "source": "ctx._source.partition_tag = params.new_tag",
                        "lang": "painless",
                        "params": {"new_tag": new_tag},
                    },
                },
                refresh=True,
            )
            actual_updates = update_response.get("updated", 0)

        except Exception as e:
            raise PartitionTagUpdateError(
                f"Update-by-query failed for record {ingestion_record_id}: {e}",
                company_id=company_id,
                record_id=ingestion_record_id,
                expected_updates=expected_count,
                actual_updates=0,
                original_tag=original_tag,
                target_tag=new_tag,
            ) from e

        # Check for partial failure and rollback if needed
        if actual_updates != expected_count:
            logger.warning(
                "Partial update detected for record %d in %s: "
                "expected %d, got %d. Rolling back.",
                ingestion_record_id,
                index_name,
                expected_count,
                actual_updates,
            )

            # Rollback: revert to original tag
            try:
                await self._client.update_by_query(
                    index=index_name,
                    body={
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "term": {
                                            "ingestion_record_id": ingestion_record_id
                                        }
                                    },
                                    {"term": {"company_id": company_id}},
                                ]
                            }
                        },
                        "script": {
                            "source": "ctx._source.partition_tag = params.original_tag",
                            "lang": "painless",
                            "params": {"original_tag": original_tag},
                        },
                    },
                    refresh=True,
                )
            except Exception as rollback_error:
                logger.error(
                    "Rollback failed for record %d in %s: %s",
                    ingestion_record_id,
                    index_name,
                    str(rollback_error),
                )

            raise PartitionTagUpdateError(
                f"Partial partition tag update for record {ingestion_record_id}: "
                f"expected {expected_count} updates, got {actual_updates}. "
                f"Rollback executed.",
                company_id=company_id,
                record_id=ingestion_record_id,
                expected_updates=expected_count,
                actual_updates=actual_updates,
                original_tag=original_tag,
                target_tag=new_tag,
            )

        logger.info(
            "Updated partition_tag to '%s' for %d chunks of record %d in %s.",
            new_tag,
            actual_updates,
            ingestion_record_id,
            index_name,
        )
        return actual_updates

    async def delete_company_index(self, company_id: int) -> bool:
        """Delete entire company index on company removal.

        Retries 3 times with 30s intervals if OpenSearch is unavailable.

        Args:
            company_id: Company whose index to delete.

        Returns:
            True if deletion succeeded or index did not exist.
        """
        index_name = self._index_name(company_id)
        last_error: Exception | None = None

        for attempt in range(1, self._INDEX_DELETION_MAX_RETRIES + 1):
            try:
                exists = await self._client.indices.exists(index=index_name)
                if not exists:
                    logger.info(
                        "Index %s does not exist, nothing to delete.", index_name
                    )
                    return True

                await self._client.indices.delete(index=index_name)
                logger.info(
                    "Deleted index %s for company %d.", index_name, company_id
                )
                return True

            except Exception as e:
                last_error = e
                logger.warning(
                    "Index deletion attempt %d/%d failed for %s: %s",
                    attempt,
                    self._INDEX_DELETION_MAX_RETRIES,
                    index_name,
                    str(e),
                )
                if attempt < self._INDEX_DELETION_MAX_RETRIES:
                    await asyncio.sleep(self._INDEX_DELETION_RETRY_INTERVAL_S)

        logger.error(
            "Failed to delete index %s after %d retries. "
            "Manual cleanup required. Last error: %s",
            index_name,
            self._INDEX_DELETION_MAX_RETRIES,
            str(last_error),
        )
        return False

    async def get_index_stats(self, company_id: int) -> dict[str, Any]:
        """Get index health, document count, size for a company.

        Returns:
            Dict with:
                - health: 'green', 'yellow', 'red', or 'unavailable'
                - doc_count: Number of documents in the index
                - size_bytes: Index size in bytes
                - last_indexing_timestamp: ISO-8601 timestamp of latest doc
        """
        index_name = self._index_name(company_id)

        try:
            exists = await self._client.indices.exists(index=index_name)
            if not exists:
                return {
                    "health": "unavailable",
                    "doc_count": 0,
                    "size_bytes": 0,
                    "last_indexing_timestamp": None,
                }

            # Get index stats
            stats_response = await self._client.indices.stats(index=index_name)
            index_stats = stats_response.get("indices", {}).get(index_name, {})
            primaries = index_stats.get("primaries", {})
            doc_count = primaries.get("docs", {}).get("count", 0)
            size_bytes = primaries.get("store", {}).get("size_in_bytes", 0)

            # Get cluster health for this index
            health_response = await self._client.cluster.health(index=index_name)
            health = health_response.get("status", "unavailable")

            # Get last indexing timestamp from the most recent document
            last_indexing_timestamp: str | None = None
            if doc_count > 0:
                try:
                    search_response = await self._client.search(
                        index=index_name,
                        body={
                            "size": 1,
                            "sort": [{"created_at": {"order": "desc"}}],
                            "_source": ["created_at"],
                        },
                    )
                    hits = search_response.get("hits", {}).get("hits", [])
                    if hits:
                        last_indexing_timestamp = hits[0]["_source"].get("created_at")
                except Exception:
                    # Non-critical: timestamp lookup failure doesn't block stats
                    pass

            return {
                "health": health,
                "doc_count": doc_count,
                "size_bytes": size_bytes,
                "last_indexing_timestamp": last_indexing_timestamp,
            }

        except Exception as e:
            logger.error(
                "Failed to get index stats for %s: %s", index_name, str(e)
            )
            return {
                "health": "unavailable",
                "doc_count": 0,
                "size_bytes": 0,
                "last_indexing_timestamp": None,
            }
