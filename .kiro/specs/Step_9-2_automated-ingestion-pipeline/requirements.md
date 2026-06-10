# Requirements Document

## Introduction

This document specifies the requirements for the Automated Ingestion Pipeline (Phase 9.2) of AlcoaBase. This feature builds directly on the Literature Search Engine (Phase 9.1) by consuming `LiteratureSearchResult` objects and implementing a dual-stage asynchronous pipeline that first stores metadata and abstracts (always available from search results), then attempts full-text retrieval via DOI resolution using the Unpaywall API and open-access publisher endpoints. Downloaded full-text files (PDF, HTML, XML/JATS) are sanitized, standardized into a structured internal format, and optionally piped through the Dual-UUID extraction layer (Phase 2.5) to maintain parity with internal document structures. The pipeline tracks each paper through a state machine (metadata_only → abstract_indexed → full_text_pending → full_text_downloaded → sanitized → indexed), stores downloaded content in MinIO with metadata in PostgreSQL, and provides per-company ingestion configuration including full-text retrieval toggles, storage quotas, and retention policies. All operations are company-scoped, audit-logged, and leverage the existing rate limiter, circuit breaker, and proxy infrastructure from Phase 9.1.

## Glossary

- **Ingestion_Pipeline_Service**: The backend service responsible for orchestrating the dual-stage ingestion of literature search results, managing state transitions, dispatching download workers, and coordinating sanitization tasks.
- **Ingestion_Record**: A per-company, per-paper database record tracking the lifecycle state of a literature item from initial metadata capture through full-text retrieval, sanitization, and indexing.
- **Ingestion_State**: An enumeration defining the lifecycle phases of an Ingestion_Record: `metadata_only`, `abstract_indexed`, `full_text_pending`, `full_text_downloaded`, `sanitized`, `indexed`, and `failed`.
- **Full_Text_Retrieval_Worker**: A Celery task responsible for resolving DOIs to open-access full-text URLs (via the Unpaywall_Adapter), downloading content, and storing files in MinIO.
- **Unpaywall_Adapter**: A Source_Adapter (following the BaseSourceAdapter pattern from Phase 9.1) that queries the Unpaywall API to resolve DOIs to open-access PDF/HTML/XML download URLs.
- **Sanitization_Pipeline**: The processing chain that takes downloaded full-text files (PDF, HTML, XML/JATS) and extracts clean structured text, normalizing all formats into a unified internal representation.
- **Structured_Content**: The normalized internal format produced by the Sanitization_Pipeline, containing extracted sections (title, abstract, body, references, figures/tables metadata), clean plaintext, and structural markup.
- **Ingestion_Configuration**: A per-company configuration record controlling ingestion behavior: full-text retrieval enabled/disabled, storage quota limits, retention policies, and Unpaywall email contact.
- **Literature_Object_Store**: The MinIO bucket/prefix hierarchy where downloaded full-text files and sanitized content are stored, organized by company ID and Ingestion_Record ID.
- **Dual_UUID_Extraction_Layer**: The existing document extraction infrastructure from Phase 2.5 that maps PDF content to database fields using dual UUIDs, reused here to maintain parity between ingested literature and internal documents.
- **Literature_Search_Result**: The normalized search result schema from Phase 9.1, serving as the input to the ingestion pipeline.
- **Rate_Limiter**: The existing rate limiting component from Phase 9.1, reused to enforce request limits on the Unpaywall API and publisher download endpoints.
- **Circuit_Breaker**: The existing circuit breaker from Phase 9.1, reused for resilience against Unpaywall and publisher endpoint failures.
- **Audit_Logger**: The existing audit logging component from Phase 9.1, extended to record ingestion pipeline events.
- **Company**: The multi-tenant entity (from Phase 1.1) to which all Ingestion_Records, configurations, and storage quotas are scoped.

## Requirements

### Requirement 1: Dual-Stage Ingestion Pipeline Architecture

**User Story:** As a quality manager, I want literature search results automatically ingested through a two-stage pipeline (metadata first, full-text second), so that abstracts are immediately available for review while full-text retrieval proceeds asynchronously in the background.

