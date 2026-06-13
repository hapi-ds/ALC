# User Requirement Specification (URS)
## AlcoaBase — Document & Knowledge Management System

| Field | Value |
|-------|-------|
| **Classification** | GxP-Relevant |
| **Regulatory Context** | 21 CFR Part 11, EU Annex 11, EU AI Act, ISO 13485 |

---

## 1. Purpose & Scope

This document defines the functional and non-functional requirements for AlcoaBase, a fully local Document & Knowledge Management System designed for regulated environments. It serves as the authoritative source for validation activities and traceability mapping.

### 1.1 Intended Use

AlcoaBase provides document lifecycle management, AI-powered knowledge retrieval, automated auditing, and computer system validation for organizations operating under GxP regulations (GMP, GLP, GCP), medical device regulations (ISO 13485, MDR 2017/745), and AI governance frameworks (EU AI Act).

### 1.2 System Boundaries

- 100% local deployment (air-gapped capable)
- No data leaves the local network
- All AI inference runs on local hardware
- Multi-tenant architecture with strict data isolation

---

## 2. Functional Requirements

### 2.1 Document Management

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-DOC-01 | System shall support upload of PDF and DOCX documents | Must | Documents uploaded via UI or API are stored in MinIO and metadata persisted to PostgreSQL |
| REQ-DOC-02 | System shall assign a unique Document-UUID (YYYY-NNNNN format) to each document | Must | UUID generated automatically on creation, unique per company |
| REQ-DOC-03 | System shall support major and minor versioning | Must | New versions created with change reason, version history preserved |
| REQ-DOC-04 | System shall support tag-based classification | Should | Tags assigned to documents, filterable in list views |
| REQ-DOC-05 | System shall support virtual folders with tag-based filtering | Should | Folders created with filter rules, documents auto-grouped |
| REQ-DOC-06 | System shall enforce document-type-specific permission templates | Must | Access controlled per role and document type |

### 2.2 Workflow & Lifecycle

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-WF-01 | System shall support configurable BPMN workflows per document type | Must | Visual editor for workflow design, BPMN XML stored |
| REQ-WF-02 | System shall enforce state transitions with mandatory change reasons | Must | Transitions require X-Change-Reason header, invalid transitions rejected |
| REQ-WF-03 | System shall support signature-gated transitions | Must | Transitions marked as requiring PAdES signature block until signed |
| REQ-WF-04 | System shall support training-gated transitions | Must | Transitions blocked until user has valid training + quiz pass |
| REQ-WF-05 | System shall support risk-based workflow pathing | Should | High-risk documents trigger stricter review paths |
| REQ-WF-06 | System shall maintain complete workflow history timeline | Must | All transitions logged with user, timestamp, reason |

### 2.3 Electronic Signatures

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-SIG-01 | System shall support PAdES digital signatures per 21 CFR Part 11 | Must | Re-authentication required, signature embedded in PDF |
| REQ-SIG-02 | System shall record signature meaning (Author/Review/Approval) | Must | Reason field mandatory, stored immutably |
| REQ-SIG-03 | System shall display visual signature overlay on signed PDFs | Should | Signature block visible with name, timestamp, certificate ID |
| REQ-SIG-04 | System shall detect tampering of signed documents | Must | Signature verification fails after PDF modification |

### 2.4 Training Management

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-TRN-01 | System shall auto-create training tasks when document versions change | Must | Version update triggers task creation for relevant users |
| REQ-TRN-02 | System shall enforce training-gated access control | Must | Untrained users blocked from accessing GxP documents |
| REQ-TRN-03 | System shall generate comprehension quizzes from document content | Should | AI-generated questions, 80% pass threshold |
| REQ-TRN-04 | System shall maintain immutable training records | Must | Training completion records append-only, no edit/delete |
| REQ-TRN-05 | System shall support AI-driven training material generation | Should | Summaries, presentations, walkthroughs generated from SOPs |

### 2.5 Search & Knowledge

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-SRH-01 | System shall support hybrid search (BM25 + semantic vector) | Must | Combined relevance scoring across full document corpus |
| REQ-SRH-02 | System shall support RAG-based Q&A with source citations | Must | Answers reference source documents with links |
| REQ-SRH-03 | System shall scope search results to user's tenant | Must | Cross-company data never exposed in results |
| REQ-SRH-04 | System shall support faceted filtering by type, status, tag | Should | UI provides filter controls, results update dynamically |

### 2.6 Multi-Agent Auditing

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-AUD-01 | System shall support parallel review by multiple AI agents | Must | N agents produce independent reviews simultaneously |
| REQ-AUD-02 | System shall produce master auditor summary from individual reviews | Must | Consensus findings, contradictions, compliance score |
| REQ-AUD-03 | System shall support company-specific audit profiles | Should | Different agents/frameworks per regulatory vertical |
| REQ-AUD-04 | System shall detect anomalies in audit trail patterns | Should | Back-dating, workflow bypasses flagged automatically |

