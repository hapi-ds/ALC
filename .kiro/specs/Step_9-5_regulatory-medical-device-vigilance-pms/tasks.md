# Implementation Plan: Regulatory Medical Device Vigilance & Post-Market Surveillance (Phase 9.5)

## Overview

This plan implements the medical device vigilance monitoring system including product portfolio management, vigilance search profiles, scheduled search execution, AI-driven signal detection via the Vigilance Analyst agent, severity-based escalation workflows, and periodic safety report generation for MDR/IVDR regulatory submissions. Tasks are ordered by dependency: configuration/models/schemas first, then the agent archetype, core services, signal detection and escalation, periodic reports, API routers, Celery tasks, ingestion pipeline integration, audit trail, and finally property-based, unit, and integration tests. Each task builds incrementally on previous work, ensuring no orphaned or disconnected code.

## Tasks

- [x] 1. Configuration, models, schemas, exceptions, and migration
  - [x] 1.1 Extend config.py with Phase 9.5 environment settings
    - Add `vigilance_search_queue`, `vigilance_signal_queue`, `vigilance_signal_confidence_threshold`, `vigilance_max_concurrent_detections`, `vigilance_search_timeout`, `vigilance_signal_batch_size`, `vigilance_escalation_retries`, `vigilance_auto_report_enabled` fields to the Settings class in `src/backend/src/alcoabase/config.py`
    - Use Pydantic Field with aliases matching `ALC_VIGILANCE_SEARCH_QUEUE`, `ALC_VIGILANCE_SIGNAL_QUEUE`, `ALC_VIGILANCE_SIGNAL_CONFIDENCE_THRESHOLD`, `ALC_VIGILANCE_MAX_CONCURRENT_DETECTIONS`, `ALC_VIGILANCE_SEARCH_TIMEOUT`, `ALC_VIGILANCE_SIGNAL_BATCH_SIZE`, `ALC_VIGILANCE_ESCALATION_RETRIES`, `ALC_VIGILANCE_AUTO_REPORT_ENABLED`
    - Add startup validation: refuse to start if numeric env vars contain non-numeric or out-of-range values (confidence 0.1–1.0, max_concurrent 1–50, timeout ≥300, batch_size 1–50, retries 1–10)
    - Log resolved config values at INFO on startup
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10_

  - [x] 1.2 Create SQLAlchemy models for Phase 9.5
    - Create `src/backend/src/alcoabase/literature/vigilance/__init__.py`, `models/__init__.py`
    - Create `medical_product.py`: `MedicalProduct` model with name (String 300), udi (String 128, nullable, unique per company), device_class (String 10), gmdn_code (String 20, nullable), intended_purpose (Text), manufacturer_name (String 300, nullable), predicate_devices (ARRAY String 300, nullable), risk_class_justification (Text, nullable), status (String 20, default "active"), AuditMixin, `__versioned__ = {}`
    - Create `vigilance_search_profile.py`: `VigilanceSearchProfile` model with product_id FK, name (String 200), search_terms (ARRAY String 500), mesh_terms (ARRAY String 200, nullable), adverse_event_keywords (ARRAY String 500), device_identifiers (ARRAY String 200, nullable), exclusion_terms (ARRAY String 500, nullable), source_ids (ARRAY String 100, nullable), schedule_cron (String 100), status (String 20, default "active"), AuditMixin, `__versioned__ = {}`
    - Create `vigilance_search_execution.py`: `VigilanceSearchExecution` model (append-only after completion) with profile_id FK, company_id FK, execution_timestamp, search_parameters (JSONB), sources_queried (ARRAY String 100), total_results_found, results_after_exclusion, results_ingested, results_duplicate, execution_duration_ms, status (String 20, default "running")
    - Create `vigilance_signal.py`: `VigilanceSignal` model with ingestion_record_id FK, product_id FK, profile_id FK, company_id FK, severity (String 20), evidence_summary (Text), affected_product_aspects (ARRAY String 500), regulatory_references (ARRAY String 200), recommended_actions (ARRAY String 500), confidence (Float), disposition (String 20, default "under_review"), dismissal_reason (Text, nullable), confirmation_note (Text, nullable), reviewer_user_id (nullable), detection_timestamp, AuditMixin, `__versioned__ = {}`
    - Create `vigilance_configuration.py`: `VigilanceConfiguration` model with unique company_id constraint, critical_signal_auto_escalate (Boolean, default True), major_signal_daily_digest (Boolean, default True), escalation_notification_channels (ARRAY String 50), report_period (String 20, default "quarterly"), report_generation_day (Integer, default 1), auto_report_enabled (Boolean, default True), AuditMixin, `__versioned__ = {}`
    - Create `periodic_safety_report.py`: `PeriodicSafetyReport` model with product_id FK, company_id FK, period_start (Date), period_end (Date), generated_at, report_content (JSONB), status (String 20, default "generated"), version (Integer, default 1), status_history (JSONB, default list), AuditMixin, `__versioned__ = {}`
    - _Requirements: 2.1, 3.1, 4.4, 5.3, 6.4, 7.7, 8.5_

  - [x] 1.3 Create Pydantic schemas for Phase 9.5
    - Create `src/backend/src/alcoabase/literature/vigilance/schemas/__init__.py`
    - Create `product.py`: `MedicalProductCreateSchema`, `MedicalProductUpdateSchema`, `MedicalProductResponseSchema` with field validators (name 1–300 chars, device_class enum, intended_purpose max 5000, udi 1–128, gmdn_code 1–20, predicate_devices max 10 entries each 1–300 chars, risk_class_justification max 3000)
    - Create `profile.py`: `VigilanceSearchProfileCreateSchema`, `VigilanceSearchProfileUpdateSchema`, `VigilanceSearchProfileResponseSchema` with validators (name 1–200, search_terms 1–50 entries each 1–500, mesh_terms 0–30 each 1–200, adverse_event_keywords 1–50 each 1–500, device_identifiers 0–20 each 1–200, exclusion_terms 0–30 each 1–500, schedule_cron 5-field cron validator)
    - Create `execution.py`: `VigilanceSearchExecutionResponseSchema`, `ExecutionListResponseSchema` with pagination
    - Create `signal.py`: `VigilanceSignalResponseSchema`, `SignalDispositionUpdateSchema` (disposition enum, optional confirmation_note max 3000, optional dismissal_reason max 2000), `SignalSummaryResponseSchema`
    - Create `report.py`: `PeriodicSafetyReportResponseSchema`, `ReportStatusUpdateSchema` (status enum, optional comment max 2000), `ReportGenerateRequestSchema` (product_id, period_start, period_end ISO-8601)
    - Create `configuration.py`: `VigilanceConfigurationSchema`, `VigilanceConfigurationUpdateSchema` with range validators (report_generation_day 1–28, report_period enum)
    - _Requirements: 2.1, 2.6, 3.1, 3.6, 6.4, 8.5, 9.1, 9.6, 10.1, 10.3, 11.1, 11.3_

  - [x] 1.4 Create Alembic migration for Phase 9.5 tables
    - Generate migration adding `vigilance_medical_products`, `vigilance_search_profiles`, `vigilance_search_executions`, `vigilance_signals`, `vigilance_configurations`, `vigilance_periodic_safety_reports` tables
    - Include unique constraint on (`company_id`, `udi`) for medical_products WHERE udi IS NOT NULL
    - Include unique constraint on `company_id` for vigilance_configurations
    - Include indexes on `company_id`, `product_id`, `profile_id`, `ingestion_record_id`, `status`, `severity`, `disposition` columns as appropriate
    - _Requirements: 2.1, 2.2, 3.1, 4.4, 5.3, 7.7, 8.5_

  - [x] 1.5 Create vigilance-specific exception classes
    - Create `src/backend/src/alcoabase/literature/vigilance/exceptions.py`
    - Define: `DuplicateUDIError`, `ProductNotFoundError`, `ProfileNotFoundError`, `SignalNotFoundError`, `ReportNotFoundError`, `InvalidDispositionTransitionError`, `InvalidReportStatusTransitionError`, `InvalidCronExpressionError`, `DuplicateExecutionError`, `ExecutionTimeoutError`, `GatewayUnavailableError`, `ConfigurationRangeError`, `InferenceConnectionError`
    - _Requirements: 2.2, 3.2, 6.4, 8.6, 13.1, 13.3, 13.4, 13.6, 14.9_

