# Requirements Document

## Introduction

This document specifies the requirements for the Literature Search Engine & External API Gateways feature (Phase 9.1) of AlcoaBase. This is the first phase that introduces controlled external network access in an otherwise air-gapped system. The feature establishes secure, multi-tenant API integrations with major scientific and medical literature databases (PubMed/MEDLINE, Crossref, arXiv, and open-access publisher APIs). Individual companies can configure their own API keys, rate limits, and priority search indices based on their regulatory vertical. All external API calls are logged in the audit trail, API keys are encrypted at rest, and the architecture supports adding new literature sources without code changes via a plugin/adapter pattern. The system supports proxy/firewall configuration for controlled external access and gracefully handles network failures, API downtime, and rate limit responses.

## Glossary

- **Literature_Gateway_Service**: The backend service responsible for orchestrating external literature API calls, enforcing rate limits, managing adapter lifecycle, and returning normalized search results to internal consumers.
- **Source_Adapter**: A pluggable module implementing a standardized interface for communicating with a specific external literature API (e.g., PubMed, Crossref, arXiv). New adapters can be registered without code changes to the core service.
- **Source_Configuration**: A per-company, per-source record storing the enabled/disabled state, API key (encrypted), rate limit overrides, priority ranking, and proxy settings for a specific literature source.
- **API_Key_Vault**: The encryption layer responsible for storing and retrieving API keys using AES-256-GCM encryption at rest, scoped to a specific company and source combination.
- **Rate_Limiter**: The component enforcing request rate limits at both the system-wide level (protecting external APIs from overuse) and the per-company level (ensuring fair resource sharing between tenants).
- **Network_Proxy**: The configurable HTTP/HTTPS proxy through which all outbound literature API requests are routed, enabling controlled external access in otherwise air-gapped environments.
- **Literature_Search_Result**: A normalized data structure representing a single search result from any literature source, containing title, authors, abstract, DOI, publication date, source identifier, and metadata.
- **Source_Registry**: The internal registry that tracks all available Source_Adapters, their health status, supported query capabilities, and version information.
- **Audit_Logger**: The component responsible for recording all external API interactions (requests, responses, errors) in the immutable audit trail with full traceability.
- **Company**: The multi-tenant entity (from Phase 1.1) to which all Source_Configurations, rate limits, and search operations are scoped.
- **Search_Query**: A structured request containing search terms, filters (date range, source selection, publication type), pagination parameters, and the requesting company context.

## Requirements

### Requirement 1: Source Adapter Plugin Architecture

**User Story:** As a system administrator, I want to add new literature sources without modifying core application code, so that the system can evolve to support additional databases as regulatory needs change.

#### Acceptance Criteria

1. THE Source_Registry SHALL provide a standardized adapter interface defining methods for search, metadata retrieval, health check, and capability declaration, where capability declaration returns the supported query fields (e.g., keyword, author, date range, publication type) and supported response formats.
2. WHEN the application starts, THE Source_Registry SHALL discover and register Source_Adapters by scanning the configured adapter directory for Python modules that expose a class implementing the adapter interface.
3. WHEN a new Source_Adapter is placed in the adapter directory and the application is restarted, THE Source_Registry SHALL register the adapter and make it available in the source registry API endpoint without changes to existing code.
4. WHEN a Source_Adapter is discovered during startup, THE Source_Registry SHALL validate it by verifying it implements all required interface methods (search, get_metadata, health_check, get_capabilities) before adding it to the active registry.
5. IF a Source_Adapter fails validation at registration time, THEN THE Source_Registry SHALL log a warning with the adapter name and the specific missing or malformed method, and SHALL exclude the adapter from the active registry without affecting the registration of other adapters.
6. THE Source_Registry SHALL expose an API endpoint listing all registered adapters with their name, version, declared query capabilities (supported query fields and filters), and current health status.
7. IF the configured adapter directory does not exist or is not readable at application startup, THEN THE Source_Registry SHALL log an error indicating the directory path and the specific filesystem error, and SHALL start with an empty adapter registry.
8. IF no Source_Adapters are discovered in the adapter directory at startup, THEN THE Source_Registry SHALL log an informational message and start normally with an empty active registry, returning an empty list from the registry API endpoint.

### Requirement 2: Built-In Source Adapters

