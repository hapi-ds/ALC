# Implementation Plan: Multi-Agent "Always-On" Auditing

## Overview

This plan implements the multi-agent review orchestration system in incremental steps. It builds on the existing Agent Registry (5.1), DocumentReviewer, InferenceClient, and Celery infrastructure. Each task builds on previous work, starting with database models and core services, then layering in the pipeline orchestration, compliance features, API endpoints, and finally the frontend dashboard.

## Tasks

- [x] 1. Database models and Pydantic schemas
  - [x] 1.1 Create review pipeline database models
    - Create `src/backend/src/alcoabase/models/review.py`
    - Implement `ReviewSession` model: id, company_id (FK), document_id (FK), document_version_id (FK), audit_profile_id (FK nullable), status (String: Pending/InProgress/Completed/Failed/Approved/Rejected), submitted_by (FK users), submitted_at, completed_at (nullable), compliance_score (nullable Float), summary_failed (Boolean default false), created_at, updated_at
    - Implement `AgentReview` model: id, session_id (FK ReviewSession), agent_definition_id (FK), status (String: Pending/InProgress/Completed/Failed), report_data (JSONB nullable), error_reason (String nullable), inference_duration_ms (Integer nullable), started_at (nullable), completed_at (nullable), created_at
    - Implement `MasterReviewSummary` model: id, session_id (FK ReviewSession, unique), summary_data (JSONB), compliance_score (Float), risk_assessment (String), created_at
    - Implement `ActionItem` model: id, session_id (FK ReviewSession), finding_id (String), title (String 500), description (Text), severity (String), status (String: Open/InProgress/Resolved/Dismissed), assigned_to (FK users nullable), resolved_at (nullable), resolution_note (Text nullable), created_at, updated_at
    - Use AuditMixin on ReviewSession and ActionItem
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.7_

  - [x] 1.2 Create audit profile database model
    - Create `src/backend/src/alcoabase/models/audit_profile.py`
    - Implement `AuditProfile` model: id, company_id (FK), name (String 200), description (Text nullable), regulatory_frameworks (JSON array), assigned_agent_ids (JSON array), quorum (Integer), severity_thresholds (JSON), is_default (Boolean), is_active (Boolean), created_at, updated_at
    - Use AuditMixin for versioning
    - _Requirements: 9.4_

  - [x] 1.3 Create anomaly alert database model
    - Create `src/backend/src/alcoabase/models/anomaly.py`
    - Implement `AnomalyAlert` model: id, company_id (FK), anomaly_type (String 100), severity (String 50), description (Text), affected_document_id (FK nullable), affected_user_id (FK nullable), detected_at, is_resolved (Boolean default false), resolved_at (nullable), resolution_note (Text nullable), created_at
    - Add unique constraint for deduplication: (anomaly_type, affected_document_id, affected_user_id, detected_at date)
    - _Requirements: 9.6, 8.7_

  - [x] 1.4 Create Alembic migration for all new models
    - Generate migration adding review_sessions, agent_reviews, master_review_summaries, action_items, audit_profiles, anomaly_alerts tables
    - Include all foreign keys, indexes, and constraints
    - _Requirements: 9.1–9.7_

  - [x] 1.5 Create Pydantic schemas for review API
    - Create `src/backend/src/alcoabase/schemas/review.py`
    - Implement: ReviewSubmitRequest, ReviewSessionResponse, AgentReviewResponse, MasterSummaryResponse, ActionItemResponse, ActionItemCreateRequest, ActionItemUpdateRequest
    - Implement: AuditProfileRequest, AuditProfileResponse
    - Implement: ComplianceScorecardResponse, MissingLinkResponse
    - Implement: AnomalyAlertResponse, AnomalyResolveRequest
    - All numeric fields with proper ge/le constraints
    - _Requirements: 10.1–10.8_

  - [x] 1.6 Register new models in models/__init__.py
    - Import ReviewSession, AgentReview, MasterReviewSummary, ActionItem, AuditProfile, AnomalyAlert
    - Ensure SQLAlchemy-Continuum picks up versioned models
    - _Requirements: 9.7_

