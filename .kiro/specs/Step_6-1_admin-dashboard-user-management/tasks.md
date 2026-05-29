# Implementation Plan: Admin Dashboard — User Management (Phase 6.1)

## Overview

This plan implements Phase 6.1 — Admin Dashboard User Management for AlcoaBase. The implementation follows a bottom-up approach: database models and Alembic migration first, then core services (RBACService, UserManagementService, PasswordResetService, PermissionTemplateService), the RBAC dependency, API routers, and finally the frontend (types, Zustand store, pages, components). Each task builds incrementally on previous work, ensuring no orphaned code.

## Tasks

- [ ] 1. Database models, schemas, and migration
  - [ ] 1.1 Extend Role model and create PermissionTemplate model
    - Modify `src/backend/src/alcoabase/models/user.py` to extend the existing `Role` model with `company_id` (FK to companies, nullable), `is_system` (bool, default False), `description` (String 500, nullable), unique constraint on (name, company_id), index on company_id
    - Create file `src/backend/src/alcoabase/models/permission_template.py` with `PermissionTemplate` model: id, name (String 200), description (Text, nullable), document_type (String 100), role_permissions (JSON), company_id (FK), is_default (bool), created_by (FK to users), created_at; unique constraint on (name, company_id), composite index on (company_id, document_type)
    - Extend `CompanyMembership` in `src/backend/src/alcoabase/models/company.py`: add `role_id` (FK to roles, nullable), `revoked_at` (DateTime, nullable), composite index on (company_id, role_id)
    - Ensure all mutable models use `AuditMixin` for SQLAlchemy-Continuum versioning
    - _Requirements: 1.1, 1.2, 1.3, 4.1, 11.3, 14.1_

  - [ ] 1.2 Create Pydantic schemas for admin user management
    - Create file `src/backend/src/alcoabase/schemas/admin_users.py`
    - Define request schemas: `UserCreateRequest` (username pattern validation, EmailStr, full_name, role Literal), `UserUpdateRequest` (optional fields), `UserListParams` (search, sort_by, sort_dir, page, page_size, is_active filter)
    - Define response schemas: `UserListItem`, `UserListResponse` (paginated), `UserCreateResponse` (includes temporary_password), `UserDetailResponse` (with memberships), `MembershipInfo`, `PasswordResetResponse`, `UserHistoryEntry`, `UserHistoryResponse`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.6, 7.1, 7.2, 9.3, 14.3_

  - [ ] 1.3 Create Pydantic schemas for roles, templates, and memberships
    - Create file `src/backend/src/alcoabase/schemas/admin_roles.py` with `PermissionEntry`, `RoleWithCount`, `RoleListResponse`, `RoleDetailResponse`
    - Create file `src/backend/src/alcoabase/schemas/admin_permission_templates.py` with `RoleActionMapping`, `PermissionTemplateCreateRequest`, `PermissionTemplateUpdateRequest`, `PermissionTemplateResponse`, `PermissionTemplateListResponse`
    - Create file `src/backend/src/alcoabase/schemas/admin_memberships.py` with `AssignMembershipRequest`, `MembershipDetailResponse`
    - _Requirements: 4.1, 4.2, 10.1, 10.2, 11.1, 11.4_

  - [ ] 1.4 Create Alembic migration for RBAC schema changes
    - Generate migration with `alembic revision --autogenerate -m "add_rbac_permission_templates"`
    - Upgrade: add `company_id`, `is_system`, `description` columns to `roles` table; create `permission_templates` table; add `role_id`, `revoked_at` columns to `company_memberships`; add unique constraints and indexes
    - Data migration: seed five default roles per existing company (system_admin, doc_admin, it_admin, member, viewer) with `is_system=True`; map existing membership `role` strings to `role_id` FK; seed default permission templates ("Internal SOP", "External Supplier File") per company
    - Downgrade: reverse all changes in dependency order
    - _Requirements: 1.2, 4.6_

  - [ ]* 1.5 Write property tests for role permission structure validity
    - **Property 3: Role Permission Structure Validity** — Generate random role records, verify permissions field is valid JSON with keys from RESOURCE_TYPES and values as arrays of valid ACTIONS strings
    - **Validates: Requirements 1.3, 1.4**

  - [ ]* 1.6 Write unit tests for Pydantic schema validation
    - Test field constraints (username pattern, email validation, role Literal, min/max lengths)
    - Test UserCreateRequest, UserUpdateRequest, UserListParams, PermissionTemplateCreateRequest serialization/deserialization
    - Test edge cases: empty strings, boundary lengths, invalid role values
    - _Requirements: 5.1, 6.1, 6.2, 6.3_

