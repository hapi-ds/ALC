# Admin Dashboard — User Management Guide

This guide covers the Admin Dashboard User Management feature (Phase 6.1) of AlcoaBase. It provides administrators with tools to manage users, roles, permissions, and company memberships through a comprehensive web interface.

## Overview

The Admin Dashboard extends AlcoaBase's authorization system from simple admin/member roles to a granular Role-Based Access Control (RBAC) model with five specialized roles, permission templates for document types, and full user lifecycle management — all while maintaining ALCOA+ audit compliance.

## Accessing the Admin Dashboard

The Administration section appears in the sidebar for users with `system_admin`, `doc_admin`, or `it_admin` roles. Three pages are available:

- **User Management** (`/admin/users`) — Create, edit, deactivate, and manage user accounts
- **Role Management** (`/admin/roles`) — View roles and their permission matrices
- **Permission Templates** (`/admin/permission-templates`) — Define document-type access rules

## Roles and Permissions

AlcoaBase provisions five default roles per company. Each role grants a specific set of actions on resource types:

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| **system_admin** | Full system access | All actions on all resources |
| **doc_admin** | Document lifecycle management | Create, read, update, approve on documents, workflows, templates, training |
| **it_admin** | IT infrastructure | Read/update system_config, read audit_logs and users |
| **member** | Standard team member | Create, read, update on documents and training; read workflows and templates |
| **viewer** | Read-only access | Read documents, workflows, templates, and training |

### Resource Types

Permissions are evaluated against these resource types: `documents`, `workflows`, `users`, `audit_logs`, `templates`, `training`, `signatures`, `system_config`.

### Actions

Each resource supports: `create`, `read`, `update`, `delete`, `approve`.

## User Management

### Creating a User

1. Navigate to **Administration → User Management**
2. Click **Create User**
3. Fill in the form:
   - **Username** — alphanumeric, dots, hyphens, underscores (3–100 chars)
   - **Email** — must be unique system-wide
   - **Full Name** — display name for audit attribution
   - **Role** — select from the five available roles
4. Provide a **Change Reason** (required for audit trail)
5. On success, a **temporary password** is displayed — communicate it securely to the new user

### Editing a User

1. Click a user row to open the detail panel
2. Click **Edit**
3. Modify full name, email, or role
4. Provide a change reason
5. Role changes take effect immediately — no stale permissions

### Deactivating / Reactivating

- **Deactivate**: Sets `is_active=false`. The user is denied all access regardless of role. You cannot deactivate your own account.
- **Reactivate**: Restores `is_active=true` with the previously assigned role permissions intact.

Both actions require a change reason and are recorded in the audit trail.

### Password Reset

1. Open the user detail panel
2. Click **Reset Password**
3. Provide a change reason
4. A new temporary password is generated and displayed
5. All existing refresh tokens for the user are invalidated

The password value is never logged — only the reset event is recorded.

### User Search and Filtering

- **Search**: Case-insensitive substring match across username, email, and full name
- **Sort**: Click column headers to sort by full name, username, role, status, or creation date
- **Pagination**: Configurable page size (10, 20, 50, 100)
- **Active filter**: Filter by active/inactive status

### Change History

Each user's detail panel includes a timeline of all modifications: field changes (old → new values), timestamps, acting user, and change reasons. Powered by SQLAlchemy-Continuum automatic versioning.

## Role Management

Navigate to **Administration → Role Management** to view all roles for your company.

- Click a role to see its full **permission matrix** (resource × action grid with checkmarks)
- System-defined roles are marked with a "System" badge and cannot be edited
- Each role shows the count of users currently assigned to it

## Permission Templates

Permission templates define document-type-specific access rules that layer on top of base role permissions using a **"most restrictive wins"** policy.

### How Templates Work

When a document has an associated permission template:
1. The user's base role permissions are checked first
2. The template's role-action mapping is checked second
3. Access is granted **only if both** the base role AND the template allow the action

This means templates can restrict access below what the base role would normally allow, but they cannot expand it.

### Managing Templates

1. Navigate to **Administration → Permission Templates**
2. Click **Create Template** to define a new template:
   - **Name** — unique within your company
   - **Document Type** — the type of documents this template governs (e.g., SOP, Protocol)
   - **Role Permissions** — check which actions (read, write, approve) each role can perform
   - **Change Reason** — required for audit trail
3. Edit existing templates by clicking the pencil icon
4. Delete templates by clicking the trash icon (disabled if active documents use the template)

### Default Templates

Two templates are seeded per company:
- **Internal SOP** — members can read/write, doc_admins can approve
- **External Supplier File** — restricted access, only doc_admins and system_admins can approve

## Company Memberships

Users can belong to multiple companies with different roles in each. The RBAC engine evaluates permissions scoped to the company identified by the `X-Company-Id` header.

### Assigning Memberships

System administrators can assign users to additional companies via the API:
```
POST /api/admin/memberships
```

### Revoking Memberships

Memberships are soft-deleted (revoked_at timestamp set) rather than hard-deleted, preserving the audit trail. Revoked memberships remain visible in the user's history.

## API Endpoints

All admin endpoints are under `/api/admin/` and require appropriate RBAC permissions. Mutation endpoints require the `X-Change-Reason` header.

| Endpoint | Method | Permission | Description |
|----------|--------|------------|-------------|
| `/api/admin/users` | GET | `users:read` | List users (paginated, searchable) |
| `/api/admin/users` | POST | `users:create` | Create user |
| `/api/admin/users/{id}` | GET | `users:read` | User detail with memberships |
| `/api/admin/users/{id}` | PATCH | `users:update` | Update profile/role |
| `/api/admin/users/{id}/deactivate` | POST | `users:update` | Deactivate user |
| `/api/admin/users/{id}/reactivate` | POST | `users:update` | Reactivate user |
| `/api/admin/users/{id}/reset-password` | POST | `users:update` | Reset password |
| `/api/admin/users/{id}/history` | GET | `audit_logs:read` | Change history |
| `/api/admin/roles` | GET | `users:read` | List roles with user counts |
| `/api/admin/roles/{id}` | GET | `users:read` | Role detail with permission matrix |
| `/api/admin/permission-templates` | GET | `templates:read` | List templates |
| `/api/admin/permission-templates` | POST | `templates:create` | Create template |
| `/api/admin/permission-templates/{id}` | GET | `templates:read` | Template detail |
| `/api/admin/permission-templates/{id}` | PATCH | `templates:update` | Update template |
| `/api/admin/permission-templates/{id}` | DELETE | `templates:delete` | Delete template |
| `/api/admin/memberships/user/{id}` | GET | `users:read` | List memberships for user |
| `/api/admin/memberships` | POST | `users:create` | Assign membership |
| `/api/admin/memberships/{id}` | DELETE | `users:delete` | Revoke membership |

## Integration with Existing Features

### Workflow Execution

Workflow transitions now enforce RBAC:
- **Approval transitions** (in `signature_required_transitions`) require `workflows:approve`
- **Document edit transitions** require `documents:update`
- Denied transitions return HTTP 403 with a descriptive error message

### Document Access

Documents governed by permission templates are filtered from search results and listing views when the user's role lacks read access. The `check_document_access` method applies the "most restrictive wins" policy for individual document access checks.

## Audit Compliance

All user management operations comply with ALCOA+ principles:
- Every mutation is versioned via SQLAlchemy-Continuum
- The `X-Change-Reason` header is required and stored with each audit record
- Password values are never logged
- Deactivation/reactivation events are fully traceable
- Membership changes (assign/revoke) are recorded with timestamps and reasons
