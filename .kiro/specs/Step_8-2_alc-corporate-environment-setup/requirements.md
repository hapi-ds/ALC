# Requirements Document

## Introduction

This document specifies the requirements for the ALC Corporate Environment Setup (Phase 8.2) of AlcoaBase. This feature initializes a dedicated "ALC" company/tenant within the existing Multi-Tenancy framework (1.1) to serve as the master reference tenant, internal management hub, and example/test environment for the platform itself.

The ALC corporate environment provides:
1. A canonical reference tenant demonstrating all platform capabilities
2. An internal management hub for ALC corporate operations and governance
3. The home tenant for all governance documents created in subsequent phases (8.3 URS, 8.4 AI Regulatory Guidelines, 8.5 Documentation Suite)
4. A standardized configuration baseline with appropriate regulatory settings for a software/platform company

This feature builds upon the existing Setup Wizard (1.2), Multi-Tenancy (1.1), RBAC (6.1), System Configuration (6.2), and AI Risk & Compliance Framework (8.1). The ALC tenant is created via a dedicated seeding mechanism (CLI command or API endpoint) that is idempotent and can be run post-setup to provision the corporate environment without disrupting existing tenants.

## Glossary

- **ALC_Seed_Service**: The backend service responsible for creating and configuring the ALC corporate tenant, its user pool, regulatory settings, folder structure, and risk profile. Operates idempotently so repeated invocations produce no duplicate data.
- **ALC_Company**: The Company entity representing the AlcoaBase corporate organization within the multi-tenancy framework. Distinguished by the reserved slug "alc-corporate".
- **Corporate_User_Pool**: The set of predefined user accounts created within the ALC_Company for internal operations, including IT-Admin, Doc-Admin, Quality Manager, and standard user roles.
- **Regulatory_Baseline**: The standardized set of regulatory framework settings, audit configurations, and compliance parameters applied to the ALC_Company appropriate for a software/platform development organization.
- **Governance_Folder_Structure**: The predefined virtual folder hierarchy within the ALC_Company designed to organize governance documents (URS, AI guidelines, user guides, admin guides) created in subsequent phases.
- **ALC_Risk_Profile**: The Company_Risk_Profile configured for the ALC_Company that maps AI task types to risk tiers appropriate for an internal platform management context.
- **Seed_Report**: A structured summary returned after the ALC environment seeding completes, detailing all entities created or confirmed as already existing.

## Requirements

### Requirement 1: ALC Company Entity Creation

**User Story:** As a platform administrator, I want to initialize a dedicated ALC company tenant with a reserved slug and appropriate metadata, so that the platform has a canonical reference environment for internal management and governance.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL create an ALC_Company entity with the following attributes: slug "alc-corporate" (reserved, unique, maximum 100 characters), display_name "AlcoaBase Corporate" (maximum 300 characters), regulatory_framework "ISO_27001", audit_config containing {"review_quorum": 2, "auto_audit_on_upload": true, "severity_threshold": "medium"}, and is_active set to true.
2. IF an ALC_Company with slug "alc-corporate" already exists in the database, THEN THE ALC_Seed_Service SHALL skip company creation, log the skip at INFO level with a message indicating the existing entity was reused, and use the existing entity for all subsequent seeding operations without modifying its current attributes.
3. IF a company creation request via the Setup Wizard or API specifies slug "alc-corporate", THEN THE system SHALL reject the request with an error response indicating the slug is reserved for the ALC corporate environment, and SHALL NOT create or modify any company record.
4. THE ALC_Seed_Service SHALL record the ALC_Company creation in the audit trail with change_reason "ALC Corporate Environment Setup — Phase 8.2 initialization" and actor identity set to the system service account (user_id corresponding to the ALC_Seed_Service principal).
5. IF the database is unreachable or a transaction failure occurs during ALC_Company creation, THEN THE ALC_Seed_Service SHALL abort the seeding operation, log the failure at ERROR level with the underlying cause, and SHALL NOT leave a partially-created company record in the database.

### Requirement 2: Corporate User Pool Provisioning

**User Story:** As a platform administrator, I want predefined user accounts with appropriate roles created within the ALC company, so that the corporate environment has a functional user pool for internal operations and serves as a demonstration of RBAC capabilities.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL create the following user accounts within the ALC_Company with CompanyMembership records linking each user to the ALC_Company:
   - Username "alc-it-admin", full_name "ALC IT Administrator", email "it-admin@alc.local", role assignment "system_administrator"
   - Username "alc-doc-admin", full_name "ALC Document Administrator", email "doc-admin@alc.local", role assignment "document_administrator"
   - Username "alc-quality-mgr", full_name "ALC Quality Manager", email "quality@alc.local", role assignment "quality_manager"
   - Username "alc-user", full_name "ALC Standard User", email "user@alc.local", role assignment "user"
