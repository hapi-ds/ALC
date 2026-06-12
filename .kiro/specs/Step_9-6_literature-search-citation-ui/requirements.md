# Requirements Document

## Introduction

This document specifies the requirements for Phase 9.6 — Literature Search, Citation UI, & Audit Trail Mapping — of AlcoaBase. This feature delivers the user-facing frontend and supporting backend APIs that connect the literature search infrastructure (Phases 9.1–9.5) to a dedicated Faceted Search Dashboard and a One-Click Internalization workflow with full traceability integration.

Phase 9.6 introduces six major capabilities:

1. **Faceted Literature Search Dashboard** — A dedicated frontend page providing hybrid search (BM25 keyword + kNN semantic) across the company's indexed literature corpus. Users can apply faceted filters (date range, journal, source, publication type, MeSH terms, device class), paginate results, and preview result cards showing title, abstract, authors, year, and provenance source.

2. **Unified Cross-Corpus Search** — A single search interface that queries both external (public literature ingested via Phase 9.2) and internal (company documents indexed via Phase 4.1) corpora simultaneously or independently, with provenance indicators clearly marking each result as "External" or "Internal."

3. **Search History & Saved Searches** — Users can save search queries (including all filter parameters) for re-execution, view previous searches with their result counts and timestamps, and re-run them. This provides regulatory evidence of search methodology for systematic literature reviews and clinical evaluations.

4. **One-Click Internalization** — Convert a public literature record (IngestionRecord from Phase 9.2) into a managed internal Document entity within the company repository. The internalization process copies the full-text file (if available in MinIO), sets the initial BPMN workflow state, and links back to the original IngestionRecord for provenance tracking.

5. **Citation Management** — Users can organize internalized papers into citation collections (e.g., "MDR Clinical Evaluation Literature Review Q1 2025") for regulatory submissions, add/remove papers from collections, and export citation lists.

6. **Traceability Mapping & Audit Trail Integration** — When internalizing a paper, users can optionally link it to specific URS requirements or IQ/OQ/PQ test cases from the Traceability Matrix (Phase 5.6), creating regulatory evidence chains. Every search execution, result viewing, internalization action, traceability link creation, and citation management operation is logged immutably in the Audit Trail (Phase 6.3) with full parameter capture.

The system reuses existing infrastructure: `HybridQueryEngine` (Phase 9.3) for search, `IngestionRecord` model (Phase 9.2) for literature metadata, `Document` model and BPMN workflow engine (Phase 3.1) for internalized documents, `Traceability_Engine` (Phase 5.6) for requirement/test case linkage, `Audit_Trail_Service` (Phase 6.3) for immutable logging, MinIO object storage for file copies, and the existing frontend `apiClient` for API communication. All operations are company-scoped via `X-Company-Id` header and require `X-Change-Reason` on mutations.

## Glossary

