# Requirements Document

## Introduction

This document specifies the requirements for Phase 9.5 — Regulatory Medical Device Vigilance & Post-Market Surveillance (PMS) — of AlcoaBase. This feature builds on the Literature Search Engine (Phase 9.1), Automated Ingestion Pipeline (Phase 9.2), High-Dimensional Embedding & Hybrid Indexing (Phase 9.3), and AI-Powered Literature Review & Synthesis Agents (Phase 9.4) by introducing continuous, automated vigilance monitoring for medical device companies.

Phase 9.5 introduces five major capabilities:

1. **"Always-On" Vigilance Monitors** — Continuous background workers (Celery beat) that execute automated, scheduled literature searches for adverse events, product issues, field safety corrective actions (FSCAs), or equivalent material updates related to the company's registered product portfolio. Each company defines vigilance search profiles linking product identifiers, MeSH terms, and adverse event keywords.

2. **Signal Detection & Risk Scoring** — When new literature results match a vigilance profile, the system uses the Literature Screener Agent (Phase 9.4) or a new "Vigilance Analyst" agent archetype to analyze whether findings represent genuine safety signals. Signal severity is classified (critical/major/minor) using regulatory criteria aligned with MDR Article 87, MedDev 2.12/1, and MEDDEV 2.7/1 Rev 4.

3. **GxP Alerting & Escalation** — If an agent flags a high-severity adverse event or safety trend, the system triggers Risk-Based Pathing (Phase 3.1 BPMN workflows), bypassing standard review flows to immediately alert Document Admins (Phase 6.1) and auto-generate a mandatory Change Impact Analysis task (Phase 5.5). Critical signals also trigger automatic Contradiction Alert creation (Phase 9.4) and SLR review initiation.

4. **Product Portfolio Management** — Companies register their medical devices/products with associated metadata (device class, UDI, intended purpose, predicate devices). Vigilance search profiles are linked to products. Periodic Search Reports are auto-generated documenting search scope, results, and disposition.

5. **Periodic Safety Update Reports** — Auto-generated reports documenting all literature monitored within configurable time windows (monthly, quarterly, annually). Includes search strategy documentation, disposition of each finding (relevant/not relevant/actioned), and regulatory compliance artifacts for MDR/IVDR submissions.

The system reuses existing Celery infrastructure (`beat_schedule` for periodic tasks), existing Settings/config pattern for new environment variables, existing API router patterns, existing SQLAlchemy model patterns, the `LiteratureGatewayService` (Phase 9.1), `IngestionPipelineService` (Phase 9.2), `HybridQueryEngine` (Phase 9.3), `ContradictionDetectionService` and `LiteratureScreenerAgentRunner` (Phase 9.4), `AgentRegistryService` (Phase 5.1), `ImpactAnalysisService` (Phase 5.5), and BPMN workflow engine (Phase 3.1). All operations are company-scoped via `X-Company-Id` header, audit-logged for ALCOA+ compliance, and traceable with full execution parameter logging.

## Glossary

- **Vigilance_Monitor_Service**: The backend service responsible for orchestrating scheduled vigilance searches, dispatching signal detection analysis, managing product portfolios, and generating periodic safety reports.
- **Vigilance_Search_Profile**: A per-company, per-product configuration defining the search terms, MeSH descriptors, adverse event keywords, device identifiers, and scheduling parameters used for automated vigilance literature searches.
- **Medical_Product**: A registered medical device or product within a company's portfolio, containing regulatory metadata (device class, UDI, intended purpose, predicate devices, GMDN code) used to scope vigilance monitoring activities.
- **Vigilance_Signal**: A record generated when the Vigilance Analyst agent identifies a potential safety signal in newly retrieved literature, containing severity classification, evidence summary, regulatory references, and recommended actions.
- **Signal_Severity**: A classification level (critical, major, minor) indicating the potential patient safety or regulatory impact of a detected signal, aligned with MDR Article 87 serious incident criteria and MedDev 2.12/1 reporting thresholds.
- **Vigilance_Analyst_Agent**: A new agent archetype in the Modular Agent Registry (Phase 5.1) specialized in evaluating literature for medical device safety signals, applying regulatory severity criteria, and producing structured signal assessments.
- **Vigilance_Search_Execution**: A single scheduled or manual execution of a Vigilance_Search_Profile, recording the search parameters, timestamp, sources queried, results count, and disposition of each result.
- **Field_Safety_Corrective_Action (FSCA)**: A regulatory action taken by a manufacturer to reduce risk of death or serious deterioration in health associated with a medical device already on the market (per MDR Article 2(68)).
- **Periodic_Safety_Report**: An auto-generated report (PMSR/PSUR format) documenting all vigilance search activity within a configurable time window, including search strategy, results disposition, signal summary, and regulatory compliance artifacts.
- **Report_Period**: A configurable time window (monthly, quarterly, annually) defining the scope of a Periodic_Safety_Report for regulatory submission purposes.
- **Signal_Disposition**: The outcome classification for a detected signal: `confirmed` (genuine safety concern requiring action), `under_review` (requires further investigation), `dismissed` (false positive with documented rationale), or `escalated` (critical signal forwarded for immediate action).
- **UDI (Unique Device Identifier)**: A globally unique identifier assigned to a medical device per EU MDR/IVDR and FDA UDI System requirements, used as a primary linking key between products and vigilance activities.
- **MeSH_Term**: Medical Subject Headings controlled vocabulary terms from the National Library of Medicine, used to construct precise vigilance search queries for specific medical device domains.
- **GMDN_Code**: Global Medical Device Nomenclature code classifying the medical device type, used for regulatory reporting and search profile construction.
- **MDR_Article_87**: EU Medical Device Regulation 2017/745 Article 87 defining manufacturer reporting obligations for serious incidents and field safety corrective actions.
- **MEDDEV_2_12_1**: European Commission guideline on medical device vigilance systems, defining the criteria and procedures for reporting incidents and field safety corrective actions.
- **MEDDEV_2_7_1_Rev4**: European Commission guideline on clinical evaluation, including post-market clinical follow-up and literature review requirements for medical devices.
- **Company**: The multi-tenant entity (from Phase 1.1) to which all products, vigilance profiles, signals, and reports are scoped.
- **Literature_Gateway_Service**: The existing service (Phase 9.1) for executing literature searches against external APIs (PubMed, Crossref, arXiv), reused here for scheduled vigilance searches.
- **Ingestion_Pipeline_Service**: The existing service (Phase 9.2) for ingesting literature search results through the metadata → full-text → indexed pipeline.
- **Hybrid_Query_Engine**: The existing component (Phase 9.3) for combined BM25 keyword + kNN semantic similarity searches, used here for cross-referencing vigilance findings against internal documents.
- **Contradiction_Detection_Service**: The existing service (Phase 9.4) for detecting contradictions between external literature and internal documents, triggered here by critical vigilance signals.
- **ImpactAnalysisService**: The existing service (Phase 5.5) for computing change impact analysis, invoked here when critical signals require mandatory safety assessment.