- [ ] 2. Core service: RBACService
  - [ ] 2.1 Implement RBACService permission evaluation
    - Create file `src/backend/src/alcoabase/services/rbac.py`
    - Define `DEFAULT_ROLE_PERMISSIONS` constant with all five roles and their resource-action mappings
    - Define `RESOURCE_TYPES` and `ACTIONS` constants
    - Implement `check_permission(user_id, company_id, resource, action, session)`: load user's active membership for company, check `is_active` flag, load role permissions JSON, evaluate resource:action grant, return AccessGranted or AccessDenied result
    - Implement `check_document_access(user_id, company_id, document, action, session)`: evaluate base role permissions AND permission template (if document has one), apply "most restrictive wins" policy
    - Implement `get_role_for_user(user_id, company_id, session)`: load role via CompanyMembership.role_id FK
    - Implement `seed_default_roles(company_id, session)`: create five system roles with predefined permissions for a company
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 13.1, 13.2_

  - [ ]* 2.2 Write property test for permission evaluation correctness
    - **Property 1: Permission Evaluation Correctness** — Generate random (role, resource, action) tuples from valid sets, verify RBAC engine grants access if and only if DEFAULT_ROLE_PERMISSIONS[role][resource] contains the action
    - **Validates: Requirements 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5**

  - [ ]* 2.3 Write property test for company-scoped permission evaluation
    - **Property 4: Company-Scoped Permission Evaluation** — Generate users with memberships in multiple companies with different roles, verify permission evaluation uses only the role from the specified company_id, ignoring roles from other companies
    - **Validates: Requirements 2.5**

  - [ ]* 2.4 Write property test for deactivated user access denial
    - **Property 13: Deactivated User Access Denial** — Generate deactivated users (is_active=False) with any role, verify all (resource, action) pairs are denied regardless of role permissions
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 2.5 Write property test for template-based permission restriction
    - **Property 20: Template-Based Permission Restriction (Most Restrictive Wins)** — Generate role+template combinations with varying action sets, verify access granted only when BOTH base role AND template grant the action
    - **Validates: Requirements 13.1, 13.2, 13.3**

  - [ ]* 2.6 Write unit tests for RBACService
    - Test permission evaluation for all five roles against all resource-action pairs
    - Test deactivated user denial, company-scoped evaluation, template restriction logic
    - Test seed_default_roles creates exactly five roles with correct permissions
    - Test edge cases: missing membership, revoked membership, null role_id
    - _Requirements: 2.1–2.6, 3.1–3.5, 8.2, 13.1–13.3_

