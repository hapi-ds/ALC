# Implementation Plan: Cross-Sector AI Regulatory Guidelines

## Overview

Implement the `GuidelinesGeneratorService` — a backend service that programmatically generates 4 AI usage guideline documents (1 master cross-sector + 3 sector-specific: Pharma/GMP, MedTech/ISO 13485, IVD/IVDR), uploads them into the ALC corporate governance environment, applies tags and the governance workflow, and supports versioning on re-execution. The service follows the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible). Guideline content is assembled from deterministic Python template constants combined with dynamic risk framework data from Phase 8.1.

## Tasks

- [ ] 1. Define schemas, data models, and content module
  - [ ] 1.1 Create Pydantic schemas for GuidelinesGenerationReport and GuidelinesGenerationError
    - Create `src/backend/src/alcoabase/schemas/guidelines_generation.py`
    - Define `DocumentReportEntry` model with fields: document_id (int), document_uuid (str), title (str), sector (str), version_number (int), tags_applied (list[str]), workflow_state (str), is_new_document (bool), policy_section_count (int)
    - Define `GuidelinesGenerationReport` model with fields: documents_created (list[DocumentReportEntry]), total_documents (int), total_policy_sections (int), risk_tiers_referenced (list[str]), regulatory_frameworks_covered (list[str]), total_duration_ms (int)
    - Define `GuidelinesGenerationError` model with fields: error (str), failed_operation (str), document_title (str | None), detail (str | None)
    - _Requirements: 5.4, 6.5_

  - [ ] 1.2 Create guidelines content module with template constants and sector module definitions
    - Create `src/backend/src/alcoabase/services/guidelines_content.py`
    - Define `RegulatoryFramework` frozen dataclass with fields: identifier (str), display_name (str), key_articles (list[str])
    - Define `SectorModule` frozen dataclass with fields: sector_id (str), title (str), sector_label (str), applicable_regulations (list[RegulatoryFramework]), dedicated_subsections (list[str]), risk_elevation_rules (dict[str, str])
    - Define `RiskFrameworkContext` dataclass with fields: task_types (list), effective_tiers (dict[str, str]), tier_definitions (dict), company_profile_active (bool), risk_factors_map (dict[str, list[str]])
    - Define `DocumentResult` dataclass with fields: document_id (int), document_uuid (str), title (str), sector (str), version_number (int), is_new_document (bool), tags_applied (list[str]), workflow_state (str)
    - Define constants: `MASTER_GUIDELINE_TITLE`, `PHARMA_GUIDELINE_TITLE`, `MEDTECH_GUIDELINE_TITLE`, `IVD_GUIDELINE_TITLE`, `GUIDELINE_TAGS` (["AI-Guidelines", "ALC-GOV"]), `GUIDELINE_DOCUMENT_TYPE`
    - Define `REGULATORY_FRAMEWORKS` list with EU AI Act, 21 CFR Part 11, EU GMP Annex 11, ISO 13485, IVDR 2017/746 (each with key_articles)
    - Define `PROHIBITED_USES` list with 4 prohibited operations
    - Define `SECTOR_MODULES` list with 3 SectorModule configs:
      - Pharma/GMP: GMP Annex 11, 21 CFR Part 11, EU GMP Chapter 4, ICH Q9/Q10; dedicated subsections for GMP data integrity, CSV expectations, AI model qualification, change control
      - MedTech/ISO 13485: ISO 13485:2016, MDR 2017/745, IEC 62304, FDA 21 CFR 820; dedicated subsections for design control, software lifecycle, risk management, post-market surveillance
      - IVD/IVDR: IVDR 2017/746, ISO 13485:2016, EU common specifications; dedicated subsections for performance evaluation, common specifications, clinical evidence, notified body expectations
    - Implement content assembly functions for each document section (header, purpose/scope, regulatory overview, risk summary, policy sections, human oversight, audit requirements, prohibited uses, glossary, URS references, regulatory reference table, sector-specific sections)
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 4.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [ ] 2. Implement GuidelinesGeneratorService core
  - [ ] 2.1 Create GuidelinesGeneratorService class with execute() orchestrator
    - Create `src/backend/src/alcoabase/services/guidelines_generator_service.py`
    - Implement `GuidelinesGeneratorService.__init__(self, session: AsyncSession, storage_service: StorageService | None = None, uuid_service: UUIDService | None = None)`
    - Implement `async execute() -> GuidelinesGenerationReport` orchestrator that calls each step in sequence: validate_prerequisites → load_risk_framework_data → check_urs_availability → generate all 4 documents → validate all content → upload/version each document → apply tags → apply workflows → build report
    - Include timing measurement for `total_duration_ms`
    - Use structured logging with `guidelines_step` field throughout
    - Acquire DB advisory lock at start to prevent concurrent generation
    - _Requirements: 5.1, 5.3, 5.9, 6.1_

  - [ ] 2.2 Implement _validate_prerequisites() step
    - Query for ALC company by slug "alc-corporate" — raise RuntimeError with "ALC corporate environment not provisioned. Run Phase 8.2 seed first." if not found
    - Query for doc-admin user by username "alc-doc-admin" — raise RuntimeError with "ALC Document Administrator user not found. Run Phase 8.2 seed first." if not found
    - Query for governance workflow by document_tag "ALC-GOV" and company_id — raise RuntimeError with "ALC Governance workflow not found. Run Phase 8.2 seed first." if not found
    - Return tuple of (company, doc_admin_user, workflow_definition)
    - Check prerequisites in strict order: company → doc-admin → workflow (halt on first failure)
    - _Requirements: 3.6, 3.7, 3.8, 8.1, 8.2, 8.3, 8.9_

  - [ ] 2.3 Implement _load_risk_framework_data() step
    - Query all active AI_Task_Types for the ALC company
    - Raise RuntimeError with "No AI task types registered. Run Phase 8.1 seed first." if zero found
    - Query active Company_Risk_Profile for tier overrides (if exists)
    - Resolve effective tier per task type: company override if present, else default_risk_tier
    - Load TIER_DEFINITIONS for control sets (HITL, audit depth, validations, output labeling, expiry, rate limits)
    - Build and return `RiskFrameworkContext` with company_profile_active flag
    - If no active profile, set company_profile_active=False (triggers notice in generated content)
    - _Requirements: 1.3, 1.7, 1.8, 4.1, 4.2, 4.3, 4.5, 4.6, 8.4_

  - [ ] 2.4 Implement _check_urs_availability() and content generation methods
    - `_check_urs_availability()`: Query for document with tags ["URS", "ALC-GOV"] in ALC company; return True/False
    - `_generate_master_guideline()`: Assemble master guideline from template constants + risk context; include all required sections (header, purpose/scope, regulatory overview, risk summary, policy sections per task type, human oversight, audit requirements, prohibited uses, roles/responsibilities, periodic review, glossary, URS references, regulatory reference table)
    - `_generate_sector_guideline()`: Assemble sector guideline from SectorModule config + risk context; include sector regulatory context, sector risk considerations, sector policy sections, sector risk mapping table, validation requirements, record keeping, dedicated subsections, cross-references, regulatory reference table
    - Include URS_Reference_Blocks when available, or notice when unavailable
    - Include "default classifications applied" notice when no active Company_Risk_Profile
    - _Requirements: 1.2, 1.4, 1.5, 2.2, 2.6, 2.7, 4.5, 8.8_

  - [ ] 2.5 Implement content validation methods
    - `_validate_content(content, document_title)`: Check content is non-empty and contains at least one Markdown heading (regex `^#{1,3}\s`); raise RuntimeError with document title if invalid
    - `_validate_section_lengths(content, document_title)`: For sector guidelines, check each section has ≥ 100 characters of content (excluding header); raise RuntimeError identifying section name and document title if any section fails
    - _Requirements: 2.8, 8.6, 8.7_

  - [ ] 2.6 Implement document upload, versioning, tagging, and workflow methods
    - `_detect_existing_document(title, company)`: Query by title + tags ["AI-Guidelines", "ALC-GOV"] + company_id; return Document or None
    - `_upload_or_version_document(title, content, company, doc_admin, workflow)`: If not found → generate Document-UUID (YYYY-NNNNN), upload to MinIO, INSERT Document + DocumentVersion (major=1, minor=0); if found → SELECT MAX(major_version), upload new version to MinIO, INSERT DocumentVersion (major=N+1, minor=0), UPDATE current_status to "Draft"
    - `_apply_tags(document, is_new)`: Insert "AI-Guidelines" and "ALC-GOV" DocumentTag records if not already present
    - `_apply_workflow(document, workflow, doc_admin)`: Create/update DocumentState with current_state="Draft", workflow_id, updated_by=doc_admin
    - Set created_by to alc-doc-admin user; record change_reason "AI Regulatory Guidelines Generation — Phase 8.4 automated governance document creation"
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [ ] 3. Checkpoint - Ensure core service logic is complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement CLI script and API endpoint
  - [ ] 4.1 Create CLI script for guidelines generation
    - Create `src/backend/src/alcoabase/scripts/generate_ai_guidelines.py`
    - Create async session, call `GuidelinesGeneratorService.execute()`, manage transaction (commit on success, rollback on failure)
    - Print GuidelinesGenerationReport as JSON to stdout on success (exit 0)
    - Print GuidelinesGenerationError as JSON to stderr on failure (exit 1)
    - Ensure script is invocable via `uv run python -m alcoabase.scripts.generate_ai_guidelines`
    - _Requirements: 5.1, 5.5_

  - [ ] 4.2 Create API endpoint for guidelines generation
    - Create `src/backend/src/alcoabase/api/admin_guidelines.py` with `POST /api/admin/generate-ai-guidelines`
    - Require system_administrator or document_administrator role authentication
    - Require X-Change-Reason header (return 400 if missing)
    - Return 401 for unauthorized, 403 for insufficient permissions, 409 for concurrent generation, 200 with GuidelinesGenerationReport on success, 500 with GuidelinesGenerationError on failure
    - Register the router in `api/router.py`
    - _Requirements: 5.2, 5.6, 5.7, 5.8, 5.9_

