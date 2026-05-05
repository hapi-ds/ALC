# Implementation Plan: Setup Wizard

## Overview

Implement the first-run Setup Wizard for AlcoaBase — a step-by-step initialization flow that creates the root admin, initial company, configures AI mode, and optionally seeds demo data. The implementation follows a bottom-up dependency order: database model → schemas → services → middleware → API router → integration into main.py → tests → documentation.

## Tasks

- [ ] 1. Create SetupStatus database model and Alembic migration
  - [ ] 1.1 Create the SetupStatus SQLAlchemy model
    - Create `src/backend/src/alcoabase/models/setup_status.py` with the `SetupStatus` class
    - Single-row table with columns: `id`, `is_complete`, `admin_created`, `company_created`, `ai_mode_configured`, `demo_data_seeded`, `root_admin_id` (FK → users.id), `company_id` (FK → companies.id), `ai_hardware_mode`, `started_at`, `completed_at`
    - Export from `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 1.4, 7.1, 7.2_

  - [ ] 1.2 Generate Alembic migration for setup_status table
    - Run `uv run alembic revision --autogenerate -m "add_setup_status_table"` from `src/backend/`
    - Verify the generated migration creates the table with correct columns, foreign keys, and defaults
    - _Requirements: 1.4_

- [ ] 2. Create Pydantic schemas for setup endpoints
  - [ ] 2.1 Create setup request and response schemas
    - Create `src/backend/src/alcoabase/schemas/setup.py`
    - Implement: `RootAdminCreate`, `CompanySetupCreate`, `AIModeConfig`, `SetupCompleteRequest`, `SetupProgress`, `RootAdminResult`, `CompanyResult`, `AIModeResult`, `SetupCompleteResult`
    - Use `Field` constraints for validation (min_length, max_length, Literal types)
    - Export from `src/backend/src/alcoabase/schemas/__init__.py`
    - _Requirements: 3.1, 3.2, 4.1, 4.3, 5.1, 8.1_

- [ ] 3. Implement PasswordValidator service
  - [ ] 3.1 Create the PasswordValidator class
    - Create `src/backend/src/alcoabase/services/password_validator.py`
    - Implement `validate(password: str) -> list[str]` returning list of unmet policy requirements
    - Policy: min 12 chars, at least one uppercase, one lowercase, one digit, one special character
    - Export from `src/backend/src/alcoabase/services/__init__.py`
    - _Requirements: 3.2, 3.3_

- [ ] 4. Implement SlugGenerator service
  - [ ] 4.1 Create the SlugGenerator class
    - Create `src/backend/src/alcoabase/services/slug_generator.py`
    - Implement `generate(display_name: str) -> str` to produce URL-safe slugs from display names
    - Implement `validate(slug: str) -> bool` to check slug matches `^[a-z0-9]+(-[a-z0-9]+)*$`
    - Handle unicode normalization, whitespace collapsing, special character removal
    - Export from `src/backend/src/alcoabase/services/__init__.py`
    - _Requirements: 4.2, 4.3_

- [ ] 5. Implement SetupService (core business logic)
  - [ ] 5.1 Create the SetupService class with status and admin methods
    - Create `src/backend/src/alcoabase/services/setup_service.py`
    - Implement `is_initialized() -> bool` querying setup_status table
    - Implement `get_status() -> SetupProgress` returning current step completion
    - Implement `create_root_admin(data: RootAdminCreate) -> RootAdminResult` with password validation, bcrypt hashing, user creation, role assignment, JWT generation, and audit logging
    - Handle idempotency: return 409 if admin already exists
    - _Requirements: 1.1, 1.2, 1.3, 3.1, 3.4, 3.5, 3.6, 8.1, 8.2, 8.4, 9.1, 9.5_

  - [ ] 5.2 Implement company creation and AI mode configuration methods
    - Implement `create_initial_company(data: CompanySetupCreate, admin_id: int) -> CompanyResult` with slug generation/validation, company creation, admin membership, and audit logging
    - Implement `configure_ai_mode(data: AIModeConfig) -> AIModeResult` with connectivity check (non-blocking warning), persistence, and audit logging
    - Handle idempotency: return 409 if company already exists
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 8.3, 8.4, 9.2, 9.3_

  - [ ] 5.3 Implement setup completion and demo data seeding methods
    - Implement `complete_setup(admin_id: int, seed_demo: bool) -> SetupCompleteResult` that validates all steps complete, optionally seeds demo data, sets is_complete=True, records timestamp, invalidates guard cache, and logs audit event
    - Implement demo data seeding logic: create sample documents, templates, virtual folders, workflow definitions tagged with `is_demo_data=True`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 9.4_

  - [ ] 5.4 Export SetupService from services __init__.py
    - Update `src/backend/src/alcoabase/services/__init__.py`
    - _Requirements: 3.1_

- [ ] 6. Implement SetupGuardMiddleware
  - [ ] 6.1 Create the SetupGuardMiddleware class
    - Create `src/backend/src/alcoabase/middleware/setup_guard.py`
    - Implement `dispatch(request, call_next)` with in-memory cached initialization state
    - When uninitialized: allow `/health`, `/api/v1/setup/**`, `/docs`, `/openapi.json`; return 503 for all others
    - When initialized: return 403 for `/api/v1/setup/**`; allow all others
    - Implement `invalidate_cache()` class method for service layer to call after completion
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 7.3_

  - [ ] 6.2 Export SetupGuardMiddleware from middleware __init__.py
    - Update `src/backend/src/alcoabase/middleware/__init__.py`
    - _Requirements: 2.1_

- [ ] 7. Create Setup API router and endpoints
  - [ ] 7.1 Create the setup router with all endpoints
    - Create `src/backend/src/alcoabase/api/setup.py`
    - Implement `GET /api/v1/setup/status` — no auth, returns SetupProgress
    - Implement `POST /api/v1/setup/admin` — no auth, creates root admin, returns RootAdminResult (201)
    - Implement `POST /api/v1/setup/company` — JWT required, creates company, returns CompanyResult (201)
    - Implement `POST /api/v1/setup/ai-mode` — JWT required, configures AI mode, returns AIModeResult (200)
    - Implement `POST /api/v1/setup/complete` — JWT required, finalizes setup, returns SetupCompleteResult (200)
    - Use proper error responses: 409 for conflicts, 422 for validation, 400 for incomplete steps
    - _Requirements: 3.1, 3.3, 3.6, 4.1, 4.3, 5.1, 6.1, 6.3, 7.1, 7.4, 8.1, 8.2, 8.3_

  - [ ] 7.2 Register setup router in the main API router
    - Update `src/backend/src/alcoabase/api/router.py` to include the setup router with prefix `/api/v1/setup`
    - _Requirements: 2.2_

- [ ] 8. Integrate SetupGuardMiddleware into main.py
  - [ ] 8.1 Register SetupGuardMiddleware in the application middleware stack
    - Add `app.add_middleware(SetupGuardMiddleware)` as the last middleware registration in `src/backend/src/alcoabase/main.py` (LIFO: executes first)
    - Import from `alcoabase.middleware`
    - _Requirements: 1.1, 2.1, 2.4_

- [ ] 9. Checkpoint - Ensure core implementation compiles and basic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Property-based tests for correctness properties
  - [ ]* 10.1 Write property test for Setup Guard Routing Correctness
    - Create `src/backend/tests/properties/test_setup_guard_properties.py`
    - **Property 1: Setup Guard Routing Correctness**
    - Generate random API paths and initialization states; verify 503/403/allow behavior matches specification
    - **Validates: Requirements 1.2, 2.1, 2.2, 2.3, 7.3**

  - [ ]* 10.2 Write property test for Password Policy Validation Completeness
    - Create `src/backend/tests/properties/test_password_validator_properties.py`
    - **Property 2: Password Policy Validation Completeness**
    - Generate random strings with controlled character classes; verify rejection iff at least one rule violated, and error list matches exactly the violated rules
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 10.3 Write property test for Password Hashing Round-Trip
    - Create `src/backend/tests/properties/test_password_hashing_properties.py`
    - **Property 3: Password Hashing Round-Trip**
    - Generate random valid passwords; verify hash-then-verify returns True for original and False for any different string
    - **Validates: Requirements 3.4**

  - [ ]* 10.4 Write property test for Root Admin Creation Preserves Identity
    - Add to `src/backend/tests/properties/test_setup_service_properties.py`
    - **Property 4: Root Admin Creation Preserves Identity**
    - Generate random valid admin inputs; verify created user fields match input and JWT decodes to correct subject
    - **Validates: Requirements 3.1, 3.6**

  - [ ]* 10.5 Write property test for Company Creation Preserves Fields
    - Add to `src/backend/tests/properties/test_setup_service_properties.py`
    - **Property 5: Company Creation Preserves Fields**
    - Generate random valid company inputs; verify created company fields match input
    - **Validates: Requirements 4.1**

  - [ ]* 10.6 Write property test for Slug Validity
    - Create `src/backend/tests/properties/test_slug_properties.py`
    - **Property 6: Slug Validity**
    - Generate random unicode display names; verify generated slug is non-empty and matches `^[a-z0-9]+(-[a-z0-9]+)*$`. Generate random ASCII strings; verify validator accepts iff pattern matches
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 10.7 Write property test for Demo Data Tagging Invariant
    - Create `src/backend/tests/properties/test_demo_seed_properties.py`
    - **Property 7: Demo Data Tagging Invariant**
    - Seed demo data with random regulatory frameworks; verify all seeded records have `is_demo_data=True` and no non-seeded records have the flag
    - **Validates: Requirements 6.4**

  - [ ]* 10.8 Write property test for Setup Progress Accuracy
    - Create `src/backend/tests/properties/test_setup_progress_properties.py`
    - **Property 8: Setup Progress Accuracy**
    - Generate random boolean step combinations in DB; verify progress endpoint response matches actual DB state
    - **Validates: Requirements 8.1**

  - [ ]* 10.9 Write property test for Setup Step Idempotency
    - Create `src/backend/tests/properties/test_setup_idempotency_properties.py`
    - **Property 9: Setup Step Idempotency**
    - Generate random valid inputs; submit same request twice; verify entity count unchanged after second submission
    - **Validates: Requirements 8.4**

- [ ] 11. Unit tests for setup wizard components
  - [ ]* 11.1 Write unit tests for PasswordValidator and SlugGenerator
    - Create `src/backend/tests/unit/test_setup_wizard.py`
    - Test password validator: valid passwords pass, each individual rule violation detected, multiple violations reported together
    - Test slug generator: basic names, unicode handling, whitespace collapsing, empty/edge cases
    - Test slug validator: valid slugs accepted, invalid characters rejected
    - _Requirements: 3.2, 3.3, 4.2, 4.3_

  - [ ]* 11.2 Write unit tests for SetupGuardMiddleware
    - Add tests to `src/backend/tests/unit/test_setup_wizard.py`
    - Test: allows `/health` when uninitialized, allows setup paths when uninitialized, returns 503 for other paths when uninitialized, returns 403 for setup paths when initialized, allows other paths when initialized, cache invalidation triggers state transition
    - _Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 7.3_

  - [ ]* 11.3 Write unit tests for SetupService
    - Add tests to `src/backend/tests/unit/test_setup_wizard.py`
    - Test: root admin gets system administrator role, company `is_active` defaults to True, root admin gets company admin membership, AI mode "mock" skips connectivity check, each AI mode persists correctly, 409 on duplicate admin/company, completion records timestamp and admin ID
    - _Requirements: 3.5, 4.4, 4.5, 5.4, 7.1, 7.2, 8.2, 8.3_

- [ ] 12. Integration tests for full setup flow
  - [ ]* 12.1 Write integration tests for the complete setup wizard flow
    - Create `src/backend/tests/integration/test_setup_flow.py`
    - Test full end-to-end flow: status → admin → company → ai-mode → complete
    - Test audit trail entries created for each setup step
    - Test audit entry for admin creation has no user context (first step)
    - Test setup status survives simulated restart (DB persistence)
    - Test demo data seeding creates expected record types with `is_demo_data=True`
    - Test setup endpoints return 403 after completion
    - _Requirements: 1.4, 2.4, 6.1, 6.4, 7.3, 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Create Setup Wizard User Guide documentation
  - [ ] 14.1 Write the Setup Wizard User Guide
    - Create `docs/setup-wizard-guide.md`
    - Include prerequisites section: required infrastructure (PostgreSQL, Redis, MinIO), environment variables, network connectivity, access credentials
    - Include step-by-step instructions for each phase: first-run detection, root admin creation, company creation, AI mode selection, demo data seeding, setup completion
    - Include troubleshooting section: connectivity failures, validation errors, interrupted setup resumption, 503/403 responses
    - Use consistent terminology matching the requirements glossary
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [ ] 15. Final checkpoint - Ensure all tests pass and documentation is complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 9 universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python with FastAPI, SQLAlchemy async, Pydantic, and pytest + hypothesis
- All commands should be run with `uv run` prefix (e.g., `uv run pytest`, `uv run alembic`)