#### Acceptance Criteria

1. WHEN a user or automated process submits one or more Literature_Search_Results for ingestion, THE Ingestion_Pipeline_Service SHALL create an Ingestion_Record for each result scoped to the requesting company, with initial state set to `metadata_only`.
2. WHEN an Ingestion_Record is created, THE Ingestion_Pipeline_Service SHALL store the normalized metadata (title, authors, DOI, publication_date, journal_or_venue, publication_type, external_id, source_id, url) from the Literature_Search_Result in the Ingestion_Record.
3. WHEN an Ingestion_Record is created with a non-empty abstract, THE Ingestion_Pipeline_Service SHALL store the abstract text and transition the state to `abstract_indexed`.
4. WHEN an Ingestion_Record reaches the `abstract_indexed` state and the company's Ingestion_Configuration has full-text retrieval enabled and the Ingestion_Record has a non-null DOI, THE Ingestion_Pipeline_Service SHALL dispatch a Full_Text_Retrieval_Worker task and transition the state to `full_text_pending`.
5. WHEN an Ingestion_Record has a null DOI, THE Ingestion_Pipeline_Service SHALL NOT dispatch a Full_Text_Retrieval_Worker and SHALL retain the record in its current state (`metadata_only` or `abstract_indexed`).
6. IF a user submits a Literature_Search_Result for ingestion that matches an existing Ingestion_Record (same company_id and DOI, or same company_id and source_id and external_id), THEN THE Ingestion_Pipeline_Service SHALL skip creating a duplicate record and return the existing Ingestion_Record ID.
7. THE Ingestion_Pipeline_Service SHALL process ingestion submissions as asynchronous Celery tasks, returning HTTP 202 with a batch ingestion task ID immediately upon submission.
8. THE Ingestion_Pipeline_Service SHALL support batch ingestion of up to 100 Literature_Search_Results in a single request.

### Requirement 2: Ingestion State Machine

**User Story:** As a system administrator, I want each ingested paper tracked through a well-defined lifecycle, so that I can monitor pipeline progress and identify papers stuck in intermediate states.

#### Acceptance Criteria

1. THE Ingestion_Pipeline_Service SHALL enforce the following valid state transitions for Ingestion_Records: `metadata_only` → `abstract_indexed`, `abstract_indexed` → `full_text_pending`, `full_text_pending` → `full_text_downloaded`, `full_text_pending` → `failed`, `full_text_downloaded` → `sanitized`, `full_text_downloaded` → `failed`, `sanitized` → `indexed`, `sanitized` → `failed`.
2. IF a state transition is attempted that does not match the valid transitions, THEN THE Ingestion_Pipeline_Service SHALL reject the transition, log a warning with the Ingestion_Record ID, current state, and attempted target state, and retain the record in its current state.
3. WHEN an Ingestion_Record transitions to the `failed` state, THE Ingestion_Pipeline_Service SHALL record the failure reason, the state from which failure occurred, the error type, and a retry count.
4. WHEN an Ingestion_Record is in the `failed` state, THE Ingestion_Pipeline_Service SHALL allow manual or automatic retry that transitions the record back to the state from which it failed (e.g., `full_text_pending` if download failed, `full_text_downloaded` if sanitization failed).
5. THE Ingestion_Pipeline_Service SHALL support a maximum of 3 automatic retries per state transition failure, with exponential backoff (30 seconds, 2 minutes, 10 minutes) between attempts.
6. WHEN a state transition occurs, THE Ingestion_Pipeline_Service SHALL record the transition timestamp, previous state, new state, and triggering event in the Ingestion_Record history.
7. THE Ingestion_Pipeline_Service SHALL expose an API endpoint returning aggregated state counts per company (number of records in each state) for monitoring dashboards.

### Requirement 3: Full-Text Retrieval via Unpaywall

**User Story:** As a quality manager, I want the system to automatically attempt to retrieve open-access full-text versions of papers using their DOI, so that I can access complete article content without manual downloads.

#### Acceptance Criteria