- [ ] 5. Checkpoint - Ensure CLI and API work end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Write property-based tests
  - [ ]* 6.1 Write property test for document structure invariant (Property 1)
    - **Property 1: Document structure invariant**
    - **Validates: Requirements 1.2, 2.2**
    - Create test in `src/backend/tests/properties/test_guidelines_generator_properties.py`
    - Generate random sets of AI_Task_Types (N ≥ 1) with varying tiers and risk_factors
    - Verify master guideline contains all required sections in specified order
    - Verify each sector guideline contains all required sector sections in specified order

  - [ ]* 6.2 Write property test for risk data completeness (Property 2)
    - **Property 2: Risk data completeness in guidelines**
    - **Validates: Requirements 1.3, 4.2, 4.3**
    - Generate random task types with assigned tiers and control sets
    - Verify each Risk_Integration_Block contains: display_name, tier level, all controls (HITL, audit depth, validations, output labeling, expiry, rate limits), and risk_factors array

  - [ ]* 6.3 Write property test for policy section structural completeness (Property 3)
    - **Property 3: Policy section structural completeness**
    - **Validates: Requirements 1.4, 7.3**
    - Generate random task types, produce Policy_Sections
    - Verify each Policy_Section contains exactly 5 subsections in order: (a) permitted uses, (b) restrictions, (c) compliance procedure (3–15 steps), (d) required evidence, (e) consequences of non-compliance

  - [ ]* 6.4 Write property test for sector non-contradiction invariant (Property 4)
    - **Property 4: Sector non-contradiction invariant**
    - **Validates: Requirements 2.7**
    - Generate random tier assignments for task types
    - Verify no sector guideline assigns a lower tier than the master guideline
    - Verify sector control sets are supersets of (or equal to) master control sets

  - [ ]* 6.5 Write property test for section minimum content validation (Property 5)
    - **Property 5: Section minimum content validation**
    - **Validates: Requirements 2.8**
    - Generate content with varying section lengths (some < 100 chars, some ≥ 100 chars)
    - Verify validation raises RuntimeError for sections < 100 chars, passes for valid sections

  - [ ]* 6.6 Write property test for document governance completeness (Property 6)
    - **Property 6: Document governance completeness**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    - Run service with valid prerequisites and random task type sets
    - Verify each document has: Document record with created_by=doc_admin, document_uuid matching `\d{4}-\d{5}`, DocumentTag records for both tags, DocumentState with current_state="Draft"

  - [ ]* 6.7 Write property test for effective tier resolution (Property 7)
    - **Property 7: Effective tier resolution**
    - **Validates: Requirements 4.1, 4.5**
    - Generate random default tiers and company profile overrides
    - Verify: override used when present, default used otherwise
    - Verify notice included when no active profile

  - [ ]* 6.8 Write property test for transaction atomicity (Property 8)
    - **Property 8: Transaction atomicity on failure**
    - **Validates: Requirements 5.3, 6.7, 8.5**
    - Simulate failures at each step (prerequisite, risk data, content, upload, tags, workflow)
    - Verify DB contains zero new records from the current attempt after rollback

  - [ ]* 6.9 Write property test for versioning idempotency (Property 9)
    - **Property 9: Versioning idempotency**
    - **Validates: Requirements 6.1, 6.3, 6.4, 6.5**
    - Run service N times (N drawn from 1–5)
    - Verify exactly 4 Document records (one per title) with exactly N DocumentVersion records each
    - Verify strictly increasing major_version numbers
    - Verify is_new_document=True for first, False for subsequent

  - [ ]* 6.10 Write property test for report accuracy (Property 10)
    - **Property 10: Report accuracy**
    - **Validates: Requirements 5.4, 6.5**
    - Run service with random task type configurations
    - Verify report fields match actual DB state: 4 entries, correct total_documents, total_policy_sections matches actual count, risk_tiers_referenced matches used tiers, total_duration_ms > 0

  - [ ]* 6.11 Write property test for content validation correctness (Property 11)
    - **Property 11: Content validation correctness**
    - **Validates: Requirements 8.6, 8.7**
    - Generate random strings (some with headings, some without, some empty)
    - Verify validation passes iff string is non-empty AND contains `^#{1,3}\s` pattern
    - Verify error message includes document title on failure

  - [ ]* 6.12 Write property test for regulatory citation completeness (Property 12)
    - **Property 12: Regulatory citation completeness**
    - **Validates: Requirements 7.1, 7.2, 7.7**
    - Generate content with random task types
    - Verify every control requirement has an inline citation (regulation + article) or "Industry best practice" annotation
    - Verify Regulatory Reference Table has ≥ 1 row per distinct regulation cited

  - [ ]* 6.13 Write property test for policy section count invariant (Property 13)
    - **Property 13: Policy section count invariant**
    - **Validates: Requirements 1.1, 7.5**
    - Generate with N task types (N ≥ 8)
    - Verify master guideline has exactly N Policy_Sections
    - Verify each sector guideline has ≥ 6 Policy_Sections
    - Verify total_policy_sections in report equals actual count across all 4 documents

