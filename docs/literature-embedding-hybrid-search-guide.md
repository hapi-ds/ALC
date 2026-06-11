# Literature Embedding & Hybrid Search — User Guide

## Overview

The High-Dimensional Embedding & Hybrid Indexing feature (Phase 9.3) extends the Automated Ingestion Pipeline by generating semantic embeddings from ingested literature content and indexing them in OpenSearch alongside classic BM25 keyword indices. This enables unified hybrid search that combines keyword matching with semantic similarity, so you can find relevant papers whether you know the exact terminology or only the general concept.

## Key Capabilities

- **Automatic embedding generation**: ingested literature is automatically chunked and embedded via the vLLM embedding model
- **Hybrid search (BM25 + kNN)**: combines keyword and semantic similarity with reciprocal rank fusion (RRF)
- **Unified search**: single query across both literature and internal company documents
- **Per-company vector spaces**: complete tenant isolation via separate OpenSearch indices
- **Partition tagging**: distinguishes `public_literature` from `private_knowledge` in results
- **Configurable chunking**: per-company settings for chunk size, overlap, and auto-embed behavior
- **Batch re-indexing**: re-generate all embeddings when switching models
- **Graceful degradation**: falls back to BM25-only when the embedding model is unavailable
- **Full audit trail**: every embedding, indexing, and search operation is logged

---

## Getting Started

### Prerequisites

Phase 9.3 requires both Phase 9.1 (Literature Search Engine) and Phase 9.2 (Ingestion Pipeline) to be active:

```env
ALC_LITERATURE_ENABLED=true
ALC_LITERATURE_ENCRYPTION_KEY=<your-key>
```

You also need the embedding model configured and available:

```env
MODEL_EMBEDDING_NAME=Qwen/Qwen3-Embedding-0.6B
MODEL_EMBEDDING_PATH=/llm_models/qwen3-embedding-0.6b
MODEL_EMBEDDING_DIMENSION=1024
MODEL_MANAGER_MODE=gpu   # or "mock" for development
```

The OpenSearch instance must be running (part of the standard Docker Compose stack).

### How It Works

1. Papers are ingested via Phase 9.2 and reach the `sanitized` state
2. A Celery task automatically chunks the content and generates embeddings
3. Embeddings are indexed into a per-company OpenSearch index (`literature-embeddings-{company_id}`)
4. The record transitions to the `indexed` state
5. Users can now search using hybrid BM25 + semantic similarity

---

## API Endpoints

All endpoints require the `Authorization`, `X-User-Id`, and `X-Company-Id` headers.

### Hybrid Search

Execute a combined keyword + semantic search against your company's literature index.

```bash
curl -X POST http://localhost:8080/api/literature/search/hybrid \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -d '{
    "query": "CRISPR gene therapy delivery mechanisms",
    "semantic_weight": 0.6,
    "page": 1,
    "page_size": 20,
    "partition_filter": "all"
  }'
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string (1–1000 chars) | required | Search query text |
| `semantic_weight` | float (0.0–1.0) | 0.5 | Balance between BM25 (0.0) and semantic (1.0) |
| `rrf_k` | int (1–200) | 60 | RRF fusion constant |
| `page` | int (≥1) | 1 | Page number |
| `page_size` | int (1–100) | 20 | Results per page |
| `partition_filter` | string | "all" | Filter: `public_literature`, `private_knowledge`, or `all` |
| `date_range` | object | null | `{"start": "2020-01-01", "end": "2024-12-31"}` |
| `source_id` | string | null | Filter by source (e.g., "pubmed") |
| `authors` | string[] | null | Filter by author names |
| `literature_boost` | float (0.1–10.0) | 1.0 | Boost factor for literature results |
| `internal_boost` | float (0.1–10.0) | 1.0 | Boost factor for internal results |

**Response:**

```json
{
  "results": [
    {
      "chunk_text": "CRISPR-Cas9 delivery via lipid nanoparticles...",
      "title": "Advances in CRISPR Delivery Systems",
      "authors": ["Smith J", "Doe A"],
      "doi": "10.1000/example.2024",
      "publication_date": "2024-03-15",
      "source_id": "pubmed",
      "relevance_score": 0.847,
      "partition_tag": "public_literature",
      "section_heading": "Methods",
      "ingestion_record_id": 42
    }
  ],
  "total_count": 156,
  "page": 1,
  "page_size": 20,
  "degraded_mode": false
}
```

When `degraded_mode: true`, the embedding model was unavailable and results are BM25-only.

**Required role:** `member` or higher.

### Unified Search

Search across both literature and internal company documents in a single request:

```bash
curl -X POST http://localhost:8080/api/literature/search/unified \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -d '{
    "query": "cleaning validation acceptance criteria",
    "semantic_weight": 0.5,
    "include_internal": true,
    "literature_boost": 1.0,
    "internal_boost": 1.5
  }'
```

The response includes `partition_tag` on each result so the UI can display origin badges ("Literature" vs "Internal"). If one index is unreachable, results from the available index are returned with `partial_results: true`.

**Required role:** `member` or higher. Internal documents are additionally filtered by ABAC permissions.

### Index Status

Check the health and statistics of your company's embedding index:

```bash
curl http://localhost:8080/api/literature/index/status \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"
```

**Response:**

```json
{
  "health": "green",
  "doc_count": 24580,
  "chunks_indexed": 24580,
  "size_bytes": 157286400,
  "last_indexing_timestamp": "2025-06-10T14:32:00Z"
}
```

**Required role:** `member` or higher.

### Embedding Configuration

View and update per-company embedding settings:

```bash
# Get current configuration
curl http://localhost:8080/api/literature/index/config \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"

