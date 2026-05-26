# Implementation Plan: AI-Powered Traceability & Gap Discovery

## Overview

This plan implements Phase 5.6 — AI-Powered Traceability & Gap Discovery for AlcoaBase. The implementation follows a bottom-up approach: database models and schemas first, then core services (TraceabilityMatrixService with three-pass matching, OrphanDetectionService, CoverageMetricsService, TraceabilityAlertService), Celery tasks, agent archetype, API routes, and finally the frontend dashboard. Each task builds incrementally on previous work, ensuring no orphaned code.

## Tasks

- [x] 1. Database models, schemas, and migration
  - [x] 1.1 Create SQLAlchemy models for traceability
    - Create file `src/backend/src/alcoabase/models/traceability.py`
    - Define `TraceabilityMatrix` model with immutability event listeners (before_update permits only deleted_at mutation, before_delete raises ImmutableRecordError), composite indexes on (company_id, generation_timestamp) and (company_id, deleted_at)
    - Define `CoverageSnapshot` model with immutability event listeners (before_update and before_delete raise ImmutableRecordError), composite index on (company_id, source_document_uuid, snapshot_date)
    - Define `TraceabilityAlert` model with AuditMixin, unique constraint on (triggering_report_id, company_id), composite index on (company_id, is_resolved)
    - Define `StaleLinkMarker` model with AuditMixin, unique constraint on (matrix_id, requirement_id, triggering_report_id), composite index on (matrix_id, is_cleared)
    - Register immutability listeners using the same pattern as `ImpactReport` in 5.5
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 1.2 Create Pydantic schemas for traceability
    - Create file `src/backend/src/alcoabase/schemas/traceability.py`
    - Define `TraceabilityLinkSchema`, `OrphanRequirementSchema`, `OrphanTestCaseSchema`, `CoverageMetricSchema` with field constraints (max_length, Literal types, ge/le ranges)
    - Define request schemas: `GenerateMatrixRequest` (source_document_ids max 10, target_document_ids max 20, matrix_name 1-200 chars, description max 1000 chars), `ResolveAlertRequest`
    - Define response schemas: `TraceabilityMatrixResponse`, `TraceabilityMatrixListResponse`, `TraceabilityLinkListResponse`, `OrphanRequirementListResponse`, `OrphanTestCaseListResponse`, `DocumentCoverageResponse`, `CoverageSummaryResponse`, `CoverageHistoryResponse`, `TraceabilityAlertResponse`, `AlertListResponse`, `JobStatusResponse`
    - Define filter/pagination schemas: `MatrixFilters`, `LinkFilters`, `OrphanFilters`, `AlertFilters`, `HistoryFilters`
    - _Requirements: 1.1, 1.4, 1.5, 2.3, 3.3, 4.1, 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.2, 9.3, 11.3_

  - [x] 1.3 Create Alembic migration for traceability tables
    - Generate migration with `alembic revision --autogenerate -m "add_traceability_tables"`
    - Verify upgrade creates all tables, indexes, and constraints
    - Verify downgrade drops tables in reverse dependency order: StaleLinkMarker, TraceabilityAlert, CoverageSnapshot, TraceabilityMatrix
    - _Requirements: 10.7_

  - [x] 1.4 Write property tests for model immutability and constraints
    - **Property 7: Immutability Enforcement** — Verify TraceabilityMatrix and CoverageSnapshot reject UPDATE/DELETE via ORM, verify TraceabilityMatrix permits only deleted_at mutation
    - **Validates: Requirements 4.2, 10.1, 10.2**

  - [x] 1.5 Write unit tests for Pydantic schema validation
    - Test field constraints (max_length, Literal enums, ge/le ranges), required vs optional fields
    - Test TraceabilityLinkSchema, OrphanRequirementSchema, OrphanTestCaseSchema, CoverageMetricSchema serialization/deserialization
    - Test GenerateMatrixRequest validation (source max 10, target max 20, name 1-200 chars)
    - _Requirements: 1.4, 1.5, 4.1, 5.1, 10.8_

