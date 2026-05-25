# Implementation Plan: AI Document Generator (Template-Based)

## Overview

This plan implements the Template-Based AI Document Generator (Phase 5.4) as a series of incremental coding tasks. The implementation builds from database models and schemas upward through services, Celery tasks, API routers, and finally the frontend. Each task builds on previous steps, ensuring no orphaned code.

## Tasks

- [x] 1. Database models and Alembic migration
  - [x] 1.1 Create SQLAlchemy models for DocumentTemplate, GenerationProvenance, CrossReferenceEntry, and GenerationJobMetadata
    - Create `src/backend/src/alcoabase/models/document_generation.py`
    - DocumentTemplate with AuditMixin, unique constraint on (document_version_id, company_id), indexes on company_id and document_type_target
    - GenerationProvenance without AuditMixin (immutable), unique index on generation_id, relationship to CrossReferenceEntry
    - CrossReferenceEntry without AuditMixin (immutable), composite index on (generation_provenance_id, reference_type)
    - GenerationJobMetadata with AuditMixin, unique index on job_id, check constraints on progress_percent and sections_completed
    - Register models in `models/__init__.py`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 1.2 Create Alembic migration for new tables
    - Generate migration with `uv run alembic revision --autogenerate`
    - Verify migration creates document_templates, generation_provenance, cross_reference_entries, generation_job_metadata tables
    - Include all constraints, indexes, and foreign keys
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 1.3 Write property test for multi-tenancy isolation on models
    - **Property 2: Multi-Tenancy Isolation**
    - **Validates: Requirements 1.9, 2.8, 3.7, 5.6, 6.7, 7.8, 9.7**

- [x] 2. Pydantic schemas for request/response validation
  - [x] 2.1 Create Pydantic schemas in `src/backend/src/alcoabase/schemas/document_generation.py`
    - Request schemas: TemplateRegisterRequest, GenerateFromTemplateRequest, DocumentReviewRequest
    - Response schemas: JobAcceptedResponse, TemplateResponse, TemplateListResponse, GenerationJobStatusResponse, ProvenanceResponse, CrossReferenceResponse, CrossReferenceListResponse, DocumentReviewResponse, GeneratedDocumentResponse, GeneratedDocumentListResponse
    - Apply Field validators for max_length, min_length constraints
    - _Requirements: 1.1, 1.13, 2.1, 2.13, 6.2, 6.10_

  - [x] 2.2 Write property test for input validation boundaries
    - **Property 19: Input Validation Boundaries**
    - **Validates: Requirements 1.13, 2.13**

- [x] 3. Template Analysis Service
  - [x] 3.1 Implement TemplateAnalysisService in `src/backend/src/alcoabase/services/template_analysis.py`
    - Implement `analyze_template()`: extract section hierarchy, numbering scheme, paragraph styles, table structures, header/footer patterns, placeholder markers using python-docx
    - Implement `detect_placeholders()`: scan text for `{{IDENTIFIER}}` or `{{IDENTIFIER:parameter}}` patterns
    - Implement `register_template()`: check duplicates, create job, dispatch Celery task
    - Implement `get_template()` and `list_templates()` with company scoping and pagination
    - Implement `validate_docx_extension()` for file type validation
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.9, 1.10_

  - [x] 3.2 Write property test for template analysis round-trip
    - **Property 1: Template Analysis Round-Trip**
    - **Validates: Requirements 1.2, 1.3, 10.1**

  - [x] 3.3 Write unit tests for TemplateAnalysisService
    - Test placeholder detection with various patterns
    - Test duplicate template registration returns existing
    - Test .docx validation rejects non-.docx files
    - Test company scoping on list/get operations
    - _Requirements: 1.3, 1.7, 1.9, 1.10_

- [x] 4. Cross-Reference Service
  - [x] 4.1 Implement CrossReferenceService in `src/backend/src/alcoabase/services/cross_reference.py`
    - Implement `build_cross_reference_map()`: extract REQ-\d{1,5}, URS-\d{1,3}\.\d{1,3}, TC-\d{1,5}, TEST-\d{1,5}, heading numbering patterns from reference documents (max 500 entries per doc)
    - Implement `extract_references_from_text()`: pure function for regex-based reference extraction
    - Implement `validate_references_in_output()`: check generated text for references not in the map, flag as unverified
    - Implement `get_cross_references()` and `auto_select_reference_documents()`
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 4.2 Write property tests for cross-reference extraction and formatting
    - **Property 5: Cross-Reference Extraction Completeness**
    - **Property 6: Cross-Reference Formatting Threshold**
    - **Property 7: Cross-Reference Validation**
    - **Validates: Requirements 3.1, 3.3, 3.4**

