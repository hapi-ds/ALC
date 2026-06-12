# Implementation Plan: Literature Search, Citation UI, & Audit Trail Mapping (Phase 9.6)

## Overview

This plan implements the user-facing literature search dashboard and backend APIs connecting the existing search infrastructure (Phases 9.1–9.5) to a Faceted Search Dashboard with One-Click Internalization, Citation Collection management, Traceability Matrix integration, and full audit trail logging. Tasks are ordered by dependency: database models/schemas first, then services, API router, Celery tasks, frontend types/store/hooks, UI components, and finally property-based and unit/integration tests. Each task builds incrementally on previous work, ensuring no orphaned or disconnected code.

## Tasks

- [x] 1. Database models, schemas, exceptions, and migration
  - [x] 1.1 Create SQLAlchemy models for Phase 9.6
    - Create `src/backend/src/alcoabase/literature/search/__init__.py`, `models/__init__.py`
    - Create `models/saved_search.py`: `SavedSearch` model with name (String 200, NOT NULL), description (Text, nullable), query_text (Text, NOT NULL), filters (JSONB, NOT NULL, default {}), search_mode (String 20, NOT NULL, default "hybrid"), include_internal (Boolean, NOT NULL, default False), user_id FK → users.id, company_id FK → companies.id, last_executed_at (TIMESTAMPTZ, nullable), last_result_count (Integer, nullable), status (String 20, NOT NULL, default "active"), created_at, updated_at, AuditMixin, `__versioned__ = {}`
    - Create `models/citation_collection.py`: `CitationCollection` model with name (String 300, NOT NULL), description (Text, nullable), purpose (String 50, NOT NULL), company_id FK, created_by FK → users.id, status (String 20, NOT NULL, default "active"), created_at, updated_at, AuditMixin, `__versioned__ = {}`; `CitationCollectionDocument` junction model with collection_id FK, document_id FK, position (Integer, NOT NULL), added_at (TIMESTAMPTZ, NOT NULL, default now()), added_by FK → users.id; UNIQUE constraint on (collection_id, document_id)
    - Create `models/search_execution_log.py`: `SearchExecutionLog` model (immutable — no update/delete) with user_id FK, company_id FK, query_text (Text, NOT NULL), filters (JSONB, NOT NULL, default {}), search_mode (String 20, NOT NULL), include_internal (Boolean, NOT NULL), total_results (Integer, NOT NULL), sources_queried (JSONB, NOT NULL), execution_duration_ms (Integer, NOT NULL), saved_search_id FK (nullable), executed_at (TIMESTAMPTZ, NOT NULL, default now())
    - Add indexes: saved_searches (company_id, user_id, status), (company_id, user_id, last_executed_at DESC); citation_collections (company_id, status), (company_id, purpose, status); citation_collection_documents UNIQUE (collection_id, document_id), (collection_id, position); search_execution_logs (company_id, user_id, executed_at DESC), (saved_search_id)
    - _Requirements: 2.2, 3.5, 5.1, 5.2, 5.3_

  - [x] 1.2 Create Pydantic schemas for Phase 9.6
    - Create `src/backend/src/alcoabase/literature/search/schemas/__init__.py`
    - Create `schemas/query.py`: `LiteratureSearchQueryRequest` (query_text 1–1000 chars, filters object with date_from/date_to ISO optional, journals max 20, sources max 10, publication_types max 10, mesh_terms max 30, device_class max 5; search_mode enum hybrid/keyword/semantic default hybrid; include_internal bool default false; page int default 1; page_size 1–100 default 20), `LiteratureSearchResult`, `PaginatedSearchResponse` with results, pagination, facets, search_execution_id
    - Create `schemas/internalization.py`: `InternalizationRequest` (ingestion_record_id UUID required, document_name optional, document_type default "literature", tags max 20, citation_collection_id optional, traceability_links optional max 20 with target_type enum + target_id), `InternalizedDocumentResponse`
    - Create `schemas/saved_search.py`: `CreateSavedSearchRequest` (name 1–200 chars, description optional max 1000, query_text 1–1000, filters, search_mode, include_internal), `SavedSearchResponse`, `PaginatedSavedSearchResponse`
    - Create `schemas/citation_collection.py`: `CreateCitationCollectionRequest` (name 1–300, description optional max 2000, purpose enum), `UpdateCitationCollectionRequest`, `CitationCollectionResponse`, `CitationCollectionDetailResponse`, `AddDocumentsRequest` (document_ids 1–50 entries)
    - Create `schemas/traceability.py`: `CreateTraceabilityLinksRequest` (document_id UUID, links array 1–20 with target_type, target_id, rationale optional max 1000), `TraceabilityLinkResponse`, `PaginatedTraceabilityLinksResponse`
    - Create `schemas/export.py`: `ExportRequest` (search_execution_id optional, saved_search_id optional, format enum csv/pdf, include_prisma_flow bool default false)
    - _Requirements: 1.1, 3.1, 4.1, 5.1, 5.4, 6.1, 7.1_

  - [x] 1.3 Create literature search exception classes
    - Create `src/backend/src/alcoabase/literature/search/exceptions.py`
    - Define: `SearchUnavailableError`, `DuplicateInternalizationError`, `IngestionRecordNotFoundError`, `InsufficientPermissionsError`, `SavedSearchLimitExceededError`, `CollectionCapacityExceededError`, `NonInternalizedDocumentError`, `InvalidTraceabilityTargetError`, `ExportReferenceNotFoundError`
    - _Requirements: 1.9, 1.10, 3.8, 4.3, 4.7, 4.8, 5.9, 5.10, 6.5, 6.6, 7.6, 7.7_

  - [x] 1.4 Create Alembic migration for Phase 9.6 tables and documents table modification
    - Generate migration adding `saved_searches`, `citation_collections`, `citation_collection_documents`, `search_execution_logs` tables
    - Add columns to `documents` table: `source_ingestion_record_id` (Integer FK → literature_ingestion_records.id, nullable), `full_text_status` (String 20, nullable, default NULL)
    - Add partial unique index on documents: UNIQUE (company_id, source_ingestion_record_id) WHERE source_ingestion_record_id IS NOT NULL
    - Include all indexes defined in the design
    - _Requirements: 2.2, 3.5, 4.2, 5.1_

