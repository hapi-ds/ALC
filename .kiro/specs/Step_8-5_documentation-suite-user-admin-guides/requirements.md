# Requirements Document

## Introduction

This document specifies the requirements for Phase 8.5 — Documentation Suite: User & Admin Guides of AlcoaBase. This feature generates comprehensive user guide and technical admin guide documents as governed documents within the ALC corporate environment, covering all implemented platform capabilities from end-user and administrator perspectives.

The feature provides:
1. A Documentation Generator Service that programmatically produces a comprehensive User Guide and a Technical Admin Guide in Markdown format
2. Automated upload of generated guides into the ALC governance folder structure with appropriate tags and workflow application
3. A service following the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible)
4. Structured guides with clear sections, step-by-step procedures, screenshot placeholders, and cross-references to other governance documents

Dependencies:
- Phase 8.2 (ALC Corporate Environment Setup) — provides ALC_Company, governance folder structure, governance workflow, and user pool
- Phase 8.3 (URS for ALC) — provides the Enhanced_URS with traceable Requirement_IDs referenced in guides
- Phase 8.4 (Cross-Sector AI Regulatory Guidelines) — provides AI usage guidelines referenced in user guide AI sections
- Phase 2.x (Document Lifecycle) — document features documented in user guide
- Phase 3.x (Workflows, Training, Signatures) — workflow features documented in user guide
- Phase 4.x (Search, Knowledge, AI) — search and RAG features documented in user guide
- Phase 5.x (Multi-Agent System) — AI agent interaction documented in user guide
- Phase 6.1 (Admin Dashboard — User Management) — admin features documented in admin guide
- Phase 6.2 (Admin Dashboard — System Configuration) — admin features documented in admin guide
- Phase 4.3 (AI Model Integration) — AI model layer documented in admin guide

## Glossary

- **Documentation_Generator_Service**: The backend service responsible for generating the User Guide and Admin Guide documents, uploading them into the ALC governance folder, and applying the governance workflow. Follows the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible).
- **User_Guide**: The comprehensive end-user manual document covering document lifecycle, training workflows, search and knowledge base, AI agent interaction, and all user-facing platform capabilities. Titled "AlcoaBase — Comprehensive User Guide".
- **Admin_Guide**: The technical administrator manual document covering system configuration, user management, RBAC, AI model configuration, storage and backup, audit trail, compliance monitoring, and agent registry management. Titled "AlcoaBase — Technical Administrator Guide".
- **Guide_Section**: A discrete chapter within a guide document covering one functional area or administrative domain, containing an overview, step-by-step procedures, screenshot placeholders, and cross-references.
- **Procedure_Block**: A numbered sequence of steps within a Guide_Section that describes how to perform a specific task, formatted with action verbs and expected outcomes for each step.
- **Screenshot_Placeholder**: A Markdown image reference with descriptive alt text and a placeholder path (format: `![Alt text](screenshots/{section}/{action}.png)`) indicating where a screenshot should be inserted during manual documentation review.
- **Cross_Reference_Block**: A structured content block within a guide that links to related governance documents (URS, AI Guidelines) by title and Requirement_ID pattern, and to other guide sections by section number.
- **Documentation_Generation_Report**: A structured summary returned after guide generation completes, detailing documents created, sections generated, tags applied, workflow states, and generation metadata.
- **ALC_Company**: The Company entity representing the AlcoaBase corporate organization within the multi-tenancy framework, identified by slug "alc-corporate" (created in Phase 8.2).
- **Governance_Folder**: The virtual folder "Governance — Documentation Suite" within the ALC_Company, with tag_filter {"tags": ["DOC-GUIDE", "ALC-GOV"]} (created or verified during execution).
- **Governance_Workflow**: The "ALC Governance Document Lifecycle" workflow definition with document_tag "ALC-GOV" and states Draft → Review → Approved → InTraining → Active → Retired (created in Phase 8.2).
- **Document_Service**: The existing service (Phase 2.1) for creating document records with UUID generation, file storage, and metadata management.
- **Workflow_Engine**: The existing service (Phase 3.2) for applying BPMN workflow definitions to documents and managing state transitions.

## Requirements

### Requirement 1: User Guide Content Generation