- **Literature_Search_Service**: The backend service responsible for executing hybrid literature searches, managing saved searches, coordinating internalization, and managing citation collections. Builds on the existing HybridQueryEngine (Phase 9.3) and Literature_Gateway_Service (Phase 9.1).
- **Literature_Search_Dashboard**: The frontend page at `/literature-search` providing the faceted search interface, result display, internalization controls, and citation management.
- **Literature_Search_Result**: A normalized result object returned from a hybrid search query, containing: ingestion_record_id, title, authors, abstract, publication_date, journal, source (adapter name), publication_type, mesh_terms, doi, relevance_score, provenance ("external" or "internal"), and full_text_available flag.
- **Saved_Search**: A persisted search query configuration containing: query text, all applied filters, creation timestamp, last execution timestamp, result count at last execution, and user-provided name/description. Enables reproducible search methodology documentation.
- **Search_Execution_Log**: An immutable audit record capturing every search execution with: query terms, filters applied, sources queried, results count, execution timestamp, duration, and user identity. Logged via the existing Audit_Trail_Service (Phase 6.3).
- **Internalization**: The process of converting a public literature IngestionRecord into a managed internal Document entity: creating the Document record, copying the full-text file from the literature MinIO bucket to the documents bucket, setting initial workflow state (Draft), and establishing provenance linkage back to the IngestionRecord.
- **Internalized_Document**: A Document entity created through the internalization process, containing a reference to the originating IngestionRecord and metadata indicating it was sourced from external literature.
- **Citation_Collection**: A named grouping of internalized documents organized for a specific regulatory purpose (e.g., clinical evaluation, post-market surveillance report). Contains: name, description, purpose, creation date, and ordered list of document references.
- **Traceability_Link_Request**: A request to associate an internalized document with specific requirements or test cases from the Traceability Matrix (Phase 5.6), creating a bidirectional regulatory evidence chain.
- **Provenance_Indicator**: A UI marker ("External" or "Internal") displayed on each search result, indicating whether the result originates from the public literature corpus (ingested via Phase 9.2) or the company's internal document repository.
- **Faceted_Filter**: A search constraint applied to narrow results by a specific metadata dimension: date_range, journal, source_adapter, publication_type, mesh_terms, or device_class (for vigilance-related papers linked to Phase 9.5 products).
- **HybridQueryEngine**: The existing search component (Phase 9.3) performing combined BM25 keyword + kNN semantic similarity searches against the company's OpenSearch index.
- **IngestionRecord**: The existing model (Phase 9.2) representing an ingested literature item with metadata, abstract, full-text reference, and embedding status.
- **Document**: The existing model representing a managed internal document with BPMN workflow state, versioning, and full audit trail.
- **Traceability_Engine**: The existing service (Phase 5.6) for managing traceability matrices and requirement-to-test-case mappings.
- **Audit_Trail_Service**: The existing service (Phase 6.3) for recording immutable audit events.
- **Company**: The multi-tenant entity (Phase 1.1) to which all searches, documents, and collections are scoped.

## Requirements

### Requirement 1: Faceted Literature Search API

