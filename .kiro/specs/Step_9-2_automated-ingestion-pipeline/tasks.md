# Implementation Plan: Automated Ingestion Pipeline (Phase 9.2)

## Overview

This plan implements the automated ingestion pipeline that consumes `LiteratureSearchResult` objects from Phase 9.1, implements dual-stage asynchronous processing (metadata → full-text via Unpaywall), sanitizes downloaded content (PDF, HTML, XML/JATS) into a unified `StructuredContent` format, and stores all artifacts in MinIO with company-level isolation. The pipeline reuses Phase 9.1's rate limiter, circuit breaker, audit logger, proxy manager, and API key vault infrastructure.

## Tasks

- [x] 1. Core interfaces, exceptions, and configuration
  - [x] 1.1 Create the ingestion sub-package structure
    - Create `src/backend/src/alcoabase/literature/ingestion/__init__.py`
    - Create `src/backend/src/alcoabase/literature/ingestion/adapters/__init__.py`
    - Create `src/backend/src/alcoabase/literature/ingestion/services/__init__.py`
    - Create `src/backend/src/alcoabase/literature/ingestion/services/sanitization/__init__.py`
    - Create `src/backend/src/alcoabase/literature/ingestion/schemas/__init__.py`
    - Create `src/backend/src/alcoabase/literature/ingestion/models/__init__.py`
    - _Requirements: 1.1, 2.1, 15.6_

  - [x] 1.2 Create custom exception hierarchy for ingestion pipeline
    - Create `src/backend/src/alcoabase/literature/ingestion/exceptions.py`
    - Implement: `IngestionPipelineError` (base), `InvalidStateTransitionError`, `DuplicateRecordError`, `StorageQuotaExceededError`, `ChecksumMismatchError`
    - Implement: `DOINotFoundError`, `NoOpenAccessError`, `UnsupportedContentTypeError`, `FileTooLargeError`
    - Implement: `SanitizationError`, `BatchTooLargeError`, `MaxRetriesExceededError`, `CompanyPausedError`
    - _Requirements: 2.2, 3.3, 3.4, 4.2, 4.3, 4.6, 5.3, 6.5, 14.2, 14.3, 14.7_

  - [x] 1.3 Extend configuration settings for ingestion pipeline
    - Add ingestion settings fields to `src/backend/src/alcoabase/config.py` Settings class
    - Fields: `ingestion_unpaywall_api_url`, `ingestion_literature_bucket`, `ingestion_max_file_size_mb`, `ingestion_retention_days`, `ingestion_storage_quota_mb`, `ingestion_queue_name`, `ingestion_cleanup_cron`, `ingestion_user_agent`
    - All fields use `ALC_LITERATURE_*` or `ALC_UNPAYWALL_*` env var aliases with defaults
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_

- [x] 2. Pydantic schemas
  - [x] 2.1 Create StructuredContent schema
    - Create `src/backend/src/alcoabase/literature/ingestion/schemas/structured_content.py`
    - Implement `SourceFormat` enum (pdf, html, xml)
    - Implement `BodySection` model (heading + text)
    - Implement `StructuredContent` frozen model with field_validator for word_count consistency
    - Validate: `word_count == len(raw_plaintext.split())` and `raw_plaintext == "\n".join([extracted_title, extracted_abstract, *[s.text for s in body_sections]])`
    - _Requirements: 16.1, 16.3, 16.4, 16.5_

  - [x] 2.2 Create ingestion request and response schemas
    - Create `src/backend/src/alcoabase/literature/ingestion/schemas/ingestion.py`
    - Implement `IngestionStateSchema` enum
    - Implement `LiteratureSearchResultInput` with field validators (title min_length=1, max_length=2000; results max 100)
    - Implement `IngestionSubmitRequest` (list of up to 100 results)
    - Implement `BatchIngestionResponse`, `IngestionRecordResponse`, `IngestionRecordListResponse`, `BatchStatusResponse`
    - Implement `StateCounts`, `StorageUsageResponse`, `IngestionHealthResponse`
    - _Requirements: 1.7, 1.8, 2.7, 11.1, 11.2, 11.3, 11.4, 11.9_

  - [x] 2.3 Create ingestion configuration schemas
    - Create `src/backend/src/alcoabase/literature/ingestion/schemas/configuration.py`
    - Implement `IngestionConfigurationCreate` with field_validator: require unpaywall_email when full_text_retrieval_enabled=True, validate email format
    - Implement `IngestionConfigurationUpdate` (all fields optional)
    - Implement `IngestionConfigurationResponse`
    - Enforce: `max_concurrent_downloads` range 1–20, `storage_quota_mb` ge=100, `retention_days` ge=0
    - _Requirements: 8.1, 8.2, 8.6, 8.7, 8.8_

