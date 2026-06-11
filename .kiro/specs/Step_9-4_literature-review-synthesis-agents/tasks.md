# Implementation Plan: AI-Powered Literature Review & Synthesis Agents (Phase 9.4)

## Overview

This plan implements the literature screener agent, screening protocol management, SLR review workflows, contradiction detection, and novelty flagging for Phase 9.4. Tasks are ordered by dependency: config/models/schemas first, then services, API routers, Celery tasks, ingestion pipeline integration, audit trail, and finally tests. Each task builds incrementally on previous work, ensuring no orphaned or disconnected code.

## Tasks

- [x] 1. Configuration, models, and schemas
  - [x] 1.1 Extend config.py with Phase 9.4 environment settings
    - Add `literature_screening_queue`, `literature_contradiction_queue`, `contradiction_similarity_threshold`, `contradiction_max_candidates`, `contradiction_confidence_threshold`, `screening_task_timeout`, `screening_max_concurrent` fields to the Settings class in `src/backend/src/alcoabase/config.py`
    - Use Pydantic Field with aliases matching `ALC_LITERATURE_SCREENING_QUEUE`, `ALC_LITERATURE_CONTRADICTION_QUEUE`, `ALC_CONTRADICTION_SIMILARITY_THRESHOLD`, `ALC_CONTRADICTION_MAX_CANDIDATES`, `ALC_CONTRADICTION_CONFIDENCE_THRESHOLD`, `ALC_SCREENING_TASK_TIMEOUT`, `ALC_SCREENING_MAX_CONCURRENT`
    - Add startup validation: refuse to start if numeric env vars contain non-numeric or out-of-range values
    - Log resolved config values at INFO on startup
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9_

  - [x] 1.2 Create SQLAlchemy models for Phase 9.4
    - Create `src/backend/src/alcoabase/literature/review/__init__.py`, `models/__init__.py`
    - Create `screening_protocol.py`: `ScreeningProtocol` model with PICO fields, inclusion/exclusion criteria (JSONB), date range, publication types, languages, version, status, AuditMixin, `__versioned__ = {}`
    - Create `screening_decision.py`: `ScreeningDecision` model (append-only, no AuditMixin) with verdict, confidence, rationale, matched criteria, human override fields
    - Create `slr_review.py`: `SLRReview` model with protocol FK, status state machine, record_filter JSONB, AuditMixin, `__versioned__ = {}`
    - Create `screening_run.py`: `ScreeningRun` model with review FK, progress tracking fields (total_records, screened_count, include/exclude/uncertain/failed counts, batch_size, current_batch, celery_task_id)
    - Create `contradiction_alert.py`: `ContradictionAlert` model with severity, description, evidence, confidence, status, impact_report_id, AuditMixin, `__versioned__ = {}`
    - Create `novelty_flag.py`: `NoveltyFlag` model with relevance_score, high_priority, suggested_document_types, status, group_id, AuditMixin, `__versioned__ = {}`
    - Create `screening_config.py`: `ScreeningConfiguration` model with unique company_id constraint, auto_screen_on_index, default_batch_size, confidence_threshold, max_concurrent, contradiction_detection_enabled, AuditMixin, `__versioned__ = {}`
    - _Requirements: 2.7, 3.2, 4.1, 4.2, 4.3, 5.5, 5.6, 7.1, 11.1_

  - [x] 1.3 Create Pydantic schemas for Phase 9.4
    - Create `src/backend/src/alcoabase/literature/review/schemas/__init__.py`
    - Create `protocol.py`: `PICOCriteriaSchema`, `ScreeningProtocolCreateSchema`, `ScreeningProtocolUpdateSchema`, `ScreeningProtocolResponseSchema` with field validators (name 1–200 chars, description max 5000, criteria max 20 items, date ISO-8601, at-least-one-criterion validator)
    - Create `review.py`: `SLRReviewCreateSchema`, `SLRReviewResponseSchema`, `PRISMAFlowSchema`, `ScreeningProgressSchema`, `InterRaterReliabilitySchema`, `SLRReportSchema`
    - Create `decision.py`: `ScreeningDecisionResponseSchema`, `HumanOverrideRequestSchema` (human_verdict enum, human_rationale max 2000 chars)
    - Create `contradiction.py`: `ContradictionAlertResponseSchema`, `ContradictionStatusUpdateSchema`, `ContradictionSummarySchema`
    - Create `novelty.py`: `NoveltyFlagResponseSchema`, `NoveltyStatusUpdateSchema`
    - Create `configuration.py`: `ScreeningConfigurationSchema`, `ScreeningConfigurationUpdateSchema` with range validators (batch_size 1–100, confidence 0.5–1.0, max_concurrent 1–20)
    - _Requirements: 8.1, 8.2, 8.3, 9.1, 9.3, 9.5, 10.1, 10.5, 11.4, 11.6_

  - [x] 1.4 Create Alembic migration for Phase 9.4 tables
    - Generate migration adding `literature_screening_protocols`, `literature_screening_decisions`, `literature_slr_reviews`, `literature_screening_runs`, `literature_contradiction_alerts`, `literature_novelty_flags`, `literature_screening_configurations` tables
    - Include unique constraint on `company_id` for screening configurations
    - Include indexes on `company_id`, `screening_run_id`, `ingestion_record_id`, `protocol_id`, `celery_task_id` columns
    - _Requirements: 2.7, 3.2, 4.3, 5.6, 7.1, 11.1_

  - [x] 1.5 Create review-specific exception classes
    - Create `src/backend/src/alcoabase/literature/review/exceptions.py`
    - Define: `InvalidStateTransitionError`, `ProtocolNotFoundError`, `ReviewNotFoundError`, `DecisionNotFoundError`, `AlertNotFoundError`, `FlagNotFoundError`, `NoCriteriaDefinedError`, `ScreeningRunActiveError`, `ConfigurationRangeError`
    - _Requirements: 4.1, 6.4, 7.4, 2.10, 11.6, 13.4_