### 2.7 AI Governance & Risk Framework

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-AI-01 | System shall classify AI operations into risk tiers (High/Medium/Low) | Must | Each AI task type has assigned tier with appropriate controls |
| REQ-AI-02 | System shall enforce HITL review for High-risk AI operations | Must | Outputs blocked until human reviewer approves |
| REQ-AI-03 | System shall log all AI operations with configurable audit depth | Must | Inputs, outputs, duration, token count recorded per tier |
| REQ-AI-04 | System shall support per-company risk profile customization | Should | Companies can override default tier assignments |

### 2.8 Administration

| REQ-ID | Requirement | Priority | Acceptance Criteria |
|--------|------------|----------|-------------------|
| REQ-ADM-01 | System shall support RBAC with 5 predefined roles | Must | system_admin, doc_admin, it_admin, member, viewer |
| REQ-ADM-02 | System shall support multi-tenancy with strict data isolation | Must | Cross-company queries impossible for non-system-admins |
| REQ-ADM-03 | System shall provide centralized audit trail viewer | Must | Filterable, searchable, exportable to PDF |
| REQ-ADM-04 | System shall monitor infrastructure health in real-time | Should | PostgreSQL, MinIO, OpenSearch, Redis, vLLM status display |
| REQ-ADM-05 | System shall support backup scheduling and management | Should | Configurable cron schedule, retention policy, manual trigger |

---

## 3. Non-Functional Requirements

### 3.1 Performance

| REQ-ID | Requirement | Acceptance Criteria |
|--------|------------|-------------------|
| REQ-NFR-01 | API response time < 500ms for CRUD operations (p95) | Measured under normal load |
| REQ-NFR-02 | Document upload supports files up to 100 MB | No timeout for files within limit |
| REQ-NFR-03 | Search results returned within 2 seconds | Hybrid search across 10,000+ documents |

### 3.2 Security

| REQ-ID | Requirement | Acceptance Criteria |
|--------|------------|-------------------|
| REQ-SEC-01 | All passwords stored using bcrypt hashing | No plaintext passwords in database |
| REQ-SEC-02 | JWT tokens expire after configurable period | Default 30 minutes, refresh via httpOnly cookie |
| REQ-SEC-03 | All mutating requests require X-Change-Reason header | 400 error returned if missing |
| REQ-SEC-04 | System runs in fully air-gapped mode | No outbound network connections (except optional literature search) |

### 3.3 Data Integrity (ALCOA+)

| REQ-ID | Requirement | Acceptance Criteria |
|--------|------------|-------------------|
| REQ-DI-01 | All records are Attributable | User ID recorded for every action |
| REQ-DI-02 | All records are Legible | Stored in structured format, human-readable audit trail |
| REQ-DI-03 | All records are Contemporaneous | Timestamps generated server-side at time of action |
| REQ-DI-04 | All records are Original | Primary data stored, not copies |
| REQ-DI-05 | All records are Accurate | Data validated at input, checksums for files |
| REQ-DI-06 | Audit trail is immutable | No UPDATE/DELETE on audit records |

### 3.4 Availability & Recovery

| REQ-ID | Requirement | Acceptance Criteria |
|--------|------------|-------------------|
| REQ-AVL-01 | System supports container restart recovery | Services auto-restart via Docker restart policy |
| REQ-AVL-02 | Database backups configurable on schedule | Cron-based, retention period enforced |
| REQ-AVL-03 | System health monitoring with alerting | Degraded/unreachable status detected within 30s |

---

## 4. Regulatory Traceability

This URS maps to the following regulatory requirements:

| Regulation | Relevant Sections | AlcoaBase Coverage |
|------------|-------------------|-------------------|
| 21 CFR Part 11 | §11.10 (controls), §11.50 (signatures), §11.70 (linking) | REQ-SIG-*, REQ-DI-*, REQ-SEC-* |
| EU Annex 11 | §4 (validation), §7 (data storage), §9 (audit trail) | REQ-DOC-*, REQ-DI-*, REQ-ADM-03 |
| EU AI Act | Art. 9 (risk management), Art. 13 (transparency), Art. 14 (human oversight) | REQ-AI-* |
| ISO 13485 | §4.2.4 (document control), §7.5.1 (production controls) | REQ-DOC-*, REQ-WF-* |

---

## 5. Glossary

| Term | Definition |
|------|-----------|
| ALCOA+ | Attributable, Legible, Contemporaneous, Original, Accurate (plus Complete, Consistent, Enduring, Available) |
| BPMN | Business Process Model and Notation |
| GxP | Good Practice guidelines (GMP, GLP, GCP) |
| HITL | Human-In-The-Loop |
| PAdES | PDF Advanced Electronic Signatures |
| RAG | Retrieval-Augmented Generation |
| URS | User Requirement Specification |
| vLLM | High-throughput LLM inference engine |

---

## 6. Change History

> Version history is managed by AlcoaBase document versioning. See document metadata for authoritative version, date, and author information.

---

*End of Document*