## Requirements

### Requirement 1: Vigilance Analyst Agent Archetype Definition

**User Story:** As a quality manager, I want a specialized AI agent archetype for medical device vigilance signal assessment, so that I can automatically evaluate whether literature findings represent genuine safety signals requiring regulatory action.

#### Acceptance Criteria

1. THE Vigilance_Analyst_Agent SHALL be defined as a YAML file in the `agents/archetypes/` directory following the agent-definition-v2 JSON schema, with `schema_version: "2.0"`, `archetype: "Vigilance Analyst"`, `agent_type: "review"`, and all required fields (`name`, `description`, `system_prompt`, `dspy_modules`, `knowledge_scopes`).
2. THE Vigilance_Analyst_Agent SHALL include a `personality_profile` with `tone: "methodical and regulatory-focused"`, `verbosity: "detailed"`, `strictness: 0.95`, `domain_focus` including "medical-device-vigilance", "adverse-event-assessment", "post-market-surveillance", "regulatory-reporting", and "signal-detection", and a `communication_style` describing structured safety signal assessments with regulatory citations.
3. THE Vigilance_Analyst_Agent SHALL include a `system_prompt` instructing the agent to evaluate literature findings against a provided product profile and vigilance criteria, classify signal severity using MDR Article 87 serious incident criteria, determine whether the finding constitutes a reportable event under MEDDEV 2.12/1, and produce a JSON response with signal_detected (boolean), severity, evidence_summary, regulatory_references, recommended_actions, and confidence.
4. THE Vigilance_Analyst_Agent SHALL include an `evaluation_rubric` with criteria for: signal detection accuracy (weight 0.30), severity classification correctness (weight 0.25), regulatory citation relevance (weight 0.20), evidence quality (weight 0.15), and response formatting (weight 0.10), using `scoring_method: "weighted_average"`.
5. THE Vigilance_Analyst_Agent SHALL include `contextual_tuning` with `temperature: 0.05`, `max_tokens: 6144`, and `top_p: 0.90` to ensure highly deterministic and reproducible signal classification decisions.
6. THE Vigilance_Analyst_Agent SHALL be hot-reloadable at runtime via the existing watchfiles mechanism in the `AgentRegistryService` without requiring application restart.
7. THE Vigilance_Analyst_Agent SHALL include `knowledge_scopes` with tags `["Vigilance", "MedicalDevice", "AdverseEvent", "PostMarketSurveillance", "MDR", "IVDR"]` for knowledge retrieval scoping.

### Requirement 2: Medical Product Portfolio Management

**User Story:** As a quality manager, I want to register my company's medical devices with their regulatory metadata, so that vigilance monitoring can be scoped to specific products in our portfolio.

#### Acceptance Criteria

