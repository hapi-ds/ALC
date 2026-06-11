# Requirements Document

## Introduction

This document specifies the requirements for Phase 9.4 — AI-Powered Literature Review & Synthesis Agents — of AlcoaBase. This feature builds on the Automated Ingestion Pipeline (Phase 9.2) and High-Dimensional Embedding & Hybrid Indexing (Phase 9.3) by introducing intelligent agents that automate systematic literature review workflows and detect contradictions between external scientific findings and internal corporate processes.

Phase 9.4 introduces two major capabilities:

1. **Literature Screener Agent** — A new agent archetype registered in the Modular Agent Registry (Phase 5.1) that screens ingested literature records against user-defined inclusion/exclusion criteria (PICO framework or custom), producing structured screening decisions to automate Systematic Literature Reviews (SLRs).

2. **Contradiction & Novelty Flagging** — An extension to the existing Master Auditor Agent (Phase 5.2) and `ReviewPipelineService` that cross-references newly ingested and indexed literature against internal SOPs, URS documents, and validation plans using the `Hybrid_Query_Engine` (Phase 9.3), automatically detecting contradictions and novel findings that may require internal process updates.

The system reuses the existing `ReviewPipelineService`, `IngestionPipelineService`, `Hybrid_Query_Engine`, `InferenceClient`, `AgentRegistryService`, `ImpactAnalysisService`, and Celery task infrastructure from prior phases. All operations are scoped to company tenants via the `X-Company-Id` header and logged in the audit trail for ALCOA+ compliance.

## Glossary

- **Literature_Screener_Agent**: A new agent archetype in the Modular Agent Registry (Phase 5.1) that evaluates ingested literature records against user-defined screening criteria and produces structured include/exclude/uncertain decisions with rationale.
- **Screening_Protocol**: A per-company configuration defining the inclusion and exclusion criteria for a systematic literature review, supporting PICO framework fields, custom keyword patterns, date ranges, and regex-based rules.
- **Screening_Decision**: The structured output of the Literature_Screener_Agent for a single Ingestion_Record, containing a verdict (include, exclude, uncertain), confidence score, rationale text, and matched/unmatched criteria references.
- **SLR_Review**: A Systematic Literature Review workflow instance that tracks the screening of a defined set of Ingestion_Records against a Screening_Protocol, recording progress, decisions, and generating PRISMA-style flow statistics.
- **PICO_Criteria**: A structured representation of Population, Intervention, Comparison, and Outcome criteria used in evidence-based systematic reviews to define inclusion/exclusion boundaries.
- **Contradiction_Alert**: A record generated when the Contradiction_Detection_Service identifies that an external scientific finding in newly ingested literature contradicts an internal document (SOP, URS, or validation plan).
- **Contradiction_Detection_Service**: The service that cross-references newly indexed literature against internal corporate documents using the Hybrid_Query_Engine, dispatches LLM-based analysis for contradiction identification, and generates Contradiction_Alerts with severity classifications.
- **Novelty_Flag**: A record generated when the Contradiction_Detection_Service identifies that a newly ingested paper presents findings not covered by any existing internal document within the company's knowledge base.
- **Contradiction_Severity**: A classification level (critical, major, minor) indicating the potential impact of a contradiction between external literature and internal processes on regulatory compliance and patient safety.
- **PRISMA_Flow**: A standardized reporting structure (Preferred Reporting Items for Systematic Reviews and Meta-Analyses) tracking the number of records at each screening stage: identified, screened, eligible, and included.
- **Screening_Run**: A single execution of the Literature_Screener_Agent against a batch of Ingestion_Records using a specific Screening_Protocol, dispatched as a Celery task.
- **Inter_Rater_Reliability**: A metric comparing screening decisions between the Literature_Screener_Agent and human reviewers (or between multiple screening runs with different criteria) to assess consistency.
- **Cross_Reference_Task**: A Celery task dispatched when an Ingestion_Record reaches the `indexed` state, which triggers the Contradiction_Detection_Service to search for related internal documents and analyze potential contradictions.
- **Company**: The multi-tenant entity (from Phase 1.1) to which all screening protocols, SLR reviews, contradiction alerts, and operations are scoped.
- **ReviewPipelineService**: The existing service (Phase 5.2) that orchestrates multi-agent document review, extended here to support literature contradiction analysis workflows.
- **Hybrid_Query_Engine**: The existing component (Phase 9.3) that executes combined BM25 keyword + kNN semantic similarity searches, used here for finding internal documents related to newly ingested literature.
- **ImpactAnalysisService**: The existing service (Phase 5.5) that computes change deltas and classifies impact severity, linked here for downstream processing of critical contradictions.

## Requirements