- [x] 2. Checkpoint - Ensure models and schemas compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement backend services
  - [x] 3.1 Implement LiteratureSearchService class
    - Create `src/backend/src/alcoabase/literature/search/services/__init__.py` and `literature_search_service.py`
    - Implement `__init__` accepting AsyncSession, HybridQueryEngine, AuditTrailService, TraceabilityMatrixService, storage_client (aioboto3)
    - Implement `execute_search()`: delegate to HybridQueryEngine.unified_search(), enrich results with is_internalized flag (query documents table for source_ingestion_record_id matches), compute facet counts, log SearchExecutionLog record, call AuditTrailService (async-safe with Celery fallback on failure)
    - Implement `internalize()`: verify IngestionRecord ownership → duplicate check (query documents by source_ingestion_record_id) → create Document (status=Draft, type=literature) → copy file from literature bucket to documents bucket → create traceability links if provided → add to collection if provided → audit log
    - Implement `create_saved_search()`: validate limit (200 active per user per company), persist, return response
    - Implement `list_saved_searches()`: paginated, ordered by last_executed_at DESC (NULLs last), company+user scoped
    - Implement `execute_saved_search()`: reload stored params, call execute_search, update last_executed_at and last_result_count
    - Implement `delete_saved_search()`: soft-delete (status=archived), verify ownership or document_admin role
    - Implement `create_citation_collection()`: persist with purpose enum validation
    - Implement `list_citation_collections()`: paginated, optional purpose filter, ordered by updated_at DESC
    - Implement `get_citation_collection()`: return detail with ordered document list
    - Implement `update_citation_collection()`: update name/description/purpose
    - Implement `delete_citation_collection()`: soft-delete (status=archived)
    - Implement `add_documents_to_collection()`: verify each doc has source_ingestion_record_id set, enforce 500 doc limit, assign positions after existing max, audit log
    - Implement `remove_document_from_collection()`: delete junction record only (Document preserved), audit log
    - Implement `create_traceability_links()`: verify document is internalized, invoke TraceabilityMatrixService with link_method="literature_evidence" and confidence=1.0, audit log
    - Implement `list_traceability_links()`: filter by document_id or target_id, paginated, company-scoped
    - Implement `delete_traceability_link()`: remove link, audit log
    - _Requirements: 1.1–1.10, 2.1–2.5, 3.1–3.8, 4.1–4.10, 5.1–5.11, 6.1–6.9, 8.1–8.6_

  - [x] 3.2 Implement ExportService class
    - Create `src/backend/src/alcoabase/literature/search/services/export_service.py`
    - Implement `__init__` accepting AsyncSession
    - Implement `generate_csv_export()`: retrieve search execution results, build CSV in-memory with columns (title, authors semicolon-separated, publication_date, journal, source, publication_type, doi, abstract first 300 chars, relevance_score, provenance, mesh_terms semicolon-separated), return StreamingResponse
    - Implement `generate_pdf_export()`: retrieve search execution, build PDF with ReportLab containing header (search params, date, databases), results summary (total per source), tabular listing (title, authors, year, journal, doi), optional PRISMA flow diagram section, metadata footer (timestamp, user, company, audit confirmation)
    - Validate that at least one of search_execution_id or saved_search_id is provided (raise HTTP 422)
    - Verify export reference belongs to requesting company (raise HTTP 404)
    - Record audit event on export generation
    - _Requirements: 7.1–7.8_

