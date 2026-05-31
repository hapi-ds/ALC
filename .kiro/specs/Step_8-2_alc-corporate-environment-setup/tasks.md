# Implementation Plan: ALC Corporate Environment Setup

## Overview

Implement the `ALCSeedService` — a backend service that initializes the dedicated "ALC" company tenant within AlcoaBase's multi-tenancy framework. The service provisions company entity, user pool, regulatory configuration, governance folder structure, AI risk profile, agent activations, and a governance workflow definition. Accessible via CLI script and REST API endpoint, with full idempotency and single-transaction atomicity.

## Tasks

- [x] 1. Define schemas, constants, and configuration
  - [x] 1.1 Create Pydantic schemas for SeedReport and related result models
    - Create `src/backend/src/alcoabase/schemas/alc_seed.py`
    - Define `UserPoolResult`, `FolderResult`, `AgentResult`, `SeedReport`, and `SeedError` Pydantic models
    - All fields must match the design document exactly (company_id, company_slug, users_created, users_skipped, folders_created, folders_skipped, risk_profile_created, regulatory_baseline_created, audit_config_created, agents_activated, agents_skipped, workflow_created, total_duration_ms)
    - _Requirements: 6.4, 7.5, 8.4_

  - [x] 1.2 Create seed data constants module
    - Create `src/backend/src/alcoabase/services/alc_seed_constants.py`
    - Define `ALC_COMPANY_DATA`, `ALC_USER_POOL`, `ALC_GOVERNANCE_FOLDERS`, `ALC_REGULATORY_BASELINE`, `ALC_AUDIT_CONFIG`, `ALC_GOVERNANCE_BPMN_XML`, and `RESERVED_SLUGS` as specified in the design
    - _Requirements: 1.1, 2.1, 3.1, 3.2, 4.1, 8.1_

  - [x] 1.3 Add ALC_SEED_DEFAULT_PASSWORD to Settings in config.py
    - Add `alc_seed_default_password` field to the existing `Settings` class with default `"AlcCorp2024!"` and alias `ALC_SEED_DEFAULT_PASSWORD`
    - _Requirements: 2.2_

- [x] 2. Implement slug reservation guard
  - [x] 2.1 Add slug reservation validation
    - Create `validate_company_slug()` function in the constants module (or a shared utility)
    - Integrate the check into `SetupService.create_initial_company()` and any company creation API endpoint to reject the reserved slug `"alc-corporate"`
    - Raise `ValueError` with a descriptive message when the reserved slug is used
    - _Requirements: 1.3_

  - [x] 2.2 Write property test for slug reservation (Property 4)
    - **Property 4: Slug reservation — reserved slug is always rejected**
    - **Validates: Requirements 1.3**
    - Create test in `src/backend/tests/properties/test_alc_seed_properties.py`
    - For any company creation request specifying slug "alc-corporate", the system rejects it regardless of other attributes

- [x] 3. Implement ALCSeedService core
  - [x] 3.1 Create ALCSeedService class with execute() orchestrator
    - Create `src/backend/src/alcoabase/services/alc_seed_service.py`
    - Implement `ALCSeedService.__init__(self, session: AsyncSession)` and `async execute() -> SeedReport`
    - The orchestrator calls each step method in sequence, collects results, and assembles the `SeedReport`
    - Include timing measurement for `total_duration_ms`
    - Use structured logging with `seed_step` field throughout
    - _Requirements: 6.1, 6.3, 6.4, 6.6, 6.7_

  - [x] 3.2 Implement _create_company() step
    - Query for existing company by slug `"alc-corporate"`
    - If exists: skip and return existing entity
    - If not: create with all attributes from `ALC_COMPANY_DATA`
    - Log at INFO level for create or skip
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 3.3 Implement _provision_users() step
    - Loop through `ALC_USER_POOL`, check existence by username
    - Handle email conflicts (skip with WARNING log)
    - Create User, Role (if not exists with company_id and is_system=True), UserRole, and CompanyMembership records
    - Hash password using configured `ALC_SEED_DEFAULT_PASSWORD`
    - Check and create root admin CompanyMembership if not present
    - Return `UserPoolResult` with created/skipped lists
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [x] 3.4 Implement _apply_regulatory_baseline() step
    - Check for existing SystemConfiguration rows by category + company_id
    - Create `"alc_regulatory_baseline"` row if not exists
    - Create `"alc_audit_config"` row if not exists
    - Set `updated_by` to ALC IT Administrator user
    - Return tuple of (baseline_created, audit_created) booleans
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.5 Implement _create_folder_structure() step
    - Verify ALC IT Administrator exists (abort with error if missing)
    - Loop through `ALC_GOVERNANCE_FOLDERS`, check existence by name + company_id
    - Create VirtualFolder with is_system_default=True, created_by=IT Admin
    - Return `FolderResult` with created/skipped lists
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.6 Implement _configure_risk_profile() step
    - Check for existing active CompanyRiskProfile for ALC_Company
    - Verify all 8 AITaskType records exist and are active (abort with error listing missing types if not)
    - Create CompanyRiskProfile with empty overrides array (no RiskTierOverride or RiskAssessmentRecord)
    - Return boolean was_created
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 3.7 Implement _activate_agents() step
    - Query all global AgentDefinition records (company_id IS NULL, is_active=True)
    - For each: check existing CompanyAgentActivation
    - If active: skip. If inactive: reactivate. If missing: create.
    - Handle empty agent table gracefully
    - Return `AgentResult` with activated/skipped lists
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 3.8 Implement _create_governance_workflow() step
    - Check for existing WorkflowDefinition with document_tag "ALC-GOV" for ALC_Company
    - If exists: skip. If IT Admin or company missing: fail gracefully.
    - Create WorkflowDefinition with all attributes from design (name, document_tag, is_active, signature_required_transitions, training_trigger_transitions, BPMN XML)
    - Create WorkflowVersion with version_number=1, same BPMN XML, change_reason for initial seed
    - Return boolean was_created
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 4. Checkpoint - Ensure core service logic is complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement CLI script and API endpoint
  - [x] 5.1 Create CLI script for seed execution
    - Create `src/backend/src/alcoabase/scripts/seed_alc_corporate.py`
    - Create async session, call `ALCSeedService.execute()`, manage transaction (commit on success, rollback on failure)
    - Print SeedReport as JSON to stdout on success (exit 0)
    - Print error details to stderr on failure (exit 1)
    - Ensure script is invocable via `uv run python -m alcoabase.scripts.seed_alc_corporate`
    - _Requirements: 6.1, 6.5_

  - [x] 5.2 Create API endpoint for seed execution
    - Create `src/backend/src/alcoabase/api/admin_seed.py` with `POST /api/admin/seed-alc-corporate`
    - Require system_administrator role authentication
    - Require X-Change-Reason header (return 400 if missing)
    - Return 401 for unauthorized, 200 with SeedReport on success, 500 with SeedError on failure
    - Register the router in `api/router.py`
    - _Requirements: 6.2, 6.8_