- [ ] 2. Core service: TraceabilityMatrixService (three-pass matching)
  - [~] 2.1 Implement TraceabilityMatrixService requirement and test case extraction
    - Create file `src/backend/src/alcoabase/services/traceability_matrix.py`
    - Implement `extract_requirements(source_documents, company_id)`: for each source document, extract text via KnowledgeService, use Traceability_Analyst agent via InferenceClient to identify requirement IDs (REQ-NNN, URS-NNN, R.N.N patterns), requirement text (first 500 chars), section headings, and acceptance criteria
    - Implement `extract_test_cases(target_documents, company_id)`: for each target document, extract text via KnowledgeService, use Traceability_Analyst agent to identify test case IDs (TC-NNN, IQ-NNN, OQ-NNN, PQ-NNN patterns), test descriptions, expected results, and section headings
    - Handle InferenceClient unavailability: connection timeout 30s, HTTP 503/429 with 3 retries and exponential backoff, mark job as "failed" on exhaustion
    - Handle per-document extraction timeout (120s): abort request, record timeout event in job metadata
    - _Requirements: 1.2, 1.10, 6.4, 6.7_

  - [~] 2.2 Implement three-pass matching strategy
    - Implement `pass_1_exact_id_match(requirements, test_cases)`: scan test case text for explicit requirement ID citations, assign link_confidence = 1.0
    - Implement `pass_2_cross_reference_match(requirements, test_cases, company_id)`: query CrossReferenceService for structural links between source/target document pairs, assign link_confidence = 0.9
    - Implement `pass_3_semantic_match(requirements, test_cases, company_id)`: compute embedding similarity via KnowledgeService, assign link_confidence = similarity score, discard matches below 0.5 threshold
    - Implement `deduplicate_links(candidate_links)`: for duplicate (requirement_id, test_case_id) pairs, retain link with highest confidence, merge all detection methods into link_methods array
    - Handle KnowledgeService unavailability: skip semantic pass, mark job as "partial_success", record in metadata
    - Handle CrossReferenceService unavailability: skip cross-ref pass, mark job as "partial_success", record in metadata
    - _Requirements: 1.2, 1.3, 1.7, 1.11_

  - [~] 2.3 Implement matrix generation orchestration and persistence
    - Implement `validate_and_enqueue(request, company_id, user_id)`: validate document IDs exist in company scope, check for overlapping source/target, check document count limits (10 source, 20 target), check for existing processing job (same docs → 409)
    - Implement `generate_matrix(job_id, request, company_id, user_id)`: orchestrate full pipeline (extract → match → deduplicate → orphan detect → compute metrics → persist)
    - Implement 600s timeout with partial_success: persist all links discovered so far, record unprocessed requirements
    - Implement parent_matrix_id resolution: find most recent matrix with matching sorted source/target doc UUIDs
    - Implement matrix persistence with 3 retries and exponential backoff on database write failure
    - Capture document versions at generation time (current version_id for each source/target document)
    - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.8, 1.9, 4.1, 4.3, 4.4, 4.5, 4.6_

  - [~] 2.4 Write property test for confidence score assignment
    - **Property 1: Confidence Score Assignment** — Generate link detection results with various methods (exact, cross-ref, semantic with random similarity scores), verify score assignment rules: 1.0 for exact, 0.9 for cross-ref, similarity score for semantic, no links below 0.5
    - **Validates: Requirements 1.3**

  - [~] 2.5 Write property test for link deduplication
    - **Property 2: Link Deduplication** — Generate sets of candidate links with duplicate (requirement_id, test_case_id) pairs via different methods, verify single link retained with highest confidence and all methods recorded in link_methods array
    - **Validates: Requirements 1.7**

  - [ ]* 2.6 Write property test for parent matrix versioning
    - **Property 8: Parent Matrix Versioning** — Generate sequences of matrices for same/different document sets within same company, verify parent_matrix_id chain correctness (null for first, references most recent for subsequent)
    - **Validates: Requirements 4.3**

  - [ ]* 2.7 Write unit tests for TraceabilityMatrixService
    - Test three-pass matching logic, deduplication, timeout handling, validation errors
    - Test partial_success on service unavailability, document version capture
    - Test parent_matrix_id resolution, duplicate job detection (409)
    - Mock InferenceClient, KnowledgeService, CrossReferenceService, JobTracker
    - _Requirements: 1.1–1.12, 4.1–4.6_

