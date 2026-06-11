# Implementation Plan: High-Dimensional Embedding Generation & Hybrid Indexing (Phase 9.3)

## Overview

This plan implements the embedding generation pipeline, hybrid search engine, and supporting infrastructure for Phase 9.3. Tasks are ordered by dependency: config/models/schemas first, then services, API routers, Celery tasks, and finally tests. Each task builds incrementally on previous work, ensuring no orphaned or disconnected code.

## Tasks

- [x] 1. Configuration, models, and schemas
  - [x] 1.1 Extend config.py with Phase 9.3 environment settings
    - Add `literature_index_shards`, `literature_index_replicas`, `literature_hnsw_ef_construction`, `literature_hnsw_m`, `literature_rrf_k`, `literature_embedding_queue`, `reindex_batch_size` fields to the Settings class in `src/backend/src/alcoabase/config.py`
    - Use Pydantic Field with aliases matching `ALC_LITERATURE_INDEX_SHARDS`, `ALC_LITERATURE_INDEX_REPLICAS`, etc.
    - Add startup validation: refuse to start if `ALC_OPENSEARCH_URL` or `MODEL_EMBEDDING_NAME` are missing
    - Log resolved config values at INFO on startup (redact credentials from OpenSearch URL)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10_

  - [x] 1.2 Create EmbeddingConfiguration SQLAlchemy model
    - Create `src/backend/src/alcoabase/literature/embedding/models/__init__.py` and `embedding_config.py`
    - Define `EmbeddingConfiguration` with fields: `id`, `company_id` (FK, unique), `chunk_size_tokens` (128–2048, default 512), `chunk_overlap_tokens` (0–256, default 50), `auto_embed_on_ingest` (default True), `embed_abstract_only` (default False), `max_chunks_per_document` (1–5000, default 500)
    - Include `AuditMixin` and `__versioned__ = {}` for SQLAlchemy-Continuum
    - _Requirements: 9.1_

  - [x] 1.3 Create ReindexJob SQLAlchemy model
    - Create `src/backend/src/alcoabase/literature/embedding/models/reindex_job.py`
    - Define `ReindexJob` with fields: `id`, `task_id` (UUID string, unique, indexed), `company_id` (FK, indexed), `status` (queued|in_progress|completed|failed|cancelled), `total_records`, `total_batches`, `current_batch`, `records_processed`, `records_failed`, `started_at`, `updated_at`, `cancelled_by`, `cancel_reason`
    - _Requirements: 8.3_

  - [x] 1.4 Create Alembic migration for new models
    - Generate migration adding `literature_embedding_configurations` and `literature_reindex_jobs` tables
    - Include unique constraint on `company_id` for embedding config
    - Include index on `task_id` and `company_id` for reindex jobs
    - _Requirements: 9.1, 8.3_

  - [x] 1.5 Create Pydantic schemas for search, indexing, and configuration
    - Create `src/backend/src/alcoabase/literature/embedding/schemas/__init__.py`
    - Create `search.py`: `HybridSearchRequestSchema` (query 1–1000 chars, partition_filter, semantic_weight 0.0–1.0, rrf_k, page, page_size 1–100, literature_boost 0.1–10.0, internal_boost 0.1–10.0, date_range, source_id, authors, publication_type, include_internal), `HybridSearchResultSchema`, `HybridSearchResponseSchema`
    - Create `indexing.py`: `ReindexRequestSchema` (state filter, record_ids), `ReindexProgressSchema`, `IndexStatusSchema`
    - Create `configuration.py`: `EmbeddingConfigurationSchema` (with Field validators for ranges), `EmbeddingConfigurationUpdateSchema`
    - _Requirements: 10.1, 10.2, 10.4, 10.5, 10.6, 6.5, 6.6_

  - [x] 1.6 Create embedding-specific exception classes
    - Create `src/backend/src/alcoabase/literature/embedding/exceptions.py`
    - Define: `EmbeddingDimensionMismatchError`, `EmbeddingGenerationError`, `IndexingUnavailableError`, `IndexCreationError`, `TenantIsolationError`, `PartitionTagUpdateError`, `ReindexAlreadyActiveError`, `SearchServiceUnavailableError`
    - _Requirements: 12.1, 12.2, 12.6, 12.7_

