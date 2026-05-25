# Implementation Plan: AI-Driven Change Impact Analysis

## Overview

This plan implements Phase 5.5 — AI-Driven Change Impact Analysis for AlcoaBase. The implementation follows a bottom-up approach: database models and schemas first, then services, Celery tasks, API routes, event triggers, and finally the frontend dashboard. Each task builds incrementally on previous work, ensuring no orphaned code.

## Tasks

- [ ] 1. Database models, schemas, and migration
  - [~] 1.1 Create SQLAlchemy models for impact analysis
    - Create file `src/backend/src/alcoabase/models/impact_analysis.py`
    - Define `DependencyEdge` model with AuditMixin, unique constraint on (source_document_uuid, target_document_uuid, dependency_type, company_id), composite indexes on (company_id, source_document_uuid) and (company_id, target_document_uuid)
    - Define `ImpactReport` model with immutability event listeners (before_update, before_delete raising ImmutableRecordError), composite index on (company_id, triggering_document_uuid)
    - Define `GapAnalysisResult` model with immutability event listeners, indexed job_id
    - Define `ImpactNotification` model with AuditMixin, unique constraint on (report_id, affected_document_uuid, target_user_id), composite index on (target_user_id, is_acknowledged)
    - Register immutability listeners using the same pattern as `GenerationProvenance`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [~] 1.2 Create Pydantic schemas for impact analysis
    - Create file `src/backend/src/alcoabase/schemas/impact_analysis.py`
    - Define `AffectedItemSchema`, `GapFindingSchema`, `ChangeDeltaSchema` with field constraints (max_length, Literal types)
    - Define request schemas: `BuildGraphRequest`, `TriggerAnalysisRequest`, `GapAnalysisRequest`
    - Define response schemas: `DependencyEdgeResponse`, `ImpactReportResponse`, `ImpactReportListResponse`, `GapAnalysisResultResponse`, `JobStatusResponse`, `NotificationResponse`, `DocumentImpactStatusResponse`
    - Define filter/pagination schemas: `ReportFilters`, `GraphFilters`, `PaginationParams`
    - _Requirements: 1.5, 1.8, 3.5, 4.3, 5.1, 5.3, 5.4, 6.3, 6.4, 8.2, 8.5_

  - [~] 1.3 Create Alembic migration for impact analysis tables
    - Generate migration with `alembic revision --autogenerate -m "add_impact_analysis_tables"`
    - Verify upgrade creates all tables, indexes, and constraints
    - Verify downgrade drops tables in reverse dependency order: ImpactNotification, GapAnalysisResult, ImpactReport, DependencyEdge
    - _Requirements: 9.7_

  - [~] 1.4 Write property tests for model immutability and constraints
    - **Property 11: Immutability Enforcement** — Verify ImpactReport and GapAnalysisResult reject UPDATE/DELETE via ORM
    - **Validates: Requirements 5.2, 9.2, 9.4**

  - [~] 1.5 Write unit tests for Pydantic schema validation
    - Test field constraints (max_length, Literal enums), required vs optional fields
    - Test AffectedItemSchema, GapFindingSchema, ChangeDeltaSchema serialization/deserialization
    - _Requirements: 3.5, 4.3, 5.1_