- [x] 2. Audit Profile Service
  - [x] 2.1 Implement AuditProfileService
    - Create `src/backend/src/alcoabase/services/audit_profile_service.py`
    - Implement CRUD: create_profile, get_profile, get_default_profile, list_profiles, update_profile, delete_profile (soft-delete)
    - Implement validate_agent_assignments: verify all agent IDs exist, are active, have agent_type "review", and belong to company or are global+activated
    - Enforce quorum ≤ len(assigned_agent_ids)
    - Enforce single default per company (unset previous default atomically)
    - Define SUPPORTED_FRAMEWORKS constant
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 2.2 Write property test for quorum constraint (Property 6)
    - **Property 6: Audit profile quorum constraint**
    - Generate random agent_ids lists and quorum values; verify quorum > len(agent_ids) is always rejected
    - **Validates: Requirements 4.5**

  - [x] 2.3 Write property test for default profile uniqueness (Property 10)
    - **Property 10: Default audit profile uniqueness**
    - Generate sequences of profile creations with is_default=true; verify at most one default exists at any time
    - **Validates: Requirements 4.2**

- [x] 3. Compliance Score and Core Pipeline Logic
  - [x] 3.1 Implement compliance score computation
    - Create `src/backend/src/alcoabase/services/compliance_scorecard.py`
    - Implement score formula: max(0.0, 100.0 - Σ(weight × count)) with weights Critical=25, Major=10, Minor=3, Informational=0.5
    - Implement risk band classification: Excellent (90–100), Good (75–89), Needs Attention (50–74), At Risk (25–49), Critical (0–24)
    - Implement get_scorecard: average scores of completed sessions in last 90 days
    - Implement get_trend: compare current 30-day average vs previous 30-day average
    - Implement score_by_document_type breakdown
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 3.2 Write property test for compliance score (Property 1)
    - **Property 1: Compliance score is deterministic and bounded**
    - Generate random finding counts per severity; verify score is always in [0.0, 100.0] and matches formula
    - **Validates: Requirements 3.4, 6.1**

  - [x] 3.3 Implement consensus and contradiction detection logic
    - Add to review pipeline service or as utility module
    - Consensus: 2+ reports have findings with same severity for same chapter/section
    - Contradiction: one report has Critical/Major for chapter, another has nothing or Informational
    - _Requirements: 3.5, 3.6_

  - [x] 3.4 Write property test for consensus detection (Property 3)
    - **Property 3: Consensus detection correctness**
    - Generate random sets of agent reports with findings; verify consensus count ≤ total unique (chapter, severity) pairs
    - **Validates: Requirements 3.5, 3.6**

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Review Pipeline Service
  - [x] 5.1 Implement ReviewPipelineService core
    - Create `src/backend/src/alcoabase/services/review_pipeline.py`
    - Implement submit_review: validate document exists, check no active session exists (409), resolve audit profile, create ReviewSession (Pending), create AgentReview records (Pending) for each assigned agent, dispatch Celery tasks
    - Implement get_session, list_sessions (with pagination and filters)
    - Implement approve_session, reject_session (validate status is Completed)
    - Implement action item CRUD methods
    - _Requirements: 1.1, 1.2, 1.3, 1.8, 1.9, 1.10, 10.1–10.8_

  - [x] 5.2 Implement Celery review tasks
    - Create `src/backend/src/alcoabase/tasks/review_tasks.py`
    - Implement `execute_agent_review` task: retrieve document content from MinIO, get agent tuning params, construct review prompt, call InferenceClient.chat_completion(), parse response into ReviewReport, persist to AgentReview record, record inference_duration_ms
    - Implement `execute_master_summary` task: collect all completed agent reports, construct Master Auditor prompt, call InferenceClient, parse MasterReviewSummary, compute compliance_score, persist
    - Implement `check_review_completion` task: check if quorum met, trigger master summary if so, mark session Failed if quorum impossible
    - Set time_limit=1800 (30 min) on agent review task
    - Handle failures: mark AgentReview as Failed with error_reason, call check_review_completion
    - _Requirements: 1.4, 1.5, 1.6, 1.7, 2.1–2.7, 3.1–3.8_

  - [x] 5.3 Write property test for quorum enforcement (Property 2)
    - **Property 2: Quorum enforcement**
    - Generate random N agents and Q quorum with various success/failure combinations; verify session status follows quorum rules
    - **Validates: Requirements 1.4, 1.5, 1.6**

  - [x] 5.4 Write property test for state machine validity (Property 8)
    - **Property 8: Review session state machine validity**
    - Generate random sequences of state transitions; verify only valid transitions are accepted
    - **Validates: Requirements 1.3, 10.4**

  - [x] 5.5 Write property test for action item transitions (Property 9)
    - **Property 9: Action item status transitions**
    - Generate random status transition sequences; verify only valid transitions succeed
    - **Validates: Requirements 5.4**

