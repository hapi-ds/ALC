# AI-Driven Change Impact Analysis

## Overview

Change Impact Analysis automatically detects when documents are updated and identifies which other documents and training tasks are affected by the change. It provides two core capabilities:

1. **Automated Dependency Mapping** — Builds a directed graph of relationships between documents (URS → MVP, SOP → Training Tasks, etc.) using cross-references, database links, and semantic similarity.

2. **Gap Analysis** — Performs section-level comparison between an updated document and its dependents, highlighting specific misalignments with severity ratings and AI-generated remediation suggestions.

The feature runs as background Celery tasks on the `ai_operations` queue, producing immutable audit reports that integrate with the existing ALCOA+ audit trail.

---

## Accessing Impact Analysis

Navigate to **Impact Analysis** in the sidebar (Activity icon). The dashboard shows:

- **Summary cards** — Total unresolved critical and major findings across all reports
- **Report list** — Paginated list of all impact analysis reports (newest first)
- **Notification badge** — Count of unacknowledged notifications requiring your attention

---

## Automatic Triggering

Impact analysis runs automatically when a new document version is uploaded, provided:

- The document status is **not** "Draft"
- The document is **not** a CSV validation record

The system enqueues the analysis within 5 seconds of the version creation event. If a previous analysis is still running for the same document (within 10 minutes), the new trigger is skipped to avoid conflicts.

---

## Manual Triggering

From any document's detail page, click **Run Impact Analysis** to manually trigger an analysis. The button shows real-time progress:

- Computing changes (0–10%)
- Querying dependencies (10–20%)
- Assessing impact (20–85%)
- Analyzing gaps (85–95%)
- Saving report (95–100%)

If an analysis is already in progress, you'll see an "Analysis Running" indicator with the current progress.

---

## Dependency Graph

### Building the Graph

The dependency graph maps relationships between documents. Build it via:

- **API**: `POST /api/impact-analysis/dependency-graph/build`
- **Scope**: "full" (rebuild everything) or "incremental" (only modified documents)

### Relationship Types

| Type | Confidence | Detection Method |
|------|-----------|-----------------|
| validates | 1.0 | Requirement ID cross-references between MVP/IQ/OQ/PQ and URS |
| references | 1.0 | Explicit document UUID citations or title mentions |
| implements | 1.0 | Test case IDs referencing requirement IDs |
| trains_on | 0.9 | TrainingTask records linking SOPs to training |
| derived_from | 0.9 | GenerationProvenance records from AI Document Generator |
| (semantic) | 0.5–0.8 | Embedding similarity above 0.5 threshold |

### Viewing Dependencies

The **Dependency Graph View** renders documents as color-coded nodes:

- 🔴 Red — Critical findings
- 🟠 Orange — Major findings
- 🟡 Yellow — Minor findings
- 🟢 Green — No findings

Use the filter dropdown to show only specific relationship types. Zoom and pan to explore large graphs (limited to 200 nodes with a truncation warning).

---

## Impact Reports

Each analysis produces an immutable report containing:

- **Change Delta** — What changed between document versions (sections added, modified, deleted) with significance classification (high/medium/low)
- **Affected Items** — Documents and training tasks impacted, with severity ratings and recommended actions
- **Gap Findings** — Specific section-level misalignments between the updated document and its dependents

### Severity Levels

| Severity | Meaning | Action |
|----------|---------|--------|
| Critical | Dependent document contradicts the updated source | Update required immediately |
| Major | Dependent document is missing content the source now requires | Update required |
| Minor | Dependent document uses outdated terminology but remains functionally correct | Review recommended |

### Candidate Prioritization

When a document has more than 50 downstream dependencies, the system prioritizes assessment by:
1. Confidence score (highest first)
2. Dependency type priority: validates > implements > references > trains_on > derived_from

---

## Gap Analysis

Gap analysis performs a detailed section-by-section comparison between two documents. Trigger it via:

- **API**: `POST /api/impact-analysis/gap-analysis`
- **Requirements**: A dependency edge with confidence ≥ 0.5 must exist between the documents

The **Gap Analysis Detail** view shows a side-by-side comparison:
- Left panel: Source section (what changed)
- Right panel: Target section (what needs updating)
- Below: AI-generated remediation suggestion