- [x] 2. Checkpoint - Ensure models and schemas compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Vigilance Analyst Agent archetype definition
  - [x] 3.1 Create vigilance-analyst.yaml agent archetype
    - Create `agents/archetypes/vigilance-analyst.yaml` following agent-definition-v2 JSON schema
    - Set `schema_version: "2.0"`, `archetype: "Vigilance Analyst"`, `agent_type: "review"`
    - Define `personality_profile` with tone "methodical and regulatory-focused", verbosity "detailed", strictness 0.95, domain_focus ["medical-device-vigilance", "adverse-event-assessment", "post-market-surveillance", "regulatory-reporting", "signal-detection"], communication_style describing structured safety signal assessments with regulatory citations
    - Define `system_prompt` instructing evaluation of literature against product profile and vigilance criteria, classifying signal severity using MDR Article 87 serious incident criteria, determining reportability under MEDDEV 2.12/1, and producing JSON response with signal_detected, severity, evidence_summary, affected_product_aspects, regulatory_references, recommended_actions, confidence
    - Define `evaluation_rubric` with: signal_detection_accuracy (0.30), severity_classification_correctness (0.25), regulatory_citation_relevance (0.20), evidence_quality (0.15), response_formatting (0.10), scoring_method "weighted_average"
    - Define `contextual_tuning` with temperature 0.05, max_tokens 6144, top_p 0.90
    - Define `knowledge_scopes` with tags ["Vigilance", "MedicalDevice", "AdverseEvent", "PostMarketSurveillance", "MDR", "IVDR"]
    - Verify hot-reload compatibility with existing watchfiles mechanism in AgentRegistryService
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 4. Implement core services (ProductPortfolioService, VigilanceSearchProfileService, VigilanceMonitorService)
  - [x] 4.1 Implement ProductPortfolioService class
    - Create `src/backend/src/alcoabase/literature/vigilance/services/__init__.py` and `product_portfolio_service.py`
    - Implement `create_product()`: validate required fields (name, device_class, intended_purpose), validate device_class enum, validate field lengths, check UDI uniqueness within company, persist, record audit trail
    - Implement `update_product()`: validate field lengths, check UDI uniqueness on change, on status change to discontinued/recalled suspend associated profiles, record audit trail
    - Implement `soft_delete_product()`: transition status to "discontinued", suspend profiles, record audit trail
    - Implement `list_products()`: paginated, filter by status and device_class, company-scoped
    - Implement `get_product()`: full details with associated profiles and signal counts by severity
    - Validate role requirements: `document_admin` or `system_admin` for mutations
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 4.2 Implement VigilanceSearchProfileService class
    - Create `src/backend/src/alcoabase/literature/vigilance/services/vigilance_search_profile_service.py`
    - Implement `create_profile()`: validate cron expression (5-field), validate search_terms non-empty and adverse_event_keywords non-empty, validate array lengths, check product exists in company, auto-pause if product is discontinued/recalled, persist, record audit trail
    - Implement `update_profile()`: validate same constraints, record audit trail
    - Implement `activate_profile()`: transition to active, register with Celery beat, enforce product not discontinued/recalled
    - Implement `pause_profile()`: transition to paused, remove from Celery beat, preserve history
    - Implement `archive_profile()`: transition to archived, remove from Celery beat
    - Implement `trigger_manual_execution()`: dispatch Celery task regardless of profile status, return task_id
    - Implement `register_all_active_schedules()`: load all active profiles, register with Celery beat (called on startup/restart)
    - Implement `validate_cron_expression()`: validate 5-field cron syntax
    - Validate role requirements: `document_admin` or `system_admin` for mutations
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 4.3 Implement VigilanceMonitorService class
    - Create `src/backend/src/alcoabase/literature/vigilance/services/vigilance_monitor_service.py`
    - Implement `execute_search()`: check idempotency → load profile + product → construct query → execute via LiteratureGatewayService → filter exclusion terms → deduplicate → ingest via IngestionPipelineService → create VigilanceSearchExecution record → audit log
    - Implement `construct_search_query()`: Boolean AND/OR logic — (search_terms OR mesh_terms OR device_identifiers) AND adverse_event_keywords
    - Implement `filter_exclusion_terms()`: case-insensitive substring match against title and abstract, return filtered results
    - Implement `deduplicate_results()`: match on (company_id, DOI) or (company_id, source_id, external_id), return (non_duplicates, duplicate_count)
    - Implement `_check_idempotency()`: verify no "running" execution exists for the same profile
    - Handle execution timeout (60 minutes), partial_failure status, retries (3x exponential backoff: 5min, 15min, 60min)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 13.1, 13.2, 13.4, 13.5, 13.6_