- [~] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Orphan Detection Service
  - [~] 4.1 Implement OrphanDetectionService
    - Create file `src/backend/src/alcoabase/services/orphan_detection.py`
    - Implement `identify_orphan_requirements(requirements, links)`: classify requirement as orphan if zero links with link_confidence >= 0.5, produce structured OrphanRequirement list with requirement_id, requirement_text, source_document_uuid, source_section, severity, suggested_action
    - Implement `identify_orphan_test_cases(test_cases, links)`: classify test case as orphan if zero links with link_confidence >= 0.5, produce structured OrphanTestCase list with test_case_id, test_case_text, target_document_uuid, target_section, risk_level, suggested_action
    - Implement `classify_orphan_severity(orphan_requirements, company_id)`: use Traceability_Analyst agent for keyword-based severity classification (critical > major > minor precedence)
    - Implement `classify_orphan_risk_level(orphan_test_cases, company_id)`: use Traceability_Analyst agent for risk classification (high > medium > low), determine suggested_action based on near-miss confidence (0.3-0.49 → link_to_requirement, no match → create_requirement, redundant → remove_test_case)
    - Handle agent timeout (30s): assign default severity "major" for requirements, default risk_level "medium" and suggested_action "link_to_requirement" for test cases, record classification failure in matrix metadata
    - _Requirements: 1.12, 2.1, 2.2, 2.4, 2.5, 3.1, 3.2, 3.4, 3.5_

  - [ ]* 4.2 Write property test for orphan requirement identification
    - **Property 4: Orphan Requirement Identification** — Generate random requirements and links with various confidence scores, verify orphan set = requirements with zero links >= 0.5, verify count = total_requirements - covered_requirements
    - **Validates: Requirements 1.12, 2.1**

  - [ ]* 4.3 Write property test for orphan test case identification
    - **Property 5: Orphan Test Case Identification** — Generate random test cases and links with various confidence scores, verify orphan set = test cases with zero links >= 0.5, verify count = total_test_cases - linked_test_cases
    - **Validates: Requirements 3.1**

  - [ ]* 4.4 Write property test for orphan classification by keyword analysis
    - **Property 6: Orphan Classification by Keyword Analysis** — Generate requirement/test case texts with random keyword combinations from each category, verify severity/risk_level follows precedence rules (critical > major > minor, high > medium > low)
    - **Validates: Requirements 2.4, 3.4**

  - [ ]* 4.5 Write unit tests for OrphanDetectionService
    - Test orphan identification logic, severity classification, risk_level classification
    - Test default assignment on agent timeout, suggested_action determination
    - Mock InferenceClient for agent calls
    - _Requirements: 1.12, 2.1–2.7, 3.1–3.7_