- [x] 3. SQLAlchemy models and Alembic migration
  - [x] 3.1 Create SQLAlchemy models for ingestion pipeline
    - Create `src/backend/src/alcoabase/literature/ingestion/models/ingestion.py`
    - Implement `IngestionRecord` model with AuditMixin, all metadata fields, file storage fields, sanitized content reference, dual-UUID reference, retention fields, state_history JSONB
    - Include UniqueConstraints: `uq_lit_ingestion_company_doi`, `uq_lit_ingestion_company_source_extid`
    - Include Indexes: `ix_lit_ingestion_company_state`, `ix_lit_ingestion_batch`, `ix_lit_ingestion_retention`
    - Implement `IngestionConfiguration` model with AuditMixin, unique on company_id
    - Implement `IngestionAuditLog` model (append-only, no Continuum)
    - Register models in `src/backend/src/alcoabase/literature/ingestion/models/__init__.py`
    - _Requirements: 1.1, 1.2, 1.6, 2.1, 2.3, 2.6, 4.5, 8.1, 9.4, 10.1, 10.2_

  - [x] 3.2 Create Alembic migration for ingestion models
    - Generate migration adding: `literature_ingestion_records`, `literature_ingestion_configurations`, `literature_ingestion_audit_log`
    - Include all foreign keys, indexes, unique constraints as defined in models
    - Test migration runs forward and backward (upgrade + downgrade)
    - _Requirements: 1.1, 8.1, 10.7_

- [x] 4. Ingestion state machine service
  - [x] 4.1 Implement IngestionState enum and transition logic
    - Create `src/backend/src/alcoabase/literature/ingestion/services/state_machine.py`
    - Implement `IngestionState` StrEnum with all 7 states
    - Define `VALID_TRANSITIONS` frozenset of (from_state, to_state) tuples
    - Define `RETRY_TRANSITIONS` frozenset for FAILED → retry states
    - Implement `is_valid_transition()`, `is_valid_retry_transition()`, `get_valid_next_states()`
    - Pure functions — no side effects, no database access
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Storage manager (MinIO operations)
  - [x] 6.1 Implement StorageManager service
    - Create `src/backend/src/alcoabase/literature/ingestion/services/storage_manager.py`
    - Implement `StorageResult` frozen dataclass (object_path, file_size_bytes, sha256_checksum, content_type, upload_timestamp)
    - Implement `build_object_path(company_id, record_id, file_type, filename)` → `{company_id}/{record_id}/{file_type}/{filename}`
    - Implement `store_file()`: compute SHA-256 before upload, upload to MinIO via aioboto3, verify checksum post-upload, attach metadata tags (company_id, ingestion_record_id, content_type, sha256_checksum, ingestion_timestamp, retention_expiry_date)
    - Implement `validate_company_isolation(path, requesting_company_id)` for tenant boundary enforcement
    - Implement `get_company_usage_bytes(company_id)` with Redis caching (5-min TTL)
    - Implement `delete_object(object_path)` for retention cleanup
    - Implement `cleanup_expired_files(batch_size=100)` processing records past retention_expiry_date
    - Handle `ChecksumMismatchError`: delete corrupted object, retry upload once
    - _Requirements: 4.4, 4.5, 4.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 13.1, 13.2, 13.3_