- [ ] 3. Core service: UserManagementService
  - [ ] 3.1 Implement UserManagementService
    - Create file `src/backend/src/alcoabase/services/user_management.py`
    - Implement `create_user(payload, company_id, session)`: validate username uniqueness (system-wide), validate email uniqueness (system-wide), generate temporary password, hash with bcrypt, INSERT User record, INSERT CompanyMembership with role_id, return user + temp password
    - Implement `update_user(user_id, payload, company_id, session)`: validate email uniqueness on change, update profile fields, update role via CompanyMembership if role changed
    - Implement `deactivate_user(user_id, acting_user_id, company_id, session)`: prevent self-deactivation (422), set is_active=False
    - Implement `reactivate_user(user_id, company_id, session)`: set is_active=True, restore role permissions
    - Implement `list_users(company_id, params, session)`: paginated query with search (username, email, full_name case-insensitive substring), sorting, active filter
    - Implement `get_user_detail(user_id, company_id, session)`: return user with all memberships
    - Implement `get_user_history(user_id, session)`: query SQLAlchemy-Continuum version tables, reconstruct change diffs
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.4, 8.5, 8.6, 14.1, 14.2, 14.3_

  - [ ]* 3.2 Write property test for username and email uniqueness
    - **Property 10: Username and Email Uniqueness Enforcement** — Generate random creation/update attempts with duplicate usernames or emails, verify rejection with 409 conflict error
    - **Validates: Requirements 6.2, 6.3, 7.3**

  - [ ]* 3.3 Write property test for password hashing invariant
    - **Property 11: Password Hashing Invariant** — Generate random passwords (creation and reset), verify stored values are valid bcrypt hashes and plaintext never appears in database
    - **Validates: Requirements 6.5, 9.2**

  - [ ]* 3.4 Write property test for user list pagination correctness
    - **Property 7: User List Pagination Correctness** — Generate companies with N users and random (page, page_size) params, verify response returns at most page_size users, total equals N, union of all pages equals complete user set
    - **Validates: Requirements 5.1**

  - [ ]* 3.5 Write property test for user search filter correctness
    - **Property 8: User Search Filter Correctness** — Generate users and search query strings, verify user appears in results if and only if query is case-insensitive substring of username, email, or full_name
    - **Validates: Requirements 5.3**

  - [ ]* 3.6 Write property test for user list sorting correctness
    - **Property 9: User List Sorting Correctness** — Generate user lists with random field values, verify returned list is ordered according to specified sort field and direction
    - **Validates: Requirements 5.4**

  - [ ]* 3.7 Write unit tests for UserManagementService
    - Test user creation happy path, duplicate username/email rejection (409)
    - Test user update with role change, email uniqueness on update
    - Test deactivation (self-deactivation prevention), reactivation
    - Test list pagination, search filtering, sorting
    - Test user detail with memberships, history reconstruction
    - _Requirements: 5.1–5.5, 6.1–6.7, 7.1–7.5, 8.1–8.6, 14.1–14.3_

- [ ] 4. Core service: PasswordResetService
  - [ ] 4.1 Implement PasswordResetService
    - Create file `src/backend/src/alcoabase/services/password_reset.py`
    - Implement `reset_password(user_id, session)`: generate secure temporary password (secrets module), hash with bcrypt, update user's stored password, invalidate all existing refresh tokens for the user, return temporary password (plaintext for admin display only)
    - Implement `generate_temporary_password()`: generate 16-char alphanumeric password using `secrets.token_urlsafe`
    - Handle bcrypt encoding errors gracefully, log without exposing internals
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 4.2 Write property test for token invalidation on password reset
    - **Property 15: Token Invalidation on Password Reset** — Generate users with N existing refresh tokens (N >= 0), perform password reset, verify all N tokens are invalidated
    - **Validates: Requirements 9.5**

  - [ ]* 4.3 Write unit tests for PasswordResetService
    - Test password reset generates valid bcrypt hash, invalidates tokens
    - Test temporary password generation (length, character set)
    - Test audit trail recording (password value NOT logged)
    - _Requirements: 9.1–9.5_