- [ ] 5. Coverage Metrics Service
  - [~] 5.1 Implement CoverageMetricsService
    - Create file `src/backend/src/alcoabase/services/coverage_metrics.py`
    - Implement `compute_coverage_metrics(requirements, test_cases, links, source_docs, target_docs)`: compute total_requirements, covered_requirements (links >= 0.5), orphan_requirements_count, coverage_percentage (covered/total * 100, 2 decimal places, 0.00 if total is 0), total_test_cases, linked_test_cases, orphan_test_cases_count, average_link_confidence (mean of all confidences, 2 decimal places, 0.00 if no links)
    - Implement `compute_compliance_readiness_score(metrics, source_docs_with_extractions, target_docs_with_extractions, total_docs)`: apply formula (coverage_percentage * 0.40) + (link_quality_score * 0.25) + (orphan_penalty * 0.20) + (completeness_score * 0.15), clamp to [0.0, 100.0]
    - Implement `persist_coverage_snapshot(matrix_id, metrics, source_document_uuid, company_id)`: create immutable CoverageSnapshot record, validate ranges before persist (reject if outside 0-100)
    - Implement `get_coverage_summary(company_id)`: aggregate across all non-deleted matrices for company
    - Implement `get_coverage_history(company_id, filters)`: return paginated CoverageSnapshots sorted by snapshot_date descending
    - Implement `get_document_coverage(document_uuid, company_id)`: return latest coverage for document as source
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 5.4, 10.8_

  - [ ]* 5.2 Write property test for coverage metrics computation
    - **Property 11: Coverage Metrics Computation** — Generate random requirement/link sets, verify coverage_percentage = covered/total * 100 (2 decimal places), average_link_confidence = mean of all confidences (2 decimal places), handle zero-total edge case
    - **Validates: Requirements 7.1**

  - [ ]* 5.3 Write property test for compliance readiness score formula
    - **Property 12: Compliance Readiness Score Formula** — Generate random metric inputs (coverage %, confidence, orphan counts, completeness), verify formula produces correct clamped result matching (coverage_percentage × 0.40) + (avg_confidence × 100 × 0.25) + (max(0, 100 − orphans_req × 5 − orphans_tc × 3) × 0.20) + (completeness × 0.15)
    - **Validates: Requirements 7.2**

  - [ ]* 5.4 Write unit tests for CoverageMetricsService
    - Test metric computation, compliance score formula, snapshot persistence, range validation
    - Test coverage summary aggregation, history pagination, document coverage lookup
    - Test edge cases: zero requirements, zero links, all orphans
    - _Requirements: 7.1–7.7, 5.4, 10.8_

- [ ] 6. Traceability Alert Service (event listener + stale link marking)
  - [~] 6.1 Implement TraceabilityAlertService
    - Create file `src/backend/src/alcoabase/services/traceability_alert.py`
    - Implement `create_alert(triggering_report_id, triggering_document_uuid, company_id)`: query non-deleted matrices where source_document_uuids contains triggering_document_uuid, compute affected_link_count, determine alert_severity from impact report's highest finding severity, persist TraceabilityAlert with unique constraint handling
    - Implement `mark_stale_links(alert, affected_matrices, triggering_document_uuid)`: for critical alerts, create StaleLinkMarker for each link originating from the changed document in affected matrices
    - Implement `resolve_alert(alert_id, user_id, resolution_action, resolution_note, company_id)`: mark alert as resolved, handle already-resolved (409), handle not-found (404)
    - Implement `clear_stale_markers(alert)`: when resolution_action is "links_verified" or "matrix_regenerated", set is_cleared=true and cleared_at on corresponding StaleLinkMarker records; "no_action_needed" does NOT clear markers
    - Implement `get_alerts(company_id, filters)`: return unresolved alerts sorted by severity then created_at, paginated
    - Handle database write failure on alert creation: log failure, do not propagate to impact analysis job
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [~] 6.2 Implement traceability alert event trigger
    - Create file `src/backend/src/alcoabase/services/traceability_alert_trigger.py`
    - Register SQLAlchemy `after_insert` listener on `ImpactReport` model
    - Implement filtering: check if triggering_document_uuid matches any source_document_uuid in existing non-deleted TraceabilityMatrices for the same company
    - Call TraceabilityAlertService.create_alert within 30 seconds of event
    - Handle alert creation failure gracefully: log error, do not fail the impact analysis job
    - _Requirements: 9.1, 9.5, 9.7_

  - [ ]* 6.3 Write property test for stale link lifecycle
    - **Property 13: Stale Link Lifecycle** — Generate critical alerts and resolutions with various actions, verify stale markers created for critical alerts, cleared on "links_verified"/"matrix_regenerated" resolution, NOT cleared on "no_action_needed"
    - **Validates: Requirements 9.4, 9.8**

  - [ ]* 6.4 Write unit tests for TraceabilityAlertService and event trigger
    - Test alert creation on ImpactReport event, severity determination, stale link marking
    - Test alert resolution, stale marker clearing, already-resolved handling (409)
    - Test event listener filtering, graceful failure handling
    - _Requirements: 9.1–9.8_

