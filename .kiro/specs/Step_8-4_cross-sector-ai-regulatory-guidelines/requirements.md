# Requirements Document

## Introduction

This document specifies the requirements for Phase 8.4 — Cross-Sector AI Regulatory Guidelines of AlcoaBase. This feature generates AI usage guideline documents as governed documents within the ALC corporate environment, explaining how to use ALC's AI features safely and compliantly based on current global regulations (EU AI Act, FDA/EMA guidance, ISO standards) and the ALC-URS (Phase 8.3).

The feature provides:
1. A Contextual Policy Engine that generates AI usage guideline documents integrating risk classifications from Phase 8.1 with regulatory context
2. Sector-Specific Policy Modules (Pharma/GMP, MedTech/ISO 13485, IVD/IVDR) that produce tailored guidance on how to use ALC AI functions within each regulatory vertical
3. Automated upload of generated guideline documents into the ALC governance folder structure with appropriate tags and workflow application
4. A service following the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible)

Dependencies:
- Phase 8.1 (AI Risk & Compliance Framework) — provides risk-based tiering, AI_Task_Types, and Control_Sets
- Phase 8.2 (ALC Corporate Environment Setup) — provides ALC_Company, governance folder structure, governance workflow, and user pool
- Phase 8.3 (URS for ALC) — provides the Enhanced_URS with traceable Requirement_IDs referenced in guidelines
- Phase 5.1 (Agent Registry) — AI agent archetypes referenced in usage guidance
- Phase 5.2 (Multi-Agent Auditing) — compliance scorecards and auditing context
- Phase 6.2 (System Configuration) — admin system settings

## Glossary

- **Guidelines_Generator_Service**: The backend service responsible for generating AI regulatory guideline documents, uploading them into the ALC governance folder, and applying the governance workflow. Follows the ALCSeedService pattern (idempotent, single-transaction, CLI + API accessible).
- **Contextual_Policy_Engine**: The core logic component within the Guidelines_Generator_Service that assembles guideline content by combining regulatory framework rules, risk tier classifications (Phase 8.1), URS requirement references (Phase 8.3), and sector-specific compliance requirements into coherent policy documents.
- **Sector_Module**: A distinct policy template configuration for a specific regulatory vertical (Pharma/GMP, MedTech/ISO 13485, IVD/IVDR) that defines sector-specific rules, terminology, and compliance requirements for AI usage within that context.
- **AI_Usage_Guideline**: A generated Markdown document that provides structured guidance on how to use specific ALC AI features (Document Generator, Multi-Agent Auditing, RAG, Training Ecosystem, Change Impact Analysis, Traceability Discovery) within a given regulatory context, including permitted uses, restrictions, required controls, and compliance evidence requirements.
- **Regulatory_Context**: A named regulatory framework configuration (EU_AI_Act, FDA_21CFR11, EMA_Annex11, ISO_13485, IVDR_2017_746, GMP_Annex11) that defines specific rules and constraints for AI usage within that regulatory scope.
- **Policy_Section**: A discrete section within an AI_Usage_Guideline covering one AI feature or cross-cutting concern (e.g., "Document Generation Usage Policy", "Human Oversight Requirements", "Audit Evidence Requirements").
- **Risk_Integration_Block**: A structured content block within a guideline that maps each AI_Task_Type to its risk tier, applicable controls, and sector-specific additional requirements, derived from the Company_Risk_Profile (Phase 8.1).
- **URS_Reference_Block**: A structured content block within a guideline that cross-references relevant Requirement_IDs from the Enhanced_URS (Phase 8.3) to provide traceability between guidelines and formal requirements.
- **Guidelines_Generation_Report**: A structured summary returned after guideline generation completes, detailing documents created, tags applied, workflow states, and sector coverage.
- **ALC_Company**: The Company entity representing the AlcoaBase corporate organization within the multi-tenancy framework, identified by slug "alc-corporate" (created in Phase 8.2).
- **Governance_Folder**: The virtual folder "Governance — AI Regulatory Guidelines" within the ALC_Company, with tag_filter {"tags": ["AI-Guidelines", "ALC-GOV"]} (created in Phase 8.2).
- **Governance_Workflow**: The "ALC Governance Document Lifecycle" workflow definition with document_tag "ALC-GOV" and states Draft → Review → Approved → InTraining → Active → Retired (created in Phase 8.2).
- **Document_Service**: The existing service (Phase 2.1) for creating document records with UUID generation, file storage, and metadata management.
- **Workflow_Engine**: The existing service (Phase 3.2) for applying BPMN workflow definitions to documents and managing state transitions.

