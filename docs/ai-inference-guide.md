# AI Inference Guide

This guide covers the vLLM-based AI inference system in AlcoaBase, including RAG (Retrieval-Augmented Generation), embedding generation for semantic search, and OCR text extraction from scanned PDFs.

---

## Overview

AlcoaBase uses a hybrid vLLM architecture for local AI inference:

- **Embedding instance** — A dedicated always-on vLLM container running a small embedding model (~2 GB VRAM). Handles all embedding requests for document indexing and search queries.
- **Main instance** — A shared vLLM container that loads either the Chat model or the OCR model. The system automatically swaps models via container restart when needed (e.g., switching from chat to OCR for a scanned PDF upload).

All inference runs locally with no outbound network access. The system supports three operating modes configured via `MODEL_MANAGER_MODE`:

| Mode | Description | Use Case |
|------|-------------|----------|
| `gpu` | Real inference on NVIDIA GPU | Production |
| `cpu` | Real inference on CPU (slower) | Fallback / testing |
| `mock` | Placeholder responses, no HTTP calls | Development without GPU |

---

## RAG (Knowledge Base Queries)

### How It Works

1. User submits a question via the Knowledge Base chat interface
2. The system performs hybrid search (BM25 keyword + kNN semantic) against indexed documents
3. Retrieved chunks are formatted with source references and truncated to fit the 8192-token context window
4. The chat model generates a grounded response citing specific sources

### Grounding Rules

The system prompt enforces strict grounding:
- Answers only from provided context documents
- Citations use `[Source N]` format referencing specific documents
- When context is insufficient, the model states this clearly
- No fabrication of information beyond what's in the context

### Response Behavior

| Scenario | Result |
|----------|--------|
| Relevant documents found | Grounded response with citations (`grounded: true`) |
| No matching documents | "No matching content found..." message (`grounded: false`) |
| vLLM unavailable | Error propagated to caller |
| Timeout (60s) | Timeout error raised |

### Context Truncation

When retrieved chunks exceed 8192 tokens (whitespace-split approximation):
- Lowest-relevance chunks are removed first
- The highest-relevance chunk is always retained regardless of size
- Remaining chunks stay in their original order

---

## Embedding Generation

### How It Works

1. Documents are chunked into ~512-token segments with 50-token overlap
2. Chunks are sent to the embedding vLLM instance in batches of 32
3. Each chunk produces a 1024-dimensional vector
4. Vectors are stored in OpenSearch for kNN similarity search

### Batching

- Maximum 32 chunks per API request
- Batches are processed sequentially (not concurrent) to avoid overwhelming vLLM
- Results are concatenated in input order

### Search Query Embeddings

When a user performs a search, their query is also embedded using the same model, ensuring consistent vector space for similarity matching. If embedding fails, the system falls back to keyword-only (BM25) search.

---

## OCR Text Extraction

### How It Works

1. When a scanned PDF is uploaded (no extractable text detected), OCR is triggered
2. Each page is converted to a PNG image at 300 DPI using PyMuPDF
3. The OCR vision model processes pages sequentially via multimodal chat completion
4. Extracted text from all successful pages is concatenated with newline separators

### Resilience

The OCR system is designed to be resilient to per-page failures:

| Scenario | Behavior |
|----------|----------|
| Page extraction succeeds | Text added to result |
| Page times out (90s) | Warning logged, page skipped, continues |
| Page returns HTTP error | Warning logged, page skipped, continues |
| All pages fail | Empty string returned, error logged |
| Zero-page PDF | Empty string returned, warning logged |
| PDF > 500 pages | Only first 500 pages processed |

### Model Swap

Since the chat and OCR models share the main vLLM instance, a model swap (container restart) occurs when switching between them. This is acceptable because:
- OCR only triggers for scanned PDFs during document upload (infrequent)
- Chat handles all RAG queries (frequent)
- The embedding model runs on its own instance and is never swapped

---