- [x] 6. Master Auditor Archetype
  - [x] 6.1 Create Master Auditor archetype YAML
    - Create `agents/archetypes/master-auditor.yaml`
    - schema_version: "2.0", archetype: "Master Auditor", strictness: 0.95, temperature: 0.1, verbosity: "detailed", max_tokens: 8192
    - System prompt focused on synthesizing multiple review reports, identifying consensus/contradictions, computing compliance scores
    - domain_focus: ["compliance", "audit", "synthesis", "risk-assessment"]
    - _Requirements: 3.1_

- [x] 7. Missing Link Detection
  - [x] 7.1 Implement MissingLinkService
    - Create `src/backend/src/alcoabase/services/missing_link_service.py`
    - Implement detect_missing_links: query documents in Approved/Active status, check training completeness (all assigned users have Passed record for current version), check signature completeness (PAdES signature exists when workflow requires it)
    - Classify severity: Critical if both missing, Major if one missing
    - Return MissingLink objects with document metadata, missing_items, affected_user_count, days_since_approval
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 7.2 Write property test for missing link classification (Property 4)
    - **Property 4: Missing link classification**
    - Generate random combinations of training/signature presence; verify severity classification
    - **Validates: Requirements 7.4**

- [x] 8. Anomaly Detection
  - [x] 8.1 Implement AnomalyDetectionService
    - Create `src/backend/src/alcoabase/services/anomaly_detection.py`
    - Implement scan_for_anomalies: orchestrates all detection methods
    - Implement _detect_backdated_signatures: signature.timestamp < audit_log.timestamp - 5min → Critical
    - Implement _detect_workflow_bypasses: status change without workflow_transition → Critical
    - Implement _detect_bulk_approvals: same user >10 approvals in 1 hour → Major
    - Implement _detect_off_hours_mutations: mutations outside 06:00–22:00 → Minor
    - Implement _detect_rapid_version_churn: >5 versions same doc in 1 hour → Minor
    - Implement deduplication: skip if (type, doc_id, user_id) already exists within 24h
    - Implement list_alerts with filters, resolve_alert with resolution_note
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 8.2 Implement anomaly detection periodic Celery task
    - Add `scan_anomalies_periodic` task to `review_tasks.py`
    - Configure Celery beat schedule: every 15 minutes
    - Task iterates over all active companies and calls scan_for_anomalies for each
    - _Requirements: 8.1_

  - [x] 8.3 Write property test for anomaly deduplication (Property 5)
    - **Property 5: Anomaly deduplication**
    - Generate sequences of anomaly scans with overlapping events; verify no duplicates created
    - **Validates: Requirements 8.7**

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. FastAPI endpoints
  - [x] 10.1 Implement reviews router
    - Create `src/backend/src/alcoabase/api/reviews.py`
    - POST /api/reviews — submit review, return 202 with session_id
    - GET /api/reviews — list sessions (paginated, filterable by status, document_type, date_from, date_to, min_score, max_score)
    - GET /api/reviews/{session_id} — full session detail with agent reviews and master summary
    - POST /api/reviews/{session_id}/approve — approve (requires Completed status, X-Change-Reason)
    - POST /api/reviews/{session_id}/reject — reject (requires Completed status, X-Change-Reason)
    - GET /api/reviews/{session_id}/action-items — list action items
    - POST /api/reviews/{session_id}/action-items — create action item (X-Change-Reason)
    - PATCH /api/reviews/{session_id}/action-items/{item_id} — update status (X-Change-Reason)
    - Return 404 for wrong company, 409 for active review conflict
    - _Requirements: 10.1–10.8_

  - [x] 10.2 Implement audit profiles router
    - Create `src/backend/src/alcoabase/api/audit_profiles.py`
    - POST /api/audit-profiles — create profile (validate agents, quorum)
    - GET /api/audit-profiles — list profiles for company
    - GET /api/audit-profiles/frameworks — return SUPPORTED_FRAMEWORKS list
    - GET /api/audit-profiles/{profile_id} — get single profile
    - PUT /api/audit-profiles/{profile_id} — update profile
    - DELETE /api/audit-profiles/{profile_id} — soft-delete
    - All mutations require X-Change-Reason
    - _Requirements: 4.3, 4.6, 4.7_

  - [x] 10.3 Implement compliance router
    - Create `src/backend/src/alcoabase/api/compliance.py`
    - GET /api/compliance/scorecard — return ComplianceScorecardResponse
    - GET /api/compliance/missing-links — return list of MissingLinkResponse
    - GET /api/compliance/anomalies — list alerts (filterable by type, severity, is_resolved, date range)
    - PATCH /api/compliance/anomalies/{anomaly_id}/resolve — resolve alert (X-Change-Reason)
    - _Requirements: 6.2, 7.1, 8.4, 8.5_

  - [x] 10.4 Register new routers in router.py
    - Add reviews, audit_profiles, and compliance routers to the central router
    - _Requirements: 10.1–10.8_

  - [x] 10.5 Write property test for company-scoped isolation (Property 7)
    - **Property 7: Company-scoped isolation**
    - Generate multi-company review data; verify listing returns only data for the specified company
    - **Validates: Requirements 1.10, 4.6, 6.5, 7.6, 8.6**

  - [x] 10.6 Write unit tests for API endpoints
    - Test all HTTP status codes: 202, 200, 204, 400, 404, 409, 422
    - Test X-Change-Reason header enforcement on mutations
    - Test pagination and filtering
    - Test approve/reject state validation
    - Test audit profile validation (quorum, agent assignments)
    - _Requirements: 10.1–10.8_