- [x] 4. Implement API router
  - [x] 4.1 Create literature_search router with all endpoints
    - Create `src/backend/src/alcoabase/api/literature_search.py`
    - `POST /api/literature-search/query`: require member+ role, X-Company-Id, X-Change-Reason; validate body; call LiteratureSearchService.execute_search; return 200
    - `POST /api/literature-search/saved-searches`: require member+ role, X-Company-Id, X-Change-Reason; call create_saved_search; return 201
    - `GET /api/literature-search/saved-searches`: require member+ role, X-Company-Id; call list_saved_searches; return 200
    - `POST /api/literature-search/saved-searches/{id}/execute`: require owner/document_admin, X-Company-Id, X-Change-Reason; call execute_saved_search; return 200
    - `DELETE /api/literature-search/saved-searches/{id}`: require owner/document_admin, X-Company-Id, X-Change-Reason; call delete_saved_search; return 200
    - `POST /api/literature-search/internalize`: require document_admin+, X-Company-Id, X-Change-Reason; call internalize; return 201
    - `POST /api/literature-search/citation-collections`: require document_admin+, X-Company-Id, X-Change-Reason; call create_citation_collection; return 201
    - `GET /api/literature-search/citation-collections`: require member+, X-Company-Id; call list_citation_collections; return 200
    - `GET /api/literature-search/citation-collections/{id}`: require member+, X-Company-Id; call get_citation_collection; return 200
    - `PUT /api/literature-search/citation-collections/{id}`: require document_admin+, X-Company-Id, X-Change-Reason; call update_citation_collection; return 200
    - `DELETE /api/literature-search/citation-collections/{id}`: require document_admin+, X-Company-Id, X-Change-Reason; call delete_citation_collection; return 200
    - `POST /api/literature-search/citation-collections/{id}/documents`: require document_admin+, X-Company-Id, X-Change-Reason; call add_documents_to_collection; return 200
    - `DELETE /api/literature-search/citation-collections/{id}/documents/{doc_id}`: require document_admin+, X-Company-Id, X-Change-Reason; call remove_document_from_collection; return 200
    - `POST /api/literature-search/traceability-links`: require document_admin+, X-Company-Id, X-Change-Reason; call create_traceability_links; return 201
    - `GET /api/literature-search/traceability-links`: require member+, X-Company-Id; accept document_id and target_id query params; call list_traceability_links; return 200
    - `DELETE /api/literature-search/traceability-links/{id}`: require document_admin+, X-Company-Id, X-Change-Reason; call delete_traceability_link; return 200
    - `POST /api/literature-search/export`: require member+, X-Company-Id, X-Change-Reason; call ExportService; return file download StreamingResponse
    - _Requirements: 1.1, 3.1–3.4, 4.1, 5.1–5.7, 6.1–6.4, 7.1, 8.1–8.6_

  - [x] 4.2 Register literature_search router in central router.py
    - Add `literature_search_router` to `src/backend/src/alcoabase/api/router.py`
    - Verify route prefix is `/api/literature-search`
    - _Requirements: 1.1, 8.1_