- [x] 5. Checkpoint - Ensure core services compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement signal detection and escalation services
  - [x] 6.1 Implement VigilanceSignalAnalyzer class
    - Create `src/backend/src/alcoabase/literature/vigilance/services/vigilance_signal_analyzer.py`
    - Implement `SignalAnalysisResult` frozen dataclass with signal_detected, severity, evidence_summary, affected_product_aspects, regulatory_references, recommended_actions, confidence, analysis_duration_ms
    - Implement `__init__` with session_factory, InferenceClient, AgentRegistryService, model_name, confidence_threshold (default 0.7), batch_size (default 10)
    - Implement `analyze_record()`: load IngestionRecord content + MedicalProduct metadata → load Vigilance Analyst archetype → construct prompt → dispatch to InferenceClient → parse/validate JSON response → create VigilanceSignal if threshold met → return result
    - Implement `analyze_batch()`: process records sequentially, on per-record failure mark as uncertain and continue
    - Implement `_construct_prompt()`: include paper title, abstract, body (truncated), product name, device_class, intended_purpose, predicate_devices, MDR severity criteria, expected JSON output schema
    - Implement `_parse_response()`: validate signal_detected (bool), severity enum (critical/major/minor/null), confidence 0.0–1.0, evidence_summary presence, recommended_actions max 5; return None on failure
    - Implement `_get_agent_config()`: load archetype from AgentRegistryService, fallback to built-in defaults (temperature 0.05, max_tokens 6144, top_p 0.90)
    - _Requirements: 1.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1_

  - [x] 6.2 Implement VigilanceEscalationService class
    - Create `src/backend/src/alcoabase/literature/vigilance/services/vigilance_escalation_service.py`
    - Implement `__init__` with session_factory, ImpactAnalysisService, ContradictionDetectionService, SLRReviewService, escalation_retries (default 3)
    - Implement `escalate_signal()`: execute 4 independent sub-tasks in parallel (impact analysis, contradiction detection, notification, SLR inclusion), collect results, record full escalation chain in audit trail
    - Implement `_invoke_impact_analysis()`: call ImpactAnalysisService.compute_change_delta with product docs, create mandatory task, return task_id; retry up to 3x with 5-min intervals on failure
    - Implement `_invoke_contradiction_detection()`: call ContradictionDetectionService.analyze_record, return list of created alert IDs
    - Implement `_dispatch_notifications()`: find all document_admin + system_admin users in company, create in-app notifications with signal_id, product_name, severity, evidence_summary (truncated 500 chars), regulatory_references, direct link
    - Implement `_add_to_slr_reviews()`: find active SLR reviews for same product, add record to each, return list of updated review IDs
    - Each sub-task has independent retry logic; failure in one does NOT block others
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 13.8_