1. THE Unpaywall_Adapter SHALL query the Unpaywall API (`https://api.unpaywall.org/v2/{doi}`) using the company's configured email address as the required `email` parameter.
2. WHEN the Unpaywall API returns a successful response with one or more open-access locations, THE Unpaywall_Adapter SHALL select the best available full-text URL using the following priority: (1) publisher-hosted PDF with `is_best` flag, (2) repository PDF, (3) publisher-hosted HTML, (4) any available PDF URL, (5) any available HTML or XML URL.
3. WHEN the Unpaywall API indicates that no open-access version is available for a DOI, THE Full_Text_Retrieval_Worker SHALL record the result as "no open-access version found", transition the Ingestion_Record to the `failed` state with error_type `no_oa_available`, and NOT retry automatically.
4. IF the Unpaywall API returns HTTP 404 for a DOI, THEN THE Full_Text_Retrieval_Worker SHALL record the result as "DOI not found in Unpaywall" and transition the Ingestion_Record to the `failed` state with error_type `doi_not_found`.
5. IF the Unpaywall API returns HTTP 429, THEN THE Full_Text_Retrieval_Worker SHALL respect the Retry-After header and requeue the task for later execution, using the Rate_Limiter from Phase 9.1.
6. THE Unpaywall_Adapter SHALL enforce rate limiting at 100,000 requests per day as specified by the Unpaywall API fair use policy, tracked via the existing Rate_Limiter infrastructure.
7. THE Full_Text_Retrieval_Worker SHALL use the existing Network_Proxy configuration from Phase 9.1 for all outbound requests to the Unpaywall API and publisher download endpoints.
8. THE Unpaywall_Adapter SHALL use the existing Circuit_Breaker from Phase 9.1, opening the circuit after 5 consecutive failures within a 5-minute window.

### Requirement 4: Full-Text Download Worker

**User Story:** As a quality manager, I want full-text articles automatically downloaded and stored securely, so that the content is available for sanitization and indexing without manual intervention.

#### Acceptance Criteria

1. WHEN the Unpaywall_Adapter resolves a valid full-text URL, THE Full_Text_Retrieval_Worker SHALL download the content with a per-request timeout of 60 seconds.
2. THE Full_Text_Retrieval_Worker SHALL detect the content type of the downloaded file from the HTTP Content-Type header and validate it against allowed types: `application/pdf`, `text/html`, `application/xml`, `text/xml`, `application/jats+xml`.
3. IF the downloaded content type does not match any allowed type, THEN THE Full_Text_Retrieval_Worker SHALL reject the download, transition the Ingestion_Record to `failed` with error_type `unsupported_content_type`, and log the actual Content-Type received.
4. WHEN a file is successfully downloaded, THE Full_Text_Retrieval_Worker SHALL store the file in the Literature_Object_Store under the path `literature/{company_id}/{ingestion_record_id}/{filename}` with the appropriate file extension (.pdf, .html, .xml).
5. WHEN a file is stored in the Literature_Object_Store, THE Full_Text_Retrieval_Worker SHALL record the object storage path, file size in bytes, content type, SHA-256 checksum, and download timestamp in the Ingestion_Record.
6. THE Full_Text_Retrieval_Worker SHALL enforce a maximum file size of 100 MB per download; IF the Content-Length header indicates a file exceeding 100 MB, THEN THE Full_Text_Retrieval_Worker SHALL abort the download before transfer and transition the Ingestion_Record to `failed` with error_type `file_too_large`.
7. WHEN a download completes successfully, THE Full_Text_Retrieval_Worker SHALL transition the Ingestion_Record from `full_text_pending` to `full_text_downloaded`.
8. IF a download fails due to network timeout, HTTP error (4xx/5xx from publisher), or connection reset, THEN THE Full_Text_Retrieval_Worker SHALL retry up to 3 times with exponential backoff (5s, 15s, 45s) before transitioning the Ingestion_Record to `failed`.
9. THE Full_Text_Retrieval_Worker SHALL include a User-Agent header identifying AlcoaBase with version and the company's contact email for publisher compliance.