- [ ] 5. Core service: PermissionTemplateService
  - [ ] 5.1 Implement PermissionTemplateService
    - Create file `src/backend/src/alcoabase/services/permission_template.py`
    - Implement `create_template(payload, company_id, user_id, session)`: validate name uniqueness within company, persist PermissionTemplate with role_permissions JSON
    - Implement `update_template(template_id, payload, company_id, session)`: validate ownership (company_id match), update fields
    - Implement `delete_template(template_id, company_id, session)`: pre-deletion check for active documents using this template, reject with 409 if count > 0, otherwise delete
    - Implement `list_templates(company_id, session)`: return all templates for company with active_document_count
    - Implement `get_template_detail(template_id, company_id, session)`: return template with active_document_count
    - Implement `seed_default_templates(company_id, user_id, session)`: create "Internal SOP" and "External Supplier File" templates with predefined role-action mappings
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 5.2 Write property test for permission template storage round-trip
    - **Property 5: Permission Template Storage Round-Trip** — Generate valid template creation payloads (name, description, document_type, role_permissions), create and retrieve, verify all fields preserved
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 5.3 Write property test for template deletion guard
    - **Property 6: Template Deletion Guard** — Generate templates with varying active document counts (0 to N), verify deletion fails with error when count > 0, succeeds when count == 0
    - **Validates: Requirements 4.4**

  - [ ]* 5.4 Write unit tests for PermissionTemplateService
    - Test template CRUD operations, name uniqueness within company
    - Test deletion guard (active documents prevent deletion)
    - Test default template seeding ("Internal SOP", "External Supplier File")
    - Test active_document_count computation
    - _Requirements: 4.1–4.6_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. RBAC dependency and membership service
  - [ ] 7.1 Implement require_permission FastAPI dependency
    - Create file `src/backend/src/alcoabase/dependencies/rbac.py`
    - Implement `require_permission(resource, action)` factory: returns a FastAPI dependency that resolves TenantContext, checks user is_active flag, loads role for company, evaluates permissions via RBACService, raises HTTP 403 with descriptive message on denial
    - Chain on top of existing `get_tenant_context` dependency
    - Return TenantContext on success for downstream route handler use
    - _Requirements: 2.6, 8.2, 12.1, 12.2, 12.3_

  - [ ] 7.2 Implement membership management in UserManagementService
    - Add `assign_membership(user_id, company_id, role, session)`: validate no duplicate active membership for (user_id, company_id), create CompanyMembership with role_id
    - Add `revoke_membership(membership_id, company_id, session)`: set revoked_at timestamp (soft delete), do NOT hard delete
    - Add `list_memberships(user_id, session)`: return all memberships (active and revoked) with company names
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 7.3 Write property test for membership uniqueness
    - **Property 17: Membership Uniqueness** — Generate (user_id, company_id) pairs that already have active memberships, verify duplicate creation is rejected with 409 conflict
    - **Validates: Requirements 11.2**

  - [ ]* 7.4 Write property test for membership soft-delete
    - **Property 18: Membership Soft-Delete** — Generate and revoke memberships, verify database record persists with non-null revoked_at, verify record retrievable in history queries
    - **Validates: Requirements 11.3**

  - [ ]* 7.5 Write property test for role change immediate effect
    - **Property 16: Role Change Immediate Effect** — Change user role from role_A to role_B, verify all subsequent permission evaluations use role_B's permissions with no stale cache
    - **Validates: Requirements 7.4**

  - [ ]* 7.6 Write property test for activation/deactivation round-trip
    - **Property 14: Activation/Deactivation Round-Trip** — Generate active users, deactivate then reactivate, verify is_active restored to true and role permissions function identically
    - **Validates: Requirements 8.4**

  - [ ]* 7.7 Write unit tests for RBAC dependency and membership management
    - Test require_permission grants access for authorized roles, denies for unauthorized
    - Test deactivated user gets 403 regardless of role
    - Test membership assignment, duplicate prevention (409), soft revocation
    - Test membership listing includes both active and revoked
    - _Requirements: 2.6, 7.4, 8.2, 11.1–11.5, 12.1–12.3_

- [ ] 8. API routers: admin_users and admin_roles
  - [ ] 8.1 Implement admin_users API router
    - Create file `src/backend/src/alcoabase/api/admin_users.py`
    - Implement GET `/admin/users` → paginated user list with search, sort, filter (requires `users:read`)
    - Implement POST `/admin/users` → create user with temp password (requires `users:create`, X-Change-Reason)
    - Implement GET `/admin/users/{user_id}` → user detail with memberships (requires `users:read`)
    - Implement PATCH `/admin/users/{user_id}` → update profile/role (requires `users:update`, X-Change-Reason)
    - Implement POST `/admin/users/{user_id}/deactivate` → deactivate user (requires `users:update`, X-Change-Reason)
    - Implement POST `/admin/users/{user_id}/reactivate` → reactivate user (requires `users:update`, X-Change-Reason)
    - Implement POST `/admin/users/{user_id}/reset-password` → reset password (requires `users:update`, X-Change-Reason)
    - Implement GET `/admin/users/{user_id}/history` → change history (requires `audit_logs:read`)
    - All endpoints use `Depends(require_permission(...))` and `Depends(get_tenant_context)`
    - _Requirements: 5.1–5.5, 6.1–6.7, 7.1–7.5, 8.1–8.6, 9.1–9.5, 14.1–14.3_

  - [ ] 8.2 Implement admin_roles API router
    - Create file `src/backend/src/alcoabase/api/admin_roles.py`
    - Implement GET `/admin/roles` → list all roles with user counts (requires `users:read`)
    - Implement GET `/admin/roles/{role_id}` → role detail with full permission matrix (requires `users:read`)
    - _Requirements: 1.4, 10.1, 10.2, 10.3, 10.4_