- [x] 7. Implement PeriodicReportService
  - [x] 7.1 Implement PeriodicReportService class
    - Create `src/backend/src/alcoabase/literature/vigilance/services/periodic_report_service.py`
    - Implement `generate_report()`: query all VigilanceSearchExecutions + VigilanceSignals in period → build sections (product metadata, period dates, search executions, signals, search strategy, disposition matrix, statistical summary, regulatory compliance) → persist as PeriodicSafetyReport with status "generated"
    - Implement `advance_status()`: validate transition (generated→reviewed→approved→submitted), require document_admin/system_admin, record user_id + timestamp + comment in status_history, audit log
    - Implement `list_reports()`: paginated, filter by product_id, status, period, company-scoped
    - Implement `get_report()`: full report content by ID, company-scoped
    - Implement `_build_disposition_matrix()`: classify every ingested result as no_signal/signal_dismissed/signal_confirmed/signal_escalated; invariant: sum == total results_ingested
    - Implement `_build_statistical_summary()`: total_searches, total_results, signals_by_severity, disposition_breakdown, avg_time_to_disposition
    - Handle empty period: generate report with "No searches executed" section
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 8. Checkpoint - Ensure all services compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement API routers
  - [x] 9.1 Implement vigilance_product_router
    - Create `src/backend/src/alcoabase/api/vigilance_product_router.py`
    - `POST /api/vigilance/products`: require `document_admin` or `system_admin`, require `X-Change-Reason`, validate body, return HTTP 201
    - `GET /api/vigilance/products`: require `member`, paginated list with status/device_class filters
    - `GET /api/vigilance/products/{product_id}`: require `member`, return full product with profiles and signal counts
    - `PUT /api/vigilance/products/{product_id}`: require `document_admin` or `system_admin`, require `X-Change-Reason`, return HTTP 200
    - `DELETE /api/vigilance/products/{product_id}`: require `document_admin` or `system_admin`, require `X-Change-Reason`, soft-delete (set status discontinued), return HTTP 200
    - `POST /api/vigilance/products/{product_id}/profiles`: require `document_admin` or `system_admin`, require `X-Change-Reason`, create profile, return HTTP 201
    - `GET /api/vigilance/products/{product_id}/profiles`: require `member`, list profiles with status filter
    - `PUT /api/vigilance/profiles/{profile_id}`: require `document_admin` or `system_admin`, require `X-Change-Reason`, return HTTP 200
    - `POST /api/vigilance/profiles/{profile_id}/execute`: require `document_admin` or `system_admin`, require `X-Change-Reason`, trigger manual execution, return HTTP 202 with task_id
    - Require `X-Company-Id` header on all endpoints; return HTTP 404 for cross-tenant access
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11_

  - [x] 9.2 Implement vigilance_signal_router
    - Create `src/backend/src/alcoabase/api/vigilance_signal_router.py`
    - `GET /api/vigilance/signals`: require `member`, paginated, filter by severity/disposition/product_id/profile_id, ordered by severity desc then detection_timestamp desc
    - `GET /api/vigilance/signals/{signal_id}`: require `member`, full details with literature metadata, product metadata, disposition history, linked impact reports, linked contradiction alerts
    - `PUT /api/vigilance/signals/{signal_id}/disposition`: require `document_admin` or `system_admin`, require `X-Change-Reason`, validate transition, require confirmation_note or dismissal_reason as appropriate, return HTTP 200
    - `GET /api/vigilance/signals/summary`: require `member`, return aggregate stats (open signals by severity by product, escalated this period, avg time-to-disposition, trend 12 months)
    - `GET /api/vigilance/executions`: require `member`, paginated, filter by profile_id/product_id/status/date_range
    - `GET /api/vigilance/executions/{execution_id}`: require `member`, full execution details with parameters, sources, counts, signal outcomes
    - Require `X-Company-Id` header; return HTTP 404 for cross-tenant access
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

  - [x] 9.3 Implement vigilance_report_router
    - Create `src/backend/src/alcoabase/api/vigilance_report_router.py`
    - `GET /api/vigilance/reports`: require `member`, paginated, filter by product_id/status/period, ordered by generated_at desc
    - `GET /api/vigilance/reports/{report_id}`: require `member`, full report content
    - `PUT /api/vigilance/reports/{report_id}/status`: require `document_admin` or `system_admin`, require `X-Change-Reason`, validate lifecycle transition, accept optional comment, return HTTP 200
    - `POST /api/vigilance/reports/generate`: require `document_admin` or `system_admin`, require `X-Change-Reason`, accept product_id + period_start + period_end, return HTTP 202 with task_id
    - Require `X-Company-Id` header; return HTTP 404 for cross-tenant access
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 9.4 Register routers in central router.py
    - Add `vigilance_product_router`, `vigilance_signal_router`, `vigilance_report_router` to `src/backend/src/alcoabase/api/router.py`
    - Verify route prefixes are `/api/vigilance/products`, `/api/vigilance/signals`, `/api/vigilance/executions`, `/api/vigilance/reports`
    - _Requirements: 9.1, 10.1, 11.1_