### Requirement 5: Sanitization Pipeline (PDF Processing)

**User Story:** As a quality manager, I want downloaded PDF files automatically converted to clean structured text, so that the content is searchable and can be piped into the extraction layer.

#### Acceptance Criteria

1. WHEN an Ingestion_Record reaches the `full_text_downloaded` state with content_type `application/pdf`, THE Sanitization_Pipeline SHALL extract text from the PDF using PyMuPDF (fitz), preserving section boundaries, paragraph structure, and reading order.
2. THE Sanitization_Pipeline SHALL detect and extract structural elements from PDFs: title, abstract, section headings, body paragraphs, figure captions, table captions, and reference lists.
3. IF a PDF contains only scanned images (no extractable text), THEN THE Sanitization_Pipeline SHALL flag the record with `requires_ocr` metadata and transition to `failed` with error_type `ocr_required` until OCR processing is available.
4. THE Sanitization_Pipeline SHALL strip PDF artifacts including headers, footers, page numbers, watermarks, and advertisement banners while preserving scientific content.
5. THE Sanitization_Pipeline SHALL produce a Structured_Content object containing: extracted_title, extracted_abstract, body_sections (list of heading + text pairs), references (list of citation strings), figure_count, table_count, word_count, and raw_plaintext.
6. FOR ALL valid PDF files processed by the Sanitization_Pipeline, THE raw_plaintext field in the resulting Structured_Content SHALL contain a non-empty string with word_count greater than zero.

### Requirement 6: Sanitization Pipeline (HTML and XML/JATS Processing)

**User Story:** As a quality manager, I want downloaded HTML and XML articles automatically converted to the same structured format as PDFs, so that all ingested content is in a consistent format regardless of its original source format.

#### Acceptance Criteria

1. WHEN an Ingestion_Record reaches the `full_text_downloaded` state with content_type `text/html`, THE Sanitization_Pipeline SHALL parse the HTML, remove navigation elements, scripts, stylesheets, advertisements, and cookie banners, and extract article content.
2. WHEN an Ingestion_Record reaches the `full_text_downloaded` state with content_type `application/xml`, `text/xml`, or `application/jats+xml`, THE Sanitization_Pipeline SHALL parse the document as JATS XML and map JATS elements to Structured_Content fields (front/article-meta → title/abstract, body → body_sections, back/ref-list → references).
3. THE Sanitization_Pipeline SHALL sanitize all extracted HTML content by removing potentially malicious elements (script, iframe, object, embed, form) and attributes (onclick, onerror, javascript: URLs) before storing.
4. THE Sanitization_Pipeline SHALL produce the same Structured_Content schema regardless of input format (PDF, HTML, or XML), ensuring downstream consumers do not need format-specific logic.
5. IF an HTML or XML file cannot be parsed (malformed markup, encoding errors), THEN THE Sanitization_Pipeline SHALL transition the Ingestion_Record to `failed` with error_type `parse_error` and log the specific parsing exception.
6. THE Sanitization_Pipeline SHALL detect the character encoding of HTML/XML files from the Content-Type charset parameter, BOM, or meta tag, and normalize all text output to UTF-8.
7. FOR ALL valid JATS XML documents, parsing the XML into Structured_Content and serializing the Structured_Content back into a normalized format SHALL preserve the title, abstract, and body section content (round-trip property for lossless extraction).

### Requirement 7: Dual-UUID Extraction Layer Integration

**User Story:** As a quality manager, I want ingested literature to be compatible with our internal document structures, so that literature and internal documents can be queried, compared, and traced using the same mechanisms.

#### Acceptance Criteria

