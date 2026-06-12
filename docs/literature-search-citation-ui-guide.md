# Literature Search & Citation UI Guide

This guide covers the Literature Search Dashboard, one-click internalization, citation collection management, traceability mapping, and search result export features in AlcoaBase.

---

## Overview

The Literature Search Dashboard connects the literature research infrastructure (Phases 9.1–9.5) to a unified user interface for regulatory evidence workflows. It provides quality managers, regulatory affairs specialists, and document administrators with a single page to find, capture, organize, and cite scientific literature for FDA/EMA submissions.

Six capabilities are delivered:

| Capability | Description |
|------------|-------------|
| **Faceted Search** | Hybrid BM25+kNN semantic search with journal, source, date, MeSH, and device class filters |
| **Cross-Corpus Search** | Simultaneous query across external literature and internal company documents |
| **Saved Searches** | Persist query configurations for reproducible search methodology documentation |
| **One-Click Internalization** | Convert public literature into governed internal Documents with lifecycle tracking |
| **Citation Collections** | Organize internalized papers into named groups for regulatory submissions |
| **Traceability Mapping** | Link papers to URS requirements or test cases, creating evidence chains |

All operations are immutably logged for regulatory audit compliance.

---

## Prerequisites

- Literature infrastructure enabled: `ALC_LITERATURE_ENABLED=true` in `.env`
- Phases 9.1–9.5 operational (gateway, ingestion, embedding, review, vigilance)
- OpenSearch running with per-company literature embedding indices populated
- At least `member` role for search; `document_admin` for internalization and citation management

---

## Accessing the Dashboard

Navigate to **Literature Search** in the sidebar, or visit `/literature-search` directly.

The page requires authentication. Unauthenticated users are redirected to login. The route is protected by the same `RouteGuard` as all other application pages.

---

## Executing a Search

### Search Input

1. Type your query in the search bar (1–1000 characters)
2. Press **Enter** or click **Search** to execute
3. The submit button is disabled for empty or whitespace-only queries

### Search Mode

Select the retrieval strategy using the segmented control above the results:

| Mode | Behavior |
|------|----------|
| **Hybrid** (default) | Combines BM25 keyword matching with kNN semantic similarity via Reciprocal Rank Fusion |
| **Keyword** | BM25 full-text keyword matching only |
| **Semantic** | kNN vector similarity only |

### Include Internal Documents

Toggle the "Include Internal Documents" switch to additionally query your company's internal document index (Phase 4.1). Internal results appear with a green "Internal" provenance badge.

### Faceted Filters

The left sidebar provides post-filter constraints that narrow results without affecting relevance scoring:

| Filter | Input Type | Limit |
|--------|-----------|-------|
| Date Range | From/to date pickers | — |
| Journals | Checkbox multi-select with count badges | 20 max |
| Sources | Checkbox multi-select (PubMed, Crossref, arXiv) | 10 max |
| Publication Type | Checkbox multi-select | 10 max |
| MeSH Terms | Tag input (type + Enter) | 30 max |
| Device Class | Checkbox (Class I, IIa, IIb, III) | 5 max |

Facet count badges update after each search, showing how many results match each filter value. Click **Clear All Filters** to reset.

---

## Understanding Search Results

Each result card displays:

| Element | Description |
|---------|-------------|
| Title | Linked to DOI source (opens in new tab) |
| Authors | First 3 shown; "+N more" if additional |
| Year / Journal / Source | Publication metadata |
| Provenance badge | "External" (blue) or "Internal" (green) |
| Relevance bar | Visual 0–100% score with percentage label |
| Full Text badge | Shown when full-text content is available in storage |
| Internalization checkmark | Green ✓ if already internalized as a Document |
| Internalize button | Visible to `document_admin` / `system_admin` roles only |

### Pagination

Below the results, pagination controls display:
- **"Showing X–Y of Z results"** summary
- Page number buttons with ellipsis for large result sets
- Previous/Next buttons (disabled on first/last page)

Default page size is 20 results.

---

## Saved Searches

### Saving the Current Search

1. Click the **Save** button (top-right, floppy disk icon)
2. In the dialog, enter:
   - **Name** (required, 1–200 characters)
   - **Description** (optional, max 1000 characters)
3. Click **Save Search**

The saved search stores: query text, all applied filters, search mode, and include-internal toggle.

### Managing Saved Searches

The right sidebar **Saved** tab lists your saved searches ordered by last execution (most recent first, never-executed at bottom). Each entry shows:

- Name
- Last executed timestamp (relative: "5m ago", "2d ago")
- Result count at last execution

Available actions:
- **Re-execute** — Runs the saved search with its original parameters
- **Delete** — Archives the search (soft-delete for regulatory preservation)

**Limit:** 200 active saved searches per user per company. Archive unused searches to free capacity.

---

## Search History

The right sidebar **History** tab displays your last 20 search executions with:

- Query text (truncated)
- Timestamp
- Result count