- [x] 7. Unpaywall adapter
  - [x] 7.1 Implement UnpaywallAdapter for DOI resolution
    - Create `src/backend/src/alcoabase/literature/ingestion/adapters/unpaywall_adapter.py`
    - Implement `OALocationPriority` StrEnum and `UnpaywallResult` frozen dataclass
    - Implement `resolve_doi(doi, email, company_id, timeout=15.0)`: query Unpaywall API at `GET /v2/{doi}?email={email}`
    - Implement `select_best_location(oa_locations)`: apply priority order (1) publisher PDF with is_best → (2) repository PDF → (3) publisher HTML → (4) any PDF → (5) any HTML/XML
    - Use existing Rate_Limiter (100,000 requests/day fair use), Circuit_Breaker (5 failures in 5 min), Proxy_Manager
    - Handle HTTP 404 → `DOINotFoundError`, no OA locations → `NoOpenAccessError`, 429 → respect Retry-After + requeue, timeouts → `AdapterTimeoutError`
    - Implement `health_check()` with response time measurement
    - Include User-Agent header from `ALC_LITERATURE_USER_AGENT` setting
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 8. Sanitization pipeline
  - [x] 8.1 Implement BaseSanitizer ABC and PDF sanitizer
    - Create `src/backend/src/alcoabase/literature/ingestion/services/sanitization/pipeline.py` with `BaseSanitizer` ABC and `SanitizationPipeline` dispatcher
    - Create `src/backend/src/alcoabase/literature/ingestion/services/sanitization/pdf_sanitizer.py`
    - Implement `PDFSanitizer` using PyMuPDF (fitz): extract text preserving section boundaries, detect title/abstract/headings/body/references/figure captions/table captions
    - Strip artifacts: headers, footers, page numbers, watermarks, ads
    - Detect scanned-only PDFs → flag `requires_ocr`, transition to `failed` with error_type `ocr_required`
    - Produce `StructuredContent` with word_count > 0 for valid PDFs
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 8.2 Implement HTML sanitizer
    - Create `src/backend/src/alcoabase/literature/ingestion/services/sanitization/html_sanitizer.py`
    - Implement `HTMLSanitizer` using BeautifulSoup: remove navigation, scripts, stylesheets, ads, cookie banners
    - Remove malicious elements: script, iframe, object, embed, form
    - Remove dangerous attributes: onclick, onerror, onload, onmouseover, javascript: URLs
    - Detect character encoding from Content-Type charset / BOM / meta tag, normalize to UTF-8
    - Extract article content into `StructuredContent` schema
    - Handle malformed HTML → transition to `failed` with error_type `parse_error`
    - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6_

  - [x] 8.3 Implement XML/JATS sanitizer
    - Create `src/backend/src/alcoabase/literature/ingestion/services/sanitization/xml_sanitizer.py`
    - Implement `XMLJATSSanitizer` using lxml: parse JATS XML and map elements
    - Map: `front/article-meta` → title/abstract, `body` → body_sections, `back/ref-list` → references
    - Detect character encoding and normalize to UTF-8
    - Handle malformed XML / encoding errors → transition to `failed` with error_type `parse_error`
    - Produce identical `StructuredContent` schema as PDF and HTML sanitizers
    - _Requirements: 6.2, 6.4, 6.5, 6.6, 6.7_

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Ingestion pipeline service (orchestrator)
  - [x] 10.1 Implement IngestionPipelineService
    - Create `src/backend/src/alcoabase/literature/ingestion/services/ingestion_service.py`
    - Implement constructor with dependencies: session_factory, storage_manager, unpaywall_adapter, sanitization_pipeline, audit_logger, rate_limiter, circuit_breaker
    - Implement `submit_batch(results, company_id, user_id)`: validate batch ≤ 100, check duplicates, create IngestionRecords, dispatch Stage 1 Celery tasks, return BatchIngestionResponse
    - Implement `check_duplicate(company_id, doi, source_id, external_id)`: check (company_id + DOI) OR (company_id + source_id + external_id)
    - Implement `transition_state(record_id, target_state, company_id, triggering_event, error_details)`: validate via state machine, persist state, record history, audit log
    - Implement `retry_failed_record(record_id, company_id, user_id)`: validate FAILED state, check retry_count ≤ 3, transition back to failed_from_state, dispatch task
    - Implement `get_state_counts(company_id)`: aggregate counts per state
    - Implement quota enforcement: check storage before dispatching downloads, warn at 90%, reject at 100%
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 8.3, 8.4_