1. WHEN an Ingestion_Record reaches the `sanitized` state, THE Ingestion_Pipeline_Service SHALL optionally pipe the Structured_Content through the Dual_UUID_Extraction_Layer (Phase 2.5), creating a literature-type document record that is queryable alongside internal documents.
2. THE Ingestion_Pipeline_Service SHALL create the literature document record scoped to the originating company, with document_type set to `external_literature` and source metadata linking back to the Ingestion_Record.
3. WHEN the Dual_UUID_Extraction_Layer integration is enabled for a company (via Ingestion_Configuration), THE Ingestion_Pipeline_Service SHALL assign dual UUIDs (content UUID and field UUID) to the extracted sections, maintaining the same mapping structure used for internal PDF uploads.
4. THE Ingestion_Pipeline_Service SHALL store a bidirectional reference between the Ingestion_Record and the created document record, enabling navigation from literature to document view and vice versa.
5. IF the Dual_UUID_Extraction_Layer processing fails, THEN THE Ingestion_Pipeline_Service SHALL transition the Ingestion_Record to `failed` with error_type `extraction_layer_error` and retain the sanitized content in the Literature_Object_Store for manual retry.
6. WHEN Dual_UUID_Extraction_Layer integration is disabled for a company, THE Ingestion_Pipeline_Service SHALL skip this step and transition directly from `sanitized` to `indexed`.

### Requirement 8: Per-Company Ingestion Configuration

**User Story:** As a document administrator, I want to configure ingestion behavior for my company, so that I can control whether full-text retrieval is enabled, manage storage usage, and define retention policies.

#### Acceptance Criteria

1. THE Ingestion_Pipeline_Service SHALL provide a per-company Ingestion_Configuration with the following settings: `full_text_retrieval_enabled` (boolean, default: true), `storage_quota_mb` (integer, default: 10240 MB / 10 GB), `retention_days` (integer, default: 365), `unpaywall_email` (string, required when full-text retrieval is enabled), `dual_uuid_integration_enabled` (boolean, default: false), `max_concurrent_downloads` (integer, default: 5, range 1–20).
2. WHEN a company does not have an explicit Ingestion_Configuration, THE Ingestion_Pipeline_Service SHALL apply the default values specified in acceptance criterion 1.
3. WHEN a company's storage usage reaches 90% of the configured storage_quota_mb, THE Ingestion_Pipeline_Service SHALL log a warning and include a quota_warning flag in API responses for that company.
4. WHEN a company's storage usage reaches 100% of the configured storage_quota_mb, THE Ingestion_Pipeline_Service SHALL reject new full-text download tasks for that company with an error indicating quota exceeded, and SHALL NOT transition pending Ingestion_Records to `full_text_pending`.
5. WHEN the retention_days period elapses for a downloaded full-text file, THE Ingestion_Pipeline_Service SHALL delete the file from the Literature_Object_Store and update the Ingestion_Record to indicate that the file has been purged while retaining the metadata and sanitized content reference.
6. THE Ingestion_Pipeline_Service SHALL require the `document_admin` or `system_admin` role to create or update Ingestion_Configurations.
7. WHEN an Ingestion_Configuration is created or updated, THE Ingestion_Pipeline_Service SHALL record the change in the audit trail with the X-Change-Reason header value, acting user, and company ID.
8. THE Ingestion_Pipeline_Service SHALL enforce that the `unpaywall_email` field contains a valid email address format when `full_text_retrieval_enabled` is true.

### Requirement 9: Storage Management in MinIO

**User Story:** As a system administrator, I want downloaded literature files stored in a well-organized, company-isolated structure in MinIO, so that storage is manageable, auditable, and respects tenant boundaries.

#### Acceptance Criteria

1. THE Literature_Object_Store SHALL use a dedicated MinIO bucket named `alcoabase-literature` with the path structure: `{company_id}/{ingestion_record_id}/{file_type}/{filename}` where file_type is one of `original`, `sanitized`, or `extracted`.
2. THE Literature_Object_Store SHALL store the original downloaded file under the `original` prefix and the sanitized Structured_Content as a JSON file under the `sanitized` prefix.
3. THE Ingestion_Pipeline_Service SHALL enforce company isolation by including the company_id in all MinIO object paths and validating that operations on objects match the requesting company's scope.
4. WHEN storing a file, THE Ingestion_Pipeline_Service SHALL attach MinIO object metadata tags including: company_id, ingestion_record_id, content_type, sha256_checksum, ingestion_timestamp, and retention_expiry_date.
5. THE Ingestion_Pipeline_Service SHALL calculate and verify SHA-256 checksums after upload to MinIO, comparing against the checksum computed during download, to ensure data integrity.
6. IF the checksum verification fails after upload, THEN THE Ingestion_Pipeline_Service SHALL delete the corrupted object, log the integrity failure, and retry the upload once before transitioning the Ingestion_Record to `failed` with error_type `storage_integrity_error`.
7. THE Ingestion_Pipeline_Service SHALL track total storage usage per company by summing object sizes and caching the total in Redis with a TTL of 5 minutes for quota enforcement.

