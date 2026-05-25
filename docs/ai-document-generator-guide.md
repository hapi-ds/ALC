# AI Document Generator Guide

This guide covers the Template-Based AI Document Generator in AlcoaBase, which generates regulatory documents (URS, SOP, Protocol, Report, MVP) from registered Master Templates using AI-powered content synthesis.

---

## Overview

The AI Document Generator automates the creation of regulatory documents by combining:

- **Master Templates** — Existing .docx files that define the structural layout (headings, numbering, styles, placeholders)
- **Knowledge Base** — RAG-retrieved content from indexed documents for factual grounding
- **Reference Documents** — Explicitly selected source documents prioritized as primary material
- **AI Generation** — Section-by-section content synthesis using the Technical Writer agent archetype

The generated output preserves the template's formatting, includes a full provenance audit trail, and enters a mandatory human review workflow before becoming active in the document ecosystem.

---

## Key Concepts

| Concept | Description |
|---------|-------------|
| Master Template | A .docx file registered as a structural blueprint for generation |
| Template Analysis | Extracted section hierarchy, numbering, styles, placeholders, tables |
| Generation Job | An async background task that produces a document from a template |
| Provenance Record | Immutable audit trail capturing every detail of a generation event |
| Cross-Reference Map | Links between generated content and source document identifiers |
| Content Status | Review state: `pending_review` → `approved` or `rejected` |

---

## Workflow

```
Register Template → Analyze Structure → Start Generation → Monitor Progress
    → Review Output → Approve/Reject → Document enters ecosystem
```

### 1. Register a Template

Navigate to **Document Generator → Templates** and fill in the registration form:

- **Document ID** — The ID of an existing .docx document in AlcoaBase
- **Document Version ID** — The specific version to use as the template
- **Template Name** — A descriptive name (e.g., "URS Master Template v2")
- **Document Type Target** — The type of document this template produces (URS, SOP, Protocol, Report, MVP)

Registration triggers a background analysis job that extracts the template's structural layout. Once analysis completes, the template status changes to "ready".

### 2. View Template Analysis

Click any registered template card to view its structural analysis:

- **Section Hierarchy** — Headings with levels (H1–H4), indented to show nesting
- **Placeholder Markers** — Detected `{{IDENTIFIER}}` patterns that trigger specialized content generation
- **Paragraph Styles** — All styles found in the template
- **Table Structures** — Tables detected with column headers
- **Page Layout** — Margins, orientation, page size

### 3. Generate a Document

Navigate to **Document Generator → Generate** and configure:

- **Template** — Select from registered templates (must be in "ready" status)
- **Document Title** — Title for the generated document
- **Generation Instructions** — Describe what the AI should generate (scope, purpose, specific requirements)
- **Reference Document IDs** — Optional comma-separated IDs of documents to use as primary source material
- **Output Folder Path** — Where to store the generated .docx file

Click **Generate Document** to start the async generation pipeline.

### 4. Monitor Progress

The Job Progress Monitor shows real-time status:

- **Progress Bar** — 0% → 10% (template load) → 20% (KB retrieval) → 20–90% (section generation) → 95% (DOCX assembly) → 100% (storage)
- **Current Section** — Which section is being generated
- **Sections Completed** — N / Total count
- **Estimated Time Remaining** — Based on average section generation time
- **Status Badge** — Pending, Processing, Completed, or Failed

Progress updates automatically via 5-second polling.

### 5. Review Generated Documents

Navigate to **Document Generator → Review** to see all AI-generated documents:

- Filter by **Content Status** (Pending Review, Approved, Rejected)
- Filter by **Document Type** and **Date Range**
- Click **Review** on any pending document to approve or reject it
- **Approve** — Transitions the document to the standard BPMN workflow
- **Reject** — Marks the document as rejected (requires a comment explaining why)

Documents remain invisible to standard search until approved.

### 6. View Provenance

Navigate to **Document Generator → Provenance** to inspect the full audit trail:

- **Generation Metadata** — Agent archetype, parameters, total tokens, duration, timestamp
- **Source Documents** — UUIDs of all knowledge base documents used
- **Per-Section Provenance** — For each section: KB query used, chunks retrieved, token count, inference duration
- **Unverified References** — Any references in the output not found in the cross-reference map
- **Cross-References** — All extracted references grouped by type (requirements, test cases, sections)

---

## Placeholder Markers

Templates can contain placeholder markers that trigger specialized content generation:

| Marker | Output |
|--------|--------|
| `{{SECTION_CONTENT}}` | 1–10 paragraphs of prose |
| `{{REQUIREMENT_LIST}}` | Numbered requirement list (max 200 items) |
| `{{CROSS_REFERENCE_SECTION}}` | Table (≥5 items) or numbered list (<5 items) |
| `{{TABLE}}` | Header row + 2–50 data rows, max 8 columns |
| `{{PROCEDURE_STEPS}}` | Numbered procedure steps (max 50) |
| `{{RISK_ASSESSMENT}}` | Risk table with ID, Severity, Likelihood, RPN, Mitigation |

Unrecognized markers fall back to `SECTION_CONTENT` behavior. Maximum 50 placeholders per template.

---

## Cross-Reference Extraction

The system automatically extracts and validates references from source documents:

- **REQ-\d{1,5}** — Requirement identifiers
- **URS-\d{1,3}.\d{1,3}** — User requirement specification references
- **TC-\d{1,5}** — Test case identifiers
- **TEST-\d{1,5}** — Test identifiers
- **Section numbering** — Heading-level numbering (e.g., 1.2.3)

References found in generated text that don't exist in the cross-reference map are flagged as "unverified" in the provenance record.

---

## Generation Pipeline Details

The pipeline executes these stages in order:

1. **Load Template** (10%) — Fetch template analysis and .docx bytes from storage
2. **Retrieve Knowledge** (20%) — Query the knowledge base for relevant chunks (relevance ≥ 0.3, top 10 per section)
3. **Generate Sections** (20–90%) — For each section, build a prompt with context and call the LLM
4. **Assemble DOCX** (95%) — Preserve template formatting, substitute header/footer tokens, add Sources appendix
5. **Store & Record** (100%) — Upload to MinIO, create document records, write provenance

### Retry Logic

- Individual section failures retry once, then fall back to a placeholder paragraph
- Transient errors (connection, timeout) retry with exponential backoff (max 2 retries)
- Non-retryable errors (validation, hard timeout) fail the job immediately

### All-or-Nothing Guarantee

If provenance cannot be persisted, the entire generation job fails and no document is stored. This ensures every document in the system has a complete audit trail.

### Concurrent Generation Prevention

Only one generation job can be in "processing" status for a given (template_id, title, company_id) combination at any time. Duplicate requests return the existing job ID.

---

## Context Window Management

When generating each section, the system manages context to stay within limits:

- **Preceding sections** — Summarized to max 1000 tokens if total context exceeds 6000 tokens
- **KB chunks** — Trimmed to top 5 chunks (by relevance) when context exceeds limits
- **Reference documents** — Always appear before KB chunks in the prompt (prioritized as primary sources)

---

## Immutability & Audit Trail

Generation provenance records are **immutable** — they cannot be updated or deleted after creation:

- SQLAlchemy event listeners prevent UPDATE/DELETE operations at the application layer
- `ImmutableRecordError` is raised if any code attempts to modify provenance
- The `previous_generation_id` field links regenerations to their predecessors for version-to-version traceability

This satisfies GxP audit trail requirements (ALCOA+ compliance).

---

## API Endpoints

All endpoints require `X-Company-Id` header. Mutating endpoints require `X-Change-Reason`.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/templates/register` | Register a template (returns 202 with job_id) |
| GET | `/api/documents/templates` | List templates (paginated, filterable by type) |
| GET | `/api/documents/templates/{id}` | Get template with full analysis |
| POST | `/api/documents/generate-from-template` | Start generation (returns 202 with job_id) |
| GET | `/api/documents/generate-from-template/{job_id}/status` | Poll job progress |
| POST | `/api/documents/{id}/review` | Approve or reject a generated document |
| GET | `/api/documents/generated` | List generated documents (filterable) |
| GET | `/api/documents/{id}/provenance` | Get generation provenance |
| GET | `/api/documents/{id}/cross-references` | Get cross-reference entries |

---

## Configuration

The document generator uses the existing AI infrastructure (vLLM, Celery, MinIO). No additional environment variables are required beyond the standard AlcoaBase configuration.

Generation tasks run on the `ai_operations` Celery queue with:
- Template analysis: 120s soft time limit, 2 max retries
- Document generation: 600s soft time limit, 2 max retries

---

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| Template stuck in "analyzing" | Celery worker not running or .docx corrupted | Check Celery logs, verify .docx opens in Word |
| Generation fails at "Knowledge retrieval" | No indexed documents match the template's domain | Index relevant documents first via the Knowledge Base |
| "Concurrent job exists" error | Another generation for same template+title is running | Wait for it to complete or check the existing job status |
| Empty sections in output | LLM returned empty content after retry | Check vLLM health, review generation instructions for clarity |
| Unverified references in provenance | Generated text references IDs not in source documents | Review source documents or add missing reference docs |