- [x] 10. Implement Celery tasks and ingestion pipeline integration
  - [x] 10.1 Implement vigilance_tasks.py
    - Create `src/backend/src/alcoabase/tasks/vigilance_tasks.py`
    - Implement `execute_vigilance_search` task: queue=`literature_ingestion`, priority=5, max_retries=3, soft_time_limit=3600s, acks_late=True, exponential backoff (5min, 15min, 60min)
      - Load VigilanceSearchProfile, instantiate VigilanceMonitorService
      - Execute search, handle idempotency check (skip if already running)
      - On completion: dispatch signal detection for ingested records in batches
    - Implement `execute_signal_detection` task: queue=`ai_operations`, priority=4, max_retries=3, soft_time_limit=1800s, acks_late=True, exponential backoff (30s, 2min, 10min)
      - Instantiate VigilanceSignalAnalyzer, call analyze_batch()
      - On critical signal: dispatch escalate_critical_signal task
      - Idempotent: skip records already analyzed for this execution
    - Implement `escalate_critical_signal` task: queue=`ai_operations`, priority=9 (high for safety), max_retries=3, soft_time_limit=600s, acks_late=True
      - Instantiate VigilanceEscalationService, call escalate_signal()
      - Independent sub-tasks: failure in one doesn't block others
    - Implement `generate_periodic_report` task: queue=`literature_ingestion`, priority=3, max_retries=2, soft_time_limit=1800s, acks_late=True
      - Instantiate PeriodicReportService, call generate_report()
    - Implement `register_vigilance_schedules` task: queue=`literature_ingestion`, acks_late=True
      - Load all active profiles, register with Celery beat
      - Detect in-progress executions and re-queue them
    - Register all tasks with celery_app
    - _Requirements: 4.1, 4.6, 4.8, 5.1, 5.7, 7.1, 8.1, 13.1, 13.2, 13.3, 13.4, 13.5, 13.7_

  - [x] 10.2 Extend IngestionPipelineService with Phase 9.5 dispatch
    - Modify existing ingestion pipeline `indexed` state transition handler
    - On `indexed` state transition for records linked to a VigilanceSearchExecution, dispatch `execute_signal_detection.delay(record_ids=[...], product_id=..., profile_id=..., execution_id=..., company_id=...)`
    - Batch records per configured `vigilance_signal_batch_size` (default 10)
    - Only dispatch when the record has a vigilance_execution_id linkage
    - _Requirements: 5.1, 5.7_

- [x] 11. Implement audit trail integration
  - [x] 11.1 Add vigilance audit log entries
    - Extend audit logging to record:
      - Search execution events (execution_id, profile_id, product_id, company_id, sources_queried, total_results_found, results_ingested, execution_duration_ms, status, timestamp)
      - Signal creation events (signal_id, ingestion_record_id, product_id, profile_id, company_id, severity, confidence, detection_duration_ms, timestamp)
      - Signal disposition change events (signal_id, company_id, previous_disposition, new_disposition, acting_user_id, confirmation_note/dismissal_reason, timestamp)
      - Escalation events (signal_id, company_id, escalation_type, target_service_invoked, success, timestamp)
      - Report generation/status events (report_id, product_id, company_id, period_start, period_end, action, new_status, acting_user_id, timestamp)
      - Product/profile creation/update/status events (entity_type, entity_id, company_id, action, acting_user_id, changed_fields, timestamp)
      - Retry attempt events (task_type, attempt_number, error_message, backoff_duration_s, entity_ids, timestamp)
    - Never log full literature content, full document content, or LLM prompt/response text
    - All entries are append-only (ALCOA+ Original and Enduring)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.7_