- [~] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Celery task and job management
  - [~] 8.1 Implement Celery task for matrix generation
    - Create file `src/backend/src/alcoabase/tasks/traceability_tasks.py`
    - Implement `generate_traceability_matrix` task: queue=ai_operations, time_limit=600s, orchestrates full pipeline (validate → extract requirements → extract test cases → three-pass matching → orphan detection → coverage metrics → persist matrix → persist snapshot)
    - Implement monotonic progress updates via JobTracker: 5% validation, 5-30% requirement extraction, 30-60% test case extraction, 60-85% link establishment, 85-90% orphan detection, 90-95% metrics computation, 95-100% persistence
    - Implement job creation with estimated_duration_seconds (30s per document, minimum 60s)
    - Implement 600s hard timeout with partial_success persistence and unprocessed_requirements metadata
    - Handle unrecoverable errors: set job status "failed", populate error_message without stack traces, freeze progress_percent at last reported value
    - _Requirements: 11.1, 11.2, 11.4, 11.5, 11.8, 11.9, 11.10_

  - [ ]* 8.2 Write property test for monotonic progress
    - **Property 14: Monotonic Progress** — Generate random progress update sequences during matrix generation, verify each progress_percent value is >= previously reported value
    - **Validates: Requirements 11.2**

  - [ ]* 8.3 Write unit tests for Celery task and job management
    - Test task execution with mocked services, progress updates, timeout handling
    - Test job creation with estimated duration, conflict detection (409)
    - Test partial_success persistence on timeout, failed status on unrecoverable error
    - Test error_message sanitization (no stack traces)
    - Mock InferenceClient, KnowledgeService, CrossReferenceService, JobTracker
    - _Requirements: 11.1–11.10_

- [ ] 9. Agent archetype and fallback logic
  - [~] 9.1 Create Traceability Analyst agent archetype YAML
    - Create file `agents/archetypes/traceability-analyst.yaml`
    - Define schema_version "2.0", agent_type "review", temperature 0.15, max_tokens 4096
    - Define evaluation rubric with weighted_average scoring, criteria weights (requirement extraction 0.25, test case identification 0.25, link establishment 0.30, orphan detection 0.20)
    - Define severity_thresholds (critical: 0.9, major: 0.7, minor: 0.4, informational: 0.2)
    - Define system prompt with requirement extraction rules, test case extraction rules, link establishment rules, orphan classification rules (keyword precedence), structured JSON output instructions
    - Define dspy_modules with ChainOfThought modules for requirement_extraction, test_case_extraction, and link_establishment
    - Define knowledge_scopes with tags: Traceability, Requirements Management, Test Coverage, Validation, Regulatory Compliance, URS, IQ, OQ, PQ
    - Define target_document_tag, required_chapters, compliance_checklist, severity_rules as mandated by agent-definition-v2.json schema
    - _Requirements: 6.1, 6.2, 6.3_

  - [~] 9.2 Implement agent loading and fallback logic in TraceabilityMatrixService
    - Add agent resolution to TraceabilityMatrixService: load "Traceability Analyst" from Agent Registry
    - Implement fallback: if archetype not found, use "Change Impact Analyst" with appended system prompt suffix for traceability focus, record fallback in job metadata under "fallback_used" field
    - Pass agent's temperature (0.15) and max_tokens (4096) to InferenceClient calls
    - Handle YAML schema validation failure against agent-definition-v2.json: reject file, log validation error identifying failing field, retain previous valid configuration
    - Handle InferenceClient timeout (120s): abort pending request, record timeout event in job metadata, return error indicating which analysis step timed out
    - _Requirements: 6.4, 6.5, 6.6, 6.7_

  - [ ]* 9.3 Write property test for agent fallback behavior
    - **Property 10: Agent Fallback Behavior** — Remove Traceability Analyst from registry, execute with random inputs, verify Change Impact Analyst used as fallback with prompt suffix, verify "fallback_used" recorded in matrix metadata
    - **Validates: Requirements 6.5**

  - [ ]* 9.4 Write unit tests for agent loading and fallback
    - Test successful agent loading from registry, missing agent fallback, schema validation failure
    - Test InferenceClient timeout handling (120s), retry behavior (3 retries with exponential backoff)
    - _Requirements: 6.1–6.7_