**User Story:** As an end-user of AlcoaBase, I want a comprehensive user guide covering all platform capabilities, so that I can learn how to perform document management, training, workflow, and AI-related tasks without external support.

#### Acceptance Criteria

1. WHEN a platform administrator initiates documentation generation, THE Documentation_Generator_Service SHALL produce a User_Guide document in Markdown format titled "AlcoaBase — Comprehensive User Guide" and SHALL complete generation within 120 seconds.
2. THE Documentation_Generator_Service SHALL structure the User_Guide with the following top-level sections in order: Document Header (title, version, generation timestamp, revision history), Table of Contents, Getting Started (login, navigation, dashboard overview), Document Management (upload, virtual folders, versioning, metadata, tags), Template Builder (creating forms, field types, drag-and-drop layout, saving templates), Report Data Entry and PDF Extraction (filling forms, uploading offline PDFs, Dual-UUID extraction), Workflows (understanding document states, triggering transitions, viewing workflow history), Training Management (viewing assigned training, completing tasks, quiz interaction), Electronic Signatures (re-authentication, signing documents, viewing signature status), Search and Knowledge Base (hybrid search, faceted filtering, RAG document Q&A, conversation history), AI Agent Interaction (understanding agent reviews, reading audit reports, compliance scorecards), AI Document Generator (selecting templates, generating documents, reviewing AI output), and Appendices (keyboard shortcuts, glossary, troubleshooting).
3. EACH Guide_Section in the User_Guide SHALL contain the following subsections in order: (a) an overview paragraph explaining the feature purpose in plain language (minimum 50 characters), (b) one or more Procedure_Blocks with numbered steps describing how to perform tasks, (c) at least one Screenshot_Placeholder per Procedure_Block indicating where a visual reference should be inserted, (d) a "Tips and Best Practices" subsection with at least two practical recommendations, and (e) a Cross_Reference_Block linking to related sections within the guide and to external governance documents where applicable.
4. EACH Procedure_Block in the User_Guide SHALL contain between 3 and 15 numbered steps, where each step begins with an action verb (e.g., "Click", "Navigate", "Enter", "Select", "Verify") and includes the expected outcome or visual confirmation the user should observe after performing the action.
5. THE Documentation_Generator_Service SHALL include a "Getting Started" section containing: system access prerequisites (browser requirements, network access), login procedure with re-authentication explanation, main navigation overview describing each sidebar menu item, and a quick-start workflow guiding the user through uploading their first document and viewing it in a virtual folder.
6. THE Documentation_Generator_Service SHALL include a "Document Management" section covering: single document upload procedure (file selection, title, folder path, document type, tags), bulk upload overview referencing the CLI tool, virtual folder creation and navigation, document versioning (uploading new versions with change reason, viewing version history), and document metadata editing.
7. THE Documentation_Generator_Service SHALL include a "Search and Knowledge Base" section covering: hybrid search usage (entering queries, interpreting relevance scores, using faceted filters), RAG Knowledge Base interaction (asking questions, interpreting source citations, managing conversation history), and understanding AI-generated answers with source attribution.
8. THE Documentation_Generator_Service SHALL include an "AI Agent Interaction" section covering: understanding multi-agent review reports, interpreting compliance scorecards, reading finding severity ratings, understanding the master auditor summary, and how training ecosystem features (AI-generated quizzes, training material, role-play scenarios) integrate with the training workflow.
9. IF the Enhanced_URS document (tags ["URS", "ALC-GOV"]) exists in the ALC_Company at generation time, THEN THE Documentation_Generator_Service SHALL include URS Requirement_ID cross-references in each Guide_Section using the pattern "Related Requirements: REQ-{MODULE}-{NN}" to establish traceability between user procedures and formal requirements.
10. IF the AI Usage Guidelines documents (tags ["AI-Guidelines", "ALC-GOV"]) exist in the ALC_Company at generation time, THEN THE Documentation_Generator_Service SHALL include cross-references to the AI Usage Guidelines in the AI-related sections (AI Agent Interaction, AI Document Generator, Search and Knowledge Base) with a note directing users to consult the guidelines for compliance requirements.

### Requirement 2: Admin Guide Content Generation

**User Story:** As a system administrator, I want a detailed technical admin guide covering system configuration, user management, and AI model oversight, so that I can manage the platform effectively and maintain compliance with regulatory requirements.

