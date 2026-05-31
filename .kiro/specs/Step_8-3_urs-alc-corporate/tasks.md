# Implementation Plan: URS for ALC Corporate

## Overview

Implement the `URSGeneratorService` — a backend service that programmatically generates the Enhanced User Requirement Specifications (URS) document, uploads it into the ALC corporate governance environment, applies tags and the governance workflow, and supports versioning on re-execution. The service follows the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible). The URS content is a deterministic Python string constant covering all 14+ modules with 40+ requirements in REQ-{MODULE}-{NN} format.

## Tasks

- [ ] 1. Define schemas, constants, and configuration
  - [ ] 1.1 Create Pydantic schemas for URSGenerationReport and URSGenerationError
    - Create `src/backend/src/alcoabase/schemas/urs_generation.py`
    - Define `URSGenerationReport` model with fields: document_id (int), document_uuid (str), document_title (str), version_number (int), tags_applied (list[str]), workflow_state (str), requirement_count (int), module_count (int), is_new_document (bool), total_duration_ms (int)
    - Define `URSGenerationError` model with fields: error (str), failed_step (str), detail (str | None)
    - _Requirements: 6.4, 7.5_

  - [ ] 1.2 Create URS content constant module
    - Create `src/backend/src/alcoabase/services/urs_content.py`
    - Define `URS_CONTENT` as a large Markdown string constant containing the complete Enhanced URS document
    - Include all 14+ requirement modules: Document Management (REQ-DM-xx), Deterministic PDF Protocol (REQ-PDF-xx), Workflows and Electronic Signatures (REQ-WF-xx, REQ-SIG-xx), Training Execution Gate (REQ-TRN-xx), ALCOA+ Audit Trail (REQ-AUD-xx), Computer System Validation (REQ-CSV-xx), Hybrid Search and Knowledge Base (REQ-SRCH-xx), RAG Document Q&A (REQ-RAG-xx), AI Model Integration (REQ-AI-xx), Agent Registry and Personality Framework (REQ-AGT-xx), Multi-Agent Auditing (REQ-MAA-xx), AI Training Ecosystem (REQ-ATE-xx), AI Document Generator (REQ-GEN-xx), Change Impact Analysis (REQ-CIA-xx), Traceability and Gap Discovery (REQ-TRC-xx), User Management and RBAC (REQ-USR-xx), System Configuration (REQ-SYS-xx), AI Risk and Compliance Framework (REQ-RISK-xx), ALC Corporate Environment (REQ-GOV-xx)
    - Each requirement must have: unique Requirement_ID (REQ-{MODULE}-{NN}), description, BDD-style acceptance criteria (Given/When/Then)
    - Include document header section with title, version placeholder, generation timestamp placeholder, applicable regulatory frameworks, and revision history table
    - Include Requirements Summary Table at the end listing all Requirement_IDs with short descriptions, module, and risk classification
    - Include Glossary section and Traceability Mapping section
    - Ensure minimum 40 distinct requirements across all modules
    - Define `URS_DOCUMENT_TITLE`, `URS_DOCUMENT_TYPE`, and `URS_TAGS` constants
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 5.2, 5.4, 5.5_

