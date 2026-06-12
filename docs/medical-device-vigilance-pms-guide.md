# Medical Device Vigilance & Post-Market Surveillance (Phase 9.5)

## Overview

Phase 9.5 introduces continuous, automated vigilance monitoring for medical device companies. It builds on the Literature Search Engine (Phase 9.1), Automated Ingestion Pipeline (Phase 9.2), High-Dimensional Embedding & Hybrid Search (Phase 9.3), and AI-Powered Literature Review & Synthesis Agents (Phase 9.4) to provide a complete post-market surveillance (PMS) system.

Five major capabilities are provided:

1. **Product Portfolio Management** — Register medical devices with regulatory metadata (UDI, device class, intended purpose, predicate devices). Vigilance monitoring is scoped to specific products.

2. **Vigilance Search Profiles** — Define targeted search strategies per product with Boolean query construction, MeSH terms, adverse event keywords, device identifiers, exclusion terms, and cron-based scheduling.

3. **Signal Detection & Severity Classification** — A specialized "Vigilance Analyst" AI agent evaluates newly retrieved literature for genuine safety signals and classifies severity (critical/major/minor) using MDR Article 87 criteria.

4. **GxP Alerting & Escalation** — Critical signals trigger automatic impact analysis, contradiction detection, admin notification, and SLR review inclusion as independent parallel tasks.

5. **Periodic Safety Reports** — Auto-generated reports documenting all vigilance activity within configurable time windows (monthly/quarterly/annually) for MDR/IVDR regulatory submissions.

---

## Prerequisites

- Phase 9.1 (Literature Search Engine) — enabled via `ALC_LITERATURE_ENABLED=true`
- Phase 9.2 (Automated Ingestion Pipeline) — for ingesting vigilance search results
- Phase 9.3 (Embedding & Hybrid Search) — for indexing and signal detection dispatch
- Phase 9.4 (Literature Review & Synthesis Agents) — for contradiction detection during escalation
- Phase 5.1 (Agent Registry) — provides the Vigilance Analyst archetype
- Phase 5.5 (Change Impact Analysis) — invoked during critical signal escalation

---

## Configuration

Add the following environment variables to your `.env` file (all have sensible defaults):

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `ALC_VIGILANCE_SEARCH_QUEUE` | `literature_ingestion` | non-empty string | Celery queue for vigilance search tasks |
| `ALC_VIGILANCE_SIGNAL_QUEUE` | `ai_operations` | non-empty string | Celery queue for signal detection tasks |
| `ALC_VIGILANCE_SIGNAL_CONFIDENCE_THRESHOLD` | `0.7` | 0.1–1.0 | Minimum confidence to persist a signal |
| `ALC_VIGILANCE_MAX_CONCURRENT_DETECTIONS` | `5` | 1–50 | Max concurrent signal detection tasks per company |
| `ALC_VIGILANCE_SEARCH_TIMEOUT` | `3600` | ≥300 | Search execution timeout in seconds |
| `ALC_VIGILANCE_SIGNAL_BATCH_SIZE` | `10` | 1–50 | Records per signal detection batch |
| `ALC_VIGILANCE_ESCALATION_RETRIES` | `3` | 1–10 | Retry attempts for escalation sub-tasks |
| `ALC_VIGILANCE_AUTO_REPORT_ENABLED` | `true` | true/false | Enable automatic periodic report generation |

The application refuses to start if numeric values are outside their valid ranges.

---

## Getting Started

### 1. Register a Medical Product

```
POST /api/vigilance/products
Headers: X-Company-Id, X-Change-Reason, Authorization
Body: {
  "name": "CardioMonitor X200",
  "device_class": "IIb",
  "intended_purpose": "Continuous cardiac monitoring for ICU patients",
  "udi": "UDI-CM-X200-001",
  "manufacturer_name": "MedTech Inc"
}
```

Valid device classes: `I`, `IIa`, `IIb`, `III`, `IVDR_A`, `IVDR_B`, `IVDR_C`, `IVDR_D`

### 2. Create a Vigilance Search Profile

```
POST /api/vigilance/products/{product_id}/profiles
Headers: X-Company-Id, X-Change-Reason, Authorization
Body: {
  "name": "Cardiac AE Monitoring",
  "search_terms": ["cardiac monitor malfunction", "CardioMonitor X200"],
  "mesh_terms": ["Heart Failure", "Cardiac Pacing, Artificial"],
  "adverse_event_keywords": ["device failure", "patient injury", "death"],
  "device_identifiers": ["UDI-CM-X200-001"],
  "exclusion_terms": ["animal model", "in vitro"],
  "schedule_cron": "0 6 * * 1"
}
```

The profile executes automatically every Monday at 6:00 AM (or any valid 5-field cron expression).

### 3. Monitor Signals

Signals are detected automatically when search results are ingested and indexed. View them at:

```
GET /api/vigilance/signals?severity=critical&disposition=under_review
```

### 4. Disposition Signals

Review and classify detected signals:

```
PUT /api/vigilance/signals/{signal_id}/disposition
Headers: X-Company-Id, X-Change-Reason, Authorization
Body: {
  "disposition": "confirmed",
  "confirmation_note": "Confirmed genuine safety signal per MDR Art 87(1)(a)"
}
```

Valid dispositions: `confirmed`, `dismissed`, `escalated`

### 5. Generate Periodic Reports

Reports can be generated on-demand or automatically based on configured schedule:

```
POST /api/vigilance/reports/generate
Headers: X-Company-Id, X-Change-Reason, Authorization
Body: {
  "product_id": 1,
  "period_start": "2025-01-01",
  "period_end": "2025-03-31"
}
```

Reports follow a lifecycle: `generated` → `reviewed` → `approved` → `submitted`