- [x] 5. Implement Celery tasks for audit retry
  - [x] 5.1 Create literature_search_tasks.py
    - Create `src/backend/src/alcoabase/tasks/literature_search_tasks.py`
    - Implement `retry_audit_log` task: queue=`literature_ingestion`, max_retries=3, retry intervals 1 minute each, acks_late=True
    - Accept audit event payload (user_id, company_id, record_type "literature_search", event_data), attempt to write via AuditTrailService, log warning if all retries exhausted
    - Register task with celery_app
    - _Requirements: 2.5_

- [x] 6. Checkpoint - Ensure backend compiles and router is registered
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Frontend types, store, and hooks
  - [x] 7.1 Create TypeScript type definitions
    - Create `src/frontend/src/types/literatureSearch.ts`
    - Define interfaces: `SearchFilters` (date_from, date_to, journals, sources, publication_types, mesh_terms, device_class), `LiteratureSearchResult` (id, title, authors, abstract, publication_date, journal, source, publication_type, mesh_terms, doi, relevance_score, provenance, full_text_available, is_internalized), `PaginationMeta` (total_results, page, page_size, total_pages), `FacetCounts` (journals, sources, publication_types each as {value, count}[]), `SavedSearch` (id, name, description, query_text, filters, search_mode, include_internal, last_executed_at, last_result_count, status, created_at), `CitationCollection` (id, name, description, purpose, status, document_count, created_at, updated_at), `CitationCollectionDetail` (extends CitationCollection with documents array), `TraceabilityLink` (id, document_id, target_type, target_id, rationale, created_at), `SearchHistoryEntry` (id, query_text, search_mode, total_results, executed_at), `InternalizationRequest`, `ExportRequest`
    - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.9_

  - [x] 7.2 Create Zustand store for literature search state
    - Create `src/frontend/src/stores/literatureSearchStore.ts`
    - Implement state: queryText, searchMode (hybrid/keyword/semantic), includeInternal, filters (SearchFilters), results (LiteratureSearchResult[]), pagination (PaginationMeta | null), facetCounts (FacetCounts | null), isLoading, error, savedSearches, savedSearchesLoading, searchHistory
    - Implement actions: setQueryText, setSearchMode, setIncludeInternal, setFilters, executeSearch (POST /api/literature-search/query), loadSavedSearches (GET /api/literature-search/saved-searches), saveCurrentSearch (POST /api/literature-search/saved-searches), executeSavedSearch (POST .../execute), deleteSavedSearch (DELETE), loadSearchHistory, resetSearch
    - Use apiClient for all API calls with proper headers (X-Company-Id, X-Change-Reason on mutations)
    - _Requirements: 9.2, 9.8, 9.9, 9.10, 9.12_

  - [x] 7.3 Create useLiteratureSearch hook for API integration
    - Create `src/frontend/src/hooks/useLiteratureSearch.ts`
    - Implement `useInternalize()`: POST /api/literature-search/internalize with loading/error state management
    - Implement `useCitationCollections()`: CRUD operations for citation collections
    - Implement `useTraceabilityLinks()`: create/list/delete traceability links
    - Implement `useExport()`: POST /api/literature-search/export triggering file download
    - All hooks use apiClient, handle loading/error states, provide success/error toast feedback
    - _Requirements: 9.7, 10.1–10.5_