- [ ] 2. Dependency Graph Service
  - [~] 2.1 Implement DependencyGraphService core logic
    - Create file `src/backend/src/alcoabase/services/dependency_graph.py`
    - Implement `build_full_graph(company_id)`: scan all documents, extract cross-references via CrossReferenceService, compute semantic similarity via KnowledgeService, create/update edges
    - Implement `build_incremental_graph(company_id)`: scan only documents modified since last successful build, prune stale edges whose detected_references are no longer present
    - Implement confidence score assignment: 1.0 for explicit cross-refs, 0.9 for DB-linked (TrainingTask, GenerationProvenance), 0.5-0.8 for semantic (based on embedding similarity), reject below 0.5
    - Implement dependency type classification: validates, references, implements, trains_on, derived_from
    - Implement edge deduplication: upsert on unique constraint, update confidence_score/detected_references/last_verified_at
    - Implement 300s timeout with partial_success handling
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.10, 1.12, 1.13, 1.14_

  - [~] 2.2 Implement DependencyGraphService query methods
    - Implement `get_edges(company_id, filters, pagination)`: list edges with filtering by source/target/type, pagination with limit (max 200) and offset
    - Implement `get_document_dependencies(company_id, document_uuid)`: return upstream + downstream edges grouped by dependency_type, return empty groups (not 404) if no edges exist
    - Implement document existence validation (return 404 if document not in company scope)
    - _Requirements: 1.8, 1.9, 1.11, 1.15_

  - [~] 2.3 Write property tests for confidence score assignment
    - **Property 1: Confidence Score Assignment** — Generate detection results with various methods, verify score ranges and 0.5 threshold
    - **Validates: Requirements 1.6**

  - [~] 2.4 Write property tests for dependency type classification
    - **Property 2: Dependency Type Classification** — Generate reference patterns, verify correct type mapping
    - **Validates: Requirements 1.4**

  - [~] 2.5 Write property tests for edge deduplication and pruning
    - **Property 4: Edge Deduplication and Pruning** — Generate duplicate edges, verify single edge with latest values; remove refs, verify pruning
    - **Validates: Requirements 1.13, 1.14**

  - [~] 2.6 Write unit tests for DependencyGraphService
    - Test full build, incremental build, timeout handling, skip-on-error behavior
    - Test edge CRUD, filtering, pagination, deduplication
    - Mock CrossReferenceService and KnowledgeService
    - _Requirements: 1.1–1.15_

- [~] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Impact Analysis Service
  - [~] 4.1 Implement Change Delta computation
    - Create file `src/backend/src/alcoabase/services/impact_analysis.py`
    - Implement `compute_change_delta(document_uuid, new_version_id, previous_version_id, company_id)`: extract text from both versions via KnowledgeService, perform section-level diff, classify changes by significance (high/medium/low) using Change_Impact_Analyst agent
    - Handle first-version case: treat entire content as "new"
    - Return `ChangeDeltaSchema` with sections_added, sections_modified, sections_deleted, significance_levels
    - _Requirements: 2.6, 2.8_

  - [~] 4.2 Implement affected item assessment logic
    - Implement `assess_affected_items(change_delta, downstream_edges, company_id)`: for each candidate, retrieve dependent doc sections via KnowledgeService, use Change_Impact_Analyst agent to assess impact
    - Implement candidate prioritization: limit to 50, sort by confidence_score desc then dependency_type priority (validates > implements > references > trains_on > derived_from)
    - Implement severity assignment: critical (contradicts), major (missing), minor (outdated terminology)
    - Implement per-item error handling: mark as severity "unknown" / action "manual_review_required" on InferenceClient or KnowledgeService failure
    - Implement training task identification: query TrainingTask records, flag incomplete tasks for review, flag completed tasks if procedural/safety changes detected
    - Produce list of `AffectedItemSchema` with inference_prompt_summary, model_response_summary, token_count
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [~] 4.3 Implement Impact Report generation and persistence
    - Implement `create_impact_report(...)`: assemble ImpactReport with all required fields (report_id UUID, change_delta_summary, affected_items, gap_findings, status, timestamps, token counts, requesting_user_id)
    - Handle requesting_user_id attribution: use uploaded_by from DocumentVersion, set null + metadata flag if unavailable
    - Handle database write failure: mark job as failed via JobTracker
    - Ensure report is created for all terminal states (completed, partial_success, failed)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 5.8_

  - [~] 4.4 Write property tests for candidate prioritization
    - **Property 8: Candidate Prioritization** — Generate >50 candidates with random scores/types, verify top-50 selection order
    - **Validates: Requirements 3.6**

  - [~] 4.5 Write property tests for change delta correctness
    - **Property 7: Change Delta Correctness** — Generate document section pairs, verify correct partitioning into added/modified/deleted
    - **Validates: Requirements 2.6**

  - [~] 4.6 Write property tests for document filtering (auto-trigger)
    - **Property 5: Document Filtering for Auto-Trigger** — Generate documents with random statuses, verify Draft/CSV exclusion
    - **Validates: Requirements 2.3**

  - [~] 4.7 Write unit tests for ImpactAnalysisService
    - Test change delta computation, affected item assessment, report generation
    - Test prioritization logic, severity assignment, error handling paths
    - Mock InferenceClient, KnowledgeService, JobTracker
    - _Requirements: 2.6, 2.8, 3.1–3.9, 5.1–5.8_