- [x] 6. Write property-based tests
  - [x] 6.1 Write property test for idempotency (Property 1)
    - **Property 1: Idempotency — repeated execution preserves state**
    - **Validates: Requirements 1.2, 2.3, 3.3, 3.4, 4.3, 5.3, 6.7, 7.2, 8.3**
    - Create test in `src/backend/tests/properties/test_alc_seed_properties.py`
    - Generate random initial DB states with subsets of ALC entities pre-existing
    - Execute seed twice, assert second run reports all entities as skipped

  - [x] 6.2 Write property test for transaction atomicity (Property 2)
    - **Property 2: Transaction atomicity — failure causes complete rollback**
    - **Validates: Requirements 1.5, 2.9, 6.3**
    - For any step that raises an exception, assert DB contains zero records from the seeding attempt

  - [x] 6.3 Write property test for SeedReport accuracy (Property 3)
    - **Property 3: Seed_Report accuracy — report reflects actual database changes**
    - **Validates: Requirements 6.4, 7.5, 8.4**
    - For any initial DB state, assert report's created/skipped arrays match actual DB changes

  - [x] 6.4 Write property test for password configuration (Property 5)
    - **Property 5: Password configuration — seed users authenticate with configured password**
    - **Validates: Requirements 2.2**
    - For any non-empty password string, assert all created users have bcrypt hashes verifying against that value

  - [x] 6.5 Write property test for agent activation completeness (Property 6)
    - **Property 6: Agent activation completeness — all global agents are activated**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    - For any set of global AgentDefinition records, assert exactly one active CompanyAgentActivation per agent after seeding

- [x] 7. Write unit tests
  - [x] 7.1 Write unit tests for company creation and user provisioning
    - Create `src/backend/tests/unit/test_alc_seed_service.py`
    - Test: fresh company creation, existing company skip, all users created, partial users exist, email conflict handling, root admin membership creation/skip
    - _Requirements: 1.1, 1.2, 2.1, 2.3, 2.6, 2.7_

  - [x] 7.2 Write unit tests for regulatory baseline, folders, and risk profile
    - Test: baseline created, baseline exists skip, audit config created, audit config exists skip, all folders created, partial folders exist, IT admin missing abort, risk profile created, risk profile exists skip, missing AITaskTypes abort
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.3, 4.4, 5.1, 5.3, 5.5_

  - [x] 7.3 Write unit tests for agent activation and workflow creation
    - Test: agents activated, agents reactivated, no agents graceful, workflow created, workflow exists skip, SeedReport structure validation, slug reservation rejection
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3_

- [x] 8. Write integration tests
  - [x] 8.1 Write integration tests for CLI and API
    - Create `src/backend/tests/integration/test_alc_seed_integration.py`
    - Test: CLI success (exit 0, valid JSON), CLI failure (exit 1, stderr), API 200 success, API 401 unauthorized, API 400 missing header, full idempotent run, transaction rollback on simulated failure
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.7, 6.8_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The service uses Python with FastAPI, SQLAlchemy async, and Pydantic v2
- All tests use pytest + Hypothesis (property-based) as per project conventions
- CLI invocation: `uv run python -m alcoabase.scripts.seed_alc_corporate`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8"] },
    { "id": 3, "tasks": ["5.1", "5.2"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3"] },
    { "id": 6, "tasks": ["8.1"] }
  ]
}
```