## Configuration

### Environment Variables

```env
# Operating mode
MODEL_MANAGER_MODE=gpu          # gpu | cpu | mock

# vLLM instance URLs
VLLM_BASE_URL=http://localhost:8000       # Main instance (chat/OCR)
VLLM_EMBEDDING_URL=http://localhost:8001  # Dedicated embedding instance

# Chat model
MODEL_CHAT_NAME=Qwen/Qwen3.6-35B-A3B
MODEL_CHAT_PATH=/models/qwen3.6-35b-a3b
MODEL_CHAT_MAX_GPU_MEMORY_GB=24

# Embedding model
MODEL_EMBEDDING_NAME=Qwen/Qwen3-Embedding-0.6B
MODEL_EMBEDDING_PATH=/models/qwen3-embedding-0.6b
MODEL_EMBEDDING_DIMENSION=1024

# OCR model
MODEL_OCR_NAME=google/gemma-4-E4B-it
MODEL_OCR_PATH=/models/gemma-4-e4b-it
```

### Timeouts

| Operation | Timeout | Retries |
|-----------|---------|---------|
| Chat completion | 60s | None (timeout = final) |
| Embedding generation | 30s | None |
| OCR per page | 90s | None (page skipped) |
| Health check | 5s | None |
| Connection | 10s | 2 retries (1s, 2s backoff) |
| HTTP 503 | — | 2 retries (1s, 2s backoff) |

### Retry Policy

- **Retried:** HTTP 503 (Service Unavailable) and connection errors — up to 2 additional attempts with 1s/2s exponential backoff
- **Not retried:** HTTP 4xx errors (client-side issues), read timeouts (server accepted but is too slow)

---

## Health Monitoring

The Model Manager exposes health status via the `/api/models/status` endpoint:

```json
{
  "current_role": "chat",
  "current_model_name": "Qwen/Qwen3.6-35B-A3B",
  "gpu_memory_used_gb": 24.0,
  "is_ready": true,
  "mode": "gpu",
  "vllm_reachable": true
}
```

| Field | Description |
|-------|-------------|
| `current_role` | Currently loaded model role (`chat`, `embedding`, `ocr`, or `null`) |
| `current_model_name` | HuggingFace model identifier |
| `gpu_memory_used_gb` | Estimated GPU memory usage |
| `is_ready` | Whether the model is ready for inference |
| `mode` | Operating mode (`gpu`, `cpu`, `mock`) |
| `vllm_reachable` | Health check result (`true`/`false` in gpu/cpu, `null` in mock) |

---

## Development (Mock Mode)

For local development without GPU hardware:

```env
MODEL_MANAGER_MODE=mock
```

In mock mode:
- **Chat:** Returns a placeholder response mentioning the prompt length
- **Embeddings:** Returns random normalized vectors of 1024 dimensions (deterministic per input text)
- **OCR:** Returns `"[OCR_PENDING: Scanned PDF text extraction requires Model_Manager]"`
- **No HTTP calls** are made to any vLLM server
- **No model weights** need to be downloaded

This allows full application testing including document upload, indexing, search, and RAG queries — all with mock responses.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModelManagerError: health check timeout` | vLLM container not starting | Check `docker compose logs vllm` for OOM or model path errors |
| `InferenceConnectionError: Cannot connect` | vLLM container not running | Run `docker compose up -d vllm` |
| `InferenceTimeoutError: timed out after 60s` | Model overloaded or too slow | Check GPU utilization; consider smaller model |
| `ValueError: Embedding dimension mismatch` | Wrong model loaded | Verify `MODEL_EMBEDDING_NAME` matches the model at `MODEL_EMBEDDING_PATH` |
| Slow model swap (chat ↔ OCR) | Container restart in progress | Normal behavior; takes 30-120s depending on model size |
| Search returns no semantic results | Embedding service down | Check `VLLM_EMBEDDING_URL` health; system falls back to keyword search |
