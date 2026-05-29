# Requirements Document

## Introduction

This document specifies the requirements for the Admin Dashboard — User Management feature (Phase 6.1) of AlcoaBase. The feature extends the existing role system beyond "admin"/"member" to introduce granular Role-Based Access Control (RBAC) with specialized roles (Document Administrator, IT Administrator, Viewer), permission models, permission templates for document types, and a comprehensive user management UI for administrators. All operations comply with ALCOA+ data integrity principles and 21 CFR Part 11 traceability requirements.

## Glossary

- **Admin_Dashboard**: The administrative interface within AlcoaBase that provides user, role, and permission management capabilities to authorized administrators.
- **RBAC_Engine**: The backend authorization service that evaluates user permissions based on assigned roles and permission templates before granting access to resources.
- **User_Management_Service**: The backend service responsible for CRUD operations on user accounts, including creation, modification, deactivation, and password reset.
- **Role**: A named collection of permissions that can be assigned to users within a company context. Roles include system_admin, doc_admin, it_admin, member, and viewer.
- **Permission**: A discrete authorization grant specifying an action (create, read, update, delete, approve) on a resource type (documents, workflows, users, audit_logs, templates).
- **Permission_Template**: A reusable, named set of permissions associated with a document type that defines default access rules for different roles interacting with that document type.
- **Company_Membership**: The association between a User and a Company, including the assigned role within that company context.
- **Doc_Admin**: A specialized role responsible for defining BPMN workflows and managing document lifecycle permissions within a company.
- **IT_Admin**: A specialized role responsible for system health monitoring and infrastructure configuration within a company.
- **Password_Reset_Service**: The backend service that generates secure, time-limited password reset tokens and processes password changes with audit logging.

## Requirements

### Requirement 1: Extended Role Definitions

**User Story:** As a system administrator, I want predefined roles with specific permission sets, so that I can assign appropriate access levels to users based on their organizational responsibilities.

#### Acceptance Criteria

1. THE RBAC_Engine SHALL support the following roles: system_admin, doc_admin, it_admin, member, and viewer.
2. WHEN a new company is created, THE RBAC_Engine SHALL provision the five default roles with their predefined permission sets for that company.
3. THE RBAC_Engine SHALL store role definitions as structured JSON permission objects containing resource-action pairs.
4. WHEN a role is queried, THE RBAC_Engine SHALL return the role name, description, and the complete list of granted permissions.

### Requirement 2: Permission Model and Evaluation

**User Story:** As a system administrator, I want a granular permission model that controls access to specific actions on specific resources, so that I can enforce the principle of least privilege.

#### Acceptance Criteria

1. THE RBAC_Engine SHALL evaluate permissions based on the combination of user role, target resource type, and requested action.
2. THE RBAC_Engine SHALL support the following resource types: documents, workflows, users, audit_logs, templates, training, signatures, and system_config.
3. THE RBAC_Engine SHALL support the following actions per resource: create, read, update, delete, and approve.
4. WHEN a user requests access to a resource, THE RBAC_Engine SHALL deny access unless the user holds a role that explicitly grants the requested action on the target resource type.
5. WHEN a user holds multiple roles across different companies, THE RBAC_Engine SHALL evaluate permissions scoped to the company identified by the X-Company-Id header.
6. THE RBAC_Engine SHALL enforce permission checks as a FastAPI dependency that executes before route handler logic.

### Requirement 3: Role-Specific Default Permissions

**User Story:** As a system administrator, I want each role to have well-defined default permissions, so that role assignment immediately grants appropriate access without manual permission configuration.

#### Acceptance Criteria

1. THE RBAC_Engine SHALL grant system_admin full access (create, read, update, delete, approve) to all resource types.
2. THE RBAC_Engine SHALL grant doc_admin create, read, update, and approve access to documents, workflows, templates, and training resources, and read access to audit_logs.
3. THE RBAC_Engine SHALL grant it_admin read and update access to system_config, read access to audit_logs and users, and no access to document lifecycle operations.
4. THE RBAC_Engine SHALL grant member create, read, and update access to documents and training, and read access to workflows and templates.
5. THE RBAC_Engine SHALL grant viewer read-only access to documents, workflows, templates, and training resources.

### Requirement 4: Permission Templates for Document Types

