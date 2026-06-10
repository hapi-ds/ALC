# Literature Search Engine — User Guide

## Overview

The Literature Search Engine (Phase 9.1) enables AlcoaBase to query external scientific databases — PubMed, Crossref, and arXiv — through a secure, multi-tenant gateway. This is AlcoaBase's first feature with controlled outbound network access, designed for environments where access to external literature is needed while maintaining full audit traceability and data integrity.

## Key Capabilities

- **Multi-source parallel search** across PubMed, Crossref, and arXiv
- **Per-company configuration** of API keys, rate limits, and source priorities
- **AES-256-GCM encryption** for all stored API keys
- **Hierarchical rate limiting** (system-wide and per-company) to respect API provider policies
- **Circuit breaker resilience** to gracefully handle external API failures
- **Full audit trail** for every outbound API call (GxP compliance)
- **Plugin architecture** — add new literature sources without code changes
- **Proxy support** for controlled external access through corporate firewalls
- **Async search** for long-running queries via Celery

---

## Getting Started

### 1. Enable the Feature

Set the following environment variables before starting the application:

```env
ALC_LITERATURE_ENABLED=true
ALC_LITERATURE_ENCRYPTION_KEY=<base64-encoded-32-byte-key>
```

Generate an encryption key:

```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

The application refuses to start if `ALC_LITERATURE_ENABLED=true` but the encryption key is missing.

### 2. Configure Source Adapters

Each company configures their own literature sources via the API:

```bash
# Create a PubMed configuration for company ID 1
curl -X POST http://localhost:8080/api/literature/sources/1/configurations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Initial PubMed setup" \
  -d '{
    "source_adapter_name": "pubmed",
    "is_enabled": true,
    "api_key": "your-ncbi-api-key",
    "priority": 1,
    "contact_email": "admin@yourcompany.com"
  }'
```

Repeat for Crossref and arXiv as needed. API keys are encrypted before storage and never returned in plaintext.

### 3. Create a Search Profile (Optional)

Search profiles define default source selections per company:

```bash
curl -X POST http://localhost:8080/api/literature/sources/1/profiles \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Set pharma default profile" \
  -d '{
    "name": "pharma_default",
    "is_default": true,
    "enabled_sources": ["pubmed", "crossref"],
    "source_priorities": {"pubmed": 1, "crossref": 2},
    "default_filters": {}
  }'
```

Pre-built templates are available: `pharma_medtech`, `technical_supplier`, `general`.

---

## Searching Literature

### Basic Search

```bash
curl -X POST http://localhost:8080/api/literature/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Literature review for SOP-042" \
  -d '{
    "terms": "CRISPR gene therapy clinical trials",
    "page_size": 20,
    "page": 1
  }'
```

### Filtered Search

```bash
curl -X POST http://localhost:8080/api/literature/search \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Regulatory literature review" \
  -d '{
    "terms": "drug stability testing",
    "sources": ["pubmed", "crossref"],
    "date_from": "2022-01-01",
    "date_to": "2024-12-31",
    "publication_types": ["journal_article", "review"],
    "page_size": 50
  }'
```

### Async Search

Searches targeting more than 3 sources or requesting more than 50 results are automatically dispatched as background tasks. The API returns HTTP 202 with a task ID:

```json
{
  "task_id": "abc123-def456",
  "status": "queued",
  "status_url": "/api/literature/tasks/abc123-def456"
}
```

Poll the status endpoint:

```bash
curl http://localhost:8080/api/literature/tasks/abc123-def456 \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"
```

Cancel a running task:

```bash
curl -X DELETE http://localhost:8080/api/literature/tasks/abc123-def456 \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: No longer needed"
```

---

## Search Results

Results are normalized into a consistent format regardless of source:

| Field | Description |
|-------|-------------|
| `title` | Publication title (max 2000 chars) |
| `authors` | List of author names (preserving source ordering) |
| `abstract` | Publication abstract (may be empty) |
| `doi` | Digital Object Identifier (may be null) |
| `publication_date` | ISO 8601 date |
| `source_id` | Which adapter produced this result (pubmed, crossref, arxiv) |
| `external_id` | Source-specific ID (PMID, DOI, arXiv ID) |
| `journal_or_venue` | Journal or conference name |
| `publication_type` | journal_article, preprint, conference_paper, review, other |
| `url` | Direct link to the source record |
| `date_precision` | day, month, or year (original date granularity) |

Results are deduplicated by DOI across sources (keeping the highest-priority source version). Results without a DOI are always included.

---

## Administration

### Rate Limits (System Admin)

View and update system-level rate limits:

```bash
# View all rate limits
curl http://localhost:8080/api/literature/admin/rate-limits \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"

# Update PubMed rate limit
curl -X PUT http://localhost:8080/api/literature/admin/rate-limits/pubmed \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Increased limit with API key" \
  -d '{"requests_per_second": 100}'
```

Default system limits follow published API policies:
- PubMed: 10 RPS (unauthenticated) / 100 RPS (with API key)
- Crossref: 50 RPS (polite pool)
- arXiv: 1 request per 3 seconds

### Proxy Configuration (System Admin)

Configure an HTTP/HTTPS proxy for outbound requests:

```bash
curl -X PUT http://localhost:8080/api/literature/admin/proxy \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Configure corporate proxy" \
  -d '{
    "proxy_url": "http://proxy.corp.example.com:8080",
    "username": "proxyuser",
    "password": "proxypass",
    "no_proxy_list": ["localhost", "10.0.0.0/8"],
    "is_active": true
  }'
```

### Health Monitoring (System Admin)

```bash
curl http://localhost:8080/api/literature/health \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"
```

Returns per-source health status: available (< 5s response), degraded (5–15s), or unreachable (> 15s or error). Sources unreachable for more than 30 minutes are flagged for attention.

### Company Usage (Document Admin)

```bash
curl http://localhost:8080/api/literature/usage/1 \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1"
```

---

## Role-Based Access

| Action | Required Role |
|--------|--------------|
| Search literature | member |
| View source registry | member |
| Configure sources / profiles | document_admin |
| Manage rate limits / proxy | system_admin |
| View health status | system_admin |
| View company usage | document_admin |

---

## Adding Custom Adapters

To add a new literature source without modifying core code:

1. Create a Python file in the configured adapter directory (default: `src/backend/src/alcoabase/literature/adapters/`)
2. Implement a class inheriting from `BaseSourceAdapter` with all required methods:
   - `search(query, api_key, timeout)` → list of normalized results
   - `get_metadata(external_id)` → dict of metadata
   - `health_check()` → response time in seconds
   - `get_capabilities()` → supported query features
   - `get_adapter_metadata()` → name, version, display_name, requires_api_key
3. Restart the application — the adapter is automatically discovered and registered

---

## Error Handling

| HTTP Status | Meaning |
|-------------|---------|
| 200 | Synchronous search completed successfully |
| 202 | Search dispatched asynchronously (check task status) |
| 400 | Missing X-Change-Reason header on mutation |
| 403 | Insufficient role permissions |
| 404 | Resource not found |
| 429 | Rate limit exceeded (check Retry-After header) |
| 503 | All sources unavailable or feature disabled |

When some sources fail but others succeed, results from responding sources are returned with a `partial_results` field listing timed-out, errored, and unavailable sources.

---

## Audit Trail

Every outbound API call is recorded in the audit log with:
- Request timestamp, source adapter, target URL (API keys redacted)
- Response timestamp, HTTP status, result count, response time
- Error type and message on failure (secrets never logged)
- Originating user ID, company ID, and query ID for full traceability

Audit records are viewable through the Audit Trail Viewer (Phase 6.3).