---

## API Endpoints

### Products & Profiles

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| POST | `/api/vigilance/products` | document_admin | Create a medical product |
| GET | `/api/vigilance/products` | member | List products (paginated) |
| GET | `/api/vigilance/products/{id}` | member | Get product with profiles and signal counts |
| PUT | `/api/vigilance/products/{id}` | document_admin | Update a product |
| DELETE | `/api/vigilance/products/{id}` | document_admin | Soft-delete (discontinue) |
| POST | `/api/vigilance/products/{id}/profiles` | document_admin | Create a search profile |
| GET | `/api/vigilance/products/{id}/profiles` | member | List profiles for a product |
| PUT | `/api/vigilance/profiles/{id}` | document_admin | Update a profile |
| POST | `/api/vigilance/profiles/{id}/execute` | document_admin | Trigger manual execution |

### Signals & Executions

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| GET | `/api/vigilance/signals` | member | List signals (paginated, filterable) |
| GET | `/api/vigilance/signals/{id}` | member | Get signal details |
| GET | `/api/vigilance/signals/summary` | member | Aggregate signal statistics |
| PUT | `/api/vigilance/signals/{id}/disposition` | document_admin | Update signal disposition |
| GET | `/api/vigilance/executions` | member | List search executions |
| GET | `/api/vigilance/executions/{id}` | member | Get execution details |

### Reports

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| GET | `/api/vigilance/reports` | member | List reports (paginated) |
| GET | `/api/vigilance/reports/{id}` | member | Get full report content |
| PUT | `/api/vigilance/reports/{id}/status` | document_admin | Advance report status |
| POST | `/api/vigilance/reports/generate` | document_admin | Generate a report (async) |

---

## Signal Severity Classification

The Vigilance Analyst agent classifies signals using regulatory-aligned criteria:

| Severity | Criteria | Regulatory Alignment |
|----------|----------|---------------------|
| **Critical** | Death, serious injury, serious public health threat, or systematic failure requiring FSCA | MDR Article 87(1) |
| **Major** | Non-serious adverse event, near-miss, or emerging trend that could escalate | MEDDEV 2.12/1 trend reporting |
| **Minor** | Isolated complaint or performance issue with low likelihood of patient harm | Monitoring only |

---

## Escalation Workflow

When a **critical** signal is detected and `critical_signal_auto_escalate` is enabled (default: true):

1. **Impact Analysis** — ImpactAnalysisService creates a mandatory change assessment task
2. **Contradiction Detection** — Cross-references literature against internal product documentation
3. **Admin Notification** — Immediate in-app alert to all document_admin and system_admin users
4. **SLR Inclusion** — Adds the record to any active systematic literature reviews for the same product

All four sub-tasks run independently — failure in one does not block the others.

---

## Periodic Safety Reports

Generated reports include 8 sections:

1. Product metadata (name, UDI, device class, intended purpose)
2. Reporting period dates
3. Search executions (parameters, sources, result counts)
4. Detected signals (severity, disposition, resolution notes)
5. Search strategy documentation (profiles, query logic)
6. Disposition matrix (every result classified exactly once)
7. Statistical summary (totals, trends, time-to-disposition)
8. Regulatory compliance (MDR/IVDR references, completeness statement)

The **disposition matrix invariant** ensures: `no_signal + signal_dismissed + signal_confirmed + signal_escalated = total_results_ingested`

---

## Multi-Tenancy & Access Control

- All operations are scoped via `X-Company-Id` header
- Cross-tenant access returns HTTP 404 (not 403) to prevent information leakage
- `X-Change-Reason` header required on all mutations (enforced by AuditMiddleware)
- UDI uniqueness is enforced per-company (same UDI allowed in different companies)

---

## Audit Trail

All vigilance operations produce structured audit log entries:

- Search execution events (parameters, results, duration)
- Signal creation events (severity, confidence, detection duration)
- Signal disposition changes (previous/new state, acting user, reason)
- Escalation events (sub-task invoked, success/failure)
- Report generation/status events (period, status, acting user)
- Product/profile mutations (changed fields, acting user)
- Retry attempts (task type, attempt number, backoff duration)

Audit entries never contain full literature content, LLM prompts, or LLM responses. All entries are append-only per ALCOA+ requirements.

---

## Agent Archetype

The **Vigilance Analyst** archetype (`agents/archetypes/vigilance-analyst.yaml`) is hot-reloaded at runtime via the existing watchfiles mechanism. Key configuration:

- Temperature: 0.05 (highly deterministic)
- Max tokens: 6,144
- Strictness: 0.95
- Knowledge scopes: Vigilance, MedicalDevice, AdverseEvent, PostMarketSurveillance, MDR, IVDR

---

## Database Tables

Phase 9.5 adds 6 tables (migration: `x1y2z3a4b5c6`):

- `vigilance_medical_products` — Product portfolio
- `vigilance_search_profiles` — Search configuration
- `vigilance_search_executions` — Execution audit records
- `vigilance_signals` — Detected safety signals
- `vigilance_configurations` — Per-company settings
- `vigilance_periodic_safety_reports` — Generated reports

Plus one column added to `literature_ingestion_records`:
- `vigilance_execution_id` — Links ingested records to their originating vigilance search

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Application won't start | Check env var ranges — confidence must be 0.1–1.0, timeout ≥300, batch_size 1–50 |
| No signals detected | Verify confidence threshold isn't too high; check that records reach `indexed` state |
| Duplicate execution skipped | Normal behavior — idempotency guard prevents overlapping runs |
| Escalation sub-task failed | Check audit logs — each sub-task retries independently with 5-min intervals |
| Empty period report | Expected — report documents the absence of activity for regulatory traceability |