Click any entry to re-execute that search with the same query text.

---

## One-Click Internalization

Internalization converts a public literature paper (IngestionRecord from Phase 9.2) into a governed internal Document entity with full BPMN workflow lifecycle.

### Who Can Internalize

Users with `document_admin` or `system_admin` role. The **Internalize** button on result cards is only visible to authorized users.

### Internalization Flow

1. Click **Internalize** on a search result card
2. In the dialog, configure:
   - **Document Name** — Pre-filled from paper title; override if desired
   - **Tags** — Comma-separated classification tags
   - **Citation Collection** — Optionally add to an existing collection immediately
   - **Traceability Links** — Optionally link to requirements or test cases
3. Click **Internalize**

### What Happens

The system performs these steps atomically:

1. Verifies the IngestionRecord belongs to your company
2. Checks for duplicate internalization (prevents re-internalization)
3. Creates a new Document entity (status: "Draft", type: "literature")
4. Copies the full-text file from the literature bucket to the documents bucket
5. Creates traceability links if specified
6. Adds to citation collection if specified
7. Records an immutable audit event

### Error States

| Error | HTTP Code | Meaning |
|-------|-----------|---------|
| Already internalized | 409 | A Document already exists for this paper. The existing document ID is shown. |
| Record not found | 404 | The IngestionRecord doesn't exist or belongs to a different company. |
| File copy failed | — | Document is created with `full_text_status: "unavailable"`. A warning is logged. |

---

## Citation Collections

Citation collections group internalized papers for specific regulatory purposes (e.g., "MDR Clinical Evaluation Q1 2025", "PMS Literature Review").

### Creating a Collection

Requires `document_admin` role. Available via the internalization dialog (collection selector dropdown) or the API:

```bash
curl -X POST http://localhost:8080/api/literature-search/citation-collections \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Create clinical evaluation collection" \
  -d '{
    "name": "MDR Clinical Evaluation — Q1 2025",
    "description": "Literature evidence for annual clinical evaluation update",
    "purpose": "clinical_evaluation"
  }'
```

### Purpose Categories

| Purpose | Use Case |
|---------|----------|
| `clinical_evaluation` | MDR clinical evaluation reports |
| `post_market_surveillance` | PMS and PMCF reports |
| `systematic_literature_review` | Formal SLR methodology evidence |
| `risk_assessment` | Risk-benefit analysis supporting evidence |
| `other` | General-purpose collections |

### Managing Documents in Collections

- **Adding:** Via the internalization dialog (collection selector), or `POST /api/literature-search/citation-collections/{id}/documents` with up to 50 document IDs per request
- **Removing:** `DELETE /api/literature-search/citation-collections/{id}/documents/{doc_id}` — removes membership only; the Document entity is preserved
- **Limit:** Maximum 500 documents per collection

Only internalized documents (those with `source_ingestion_record_id` set) can be added to collections.

---

## Traceability Mapping

Link internalized papers to specific requirements or test cases in the Traceability Matrix (Phase 5.6), creating bidirectional regulatory evidence chains.

### Creating Links

During internalization or afterward via the API:

```bash
curl -X POST http://localhost:8080/api/literature-search/traceability-links \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Link literature evidence to URS requirements" \
  -d '{
    "document_id": 42,
    "links": [
      {"target_type": "requirement", "target_id": 101, "rationale": "Supports biocompatibility claim"},
      {"target_type": "test_case", "target_id": 202, "rationale": "Evidence for OQ-3 acceptance criteria"}
    ]
  }'
```

Each link is stored with:
- `link_method: "literature_evidence"`
- `link_confidence: 1.0` (manual creation = full confidence)
- Optional rationale (max 1000 characters)

### Viewing and Filtering Links

Query traceability links via:
- Filter by `document_id` — "What requirements/tests does this paper support?"
- Filter by `target_id` — "What literature evidence supports this requirement?"

Links appear in the Traceability Matrix dashboard (Phase 5.6) as part of the coverage analysis.

### Constraints

- Only internalized documents can have traceability links (returns HTTP 422 otherwise)
- Only `document_admin` or `system_admin` can create/delete links
- Maximum 20 links per creation request

---

## Exporting Search Results

### Export Menu

Click the **Export** dropdown button (top-right) to generate a file:

| Format | Contents |
|--------|----------|
| **CSV** | Tabular data: title, authors (;-separated), publication_date, journal, source, publication_type, doi, abstract (300 chars), relevance_score, provenance, mesh_terms (;-separated) |
| **PDF** | Formatted report: search parameters header, results summary by source, tabular listing (title, authors, year, journal, doi), metadata footer with audit confirmation |

### PRISMA Flow Diagram

For PDF exports, check **"Include PRISMA flow (PDF)"** in the export menu. This adds a PRISMA-style flow section showing records identified per database, screening counts, and final inclusion count — useful for systematic literature review submissions.

### Audit Metadata