1. THE Medical_Product SHALL store: `name` (string, 1–300 characters), `udi` (string, 1–128 characters, optional, unique within company when provided), `device_class` (enum: "I", "IIa", "IIb", "III", "IVDR_A", "IVDR_B", "IVDR_C", "IVDR_D"), `gmdn_code` (string, 1–20 characters, optional), `intended_purpose` (text, max 5000 characters), `manufacturer_name` (string, 1–300 characters, optional), `predicate_devices` (array of strings, max 10 entries, each 1–300 characters, optional), `risk_class_justification` (text, max 3000 characters, optional), `status` (enum: "active", "discontinued", "recalled"), `company_id`, `created_by` (user_id), `created_at`, and `updated_at`.
2. WHEN a Medical_Product is created with a `udi` that already exists within the same company, THE system SHALL reject the request with HTTP 409 and an error message indicating a duplicate UDI.
3. WHEN a Medical_Product transitions to `discontinued` or `recalled` status, THE system SHALL retain all associated Vigilance_Search_Profiles but suspend their scheduled executions, and SHALL record the status change in the audit trail.
4. THE system SHALL support associating multiple Vigilance_Search_Profiles with a single Medical_Product, enabling different search strategies for different aspects of the device (e.g., biocompatibility vs. mechanical failure).
5. IF a user without the `document_admin` or `system_admin` role attempts to create, update, or delete a Medical_Product, THEN THE system SHALL reject the request with HTTP 403 and an error message indicating insufficient permissions.
6. WHEN a Medical_Product is created or updated, THE system SHALL validate that at least `name`, `device_class`, and `intended_purpose` are provided, rejecting requests with HTTP 422 if any required field is missing or empty.

### Requirement 3: Vigilance Search Profile Configuration

**User Story:** As a quality manager, I want to define targeted search profiles for each product in my portfolio, so that automated vigilance monitoring focuses on relevant adverse events and safety issues.

#### Acceptance Criteria

1. THE Vigilance_Search_Profile SHALL store: `name` (string, 1–200 characters), `product_id` (foreign key to Medical_Product), `search_terms` (array of strings, 1–50 entries, each 1–500 characters, containing product names, brand names, and synonyms), `mesh_terms` (array of strings, 0–30 entries, each 1–200 characters), `adverse_event_keywords` (array of strings, 1–50 entries, each 1–500 characters, containing adverse event descriptors), `device_identifiers` (array of strings, 0–20 entries, each 1–200 characters, containing UDIs, catalog numbers, model numbers), `exclusion_terms` (array of strings, 0–30 entries, each 1–500 characters), `source_ids` (array of source adapter identifiers to search, empty means all enabled sources), `schedule_cron` (string, valid cron expression), `status` (enum: "active", "paused", "archived"), `company_id`, `created_by`, `created_at`, and `updated_at`.
2. WHEN a Vigilance_Search_Profile is created, THE system SHALL validate the `schedule_cron` field against standard 5-field cron expression syntax and reject invalid expressions with HTTP 422.
3. WHEN a Vigilance_Search_Profile is activated (status set to `active`), THE system SHALL register it with the Celery beat scheduler using the specified `schedule_cron`, so that searches execute automatically at the configured intervals.
4. WHEN a Vigilance_Search_Profile is paused or archived, THE system SHALL remove it from the Celery beat scheduler, ceasing automated search execution while preserving all historical execution records.
5. THE system SHALL support manual (on-demand) execution of any Vigilance_Search_Profile regardless of its status, allowing quality managers to trigger searches outside the scheduled interval.
6. WHEN a Vigilance_Search_Profile is created, THE system SHALL validate that at least one entry exists in `search_terms` and at least one entry exists in `adverse_event_keywords`, rejecting requests with HTTP 422 if either is empty.
7. IF a user without the `document_admin` or `system_admin` role attempts to create, update, or delete a Vigilance_Search_Profile, THEN THE system SHALL reject the request with HTTP 403.
8. WHEN a Vigilance_Search_Profile's `product_id` references a Medical_Product with status `discontinued` or `recalled`, THE system SHALL accept the profile creation but set its status to `paused` and log an informational warning in the audit trail.

### Requirement 4: Scheduled Vigilance Search Execution

**User Story:** As a quality manager, I want my vigilance search profiles to execute automatically on schedule, so that new adverse event literature is detected without manual intervention.

#### Acceptance Criteria