- [ ] 5. Gap Analysis Service
  - [~] 5.1 Implement GapAnalysisService
    - Create file `src/backend/src/alcoabase/services/gap_analysis.py`
    - Implement `execute_gap_analysis(source_doc_id, target_doc_id, source_version_id, target_version_id, company_id)`: extract text/sections from both docs, identify requirements/steps/assertions in source, search target for coverage, produce GapFindings
    - Implement dependency validation: reject with 422 if no edge exists with confidence_score >= 0.5
    - Implement same-document validation: reject with 422 if source == target
    - Implement document existence validation: return 404 if either doc not found in company scope
    - Use Change_Impact_Analyst agent for semantic comparison with dependency_type-aware instructions
    - Implement 180s timeout with partial_success handling
    - Implement gap finding limiting: retain top 100 by severity (critical > major > minor), record total count in metadata
    - Persist results as GapAnalysisResult record
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12_

  - [~] 5.2 Write property tests for gap findings retention
    - **Property 9: Gap Findings Retention** — Generate >100 findings with random severities, verify top-100 retention by severity
    - **Validates: Requirements 4.10**

  - [~] 5.3 Write property tests for dependency validation threshold
    - **Property 10: Dependency Validation Threshold** — Generate document pairs with/without edges, verify 422 vs accept
    - **Validates: Requirements 4.6**

  - [~] 5.4 Write unit tests for GapAnalysisService
    - Test gap finding production, limiting, timeout handling, validation errors
    - Mock InferenceClient and KnowledgeService
    - _Requirements: 4.1–4.12_

- [ ] 6. Notification Service
  - [~] 6.1 Implement ImpactNotificationService
    - Create file `src/backend/src/alcoabase/services/impact_notification.py`
    - Implement `create_notifications(report_id, affected_items, company_id)`: create notifications only for critical/major severity items, target document owner (Document.created_by), deduplicate against existing unacknowledged notifications
    - Implement `acknowledge_notification(notification_id, user_id, company_id)`: mark as acknowledged (idempotent), return 404 if not found/wrong company
    - Implement `get_unacknowledged(user_id, company_id, pagination)`: sorted by severity (critical first) then created_at (newest first)
    - Implement `reset_training_tasks(affected_items, report_id)`: set is_completed=false for affected TrainingTasks with recommended_action "retraining_required" (idempotent), record failures in report metadata
    - Implement `get_document_status(document_uuid, company_id)`: compute is_up_to_date, outstanding counts from unacknowledged notifications
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [~] 6.2 Write property tests for notification creation rules
    - **Property 13: Notification Creation Rules** — Generate items with random severities, verify only critical/major create notifications
    - **Validates: Requirements 8.1**

  - [~] 6.3 Write property tests for notification idempotence
    - **Property 14: Notification Idempotence** — Generate duplicate acknowledge/create attempts, verify no duplicates
    - **Validates: Requirements 8.3, 8.8**

  - [~] 6.4 Write property tests for training task reset idempotence
    - **Property 15: Training Task Reset Idempotence** — Generate tasks in various states, verify idempotent reset
    - **Validates: Requirements 8.4**

  - [~] 6.5 Write property tests for document impact status computation
    - **Property 16: Document Impact Status Computation** — Generate documents with various finding states, verify is_up_to_date logic
    - **Validates: Requirements 8.5**

  - [~] 6.6 Write unit tests for ImpactNotificationService
    - Test notification creation, deduplication, acknowledgment, training reset, document status
    - _Requirements: 8.1–8.8_

