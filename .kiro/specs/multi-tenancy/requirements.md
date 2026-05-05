# Requirements Document

## Introduction

This document specifies the requirements for introducing multi-tenancy (company separation) into AlcoaBase. The system must support multiple organizations (tenants) operating in isolated data environments, each with its own regulatory context, user pool, and document repository. This is the foundational layer upon which all other features depend — documents, templates, workflows, training records, agents, and audit trails must be scoped to a specific company.

## Glossary

- **Company**: The tenant entity representing a single organization. Each Company operates in an isolated data context within AlcoaBase.
- **Tenant**: Synonym for Company in the context of data isolation and scoping.
- **Regulatory_Framework**: The quality management standard governing a Company's operations (e.g., ISO 13485, GMP, GDP, ISO 9001).
- **Company_Membership**: The association between a User and a Company, including the User's role within that Company.
- **Tenant_Scope**: The data isolation boundary ensuring that all queries and mutations are restricted to the active Company context.
- **System_Admin**: A platform-level administrator who can manage Companies and assign users across tenants.
- **Company_Admin**: An administrator scoped to a single Company who manages users, roles, and configuration within that tenant.
- **Tenant_Context**: The runtime state identifying which Company the current request is operating within.
- **Audit_Profile**: A Company-specific configuration defining which regulatory frameworks, agent auditors, and review thresholds apply.
- **Global_Resource**: A system-level resource (such as agent definitions or base templates) that can be shared across Companies without duplication.

## Requirements

### Requirement 1: Company Entity Creation

**User Story:** As a System_Admin, I want to create a new Company with a unique identifier and regulatory context, so that organizations can operate in isolated environments.

#### Acceptance Criteria

1. WHEN a System_Admin submits a valid company creation request, THE Company_Service SHALL create a new Company record with a unique slug, display name, and regulatory framework designation.
2. THE Company entity SHALL store the following attributes: unique slug (URL-safe identifier), display name, regulatory framework type, active status, and creation timestamp.
3. WHEN a Company is created, THE Company_Service SHALL generate an isolated data scope for that Company covering documents, templates, workflows, training records, virtual folders, and reports.
4. IF a company creation request contains a slug that already exists, THEN THE Company_Service SHALL reject the request with a conflict error.
5. IF a company creation request omits required fields (slug, display name, or regulatory framework), THEN THE Company_Service SHALL reject the request with a validation error.

### Requirement 2: User-Company Membership

**User Story:** As a System_Admin, I want to assign users to one or more Companies, so that users can access only the data belonging to their assigned organizations.

#### Acceptance Criteria

1. WHEN a System_Admin assigns a User to a Company, THE Membership_Service SHALL create a Company_Membership record linking the User to the Company with a designated role.
2. THE Company_Membership SHALL support multiple memberships per User, enabling a single User to belong to more than one Company.
3. WHEN a User belongs to multiple Companies, THE Tenant_Context SHALL require explicit Company selection before granting access to tenant-scoped resources.
4. IF a membership assignment references a non-existent User or Company, THEN THE Membership_Service SHALL reject the request with a not-found error.
5. WHEN a Company_Membership is revoked, THE Membership_Service SHALL immediately prevent the User from accessing that Company's resources on subsequent requests.

### Requirement 3: Tenant-Scoped Data Isolation for Documents

**User Story:** As a Company user, I want all documents I create to be automatically scoped to my Company, so that other organizations cannot access my data.

#### Acceptance Criteria

1. WHEN a User creates a document, THE Document_Service SHALL automatically associate the document with the User's active Tenant_Context.
2. WHEN a User queries documents, THE Document_Service SHALL return only documents belonging to the User's active Tenant_Context.
3. THE Document_Service SHALL enforce tenant scoping at the database query level, preventing cross-tenant data leakage regardless of API parameter manipulation.
4. IF a User attempts to access a document belonging to a different Company, THEN THE Document_Service SHALL reject the request with a forbidden error.

### Requirement 4: Tenant-Scoped Data Isolation for Templates and Reports