### Requirement 1: Literature Screener Agent Archetype Definition

**User Story:** As a quality manager, I want a specialized AI agent archetype for literature screening, so that I can automate the initial triage of papers in systematic literature reviews.

#### Acceptance Criteria

1. THE Literature_Screener_Agent SHALL be defined as a YAML file in the `agents/archetypes/` directory following the agent-definition-v2 JSON schema, with `schema_version: "2.0"`, `archetype: "Literature Screener"`, `agent_type: "review"`, and all required fields (`name`, `description`, `system_prompt`, `dspy_modules`, `knowledge_scopes`).
2. THE Literature_Screener_Agent SHALL include a `personality_profile` with `tone: "analytical and evidence-based"`, `verbosity: "detailed"`, `strictness: 0.9`, `domain_focus` including "systematic-review", "literature-screening", "evidence-assessment", and "PICO-analysis"`, and a `communication_style` describing structured evidence assessments.
3. THE Literature_Screener_Agent SHALL include a `system_prompt` instructing the agent to evaluate a paper's title, abstract, and available full-text against provided inclusion/exclusion criteria, produce a JSON response with verdict, confidence, rationale, and criteria matching details, and specify the expected output JSON schema within the prompt.
4. THE Literature_Screener_Agent SHALL include an `evaluation_rubric` with criteria for: screening accuracy (weight 0.35), rationale quality (weight 0.25), criteria coverage (weight 0.20), consistency (weight 0.10), and response formatting (weight 0.10), using `scoring_method: "weighted_average"`.
5. THE Literature_Screener_Agent SHALL include `contextual_tuning` with `temperature: 0.1`, `max_tokens: 4096`, and `top_p: 0.95` to ensure consistent and reproducible screening decisions.
6. THE Literature_Screener_Agent SHALL be hot-reloadable at runtime via the existing watchfiles mechanism in the `AgentRegistryService` without requiring application restart.
7. THE Literature_Screener_Agent SHALL include `knowledge_scopes` with tags `["Literature", "SystematicReview", "Screening", "PICO"]` for knowledge retrieval scoping.

### Requirement 2: Screening Protocol Management

**User Story:** As a quality manager, I want to define and manage screening protocols with inclusion/exclusion criteria, so that I can configure systematic literature reviews tailored to my research questions.

#### Acceptance Criteria

1. THE Screening_Protocol SHALL support PICO framework fields: `population` (text, max 2000 characters), `intervention` (text, max 2000 characters), `comparison` (text, max 2000 characters, optional), and `outcome` (text, max 2000 characters), each accepting natural language descriptions of the criteria.
2. THE Screening_Protocol SHALL support custom inclusion criteria as a list of up to 20 keyword patterns, where each pattern is a string of 1–500 characters that may contain plain text terms or POSIX-compatible regular expressions prefixed with `regex:`.
3. THE Screening_Protocol SHALL support custom exclusion criteria as a list of up to 20 keyword patterns following the same format as inclusion criteria.
4. THE Screening_Protocol SHALL support date range filtering with optional `publication_date_from` and `publication_date_to` fields (ISO-8601 date format), restricting screening to papers published within the specified range.
5. THE Screening_Protocol SHALL support publication type filtering with an optional `allowed_publication_types` field (array of strings from: "article", "review", "meta-analysis", "conference_paper", "preprint", "book_chapter", "case_report", "guideline"), restricting screening to specified types.
6. THE Screening_Protocol SHALL support language filtering with an optional `allowed_languages` field (array of ISO 639-1 language codes, default: all languages accepted).
7. THE Screening_Protocol SHALL store a `name` (string, 1–200 characters), `description` (text, max 5000 characters, optional), `version` (integer, auto-incremented on update), `status` (draft, active, archived), `company_id`, `created_by` (user_id), `created_at`, and `updated_at`.
8. WHEN a Screening_Protocol is updated while in `active` status with associated SLR_Reviews in progress, THE system SHALL create a new version of the protocol and associate it with subsequent screening runs while preserving the original version for in-progress reviews.
9. IF a user without the `document_admin` or `system_admin` role attempts to create, update, or delete a Screening_Protocol, THEN THE system SHALL reject the request with HTTP 403 and an error message indicating insufficient permissions.
10. WHEN a Screening_Protocol is created or updated, THE system SHALL validate that at least one criterion is defined (at minimum one of: any PICO field populated, at least one inclusion criterion, or at least one exclusion criterion), rejecting requests with HTTP 422 if no criteria are specified.

### Requirement 3: Automated Literature Screening Execution

**User Story:** As a quality manager, I want to automatically screen batches of ingested papers against my defined criteria, so that I can efficiently triage hundreds of papers without manual review of each one.

#### Acceptance Criteria

1. WHEN a Screening_Run is initiated, THE Literature_Screener_Agent SHALL evaluate each Ingestion_Record in the batch by constructing a prompt containing the paper's title, abstract (and full-text body sections if available and `indexed` state reached), and the Screening_Protocol criteria, then dispatching the prompt to the vLLM instance via the existing InferenceClient.
2. THE Literature_Screener_Agent SHALL produce a Screening_Decision for each evaluated Ingestion_Record containing: `verdict` (enum: "include", "exclude", "uncertain"), `confidence` (float 0.0–1.0), `rationale` (text, max 2000 characters), `matched_inclusion_criteria` (array of criterion indices that matched), `matched_exclusion_criteria` (array of criterion indices that matched), and `screening_duration_ms` (integer).
3. THE system SHALL process Screening_Runs as Celery tasks on the `ai_operations` queue, with configurable batch sizes (integer, default: 20, range: 1–100), dispatching one task per batch to avoid overwhelming the vLLM instance.
4. WHEN a Screening_Run is in progress, THE system SHALL track and expose progress: total records in the run, records screened, records pending, records with each verdict (include/exclude/uncertain), and estimated time remaining based on average screening duration per record.
5. IF the vLLM instance is unavailable during a Screening_Run, THEN THE system SHALL retry the current batch up to 3 times with exponential backoff (30 seconds, 2 minutes, 10 minutes) before marking the batch as failed, recording the failure in the audit trail, and proceeding to the next batch.
6. IF the Literature_Screener_Agent returns a response that does not conform to the expected JSON schema (missing verdict, confidence outside 0.0–1.0, or missing rationale), THEN THE system SHALL mark that Ingestion_Record's Screening_Decision as `verdict: "uncertain"` with `confidence: 0.0` and a rationale indicating "Agent response parsing failed", and log the malformed response in the audit trail.
7. THE system SHALL support re-screening: initiating a new Screening_Run against records that previously received an "uncertain" verdict, using the same or an updated Screening_Protocol, without overwriting previous Screening_Decisions (all decisions are append-only with timestamps).
8. WHEN a Screening_Run completes (all batches processed or failed), THE system SHALL update the SLR_Review progress statistics and record the completion event in the audit trail with: screening_protocol_id, total_screened, include_count, exclude_count, uncertain_count, total_duration_ms, and failed_count.

### Requirement 4: SLR Review Workflow Management

**User Story:** As a quality manager, I want to manage end-to-end systematic literature review workflows with progress tracking and PRISMA-style reporting, so that I can demonstrate regulatory-compliant review processes during audits.

#### Acceptance Criteria

1. THE SLR_Review SHALL track the following lifecycle states: `protocol_defined` → `screening_in_progress` → `screening_complete` → `human_review_in_progress` → `completed`, with valid transitions enforced by the system.
2. THE SLR_Review SHALL maintain PRISMA_Flow statistics updated in real-time: `records_identified` (total Ingestion_Records submitted to the review), `records_screened` (total with a Screening_Decision), `records_eligible` (total with verdict "include" or "uncertain" after AI screening), `records_included_final` (total confirmed by human reviewer), and `records_excluded_with_reasons` (grouped by exclusion reason category).
3. WHEN an SLR_Review is created, THE system SHALL associate it with a Screening_Protocol, a set of Ingestion_Record IDs (or a query filter defining the record set), the initiating user_id, and the company_id.
4. THE SLR_Review SHALL support human verification of AI screening decisions: reviewers can override any Screening_Decision by setting a `human_verdict` (include, exclude) with a `human_rationale` (text, max 2000 characters), and the system SHALL record the override with the reviewer's user_id and timestamp.
5. WHEN all records in an SLR_Review have either a final human verdict or an uncontested AI verdict (AI "include" or "exclude" with confidence ≥ 0.8 that has not been flagged for human review), THE system SHALL transition the SLR_Review state to `screening_complete`.
6. THE SLR_Review SHALL compute Inter_Rater_Reliability metrics when human overrides exist: agreement rate (percentage of AI decisions confirmed by human reviewers), Cohen's kappa coefficient between AI and human verdicts, and per-criterion false positive/negative rates.
7. THE system SHALL support generating SLR summary reports containing: review metadata (protocol name, date range, search strategy), PRISMA_Flow diagram data, screening statistics, inclusion/exclusion rationale summaries, and inter-rater reliability metrics, exportable as JSON for regulatory submissions.
8. IF a user without at least the `member` role attempts to access an SLR_Review, THEN THE system SHALL reject the request with HTTP 403.
9. WHEN an SLR_Review transitions to `completed`, THE system SHALL record a final audit trail entry containing: review_id, protocol_id, company_id, completing_user_id, total_records, final_included_count, final_excluded_count, agreement_rate, duration_days (from creation to completion), and a UTC timestamp.

### Requirement 5: Contradiction Detection Upon Literature Indexing

**User Story:** As a quality manager, I want newly ingested literature automatically cross-referenced against our internal SOPs and validation plans, so that contradictions between external scientific findings and our processes are surfaced immediately.

#### Acceptance Criteria

1. WHEN an Ingestion_Record transitions to the `indexed` state (embedding generation complete per Phase 9.3), THE Contradiction_Detection_Service SHALL dispatch a Cross_Reference_Task as a Celery task on the `ai_operations` queue to analyze the record against internal documents.
2. THE Cross_Reference_Task SHALL use the Hybrid_Query_Engine to search for internal documents (partition_tag: `private_knowledge`) semantically similar to the newly indexed literature record, using the paper's title and abstract as the query text, retrieving up to 10 candidate internal documents with a minimum similarity threshold of 0.6.
3. WHEN candidate internal documents are found, THE Contradiction_Detection_Service SHALL construct a prompt containing the literature paper's key findings (extracted from title, abstract, and available body sections) and the relevant sections of each candidate internal document, then dispatch the prompt to the vLLM instance via InferenceClient for contradiction analysis.
4. THE Contradiction_Detection_Service SHALL use the Master Auditor Agent archetype's system prompt (extended with contradiction-specific instructions) for analysis, leveraging its existing contradiction detection evaluation rubric criteria.
5. THE Contradiction_Detection_Service SHALL produce a structured analysis result for each literature-vs-internal-document pair containing: `contradiction_found` (boolean), `contradiction_description` (text, max 3000 characters), `severity` (critical, major, minor), `affected_internal_sections` (array of section identifiers), `evidence_from_literature` (text, max 2000 characters), `recommended_action` (text, max 1000 characters), and `confidence` (float 0.0–1.0).
6. WHEN a contradiction is identified with confidence ≥ 0.7, THE Contradiction_Detection_Service SHALL create a Contradiction_Alert record with: ingestion_record_id, internal_document_id, company_id, severity, description, evidence, recommended_action, confidence, analysis_timestamp, and status (new, acknowledged, resolved, dismissed).
7. IF the Hybrid_Query_Engine returns zero results for a Cross_Reference_Task (no related internal documents found with similarity ≥ 0.6), THEN THE Contradiction_Detection_Service SHALL create a Novelty_Flag record indicating that the paper's findings are not covered by existing internal knowledge, with fields: ingestion_record_id, company_id, novelty_description (generated summary of uncovered topics), and status (new, acknowledged, integrated, dismissed).
8. IF the vLLM instance is unavailable during contradiction analysis, THEN THE Contradiction_Detection_Service SHALL retry the Cross_Reference_Task up to 3 times with exponential backoff (30 seconds, 2 minutes, 10 minutes) before marking it as failed and recording the failure in the audit trail without transitioning the Ingestion_Record state.

### Requirement 6: Contradiction Severity Classification and Escalation

**User Story:** As a quality manager, I want contradictions classified by severity and critical ones escalated automatically, so that regulatory-impacting discrepancies trigger immediate action.

#### Acceptance Criteria

1. THE Contradiction_Detection_Service SHALL classify contradiction severity using the following criteria: `critical` — the external finding directly contradicts a validated process step, dosage, safety parameter, or regulatory claim in an active SOP or validation plan; `major` — the external finding presents evidence that could invalidate assumptions in internal documents but does not directly contradict validated parameters; `minor` — the external finding suggests improvements or alternatives to internal processes without contradicting validated parameters.
2. WHEN a Contradiction_Alert with severity `critical` is created, THE system SHALL automatically generate an impact analysis task by invoking the existing ImpactAnalysisService with the affected internal document, creating a linkage between the Contradiction_Alert and the resulting impact analysis report.
3. WHEN a Contradiction_Alert with severity `critical` is created, THE system SHALL dispatch a notification to all users with the `document_admin` or `system_admin` role within the affected company, containing: alert_id, literature paper title, affected internal document name, contradiction summary, and severity level.
4. THE Contradiction_Alert SHALL support status transitions: `new` → `acknowledged` → `resolved` or `dismissed`, where `acknowledged` requires a user_id and timestamp, `resolved` requires a resolution_note (text, max 3000 characters) and linked change_request_id (optional), and `dismissed` requires a dismissal_reason (text, max 2000 characters).
5. IF a user without the `document_admin` or `system_admin` role attempts to transition a Contradiction_Alert from `new` to `dismissed`, THEN THE system SHALL reject the request with HTTP 403, as only authorized personnel can dismiss potential compliance risks.
6. WHEN a Contradiction_Alert is resolved and linked to a change_request_id, THE system SHALL verify that the referenced change request exists within the same company scope before accepting the resolution.
7. THE system SHALL maintain a running count of open (status: `new` or `acknowledged`) Contradiction_Alerts per company, exposed via the contradiction alerts summary endpoint, grouped by severity.

### Requirement 7: Novelty Detection and Knowledge Gap Identification

**User Story:** As a quality manager, I want to know when newly published research covers topics not addressed by our internal documentation, so that I can proactively update our knowledge base and stay current with scientific advances.

#### Acceptance Criteria

1. WHEN the Contradiction_Detection_Service finds zero internal documents with similarity ≥ 0.6 for a newly indexed literature record, THE system SHALL create a Novelty_Flag with: ingestion_record_id, company_id, novelty_description (LLM-generated summary of the paper's key topics not found internally, max 2000 characters), suggested_document_types (array of internal document types that might need creation, e.g., "SOP", "URS", "Validation Plan"), and status (new, acknowledged, integrated, dismissed).
2. THE Novelty_Flag SHALL include a `relevance_score` (float 0.0–1.0) computed by the LLM based on how relevant the paper's topic is to the company's domain focus (inferred from existing internal document topics), enabling prioritized review of novel findings.
3. WHEN a Novelty_Flag with relevance_score ≥ 0.8 is created, THE system SHALL flag it as `high_priority` in the response payload and include it in the company's novelty alerts summary.
4. THE Novelty_Flag SHALL support status transitions: `new` → `acknowledged` → `integrated` or `dismissed`, where `integrated` indicates the findings have been incorporated into internal documentation (with optional linked_document_id), and `dismissed` requires a reason.
5. IF a user with at least `member` role queries novelty flags, THE system SHALL return flags scoped to the user's company, ordered by relevance_score descending then created_at descending.
6. THE system SHALL support batch novelty analysis: when multiple papers from the same Screening_Run are flagged as novel, group them by topic similarity (using embedding cosine similarity ≥ 0.8 between their abstracts) and present grouped novelty summaries rather than individual flags, to reduce alert fatigue.

### Requirement 8: API Endpoints for Screening Protocol Management

**User Story:** As a developer building the literature review UI (Phase 9.6), I want RESTful API endpoints for managing screening protocols, so that the frontend can provide CRUD operations on review criteria.

#### Acceptance Criteria

1. THE system SHALL expose a `POST /api/literature/screening/protocols` endpoint accepting a JSON body with all Screening_Protocol fields (name, description, pico_criteria, inclusion_criteria, exclusion_criteria, date_range, publication_types, languages), returning HTTP 201 with the created protocol on success.
2. THE system SHALL expose a `GET /api/literature/screening/protocols` endpoint returning a paginated list of Screening_Protocols for the requesting company, supporting `page` (integer, default 1), `page_size` (integer, 1–100, default 20), and `status` filter (draft, active, archived).
3. THE system SHALL expose a `GET /api/literature/screening/protocols/{protocol_id}` endpoint returning the full protocol details including all criteria fields and version history.
4. THE system SHALL expose a `PUT /api/literature/screening/protocols/{protocol_id}` endpoint accepting updated protocol fields, auto-incrementing the version number, and returning HTTP 200 with the updated protocol.
5. THE system SHALL expose a `DELETE /api/literature/screening/protocols/{protocol_id}` endpoint that transitions the protocol status to `archived` (soft delete) rather than physically deleting, returning HTTP 200 on success.
6. THE system SHALL expose a `POST /api/literature/screening/protocols/{protocol_id}/activate` endpoint that transitions a protocol from `draft` to `active` status, returning HTTP 200 on success.
7. WHEN any mutation endpoint (POST, PUT, DELETE) is called, THE system SHALL require the X-Change-Reason header and return HTTP 400 if it is missing or empty.
8. THE system SHALL require at least the `document_admin` role for all screening protocol mutation endpoints and at least the `member` role for read endpoints, returning HTTP 403 when the caller lacks the required role.

### Requirement 9: API Endpoints for SLR Review Management

**User Story:** As a developer building the literature review UI, I want RESTful API endpoints for managing SLR reviews and viewing screening results, so that the frontend can display review progress and screening decisions.

#### Acceptance Criteria

1. THE system SHALL expose a `POST /api/literature/reviews` endpoint accepting: `protocol_id` (integer, required), `name` (string, 1–200 characters, required), `description` (text, optional), and `record_filter` (object with optional fields: `ingestion_record_ids` array, `state` filter, `date_range`, `source_id`), creating an SLR_Review and returning HTTP 201 with the review details.
2. THE system SHALL expose a `GET /api/literature/reviews` endpoint returning a paginated list of SLR_Reviews for the requesting company with PRISMA_Flow summary statistics, supporting filtering by `status`.
3. THE system SHALL expose a `GET /api/literature/reviews/{review_id}` endpoint returning full review details including: protocol reference, PRISMA_Flow statistics, current state, progress metrics, and inter-rater reliability metrics (when available).
4. THE system SHALL expose a `POST /api/literature/reviews/{review_id}/screen` endpoint that initiates a Screening_Run for the review, accepting optional `batch_size` (integer, 1–100, default 20) and `re_screen_uncertain` (boolean, default false), returning HTTP 202 with a `task_id` for progress tracking.
5. THE system SHALL expose a `GET /api/literature/reviews/{review_id}/decisions` endpoint returning paginated Screening_Decisions for the review, supporting filtering by `verdict` (include, exclude, uncertain), `confidence_min` (float), and `has_human_override` (boolean).
6. THE system SHALL expose a `PUT /api/literature/reviews/{review_id}/decisions/{decision_id}/override` endpoint accepting `human_verdict` (include, exclude) and `human_rationale` (text, max 2000 characters), recording the human override and returning HTTP 200.
7. THE system SHALL expose a `GET /api/literature/reviews/{review_id}/report` endpoint generating and returning the SLR summary report as JSON, including PRISMA_Flow data, screening statistics, and inter-rater reliability metrics.
8. THE system SHALL expose a `GET /api/literature/reviews/{review_id}/progress` endpoint returning real-time screening progress: total_records, screened_count, pending_count, include_count, exclude_count, uncertain_count, estimated_time_remaining_seconds.
9. WHEN any mutation endpoint is called, THE system SHALL require the X-Change-Reason header and return HTTP 400 if missing or empty.
10. THE system SHALL require at least the `member` role for read endpoints and at least the `document_admin` role for mutation endpoints (initiating screens, recording overrides), returning HTTP 403 when the caller lacks the required role.

### Requirement 10: API Endpoints for Contradiction and Novelty Alerts

**User Story:** As a developer building the literature review UI, I want RESTful API endpoints for viewing and managing contradiction alerts and novelty flags, so that the frontend can present actionable findings to quality managers.

#### Acceptance Criteria

1. THE system SHALL expose a `GET /api/literature/contradictions` endpoint returning paginated Contradiction_Alerts for the requesting company, supporting filtering by `severity` (critical, major, minor), `status` (new, acknowledged, resolved, dismissed), `ingestion_record_id`, and `internal_document_id`, ordered by severity descending then created_at descending.
2. THE system SHALL expose a `GET /api/literature/contradictions/{alert_id}` endpoint returning full alert details including: literature paper metadata, affected internal document metadata, contradiction description, evidence, recommended action, confidence, status history, and linked impact analysis report (if any).
3. THE system SHALL expose a `PUT /api/literature/contradictions/{alert_id}/status` endpoint accepting `status` (acknowledged, resolved, dismissed), optional `resolution_note` or `dismissal_reason`, and optional `change_request_id`, returning HTTP 200 on success.
4. THE system SHALL expose a `GET /api/literature/contradictions/summary` endpoint returning aggregate statistics: total open alerts by severity, alerts resolved this month, average time-to-resolution, and top-5 most-affected internal documents.
5. THE system SHALL expose a `GET /api/literature/novelty` endpoint returning paginated Novelty_Flags for the requesting company, supporting filtering by `status`, `relevance_score_min` (float), and `high_priority` (boolean), ordered by relevance_score descending.
6. THE system SHALL expose a `PUT /api/literature/novelty/{flag_id}/status` endpoint accepting `status` (acknowledged, integrated, dismissed), optional `linked_document_id`, and optional `reason`, returning HTTP 200 on success.
7. WHEN any mutation endpoint (PUT) is called, THE system SHALL require the X-Change-Reason header and return HTTP 400 if missing or empty.
8. THE system SHALL require at least the `member` role for read endpoints and at least the `document_admin` role for status transition endpoints, returning HTTP 403 when the caller lacks the required role.
9. IF the `alert_id` or `flag_id` does not exist or belongs to a different company, THEN THE system SHALL return HTTP 404 with a generic "not found" message without revealing cross-tenant information.

### Requirement 11: Screening Configuration and Tuning

**User Story:** As a system administrator, I want to configure screening behavior per company, so that different organizations can tune agent parameters and batch sizes for their review workloads.

#### Acceptance Criteria

1. THE system SHALL provide per-company screening configuration with the following settings: `auto_screen_on_index` (boolean, default: false — whether to automatically screen newly indexed papers against all active protocols), `default_batch_size` (integer, default: 20, range: 1–100), `confidence_threshold_for_auto_include` (float, default: 0.8, range: 0.5–1.0 — AI decisions above this threshold do not require human review), `max_concurrent_screening_tasks` (integer, default: 5, range: 1–20), and `contradiction_detection_enabled` (boolean, default: true).
2. WHILE `auto_screen_on_index` is true for a company, WHEN an Ingestion_Record transitions to the `indexed` state, THE system SHALL automatically initiate a Screening_Run against all active Screening_Protocols for that company, in addition to the standard Cross_Reference_Task.
3. WHILE `contradiction_detection_enabled` is false for a company, THE system SHALL NOT dispatch Cross_Reference_Tasks when Ingestion_Records reach the `indexed` state for that company.
4. THE system SHALL expose configuration endpoints at `GET /api/literature/screening/config` and `PUT /api/literature/screening/config`, requiring at least `system_admin` role for updates and `document_admin` role for reads.
5. WHEN a screening configuration is updated, THE system SHALL record the change in the audit trail including previous values, new values, acting user_id, timestamp, and X-Change-Reason header value.
6. IF a configuration update request contains values outside defined ranges (batch_size outside 1–100, confidence_threshold outside 0.5–1.0, max_concurrent outside 1–20), THEN THE system SHALL reject the request with HTTP 422 and an error message indicating which parameter violated its allowed range.

### Requirement 12: Audit Trail for Literature Review Operations

**User Story:** As a quality manager, I want all screening decisions, contradiction alerts, and review workflow actions logged in the audit trail, so that I can demonstrate the integrity of our literature review process during regulatory audits.

#### Acceptance Criteria

1. WHEN a Screening_Decision is recorded, THE Audit_Logger SHALL create an append-only entry containing: screening_run_id, ingestion_record_id, protocol_id, company_id, verdict, confidence, agent_model_name, screening_duration_ms, and a UTC timestamp.
2. WHEN a human override is recorded for a Screening_Decision, THE Audit_Logger SHALL create an append-only entry containing: decision_id, review_id, company_id, original_verdict, human_verdict, reviewer_user_id, and a UTC timestamp.
3. WHEN a Contradiction_Alert is created, THE Audit_Logger SHALL create an append-only entry containing: alert_id, ingestion_record_id, internal_document_id, company_id, severity, confidence, detection_duration_ms, and a UTC timestamp.
4. WHEN a Contradiction_Alert status changes, THE Audit_Logger SHALL create an append-only entry containing: alert_id, company_id, previous_status, new_status, acting_user_id, resolution_note or dismissal_reason (if applicable), and a UTC timestamp.
5. WHEN a Novelty_Flag is created, THE Audit_Logger SHALL create an append-only entry containing: flag_id, ingestion_record_id, company_id, relevance_score, high_priority (boolean), and a UTC timestamp.
6. WHEN an SLR_Review transitions state, THE Audit_Logger SHALL create an append-only entry containing: review_id, company_id, previous_state, new_state, acting_user_id, and a UTC timestamp.
7. THE Audit_Logger SHALL never log full paper content, full internal document content, or LLM prompt/response text in audit records to minimize storage overhead and avoid sensitive data exposure; only metadata identifiers, verdicts, and metrics SHALL be logged.
8. THE Audit_Logger SHALL store all literature review audit records as append-only entries that cannot be modified or deleted through application-level operations, preserving ALCOA+ Original and Enduring principles.

### Requirement 13: Error Handling and Resilience

**User Story:** As a system administrator, I want the literature screening and contradiction detection pipeline to handle failures gracefully, so that temporary AI service outages do not corrupt review workflows or lose screening progress.

#### Acceptance Criteria

1. IF the vLLM instance is unavailable during a Screening_Run, THEN THE system SHALL retain all unscreened Ingestion_Records in their pending state within the SLR_Review, retry the current batch up to 3 times with exponential backoff (30 seconds, 2 minutes, 10 minutes), and if all retries are exhausted, mark the batch as failed while preserving the Screening_Run for later resumption.
2. IF the vLLM instance is unavailable during a Cross_Reference_Task, THEN THE Contradiction_Detection_Service SHALL retry up to 3 times with exponential backoff before marking the task as failed and recording the failure in the audit trail, without affecting the Ingestion_Record's `indexed` state.
3. IF the Hybrid_Query_Engine is unavailable during a Cross_Reference_Task (OpenSearch unreachable), THEN THE Contradiction_Detection_Service SHALL retry up to 3 times with 10-second intervals before marking the task as failed and scheduling an automatic retry after 5 minutes.
4. THE system SHALL implement idempotent screening: re-running a Screening_Run for the same batch of records SHALL NOT create duplicate Screening_Decisions; if a decision already exists for a record within the same Screening_Run, the system SHALL skip that record.
5. IF a Screening_Run is interrupted (worker crash, deployment restart), THEN THE system SHALL detect the incomplete run on startup by checking for runs in `screening_in_progress` state with no active Celery task, and SHALL resume processing from the last completed batch.
6. THE system SHALL enforce a maximum execution time of 30 minutes per Screening_Run batch; IF a batch exceeds this timeout, THEN the system SHALL mark the batch as failed, log the timeout, and proceed to the next batch.
7. IF the Contradiction_Detection_Service encounters a partial failure (some literature-vs-document pairs analyzed, others fail), THEN THE system SHALL persist the successfully analyzed results and retry only the failed pairs, up to 2 additional attempts.
8. WHEN any retry attempt is made for screening or contradiction detection, THE system SHALL log the retry attempt number, the error that triggered the retry, and the backoff duration in the audit trail.

### Requirement 14: Environment and Deployment Configuration

**User Story:** As a system administrator, I want all literature review and contradiction detection settings configurable via environment variables, so that deployment across environments requires no code changes.

#### Acceptance Criteria

1. THE system SHALL read the Celery queue name for screening tasks from `ALC_LITERATURE_SCREENING_QUEUE` environment variable (default: `ai_operations`), accepting only non-empty string values.
2. THE system SHALL read the Celery queue name for contradiction detection tasks from `ALC_LITERATURE_CONTRADICTION_QUEUE` environment variable (default: `ai_operations`), accepting only non-empty string values.
3. THE system SHALL read the default similarity threshold for internal document matching from `ALC_CONTRADICTION_SIMILARITY_THRESHOLD` environment variable (default: 0.6), accepting float values between 0.1 and 1.0.
4. THE system SHALL read the maximum number of candidate internal documents to retrieve per Cross_Reference_Task from `ALC_CONTRADICTION_MAX_CANDIDATES` environment variable (default: 10), accepting integer values between 1 and 50.
5. THE system SHALL read the contradiction analysis confidence threshold from `ALC_CONTRADICTION_CONFIDENCE_THRESHOLD` environment variable (default: 0.7), accepting float values between 0.1 and 1.0.
6. THE system SHALL read the screening task timeout in seconds from `ALC_SCREENING_TASK_TIMEOUT` environment variable (default: 1800, representing 30 minutes), accepting integer values of 60 or greater.
7. THE system SHALL read the maximum concurrent screening tasks per company from `ALC_SCREENING_MAX_CONCURRENT` environment variable (default: 5), accepting integer values between 1 and 50.
8. IF any numeric environment variable contains a non-numeric value or a value outside its accepted range, THEN THE system SHALL refuse to start and log an error message at ERROR level to standard error indicating the invalid variable name and its accepted range.
9. WHEN the system starts successfully, THE system SHALL log the resolved values of all Phase 9.4 configuration variables at INFO level.

### Requirement 15: Screening Decision Round-Trip Integrity

**User Story:** As a developer, I want to verify that screening decisions produced by the agent are accurately persisted and retrievable, so that no data is lost or corrupted in the screening pipeline.

#### Acceptance Criteria

1. FOR ALL Screening_Decisions produced by the Literature_Screener_Agent with a valid verdict (include, exclude, uncertain), persisting the decision to the database and retrieving it by ID SHALL yield a record with identical verdict, confidence (within floating-point precision tolerance of 1e-6), rationale text, matched_inclusion_criteria array, and matched_exclusion_criteria array.
2. FOR ALL Screening_Protocols with valid PICO criteria, serializing the protocol to JSON for API response and deserializing it back SHALL produce an equivalent object with identical field values (serialization round-trip property).
3. FOR ALL Contradiction_Alerts with valid severity (critical, major, minor) and confidence (0.0–1.0), persisting and retrieving the alert SHALL yield identical severity, confidence (within 1e-6), contradiction_description, and evidence_from_literature fields.
4. FOR ALL SLR_Reviews, the PRISMA_Flow statistics SHALL satisfy the invariant: `records_identified >= records_screened >= records_eligible >= records_included_final`, and `records_excluded_with_reasons` summed across all reason categories plus `records_included_final` SHALL equal `records_screened`.
5. WHEN verifying round-trip integrity via property-based tests, THE system SHALL execute a minimum of 100 Hypothesis-generated examples per property, covering Screening_Decisions with varying verdicts, confidence levels across the full 0.0–1.0 range, rationale texts of varying lengths (empty to 2000 characters), and criteria arrays of varying sizes (0 to 20 elements).