- [ ] 10. API router and endpoint wiring
  - [~] 10.1 Implement traceability API router
    - Create file `src/backend/src/alcoabase/api/traceability.py`
    - Implement POST `/matrices/generate` → 202 + job_id (requires X-Change-Reason), validate request body, check document existence (404), check overlap (422), check limits (422), check concurrent job (409)
    - Implement GET `/matrices` → paginated matrices (limit max 100, offset), filterable by source_document_uuid, target_document_uuid, status, date_range, exclude soft-deleted
    - Implement GET `/matrices/{matrix_id}` → full matrix detail (404 if not found/wrong company, 422 if invalid UUID)
    - Implement GET `/matrices/{matrix_id}/links` → paginated links (limit max 200, offset), filterable by source_document_uuid, target_document_uuid, link_confidence_min (0.0-1.0, 422 if out of range), link_method
    - Implement GET `/matrices/{matrix_id}/orphan-requirements` → paginated orphan requirements (limit max 100, offset), filterable by severity, source_document_uuid
    - Implement GET `/matrices/{matrix_id}/orphan-test-cases` → paginated orphan test cases (limit max 100, offset), filterable by risk_level, target_document_uuid, ordered by risk_level desc then test_case_id asc
    - Implement DELETE `/matrices/{matrix_id}` → soft-delete (204), requires X-Change-Reason, 404 if not found/wrong company/already deleted, 422 if invalid UUID
    - _Requirements: 1.1, 1.4, 1.5, 1.8, 1.9, 2.3, 2.6, 2.7, 3.3, 3.6, 3.7, 5.1, 5.2, 5.3, 5.5, 5.6_

  - [~] 10.2 Implement coverage and alert API endpoints
    - Implement GET `/documents/{document_uuid}/coverage` → document coverage status (422 if invalid UUID, null values if never in matrix as source)
    - Implement GET `/coverage/summary` → aggregated coverage summary across all non-deleted matrices for company (0 values if no matrices)
    - Implement GET `/coverage/history` → paginated coverage snapshots (limit max 100, offset), filterable by source_document_uuid, date_range
    - Implement GET `/alerts` → unresolved alerts sorted by severity then created_at, paginated (limit max 100, offset)
    - Implement POST `/alerts/{alert_id}/resolve` → resolve alert (requires X-Change-Reason), 404 if not found/wrong company, 409 if already resolved
    - Implement GET `/jobs/{job_id}/status` → job status with progress (404 if not found/wrong company)
    - All endpoints scoped by X-Company-Id header via dependency injection
    - _Requirements: 5.4, 5.6, 7.3, 7.4, 7.6, 7.7, 9.2, 9.3, 9.6, 11.3, 11.6, 11.7_

  - [~] 10.3 Register traceability router in central router
    - Add import and include_router in `src/backend/src/alcoabase/api/router.py` with prefix `/traceability`
    - _Requirements: 1.1, 5.6_

  - [ ]* 10.4 Write property test for company isolation
    - **Property 3: Company Isolation** — Generate multi-tenant matrix/snapshot/alert/stale-marker data, query with specific company_id, verify no cross-tenant leakage across all traceability endpoints
    - **Validates: Requirements 1.8, 2.6, 3.6, 4.5, 5.6, 7.6, 7.7, 9.6, 11.6**

  - [ ]* 10.5 Write property test for soft-delete exclusion
    - **Property 9: Soft-Delete Exclusion** — Generate matrices with random deleted_at values (null or timestamp), verify GET /matrices list queries exclude deleted matrices, verify underlying records still exist in database
    - **Validates: Requirements 5.5**

  - [ ]* 10.6 Write integration tests for API endpoints
    - Test all 13 endpoints with database, verify HTTP status codes, pagination, filtering
    - Test X-Change-Reason enforcement on mutation endpoints (POST generate, DELETE matrix, POST resolve)
    - Test error responses (404, 409, 422, 503)
    - Test soft-delete behavior, concurrent job detection, document validation
    - _Requirements: 1.1–1.12, 2.3–2.7, 3.3–3.7, 4.5, 5.1–5.6, 7.3–7.7, 9.2–9.6, 11.3–11.10_