**User Story:** As a quality manager, I want to execute hybrid searches against the indexed literature corpus with faceted filtering, so that I can efficiently find relevant scientific evidence for regulatory submissions.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/query` endpoint accepting a JSON body with: `query_text` (string, 1–1000 characters), `filters` (object with optional fields: `date_from` (ISO date), `date_to` (ISO date), `journals` (array of strings, max 20), `sources` (array of source adapter names, max 10), `publication_types` (array of strings, max 10), `mesh_terms` (array of strings, max 30), `device_class` (array of enum values from Medical_Product device classes, max 5)), `search_mode` (enum: "hybrid", "keyword", "semantic", default "hybrid"), `include_internal` (boolean, default false), `page` (integer, default 1), `page_size` (integer, 1–100, default 20), and returning HTTP 200 with paginated Literature_Search_Results.
2. WHEN `search_mode` is "hybrid", THE Literature_Search_Service SHALL execute both BM25 keyword and kNN semantic searches via the HybridQueryEngine and combine results using Reciprocal Rank Fusion (RRF), returning a unified `relevance_score` per result.
3. WHEN `search_mode` is "keyword", THE Literature_Search_Service SHALL execute only BM25 keyword search. WHEN `search_mode` is "semantic", THE Literature_Search_Service SHALL execute only kNN vector similarity search.
4. WHEN `include_internal` is true, THE Literature_Search_Service SHALL additionally query the company's internal document index (Phase 4.1) using the same query parameters and merge results into the response with `provenance: "internal"`, distinct from literature results with `provenance: "external"`.
5. THE Literature_Search_Service SHALL return for each result: `id` (ingestion_record_id or document_id), `title`, `authors` (array of strings), `abstract` (first 500 characters), `publication_date`, `journal`, `source` (adapter name or "internal"), `publication_type`, `mesh_terms`, `doi`, `relevance_score` (float 0.0–1.0), `provenance` ("external" or "internal"), `full_text_available` (boolean), and `is_internalized` (boolean indicating whether this literature item has already been internalized as a Document).
6. THE Literature_Search_Service SHALL return pagination metadata: `total_results`, `page`, `page_size`, `total_pages`, and available facet counts for each filter dimension (journals with result counts, sources with result counts, publication_types with result counts).
7. WHEN filters are applied, THE Literature_Search_Service SHALL apply them as post-filter constraints on the OpenSearch query, reducing results without affecting relevance scoring of remaining results.
8. THE Literature_Search_Service SHALL scope all queries to the company identified by the `X-Company-Id` header. Literature indexed for company A is not visible to company B.
9. IF the HybridQueryEngine is unavailable (OpenSearch connection timeout after 10 seconds or HTTP 503), THEN THE Literature_Search_Service SHALL return HTTP 503 with an error message indicating the search index is temporarily unavailable.
10. IF `query_text` is empty or contains only whitespace, THEN THE Literature_Search_Service SHALL return HTTP 422 with an error message indicating a search query is required.

### Requirement 2: Search Execution Audit Logging

**User Story:** As a regulatory affairs specialist, I want every search execution automatically logged with full parameter capture, so that I can demonstrate reproducible search methodology during FDA/EMA audits.

#### Acceptance Criteria

1. WHEN a search query is executed via `POST /api/literature-search/query`, THE Literature_Search_Service SHALL record a Search_Execution_Log entry in the Audit_Trail_Service containing: `user_id`, `company_id`, `query_text`, `filters` (complete filter object as JSON), `search_mode`, `include_internal`, `total_results_returned`, `execution_timestamp` (UTC), `execution_duration_ms`, and `sources_queried` (list of source adapter names searched).
2. THE Search_Execution_Log SHALL be immutable once recorded and SHALL NOT be modifiable or deletable by any user role.
3. WHEN a user views a specific search result detail (clicks to expand or navigate to full record), THE Literature_Search_Service SHALL record a result-view audit event containing: `user_id`, `company_id`, `ingestion_record_id` or `document_id`, `originating_search_id` (reference to the search execution that surfaced this result), and `view_timestamp`.
4. THE Audit_Trail_Service SHALL categorize literature search audit events under the record_type "literature_search" to enable filtering in the Audit Trail Viewer (Phase 6.3).
5. IF the Audit_Trail_Service is unavailable during search execution, THEN THE Literature_Search_Service SHALL still return search results to the user and SHALL queue the audit log entry for retry via Celery (up to 3 attempts with 1-minute intervals), logging a warning if all retries fail.

### Requirement 3: Saved Searches

**User Story:** As a quality manager conducting a systematic literature review, I want to save my search queries for later re-execution, so that I can document my search strategy and reproduce results for regulatory submissions.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/saved-searches` endpoint accepting: `name` (string, 1–200 characters), `description` (string, optional, max 1000 characters), `query_text` (string, 1–1000 characters), `filters` (same filter object as the query endpoint), `search_mode` (enum), and `include_internal` (boolean), returning HTTP 201 with the created Saved_Search record.
2. THE Literature_Search_Service SHALL expose a `GET /api/literature-search/saved-searches` endpoint returning a paginated list of Saved_Searches for the current user within the company, supporting `page` (default 1) and `page_size` (default 20, max 100) query parameters, ordered by `last_executed_at` descending (most recently executed first), with null `last_executed_at` entries at the end.
3. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/saved-searches/{saved_search_id}/execute` endpoint that re-executes the saved search query with its stored parameters, updates the `last_executed_at` timestamp and `last_result_count`, and returns the search results in the same format as the query endpoint.
4. THE Literature_Search_Service SHALL expose a `DELETE /api/literature-search/saved-searches/{saved_search_id}` endpoint that soft-deletes the saved search (sets `status` to "archived"), returning HTTP 200 on success. The `X-Change-Reason` header is required.
5. THE Saved_Search SHALL store: `id`, `name`, `description`, `query_text`, `filters` (JSON), `search_mode`, `include_internal`, `user_id` (creator), `company_id`, `created_at`, `last_executed_at` (nullable), `last_result_count` (nullable integer), and `status` (enum: "active", "archived").
6. WHEN a Saved_Search is executed, THE system SHALL record the execution in the Search_Execution_Log (Requirement 2) with a reference to the `saved_search_id`, enabling audit traceability between the saved search strategy and its execution history.
7. IF a user attempts to access or execute a Saved_Search belonging to a different user within the same company, THE system SHALL allow read access (viewing the search definition) but restrict execution and deletion to the owning user or users with `document_admin` role.
8. THE system SHALL support a maximum of 200 active Saved_Searches per user per company. IF this limit is exceeded, THEN THE system SHALL return HTTP 422 with an error message indicating the saved search limit has been reached.

### Requirement 4: One-Click Internalization

**User Story:** As a document administrator, I want to internalize a public literature paper into our managed document repository with one click, so that external scientific evidence becomes a governed document with full lifecycle tracking.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/internalize` endpoint accepting: `ingestion_record_id` (UUID, required), `document_name` (string, optional, defaults to the paper title from the IngestionRecord), `document_type` (string, optional, default "literature"), `tags` (array of strings, optional, max 20), `citation_collection_id` (UUID, optional, adds to an existing collection), and `traceability_links` (array of objects with `target_type` ("requirement" or "test_case") and `target_id` (UUID), optional, max 20 entries), returning HTTP 201 with the created Document entity.
2. WHEN internalization is requested, THE Literature_Search_Service SHALL: (a) retrieve the IngestionRecord and verify it belongs to the requesting company, (b) create a new Document entity with metadata copied from the IngestionRecord (title, authors, abstract, publication_date, doi, source), (c) if the IngestionRecord has a full-text file reference in MinIO, copy the file from the literature bucket to the documents bucket under the company's namespace, (d) set the Document's initial BPMN workflow state to "Draft", (e) store a `source_ingestion_record_id` foreign key on the Document linking back to the original IngestionRecord.
3. WHEN an IngestionRecord has already been internalized within the same company (a Document with `source_ingestion_record_id` matching the requested IngestionRecord already exists), THE system SHALL return HTTP 409 with the existing Document ID and a message indicating this paper has already been internalized.
4. WHEN `traceability_links` are provided in the internalization request, THE Literature_Search_Service SHALL invoke the Traceability_Engine (Phase 5.6) to create bidirectional links between the new Document and the specified requirements or test cases, with `link_method: "manual_literature_link"` and `link_confidence: 1.0`.
5. WHEN `citation_collection_id` is provided, THE Literature_Search_Service SHALL add the newly created Document to the specified Citation_Collection, appending it to the end of the collection's ordered list.
6. THE Literature_Search_Service SHALL record an audit event for the internalization action containing: `user_id`, `company_id`, `ingestion_record_id`, `created_document_id`, `traceability_link_ids` (if any were created), `citation_collection_id` (if specified), and `internalization_timestamp`.
7. IF the IngestionRecord referenced by `ingestion_record_id` does not exist or does not belong to the requesting company, THEN THE system SHALL return HTTP 404 with an error message indicating the literature record was not found.
8. IF a user without the `document_admin` or `system_admin` role attempts to internalize, THEN THE system SHALL return HTTP 403 with an error message indicating insufficient permissions.
9. IF the MinIO file copy fails during internalization (source file missing or storage error), THEN THE system SHALL still create the Document entity without the full-text file, set a `full_text_status` field to "unavailable", and log a warning in the audit trail indicating the file copy failure.
10. THE `POST /api/literature-search/internalize` endpoint SHALL require the `X-Change-Reason` header.

