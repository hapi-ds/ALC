# Implementation Plan: Literature Search Engine & External API Gateways (Phase 9.1)

## Overview

This plan implements the literature search gateway in incremental steps. It builds on the existing FastAPI backend, SQLAlchemy models, Celery infrastructure, and Redis cache. Each task builds on previous work, starting with core interfaces and data models, then layering in encryption, rate limiting, circuit breaking, adapters, the orchestrator service, API endpoints, and async tasks.

## Tasks

- [x] 1. Core interfaces, exceptions, and configuration
  - [x] 1.1 Create the literature package structure and adapter base interface
    - Create `src/backend/src/alcoabase/literature/__init__.py`
    - Create `src/backend/src/alcoabase/literature/adapters/__init__.py`
    - Create `src/backend/src/alcoabase/literature/adapters/base.py` with `BaseSourceAdapter` ABC, `AdapterMetadata` dataclass
    - Define abstract methods: `search`, `get_metadata`, `health_check`, `get_capabilities`, `get_adapter_metadata`
    - Create `src/backend/src/alcoabase/literature/services/__init__.py`
    - Create `src/backend/src/alcoabase/literature/schemas/__init__.py`
    - Create `src/backend/src/alcoabase/literature/models/__init__.py`
    - _Requirements: 1.1, 1.4, 2.4_

  - [x] 1.2 Create custom exception hierarchy
    - Create `src/backend/src/alcoabase/literature/exceptions.py`
    - Implement: `LiteratureGatewayError`, `AdapterError`, `AdapterAuthError`, `AdapterTimeoutError`, `AdapterParseError`, `AdapterConnectionError`
    - Implement: `RateLimitExceededError`, `AllSourcesUnavailableError`, `EncryptionKeyMissingError`, `QueueFullError`
    - _Requirements: 2.8, 2.9, 9.1–9.6_

  - [x] 1.3 Extend configuration settings for literature gateway
    - Add literature settings fields to `src/backend/src/alcoabase/config.py` Settings class
    - Fields: `literature_enabled`, `literature_encryption_key`, `literature_adapter_dir`, `literature_proxy_url`, `literature_proxy_user`, `literature_proxy_password`, `literature_health_check_interval_seconds`, `literature_async_result_ttl_seconds`
    - All fields use `ALC_LITERATURE_*` env var aliases
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

- [x] 2. Pydantic schemas
  - [x] 2.1 Create search query and result schemas
    - Create `src/backend/src/alcoabase/literature/schemas/search.py`
    - Implement enums: `PublicationType`, `DatePrecision`, `TaskStatus`
    - Implement `SearchQuery` with field validators (page_size 1–100, date_to after date_from)
    - Implement `LiteratureSearchResult` (frozen model with all normalized fields)
    - Implement `PartialResultInfo`, `SearchResponse`, `AdapterCapabilities`, `AdapterRegistryEntry`
    - Implement `AsyncTaskResponse`, `AsyncTaskStatus`
    - _Requirements: 8.5, 12.1, 12.4, 12.5, 14.5, 15.2_

  - [x] 2.2 Create configuration and profile schemas
    - Create `src/backend/src/alcoabase/literature/schemas/configuration.py`
    - Implement: `SourceConfigurationCreate`, `SourceConfigurationUpdate`, `SourceConfigurationResponse`
    - Create `src/backend/src/alcoabase/literature/schemas/profiles.py`
    - Implement: `SearchProfileCreate`, `SearchProfileUpdate`, `SearchProfileResponse`
    - _Requirements: 3.1, 3.4, 3.5, 13.1, 13.4, 14.1, 14.2_

  - [x] 2.3 Create admin endpoint schemas
    - Create `src/backend/src/alcoabase/literature/schemas/admin.py`
    - Implement: `SystemRateLimitResponse`, `SystemRateLimitUpdate`, `ProxyConfigurationResponse`, `ProxyConfigurationUpdate`
    - Implement: `SourceHealthResponse`, `CompanyUsageResponse`
    - _Requirements: 5.7, 7.1, 11.4, 14.3, 14.4_

  - [x] 2.4 Write property test for pagination validation (Property 14)
    - **Property 14: Pagination Validation**
    - Generate random integers for page_size; verify SearchQuery accepts [1, 100] and rejects outside range
    - **Validates: Requirements 8.5**

  - [x] 2.5 Write property test for JSON round-trip (Property 13)
    - **Property 13: Literature Search Result JSON Round-Trip**
    - Generate valid LiteratureSearchResult instances; verify model_dump_json() → model_validate_json() produces field-by-field equal objects
    - **Validates: Requirements 12.6**