- [x] 2. Checkpoint - Ensure models and schemas compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement ChunkingPipeline service
  - [x] 3.1 Implement ChunkingPipeline class
    - Create `src/backend/src/alcoabase/literature/embedding/services/__init__.py` and `chunking_pipeline.py`
    - Implement `ContentChunk` frozen dataclass with `text`, `chunk_index`, `section_heading`, `source_field`
    - Implement `ChunkingPipeline.__init__` with `chunk_size_tokens`, `chunk_overlap_tokens`, `max_context_tokens` params
    - Implement `chunk_structured_content()`: process abstract first, then body sections; respect section boundaries; truncate to `max_chunks`
    - Implement `chunk_abstract()` for abstract-only embedding
    - Implement `_prepend_context()`: truncate combined title+heading to 64 tokens at word boundary
    - Implement `_split_at_section_boundaries()`: split on double-newlines or heading patterns
    - Implement `_split_at_sentence_boundary()`: split at nearest sentence boundary (. ? ! + whitespace), fallback to word boundary
    - Reuse `KnowledgeService.chunk_text()` logic for core token splitting with overlap
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 1.3_

  - [x] 3.2 Write property test: Chunking token limit and overlap (Property 1)
    - **Property 1: Chunking token limit and overlap**
    - Use Hypothesis to generate random text inputs and chunk_size (128–2048), overlap (0–256 where overlap < chunk_size)
    - Assert every chunk has ≤ chunk_size whitespace-delimited tokens
    - Assert consecutive chunks share exactly overlap tokens at boundaries
    - **Validates: Requirements 1.3, 2.1**

  - [x] 3.3 Write property test: Chunking completeness round-trip (Property 2)
    - **Property 2: Round trip consistency**
    - Use Hypothesis to generate random text inputs
    - Assert concatenation of unique (non-overlapping) portions reconstructs original without omission or reordering
    - **Validates: Requirements 2.7**

  - [x] 3.4 Write property test: Non-empty input produces chunks (Property 3)
    - **Property 3: Non-empty input produces chunks; whitespace produces none**
    - Generate strings with ≥1 non-whitespace char → assert ≥1 chunk
    - Generate whitespace-only or empty strings → assert 0 chunks
    - **Validates: Requirements 2.6**

  - [x] 3.5 Write property test: Context prepending bounded at 64 tokens (Property 4)
    - **Property 4: Context prepending bounded at 64 tokens**
    - Generate random title and section_heading strings
    - Assert prepended context ≤ 64 whitespace-delimited tokens
    - Assert truncation happens at word boundary
    - **Validates: Requirements 2.5**

- [x] 4. Implement LiteratureIndexManager service
  - [x] 4.1 Implement LiteratureIndexManager class
    - Create `src/backend/src/alcoabase/literature/embedding/services/index_manager.py`
    - Implement `IndexedChunk` frozen dataclass
    - Implement `__init__` with opensearch_client, embedding_dimension, shards, replicas, hnsw params
    - Implement `_index_name(company_id)` → `literature-embeddings-{company_id}`
    - Implement `_build_index_mapping()` with kNN vector field (HNSW, cosinesimil, nmslib), BM25 text fields, keyword/date metadata
    - Implement `ensure_index_exists()` with 3 retries at 10s intervals
    - Implement `apply_index_template()` for `literature-embeddings-*` pattern
    - Implement `bulk_index_chunks()` with company_id validation before write
    - Implement `delete_record_chunks()` using delete-by-query on `ingestion_record_id`
    - Implement `update_partition_tags()` with scripted update-by-query and rollback on partial failure
    - Implement `delete_company_index()` with 3 retries at 30s intervals
    - Implement `get_index_stats()` returning health, doc_count, size_bytes, last_indexing_timestamp
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.4, 4.5, 5.6, 5.7, 12.2, 12.4, 12.5, 14.2_

  - [x] 4.2 Write property test: Tenant isolation on indexing and search (Property 5)
    - **Property 5: Tenant isolation on indexing and search**
    - Generate random company_id values
    - Assert index name is exactly `literature-embeddings-{company_id}`
    - Assert query construction includes mandatory boolean filter for company_id
    - Mock OpenSearch client to verify query structure
    - **Validates: Requirements 4.1, 4.2, 4.4, 4.5**

  - [x] 4.3 Write property test: Source-based partition tagging (Property 6)
    - **Property 6: Source-based partition tagging**
    - Assert chunks from literature pipeline get `public_literature`
    - Assert chunks from internal uploads get `private_knowledge`
    - **Validates: Requirements 5.1, 5.2**

  - [x] 4.4 Write property test: Deletion scoping by record_id (Property 12)
    - **Property 12: Deletion scoping by record_id**
    - Generate sets of indexed records with different record_ids
    - Assert deleting one record_id removes only that record's chunks
    - Mock OpenSearch to verify delete-by-query filter
    - **Validates: Requirements 12.5**

