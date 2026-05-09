# AlcoaBase — Implementation Roadmap

> Each item will get its own spec (requirements → design → tasks) before implementation.
> Priority is based on: foundational dependencies first, then core workflows, then advanced AI features.

> Read and understand todo.md and generate spec for Phase x.x in a way that is good / correct for all other phases.

---

## Phase 1 — Foundation (must exist before anything else works)

- [x] **1.1 Multi-Tenancy / Company Separation**
  Introduce a `Company` (tenant) entity. All documents, templates, workflows, training records, and agents are scoped to a company. Each company has its own regulatory context (MedTec, Supplier, Pharma, etc.), audit requirements, and user pool. Enables isolated document repositories per organization.

- [x] **1.2 Setup Wizard**
  First-run flow: create root admin account, create initial company/tenant, configure AI hardware mode (GPU/CPU/mock), optionally seed demo data. Blocks access to the app until completed.

- [x] **1.3 Authentication & Session Management (Frontend)**
  Login page, JWT token handling, protected routes, session expiry, logout. Connect to existing backend auth endpoints.

---

## Phase 2 — Core Document Lifecycle (frontend ↔ backend integration)

- [x] **2.1 Document Upload & List (Frontend Integration)**
  Wire up the Documents page: fetch document list from API, implement upload flow (file picker → multipart POST → refresh list), display metadata, tags, and version info. Bulk document upload from a whole document tree (import of all documents of a company) - can also be a separate small python programm running at client side, walking trough the directory tree and upload the files via api.

- [x] **2.2 Virtual Folders (Frontend Integration)**
  Connect folder CRUD and tag-based filtering UI to backend. Allow creating, renaming, deleting folders and browsing documents within them.

- [x] **2.3 Document Versioning UI**
  Display version history per document, allow uploading new versions with change reason, show diff metadata between versions.

- [x] **2.4 Template Builder (Frontend — Drag & Drop)**
  Implement the JSON-driven form builder with `@hello-pangea/dnd`. Field palette, canvas, field configuration panel. Save template schema to backend.

- [x] **2.5 Report Data Entry & PDF Extraction**
  Frontend form rendered from template schema. Submit field values. Upload offline PDF and trigger Dual-UUID extraction. Display extracted vs. entered data comparison.

---

## Phase 3 — Workflows, Training & Signatures

- [x] **3.1 BPMN Workflow Visual Editor**
  Integrate a BPMN editor component (e.g., bpmn-js). Allow admins to design document lifecycles visually. Save/load BPMN XML to backend.

  Preprare for Auto-Assignment: AI analyzes document content to suggest appropriate reviewers and approvers based on the Agent Registry (5.1) (e.g., identifying technical content and suggesting the CTO).

  Risk-Based Pathing: High-risk documents automatically trigger stricter workflow paths with increased review cycles compared to standard instructions.

- [~] **3.2 Workflow Execution & State Transitions (Frontend)**
  Show current document state, available transitions, trigger transitions with confirmation. Display workflow history timeline.

- [ ] **3.3 Training Management UI**
  List training tasks, mark completion, view training records per user/document. Enforce training-gated access in frontend routing.

- [ ] **3.4 Electronic Signatures UI**
  Re-authentication dialog with password verification. Trigger PAdES signing. Display signature status and certificate info on documents.
  
  Regulatory Compliance: Integration of mandatory "Reason for Signature" fields (Author, Review, Approval) in accordance with 21 CFR Part 11.

  Visual Signature Overlay: Automatically generates a signature block in the PDF (2.5) displaying name, timestamp, and certificate ID.

- [ ] **3.5 Training-Gated Access Control**

  Compliance Enforcement: Implements a strict access lock where users cannot open or interact with a document until the associated training task (3.3) and AI-generated quiz (5.3) are marked as "Passed".

---

## Phase 4 — Search, Knowledge & AI Integration

- [ ] **4.1 Search UI Integration**
  Connect search page to hybrid search API. Display results with relevance scores, snippets, and faceted filtering by company/type/status.

- [ ] **4.2 RAG Knowledge Base UI**
  Chat-style interface for asking questions against documents. Show source citations with links to original documents. Conversation history.