- [x] 12. Checkpoint - Ensure all components compile and pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Write property-based tests (20 properties from design)
  - [x] 13.1 Write property test: Medical Product serialization round-trip (Property 1)
    - **Property 1: Medical Product serialization round-trip**
    - Use Hypothesis to generate valid MedicalProduct objects with random device_class from valid enum set, name (1–300 chars), intended_purpose (1–5000 chars), optional udi (1–128 chars), optional predicate_devices (0–10 entries each 1–300 chars), optional gmdn_code (1–20 chars)
    - Serialize to JSON via MedicalProductResponseSchema, deserialize back via Pydantic, assert identical field values including array order preservation
    - **Validates: Requirements 2.1, 15.2**

  - [x] 13.2 Write property test: Vigilance Search Profile serialization round-trip (Property 2)
    - **Property 2: Vigilance Search Profile serialization round-trip**
    - Use Hypothesis to generate valid profiles with search_terms (1–50 entries each 1–500 chars), adverse_event_keywords (1–50 entries each 1–500 chars), mesh_terms (0–30 entries), device_identifiers (0–20 entries), exclusion_terms (0–30 entries), valid 5-field cron expression
    - Serialize to JSON via VigilanceSearchProfileResponseSchema, deserialize back, assert identical field values and array ordering preserved
    - **Validates: Requirements 3.1, 15.3**

  - [x] 13.3 Write property test: Vigilance Signal persistence round-trip (Property 3)
    - **Property 3: Vigilance Signal persistence round-trip**
    - Use Hypothesis to generate signals with valid severity (critical/major/minor), confidence (0.0–1.0), evidence_summary (0–3000 chars), affected_product_aspects (0–10 entries), regulatory_references (0–10 entries), recommended_actions (0–5 entries)
    - Serialize to model, persist (mocked), retrieve by ID, assert identical fields (confidence within 1e-6)
    - **Validates: Requirements 5.3, 15.1**

  - [x] 13.4 Write property test: Signal creation threshold logic (Property 4)
    - **Property 4: Signal creation threshold logic**
    - Use Hypothesis to generate analysis results with signal_detected (boolean) and confidence (0.0–1.0)
    - Assert VigilanceSignal record created if and only if signal_detected is True AND confidence >= threshold (0.7)
    - Assert no signal for results below threshold or with signal_detected=False
    - **Validates: Requirements 5.3, 5.4**

  - [x] 13.5 Write property test: Malformed LLM response produces uncertain fallback (Property 5)
    - **Property 5: Malformed LLM response produces uncertain fallback**
    - Use Hypothesis to generate random non-conforming strings (missing signal_detected field, severity not in valid enum, confidence outside 0.0–1.0, missing evidence_summary, unparseable JSON, random bytes)
    - Assert `_parse_response()` returns None for all malformed inputs
    - Assert that analyze_record with a malformed response marks as "uncertain" and flags for manual review
    - **Validates: Requirements 5.5**

  - [x] 13.6 Write property test: Search query Boolean construction (Property 6)
    - **Property 6: Search query Boolean construction**
    - Use Hypothesis to generate random non-empty search_terms, mesh_terms, adverse_event_keywords, device_identifiers
    - Assert constructed query has structure: (search_terms OR mesh_terms OR device_identifiers) AND adverse_event_keywords
    - Verify all provided terms appear in their correct clause
    - **Validates: Requirements 4.1**

  - [x] 13.7 Write property test: Exclusion term filtering completeness (Property 7)
    - **Property 7: Exclusion term filtering completeness**
    - Use Hypothesis to generate random results (with title/abstract) and random exclusion terms
    - Assert filtered set contains zero results matching any exclusion term (case-insensitive substring)
    - Assert filtered set retains all results not matching any exclusion term
    - **Validates: Requirements 4.3**

  - [x] 13.8 Write property test: Search execution count invariant (Property 8)
    - **Property 8: Search execution count invariant**
    - Use Hypothesis to generate random count tuples (total_results_found, results_after_exclusion, results_ingested, results_duplicate)
    - Assert invariant: total_results_found >= results_after_exclusion >= results_ingested + results_duplicate
    - Assert results_after_exclusion == results_ingested + results_duplicate
    - **Validates: Requirements 4.4, 15.5**

  - [x] 13.9 Write property test: Deduplication correctness (Property 9)
    - **Property 9: Deduplication correctness**
    - Use Hypothesis to generate result sets with known duplicates (matching DOI or source_id + external_id)
    - Assert non-duplicate set contains zero records matching existing records
    - Assert duplicate_count == total minus non_duplicate count
    - **Validates: Requirements 4.7**

  - [x] 13.10 Write property test: Signal disposition state machine (Property 10)
    - **Property 10: Signal disposition state machine**
    - Use Hypothesis to generate random (current_disposition, target_disposition) pairs from all possible values
    - Assert transition succeeds only for valid paths: under_review→confirmed, under_review→dismissed, under_review→escalated, confirmed→escalated
    - Assert InvalidDispositionTransitionError for invalid pairs
    - Assert dismissed requires non-empty dismissal_reason, confirmed requires non-empty confirmation_note
    - **Validates: Requirements 6.4**

  - [x] 13.11 Write property test: Report status lifecycle state machine (Property 11)
    - **Property 11: Report status lifecycle state machine**
    - Use Hypothesis to generate random (current_status, target_status) pairs
    - Assert transition succeeds only for: generated→reviewed→approved→submitted
    - Assert InvalidReportStatusTransitionError for invalid/backward/skip transitions
    - Assert each transition records user_id and timestamp
    - **Validates: Requirements 8.6**

  - [x] 13.12 Write property test: Disposition matrix completeness invariant (Property 12)
    - **Property 12: Disposition matrix completeness invariant**
    - Use Hypothesis to generate random execution/signal data for a report period
    - Assert sum(no_signal + signal_dismissed + signal_confirmed + signal_escalated) == total_results_ingested
    - Every ingested result classified exactly once
    - **Validates: Requirements 8.4, 15.4**

  - [x] 13.13 Write property test: Report statistical monotonic invariant (Property 13)
    - **Property 13: Report statistical monotonic invariant**
    - Use Hypothesis to generate random count data for report executions
    - Assert total_results_found >= results_after_exclusion >= results_ingested across all executions
    - **Validates: Requirements 15.4**

  - [x] 13.14 Write property test: Critical signal escalation triggers (Property 14)
    - **Property 14: Critical signal escalation triggers**
    - Use Hypothesis to generate signals with varying severity (critical/major/minor) and company config (auto_escalate True/False)
    - Assert ImpactAnalysisService + ContradictionDetectionService invoked only for severity "critical" AND auto_escalate=True
    - Assert no invocation for "major" or "minor" or when auto_escalate=False
    - **Validates: Requirements 7.1, 7.3**

  - [x] 13.15 Write property test: Open signals aggregate count correctness (Property 15)
    - **Property 15: Open signals aggregate count correctness**
    - Use Hypothesis to generate sets of VigilanceSignals with varying dispositions and severities
    - Assert summary counts per product per severity equal actual count where disposition is "under_review" or "confirmed"
    - Assert "dismissed" and "escalated" signals not counted as open
    - **Validates: Requirements 6.6**

  - [x] 13.16 Write property test: Signal detection batch computation (Property 16)
    - **Property 16: Signal detection batch computation**
    - Use Hypothesis to generate N (1–500) record IDs and batch_size B (1–50)
    - Assert system dispatches exactly ceil(N / B) batch tasks
    - Assert each batch contains at most B record IDs
    - Assert union of all batch record IDs equals original set without duplicates or omissions
    - **Validates: Requirements 5.7**

  - [x] 13.17 Write property test: Idempotent vigilance search execution (Property 17)
    - **Property 17: Idempotent vigilance search execution**
    - Use Hypothesis to generate concurrent execution scenarios for same profile
    - Assert only one execution per profile may be in "running" status at any time
    - Assert duplicate attempts are skipped with informational log
    - **Validates: Requirements 13.4**

  - [x] 13.18 Write property test: Configuration range enforcement (Property 18)
    - **Property 18: Configuration range enforcement**
    - Use Hypothesis to generate config values outside valid ranges (confidence outside 0.1–1.0, max_concurrent outside 1–50, timeout < 300, batch_size outside 1–50)
    - Assert rejection/startup failure for out-of-range values
    - Generate in-range values and assert acceptance
    - **Validates: Requirements 14.3, 14.4, 14.5, 14.6**

  - [x] 13.19 Write property test: Required field validation for Medical Products (Property 19)
    - **Property 19: Required field validation for Medical Products**
    - Use Hypothesis to generate product creation requests with various combinations of present/absent required fields
    - Assert rejection (HTTP 422) when name is empty/missing, device_class is invalid/missing, or intended_purpose is empty/missing
    - Assert acceptance when all three required fields are present and valid
    - **Validates: Requirements 2.6**

  - [x] 13.20 Write property test: Required array validation for Search Profiles (Property 20)
    - **Property 20: Required array validation for Search Profiles**
    - Use Hypothesis to generate profile creation requests with various combinations of empty/non-empty search_terms and adverse_event_keywords
    - Assert rejection (HTTP 422) when either search_terms or adverse_event_keywords is empty
    - Assert acceptance when both contain at least one entry
    - **Validates: Requirements 3.6**