- [x] 11. API router and endpoints
  - [x] 11.1 Create ingestion API router with all endpoints
    - Create `src/backend/src/alcoabase/api/ingestion_router.py`
    - Register router in `src/backend/src/alcoabase/api/router.py` with prefix `/literature/ingest`
    - Implement `POST /api/literature/ingest`: accept batch, require `member` role, return HTTP 202 + BatchIngestionResponse
    - Implement `GET /api/literature/ingest`: list records with filters (state, date_range, doi, source_id), pagination (page_size default 20, max 100)
    - Implement `GET /api/literature/ingest/{ingestion_record_id}`: single record with state history
    - Implement `GET /api/literature/ingest/batch/{batch_id}`: batch status with all records
    - Implement `POST /api/literature/ingest/{ingestion_record_id}/retry`: require `document_admin` role, return HTTP 202
    - Implement `GET /api/literature/ingest/config` and `PUT /api/literature/ingest/config`: require `document_admin` role
    - Implement `GET /api/literature/ingest/storage`: return storage usage, quota, per-state file counts
    - Implement `GET /api/literature/ingest/states`: return aggregated state counts
    - Implement `GET /api/literature/ingest/health`: require `system_admin` role, return pipeline health
    - Require `X-Change-Reason` header on all mutation endpoints (return 400 if missing)
    - Map exceptions to HTTP responses: BatchTooLargeError→413, StorageQuotaExceededError→409, InvalidStateTransitionError→400, CompanyPausedError→429
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 14.6_

- [x] 12. Celery tasks for ingestion pipeline
  - [x] 12.1 Implement Stage 1 metadata ingestion task
    - Create `src/backend/src/alcoabase/tasks/literature_ingestion_tasks.py`
    - Implement `ingest_stage1_metadata` task: create IngestionRecords, store metadata + abstract, transition to `abstract_indexed`, dispatch Stage 2 for records with DOI when full-text enabled
    - Task settings: queue=`literature_ingestion`, priority=1 (high), max_retries=3, default_retry_delay=30
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 12.1_

  - [x] 12.2 Implement Stage 2 download task
    - Implement `ingest_stage2_download` task: acquire Redis semaphore per company, call Unpaywall adapter, download content, validate content_type and size (≤100MB), compute SHA-256, store in MinIO, transition to `full_text_downloaded`, dispatch sanitization task
    - Include User-Agent header with version and company contact email
    - Task settings: queue=`literature_ingestion`, priority=9 (low), max_retries=3, retry backoff (5s, 15s, 45s)
    - Implement Redis-based semaphore for `max_concurrent_downloads` per company (requeue with 30s delay if unavailable)
    - _Requirements: 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 12.2, 12.4, 12.5_

  - [x] 12.3 Implement sanitization task
    - Implement `ingest_sanitize` task: read original file from MinIO, dispatch to SanitizationPipeline, store structured_content.json in MinIO under sanitized prefix, transition to `sanitized`, optionally dispatch dual_uuid_extract task
    - Task settings: queue=`literature_ingestion`, priority=5 (medium), max_retries=2, default_retry_delay=15
    - _Requirements: 5.1, 6.1, 6.2, 12.3, 16.2_

  - [x] 12.4 Implement retention cleanup periodic task
    - Implement `retention_cleanup_task`: identify records past retention_expiry_date, delete original files from MinIO, retain sanitized content, update records with `original_file_purged=True` and purge_timestamp, log audit events
    - Process in batches of 100 per execution
    - Respect `retention_days=0` as indefinite retention
    - Register with Celery beat schedule (default: daily at 02:00 UTC from `ALC_LITERATURE_CLEANUP_CRON`)
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [x] 13. Startup integration and wiring
  - [x] 13.1 Wire ingestion pipeline into FastAPI application startup
    - Add startup initialization in `src/backend/src/alcoabase/main.py` (lifespan or startup event)
    - Initialize StorageManager with MinIO bucket from settings
    - Initialize UnpaywallAdapter with existing RateLimiter, CircuitBreaker, ProxyManager from Phase 9.1
    - Initialize SanitizationPipeline with PDF, HTML, XML sanitizers
    - Initialize IngestionPipelineService with all dependencies
    - Ensure MinIO bucket `alcoabase-literature` exists at startup (create if missing)
    - Register Celery beat schedule for retention_cleanup_task
    - Handle unhandled exceptions in Celery tasks: catch, transition to `failed`, audit log
    - _Requirements: 12.6, 12.7, 14.1, 14.5, 14.6, 15.8_