- [x] 11. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Frontend — Review Dashboard
  - [x] 12.1 Create frontend API client functions and TypeScript types
    - Create `src/frontend/src/lib/reviews-api.ts` with typed API functions for all review, audit profile, compliance, and anomaly endpoints
    - Define TypeScript interfaces: ReviewSession, AgentReview, MasterSummary, ActionItem, AuditProfile, ComplianceScorecard, MissingLink, AnomalyAlert
    - Use existing apiClient with X-Change-Reason header on mutations
    - _Requirements: 11.1, 11.8_

  - [x] 12.2 Create Zustand store for review state
    - Create `src/frontend/src/stores/reviewStore.ts`
    - State: sessions list, current session detail, action items, scorecard, loading states
    - Actions: fetchSessions, fetchSessionDetail, submitReview, approveSession, rejectSession, updateActionItem
    - Polling logic: refresh current session every 10 seconds when status is Pending/InProgress
    - _Requirements: 11.7_

  - [x] 12.3 Implement ReviewDashboardPage with session list
    - Create `src/frontend/src/pages/ReviewDashboardPage.tsx`
    - Display filterable list of review sessions: Document, Type, Status (color-coded badge), Score, Findings (severity icons), Submitted Date, Actions
    - Filters: status, date range, document type, score range, audit profile
    - Link to session detail on row click
    - _Requirements: 11.1, 5.1, 5.5_

  - [x] 12.4 Implement ReviewSessionDetail component
    - Create `src/frontend/src/components/reviews/ReviewSessionDetail.tsx`
    - Progress tracker showing agent completion status with elapsed time
    - Individual agent reports in expandable cards with findings tables
    - Master summary in highlighted section
    - Approve/Reject buttons with change reason modal
    - _Requirements: 11.2, 5.2, 5.6, 5.7_

  - [x] 12.5 Implement AgentReportComparison component
    - Create `src/frontend/src/components/reviews/AgentReportComparison.tsx`
    - Side-by-side display of 2–4 agent reports with synchronized scrolling
    - Highlight consensus findings (green border)
    - Highlight contradictions (red border)
    - _Requirements: 11.3_

  - [x] 12.6 Implement SeverityHeatmap component
    - Create `src/frontend/src/components/reviews/SeverityHeatmap.tsx`
    - Grid visualization: chapters/sections on Y-axis, severity levels on X-axis
    - Color intensity indicates finding density
    - Colors: Critical (red), Major (orange), Minor (yellow), Informational (blue)
    - _Requirements: 11.4, 5.3_

  - [x] 12.7 Implement ActionItemTracker component
    - Create `src/frontend/src/components/reviews/ActionItemTracker.tsx`
    - Kanban-style board with columns: Open, In Progress, Resolved, Dismissed
    - Drag-and-drop between columns triggers status update with change reason prompt
    - Use @hello-pangea/dnd for drag-and-drop
    - _Requirements: 11.5, 5.4_

  - [x] 12.8 Implement ComplianceScorecard component
    - Create `src/frontend/src/components/reviews/ComplianceScorecard.tsx`
    - Large gauge/dial showing overall score
    - Risk band label with color coding
    - Trend indicator (arrow up/down/flat)
    - Breakdown by document type as bar chart
    - _Requirements: 11.6, 6.1, 6.2, 6.3_

  - [x] 12.9 Implement "Submit for Review" modal on document detail
    - Add review submission button to existing document detail page
    - Modal: select audit profile (or use default), confirm submission
    - Calls POST /api/reviews with X-Change-Reason
    - _Requirements: 11.8_

  - [x] 12.10 Add route and navigation for ReviewDashboardPage
    - Register /reviews route in App.tsx
    - Add navigation link in sidebar/header
    - _Requirements: 11.1_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The existing `DocumentReviewer` service is preserved; the new `ReviewPipelineService` orchestrates multiple DocumentReviewer instances