1. WHEN a Vigilance_Search_Profile's scheduled time arrives (per its `schedule_cron`), THE Vigilance_Monitor_Service SHALL dispatch a Celery task on the `literature_ingestion` queue that constructs a Search_Query from the profile's search_terms, mesh_terms, adverse_event_keywords, and device_identifiers, combining them with Boolean AND/OR logic (terms within a category ORed, categories ANDed with adverse_event_keywords).
2. THE Vigilance_Monitor_Service SHALL execute the constructed Search_Query against all enabled Source_Adapters for the company (or only those specified in `source_ids` if non-empty), via the existing Literature_Gateway_Service, respecting rate limits and circuit breakers.
3. WHEN search results are returned, THE Vigilance_Monitor_Service SHALL filter out results that match any `exclusion_terms` in title or abstract (case-insensitive substring match), and SHALL auto-ingest remaining results via the Ingestion_Pipeline_Service, creating Ingestion_Records linked to the originating Vigilance_Search_Execution.
4. THE Vigilance_Monitor_Service SHALL create a Vigilance_Search_Execution record for each execution containing: `profile_id`, `company_id`, `execution_timestamp` (UTC), `search_parameters` (full query as JSON), `sources_queried` (array of source adapter names), `total_results_found` (integer), `results_after_exclusion` (integer), `results_ingested` (integer), `results_duplicate` (integer, matching existing Ingestion_Records), `execution_duration_ms` (integer), and `status` (completed, partial_failure, failed).
5. WHEN a scheduled search returns zero results, THE Vigilance_Monitor_Service SHALL record the execution as `completed` with `total_results_found: 0` and proceed without error.
6. IF the Literature_Gateway_Service is unavailable or all source adapters fail during a scheduled execution, THEN THE Vigilance_Monitor_Service SHALL retry the execution up to 3 times with exponential backoff (5 minutes, 15 minutes, 60 minutes) before marking the execution as `failed` and recording the failure in the audit trail.
7. THE Vigilance_Monitor_Service SHALL deduplicate results against existing Ingestion_Records (same company_id and DOI, or same company_id, source_id, and external_id) before ingestion, recording the duplicate count in the Vigilance_Search_Execution record.
8. WHEN the Celery beat scheduler starts or restarts, THE Vigilance_Monitor_Service SHALL load all Vigilance_Search_Profiles with status `active` and register their cron schedules dynamically, without requiring hardcoded beat_schedule entries.

### Requirement 5: Signal Detection and Analysis

**User Story:** As a quality manager, I want newly retrieved vigilance literature automatically analyzed for genuine safety signals, so that potential adverse events are identified and classified without manual screening of every paper.

#### Acceptance Criteria

1. WHEN an Ingestion_Record linked to a Vigilance_Search_Execution transitions to the `indexed` state (embedding generation complete), THE Vigilance_Monitor_Service SHALL dispatch a signal detection task on the `ai_operations` queue, passing the Ingestion_Record content and the associated Vigilance_Search_Profile's product metadata to the Vigilance_Analyst_Agent.
2. THE Vigilance_Analyst_Agent SHALL evaluate the literature content against the linked Medical_Product's intended purpose, device class, and known risk profile, producing a structured assessment containing: `signal_detected` (boolean), `severity` (critical, major, minor, or null if no signal), `evidence_summary` (text, max 3000 characters), `affected_product_aspects` (array of strings describing which device functions/components are implicated), `regulatory_references` (array of applicable regulation articles, e.g., "MDR Article 87(1)(a)"), `recommended_actions` (array of strings, max 5 actions), `confidence` (float 0.0–1.0), and `analysis_duration_ms` (integer).
3. WHEN the Vigilance_Analyst_Agent determines `signal_detected: true` with `confidence >= 0.7`, THE Vigilance_Monitor_Service SHALL create a Vigilance_Signal record with: ingestion_record_id, product_id, profile_id, company_id, severity, evidence_summary, affected_product_aspects, regulatory_references, recommended_actions, confidence, detection_timestamp, and disposition (initial: "under_review").
4. WHEN the Vigilance_Analyst_Agent determines `signal_detected: false` or `confidence < 0.7`, THE system SHALL record the analysis result in the Vigilance_Search_Execution's result disposition as "no_signal" with the confidence score, without creating a Vigilance_Signal record.
5. IF the Vigilance_Analyst_Agent returns a response that does not conform to the expected JSON schema, THEN THE system SHALL mark the analysis as `uncertain`, log the malformed response in the audit trail, and flag the Ingestion_Record for manual review.
6. IF the vLLM instance is unavailable during signal detection, THEN THE system SHALL retry up to 3 times with exponential backoff (30 seconds, 2 minutes, 10 minutes) before marking the detection task as failed and flagging the Ingestion_Record for manual review.
7. THE system SHALL support batch signal detection: when multiple Ingestion_Records from the same Vigilance_Search_Execution reach the `indexed` state, process them in configurable batches (default: 10, range: 1–50) to avoid overwhelming the vLLM instance.

### Requirement 6: Signal Severity Classification

**User Story:** As a quality manager, I want vigilance signals classified by regulatory severity criteria, so that I can prioritize responses according to MDR/IVDR reporting obligations.

#### Acceptance Criteria

1. THE Vigilance_Analyst_Agent SHALL classify signal severity using the following regulatory-aligned criteria: `critical` — the finding describes a death, serious injury, or serious public health threat directly attributable to the device, or a systematic failure requiring immediate FSCA (aligned with MDR Article 87(1) serious incident definition); `major` — the finding describes a non-serious adverse event, near-miss, or emerging trend that could escalate to a serious incident if unaddressed (aligned with MEDDEV 2.12/1 trend reporting); `minor` — the finding describes a complaint, performance issue, or isolated event with low likelihood of patient harm that warrants monitoring but not immediate action.
2. WHEN a Vigilance_Signal with severity `critical` is created, THE system SHALL apply escalation rules as defined in Requirement 7 within 60 seconds of signal creation.
3. WHEN a Vigilance_Signal with severity `major` is created, THE system SHALL flag it for priority human review and include it in the next daily vigilance summary notification to Document Admins.
4. THE Vigilance_Signal SHALL support disposition transitions: `under_review` → `confirmed`, `under_review` → `dismissed`, `under_review` → `escalated`, `confirmed` → `escalated`, where `dismissed` requires a `dismissal_reason` (text, max 2000 characters) and reviewer user_id, and `confirmed` requires a `confirmation_note` (text, max 3000 characters) and reviewer user_id.
5. IF a user without the `document_admin` or `system_admin` role attempts to transition a Vigilance_Signal's disposition, THEN THE system SHALL reject the request with HTTP 403.
6. THE system SHALL maintain a running count of open (disposition: `under_review` or `confirmed`) Vigilance_Signals per company per product, exposed via the vigilance signals summary endpoint, grouped by severity.