- [x] 2. Checkpoint - Ensure models and schemas compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Literature Screener Agent archetype definition
  - [x] 3.1 Create literature-screener.yaml agent archetype
    - Create `agents/archetypes/literature-screener.yaml` following agent-definition-v2 JSON schema
    - Set `schema_version: "2.0"`, `archetype: "Literature Screener"`, `agent_type: "review"`
    - Define `personality_profile` with tone "analytical and evidence-based", verbosity "detailed", strictness 0.9, domain_focus ["systematic-review", "literature-screening", "evidence-assessment", "PICO-analysis"]
    - Define `system_prompt` instructing evaluation of title/abstract/full-text against PICO + custom criteria, specifying expected JSON output schema (verdict, confidence, rationale, matched criteria)
    - Define `evaluation_rubric` with: screening_accuracy (0.35), rationale_quality (0.25), criteria_coverage (0.20), consistency (0.10), response_formatting (0.10), scoring_method "weighted_average"
    - Define `contextual_tuning` with temperature 0.1, max_tokens 4096, top_p 0.95
    - Define `knowledge_scopes` with tags ["Literature", "SystematicReview", "Screening", "PICO"]
    - Verify hot-reload compatibility with existing watchfiles mechanism in AgentRegistryService
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 4. Implement ScreeningProtocolService
  - [x] 4.1 Implement ScreeningProtocolService class
    - Create `src/backend/src/alcoabase/literature/review/services/__init__.py` and `screening_protocol_service.py`
    - Implement `create_protocol()`: validate at-least-one-criterion, set status "draft", version 1, persist, record audit trail
    - Implement `update_protocol()`: auto-increment version, if active with in-progress reviews create new version preserving old for those reviews, validate criteria remain
    - Implement `activate_protocol()`: enforce draft→active transition only
    - Implement `archive_protocol()`: soft-delete by transitioning to archived
    - Implement `list_protocols()`: paginated, filter by status, company-scoped
    - Implement `get_protocol()`: full details with version history, company-scoped
    - Validate role requirements: `document_admin` for mutations, `member` for reads
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [x] 4.2 Write property test: Protocol requires at least one criterion (Property 16)
    - **Property 16: Protocol requires at least one criterion**
    - Use Hypothesis to generate protocol creation payloads with all PICO fields empty/null AND both criteria lists empty → assert rejection (ValidationError/HTTP 422)
    - Generate payloads with at least one non-empty PICO field OR at least one criterion → assert acceptance
    - **Validates: Requirements 2.10**

  - [x] 4.3 Write property test: Screening Protocol serialization round-trip (Property 1)
    - **Property 1: Screening Protocol serialization round-trip**
    - Use Hypothesis to generate valid ScreeningProtocol objects with random PICO criteria (0–2000 chars each), inclusion criteria (0–20 patterns, 1–500 chars), exclusion criteria (0–20 patterns), and metadata
    - Serialize to JSON via ScreeningProtocolResponseSchema, deserialize back via Pydantic, assert identical field values
    - **Validates: Requirements 2.1, 2.7, 15.2**

