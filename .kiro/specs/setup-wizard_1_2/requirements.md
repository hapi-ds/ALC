# Requirements Document

## Introduction

This document specifies the requirements for the First-Run Setup Wizard in AlcoaBase. The Setup Wizard is a mandatory initialization flow that runs exactly once on a fresh deployment. It guides the administrator through creating the root admin account, establishing the initial company (tenant), configuring the AI hardware mode, and optionally seeding demo data. Until the wizard is completed, the system blocks all other API access, ensuring the platform is properly initialized before any regulated operations begin.

## Glossary

- **Setup_Wizard**: The first-run initialization flow that configures the AlcoaBase platform before normal operation begins.
- **Root_Admin**: The initial administrator account created during setup, possessing full system-level privileges across all tenants.
- **Initial_Company**: The first Company (tenant) entity created during setup, providing the organizational context for the Root_Admin.
- **AI_Hardware_Mode**: The operational mode for the model manager, determining how AI inference is executed. Valid values are "gpu", "cpu", or "mock".
- **Setup_Guard**: The middleware or dependency that blocks all non-setup API access while the system remains uninitialized.
- **Setup_Status**: A persistent database flag indicating whether the Setup Wizard has been completed.
- **Demo_Seed**: An optional set of sample documents, templates, and configuration data loaded during setup for evaluation purposes.
- **Password_Policy**: The set of complexity rules that passwords must satisfy, including minimum length, character class diversity, and common password rejection.
- **Documentation_Team**: The team or individual responsible for authoring and maintaining user-facing documentation for the AlcoaBase platform.
- **User_Guide**: The user-facing documentation artifact that explains the Setup Wizard flow, prerequisites, step-by-step instructions, and troubleshooting guidance.

## Requirements

### Requirement 1: First-Run Detection

**User Story:** As the system, I want to detect whether initialization has been completed, so that the Setup Wizard is presented only on a fresh deployment.

#### Acceptance Criteria

1. WHEN the application starts, THE Setup_Guard SHALL query the Setup_Status from the database to determine if initialization has been completed.
2. IF the Setup_Status record does not exist or is set to incomplete, THEN THE Setup_Guard SHALL treat the system as uninitialized.
3. IF the Setup_Status record exists and is set to complete, THEN THE Setup_Guard SHALL allow normal application operation without presenting the Setup Wizard.
4. THE Setup_Status SHALL be stored in a dedicated database table to survive application restarts and container re-creation.

### Requirement 2: API Access Blocking During Setup

**User Story:** As a security administrator, I want all non-setup API endpoints to be inaccessible until setup is complete, so that no regulated operations occur on an unconfigured system.

#### Acceptance Criteria

1. WHILE the system is uninitialized, THE Setup_Guard SHALL reject all API requests to non-setup endpoints with an HTTP 503 response and a JSON body indicating setup is required.
2. WHILE the system is uninitialized, THE Setup_Guard SHALL allow requests to the setup wizard endpoints (under the `/api/v1/setup/` path prefix).
3. WHILE the system is uninitialized, THE Setup_Guard SHALL allow requests to the health check endpoint (`/health`).
4. WHEN the Setup_Status transitions to complete, THE Setup_Guard SHALL immediately allow requests to all API endpoints without requiring an application restart.

### Requirement 3: Root Admin Account Creation

**User Story:** As a deploying administrator, I want to create the root admin account during setup, so that there is a credentialed user who can manage the platform.

#### Acceptance Criteria

1. WHEN the setup wizard receives a valid root admin creation request, THE Setup_Wizard SHALL create a Root_Admin user with the provided username, email address, and password.
2. THE Setup_Wizard SHALL enforce the Password_Policy requiring: minimum 12 characters, at least one uppercase letter, at least one lowercase letter, at least one digit, and at least one special character.
3. IF the provided password does not satisfy the Password_Policy, THEN THE Setup_Wizard SHALL reject the request with a validation error listing all unmet requirements.
4. THE Setup_Wizard SHALL hash the Root_Admin password using bcrypt before storing it in the database.
5. THE Setup_Wizard SHALL assign the Root_Admin the system-level administrator role, granting full platform privileges.
6. WHEN the Root_Admin account is created, THE Setup_Wizard SHALL generate a JWT access token for the Root_Admin to use in subsequent setup steps.

### Requirement 4: Initial Company Creation

**User Story:** As a deploying administrator, I want to create the initial company during setup, so that the platform has a tenant context for organizing documents and users.

#### Acceptance Criteria

1. WHEN the setup wizard receives a valid company creation request, THE Setup_Wizard SHALL create an Initial_Company with the provided display name, slug, and regulatory framework designation.
2. THE Setup_Wizard SHALL automatically generate a URL-safe slug from the display name if no explicit slug is provided.
3. IF the provided slug contains characters other than lowercase letters, digits, and hyphens, THEN THE Setup_Wizard SHALL reject the request with a validation error.
4. THE Setup_Wizard SHALL assign the Root_Admin as a Company_Admin of the Initial_Company upon creation.
5. THE Setup_Wizard SHALL set the Initial_Company's active status to true upon creation.

### Requirement 5: AI Hardware Mode Configuration

**User Story:** As a deploying administrator, I want to select the AI hardware mode during setup, so that the system uses the appropriate inference backend for the available hardware.