### Requirement 7: GxP Alerting and Escalation

**User Story:** As a quality manager, I want critical vigilance signals to trigger immediate escalation including mandatory impact analysis and stakeholder notification, so that potential serious incidents receive timely regulatory response.

#### Acceptance Criteria

1. WHEN a Vigilance_Signal with severity `critical` is created or transitions to disposition `escalated`, THE system SHALL automatically invoke the ImpactAnalysisService with the linked Medical_Product's associated internal documents (SOPs, validation plans referencing the product), creating a mandatory Change Impact Analysis task and linking it to the Vigilance_Signal.
2. WHEN a Vigilance_Signal with severity `critical` is created, THE system SHALL dispatch an immediate notification to all users with the `document_admin` or `system_admin` role within the affected company, containing: signal_id, product_name, severity, evidence_summary (truncated to 500 characters), regulatory_references, and a direct link to the signal detail view.
3. WHEN a Vigilance_Signal with severity `critical` is created, THE system SHALL invoke the Contradiction_Detection_Service to cross-reference the underlying literature against internal product documentation, creating Contradiction_Alerts if discrepancies are found between the external adverse event evidence and internal safety claims.
4. WHEN a Vigilance_Signal with severity `critical` is created and the company has active SLR_Reviews associated with the same Medical_Product, THE system SHALL automatically add the underlying Ingestion_Record to the relevant SLR_Review's record set for inclusion in the systematic review.
5. WHEN a Vigilance_Signal triggers escalation, THE system SHALL record the full escalation chain in the audit trail: signal_id, escalation_timestamp, impact_analysis_task_id (if created), contradiction_alert_ids (if created), notification_recipient_user_ids, and the triggering severity/disposition.
6. IF the ImpactAnalysisService is unavailable during escalation, THEN THE system SHALL queue the impact analysis request for retry (up to 3 attempts with 5-minute intervals) and SHALL NOT block the notification or contradiction detection steps.
7. THE system SHALL support configuring escalation thresholds per company: `critical_signal_auto_escalate` (boolean, default: true), `major_signal_daily_digest` (boolean, default: true), and `escalation_notification_channels` (array, currently: "in_app"), stored in the company's vigilance configuration.

### Requirement 8: Periodic Safety Report Generation

**User Story:** As a quality manager, I want the system to automatically generate periodic safety reports documenting all vigilance monitoring activity, so that I have regulatory-compliant documentation ready for MDR/IVDR submission.

#### Acceptance Criteria

1. THE system SHALL support configurable report periods per Medical_Product: `monthly`, `quarterly`, or `annually`, stored in the product's vigilance configuration, with a `report_generation_day` (integer, 1–28) specifying the day of the period when the report is auto-generated.
2. WHEN the report generation day arrives for a Medical_Product's configured period, THE Vigilance_Monitor_Service SHALL auto-generate a Periodic_Safety_Report containing: product metadata (name, UDI, device class, intended purpose), reporting period dates, all Vigilance_Search_Executions within the period (with parameters, sources, result counts), all Vigilance_Signals detected within the period (with severity, disposition, and resolution notes), search strategy documentation (listing all active profiles and their query construction), and a statistical summary (total searches, total results, signals by severity, disposition breakdown).
3. THE Periodic_Safety_Report SHALL include a regulatory compliance section documenting: applicable regulations (MDR/IVDR articles), MEDDEV guideline references, confirmation that search strategy covers the device's intended purpose and known risk areas, and a statement of completeness (all scheduled searches executed or documented failures).
4. THE Periodic_Safety_Report SHALL include a disposition matrix showing every search result's final classification: `no_signal` (dismissed by agent with low confidence), `signal_dismissed` (signal created but dismissed by human reviewer), `signal_confirmed` (genuine signal under action), `signal_escalated` (critical signal with full escalation), enabling auditors to trace the handling of every identified paper.
5. THE system SHALL store generated Periodic_Safety_Reports as structured JSON records with: `report_id`, `product_id`, `company_id`, `period_start`, `period_end`, `generated_at`, `report_content` (full JSON body), `status` (generated, reviewed, approved, submitted), and `version` (integer, incremented on edits).
6. THE Periodic_Safety_Report SHALL support status transitions: `generated` → `reviewed` → `approved` → `submitted`, where each transition records the acting user_id, timestamp, and optional comment, and only users with `document_admin` or `system_admin` role can advance status.
7. IF no Vigilance_Search_Executions occurred during a reporting period (all profiles were paused or the product was discontinued), THE system SHALL still generate a report with an explicit "No searches executed" section documenting the reason, maintaining regulatory traceability.

