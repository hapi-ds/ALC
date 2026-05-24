# Multi-Agent "Always-On" Auditing Guide

## Overview

The Multi-Agent Auditing system provides automated, parallel document review by multiple AI auditor agents. When a document is submitted for review, it is dispatched to N configured auditor agents simultaneously. Each agent produces an independent review report with findings, severity ratings, and recommendations. A supervisory "Master Auditor" agent then synthesizes all individual reports into a unified executive summary with prioritized action items and an overall compliance score.

## Key Concepts

- **Review Session** — A single execution of the review pipeline for one document, containing individual agent reports and the master summary.
- **Audit Profile** — A company-scoped configuration that determines which auditor agents are assigned, what regulatory frameworks apply, and the required review quorum.
- **Quorum** — The minimum number of agent reviews that must complete before the Master Auditor produces a summary. If too many agents fail and quorum becomes impossible, the session is marked as Failed.
- **Compliance Score** — A numeric score (0.0–100.0) computed from findings weighted by severity: Critical=25, Major=10, Minor=3, Informational=0.5.
- **Missing Link** — A document in "Approved" or "Active" status that lacks required training records or electronic signatures.
- **Anomaly Alert** — A suspicious pattern detected in the audit trail (e.g., backdated signatures, workflow bypasses).

## Getting Started

### 1. Configure an Audit Profile

Before submitting documents for review, configure at least one audit profile for your company.

1. Navigate to the **Admin** section or use the API directly.
2. Create an audit profile with:
   - **Name** — A descriptive name (e.g., "GMP Full Review")
   - **Regulatory Frameworks** — Select applicable frameworks (ISO 13485, GMP, GDP, etc.)
   - **Assigned Agents** — Select which review-type agents will participate
   - **Quorum** — Minimum number of agents that must complete (must be ≤ number of assigned agents)
3. Mark one profile as the **default** for your company.

### 2. Submit a Document for Review

From any document detail page:

1. Click the **"Submit for Review"** button in the document header.
2. In the modal:
   - Select an audit profile (or leave blank to use the company default).
   - Enter a **change reason** (required for ALCOA+ compliance).
3. Click **Submit for Review**.

The system returns immediately with HTTP 202 (Accepted). The review runs asynchronously in the background.

### 3. Monitor Review Progress

Navigate to **Audit Reviews** in the sidebar (or `/reviews` route).

The dashboard shows all review sessions with:
- Document title and type
- Status badge (Pending → InProgress → Completed/Failed → Approved/Rejected)
- Compliance score (when completed)
- Finding counts by severity
- Submission date

**Real-time updates:** When viewing an in-progress session, the page polls every 10 seconds to show agent completion progress.

### 4. Review Results

Click any session to see the full detail view:

- **Progress Tracker** — Shows which agents have completed, with elapsed time per agent.
- **Master Auditor Summary** — The synthesized executive summary with:
  - Overall compliance score and risk band
  - Consensus findings (agreed upon by 2+ agents)
  - Contradictions (agents disagree on severity)
  - Prioritized action items
- **Individual Agent Reports** — Expandable cards showing each agent's findings table.
- **Agent Report Comparison** — Side-by-side view with synchronized scrolling. Consensus findings are highlighted in green, contradictions in red.
- **Severity Heatmap** — Grid visualization showing finding density by chapter and severity level.

### 5. Approve or Reject

Once a review session reaches "Completed" status:

1. Click **Approve** or **Reject**.
2. Enter a change reason (required for audit trail).
3. The session status updates to "Approved" or "Rejected".

### 6. Manage Action Items

Action items are generated from review findings and tracked on a kanban board:

- **Columns:** Open → In Progress → Resolved / Dismissed
- **Drag and drop** items between columns to update status (prompts for a change reason).
- Each item shows severity, title, description, and resolution notes.

## Compliance Scorecard

The **Audit Readiness** scorecard (visible on the review dashboard) shows:

- **Overall Score** — Average compliance score across all completed reviews in the last 90 days.
- **Risk Band** — Excellent (90–100), Good (75–89), Needs Attention (50–74), At Risk (25–49), Critical (0–24).
- **Trend** — Improving, stable, or declining (compares current 30-day average vs. previous 30 days).
- **Breakdown by Document Type** — Bar chart showing scores per document category.