- [ ] 7. Write unit tests
  - [ ]* 7.1 Write unit tests for prerequisites validation and risk framework loading
    - Create `src/backend/tests/unit/test_guidelines_generator_service.py`
    - Test: validate_prerequisites with all present (returns company, user, workflow)
    - Test: validate_prerequisites no company (RuntimeError with correct message)
    - Test: validate_prerequisites no doc-admin (RuntimeError with correct message)
    - Test: validate_prerequisites no workflow (RuntimeError with correct message)
    - Test: validate_prerequisites check order (company before doc-admin before workflow)
    - Test: load_risk_framework_data with zero task types (RuntimeError)
    - Test: load_risk_framework_data with active profile (uses overrides)
    - Test: load_risk_framework_data without profile (uses defaults, company_profile_active=False)
    - Test: check_urs_availability returns True when URS exists, False when missing
    - _Requirements: 1.7, 1.8, 4.1, 4.5, 4.6, 8.1, 8.2, 8.3, 8.4, 8.8, 8.9_

  - [ ]* 7.2 Write unit tests for content generation and validation
    - Test: generate_master_guideline has all required sections in order
    - Test: generate_master_guideline includes Risk_Integration_Blocks for each task type
    - Test: generate_master_guideline includes all 4 prohibited uses
    - Test: generate_master_guideline includes URS notice when unavailable
    - Test: generate_master_guideline includes "default classifications" notice when no profile
    - Test: generate_sector_guideline (Pharma) has 4 dedicated subsections
    - Test: generate_sector_guideline (MedTech) has 4 dedicated subsections
    - Test: generate_sector_guideline (IVD) has 4 dedicated subsections
    - Test: generate_sector_guideline includes mapping table with all task types
    - Test: sector guideline never assigns lower tier than master
    - Test: validate_content passes for valid content with headings
    - Test: validate_content raises RuntimeError for empty content
    - Test: validate_content raises RuntimeError for content without headings
    - Test: validate_section_lengths passes when all sections ≥ 100 chars
    - Test: validate_section_lengths raises RuntimeError identifying short section
    - Test: policy section has exactly 5 subsections (a–e) in order
    - Test: compliance procedure has 3–15 numbered steps
    - Test: header contains version number and ISO 8601 timestamp
    - Test: header lists all applicable regulatory frameworks
    - Test: roles and responsibilities section has correct role mappings
    - Test: periodic review section references review_cycle_days
    - Test: regulatory reference table present with required columns
    - Test: URS reference blocks match "Implements: REQ-{MODULE}-{NN}" pattern
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 4.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.6, 8.7_

  - [ ]* 7.3 Write unit tests for document operations and report building
    - Test: detect_existing_document found (returns Document)
    - Test: detect_existing_document not found (returns None)
    - Test: upload_or_version new document has correct title, type, company_id, created_by, UUID format
    - Test: upload_or_version existing document increments major_version correctly
    - Test: apply_tags creates both "AI-Guidelines" and "ALC-GOV" tags on new document
    - Test: apply_tags does not duplicate on re-run
    - Test: apply_workflow creates DocumentState with state="Draft" on new document
    - Test: apply_workflow resets to "Draft" on new version
    - Test: report has 4 entries, all is_new_document=True on first run
    - Test: report correctly identifies new vs versioned on subsequent runs
    - Test: report total_policy_sections matches actual count
    - Test: report risk_tiers_referenced matches used tiers
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 8. Write integration tests
  - [ ]* 8.1 Write integration tests for CLI, API, and end-to-end flows
    - Create `src/backend/tests/integration/test_guidelines_generator_integration.py`
    - Test: CLI success (exit 0, stdout is valid JSON GuidelinesGenerationReport with 4 documents)
    - Test: CLI failure without prerequisites (exit 1, stderr has JSON error with failed_operation)
    - Test: API endpoint success (POST returns 200 with GuidelinesGenerationReport)
    - Test: API endpoint unauthorized (POST without auth returns 401)
    - Test: API endpoint forbidden (POST with non-admin role returns 403)
    - Test: API endpoint missing header (POST without X-Change-Reason returns 400)
    - Test: API endpoint concurrent generation (second request returns 409)
    - Test: Full idempotent run (two consecutive runs produce 4 Documents with 2 versions each)
    - Test: Partial existence (some documents exist, others don't — correct new/version behavior)
    - Test: Documents appear in governance folder (documents with tags appear in virtual folder query)
    - Test: Generation with URS available (URS_Reference_Blocks included)
    - Test: Generation without URS (notice included)
    - Test: Generation with company risk profile (overrides reflected)
    - Test: Generation with default tiers (defaults used with notice)
    - Test: Rollback on upload failure (no partial documents after MinIO failure)
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 8.5, 8.8_

- [ ] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The service uses Python 3.12+ with FastAPI, SQLAlchemy 2.0 async, and Pydantic v2
- All tests use pytest + pytest-asyncio + Hypothesis (property-based) as per project conventions
- CLI invocation: `uv run python -m alcoabase.scripts.generate_ai_guidelines`
- The guidelines_content.py module isolates large template constants and sector configs from service orchestration logic
- Follows ALCSeedService / URSGeneratorService pattern exactly (single transaction, idempotent, dual interface, advisory lock)
- Risk data is queried dynamically from Phase 8.1 at generation time — guidelines always reflect current risk profile
- Content is deterministic (template constants + dynamic risk data), not AI-generated at runtime

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": 3, "tasks": ["4.1", "4.2"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8", "6.9", "6.10", "6.11", "6.12", "6.13"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 6, "tasks": ["8.1"] }
  ]
}
```