### Requirement 9: API Endpoints for Product Portfolio Management

**User Story:** As a developer building the vigilance UI (Phase 9.6), I want RESTful API endpoints for managing medical products and their vigilance profiles, so that the frontend can provide CRUD operations on the product portfolio.

#### Acceptance Criteria

1. THE system SHALL expose a `POST /api/vigilance/products` endpoint accepting a JSON body with all Medical_Product fields (name, udi, device_class, gmdn_code, intended_purpose, manufacturer_name, predicate_devices, risk_class_justification), returning HTTP 201 with the created product on success.
2. THE system SHALL expose a `GET /api/vigilance/products` endpoint returning a paginated list of Medical_Products for the requesting company, supporting `page` (integer, default 1), `page_size` (integer, 1–100, default 20), `status` filter (active, discontinued, recalled), and `device_class` filter.
3. THE system SHALL expose a `GET /api/vigilance/products/{product_id}` endpoint returning full product details including associated Vigilance_Search_Profiles and signal counts by severity.
4. THE system SHALL expose a `PUT /api/vigilance/products/{product_id}` endpoint accepting updated product fields, returning HTTP 200 with the updated product.
5. THE system SHALL expose a `DELETE /api/vigilance/products/{product_id}` endpoint that transitions the product status to `discontinued` (soft delete) rather than physically deleting, returning HTTP 200 on success.
6. THE system SHALL expose a `POST /api/vigilance/products/{product_id}/profiles` endpoint accepting a JSON body with all Vigilance_Search_Profile fields, returning HTTP 201 with the created profile linked to the specified product.
7. THE system SHALL expose a `GET /api/vigilance/products/{product_id}/profiles` endpoint returning all Vigilance_Search_Profiles associated with the product, supporting `status` filter (active, paused, archived).
8. THE system SHALL expose a `PUT /api/vigilance/profiles/{profile_id}` endpoint accepting updated profile fields, returning HTTP 200 with the updated profile.
9. THE system SHALL expose a `POST /api/vigilance/profiles/{profile_id}/execute` endpoint triggering an immediate (manual) execution of the profile's search, returning HTTP 202 with a task_id for progress tracking.
10. WHEN any mutation endpoint (POST, PUT, DELETE) is called, THE system SHALL require the X-Change-Reason header and return HTTP 400 if it is missing or empty.
11. IF the `product_id` or `profile_id` does not exist or belongs to a different company, THEN THE system SHALL return HTTP 404 with a generic "not found" message without revealing cross-tenant information.

### Requirement 10: API Endpoints for Vigilance Signals and Escalation

**User Story:** As a developer building the vigilance UI, I want RESTful API endpoints for viewing and managing vigilance signals, so that the frontend can present actionable safety findings to quality managers.

#### Acceptance Criteria

1. THE system SHALL expose a `GET /api/vigilance/signals` endpoint returning paginated Vigilance_Signals for the requesting company, supporting filtering by `severity` (critical, major, minor), `disposition` (under_review, confirmed, dismissed, escalated), `product_id`, and `profile_id`, ordered by severity descending then detection_timestamp descending.
2. THE system SHALL expose a `GET /api/vigilance/signals/{signal_id}` endpoint returning full signal details including: literature paper metadata, product metadata, evidence_summary, regulatory_references, recommended_actions, confidence, disposition history, linked impact analysis reports, and linked contradiction alerts.
3. THE system SHALL expose a `PUT /api/vigilance/signals/{signal_id}/disposition` endpoint accepting `disposition` (confirmed, dismissed, escalated), optional `confirmation_note` or `dismissal_reason`, returning HTTP 200 on success.
4. THE system SHALL expose a `GET /api/vigilance/signals/summary` endpoint returning aggregate statistics: total open signals by severity by product, signals escalated this period, average time-to-disposition, and trend data (signals per month over last 12 months).
5. THE system SHALL expose a `GET /api/vigilance/executions` endpoint returning paginated Vigilance_Search_Executions for the requesting company, supporting filtering by `profile_id`, `product_id`, `status` (completed, partial_failure, failed), and `date_range` (from/to ISO-8601 dates).
6. THE system SHALL expose a `GET /api/vigilance/executions/{execution_id}` endpoint returning full execution details including: search parameters, sources queried, result counts, ingested record references, and signal detection outcomes.
7. WHEN any mutation endpoint (PUT) is called, THE system SHALL require the X-Change-Reason header and return HTTP 400 if missing or empty.
8. THE system SHALL require at least the `member` role for read endpoints and at least the `document_admin` role for disposition changes, returning HTTP 403 when the caller lacks the required role.
9. IF the `signal_id` or `execution_id` does not exist or belongs to a different company, THEN THE system SHALL return HTTP 404 with a generic "not found" message without revealing cross-tenant information.

### Requirement 11: API Endpoints for Periodic Safety Reports

**User Story:** As a developer building the vigilance UI, I want RESTful API endpoints for viewing and managing periodic safety reports, so that quality managers can review, approve, and submit compliance documentation.

#### Acceptance Criteria