**User Story:** As a document administrator, I want to define reusable permission templates for different document types, so that access rules are consistently applied when new documents of that type are created.

#### Acceptance Criteria

1. WHEN a Doc_Admin creates a Permission_Template, THE Admin_Dashboard SHALL store the template with a name, description, associated document type, and a mapping of roles to permitted actions.
2. THE Admin_Dashboard SHALL allow a Doc_Admin to define which roles can read, write, and approve documents governed by a specific Permission_Template.
3. WHEN a Permission_Template is updated, THE RBAC_Engine SHALL apply the updated permissions to all future access checks for documents of that type.
4. THE Admin_Dashboard SHALL prevent deletion of a Permission_Template that is currently assigned to one or more active documents.
5. WHEN a Permission_Template is created or modified, THE User_Management_Service SHALL record the change in the audit trail with the acting user and X-Change-Reason.
6. THE Admin_Dashboard SHALL provide at least two default Permission_Templates: "Internal SOP" (department members read, doc_admins approve) and "External Supplier File" (restricted read, doc_admins and system_admins approve).

### Requirement 5: User Listing and Search

**User Story:** As an administrator, I want to view and search all users within my company, so that I can quickly find and manage user accounts.

#### Acceptance Criteria

1. WHEN an administrator navigates to the User Management page, THE Admin_Dashboard SHALL display a paginated list of all users belonging to the current company.
2. THE Admin_Dashboard SHALL display for each user: full name, username, email, assigned role, active status, and creation date.
3. WHEN an administrator enters a search query, THE Admin_Dashboard SHALL filter the user list by matching against username, email, or full name.
4. THE Admin_Dashboard SHALL support sorting the user list by full name, username, role, active status, and creation date.
5. THE Admin_Dashboard SHALL indicate visually whether each user account is active or deactivated.

### Requirement 6: User Creation

**User Story:** As an administrator, I want to create new user accounts and assign them to my company with a specific role, so that new team members can access the system with appropriate permissions.

#### Acceptance Criteria

1. WHEN an administrator submits a user creation form, THE User_Management_Service SHALL create a new user with username, email, full name, and an initial temporary password.
2. THE User_Management_Service SHALL validate that the username is unique across the entire system.
3. THE User_Management_Service SHALL validate that the email address is unique across the entire system.
4. WHEN a user is created, THE User_Management_Service SHALL automatically create a Company_Membership associating the new user with the current company and the specified role.
5. THE User_Management_Service SHALL hash the initial password using bcrypt before storing it in the database.
6. WHEN user creation succeeds, THE Admin_Dashboard SHALL display a confirmation message including the temporary password for the administrator to communicate to the new user.
7. THE User_Management_Service SHALL record the user creation event in the audit trail with the X-Change-Reason header value.

### Requirement 7: User Editing

**User Story:** As an administrator, I want to edit user profile information and role assignments, so that I can keep user records accurate and adjust access as responsibilities change.

#### Acceptance Criteria

1. WHEN an administrator opens the edit form for a user, THE Admin_Dashboard SHALL pre-populate all editable fields with the current values.
2. THE Admin_Dashboard SHALL allow editing of full name, email, and role assignment.
3. THE User_Management_Service SHALL validate email uniqueness when the email is changed.
4. WHEN a role change is submitted, THE RBAC_Engine SHALL update the user's Company_Membership role and apply the new permissions immediately.
5. THE User_Management_Service SHALL record all profile modifications in the audit trail with the X-Change-Reason header value.

### Requirement 8: User Activation and Deactivation

**User Story:** As an administrator, I want to activate or deactivate user accounts, so that I can control system access without permanently deleting user records.

#### Acceptance Criteria

1. WHEN an administrator deactivates a user, THE User_Management_Service SHALL set the user's is_active flag to false.
2. WHILE a user account is deactivated, THE RBAC_Engine SHALL deny all access requests from that user regardless of assigned roles.
3. WHEN a deactivated user attempts to log in, THE Admin_Dashboard SHALL display a message indicating the account is deactivated.
4. WHEN an administrator reactivates a user, THE User_Management_Service SHALL set the user's is_active flag to true and restore the previously assigned role permissions.
5. THE User_Management_Service SHALL record activation and deactivation events in the audit trail with the X-Change-Reason header value.
6. THE Admin_Dashboard SHALL prevent an administrator from deactivating their own account.