# Update configuration
curl -X PUT http://localhost:8080/api/literature/index/config \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Increase chunk size for longer documents" \
  -d '{
    "chunk_size_tokens": 768,
    "chunk_overlap_tokens": 75,
    "auto_embed_on_ingest": true,
    "embed_abstract_only": false,
    "max_chunks_per_document": 1000
  }'
```

**Configuration parameters:**

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| `chunk_size_tokens` | 128–2048 | 512 | Maximum tokens per chunk |
| `chunk_overlap_tokens` | 0–256 | 50 | Overlap between consecutive chunks |
| `auto_embed_on_ingest` | bool | true | Automatically embed on ingestion |
| `embed_abstract_only` | bool | false | Only embed abstracts, skip body |
| `max_chunks_per_document` | 1–5000 | 500 | Maximum chunks indexed per document |

**Required role:** `document_admin` or higher. The `X-Change-Reason` header is required for updates.

### Batch Re-indexing

Re-generate embeddings for all (or selected) records. Useful after switching embedding models.

```bash
# Initiate re-indexing
curl -X POST http://localhost:8080/api/literature/index/reindex \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Upgrading to Qwen3-Embedding-8B model" \
  -d '{
    "state": ["indexed", "abstract_indexed"]
  }'
```

**Response (HTTP 202):**

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "total_records": 1250
}
```

```bash
# Check progress
curl http://localhost:8080/api/literature/index/reindex/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"
```

**Progress response:**

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "in_progress",
  "percentage": 45,
  "records_processed": 562,
  "records_failed": 3,
  "estimated_remaining_seconds": 180
}
```

**Required role:** `system_admin`. Only one re-indexing job can run per company at a time.

---

## Configuration Reference

### Environment Variables (Phase 9.3)

Add these to your `.env` file to tune embedding and indexing behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `ALC_LITERATURE_INDEX_SHARDS` | 1 | Number of primary shards per company index |
| `ALC_LITERATURE_INDEX_REPLICAS` | 1 | Number of replica shards per company index |
| `ALC_LITERATURE_HNSW_EF_CONSTRUCTION` | 256 | HNSW index build quality (higher = better recall, slower builds) |
| `ALC_LITERATURE_HNSW_M` | 16 | HNSW connections per node (higher = better recall, more memory) |
| `ALC_LITERATURE_RRF_K` | 60 | Default RRF fusion constant (1–200) |
| `ALC_LITERATURE_EMBEDDING_QUEUE` | literature_ingestion | Celery queue for embedding tasks |
| `ALC_REINDEX_BATCH_SIZE` | 50 | Records per batch during re-indexing (10–200) |

These are infrastructure-level defaults. Per-company chunking parameters are configured via the `/api/literature/index/config` endpoint.

---

## Architecture Notes

### Chunking Strategy

Content is chunked using the same algorithm as internal documents (KnowledgeService) to maintain embedding space consistency:

1. **Abstract** is always chunked first
2. **Body sections** are split respecting paragraph/heading boundaries
3. Each chunk has the document title + section heading prepended (up to 64 tokens)
4. Chunk size defaults to 512 tokens with 50-token overlap

### Tenant Isolation

Every company gets a dedicated OpenSearch index (`literature-embeddings-{company_id}`). Additionally, a mandatory `company_id` filter is applied on every query as defense-in-depth. Cross-tenant data access is impossible at both the index level and the query level.

### Graceful Degradation

If the vLLM embedding model is unavailable:
- **Search** falls back to BM25-only (keyword matching) with `degraded_mode: true` in the response
- **Indexing** retries 3 times with exponential backoff (30s, 2min, 10min) before marking the record as failed

### Partition Tags

Every indexed chunk carries a `partition_tag`:
- `public_literature` — content from the literature ingestion pipeline (PubMed, Crossref, arXiv)
- `private_knowledge` — content from internal company document uploads

Use the `partition_filter` parameter in search to limit results to one source type.

---

## Troubleshooting

### "Search service unavailable" (HTTP 503)

OpenSearch is unreachable. Verify the OpenSearch container is running:
```bash
docker compose ps opensearch
curl http://localhost:9200/_cluster/health
```

### Empty search results despite indexed content

1. Check index status: `GET /api/literature/index/status` — verify `doc_count > 0`
2. Verify the record reached `indexed` state (not stuck at `sanitized` or `failed`)
3. Check if `auto_embed_on_ingest` is enabled for your company

### Records stuck in "sanitized" state

The embedding task may have failed. Check:
1. Celery worker logs for the `literature_ingestion` queue
2. vLLM embedding instance availability at the configured `VLLM_EMBEDDING_URL`
3. The `MODEL_EMBEDDING_NAME` matches an actually loaded model

### Re-indexing rejected with "already active"

Only one re-indexing job runs per company. Wait for the current job to complete or cancel it (via the admin API) before starting a new one.

### HTTP 422 on configuration update

One or more values are outside allowed ranges. Check:
- `chunk_size_tokens`: 128–2048
- `chunk_overlap_tokens`: 0–256
- `max_chunks_per_document`: 1–5000

---

## Role Requirements Summary

| Endpoint | Minimum Role |
|----------|-------------|
| `POST /api/literature/search/hybrid` | `member` |
| `POST /api/literature/search/unified` | `member` |
| `GET /api/literature/index/status` | `member` |
| `GET /api/literature/index/config` | `document_admin` |
| `PUT /api/literature/index/config` | `document_admin` |
| `POST /api/literature/index/reindex` | `system_admin` |
| `GET /api/literature/index/reindex/{task_id}` | `system_admin` |