**User Story:** As a Company user, I want templates and reports to be scoped to my Company, so that each organization maintains its own form definitions and data records.

#### Acceptance Criteria

1. WHEN a User creates a template, THE Template_Service SHALL automatically associate the template with the User's active Tenant_Context.
2. WHEN a User queries templates, THE Template_Service SHALL return only templates belonging to the User's active Tenant_Context.
3. WHEN a User creates a report, THE Report_Service SHALL automatically associate the report with the User's active Tenant_Context.
4. WHEN a User queries reports, THE Report_Service SHALL return only reports belonging to the User's active Tenant_Context.
5. IF a User attempts to create a report referencing a template from a different Company, THEN THE Report_Service SHALL reject the request with a forbidden error.

### Requirement 5: Tenant-Scoped Data Isolation for Workflows

**User Story:** As a Company_Admin, I want workflow definitions to be scoped to my Company, so that each organization can define its own document lifecycle processes.

#### Acceptance Criteria

1. WHEN a Company_Admin creates a workflow definition, THE Workflow_Service SHALL automatically associate the workflow with the Company_Admin's active Tenant_Context.
2. WHEN the system evaluates workflow transitions for a document, THE Workflow_Service SHALL use only workflow definitions belonging to the document's Company.
3. WHEN a User queries available workflows, THE Workflow_Service SHALL return only workflows belonging to the User's active Tenant_Context.
4. IF a document state transition references a workflow from a different Company, THEN THE Workflow_Service SHALL reject the transition with a forbidden error.

### Requirement 6: Tenant-Scoped Data Isolation for Training Records

**User Story:** As a Company user, I want training records and tasks to be scoped to my Company, so that training compliance is tracked independently per organization.

#### Acceptance Criteria

1. WHEN a training task is generated from an SOP approval, THE Training_Service SHALL scope the task to the Company that owns the SOP document.
2. WHEN a User queries training records, THE Training_Service SHALL return only records belonging to the User's active Tenant_Context.
3. THE Training_Service SHALL evaluate training compliance (the training gate) using only training records within the same Company as the target document.
4. IF a User attempts to complete a training task belonging to a different Company, THEN THE Training_Service SHALL reject the request with a forbidden error.

### Requirement 7: Tenant-Scoped Virtual Folders

**User Story:** As a Company user, I want virtual folders to be scoped to my Company, so that document organization is independent per organization.

#### Acceptance Criteria

1. WHEN a User creates a virtual folder, THE VirtualFolder_Service SHALL automatically associate the folder with the User's active Tenant_Context.
2. WHEN a User queries virtual folders, THE VirtualFolder_Service SHALL return only folders belonging to the User's active Tenant_Context.
3. WHEN a virtual folder applies its tag filter, THE VirtualFolder_Service SHALL match only documents within the same Company.

### Requirement 8: Company-Specific Regulatory Framework Configuration

**User Story:** As a Company_Admin, I want to configure my Company's regulatory framework, so that audit profiles, review requirements, and compliance rules match my industry.

#### Acceptance Criteria

1. THE Company entity SHALL store a regulatory framework type from a defined set (ISO_13485, GMP, GDP, ISO_9001, ISO_17025, or a custom designation).
2. WHEN a Company_Admin updates the regulatory framework configuration, THE Company_Service SHALL persist the change and apply the updated framework to subsequent compliance evaluations.
3. THE Company entity SHALL store additional audit configuration including required signature roles, training requirements scope, and document retention policies.
4. IF a regulatory framework update would invalidate active workflows, THEN THE Company_Service SHALL warn the Company_Admin and require explicit confirmation before applying the change.

### Requirement 9: Tenant Context Resolution in API Requests

**User Story:** As a developer, I want a consistent mechanism for resolving the active tenant context from API requests, so that all service layers can enforce data isolation uniformly.

#### Acceptance Criteria