- All backend API endpoints use the `/api` prefix (not `/api/v1`)
- All mutating requests require the `X-Change-Reason` header per AuditMiddleware conventions
- Frontend uses the existing `apiClient` for consistent auth and header handling
- Celery tasks use the existing `celery_app` from `alcoabase/tasks/celery_app.py`
- The Master Auditor archetype is added to `agents/archetypes/` alongside existing archetypes from 5.1

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.5"] },
    { "id": 1, "tasks": ["1.4", "1.6"] },
    { "id": 2, "tasks": ["2.1", "3.1", "3.3"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.2", "3.4"] },
    { "id": 4, "tasks": ["5.1", "6.1"] },
    { "id": 5, "tasks": ["5.2"] },
    { "id": 6, "tasks": ["5.3", "5.4", "5.5", "7.1", "8.1"] },
    { "id": 7, "tasks": ["7.2", "8.2", "8.3"] },
    { "id": 8, "tasks": ["10.1", "10.2", "10.3", "10.4"] },
    { "id": 9, "tasks": ["10.5", "10.6"] },
    { "id": 10, "tasks": ["12.1", "12.2"] },
    { "id": 11, "tasks": ["12.3", "12.4", "12.5", "12.6", "12.7", "12.8"] },
    { "id": 12, "tasks": ["12.9", "12.10"] }
  ]
}
```