- [x] 5. Implement HybridQueryEngine service
  - [x] 5.1 Implement HybridQueryEngine class
    - Create `src/backend/src/alcoabase/literature/embedding/services/hybrid_query_engine.py`
    - Implement `HybridSearchRequest`, `HybridSearchResult`, `HybridSearchResponse` dataclasses
    - Implement `__init__` with index_manager, inference_client, model_manager, model_name, default_rrf_k
    - Implement `search()`: generate query embedding → build BM25 + kNN queries → execute → apply RRF → paginate
    - Implement `unified_search()`: query both literature + internal indices → merge with RRF → apply ABAC for internal docs
    - Implement `_apply_rrf()`: compute `(1-w) * 1/(k + bm25_rank) + w * 1/(k + knn_rank)`, sort descending
    - Implement `_build_bm25_query()` with mandatory company_id filter, search chunk_text + title
    - Implement `_build_knn_query()` with mandatory company_id filter
    - Implement graceful degradation: BM25-only fallback when vLLM unavailable, set `degraded_mode: true`
    - Handle partial results for unified search when one index unreachable
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 10.10_

  - [x] 5.2 Write property test: RRF fusion computation correctness (Property 7)
    - **Property 7: RRF fusion computation correctness**
    - Generate two ranked lists of document IDs with varying overlap
    - Generate k (1–200) and semantic_weight (0.0–1.0)
    - Assert RRF score equals `(1-w) * 1/(k + bm25_rank) + w * 1/(k + knn_rank)`
    - Assert final list sorted by RRF score descending
    - **Validates: Requirements 6.1, 6.3**

  - [x] 5.3 Write property test: Semantic weight boundary behavior (Property 8)
    - **Property 8: Semantic weight boundary behavior**
    - Generate two ranked lists
    - Assert semantic_weight=0.0 → ranking determined entirely by BM25 ranks
    - Assert semantic_weight=1.0 → ranking determined entirely by kNN ranks
    - **Validates: Requirements 6.4**

  - [x] 5.4 Write property test: Pagination correctness (Property 9)
    - **Property 9: Pagination correctness**
    - Generate ranked list of N items, page p, page_size s
    - Assert returned results are slice `[(p-1)*s : p*s]`
    - Assert total_count equals N
    - **Validates: Requirements 6.5**

- [x] 6. Checkpoint - Ensure all service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement EmbeddingService orchestrator
  - [x] 7.1 Implement EmbeddingService class
    - Create `src/backend/src/alcoabase/literature/embedding/services/embedding_service.py`
    - Implement `__init__` with session_factory, inference_client, model_manager, index_manager, chunking_pipeline
    - Implement `generate_and_index_embeddings()`: load record + config → chunk → batch embed (32/batch) → validate dimensions → delete existing → bulk index → transition state → audit log
    - Implement `initiate_reindex()`: create ReindexJob → dispatch first batch via Celery
    - Implement `cancel_reindex()`: set status to cancelled, stop dispatching
    - Implement `get_reindex_progress()`: return percentage, processed, failed, estimated_remaining
    - Implement dimension validation: reject batch if vector length ≠ MODEL_EMBEDDING_DIMENSION
    - Implement idempotent indexing: delete-then-insert per record with retry on insert failure
    - Implement retry logic with exponential backoff (30s, 2min, 10min)
    - Respect `auto_embed_on_ingest`, `embed_abstract_only`, `max_chunks_per_document` from EmbeddingConfiguration
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 9.2, 9.3, 9.4, 9.5, 9.6, 12.1, 12.4, 12.6, 12.7, 12.8_

  - [x] 7.2 Write property test: Embedding batch size correctness (Property 10)
    - **Property 10: Embedding batch size correctness**
    - Generate N content chunks (1–500)
    - Assert InferenceClient is called exactly `ceil(N/32)` times
    - Assert each call has at most 32 chunks
    - Assert concatenated results maintain original ordering
    - **Validates: Requirements 1.4**

  - [x] 7.3 Write property test: Embedding dimension validation (Property 13)
    - **Property 13: Embedding dimension validation**
    - Generate embedding vectors with incorrect dimensions
    - Assert EmbeddingService rejects the batch
    - Assert record transitions to `failed` with `embedding_dimension_mismatch`
    - **Validates: Requirements 1.5, 12.7**

  - [x] 7.4 Write property test: Max chunks truncation (Property 17)
    - **Property 17: Max chunks truncation**
    - Generate content producing N chunks where N > configured max_chunks_per_document M
    - Assert exactly M chunks are indexed (first M in document order)
    - Assert truncation is recorded in audit trail
    - **Validates: Requirements 9.6**

  - [x] 7.5 Write property test: Idempotent indexing (Property 11)
    - **Property 11: Idempotent indexing**
    - Index a record, then re-index (delete + re-insert)
    - Assert identical chunk count, texts, and vectors as fresh indexing
    - Mock OpenSearch to verify delete-then-insert sequence
    - **Validates: Requirements 8.4, 12.4**