- [ ] **4.3 AI Model Integration (vLLM Service Layer)**
  Implement actual LLM inference calls in the backend service layer (replace mock responses). Embedding generation for document indexing. OCR pipeline for scanned PDFs.

- [ ] **4.4 Multimodal Knowledge Base**

  Diagram & Flowchart Understanding: Enhances the RAG engine (4.2) to interpret visual process flows and diagrams within documents for complex process-related queries.

  Video-to-SOP Alignment: Analyzes uploaded training videos to extract core steps and automatically compares them against written SOPs to detect discrepancies.

---

## Phase 5 — Multi-Agent Document Review System

- [ ] **5.1 Modular Agent Registry & Personality Framework**

  Pluggable Agent Archetypes: Define a base Agent class with configurable parameters: personality, domain expertise, and system prompts.

  Role-Based Profiles: Support for diverse profiles such as "Regulatory Auditor," "Data Integrity Specialist," "Technical Writer," and "Educational Specialist".

  Extensible Config (YAML/JSON): Store agent definitions in a modular registry allowing for hot-loading of new archetypes (e.g., adding an "Environmental Impact Auditor" later) without code changes.

  Contextual Tuning: Settings for LLM temperature, maximum tokens, and specific evaluation rubrics per agent role.

  Define agent archetypes (e.g., "Regulatory Compliance Auditor", "Data Integrity Specialist", "Process Safety Reviewer", "Statistical Methods Auditor").

- [ ] **5.2 Multi-Agent "Always-On" Auditing**
  
  Review Orchestration - Implement a review pipeline: document/company is submitted for review → dispatched to N configured auditor agents in parallel → each agent produces an independent review report with findings, severity ratings, and recommendations. Configurable per company/document type (MedTec audits differ from supplier audits).

  Master Auditor Summarization Agent - A supervisory agent that receives all individual review reports, identifies consensus findings, flags contradictions between auditors, produces a unified executive summary with prioritized action items, and assigns an overall compliance score.

  Review Dashboard & Findings UI - Frontend page showing: review status per document, individual agent reports side-by-side, master summary, finding severity heatmap, action item tracking, and approval/rejection workflow for review outcomes.

  Compliance Scorecards: Each company/tenant gets a real-time "Audit Readiness" score.

  Missing Link Detection: The AI proactively flags documents that are approved but missing the required training records (Phase 3.3) or electronic signatures (Phase 3.4).

  Anomaly Detection in Logs: The Master Auditor (Phase 5.3) can monitor the Audit Trail (6.3) to flag suspicious patterns, such as "Back-dating" signatures or bypasses in the BPMN workflow.

  Company-Specific Audit Profiles - Each company/tenant gets configurable audit profiles that determine: which auditor agents are assigned, what regulatory frameworks apply (ISO 13485, GMP, GDP, ISO 9001, etc.), severity thresholds, and required review quorum before a document can be approved.

- [ ] **5.3 AI-Enhanced Training Ecosystem**

  AI Training Planner: Automated career-path and compliance-based training schedules for employees. Maps document requirements to user roles and identifies skill gaps.

  AI Training Material Generator: Automatically generates training presentations, summaries, and educational content based on uploaded documents (SOPs, Work Instructions).

  Automated Question Generator: LLM-driven generation of comprehension quizzes and assessments derived directly from documents that require mandatory training. Includes automated grading and validation logic.

  Role-Play Scenarios: Instead of a static quiz, the AI Training Generator creates a "Virtual Audit" where the employee must answer questions using the document they just read.

  Dynamic Feedback: If a user fails a training question, the AI doesn't just give the answer; it points them to the exact paragraph in the DOCX (Phase 5.7) where the information resides.

- [ ] **5.4 AI Document Generator (Template-Based)**

  DOCX Template Intelligence: Use existing .docx files in the database as "Master Templates" to guide the structure of new documents.

  Semantic Content Generation: AI builds new regulatory documents (URS, MVP, etc.) by synthesizing data from the company's knowledge base into the layout of a selected DOCX template.

  Distinction from 2.4: Unlike the JSON-driven Form Builder (2.4), this engine focuses on high-volume text generation within standard word processing formats.

  Cross-Document Consistency: Ensures that a generated MVP (Master Validation Plan) correctly references the specific requirements listed in the associated URS (User Requirement Specification).

