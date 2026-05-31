"""Enhanced URS content constant for ALC Corporate governance.

Contains the complete User Requirement Specifications document as a
Markdown string constant. This is deterministic, version-controlled
content — not AI-generated at runtime.

The content covers all implemented platform phases (1-8.2) with
traceable Requirement_IDs in REQ-{MODULE}-{NN} format.
"""

URS_DOCUMENT_TITLE: str = "AlcoaBase — Enhanced User Requirement Specifications"

URS_DOCUMENT_TYPE: str = "User Requirement Specifications"

URS_TAGS: list[str] = ["URS", "ALC-GOV"]

URS_CONTENT: str = """\
# AlcoaBase — Enhanced User Requirement Specifications

| Field | Value |
|-------|-------|
| **Document Title** | AlcoaBase — Enhanced User Requirement Specifications |
| **Document Type** | User Requirement Specifications (URS) |
| **Version** | {{VERSION}} |
| **Generated** | {{TIMESTAMP}} |
| **Applicable Frameworks** | ISO 27001, ISO 9001, EU AI Act, FDA 21 CFR Part 11 |
| **Classification** | Controlled Document — ALC Governance |

## Revision History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| {{VERSION}} | {{TIMESTAMP}} | URS Generator Service | Automated generation |

---

## 1. Document Management (REQ-DM)

### REQ-DM-01: Document Input and UUID Assignment

* **Description:** The system shall accept document uploads of various types, \
organize them into directories, assign a unique Document-UUID, and support \
categorization via tags.
* **Acceptance Criteria:**
    * **Given** a user uploads a new file into a folder.
    * **When** the upload request is processed by the backend.
    * **Then** the system generates a unique Document-UUID (format YYYY-NNNNN).
    * **And** the system suggests a title based on file metadata.
    * **And** the system prompts the user for tags.

### REQ-DM-02: Document Versioning

* **Description:** The system shall maintain a complete version history for \
every document, with each version immutably stored and linked to the parent \
document record.
* **Acceptance Criteria:**
    * **Given** a document with Document-UUID "DOC-001" exists at version 1.0.
    * **When** a user uploads a revised version with a change reason.
    * **Then** the system creates a new DocumentVersion record with \
major_version incremented.
    * **And** the previous version remains accessible and unmodified.
    * **And** the audit trail records the version creation event.

### REQ-DM-03: Document Metadata and Search Indexing

* **Description:** The system shall extract and store document metadata \
(title, author, creation date, content type) and index it for search.
* **Acceptance Criteria:**
    * **Given** a PDF document is uploaded with embedded metadata.
    * **When** the document is processed by the ingestion pipeline.
    * **Then** the system extracts title, author, and creation date from \
the file metadata.
    * **And** the document content is indexed in OpenSearch within 30 seconds.
    * **And** the document is retrievable via keyword search.

---

## 2. Deterministic PDF Protocol (REQ-PDF)

### REQ-PDF-01: Generation of Template and Field UUIDs

* **Description:** When saving a new report template via the visual editor, \
the system shall generate the JSON schema and assign immutable UUIDs to form \
elements.
* **Acceptance Criteria:**
    * **Given** the admin saves a new template with two input fields \
(Text, Float).
    * **When** the template is persisted.
    * **Then** the backend generates a unique Document-UUID for the template.
    * **And** every input field in the JSON schema receives a valid, unique \
Field-UUID.
    * **And** the template status is set to "ReadOnly" (schema is immutable).

### REQ-PDF-02: Generation of Offline PDFs (ReportLab)

* **Description:** The system shall generate a fillable PDF from the approved \
JSON schema, using UUIDs as technical field names.
* **Acceptance Criteria:**
    * **Given** an active template with Document-UUID "DOC-123" and a field \
with Field-UUID "FLD-456".
    * **When** the user clicks "Download Offline Template".
    * **Then** a PDF document is generated and downloaded.
    * **And** the PDF contains an interactive AcroForm text field with \
internal name exactly "FLD-456".
    * **And** the Document-UUID is embedded as a hidden field or in metadata.

### REQ-PDF-03: Automatic Data Extraction and Mapping (PyMuPDF)

* **Description:** Upon uploading a completed offline PDF, the system shall \
extract data using UUIDs and write it into relational data tables.
* **Acceptance Criteria:**
    * **Given** the user uploads a PDF where field "FLD-456" contains "7.2".
    * **When** the upload API endpoint is called.
    * **Then** the system reads the Document-UUID and matches the upload to \
the correct report type.
    * **And** the system extracts "7.2" via "FLD-456" and saves it in the \
correct database column.

---

## 3. Workflows and Electronic Signatures (REQ-WF, REQ-SIG)

### REQ-WF-01: Enforcement of BPMN State Transitions

* **Description:** Documents shall only transition states along predefined \
BPMN paths configured by the admin. See REQ-SIG-01 for signature requirements.
* **Acceptance Criteria:**
    * **Given** the BPMN workflow defines: Draft -> Review -> Approved.
    * **When** a user attempts to move a document from Draft to Approved \
directly via API.
    * **Then** the workflow engine rejects the request (HTTP 400).
    * **And** the document status remains as Draft.

### REQ-WF-02: Visual Workflow Editor

* **Description:** The system shall provide a drag-and-drop BPMN workflow \
editor for administrators to define document lifecycle states and transitions.
* **Acceptance Criteria:**
    * **Given** an administrator opens the workflow editor.
    * **When** they create a new workflow with states Draft, Review, Approved.
    * **Then** the system persists the BPMN XML definition.
    * **And** the workflow is available for assignment to document types.

### REQ-SIG-01: Cryptographic Signatures (21 CFR Part 11 Compliant)

* **Description:** State transitions representing approvals shall require a \
digital signature with re-authentication. See REQ-WF-01 for workflow enforcement.
* **Acceptance Criteria:**
    * **When** the QA Manager clicks "Approve" on an SOP.
    * **Then** a re-authentication dialog (Password or PIN) is displayed.
    * **When** the credentials are correct.
    * **Then** the PDF is cryptographically signed using an x.509 certificate \
(PAdES standard).
    * **And** the PDF displays a visual stamp with Name, Date, Time, and \
Reason for Signature.
    * **And** any subsequent modification invalidates the signature.

### REQ-SIG-02: Signature Audit Trail

* **Description:** Every electronic signature event shall be recorded in the \
audit trail with full traceability to the signer identity and timestamp.
* **Acceptance Criteria:**
    * **Given** a document is signed by user "qa-manager-01".
    * **When** the signature is applied successfully.
    * **Then** the audit trail records: signer user ID, timestamp (UTC), \
signature reason, document version, and certificate serial number.
    * **And** the audit entry is immutable (no DELETE endpoint exposed).

---

## 4. Training Execution Gate (REQ-TRN)

### REQ-TRN-01: Automatic Training Assignment

* **Description:** When a new major version of an SOP is approved, the system \
shall automatically issue training tasks to assigned roles. See REQ-WF-01.
* **Acceptance Criteria:**
    * **Given** the role "Lab Analyst" is required to know SOP-A.
    * **When** SOP-A Version 2.0 reaches Approved status.
    * **Then** the SOP status transitions to InTraining.
    * **And** the system generates a training task for all users with the \
"Lab Analyst" role.

### REQ-TRN-02: Hard Stop for Untrained Personnel

* **Description:** The system shall block report creation by personnel who \
have not completed required training for the current SOP version.
* **Acceptance Criteria:**
    * **Given** SOP-A Version 2.0 is active.
    * **Given** User X has only completed training for Version 1.0.
    * **When** User X attempts to create a report based on SOP-A v2.0.
    * **Then** the backend blocks the request (HTTP 403 Forbidden).
    * **And** the error message states: "Action denied: Valid training record \
for SOP-A Version 2.0 is missing."

### REQ-TRN-03: Training Comprehension Verification

* **Description:** The system shall require users to pass a comprehension quiz \
before marking training as complete.
* **Acceptance Criteria:**
    * **Given** User X has read SOP-A Version 2.0.
    * **When** User X attempts to mark training as complete.
    * **Then** the system presents a comprehension quiz with AI-generated \
questions.
    * **And** User X must achieve a minimum score of 80% to pass.
    * **And** failed attempts are logged in the training record.

---

## 5. ALCOA+ Audit Trail (REQ-AUD)

### REQ-AUD-01: Immutable Logging of Database Changes

* **Description:** Every creation, modification, or logical deletion of a \
GxP-relevant record shall be logged in a tamper-proof manner.
* **Acceptance Criteria:**
    * **When** a user modifies a report field value from "10" to "15" with a \
reason for change.
    * **Then** SQLAlchemy-Continuum writes a new row in the audit version table.
    * **And** the entry contains: Old Value, New Value, User ID, server \
timestamp, and Reason for Change.
    * **When** an attempt is made to delete an audit trail entry.
    * **Then** the system blocks the action (no DELETE endpoints for audit \
tables).

### REQ-AUD-02: Audit Trail Export

* **Description:** The system shall support export of audit trail records in \
PDF format for regulatory submission.
* **Acceptance Criteria:**
    * **Given** an administrator requests an audit trail export for document \
"DOC-001".
    * **When** the export is generated.
    * **Then** the system produces a PDF containing all audit entries for that \
document.
    * **And** the PDF includes a cryptographic hash for integrity verification.
    * **And** entries are sorted chronologically with no gaps in sequence.

---

## 6. Computer System Validation (REQ-CSV)

### REQ-CSV-01: Isolated Test Execution and Data Tagging

* **Description:** The CSV Runner shall execute E2E tests without contaminating \
production data, search results, or the audit trail.
* **Acceptance Criteria:**
    * **When** the CSV container initiates a validation run.
    * **Then** it authenticates using the dedicated CSV Test User.
    * **And** all records created receive the flag \
is_csv_validation_record = True.
    * **And** standard user searches filter out tagged records.

### REQ-CSV-02: Generation of the Validation Certificate

* **Description:** Upon completion of the Playwright test suite, a formal \
validation report shall be generated and archived.
* **Acceptance Criteria:**
    * **When** the Playwright test suite passes with 100% success rate.
    * **Then** the CSV Runner generates a PDF certificate with test results, \
timestamps, and module versions.
    * **And** the certificate is system-signed and stored as document type \
"Validation Report".

---

## 7. Hybrid Search and Knowledge Base (REQ-SRCH)

### REQ-SRCH-01: Hybrid Lexical and Semantic Search

* **Description:** The system shall support combined lexical (BM25) and \
semantic (vector) search across all indexed documents. See REQ-RAG-01.
* **Acceptance Criteria:**
    * **Given** a document containing the phrase "dissolution testing protocol".
    * **When** a user searches for "tablet dissolution procedure".
    * **Then** the system returns the document via semantic similarity matching.
    * **And** the search response includes a relevance score above 0.7.
    * **And** results are returned within 2 seconds.

### REQ-SRCH-02: Multi-Tenant Search Isolation

* **Description:** Search results shall be strictly scoped to the user's \
current company context, preventing cross-tenant data leakage.
* **Acceptance Criteria:**
    * **Given** Company A has document "SOP-001" and Company B has document \
"SOP-002".
    * **When** a user from Company A performs a search.
    * **Then** only documents belonging to Company A are returned.
    * **And** no documents from Company B appear in results.

---

## 8. RAG Document Q&A (REQ-RAG)

### REQ-RAG-01: Context-Aware Document Question Answering

* **Description:** The system shall answer user questions about documents using \
retrieval-augmented generation with local LLM inference. See REQ-SRCH-01 for \
search integration and REQ-AI-01 for model requirements.
* **Acceptance Criteria:**
    * **Given** a user asks "What is the storage temperature for Reagent X?" \
and the answer exists in SOP-042.
    * **When** the RAG pipeline processes the query.
    * **Then** the system retrieves relevant chunks from SOP-042.
    * **And** the LLM generates an answer citing the source document and page.
    * **And** the response includes confidence score and source references.

### REQ-RAG-02: Citation and Source Traceability

* **Description:** Every RAG-generated answer shall include traceable citations \
back to the source document sections.
* **Acceptance Criteria:**
    * **Given** the RAG system generates an answer from multiple documents.
    * **When** the response is returned to the user.
    * **Then** each claim in the answer is annotated with document ID, section, \
and page number.
    * **And** users can click citations to navigate to the source passage.

---

## 9. AI Model Integration (REQ-AI)

### REQ-AI-01: Local LLM Inference via vLLM

* **Description:** The system shall perform all AI inference locally using vLLM \
with no external API calls, ensuring data never leaves the network.
* **Acceptance Criteria:**
    * **Given** the vLLM service is running with a loaded model.
    * **When** an inference request is submitted.
    * **Then** the request is processed entirely on the local GPU.
    * **And** no network traffic leaves the Docker network boundary.
    * **And** the response is returned within the configured timeout (default \
60 seconds).

### REQ-AI-02: Model Health Monitoring

* **Description:** The system shall continuously monitor AI model availability \
and report health status via the health endpoint.
* **Acceptance Criteria:**
    * **Given** the vLLM service is running.
    * **When** the health endpoint is queried.
    * **Then** the response includes model name, loaded status, GPU memory \
usage, and request queue depth.
    * **And** if the model is unavailable, the health status reports "degraded".

### REQ-AI-03: Inference Rate Limiting

* **Description:** The system shall enforce per-user rate limits on AI \
inference requests to prevent resource exhaustion.
* **Acceptance Criteria:**
    * **Given** a rate limit of 10 requests per minute per user.
    * **When** a user exceeds the limit.
    * **Then** the system returns HTTP 429 Too Many Requests.
    * **And** the response includes a Retry-After header.

---

## 10. Agent Registry and Personality Framework (REQ-AGT)

### REQ-AGT-01: YAML-Based Agent Definition

* **Description:** The system shall load AI agent definitions from YAML files \
with personality profiles, capabilities, and behavioral constraints.
* **Acceptance Criteria:**
    * **Given** a YAML file defines an agent with role "regulatory-auditor" \
and personality traits.
    * **When** the agent registry loads the file.
    * **Then** the agent is available for assignment to review tasks.
    * **And** the agent's system prompt incorporates the defined personality.

### REQ-AGT-02: Hot-Reload Agent Definitions

* **Description:** The system shall detect changes to agent YAML files and \
reload definitions without requiring a service restart.
* **Acceptance Criteria:**
    * **Given** the agent registry is running with agent "auditor-v1".
    * **When** the YAML file is modified to update the personality prompt.
    * **Then** the registry detects the change within 10 seconds.
    * **And** subsequent requests use the updated agent definition.
    * **And** in-progress reviews using the old definition complete unchanged.

---

## 11. Multi-Agent Auditing (REQ-MAA)

### REQ-MAA-01: Parallel Multi-Agent Document Review

* **Description:** The system shall support concurrent review of a document by \
multiple AI agents, each applying their specialized audit perspective.
* **Acceptance Criteria:**
    * **Given** a document is submitted for multi-agent review.
    * **When** the review pipeline is triggered.
    * **Then** at least 2 distinct agent archetypes review the document in \
parallel.
    * **And** each agent produces an independent finding report.
    * **And** findings are aggregated into a consolidated review summary.

### REQ-MAA-02: Agent Finding Severity Classification

* **Description:** Each agent finding shall be classified by severity (Critical, \
Major, Minor, Observation) with justification. See REQ-RISK-01.
* **Acceptance Criteria:**
    * **Given** an agent identifies a data integrity issue in a document.
    * **When** the finding is recorded.
    * **Then** the finding includes: severity level, affected section, \
description, regulatory reference, and recommended action.
    * **And** Critical findings trigger an automatic notification to the \
quality manager.

---

## 12. AI Training Ecosystem (REQ-ATE)

### REQ-ATE-01: AI-Generated Training Materials

* **Description:** The system shall generate training materials (summaries, \
flashcards, quizzes) from SOP content using local LLM inference. \
See REQ-AI-01.
* **Acceptance Criteria:**
    * **Given** SOP-A Version 2.0 is approved and requires training.
    * **When** the training material generator is invoked.
    * **Then** the system produces a summary, key points list, and \
comprehension quiz.
    * **And** generated content references specific sections of the source SOP.
    * **And** quiz questions have verifiable correct answers traceable to \
the SOP text.

### REQ-ATE-02: Adaptive Quiz Difficulty

* **Description:** The system shall adjust quiz difficulty based on the user's \
role and previous training performance.
* **Acceptance Criteria:**
    * **Given** a user with role "Lab Analyst" has failed a quiz once.
    * **When** the system generates a retry quiz.
    * **Then** the quiz includes additional context hints for previously \
missed topics.
    * **And** the passing threshold remains at 80%.

---

## 13. AI Document Generator (REQ-GEN)

### REQ-GEN-01: Template-Based Document Generation

* **Description:** The system shall generate structured documents (SOPs, \
protocols, reports) from templates using AI-assisted content filling. \
See REQ-AI-01.
* **Acceptance Criteria:**
    * **Given** a user selects template "SOP Template v2" and provides \
input parameters.
    * **When** the document generator processes the request.
    * **Then** the system produces a complete document following the template \
structure.
    * **And** generated content is marked as "AI-Generated — Requires Review".
    * **And** the document enters the Draft state of the assigned workflow.

### REQ-GEN-02: Human-in-the-Loop Review Gate

* **Description:** All AI-generated documents shall require explicit human \
approval before advancing beyond Draft state. See REQ-WF-01.
* **Acceptance Criteria:**
    * **Given** an AI-generated document is in Draft state.
    * **When** a user attempts to advance it to Review without editing.
    * **Then** the system requires acknowledgment that the content has been \
reviewed by a human.
    * **And** the acknowledgment is recorded in the audit trail with the \
reviewer's identity.

---

## 14. Change Impact Analysis (REQ-CIA)

### REQ-CIA-01: Automated Impact Detection

* **Description:** When a document is modified, the system shall automatically \
identify all dependent documents, training records, and workflows that may be \
affected. See REQ-TRC-01.
* **Acceptance Criteria:**
    * **Given** SOP-A is referenced by Protocol-B and Training-Plan-C.
    * **When** SOP-A is updated to a new version.
    * **Then** the system identifies Protocol-B and Training-Plan-C as \
impacted artifacts.
    * **And** an impact report is generated listing all affected items with \
their relationship type.
    * **And** stakeholders are notified of the pending impact assessment.

### REQ-CIA-02: Impact Severity Scoring

* **Description:** Each identified impact shall be scored by severity based on \
the nature of the change and the criticality of the dependent artifact.
* **Acceptance Criteria:**
    * **Given** a change to a critical SOP referenced by 5 protocols.
    * **When** the impact analysis completes.
    * **Then** each impacted artifact receives a severity score (High, Medium, \
Low).
    * **And** High-severity impacts require mandatory review before the change \
is finalized.

---

## 15. Traceability and Gap Discovery (REQ-TRC)

### REQ-TRC-01: Automated Requirement-to-Test Mapping

* **Description:** The system shall automatically extract Requirement_IDs from \
source documents and link them to corresponding test cases. See REQ-CIA-01.
* **Acceptance Criteria:**
    * **Given** a URS document contains REQ-DM-01 through REQ-DM-03.
    * **When** the traceability matrix service scans the document.
    * **Then** all Requirement_IDs matching pattern REQ-[A-Z]+-[0-9]+ are \
extracted.
    * **And** each ID is linked to any test case that references it.
    * **And** unlinked requirements are flagged as coverage gaps.

### REQ-TRC-02: Gap Analysis Reporting

* **Description:** The system shall generate gap analysis reports identifying \
requirements without test coverage and tests without requirement linkage.
* **Acceptance Criteria:**
    * **Given** the traceability matrix contains 50 requirements and 45 \
linked test cases.
    * **When** a gap analysis report is requested.
    * **Then** the report lists 5 requirements without test coverage.
    * **And** the report includes coverage percentage (90%) and a risk \
assessment for uncovered requirements.

---

## 16. User Management and RBAC (REQ-USR)

### REQ-USR-01: Role-Based Access Control

* **Description:** The system shall enforce role-based access control with \
predefined roles: system_administrator, document_administrator, \
quality_manager, lab_analyst, and user.
* **Acceptance Criteria:**
    * **Given** a user with role "lab_analyst" is authenticated.
    * **When** they attempt to access the admin configuration panel.
    * **Then** the system returns HTTP 403 Forbidden.
    * **And** the access attempt is logged in the audit trail.

### REQ-USR-02: Multi-Tenancy User Isolation

* **Description:** Users shall only access data within their assigned company \
context, with strict data boundary enforcement.
* **Acceptance Criteria:**
    * **Given** User A belongs to Company X and User B belongs to Company Y.
    * **When** User A queries documents.
    * **Then** only documents with company_id matching Company X are returned.
    * **And** no API endpoint allows cross-tenant data access without \
system_administrator privileges.

---

## 17. System Configuration (REQ-SYS)

### REQ-SYS-01: Centralized Configuration Management

* **Description:** The system shall provide a centralized configuration \
interface for managing system-wide settings including retention policies, \
signature requirements, and AI model parameters.
* **Acceptance Criteria:**
    * **Given** a system administrator accesses the configuration panel.
    * **When** they modify the document retention period from 7 to 10 years.
    * **Then** the configuration is persisted immediately.
    * **And** the change is recorded in the audit trail with the previous \
and new values.
    * **And** the new retention policy applies to all subsequent operations.

### REQ-SYS-02: Environment-Based Configuration

* **Description:** The system shall load sensitive configuration from \
environment variables, never hardcoding secrets in source code.
* **Acceptance Criteria:**
    * **Given** the application starts with DATABASE_URL set in the environment.
    * **When** the configuration is loaded.
    * **Then** the database connection uses the environment-provided URL.
    * **And** no secrets appear in application logs or error messages.

---

## 18. AI Risk and Compliance Framework (REQ-RISK)

### REQ-RISK-01: AI Risk Classification

* **Description:** The system shall classify AI-generated outputs by risk level \
(High, Medium, Low) based on the output type, regulatory context, and potential \
impact. See REQ-MAA-02.
* **Acceptance Criteria:**
    * **Given** an AI agent generates a finding about data integrity.
    * **When** the risk classification service evaluates the output.
    * **Then** the output receives a risk level based on predefined criteria.
    * **And** High-risk outputs require human review before action.
    * **And** the classification rationale is recorded for audit purposes.

### REQ-RISK-02: AI Decision Audit Trail

* **Description:** Every AI-assisted decision shall be logged with the model \
used, input context, output generated, and confidence score.
* **Acceptance Criteria:**
    * **Given** the RAG system generates an answer to a user query.
    * **When** the response is delivered.
    * **Then** the audit trail records: model identifier, input tokens \
(truncated), output text, confidence score, and latency.
    * **And** the record is immutable and linked to the requesting user.

### REQ-RISK-03: EU AI Act Compliance Controls

* **Description:** The system shall implement transparency and documentation \
controls required by the EU AI Act for high-risk AI systems.
* **Acceptance Criteria:**
    * **Given** the system is configured with EU AI Act compliance enabled.
    * **When** an AI model is used for document review.
    * **Then** the system records: purpose of AI use, data processed, \
human oversight measures, and accuracy metrics.
    * **And** users are informed when AI-generated content is presented.

---

## 19. ALC Corporate Environment (REQ-GOV)

### REQ-GOV-01: Corporate Tenant Provisioning

* **Description:** The system shall support provisioning of the ALC corporate \
tenant environment with predefined users, folders, and governance workflows.
* **Acceptance Criteria:**
    * **Given** the ALC seed service is executed.
    * **When** provisioning completes successfully.
    * **Then** the ALC company entity exists with slug "alc-corporate".
    * **And** all predefined users (alc-it-admin, alc-doc-admin, \
alc-quality-mgr, alc-user) are created.
    * **And** governance folders are created with correct tag filters.

### REQ-GOV-02: Governance Document Lifecycle Workflow

* **Description:** The system shall enforce a governance document lifecycle \
(Draft -> Review -> Approved -> InTraining -> Active -> Retired) for all \
documents tagged with "ALC-GOV". See REQ-WF-01.
* **Acceptance Criteria:**
    * **Given** a document is tagged with "ALC-GOV".
    * **When** the governance workflow is applied.
    * **Then** the document enters "Draft" state.
    * **And** state transitions follow the defined sequence without skipping.
    * **And** each transition requires appropriate role authorization.

### REQ-GOV-03: URS Generation and Upload

* **Description:** The system shall support automated generation and upload of \
the Enhanced URS document into the governance folder with appropriate tags and \
workflow assignment.
* **Acceptance Criteria:**
    * **Given** the ALC corporate environment is provisioned.
    * **When** the URS generator service is invoked.
    * **Then** the Enhanced URS document is created with tags ["URS", "ALC-GOV"].
    * **And** the document appears in the "Governance — User Requirement \
Specifications" folder.
    * **And** the governance workflow is applied with initial state "Draft".
    * **And** the generation report includes document_id, version, and \
requirement count.

---

## Requirements Summary Table

| Requirement_ID | Description | Module | Risk |
|----------------|-------------|--------|------|
| REQ-DM-01 | Document Input and UUID Assignment | Document Management | Medium |
| REQ-DM-02 | Document Versioning | Document Management | High |
| REQ-DM-03 | Document Metadata and Search Indexing | Document Management | Low |
| REQ-PDF-01 | Generation of Template and Field UUIDs | Deterministic PDF Protocol | High |
| REQ-PDF-02 | Generation of Offline PDFs (ReportLab) | Deterministic PDF Protocol | High |
| REQ-PDF-03 | Automatic Data Extraction and Mapping | Deterministic PDF Protocol | High |
| REQ-WF-01 | Enforcement of BPMN State Transitions | Workflows and Electronic Signatures | High |
| REQ-WF-02 | Visual Workflow Editor | Workflows and Electronic Signatures | Medium |
| REQ-SIG-01 | Cryptographic Signatures (21 CFR Part 11) | Workflows and Electronic Signatures | High |
| REQ-SIG-02 | Signature Audit Trail | Workflows and Electronic Signatures | High |
| REQ-TRN-01 | Automatic Training Assignment | Training Execution Gate | High |
| REQ-TRN-02 | Hard Stop for Untrained Personnel | Training Execution Gate | High |
| REQ-TRN-03 | Training Comprehension Verification | Training Execution Gate | Medium |
| REQ-AUD-01 | Immutable Logging of Database Changes | ALCOA+ Audit Trail | High |
| REQ-AUD-02 | Audit Trail Export | ALCOA+ Audit Trail | Medium |
| REQ-CSV-01 | Isolated Test Execution and Data Tagging | Computer System Validation | High |
| REQ-CSV-02 | Generation of the Validation Certificate | Computer System Validation | High |
| REQ-SRCH-01 | Hybrid Lexical and Semantic Search | Hybrid Search and Knowledge Base | Medium |
| REQ-SRCH-02 | Multi-Tenant Search Isolation | Hybrid Search and Knowledge Base | High |
| REQ-RAG-01 | Context-Aware Document Question Answering | RAG Document Q&A | Medium |
| REQ-RAG-02 | Citation and Source Traceability | RAG Document Q&A | Medium |
| REQ-AI-01 | Local LLM Inference via vLLM | AI Model Integration | High |
| REQ-AI-02 | Model Health Monitoring | AI Model Integration | Low |
| REQ-AI-03 | Inference Rate Limiting | AI Model Integration | Medium |
| REQ-AGT-01 | YAML-Based Agent Definition | Agent Registry and Personality Framework | Medium |
| REQ-AGT-02 | Hot-Reload Agent Definitions | Agent Registry and Personality Framework | Low |
| REQ-MAA-01 | Parallel Multi-Agent Document Review | Multi-Agent Auditing | Medium |
| REQ-MAA-02 | Agent Finding Severity Classification | Multi-Agent Auditing | High |
| REQ-ATE-01 | AI-Generated Training Materials | AI Training Ecosystem | Medium |
| REQ-ATE-02 | Adaptive Quiz Difficulty | AI Training Ecosystem | Low |
| REQ-GEN-01 | Template-Based Document Generation | AI Document Generator | Medium |
| REQ-GEN-02 | Human-in-the-Loop Review Gate | AI Document Generator | High |
| REQ-CIA-01 | Automated Impact Detection | Change Impact Analysis | High |
| REQ-CIA-02 | Impact Severity Scoring | Change Impact Analysis | Medium |
| REQ-TRC-01 | Automated Requirement-to-Test Mapping | Traceability and Gap Discovery | High |
| REQ-TRC-02 | Gap Analysis Reporting | Traceability and Gap Discovery | Medium |
| REQ-USR-01 | Role-Based Access Control | User Management and RBAC | High |
| REQ-USR-02 | Multi-Tenancy User Isolation | User Management and RBAC | High |
| REQ-SYS-01 | Centralized Configuration Management | System Configuration | Medium |
| REQ-SYS-02 | Environment-Based Configuration | System Configuration | High |
| REQ-RISK-01 | AI Risk Classification | AI Risk and Compliance Framework | High |
| REQ-RISK-02 | AI Decision Audit Trail | AI Risk and Compliance Framework | High |
| REQ-RISK-03 | EU AI Act Compliance Controls | AI Risk and Compliance Framework | High |
| REQ-GOV-01 | Corporate Tenant Provisioning | ALC Corporate Environment | Medium |
| REQ-GOV-02 | Governance Document Lifecycle Workflow | ALC Corporate Environment | High |
| REQ-GOV-03 | URS Generation and Upload | ALC Corporate Environment | Medium |

---

## Glossary

| Term | Definition |
|------|-----------|
| ALCOA+ | Attributable, Legible, Contemporaneous, Original, Accurate + Complete, Consistent, Enduring, Available |
| BDD | Behavior-Driven Development — specification format using Given/When/Then syntax |
| BPMN | Business Process Model and Notation — standard for workflow modeling |
| CFR 21 Part 11 | FDA regulation on electronic records and electronic signatures |
| CSV | Computer System Validation — formal process to verify system meets requirements |
| Document-UUID | Unique identifier assigned to each document (format: YYYY-NNNNN) |
| E2E | End-to-End — testing that validates complete user workflows |
| EU AI Act | European Union regulation on artificial intelligence systems |
| Field-UUID | Unique identifier assigned to each form field in a template |
| GLP | Good Laboratory Practice |
| GMP | Good Manufacturing Practice |
| GxP | General term for Good Practice regulations (GLP, GMP, GCP) |
| LLM | Large Language Model — AI model for natural language processing |
| MinIO | S3-compatible object storage service |
| OQ | Operational Qualification — testing that system operates correctly |
| PAdES | PDF Advanced Electronic Signatures — standard for PDF signing |
| PQ | Performance Qualification — testing under real-world conditions |
| RAG | Retrieval-Augmented Generation — AI technique combining search with generation |
| RBAC | Role-Based Access Control |
| SOP | Standard Operating Procedure |
| URS | User Requirement Specifications |
| vLLM | High-throughput LLM serving engine |

---

## Traceability Mapping

| Requirement_ID | Phase Reference | Implementation Area |
|----------------|-----------------|---------------------|
| REQ-DM-01 | Phase 2.1 | Document upload and UUID generation |
| REQ-DM-02 | Phase 2.1 | Document versioning service |
| REQ-DM-03 | Phase 2.1 | Document metadata extraction |
| REQ-PDF-01 | Phase 2.2 | Template JSON schema generation |
| REQ-PDF-02 | Phase 2.2 | ReportLab PDF generation |
| REQ-PDF-03 | Phase 2.2 | PyMuPDF data extraction |
| REQ-WF-01 | Phase 3.1 | SpiffWorkflow BPMN engine |
| REQ-WF-02 | Phase 3.1 | Workflow editor frontend |
| REQ-SIG-01 | Phase 3.2 | pyhanko PAdES signatures |
| REQ-SIG-02 | Phase 3.2 | Signature audit logging |
| REQ-TRN-01 | Phase 3.3 | Training assignment service |
| REQ-TRN-02 | Phase 3.3 | Training gate middleware |
| REQ-TRN-03 | Phase 3.3 | Quiz comprehension service |
| REQ-AUD-01 | Phase 2.3 | SQLAlchemy-Continuum audit |
| REQ-AUD-02 | Phase 2.3 | Audit PDF export service |
| REQ-CSV-01 | Phase 2.4 | CSV runner container |
| REQ-CSV-02 | Phase 2.4 | Validation certificate generation |
| REQ-SRCH-01 | Phase 4.1 | OpenSearch hybrid search |
| REQ-SRCH-02 | Phase 4.1 | Multi-tenant search filtering |
| REQ-RAG-01 | Phase 4.2 | RAG pipeline service |
| REQ-RAG-02 | Phase 4.2 | Citation extraction |
| REQ-AI-01 | Phase 4.3 | vLLM inference client |
| REQ-AI-02 | Phase 4.3 | Health monitor service |
| REQ-AI-03 | Phase 4.3 | Rate limiting middleware |
| REQ-AGT-01 | Phase 5.1 | Agent registry YAML loader |
| REQ-AGT-02 | Phase 5.1 | File watcher hot-reload |
| REQ-MAA-01 | Phase 5.2 | Multi-agent review pipeline |
| REQ-MAA-02 | Phase 5.2 | Finding severity classifier |
| REQ-ATE-01 | Phase 5.3 | Training material generator |
| REQ-ATE-02 | Phase 5.3 | Adaptive quiz engine |
| REQ-GEN-01 | Phase 5.4 | Document generator service |
| REQ-GEN-02 | Phase 5.4 | HITL checkpoint service |
| REQ-CIA-01 | Phase 5.5 | Impact analysis service |
| REQ-CIA-02 | Phase 5.5 | Impact severity scoring |
| REQ-TRC-01 | Phase 5.6 | Traceability matrix service |
| REQ-TRC-02 | Phase 5.6 | Gap analysis reporting |
| REQ-USR-01 | Phase 6.1 | RBAC service |
| REQ-USR-02 | Phase 6.1 | Multi-tenancy middleware |
| REQ-SYS-01 | Phase 6.2 | System configuration service |
| REQ-SYS-02 | Phase 6.2 | Pydantic settings |
| REQ-RISK-01 | Phase 8.1 | Risk classification service |
| REQ-RISK-02 | Phase 8.1 | AI decision audit logging |
| REQ-RISK-03 | Phase 8.1 | EU AI Act compliance module |
| REQ-GOV-01 | Phase 8.2 | ALC seed service |
| REQ-GOV-02 | Phase 8.2 | Governance workflow definition |
| REQ-GOV-03 | Phase 8.3 | URS generator service |

---

*End of Document*
"""
