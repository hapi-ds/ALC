# Implementation Plan: Documentation Suite — User & Admin Guides

## Overview

Implement the `DocumentationGeneratorService` — a backend service that programmatically generates 2 guide documents (User Guide + Admin Guide), uploads them into the ALC corporate governance environment, applies tags and the governance workflow, and supports versioning on re-execution. The service follows the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible). Guide content is assembled from deterministic Python template constants combined with dynamic cross-reference data from existing governance documents (URS, AI Guidelines).

## Tasks

- [ ] 1. Define schemas, data models, and content module
  - [-] 1.1 Create Pydantic schemas for DocumentationGenerationReport and DocumentationGenerationError
    - Create `src/backend/src/alcoabase/schemas/documentation_generation.py`
    - Define `DocumentReportEntry` model with fields: document_id (int), document_uuid (str), title (str), guide_type (str), version_number (int), tags_applied (list[str]), workflow_state (str), is_new_document (bool), section_count (int), procedure_count (int), screenshot_placeholder_count (int)
    - Define `CrossReferenceSummary` model with fields: urs_references (bool), ai_guidelines_references (bool)
    - Define `DocumentationGenerationReport` model with fields: documents_created (list[DocumentReportEntry]), total_documents (int), total_sections (int), total_procedures (int), cross_references_included (CrossReferenceSummary), total_duration_ms (int)
    - Define `DocumentationGenerationError` model with fields: error (str), failed_operation (str), document_title (str | None), detail (str | None)
    - _Requirements: 4.4, 4.5_

  - [-] 1.2 Create documentation content module with template constants and section definitions
    - Create `src/backend/src/alcoabase/services/documentation_content.py`
    - Define `ProcedureBlock` frozen dataclass with fields: title (str), steps (list[str]), screenshot_slug (str)
    - Define `UserGuideSection` frozen dataclass with fields: section_id (str), title (str), overview (str, min 50 chars), procedures (list[ProcedureBlock]), tips (list[str], min 2), cross_ref_sections (list[str]), urs_requirement_ids (list[str]), ai_guidelines_ref (bool)
    - Define `AdminGuideSection` frozen dataclass with fields: section_id (str), title (str), overview (str, min 80 chars), prerequisites (list[str]), procedures (list[ProcedureBlock]), security_considerations (str), cross_ref_sections (list[str]), user_guide_refs (list[str]), urs_requirement_ids (list[str]), ai_guidelines_ref (bool)
    - Define `CrossReferenceContext` dataclass with fields: urs_available (bool), urs_document_uuid (str | None), urs_document_title (str | None), ai_guidelines_available (bool), ai_guidelines_documents (list[dict]), governance_documents (list[dict])
    - Define constants: `USER_GUIDE_TITLE` ("AlcoaBase — Comprehensive User Guide"), `ADMIN_GUIDE_TITLE` ("AlcoaBase — Technical Administrator Guide"), `DOCUMENTATION_TAGS` (["DOC-GUIDE", "ALC-GOV"]), `DOCUMENTATION_DOCUMENT_TYPE` ("Documentation Guide")
    - Define `USER_GUIDE_SECTIONS` list with 12 UserGuideSection configs:
      - Getting Started (login, navigation, dashboard, quick-start workflow)
      - Document Management (upload, bulk, virtual folders, versioning, metadata)
      - Template Builder (creating forms, field types, drag-and-drop, saving)
      - Report Data Entry and PDF Extraction (filling forms, offline PDFs, Dual-UUID)
      - Workflows (document states, transitions, workflow history)
      - Training Management (assigned training, completing tasks, quiz interaction)
      - Electronic Signatures (re-authentication, signing, signature status)
      - Search and Knowledge Base (hybrid search, RAG, AI answers)
      - AI Agent Interaction (review reports, scorecards, severity, master auditor, training ecosystem)
      - AI Document Generator (templates, generation, reviewing output)
      - Related Governance Documents (list of ALC-GOV docs)
      - Appendices (keyboard shortcuts, glossary, troubleshooting, URS traceability)
    - Define `ADMIN_GUIDE_SECTIONS` list with 12 AdminGuideSection configs:
      - Administration Overview (roles, responsibilities, access levels)
      - User Management (CRUD, role assignment, company assignment, activation, password, permissions)
      - Role-Based Access Control (RBAC model, predefined roles, custom roles, inheritance)
      - System Configuration (AI hardware, storage quotas, backup, health monitoring, service status)
      - AI Model Layer Management (vLLM config, model weights, GPU/CPU/mock, embedding, OCR, timeouts)
      - Storage and Backup (MinIO config, quotas, backup schedules, data retention)
      - Audit Trail Administration (viewing logs, filtering, export, interpreting entries)
      - Compliance Monitoring (scorecards, agent review config, regulatory frameworks, risk tiers)
      - Agent Registry Management (YAML structure, add/modify agents, hot-reload, audit profiles)
      - Workflow Administration (BPMN editor, workflow definitions, lifecycle config)
      - Related Governance Documents (list of ALC-GOV docs)
      - Appendices (CLI reference, API endpoints, environment variables, glossary, troubleshooting)
    - Implement content assembly functions for each document section (header, table of contents, each guide section with overview, procedures, screenshots, tips/prerequisites/security, cross-references)
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 2. Implement DocumentationGeneratorService core
  - [~] 2.1 Create DocumentationGeneratorService class with execute() orchestrator
    - Create `src/backend/src/alcoabase/services/documentation_generator_service.py`
    - Implement `DocumentationGeneratorService.__init__(self, session: AsyncSession, storage_service: StorageService | None = None, uuid_service: UUIDService | None = None)`
    - Implement `async execute() -> DocumentationGenerationReport` orchestrator that calls each step in sequence: acquire_advisory_lock → validate_prerequisites → load_cross_reference_data → generate_user_guide → generate_admin_guide → validate all content → upload/version each document → apply tags → apply workflows → build report
    - Include timing measurement for `total_duration_ms`
    - Use structured logging with `documentation_step` field throughout
    - Acquire DB advisory lock at start to prevent concurrent generation
    - _Requirements: 4.1, 4.3, 4.9, 5.1_

  - [~] 2.2 Implement _validate_prerequisites() step
    - Query for ALC company by slug "alc-corporate" — raise RuntimeError with "ALC corporate environment not provisioned. Run Phase 8.2 seed first." if not found
    - Query for doc-admin user by username "alc-doc-admin" — raise RuntimeError with "ALC Document Administrator user not found. Run Phase 8.2 seed first." if not found
    - Query for governance workflow by document_tag "ALC-GOV" and company_id — raise RuntimeError with "ALC Governance workflow not found. Run Phase 8.2 seed first." if not found
    - Return tuple of (company, doc_admin_user, workflow_definition)
    - Check prerequisites in strict order: company → doc-admin → workflow (halt on first failure)
    - _Requirements: 3.6, 3.7, 3.8, 8.1, 8.2, 8.3, 8.7_

  - [~] 2.3 Implement _load_cross_reference_data() step
    - Query for Enhanced_URS document (tags ["URS", "ALC-GOV"]) in ALC company; set urs_available=True/False with document metadata
    - Query for AI Usage Guidelines documents (tags ["AI-Guidelines", "ALC-GOV"]) in ALC company; set ai_guidelines_available=True/False with document list
    - Query all documents with tag "ALC-GOV" in ALC company for the Related Governance Documents section
    - Build and return `CrossReferenceContext` with all availability flags and document metadata
    - _Requirements: 1.9, 1.10, 7.1, 7.2, 7.3, 7.6, 7.7_

  - [~] 2.4 Implement _generate_user_guide() and _generate_admin_guide() content generation methods
    - `_generate_user_guide(cross_refs, version_number)`: Assemble User Guide from USER_GUIDE_SECTIONS + cross-reference context; include all required sections (header, ToC, 10 content sections, related governance docs, appendices); ensure ≥10 sections and ≥25 Procedure_Blocks
    - `_generate_admin_guide(cross_refs, version_number)`: Assemble Admin Guide from ADMIN_GUIDE_SECTIONS + cross-reference context; include all required sections (header, ToC, 10 content sections, related governance docs, appendices); ensure ≥10 sections and ≥20 Procedure_Blocks
    - Include URS Requirement_ID cross-references (pattern "Implements: REQ-{MODULE}-{NN}") when urs_available=True, or notice when unavailable
    - Include AI Guidelines cross-references in AI-related sections when ai_guidelines_available=True, or notice when unavailable
    - Include inter-guide cross-references (User Guide → Admin Guide and Admin Guide → User Guide)
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 6.5, 6.6, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [~] 2.5 Implement content validation methods
    - `_validate_content(content, document_title)`: Check content is non-empty and contains at least one Markdown heading (regex `^#{1,3}\s`); raise RuntimeError with document title if invalid
    - `_validate_section_lengths(content, document_title)`: Check each section has ≥ 200 characters of content (excluding header and Screenshot_Placeholders); raise RuntimeError identifying section name and document title if any section fails
    - _Requirements: 6.8, 8.5, 8.6_

  - [~] 2.6 Implement document upload, versioning, tagging, and workflow methods
    - `_detect_existing_document(title, company)`: Query by title + tags ["DOC-GUIDE", "ALC-GOV"] + company_id; return Document or None
    - `_upload_or_version_document(title, content, guide_type, company, doc_admin, workflow)`: If not found → generate Document-UUID (YYYY-NNNNN), upload to MinIO, INSERT Document + DocumentVersion (major=1, minor=0); if found → SELECT MAX(major_version), upload new version to MinIO, INSERT DocumentVersion (major=N+1, minor=0), UPDATE current_status to "Draft"
    - `_apply_tags(document, is_new)`: Insert "DOC-GUIDE" and "ALC-GOV" DocumentTag records if not already present
    - `_apply_workflow(document, workflow, doc_admin)`: Create/update DocumentState with current_state="Draft", workflow_id, updated_by=doc_admin
    - `_get_next_version_number(document)`: Get next major_version number (current max + 1)
    - `_count_sections(content)`: Count level-2 headings (## ) in generated content
    - `_count_procedures(content)`: Count Procedure_Blocks in generated content
    - `_count_screenshot_placeholders(content)`: Count screenshot placeholder image references matching `![...](screenshots/...)`
    - Set created_by to alc-doc-admin user; record change_reason "Documentation Suite Generation — Phase 8.5 automated governance document creation"
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [~] 3. Checkpoint - Ensure core service logic is complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement CLI script and API endpoint
  - [~] 4.1 Create CLI script for documentation generation
    - Create `src/backend/src/alcoabase/scripts/generate_documentation.py`
    - Create async session, call `DocumentationGeneratorService.execute()`, manage transaction (commit on success, rollback on failure)
    - Print DocumentationGenerationReport as JSON to stdout on success (exit 0)
    - Print DocumentationGenerationError as JSON to stderr on failure (exit 1)
    - Ensure script is invocable via `uv run python -m alcoabase.scripts.generate_documentation`
    - _Requirements: 4.1, 4.5_

  - [~] 4.2 Create API endpoint for documentation generation
    - Create `src/backend/src/alcoabase/api/admin_documentation.py` with `POST /api/admin/generate-documentation`
    - Require system_administrator or document_administrator role authentication
    - Require X-Change-Reason header (return 400 if missing)
    - Return 401 for unauthorized, 403 for insufficient permissions, 409 for concurrent generation, 200 with DocumentationGenerationReport on success, 500 with DocumentationGenerationError on failure
    - Register the router in `api/router.py`
    - _Requirements: 4.2, 4.6, 4.7, 4.8, 4.9_

- [~] 5. Checkpoint - Ensure CLI and API work end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Write property-based tests
  - [~] 6.1 Write property test for document structure invariant (Property 1)
    - **Property 1: Document structure invariant**
    - **Validates: Requirements 1.2, 2.2**
    - Create test in `src/backend/tests/properties/test_documentation_generator_properties.py`
    - Generate random CrossReferenceContext states (URS available/unavailable, AI Guidelines available/unavailable)
    - Verify User Guide contains all 12 required top-level sections in specified order
    - Verify Admin Guide contains all 12 required top-level sections in specified order

  - [~] 6.2 Write property test for section subsection completeness (Property 2)
    - **Property 2: Section subsection completeness**
    - **Validates: Requirements 1.3, 2.3**
    - Generate sections with random cross-reference states
    - Verify each User Guide section contains: overview (≥50 chars), Procedure_Block, Screenshot_Placeholder, Tips (≥2), Cross_Reference_Block
    - Verify each Admin Guide section contains: overview (≥80 chars), Prerequisites, Procedure_Block, Screenshot_Placeholder, Security Considerations, Cross_Reference_Block

  - [~] 6.3 Write property test for Procedure_Block structural validity (Property 3)
    - **Property 3: Procedure_Block structural validity**
    - **Validates: Requirements 1.4, 6.3**
    - Generate procedure blocks from random section configurations
    - Verify each Procedure_Block has 3–15 numbered steps
    - Verify each step begins with a bold action verb (e.g., **Click**, **Navigate**, **Enter**)
    - Verify each step includes an expected outcome in italics

  - [~] 6.4 Write property test for Screenshot_Placeholder format invariant (Property 4)
    - **Property 4: Screenshot_Placeholder format invariant**
    - **Validates: Requirements 6.4**
    - Generate content with random cross-reference states
    - Verify all placeholders match pattern `![{Descriptive alt text}](screenshots/{section-slug}/{action-slug}.png)`
    - Verify section-slug and action-slug are non-empty kebab-case identifiers matching `[a-z0-9]+(-[a-z0-9]+)*`

  - [~] 6.5 Write property test for cross-reference conditional inclusion (Property 5)
    - **Property 5: Cross-reference conditional inclusion**
    - **Validates: Requirements 1.9, 1.10, 7.2, 7.3, 7.6, 7.7**
    - Generate with random urs_available/ai_guidelines_available flags
    - Verify URS cross-references (pattern "Implements: REQ-{MODULE}-{NN}") present when urs_available=True, notice present when False
    - Verify AI Guidelines cross-references in AI sections when ai_guidelines_available=True, notice present when False

  - [~] 6.6 Write property test for document governance completeness (Property 6)
    - **Property 6: Document governance completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    - Run service with valid prerequisites and random cross-reference states
    - Verify each document has: Document record with created_by=doc_admin, document_uuid matching `\d{4}-\d{5}`, DocumentTag records for both "DOC-GUIDE" and "ALC-GOV", DocumentState with current_state="Draft"

  - [~] 6.7 Write property test for transaction atomicity on failure (Property 7)
    - **Property 7: Transaction atomicity on failure**
    - **Validates: Requirements 4.3, 5.7, 8.4, 8.8**
    - Simulate failures at each step (advisory lock, prerequisite, cross-reference, content generation, upload, tags, workflow)
    - Verify DB contains zero new records from the current attempt after rollback

  - [~] 6.8 Write property test for versioning idempotency (Property 8)
    - **Property 8: Versioning idempotency**
    - **Validates: Requirements 5.1, 5.4, 5.5, 5.6**
    - Run service N times (N drawn from 1–5)
    - Verify exactly 2 Document records (one per guide title) with exactly N DocumentVersion records each
    - Verify strictly increasing major_version numbers
    - Verify is_new_document=True for first, False for subsequent
    - Verify DocumentState reset to "Draft" after each invocation

  - [~] 6.9 Write property test for report accuracy (Property 9)
    - **Property 9: Report accuracy**
    - **Validates: Requirements 4.4, 6.5, 6.6**
    - Run service with random cross-reference configurations
    - Verify report has exactly 2 entries, total_documents=2
    - Verify total_sections matches actual level-2 heading count (User Guide ≥10, Admin Guide ≥10)
    - Verify total_procedures matches actual Procedure_Block count (User Guide ≥25, Admin Guide ≥20)
    - Verify cross_references_included flags match actual availability
    - Verify total_duration_ms > 0

  - [~] 6.10 Write property test for document header completeness (Property 10)
    - **Property 10: Document header completeness**
    - **Validates: Requirements 5.3, 6.1**
    - Generate with random version numbers
    - Verify header contains: document title, version number N, ISO 8601 timestamp with timezone, target audience, applicable platform version, revision history table

  - [~] 6.11 Write property test for Table of Contents consistency (Property 11)
    - **Property 11: Table of Contents consistency**
    - **Validates: Requirements 6.2**
    - Generate content with random cross-reference states
    - Verify ToC lists all level-2 and level-3 headings with section numbers
    - Verify every ToC entry corresponds to an actual heading in the document

  - [~] 6.12 Write property test for content validation correctness (Property 12)
    - **Property 12: Content validation correctness**
    - **Validates: Requirements 6.8, 8.5, 8.6**
    - Generate random strings (some with headings, some without, some empty)
    - Verify validation passes iff string is non-empty AND contains `^#{1,3}\s` pattern
    - Verify section length validation raises RuntimeError for sections < 200 chars
    - Verify error message includes document title on failure

  - [~] 6.13 Write property test for prerequisite check ordering (Property 13)
    - **Property 13: Prerequisite check ordering**
    - **Validates: Requirements 8.7**
    - Test with random combinations of missing prerequisites (company, doc-admin, workflow)
    - Verify check order: company → doc-admin → workflow
    - Verify halts on first failure with correct error message

  - [~] 6.14 Write property test for inter-guide cross-references (Property 14)
    - **Property 14: Inter-guide cross-references**
    - **Validates: Requirements 7.4, 7.5**
    - Generate both guides with random cross-reference states
    - Verify User Guide contains references to Admin Guide (pattern "see Admin Guide Section")
    - Verify Admin Guide contains references to User Guide (pattern "see User Guide Section")

  - [~] 6.15 Write property test for Related Governance Documents completeness (Property 15)
    - **Property 15: Related Governance Documents completeness**
    - **Validates: Requirements 7.1**
    - Generate with random sets of ALC-GOV documents in the company
    - Verify "Related Governance Documents" section lists every ALC-GOV document with title, UUID, and workflow state

- [ ] 7. Write unit tests
  - [~] 7.1 Write unit tests for prerequisites validation and cross-reference loading
    - Create `src/backend/tests/unit/test_documentation_generator_service.py`
    - Test: validate_prerequisites with all present (returns company, user, workflow)
    - Test: validate_prerequisites no company (RuntimeError with correct message)
    - Test: validate_prerequisites no doc-admin (RuntimeError with correct message)
    - Test: validate_prerequisites no workflow (RuntimeError with correct message)
    - Test: validate_prerequisites check order (company before doc-admin before workflow)
    - Test: load_cross_references with URS available (urs_available=True, document metadata populated)
    - Test: load_cross_references with URS unavailable (urs_available=False)
    - Test: load_cross_references with AI Guidelines available (ai_guidelines_available=True)
    - Test: load_cross_references with AI Guidelines unavailable (ai_guidelines_available=False)
    - Test: advisory_lock acquired successfully on first call
    - Test: advisory_lock concurrent rejection (raises RuntimeError)
    - _Requirements: 1.9, 1.10, 3.6, 3.7, 3.8, 7.6, 7.7, 8.1, 8.2, 8.3, 8.7_

  - [~] 7.2 Write unit tests for content generation and validation
    - Test: generate_user_guide has all 12 required sections in order
    - Test: generate_user_guide Getting Started has prerequisites, login, navigation, quick-start
    - Test: generate_user_guide Document Management covers upload, bulk, folders, versioning, metadata
    - Test: generate_user_guide Search section covers hybrid search, RAG, AI answers
    - Test: generate_user_guide AI Agent section covers reports, scorecards, severity, master auditor, training ecosystem
    - Test: generate_user_guide minimum counts (≥10 sections, ≥25 procedures)
    - Test: generate_admin_guide has all 12 required sections in order
    - Test: generate_admin_guide User Management covers CRUD, roles, activation, password, permissions
    - Test: generate_admin_guide System Configuration covers AI hardware, quotas, backup, health, services
    - Test: generate_admin_guide AI Model Layer covers vLLM, weights, GPU/CPU/mock, embedding, OCR, timeouts
    - Test: generate_admin_guide Agent Registry covers YAML structure, add/modify, hot-reload, audit profiles
    - Test: generate_admin_guide Compliance Monitoring covers scorecards, thresholds, findings, risk workflow, tiers
    - Test: generate_admin_guide CLI Reference lists all 5 required commands with syntax and examples
    - Test: generate_admin_guide Environment Variables has name, description, default, component columns
    - Test: generate_admin_guide minimum counts (≥10 sections, ≥20 procedures)
    - Test: validate_content passes for valid content with headings
    - Test: validate_content raises RuntimeError for empty content
    - Test: validate_content raises RuntimeError for content without headings
    - Test: validate_section_lengths passes when all sections ≥ 200 chars
    - Test: validate_section_lengths raises RuntimeError identifying short section and guide
    - Test: procedure blocks have 3–15 numbered steps each
    - Test: procedure block steps start with bold action verb
    - Test: procedure block steps include italic expected outcome
    - Test: screenshot placeholders match required format with kebab-case slugs
    - Test: header contains version number and ISO 8601 timestamp
    - Test: header contains target audience (End-Users / Administrators)
    - Test: ToC entries correspond to actual document headings
    - Test: URS cross-references included when urs_available=True (pattern "Implements: REQ-{MODULE}-{NN}")
    - Test: URS notice included when urs_available=False
    - Test: AI Guidelines cross-references in AI sections when ai_guidelines_available=True
    - Test: AI Guidelines notice in AI sections when ai_guidelines_available=False
    - Test: User Guide references Admin Guide sections (inter-guide cross-refs)
    - Test: Admin Guide references User Guide sections (inter-guide cross-refs)
    - Test: Related Governance Documents section lists all ALC-GOV documents with title, UUID, state
    - Test: Glossary appendix present in both guides
    - Test: _count_sections returns correct level-2 heading count
    - Test: _count_procedures returns correct Procedure_Block count
    - Test: _count_screenshot_placeholders returns correct count
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.5, 8.6_

  - [~] 7.3 Write unit tests for document operations and report building
    - Test: detect_existing_document found (returns Document)
    - Test: detect_existing_document not found (returns None)
    - Test: upload_or_version new document has correct title, type, company_id, created_by, UUID format
    - Test: upload_or_version existing document increments major_version correctly
    - Test: apply_tags creates both "DOC-GUIDE" and "ALC-GOV" tags on new document
    - Test: apply_tags does not duplicate on re-run
    - Test: apply_workflow creates DocumentState with state="Draft" on new document
    - Test: apply_workflow resets to "Draft" on new version
    - Test: report has 2 entries, all is_new_document=True on first run
    - Test: report correctly identifies new vs versioned on subsequent runs
    - Test: report section_count matches actual level-2 headings per guide
    - Test: report procedure_count matches actual Procedure_Blocks per guide
    - Test: report screenshot_placeholder_count matches actual placeholders per guide
    - Test: report cross_references_included flags match actual availability
    - Test: report total_duration_ms > 0
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 8. Write integration tests
  - [~] 8.1 Write integration tests for CLI, API, and end-to-end flows
    - Create `src/backend/tests/integration/test_documentation_generator_integration.py`
    - Test: CLI success (exit 0, stdout is valid JSON DocumentationGenerationReport with 2 documents)
    - Test: CLI failure without prerequisites (exit 1, stderr has JSON error with failed_operation)
    - Test: API endpoint success (POST returns 200 with DocumentationGenerationReport)
    - Test: API endpoint unauthorized (POST without auth returns 401)
    - Test: API endpoint forbidden (POST with non-admin role returns 403)
    - Test: API endpoint missing header (POST without X-Change-Reason returns 400)
    - Test: API endpoint concurrent generation (second request returns 409)
    - Test: Full idempotent run (two consecutive runs produce 2 Documents with 2 versions each)
    - Test: Partial existence (one guide exists, other doesn't — correct new/version behavior)
    - Test: Documents appear in governance folder (documents with tags appear in virtual folder query)
    - Test: Generation with URS available (URS cross-references included)
    - Test: Generation without URS (notice included)
    - Test: Generation with AI Guidelines available (AI Guidelines cross-references included)
    - Test: Generation without AI Guidelines (notice included)
    - Test: Rollback on upload failure (no partial documents after MinIO failure)
    - Test: Rollback on second guide failure (first guide rolled back when second fails)
    - Test: Generation timing under 120 seconds (both guides generated within time limit)
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9, 5.1, 5.4, 5.5, 5.6, 5.7, 7.6, 7.7, 8.4, 8.8_

- [~] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The service uses Python 3.12+ with FastAPI, SQLAlchemy 2.0 async, and Pydantic v2
- All tests use pytest + pytest-asyncio + Hypothesis (property-based) as per project conventions
- CLI invocation: `uv run python -m alcoabase.scripts.generate_documentation`
- The documentation_content.py module isolates large template constants and section configs from service orchestration logic
- Follows ALCSeedService / URSGeneratorService / GuidelinesGeneratorService pattern exactly (single transaction, idempotent, dual interface, advisory lock)
- Cross-reference data is queried dynamically at generation time — guides always reflect current governance document state
- Content is deterministic (template constants + dynamic cross-reference data), not AI-generated at runtime
- Tags used: ["DOC-GUIDE", "ALC-GOV"] (distinct from Phase 8.4's ["AI-Guidelines", "ALC-GOV"])
- Two documents produced per execution: User Guide + Admin Guide

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": 3, "tasks": ["4.1", "4.2"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10", "6.11", "6.12", "6.13", "6.14", "6.15"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 6, "tasks": ["8.1"] }
  ]
}
```