- [~] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Frontend: Types, store, and API client integration
  - [~] 12.1 Create TypeScript types for traceability
    - Create file `src/frontend/src/types/traceability.ts`
    - Define interfaces: `TraceabilityMatrix`, `TraceabilityLink`, `OrphanRequirement`, `OrphanTestCase`, `CoverageMetric`, `CoverageSummary`, `CoverageSnapshot`, `DocumentCoverage`, `TraceabilityAlert`, `StaleLinkMarker`, `JobStatus`
    - Define filter/pagination types: `MatrixFilters`, `LinkFilters`, `OrphanFilters`, `AlertFilters`, `HistoryFilters`
    - Define request types: `GenerateMatrixRequest`, `ResolveAlertRequest`
    - Define API response types with total_count for paginated responses
    - _Requirements: 8.1, 8.9_

  - [~] 12.2 Create Zustand store for traceability
    - Create file `src/frontend/src/stores/traceabilityStore.ts`
    - Implement state: matrices, currentMatrix, links, orphanRequirements, orphanTestCases, coverageSummary, coverageHistory, alerts, activeJob, isLoading, error
    - Implement actions: fetchMatrices, fetchMatrix, fetchLinks, fetchOrphanRequirements, fetchOrphanTestCases, generateMatrix (with X-Change-Reason), deleteMatrix (with X-Change-Reason), fetchCoverageSummary, fetchCoverageHistory, fetchAlerts, resolveAlert (with X-Change-Reason), pollJobStatus (5s interval, max 10 minutes), fetchDocumentCoverage
    - Handle 409 response on generate: display message, poll existing job_id
    - Handle polling timeout (10 minutes): stop polling, display error, provide retry
    - Use apiClient with X-Change-Reason header on mutations
    - _Requirements: 8.6, 8.7, 8.9, 8.12_

  - [ ]* 12.3 Write unit tests for traceabilityStore
    - Test state transitions, action sequences, error handling, polling logic
    - Test 409 handling on generate, polling timeout behavior
    - Use fast-check for property-based testing of state invariants
    - _Requirements: 8.9_