- [x] 5. Implement LiteratureScreenerAgentRunner service
  - [x] 5.1 Implement LiteratureScreenerAgentRunner class
    - Create `src/backend/src/alcoabase/literature/review/services/screener_agent_runner.py`
    - Implement `ScreeningResult` frozen dataclass with verdict, confidence, rationale, matched criteria, duration_ms
    - Implement `__init__` with InferenceClient, AgentRegistryService, model_name
    - Implement `screen_record()`: load archetype → construct prompt → dispatch to vLLM → parse and validate JSON → return ScreeningResult or fallback
    - Implement `screen_batch()`: process records sequentially, on per-record failure return uncertain/0.0 fallback, continue
    - Implement `_construct_prompt()`: include paper title, abstract (truncated 4000 chars), body sections (truncated 8000 chars), PICO criteria, inclusion/exclusion patterns, date range, publication types
    - Implement `_parse_response()`: validate verdict enum, confidence 0.0–1.0, rationale presence; return None on failure
    - Implement `_get_agent_config()`: load Literature Screener archetype from registry, fallback to built-in defaults (temperature 0.1, max_tokens 4096)
    - _Requirements: 1.1, 1.3, 1.5, 3.1, 3.2, 3.6_

  - [x] 5.2 Write property test: Malformed LLM response produces uncertain fallback (Property 6)
    - **Property 6: Malformed LLM response produces uncertain fallback**
    - Use Hypothesis to generate random non-conforming strings (missing verdict, confidence outside 0.0–1.0, missing rationale, unparseable JSON, random bytes)
    - Assert `_parse_response()` returns None for all malformed inputs
    - Assert that `screen_record()` with a malformed response yields verdict "uncertain", confidence 0.0, rationale containing "Agent response parsing failed"
    - **Validates: Requirements 3.6**

- [x] 6. Implement SLRReviewService
  - [x] 6.1 Implement SLRReviewService class
    - Create `src/backend/src/alcoabase/literature/review/services/slr_review_service.py`
    - Implement `VALID_TRANSITIONS` dict for state machine (protocol_defined→screening_in_progress→screening_complete→human_review_in_progress→completed)
    - Implement `create_review()`: validate protocol exists and belongs to company, resolve record_filter into IngestionRecord IDs, persist SLRReview in protocol_defined state
    - Implement `initiate_screening()`: create ScreeningRun, transition to screening_in_progress, dispatch Celery task, return task_id
    - Implement `record_human_override()`: store human_verdict, human_rationale, reviewer_user_id, timestamp on ScreeningDecision; record audit trail
    - Implement `get_prisma_flow()`: compute from ScreeningDecision aggregates (records_identified, screened, eligible, included_final, excluded_with_reasons)
    - Implement `get_progress()`: return real-time screening progress (total, screened, pending, include/exclude/uncertain, estimated_time_remaining)
    - Implement `compute_inter_rater_reliability()`: agreement rate, Cohen's kappa between AI and human verdicts, per-criterion false positive/negative rates
    - Implement `generate_report()`: compile metadata, PRISMA flow, statistics, rationale summaries, inter-rater reliability into JSON
    - Implement `_check_auto_completion()`: auto-transition to screening_complete when all records have final human verdict or uncontested AI verdict with confidence ≥ threshold
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [x] 6.2 Write property test: PRISMA flow monotonic invariant (Property 4)
    - **Property 4: PRISMA flow monotonic invariant**
    - Use Hypothesis to generate random sets of ScreeningDecisions with varying verdicts and human overrides
    - Compute PRISMA Flow statistics via `get_prisma_flow()` logic
    - Assert `records_identified >= records_screened >= records_eligible >= records_included_final`
    - Assert sum of `records_excluded_with_reasons` + `records_included_final` == `records_screened`
    - **Validates: Requirements 4.2, 15.4**

  - [x] 6.3 Write property test: State machine transitions enforce valid paths (Property 8)
    - **Property 8: State machine transitions enforce valid paths only**
    - Use Hypothesis to generate random (current_state, target_state) pairs from all possible states
    - Assert transition succeeds only when the pair is in VALID_TRANSITIONS
    - Assert InvalidStateTransitionError raised for invalid pairs
    - Test for SLR Review, Contradiction Alert, and Novelty Flag state machines
    - **Validates: Requirements 4.1, 6.4, 7.4**

  - [x] 6.4 Write property test: Cohen's kappa computation correctness (Property 10)
    - **Property 10: Cohen's kappa computation correctness**
    - Use Hypothesis to generate lists of (AI_verdict, human_verdict) pairs where both are in {"include", "exclude"}
    - Compute Cohen's kappa via the service method
    - Assert result equals `(P_observed - P_expected) / (1 - P_expected)` where P_observed = proportion of agreements, P_expected = probability of chance agreement
    - When P_expected == 1.0, assert kappa == 0.0
    - **Validates: Requirements 4.6**

  - [x] 6.5 Write property test: Auto-completion threshold logic (Property 9)
    - **Property 9: Auto-completion threshold logic**
    - Use Hypothesis to generate SLR Review states with varying confidence values and human override presence
    - When all records have human override OR AI confidence >= threshold → assert auto-transition to screening_complete
    - When any record lacks resolution → assert no transition
    - **Validates: Requirements 4.5**