- [x] 14. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Property-based tests
  - [x] 15.1 Write property test for state machine transition validity (Property 1)
    - **Property 1: Ingestion State Machine Transition Validity**
    - Generate all pairs of `(current_state, target_state)` from `IngestionState` enum
    - Verify `is_valid_transition()` returns True iff pair is in VALID_TRANSITIONS
    - Verify `is_valid_retry_transition(FAILED, target)` returns True iff target is one of `full_text_pending`, `full_text_downloaded`, `sanitized`
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [x] 15.2 Write property test for metadata preservation round-trip (Property 2)
    - **Property 2: Metadata Preservation Round-Trip**
    - Generate valid `LiteratureSearchResultInput` with random fields via Hypothesis strategies
    - Create an IngestionRecord from the input and verify all metadata fields are preserved field-by-field
    - **Validates: Requirements 1.2**

  - [x] 15.3 Write property test for StructuredContent JSON round-trip (Property 3)
    - **Property 3: Structured_Content JSON Round-Trip**
    - Generate valid `StructuredContent` instances with consistent word_count and raw_plaintext
    - Verify `model_dump_json()` → `StructuredContent.model_validate_json()` produces field-by-field equal objects
    - **Validates: Requirements 16.3, 6.7**

  - [x] 15.4 Write property test for StructuredContent internal consistency (Property 4)
    - **Property 4: Structured_Content Internal Consistency**
    - Generate title, abstract, and body sections via `st.text(min_size=1)`
    - Verify: word_count == len(raw_plaintext.split()), raw_plaintext == "\n".join([title, abstract, *section_texts]), non-empty raw_plaintext → word_count > 0
    - **Validates: Requirements 16.4, 16.5, 5.6**

  - [x] 15.5 Write property test for SHA-256 checksum integrity (Property 5)
    - **Property 5: SHA-256 Checksum Integrity**
    - Generate byte sequences via `st.binary(min_size=1, max_size=10_000_000)`
    - Verify: computing SHA-256 twice on same bytes produces identical hex strings; checksum before and after simulated storage round-trip are equal
    - **Validates: Requirements 4.5, 9.5**

  - [x] 15.6 Write property test for deduplication idempotency (Property 6)
    - **Property 6: Deduplication Idempotency**
    - Generate `(company_id, doi, source_id, external_id)` tuples
    - Submit N times (N ≥ 2); verify exactly 1 record created and N-1 detections return the same ID
    - **Validates: Requirements 1.6, 14.4**

  - [x] 15.7 Write property test for storage path company isolation (Property 7)
    - **Property 7: Storage Path Company Isolation**
    - Generate `company_id` and `record_id` as positive integers
    - Verify `build_object_path()` starts with `"{company_id}/"`
    - Verify `validate_company_isolation(path, same_company)` returns True and `validate_company_isolation(path, different_company)` returns False
    - **Validates: Requirements 4.4, 9.1, 9.3**

  - [x] 15.8 Write property test for OA location priority selection (Property 8)
    - **Property 8: OA Location Priority Selection**
    - Generate lists of OA location dicts with varying host_type, url_for_pdf, url_for_landing_page, is_best
    - Verify `select_best_location()` returns highest-priority URL per ordering: publisher PDF with is_best > repository PDF > publisher HTML > any PDF > any HTML/XML
    - Verify empty list or no valid URLs returns None
    - **Validates: Requirements 3.2**

  - [x] 15.9 Write property test for storage quota threshold enforcement (Property 9)
    - **Property 9: Storage Quota Threshold Enforcement**
    - Generate `quota_mb` (1–100000) and `usage_bytes` (0–200000 MB as bytes)
    - Verify: usage ≥ 90% quota → quota_warning=True; usage ≥ 100% quota → downloads rejected; usage < 90% → quota_warning=False and downloads permitted
    - **Validates: Requirements 8.3, 8.4**

  - [x] 15.10 Write property test for content type validation (Property 10)
    - **Property 10: Content Type Validation**
    - Generate random content_type strings via `st.text(min_size=1, max_size=100)`
    - Verify: accepted iff in {application/pdf, text/html, application/xml, text/xml, application/jats+xml}; all others rejected
    - **Validates: Requirements 4.2, 4.3**

  - [x] 15.11 Write property test for HTML sanitization security (Property 11)
    - **Property 11: HTML Sanitization Security**
    - Generate HTML strings containing elements from {script, iframe, object, embed, form} and attributes {onclick, onerror, onload, onmouseover} and javascript: URLs
    - Verify output raw_plaintext and body_sections text contain NONE of these elements/attributes/schemes
    - **Validates: Requirements 6.3**

  - [x] 15.12 Write property test for audit log secret exclusion (Property 12)
    - **Property 12: Audit Log Secret Exclusion**
    - Generate random token strings (8–128 chars) and URLs containing tokens
    - Verify IngestionAuditLog details JSON never contains the raw token; URLs have auth params replaced with [REDACTED]
    - **Validates: Requirements 10.6**

  - [x] 15.13 Write property test for conditional email validation (Property 13)
    - **Property 13: Conditional Email Validation**
    - Generate `full_text_retrieval_enabled` (bool) and `unpaywall_email` (valid/invalid/null)
    - Verify: when enabled=True, null/empty/missing-@ email is rejected; when enabled=False, null email is accepted; invalid format always rejected
    - **Validates: Requirements 8.8**

  - [x] 15.14 Write property test for word count consistency (Property 14)
    - **Property 14: Word Count Consistency**
    - Generate text strings via `st.text(alphabet=st.characters(categories=("L","N","P","Z")))`
    - Verify: `len(text.split())` is deterministic; empty string → 0; StructuredContent.word_count always equals len(raw_plaintext.split())
    - **Validates: Requirements 5.6, 16.4**