- [ ] **5.5 AI-Driven Change Impact Analysis**

  Automated Dependency Mapping: When a Document (e.g. a SOP) is updated, the AI scans the repository to flag which other documents (URS, MVP) or Training Tasks are now out of date.

  Gap Analysis: If a user updates a Document (e.g. a URS), the AI compares it against the existing MVP and highlights specific sections that no longer meet the updated requirements.

- [ ] **5.6 AI-Powered Traceability & Gap Discovery**

  Automated Matrix Generation: AI crawls requirements in one document and maps them to test cases in another, creating the Traceability Matrix automatically.

  Orphan Requirement Alerts: Flags any requirement in a URS that doesn't have a corresponding test case or validation result in the system.



---

## Phase 6 — Admin & System Management

- [ ] **6.1 Admin Dashboard — User Management**
  Doc-Admin Group: Introduction of a specialized "Document Administrator" role responsible for defining BPMN workflows (3.1) and managing granular read/write/approve permissions.

  Role-Based Access Control (RBAC): UI to manage group assignments, ensuring IT-Admins handle system health (6.2) while Doc-Admins control document lifecycles and compliance logic.

  Permission Templates: Ability to define standard access sets for different document types (e.g., "Internal SOP" vs. "External Supplier File").

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

- [ ] **7.3 Automated Validation Evidence Locker**

  Self-Documentation: Generates a "Validation Snapshot" upon deployment or configuration changes, capturing current Playwright E2E results and system state.

  AI-Generated Test Scenarios: AI analyzes new roadmap features and automatically proposes Playwright test scripts to maintain high CSV (Computerized System Validation) coverage.


---

## Phase 8 — Governance, Corporate Setup & Documentation

- [ ] **8.1 AI Risk & Compliance Framework Structure**
  **Risk-Based Tiering:** Establish a formal classification system separating High-Risk AI tasks (e.g., Document Generation 5.4, Automated Auditing 5.2) from Low-Risk AI tasks (e.g., Knowledge Base RAG 4.2) to define appropriate validation depth.
  **Task-Specific Control Sets:** Define specific control measures and human-in-the-loop (HITL) requirements for each risk tier to ensure GxP and regulatory alignment as a base for all following documents


- [ ] **8.2 ALC Corporate Environment Setup**
  
  **ALC Company Entity:** Initialize a dedicated "ALC" tenant/company within the Multi-Tenancy framework (1.1) to serve as the master reference and internal management hub and as a example/test environment. Add all following documents here
  **Standardized Configuration:** Apply baseline regulatory settings and user pools specific to the ALC corporate structure.

- [ ] **8.3 User Requirement Specifications (URS) for ALC**
  **Requirement Elicitation:** Enhance existing URS based on current implementation within the ALC company scope, defining the functional and non-functional needs of the platform from a corporate perspective.
  **Traceability Integration:** Ensure all ALC requirements are mapped to the Global Traceability Matrix (7.2). Enhance 7.2 if neccessary.


- [ ] **8.4 Cross-Sector AI Regulatory Guidelines**
  **Contextual Policy Engine:** Develop how to use AI guidelines-documents for stuff based on current global regulations (e.g., EU AI Act, FDA/EMA guidance) and the ALC-URS. Integrate risk-analysis based on 8.1
  **Sector-Specific Modules:** Create distinct policy templates for Pharma (GMP), MedTech (ISO 13485), and IVD (IVDR) to guide stuff how to use ALC functions.


- [ ] **8.5 Documentation Suite: User & Admin Guides**
  **Comprehensive User Guide:** Create a manual for end-users covering document lifecycle, training workflows, and interacting with AI agents.
  **Technical Admin Guide:** Develop a detailed administrator manual for system configuration (6.2), user management (6.1), and oversight of the AI model layer (4.3).


---

## Notes

- Each item above will become a dedicated spec in `.kiro/specs/{feature-name}/`
- Implementation order within a phase can be parallelized where no dependencies exist
- Company separation (1.1) is foundational — almost everything else depends on it
- The multi-agent review system (Phase 5) depends on AI integration (4.3) being functional
- Frontend integration tasks (Phase 2–3) can proceed in parallel with AI work (Phase 4–5)
