# AI-Powered Traceability & Gap Discovery

## Overview

The Traceability & Gap Discovery module (Phase 5.6) automatically generates Traceability Matrices by crawling requirements documents (URS) and mapping them to test cases and validation results in target documents (IQ, OQ, PQ, MVP). It detects orphan requirements (requirements without test cases) and orphan test cases (tests without justifying requirements), computes coverage metrics, and integrates with Change Impact Analysis to flag stale links when requirements change.

## Key Concepts

- **Traceability Matrix** — A structured mapping between requirements and their corresponding test cases, stored as an immutable audit record.
- **Traceability Link** — A single mapping between one requirement and one test case, with a confidence score (0.0–1.0) and detection method.
- **Orphan Requirement** — A requirement with no corresponding test case (coverage gap).
- **Orphan Test Case** — A test case that doesn't trace back to any requirement (unjustified test).
- **Coverage Metrics** — Quantitative measures of traceability completeness including coverage percentage and compliance readiness score.
- **Stale Link** — A traceability link that may be outdated because the source requirement document was modified.

## Getting Started

### Navigating to Traceability

Click **Traceability** in the left sidebar (represented by the merge icon). The dashboard shows:

1. **Summary cards** — Overall coverage %, compliance readiness score, orphan requirement count, orphan test case count.
2. **Alert banner** — Unresolved critical/major alerts indicating stale traceability data.
3. **Coverage trend chart** — Historical coverage % and compliance score over time.
4. **Matrix list** — All generated matrices sorted newest first, with status badges.

### Generating a Traceability Matrix

1. Click **Generate Matrix** on the dashboard.
2. In the dialog:
   - Enter a **Matrix Name** (required, 1–200 characters).
   - Optionally add a **Description** (max 1000 characters).
   - Add **Source Documents** (requirements documents like URS) — up to 10.
   - Add **Target Documents** (test documents like IQ/OQ/PQ) — up to 20.
   - Enter a **Change Reason** (required for ALCOA+ compliance).
3. Click **Generate Matrix**. The system will:
   - Extract requirements from source documents using AI.
   - Extract test cases from target documents using AI.
   - Establish links via three-pass matching (exact ID → cross-reference → semantic similarity).
   - Detect orphan requirements and test cases.
   - Compute coverage metrics and compliance readiness score.
4. A progress indicator shows the current phase and percentage. Generation typically takes 30–60 seconds per document.

### Three-Pass Matching Strategy

Links are established using three methods in priority order:

| Pass | Method | Confidence | Description |
|------|--------|-----------|-------------|
| 1 | Exact ID Match | 1.0 | Requirement ID (e.g., "REQ-001") explicitly cited in test case text |
| 2 | Cross-Reference | 0.9 | Structural link detected via the Cross-Reference Service |
| 3 | Semantic Match | 0.5–1.0 | Embedding similarity above 0.5 threshold |

When the same requirement-test pair is found by multiple methods, the highest confidence is retained and all methods are recorded.

### Viewing Matrix Details

Click any matrix in the list to see:

- **Links table** — All traceability links with sortable columns, confidence badges (green ≥80%, yellow ≥50%, red <50%), and stale indicators.
- **Orphan Requirements tab** — Requirements without test coverage, classified by severity (critical/major/minor) with suggested actions.
- **Orphan Test Cases tab** — Tests without justifying requirements, classified by risk level (high/medium/low) with suggested actions.
- **Coverage Heatmap** — Source × target document grid showing per-pair coverage percentages.

### Understanding Orphan Classification

**Orphan Requirement Severity** (keyword-based precedence):
- **Critical** — Contains safety keywords (hazard, safety, sterility, alarm, interlock) or regulatory keywords (FDA, EMA, ISO, shall comply).
- **Major** — Contains functional keywords (shall perform, shall calculate, shall display).
- **Minor** — Contains informational keywords (should, may, optional, nice-to-have).

**Orphan Test Case Risk Level:**
- **High** — Validates safety functions, alarm verification, interlock tests.
- **Medium** — Verifies calculations, confirms workflows, validates data entry.
- **Low** — Checks display format, verifies label text, cosmetic verification.

### Coverage Metrics

The **Compliance Readiness Score** is a weighted composite:

```
Score = (Coverage % × 0.40)
      + (Avg Link Confidence × 100 × 0.25)
      + (Orphan Penalty × 0.20)
      + (Completeness × 0.15)
```

Where:
- Orphan Penalty = max(0, 100 − orphan_reqs × 5 − orphan_tcs × 3)
- Completeness = 100 if all documents had extractions, else proportional

The score is clamped to 0–100 and indicates readiness for regulatory submission.

### Traceability Alerts

When a document that is a source in an existing matrix is modified (detected via Change Impact Analysis), the system automatically:

1. Creates a **Traceability Alert** with severity based on the impact report findings.
2. For **critical** alerts, marks affected links as **stale** (visible as amber indicators in the links table).

**Resolving alerts:**
- **Links Verified** — You've confirmed the links are still valid. Clears stale markers.
- **Matrix Regenerated** — You've regenerated the matrix with updated documents. Clears stale markers.
- **No Action Needed** — The change doesn't affect traceability. Stale markers remain for visibility.

### Soft-Delete

Matrices can be soft-deleted (removed from list views but preserved as immutable audit records). Use the delete action on any matrix — this requires a change reason.

## API Reference

All endpoints are prefixed with `/api/traceability` and require `X-Company-Id` and `Authorization` headers. Mutation endpoints also require `X-Change-Reason`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/matrices/generate` | Trigger async matrix generation (202) |
| GET | `/matrices` | List matrices (paginated, filterable) |
| GET | `/matrices/{id}` | Get full matrix detail |
| GET | `/matrices/{id}/links` | Get traceability links (paginated) |
| GET | `/matrices/{id}/orphan-requirements` | Get orphan requirements |
| GET | `/matrices/{id}/orphan-test-cases` | Get orphan test cases |
| DELETE | `/matrices/{id}` | Soft-delete matrix (204) |
| GET | `/documents/{uuid}/coverage` | Get document coverage status |
| GET | `/coverage/summary` | Aggregated coverage summary |
| GET | `/coverage/history` | Coverage snapshots over time |
| GET | `/alerts` | List unresolved alerts |
| POST | `/alerts/{id}/resolve` | Resolve an alert |
| GET | `/jobs/{id}/status` | Job progress and status |

## Agent Configuration

The feature uses a **Traceability Analyst** agent archetype (`agents/archetypes/traceability-analyst.yaml`) configured with:
- Temperature: 0.15 (low for deterministic extraction)
- Max tokens: 4096
- Specialized system prompt for requirement/test case extraction and orphan classification

If the Traceability Analyst is unavailable, the system falls back to the Change Impact Analyst with a traceability-focused prompt suffix.

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| Matrix stuck at "processing" | Check Celery worker logs. The 600s hard timeout will mark it as partial_success. |
| "Partial success" status | One or more AI services were unavailable. Exact ID matches still work. Retry when services recover. |
| No semantic matches found | Ensure documents are indexed in the Knowledge Base (Phase 4.2). |
| Stale link indicators | A source document was modified. Regenerate the matrix or resolve the alert. |
| 409 on generate | A job is already processing for the same document set. Wait for it to complete. |