Every export includes:
- Export generation timestamp (UTC)
- Requesting user and company
- Statement confirming the search was executed against an audited literature index

---

## Audit Trail Integration

Every operation produces an immutable audit record:

| Operation | What's Logged |
|-----------|---------------|
| Search execution | Query text, filters, mode, sources queried, result count, duration (ms) |
| Internalization | User, ingestion_record_id, created document_id, timestamp |
| Collection modification | User, collection_id, document_ids added/removed |
| Traceability link CRUD | User, document_id, target_type, target_id, action |
| Export generation | User, format, search reference, result count |

Search execution logs (`SearchExecutionLog`) are append-only — they cannot be updated or deleted once recorded. This ensures search methodology evidence is tamper-proof for regulatory submissions.

If the audit service is temporarily unavailable, searches still return results. The audit log is retried via Celery (up to 3 attempts, 1-minute intervals).

---

## Access Control

| Operation | Required Role |
|-----------|--------------|
| Execute search, view results | `member` or above |
| Save/manage own searches | `member` or above |
| Export results (CSV/PDF) | `member` or above |
| Internalize literature | `document_admin` or `system_admin` |
| Manage citation collections | `document_admin` or `system_admin` |
| Create/delete traceability links | `document_admin` or `system_admin` |

All operations are scoped to the company identified by the `X-Company-Id` header. Data belonging to one company is never visible to another company.

---

## API Reference

All endpoints are prefixed with `/api/literature-search`. Mutations require `X-Change-Reason` header (enforced globally by AuditMiddleware).

### Search

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/query` | member+ | Execute faceted hybrid search |

### Saved Searches

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/saved-searches` | member+ | Save a search configuration |
| `GET` | `/saved-searches` | member+ | List saved searches (paginated) |
| `POST` | `/saved-searches/{id}/execute` | owner/admin | Re-execute a saved search |
| `DELETE` | `/saved-searches/{id}` | owner/admin | Archive a saved search |

### Internalization

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/internalize` | document_admin+ | Internalize a literature record |

### Citation Collections

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/citation-collections` | document_admin+ | Create collection |
| `GET` | `/citation-collections` | member+ | List collections |
| `GET` | `/citation-collections/{id}` | member+ | Get detail with documents |
| `PUT` | `/citation-collections/{id}` | document_admin+ | Update metadata |
| `DELETE` | `/citation-collections/{id}` | document_admin+ | Archive collection |
| `POST` | `/citation-collections/{id}/documents` | document_admin+ | Add documents (1–50) |
| `DELETE` | `/citation-collections/{id}/documents/{doc_id}` | document_admin+ | Remove document |

### Traceability Links

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/traceability-links` | document_admin+ | Create links (1–20) |
| `GET` | `/traceability-links` | member+ | List links (filterable) |
| `DELETE` | `/traceability-links/{id}` | document_admin+ | Delete a link |

### Export

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/export` | member+ | Generate CSV or PDF export |

---

## Configuration

These environment variables control Phase 9.6 behavior (all have defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `ALC_LITERATURE_MAX_SAVED_SEARCHES` | `200` | Max active saved searches per user per company |
| `ALC_LITERATURE_MAX_COLLECTION_DOCUMENTS` | `500` | Max documents per citation collection |
| `ALC_DOCUMENTS_BUCKET` | `alcoabase-documents` | MinIO bucket for internalized file copies |
| `ALC_LITERATURE_AUDIT_RETRY_MAX` | `3` | Celery retry attempts for failed audit writes |
| `ALC_LITERATURE_AUDIT_RETRY_DELAY_SECONDS` | `60` | Delay between audit retry attempts |
| `ALC_LITERATURE_EXPORT_PDF_ORIENTATION` | `landscape` | PDF export page orientation |

---

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|------------|
| Search returns HTTP 503 | OpenSearch unavailable | Check search index service in Admin → System Configuration |
| "Saved search limit reached" (422) | 200 active searches | Archive unused saved searches |
| "Collection capacity reached" (422) | 500 documents in collection | Create a new collection or remove unused entries |
| "Only internalized documents" (422) | Document lacks `source_ingestion_record_id` | The document was not created through internalization |
| Internalize returns 409 | Already internalized | The paper already exists as a Document; use the existing one |
| Export shows empty results | No results from search | Verify the search_execution_id references a completed search |
| Facet counts all zero | No indexed literature | Ensure Phase 9.2–9.3 ingestion and embedding pipeline is active |

---

## Related Guides

- [Literature Search Engine](literature-search-guide.md) — Configure external database gateways
- [Literature Ingestion Pipeline](literature-ingestion-guide.md) — Full-text retrieval and storage
- [Literature Embedding & Hybrid Search](literature-embedding-hybrid-search-guide.md) — Index management and search configuration
- [Traceability & Gap Discovery](traceability-gap-discovery-guide.md) — Traceability Matrix that receives literature evidence links
- [Audit Trail Viewer](audit-trail-viewer-guide.md) — View and export audit records including search execution logs