### Requirement 5: Citation Collection Management

**User Story:** As a regulatory affairs specialist, I want to organize internalized literature into named citation collections for specific submissions, so that I can compile and export evidence packages for MDR clinical evaluations or PMS reports.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/citation-collections` endpoint accepting: `name` (string, 1–300 characters), `description` (string, optional, max 2000 characters), `purpose` (enum: "clinical_evaluation", "post_market_surveillance", "systematic_literature_review", "risk_assessment", "other"), returning HTTP 201 with the created Citation_Collection. The `X-Change-Reason` header is required.
2. THE Literature_Search_Service SHALL expose a `GET /api/literature-search/citation-collections` endpoint returning a paginated list of Citation_Collections for the company, supporting `page` (default 1), `page_size` (default 20, max 100), and optional `purpose` filter, ordered by `updated_at` descending.
3. THE Literature_Search_Service SHALL expose a `GET /api/literature-search/citation-collections/{collection_id}` endpoint returning the collection detail including its ordered list of document references with metadata (title, authors, year, doi, document_id).
4. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/citation-collections/{collection_id}/documents` endpoint accepting: `document_ids` (array of UUIDs, 1–50 entries), which adds the specified internalized Documents to the collection. The `X-Change-Reason` header is required. Returns HTTP 200 with updated collection.
5. THE Literature_Search_Service SHALL expose a `DELETE /api/literature-search/citation-collections/{collection_id}/documents/{document_id}` endpoint that removes a document from the collection (does not delete the Document itself). The `X-Change-Reason` header is required. Returns HTTP 200 on success.
6. THE Literature_Search_Service SHALL expose a `PUT /api/literature-search/citation-collections/{collection_id}` endpoint accepting updated `name`, `description`, and `purpose` fields. The `X-Change-Reason` header is required. Returns HTTP 200 with updated collection.
7. THE Literature_Search_Service SHALL expose a `DELETE /api/literature-search/citation-collections/{collection_id}` endpoint that soft-deletes the collection (status set to "archived"), preserving all historical references. The `X-Change-Reason` header is required.
8. IF a user without the `document_admin` or `system_admin` role attempts to create, modify, or delete a Citation_Collection, THEN THE system SHALL return HTTP 403.
9. IF a `document_id` in the add-documents request does not reference a Document with `source_ingestion_record_id` set (i.e., not an internalized literature document), THEN THE system SHALL return HTTP 422 indicating only internalized literature documents can be added to citation collections.
10. THE system SHALL support a maximum of 500 documents per Citation_Collection. IF adding documents would exceed this limit, THEN THE system SHALL return HTTP 422 with an error indicating the collection capacity has been reached.
11. WHEN documents are added to or removed from a Citation_Collection, THE system SHALL record an audit event with: `user_id`, `company_id`, `collection_id`, `document_ids_added` or `document_id_removed`, and `action_timestamp`.