- [x] 8. Checkpoint - Ensure frontend types and store compile
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Frontend UI components
  - [x] 9.1 Create SearchInput and SearchModeSelector components
    - Create `src/frontend/src/components/literature-search/SearchInput.tsx`: text input field with search button, dispatches executeSearch from store on submit, disables submit for empty/whitespace-only queries
    - Create `src/frontend/src/components/literature-search/SearchModeSelector.tsx`: radio group or segmented control for hybrid/keyword/semantic mode selection, toggle for "Include Internal Documents"
    - Use shadcn/ui Input, Button, RadioGroup, Switch components
    - _Requirements: 9.2_

  - [x] 9.2 Create FacetFilterPanel component
    - Create `src/frontend/src/components/literature-search/FacetFilterPanel.tsx`
    - Implement: date range picker (from/to), journal multi-select with count badges, source multi-select (from available adapters) with count badges, publication type multi-select with count badges, MeSH terms tag-style input with autocomplete, device class multi-select (from Phase 9.5 enum)
    - Display facet count badges next to each option showing matching result count
    - Connect to store filters state via setFilters action
    - Use shadcn/ui DatePicker, Select, MultiSelect, Badge components
    - _Requirements: 9.3, 9.6_

  - [x] 9.3 Create SearchResultCard and SearchResultsList components
    - Create `src/frontend/src/components/literature-search/SearchResultCard.tsx`: display title (linked), authors (truncated to 3 + "+N more"), publication year, journal, source adapter, relevance score (visual bar), provenance badge ("External" blue / "Internal" green), full-text indicator, internalization status checkmark, "Internalize" button (visible to document_admin/system_admin only)
    - Create `src/frontend/src/components/literature-search/SearchResultsList.tsx`: maps results array to SearchResultCard components, displays loading skeletons during search, empty state message when no results
    - Use shadcn/ui Card, Badge, Button, Skeleton components
    - _Requirements: 9.4, 9.7, 9.11_

  - [x] 9.4 Create PaginationControls component
    - Create `src/frontend/src/components/literature-search/PaginationControls.tsx`
    - Display page numbers, previous/next buttons, result count summary ("Showing 1–20 of 342 results")
    - Connect to store pagination state, dispatch executeSearch with new page on click
    - Use shadcn/ui Pagination components
    - _Requirements: 9.5_

  - [x] 9.5 Create InternalizationDialog with CitationCollectionSelector and TraceabilityLinkSelector
    - Create `src/frontend/src/components/literature-search/InternalizationDialog.tsx`: modal dialog with form fields (document name override, tags input, citation collection selector, traceability link selector), submit button calling POST /api/literature-search/internalize via useInternalize hook
    - Create `src/frontend/src/components/literature-search/CitationCollectionSelector.tsx`: dropdown/combobox listing available citation collections, option to create new
    - Create `src/frontend/src/components/literature-search/TraceabilityLinkSelector.tsx`: multi-select for requirements/test cases from TraceabilityMatrix, each with target_type selector and rationale field
    - Use react-hook-form for form validation, shadcn/ui Dialog, Select, Input, Textarea
    - _Requirements: 9.7, 4.1, 4.4, 4.5_

  - [x] 9.6 Create SaveSearchDialog and SavedSearchesPanel components
    - Create `src/frontend/src/components/literature-search/SaveSearchDialog.tsx`: modal with name (required 1–200), description (optional max 1000), submits via saveCurrentSearch store action
    - Create `src/frontend/src/components/literature-search/SavedSearchesPanel.tsx`: collapsible sidebar/tab listing saved searches with name, last executed date, result count; re-execute and delete buttons per entry
    - Use shadcn/ui Dialog, Input, Textarea, Button, ScrollArea
    - _Requirements: 9.8, 9.9_

  - [x] 9.7 Create SearchHistoryPanel and ExportMenu components
    - Create `src/frontend/src/components/literature-search/SearchHistoryPanel.tsx`: display last 20 search executions with query text, timestamp, result count; click to re-execute
    - Create `src/frontend/src/components/literature-search/ExportMenu.tsx`: dropdown button offering "Export as CSV" and "Export as PDF" (with PRISMA checkbox for PDF), calls useExport hook, shows loading indicator during generation, success/error toast
    - Use shadcn/ui DropdownMenu, Checkbox, Button components
    - _Requirements: 9.10, 10.1–10.5_

  - [x] 9.8 Create LiteratureSearchPage and wire all components
    - Create `src/frontend/src/pages/LiteratureSearchPage.tsx`
    - Compose: SearchInput + SearchModeSelector (top), FacetFilterPanel (sidebar), SearchResultsList (main content), PaginationControls (bottom), SavedSearchesPanel + SearchHistoryPanel (right sidebar or tabs), ExportMenu (top-right), SaveSearchDialog (triggered by button)
    - Register route at `/literature-search` in router config, protected by authentication
    - On mount: load saved searches and search history
    - Display loading states (skeleton cards), error states (toast notifications)
    - _Requirements: 9.1, 9.11, 9.12_