**User Story:** As a quality manager, I want pre-configured adapters for major scientific databases, so that I can immediately search PubMed, Crossref, and arXiv without custom development.

#### Acceptance Criteria

1. THE Source_Registry SHALL include a built-in PubMed_Adapter that queries the NCBI E-utilities API (eSearch and eFetch endpoints) and returns results as Literature_Search_Results.
2. THE Source_Registry SHALL include a built-in Crossref_Adapter that queries the Crossref REST API (/works endpoint) and returns results as Literature_Search_Results.
3. THE Source_Registry SHALL include a built-in ArXiv_Adapter that queries the arXiv API (search_query endpoint) and returns results as Literature_Search_Results.
4. WHEN a Source_Adapter receives a Search_Query, THE Source_Adapter SHALL translate the query into the source-specific API format, execute the request with a per-request timeout of 15 seconds, and normalize the response into Literature_Search_Results.
5. THE PubMed_Adapter SHALL support both authenticated (API key) and unauthenticated access modes, with authenticated mode providing higher rate limits as defined by NCBI policy.
6. THE Crossref_Adapter SHALL support both authenticated (Crossref Plus API token) and unauthenticated (polite pool) access modes, where unauthenticated mode uses a mailto contact email read from the Source_Configuration for the requesting company.
7. THE ArXiv_Adapter SHALL operate in unauthenticated mode as arXiv does not require API keys.
8. IF a Source_Adapter receives an HTTP 401 or 403 response from its external API, THEN THE Source_Adapter SHALL mark the request as an authentication failure, return an error indicating invalid or expired credentials for that source, and log the event without exposing the API key value.
9. IF a Source_Adapter receives a response that cannot be parsed according to the expected source API format, THEN THE Source_Adapter SHALL discard the unparseable response, return an error indicating a malformed response from the source, and log the raw response size and content type for diagnostic purposes.

### Requirement 3: Per-Company Source Configuration

**User Story:** As a document administrator, I want to configure which literature sources my company uses and provide our own API keys, so that search results are relevant to our regulatory vertical and we control our own API access.

#### Acceptance Criteria

1. WHEN a document_administrator creates a Source_Configuration for a company, THE Literature_Gateway_Service SHALL store the configuration scoped to that company ID and source adapter name, enforcing a uniqueness constraint on the combination of company ID and source adapter name.
2. IF a document_administrator attempts to create a Source_Configuration for a company and source adapter combination that already exists, THEN THE Literature_Gateway_Service SHALL reject the request with an error indicating a duplicate configuration.
3. THE Literature_Gateway_Service SHALL allow each company to independently enable or disable any registered Source_Adapter via the Source_Configuration.
4. WHEN a document_administrator provides an API key in a Source_Configuration, THE API_Key_Vault SHALL encrypt the key using AES-256-GCM before persisting it to the database, accepting keys between 1 and 512 characters in length.
5. THE Literature_Gateway_Service SHALL allow each company to set a priority ranking (integer 1–100, where 1 is highest priority) for each enabled source, determining the default search order; WHEN two or more sources share the same priority ranking, THE Literature_Gateway_Service SHALL use alphabetical order of the source adapter name as the tie-breaker.
6. WHEN a company has no Source_Configuration for a registered adapter, THE Literature_Gateway_Service SHALL treat that source as disabled for the company.
7. THE Literature_Gateway_Service SHALL require the `document_admin` or `system_admin` role to create, update, or delete Source_Configurations.
8. IF a user without the `document_admin` or `system_admin` role attempts to create, update, or delete a Source_Configuration, THEN THE Literature_Gateway_Service SHALL return HTTP 403 and SHALL NOT modify the configuration.
9. WHEN a Source_Configuration is created, updated, or deleted, THE Literature_Gateway_Service SHALL record the change in the audit trail with the X-Change-Reason header value, acting user, and company ID.

### Requirement 4: API Key Security

**User Story:** As a system administrator, I want API keys encrypted at rest and never exposed in plaintext through the API, so that credentials remain secure even if the database is compromised.

#### Acceptance Criteria

