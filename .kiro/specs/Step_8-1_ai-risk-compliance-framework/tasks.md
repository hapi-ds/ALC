# Implementation Plan: AI Risk & Compliance Framework

## Overview

This plan implements the AI Risk & Compliance Framework as a cross-cutting governance layer for AlcoaBase. The implementation follows the layered architecture: database models and migrations first, then service layer (RiskClassificationService, ControlGate, decorator), API routes, and finally the React admin UI. Property-based tests validate correctness properties from the design document alongside implementation tasks.

## Tasks

- [ ] 1. Database models, enums, and migration
  - [ ] 1.1 Create risk framework enum definitions and data models
    - Create `src/backend/src/alcoabase/models/risk_framework.py` with all SQLAlchemy models: AITaskType, CompanyRiskProfile, RiskTierOverride, RiskAssessmentRecord, HITLCheckpoint, AIOperationLog, ControlEnforcementLog
    - Define enums: RiskTier, AuditDepth, GateResult, CheckpointStatus in the models file
    - AITaskType, CompanyRiskProfile, HITLCheckpoint use AuditMixin (SQLAlchemy-Continuum)
    - RiskAssessmentRecord, AIOperationLog, ControlEnforcementLog use immutability event listeners (no UPDATE/DELETE)
    - Add unique constraint on (company_id, is_active) filtered to is_active=true for CompanyRiskProfile
    - Register models in `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [ ] 1.2 Create Alembic migration for risk framework tables
    - Generate migration in `src/backend/alembic/versions/` for all risk framework tables
    - Include enum type creation for risk_tier, audit_depth, gate_result, checkpoint_status
    - Include indexes on company_id, task_type_id, created_at for query performance
    - Include partial unique index on CompanyRiskProfile (company_id) WHERE is_active=true
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ] 1.3 Create seed data for default AI task types
    - Create `src/backend/src/alcoabase/services/risk_framework_seed.py` with a function to seed the 8 default AI task types (document_generation, multi_agent_audit, training_content_generation, change_impact_analysis, traceability_gap_discovery, rag_knowledge_query, document_search, template_analysis) with their default risk tiers, risk factors, and module references
    - Seed function should be idempotent (skip existing entries)
    - _Requirements: 1.2_

- [ ] 2. Pydantic schemas for risk framework
  - [ ] 2.1 Create request/response schemas
    - Create `src/backend/src/alcoabase/schemas/risk_framework.py` with Pydantic v2 models
    - Request schemas: CreateProfileRequest, UpdateProfileRequest, ReviewCheckpointRequest, CheckpointFilters
    - Response schemas: AITaskTypeResponse, AITaskTypeDetailResponse, CompanyRiskProfileResponse, HITLCheckpointResponse, AIOperationLogResponse, ControlEnforcementLogResponse, DashboardStatsResponse, TierDefinitionResponse, PaginatedResult generic
    - Include field validators for task_type_id pattern (^[a-z0-9_]{1,100}$), profile_name length (3-200), justification minimum (50 chars for de-escalation), reviewer_comments required on reject
    - _Requirements: 1.1, 3.2, 5.2, 5.11, 10.1–10.16_

- [ ] 3. Service layer — RiskClassificationService
  - [ ] 3.1 Implement RiskClassificationService
    - Create `src/backend/src/alcoabase/services/risk_classification_service.py`
    - Implement: get_task_types, get_task_type, get_effective_tier, create_profile, update_profile, get_active_profile, get_profile_history, get_dashboard_stats
    - Tier resolution: check CompanyRiskProfile overrides first, fall back to AITaskType.default_risk_tier
    - Profile creation deactivates previous active profile (single active profile per company)
    - Create RiskAssessmentRecord on every tier change (escalation and de-escalation)
    - Enforce de-escalation rules: require justification ≥50 chars, regulatory_reference, approved_by
    - Validate override task_type_ids exist in registry; reject duplicates
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 3.1–3.11, 9.7_

  - [ ]* 3.2 Write property tests for RiskClassificationService
    - **Property 2: Task Type Field Validation** — verify acceptance/rejection based on field constraints
    - **Property 3: Pagination Correctness** — verify paginated results are correct slices
    - **Property 6: Profile Creation Validation** — verify profile acceptance/rejection rules
    - **Property 9: Single Active Profile Per Company** — verify at most one active profile
    - **Property 10: Tier Resolution with Fallback** — verify override-first, then default, then error
    - **Validates: Requirements 1.1, 1.3, 3.2, 3.7, 3.8, 3.10, 3.11, 9.7**
    - Create `src/backend/tests/properties/test_risk_framework_properties.py`

- [ ] 4. Service layer — ControlGate and decorator
  - [ ] 4.1 Implement ControlGate service
    - Create `src/backend/src/alcoabase/services/control_gate.py`
    - Implement pre_execution_check: resolve tier, verify HITL reviewer availability, audit trail writability
    - Implement post_execution_log: create AIOperationLog and ControlEnforcementLog at tier-appropriate audit depth
    - Block operation if task_type_id is unregistered or required controls unavailable
    - For High/Medium tiers: write audit log synchronously before returning response
    - If audit log write fails for High/Medium: raise AuditWriteError, do NOT return AI output
    - Define ControlSet dataclass and TIER_CONTROL_SETS static mapping
    - _Requirements: 4.1–4.10, 6.1–6.4, 6.8, 6.9_

  - [ ] 4.2 Implement @risk_controlled decorator
    - Create `src/backend/src/alcoabase/services/risk_controlled.py`
    - Decorator wraps async service functions, invokes ControlGate.pre_execution_check before execution
    - On success: call post_execution_log, create HITL checkpoint for High/Medium tiers
    - On exception: log operation as "failure" with available fields, re-raise original exception
    - For High tier: block output visibility until HITL approved
    - For Medium tier: tag output "ai_assisted", block automated actions until HITL approved
    - For Low tier: return output immediately with "ai_generated" tag
    - _Requirements: 4.2, 4.3, 4.4, 9.1, 9.8_

  - [ ]* 4.3 Write property tests for ControlGate
    - **Property 4: Unregistered Task Type Blocking** — verify unregistered task types are always blocked
    - **Property 11: Tier-Appropriate Output Handling** — verify correct output behavior per tier
    - **Property 12: Control Enforcement Log Invariant** — verify exactly one log per operation
    - **Property 13: Gate Blocks on Unavailable Controls** — verify blocking when controls unavailable
    - **Property 14: Audit Depth Matches Tier** — verify log fields match tier audit depth
    - **Property 16: Immutable Operation Logs** — verify UPDATE/DELETE raises ImmutableRecordError
    - **Property 17: Audit Logging Resilience** — verify synchronous logging for High/Medium, failure logging
    - **Validates: Requirements 1.7, 4.2–4.8, 6.1–6.4, 6.8, 6.9**
    - Add tests to `src/backend/tests/properties/test_risk_framework_properties.py`

- [ ] 5. Service layer — HITLCheckpointService
  - [ ] 5.1 Implement HITLCheckpointService
    - Create `src/backend/src/alcoabase/services/hitl_checkpoint_service.py`
    - Implement: list_checkpoints (with filters, pagination), review_checkpoint (approve/reject with optimistic locking), expire_stale_checkpoints
    - State machine: pending → approved | rejected | expired (no other transitions)
    - Only system_admin or doc_admin can review
    - Rejection requires non-empty reviewer_comments
    - Concurrent review handling via version column (optimistic locking)
    - Expired checkpoints: mark output as invalid, prevent approval/rejection
    - _Requirements: 5.1–5.11, 8.9_

  - [ ]* 5.2 Write property tests for HITLCheckpointService
    - **Property 5: Checkpoint Expiry Invalidates Output** — verify expired checkpoints block actions
    - **Property 7: Escalation/De-escalation Enforcement** — verify approval rules for tier changes
    - **Property 8: Risk Assessment Record on Tier Change** — verify immutable record creation
    - **Property 15: Checkpoint Review State Machine** — verify valid transitions and role enforcement
    - **Validates: Requirements 2.7, 3.5, 3.6, 4.10, 5.2, 5.6, 5.7, 5.9, 5.11, 8.3, 8.9, 8.10**
    - Add tests to `src/backend/tests/properties/test_risk_framework_properties.py`

- [ ] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. API routes for risk framework
  - [ ] 7.1 Implement risk framework API router
    - Create `src/backend/src/alcoabase/api/risk_framework.py` with FastAPI router prefix `/risk-framework`
    - Endpoints: GET /task-types, GET /task-types/{task_type_id}, GET /tiers, GET /tiers/{tier_level}, POST /profiles, GET /profiles, PUT /profiles/{profile_id}, GET /profiles/history, GET /checkpoints, POST /checkpoints/{checkpoint_id}/review, GET /operation-logs, GET /dashboard-stats
    - All endpoints require X-Company-Id header; mutations require X-Change-Reason
    - Role check: system_admin or doc_admin required (return 403 otherwise)
    - Register router in `src/backend/src/alcoabase/api/router.py`
    - _Requirements: 1.3, 1.4, 1.5, 2.4, 2.5, 2.6, 3.2, 3.3, 3.4, 3.9, 5.1, 5.2, 5.8, 6.5, 6.7, 10.1–10.16_

  - [ ]* 7.2 Write unit tests for risk framework API endpoints
    - Create `src/backend/tests/unit/test_risk_framework/test_risk_framework_api.py`
    - Test all endpoint validation, error responses (400, 403, 404, 409, 422)
    - Test pagination parameters, filter combinations
    - Test X-Company-Id scoping and X-Change-Reason enforcement
    - _Requirements: 10.13, 10.14, 10.15, 10.16_

- [ ] 8. Multi-tenancy isolation property test
  - [ ]* 8.1 Write property test for multi-tenancy isolation
    - **Property 1: Multi-tenancy Isolation** — verify queries for company A never return company B's data
    - **Validates: Requirements 1.6, 3.9, 5.8, 6.7, 10.13**
    - Add test to `src/backend/tests/properties/test_risk_framework_properties.py`

- [ ] 9. Frontend — API client and store
  - [ ] 9.1 Create risk framework API client
    - Create `src/frontend/src/lib/riskFrameworkApi.ts`
    - Typed functions for all /api/risk-framework/* endpoints using apiClient
    - Include proper typing for request/response payloads
    - _Requirements: 10.1–10.12_

  - [ ] 9.2 Create risk framework Zustand store
    - Create `src/frontend/src/stores/riskFrameworkStore.ts`
    - State: taskTypes, activeProfile, checkpoints, operationLogs, dashboardStats, loading states, error states
    - Actions: fetchTaskTypes, fetchProfile, createProfile, updateProfile, fetchCheckpoints, reviewCheckpoint, fetchOperationLogs, fetchDashboardStats
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 10. Frontend — AI Risk Framework admin page
  - [ ] 10.1 Create AIRiskFrameworkPage with tab navigation
    - Create `src/frontend/src/pages/AIRiskFrameworkPage.tsx`
    - Tab structure: Dashboard, Task Types, Risk Profile, HITL Queue, Operation Logs
    - Route at /admin/ai-risk-framework, restricted to system_admin/doc_admin roles
    - Redirect unauthorized users to main dashboard with access denied notification
    - Use shadcn/ui components (Tabs, Card, Table, Badge, Button, Dialog)
    - _Requirements: 7.1, 7.7_

  - [ ] 10.2 Implement Dashboard tab with stats and risk matrix
    - Summary cards: operations by tier (last 30 days), pending checkpoints, expired checkpoints, blocked operations, active profile name
    - 3x3 risk matrix visualization showing task types positioned by impact/likelihood, color-coded by tier
    - Fetch data from GET /api/risk-framework/dashboard-stats
    - _Requirements: 7.2, 7.8_

  - [ ] 10.3 Implement Task Types tab
    - Paginated table (20 rows/page) with columns: display_name, module_reference, default_tier, company_tier, status
    - Expandable rows showing risk_factors and applicable ControlSet
    - _Requirements: 7.3_

  - [ ] 10.4 Implement Risk Profile tab
    - View current CompanyRiskProfile with overrides
    - Create new profile form with profile_name, regulatory_frameworks, overrides
    - De-escalation overrides require regulatory_reference field and display approval notice
    - Profile history viewer
    - _Requirements: 7.4_

  - [ ] 10.5 Implement HITL Queue tab
    - Paginated table (20 rows/page) sorted by expires_at ascending
    - Columns: operation type, created date, expires date, status, Review action button
    - Review detail panel: AI output content, operation metadata, approve/reject controls with reviewer_comments field
    - _Requirements: 7.5_

  - [ ] 10.6 Implement Operation Logs tab
    - Paginated table (20 rows/page) with filtering by task type, tier, date range, outcome
    - Fetch from GET /api/risk-framework/operation-logs
    - _Requirements: 7.6_

  - [ ]* 10.7 Write frontend tests for AIRiskFrameworkPage
    - Create `src/frontend/src/__tests__/AIRiskFrameworkPage.test.tsx`
    - Test page rendering, tab navigation, role-based access redirect
    - Create `src/frontend/src/__tests__/riskFrameworkStore.test.ts`
    - Test Zustand store actions and state management
    - _Requirements: 7.1–7.8_

- [ ] 11. Integration wiring and Celery task
  - [ ] 11.1 Create Celery task for checkpoint expiry
    - Create or extend `src/backend/src/alcoabase/tasks/risk_framework_tasks.py`
    - Implement `expire_stale_checkpoints` task running every 15 minutes
    - Idempotent: multiple runs on same checkpoint have no additional effect
    - Mark expired checkpoints, create alert entries for compliance dashboard
    - _Requirements: 2.7, 4.10, 5.6_

  - [ ] 11.2 Wire @risk_controlled decorator to existing AI services
    - Add `@risk_controlled(task_type_id="document_generation")` to Document Generator pipeline
    - Add `@risk_controlled(task_type_id="multi_agent_audit")` to Multi-Agent Auditing pipeline
    - Add `@risk_controlled(task_type_id="rag_knowledge_query")` to RAG query service
    - Add `@risk_controlled(task_type_id="change_impact_analysis")` to Change Impact Analysis
    - Add `@risk_controlled(task_type_id="training_content_generation")` to Training Ecosystem
    - Add `@risk_controlled(task_type_id="traceability_gap_discovery")` to Traceability Discovery
    - No modifications to InferenceClient interface
    - _Requirements: 9.1–9.6, 9.8, 9.9_

- [ ] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The `@risk_controlled` decorator integration (task 11.2) should be applied carefully to avoid breaking existing service tests — mock the ControlGate in existing test suites
- The Celery task (11.1) requires Redis to be running; integration tests should use the Docker Compose stack

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["3.2", "4.2", "5.1"] },
    { "id": 4, "tasks": ["4.3", "5.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1", "9.1"] },
    { "id": 6, "tasks": ["9.2", "11.1"] },
    { "id": 7, "tasks": ["10.1"] },
    { "id": 8, "tasks": ["10.2", "10.3", "10.4", "10.5", "10.6"] },
    { "id": 9, "tasks": ["10.7", "11.2"] }
  ]
}
```