## Missing Link Detection

The system proactively flags documents that are approved but missing compliance requirements:

- **Training gaps** — Users assigned to training tasks who haven't completed training for the current document version.
- **Signature gaps** — Documents whose workflow requires a PAdES signature but none exists.

Severity: **Critical** if both are missing, **Major** if either one is missing.

Access via: `GET /api/compliance/missing-links`

## Anomaly Detection

A background task runs every 15 minutes scanning the audit trail for suspicious patterns:

| Anomaly Type | Detection Rule | Severity |
|-------------|----------------|----------|
| Backdated Signature | Signature timestamp > 5 min before audit log entry | Critical |
| Workflow Bypass | Document status changed without workflow transition record | Critical |
| Bulk Approval | Same user approved > 10 documents in 1 hour | Major |
| Off-Hours Mutation | Mutating operations outside 06:00–22:00 | Minor |
| Rapid Version Churn | > 5 versions of same document in 1 hour | Minor |

Alerts are deduplicated (same event won't generate duplicate alerts within 24 hours).

To resolve an alert: provide a resolution note explaining the investigation outcome.

Access via: `GET /api/compliance/anomalies`

## API Reference

### Review Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/reviews` | Submit document for review (returns 202) |
| GET | `/api/reviews` | List sessions (paginated, filterable) |
| GET | `/api/reviews/{id}` | Get session detail with reports |
| POST | `/api/reviews/{id}/approve` | Approve completed session |
| POST | `/api/reviews/{id}/reject` | Reject completed session |
| GET | `/api/reviews/{id}/action-items` | List action items |
| POST | `/api/reviews/{id}/action-items` | Create action item |
| PATCH | `/api/reviews/{id}/action-items/{itemId}` | Update action item status |

### Audit Profiles

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/audit-profiles` | Create profile |
| GET | `/api/audit-profiles` | List profiles |
| GET | `/api/audit-profiles/frameworks` | List supported frameworks |
| GET | `/api/audit-profiles/{id}` | Get profile |
| PUT | `/api/audit-profiles/{id}` | Update profile |
| DELETE | `/api/audit-profiles/{id}` | Soft-delete profile |

### Compliance

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/compliance/scorecard` | Company compliance scorecard |
| GET | `/api/compliance/missing-links` | Documents with compliance gaps |
| GET | `/api/compliance/anomalies` | List anomaly alerts |
| PATCH | `/api/compliance/anomalies/{id}/resolve` | Resolve an alert |

All mutating endpoints require the `X-Change-Reason` header.

## Supported Regulatory Frameworks

- ISO 13485 (Medical devices QMS)
- GMP (Good Manufacturing Practice)
- GDP (Good Distribution Practice)
- GLP (Good Laboratory Practice)
- GCP (Good Clinical Practice)
- ISO 9001 (General QMS)
- ISO 14001 (Environmental management)
- 21 CFR Part 11 (FDA electronic records)
- EU GMP Annex 11 (EU computerized systems)
- IVDR (In Vitro Diagnostic Regulation)

## Master Auditor Archetype

The Master Auditor is a predefined agent archetype (`agents/archetypes/master-auditor.yaml`) with:
- Strictness: 0.95
- Temperature: 0.1 (highly deterministic)
- Max tokens: 8192
- Focus: compliance synthesis, consensus detection, contradiction flagging, score computation

It produces a structured JSON response containing the executive summary, consensus findings, contradictions, prioritized action items, and compliance score.

## Troubleshooting

**Review session stuck in "Pending":**
- Check that Celery workers are running (`celery -A alcoabase.tasks.celery_app worker`)
- Verify the vLLM inference service is healthy

**Session marked as "Failed":**
- Check the individual agent review error reasons in the session detail
- Common causes: inference timeout (30 min limit), connection errors, invalid LLM response

**No default audit profile error (422):**
- Create an audit profile and mark it as default for your company

**Anomaly alerts not appearing:**
- Verify Celery beat is running (`celery -A alcoabase.tasks.celery_app beat`)
- The scan runs every 15 minutes; check logs for errors