- [x] 14. Write unit tests for services and routers
  - [x] 14.1 Write unit tests for ProductPortfolioService
    - Test create_product with valid fields (all required + optional)
    - Test create_product rejection when required fields missing (HTTP 422)
    - Test create_product rejection with duplicate UDI in same company (HTTP 409)
    - Test create_product success with same UDI in different company
    - Test update_product status change to discontinued suspends profiles
    - Test soft_delete transitions to discontinued, suspends profiles
    - Test list_products pagination and filtering (status, device_class)
    - Test get_product returns profiles and signal counts
    - Test role-based access (document_admin/system_admin for mutations, member for reads)
    - Mock database session
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6_

  - [x] 14.2 Write unit tests for VigilanceSearchProfileService
    - Test create_profile with valid cron expression and arrays
    - Test create_profile rejection with invalid cron (HTTP 422)
    - Test create_profile rejection with empty search_terms or adverse_event_keywords (HTTP 422)
    - Test create_profile auto-pauses when product is discontinued/recalled
    - Test activate_profile registers with Celery beat
    - Test pause_profile removes from Celery beat, preserves history
    - Test trigger_manual_execution dispatches Celery task regardless of status
    - Test register_all_active_schedules loads and registers all active profiles
    - Test validate_cron_expression with valid/invalid expressions
    - Test role-based access
    - Mock database session and Celery
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 14.3 Write unit tests for VigilanceMonitorService
    - Test execute_search end-to-end with mocked gateway and pipeline
    - Test construct_search_query Boolean logic (AND/OR structure)
    - Test filter_exclusion_terms with matching/non-matching terms
    - Test deduplicate_results with known duplicates (DOI match, source+external_id match)
    - Test idempotency check (skip when already running)
    - Test execution timeout handling (partial_failure after 60 min)
    - Test retry behavior on gateway failure (3x exponential backoff)
    - Test zero results execution (completed with count 0)
    - Mock LiteratureGatewayService, IngestionPipelineService, database session
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 13.1, 13.4, 13.6_

  - [x] 14.4 Write unit tests for VigilanceSignalAnalyzer
    - Test _construct_prompt contains product name, device_class, intended_purpose, MDR severity criteria, expected JSON schema
    - Test _parse_response with valid JSON (correct SignalAnalysisResult)
    - Test _parse_response with malformed JSON (returns None)
    - Test _parse_response with missing fields, wrong severity enum, confidence out of range (returns None)
    - Test analyze_record with successful response above threshold (creates signal)
    - Test analyze_record with response below threshold (no signal, records no_signal)
    - Test analyze_record fallback to uncertain on parse failure
    - Test analyze_batch continues on per-record failure
    - Test _get_agent_config loads archetype, falls back on not found
    - Mock InferenceClient and AgentRegistryService
    - _Requirements: 1.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 14.5 Write unit tests for VigilanceEscalationService
    - Test escalate_signal dispatches all 4 sub-tasks for critical signal with auto_escalate=True
    - Test escalate_signal skips when auto_escalate=False
    - Test _invoke_impact_analysis creates task, retries on failure
    - Test _invoke_contradiction_detection cross-references literature
    - Test _dispatch_notifications sends to all admin users with correct content (truncated evidence_summary 500 chars)
    - Test _add_to_slr_reviews finds active reviews for product
    - Test partial failure isolation (one sub-task fails, others succeed)
    - Test audit trail records full escalation chain
    - Mock ImpactAnalysisService, ContradictionDetectionService, SLRReviewService
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 13.8_

  - [x] 14.6 Write unit tests for PeriodicReportService
    - Test generate_report includes all 8 sections
    - Test generate_report with empty period (no executions) includes "No searches executed" section
    - Test _build_disposition_matrix sum invariant (sum == total_results_ingested)
    - Test _build_statistical_summary computes correct totals
    - Test advance_status valid transitions (generated→reviewed→approved→submitted)
    - Test advance_status rejects invalid/backward transitions
    - Test advance_status records user_id, timestamp, comment in status_history
    - Test list_reports pagination and filtering
    - Test role-based access (document_admin/system_admin for status changes)
    - Mock database session
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 14.7 Write unit tests for API routers
    - Test all product endpoints (201, 200, 400, 403, 409, 422)
    - Test all profile endpoints (201, 200, 202, 400, 403, 404, 422)
    - Test all signal endpoints (200, 400, 403, 404)
    - Test signal disposition endpoint with valid/invalid transitions
    - Test all report endpoints (200, 202, 400, 403, 404)
    - Test X-Change-Reason requirement on all mutation endpoints (HTTP 400 if missing)
    - Test X-Company-Id requirement on all endpoints (HTTP 400 if missing)
    - Test role-based access control (member for reads, document_admin for writes)
    - Test cross-tenant access returns 404 (not 403)
    - Test execution endpoints with date_range filtering
    - Use FastAPI TestClient with mocked dependencies
    - _Requirements: 9.10, 9.11, 10.7, 10.8, 10.9, 11.5, 11.6, 11.7_