2. THE ALC_Seed_Service SHALL set initial passwords for all Corporate_User_Pool accounts to a configurable value read from the environment variable ALC_SEED_DEFAULT_PASSWORD (defaulting to "AlcCorp2024!" if not set). All accounts SHALL have is_active set to true.
3. IF any user account in the Corporate_User_Pool already exists (matched by username), THEN THE ALC_Seed_Service SHALL skip creation of that account and log a message indicating the username that was skipped, and proceed with the remaining accounts without raising an error or aborting the provisioning sequence.
4. THE ALC_Seed_Service SHALL assign each Corporate_User_Pool user to the appropriate Role via the UserRole association table, creating the Role record first if it does not already exist for the ALC_Company scope. Each Role record SHALL have company_id set to the ALC_Company's id and is_system set to true.
5. THE ALC_Seed_Service SHALL create CompanyMembership records linking each Corporate_User_Pool user to the ALC_Company with the role_id referencing the appropriate company-scoped Role and the legacy role string field set to the role assignment name.
6. IF the root admin user (created during Setup Wizard Phase 1.2) is not already a member of the ALC_Company (no active CompanyMembership with revoked_at IS NULL exists for that user_id and company_id pair), THEN THE ALC_Seed_Service SHALL create a CompanyMembership for the root admin with the "system_administrator" role in the ALC_Company.
7. IF a user account in the Corporate_User_Pool has a username that does not already exist but has an email that conflicts with an existing account, THEN THE ALC_Seed_Service SHALL skip creation of that account, log a warning indicating the email conflict, and proceed with the remaining accounts without raising an error.
8. WHEN the ALC_Seed_Service completes Corporate_User_Pool provisioning, THE ALC_Seed_Service SHALL have created exactly 4 user accounts (or fewer if some were skipped due to pre-existence or conflicts), each with exactly one CompanyMembership to the ALC_Company and exactly one UserRole association linking the user to their designated company-scoped Role.
9. IF the database connection fails or a transaction error occurs during Corporate_User_Pool provisioning, THEN THE ALC_Seed_Service SHALL roll back all changes from the current provisioning attempt and report the failure with an error message indicating which step failed.

### Requirement 3: Regulatory Baseline Configuration

**User Story:** As a compliance officer, I want the ALC company to have standardized regulatory settings appropriate for a software platform company, so that governance documents and AI operations within the ALC tenant follow a consistent compliance baseline.

#### Acceptance Criteria

1. WHEN the ALC_Company is created during setup, THE ALC_Seed_Service SHALL create a SystemConfiguration row with category "alc_regulatory_baseline" and company_id referencing the ALC_Company, storing the following values as a JSON config_values object: applicable_frameworks ["ISO_27001", "ISO_9001", "EU_AI_Act"], document_retention_years 10, signature_required_for_approval true, training_required_before_access true, audit_log_retention_years 7, and review_cycle_days 365.
2. WHEN the ALC_Company is created during setup, THE ALC_Seed_Service SHALL create a SystemConfiguration row with category "alc_audit_config" and company_id referencing the ALC_Company, storing the following values as a JSON config_values object: review_quorum 2, auto_audit_on_upload true, severity_threshold "medium", and default_workflow_tag "ALC-GOV".
3. IF a SystemConfiguration row with category "alc_regulatory_baseline" already exists for the ALC_Company, THEN THE ALC_Seed_Service SHALL skip regulatory baseline creation and leave the existing row unmodified.
4. IF a SystemConfiguration row with category "alc_audit_config" already exists for the ALC_Company, THEN THE ALC_Seed_Service SHALL skip audit configuration creation and leave the existing row unmodified.
5. WHEN the regulatory baseline is successfully applied, THE ALC_Seed_Service SHALL log an audit trail entry attributing the configuration creation to the system seed operation.

### Requirement 4: Governance Folder Structure