- [~] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Celery tasks and event trigger
  - [~] 8.1 Implement Celery tasks for impact analysis
    - Create file `src/backend/src/alcoabase/tasks/impact_analysis_tasks.py`
    - Implement `build_dependency_graph` task: queue=ai_operations, time_limit=300s, calls DependencyGraphService, updates JobTracker progress
    - Implement `analyze_change_impact` task: queue=ai_operations, time_limit=600s, orchestrates full pipeline (delta → dependencies → assessment → notifications → report), updates JobTracker progress monotonically (10% delta, 20% deps, 20-85% items, 85-95% gaps, 100% report)
    - Implement `execute_gap_analysis` task: queue=ai_operations, time_limit=180s, calls GapAnalysisService, updates JobTracker progress
    - Implement 600s hard timeout with partial_success persistence and unassessed_items metadata
    - Implement job creation with estimated_duration_seconds (15s per dependency, minimum 30s)
    - _Requirements: 6.1, 6.2, 6.4, 6.5_

  - [~] 8.2 Implement impact analysis event trigger
    - Create file `src/backend/src/alcoabase/services/impact_analysis_trigger.py`
    - Register SQLAlchemy `after_insert` listener on DocumentVersion model
    - Implement filtering: skip if document status is "Draft" or is_csv_validation_record is true
    - Implement conflict detection: check for existing "processing" job for same document_uuid, return 409 if active (last update < 600s), allow if stale
    - Handle Celery broker unavailability: log failure, document remains eligible for manual trigger
    - Enqueue within 5 seconds of version creation event
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 2.9_

  - [~] 8.3 Write property tests for conflict detection with staleness
    - **Property 6: Conflict Detection with Staleness** — Generate jobs with random timestamps, verify 409 vs 202 behavior
    - **Validates: Requirements 2.5**

  - [~] 8.4 Write property tests for monotonic progress
    - **Property 12: Monotonic Progress** — Generate random progress sequences, verify non-decreasing
    - **Validates: Requirements 6.2**

  - [~] 8.5 Write property tests for error message sanitization
    - **Property 17: Error Message Sanitization** — Generate random exceptions, verify no stack traces in error_message
    - **Validates: Requirements 6.9**

  - [~] 8.6 Write unit tests for Celery tasks and event trigger
    - Test task execution with mocked services, progress updates, timeout handling
    - Test event listener filtering, conflict detection, broker failure handling
    - _Requirements: 2.1–2.9, 6.1–6.9_

- [ ] 9. Agent archetype and fallback logic
  - [~] 9.1 Create Change Impact Analyst agent archetype YAML
    - Create file `agents/archetypes/change-impact-analyst.yaml`
    - Define schema_version "2.0", agent_type "review", temperature 0.2, max_tokens 4096
    - Define evaluation rubric with weighted_average scoring, criteria weights (accuracy 0.30, completeness 0.30, severity 0.25, regulatory 0.15)
    - Define severity_thresholds (critical: 0.9, major: 0.7, minor: 0.4, informational: 0.2)
    - Define system prompt with classification rules, dependency-type-aware strictness, structured JSON output instructions
    - Define dspy_modules with ChainOfThought modules for impact_assessment and gap_identification
    - Define knowledge_scopes with relevant tags
    - _Requirements: 7.1, 7.2, 7.3_

  - [~] 9.2 Implement agent loading and fallback logic in services
    - Add agent resolution to ImpactAnalysisService and GapAnalysisService: load "Change Impact Analyst" from Agent Registry
    - Implement fallback: if archetype not found, use "Regulatory Compliance Auditor" with appended system prompt suffix, record fallback in job metadata under "fallback_used"
    - Pass agent's temperature (0.2) and max_tokens (4096) to InferenceClient calls
    - Handle YAML schema validation failure: reject file, log error, retain previous config
    - _Requirements: 7.4, 7.5, 7.6_

  - [~] 9.3 Write property tests for agent fallback behavior
    - **Property 18: Agent Fallback Behavior** — Remove agent from registry, verify fallback used and recorded in metadata
    - **Validates: Requirements 7.5**

  - [~] 9.4 Write unit tests for agent loading and fallback
    - Test successful agent loading, missing agent fallback, schema validation failure
    - _Requirements: 7.1–7.6_