- [x] 16. Unit tests
  - [x] 16.1 Write unit tests for state machine and exceptions
    - Create `src/backend/tests/unit/test_ingestion/test_state_machine.py`
    - Test all valid transitions succeed
    - Test all invalid transitions are rejected
    - Test retry transitions from FAILED state
    - Test `get_valid_next_states()` for each state
    - Test exception messages and attributes for all custom exceptions
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x] 16.2 Write unit tests for Unpaywall adapter
    - Create `src/backend/tests/unit/test_ingestion/test_unpaywall_adapter.py`
    - Test successful DOI resolution with various OA location configurations
    - Test `select_best_location()` priority ordering with all combinations
    - Test HTTP 404 → DOINotFoundError, no OA → NoOpenAccessError, 429 → rate limit handling
    - Test circuit breaker integration (open circuit rejects immediately)
    - Use respx to mock Unpaywall API responses
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8_

  - [x] 16.3 Write unit tests for sanitization pipeline
    - Create `src/backend/tests/unit/test_ingestion/test_sanitization.py`
    - Test PDF sanitizer: valid PDF → StructuredContent with sections, scanned-only PDF → ocr_required error
    - Test HTML sanitizer: valid article → clean text, malicious elements stripped, encoding detection
    - Test XML/JATS sanitizer: valid JATS → correct field mapping, malformed XML → parse_error
    - Test SanitizationPipeline dispatcher routes by content_type correctly
    - Test unsupported content_type raises UnsupportedContentTypeError
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.5, 6.6_

  - [x] 16.4 Write unit tests for storage manager
    - Create `src/backend/tests/unit/test_ingestion/test_storage_manager.py`
    - Test `build_object_path()` produces correct path structure
    - Test `validate_company_isolation()` accepts matching company, rejects others
    - Test checksum computation and verification logic
    - Test quota check logic (90% warning, 100% rejection)
    - Test `cleanup_expired_files()` batch processing
    - _Requirements: 9.1, 9.3, 9.5, 9.6, 9.7_

  - [x] 16.5 Write unit tests for ingestion pipeline service
    - Create `src/backend/tests/unit/test_ingestion/test_ingestion_service.py`
    - Test `submit_batch()`: batch size validation, duplicate detection, record creation
    - Test `check_duplicate()`: DOI-based and source+external_id-based matching
    - Test `transition_state()`: valid transitions succeed, invalid transitions rejected, history recorded
    - Test `retry_failed_record()`: validates FAILED state, enforces max retries (3), restores correct state
    - Test quota enforcement during submission
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.4_

  - [x] 16.6 Write unit tests for configuration schemas
    - Create `src/backend/tests/unit/test_ingestion/test_configuration.py`
    - Test default values applied when no explicit config exists
    - Test email validation: required when full_text_retrieval_enabled=True, valid format check
    - Test max_concurrent_downloads range (1–20)
    - Test storage_quota_mb minimum (100)
    - Test retention_days minimum (0)
    - _Requirements: 8.1, 8.2, 8.6, 8.8_