## Requirements

### Requirement 1: Contextual Policy Engine — Core Guideline Generation

**User Story:** As a quality manager, I want AI usage guideline documents generated programmatically based on current global regulations and the ALC risk framework, so that my organization has up-to-date, auditable guidance on how to use AI features compliantly.

#### Acceptance Criteria

1. WHEN a quality manager or system_admin initiates guideline generation, THE Guidelines_Generator_Service SHALL produce one AI_Usage_Guideline document in Markdown format, titled "AlcoaBase — AI Usage Guidelines (Cross-Sector)", covering all registered AI_Task_Types with regulatory context applicable across all sectors, and SHALL complete generation within 120 seconds.
2. THE Guidelines_Generator_Service SHALL structure the master guideline document with the following sections in order: Document Header (title, version, generation timestamp, applicable regulations), Purpose and Scope, Regulatory Framework Overview, Risk Classification Summary (derived from Phase 8.1 Default_Risk_Profile), AI Feature Usage Policies (one Policy_Section per AI_Task_Type), Human Oversight Requirements, Audit and Evidence Requirements, Prohibited Uses, Glossary, and URS Traceability References.
3. WHEN generating the Risk Classification Summary, THE Contextual_Policy_Engine SHALL query the Risk_Classification_Service (Phase 8.1) to retrieve all AI_Task_Types with status "active" and their assigned risk tiers and control sets, and SHALL format each task type as a Risk_Integration_Block containing: task_type display_name, assigned tier (High, Medium, or Low), required controls from the tier's Control_Set, HITL requirements (required or not required), and audit depth (Full, Standard, or Minimal).
4. WHEN generating AI Feature Usage Policies, THE Contextual_Policy_Engine SHALL produce one Policy_Section per registered AI_Task_Type containing: feature description derived from the task_type display_name and module reference, permitted use cases derived from the task_type's registered scope, restrictions and limitations derived from the tier's Control_Set constraints, required human oversight steps matching the tier's HITL checkpoint requirements, required documentation and evidence matching the tier's audit depth level, and references to applicable regulatory articles from the document header's regulatory framework list.
5. THE Contextual_Policy_Engine SHALL include a URS_Reference_Block that cross-references relevant Requirement_IDs from the Enhanced_URS (Phase 8.3) for each AI feature policy section, using the pattern "Implements: REQ-{MODULE}-{NN}" to establish traceability between guidelines and formal requirements, where MODULE matches the AI_Task_Type's module reference and NN is a zero-padded two-digit sequence number.
6. THE Guidelines_Generator_Service SHALL include a document header containing: document title, document version (auto-incremented integer starting at 1 for the first generation), generation timestamp in ISO 8601 format with timezone offset, applicable regulatory frameworks (EU AI Act, 21 CFR Part 11, EU GMP Annex 11, ISO 13485, IVDR 2017/746), and a revision history table listing all previous generation versions with their timestamps and change summaries.
7. IF the Risk_Classification_Service returns zero active AI_Task_Types, THEN THE Guidelines_Generator_Service SHALL abort generation and return an error indicating the AI Risk Framework (Phase 8.1) must be seeded before guidelines can be generated.
8. IF the Risk_Classification_Service is unreachable or returns an error response within 30 seconds, THEN THE Guidelines_Generator_Service SHALL abort generation and return an error indicating the Risk_Classification_Service dependency is unavailable, preserving the most recent previously generated guideline document unchanged.

### Requirement 2: Sector-Specific Policy Modules

**User Story:** As a regulatory affairs specialist, I want sector-specific AI usage policy templates for Pharma, MedTech, and IVD, so that each regulatory vertical has tailored guidance reflecting its unique compliance requirements for AI usage.

#### Acceptance Criteria

1. THE Guidelines_Generator_Service SHALL generate three sector-specific AI_Usage_Guideline documents in addition to the master guideline:
   - "AlcoaBase — AI Usage Guidelines (Pharma / GMP)" covering GMP Annex 11, 21 CFR Part 11, EU GMP Chapter 4, and ICH Q9/Q10 requirements
   - "AlcoaBase — AI Usage Guidelines (MedTech / ISO 13485)" covering ISO 13485:2016, MDR 2017/745, IEC 62304, and FDA 21 CFR 820 requirements
   - "AlcoaBase — AI Usage Guidelines (IVD / IVDR)" covering IVDR 2017/746, ISO 13485:2016, and EU common specifications requirements