- [-] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Placeholder Processor
  - [x] 6.1 Implement PlaceholderProcessor in `src/backend/src/alcoabase/services/placeholder_processor.py`
    - Define STANDARD_MARKERS class variable and MAX_PLACEHOLDERS_PER_TEMPLATE = 50
    - Implement `process_placeholder()`: route to appropriate handler based on marker type
    - Implement `generate_section_content()`: 1-10 paragraphs of prose via InferenceClient
    - Implement `generate_requirement_list()`: numbered list, max 200 items, 500 chars each
    - Implement `generate_cross_reference_section()`: table if >= 5 items, list if < 5
    - Implement `generate_table()`: header row + 2-50 data rows, max 8 columns
    - Implement `generate_procedure_steps()`: numbered steps, max 50, from SOPs/WIs
    - Implement `generate_risk_assessment()`: table with Risk ID, Severity(1-5), Likelihood(1-5), RPN(S×L), Mitigation, 2-25 rows
    - Implement `is_recognized_marker()` for standard marker validation
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

  - [x] 6.2 Write property test for Risk Assessment RPN correctness
    - **Property 17: Risk Assessment RPN Correctness**
    - **Validates: Requirements 10.5**

  - [x] 6.3 Write unit tests for PlaceholderProcessor
    - Test each placeholder type generates correct format
    - Test unrecognized markers fall back to SECTION_CONTENT
    - Test max 50 placeholders per template enforcement
    - Test empty results handling for REQUIREMENT_LIST and PROCEDURE_STEPS
    - _Requirements: 10.1, 10.6, 10.8, 10.9_

- [x] 7. Template Document Generator Service
  - [x] 7.1 Implement TemplateDocumentGeneratorService in `src/backend/src/alcoabase/services/template_document_generator.py`
    - Implement `request_generation()`: validate inputs, check concurrent jobs, dispatch Celery task
    - Implement `get_job_status()` with company scoping
    - Implement `execute_generation_pipeline()`: full pipeline orchestration (load template → retrieve KB → generate sections → assemble DOCX → store)
    - Implement `retrieve_knowledge_context()`: query KnowledgeService with relevance >= 0.3, top 10 chunks, reference doc excerpts up to 2000 chars
    - Implement `generate_section()`: call InferenceClient with retry-once-then-placeholder logic
    - Implement `build_section_prompt()`: construct messages array with Technical Writer system prompt, cross-reference map, section context
    - Implement `manage_context_window()`: summarize preceding sections to max 1000 tokens, trim KB chunks if context exceeds 6000 tokens
    - Implement `assemble_docx()`: preserve template formatting, substitute header/footer tokens, populate document properties, add Sources appendix, validate OPC compliance
    - Implement `validate_output_docx()`: verify valid ZIP/OPC structure
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 5.1, 5.2, 5.5, 5.7, 5.8, 7.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [x] 7.2 Write property tests for DOCX assembly and context management
    - **Property 3: Template Formatting Preservation**
    - **Property 8: Output Document Completeness**
    - **Property 15: Knowledge Base Relevance Ordering**
    - **Property 16: Context Window Management**
    - **Property 18: No Raw Placeholders in Output**
    - **Property 20: Header/Footer Token Substitution**
    - **Validates: Requirements 2.4, 4.1, 4.2, 4.6, 4.7, 4.9, 4.10, 9.1, 9.2, 9.4, 10.7, 4.3**

  - [x] 7.3 Write unit tests for TemplateDocumentGeneratorService
    - Test section generation retry logic (retry once, placeholder on second failure)
    - Test 50 MB output limit with section-boundary truncation
    - Test concurrent generation prevention (same template_id + title)
    - Test knowledge base empty results fails job
    - Test reference document prioritization in context
    - _Requirements: 2.5, 2.6, 2.9, 2.11, 7.6_

