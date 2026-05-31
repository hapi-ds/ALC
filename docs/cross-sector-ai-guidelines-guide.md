# Cross-Sector AI Regulatory Guidelines Guide

## Overview

The Cross-Sector AI Regulatory Guidelines service (Phase 8.4) generates a suite of AI usage policy documents tailored to regulated industries. It produces **4 guideline documents** within the ALC corporate governance environment:

1. **Master Cross-Sector Guideline** — Universal AI usage policies applicable across all industries
2. **Pharma/GMP Sector Module** — AI policies specific to pharmaceutical manufacturing (GMP)
3. **MedTech/ISO 13485 Sector Module** — AI policies specific to medical device development
4. **IVD/IVDR Sector Module** — AI policies specific to in-vitro diagnostics

Each document integrates with the AI Risk & Compliance Framework (Phase 8.1) to reference risk tier classifications, HITL requirements, and control measures. Documents are uploaded as governed documents with tags `["AI-Guidelines", "ALC-GOV"]` and the governance workflow applied.

---

## Prerequisites

- AlcoaBase must be running with the Setup Wizard completed (Phase 1.2)
- ALC Corporate Environment must be provisioned (Phase 8.2)
- AI Risk & Compliance Framework must be seeded (Phase 8.1)
- The `alc-doc-admin` user must exist

---

## Running the Generator

### Option 1: CLI Command

```bash
cd src/backend
uv run python -m alcoabase.scripts.generate_ai_guidelines
```

On success, prints a JSON report to stdout and exits with code 0:

```json
{
  "documents_created": [
    {
      "document_id": 15,
      "document_uuid": "2025-00015",
      "title": "AlcoaBase — AI Usage Guidelines: Cross-Sector Master Policy",
      "sector": "cross-sector",
      "version_number": 1,
      "tags_applied": ["AI-Guidelines", "ALC-GOV"],
      "workflow_state": "Draft",
      "is_new_document": true,
      "policy_section_count": 8
    },
    ...
  ],
  "total_documents": 4,
  "total_policy_sections": 28,
  "risk_tiers_referenced": ["High", "Medium", "Low"],
  "regulatory_frameworks_covered": ["ISO_27001", "ISO_9001", "EU_AI_Act", "GMP", "ISO_13485", "IVDR"],
  "total_duration_ms": 320
}
```

On failure, error details are printed to stderr as JSON and exit code is 1.

### Option 2: REST API

```
POST /api/admin/generate-guidelines
```

**Required headers:**

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {token}` (system_administrator or document_administrator) |
| `X-User-Id` | Your user ID |
| `X-Company-Id` | Your current company ID |
| `X-Change-Reason` | Reason for the operation (audit trail) |

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Success — returns `GuidelinesGenerationReport` JSON |
| 400 | Missing `X-Change-Reason` header |
| 401 | Not authenticated |
| 403 | Insufficient permissions |
| 409 | Generation already in progress (concurrent request) |
| 500 | Generation failed — returns error details |

---

## What Gets Generated

### Master Cross-Sector Guideline

The master document covers universal AI governance policies:

- AI system classification and risk tiering
- Human-in-the-loop (HITL) requirements per risk tier
- Data integrity requirements for AI operations (ALCOA+ alignment)
- Model validation and performance monitoring
- Change management for AI systems
- Incident reporting and corrective actions
- Training requirements for AI system users
- Audit trail requirements for AI operations

### Sector-Specific Modules

Each sector module extends the master policy with industry-specific requirements:

| Sector | Key Topics |
|--------|-----------|
| **Pharma/GMP** | GMP Annex 11 compliance, computerized system validation for AI, batch record integrity, deviation management |
| **MedTech/ISO 13485** | Design control integration, risk management (ISO 14971), clinical evaluation support, post-market surveillance |
| **IVD/IVDR** | Performance evaluation support, analytical validation, clinical evidence generation, notified body requirements |

### Risk Framework Integration

All guidelines reference the AI Risk & Compliance Framework (Phase 8.1):

- **High-risk operations** (Document Generation, Automated Auditing): Mandatory HITL review, full audit depth, 7-year retention
- **Medium-risk operations** (Training Material Generation, Impact Analysis): Blocking controls, standard audit depth
- **Low-risk operations** (RAG Knowledge Base, Search): Immediate return, summary audit depth

---

## Versioning & Idempotency

The service is fully idempotent:

- **First run**: Creates 4 new documents with version 1
- **Subsequent runs**: Creates new DocumentVersion records (version N+1) for each existing document
- Each document is evaluated independently — if one exists and another doesn't, the service handles both correctly
- Document workflow state is reset to "Draft" on each new version (requires re-approval)
- All operations execute within a single database transaction (all-or-nothing)

---

## Governance Integration

Generated documents automatically receive:

- **Tags**: `["AI-Guidelines", "ALC-GOV"]` — places them in the "Governance — AI Regulatory Guidelines" virtual folder
- **Workflow**: ALC Governance Document Lifecycle (Draft → Review → Approved → InTraining → Active → Retired)
- **Created by**: `alc-doc-admin` user
- **Change reason**: "AI Regulatory Guidelines Generation — Phase 8.4 automated governance document creation"

---

## Cross-References

The generated guidelines are automatically cross-referenced by other governance documents:

- The **URS** (Phase 8.3) references AI guidelines for compliance context
- The **User Guide** and **Admin Guide** (Phase 8.5) include AI Guidelines cross-references in AI-related sections
- If guidelines are unavailable when other documents are generated, a notice is included instead

---

## Concurrency Protection

A PostgreSQL advisory lock prevents concurrent generation. If two requests arrive simultaneously, the second receives a 409 (Conflict) response. The lock is automatically released at transaction end.

---

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| "ALC corporate environment not provisioned" | Phase 8.2 seed not run | Run `uv run python -m alcoabase.scripts.seed_alc_corporate` |
| "ALC Document Administrator user not found" | User provisioning failed | Re-run Phase 8.2 seed |
| "ALC Governance workflow not found" | Workflow not created | Re-run Phase 8.2 seed |
| "Risk framework data unavailable" | Phase 8.1 not seeded | Run the AI Risk Framework seed first |
| 409 Conflict | Another generation in progress | Wait for the current generation to complete |

---

## Related Features

- [AI Risk & Compliance Framework](ai-risk-compliance-framework-guide.md) — Risk tier definitions referenced by guidelines
- [ALC Corporate Environment](alc-corporate-environment-guide.md) — Provides the company, users, and workflow
- [Documentation Suite](documentation-suite-guide.md) — User & Admin Guides that cross-reference these guidelines