- [ ] 9. API routers: admin_permission_templates and admin_memberships
  - [ ] 9.1 Implement admin_permission_templates API router
    - Create file `src/backend/src/alcoabase/api/admin_permission_templates.py`
    - Implement GET `/admin/permission-templates` → list templates (requires `templates:read`)
    - Implement POST `/admin/permission-templates` → create template (requires `templates:create`, X-Change-Reason)
    - Implement GET `/admin/permission-templates/{template_id}` → template detail (requires `templates:read`)
    - Implement PATCH `/admin/permission-templates/{template_id}` → update template (requires `templates:update`, X-Change-Reason)
    - Implement DELETE `/admin/permission-templates/{template_id}` → delete template with guard (requires `templates:delete`, X-Change-Reason)
    - _Requirements: 4.1–4.5_

  - [ ] 9.2 Implement admin_memberships API router
    - Create file `src/backend/src/alcoabase/api/admin_memberships.py`
    - Implement GET `/admin/memberships/user/{user_id}` → list memberships for user (requires `users:read`)
    - Implement POST `/admin/memberships` → assign user to company (requires `users:create`, X-Change-Reason)
    - Implement DELETE `/admin/memberships/{membership_id}` → revoke membership soft-delete (requires `users:delete`, X-Change-Reason)
    - _Requirements: 11.1–11.5_

  - [ ] 9.3 Register admin routers in central router
    - Add imports and `include_router` calls in `src/backend/src/alcoabase/api/router.py` for all four admin routers with appropriate prefixes
    - _Requirements: 2.6_

- [ ] 10. Integration with existing services
  - [ ] 10.1 Integrate RBAC with Workflow Execution
    - Modify workflow execution endpoint(s) in `src/backend/src/alcoabase/api/workflows.py` to add `Depends(require_permission("workflows", "approve"))` for approval transitions
    - Add `Depends(require_permission("documents", "update"))` for document edit transitions
    - Ensure HTTP 403 with descriptive error message on permission denial
    - _Requirements: 12.1, 12.2, 12.3_

  - [ ] 10.2 Integrate RBAC with Document Access
    - Extend `DocumentService` to call `RBACService.check_document_access()` for template-aware access checks
    - Add WHERE clause to document list/search queries excluding documents where user's role lacks "read" in applicable permission template
    - Apply "most restrictive wins" policy: access granted only if BOTH base role AND template grant the action
    - _Requirements: 13.1, 13.2, 13.3_

  - [ ]* 10.3 Write property test for RBAC enforcement on workflow actions
    - **Property 19: RBAC Enforcement on Workflow Actions** — Generate users with various roles attempting workflow approval, verify access granted if and only if role includes "approve" on "workflows", denied returns HTTP 403
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [ ]* 10.4 Write property test for audit trail completeness
    - **Property 12: Audit Trail Completeness** — Generate user management mutations (create, update, deactivate, reactivate, reset, role change, membership change), verify audit record created with acting user ID, timestamp, and X-Change-Reason
    - **Validates: Requirements 6.7, 7.5, 8.5, 9.4, 11.5, 14.2**

  - [ ]* 10.5 Write property test for company role provisioning
    - **Property 2: Company Role Provisioning** — Generate new companies, verify exactly five roles provisioned (system_admin, doc_admin, it_admin, member, viewer) with permissions matching DEFAULT_ROLE_PERMISSIONS
    - **Validates: Requirements 1.2**

  - [ ]* 10.6 Write integration tests for admin API endpoints
    - Test full user lifecycle: create → assign role → verify access → deactivate → verify denial → reactivate
    - Test all admin_users endpoints with database (HTTP status codes, pagination, search, sort)
    - Test admin_roles endpoints (list with counts, detail with permission matrix)
    - Test admin_permission_templates endpoints (CRUD, deletion guard)
    - Test admin_memberships endpoints (assign, revoke soft-delete, list)
    - Test X-Change-Reason enforcement on all mutation endpoints
    - Test error responses (403, 404, 409, 422)
    - Test SQLAlchemy-Continuum version record creation
    - Test multi-company permission isolation end-to-end
    - _Requirements: 1.1–14.3 (all requirements)_