### Requirement 10: Audit Trail for Ingestion Operations

**User Story:** As a quality manager, I want all ingestion pipeline operations logged in the audit trail, so that I can demonstrate the provenance of ingested literature during regulatory audits.

#### Acceptance Criteria

1. WHEN an Ingestion_Record is created, THE Audit_Logger SHALL record the creation event with: company_id, user_id (or "system" for automated ingestion), source Literature_Search_Result external_id, DOI, and initial state.
2. WHEN an Ingestion_Record transitions between states, THE Audit_Logger SHALL record the transition with: ingestion_record_id, company_id, previous_state, new_state, transition_timestamp, and triggering event (user action, automated task, or retry).
3. WHEN the Full_Text_Retrieval_Worker downloads a file, THE Audit_Logger SHALL record: ingestion_record_id, company_id, download_url (with authentication tokens redacted), content_type, file_size_bytes, download_duration_ms, and source (Unpaywall or publisher direct).
4. WHEN the Sanitization_Pipeline processes a file, THE Audit_Logger SHALL record: ingestion_record_id, company_id, input_content_type, output_word_count, processing_duration_ms, and sections_extracted_count.
5. IF any ingestion operation fails, THEN THE Audit_Logger SHALL record the failure with: ingestion_record_id, company_id, failed_operation, error_type, error_message, and retry_attempt_number.
6. THE Audit_Logger SHALL never log full-text content, file contents, or download URLs containing authentication tokens in audit records.
7. THE Audit_Logger SHALL store ingestion audit records using the existing ExternalAPIAuditLog table structure from Phase 9.1, extended with ingestion-specific fields.

### Requirement 11: Ingestion API Endpoints

**User Story:** As a developer building the literature search UI (Phase 9.6), I want RESTful API endpoints for managing ingestion operations, so that users can trigger ingestion, monitor progress, and view ingested content.

#### Acceptance Criteria

1. THE Ingestion_Pipeline_Service SHALL expose an ingestion submission endpoint at `POST /api/literature/ingest` accepting a list of Literature_Search_Result objects (maximum 100) and returning HTTP 202 with a batch task ID.
2. THE Ingestion_Pipeline_Service SHALL expose an ingestion status endpoint at `GET /api/literature/ingest/{ingestion_record_id}` returning the Ingestion_Record with current state, metadata, file information, and state transition history.
3. THE Ingestion_Pipeline_Service SHALL expose a batch status endpoint at `GET /api/literature/ingest/batch/{batch_id}` returning the status of all Ingestion_Records created in a batch submission.
4. THE Ingestion_Pipeline_Service SHALL expose a list endpoint at `GET /api/literature/ingest` accepting filters for state, date range, DOI, and source_id, with pagination (page_size default 20, maximum 100).
5. THE Ingestion_Pipeline_Service SHALL expose a retry endpoint at `POST /api/literature/ingest/{ingestion_record_id}/retry` that requeues a failed Ingestion_Record for reprocessing from its last successful state.
6. THE Ingestion_Pipeline_Service SHALL expose an ingestion configuration endpoint at `GET/PUT /api/literature/ingest/config` for managing the company's Ingestion_Configuration.
7. WHEN any mutation endpoint is called, THE Ingestion_Pipeline_Service SHALL require the X-Change-Reason header and return HTTP 400 if it is missing or empty.
8. THE Ingestion_Pipeline_Service SHALL require at least the `member` role for read endpoints and `document_admin` or `system_admin` role for mutation endpoints (ingest submission, retry, configuration changes).
9. THE Ingestion_Pipeline_Service SHALL expose a storage usage endpoint at `GET /api/literature/ingest/storage` returning current storage usage, quota, and per-state file counts for the requesting company.