- [x] 8. Implement API routers
  - [x] 8.1 Implement literature_search_router
    - Create `src/backend/src/alcoabase/api/literature_search_router.py`
    - `POST /api/literature/search/hybrid`: validate request body, require `member` role, execute hybrid search, return `HybridSearchResponseSchema`
    - `POST /api/literature/search/unified`: same params + `include_internal`, require `member` role, execute unified search
    - Require `X-Company-Id` header (HTTP 400 if missing)
    - Return empty results (HTTP 200) if company index doesn't exist
    - Reject empty/whitespace queries with HTTP 422
    - _Requirements: 10.1, 10.2, 10.8, 10.9, 10.10, 4.7, 6.9_

  - [x] 8.2 Implement literature_index_router
    - Create `src/backend/src/alcoabase/api/literature_index_router.py`
    - `GET /api/literature/index/status`: require `member` role, return `IndexStatusSchema`
    - `POST /api/literature/index/reindex`: require `system_admin` role, require `X-Change-Reason`, return HTTP 202 with task_id
    - `GET /api/literature/index/reindex/{task_id}`: require `system_admin` role, return `ReindexProgressSchema`
    - `GET /api/literature/index/config`: require `document_admin` role, return current `EmbeddingConfigurationSchema`
    - `PUT /api/literature/index/config`: require `document_admin` role, require `X-Change-Reason`, validate ranges (HTTP 422 on violation), write audit log
    - Require `X-Company-Id` header on all endpoints
    - _Requirements: 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 9.7, 9.8, 9.9, 8.7_

  - [x] 8.3 Register routers in central router.py
    - Add `literature_search_router` and `literature_index_router` to `src/backend/src/alcoabase/api/router.py`
    - Verify route prefix is `/api/literature`
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 9. Implement Celery tasks
  - [x] 9.1 Implement literature_embedding_tasks.py
    - Create `src/backend/src/alcoabase/tasks/literature_embedding_tasks.py`
    - Implement `generate_embeddings` task: queue=`literature_ingestion`, priority=5, max_retries=3, soft_time_limit=600s, exponential backoff (30s, 120s, 600s), acks_late=True
    - Implement `reindex_batch` task: queue=`literature_ingestion`, priority=7, max_retries=0, soft_time_limit=600s, acks_late=True
    - Both tasks call EmbeddingService methods within an async event loop
    - Register tasks with celery_app
    - _Requirements: 1.8, 8.2, 8.9, 12.1, 12.6_

  - [x] 9.2 Extend Ingestion_Pipeline_Service with embedding dispatch
    - Modify existing `src/backend/src/alcoabase/tasks/literature_ingestion_tasks.py` (or the Ingestion_Pipeline_Service)
    - On `sanitized` state transition, check company's `auto_embed_on_ingest` flag
    - If True, dispatch `generate_embeddings.delay(record_id=..., company_id=...)`
    - If False, do nothing (manual trigger via API)
    - _Requirements: 1.1, 1.8, 9.2, 9.3_

