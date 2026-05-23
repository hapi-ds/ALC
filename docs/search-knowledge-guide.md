# Search & Knowledge Base Guide

This guide covers the hybrid search and RAG (Retrieval-Augmented Generation) knowledge base features in AlcoaBase.

---

## Overview

AlcoaBase provides two complementary ways to find information across your document repository:

- **Hybrid Search** — Fast document discovery combining keyword matching (BM25) with semantic vector similarity (kNN). Best for finding specific documents or passages.
- **Knowledge Chat** — Conversational Q&A powered by RAG. Ask natural language questions and receive grounded answers with source citations.

Both features respect ABAC (Attribute-Based Access Control) permissions — users only see results from documents they have access to.

---

## Hybrid Search

### How to Use

1. Navigate to the **Search** page from the sidebar
2. Type your query in the search bar (up to 1000 characters)
3. Results appear automatically after a 300ms debounce, or press Enter for immediate search
4. Use the filter sidebar to narrow results by document type, status, or tags

### Search Behavior

| Feature | Description |
|---------|-------------|
| Debounced input | Searches trigger 300ms after you stop typing |
| Faceted filters | Filter by document_type, status, and tags (AND between categories, OR within) |
| Pagination | 20 results per page with next/previous navigation |
| Sorting | Sort by relevance score (default) or by date |
| Query truncation | Queries exceeding 1000 characters are automatically truncated with a notification |

### Result Cards

Each result displays:
- Document title with link
- Document-UUID and version
- Relevance score (0.0–1.0)
- Text excerpt with the matching passage
- Document type badge, status, and tags

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Execute search immediately |
| Escape | Clear search and results |

---

## Knowledge Chat (RAG)

### How to Use

1. Navigate to the **Knowledge Chat** page from the sidebar
2. Type a question about your documents (up to 2000 characters)
3. The system retrieves relevant document chunks and generates a grounded answer
4. Source citations appear with each response — click to navigate to the source document
5. Ask follow-up questions in the same conversation for contextual answers

### Grounding Rules

The knowledge base enforces strict grounding to prevent hallucination:

- Answers are generated **only** from retrieved document content
- Each claim cites its source using `[Source N]` format
- When documents don't contain enough information, the system states this clearly
- No information is fabricated beyond what exists in the indexed documents

### Response Types

| Scenario | Behavior |
|----------|----------|
| Relevant documents found | Grounded answer with `[Source N]` citations |
| No matching documents | "No matching content found..." message |
| Network/server error | Error displayed with retry button (up to 3 retries) |

### Conversation Management

- **New Conversation** — Start fresh with no prior context
- **Clear** — Remove all messages (requires confirmation)
- **Follow-up questions** — The system uses the last 6 messages as context for better answers

### Visual Content Understanding

The knowledge base can interpret diagrams, flowcharts, and process maps within your documents. When you ask process-related questions (containing words like "process", "flow", "workflow", "steps", "procedure"), visual content receives a relevance boost to surface diagram-based answers alongside text.

---

## Document Indexing

Documents are automatically indexed when uploaded. The indexing pipeline:

1. **Text extraction** — Extracts text from PDF, DOCX, and plain text files
2. **Scanned PDF detection** — If no extractable text is found, triggers OCR via the vision model
3. **Visual content detection** — Identifies diagrams and flowcharts for separate indexing
4. **Chunking** — Splits text into ~512-token segments with 50-token overlap
5. **Embedding** — Generates 1024-dimensional vectors for each chunk
6. **Indexing** — Stores chunks and vectors for hybrid search

### Supported Formats

| Format | Text Extraction | OCR Fallback | Visual Indexing |
|--------|----------------|--------------|-----------------|
| PDF (digital) | ✅ PyMuPDF | N/A | ✅ |
| PDF (scanned) | N/A | ✅ Vision model | ✅ |
| DOCX | ✅ python-docx | N/A | ❌ |
| Plain text | ✅ Direct | N/A | ❌ |

---

## API Endpoints

### Search

```
POST /api/search
```

Request body:
```json
{
  "query": "calibration procedure for pH meters",
  "user_id": 1,
  "limit": 20,
  "offset": 0,
  "sort_by": "relevance",
  "filters": {
    "document_type": ["SOP"],
    "status": ["Active"],
    "tags": []
  }
}
```

### Knowledge Query

```
POST /api/knowledge/query
```

Request body:
```json
{
  "question": "What is the calibration frequency for pH meters?",
  "user_id": 1,
  "top_k": 5
}
```

### Conversation Follow-up

```
POST /api/knowledge/conversation
```

Request body:
```json
{
  "question": "What about temperature probes?",
  "user_id": 1,
  "conversation_id": "uuid-from-previous-response",
  "top_k": 5
}
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_MANAGER_MODE` | `mock` | Operating mode: `gpu`, `cpu`, or `mock` |
| `VLLM_BASE_URL` | `http://localhost:8000` | Main vLLM instance (chat/OCR) |
| `VLLM_EMBEDDING_URL` | `http://localhost:8001` | Dedicated embedding instance |
| `MODEL_EMBEDDING_DIMENSION` | `1024` | Embedding vector dimensions |
| `ENABLE_VISUAL_INDEXING` | `true` | Enable diagram/flowchart indexing |
| `VISUAL_BOOST_FACTOR` | `1.5` | Relevance boost for visual chunks in process queries (1.0–3.0) |
| `MAX_VISUAL_PAGES_PER_DOCUMENT` | `100` | Max pages to scan for visual content |

### Mock Mode

In mock mode (`MODEL_MANAGER_MODE=mock`):
- Search uses keyword matching against the in-memory index
- Knowledge Chat returns placeholder responses mentioning context size
- Embeddings are random normalized vectors (consistent per input text)
- No vLLM server or GPU hardware is required

This allows full UI testing of search and knowledge features during development.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Search returns no results | No documents indexed | Upload documents first; they're indexed automatically |
| Knowledge Chat says "No matching content" | Query doesn't match indexed content | Try different keywords; check that relevant documents are uploaded |
| Slow search responses | Large index or embedding generation | Check vLLM health at `/api/models/status` |
| Citations show wrong document | Index stale after document update | Re-upload the document to trigger re-indexing |
| Visual content not appearing in results | Visual indexing disabled | Set `ENABLE_VISUAL_INDEXING=true` in `.env` |