2. EACH sector-specific guideline SHALL contain the following sections in order: Document Header (title, version, generation timestamp, applicable sector regulations), Sector Regulatory Context (listing each applicable regulation with at least one specific article or section reference per regulation), Sector-Specific Risk Considerations (at least one additional risk factor per AI_Task_Type beyond the base framework risk_factors), AI Feature Usage Policies (one Policy_Section per active AI_Task_Type with sector-specific restrictions), Validation Requirements (sector-specific validation expectations for AI outputs including acceptance criteria), Record Keeping Requirements (sector-specific retention periods and format rules), and Cross-References (explicit references to the master guideline by title and to the URS by Requirement_ID pattern).
3. THE Pharma/GMP Sector_Module SHALL include at least one dedicated subsection for each of the following topics: GMP data integrity requirements (ALCOA+ principles applied to AI outputs, referencing EU GMP Annex 11 Section 7), computer system validation expectations for AI-assisted processes (referencing GAMP 5 software categories 3, 4, and 5), qualification requirements for AI models used in GxP-regulated activities (referencing ICH Q9 risk assessment methodology), and change control procedures for AI model updates (referencing EU GMP Chapter 4 change control requirements).
4. THE MedTech/ISO 13485 Sector_Module SHALL include at least one dedicated subsection for each of the following topics: design control integration (AI outputs as design inputs per ISO 13485 Section 7.3, specifying design input review requirements), software lifecycle requirements for AI components (IEC 62304 safety classification Classes A, B, and C with corresponding documentation requirements), risk management integration (ISO 14971 applied to AI-generated content, specifying hazard identification and risk estimation steps), and post-market surveillance considerations for AI-assisted decisions (referencing MDR 2017/745 Article 83 vigilance requirements).
5. THE IVD/IVDR Sector_Module SHALL include at least one dedicated subsection for each of the following topics: performance evaluation requirements for AI-assisted analytical processes (referencing IVDR 2017/746 Article 56 performance studies), common specifications compliance for AI-generated IVD documentation (referencing IVDR Article 9 common specifications), clinical evidence requirements when AI supports performance studies (referencing IVDR Annex XIII clinical evidence requirements), and notified body expectations for AI usage documentation (referencing IVDR Article 48 conformity assessment documentation).
6. EACH sector-specific guideline SHALL include a mapping table covering all active AI_Task_Types registered in the Risk_Classification_Service (Phase 8.1), with columns: AI_Task_Type display_name, base risk tier (from the Default_Risk_Profile or active Company_Risk_Profile), sector-specific risk elevation recommendation (one of: "Elevate to High", "Elevate to Medium", or "No elevation" with a one-sentence regulatory justification), sector-specific additional controls beyond the base Control_Set (at least one additional control per elevated task type, or "None — base controls sufficient" for non-elevated types), and applicable regulatory article reference justifying the sector position.
7. THE Guidelines_Generator_Service SHALL ensure sector-specific guidelines do not contradict the master guideline by enforcing the following rule: no sector-specific guideline SHALL assign a lower risk tier recommendation or fewer controls to any AI_Task_Type than the master guideline specifies. WHERE a sector-specific guideline adds stricter requirements, THE guideline SHALL explicitly state the additional requirement as "Supplementary to base policy" with a reference to the corresponding master guideline section.
8. IF a sector-specific guideline is generated with any section containing fewer than 100 characters of content (excluding section headers), THEN THE Guidelines_Generator_Service SHALL abort generation for that sector document and return an error indicating which section in which sector guideline failed content validation.

### Requirement 3: Document Upload and Governance Integration

**User Story:** As a document administrator, I want generated guideline documents automatically uploaded into the ALC governance folder with correct tags and workflow applied, so that they appear in the governance structure and follow the formal document lifecycle.

#### Acceptance Criteria

