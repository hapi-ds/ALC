# Literature Review & Synthesis Agents (Phase 9.4)

## Overview

Phase 9.4 introduces AI-powered agents that automate systematic literature review (SLR) workflows and detect contradictions between newly published research and your internal SOPs, URS documents, and validation plans.

Two major capabilities are provided:

1. **Literature Screener Agent** — Screens ingested papers against user-defined PICO criteria and custom inclusion/exclusion rules, producing structured verdicts (include/exclude/uncertain) with confidence scores and rationale.

2. **Contradiction & Novelty Detection** — Automatically cross-references newly indexed literature against internal corporate documents. Identifies contradictions that may require process updates and flags novel findings not yet covered internally.

---

## Prerequisites

- Phase 9.1 (Literature Search Engine) — enabled via `ALC_LITERATURE_ENABLED=true`
- Phase 9.2 (Automated Ingestion Pipeline) — papers must be ingested
- Phase 9.3 (Embedding & Hybrid Search) — papers must be indexed with embeddings
- Phase 5.1 (Agent Registry) — provides the Literature Screener archetype

---

## Configuration

Add the following environment variables to your `.env` file (all have sensible defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `ALC_LITERATURE_SCREENING_QUEUE` | `ai_operations` | Celery queue for screening tasks |
| `ALC_LITERATURE_CONTRADICTION_QUEUE` | `ai_operations` | Celery queue for contradiction tasks |
| `ALC_CONTRADICTION_SIMILARITY_THRESHOLD` | `0.6` | Min similarity to match internal docs (0.0–1.0) |
| `ALC_CONTRADICTION_MAX_CANDIDATES` | `10` | Max internal docs to compare per paper (1–50) |
| `ALC_CONTRADICTION_CONFIDENCE_THRESHOLD` | `0.7` | Min confidence to create a contradiction alert (0.0–1.0) |
| `ALC_SCREENING_TASK_TIMEOUT` | `1800` | Soft time limit per screening task in seconds (60–7200) |
| `ALC_SCREENING_MAX_CONCURRENT` | `5` | Max concurrent screening tasks per company (1–20) |

---

## Concepts

### Screening Protocol

A reusable definition of inclusion/exclusion criteria for an SLR. Supports:
- **PICO criteria** — Population, Intervention, Comparison, Outcome (free-text, up to 2000 chars each)
- **Custom inclusion criteria** — Up to 20 keyword patterns or regex rules
- **Custom exclusion criteria** — Up to 20 keyword patterns or regex rules
- **Date range filtering** — Restrict to papers published within a date range
- **Publication type filtering** — e.g., article, review, meta-analysis, conference paper
- **Language filtering** — ISO 639-1 codes

Protocols have a lifecycle: `draft` → `active` → `archived`. Only active protocols can be used for screening.

### SLR Review

A workflow instance that tracks screening progress for a set of papers against a specific protocol. Lifecycle:

```
protocol_defined → screening_in_progress → screening_complete → human_review_in_progress → completed
```

### Screening Decision

The output of the Literature Screener Agent for each paper. Contains:
- **Verdict**: include, exclude, or uncertain
- **Confidence**: 0.0–1.0
- **Rationale**: explanation of the decision
- **Matched criteria**: which inclusion/exclusion criteria matched

Decisions are append-only — re-screening creates new decisions without modifying previous ones.

### Contradiction Alert

Created when the system detects that a newly indexed paper contradicts an internal document. Classified by severity:
- **Critical** — Contradicts validated process steps, safety parameters, or regulatory claims. Auto-escalated to ImpactAnalysisService.
- **Major** — Could invalidate assumptions but no direct contradiction of validated parameters.
- **Minor** — Suggests improvements without contradicting validated parameters.

Lifecycle: `new` → `acknowledged` → `resolved` or `dismissed`.

### Novelty Flag

Created when a newly indexed paper covers topics not addressed by any internal document (no semantic match found). Includes a relevance score; flags with score ≥ 0.8 are marked high-priority.

Lifecycle: `new` → `acknowledged` → `integrated` or `dismissed`.

---

## Workflow: Systematic Literature Review

### 1. Create a Screening Protocol

```
POST /api/literature/screening/protocols
X-Company-Id: {company_id}
X-Change-Reason: "Initial protocol for Q1 2025 diabetes SLR"

{
  "name": "GLP-1 Agonists SLR Protocol",
  "pico_criteria": {
    "population": "Adults with type 2 diabetes",
    "intervention": "GLP-1 receptor agonists",
    "comparison": "Placebo or standard care",
    "outcome": "HbA1c reduction"
  },
  "inclusion_criteria": ["randomized controlled trial", "published after 2020"],
  "exclusion_criteria": ["animal study", "pediatric population"],
  "publication_date_from": "2020-01-01",
  "allowed_publication_types": ["article", "review", "meta-analysis"]
}
```

### 2. Activate the Protocol

```
POST /api/literature/screening/protocols/{protocol_id}/activate
X-Change-Reason: "Protocol reviewed and approved by QM"
```

### 3. Create an SLR Review

```
POST /api/literature/reviews
X-Change-Reason: "Initiating Q1 2025 diabetes literature review"

{
  "protocol_id": 1,
  "name": "Q1 2025 GLP-1 Literature Review",
  "record_filter": { "state": "indexed" }
}
```

### 4. Initiate Screening

```
POST /api/literature/reviews/{review_id}/screen
X-Change-Reason: "Starting batch screening"

?batch_size=20
```

Returns HTTP 202 with a `task_id` for progress tracking.

### 5. Monitor Progress

```
GET /api/literature/reviews/{review_id}/progress
```

Returns real-time counts: total, screened, pending, include/exclude/uncertain, estimated time remaining.

### 6. Review Decisions & Apply Human Overrides

```
GET /api/literature/reviews/{review_id}/decisions?verdict=uncertain
```

Override uncertain decisions:
```
PUT /api/literature/reviews/{review_id}/decisions/{decision_id}/override
X-Change-Reason: "Manual review: paper relevant to our population"

{
  "human_verdict": "include",
  "human_rationale": "Paper covers our target population after closer reading"
}
```

### 7. Generate Report

```
GET /api/literature/reviews/{review_id}/report
```

Returns a comprehensive SLR report with PRISMA flow statistics, screening metrics, rationale summaries, and inter-rater reliability (Cohen's kappa).

---

## Workflow: Contradiction Detection

Contradiction detection runs automatically when a paper reaches the `indexed` state (after embedding generation). No manual action is required.

### Automatic Triggers

When a paper is indexed:
1. If `contradiction_detection_enabled = true` (default): dispatches a cross-reference task
2. If `auto_screen_on_index = true`: dispatches screening against all active protocols

### Viewing Contradictions

```
GET /api/literature/contradictions?severity=critical&status=new
```

### Acknowledging & Resolving

```
PUT /api/literature/contradictions/{alert_id}/status
X-Change-Reason: "Acknowledged critical finding — initiating SOP review"

{ "status": "acknowledged" }
```

```
PUT /api/literature/contradictions/{alert_id}/status
X-Change-Reason: "SOP-001 updated to reflect new stability data"

{
  "status": "resolved",
  "resolution_note": "Updated storage conditions in SOP-001 Section 4.2",
  "change_request_id": 42
}
```

### Viewing Novelty Flags

```
GET /api/literature/novelty?high_priority=true
```

---

## Per-Company Configuration

Each company can customize screening behavior:

```
GET /api/literature/screening/config      (requires document_admin)
PUT /api/literature/screening/config      (requires system_admin)
```

Configurable settings:
- `auto_screen_on_index` — Automatically screen papers when indexed (default: false)
- `default_batch_size` — Records per screening batch, 1–100 (default: 20)
- `confidence_threshold` — Auto-include threshold, 0.5–1.0 (default: 0.8)
- `max_concurrent` — Max parallel screening tasks, 1–20 (default: 5)
- `contradiction_detection_enabled` — Enable cross-referencing (default: true)

---

## PRISMA Flow Statistics

The system maintains real-time PRISMA (Preferred Reporting Items for Systematic Reviews) statistics:

- **Records identified** — Total papers submitted to the review
- **Records screened** — Papers that have received a screening decision
- **Records eligible** — Papers with include or uncertain verdict
- **Records included (final)** — Confirmed by human or high-confidence AI
- **Records excluded with reasons** — Grouped by exclusion category

---

## Inter-Rater Reliability

When human overrides exist, the system computes:
- **Agreement rate** — Percentage of AI decisions confirmed by humans
- **Cohen's kappa** — Standardized measure of agreement beyond chance
- **Per-criterion false positive/negative rates** — Which criteria the AI gets wrong most often

---

## Role Requirements

| Action | Minimum Role |
|--------|-------------|
| View protocols, reviews, decisions, alerts | `member` |
| Create/update/delete protocols | `document_admin` |
| Initiate screening, override decisions | `document_admin` |
| Update alert/flag status | `document_admin` |
| Dismiss alerts | `document_admin` |
| Read screening configuration | `document_admin` |
| Update screening configuration | `system_admin` |

---

## Audit Trail

All operations are logged to the structured audit trail:
- Screening decisions (verdict, confidence, model name, duration)
- Human overrides (original vs. new verdict, reviewer)
- Contradiction alert creation and status changes
- Novelty flag creation
- SLR review state transitions
- Retry attempts with backoff details

Paper content, internal document content, and LLM prompts/responses are never logged.

---

## Agent Archetype

The Literature Screener agent is defined at `agents/archetypes/literature-screener.yaml` and is hot-reloaded via the existing watchfiles mechanism. Key tuning parameters:

- Temperature: 0.1 (highly deterministic)
- Max tokens: 4096
- Strictness: 0.9
- Evaluation rubric: screening accuracy (35%), rationale quality (25%), criteria coverage (20%), consistency (10%), formatting (10%)
