# Implementation Plan: Multi-Tenancy

## Overview

This plan implements shared-schema multi-tenancy for AlcoaBase by introducing a `companies` table as the tenant entity, a `company_memberships` table for user-company associations, and a `company_agent_activations` table for per-company agent configuration. All tenant-scoped tables receive a `company_id` foreign key, and a FastAPI dependency (`get_tenant_context`) resolves the active company from the authenticated user and an optional `X-Company-Id` header. Existing service queries are augmented with a mandatory `company_id` filter.

## Tasks

- [x] 1. Create Company, CompanyMembership, and CompanyAgentActivation SQLAlchemy models
  - [x] 1.1 Create `src/backend/src/alcoabase/models/company.py` with Company, CompanyMembership, and CompanyAgentActivation models
    - Define Company model with id, slug (unique, indexed), display_name, regulatory_framework, audit_config (JSON), is_active, created_at
    - Define CompanyMembership model with id, user_id (FK), company_id (FK), role, created_at, revoked_at (nullable)
    - Add UniqueConstraint on (user_id, company_id) for CompanyMembership
    - Define CompanyAgentActivation model with id, company_id (FK), agent_definition_id (FK), config_overrides (JSON), is_active, activated_at
    - Add UniqueConstraint on (company_id, agent_definition_id) for CompanyAgentActivation
    - Add relationships (Company.memberships, CompanyMembership.user, CompanyMembership.company, CompanyAgentActivation.company, CompanyAgentActivation.agent_definition)
    - Register models in `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 12.1, 12.2, 1.2_

  - [x] 1.2 Write property tests for Company creation (Properties 1, 2, 3)
    - **Property 1: Company creation produces a valid record**
    - **Property 2: Duplicate slug rejection**
    - **Property 3: Missing required fields rejection**
    - Create `src/backend/tests/properties/test_company_crud.py`
    - Use Hypothesis strategies for valid slugs (`^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$`), display names, and regulatory frameworks
    - **Validates: Requirements 1.1, 1.2, 1.4, 1.5**

- [x] 2. Create Alembic migration for multi-tenancy schema changes
  - [x] 2.1 Generate and implement the Alembic migration
    - Create new tables: `companies`, `company_memberships`, `company_agent_activations`
    - Insert a default company with slug `"default"` for backfill
    - Add nullable `company_id` column to: documents, templates, workflow_definitions, training_records, training_tasks, virtual_folders, reports, signature_records
    - Add nullable `company_id` column to agent_definitions (remains nullable for global agents)
    - Backfill all existing records with the default company's ID
    - Alter `company_id` to NOT NULL on all tables except agent_definitions
    - Add composite indexes: (company_id, document_uuid) on documents, (company_id, document_uuid) on templates, (company_id, document_tag) on workflow_definitions, (company_id, assigned_user_id) on training_tasks, (company_id, created_at) on documents
    - Add foreign key constraints to companies.id
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 2.2 Write property test for migration backfill completeness (Property 19)
    - **Property 19: Migration backfill completeness**
    - Create `src/backend/tests/properties/test_migration.py`
    - Verify all pre-existing records have non-null company_id equal to default company's ID after migration
    - **Validates: Requirements 12.6**

- [x] 3. Add `company_id` foreign key to existing models
  - [x] 3.1 Modify existing SQLAlchemy models to include `company_id`
    - Add `company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))` to Document, Template, WorkflowDefinition, TrainingRecord, TrainingTask, VirtualFolder, Report, SignatureRecord models
    - Add `company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)` to AgentDefinition model
    - Add relationship back-references where appropriate
    - _Requirements: 12.3, 12.4_

- [x] 4. Checkpoint - Ensure models and migration are correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create Pydantic schemas for Company, Membership, and Agent Activation
  - [x] 5.1 Create `src/backend/src/alcoabase/schemas/company.py` with request/response schemas
    - CompanyCreate: slug (regex validated), display_name, regulatory_framework (Literal), audit_config
    - CompanyUpdate: display_name (optional), regulatory_framework (optional), audit_config (optional)
    - CompanyResponse: id, slug, display_name, regulatory_framework, audit_config, is_active, created_at (from_attributes=True)
    - MembershipCreate: user_id, role (Literal["admin", "member", "viewer"])
    - MembershipUpdate: role (Literal["admin", "member", "viewer"])
    - MembershipResponse: id, user_id, company_id, role, created_at, revoked_at (from_attributes=True)
    - AgentActivationCreate: config_overrides (optional dict)
    - AgentActivationResponse: id, company_id, agent_definition_id, config_overrides, is_active, activated_at (from_attributes=True)
    - _Requirements: 1.2, 1.5, 2.1_

- [x] 6. Implement Tenant Context dependency
  - [x] 6.1 Create `src/backend/src/alcoabase/dependencies/tenant.py` with TenantContext dataclass and `get_tenant_context` dependency
    - Define frozen TenantContext dataclass with company_id, company_slug, user_id, membership_role
    - Implement resolution logic: query active memberships for user → auto-select if single → require X-Company-Id header if multiple → validate membership → validate company is active
    - Raise HTTPException 400 if multi-company user without X-Company-Id
    - Raise HTTPException 403 if user not a member of specified company or company is inactive
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 13.2_

  - [x] 6.2 Write property tests for tenant context resolution (Properties 5, 14, 15)
    - **Property 5: Tenant context requires explicit selection for multi-company users**
    - **Property 14: Unauthorized company access returns forbidden**
    - **Property 15: Company deactivation blocks access**
    - Create `src/backend/tests/properties/test_membership.py`
    - Use Hypothesis to generate users with varying numbers of memberships
    - **Validates: Requirements 2.3, 9.2, 9.3, 9.4, 9.5, 13.1, 13.2, 13.4**

- [x] 7. Implement Company CRUD API endpoints
  - [x] 7.1 Create `src/backend/src/alcoabase/api/companies.py` with company management routes
    - POST `/api/companies` — Create a new company (System Admin only)
    - GET `/api/companies` — List all companies (System Admin only)
    - GET `/api/companies/{slug}` — Get company details (System Admin or Company Member)
    - PATCH `/api/companies/{slug}` — Update company config (System Admin or Company Admin)
    - POST `/api/companies/{slug}/deactivate` — Deactivate company (System Admin only)
    - POST `/api/companies/{slug}/reactivate` — Reactivate company (System Admin only)
    - Register router in `src/backend/src/alcoabase/api/router.py`
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 8.1, 8.2, 8.3, 13.1, 13.4_

  - [x] 7.2 Write unit tests for Company CRUD endpoints
    - Test successful creation, duplicate slug conflict (409), missing fields (422)
    - Test deactivation and reactivation flows
    - Test authorization (non-admin rejected)
    - _Requirements: 1.1, 1.4, 1.5, 13.1, 13.4_

- [x] 8. Implement Membership Management API endpoints
  - [x] 8.1 Create `src/backend/src/alcoabase/api/memberships.py` with membership routes
    - POST `/api/companies/{slug}/members` — Add user to company (System Admin)
    - GET `/api/companies/{slug}/members` — List company members (Company Admin)
    - PATCH `/api/companies/{slug}/members/{user_id}` — Update member role (System Admin or Company Admin)
    - DELETE `/api/companies/{slug}/members/{user_id}` — Revoke membership (System Admin or Company Admin)
    - Register router in `src/backend/src/alcoabase/api/router.py`
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x] 8.2 Write property tests for membership (Properties 4, 6)
    - **Property 4: Membership creation and multi-membership support**
    - **Property 6: Membership revocation prevents access**
    - Add to `src/backend/tests/properties/test_membership.py`
    - **Validates: Requirements 2.1, 2.2, 2.5**

- [x] 9. Implement Agent Activation API endpoints
  - [x] 9.1 Create `src/backend/src/alcoabase/api/agent_activations.py` with agent activation routes
    - POST `/api/companies/{slug}/agents/{agent_id}/activate` — Activate global agent for company (Company Admin)
    - DELETE `/api/companies/{slug}/agents/{agent_id}/deactivate` — Deactivate agent for company (Company Admin)
    - GET `/api/companies/{slug}/agents` — List activated agents (Company Member)
    - Register router in `src/backend/src/alcoabase/api/router.py`
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 9.2 Write property tests for agent activation (Properties 17, 18)
    - **Property 17: Global agent modification rejection**
    - **Property 18: Agent activation scoping**
    - Create `src/backend/tests/properties/test_agents.py`
    - **Validates: Requirements 10.2, 10.3, 10.5**

- [x] 10. Checkpoint - Ensure all new endpoints work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Modify existing endpoints for tenant scoping
  - [x] 11.1 Add TenantContext dependency to Document endpoints
    - Inject `get_tenant_context` into all document routes (create, list, get, update, delete)
    - Pass `company_id` to service layer queries
    - Filter all document queries by `Document.company_id == tenant.company_id`
    - Auto-set `company_id` on document creation
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 11.2 Add TenantContext dependency to Template and Report endpoints
    - Inject `get_tenant_context` into all template and report routes
    - Pass `company_id` to service layer queries
    - Validate cross-tenant template reference on report creation (reject with 403 if template belongs to different company)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 11.3 Add TenantContext dependency to Workflow endpoints
    - Inject `get_tenant_context` into all workflow routes
    - Filter workflow evaluation to use only tenant's workflow definitions
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 11.4 Add TenantContext dependency to Training endpoints
    - Inject `get_tenant_context` into all training routes
    - Scope training compliance evaluation to tenant's records only
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 11.5 Add TenantContext dependency to Virtual Folder endpoints
    - Inject `get_tenant_context` into all virtual folder routes
    - Ensure tag filter matches only documents within the same company
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 11.6 Add TenantContext dependency to Signature and Audit endpoints
    - Inject `get_tenant_context` into signature record routes
    - Scope audit trail queries to tenant context (except System Admin platform-level view)
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 12. Checkpoint - Ensure tenant scoping is applied to all existing endpoints
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Write property-based tests for tenant isolation
  - [x] 13.1 Write property test for tenant-scoped resource isolation (Property 7)
    - **Property 7: Tenant-scoped resource isolation**
    - Create `src/backend/tests/properties/test_tenant_isolation.py`
    - Generate resources across N companies, verify querying from company X returns only company X's resources
    - **Validates: Requirements 3.2, 3.3, 4.2, 4.4, 5.3, 6.2, 7.2**

  - [x] 13.2 Write property test for auto-scoping on resource creation (Property 8)
    - **Property 8: Auto-scoping on resource creation**
    - Add to `src/backend/tests/properties/test_tenant_isolation.py`
    - Verify created resources always have company_id matching active tenant context
    - **Validates: Requirements 3.1, 4.1, 4.3, 5.1, 6.1, 7.1**

  - [x] 13.3 Write property test for cross-tenant access (Property 9)
    - **Property 9: Cross-tenant access returns forbidden**
    - Add to `src/backend/tests/properties/test_tenant_isolation.py`
    - Verify accessing resource from company A with tenant context B returns 403
    - **Validates: Requirements 3.4, 4.5, 5.4, 6.4**

  - [x] 13.4 Write property test for cross-tenant template reference (Property 10)
    - **Property 10: Cross-tenant template reference rejection**
    - Add to `src/backend/tests/properties/test_tenant_isolation.py`
    - Verify creating a report referencing a template from another company returns 403
    - **Validates: Requirements 4.5**

  - [x] 13.5 Write property test for virtual folder tag filter (Property 11)
    - **Property 11: Virtual folder tag filter respects tenant boundary**
    - Add to `src/backend/tests/properties/test_tenant_isolation.py`
    - Verify tag filter returns only documents within the same company
    - **Validates: Requirements 7.3**

  - [x] 13.6 Write property test for workflow evaluation scoping (Property 12)
    - **Property 12: Workflow evaluation uses only tenant's workflows**
    - Add to `src/backend/tests/properties/test_tenant_isolation.py`
    - Verify workflow transitions consider only company X's workflow definitions
    - **Validates: Requirements 5.2**

  - [x] 13.7 Write property test for training compliance scoping (Property 13)
    - **Property 13: Training compliance evaluation is tenant-scoped**
    - Add to `src/backend/tests/properties/test_tenant_isolation.py`
    - Verify training gate uses only training records within the same company
    - **Validates: Requirements 6.3**

  - [x] 13.8 Write property test for company deactivation audit retention (Property 16)
    - **Property 16: Audit trail entries retain company_id after deactivation**
    - Create `src/backend/tests/properties/test_company_lifecycle.py`
    - Verify audit entries remain unchanged after company deactivation
    - **Validates: Requirements 13.3**

- [x] 14. Write integration tests for end-to-end tenant flows
  - [x] 14.1 Write integration tests for full request lifecycle
    - Create `src/backend/tests/integration/test_multi_tenancy.py`
    - Test: authenticate → resolve tenant → create resource → query resource (only own tenant's data returned)
    - Test: two companies with overlapping data, verify complete isolation
    - Test: migration backfill verification (seed data → run migration → verify company_id populated)
    - Test: company deactivation blocks access, reactivation restores access
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 9.1, 9.2, 13.1, 13.2, 13.4_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (19 total)
- Unit tests validate specific examples and edge cases
- Run tests with: `uv run pytest --tb=short -q`
- The design uses Python (FastAPI + SQLAlchemy 2.0 async + PostgreSQL), so all code is in Python
- Hypothesis is already in dev dependencies for property-based testing