1. THE API_Gateway SHALL resolve the active Tenant_Context from the authenticated User's session or an explicit company identifier in the request.
2. WHEN a User belongs to exactly one Company, THE API_Gateway SHALL automatically set the Tenant_Context to that Company without requiring explicit selection.
3. WHEN a User belongs to multiple Companies, THE API_Gateway SHALL require an explicit company identifier in the request header or path parameter.
4. IF the Tenant_Context cannot be resolved (missing company identifier for a multi-company User), THEN THE API_Gateway SHALL reject the request with a 400 error indicating company selection is required.
5. IF the authenticated User does not have membership in the specified Company, THEN THE API_Gateway SHALL reject the request with a 403 forbidden error.

### Requirement 10: Global Agent Definitions with Company-Scoped Activation

**User Story:** As a System_Admin, I want agent definitions to be available globally while allowing Companies to activate and configure them independently, so that agent logic is reusable without duplication.

#### Acceptance Criteria

1. THE Agent_Service SHALL support agent definitions at two levels: global (system-wide) and company-scoped (tenant-specific).
2. WHEN a Company_Admin activates a global agent definition for a Company, THE Agent_Service SHALL create a company-scoped activation record linking the agent to the Company with optional configuration overrides.
3. WHEN the multi-agent review system evaluates a document, THE Agent_Service SHALL use only agents activated for the document's Company.
4. WHEN a Company_Admin creates a custom agent definition, THE Agent_Service SHALL scope that definition exclusively to the creating Company.
5. IF a Company_Admin attempts to modify a global agent definition, THEN THE Agent_Service SHALL reject the modification and suggest creating a company-scoped override instead.

### Requirement 11: Tenant-Scoped Audit Trail

**User Story:** As a compliance officer, I want audit trail entries to be scoped to my Company, so that regulatory audits can be conducted independently per organization.

#### Acceptance Criteria

1. WHEN an auditable action occurs, THE Audit_Service SHALL tag the audit trail entry with the Company identifier from the active Tenant_Context.
2. WHEN a User queries the audit trail, THE Audit_Service SHALL return only entries belonging to the User's active Tenant_Context.
3. THE Audit_Service SHALL prevent cross-tenant audit trail access regardless of the User's role within a different Company.
4. WHEN a System_Admin queries the audit trail without a Tenant_Context, THE Audit_Service SHALL return entries across all Companies (platform-level audit view).

### Requirement 12: Database Schema Migration for Multi-Tenancy

**User Story:** As a developer, I want the database schema to support multi-tenancy through a company foreign key on all tenant-scoped tables, so that data isolation is enforced at the storage level.

#### Acceptance Criteria

1. THE Database_Migration SHALL add a `companies` table with columns for id, slug, display name, regulatory framework, audit configuration (JSON), is_active flag, and created_at timestamp.
2. THE Database_Migration SHALL add a `company_memberships` table linking users to companies with a role designation and timestamps.
3. THE Database_Migration SHALL add a `company_id` foreign key column to the following existing tables: documents, templates, workflow_definitions, training_records, training_tasks, virtual_folders, reports, and signature_records.
4. THE Database_Migration SHALL add a `company_id` nullable foreign key to the agent_definitions table (null indicates a global agent definition).
5. THE Database_Migration SHALL create a composite index on (company_id, document_uuid) for the documents table to optimize tenant-scoped lookups.
6. THE Database_Migration SHALL backfill existing records with a default company_id for systems upgrading from a single-tenant deployment.

### Requirement 13: Company Deactivation

**User Story:** As a System_Admin, I want to deactivate a Company without deleting its data, so that regulatory retention requirements are met while preventing further access.

#### Acceptance Criteria

1. WHEN a System_Admin deactivates a Company, THE Company_Service SHALL set the Company's active status to false.
2. WHILE a Company is deactivated, THE API_Gateway SHALL reject all requests with that Company's Tenant_Context with a 403 error indicating the company is inactive.
3. WHILE a Company is deactivated, THE Audit_Service SHALL retain all audit trail entries for the deactivated Company without modification.
4. WHEN a System_Admin reactivates a Company, THE Company_Service SHALL restore access for all previously assigned users without requiring re-assignment.
