# AlcoaBase — Implementation Roadmap

> Each item will get its own spec (requirements → design → tasks) before implementation.
> Priority is based on: foundational dependencies first, then core workflows, then advanced AI features.

---

## Phase 1 — Foundation (must exist before anything else works)

- [ ] **1.1 Multi-Tenancy / Company Separation**
  Introduce a `Company` (tenant) entity. All documents, templates, workflows, training records, and agents are scoped to a company. Each company has its own regulatory context (MedTec, Supplier, Pharma, etc.), audit requirements, and user pool. Enables isolated document repositories per organization.

- [ ] **1.2 Setup Wizard**
  First-run flow: create root admin account, create initial company/tenant, configure AI hardware mode (GPU/CPU/mock), optionally seed demo data. Blocks access to the app until completed.

- [ ] **1.3 Authentication & Session Management (Frontend)**
  Login page, JWT token handling, protected routes, session expiry, logout. Connect to existing backend auth endpoints.

---

## Phase 2 — Core Document Lifecycle (frontend ↔ backend integration)

- [ ] **2.1 Document Upload & List (Frontend Integration)**
  Wire up the Documents page: fetch document list from API, implement upload flow (file picker → multipart POST → refresh list), display metadata, tags, and version info.

- [ ] **2.2 Virtual Folders (Frontend Integration)**
  Connect folder CRUD and tag-based filtering UI to backend. Allow creating, renaming, deleting folders and browsing documents within them.

- [ ] **2.3 Document Versioning UI**
  Display version history per document, allow uploading new versions with change reason, show diff metadata between versions.

- [ ] **2.4 Template Builder (Frontend — Drag & Drop)**
  Implement the JSON-driven form builder with `@hello-pangea/dnd`. Field palette, canvas, field configuration panel. Save template schema to backend.

- [ ] **2.5 Report Data Entry & PDF Extraction**
  Frontend form rendered from template schema. Submit field values. Upload offline PDF and trigger Dual-UUID extraction. Display extracted vs. entered data comparison.

---

## Phase 3 — Workflows, Training & Signatures

- [ ] **3.1 BPMN Workflow Visual Editor**
  Integrate a BPMN editor component (e.g., bpmn-js). Allow admins to design document lifecycles visually. Save/load BPMN XML to backend.

- [ ] **3.2 Workflow Execution & State Transitions (Frontend)**
  Show current document state, available transitions, trigger transitions with confirmation. Display workflow history timeline.

- [ ] **3.3 Training Management UI**
  List training tasks, mark completion, view training records per user/document. Enforce training-gated access in frontend routing.

- [ ] **3.4 Electronic Signatures UI**
  Re-authentication dialog with password verification. Trigger PAdES signing. Display signature status and certificate info on documents.

---

## Phase 4 — Search, Knowledge & AI Integration

- [ ] **4.1 Search UI Integration**
  Connect search page to hybrid search API. Display results with relevance scores, snippets, and faceted filtering by company/type/status.

- [ ] **4.2 RAG Knowledge Base UI**
  Chat-style interface for asking questions against documents. Show source citations with links to original documents. Conversation history.

- [ ] **4.3 AI Model Integration (vLLM Service Layer)**
  Implement actual LLM inference calls in the backend service layer (replace mock responses). Embedding generation for document indexing. OCR pipeline for scanned PDFs.

---

## Phase 5 — Multi-Agent Document Review System (NEW)

- [ ] **5.1 Agent Personality & Role Framework**
  Define agent auditor archetypes with configurable personalities, expertise domains, and review focus areas (e.g., "Regulatory Compliance Auditor", "Data Integrity Specialist", "Process Safety Reviewer", "Statistical Methods Auditor"). Store as YAML definitions with system prompts, temperature settings, and evaluation criteria.

- [ ] **5.2 Multi-Agent Review Orchestration**
  Implement a review pipeline: document is submitted for review → dispatched to N configured auditor agents in parallel → each agent produces an independent review report with findings, severity ratings, and recommendations. Configurable per company/document type (MedTec audits differ from supplier audits).

- [ ] **5.3 Master Auditor Summarization Agent**
  A supervisory agent that receives all individual review reports, identifies consensus findings, flags contradictions between auditors, produces a unified executive summary with prioritized action items, and assigns an overall compliance score.

- [ ] **5.4 Review Dashboard & Findings UI**
  Frontend page showing: review status per document, individual agent reports side-by-side, master summary, finding severity heatmap, action item tracking, and approval/rejection workflow for review outcomes.

- [ ] **5.5 Company-Specific Audit Profiles**
  Each company/tenant gets configurable audit profiles that determine: which auditor agents are assigned, what regulatory frameworks apply (ISO 13485, GMP, GDP, ISO 9001, etc.), severity thresholds, and required review quorum before a document can be approved.

---

## Phase 6 — Admin & System Management

- [ ] **6.1 Admin Dashboard — User Management**
  CRUD for users, role assignment, company assignment, activation/deactivation. Password reset flow.

- [ ] **6.2 Admin Dashboard — System Configuration**
  AI hardware settings, storage quotas, backup configuration, system health monitoring, service status overview.

- [ ] **6.3 Audit Trail Viewer**
  Searchable, filterable audit log UI. Who did what, when, why. Export to PDF for regulatory submissions.

---

## Phase 7 — Validation & Compliance

- [ ] **7.1 CSV Validation Runner Integration**
  Trigger Playwright E2E validation from the UI. Show progress, results, and generated validation certificate. Per-company validation scoping.

- [ ] **7.2 Traceability Matrix**
  Auto-generated matrix linking requirements → test cases → results. Exportable for FDA/EMA audit submissions.

---

## Notes

- Each item above will become a dedicated spec in `.kiro/specs/{feature-name}/`
- Implementation order within a phase can be parallelized where no dependencies exist
- Company separation (1.1) is foundational — almost everything else depends on it
- The multi-agent review system (Phase 5) depends on AI integration (4.3) being functional
- Frontend integration tasks (Phase 2–3) can proceed in parallel with AI work (Phase 4–5)
