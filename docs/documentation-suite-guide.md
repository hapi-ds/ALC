# Documentation Suite: User & Admin Guides

## Overview

The Documentation Suite service (Phase 8.5) generates two comprehensive guide documents for the AlcoaBase platform:

1. **AlcoaBase — Comprehensive User Guide** — End-user manual covering all platform capabilities
2. **AlcoaBase — Technical Administrator Guide** — System administration manual for platform management

Both documents are generated programmatically from deterministic template constants combined with dynamic cross-reference data from existing governance documents (URS, AI Guidelines). They are uploaded as governed documents with tags `["DOC-GUIDE", "ALC-GOV"]` and the governance workflow applied.

---

## Prerequisites

- AlcoaBase must be running with the Setup Wizard completed (Phase 1.2)
- ALC Corporate Environment must be provisioned (Phase 8.2)
- The `alc-doc-admin` user must exist
- The ALC Governance workflow must exist

Optional (for full cross-references):
- URS document (Phase 8.3) — enables requirement traceability references
- AI Guidelines documents (Phase 8.4) — enables AI compliance cross-references

---

## Running the Generator

### Option 1: CLI Command

```bash
cd src/backend
uv run python -m alcoabase.scripts.generate_documentation
```

On success, prints a JSON report to stdout and exits with code 0:

```json
{
  "documents_created": [
    {
      "document_id": 20,
      "document_uuid": "2025-00020",
      "title": "AlcoaBase — Comprehensive User Guide",
      "guide_type": "user_guide",
      "version_number": 1,
      "tags_applied": ["DOC-GUIDE", "ALC-GOV"],
      "workflow_state": "Draft",
      "is_new_document": true,
      "section_count": 14,
      "procedure_count": 28,
      "screenshot_placeholder_count": 28
    },
    {
      "document_id": 21,
      "document_uuid": "2025-00021",
      "title": "AlcoaBase — Technical Administrator Guide",
      "guide_type": "admin_guide",
      "version_number": 1,
      "tags_applied": ["DOC-GUIDE", "ALC-GOV"],
      "workflow_state": "Draft",
      "is_new_document": true,
      "section_count": 14,
      "procedure_count": 25,
      "screenshot_placeholder_count": 25
    }
  ],
  "total_documents": 2,
  "total_sections": 28,
  "total_procedures": 53,
  "cross_references_included": {
    "urs_references": true,
    "ai_guidelines_references": true
  },
  "total_duration_ms": 85
}
```

On failure, error details are printed to stderr as JSON and exit code is 1.

### Option 2: REST API