- [ ] 2. Implement URSGeneratorService core
  - [ ] 2.1 Create URSGeneratorService class with execute() orchestrator
    - Create `src/backend/src/alcoabase/services/urs_generator_service.py`
    - Implement `URSGeneratorService.__init__(self, session: AsyncSession, storage_service: StorageService | None = None, uuid_service: UUIDService | None = None)`
    - Implement `async execute() -> URSGenerationReport` orchestrator that calls each step method in sequence
    - Include timing measurement for `total_duration_ms`
    - Use structured logging with `urs_step` field throughout
    - Import and use `URS_CONTENT`, `URS_DOCUMENT_TITLE`, `URS_DOCUMENT_TYPE`, `URS_TAGS` from `urs_content.py`
    - _Requirements: 6.1, 6.3, 6.4_

  - [ ] 2.2 Implement _validate_prerequisites() step
    - Query for ALC company by slug "alc-corporate" — raise RuntimeError with "ALC corporate environment not provisioned. Run Phase 8.2 seed first." if not found
    - Query for doc-admin user by username "alc-doc-admin" — raise RuntimeError with "ALC Document Administrator user not found. Run Phase 8.2 seed first." if not found
    - Query for governance workflow by document_tag "ALC-GOV" and company_id — raise RuntimeError with "ALC Governance workflow not found. Run Phase 8.2 seed first." if not found
    - Return tuple of (company, doc_admin_user, workflow_definition)
    - _Requirements: 3.3, 4.3, 8.1, 8.2, 8.3_

  - [ ] 2.3 Implement _generate_content() and _validate_content() steps
    - Build URS Markdown from `URS_CONTENT` constant with version metadata injected (version number, generation timestamp)
    - Implement `_validate_content(content)` that checks content is non-empty and contains valid Requirement_IDs matching regex `REQ-[A-Z]+-\d{2}`
    - Raise RuntimeError if content is empty or contains no valid Requirement_IDs
    - _Requirements: 1.7, 8.5_

  - [ ] 2.4 Implement _detect_existing_document() step
    - Query for existing document by joining DocumentTag records where tags contain both "URS" and "ALC-GOV" and company_id matches ALC company
    - Return the existing Document if found, None otherwise
    - _Requirements: 1.6, 7.1_

  - [ ] 2.5 Implement _create_new_document() and _create_new_version() steps
    - `_create_new_document()`: Generate Document-UUID (YYYY-NNNNN), upload content to MinIO at `documents/{uuid}/1.0/document.md`, INSERT Document record (title, document_type, folder_path="/governance/urs", company_id, created_by), INSERT DocumentVersion (major=1, minor=0, storage_key, file_hash=SHA-512)
    - `_create_new_version()`: SELECT MAX(major_version), upload to MinIO at `documents/{uuid}/{new_ver}.0/document.md`, INSERT DocumentVersion (major=N+1, minor=0), UPDATE document.current_status to "Draft"
    - _Requirements: 3.1, 3.4, 3.5, 7.1, 7.3_

  - [ ] 2.6 Implement _apply_tags() step
    - Query existing tags for the document
    - Insert "URS" and "ALC-GOV" DocumentTag records if not already present
    - Return list of tag strings applied
    - _Requirements: 3.2_

  - [ ] 2.7 Implement _apply_workflow() step
    - Create or update DocumentState record with current_state="Draft", workflow_id from governance workflow, updated_by=doc_admin
    - Record audit trail entry with change_reason "Governance workflow applied — document enters Draft state"
    - Return workflow state string "Draft"
    - _Requirements: 4.1, 4.2, 4.4, 7.4_

- [ ] 3. Checkpoint - Ensure core service logic is complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement CLI script and API endpoint
  - [ ] 4.1 Create CLI script for URS generation
    - Create `src/backend/src/alcoabase/scripts/generate_urs_alc.py`
    - Create async session, call `URSGeneratorService.execute()`, manage transaction (commit on success, rollback on failure)
    - Print URSGenerationReport as JSON to stdout on success (exit 0)
    - Print error details to stderr on failure (exit 1)
    - Ensure script is invocable via `uv run python -m alcoabase.scripts.generate_urs_alc`
    - _Requirements: 6.1, 6.5_

  - [ ] 4.2 Create API endpoint for URS generation
    - Create `src/backend/src/alcoabase/api/admin_urs.py` with `POST /api/admin/generate-urs-alc`
    - Require system_administrator or document_administrator role authentication
    - Require X-Change-Reason header (return 400 if missing)
    - Return 401 for unauthorized, 403 for insufficient permissions, 200 with URSGenerationReport on success, 500 with URSGenerationError on failure
    - Register the router in `api/router.py`
    - _Requirements: 6.2, 6.6, 6.7_