#### Acceptance Criteria

1. WHEN the setup wizard receives an AI hardware mode selection, THE Setup_Wizard SHALL persist the selected mode ("gpu", "cpu", or "mock") to the application configuration.
2. IF the selected mode is "gpu", THEN THE Setup_Wizard SHALL validate that the vLLM GPU service endpoint is reachable and return a warning if connectivity fails.
3. IF the selected mode is "cpu", THEN THE Setup_Wizard SHALL validate that the vLLM CPU service endpoint is reachable and return a warning if connectivity fails.
4. IF the selected mode is "mock", THEN THE Setup_Wizard SHALL skip connectivity validation and configure the model manager for mock responses.
5. THE Setup_Wizard SHALL store the AI_Hardware_Mode selection in the database so that it persists across application restarts independently of environment variables.

### Requirement 6: Demo Data Seeding

**User Story:** As a deploying administrator, I want to optionally seed demo data during setup, so that I can evaluate the platform with realistic sample content.

#### Acceptance Criteria

1. WHERE the administrator opts to seed demo data, THE Setup_Wizard SHALL create sample documents, templates, and virtual folders within the Initial_Company scope.
2. WHERE the administrator opts to seed demo data, THE Setup_Wizard SHALL create sample workflow definitions appropriate to the Initial_Company's regulatory framework.
3. WHERE the administrator opts to skip demo data, THE Setup_Wizard SHALL complete setup without creating any sample content.
4. WHEN demo data is seeded, THE Setup_Wizard SHALL tag all seeded records with a `is_demo_data` flag to allow future identification and removal.

### Requirement 7: Setup Completion and Lockout

**User Story:** As a security administrator, I want the setup wizard to be permanently inaccessible after completion, so that the initial configuration cannot be tampered with.

#### Acceptance Criteria

1. WHEN all required setup steps (root admin creation, company creation, and AI mode selection) are completed, THE Setup_Wizard SHALL set the Setup_Status to complete in the database.
2. WHEN the Setup_Status is set to complete, THE Setup_Wizard SHALL record the completion timestamp and the Root_Admin user identifier in the Setup_Status record.
3. WHILE the system is initialized (Setup_Status is complete), THE Setup_Guard SHALL reject all requests to setup wizard endpoints with an HTTP 403 response indicating setup has already been completed.
4. THE Setup_Status completion SHALL be irreversible through the API — no endpoint shall exist to reset the Setup_Status to incomplete.

### Requirement 8: Setup Idempotency and Resumption

**User Story:** As a deploying administrator, I want to resume the setup wizard if it was interrupted, so that partial progress is not lost.

#### Acceptance Criteria

1. WHEN the setup wizard is accessed and partial setup data exists (e.g., root admin created but company not yet created), THE Setup_Wizard SHALL return the current setup progress indicating which steps are complete.
2. IF the root admin account already exists when a root admin creation request is submitted, THEN THE Setup_Wizard SHALL reject the request with a conflict error indicating the account already exists.
3. IF the initial company already exists when a company creation request is submitted, THEN THE Setup_Wizard SHALL reject the request with a conflict error indicating the company already exists.
4. WHEN a setup step is repeated with identical parameters after a previous successful execution, THE Setup_Wizard SHALL return the existing result without creating duplicate records.

### Requirement 9: Setup Audit Trail

**User Story:** As a compliance officer, I want all setup actions to be recorded in the audit trail, so that the initial system configuration is traceable for regulatory purposes.

#### Acceptance Criteria

1. WHEN the Root_Admin account is created during setup, THE Audit_Service SHALL record the creation event with a timestamp and the action description.
2. WHEN the Initial_Company is created during setup, THE Audit_Service SHALL record the creation event with the company details and timestamp.
3. WHEN the AI_Hardware_Mode is configured during setup, THE Audit_Service SHALL record the selected mode and timestamp.
4. WHEN the Setup_Status is set to complete, THE Audit_Service SHALL record the completion event with the Root_Admin identifier and timestamp.
5. THE Audit_Service SHALL record setup audit entries without requiring an authenticated user context for the initial root admin creation step (since no user exists yet).

### Requirement 10: Setup Wizard User Guide

**User Story:** As a deploying administrator, I want a user-facing guide for the Setup Wizard, so that I can understand the full initialization flow, prerequisites, and troubleshooting steps before and during deployment.

#### Acceptance Criteria

1. THE Documentation_Team SHALL produce a user guide document covering the complete Setup Wizard flow from first-run detection through setup completion.
2. THE User_Guide SHALL include a prerequisites section listing required infrastructure, environment variables, network connectivity, and access credentials needed before starting the Setup Wizard.
3. THE User_Guide SHALL include step-by-step instructions for each setup phase: Root_Admin account creation, Initial_Company creation, AI_Hardware_Mode selection, and Demo_Seed configuration.
4. THE User_Guide SHALL include a troubleshooting section describing common error scenarios (connectivity failures, validation errors, interrupted setup resumption) and their resolutions.
5. WHEN the Setup Wizard behavior or API contract changes, THE Documentation_Team SHALL update the User_Guide to reflect the current behavior before the change is released.
6. THE User_Guide SHALL use consistent terminology matching the Glossary defined in this requirements document.