1. THE system SHALL expose a `GET /api/vigilance/reports` endpoint returning paginated Periodic_Safety_Reports for the requesting company, supporting filtering by `product_id`, `status` (generated, reviewed, approved, submitted), and `period` (monthly, quarterly, annually), ordered by generated_at descending.
2. THE system SHALL expose a `GET /api/vigilance/reports/{report_id}` endpoint returning the full report content including all sections (product metadata, search executions, signals, disposition matrix, regulatory compliance, statistical summary).
3. THE system SHALL expose a `PUT /api/vigilance/reports/{report_id}/status` endpoint accepting `status` (reviewed, approved, submitted) and optional `comment` (text, max 2000 characters), advancing the report through its lifecycle and returning HTTP 200 on success.
4. THE system SHALL expose a `POST /api/vigilance/reports/generate` endpoint accepting `product_id`, `period_start` (ISO-8601 date), and `period_end` (ISO-8601 date), triggering manual generation of a Periodic_Safety_Report for the specified range, returning HTTP 202 with a task_id.
5. WHEN any mutation endpoint (PUT, POST) is called, THE system SHALL require the X-Change-Reason header and return HTTP 400 if missing or empty.
6. THE system SHALL require at least the `member` role for read endpoints and at least the `document_admin` role for status transitions and report generation, returning HTTP 403 when the caller lacks the required role.
7. IF the `report_id` does not exist or belongs to a different company, THEN THE system SHALL return HTTP 404 with a generic "not found" message without revealing cross-tenant information.

### Requirement 12: Audit Trail for Vigilance Operations

**User Story:** As a quality manager, I want all vigilance monitoring activities logged in the audit trail, so that I can demonstrate the integrity of our post-market surveillance process during regulatory audits and inspections.

#### Acceptance Criteria

1. WHEN a Vigilance_Search_Execution completes (any status), THE Audit_Logger SHALL create an append-only entry containing: execution_id, profile_id, product_id, company_id, sources_queried, total_results_found, results_ingested, execution_duration_ms, status, and a UTC timestamp.
2. WHEN a Vigilance_Signal is created, THE Audit_Logger SHALL create an append-only entry containing: signal_id, ingestion_record_id, product_id, profile_id, company_id, severity, confidence, detection_duration_ms, and a UTC timestamp.
3. WHEN a Vigilance_Signal disposition changes, THE Audit_Logger SHALL create an append-only entry containing: signal_id, company_id, previous_disposition, new_disposition, acting_user_id, confirmation_note or dismissal_reason (if applicable), and a UTC timestamp.
4. WHEN an escalation is triggered for a Vigilance_Signal, THE Audit_Logger SHALL create an append-only entry containing: signal_id, company_id, escalation_type (impact_analysis, contradiction_check, notification, slr_inclusion), target_service_invoked, success (boolean), and a UTC timestamp.
5. WHEN a Periodic_Safety_Report is generated or its status changes, THE Audit_Logger SHALL create an append-only entry containing: report_id, product_id, company_id, period_start, period_end, action (generated, status_change), new_status, acting_user_id (null for auto-generation), and a UTC timestamp.
6. WHEN a Medical_Product or Vigilance_Search_Profile is created, updated, or status-changed, THE Audit_Logger SHALL create an append-only entry containing: entity_type (product, profile), entity_id, company_id, action (create, update, status_change), acting_user_id, changed_fields (array of field names), and a UTC timestamp.
7. THE Audit_Logger SHALL never log full literature content, full internal document content, or LLM prompt/response text in vigilance audit records; only metadata identifiers, classifications, and metrics SHALL be logged.
8. THE Audit_Logger SHALL store all vigilance audit records as append-only entries that cannot be modified or deleted through application-level operations, preserving ALCOA+ Original and Enduring principles.

### Requirement 13: Error Handling and Resilience

**User Story:** As a system administrator, I want the vigilance monitoring pipeline to handle failures gracefully, so that temporary service outages do not miss critical adverse event literature or corrupt surveillance records.

#### Acceptance Criteria

1. IF the Literature_Gateway_Service is unavailable during a scheduled vigilance search, THEN THE Vigilance_Monitor_Service SHALL retry the execution up to 3 times with exponential backoff (5 minutes, 15 minutes, 60 minutes) before marking the execution as `failed`, recording the failure in the audit trail, and scheduling an automatic retry at the next scheduled interval.
2. IF the Ingestion_Pipeline_Service is unavailable when attempting to ingest vigilance search results, THEN THE Vigilance_Monitor_Service SHALL queue the ingestion request for retry (up to 5 attempts over 2 hours) and SHALL NOT mark the Vigilance_Search_Execution as failed until all retries are exhausted.
3. IF the vLLM instance is unavailable during signal detection analysis, THEN THE system SHALL retry up to 3 times with exponential backoff (30 seconds, 2 minutes, 10 minutes) before marking the detection as failed and flagging the Ingestion_Record for manual review without affecting other pending detections in the same batch.
4. THE system SHALL implement idempotent vigilance search execution: if a scheduled search fires while a previous execution for the same profile is still in progress, THE system SHALL skip the duplicate execution and log an informational message in the audit trail.
5. IF the Celery beat scheduler restarts, THE Vigilance_Monitor_Service SHALL detect any Vigilance_Search_Executions that were in progress at the time of shutdown (status: `running`) and SHALL re-queue them for completion, processing from the last successful step.
6. THE system SHALL enforce a maximum execution time of 60 minutes per vigilance search execution; IF an execution exceeds this timeout, THEN the system SHALL mark it as `partial_failure`, persist all results obtained so far, and log the timeout in the audit trail.
7. WHEN any retry attempt is made for vigilance operations (search execution, ingestion, signal detection, escalation), THE system SHALL log the retry attempt number, the error that triggered the retry, the backoff duration, and the affected entity IDs in the audit trail.
8. IF the Contradiction_Detection_Service or ImpactAnalysisService is unavailable during escalation, THEN THE system SHALL queue the escalation sub-tasks independently, allowing notifications to proceed while service-dependent tasks retry separately.

