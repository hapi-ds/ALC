# URS

For a clean Computer System Validation (CSV) in a GxP environment (GLP/GMP), a User Requirements Specification (URS) with clearly testable acceptance criteria is the absolute foundation. The test scripts (OQ/PQ) that Playwright will execute automatically are built directly upon this.

Here is the detailed, structured requirements list for the business-critical core modules of AlcoaBase. It is formulated using BDD (Behavior-Driven Development) syntax so that developers can translate them directly into Playwright tests (as assertions).

---

## Module 1: Deterministic PDF Mapping (Dual-UUID)

**REQ-PDF-01: Generation of Template and Field UUIDs**
* **Description:** When saving a new report template via the visual editor, the system must generate the JSON schema and assign immutable UUIDs to the form elements.
* **Acceptance Criteria:**
    * **Given** the admin saves a new template with two input fields (Text, Float).
    * **Then** the backend generates a unique `Document-UUID` for the template.
    * **And** every input field in the JSON schema strictly receives a valid, unique `Field-UUID`.
    * **And** the template's status is set to "ReadOnly" in the database (the schema is henceforth immutable).

**REQ-PDF-02: Generation of Offline PDFs (ReportLab)**
* **Description:** The system must generate a fillable PDF from the approved JSON schema, using the UUIDs as technical field names.
* **Acceptance Criteria:**
    * **Given** an active template with the Document-UUID `DOC-123` and a field with the Field-UUID `FLD-456`.
    * **When** the user clicks "Download Offline Template".
    * **Then** a PDF document is generated and downloaded.
    * **And** the PDF contains an interactive AcroForm text field whose internal property name is exactly `FLD-456`.
    * **And** the `DOC-123` is embedded as a hidden field or within the file's metadata.

**REQ-PDF-03: Automatic Data Extraction and Mapping (PyMuPDF)**
* **Description:** Upon uploading a completed offline PDF, the system must flawlessly extract the data using the UUIDs and write it into the relational laboratory data tables.
* **Acceptance Criteria:**
    * **Given** the user uploads a PDF where the field `FLD-456` contains the value "7.2".
    * **When** the upload API endpoint is called.
    * **Then** the system reads the `DOC-123` and matches the upload to the correct report type.
    * **And** the system extracts the value "7.2" via the `FLD-456` and saves it in the correct Postgres column (without relying on optical labels like "pH-Value").

---

## Module 2: Workflows & Electronic Signatures

**REQ-WF-01: Enforcement of BPMN State Transitions**
* **Description:** Documents may only transition states along the predefined BPMN paths configured by the admin.
* **Acceptance Criteria:**
    * **Given** the BPMN workflow defines the path: `Draft` -> `Review` -> `Approved`.
    * **When** a user attempts to move a document directly from `Draft` to `Approved` via an API call.
    * **Then** the SpiffWorkflow engine rejects the request (HTTP 400).
    * **And** the document's status remains as `Draft`.

**REQ-SIG-01: Cryptographic Signatures (CFR 21 Part 11 Compliant)**
* **Description:** State transitions that represent an approval require a digital signature accompanied by re-authentication.
* **Acceptance Criteria:**
    * **When** the QA Manager clicks "Approve" on an SOP.
    * **Then** a re-authentication dialog (Password or PIN) must be displayed.
    * **When** the provided credentials are correct.
    * **Then** the PDF document is cryptographically signed using an x.509 certificate (PAdES standard).
    * **And** the PDF displays a visual stamp including Name, Date, Time, and the Reason for Signature ("Approved by QA").
    * **And** any subsequent modification to the PDF invalidates the signature (displays as broken/invalid in PDF readers).

---

## Module 3: Training Execution Gate (ABAC)

**REQ-TRN-01: Automatic Training Assignment**
* **Description:** When a new major version of an SOP is approved, the system must automatically issue training tasks to the assigned roles.
* **Acceptance Criteria:**
    * **Given** the role "Lab Analyst" is required to know SOP-A.
    * **When** SOP-A Version 2.0 reaches the `Approved` status.
    * **Then** the SOP's status automatically transitions to `InTraining`.
    * **And** the system generates an open task "Read and understand SOP-A v2.0" for all users holding the "Lab Analyst" role.

**REQ-TRN-02: Hard Stop for Untrained Personnel**
* **Description:** The system must actively block the creation of reports by personnel who have not completed the required training for the current SOP version.
* **Acceptance Criteria:**
    * **Given** SOP-A Version 2.0 is currently active.
    * **Given** User X has only completed training for Version 1.0.
    * **When** User X attempts to create or upload a report based on SOP-A v2.0.
    * **Then** the backend blocks the request (HTTP 403 Forbidden).
    * **And** the UI displays the error: *"Action denied: Valid training record for SOP-A Version 2.0 is missing."*

---

## Module 4: ALCOA+ Audit Trail

**REQ-AUD-01: Immutable Logging of Database Changes**
* **Description:** Every creation, modification, or (logical) deletion of a GLP-relevant record must be logged systematically in a tamper-proof manner.
* **Acceptance Criteria:**
    * **When** a user modifies the value in a report field from "10" to "15" and submits a reason for change.
    * **Then** `SQLAlchemy-Continuum` automatically writes a new row into the corresponding audit version table.
    * **And** the audit trail entry strictly contains: Old Value ("10"), New Value ("15"), User ID, precise server timestamp, and the Reason for Change.
    * **When** an attempt is made to delete an audit trail entry via the API or UI.
    * **Then** the system completely blocks the action (no DELETE endpoints are exposed for audit tables).

---

## Module 5: Computer System Validation (CSV) System

**REQ-CSV-01: Isolated Test Execution and Data Tagging**
* **Description:** The CSV Runner must execute E2E tests without contaminating the production database, search results, or the actual audit trail.
* **Acceptance Criteria:**
    * **When** the CSV container initiates a validation run.
    * **Then** it authenticates using the dedicated, hidden CSV Test User.
    * **And** all database rows, generated documents, and OpenSearch vectors created by the CSV runner automatically receive the flag `is_csv_validation_record = True`.
    * **And** standard user searches via the UI completely filter out these tagged records.

**REQ-CSV-02: Generation of the Validation Certificate**
* **Description:** Upon completion of the Playwright test suite, a formal validation report must be generated and securely archived.
* **Acceptance Criteria:**
    * **When** the Playwright test suite passes with a 100% success rate.
    * **Then** the CSV Runner generates a PDF certificate detailing the test results, timestamps, and module versions.
    * **And** the certificate is system-signed and immutably stored in the AlcoaBase document repository under the document type "Validation Report".