- [x] 7. Checkpoint - Ensure screening services and property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement ContradictionDetectionService
  - [x] 8.1 Implement ContradictionDetectionService class
    - Create `src/backend/src/alcoabase/literature/review/services/contradiction_detection_service.py`
    - Implement `ContradictionAnalysisResult` frozen dataclass
    - Implement `__init__` with session_factory, HybridQueryEngine, InferenceClient, ImpactAnalysisService, model_name, configurable thresholds
    - Implement `analyze_record()`: load IngestionRecord → search internal docs via HybridQueryEngine (partition_tag: private_knowledge, top_k=10, similarity ≥ 0.6) → if no results: create NoveltyFlag → if results: analyze each pair → create ContradictionAlerts → escalate critical → audit log
    - Implement `_search_internal_documents()`: use HybridQueryEngine with partition_filter='private_knowledge', company_id filter, min similarity threshold
    - Implement `_analyze_contradiction()`: construct prompt with Master Auditor archetype extended instructions, dispatch to vLLM, parse structured result
    - Implement `_create_novelty_flag()`: dispatch LLM for novelty_description + relevance_score, set high_priority if score >= 0.8, group by topic similarity if applicable
    - Implement `_escalate_critical()`: invoke ImpactAnalysisService, dispatch notifications to document_admin/system_admin users
    - Implement `_construct_contradiction_prompt()`: include severity classification criteria (critical/major/minor definitions), expected JSON output schema
    - Implement `_parse_contradiction_response()`: validate JSON schema, return None on failure
    - Handle partial failures: persist successful results, retry only failed pairs (up to 2 additional attempts)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 7.6_

  - [x] 8.2 Write property test: Contradiction alert creation threshold (Property 11)
    - **Property 11: Contradiction alert creation threshold**
    - Use Hypothesis to generate ContradictionAnalysisResult objects with varying `contradiction_found` (True/False) and `confidence` (0.0–1.0)
    - Assert alert created if and only if `contradiction_found is True AND confidence >= 0.7`
    - Assert no alert for results below threshold or with `contradiction_found=False`
    - **Validates: Requirements 5.6**

  - [x] 8.3 Write property test: Novelty flag creation and priority classification (Property 12)
    - **Property 12: Novelty flag creation and priority classification**
    - Use Hypothesis to generate relevance_score values (0.0–1.0)
    - Assert `high_priority` is True if and only if `relevance_score >= 0.8`
    - Assert NoveltyFlag is created when zero internal docs found with similarity >= threshold
    - **Validates: Requirements 5.7, 7.1, 7.3**

  - [x] 8.4 Write property test: Critical contradiction escalates to impact analysis (Property 13)
    - **Property 13: Critical contradiction escalates to impact analysis**
    - Use Hypothesis to generate ContradictionAlerts with varying severity (critical, major, minor)
    - Assert ImpactAnalysisService.compute_change_delta is invoked only for severity "critical"
    - Assert no invocation for "major" or "minor"
    - **Validates: Requirements 6.2**

