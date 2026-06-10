# Automated Literature Ingestion Pipeline — User Guide

## Overview

The Automated Ingestion Pipeline (Phase 9.2) extends the Literature Search Engine by consuming search results and automatically retrieving, storing, and sanitizing full-text articles. It implements a dual-stage asynchronous workflow: metadata and abstracts are stored immediately, while full-text retrieval via the Unpaywall API proceeds in the background. Downloaded files (PDF, HTML, XML/JATS) are sanitized into a unified structured format and stored in MinIO with company-level isolation.

## Key Capabilities

- **Dual-stage pipeline**: metadata ingestion (instant) followed by full-text retrieval (async)
- **Unpaywall integration**: automatic open-access DOI resolution with priority-based URL selection
- **Multi-format sanitization**: PDF (PyMuPDF), HTML (BeautifulSoup), XML/JATS (lxml) normalized into a single schema
- **Per-company configuration**: storage quotas, retention policies, concurrent download limits
- **State machine lifecycle**: 7-state tracking from `metadata_only` through `indexed`
- **Company-isolated storage**: MinIO paths enforce tenant boundaries
- **Retention management**: automatic cleanup of expired original files (configurable)
- **Full audit trail**: every state transition, download, and sanitization is logged

---

## Getting Started

### Prerequisites

The ingestion pipeline requires Phase 9.1 (Literature Search Engine) to be active:

```env
ALC_LITERATURE_ENABLED=true
ALC_LITERATURE_ENCRYPTION_KEY=<your-key>
```

No additional feature flag is needed — the ingestion pipeline activates automatically when the literature gateway is enabled.

### 1. Configure Ingestion for Your Company

Before ingesting papers with full-text retrieval, configure your company's ingestion settings. You need the `document_admin` role.

```bash
curl -X PUT http://localhost:8080/api/literature/ingest/config \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Enable full-text ingestion" \
  -d '{
    "full_text_retrieval_enabled": true,
    "unpaywall_email": "admin@yourcompany.com",
    "storage_quota_mb": 10240,
    "retention_days": 365,
    "max_concurrent_downloads": 5,
    "dual_uuid_integration_enabled": false
  }'
```

The `unpaywall_email` is required by Unpaywall's fair-use policy when full-text retrieval is enabled.

### 2. Submit Papers for Ingestion

Submit up to 100 literature search results in a single batch:

```bash
curl -X POST http://localhost:8080/api/literature/ingest \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Ingest CRISPR review papers" \
  -d '{
    "results": [
      {
        "title": "CRISPR-Cas9 in Gene Therapy",
        "authors": ["Smith J", "Doe A"],
        "doi": "10.1000/example.2024",
        "source_id": "pubmed",
        "external_id": "PM39001234",
        "url": "https://pubmed.ncbi.nlm.nih.gov/39001234/",
        "abstract": "This review covers recent advances in CRISPR..."
      }
    ]
  }'
```

Response (HTTP 202):
```json
{
  "batch_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "submitted_count": 1,
  "duplicate_count": 0,
  "created_ids": [42]
}
```

The pipeline immediately begins processing asynchronously.

### 3. Monitor Ingestion Progress

Check the status of individual records:

```bash
# Single record
curl http://localhost:8080/api/literature/ingest/42 \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1"

# Batch status
curl http://localhost:8080/api/literature/ingest/batch/a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1"

# List with filters
curl "http://localhost:8080/api/literature/ingest?state=failed&page_size=20" \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1"

# Aggregated state counts
curl http://localhost:8080/api/literature/ingest/states \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1"
```

### 4. Retry Failed Records

If a record fails (network timeout, temporary publisher issue), retry it:

```bash
curl -X POST http://localhost:8080/api/literature/ingest/42/retry \
  -H "Authorization: Bearer <token>" \
  -H "X-User-Id: 1" \
  -H "X-Company-Id: 1" \
  -H "X-Change-Reason: Retry after Unpaywall timeout"
```

Records can be retried up to 3 times. The system automatically retries with exponential backoff during processing.

---

## Ingestion Lifecycle States

Each paper progresses through a well-defined lifecycle:

```
metadata_only → abstract_indexed → full_text_pending → full_text_downloaded → sanitized → indexed
                                                     ↘ failed (retryable)
```