- [ ] 5. Write property-based tests
  - [ ]* 5.1 Write property test for Requirement ID format and uniqueness (Property 1)
    - **Property 1: Requirement ID format and uniqueness**
    - **Validates: Requirements 1.2, 5.1, 5.4**
    - Create test in `src/backend/tests/properties/test_urs_generator_properties.py`
    - Extract all Requirement_IDs from `URS_CONTENT`, verify each matches regex `REQ-[A-Z]+-[0-9]{2,}`, verify all IDs are globally unique (no duplicates across modules)

  - [ ]* 5.2 Write property test for document creation completeness (Property 2)
    - **Property 2: Document creation completeness**
    - **Validates: Requirements 3.1, 3.2, 3.4, 4.1, 4.2**
    - For any valid initial state where ALC company, doc-admin user, and governance workflow exist, after successful execution: exactly one Document with tags ["URS", "ALC-GOV"], created_by=doc_admin, at least one DocumentVersion, and DocumentState with current_state="Draft"

  - [ ]* 5.3 Write property test for transaction atomicity (Property 3)
    - **Property 3: Transaction atomicity — failure causes complete rollback**
    - **Validates: Requirements 6.3, 8.4**
    - For any step that raises an exception, assert DB contains zero records from the current generation attempt (complete rollback)

  - [ ]* 5.4 Write property test for versioning idempotency (Property 4)
    - **Property 4: Versioning idempotency**
    - **Validates: Requirements 1.6, 7.1, 7.4, 7.5**
    - For N successive invocations (N ≥ 1): exactly one Document with tags ["URS", "ALC-GOV"], exactly N DocumentVersion records with strictly increasing major_version, DocumentState current_state="Draft" after each, is_new_document=True for first and False for subsequent

  - [ ]* 5.5 Write property test for report accuracy (Property 5)
    - **Property 5: Report accuracy**
    - **Validates: Requirements 6.4**
    - For any successful execution: report document_id matches persisted Document ID, document_uuid matches Document UUID, tags_applied=["URS", "ALC-GOV"], workflow_state="Draft", requirement_count matches actual distinct REQ-IDs in content, module_count matches actual modules

- [ ] 6. Write unit tests
  - [ ]* 6.1 Write unit tests for prerequisites validation and content generation
    - Create `src/backend/tests/unit/test_urs_generator_service.py`
    - Test: validate_prerequisites with all present (returns company, user, workflow), no company (RuntimeError), no doc-admin (RuntimeError), no workflow (RuntimeError)
    - Test: generate_content includes header with title/version/timestamp, includes all module sections, minimum 40 distinct REQ-IDs
    - Test: content validation rejects empty content, rejects content without REQ-IDs, accepts valid content
    - Test: URS_CONTENT constant is non-empty and well-formed
    - _Requirements: 1.1, 1.2, 2.5, 8.1, 8.2, 8.3, 8.5_

  - [ ]* 6.2 Write unit tests for document operations and workflow
    - Test: detect_existing_document found (returns Document), not found (returns None)
    - Test: create_new_document has correct title, type, company_id, created_by; initial version is major=1, minor=0
    - Test: create_new_version increments major_version correctly
    - Test: apply_tags creates both "URS" and "ALC-GOV" tags on new document, does not duplicate on re-run
    - Test: apply_workflow creates DocumentState with state="Draft" on new document, resets to "Draft" on new version
    - Test: report structure for new document (is_new_document=True), existing document (is_new_document=False, incremented version)
    - _Requirements: 1.6, 3.1, 3.2, 3.4, 4.1, 4.2, 7.1, 7.4, 7.5_

- [ ] 7. Write integration tests
  - [ ]* 7.1 Write integration tests for CLI and API
    - Create `src/backend/tests/integration/test_urs_generator_integration.py`
    - Test: CLI success (exit 0, stdout is valid JSON URSGenerationReport)
    - Test: CLI failure without prerequisites (exit 1, stderr has error message)
    - Test: API endpoint success (POST returns 200 with URSGenerationReport)
    - Test: API endpoint unauthorized (POST without auth returns 401)
    - Test: API endpoint forbidden (POST with non-admin role returns 403)
    - Test: API endpoint missing header (POST without X-Change-Reason returns 400)
    - Test: Full idempotent run (two consecutive runs produce one Document with two versions)
    - Test: Document appears in governance folder (document with tags appears in virtual folder query)
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 7.1_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The service uses Python with FastAPI, SQLAlchemy async, and Pydantic v2
- All tests use pytest + Hypothesis (property-based) as per project conventions
- CLI invocation: `uv run python -m alcoabase.scripts.generate_urs_alc`
- The URS_CONTENT constant is a large Markdown string (~14+ modules, 40+ requirements) — isolate in its own module for maintainability
- Follows ALCSeedService pattern from Phase 8.2 exactly (single transaction, idempotent, dual interface)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 3, "tasks": ["4.1", "4.2"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["7.1"] }
  ]
}
```