1. WHEN the Guidelines_Generator_Service completes content generation, THE Guidelines_Generator_Service SHALL upload each AI_Usage_Guideline as a document record in the ALC_Company scope using the Document_Service, with content_type "text/markdown" and the generated Markdown content stored as the document file.
2. WHEN each guideline document is uploaded, THE Guidelines_Generator_Service SHALL apply the tags "AI-Guidelines" and "ALC-GOV" to the document via DocumentTag records, ensuring the document appears in the "Governance — AI Regulatory Guidelines" virtual folder.
3. WHEN each guideline document is uploaded with the "ALC-GOV" tag, THE Guidelines_Generator_Service SHALL apply the ALC Governance Document Lifecycle workflow to the document, setting its initial state to "Draft" by creating a DocumentState record referencing the workflow definition.
4. WHEN each guideline document is uploaded, THE Guidelines_Generator_Service SHALL set the created_by field to the ALC Document Administrator user (username "alc-doc-admin") and record the upload in the audit trail with change_reason "AI Regulatory Guidelines Generation — Phase 8.4 automated governance document creation".
5. WHEN a document is uploaded successfully, THE Guidelines_Generator_Service SHALL generate a Document-UUID for each guideline following the existing UUID generation pattern (YYYY-NNNNN format).
6. IF the ALC_Company entity (slug "alc-corporate") does not exist at execution time, THEN THE Guidelines_Generator_Service SHALL abort the operation and return an error with message "ALC corporate environment not provisioned. Run Phase 8.2 seed first."
7. IF the Governance_Workflow definition (document_tag "ALC-GOV") does not exist for the ALC_Company at execution time, THEN THE Guidelines_Generator_Service SHALL abort workflow application and return an error with message "ALC Governance workflow not found. Run Phase 8.2 seed first."
8. IF the ALC Document Administrator user (username "alc-doc-admin") does not exist at execution time, THEN THE Guidelines_Generator_Service SHALL abort the operation and return an error with message "ALC Document Administrator user not found. Run Phase 8.2 seed first."

### Requirement 4: Risk Framework Integration

**User Story:** As a compliance officer, I want the AI usage guidelines to dynamically reflect the current risk classifications and control sets from Phase 8.1, so that guidelines remain accurate as risk profiles evolve.

#### Acceptance Criteria

1. WHEN generating guideline content, THE Contextual_Policy_Engine SHALL query the active Company_Risk_Profile for the ALC_Company (Phase 8.1) and use the effective risk tier for each AI_Task_Type (company override if present, otherwise the AI_Task_Type default_risk_tier) when composing Risk_Integration_Blocks.
2. THE Contextual_Policy_Engine SHALL include the complete Control_Set for each risk tier in the guidelines, specifying: HITL checkpoint requirements (required or not required, and whether it blocks visibility), audit depth level (full, standard, or minimal), validation requirements (format, cross-reference, completeness as applicable), output labeling rules (ai_assisted or ai_generated as applicable), expiry windows (in hours, or none), and rate limits (requests per user per hour, or none) as defined in the Risk_Classification_Service TIER_DEFINITIONS.
3. THE Contextual_Policy_Engine SHALL include the risk_factors array from the AI_Task_Type registry for each active AI_Task_Type registered for the ALC_Company to explain why the task type received its assigned tier.
4. THE Contextual_Policy_Engine SHALL include a "Prohibited Uses" section listing operations that are explicitly not permitted regardless of risk tier, including: using AI outputs as sole basis for batch release decisions without human verification, bypassing HITL checkpoints for High-tier operations, using AI-generated content in regulatory submissions without formal review and approval through the governance workflow, and disabling audit logging for any AI operation.
5. IF the ALC_Company has no active Company_Risk_Profile, THEN THE Contextual_Policy_Engine SHALL resolve each AI_Task_Type to its default_risk_tier from the AI_Task_Type registry and SHALL include a notice in the generated guideline indicating that default risk classifications are applied because no company-specific risk profile is active.
6. IF the Contextual_Policy_Engine cannot retrieve AI_Task_Type records or TIER_DEFINITIONS from the Risk_Classification_Service during guideline generation, THEN THE Contextual_Policy_Engine SHALL abort the risk integration block generation and return an error indicating that risk framework data is unavailable.

### Requirement 5: Service Execution Interface

**User Story:** As a platform administrator, I want to trigger guideline generation via a CLI command or API endpoint, so that documents can be regenerated independently and the process is repeatable and auditable.

#### Acceptance Criteria