| State | Description |
|-------|-------------|
| `metadata_only` | Record created with metadata, no abstract available |
| `abstract_indexed` | Metadata + abstract stored and searchable |
| `full_text_pending` | Full-text download task dispatched (awaiting Unpaywall) |
| `full_text_downloaded` | PDF/HTML/XML downloaded and stored in MinIO |
| `sanitized` | Content sanitized into StructuredContent format |
| `indexed` | Fully processed, available for search and extraction |
| `failed` | Processing failed (retryable from the stage that failed) |

---

## Storage and Quotas

### File Organization

Files are stored in MinIO under company-isolated paths:

```
alcoabase-literature/
  {company_id}/
    {record_id}/
      original/     ← Downloaded PDF/HTML/XML
      sanitized/    ← structured_content.json
```

### Quota Management

Monitor storage usage:

```bash
curl http://localhost:8080/api/literature/ingest/storage \
  -H "Authorization: Bearer <token>" \
  -H "X-Company-Id: 1"
```

Response:
```json
{
  "usage_bytes": 5368709120,
  "quota_bytes": 10737418240,
  "usage_percent": 50.0,
  "quota_warning": false,
  "file_counts_per_state": {"full_text_downloaded": 100, "sanitized": 85}
}
```

- At 90% usage: API responses include `quota_warning: true`
- At 100% usage: new downloads are rejected until space is freed

### Retention Policy

Original files are automatically cleaned up after the configured `retention_days` (default 365). Sanitized content and metadata are retained indefinitely. Set `retention_days: 0` for indefinite retention of original files.

---

## API Endpoints Reference

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| POST | `/api/literature/ingest` | member | Submit batch for ingestion |
| GET | `/api/literature/ingest` | member | List records (with filters/pagination) |
| GET | `/api/literature/ingest/{id}` | member | Single record detail |
| GET | `/api/literature/ingest/batch/{batch_id}` | member | Batch status |
| POST | `/api/literature/ingest/{id}/retry` | document_admin | Retry a failed record |
| GET | `/api/literature/ingest/config` | document_admin | Get ingestion configuration |
| PUT | `/api/literature/ingest/config` | document_admin | Update ingestion configuration |
| GET | `/api/literature/ingest/storage` | member | Storage usage and quota |
| GET | `/api/literature/ingest/states` | member | Aggregated state counts |
| GET | `/api/literature/ingest/health` | system_admin | Pipeline health status |

All mutation endpoints require the `X-Change-Reason` header.

---

## Configuration Reference

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ALC_UNPAYWALL_API_URL` | `https://api.unpaywall.org` | Unpaywall API base URL |
| `ALC_LITERATURE_BUCKET` | `alcoabase-literature` | MinIO bucket for literature files |
| `ALC_LITERATURE_MAX_FILE_SIZE_MB` | `100` | Maximum download file size (MB) |
| `ALC_LITERATURE_RETENTION_DAYS` | `365` | Default retention for original files |
| `ALC_LITERATURE_STORAGE_QUOTA_MB` | `10240` | Default per-company storage quota (MB) |
| `ALC_LITERATURE_QUEUE_NAME` | `literature_ingestion` | Celery queue for ingestion tasks |
| `ALC_LITERATURE_CLEANUP_CRON` | `0 2 * * *` | Retention cleanup schedule (cron) |
| `ALC_LITERATURE_USER_AGENT` | `AlcoaBase/1.0 (Literature Ingestion)` | User-Agent for outbound requests |

---

## Troubleshooting

### Papers stuck in `full_text_pending`

- Check that `unpaywall_email` is configured for the company
- Verify the Unpaywall API is reachable (check `/api/literature/ingest/health`)
- The circuit breaker may be open — wait 5 minutes for it to reset
- Check Celery worker logs for the `literature_ingestion` queue

### Downloads failing with `no_oa_available`

Not all papers have open-access versions. This is expected — the paper remains in `abstract_indexed` state with its metadata and abstract available for search.

### Storage quota exceeded

Increase the quota via the configuration endpoint, or wait for retention cleanup to free space. The cleanup task runs daily at 02:00 UTC by default.

### Sanitization errors (`ocr_required`)

PDFs that are scanned images with no extractable text cannot be sanitized automatically. These remain in `failed` state until OCR processing is available in a future release.