- [ ] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Frontend: Types and Zustand store
  - [ ] 12.1 Create TypeScript types for admin user management
    - Create file `src/frontend/src/types/admin.ts`
    - Define interfaces: `UserListItem`, `UserDetail`, `UserCreatePayload`, `UserUpdatePayload`, `CreateUserResponse`, `UserHistoryEntry`, `MembershipInfo`
    - Define interfaces: `RoleWithCount`, `RoleDetail`, `PermissionEntry`
    - Define interfaces: `PermissionTemplate`, `PermissionTemplateDetail`, `CreateTemplatePayload`, `UpdateTemplatePayload`, `RoleActionMapping`
    - Define interfaces: `AssignMembershipPayload`, `MembershipDetail`
    - Define filter/pagination types: `UserListParams`, `PaginatedResponse`
    - _Requirements: 5.2, 10.1, 10.2_

  - [ ] 12.2 Create Zustand store for admin management
    - Create file `src/frontend/src/stores/adminStore.ts`
    - Implement state: users, totalUsers, currentUser, userHistory, roles, currentRole, permissionTemplates, currentTemplate, isLoading, error, searchQuery, sortField, sortDirection, page, pageSize
    - Implement user actions: fetchUsers, createUser (with X-Change-Reason), updateUser (with X-Change-Reason), deactivateUser (with X-Change-Reason), reactivateUser (with X-Change-Reason), resetPassword (with X-Change-Reason), fetchUserDetail, fetchUserHistory
    - Implement role actions: fetchRoles, fetchRoleDetail
    - Implement template actions: fetchPermissionTemplates, createPermissionTemplate (with X-Change-Reason), updatePermissionTemplate (with X-Change-Reason), deletePermissionTemplate (with X-Change-Reason)
    - Implement membership actions: assignMembership (with X-Change-Reason), revokeMembership (with X-Change-Reason)
    - Use apiClient with appropriate headers on all mutations
    - _Requirements: 5.1–5.5, 6.6, 7.1, 8.3, 9.3, 10.1, 10.3_

  - [ ]* 12.3 Write unit tests for adminStore
    - Test state transitions for all actions, error handling, loading states
    - Test X-Change-Reason header inclusion on mutations
    - Test pagination state management, search/sort state updates
    - Mock apiClient responses
    - _Requirements: 5.1, 6.6, 9.3_