#### Acceptance Criteria

1. WHEN a platform administrator initiates documentation generation, THE Documentation_Generator_Service SHALL produce an Admin_Guide document in Markdown format titled "AlcoaBase — Technical Administrator Guide" and SHALL complete generation within 120 seconds.
2. THE Documentation_Generator_Service SHALL structure the Admin_Guide with the following top-level sections in order: Document Header (title, version, generation timestamp, revision history), Table of Contents, Administration Overview (admin roles, responsibilities, access levels), User Management (CRUD operations, role assignment, company assignment, activation/deactivation, password reset, permission templates), Role-Based Access Control (RBAC model, predefined roles, custom role creation, permission inheritance), System Configuration (AI hardware settings, storage quotas, backup configuration, system health monitoring, service status), AI Model Layer Management (vLLM service configuration, model selection, GPU/CPU/mock modes, embedding generation settings, OCR pipeline configuration), Storage and Backup (MinIO configuration, storage quotas, backup schedules, data retention policies), Audit Trail Administration (viewing audit logs, filtering and search, export to PDF, interpreting audit entries), Compliance Monitoring (compliance scorecards, agent review configuration, regulatory framework settings), Agent Registry Management (agent archetypes, YAML configuration, hot-reloading, adding new agents, contextual tuning parameters), Workflow Administration (BPMN editor usage, workflow definition management, document lifecycle configuration), and Appendices (CLI reference, API endpoints summary, environment variables, troubleshooting).
3. EACH Guide_Section in the Admin_Guide SHALL contain the following subsections in order: (a) an overview paragraph explaining the administrative function and its regulatory significance (minimum 80 characters), (b) a "Prerequisites" subsection listing required roles and permissions for the described operations, (c) one or more Procedure_Blocks with numbered steps for administrative tasks, (d) at least one Screenshot_Placeholder per Procedure_Block, (e) a "Security Considerations" subsection describing audit implications and compliance impact of the described operations, and (f) a Cross_Reference_Block linking to related admin sections and governance documents.
4. THE Documentation_Generator_Service SHALL include a "User Management" section covering: creating new users (username, email, role assignment, company assignment), editing user profiles, activating and deactivating accounts, password reset procedures, assigning users to companies, and managing permission templates for document type access control.
5. THE Documentation_Generator_Service SHALL include a "System Configuration" section covering: AI hardware mode selection (GPU, CPU, mock) with performance implications, storage quota configuration per company, backup schedule configuration, system health monitoring dashboard interpretation, and service status overview (database, Redis, OpenSearch, MinIO, vLLM connectivity).
6. THE Documentation_Generator_Service SHALL include an "AI Model Layer Management" section covering: vLLM service configuration parameters, model weight management (download, storage location, selection), GPU allocation and memory settings, CPU fallback configuration, mock mode for development, embedding model configuration for document indexing, OCR pipeline settings for scanned PDFs, and inference timeout and rate limit configuration.
7. THE Documentation_Generator_Service SHALL include an "Agent Registry Management" section covering: understanding agent archetype YAML structure (personality, domain expertise, system prompts, temperature, max tokens, evaluation rubrics), adding new agent archetypes, modifying existing agents, hot-reload mechanism explanation, and configuring company-specific audit profiles (agent assignment, regulatory frameworks, severity thresholds, review quorum).
8. THE Documentation_Generator_Service SHALL include a "Compliance Monitoring" section covering: interpreting company compliance scorecards, configuring audit readiness thresholds, reviewing multi-agent audit findings, managing risk-based workflow pathing, and monitoring the AI Risk and Compliance Framework tier assignments.
9. THE Documentation_Generator_Service SHALL include a "CLI Reference" appendix listing all administrative CLI commands with syntax, required arguments, optional flags, example invocations, and expected output format. The CLI reference SHALL include at minimum: generate_urs_alc, generate_ai_guidelines, generate_documentation, bulk_upload, and ensure_tables commands.
10. THE Documentation_Generator_Service SHALL include an "Environment Variables" appendix listing all configurable environment variables from the .env file with: variable name, description, default value (or "required" if no default), and which service component uses the variable.