- [x] 9. Implement ScreeningConfigService
  - [x] 9.1 Implement ScreeningConfigService class
    - Create `src/backend/src/alcoabase/literature/review/services/screening_config_service.py`
    - Implement `get_config()`: return company's ScreeningConfiguration or default values if none exists
    - Implement `update_config()`: validate ranges (batch_size 1–100, confidence 0.5–1.0, max_concurrent 1–20), persist, record audit trail with previous/new values
    - Implement `get_or_create_default()`: create default config for company if not exists
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 9.2 Write property test: Configuration range enforcement (Property 15)
    - **Property 15: Configuration range enforcement**
    - Use Hypothesis to generate configuration values outside valid ranges (batch_size outside 1–100, confidence outside 0.5–1.0, max_concurrent outside 1–20)
    - Assert rejection with HTTP 422 for out-of-range values
    - Generate in-range values and assert acceptance
    - **Validates: Requirements 11.6**

- [x] 10. Implement API routers
  - [x] 10.1 Implement literature_screening_router
    - Create `src/backend/src/alcoabase/api/literature_screening_router.py`
    - `POST /api/literature/screening/protocols`: require `document_admin`, require `X-Change-Reason`, validate body, return HTTP 201
    - `GET /api/literature/screening/protocols`: require `member`, paginated list with status filter
    - `GET /api/literature/screening/protocols/{protocol_id}`: require `member`, return full details
    - `PUT /api/literature/screening/protocols/{protocol_id}`: require `document_admin`, require `X-Change-Reason`, auto-increment version, return HTTP 200
    - `DELETE /api/literature/screening/protocols/{protocol_id}`: require `document_admin`, require `X-Change-Reason`, soft-delete (archive), return HTTP 200
    - `POST /api/literature/screening/protocols/{protocol_id}/activate`: require `document_admin`, require `X-Change-Reason`, transition draft→active
    - `GET /api/literature/screening/config`: require `document_admin`, return current config
    - `PUT /api/literature/screening/config`: require `system_admin`, require `X-Change-Reason`, validate ranges (HTTP 422 on violation), update config
    - Require `X-Company-Id` header on all endpoints (HTTP 400 if missing)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 11.4_

  - [x] 10.2 Implement literature_review_router
    - Create `src/backend/src/alcoabase/api/literature_review_router.py`
    - `POST /api/literature/reviews`: require `document_admin`, require `X-Change-Reason`, create SLR Review, return HTTP 201
    - `GET /api/literature/reviews`: require `member`, paginated list with status filter and PRISMA summary
    - `GET /api/literature/reviews/{review_id}`: require `member`, full details with PRISMA, progress, inter-rater metrics
    - `POST /api/literature/reviews/{review_id}/screen`: require `document_admin`, require `X-Change-Reason`, accept batch_size and re_screen_uncertain, return HTTP 202 with task_id
    - `GET /api/literature/reviews/{review_id}/decisions`: require `member`, paginated, filter by verdict/confidence_min/has_human_override
    - `PUT /api/literature/reviews/{review_id}/decisions/{decision_id}/override`: require `document_admin`, require `X-Change-Reason`, accept human_verdict and human_rationale, return HTTP 200
    - `GET /api/literature/reviews/{review_id}/progress`: require `member`, return real-time progress
    - `GET /api/literature/reviews/{review_id}/report`: require `member`, generate and return SLR summary report as JSON
    - Require `X-Company-Id` header on all endpoints (HTTP 400 if missing)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [x] 10.3 Implement literature_contradiction_router
    - Create `src/backend/src/alcoabase/api/literature_contradiction_router.py`
    - `GET /api/literature/contradictions`: require `member`, paginated, filter by severity/status/ingestion_record_id/internal_document_id, ordered by severity desc then created_at desc
    - `GET /api/literature/contradictions/summary`: require `member`, return aggregate stats (total_open_by_severity, resolved_this_month, avg_time_to_resolution, top_affected_docs)
    - `GET /api/literature/contradictions/{alert_id}`: require `member`, full alert details with literature/internal doc metadata, status history, linked impact report
    - `PUT /api/literature/contradictions/{alert_id}/status`: require `document_admin`, require `X-Change-Reason`, accept status transition + optional resolution_note/dismissal_reason/change_request_id, enforce dismiss requires document_admin/system_admin
    - `GET /api/literature/novelty`: require `member`, paginated, filter by status/relevance_score_min/high_priority, ordered by relevance_score desc then created_at desc
    - `PUT /api/literature/novelty/{flag_id}/status`: require `document_admin`, require `X-Change-Reason`, accept status transition + optional linked_document_id/reason
    - Require `X-Company-Id` header on all endpoints (HTTP 400 if missing)
    - Return HTTP 404 (not 403) for cross-tenant access attempts
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

  - [x] 10.4 Register routers in central router.py
    - Add `literature_screening_router`, `literature_review_router`, `literature_contradiction_router` to `src/backend/src/alcoabase/api/router.py`
    - Verify route prefixes are `/api/literature/screening`, `/api/literature/reviews`, `/api/literature/contradictions` and `/api/literature/novelty`
    - _Requirements: 8.1, 9.1, 10.1_