### Requirement 14: Environment and Deployment Configuration

**User Story:** As a system administrator, I want all vigilance monitoring settings configurable via environment variables, so that deployment across environments requires no code changes.

#### Acceptance Criteria

1. THE system SHALL read the Celery queue name for vigilance search tasks from `ALC_VIGILANCE_SEARCH_QUEUE` environment variable (default: `literature_ingestion`), accepting only non-empty string values.
2. THE system SHALL read the Celery queue name for signal detection tasks from `ALC_VIGILANCE_SIGNAL_QUEUE` environment variable (default: `ai_operations`), accepting only non-empty string values.
3. THE system SHALL read the default signal detection confidence threshold from `ALC_VIGILANCE_SIGNAL_CONFIDENCE_THRESHOLD` environment variable (default: 0.7), accepting float values between 0.1 and 1.0.
4. THE system SHALL read the maximum concurrent signal detection tasks per company from `ALC_VIGILANCE_MAX_CONCURRENT_DETECTIONS` environment variable (default: 5), accepting integer values between 1 and 50.
5. THE system SHALL read the vigilance search execution timeout in seconds from `ALC_VIGILANCE_SEARCH_TIMEOUT` environment variable (default: 3600, representing 60 minutes), accepting integer values of 300 or greater.
6. THE system SHALL read the signal detection batch size from `ALC_VIGILANCE_SIGNAL_BATCH_SIZE` environment variable (default: 10), accepting integer values between 1 and 50.
7. THE system SHALL read the escalation notification retry attempts from `ALC_VIGILANCE_ESCALATION_RETRIES` environment variable (default: 3), accepting integer values between 1 and 10.
8. THE system SHALL read the periodic report auto-generation enabled flag from `ALC_VIGILANCE_AUTO_REPORT_ENABLED` environment variable (default: true), accepting boolean string values ("true", "false", "1", "0").
9. IF any numeric environment variable contains a non-numeric value or a value outside its accepted range, THEN THE system SHALL refuse to start and log an error message at ERROR level to standard error indicating the invalid variable name, its provided value, and its accepted range.
10. WHEN the system starts successfully, THE system SHALL log the resolved values of all Phase 9.5 configuration variables at INFO level.

### Requirement 15: Vigilance Data Round-Trip Integrity

**User Story:** As a developer, I want to verify that vigilance signals, search executions, and product registrations produced by the system are accurately persisted and retrievable, so that no safety-critical data is lost or corrupted in the pipeline.

#### Acceptance Criteria

1. FOR ALL Vigilance_Signals produced by the Vigilance_Analyst_Agent with a valid severity (critical, major, minor) and confidence (0.0–1.0), persisting the signal to the database and retrieving it by ID SHALL yield a record with identical severity, confidence (within floating-point precision tolerance of 1e-6), evidence_summary, affected_product_aspects array, regulatory_references array, and recommended_actions array.
2. FOR ALL Medical_Products with valid device_class and non-empty name and intended_purpose, serializing the product to JSON for API response and deserializing it back SHALL produce an equivalent object with identical field values (serialization round-trip property).
3. FOR ALL Vigilance_Search_Profiles with valid cron expressions and non-empty search_terms and adverse_event_keywords, serializing the profile to JSON for API response and deserializing it back SHALL produce an equivalent object with identical field values including all array fields preserving order.
4. FOR ALL Periodic_Safety_Reports, the statistical summary SHALL satisfy the invariant: `total_results_found >= results_after_exclusion >= results_ingested`, and the disposition matrix SHALL account for every ingested result exactly once (sum of all disposition categories equals results_ingested).
5. FOR ALL Vigilance_Search_Executions, the invariant `total_results_found >= results_after_exclusion >= results_ingested + results_duplicate` SHALL hold, ensuring no results are unaccounted for in the execution record.
6. WHEN verifying round-trip integrity via property-based tests, THE system SHALL execute a minimum of 100 Hypothesis-generated examples per property, covering Vigilance_Signals with varying severities, confidence levels across the full 0.0–1.0 range, evidence_summary texts of varying lengths (empty to 3000 characters), and regulatory_references arrays of varying sizes (0 to 10 elements).