1. THE Guidelines_Generator_Service SHALL be invocable via a CLI command: "uv run python -m alcoabase.scripts.generate_ai_guidelines" that executes the full generation and upload sequence within a single database transaction.
2. THE Guidelines_Generator_Service SHALL be invocable via a POST /api/admin/generate-ai-guidelines endpoint that requires authentication with a system_administrator or document_administrator role and the X-Change-Reason header, returning a Guidelines_Generation_Report as the response body with HTTP 200 on success.
3. THE Guidelines_Generator_Service SHALL execute all operations (content generation for all documents, document uploads, tag applications, workflow assignments) within a single database transaction. IF any operation fails, THEN THE Guidelines_Generator_Service SHALL roll back the entire transaction and return an error response containing the failed_operation name, the affected document_title, and a human-readable detail message.
4. THE Guidelines_Generator_Service SHALL return a Guidelines_Generation_Report upon successful completion containing: documents_created (array of objects with document_id, document_uuid, title, sector, version_number, tags_applied, workflow_state), total_documents (integer count of guideline documents generated), total_policy_sections (integer count of policy sections across all documents), risk_tiers_referenced (array of tier levels used), regulatory_frameworks_covered (array of framework identifiers), and total_duration_ms (integer).
5. WHEN the CLI command executes, THE Guidelines_Generator_Service SHALL print the Guidelines_Generation_Report to stdout in JSON format and exit with code 0 on success or code 1 on failure (with error details printed to stderr in JSON format containing failed_operation, document_title, and detail fields).
6. IF the POST /api/admin/generate-ai-guidelines endpoint is called without a valid authentication session, THEN THE system SHALL reject the request with HTTP 401 without executing any generation operations.
7. IF the POST /api/admin/generate-ai-guidelines endpoint is called with a valid session that does not hold the system_administrator or document_administrator role, THEN THE system SHALL reject the request with HTTP 403 without executing any generation operations.
8. IF the POST /api/admin/generate-ai-guidelines endpoint is called without the X-Change-Reason header, THEN THE system SHALL reject the request with HTTP 400 without executing any generation operations.
9. IF a generation request is received while another generation transaction is already in progress, THEN THE Guidelines_Generator_Service SHALL reject the concurrent request with an error indicating that generation is already in progress, without starting a second transaction.

### Requirement 6: Idempotency and Versioning

**User Story:** As a platform administrator, I want repeated guideline generation to create new document versions rather than duplicates, so that the governance folder maintains a clean document history and the audit trail reflects each regeneration.

#### Acceptance Criteria

1. WHEN the Guidelines_Generator_Service is invoked and a document with tags ["AI-Guidelines", "ALC-GOV"] and a case-sensitive exact-match on title already exists in the ALC_Company, THE Guidelines_Generator_Service SHALL create a new DocumentVersion record for the existing document with a version_number incremented by 1 from the current highest version and the newly generated content, rather than creating a new Document record.
2. WHEN a new version is created, THE Guidelines_Generator_Service SHALL record the version creation in the audit trail with change_reason containing the document title and the new version number.
3. THE Guidelines_Generator_Service SHALL include the version number (integer) and generation timestamp (ISO 8601 UTC format) in each document header.
4. WHEN a new version is created for any guideline document, THE Guidelines_Generator_Service SHALL reset that document's workflow state to "Draft" by creating a new DocumentState record, requiring the document to go through the full governance lifecycle again.
5. THE Guidelines_Generator_Service SHALL report in the Guidelines_Generation_Report for each document whether the operation created a new document (is_new_document: true) or a new version of an existing document (is_new_document: false), along with the version_number.
6. THE Guidelines_Generator_Service SHALL evaluate each of the four guideline documents (master + 3 sector-specific) separately for existence, creating a new version for documents that already exist and a new document for those that do not.
7. IF any one of the four guideline document operations fails during generation, THEN THE Guidelines_Generator_Service SHALL roll back the entire transaction so that no partial results (new documents or new versions) are persisted.

### Requirement 7: Regulatory Content Structure and Quality

**User Story:** As a regulatory auditor, I want the generated guidelines to follow a consistent, auditable structure with clear regulatory references and traceability, so that the documents can serve as evidence of AI governance during compliance audits.

#### Acceptance Criteria