- [x] 10. Implement audit trail integration
  - [x] 10.1 Add embedding/indexing audit log entries
    - Extend audit logging to record embedding generation events (ingestion_record_id, company_id, user_id, chunk_count, dimension, model_name, duration_ms, triggering_event, timestamp)
    - Record indexing events (ingestion_record_id, company_id, index_name, chunks_indexed, duration_ms, partition_tag, timestamp)
    - Record re-indexing initiation (company_id, user_id, total_records, reason, task_id, timestamp)
    - Record failures (ingestion_record_id, error_type, error_message truncated to 2000 chars, retry_attempt)
    - Record search queries (company_id, user_id, query_text_length only, search_mode, result_count, response_time_ms, partition_filter)
    - Never log embedding vectors, full query text, or document content
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

- [x] 11. Checkpoint - Ensure all components compile and unit tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Write unit tests for services and routers
  - [x] 12.1 Write unit tests for EmbeddingService
    - Test state transitions: `sanitized → indexed`, `sanitized → failed`
    - Test retry logic with exponential backoff timing
    - Test idempotent indexing (delete-then-insert)
    - Test configuration respect (auto_embed_on_ingest, embed_abstract_only, max_chunks)
    - Test reindex initiation, progress, and cancellation
    - Mock InferenceClient, OpenSearch, and database session
    - _Requirements: 1.1, 1.6, 1.7, 8.1, 8.4, 8.8, 8.10_

  - [x] 12.2 Write unit tests for HybridQueryEngine
    - Test graceful degradation (BM25-only fallback when vLLM down)
    - Test unified search partial results
    - Test query validation (empty query rejection)
    - Test role-based access (member, document_admin, system_admin)
    - Test pagination edge cases
    - Mock InferenceClient and LiteratureIndexManager
    - _Requirements: 6.8, 6.9, 6.10, 7.7, 7.8_

  - [x] 12.3 Write unit tests for API routers
    - Test all endpoint response codes (200, 202, 400, 403, 422, 503)
    - Test X-Change-Reason requirement on mutation endpoints
    - Test X-Company-Id requirement
    - Test role-based access control
    - Test configuration range validation (HTTP 422)
    - Use FastAPI TestClient with mocked dependencies
    - _Requirements: 10.7, 10.8, 10.9, 4.3, 4.7, 9.8, 9.9_

  - [x] 12.4 Write property test: Configuration range validation (Property 16)
    - **Property 16: Configuration range validation**
    - Generate config values outside valid ranges
    - Assert HTTP 422 rejection for out-of-range values
    - Assert acceptance for in-range values
    - **Validates: Requirements 9.9**

- [x] 13. Write integration tests
  - [x] 13.1 Write integration tests for embedding pipeline
    - Test end-to-end: StructuredContent → chunks → embeddings → indexed → searchable
    - Test hybrid search accuracy (BM25 + kNN merge)
    - Test unified search across both indices
    - Test company index isolation (company A data not visible to company B)
    - Test re-tagging (atomic partition_tag update)
    - Test index lifecycle (create → populate → delete on company removal)
    - Requires Docker OpenSearch and Redis fixtures
    - _Requirements: 1.1, 3.1, 4.1, 4.2, 5.6, 6.1, 7.1_

  - [x] 13.2 Write integration tests for round-trip and self-retrieval (Properties 14, 15)
    - **Property 14: Embedding vector round-trip precision**
    - **Property 15: Self-retrieval property**
    - Generate embedding, store in OpenSearch, retrieve and compare element-by-element (tolerance < 1e-6)
    - Index text, search with same text, assert top-1 result with similarity ≈ 1.0
    - Requires Docker OpenSearch + vLLM (or mock)
    - **Validates: Requirements 14.1, 14.3**

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (17 total)
- Unit tests validate specific examples and edge cases
- Integration tests require Docker infrastructure (OpenSearch, Redis, optionally vLLM)
- All commands use `uv run pytest` per project convention
- Property tests use Hypothesis with `@settings(max_examples=100)` minimum

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.5", "1.6"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["3.1", "4.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.5", "4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["5.1"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 7, "tasks": ["7.1"] },
    { "id": 8, "tasks": ["7.2", "7.3", "7.4", "7.5", "8.1", "8.2"] },
    { "id": 9, "tasks": ["8.3", "9.1"] },
    { "id": 10, "tasks": ["9.2", "10.1"] },
    { "id": 11, "tasks": ["12.1", "12.2", "12.3", "12.4"] },
    { "id": 12, "tasks": ["13.1", "13.2"] }
  ]
}
```