### Requirement 3: Document Upload and Governance Integration

**User Story:** As a document administrator, I want generated guide documents automatically uploaded into the ALC governance folder with correct tags and workflow applied, so that they appear in the governance structure and follow the formal document lifecycle.

#### Acceptance Criteria

1. WHEN the Documentation_Generator_Service completes content generation for both guides, THE Documentation_Generator_Service SHALL upload each guide as a document record in the ALC_Company scope using the Document_Service, with content_type "text/markdown" and the generated Markdown content stored as the document file.
2. WHEN each guide document is uploaded, THE Documentation_Generator_Service SHALL apply the tags "DOC-GUIDE" and "ALC-GOV" to the document via DocumentTag records, ensuring the documents appear in the governance folder structure and are subject to the governance workflow.
3. WHEN each guide document is uploaded with the "ALC-GOV" tag, THE Documentation_Generator_Service SHALL apply the ALC Governance Document Lifecycle workflow to the document, setting its initial state to "Draft" by creating a DocumentState record referencing the workflow definition.
4. WHEN each guide document is uploaded, THE Documentation_Generator_Service SHALL set the created_by field to the ALC Document Administrator user (username "alc-doc-admin") and record the upload in the audit trail with change_reason "Documentation Suite Generation — Phase 8.5 automated governance document creation".
5. WHEN a document is uploaded successfully, THE Documentation_Generator_Service SHALL generate a Document-UUID for each guide following the existing UUID generation pattern (YYYY-NNNNN format).
6. IF the ALC_Company entity (slug "alc-corporate") does not exist at execution time, THEN THE Documentation_Generator_Service SHALL abort the operation and return an error with message "ALC corporate environment not provisioned. Run Phase 8.2 seed first."
7. IF the Governance_Workflow definition (document_tag "ALC-GOV") does not exist for the ALC_Company at execution time, THEN THE Documentation_Generator_Service SHALL abort workflow application and return an error with message "ALC Governance workflow not found. Run Phase 8.2 seed first."
8. IF the ALC Document Administrator user (username "alc-doc-admin") does not exist at execution time, THEN THE Documentation_Generator_Service SHALL abort the operation and return an error with message "ALC Document Administrator user not found. Run Phase 8.2 seed first."

### Requirement 4: Service Execution Interface

**User Story:** As a platform administrator, I want to trigger documentation generation via a CLI command or API endpoint, so that guides can be regenerated independently and the process is repeatable and auditable.

#### Acceptance Criteria

1. THE Documentation_Generator_Service SHALL be invocable via a CLI command: "uv run python -m alcoabase.scripts.generate_documentation" that executes the full generation and upload sequence within a single database transaction.
2. THE Documentation_Generator_Service SHALL be invocable via a POST /api/admin/generate-documentation endpoint that requires authentication with a system_administrator or document_administrator role and the X-Change-Reason header, returning a Documentation_Generation_Report as the response body with HTTP 200 on success.
3. THE Documentation_Generator_Service SHALL execute all operations (content generation for both guides, document uploads, tag applications, workflow assignments) within a single database transaction. IF any operation fails, THEN THE Documentation_Generator_Service SHALL roll back the entire transaction and return an error response containing the failed_operation name, the affected document_title, and a human-readable detail message.
4. THE Documentation_Generator_Service SHALL return a Documentation_Generation_Report upon successful completion containing: documents_created (array of objects with document_id, document_uuid, title, guide_type, version_number, tags_applied, workflow_state, section_count, procedure_count, screenshot_placeholder_count), total_documents (integer count, expected 2), total_sections (integer count across both guides), total_procedures (integer count of Procedure_Blocks across both guides), cross_references_included (object with urs_references: boolean, ai_guidelines_references: boolean), and total_duration_ms (integer).
5. WHEN the CLI command executes, THE Documentation_Generator_Service SHALL print the Documentation_Generation_Report to stdout in JSON format and exit with code 0 on success or code 1 on failure (with error details printed to stderr in JSON format containing failed_operation, document_title, and detail fields).
6. IF the POST /api/admin/generate-documentation endpoint is called without a valid authentication session, THEN THE system SHALL reject the request with HTTP 401 without executing any generation operations.
7. IF the POST /api/admin/generate-documentation endpoint is called with a valid session that does not hold the system_administrator or document_administrator role, THEN THE system SHALL reject the request with HTTP 403 without executing any generation operations.
8. IF the POST /api/admin/generate-documentation endpoint is called without the X-Change-Reason header, THEN THE system SHALL reject the request with HTTP 400 without executing any generation operations.
9. IF a generation request is received while another generation transaction is already in progress, THEN THE Documentation_Generator_Service SHALL reject the concurrent request with an error indicating that generation is already in progress, without starting a second transaction.