1. EACH AI_Usage_Guideline SHALL include explicit regulatory article references (e.g., "EU AI Act Article 14 — Human Oversight", "21 CFR 11.10(a) — Validation") for every control requirement stated in the document, formatted as inline citations. Each citation SHALL include the regulation name and the specific article or section number.
2. EACH AI_Usage_Guideline SHALL include a Regulatory Reference Table at the end of the document listing all cited regulations with: regulation name, article/section number, requirement summary (maximum 500 characters per entry), and how ALC addresses the requirement (maximum 1000 characters per entry). The table SHALL contain at minimum one row per distinct regulation cited in the document body.
3. THE Guidelines_Generator_Service SHALL ensure each Policy_Section contains the following five subsections in order: (a) a statement of permitted uses listing specific allowed operations, (b) a statement of restrictions listing explicitly prohibited actions, (c) a numbered compliance procedure for users with between 3 and 15 steps, (d) a list of required evidence and documentation items, and (e) a consequences of non-compliance subsection referencing the audit trail (Phase 6.3) and compliance scorecard (Phase 5.2) as enforcement mechanisms.
4. EACH AI_Usage_Guideline SHALL include a "Roles and Responsibilities" section defining who is responsible for: approving AI outputs (mapped to HITL reviewer roles), monitoring compliance (mapped to quality_manager role), configuring risk profiles (mapped to system_admin or doc_admin roles), and conducting periodic reviews of guideline adequacy.
5. THE Guidelines_Generator_Service SHALL produce guidelines with one Policy_Section per active AI_Task_Type registered in the Risk_Classification_Service, resulting in a minimum of 8 Policy_Sections in the master guideline and a minimum of 6 Policy_Sections in each sector-specific guideline. IF the number of active AI_Task_Types exceeds 8, THEN THE master guideline SHALL contain one Policy_Section per active AI_Task_Type.
6. EACH AI_Usage_Guideline SHALL include a "Periodic Review" section specifying that the guideline must be reviewed within the number of days defined by the review_cycle_days setting (default 365 days) from the ALC regulatory baseline configuration, or whenever the Company_Risk_Profile is modified (tier override added, removed, or changed), whichever occurs first.
7. IF a control requirement in a Policy_Section cannot be mapped to a specific regulatory article reference, THEN THE Guidelines_Generator_Service SHALL annotate that control with "Regulatory reference: Industry best practice — no specific article applicable" rather than omitting the citation.

### Requirement 8: Error Handling and Prerequisites

**User Story:** As a platform administrator, I want clear error messages when prerequisites are missing, so that I can resolve issues and successfully generate the guideline documents.

#### Acceptance Criteria

1. IF the ALC_Company (slug "alc-corporate") does not exist, THEN THE Guidelines_Generator_Service SHALL return an error with message "ALC corporate environment not provisioned. Run Phase 8.2 seed first." and exit code 1, without performing subsequent prerequisite checks.
2. IF the ALC_Company exists but the ALC Document Administrator user (username "alc-doc-admin") does not exist, THEN THE Guidelines_Generator_Service SHALL return an error with message "ALC Document Administrator user not found. Run Phase 8.2 seed first." and exit code 1.
3. IF the ALC_Company and ALC Document Administrator exist but the Governance_Workflow (document_tag "ALC-GOV") does not exist for the ALC_Company, THEN THE Guidelines_Generator_Service SHALL return an error with message "ALC Governance workflow not found. Run Phase 8.2 seed first." and exit code 1.
4. IF the Risk_Classification_Service returns zero active AI_Task_Types, THEN THE Guidelines_Generator_Service SHALL return an error with message "No AI task types registered. Run Phase 8.1 seed first." and exit code 1.
5. IF a database connection failure or transaction error occurs during content_generation, document_upload, tag_application, or workflow_assignment, THEN THE Guidelines_Generator_Service SHALL roll back all changes made during the current execution, and return an error indicating which step failed and for which document (by title), with exit code 1.
6. WHEN the Guidelines_Generator_Service produces guideline content, THE Guidelines_Generator_Service SHALL validate that the content is non-empty and contains at least one Markdown heading (level 1–3) before proceeding to upload.
7. IF content validation fails because the generated content is empty or contains no Markdown heading, THEN THE Guidelines_Generator_Service SHALL abort with an error indicating which document (by title) produced invalid output, with exit code 1.
8. IF the Enhanced_URS document (tags ["URS", "ALC-GOV"]) does not exist in the ALC_Company at generation time, THEN THE Guidelines_Generator_Service SHALL proceed with generation but SHALL omit URS_Reference_Blocks and include a notice in each guideline stating "URS cross-references unavailable — generate URS (Phase 8.3) for full traceability."
9. THE Guidelines_Generator_Service SHALL check prerequisites in the following order: ALC_Company existence, ALC Document Administrator existence, Governance_Workflow existence, AI_Task_Types availability, and SHALL halt on the first failing check.