1. THE API_Key_Vault SHALL encrypt all API keys using AES-256-GCM with a master encryption key derived from an environment variable.
2. THE API_Key_Vault SHALL store the encryption nonce alongside the ciphertext to enable decryption.
3. WHEN a Source_Configuration is retrieved via the API, THE Literature_Gateway_Service SHALL return a masked representation of the API key (showing only the last 4 characters) and SHALL never return the plaintext or ciphertext.
4. THE API_Key_Vault SHALL decrypt API keys only at the moment of outbound API request construction, holding the plaintext in memory for the minimum duration required.
5. IF the master encryption key environment variable is not set, THEN THE Literature_Gateway_Service SHALL refuse to start and log an error indicating the missing configuration.
6. WHEN a Source_Configuration's API key is updated, THE API_Key_Vault SHALL overwrite the previous ciphertext with the newly encrypted value without retaining the old key material.

### Requirement 5: Rate Limiting — System Level

**User Story:** As a system administrator, I want system-wide rate limits per external API, so that AlcoaBase respects external service usage policies and avoids being blocked.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL enforce a configurable maximum requests-per-second limit for each registered Source_Adapter at the system level (across all companies), with configurable values ranging from 1 to 1000 requests per second.
2. THE Rate_Limiter SHALL use a sliding window algorithm to track request counts per source over a 1-second window granularity.
3. WHEN the system-level rate limit for a source is reached, THE Rate_Limiter SHALL queue subsequent requests (up to a maximum of 500 queued requests per source) and execute them when the window permits, rather than rejecting them immediately.
4. IF the per-source request queue reaches its maximum capacity of 500 requests, THEN THE Rate_Limiter SHALL reject new incoming requests for that source with an error indicating that the source queue is full, and include an estimated wait time based on the current drain rate.
5. THE Rate_Limiter SHALL apply default system-level rate limits based on each source's published API policies (PubMed: 10 requests/second without API key, 100/second with key; Crossref: 50 requests/second polite pool; arXiv: 1 request/3 seconds).
6. THE Rate_Limiter SHALL store rate limit counters in Redis to ensure consistency across multiple backend worker processes.
7. WHEN a system_admin updates system-level rate limits, THE Literature_Gateway_Service SHALL apply the new limits within 1 second without requiring a service restart.

### Requirement 6: Rate Limiting — Per-Company Level

**User Story:** As a system administrator, I want per-company rate limits, so that one company's heavy usage does not exhaust the shared rate budget and degrade service for other tenants.

#### Acceptance Criteria

1. THE Rate_Limiter SHALL enforce a configurable maximum requests-per-minute limit for each company, applied across all sources combined.
2. THE Rate_Limiter SHALL enforce a configurable maximum requests-per-minute limit for each company per individual source.
3. WHEN a company's per-company rate limit is reached, THE Literature_Gateway_Service SHALL return HTTP 429 with a Retry-After header indicating the number of seconds until the next request window opens.
4. THE Rate_Limiter SHALL default per-company limits to a fraction of the system-level limit (default: system_limit divided by the number of active companies, with a minimum of 5 requests per minute per source).
5. WHEN a document_administrator configures custom rate limits in the Source_Configuration, THE Rate_Limiter SHALL use the custom limits instead of the calculated defaults, provided they do not exceed the system-level limit.
6. THE Rate_Limiter SHALL track per-company usage metrics (requests made, requests queued, requests rate-limited) and expose them via an API endpoint accessible to system_admin and document_admin roles.

### Requirement 7: Network Proxy Configuration

**User Story:** As a system administrator, I want to configure HTTP/HTTPS proxy settings for outbound literature API requests, so that external access is routed through the organization's firewall in a controlled manner.

#### Acceptance Criteria

1. THE Literature_Gateway_Service SHALL support configuration of an HTTP/HTTPS proxy URL through which all outbound literature API requests are routed.
2. THE Literature_Gateway_Service SHALL support proxy authentication via username and password stored encrypted in the API_Key_Vault.
3. WHEN a Network_Proxy is configured, THE Literature_Gateway_Service SHALL route all outbound requests from all Source_Adapters through the configured proxy.
4. THE Literature_Gateway_Service SHALL support a no-proxy list of hostnames or IP ranges that bypass the proxy for direct connection.
5. IF the configured Network_Proxy is unreachable, THEN THE Literature_Gateway_Service SHALL return an error indicating proxy connectivity failure and log the event in the audit trail.
6. THE Literature_Gateway_Service SHALL support per-source proxy override, allowing specific Source_Adapters to use a different proxy or direct connection as configured in the Source_Configuration.
7. WHEN no Network_Proxy is configured, THE Literature_Gateway_Service SHALL make direct outbound connections to external APIs.