- [x] 11. Implement Celery tasks
  - [x] 11.1 Implement literature_screening_tasks.py
    - Create `src/backend/src/alcoabase/tasks/literature_screening_tasks.py`
    - Implement `execute_screening_batch` task: queue=`ai_operations`, priority=5, max_retries=3, soft_time_limit=1800s (from ALC_SCREENING_TASK_TIMEOUT), acks_late=True, exponential backoff (30s, 120s, 600s)
      - Load protocol criteria, instantiate LiteratureScreenerAgentRunner
      - Process each record via screen_batch(), persist ScreeningDecisions
      - Idempotent: skip records with existing decision in this run
      - Update ScreeningRun progress after each batch
      - On completion: update SLR_Review PRISMA stats, check auto-completion
    - Implement `execute_cross_reference` task: queue=`ai_operations`, priority=4, max_retries=3, soft_time_limit=600s, acks_late=True, exponential backoff (30s, 120s, 600s)
      - Instantiate ContradictionDetectionService, call analyze_record()
      - Does NOT affect IngestionRecord state on failure
    - Implement `auto_screen_on_index` task: queue=`ai_operations`, priority=6, max_retries=1, acks_late=True
      - Only when company config has auto_screen_on_index=True
      - Create ScreeningRun per active protocol, dispatch batch tasks
    - Register all tasks with celery_app
    - _Requirements: 3.3, 3.4, 3.5, 3.7, 3.8, 5.1, 5.8, 11.2, 13.1, 13.4, 13.5, 13.6_

  - [x] 11.2 Write property test: Screening batch count computation (Property 5)
    - **Property 5: Screening batch count computation**
    - Use Hypothesis to generate N (1–500) record IDs and batch_size B (1–100)
    - Assert system dispatches exactly `ceil(N / B)` batch tasks
    - Assert each batch contains at most B record IDs
    - Assert union of all batch record IDs equals original set without duplicates or omissions
    - **Validates: Requirements 3.3**

  - [x] 11.3 Write property test: Screening decisions are append-only and idempotent (Property 7)
    - **Property 7: Screening decisions are append-only and idempotent**
    - Use Hypothesis to generate batches of record IDs within a specific ScreeningRun
    - Simulate executing screening task twice for the same batch
    - Assert no duplicate decisions created (one per record per run)
    - Assert all previously persisted decisions remain unmodified
    - **Validates: Requirements 3.7, 13.4**

- [x] 12. Implement IngestionPipelineService integration
  - [x] 12.1 Extend IngestionPipelineService with Phase 9.4 dispatch
    - Modify existing ingestion pipeline `indexed` state transition handler
    - On `indexed` state transition, check company's `contradiction_detection_enabled` flag
    - If True, dispatch `execute_cross_reference.delay(record_id=..., company_id=...)`
    - Check company's `auto_screen_on_index` flag
    - If True, dispatch `auto_screen_on_index.delay(record_id=..., company_id=...)`
    - _Requirements: 5.1, 11.2, 11.3_