- [ ] 10. API router and endpoint wiring
  - [~] 10.1 Implement impact analysis API router
    - Create file `src/backend/src/alcoabase/api/impact_analysis.py`
    - Implement POST `/dependency-graph/build` → 202 + job_id (requires X-Change-Reason)
    - Implement GET `/dependency-graph` → paginated edges (limit max 200, offset)
    - Implement GET `/dependency-graph/{document_uuid}` → grouped dependencies (empty groups if no edges, 404 if doc not in company)
    - Implement POST `/trigger` → 202 + job_id, 409 if concurrent (requires X-Change-Reason)
    - Implement POST `/gap-analysis` → 202 + job_id (requires X-Change-Reason), 422 if no dependency/same doc, 404 if doc not found
    - Implement GET `/gap-analysis/{job_id}/results` → findings with pagination, 202 if processing, 200 with empty + reason if failed
    - Implement GET `/reports` → paginated reports with filters (document_uuid, severity, date_range, status), total_count
    - Implement GET `/reports/{report_id}` → full report, 404 if not found/wrong company, 422 if invalid UUID
    - Implement GET `/jobs/{job_id}/status` → job status with progress, 404 if not found/wrong company
    - Implement GET `/notifications` → unacknowledged notifications for current user, paginated
    - Implement POST `/notifications/{notification_id}/acknowledge` → 200 (idempotent), 404 if not found (requires X-Change-Reason)
    - Implement GET `/documents/{document_uuid}/status` → document impact status
    - All endpoints scoped by X-Company-Id header via dependency injection
    - _Requirements: 1.1, 1.8, 1.9, 1.11, 1.15, 2.4, 2.5, 2.7, 3.7, 4.1, 4.5, 4.6, 4.8, 4.11, 5.3, 5.4, 5.6, 6.3, 6.6, 6.7, 6.8, 6.9, 8.2, 8.3, 8.5, 8.6_

  - [~] 10.2 Register impact analysis router in central router
    - Add import and include_router in `src/backend/src/alcoabase/api/router.py` with prefix `/impact-analysis`
    - _Requirements: 1.1, 1.8_

  - [~] 10.3 Write property tests for company isolation
    - **Property 3: Company Isolation** — Generate multi-tenant data, verify no cross-tenant leakage across all endpoints
    - **Validates: Requirements 1.11, 2.7, 3.7, 4.8, 5.6, 6.6, 8.6**

  - [~] 10.4 Write integration tests for API endpoints
    - Test all 12 endpoints with database, verify HTTP status codes, pagination, filtering
    - Test X-Change-Reason enforcement on mutation endpoints
    - Test error responses (404, 409, 422, 503)
    - _Requirements: 1.1–1.15, 2.4–2.5, 4.1–4.11, 5.3–5.4, 6.3–6.9, 8.2–8.3, 8.5_

- [~] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Frontend: Types, store, and API client integration
  - [~] 12.1 Create TypeScript types for impact analysis
    - Create file `src/frontend/src/types/impactAnalysis.ts`
    - Define interfaces: `DependencyEdge`, `ImpactReport`, `AffectedItem`, `GapFinding`, `ChangeDelta`, `ImpactNotification`, `JobStatus`, `DocumentImpactStatus`
    - Define filter/pagination types: `ReportFilters`, `GraphFilters`, `PaginationParams`
    - Define API response types with total_count for paginated responses
    - _Requirements: 10.1, 10.2, 10.7_

  - [~] 12.2 Create Zustand store for impact analysis
    - Create file `src/frontend/src/stores/impactAnalysisStore.ts`
    - Implement state: reports, notifications, dependencyGraph, activeJob, documentStatus, isLoading, error
    - Implement actions: fetchReports, fetchNotifications, fetchDependencyGraph, triggerAnalysis, acknowledgeNotification, pollJobStatus (5s interval), fetchDocumentStatus
    - Use apiClient with X-Change-Reason header on mutations (acknowledge, trigger)
    - Handle 409 response on trigger: display message, poll existing job_id
    - _Requirements: 10.1, 10.6, 10.7, 10.10_

  - [~] 12.3 Write unit tests for impactAnalysisStore
    - Test state transitions, action sequences, error handling, polling logic
    - Use fast-check for property-based testing of state invariants
    - _Requirements: 10.7_