### Requirement 12: Celery Task Integration

**User Story:** As a system administrator, I want ingestion tasks processed as background Celery jobs, so that the pipeline can scale independently of the API layer and long-running downloads do not block user requests.

#### Acceptance Criteria

1. THE Ingestion_Pipeline_Service SHALL dispatch Stage 1 (metadata and abstract ingestion) as a Celery task with priority `high` (executed within seconds of submission).
2. THE Ingestion_Pipeline_Service SHALL dispatch Stage 2 (full-text retrieval) as a Celery task with priority `low` (background processing that yields to higher-priority tasks).
3. THE Ingestion_Pipeline_Service SHALL dispatch sanitization as a Celery task with priority `medium` triggered automatically when download completes.
4. THE Ingestion_Pipeline_Service SHALL limit concurrent full-text download tasks per company to the configured `max_concurrent_downloads` value using a Redis-based semaphore.
5. WHEN a download task cannot acquire the company semaphore, THE Ingestion_Pipeline_Service SHALL requeue the task with a 30-second delay rather than rejecting it.
6. THE Ingestion_Pipeline_Service SHALL use a dedicated Celery queue named `literature_ingestion` for all ingestion tasks, separate from the `literature_search` queue used by Phase 9.1.
7. IF a Celery task fails with an unhandled exception, THEN THE Ingestion_Pipeline_Service SHALL catch the exception, transition the Ingestion_Record to `failed`, and record the exception details in the audit trail.

### Requirement 13: Retention and Cleanup

**User Story:** As a system administrator, I want expired full-text files automatically cleaned up according to retention policies, so that storage costs remain controlled and data governance policies are enforced.

#### Acceptance Criteria

1. THE Ingestion_Pipeline_Service SHALL run a periodic Celery beat task (default: daily at 02:00 UTC) that identifies Ingestion_Records with downloaded files past their retention_expiry_date.
2. WHEN a file reaches its retention expiry, THE Ingestion_Pipeline_Service SHALL delete the original file from the Literature_Object_Store, retain the sanitized content JSON, and update the Ingestion_Record with `original_file_purged: true` and the purge timestamp.
3. THE Ingestion_Pipeline_Service SHALL NOT delete sanitized content or metadata during retention cleanup, preserving the abstract, structured content, and all audit records indefinitely.
4. WHEN files are purged during retention cleanup, THE Audit_Logger SHALL record each purge event with: ingestion_record_id, company_id, file_path, file_size_bytes, and retention_policy_applied.
5. THE Ingestion_Pipeline_Service SHALL support a company-level override to retain original files indefinitely (retention_days = 0 means no expiry).
6. THE Ingestion_Pipeline_Service SHALL process retention cleanup in batches of 100 records per execution cycle to avoid overwhelming MinIO with bulk deletions.

### Requirement 14: Error Handling and Resilience

**User Story:** As a system administrator, I want the ingestion pipeline to gracefully handle failures at every stage without losing data or corrupting state, so that the system remains reliable under adverse conditions.

#### Acceptance Criteria