Gap findings are classified by type:
- **Missing** — No coverage exists in the target
- **Contradicts** — Target states the opposite of the source
- **Incomplete** — Target partially covers the requirement
- **Outdated** — Target references a superseded version

---

## Notifications

When critical or major findings are identified, the system creates notifications for the affected document's owner. Notifications appear in the notification panel and include:

- Affected document identifier
- Severity badge (Critical/Major)
- Change summary explaining why the document is affected
- **Acknowledge** button to mark as reviewed

Acknowledging a notification is idempotent — clicking it multiple times has no additional effect.

---

## Training Task Impact

When a document change affects training tasks:

- **Incomplete training tasks** are flagged for content review (major severity)
- **Completed training** is flagged for retraining if procedural or safety-critical changes are detected (critical severity)

The system automatically resets `is_completed` to false for affected training tasks when the recommended action is "retraining_required".

---

## Document Impact Status

Each document's detail page shows an inline **Impact Status** widget:

- ✅ **Up to date** — No unresolved critical or major findings
- ⚠️ **Needs review** — Outstanding critical/major findings exist
- Counts of outstanding critical and major findings
- Date of the last analysis

---

## Change Impact Analyst Agent

The system uses a specialized AI agent archetype ("Change Impact Analyst") configured for:

- Temperature: 0.2 (precise, evidence-based)
- Max tokens: 4096
- Dependency-type-aware strictness rules
- Structured JSON output for gap identification

If the Change Impact Analyst archetype is not found in the Agent Registry, the system falls back to the "Regulatory Compliance Auditor" with an appended prompt suffix. Fallback usage is recorded in job metadata.

---

## API Endpoints

All endpoints are prefixed with `/api/impact-analysis/` and require `X-Company-Id` and `Authorization` headers. Mutation endpoints (POST) require `X-Change-Reason`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/dependency-graph/build` | Trigger dependency graph build (202) |
| GET | `/dependency-graph` | List edges (paginated, filterable) |
| GET | `/dependency-graph/{uuid}` | Get document dependencies (grouped) |
| POST | `/trigger` | Manually trigger impact analysis (202/409) |
| POST | `/gap-analysis` | Trigger gap analysis (202/422/404) |
| GET | `/gap-analysis/{job_id}/results` | Get gap findings (200/202) |
| GET | `/reports` | List reports (paginated, filterable) |
| GET | `/reports/{report_id}` | Get full report (200/404/422) |
| GET | `/jobs/{job_id}/status` | Get job progress (200/404) |
| GET | `/notifications` | List unacknowledged notifications |
| POST | `/notifications/{id}/acknowledge` | Acknowledge notification (200/404) |
| GET | `/documents/{uuid}/status` | Get document impact status |

---

## Configuration

See `.env.example` for the relevant environment variables under the "AI-Driven Change Impact Analysis" section. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `IMPACT_ANALYSIS_TIMEOUT_SECONDS` | 600 | Hard timeout for the full analysis pipeline |
| `DEPENDENCY_GRAPH_BUILD_TIMEOUT_SECONDS` | 300 | Timeout for dependency graph builds |
| `GAP_ANALYSIS_TIMEOUT_SECONDS` | 180 | Timeout for gap analysis between document pairs |
| `IMPACT_ANALYSIS_MAX_CANDIDATES` | 50 | Maximum affected items assessed per job |
| `IMPACT_ANALYSIS_STALENESS_THRESHOLD_SECONDS` | 600 | Seconds before a processing job is considered stale |

---

## Troubleshooting

**Analysis stuck at "processing"**: If a job hasn't progressed in 10+ minutes, it's considered stale. A new trigger will be allowed. Check Celery worker logs for errors.

**No dependency edges found**: Run a full dependency graph build first. The graph needs to be built before impact analysis can identify affected documents.

**Gap analysis returns 422**: Ensure a dependency edge with confidence ≥ 0.5 exists between the two documents. Build the dependency graph if needed.

**Agent fallback warning in logs**: The Change Impact Analyst archetype YAML may be missing from `agents/archetypes/`. Verify `change-impact-analyst.yaml` exists and passes schema validation.