- [x] 15. Write integration tests
  - [x] 15.1 Write integration tests for vigilance search pipeline
    - Test end-to-end: Create product → Create profile → Execute search → Verify execution record with correct counts
    - Test deduplication: Execute same search twice → Verify duplicates counted
    - Test exclusion filtering: Configure exclusion terms → Execute → Verify matching results excluded
    - Test manual execution on paused profile → Verify execution runs regardless of status
    - Test zero results: Execute search with no matches → Verify completed with count 0
    - Test execution timeout: Simulate long-running search → Verify partial_failure
    - Test dynamic schedule registration: Start worker → Verify active profiles registered with Celery beat
    - Requires Docker PostgreSQL and Redis fixtures
    - _Requirements: 4.1, 4.3, 4.5, 4.7, 4.8, 13.4, 13.6_

  - [x] 15.2 Write integration tests for signal detection and escalation pipeline
    - Test end-to-end: Index record (vigilance-linked) → Signal detection → Verify signal created
    - Test batch processing: Multiple records from same execution → Verify batch dispatch
    - Test critical escalation: Create critical signal → Verify impact analysis + contradiction + notification + SLR inclusion
    - Test major signal: Create major signal → Verify no automatic escalation, flagged for daily digest
    - Test malformed LLM response: Verify uncertain status and manual review flag
    - Test vLLM retry: Simulate unavailability → Verify 3 retries with backoff
    - Requires Docker PostgreSQL, Redis, and mocked vLLM
    - _Requirements: 5.1, 5.3, 5.5, 5.6, 5.7, 6.2, 6.3, 7.1, 7.3, 13.3_

  - [x] 15.3 Write integration tests for periodic reports and product lifecycle
    - Test report generation: Execute searches over period → Generate report → Verify all sections and disposition matrix invariant
    - Test report status lifecycle: generated → reviewed → approved → submitted with audit trail
    - Test product lifecycle: Create → Update → Discontinue → Verify profiles suspended
    - Test UDI uniqueness: Same UDI same company → 409; same UDI different company → OK
    - Test empty period report: No executions → Report generated with explanation section
    - Test multi-tenant isolation: Company A data not visible to Company B
    - Requires Docker PostgreSQL and Redis fixtures
    - _Requirements: 2.2, 2.3, 8.1, 8.4, 8.6, 8.7_

  - [x] 15.4 Write integration tests for API access control
    - Test all endpoints with correct and incorrect roles
    - Test cross-tenant access returns 404
    - Test X-Change-Reason enforcement on all mutations
    - Test X-Company-Id requirement
    - Test signal disposition with invalid transitions (rejected)
    - Test report status with invalid transitions (rejected)
    - Test configuration range validation for env vars
    - _Requirements: 2.5, 3.7, 6.5, 9.10, 9.11, 10.7, 10.8, 10.9, 11.5, 11.6_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (20 total)
- Unit tests validate specific examples and edge cases
- Integration tests require Docker infrastructure (PostgreSQL, Redis, optionally vLLM mocks)
- All commands use `uv run pytest` per project convention
- Property tests use Hypothesis with `@settings(max_examples=100)` minimum
- Property test file location: `src/backend/tests/properties/test_vigilance_properties.py`
- The Vigilance Analyst YAML archetype is hot-reloaded via existing watchfiles mechanism — no restart needed
- Signal detection confidence threshold is configurable via `ALC_VIGILANCE_SIGNAL_CONFIDENCE_THRESHOLD` (default 0.7)
- Batch size configurable via `ALC_VIGILANCE_SIGNAL_BATCH_SIZE` (default 10, range 1–50)
- All vigilance operations are company-scoped via `X-Company-Id` header for multi-tenancy isolation

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.5"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4"] },
    { "id": 3, "tasks": ["3.1"] },
    { "id": 4, "tasks": ["4.1", "4.2", "4.3"] },
    { "id": 5, "tasks": ["6.1", "6.2"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["9.1", "9.2", "9.3"] },
    { "id": 8, "tasks": ["9.4", "10.1"] },
    { "id": 9, "tasks": ["10.2"] },
    { "id": 10, "tasks": ["11.1"] },
    { "id": 11, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6", "13.7", "13.8", "13.9", "13.10", "13.11", "13.12", "13.13", "13.14", "13.15", "13.16", "13.17", "13.18", "13.19", "13.20"] },
    { "id": 12, "tasks": ["14.1", "14.2", "14.3", "14.4", "14.5", "14.6", "14.7"] },
    { "id": 13, "tasks": ["15.1", "15.2", "15.3", "15.4"] }
  ]
}
```