1. IF the Unpaywall API is unavailable (circuit breaker open), THEN THE Ingestion_Pipeline_Service SHALL retain Ingestion_Records in the `full_text_pending` state and requeue download tasks with exponential backoff until the circuit closes.
2. IF MinIO is unreachable during a file upload, THEN THE Full_Text_Retrieval_Worker SHALL retry the upload 3 times with 10-second intervals before transitioning the Ingestion_Record to `failed` with error_type `storage_unavailable`.
3. IF the Sanitization_Pipeline encounters a corrupted or encrypted PDF, THEN THE Sanitization_Pipeline SHALL transition the Ingestion_Record to `failed` with error_type `corrupt_file` and log the specific error without exposing file content.
4. THE Ingestion_Pipeline_Service SHALL implement idempotent task execution: reprocessing the same Ingestion_Record through any pipeline stage SHALL produce the same result without creating duplicate files or records.
5. WHEN a Celery worker crashes during task execution, THE Ingestion_Pipeline_Service SHALL detect the orphaned task via Celery's visibility timeout (default: 30 minutes) and requeue the task automatically.
6. THE Ingestion_Pipeline_Service SHALL expose a health endpoint at `GET /api/literature/ingest/health` reporting: Celery worker count, queue depths per priority level, circuit breaker states, and MinIO connectivity status.
7. IF multiple failures occur for the same company within a 10-minute window (more than 10 consecutive failures), THEN THE Ingestion_Pipeline_Service SHALL temporarily pause ingestion for that company, log a critical alert, and resume after 15 minutes.

### Requirement 15: Environment and Deployment Configuration

**User Story:** As a system administrator, I want all ingestion pipeline settings configurable via environment variables, so that deployment in different environments requires no code changes.

#### Acceptance Criteria

1. THE Ingestion_Pipeline_Service SHALL read the Unpaywall API base URL from the `ALC_UNPAYWALL_API_URL` environment variable with a default of `https://api.unpaywall.org/v2`.
2. THE Ingestion_Pipeline_Service SHALL read the MinIO literature bucket name from the `ALC_LITERATURE_BUCKET` environment variable with a default of `alcoabase-literature`.
3. THE Ingestion_Pipeline_Service SHALL read the maximum file download size from the `ALC_LITERATURE_MAX_FILE_SIZE_MB` environment variable with a default of 100.
4. THE Ingestion_Pipeline_Service SHALL read the default retention period from the `ALC_LITERATURE_RETENTION_DAYS` environment variable with a default of 365.
5. THE Ingestion_Pipeline_Service SHALL read the default storage quota from the `ALC_LITERATURE_STORAGE_QUOTA_MB` environment variable with a default of 10240.
6. THE Ingestion_Pipeline_Service SHALL read the Celery queue name from the `ALC_LITERATURE_INGESTION_QUEUE` environment variable with a default of `literature_ingestion`.
7. THE Ingestion_Pipeline_Service SHALL read the cleanup schedule from the `ALC_LITERATURE_CLEANUP_CRON` environment variable with a default of `0 2 * * *` (daily at 02:00 UTC).
8. THE Ingestion_Pipeline_Service SHALL validate all environment variables at startup and log clear error messages for any invalid values, using the existing Pydantic settings infrastructure.

### Requirement 16: Structured Content Serialization

**User Story:** As a developer building downstream features (9.3 embedding generation, 9.4 literature review agents), I want sanitized content in a consistent, well-defined JSON schema, so that downstream processing can reliably extract sections without format-specific logic.

#### Acceptance Criteria

1. THE Sanitization_Pipeline SHALL produce Structured_Content as a Pydantic model with fields: extracted_title (string), extracted_abstract (string), body_sections (list of objects with `heading` and `text` fields), references (list of citation strings), figure_count (integer), table_count (integer), word_count (integer), raw_plaintext (string), source_format (enum: pdf, html, xml), processing_timestamp (ISO 8601 datetime), and ingestion_record_id (string).
2. THE Sanitization_Pipeline SHALL store the Structured_Content as a JSON file in the Literature_Object_Store under the `sanitized` prefix with the filename `structured_content.json`.
3. FOR ALL valid Structured_Content objects, serializing to JSON and deserializing back into a Structured_Content object SHALL produce a field-by-field equal object with identical types, values, and list ordering (round-trip property).
4. THE Structured_Content word_count field SHALL equal the number of whitespace-delimited tokens in the raw_plaintext field.
5. THE Structured_Content raw_plaintext field SHALL be the concatenation of extracted_title, extracted_abstract, and all body_section text values separated by newline characters.
6. THE Sanitization_Pipeline SHALL truncate raw_plaintext to a maximum of 5,000,000 characters, recording the truncation in the Ingestion_Record metadata if truncation occurs.