- [x] 3. SQLAlchemy models and migration
  - [x] 3.1 Create SQLAlchemy models for literature feature
    - Create `src/backend/src/alcoabase/literature/models/literature.py`
    - Implement `SourceConfiguration` model with AuditMixin, unique constraint on (company_id, source_adapter_name)
    - Implement `SearchProfile` model with AuditMixin, unique constraint on (company_id, name)
    - Implement `SystemRateLimitConfig` model with AuditMixin
    - Implement `ProxyConfiguration` model with AuditMixin
    - Implement `ExternalAPIAuditLog` model (append-only, no Continuum)
    - Implement `SourceHealthCheck` model
    - Register models in `src/backend/src/alcoabase/literature/models/__init__.py`
    - _Requirements: 3.1, 4.1, 4.2, 5.6, 7.1, 10.1, 10.6, 11.5, 13.1_

  - [x] 3.2 Create Alembic migration for all literature models
    - Generate migration adding: `literature_source_configurations`, `literature_search_profiles`, `literature_system_rate_limits`, `literature_proxy_configuration`, `literature_external_api_audit_log`, `literature_source_health_checks`
    - Include all foreign keys, indexes, unique constraints
    - _Requirements: 3.1, 10.6, 11.5_

- [x] 4. API Key Vault (encryption service)
  - [x] 4.1 Implement APIKeyVault service
    - Create `src/backend/src/alcoabase/literature/services/api_key_vault.py`
    - Implement `EncryptedKey` dataclass (ciphertext, nonce, tag — all base64-encoded)
    - Implement `APIKeyVault.__init__` with 32-byte master key validation
    - Implement `encrypt()` using AES-256-GCM via `cryptography` library, generating random 12-byte nonce per call
    - Implement `decrypt()` with integrity verification via GCM tag
    - Implement `mask_key()` static method (asterisks + last 4 chars; all asterisks for keys < 4 chars)
    - Raise `EncryptionKeyMissingError` if env var not set at startup
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 4.2 Write property test for encryption round-trip (Property 1)
    - **Property 1: API Key Encryption Round-Trip**
    - Generate random strings 1–512 chars (printable Unicode); verify encrypt → decrypt produces identical string
    - **Validates: Requirements 3.4, 4.1, 4.2**

  - [x] 4.3 Write property test for API key masking (Property 2)
    - **Property 2: API Key Masking**
    - Generate random strings; verify mask_key returns correct asterisk prefix + last 4 chars (or all asterisks for short keys)
    - **Validates: Requirements 4.3**

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Rate Limiter (Redis-backed)
  - [x] 6.1 Implement RateLimiter service
    - Create `src/backend/src/alcoabase/literature/services/rate_limiter.py`
    - Implement `RateLimitResult` dataclass and `RateLimitScope` enum
    - Implement Redis sliding window using sorted sets (ZADD/ZRANGEBYSCORE/ZREMRANGEBYSCORE)
    - Implement `check_and_consume()` checking three levels: system per-source (RPS), company all-sources (RPM), company per-source (RPM)
    - Implement request queuing (up to 500 per source) when system limit reached
    - Implement `get_system_limit()`, `set_system_limit()` (1–1000 range validation)
    - Implement `get_company_usage()` returning requests_made, requests_queued, requests_rate_limited
    - Implement `calculate_default_company_limit()`: max(5, system_limit // active_company_count)
    - Apply default limits per source: PubMed 10/100 RPS, Crossref 50 RPS, arXiv 0.33 RPS
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 6.2 Write property test for sliding window enforcement (Property 6)
    - **Property 6: Sliding Window Rate Limit Enforcement**
    - Generate sequences of requests within 1-second windows with various limits; verify at most L requests allowed per window
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 6.3 Write property test for per-company limit derivation (Property 7)
    - **Property 7: Per-Company Rate Limit Derivation**
    - Generate random system limits (1–1000) and company counts (1–100); verify calculate_default_company_limit returns max(5, S // C)
    - **Validates: Requirements 6.4, 6.5**

- [x] 7. Circuit Breaker (Redis-backed)
  - [x] 7.1 Implement CircuitBreaker service
    - Create `src/backend/src/alcoabase/literature/services/circuit_breaker.py`
    - Implement `CircuitState` enum (CLOSED, OPEN, HALF_OPEN)
    - Implement state machine: CLOSED → OPEN after 5 consecutive failures in 5-min window; OPEN → HALF_OPEN after 5-min recovery timeout; HALF_OPEN → CLOSED on success, HALF_OPEN → OPEN on failure
    - Implement `can_execute()`, `record_success()`, `record_failure()`, `get_state()`, `get_estimated_recovery_time()`
    - Store state and failure counts in Redis for cross-worker consistency
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 7.2 Write property test for circuit breaker state transitions (Property 8)
    - **Property 8: Circuit Breaker State Transitions**
    - Generate random sequences of success/failure events; verify state transitions follow the defined state machine rules
    - **Validates: Requirements 9.5**

  - [x] 7.3 Write property test for health status classification (Property 9)
    - **Property 9: Health Status Classification**
    - Generate random response times (0–60s); verify classify_response_time returns AVAILABLE (<5s), DEGRADED (5–15s), UNREACHABLE (≥15s)
    - **Validates: Requirements 11.2**

- [x] 8. Source Registry and Proxy Manager
  - [x] 8.1 Implement Source Registry service
    - Create `src/backend/src/alcoabase/literature/services/source_registry.py`
    - Implement `SourceStatus` enum (AVAILABLE, DEGRADED, UNREACHABLE)
    - Implement `discover_adapters()`: scan configured directory for Python modules exposing BaseSourceAdapter subclass
    - Implement `validate_adapter()`: verify all required methods present (search, get_metadata, health_check, get_capabilities, get_adapter_metadata)
    - Implement `get_adapter()`, `list_adapters()` (with metadata and health status)
    - Implement `run_health_check()` with response time measurement and status classification
    - Implement `classify_response_time()`: <5s AVAILABLE, 5–15s DEGRADED, ≥15s UNREACHABLE
    - Store last 50 health check results per source; flag sources unreachable >30 min
    - Handle missing/unreadable adapter directory gracefully (log error, start with empty registry)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 8.2 Implement Proxy Manager service
    - Create `src/backend/src/alcoabase/literature/services/proxy_manager.py`
    - Implement proxy URL resolution: global proxy, per-source override, no-proxy list
    - Implement proxy credential decryption via APIKeyVault
    - Implement `get_proxy_for_source()` returning httpx proxy config dict
    - Handle no-proxy list matching (hostname and IP range)
    - Return None (direct connection) when no proxy configured
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 8.3 Write property test for adapter validation and isolation (Property 19)
    - **Property 19: Adapter Validation and Isolation**
    - Generate sets of mock adapter objects (some valid, some missing methods); verify only valid ones are registered and invalid ones don't affect valid registrations
    - **Validates: Requirements 1.4, 1.5**

- [x] 9. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Built-in Source Adapters
  - [x] 10.1 Implement PubMed adapter
    - Create `src/backend/src/alcoabase/literature/adapters/pubmed_adapter.py`
    - Implement `PubMedAdapter(BaseSourceAdapter)` querying NCBI E-utilities (eSearch + eFetch)
    - Support authenticated (API key → higher rate limits) and unauthenticated modes
    - Translate SearchQuery to E-utilities query format; normalize XML responses to LiteratureSearchResult
    - Handle partial date normalization (year-only, year-month)
    - Implement health_check against E-utilities info endpoint
    - Declare capabilities: keyword, author, date_range, publication_type
    - Handle HTTP 401/403 as AdapterAuthError, timeout as AdapterTimeoutError, parse failures as AdapterParseError
    - Use httpx.AsyncClient with configurable timeout (15s default) and proxy support
    - _Requirements: 2.1, 2.4, 2.5, 2.8, 2.9, 12.1, 12.2, 12.3, 12.5_

  - [x] 10.2 Implement Crossref adapter
    - Create `src/backend/src/alcoabase/literature/adapters/crossref_adapter.py`
    - Implement `CrossrefAdapter(BaseSourceAdapter)` querying Crossref REST API (/works endpoint)
    - Support authenticated (Crossref Plus token) and unauthenticated (polite pool with mailto) modes
    - Translate SearchQuery to Crossref query params; normalize JSON responses to LiteratureSearchResult
    - Handle partial date normalization
    - Implement health_check against Crossref /works?rows=0
    - Declare capabilities: keyword, author, date_range, DOI
    - _Requirements: 2.2, 2.4, 2.6, 2.8, 2.9, 12.1, 12.2, 12.3, 12.5_

  - [x] 10.3 Implement arXiv adapter
    - Create `src/backend/src/alcoabase/literature/adapters/arxiv_adapter.py`
    - Implement `ArXivAdapter(BaseSourceAdapter)` querying arXiv API (search_query endpoint)
    - Operate in unauthenticated mode only (arXiv requires no API key)
    - Translate SearchQuery to arXiv query format; parse Atom XML responses to LiteratureSearchResult
    - Handle partial date normalization
    - Implement health_check against arXiv API
    - Declare capabilities: keyword, author, date_range
    - _Requirements: 2.3, 2.4, 2.7, 2.8, 2.9, 12.1, 12.2, 12.3, 12.5_

  - [x] 10.4 Write property test for normalization schema conformance (Property 10)
    - **Property 10: Search Result Normalization Schema Conformance**
    - Generate raw API responses with at least title and external_id; verify adapter normalization produces valid LiteratureSearchResult passing Pydantic validation
    - **Validates: Requirements 12.1, 12.4**

  - [x] 10.5 Write property test for missing fields exclusion (Property 11)
    - **Property 11: Missing Required Fields Exclusion**
    - Generate raw responses with optional title/external_id; verify results missing required fields are excluded and normalized count ≤ raw count
    - **Validates: Requirements 12.3**

  - [x] 10.6 Write property test for partial date normalization (Property 12)
    - **Property 12: Partial Date Normalization**
    - Generate date strings with year-only, year-month, and full precision; verify normalization produces correct ISO date and date_precision field
    - **Validates: Requirements 12.5**

- [x] 11. Audit Logger
  - [x] 11.1 Implement Audit Logger service
    - Create `src/backend/src/alcoabase/literature/services/audit_logger.py`
    - Implement `log_request()`: record request_timestamp, source_adapter_name, target URL (redact API keys from query params), user_id, company_id, query_id
    - Implement `log_response()`: record response_timestamp, http_status_code, result_count, response_time_ms
    - Implement `log_failure()`: record error_type, error_message (never include secrets), retry_attempt
    - Persist records to `ExternalAPIAuditLog` model via async SQLAlchemy session
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 11.2 Write property test for secrets never leak (Property 3)
    - **Property 3: Secrets Never Leak**
    - Generate random API key strings and mock adapter errors; verify the key never appears in audit log request_url, error_message, or API response bodies
    - **Validates: Requirements 2.8, 4.3, 10.4**

- [x] 12. Literature Gateway Service (orchestrator)
  - [x] 12.1 Implement LiteratureGatewayService core
    - Create `src/backend/src/alcoabase/literature/services/gateway_service.py`
    - Implement constructor with all service dependencies (source_registry, rate_limiter, circuit_breaker, api_key_vault, audit_logger, proxy_manager)
    - Implement `search()`: dispatch queries to enabled sources in parallel (asyncio.gather), enforce rate limits and circuit breaker, collect results
    - Implement `deduplicate_results()`: deduplicate by DOI (keep highest-priority source), never remove null-DOI results
    - Implement `order_results_by_priority()`: sort by priority number ascending, alphabetical tie-breaking on source_adapter_name
    - Implement `should_dispatch_async()`: True if >3 sources targeted OR >50 results requested
    - Handle partial failures: return results from responding sources, populate partial_results with timed-out/errored sources
    - Return HTTP 503 via AllSourcesUnavailableError when all sources unavailable
    - Return HTTP 429 via RateLimitExceededError with Retry-After when company rate limit hit
    - Enforce 30-second overall search timeout
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 9.1, 9.2, 9.3, 12.1, 12.4_

  - [x] 12.2 Write property test for priority ordering (Property 4)
    - **Property 4: Source Priority Ordering**
    - Generate lists of results with various source priorities (1–100); verify order_results_by_priority returns ascending priority order with alphabetical tie-breaking
    - **Validates: Requirements 3.5, 8.1**

  - [x] 12.3 Write property test for DOI deduplication (Property 5)
    - **Property 5: DOI Deduplication**
    - Generate lists of results with shared non-null DOIs and null DOIs; verify exactly one result per unique DOI retained (from highest-priority source) and null-DOI results never removed
    - **Validates: Requirements 8.3**

  - [x] 12.4 Write property test for partial results on timeout (Property 15)
    - **Property 15: Partial Results on Source Timeout**
    - Generate N sources with K successes and (N-K) timeouts; verify response contains K source results and partial_results.timed_out_sources lists exactly the timed-out sources
    - **Validates: Requirements 8.6**

  - [x] 12.5 Write property test for source filter dispatch (Property 16)
    - **Property 16: Source Filter Dispatch Correctness**
    - Generate queries with source filter lists and registry states; verify dispatch only to sources both in filter AND enabled, with warnings for unavailable sources
    - **Validates: Requirements 8.4**

  - [x] 12.6 Write property test for async dispatch threshold (Property 18)
    - **Property 18: Async Dispatch Threshold**
    - Generate source counts (1–10) and page_size values (1–100); verify should_dispatch_async returns True when >3 sources OR >50 results, False otherwise
    - **Validates: Requirements 15.1**

- [x] 13. Search Profiles and Default Profile Logic
  - [x] 13.1 Implement SearchProfileService
    - Create `src/backend/src/alcoabase/literature/services/search_profile_service.py`
    - Implement CRUD: create_profile, get_profile, list_profiles, update_profile, delete_profile
    - Implement default profile resolution: apply profile's enabled_sources and source_priorities to queries without explicit overrides
    - Validate all referenced source adapters are registered in Source_Registry
    - Enforce single default per company (unset previous default atomically)
    - Provide pre-built templates: "pharma_medtech", "technical_supplier", "general"
    - Record changes in audit trail with X-Change-Reason
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

  - [x] 13.2 Write property test for default profile application (Property 17)
    - **Property 17: Default Profile Application**
    - Generate queries with/without profile_name and explicit source overrides; verify default profile applied when no overrides, and profile NOT applied when query explicitly specifies sources
    - **Validates: Requirements 13.2**

- [x] 14. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. API Router and Endpoints
  - [x] 15.1 Create literature API router with configuration endpoints
    - Create `src/backend/src/alcoabase/api/literature_router.py`
    - Register router in `src/backend/src/alcoabase/api/router.py` with prefix `/literature`
    - Implement CRUD endpoints for Source_Configurations at `/sources/{company_id}/configurations`
    - Implement CRUD endpoints for search profiles at `/sources/{company_id}/profiles`
    - Enforce `document_admin` or `system_admin` role for configuration mutations
    - Require X-Change-Reason header on all mutation endpoints (return 400 if missing)
    - Record configuration changes in audit trail
    - _Requirements: 3.1, 3.2, 3.7, 3.8, 3.9, 14.1, 14.2, 14.7_

  - [x] 15.2 Implement search and admin endpoints
    - Implement POST `/search` endpoint: validate auth (member role), dispatch to gateway service, return SearchResponse (200) or AsyncTaskResponse (202)
    - Implement GET `/sources` endpoint: list registered adapters with capabilities and health
    - Implement GET/PUT `/admin/rate-limits` and `/admin/rate-limits/{source_name}` (system_admin only)
    - Implement GET/PUT `/admin/proxy` (system_admin only)
    - Implement GET `/health` (system_admin only): source health status with last check, avg response time, failure count
    - Implement GET `/usage/{company_id}` (document_admin): company usage metrics
    - Map exceptions to HTTP responses: RateLimitExceededError→429, AllSourcesUnavailableError→503
    - _Requirements: 5.7, 6.6, 7.1, 8.1, 8.7, 11.4, 14.3, 14.4, 14.5, 14.6_

  - [x] 15.3 Implement async task endpoints
    - Implement GET `/tasks/{task_id}` endpoint: return task status (queued/running/completed/failed), progress percentage, partial results
    - Implement DELETE `/tasks/{task_id}` endpoint: cancel running task, retain partial results
    - Require `member` role for task status and cancellation
    - _Requirements: 15.2, 15.4, 15.5_

- [x] 16. Celery Tasks for Async Search
  - [x] 16.1 Implement Celery literature search tasks
    - Create `src/backend/src/alcoabase/tasks/literature_search_tasks.py`
    - Implement `execute_literature_search` task: instantiate gateway service, execute search, store results in Redis with configurable TTL (default 1 hour)
    - Implement task progress reporting (update status: queued → running → completed/failed)
    - Handle task cancellation: check for revoke signal between source queries, retain partial results
    - Record failure reason on task failure
    - Register task in existing Celery app
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 17. Startup Integration and Wiring
  - [x] 17.1 Wire literature gateway into FastAPI application startup
    - Add startup event handler in `src/backend/src/alcoabase/main.py` (or lifespan)
    - Initialize APIKeyVault with master key from settings (refuse to start if missing and literature_enabled=True)
    - Initialize SourceRegistry and run adapter discovery
    - Initialize RateLimiter and CircuitBreaker with Redis connection
    - Initialize ProxyManager, AuditLogger, and LiteratureGatewayService
    - Register periodic health check task (configurable interval, default 5 min)
    - When `ALC_LITERATURE_ENABLED=false`, skip initialization and return 503 on all literature endpoints
    - _Requirements: 1.2, 1.7, 1.8, 4.5, 11.1, 16.1, 16.5, 16.6_

- [x] 18. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 19. Unit tests
  - [x] 19.1 Write unit tests for adapter response parsing
    - Create `src/backend/tests/unit/test_literature/test_adapters.py`
    - Test PubMed XML response parsing (valid, malformed, empty)
    - Test Crossref JSON response parsing (valid, malformed, empty)
    - Test arXiv Atom XML response parsing (valid, malformed, empty)
    - Test error handling paths: 401, 403, 5xx, timeout, parse failure
    - Use respx to mock HTTP responses
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.8, 2.9_

  - [x] 19.2 Write unit tests for configuration and profile services
    - Create `src/backend/tests/unit/test_literature/test_services.py`
    - Test Source_Configuration CRUD with uniqueness constraint enforcement
    - Test SearchProfile CRUD with default profile enforcement
    - Test profile template loading
    - Test proxy routing logic (global, per-source override, no-proxy list)
    - _Requirements: 3.1, 3.2, 3.5, 7.1, 7.4, 7.6, 13.1, 13.4, 13.5_

  - [x] 19.3 Write unit tests for gateway service orchestration
    - Create `src/backend/tests/unit/test_literature/test_gateway.py`
    - Test parallel dispatch to multiple sources
    - Test deduplication logic (shared DOIs, null DOIs)
    - Test priority ordering with tie-breaking
    - Test partial failure handling (some sources timeout)
    - Test async dispatch threshold logic
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 15.1_

- [x] 20. Integration tests
  - [x] 20.1 Write integration tests for full search flow
    - Create `src/backend/tests/integration/test_literature/test_search_flow.py`
    - Test full search flow with mocked external APIs (respx)
    - Test rate limiter with real Redis
    - Test circuit breaker state persistence across calls
    - Test audit log creation and query traceability
    - Test Celery task dispatch and result retrieval
    - _Requirements: 5.6, 8.1, 9.5, 10.1, 10.5, 15.1_

  - [x] 20.2 Write integration tests for API endpoint authorization
    - Create `src/backend/tests/integration/test_literature/test_endpoints.py`
    - Test role-based access: member can search, document_admin can configure, system_admin can manage rate limits/proxy
    - Test X-Change-Reason enforcement on mutation endpoints
    - Test HTTP 403 for unauthorized access attempts
    - Test HTTP 429 response with Retry-After header
    - _Requirements: 3.7, 3.8, 6.3, 8.7, 14.7_

- [x] 21. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (19 properties)
- Tasks marked with `*` are optional and can be skipped for faster MVP
- All backend API endpoints use the `/api/literature` prefix (not `/api/v1`)
- All mutating requests require the `X-Change-Reason` header per AuditMiddleware conventions
- Celery tasks use the existing `celery_app` from `alcoabase/tasks/celery_app.py`
- Redis is used for rate limiting counters, circuit breaker state, and async task results
- The `cryptography` library is used for AES-256-GCM encryption (already available in project)
- httpx is used for all outbound HTTP requests with native proxy and async support
- respx is used for HTTP mocking in tests
- Hypothesis is used for property-based tests with `@settings(max_examples=100)`
- Property test file: `src/backend/tests/properties/test_literature_properties.py`
- Unit test directory: `src/backend/tests/unit/test_literature/`
- Integration test directory: `src/backend/tests/integration/test_literature/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "3.1"] },
    { "id": 2, "tasks": ["2.4", "2.5", "3.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3"] },
    { "id": 4, "tasks": ["6.1", "7.1", "8.1", "8.2"] },
    { "id": 5, "tasks": ["6.2", "6.3", "7.2", "7.3", "8.3"] },
    { "id": 6, "tasks": ["10.1", "10.2", "10.3", "11.1"] },
    { "id": 7, "tasks": ["10.4", "10.5", "10.6", "11.2"] },
    { "id": 8, "tasks": ["12.1", "13.1"] },
    { "id": 9, "tasks": ["12.2", "12.3", "12.4", "12.5", "12.6", "13.2"] },
    { "id": 10, "tasks": ["15.1", "15.2", "15.3"] },
    { "id": 11, "tasks": ["16.1", "17.1"] },
    { "id": 12, "tasks": ["19.1", "19.2", "19.3"] },
    { "id": 13, "tasks": ["20.1", "20.2"] }
  ]
}
```