### Requirement 8: Literature Search Execution

**User Story:** As a quality manager, I want to search across multiple literature sources simultaneously, so that I can find relevant scientific evidence efficiently without querying each database individually.

#### Acceptance Criteria

1. WHEN a user submits a Search_Query, THE Literature_Gateway_Service SHALL dispatch the query to all enabled sources for the requesting company in parallel and present results ordered by source priority ranking (lowest priority number first).
2. THE Literature_Gateway_Service SHALL normalize results from all sources into a unified list of Literature_Search_Results with consistent field mapping as defined by the Literature_Search_Result schema.
3. THE Literature_Gateway_Service SHALL deduplicate results across sources using DOI as the primary deduplication key, retaining the result from the highest-priority source. Results with a null DOI SHALL NOT be subject to deduplication and SHALL always be included in the output.
4. WHEN a Search_Query includes source filter parameters, THE Literature_Gateway_Service SHALL dispatch the query only to the specified sources that are both registered in the Source_Registry and enabled for the requesting company. IF any specified source is not registered or not enabled for the company, THEN THE Literature_Gateway_Service SHALL exclude that source from dispatch and include a warning in the response indicating which requested sources were unavailable.
5. THE Literature_Gateway_Service SHALL support pagination with configurable page size (minimum 1, default 20, maximum 100) and return total result count estimates from each source. IF the requested page size is outside the allowed range, THEN THE Literature_Gateway_Service SHALL reject the request with an error indicating the valid range.
6. IF any source fails to respond within 15 seconds, THEN THE Literature_Gateway_Service SHALL return results from responding sources and include a partial_results flag indicating which sources timed out. IF all dispatched sources fail to respond within 15 seconds, THEN THE Literature_Gateway_Service SHALL return an empty result set with the partial_results flag listing all timed-out sources.
7. WHEN a user submits a Search_Query, THE Literature_Gateway_Service SHALL require the user to have at least the `member` role within the requesting company. IF the user does not have the required role, THEN THE Literature_Gateway_Service SHALL reject the request with HTTP 403.
8. THE Literature_Gateway_Service SHALL return the complete search response within 30 seconds of receiving the Search_Query, inclusive of all source queries, deduplication, and normalization processing.

### Requirement 9: Error Handling and Resilience

**User Story:** As a quality manager, I want the system to gracefully handle external API failures, so that temporary outages do not prevent me from accessing results from other working sources.

#### Acceptance Criteria

1. WHEN a Source_Adapter receives an HTTP 429 (rate limited) response from an external API, THE Literature_Gateway_Service SHALL respect the Retry-After header value and requeue the request for later execution.
2. WHEN a Source_Adapter receives an HTTP 5xx response from an external API, THE Literature_Gateway_Service SHALL retry the request up to 3 times with exponential backoff (1s, 2s, 4s) before marking the source as temporarily unavailable.
3. IF a Source_Adapter fails to connect to its external API (network timeout or DNS resolution failure), THEN THE Literature_Gateway_Service SHALL mark the source as "unreachable" in the Source_Registry and exclude it from search dispatch until the next successful health check.
4. WHEN a source is marked as "unreachable", THE Literature_Gateway_Service SHALL attempt a health check every 60 seconds and restore the source to "available" status upon successful response.
5. THE Literature_Gateway_Service SHALL implement circuit breaker logic: WHEN a source accumulates 5 consecutive failures within a 5-minute window, THE Literature_Gateway_Service SHALL open the circuit and stop dispatching requests to that source for 5 minutes before attempting a half-open probe.
6. IF all enabled sources for a company are unavailable, THEN THE Literature_Gateway_Service SHALL return HTTP 503 with a message indicating that no literature sources are currently reachable and the estimated recovery time based on circuit breaker state.

### Requirement 10: Audit Trail for External API Calls

**User Story:** As a quality manager, I want all external literature API interactions logged in the audit trail, so that I can demonstrate due diligence in literature searches during regulatory audits.

#### Acceptance Criteria