- [x] 10. Checkpoint - Ensure frontend compiles and renders
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Write property-based tests (18 properties from design)
  - [x] 11.1 Write property test: Search result schema validity (Property 1)
    - **Property 1: Search result schema validity**
    - Use Hypothesis to generate random search results with varying field values (relevance_score floats, provenance strings, abstract lengths, author arrays)
    - Assert every result has: relevance_score in [0.0, 1.0], provenance in {"external", "internal"}, abstract length ≤ 500, all required fields non-null (id, title, authors, source, publication_type)
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 1.4, 1.5**

  - [x] 11.2 Write property test: Pagination metadata correctness (Property 2)
    - **Property 2: Pagination metadata correctness**
    - Use Hypothesis to generate random (total_results, page, page_size) triples with total_results 0–10000, page 1–500, page_size 1–100
    - Assert total_pages == ceil(total_results / page_size), results on current page == min(page_size, total_results - (page-1)*page_size), page ≤ total_pages (or empty when page > total_pages)
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 1.6**

  - [x] 11.3 Write property test: Tenant isolation (Property 3)
    - **Property 3: Tenant isolation**
    - Use Hypothesis to generate data for 2+ companies (random saved searches, collections, traceability links), query from company A context
    - Assert zero results belonging to company B appear in any response
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 1.8, 8.1, 8.5**

  - [x] 11.4 Write property test: Whitespace query rejection (Property 4)
    - **Property 4: Whitespace query rejection**
    - Use Hypothesis `st.text(alphabet=st.characters(whitespace_categories=("Zs", "Zl", "Zp", "Cc")))` to generate whitespace-only strings including empty string
    - Assert submitting as query_text returns HTTP 422 with zero results
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 1.10**

  - [x] 11.5 Write property test: Search execution creates audit log (Property 5)
    - **Property 5: Search execution creates audit log**
    - Use Hypothesis to generate valid search requests (non-empty query, valid filters)
    - After execution, assert SearchExecutionLog record exists with matching user_id, company_id, query_text, filters, search_mode, include_internal, total_results matching response, execution_duration_ms > 0
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 2.1**

  - [x] 11.6 Write property test: Audit log immutability (Property 6)
    - **Property 6: Audit log immutability**
    - Use Hypothesis to generate existing SearchExecutionLog records, attempt UPDATE on any field or DELETE
    - Assert operation raises error and record remains unchanged
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 2.2**

  - [x] 11.7 Write property test: Saved search round-trip (Property 7)
    - **Property 7: Saved search round-trip**
    - Use Hypothesis to generate valid creation payloads (name 1–200 chars, query_text 1–1000 chars, valid filters, search_mode, include_internal)
    - Create then retrieve; assert name, query_text, filters, search_mode, include_internal exactly match input
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 3.1, 3.5**

  - [x] 11.8 Write property test: Saved search listing order (Property 8)
    - **Property 8: Saved search listing order**
    - Use Hypothesis to generate sets of saved searches with mixed last_executed_at values (some NULL)
    - Assert listing returns entries ordered by last_executed_at DESC with NULLs at end
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 3.2**

  - [x] 11.9 Write property test: Saved search execution updates metadata (Property 9)
    - **Property 9: Saved search execution updates metadata**
    - Use Hypothesis to generate saved search + random execution scenario
    - After execution, assert last_executed_at within 5 seconds of now and last_result_count == actual results returned
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 3.3, 3.6**

  - [x] 11.10 Write property test: Internalization metadata preservation (Property 10)
    - **Property 10: Internalization metadata preservation**
    - Use Hypothesis to generate IngestionRecord field values (title, authors, abstract, publication_date, doi, source_id)
    - After internalization, assert Document has matching title, document_type="literature", source_ingestion_record_id set, current_status="Draft"
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 4.1, 4.2**

  - [x] 11.11 Write property test: Duplicate internalization detection (Property 11)
    - **Property 11: Duplicate internalization detection**
    - Use Hypothesis to generate any IngestionRecord already internalized (Document with matching source_ingestion_record_id exists)
    - Assert second attempt returns HTTP 409 with existing Document ID
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 4.3**

  - [x] 11.12 Write property test: Citation collection document ordering (Property 12)
    - **Property 12: Citation collection document ordering**
    - Use Hypothesis to generate N documents added to a collection in sequence
    - Assert documents appear at positions after previously existing entries, retrieval returns ascending position order
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 5.3, 5.4**

  - [x] 11.13 Write property test: Collection removal preserves Document entity (Property 13)
    - **Property 13: Collection removal preserves Document entity**
    - Use Hypothesis to generate a document in a collection, remove it
    - Assert Document record still exists in documents table with all data intact; only junction record deleted
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 5.5**

  - [x] 11.14 Write property test: Only internalized documents in citation collections (Property 14)
    - **Property 14: Only internalized documents in citation collections**
    - Use Hypothesis to generate Documents without source_ingestion_record_id set
    - Assert adding to collection returns HTTP 422 and collection document list unchanged
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 5.9**

  - [x] 11.15 Write property test: Only internalized documents for traceability links (Property 15)
    - **Property 15: Only internalized documents for traceability links**
    - Use Hypothesis to generate Documents without source_ingestion_record_id
    - Assert creating traceability link returns HTTP 422 and no link created
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 6.5**

  - [x] 11.16 Write property test: Traceability link filtering correctness (Property 16)
    - **Property 16: Traceability link filtering correctness**
    - Use Hypothesis to generate sets of traceability links and filter queries (by document_id or target_id)
    - Assert returned results contain only links matching filter AND contain all matching links (completeness)
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 6.3**

  - [x] 11.17 Write property test: CSV export contains all required columns (Property 17)
    - **Property 17: CSV export contains all required columns**
    - Use Hypothesis to generate random result sets with varying field values (including nulls)
    - Assert CSV output contains columns: title, authors, publication_date, journal, source, publication_type, doi, abstract, relevance_score, provenance, mesh_terms; every row has a value for every column (empty string for null)
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 7.2**

  - [x] 11.18 Write property test: All mutations create audit events (Property 18)
    - **Property 18: All mutations create audit events**
    - Use Hypothesis to generate random mutation operations (internalization, collection modification, traceability link creation/deletion)
    - Assert corresponding audit event exists with correct user_id, company_id, action type, timestamp within 5 seconds
    - Location: `src/backend/tests/properties/test_literature_search_properties.py`
    - **Validates: Requirements 4.6, 5.11, 6.8**