### Requirement 6: Traceability Mapping for Internalized Literature

**User Story:** As a quality manager, I want to link internalized scientific papers to specific requirements or test cases in our traceability matrix, so that I can establish regulatory evidence chains demonstrating that product decisions are supported by published scientific evidence.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/traceability-links` endpoint accepting: `document_id` (UUID, required, must be an internalized Document), `links` (array of objects with `target_type` ("requirement" or "test_case"), `target_id` (UUID), and `rationale` (string, optional, max 1000 characters), 1–20 entries), returning HTTP 201 with the created Traceability_Link records.
2. WHEN traceability links are created, THE Literature_Search_Service SHALL invoke the Traceability_Engine to create entries in the traceability matrix with: source document = the internalized Document, target = the specified requirement or test case, `link_method: "literature_evidence"`, `link_confidence: 1.0`, and the optional `rationale` stored as link metadata.
3. THE Literature_Search_Service SHALL expose a `GET /api/literature-search/traceability-links` endpoint accepting query parameters `document_id` (optional) and `target_id` (optional), returning all literature traceability links matching the filter criteria within the company scope, with pagination support.
4. THE Literature_Search_Service SHALL expose a `DELETE /api/literature-search/traceability-links/{link_id}` endpoint that removes a specific traceability link. The `X-Change-Reason` header is required. Returns HTTP 200 on success.
5. IF the `document_id` does not reference an internalized Document (no `source_ingestion_record_id`), THEN THE system SHALL return HTTP 422 indicating traceability links can only be created for internalized literature documents.
6. IF any `target_id` does not reference a valid requirement or test case in the Traceability_Engine within the company scope, THEN THE system SHALL return HTTP 404 indicating the specified target was not found.
7. IF a user without the `document_admin` or `system_admin` role attempts to create or delete traceability links, THEN THE system SHALL return HTTP 403.
8. WHEN a traceability link is created or deleted, THE system SHALL record an audit event containing: `user_id`, `company_id`, `document_id`, `target_type`, `target_id`, `action` ("created" or "deleted"), and `action_timestamp`.
9. THE `POST /api/literature-search/traceability-links` endpoint SHALL require the `X-Change-Reason` header.

### Requirement 7: Search Results Export

**User Story:** As a regulatory affairs specialist, I want to export search results as structured reports documenting my search strategy, so that I can include search methodology evidence in FDA/EMA submissions following PRISMA guidelines.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL expose a `POST /api/literature-search/export` endpoint accepting: `search_execution_id` (UUID, optional, exports results from a specific past search execution), `saved_search_id` (UUID, optional, re-executes and exports the saved search), `format` (enum: "csv", "pdf"), and `include_prisma_flow` (boolean, default false, PDF only), returning the generated file as a download response.
2. WHEN `format` is "csv", THE system SHALL generate a CSV file with columns: title, authors (semicolon-separated), publication_date, journal, source, publication_type, doi, abstract (first 300 characters), relevance_score, provenance, and mesh_terms (semicolon-separated).
3. WHEN `format` is "pdf", THE system SHALL generate a PDF document using ReportLab containing: a header section with search parameters (query text, filters applied, date executed, databases searched), a results summary section (total results per source, total unique results), and a tabular listing of all results with title, authors, year, journal, and doi.
4. WHEN `format` is "pdf" and `include_prisma_flow` is true, THE system SHALL include a PRISMA-style flow diagram section showing: records identified per database, duplicates removed, records screened, records excluded (if filter data available), and records included in the export.
5. THE export SHALL include a metadata footer containing: export generation timestamp, user who generated the export, company name, and a statement confirming the search was executed against the AlcoaBase literature index with complete audit trail logging.
6. IF neither `search_execution_id` nor `saved_search_id` is provided, THEN THE system SHALL return HTTP 422 indicating at least one search reference is required.
7. IF the referenced search execution or saved search does not belong to the requesting company, THEN THE system SHALL return HTTP 404.
8. WHEN an export is generated, THE system SHALL record an audit event with: `user_id`, `company_id`, `export_format`, `search_reference_id`, `results_exported_count`, and `export_timestamp`.

### Requirement 8: Multi-Tenancy and Access Control

**User Story:** As a system administrator, I want all literature search operations strictly scoped to the requesting company with role-based access enforcement, so that tenant isolation is maintained and only authorized users can perform privileged actions.

#### Acceptance Criteria

1. THE Literature_Search_Service SHALL scope all read operations (search queries, saved searches, citation collections, traceability links) to the company identified by the `X-Company-Id` header. Results from one company's literature index are not visible to another company.
2. THE Literature_Search_Service SHALL enforce role-based access: users with `member` role or above can execute searches, view results, and manage their own saved searches; users with `document_admin` or `system_admin` role can internalize literature, manage citation collections, and create/delete traceability links.
3. WHEN the `X-Company-Id` header is missing on any literature search endpoint, THE system SHALL return HTTP 400 with an error indicating the company context is required.
4. WHEN the `X-Change-Reason` header is missing on any POST, PUT, PATCH, or DELETE endpoint, THE system SHALL return HTTP 400 (enforced by existing AuditMiddleware).
5. IF a user attempts to access a Saved_Search, Citation_Collection, or Document belonging to a different company (even if they know the ID), THEN THE system SHALL return HTTP 404 (treating it as non-existent to avoid information leakage).
6. THE system SHALL validate that `X-Company-Id` matches the authenticated user's company membership before processing any request.

### Requirement 9: Literature Search Dashboard Frontend

**User Story:** As a quality manager, I want a dedicated search page with an intuitive interface for executing literature searches, viewing results, and managing internalization, so that I can efficiently find and capture regulatory evidence.

#### Acceptance Criteria

1. THE Literature_Search_Dashboard SHALL be accessible at the route `/literature-search` in the frontend application, protected by authentication (redirect to login if unauthenticated).
2. THE Literature_Search_Dashboard SHALL display a search input field with mode selector (hybrid/keyword/semantic), a toggle for "Include Internal Documents", and a "Search" button that dispatches the query to `POST /api/literature-search/query`.
3. THE Literature_Search_Dashboard SHALL display a faceted filter panel with: date range picker (from/to), journal multi-select, source multi-select (populated from available adapters), publication type multi-select, MeSH terms input (tag-style with autocomplete from indexed terms), and device class multi-select (populated from the Phase 9.5 Medical_Product device class enum).
4. THE Literature_Search_Dashboard SHALL display search results as cards showing: title (linked to detail view), authors (truncated to 3 with "+N more"), publication year, journal name, source adapter name, relevance score (visual bar or percentage), provenance badge ("External" in blue or "Internal" in green), full-text availability indicator, and internalization status (already internalized shown with a checkmark).
5. THE Literature_Search_Dashboard SHALL display pagination controls below the results with page numbers, previous/next buttons, and a result count summary (e.g., "Showing 1–20 of 342 results").
6. THE Literature_Search_Dashboard SHALL display facet count badges next to each filter option showing how many results match that facet value, updated after each search execution.
7. THE Literature_Search_Dashboard SHALL provide an "Internalize" button on each external result card (visible only to document_admin/system_admin users) that opens a dialog for configuring internalization options (name override, tags, citation collection selection, traceability link selection) before submitting to `POST /api/literature-search/internalize`.
8. THE Literature_Search_Dashboard SHALL provide a "Save Search" button that opens a dialog to name and describe the current search configuration, submitting to `POST /api/literature-search/saved-searches`.
9. THE Literature_Search_Dashboard SHALL include a "Saved Searches" panel (collapsible sidebar or tab) listing the user's saved searches with name, last executed date, and result count, with options to re-execute or delete each entry.
10. THE Literature_Search_Dashboard SHALL include a "Search History" section displaying the last 20 search executions for the current user (from audit trail) with query text, timestamp, and result count, allowing re-execution of any historical search.
11. THE Literature_Search_Dashboard SHALL display loading states (skeleton cards) during search execution and error states (toast notifications) when the search API returns an error.
12. THE Literature_Search_Dashboard SHALL use Zustand for managing search state (query, filters, results, pagination, saved searches) and react-hook-form for the internalization dialog form validation.

### Requirement 10: Export and Reporting Frontend

**User Story:** As a regulatory affairs specialist, I want to export search results directly from the dashboard as CSV or PDF, so that I can include documented search strategies in regulatory submission packages.

#### Acceptance Criteria

1. THE Literature_Search_Dashboard SHALL display an "Export" button (visible when search results are present) offering format options: "Export as CSV" and "Export as PDF".
2. WHEN "Export as PDF" is selected, THE dashboard SHALL display a checkbox option "Include PRISMA Flow Diagram" before initiating the export.
3. WHEN an export is initiated, THE dashboard SHALL submit a request to `POST /api/literature-search/export` with the current search execution reference and selected format, and trigger a file download upon receiving the response.
4. THE dashboard SHALL display a loading indicator during export generation and a success toast upon completion.
5. IF the export request fails, THE dashboard SHALL display an error toast with the failure reason.