1. WHEN the Literature_Gateway_Service dispatches a request to an external API, THE Audit_Logger SHALL record the request timestamp, source adapter name, target URL (with query parameters redacted of API keys), requesting user ID, and company ID.
2. WHEN the Literature_Gateway_Service receives a response from an external API, THE Audit_Logger SHALL record the response timestamp, HTTP status code, result count, and response time in milliseconds.
3. IF an external API request fails (timeout, connection error, or HTTP error status), THEN THE Audit_Logger SHALL record the failure type, error message, and retry attempt number.
4. THE Audit_Logger SHALL never log API keys, authentication tokens, or proxy credentials in audit records.
5. THE Audit_Logger SHALL associate each audit record with the originating Search_Query ID to enable full traceability from user action to external API call.
6. THE Audit_Logger SHALL store audit records using the existing SQLAlchemy-Continuum audit infrastructure, accessible through the Audit Trail Viewer (Phase 6.3).

### Requirement 11: Source Health Monitoring

**User Story:** As a system administrator, I want to monitor the health and availability of all configured literature sources, so that I can proactively identify connectivity issues and inform users of degraded service.

#### Acceptance Criteria

1. THE Source_Registry SHALL perform periodic health checks against all registered Source_Adapters at a configurable interval (default: 5 minutes).
2. THE Source_Registry SHALL classify each source status as "available" (responds within 5 seconds), "degraded" (responds but exceeds 5 seconds), or "unreachable" (fails to respond within 15 seconds or returns an error).
3. WHEN a source transitions from "available" to "degraded" or "unreachable", THE Source_Registry SHALL record the transition event in the audit trail.
4. THE Source_Registry SHALL expose a health status API endpoint showing all sources with their current status, last check timestamp, average response time over the last hour, and consecutive failure count.
5. THE Source_Registry SHALL store the last 50 health check results per source for trend analysis.
6. WHEN a source is classified as "unreachable" for more than 30 minutes, THE Source_Registry SHALL flag the source for administrator attention in the health status response.

### Requirement 12: Search Result Normalization

**User Story:** As a developer building downstream features (9.2–9.6), I want literature search results in a consistent normalized format regardless of source, so that downstream processing does not need source-specific logic.

#### Acceptance Criteria

1. THE Literature_Gateway_Service SHALL normalize all search results into a Literature_Search_Result containing: title (string, maximum 2000 characters), authors (list of strings preserving source ordering, maximum 500 entries), abstract (string, may be empty, maximum 50000 characters), DOI (string, may be null), publication_date (ISO 8601 date), source_id (string identifying the source adapter), external_id (string, the source-specific identifier such as PMID or arXiv ID), journal_or_venue (string, may be empty), publication_type (string: "journal_article", "preprint", "conference_paper", "review", "other"), and url (string, direct link to the source record, may be null if the source does not provide a stable URL).
2. WHEN a source returns fields that do not map to the normalized schema, THE Source_Adapter SHALL discard unmapped fields and log a debug-level message identifying the source adapter name and the discarded field names.
3. WHEN a source returns a result missing required fields (title and external_id), THE Source_Adapter SHALL exclude the result from the normalized output and log a warning containing the source adapter name, the external_id or title if partially available, and which required field is missing.
4. THE Literature_Gateway_Service SHALL include source provenance metadata with each result: source_adapter_name, retrieval_timestamp (ISO 8601 datetime with UTC timezone), and query_id.
5. IF a source returns a publication_date with only year or year-month precision, THEN THE Source_Adapter SHALL normalize it to the first day of the missing component (e.g., "2023" becomes "2023-01-01", "2023-03" becomes "2023-03-01") and SHALL include a date_precision field ("day", "month", or "year") in the Literature_Search_Result indicating the original granularity.
6. THE Literature_Gateway_Service SHALL ensure that for all valid Literature_Search_Results, serializing to JSON and deserializing produces a field-by-field equal object with identical types, values, and list ordering (round-trip property).

### Requirement 13: Scoped Search Configuration Profiles

**User Story:** As a document administrator, I want to configure default search profiles for my company based on our regulatory vertical, so that users get relevant results without manually selecting sources each time.

#### Acceptance Criteria

1. THE Literature_Gateway_Service SHALL support named search profiles per company, each defining a set of enabled sources, priority ordering, and default query filters (e.g., publication date range, publication types).
2. WHEN a company has a configured default search profile, THE Literature_Gateway_Service SHALL apply the profile's settings to all Search_Queries from that company unless the query explicitly overrides them.
3. THE Literature_Gateway_Service SHALL provide pre-built profile templates for common regulatory verticals: "pharma_medtech" (prioritizing PubMed, Crossref), "technical_supplier" (prioritizing arXiv, IEEE), and "general" (equal priority across all sources).
4. WHEN a document_administrator creates or updates a search profile, THE Literature_Gateway_Service SHALL validate that all referenced source adapters are registered in the Source_Registry.
5. THE Literature_Gateway_Service SHALL allow multiple search profiles per company, with one designated as the default.
6. WHEN a search profile is created, updated, or deleted, THE Literature_Gateway_Service SHALL record the change in the audit trail with the X-Change-Reason header value.