### Requirement 5: Idempotency and Versioning

**User Story:** As a platform administrator, I want repeated documentation generation to create new document versions rather than duplicates, so that the governance folder maintains a clean document history and the audit trail reflects each regeneration.

#### Acceptance Criteria

1. WHEN the Documentation_Generator_Service is invoked and a document with tags ["DOC-GUIDE", "ALC-GOV"] and a case-sensitive exact-match on title already exists in the ALC_Company, THE Documentation_Generator_Service SHALL create a new DocumentVersion record for the existing document with a version_number incremented by 1 from the current highest version and the newly generated content, rather than creating a new Document record.
2. WHEN a new version is created, THE Documentation_Generator_Service SHALL record the version creation in the audit trail with change_reason containing the document title and the new version number.
3. THE Documentation_Generator_Service SHALL include the version number (integer) and generation timestamp (ISO 8601 UTC format) in each document header.
4. WHEN a new version is created for any guide document, THE Documentation_Generator_Service SHALL reset that document's workflow state to "Draft" by creating a new DocumentState record, requiring the document to go through the full governance lifecycle again.
5. THE Documentation_Generator_Service SHALL report in the Documentation_Generation_Report for each document whether the operation created a new document (is_new_document: true) or a new version of an existing document (is_new_document: false), along with the version_number.
6. THE Documentation_Generator_Service SHALL evaluate each of the two guide documents (User_Guide and Admin_Guide) separately for existence, creating a new version for documents that already exist and a new document for those that do not.
7. IF any one of the two guide document operations fails during generation, THEN THE Documentation_Generator_Service SHALL roll back the entire transaction so that no partial results (new documents or new versions) are persisted.

### Requirement 6: Content Quality and Structure Standards

**User Story:** As a quality manager, I want the generated guides to follow consistent formatting and quality standards, so that the documentation is professional, auditable, and usable as formal governance documents.

#### Acceptance Criteria

1. EACH guide document SHALL include a document header containing: document title, document version (auto-incremented integer starting at 1 for the first generation), generation timestamp in ISO 8601 format with timezone offset, target audience (end-users for User_Guide, administrators for Admin_Guide), applicable platform version, and a revision history table listing all previous generation versions with their timestamps and change summaries.
2. EACH guide document SHALL include a Table of Contents section generated from the document's heading structure, listing all level-2 and level-3 headings with their section numbers.
3. THE Documentation_Generator_Service SHALL ensure each Procedure_Block uses consistent formatting: steps numbered sequentially starting at 1, each step on its own line, action verbs in bold at the start of each step, UI element names in bold (e.g., **Upload Document**), and expected outcomes in italics following the action description.
4. THE Documentation_Generator_Service SHALL include at least one Screenshot_Placeholder per Procedure_Block, formatted as `![{Descriptive alt text}](screenshots/{section-slug}/{action-slug}.png)` where section-slug and action-slug are kebab-case identifiers derived from the section title and procedure action.
5. THE Documentation_Generator_Service SHALL produce a User_Guide containing a minimum of 10 Guide_Sections and a minimum of 25 Procedure_Blocks across all sections.
6. THE Documentation_Generator_Service SHALL produce an Admin_Guide containing a minimum of 10 Guide_Sections and a minimum of 20 Procedure_Blocks across all sections.
7. EACH guide document SHALL use consistent terminology throughout, matching the terms defined in the Glossary section of the guide and the platform UI labels. THE Documentation_Generator_Service SHALL include a Glossary appendix in each guide defining all technical terms, acronyms, and platform-specific terminology used within the document.
8. IF a Guide_Section contains fewer than 200 characters of content (excluding section headers and Screenshot_Placeholders), THEN THE Documentation_Generator_Service SHALL abort generation and return an error indicating which section in which guide failed content validation.