- [x] 13. Implement audit trail integration
  - [x] 13.1 Add literature review audit log entries
    - Extend audit logging to record:
      - Screening decision events (screening_run_id, ingestion_record_id, protocol_id, company_id, verdict, confidence, agent_model_name, screening_duration_ms, timestamp)
      - Human override events (decision_id, review_id, company_id, original_verdict, human_verdict, reviewer_user_id, timestamp)
      - Contradiction alert creation events (alert_id, ingestion_record_id, internal_document_id, company_id, severity, confidence, detection_duration_ms, timestamp)
      - Contradiction alert status change events (alert_id, company_id, previous_status, new_status, acting_user_id, resolution_note/dismissal_reason, timestamp)
      - Novelty flag creation events (flag_id, ingestion_record_id, company_id, relevance_score, high_priority, timestamp)
      - SLR Review state transition events (review_id, company_id, previous_state, new_state, acting_user_id, timestamp)
      - Retry attempt events (task_type, attempt_number, error_message, backoff_duration_s, timestamp)
    - Never log full paper content, internal doc content, or LLM prompt/response text
    - All entries are append-only (ALCOA+ Original and Enduring)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.8_

- [x] 14. Checkpoint - Ensure all components compile and pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Write unit tests for services and routers
  - [x] 15.1 Write unit tests for ScreeningProtocolService
    - Test create_protocol with valid criteria (PICO, inclusion, exclusion)
    - Test create_protocol rejection when no criteria defined (HTTP 422)
    - Test update_protocol auto-versioning
    - Test activate_protocol transition (draft→active only)
    - Test archive_protocol soft-delete behavior
    - Test role-based access (document_admin for mutations, member for reads)
    - Test protocol update with in-progress reviews creates new version
    - Mock database session
    - _Requirements: 2.1, 2.8, 2.9, 2.10_

  - [x] 15.2 Write unit tests for LiteratureScreenerAgentRunner
    - Test _construct_prompt contains title, abstract, PICO criteria, inclusion/exclusion patterns
    - Test _parse_response with valid JSON (correct ScreeningResult)
    - Test _parse_response with malformed JSON (returns None)
    - Test _parse_response with missing fields (returns None)
    - Test _parse_response with confidence outside 0.0–1.0 (returns None)
    - Test screen_record with successful response
    - Test screen_record fallback to uncertain on parse failure
    - Test screen_batch continues on per-record failure
    - Test _get_agent_config loads archetype from registry, falls back on not found
    - Mock InferenceClient and AgentRegistryService
    - _Requirements: 1.3, 1.5, 3.1, 3.2, 3.6_

  - [x] 15.3 Write unit tests for SLRReviewService
    - Test create_review validates protocol exists in company
    - Test state machine transitions (valid paths succeed, invalid rejected with error)
    - Test initiate_screening creates ScreeningRun and dispatches Celery task
    - Test record_human_override stores verdict and rationale
    - Test get_prisma_flow computes correct aggregates
    - Test compute_inter_rater_reliability with known verdict pairs
    - Test _check_auto_completion logic with various confidence scenarios
    - Test generate_report includes all required sections
    - Mock database session and Celery
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.9_

  - [x] 15.4 Write unit tests for ContradictionDetectionService
    - Test analyze_record when no internal docs found (creates NoveltyFlag)
    - Test analyze_record when internal docs found and contradiction detected (creates Alert)
    - Test analyze_record when contradiction below confidence threshold (no alert)
    - Test _escalate_critical invokes ImpactAnalysisService for critical severity
    - Test partial failure handling (persist successful, retry failed pairs)
    - Test _parse_contradiction_response with valid and malformed responses
    - Test novelty_flag high_priority classification (score >= 0.8)
    - Mock HybridQueryEngine, InferenceClient, ImpactAnalysisService
    - _Requirements: 5.2, 5.3, 5.6, 5.7, 6.1, 6.2, 7.1, 7.3, 13.7_

  - [x] 15.5 Write unit tests for API routers
    - Test all screening protocol endpoints (201, 200, 400, 403, 422)
    - Test all SLR review endpoints (201, 202, 200, 400, 403, 404)
    - Test all contradiction/novelty endpoints (200, 400, 403, 404)
    - Test X-Change-Reason requirement on all mutation endpoints (HTTP 400 if missing)
    - Test X-Company-Id requirement on all endpoints (HTTP 400 if missing)
    - Test role-based access control (member for reads, document_admin for mutations, system_admin for config updates)
    - Test cross-tenant access returns 404 (not 403)
    - Test configuration range validation (HTTP 422 for out-of-range values)
    - Test dismiss contradiction requires document_admin/system_admin (HTTP 403 for others)
    - Use FastAPI TestClient with mocked dependencies
    - _Requirements: 8.7, 8.8, 9.9, 9.10, 10.7, 10.8, 10.9, 6.5, 11.4_

  - [x] 15.6 Write property test: Screening Decision persistence round-trip (Property 2)
    - **Property 2: Screening Decision persistence round-trip**
    - Use Hypothesis to generate ScreeningDecisions with valid verdict (include/exclude/uncertain), confidence (0.0–1.0), rationale (0–2000 chars), matched criteria arrays (0–20 integers)
    - Serialize to model, persist (mocked), retrieve by ID, assert identical fields (confidence within 1e-6)
    - **Validates: Requirements 3.2, 15.1**

  - [x] 15.7 Write property test: Contradiction Alert persistence round-trip (Property 3)
    - **Property 3: Contradiction Alert persistence round-trip**
    - Use Hypothesis to generate ContradictionAlerts with valid severity (critical/major/minor), confidence (0.0–1.0), description (1–3000 chars), evidence (1–2000 chars), affected_sections (0–20 items)
    - Serialize to model, persist (mocked), retrieve by ID, assert identical fields (confidence within 1e-6)
    - **Validates: Requirements 5.5, 15.3**

  - [x] 15.8 Write property test: Open alerts aggregate count correctness (Property 14)
    - **Property 14: Open alerts aggregate count correctness**
    - Use Hypothesis to generate sets of ContradictionAlerts with varying statuses (new, acknowledged, resolved, dismissed) and severities
    - Compute summary counts via the summary endpoint logic
    - Assert `total_open_by_severity` counts equal actual count of alerts where status is "new" or "acknowledged", grouped by severity
    - Assert resolved and dismissed alerts are not counted
    - **Validates: Requirements 6.7**