- [ ] 13. Frontend: Page and components
  - [~] 13.1 Implement TraceabilityPage
    - Create file `src/frontend/src/pages/TraceabilityPage.tsx`
    - Display summary card: overall coverage percentage (0-100%, 1 decimal place), compliance readiness score (0-100), total orphan requirements count, total orphan test cases count
    - Display paginated matrix list (20 per page, newest first) with status badges
    - Display "Generate Matrix" button
    - Display coverage trend chart component
    - Implement loading skeletons and empty states with descriptive messages and call-to-action
    - Implement inline error messages with "Retry" button on API failures
    - Fetch data from GET /api/traceability/matrices and GET /api/traceability/coverage/summary
    - _Requirements: 8.1, 8.10, 8.11_

  - [~] 13.2 Implement MatrixDetailView component
    - Create file `src/frontend/src/components/traceability/MatrixDetailView.tsx`
    - Display tabular view of TraceabilityLinks with columns: requirement_id, requirement_text (truncated 100 chars with tooltip), target_document, test_case_id, test_case_text (truncated 100 chars with tooltip), link_confidence (percentage badge: green >= 0.8, yellow >= 0.5, red < 0.5), link_method, is_stale indicator
    - Support sorting by any column and filtering by link_confidence_min
    - Fetch data from GET /api/traceability/matrices/{matrix_id}/links
    - _Requirements: 8.2_

  - [~] 13.3 Implement CoverageHeatmap component
    - Create file `src/frontend/src/components/traceability/CoverageHeatmap.tsx`
    - Render grid: rows = source documents, columns = target documents, cells = coverage percentage
    - Color intensity: dark green (100%) → yellow (50%) → red (0%)
    - Tooltip on hover: exact coverage percentage and orphan count for document pair
    - _Requirements: 8.3_

  - [~] 13.4 Implement OrphanAlertsPanel component
    - Create file `src/frontend/src/components/traceability/OrphanAlertsPanel.tsx`
    - Two tabs: "Orphan Requirements" and "Orphan Test Cases"
    - Orphan Requirements: severity badges (red=critical, orange=major, yellow=minor), suggested_action chips
    - Orphan Test Cases: risk_level badges (red=high, orange=medium, green=low), suggested_action chips
    - Fetch from GET /api/traceability/matrices/{matrix_id}/orphan-requirements and orphan-test-cases
    - _Requirements: 8.4_

  - [~] 13.5 Implement GenerateMatrixDialog component
    - Create file `src/frontend/src/components/traceability/GenerateMatrixDialog.tsx`
    - Multi-select document picker for source documents (filtered to URS/specification types, max 50 selections)
    - Multi-select document picker for target documents (filtered to IQ/OQ/PQ/MVP types, max 50 selections)
    - matrix_name text input (required, 1-150 chars)
    - Optional description textarea (max 500 chars)
    - Submit calls POST /api/traceability/matrices/generate with X-Change-Reason
    - Submit button disabled until at least one source, one target, and valid matrix_name provided
    - On 202: poll job status every 5s, show progress indicator (current_phase, progress_percent), auto-navigate to matrix detail on completion
    - On 409: display "generation in progress" message, poll existing job_id
    - On failure/timeout (10 min): stop polling, show error, provide "Retry" with preserved values
    - _Requirements: 8.5, 8.6, 8.7, 8.12_

  - [~] 13.6 Implement CoverageTrendChart component
    - Create file `src/frontend/src/components/traceability/CoverageTrendChart.tsx`
    - Line chart of coverage_percentage over time
    - Secondary axis for compliance_readiness_score
    - Filter by source_document_uuid
    - Fetch from GET /api/traceability/coverage/history
    - _Requirements: 8.8_

  - [~] 13.7 Implement TraceabilityAlertBanner component
    - Create file `src/frontend/src/components/traceability/TraceabilityAlertBanner.tsx`
    - Display banner showing unresolved critical/major alerts count
    - Link to alerts list, show severity badges
    - Fetch from GET /api/traceability/alerts
    - _Requirements: 9.2_

  - [~] 13.8 Add route and navigation for traceability page
    - Add `/traceability` route in router configuration
    - Add `/traceability/matrices/{matrix_id}` route for matrix detail view
    - Add navigation link in main sidebar/nav
    - Wire MatrixDetailView with OrphanAlertsPanel and TraceabilityAlertBanner
    - _Requirements: 8.1, 8.2_

  - [ ]* 13.9 Write frontend component tests
    - Test TraceabilityPage rendering, data fetching, empty states, loading skeletons, error handling
    - Test MatrixDetailView rendering, sorting, filtering, stale indicators
    - Test CoverageHeatmap rendering, color coding, tooltip display
    - Test OrphanAlertsPanel tab switching, severity badges, suggested action chips
    - Test GenerateMatrixDialog form validation, submit disabled state, polling behavior
    - Test CoverageTrendChart rendering, filtering, dual axis
    - Test TraceabilityAlertBanner rendering, alert count display
    - _Requirements: 8.1–8.12_

- [~] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + fast-check
- All backend services mock InferenceClient via `respx` and KnowledgeService/CrossReferenceService in unit/property tests
- Celery tasks are tested synchronously via `asyncio.run()` pattern (matching existing `review_tasks.py`)
- The TraceabilityAlertService event trigger integrates with the existing ImpactReport model from Phase 5.5
- Immutability enforcement follows the same ORM event listener pattern as ImpactReport in Phase 5.5

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "9.1"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "2.6", "2.7"] },
    { "id": 4, "tasks": ["4.1", "5.1", "6.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "4.5", "5.2", "5.3", "5.4", "6.2"] },
    { "id": 6, "tasks": ["6.3", "6.4", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "9.2"] },
    { "id": 8, "tasks": ["9.3", "9.4"] },
    { "id": 9, "tasks": ["10.1", "10.2", "10.3"] },
    { "id": 10, "tasks": ["10.4", "10.5", "10.6"] },
    { "id": 11, "tasks": ["12.1"] },
    { "id": 12, "tasks": ["12.2", "12.3"] },
    { "id": 13, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6", "13.7"] },
    { "id": 14, "tasks": ["13.8", "13.9"] }
  ]
}
```