- [ ] 13. Frontend: Page and components
  - [~] 13.1 Implement ImpactAnalysisPage
    - Create file `src/frontend/src/pages/ImpactAnalysisPage.tsx`
    - Display summary card (total unresolved critical/major findings)
    - Display paginated report list (20 per page, newest first)
    - Display notification badge with unacknowledged count
    - Implement loading skeletons and empty states with descriptive messages
    - Implement inline error messages with "Retry" button on API failures
    - _Requirements: 10.1, 10.8, 10.9_

  - [~] 13.2 Implement DependencyGraphView component
    - Create file `src/frontend/src/components/impact/DependencyGraphView.tsx`
    - Render documents as nodes, dependencies as directed edges
    - Color-code by severity: red (critical), orange (major), yellow (minor), green (no findings)
    - Support filtering by dependency_type, zooming/panning
    - Limit to 200 nodes max, show truncation message if exceeded
    - _Requirements: 10.2, 10.3_

  - [~] 13.3 Implement GapAnalysisDetail component
    - Create file `src/frontend/src/components/impact/GapAnalysisDetail.tsx`
    - Display side-by-side comparison: source section (left), target section (right)
    - Highlight misalignments, show AI remediation suggestion below each finding
    - _Requirements: 10.4_

  - [~] 13.4 Implement NotificationPanel component
    - Create file `src/frontend/src/components/impact/NotificationPanel.tsx`
    - List unacknowledged notifications: affected document title, severity badge, change summary
    - Implement "Acknowledge" button calling POST with X-Change-Reason header
    - _Requirements: 10.5_

  - [~] 13.5 Implement TriggerAnalysisButton and DocumentImpactStatus components
    - Create file `src/frontend/src/components/impact/TriggerAnalysisButton.tsx`
    - Implement trigger button calling POST /api/impact-analysis/trigger with X-Change-Reason
    - On 202: poll job status every 5s, show progress indicator (current_phase, progress_percent)
    - On 409: display "analysis in progress" message, poll existing job_id
    - Auto-refresh results on completion/partial_success
    - Create file `src/frontend/src/components/impact/DocumentImpactStatus.tsx`
    - Display inline widget: last_analysis_date, outstanding counts, is_up_to_date badge
    - _Requirements: 10.6, 10.10_

  - [~] 13.6 Implement ImpactReportCard component
    - Create file `src/frontend/src/components/impact/ImpactReportCard.tsx`
    - Display summary card for a single report: status, severity counts, timestamp, triggering document
    - _Requirements: 10.1_

  - [~] 13.7 Add route and navigation for impact analysis page
    - Add `/impact-analysis` route in router configuration
    - Add navigation link in main sidebar/nav
    - Integrate DocumentImpactStatus widget into existing document detail page
    - _Requirements: 10.1, 10.2_

  - [~] 13.8 Write frontend component tests
    - Test ImpactAnalysisPage rendering, data fetching, empty states, error handling
    - Test DependencyGraphView rendering, filtering, node limits
    - Test NotificationPanel list, acknowledge action
    - _Requirements: 10.1–10.10_

- [~] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + fast-check
- All backend services mock InferenceClient via `respx` and KnowledgeService in unit/property tests
- Celery tasks are tested synchronously via `asyncio.run()` pattern (matching existing `review_tasks.py`)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "9.1"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "2.6"] },
    { "id": 4, "tasks": ["4.1", "5.1", "6.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "5.2", "5.3", "5.4", "6.2", "6.3", "6.4", "6.5", "6.6"] },
    { "id": 6, "tasks": ["4.4", "4.5", "4.6", "4.7", "9.2"] },
    { "id": 7, "tasks": ["8.1", "8.2", "9.3", "9.4"] },
    { "id": 8, "tasks": ["8.3", "8.4", "8.5", "8.6"] },
    { "id": 9, "tasks": ["10.1", "10.2"] },
    { "id": 10, "tasks": ["10.3", "10.4"] },
    { "id": 11, "tasks": ["12.1"] },
    { "id": 12, "tasks": ["12.2", "12.3"] },
    { "id": 13, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6"] },
    { "id": 14, "tasks": ["13.7", "13.8"] }
  ]
}
```