### Requirement 7: Cross-Reference and Traceability Integration

**User Story:** As a regulatory auditor, I want the generated guides to include cross-references to formal governance documents and traceable requirement IDs, so that documentation can be linked to requirements and compliance evidence during audits.

#### Acceptance Criteria

1. EACH guide document SHALL include a "Related Governance Documents" section listing all governance documents in the ALC_Company that the guide references, with document title, document UUID, and current workflow state for each referenced document.
2. WHEN the Enhanced_URS document (tags ["URS", "ALC-GOV"]) exists in the ALC_Company, THE Documentation_Generator_Service SHALL include Requirement_ID cross-references in relevant Guide_Sections using the pattern "Implements: REQ-{MODULE}-{NN}" to establish traceability between documented procedures and formal requirements.
3. WHEN the AI Usage Guidelines documents (tags ["AI-Guidelines", "ALC-GOV"]) exist in the ALC_Company, THE Documentation_Generator_Service SHALL include explicit cross-references in AI-related sections of both guides, directing users to the appropriate guideline document for compliance requirements and permitted use policies.
4. THE User_Guide SHALL include cross-references from the Admin_Guide in sections where administrative action is required (e.g., "Contact your administrator to configure workflow definitions — see Admin Guide Section X").
5. THE Admin_Guide SHALL include cross-references from the User_Guide in sections where end-user impact is described (e.g., "This setting affects user experience as described in User Guide Section Y").
6. IF the Enhanced_URS document does not exist at generation time, THEN THE Documentation_Generator_Service SHALL proceed with generation but SHALL omit URS Requirement_ID cross-references and include a notice stating "URS cross-references unavailable — generate URS (Phase 8.3) for full traceability."
7. IF the AI Usage Guidelines documents do not exist at generation time, THEN THE Documentation_Generator_Service SHALL proceed with generation but SHALL omit AI Guidelines cross-references and include a notice in AI-related sections stating "AI Usage Guidelines cross-references unavailable — generate guidelines (Phase 8.4) for compliance context."

### Requirement 8: Error Handling and Prerequisites

**User Story:** As a platform administrator, I want clear error messages when prerequisites are missing, so that I can resolve issues and successfully generate the documentation suite.

#### Acceptance Criteria

1. IF the ALC_Company (slug "alc-corporate") does not exist, THEN THE Documentation_Generator_Service SHALL return an error with message "ALC corporate environment not provisioned. Run Phase 8.2 seed first." and exit code 1, without performing subsequent prerequisite checks.
2. IF the ALC_Company exists but the ALC Document Administrator user (username "alc-doc-admin") does not exist, THEN THE Documentation_Generator_Service SHALL return an error with message "ALC Document Administrator user not found. Run Phase 8.2 seed first." and exit code 1.
3. IF the ALC_Company and ALC Document Administrator exist but the Governance_Workflow (document_tag "ALC-GOV") does not exist for the ALC_Company, THEN THE Documentation_Generator_Service SHALL return an error with message "ALC Governance workflow not found. Run Phase 8.2 seed first." and exit code 1.
4. IF a database connection failure or transaction error occurs during content_generation, document_upload, tag_application, or workflow_assignment, THEN THE Documentation_Generator_Service SHALL roll back all changes made during the current execution, and return an error indicating which step failed and for which document (by title), with exit code 1.
5. WHEN the Documentation_Generator_Service produces guide content, THE Documentation_Generator_Service SHALL validate that the content is non-empty and contains at least one Markdown heading (level 1–3) before proceeding to upload.
6. IF content validation fails because the generated content is empty or contains no Markdown heading, THEN THE Documentation_Generator_Service SHALL abort with an error indicating which document (by title) produced invalid output, with exit code 1.
7. THE Documentation_Generator_Service SHALL check prerequisites in the following order: ALC_Company existence, ALC Document Administrator existence, Governance_Workflow existence, and SHALL halt on the first failing check.
8. IF the Documentation_Generator_Service encounters a content generation error for one guide but the other guide has already been generated successfully, THEN THE Documentation_Generator_Service SHALL roll back the entire transaction (including the successfully generated guide) and return an error indicating which guide failed, ensuring atomic all-or-nothing behavior.