- [x] 17. Integration tests
  - [x] 17.1 Write integration tests for full ingestion flow
    - Create `src/backend/tests/integration/test_ingestion/test_ingestion_flow.py`
    - Test full pipeline: submit → Stage 1 → Stage 2 (mocked Unpaywall via respx) → sanitization → indexed
    - Test deduplication across submissions
    - Test retry flow: failed record → retry → success
    - Test state transition history is correctly recorded
    - Test audit log entries created at each stage
    - Test Celery task dispatch and completion
    - _Requirements: 1.1, 1.6, 2.1, 2.4, 2.6, 10.1, 10.2, 12.1, 12.2, 12.3_

  - [x] 17.2 Write integration tests for API endpoint authorization
    - Create `src/backend/tests/integration/test_ingestion/test_endpoints.py`
    - Test role-based access: `member` can submit and read, `document_admin` can retry and configure, `system_admin` can view health
    - Test `X-Change-Reason` enforcement on POST /ingest, POST /retry, PUT /config (return 400 if missing)
    - Test HTTP 403 for unauthorized access attempts
    - Test pagination on list endpoint (page_size, page)
    - Test filters: state, date_range, doi, source_id
    - Test storage usage endpoint returns correct quota info
    - _Requirements: 11.1, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9_

  - [x] 17.3 Write integration tests for storage and quota enforcement
    - Create `src/backend/tests/integration/test_ingestion/test_storage.py`
    - Test MinIO upload and download with real MinIO (Docker)
    - Test checksum verification (mismatch triggers retry + deletion)
    - Test Redis-cached storage usage (5-min TTL)
    - Test quota warning at 90% and rejection at 100%
    - Test retention cleanup: original file deleted, sanitized content retained, audit logged
    - Test company isolation: cross-company access rejected
    - _Requirements: 4.5, 8.3, 8.4, 9.1, 9.3, 9.5, 9.6, 9.7, 13.1, 13.2, 13.3_

- [x] 18. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (14 properties)
- Tasks marked with `*` are optional and can be skipped for faster MVP
- All backend API endpoints use the `/api/literature/ingest` prefix
- All mutating requests require the `X-Change-Reason` header per AuditMiddleware conventions
- Celery tasks use the existing `celery_app` from `alcoabase/tasks/celery_app.py` with a dedicated `literature_ingestion` queue
- Redis is used for concurrency semaphores, quota caching, and circuit breaker state
- This feature reuses Phase 9.1 services: `rate_limiter.py`, `circuit_breaker.py`, `audit_logger.py`, `proxy_manager.py`, `api_key_vault.py`
- Schemas import `LiteratureSearchResult` from `alcoabase.literature.schemas.search`
- PyMuPDF (fitz) is used for PDF extraction, BeautifulSoup for HTML, lxml for JATS XML
- aioboto3 is used for MinIO S3-compatible operations
- Hypothesis is used for property-based tests with `@settings(max_examples=100)`
- Property test file: `src/backend/tests/properties/test_ingestion_properties.py`
- Unit test directory: `src/backend/tests/unit/test_ingestion/`
- Integration test directory: `src/backend/tests/integration/test_ingestion/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "3.1"] },
    { "id": 2, "tasks": ["3.2", "4.1"] },
    { "id": 3, "tasks": ["6.1", "7.1"] },
    { "id": 4, "tasks": ["8.1", "8.2", "8.3"] },
    { "id": 5, "tasks": ["10.1"] },
    { "id": 6, "tasks": ["11.1"] },
    { "id": 7, "tasks": ["12.1", "12.2", "12.3", "12.4"] },
    { "id": 8, "tasks": ["13.1"] },
    { "id": 9, "tasks": ["15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "15.7", "15.8", "15.9", "15.10", "15.11", "15.12", "15.13", "15.14"] },
    { "id": 10, "tasks": ["16.1", "16.2", "16.3", "16.4", "16.5", "16.6"] },
    { "id": 11, "tasks": ["17.1", "17.2", "17.3"] }
  ]
}
```