### Requirement 9: Password Reset Flow

**User Story:** As an administrator, I want to initiate a password reset for a user, so that users who have forgotten their credentials can regain access securely.

#### Acceptance Criteria

1. WHEN an administrator initiates a password reset for a user, THE Password_Reset_Service SHALL generate a new temporary password.
2. THE Password_Reset_Service SHALL hash the new temporary password using bcrypt and update the user's stored password.
3. WHEN a password reset is completed, THE Admin_Dashboard SHALL display the temporary password to the administrator for secure communication to the user.
4. THE Password_Reset_Service SHALL record the password reset event in the audit trail with the X-Change-Reason header value, without logging the password value.
5. THE Password_Reset_Service SHALL invalidate all existing refresh tokens for the affected user upon password reset.

### Requirement 10: Role Management UI

**User Story:** As an administrator, I want to view all available roles and their associated permissions, so that I can make informed decisions when assigning roles to users.

#### Acceptance Criteria

1. WHEN an administrator navigates to the Role Management page, THE Admin_Dashboard SHALL display all available roles with their names and descriptions.
2. WHEN an administrator selects a role, THE Admin_Dashboard SHALL display the complete permission matrix showing all resource types and their granted actions.
3. THE Admin_Dashboard SHALL display the count of users currently assigned to each role within the current company.
4. THE Admin_Dashboard SHALL visually distinguish between system-defined roles (non-editable) and custom roles (editable by system_admin).

### Requirement 11: Company Assignment Management

**User Story:** As a system administrator, I want to assign users to multiple companies with different roles, so that users who work across organizational boundaries have appropriate access in each context.

#### Acceptance Criteria

1. WHEN a system_admin assigns a user to an additional company, THE User_Management_Service SHALL create a new Company_Membership with the specified role.
2. THE User_Management_Service SHALL prevent duplicate Company_Membership records for the same user-company pair.
3. WHEN a Company_Membership is revoked, THE User_Management_Service SHALL set the revoked_at timestamp rather than deleting the record.
4. THE Admin_Dashboard SHALL display all company memberships for a user, including both active and revoked memberships with their respective timestamps.
5. THE User_Management_Service SHALL record all company assignment changes in the audit trail with the X-Change-Reason header value.

### Requirement 12: Integration with Workflow Execution

**User Story:** As a document administrator, I want workflow transitions to respect role-based permissions, so that only authorized users can advance documents through lifecycle stages.

#### Acceptance Criteria

1. WHEN a user attempts a workflow transition, THE RBAC_Engine SHALL verify the user holds a role with the approve action on the workflows resource type before allowing approval transitions.
2. WHEN a user attempts to edit a document in a workflow, THE RBAC_Engine SHALL verify the user holds a role with the update action on the documents resource type.
3. IF a user lacks the required permission for a workflow action, THEN THE RBAC_Engine SHALL return HTTP 403 with a descriptive error message identifying the missing permission.

### Requirement 13: Integration with Document Access

**User Story:** As a system administrator, I want document access to respect both role permissions and permission templates, so that sensitive documents are protected according to their classification.

#### Acceptance Criteria

1. WHEN a document has an associated Permission_Template, THE RBAC_Engine SHALL evaluate access using the template's role-action mapping in addition to the user's base role permissions.
2. WHEN a Permission_Template restricts access beyond the user's base role, THE RBAC_Engine SHALL apply the more restrictive rule.
3. IF a user lacks read permission for a document governed by a Permission_Template, THEN THE Admin_Dashboard SHALL exclude that document from search results and listing views for that user.

### Requirement 14: Audit Compliance for User Management Operations

**User Story:** As a compliance officer, I want all user management operations to be fully auditable, so that regulatory inspectors can trace who made what changes to user access and when.

#### Acceptance Criteria

1. THE User_Management_Service SHALL record all user management operations (create, update, deactivate, reactivate, password reset, role change) as versioned records via SQLAlchemy-Continuum.
2. WHEN any user management mutation is performed via the API, THE User_Management_Service SHALL require the X-Change-Reason header and store the reason with the audit record.
3. THE Admin_Dashboard SHALL display a change history for each user showing all modifications with timestamps, acting user, and change reasons.