- [x] 12. Write frontend property-based tests
  - [x] 12.1 Write frontend property test: Pagination component correctness (Property 2 frontend)
    - **Property 2 (frontend): Pagination renders correct page numbers**
    - Use fast-check to generate random (total_results, page, page_size) triples
    - Assert PaginationControls renders correct total_pages, disables prev on page 1, disables next on last page, shows correct "Showing X–Y of Z" text
    - Location: `src/frontend/src/__tests__/literatureSearch.property.test.ts`
    - **Validates: Requirements 9.5**

  - [x] 12.2 Write frontend property test: Whitespace query rejection (Property 4 frontend)
    - **Property 4 (frontend): Search input rejects whitespace-only strings**
    - Use fast-check to generate whitespace-only strings
    - Assert SearchInput component disables submit button for all such inputs
    - Location: `src/frontend/src/__tests__/literatureSearch.property.test.ts`
    - **Validates: Requirements 9.2**

- [x] 13. Write unit tests for backend services and router
  - [x] 13.1 Write unit tests for LiteratureSearchService
    - Test execute_search with valid params (mocked HybridQueryEngine returns results)
    - Test execute_search enriches is_internalized flag correctly
    - Test execute_search records SearchExecutionLog
    - Test execute_search handles OpenSearch unavailability (raises SearchUnavailableError → 503)
    - Test execute_search with whitespace-only query (raises 422)
    - Test internalize with valid IngestionRecord (creates Document, copies file)
    - Test internalize duplicate detection (returns 409 with existing doc ID)
    - Test internalize with wrong company (returns 404)
    - Test internalize with MinIO failure (Document created, full_text_status="unavailable")
    - Test create_saved_search success and limit enforcement (200 max)
    - Test list_saved_searches ordering (last_executed_at DESC, NULLs last)
    - Test execute_saved_search updates metadata
    - Test delete_saved_search (soft-delete, role check)
    - Test citation collection CRUD (create, list, get, update, archive)
    - Test add_documents_to_collection validates internalized-only, 500 limit
    - Test remove_document_from_collection preserves Document
    - Test create_traceability_links validates internalized doc, invokes TraceabilityMatrixService
    - Test list_traceability_links filtering
    - Test delete_traceability_link
    - Mock AsyncSession, HybridQueryEngine, AuditTrailService, TraceabilityMatrixService, storage_client
    - _Requirements: 1.1–1.10, 2.1–2.5, 3.1–3.8, 4.1–4.10, 5.1–5.11, 6.1–6.9_

  - [x] 13.2 Write unit tests for ExportService
    - Test generate_csv_export produces correct columns and semicolon-separated arrays
    - Test generate_pdf_export includes header, results table, metadata footer
    - Test generate_pdf_export with include_prisma_flow=True includes PRISMA section
    - Test validation: neither search_execution_id nor saved_search_id → 422
    - Test cross-company reference → 404
    - Test audit event recorded on export
    - Mock AsyncSession, ReportLab
    - _Requirements: 7.1–7.8_

  - [x] 13.3 Write unit tests for API router endpoints
    - Test all 17 endpoints with valid requests (correct status codes: 200, 201)
    - Test X-Change-Reason requirement on all POST/PUT/DELETE (400 if missing)
    - Test X-Company-Id requirement (400 if missing)
    - Test role-based access: member for reads, document_admin for mutations (403 on insufficient role)
    - Test cross-tenant access returns 404
    - Test saved search access control (owner vs other user vs admin)
    - Test error responses (409, 422, 503) match expected format
    - Use FastAPI TestClient with mocked dependencies
    - _Requirements: 8.1–8.6_