- [x] 16. Write integration tests
  - [x] 16.1 Write integration tests for screening pipeline
    - Test end-to-end: Create protocol → Create review → Initiate screen → Verify decisions persisted
    - Test human override workflow: Screen → Override decision → Verify inter-rater metrics
    - Test SLR lifecycle: protocol_defined → screening → complete → human_review → completed
    - Test re-screening uncertain records (append-only, no duplicates)
    - Test auto-screen on index (enable config → index record → verify screening tasks dispatched)
    - Test report generation (complete review → generate report → verify all sections)
    - Requires Docker PostgreSQL and Redis fixtures
    - _Requirements: 3.1, 3.7, 4.1, 4.4, 4.7, 11.2_

  - [x] 16.2 Write integration tests for contradiction detection pipeline
    - Test end-to-end: Index record → Cross-reference → Verify alert created
    - Test novelty flagging: Index record with no internal doc matches → verify NoveltyFlag
    - Test critical escalation: Create critical alert → verify ImpactAnalysisService invoked
    - Test multi-tenant isolation: Company A data not visible to Company B
    - Test contradiction_detection_enabled=false skips cross-reference
    - Requires Docker PostgreSQL, Redis, and mocked vLLM/OpenSearch
    - _Requirements: 5.1, 5.6, 5.7, 6.2, 11.3_

  - [x] 16.3 Write integration tests for API access control
    - Test all endpoints with correct and incorrect roles
    - Test cross-tenant access returns 404
    - Test X-Change-Reason enforcement on mutations
    - Test configuration update with out-of-range values (HTTP 422)
    - _Requirements: 2.9, 4.8, 6.5, 8.7, 8.8, 9.9, 9.10, 10.7, 10.8, 10.9_

- [x] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (16 total)
- Unit tests validate specific examples and edge cases
- Integration tests require Docker infrastructure (PostgreSQL, Redis, optionally vLLM/OpenSearch mocks)
- All commands use `uv run pytest` per project convention
- Property tests use Hypothesis with `@settings(max_examples=100)` minimum
- Property test file location: `src/backend/tests/properties/test_literature_review_properties.py`
- The Literature Screener YAML archetype is hot-reloaded via existing watchfiles mechanism — no restart needed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.5"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["3.1", "4.1", "9.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "5.1", "9.2"] },
    { "id": 5, "tasks": ["5.2", "6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "6.4", "6.5", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3", "8.4", "10.1", "10.2", "10.3"] },
    { "id": 8, "tasks": ["10.4", "11.1"] },
    { "id": 9, "tasks": ["11.2", "11.3", "12.1"] },
    { "id": 10, "tasks": ["13.1"] },
    { "id": 11, "tasks": ["15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "15.7", "15.8"] },
    { "id": 12, "tasks": ["16.1", "16.2", "16.3"] }
  ]
}
```