### Requirement 14: Configuration API Endpoints

**User Story:** As a system administrator, I want RESTful API endpoints for managing all literature gateway configurations, so that settings can be managed programmatically and through the admin dashboard.

#### Acceptance Criteria

1. THE Literature_Gateway_Service SHALL expose CRUD endpoints for Source_Configurations at `/api/literature/sources/{company_id}/configurations`.
2. THE Literature_Gateway_Service SHALL expose CRUD endpoints for search profiles at `/api/literature/sources/{company_id}/profiles`.
3. THE Literature_Gateway_Service SHALL expose system-level rate limit configuration endpoints at `/api/literature/admin/rate-limits` accessible only to system_admin role.
4. THE Literature_Gateway_Service SHALL expose proxy configuration endpoints at `/api/literature/admin/proxy` accessible only to system_admin role.
5. THE Literature_Gateway_Service SHALL expose the search endpoint at `/api/literature/search` accepting Search_Query parameters and returning paginated Literature_Search_Results.
6. THE Literature_Gateway_Service SHALL expose the source registry endpoint at `/api/literature/sources` listing all registered adapters and their capabilities.
7. WHEN any mutation endpoint (POST, PUT, PATCH, DELETE) is called, THE Literature_Gateway_Service SHALL require the X-Change-Reason header and return HTTP 400 if it is missing or empty.

### Requirement 15: Celery Task Integration for Async Search

**User Story:** As a quality manager, I want long-running literature searches to execute asynchronously, so that the UI remains responsive and I can check results when they are ready.

#### Acceptance Criteria

1. WHEN a Search_Query is expected to take longer than 5 seconds (querying more than 3 sources or requesting more than 50 results), THE Literature_Gateway_Service SHALL dispatch the search as an asynchronous Celery task and return HTTP 202 with a task ID.
2. THE Literature_Gateway_Service SHALL expose a task status endpoint at `/api/literature/tasks/{task_id}` returning the current status (queued, running, completed, failed), progress percentage, and partial results if available.
3. WHEN an asynchronous search task completes, THE Literature_Gateway_Service SHALL store the results in Redis with a configurable TTL (default: 1 hour) and mark the task as completed.
4. WHEN an asynchronous search task fails, THE Literature_Gateway_Service SHALL record the failure reason and mark the task as failed with an error message retrievable via the task status endpoint.
5. THE Literature_Gateway_Service SHALL allow cancellation of a running search task via DELETE to `/api/literature/tasks/{task_id}`, which stops further source queries but retains any partial results already collected.

### Requirement 16: Environment and Deployment Configuration

**User Story:** As a system administrator, I want all literature gateway settings configurable via environment variables, so that deployment in different environments (development, staging, production) requires no code changes.

#### Acceptance Criteria

1. THE Literature_Gateway_Service SHALL read the master encryption key for the API_Key_Vault from the `ALC_LITERATURE_ENCRYPTION_KEY` environment variable.
2. THE Literature_Gateway_Service SHALL read default proxy configuration from `ALC_LITERATURE_PROXY_URL`, `ALC_LITERATURE_PROXY_USER`, and `ALC_LITERATURE_PROXY_PASSWORD` environment variables.
3. THE Literature_Gateway_Service SHALL read the adapter directory path from the `ALC_LITERATURE_ADAPTER_DIR` environment variable with a default of `src/alcoabase/literature/adapters/`.
4. THE Literature_Gateway_Service SHALL read Redis connection details for rate limiting from the existing `REDIS_URL` environment variable.
5. WHEN the `ALC_LITERATURE_ENABLED` environment variable is set to "false", THE Literature_Gateway_Service SHALL disable all external API access and return HTTP 503 with a message indicating that literature search is disabled in this deployment.
6. THE Literature_Gateway_Service SHALL validate all required environment variables at startup and log clear error messages for any missing or invalid values.