- [x] 8. Generated Document Review Service
  - [x] 8.1 Implement GeneratedDocReviewService in `src/backend/src/alcoabase/services/generated_doc_review.py`
    - Implement `review_document()`: approve transitions Draft → Review (enters BPMN workflow), reject marks ContentStatus as "rejected"
    - Implement `list_generated_documents()`: filter by content_status, document_type, date range, with pagination
    - Implement `is_ai_generated()`: check for associated GenerationProvenance record
    - Implement `get_content_status()`: retrieve current ContentStatus
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x] 8.2 Write property tests for generated document status
    - **Property 11: Generated Document Initial Status**
    - **Property 12: Pending/Rejected Exclusion from Standard Search**
    - **Validates: Requirements 6.1, 6.6**

  - [x] 8.3 Write unit tests for GeneratedDocReviewService
    - Test approve transitions document correctly
    - Test reject marks ContentStatus as "rejected"
    - Test review on non-AI-generated document returns 422
    - Test review on already-reviewed document returns 409
    - _Requirements: 6.3, 6.4, 6.8, 6.9_

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Celery tasks for template analysis and document generation
  - [x] 10.1 Implement Celery tasks in `src/backend/src/alcoabase/tasks/document_generation_tasks.py`
    - Implement `analyze_template_task`: download .docx from MinIO, validate format, extract structure, detect placeholders, persist TemplateAnalysis, complete job (soft_time_limit=120, max_retries=2, queue="ai_operations")
    - Implement `generate_document_task`: full pipeline execution with progress reporting, 600s timeout, retry strategy for transient errors, section-level retry with placeholder fallback (soft_time_limit=600, max_retries=2, queue="ai_operations")
    - Handle retryable exceptions (ConnectionError, OSError, InferenceTimeoutError, InferenceConnectionError) with exponential backoff
    - Handle non-retryable exceptions (InferenceError, ValueError, SoftTimeLimitExceeded) as permanent failures
    - _Requirements: 1.2, 1.8, 1.12, 2.2, 2.9, 7.1, 7.2, 7.5, 7.7_

  - [x] 10.2 Write property test for progress monotonicity
    - **Property 13: Progress Monotonicity**
    - **Validates: Requirements 7.2**

  - [x] 10.3 Write property test for all-or-nothing generation integrity
    - **Property 10: All-or-Nothing Generation Integrity**
    - **Validates: Requirements 5.8, 7.5**

  - [x] 10.4 Write property test for concurrent generation prevention
    - **Property 14: Concurrent Generation Prevention**
    - **Validates: Requirements 7.6**

- [x] 11. FastAPI routers
  - [x] 11.1 Implement Template Management Router in `src/backend/src/alcoabase/api/document_templates.py`
    - POST `/api/documents/templates/register`: register template, return 202 with job_id; handle duplicate (200), non-.docx (422), not found (404)
    - GET `/api/documents/templates`: list templates with pagination and document_type_target filter
    - GET `/api/documents/templates/{template_id}`: get template with full analysis
    - All endpoints require X-Company-Id header for tenant scoping
    - POST requires X-Change-Reason header
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.9, 1.10, 1.11, 1.13_

  - [x] 11.2 Implement Template Generation Router in `src/backend/src/alcoabase/api/document_generation.py`
    - POST `/api/documents/generate-from-template`: start generation, return 202 with job_id; validate template_id (404), reference_document_ids (422), empty instructions (422), concurrent job (409)
    - GET `/api/documents/generate-from-template/{job_id}/status`: return job progress and status
    - GET `/api/documents/{document_id}/provenance`: return full generation provenance (404 if not AI-generated)
    - GET `/api/documents/{document_id}/cross-references`: return cross-reference map
    - All endpoints require X-Company-Id header
    - POST requires X-Change-Reason header
    - _Requirements: 2.1, 2.8, 2.10, 2.11, 2.12, 2.13, 3.5, 5.3, 5.6, 7.3, 7.6, 7.8, 7.9_

  - [x] 11.3 Implement Generated Document Review Router in `src/backend/src/alcoabase/api/document_review.py`
    - POST `/api/documents/{document_id}/review`: approve or reject, return 200 with updated status; handle non-AI-generated (422), already reviewed (409), comment too long (422)
    - GET `/api/documents/generated`: list AI-generated documents with filters (content_status, document_type, date range) and pagination
    - All endpoints require X-Company-Id header
    - POST requires X-Change-Reason header
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.7, 6.8, 6.9, 6.10_

  - [x] 11.4 Register new routers in `src/backend/src/alcoabase/api/router.py`
    - Import and include document_templates, document_generation, and document_review routers
    - _Requirements: 1.1, 2.1, 6.2_

  - [x] 11.5 Write property test for reference document prioritization
    - **Property 4: Reference Document Prioritization**
    - **Validates: Requirements 2.5, 9.3**