**User Story:** As a document administrator, I want a predefined folder structure within the ALC company for organizing governance documents, so that subsequent phases (8.3, 8.4, 8.5) have designated locations for their outputs.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL create the following VirtualFolder records with company_id referencing the ALC_Company:
   - Name "Governance — User Requirement Specifications", tag_filter {"tags": ["URS", "ALC-GOV"]}, sort_order "created_at_desc"
   - Name "Governance — AI Regulatory Guidelines", tag_filter {"tags": ["AI-Guidelines", "ALC-GOV"]}, sort_order "created_at_desc"
   - Name "Governance — User Guides", tag_filter {"tags": ["User-Guide", "ALC-GOV"]}, sort_order "created_at_desc"
   - Name "Governance — Admin Guides", tag_filter {"tags": ["Admin-Guide", "ALC-GOV"]}, sort_order "created_at_desc"
   - Name "Governance — Risk Framework", tag_filter {"tags": ["Risk-Framework", "ALC-GOV"]}, sort_order "created_at_desc"
   - Name "Governance — All Documents", tag_filter {"tags": ["ALC-GOV"]}, sort_order "created_at_desc"
2. THE ALC_Seed_Service SHALL mark all governance VirtualFolder records with is_system_default set to true and created_by referencing the ALC IT Administrator user account.
3. IF a VirtualFolder with the same name already exists within the ALC_Company scope, THEN THE ALC_Seed_Service SHALL skip creation of that folder and continue processing remaining folders without raising an error.
4. IF the ALC IT Administrator user account does not exist at seed execution time, THEN THE ALC_Seed_Service SHALL abort governance folder creation and raise an error indicating the required user account is missing.

### Requirement 5: ALC Risk Profile Configuration

**User Story:** As a quality manager, I want the ALC company to have a pre-configured AI risk profile aligned with the Risk & Compliance Framework (8.1), so that AI operations within the ALC tenant are governed by appropriate tier-specific controls from day one.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL create a CompanyRiskProfile for the ALC_Company with profile_name "ALC Corporate Risk Profile", description "Baseline risk profile for AlcoaBase corporate environment — software platform development and governance context", regulatory_frameworks ["ISO_27001", "ISO_9001", "EU_AI_Act"], is_active set to true, and created_by referencing the ALC IT Administrator user ID.
2. IF the ALC_Risk_Profile requires no tier deviations from the Default_Risk_Profile (task types "rag_knowledge_query", "document_search", "template_analysis" remain Low; "change_impact_analysis", "traceability_gap_discovery" remain Medium; "document_generation", "multi_agent_audit", "training_content_generation" remain High), THEN THE ALC_Seed_Service SHALL create the CompanyRiskProfile record with an empty overrides array and SHALL NOT create any RiskTierOverride records for this profile.
3. IF a CompanyRiskProfile with is_active set to true already exists for the ALC_Company, THEN THE ALC_Seed_Service SHALL skip risk profile creation without modifying the existing profile and SHALL NOT create any RiskAssessmentRecord.
4. WHEN the ALC_Risk_Profile is created with an empty overrides array (no tier changes from defaults), THE ALC_Seed_Service SHALL NOT create any RiskAssessmentRecord, since no tier assignment change has occurred.
5. THE ALC_Seed_Service SHALL verify that all 8 system-defined AITaskType records (rag_knowledge_query, document_search, template_analysis, change_impact_analysis, traceability_gap_discovery, document_generation, multi_agent_audit, training_content_generation) exist and are active before creating the CompanyRiskProfile; IF any required AITaskType record is missing or inactive, THEN THE ALC_Seed_Service SHALL raise an error indicating which task types are unavailable.

### Requirement 6: Seed Execution Interface