- [x] 14. Write integration tests
  - [x] 14.1 Write integration tests for search and audit pipeline
    - Test full search flow: execute query → verify SearchExecutionLog created with correct fields
    - Test audit service unavailability: search succeeds, audit retried via Celery task
    - Test saved search lifecycle: create → execute → verify metadata updated → archive
    - Test search with OpenSearch mock (keyword, semantic, hybrid modes)
    - Requires Docker PostgreSQL and Redis fixtures
    - _Requirements: 1.1–1.10, 2.1–2.5, 3.1–3.8_

  - [x] 14.2 Write integration tests for internalization and traceability
    - Test full internalization: IngestionRecord → Document creation → file copy (mocked MinIO) → traceability links → citation collection add
    - Test duplicate internalization detection (HTTP 409)
    - Test MinIO failure graceful handling (Document created, full_text_status="unavailable")
    - Test traceability link creation via mocked TraceabilityMatrixService
    - Test non-internalized document rejection (422 for collection add and traceability)
    - Requires Docker PostgreSQL and mocked MinIO
    - _Requirements: 4.1–4.10, 5.1–5.11, 6.1–6.9_

  - [x] 14.3 Write integration tests for export and multi-tenancy
    - Test CSV export generation with correct columns
    - Test PDF export with and without PRISMA flow
    - Test multi-tenant isolation: company A data invisible to company B
    - Test citation collection 500 document limit enforcement
    - Test saved search 200 limit per user per company
    - Requires Docker PostgreSQL
    - _Requirements: 7.1–7.8, 8.1–8.6_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (18 backend + 2 frontend)
- Unit tests validate specific examples and edge cases
- Integration tests require Docker infrastructure (PostgreSQL, Redis, mocked MinIO/OpenSearch)
- All backend commands use `cd src/backend && uv run pytest --tb=short -q`
- All frontend commands use `cd src/frontend && npx vitest run`
- Property tests use Hypothesis with `@settings(max_examples=100)` minimum
- Backend property test file: `src/backend/tests/properties/test_literature_search_properties.py`
- Frontend property test file: `src/frontend/src/__tests__/literatureSearch.property.test.ts`
- The design uses Python (backend) and TypeScript (frontend) — no language selection needed
- SearchExecutionLog table is immutable (append-only) per ALCOA+ compliance
- Saved searches and citation collections use soft-delete (status=archived) for regulatory evidence preservation
- All mutations require `X-Change-Reason` header (enforced by AuditMiddleware)
- All operations company-scoped via `X-Company-Id` header for multi-tenancy isolation
- Citation collections limited to 500 documents; saved searches limited to 200 per user per company

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "1.4"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["4.1", "5.1"] },
    { "id": 4, "tasks": ["4.2"] },
    { "id": 5, "tasks": ["7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["9.1", "9.2", "9.4"] },
    { "id": 8, "tasks": ["9.3", "9.5", "9.6", "9.7"] },
    { "id": 9, "tasks": ["9.8"] },
    { "id": 10, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.5", "11.6", "11.7", "11.8", "11.9", "11.10", "11.11", "11.12", "11.13", "11.14", "11.15", "11.16", "11.17", "11.18"] },
    { "id": 11, "tasks": ["12.1", "12.2"] },
    { "id": 12, "tasks": ["13.1", "13.2", "13.3"] },
    { "id": 13, "tasks": ["14.1", "14.2", "14.3"] }
  ]
}
```