- [x] 12. Provenance immutability enforcement
  - [x] 12.1 Implement application-layer immutability for GenerationProvenance and CrossReferenceEntry
    - Add SQLAlchemy event listeners to prevent UPDATE/DELETE on generation_provenance and cross_reference_entries tables
    - Implement `previous_generation_id` linking for regeneration traceability
    - Ensure provenance write failure causes entire generation job to fail
    - _Requirements: 5.4, 5.7, 5.8, 8.2, 8.3_

  - [x] 12.2 Write property test for provenance completeness and immutability
    - **Property 9: Provenance Completeness and Immutability**
    - **Validates: Requirements 5.1, 5.2, 5.4, 9.5**

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Frontend Zustand store and API integration
  - [x] 14.1 Create TypeScript types in `src/frontend/src/types/documentGenerator.ts`
    - Define interfaces: DocumentTemplate, TemplateAnalysis, TemplateSection, GenerationJob, GenerationJobStatus, GeneratedDocument, ProvenanceData, CrossReference, TemplateRegisterRequest, GenerateFromTemplateRequest, DocumentReviewRequest, GeneratedDocFilters
    - _Requirements: 1.1, 2.1, 6.2, 7.3_

  - [x] 14.2 Create Zustand store in `src/frontend/src/stores/documentGeneratorStore.ts`
    - Implement state: templates, selectedTemplate, templateAnalysis, activeJobs, generatedDocuments, currentProvenance, crossReferences, isRegistering, isGenerating, pollingInterval
    - Implement actions: fetchTemplates, registerTemplate, getTemplateAnalysis, startGeneration, pollJobStatus, reviewDocument, fetchGeneratedDocuments, fetchProvenance, fetchCrossReferences, startPolling, stopPolling
    - Use apiClient for all API calls with proper headers (X-Company-Id, X-Change-Reason)
    - Implement polling with setInterval for active jobs
    - _Requirements: 7.3_

- [x] 15. Frontend page and panels
  - [x] 15.1 Create DocumentGeneratorPage in `src/frontend/src/pages/DocumentGeneratorPage.tsx`
    - Main page component with tab navigation between Template Registration, Generation, Review, and Provenance views
    - Wire to documentGeneratorStore
    - Add route in router configuration
    - _Requirements: 1.1, 2.1, 6.2, 7.3_

  - [x] 15.2 Implement TemplateRegistrationPanel and TemplateListPanel
    - TemplateRegistrationPanel: form with document selector, template_name input, document_type_target dropdown, submit button
    - TemplateListPanel: paginated list of registered templates with TemplateCard components showing name, type, status, section count
    - AnalysisPreview: display template analysis (section hierarchy, placeholders, styles)
    - _Requirements: 1.1, 1.5, 1.6_

  - [x] 15.3 Implement GenerationSetupPanel and JobProgressMonitor
    - GenerationSetupPanel: template selector, title input, generation instructions textarea, reference document multi-select, output folder path input, generate button
    - JobProgressMonitor: progress bar, current section name, sections completed/total, estimated time remaining, error display
    - Implement polling via store's startPolling/stopPolling
    - _Requirements: 2.1, 7.1, 7.2, 7.3_

  - [x] 15.4 Implement ReviewWorkflowPanel and ProvenanceViewer
    - ReviewWorkflowPanel: list of generated documents filterable by status, approve/reject buttons with comment input
    - ProvenanceViewer: sources table, cross-reference viewer, per-section provenance breakdown
    - CrossReferenceViewer: display cross-reference map grouped by reference_type
    - _Requirements: 5.3, 6.2, 6.5_

  - [x] 15.5 Write frontend tests for DocumentGeneratorPage
    - Test template registration form validation
    - Test generation setup form submission
    - Test job progress polling and display
    - Test review workflow approve/reject actions
    - _Requirements: 1.1, 2.1, 6.2, 7.3_

- [ ] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (20 properties mapped to 14 test sub-tasks)
- Unit tests validate specific examples and edge cases
- The design uses Python (FastAPI, SQLAlchemy, python-docx, Celery) throughout — no language selection needed
- All backend code lives under `src/backend/src/alcoabase/`
- All frontend code lives under `src/frontend/src/`
- Existing services (InferenceClient, KnowledgeService, StorageService, JobTracker, AgentRegistryService) are dependencies — not reimplemented

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "4.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.2", "6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "7.1", "8.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "8.2", "8.3", "10.1"] },
    { "id": 6, "tasks": ["10.2", "10.3", "10.4", "11.1", "11.2", "11.3"] },
    { "id": 7, "tasks": ["11.4", "11.5", "12.1"] },
    { "id": 8, "tasks": ["12.2", "14.1"] },
    { "id": 9, "tasks": ["14.2"] },
    { "id": 10, "tasks": ["15.1"] },
    { "id": 11, "tasks": ["15.2", "15.3", "15.4"] },
    { "id": 12, "tasks": ["15.5"] }
  ]
}
```