```
POST /api/admin/generate-documentation
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
| 200 | Success — returns `DocumentationGenerationReport` JSON |
| 400 | Missing `X-Change-Reason` header |
| 401 | Not authenticated |
| 403 | Insufficient permissions |
| 409 | Generation already in progress (concurrent request) |
| 500 | Generation failed — returns error details |

---

## User Guide Contents

The User Guide (12 sections, 28+ procedures) covers:

| Section | Topics |
|---------|--------|
| Getting Started | Login, navigation, dashboard, quick-start workflow |
| Document Management | Upload, bulk upload, virtual folders, versioning, metadata |
| Template Builder | Creating forms, field types, drag-and-drop, saving |
| Report Data Entry & PDF Extraction | Filling forms, offline PDFs, Dual-UUID extraction |
| Workflows | Document states, transitions, workflow history |
| Training Management | Assigned training, completing tasks, quiz interaction |
| Electronic Signatures | Re-authentication, signing, signature status |
| Search and Knowledge Base | Hybrid search, RAG, AI answers |
| AI Agent Interaction | Review reports, scorecards, severity, master auditor, training ecosystem |
| AI Document Generator | Templates, generation, reviewing output |
| Related Governance Documents | All ALC-GOV documents with UUID and state |
| Appendices | Keyboard shortcuts, glossary, troubleshooting, URS traceability |

---

## Admin Guide Contents

The Admin Guide (12 sections, 25+ procedures) covers:

| Section | Topics |
|---------|--------|
| Administration Overview | Roles, responsibilities, access levels |
| User Management | CRUD, role assignment, company assignment, activation, password, permissions |
| Role-Based Access Control | RBAC model, predefined roles, custom roles, inheritance |
| System Configuration | AI hardware, storage quotas, backup, health monitoring, service status |
| AI Model Layer Management | vLLM config, model weights, GPU/CPU/mock, embedding, OCR, timeouts |
| Storage and Backup | MinIO config, quotas, backup schedules, data retention |
| Audit Trail Administration | Viewing logs, filtering, export, interpreting entries |
| Compliance Monitoring | Scorecards, agent review config, regulatory frameworks, risk tiers |
| Agent Registry Management | YAML structure, add/modify agents, hot-reload, audit profiles |
| Workflow Administration | BPMN editor, workflow definitions, lifecycle config |
| Related Governance Documents | All ALC-GOV documents with UUID and state |
| Appendices | CLI reference, API endpoints, environment variables, glossary, troubleshooting |

---

## Content Quality Standards

Each section in both guides follows strict formatting:

- **Overview paragraph** — Plain language explanation (≥50 chars for User Guide, ≥80 chars for Admin Guide)
- **Procedure Blocks** — 3–15 numbered steps, each starting with a bold action verb and including an italic expected outcome
- **Screenshot Placeholders** — Markdown image references in format `![Alt text](screenshots/{section-slug}/{action-slug}.png)`
- **Tips / Prerequisites / Security Considerations** — Contextual guidance per section
- **Cross-Reference Block** — Links to related sections, URS requirements, and AI Guidelines

---

## Cross-Reference Behavior

The service dynamically queries for existing governance documents at generation time:

| Document | When Available | When Unavailable |
|----------|---------------|-----------------|
| Enhanced URS (Phase 8.3) | Includes `Implements: REQ-{MODULE}-{NN}` references in each section | Includes notice: "URS cross-references unavailable — generate URS (Phase 8.3) for full traceability" |
| AI Guidelines (Phase 8.4) | Includes AI Guidelines references in AI-related sections | Includes notice: "AI Usage Guidelines cross-references unavailable — generate guidelines (Phase 8.4) for compliance context" |
| All ALC-GOV documents | Listed in "Related Governance Documents" section with title, UUID, and workflow state | Empty state notice displayed |

**Inter-guide cross-references** are always included:
- User Guide → Admin Guide (e.g., "Contact your administrator — see Admin Guide Section")
- Admin Guide → User Guide (e.g., "This setting affects user experience as described in User Guide Section")

---

## Versioning & Idempotency

The service is fully idempotent:

- **First run**: Creates 2 new documents with version 1
- **Subsequent runs**: Creates new DocumentVersion records (version N+1) for each existing document
- Each guide is evaluated independently for existence
- Document workflow state is reset to "Draft" on each new version
- All operations execute within a single database transaction (all-or-nothing)
- Document header includes version number, ISO 8601 timestamp, and revision history table

---

## Governance Integration

Generated documents automatically receive:

- **Tags**: `["DOC-GUIDE", "ALC-GOV"]` — places them in the "Governance — Documentation Suite" virtual folder
- **Workflow**: ALC Governance Document Lifecycle (Draft → Review → Approved → InTraining → Active → Retired)
- **Created by**: `alc-doc-admin` user
- **Change reason**: "Documentation Suite Generation — Phase 8.5 automated governance document creation"
- **Document type**: "Documentation Guide"
- **Folder path**: `/governance/documentation-suite`

---

## Concurrency Protection

A PostgreSQL advisory lock prevents concurrent generation. If two requests arrive simultaneously, the second receives a 409 (Conflict) response. The lock is automatically released at transaction end.

---

## Recommended Execution Order

For complete cross-references across all governance documents, run the generators in this order:

```bash
# 1. Provision the ALC corporate environment
uv run python -m alcoabase.scripts.seed_alc_corporate

# 2. Generate the URS (provides requirement IDs for cross-references)
uv run python -m alcoabase.scripts.generate_urs_alc

# 3. Generate AI Guidelines (provides AI compliance references)
uv run python -m alcoabase.scripts.generate_ai_guidelines

# 4. Generate Documentation Suite (references both URS and AI Guidelines)
uv run python -m alcoabase.scripts.generate_documentation
```

---

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| "ALC corporate environment not provisioned" | Phase 8.2 seed not run | Run `uv run python -m alcoabase.scripts.seed_alc_corporate` |
| "ALC Document Administrator user not found" | User provisioning failed | Re-run Phase 8.2 seed |
| "ALC Governance workflow not found" | Workflow not created | Re-run Phase 8.2 seed |
| "Section X has insufficient content" | Content validation failure | Report as a bug — template constants need updating |
| 409 Conflict | Another generation in progress | Wait for the current generation to complete |
| Missing URS cross-references | URS not generated yet | Run `uv run python -m alcoabase.scripts.generate_urs_alc` first |
| Missing AI Guidelines references | Guidelines not generated yet | Run `uv run python -m alcoabase.scripts.generate_ai_guidelines` first |

---

## Related Features

- [ALC Corporate Environment](alc-corporate-environment-guide.md) — Provides the company, users, and workflow
- [Cross-Sector AI Guidelines](cross-sector-ai-guidelines-guide.md) — AI policy documents referenced by guides
- [AI Risk & Compliance Framework](ai-risk-compliance-framework-guide.md) — Risk tier governance referenced in admin guide