**User Story:** As a platform administrator, I want to trigger the ALC corporate environment setup via a CLI command or API endpoint, so that the seeding can be executed independently of the initial Setup Wizard and repeated safely.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL be invocable via a CLI command: "uv run python -m alcoabase.scripts.seed_alc_corporate" that executes the full seeding sequence (company creation, user pool, regulatory baseline, folder structure, risk profile) within a single database transaction and completes within 60 seconds.
2. THE ALC_Seed_Service SHALL be invocable via a POST /api/admin/seed-alc-corporate endpoint that requires authentication with a system_administrator role and the X-Change-Reason header. The endpoint SHALL return a Seed_Report as the response body with HTTP 200 on success.
3. THE ALC_Seed_Service SHALL execute all seeding operations within a single database transaction. IF any operation fails, THEN THE ALC_Seed_Service SHALL roll back the entire transaction and return an error indicating which operation failed (by name: company creation, user pool, regulatory baseline, folder structure, or risk profile) and the reason for failure.
4. THE ALC_Seed_Service SHALL return a Seed_Report upon successful completion containing: company_id (integer), company_slug (string "alc-corporate"), users_created (array of usernames created), users_skipped (array of usernames that already existed), folders_created (array of folder names created), folders_skipped (array of folder names that already existed), risk_profile_created (boolean), regulatory_baseline_created (boolean), and total_duration_ms (integer).
5. WHEN the CLI command executes, THE ALC_Seed_Service SHALL print the Seed_Report to stdout in JSON format and exit with code 0 on success or code 1 on failure (with error details printed to stderr).
6. THE ALC_Seed_Service SHALL log each entity created or skipped at INFO level, including the entity type and name, to provide a traceable record of the initialization process.
7. WHEN the ALC_Seed_Service is invoked and the target entities already exist, THE ALC_Seed_Service SHALL skip existing entities without error, report them in the users_skipped and folders_skipped arrays of the Seed_Report, and complete successfully (idempotent execution).
8. IF the POST /api/admin/seed-alc-corporate endpoint is called without a valid system_administrator session or without the X-Change-Reason header, THEN THE ALC_Seed_Service SHALL reject the request with HTTP 401 for missing or invalid authentication, or HTTP 400 for a missing X-Change-Reason header, without executing any seeding operations.

### Requirement 7: Agent Activation for ALC Company

**User Story:** As a platform administrator, I want all available AI agent archetypes activated for the ALC company, so that the corporate environment can demonstrate the full multi-agent auditing capabilities and serve as a reference for other tenants.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL create CompanyAgentActivation records for the ALC_Company for every AgentDefinition where company_id IS NULL (global agents) and is_active is true in the agent_definitions table at the time of seeding, with is_active set to true and config_overrides set to an empty JSON object (using global defaults).
2. IF a CompanyAgentActivation record already exists for a given AgentDefinition within the ALC_Company and has is_active set to true, THEN THE ALC_Seed_Service SHALL skip activation of that agent without error.
3. IF a CompanyAgentActivation record already exists for a given AgentDefinition within the ALC_Company but has is_active set to false, THEN THE ALC_Seed_Service SHALL update that record by setting is_active to true and config_overrides to an empty JSON object, and report the agent in the agents_activated array.
4. IF the agent_definitions table contains zero global AgentDefinition records at the time of seeding, THEN THE ALC_Seed_Service SHALL proceed without error and report empty arrays for both agents_activated and agents_skipped in the Seed_Report.
5. THE ALC_Seed_Service SHALL include in the Seed_Report: agents_activated (array of AgentDefinition.name values for agents that were newly activated or re-activated) and agents_skipped (array of AgentDefinition.name values for agents that already had an active CompanyAgentActivation).

### Requirement 8: Governance Workflow Definition

**User Story:** As a document administrator, I want a predefined BPMN workflow for governance documents within the ALC company, so that URS, guidelines, and manuals created in subsequent phases follow a standardized lifecycle.

#### Acceptance Criteria

1. THE ALC_Seed_Service SHALL create a WorkflowDefinition for the ALC_Company with name "ALC Governance Document Lifecycle", document_tag "ALC-GOV", is_active true, signature_required_transitions ["Review→Approved"], training_trigger_transitions ["Approved→InTraining"], and a valid BPMN XML defining the states: Draft → Review → Approved → InTraining → Active → Retired, where the BPMN XML conforms to the BPMN 2.0 schema and passes SpiffWorkflow validation with no unreachable or missing terminal states.
2. THE ALC_Seed_Service SHALL set created_by on the WorkflowDefinition to the ALC IT Administrator user_id and company_id to the ALC_Company id, and SHALL create a corresponding WorkflowVersion record with version_number 1, the same BPMN XML, and change_reason set to a description indicating initial seed creation.
3. IF a WorkflowDefinition with document_tag "ALC-GOV" already exists for the ALC_Company, THEN THE ALC_Seed_Service SHALL skip workflow creation without modifying the existing definition and SHALL NOT create a new WorkflowVersion record.
4. THE ALC_Seed_Service SHALL include in the Seed_Report: workflow_created (boolean indicating whether the governance workflow was newly created or already existed).
5. IF the ALC IT Administrator user_id or ALC_Company id is not available at seed execution time, THEN THE ALC_Seed_Service SHALL fail the workflow creation step and report workflow_created as false in the Seed_Report.