- [ ] 13. Frontend: User Management pages and components
  - [ ] 13.1 Implement UserManagementPage
    - Create file `src/frontend/src/pages/UserManagementPage.tsx`
    - Display paginated table of users: full name, username, email, role (badge), active status (visual indicator), creation date
    - Implement search input filtering by username, email, or full name
    - Implement column sorting (full_name, username, role, is_active, created_at)
    - Implement pagination controls with page size selector
    - Add "Create User" button opening UserCreateDialog
    - Add row click opening UserDetailPanel
    - Implement loading skeletons and empty states
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 13.2 Implement UserCreateDialog
    - Create file `src/frontend/src/components/admin/UserCreateDialog.tsx`
    - Form fields: username (pattern validation), email (email validation), full_name, role (dropdown with 5 options)
    - Use react-hook-form for validation
    - On submit: call createUser action with X-Change-Reason prompt
    - On success: display confirmation with temporary password for admin to communicate
    - Handle validation errors (409 duplicate username/email)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

  - [ ] 13.3 Implement UserEditDialog
    - Create file `src/frontend/src/components/admin/UserEditDialog.tsx`
    - Pre-populate form with current values (full_name, email, role)
    - Use react-hook-form for validation
    - On submit: call updateUser action with X-Change-Reason prompt
    - Handle validation errors (409 duplicate email)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 13.4 Implement UserDetailPanel and UserHistoryTimeline
    - Create file `src/frontend/src/components/admin/UserDetailPanel.tsx`
    - Display user details, all memberships (active and revoked with timestamps)
    - Action buttons: Edit, Deactivate/Reactivate, Reset Password
    - Prevent self-deactivation (disable button for current user)
    - Create file `src/frontend/src/components/admin/UserHistoryTimeline.tsx`
    - Display timeline of changes: version, timestamp, changed_by, change_reason, field diffs
    - _Requirements: 7.1, 8.1, 8.3, 8.4, 8.6, 9.3, 11.4, 14.3_

  - [ ] 13.5 Implement RoleManagementPage and PermissionMatrixView
    - Create file `src/frontend/src/pages/RoleManagementPage.tsx`
    - Display all roles with names, descriptions, user counts
    - Visually distinguish system-defined roles (non-editable) from custom roles
    - Create file `src/frontend/src/components/admin/PermissionMatrixView.tsx`
    - Grid showing resource types (rows) × actions (columns) with checkmarks for granted permissions
    - On role selection: display full permission matrix
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ] 13.6 Implement PermissionTemplateManagementPage and PermissionTemplateDialog
    - Create file `src/frontend/src/pages/PermissionTemplateManagementPage.tsx`
    - Display template list with name, document_type, active_document_count, is_default badge
    - Add "Create Template" button, edit/delete actions per row
    - Disable delete for templates with active documents (show tooltip explaining why)
    - Create file `src/frontend/src/components/admin/PermissionTemplateDialog.tsx`
    - Form: name, description, document_type, role_permissions (multi-select per role for read/write/approve)
    - Use react-hook-form for validation
    - On submit: call createPermissionTemplate or updatePermissionTemplate with X-Change-Reason
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 13.7 Add admin routes and navigation
    - Add `/admin/users` route for UserManagementPage
    - Add `/admin/roles` route for RoleManagementPage
    - Add `/admin/permission-templates` route for PermissionTemplateManagementPage
    - Add navigation links in main sidebar under "Administration" section
    - Conditionally show admin nav items based on user's role permissions
    - _Requirements: 5.1, 10.1_

  - [ ]* 13.8 Write frontend component tests
    - Test UserManagementPage rendering, pagination, search, sort, empty states, loading skeletons
    - Test UserCreateDialog form validation, submit, success display with temp password, error handling
    - Test UserEditDialog pre-population, submit, error handling
    - Test UserDetailPanel rendering, action buttons, self-deactivation prevention
    - Test UserHistoryTimeline rendering, timeline entries
    - Test RoleManagementPage rendering, role selection, system role distinction
    - Test PermissionMatrixView grid rendering, checkmark display
    - Test PermissionTemplateManagementPage rendering, delete guard UI
    - Test PermissionTemplateDialog form validation, submit
    - Use fast-check for property-based testing of permission matrix display logic
    - _Requirements: 5.1–5.5, 6.1–6.6, 7.1–7.4, 8.1–8.6, 9.3, 10.1–10.4, 4.1–4.5_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (20 properties)
- Unit tests validate specific examples and edge cases
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + Testing Library + fast-check
- All backend services use async SQLAlchemy sessions (asyncpg)
- The RBAC dependency chains on top of existing TenantContext — no modification to existing auth flow
- AuditMiddleware automatically enforces X-Change-Reason on all `/api/admin/*` mutations (not in exempt paths)
- SQLAlchemy-Continuum versioning is enabled via AuditMixin on all mutable models
- Soft operations only: deactivation sets is_active=false, membership revocation sets revoked_at (no hard deletes for GxP compliance)
- Default role seeding happens in the Alembic data migration and also in RBACService.seed_default_roles for new companies created after migration

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "1.5", "1.6"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "3.1", "4.1", "5.1"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "4.2", "4.3", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "7.5", "7.6", "7.7"] },
    { "id": 7, "tasks": ["8.1", "8.2", "9.1", "9.2"] },
    { "id": 8, "tasks": ["9.3", "10.1", "10.2"] },
    { "id": 9, "tasks": ["10.3", "10.4", "10.5", "10.6"] },
    { "id": 10, "tasks": ["12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3"] },
    { "id": 12, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6"] },
    { "id": 13, "tasks": ["13.7", "13.8"] }
  ]
}
```
