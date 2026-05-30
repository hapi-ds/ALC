# Implementation Plan: Audit Trail Viewer (Phase 6.3)

## Overview

This plan implements Phase 6.3 — Audit Trail Viewer for AlcoaBase. The implementation follows a bottom-up approach: database model and Alembic migration first, then core services (AuditTrailService, AuditPDFExporter, AuditAccessLogger), Celery tasks for async PDF export, the API router with all endpoints (including immutability enforcement), and finally the frontend (types, Zustand store, page/components). Each task builds incrementally on previous work, ensuring no orphaned code.

## Tasks

- [ ] 1. Database model, schemas, and migration
  - [ ] 1.1 Create SQLAlchemy model for audit_access_log
    - Create file `src/backend/src/alcoabase/models/audit_access_log.py`
    - Define `AuditAccessLog` model: id (int PK), user_id (FK users.id, indexed), company_id (FK companies.id, indexed), action (String, "view" | "export"), filters_applied (JSON, nullable), event_count (int, nullable), timestamp (DateTime TZ, server_default=func.now(), indexed)
    - Add composite index on (user_id, timestamp) for efficient access log queries
    - No SQLAlchemy-Continuum versioning (this table is itself an immutable audit log)
    - Register model in `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ] 1.2 Create Pydantic schemas for audit trail
    - Create file `src/backend/src/alcoabase/schemas/audit_trail.py`
    - Define `AuditTrailFilters` schema: user_id (int | None), date_start (datetime | None), date_end (datetime | None), record_type (str | None, validated against allowed types: documents, templates, reports, workflows, signatures, training_tasks, training_records), operation_type (Literal["INSERT", "UPDATE", "DELETE"] | None)
    - Define `AuditEvent` response schema: transaction_id (int), timestamp (datetime), user_id (int), user_display_name (str | None), record_type (str), record_id (int), operation_type (Literal["INSERT", "UPDATE", "DELETE"]), change_reason (str | None), changed_fields (list[str], max 10), total_changed_fields (int), company_id (int)
    - Define `FieldChange` schema: field_name (str), old_value (Any | None), new_value (Any | None)
    - Define `AuditEventDetail` response schema: transaction_id, timestamp, user_id, user_display_name, record_type, record_id, operation_type, change_reason, field_changes (list[FieldChange]), company_id
    - Define `AuditTrailPage` response schema: events (list[AuditEvent]), next_cursor (str | None), total_count (int), warnings (list[str] | None)
    - Define `ExportMetadata` schema: company_name (str), export_timestamp (datetime), filters_applied (AuditTrailFilters), total_event_count (int), requesting_user_name (str)
    - Define `ExportRequest` schema: filters (AuditTrailFilters | None), search_query (str | None)
    - Define `ExportStatusResponse` schema: job_id (str), status (Literal["pending", "processing", "completed", "failed"]), download_url (str | None), error_message (str | None)
    - Define `AuditTrailListParams` query schema: cursor (str | None), page_size (int, default=50, ge=1, le=200), search (str | None), plus all filter fields as query params
    - _Requirements: 1.3, 2.1, 2.2, 3.1–3.5, 5.1–5.3, 6.1–6.5, 7.1–7.3_

  - [ ] 1.3 Create Alembic migration for audit_access_log table
    - Generate migration with `alembic revision --autogenerate -m "add_audit_access_log_table"`
    - Upgrade: create `audit_access_log` table with all columns, indexes, and foreign key constraints
    - Add composite index on (user_id, timestamp)
    - Downgrade: drop `audit_access_log` table
    - _Requirements: 11.3_

  - [ ]* 1.4 Write unit tests for Pydantic schema validation
    - Test AuditTrailFilters: valid record_type values accepted, invalid rejected; valid operation_type Literal accepted, invalid rejected; date_start before date_end validation
    - Test AuditEvent serialization: changed_fields max 10 items, total_changed_fields reflects actual count
    - Test AuditTrailListParams: page_size clamped to [1, 200], cursor format validation
    - Test ExportRequest: empty filters allowed, search_query optional
    - Test FieldChange: old_value/new_value accept Any type (str, int, dict, list, None)
    - _Requirements: 1.3, 2.2, 3.1–3.4_

- [ ] 2. Core service: AuditAccessLogger
  - [ ] 2.1 Implement AuditAccessLogger service
    - Create file `src/backend/src/alcoabase/services/audit_access_logger.py`
    - Implement `log_access(session, user_id, company_id, action, filters_applied, event_count)`: create AuditAccessLog record with server-side timestamp, commit immediately (fire-and-forget pattern)
    - Action values: "view" for list/detail requests, "export" for PDF export requests
    - filters_applied stored as JSON dict of active filter parameters (None if no filters)
    - event_count populated only for export actions (number of events exported)
    - No update or delete methods — table is append-only
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ]* 2.2 Write unit tests for AuditAccessLogger
    - Test log_access creates record with correct user_id, company_id, action, timestamp
    - Test log_access with filters_applied as dict and as None
    - Test log_access with event_count for export actions
    - Test that no update/delete methods exist on the service
    - _Requirements: 11.1, 11.2, 11.3_

- [ ] 3. Core service: AuditTrailService
  - [ ] 3.1 Implement AuditTrailService
    - Create file `src/backend/src/alcoabase/services/audit_trail_service.py`
    - Define `AUDITED_RECORD_TYPES` mapping: {"documents": DocumentVersion, "templates": TemplateVersion, "reports": ReportVersion, "workflows": WorkflowVersion, "signatures": SignatureVersion, "training_tasks": TrainingTaskVersion, "training_records": TrainingRecordVersion}
    - Implement `list_events(session, company_id, filters, search_query, cursor, page_size, cross_company)`:
      - Query each version table individually with applied filters (user_id, date_range, record_type, operation_type)
      - JOIN to transaction table for timestamp and user metadata
      - Apply company_id scoping (skip if cross_company=True and user is system_admin)
      - Apply search query as ILIKE substring match against change_reason, record_type, user display_name, and cast record_id to string
      - Merge results in-memory, sort by timestamp descending
      - Apply cursor-based pagination using composite cursor (timestamp, transaction_id, record_type)
      - Resolve user_display_name from users table (fallback to None if user not found)
      - Truncate changed_fields to max 10, set total_changed_fields to actual count
      - Return AuditTrailPage with events, next_cursor, total_count, and warnings for failed tables
    - Implement graceful degradation: wrap each version table query in try/except, collect warnings for failed tables, continue with remaining
    - Implement `get_event_detail(session, company_id, record_type, record_id, transaction_id)`:
      - Query specific version table for the exact version entry
      - Compute field_changes by comparing with previous version (or None for INSERT)
      - For UPDATE: return list of FieldChange with old_value and new_value for each changed field
      - For INSERT: return all fields with old_value=None
      - For DELETE: return all fields with new_value=None
      - Resolve user_display_name
    - Implement `get_total_count(session, company_id, filters, search_query)`:
      - Execute COUNT queries against each version table with same filters
      - Sum results across all accessible tables
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3, 6.1–6.5_

  - [ ]* 3.2 Write property test for aggregation completeness and ordering
    - **Property 1: Aggregation completeness and ordering**
    - Generate random sets of audit events distributed across multiple version tables with varying timestamps; verify aggregation returns every event exactly once, ordered by timestamp descending
    - Use Hypothesis strategies to generate events with random timestamps, record types, and transaction IDs
    - **Validates: Requirements 1.1, 1.2**

  - [ ]* 3.3 Write property test for event serialization field truncation
    - **Property 2: Event serialization includes required fields with truncation**
    - Generate version table entries with N changed fields (0 ≤ N ≤ 50); verify serialized AuditEvent includes all required fields and changed_fields contains at most 10 items with total_changed_fields reflecting actual count
    - **Validates: Requirements 1.3**

  - [ ]* 3.4 Write property test for user identity resolution
    - **Property 3: User identity resolution with fallback**
    - Generate audit events with user_ids that exist and don't exist in users table; verify user_display_name is display name when user exists, None when user unavailable, and user_id is always the numeric identifier
    - **Validates: Requirements 1.4**

  - [ ]* 3.5 Write property test for transaction grouping
    - **Property 4: Transaction grouping**
    - Generate sets of events where multiple events share the same transaction_id; verify those events are presented with transaction_id as correlation identifier
    - **Validates: Requirements 1.5**

  - [ ]* 3.6 Write property test for graceful degradation
    - **Property 5: Graceful degradation on partial failure**
    - Generate subsets of version tables that fail during aggregation; verify service returns events from all non-failing tables and includes a warning listing exactly the failed record types
    - **Validates: Requirements 1.6**

  - [ ]* 3.7 Write property test for pagination completeness
    - **Property 6: Pagination completeness with page size clamping**
    - Generate datasets of audit events and sequences of cursor-based page requests with page_size in [1, 200]; verify iterating through all pages yields every matching event exactly once with no duplicates and no gaps
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 3.8 Write property test for total count accuracy
    - **Property 7: Total count accuracy**
    - Generate combinations of filters and search queries applied to a dataset; verify total_count equals the number of events satisfying all applied criteria
    - **Validates: Requirements 2.3**

  - [ ]* 3.9 Write property test for filter correctness
    - **Property 8: Filter correctness**
    - Generate single filters (user_id, date_range, record_type, operation_type) applied to a dataset; verify every event in response satisfies the filter and no satisfying event is excluded
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [ ]* 3.10 Write property test for filter AND-combination with search
    - **Property 9: Filter AND-combination with search**
    - Generate combinations of multiple filters and search query; verify result set equals the intersection of applying each filter and search individually
    - **Validates: Requirements 3.5, 5.3**

  - [ ]* 3.11 Write property test for tenant scoping
    - **Property 10: Tenant scoping**
    - Generate audit events belonging to multiple companies; verify query scoped to company_id returns only events from that company and no events from other companies
    - **Validates: Requirements 4.1**

  - [ ]* 3.12 Write property test for substring search completeness
    - **Property 11: Substring search completeness**
    - Generate audit events and substrings of their searchable fields (change_reason, record_type, user_display_name, record_id as string); verify searching for that substring includes the event in results
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 3.13 Write unit tests for AuditTrailService
    - Test list_events returns events ordered by timestamp descending
    - Test list_events with each filter type individually (user_id, date_range, record_type, operation_type)
    - Test list_events with combined filters (AND logic)
    - Test list_events with search query (substring matching)
    - Test list_events cursor-based pagination (next page, no duplicates)
    - Test list_events company_id scoping (multi-tenant isolation)
    - Test list_events cross_company=True for system_admin
    - Test list_events graceful degradation when a version table query fails
    - Test list_events with no Change_Reason (returns null, event not omitted)
    - Test get_event_detail for INSERT (all fields, no old_value)
    - Test get_event_detail for UPDATE (changed fields with old/new values)
    - Test get_event_detail for DELETE (final values, no new_value)
    - Test get_event_detail user_display_name resolution and fallback
    - Test get_total_count accuracy with filters
    - Test page_size clamping to [1, 200]
    - _Requirements: 1.1–1.7, 2.1–2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3, 6.1–6.5_

- [ ] 4. Core service: AuditPDFExporter
  - [ ] 4.1 Implement AuditPDFExporter service
    - Create file `src/backend/src/alcoabase/services/audit_pdf_exporter.py`
    - Implement `generate_pdf(events, metadata) -> bytes`:
      - Use ReportLab with A4 page size, portrait orientation
      - Use fixed-width font (Courier) for tabular data
      - Create table-based layout with visible row separators
      - Repeat column headers on each page
      - PDF header: company name, export date/time (UTC), applied filters summary, total event count, requesting user identity
      - Each event row: sequential number, timestamp, user identity, record type, record ID, operation_type, change_reason (truncated to 500 chars with "..." if exceeds)
      - Footer on each page: page number, total pages, generation timestamp
      - Return PDF as bytes
    - Implement `export_sync(session, company_id, filters, search_query, requesting_user_id) -> bytes`:
      - Fetch all matching events via AuditTrailService
      - If event count is 0, raise ValueError("No events match the current filters")
      - Build ExportMetadata from company info and user info
      - Call generate_pdf and return bytes
    - Implement `export_async(session, company_id, filters, search_query, requesting_user_id) -> str`:
      - Generate job_id (UUID)
      - Dispatch Celery task with job_id, company_id, filters, search_query, requesting_user_id
      - Return job_id
    - Implement `get_export_status(job_id) -> ExportStatusResponse`:
      - Check Celery task state and return status with download_url if completed
    - _Requirements: 7.1–7.10_

  - [ ]* 4.2 Write property test for PDF content consistency
    - **Property 12: PDF content consistency with API**
    - Generate sets of filter criteria and audit events; verify the events included in the generated PDF are exactly the same set that the list API would return for those criteria
    - **Validates: Requirements 7.1**

  - [ ]* 4.3 Write property test for PDF header metadata completeness
    - **Property 13: PDF header metadata completeness**
    - Generate export requests with varying metadata; verify generated PDF header contains: company name, export timestamp (UTC), all applied filters, total event count, and requesting user identity
    - **Validates: Requirements 7.2**

  - [ ]* 4.4 Write property test for PDF event formatting with truncation
    - **Property 14: PDF event formatting with truncation**
    - Generate audit events with change_reason of varying lengths (0 to 1000+ chars); verify PDF entry includes sequential number, timestamp, user identity, record type, record ID, operation_type; if change_reason length > 500, verify truncation to 500 chars followed by ellipsis
    - **Validates: Requirements 7.3**

  - [ ]* 4.5 Write unit tests for AuditPDFExporter
    - Test generate_pdf produces valid PDF bytes (parseable by PyMuPDF)
    - Test PDF uses A4 page size, portrait orientation
    - Test PDF uses fixed-width font for tabular data
    - Test column headers repeated on each page (multi-page document)
    - Test footer contains page number, total pages, generation timestamp
    - Test header contains company name, export timestamp, filters, event count, user
    - Test change_reason truncation at 500 chars with ellipsis
    - Test export_sync raises ValueError when zero events match
    - Test export_async dispatches Celery task and returns job_id
    - Test get_export_status returns correct status for pending/completed/failed jobs
    - _Requirements: 7.1–7.10_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Celery task for async PDF export
  - [ ] 6.1 Implement Celery task for PDF export
    - Create file `src/backend/src/alcoabase/tasks/audit_export_tasks.py`
    - Implement `export_audit_pdf_task(self, job_id, company_id, filters, search_query, requesting_user_id)`:
      - Decorated with `@celery_app.task(bind=True, soft_time_limit=300, max_retries=0, queue="default", name="alcoabase.tasks.audit_export_tasks.export_audit_pdf_task")`
      - Create async DB session, instantiate AuditTrailService and AuditPDFExporter
      - Fetch all matching events (iterate through all pages)
      - Generate PDF via AuditPDFExporter.generate_pdf
      - Upload PDF to MinIO under `exports/audit-trail/{job_id}.pdf` with 72-hour expiry
      - Log export event via AuditAccessLogger (action="export", event_count=total)
      - On success: return {"status": "completed", "download_url": presigned_url}
      - On SoftTimeLimitExceeded: return {"status": "failed", "error_message": "Export timed out after 300 seconds"}
      - On any other exception: return {"status": "failed", "error_message": str(error)}; ensure no partial PDF is stored
    - _Requirements: 7.5, 7.9, 7.10_

  - [ ]* 6.2 Write unit tests for Celery export task
    - Test successful export: events fetched, PDF generated, uploaded to MinIO, access logged
    - Test timeout handling: SoftTimeLimitExceeded caught, status set to "failed"
    - Test error handling: exception caught, no partial PDF stored, error message returned
    - Test MinIO upload with 72-hour expiry
    - Test presigned URL generation for download
    - _Requirements: 7.5, 7.9, 7.10_

- [ ] 7. API router: audit trail endpoints
  - [ ] 7.1 Implement audit trail API router (list and detail endpoints)
    - Create file `src/backend/src/alcoabase/api/audit_trail.py`
    - Define router with prefix `/audit-trail`
    - Implement GET `/` → list/filter/search audit events (paginated):
      - Query params: cursor, page_size (default 50, max 200), search, user_id, date_start, date_end, record_type, operation_type
      - Depends: require_permission("audit_logs", "read"), tenant resolution via X-Company-Id
      - Call AuditTrailService.list_events with parsed filters
      - Call AuditAccessLogger.log_access(action="view", filters_applied=active_filters)
      - Return AuditTrailPage response
    - Implement GET `/{record_type}/{record_id}/{transaction_id}` → get full event detail:
      - Depends: require_permission("audit_logs", "read"), tenant resolution
      - Call AuditTrailService.get_event_detail
      - Return AuditEventDetail response
      - Return 404 if event not found
    - _Requirements: 1.1–1.7, 2.1–2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3, 6.1–6.5, 9.1–9.4, 11.1_

  - [ ] 7.2 Implement export endpoints
    - Add to `src/backend/src/alcoabase/api/audit_trail.py`
    - Implement POST `/export` → trigger PDF export:
      - Body: ExportRequest (filters, search_query)
      - Depends: require_permission("audit_logs", "read"), tenant resolution
      - If total matching events == 0: return HTTP 400 with message "No events match the current filters for export"
      - If total matching events ≤ 10,000: generate PDF synchronously, return PDF bytes as file response
      - If total matching events > 10,000: dispatch async Celery task, return ExportStatusResponse with job_id and status="pending"
      - Log export via AuditAccessLogger
    - Implement GET `/export/{job_id}` → check export status / download:
      - Depends: require_permission("audit_logs", "read")
      - Return ExportStatusResponse with status and download_url if completed
      - Return 404 if job_id not found
    - _Requirements: 7.1–7.10, 11.2_

  - [ ] 7.3 Implement immutability enforcement
    - Add to `src/backend/src/alcoabase/api/audit_trail.py`
    - Implement PUT, PATCH, DELETE handlers for `/audit-trail` and `/audit-trail/{path:path}`:
      - Return HTTP 403 with body: {"detail": "Audit records are immutable per ALCOA+ and CFR 21 Part 11"}
      - Enforce regardless of requesting user's role or permissions
    - _Requirements: 8.1, 8.2, 8.4_

  - [ ] 7.4 Implement cross-company query support for system_admin
    - Add to GET `/` endpoint in `src/backend/src/alcoabase/api/audit_trail.py`
    - Add optional query param `cross_company: bool = False`
    - If cross_company=True: verify user has system_admin role, pass cross_company=True to AuditTrailService
    - If cross_company=True and user is NOT system_admin: return HTTP 403
    - If no X-Company-Id header and cross_company is False: return HTTP 400
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 7.5 Register audit_trail router in central router
    - Add import and `include_router` call in `src/backend/src/alcoabase/api/router.py` for audit_trail router with prefix `/audit-trail`
    - _Requirements: 9.1_

  - [ ]* 7.6 Write property test for immutability enforcement
    - **Property 15: Immutability enforcement**
    - Generate HTTP requests using PUT, PATCH, and DELETE methods against any audit trail endpoint path, with users of varying roles (including system_admin); verify all return HTTP 403 with message "Audit records are immutable per ALCOA+ and CFR 21 Part 11"
    - **Validates: Requirements 8.1, 8.2, 8.4**

  - [ ]* 7.7 Write property test for access logging completeness
    - **Property 16: Access logging completeness**
    - Generate audit trail interactions (view and export); verify each creates an entry in audit_access_log containing user_id, timestamp, action type, and applied filters
    - **Validates: Requirements 11.1, 11.2**

  - [ ]* 7.8 Write unit tests for audit trail API router
    - Test GET / returns paginated events with correct structure
    - Test GET / with each filter type (user_id, date_range, record_type, operation_type)
    - Test GET / with search query
    - Test GET / with cursor pagination
    - Test GET / without X-Company-Id returns 400
    - Test GET / with unauthorized role returns 403
    - Test GET /{record_type}/{record_id}/{transaction_id} returns event detail
    - Test GET /{record_type}/{record_id}/{transaction_id} returns 404 for non-existent event
    - Test POST /export with zero events returns 400
    - Test POST /export with ≤10,000 events returns PDF synchronously
    - Test POST /export with >10,000 events returns job_id (async)
    - Test GET /export/{job_id} returns status
    - Test PUT /audit-trail returns 403 with immutability message
    - Test PATCH /audit-trail returns 403 with immutability message
    - Test DELETE /audit-trail returns 403 with immutability message
    - Test cross_company=True with system_admin succeeds
    - Test cross_company=True with non-system_admin returns 403
    - Test access logging occurs on each request
    - _Requirements: 1.1–1.7, 2.1–2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3, 6.1–6.5, 7.1–7.10, 8.1–8.4, 9.1–9.4, 11.1–11.2_

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Frontend: TypeScript types and Zustand store
  - [ ] 9.1 Create TypeScript types for audit trail
    - Create file `src/frontend/src/types/auditTrail.ts`
    - Define `AuditEvent` interface: transaction_id (number), timestamp (string), user_id (number), user_display_name (string | null), record_type (string), record_id (number), operation_type ("INSERT" | "UPDATE" | "DELETE"), change_reason (string | null), changed_fields (string[]), total_changed_fields (number), company_id (number)
    - Define `AuditTrailFilters` interface: user_id? (number), date_start? (string), date_end? (string), record_type? (string), operation_type? ("INSERT" | "UPDATE" | "DELETE")
    - Define `AuditTrailPage` interface: events (AuditEvent[]), next_cursor (string | null), total_count (number), warnings? (string[])
    - Define `FieldChange` interface: field_name (string), old_value (unknown), new_value (unknown)
    - Define `AuditEventDetail` interface: transaction_id, timestamp, user_id, user_display_name, record_type, record_id, operation_type, change_reason, field_changes (FieldChange[]), company_id
    - Define `ExportStatus` interface: job_id (string), status ("pending" | "processing" | "completed" | "failed"), download_url? (string), error_message? (string)
    - Define `SortConfig` interface: column (string), direction ("asc" | "desc")
    - _Requirements: 1.3, 2.1, 2.4, 3.6, 5.4, 6.1–6.5, 7.7, 10.1–10.6_

  - [ ] 9.2 Create Zustand store for audit trail
    - Create file `src/frontend/src/stores/useAuditTrailStore.ts`
    - Implement state: events (AuditEvent[]), filters (AuditTrailFilters), searchQuery (string), cursor (string | null), totalCount (number), isLoading (boolean), selectedEvent (AuditEventDetail | null), exportStatus (ExportStatus | null), sort (SortConfig), warnings (string[])
    - Implement actions:
      - `fetchEvents()`: GET /api/audit-trail with current filters, search, cursor, page_size; update events and totalCount
      - `fetchNextPage()`: GET /api/audit-trail with next_cursor; append events
      - `fetchEventDetail(record_type, record_id, transaction_id)`: GET /api/audit-trail/{record_type}/{record_id}/{transaction_id}; set selectedEvent
      - `setFilters(filters)`: update filters, reset cursor, refetch events
      - `setSearchQuery(query)`: update searchQuery, reset cursor, refetch events
      - `setSort(sort)`: update sort config, refetch events
      - `triggerExport()`: POST /api/audit-trail/export with current filters and search; handle sync (download PDF) and async (set exportStatus) responses
      - `checkExportStatus(job_id)`: GET /api/audit-trail/export/{job_id}; update exportStatus
      - `clearSelectedEvent()`: set selectedEvent to null
      - `resetFilters()`: clear all filters and search, refetch
    - _Requirements: 2.4, 3.6, 5.4, 7.7, 10.1–10.6_

- [ ] 10. Frontend: Audit Trail Viewer page and components
  - [ ] 10.1 Implement AuditTrailFilters component
    - Create file `src/frontend/src/components/AuditTrailFilters.tsx`
    - User selection dropdown (searchable, fetches from /api/users)
    - Date range picker (start date, end date) using shadcn/ui DatePicker
    - Record type dropdown: documents, templates, reports, workflows, signatures, training_tasks, training_records
    - Operation type dropdown: INSERT, UPDATE, DELETE
    - Search input field with submit-on-enter behavior
    - "Clear filters" button to reset all filters
    - All filter changes call store.setFilters() or store.setSearchQuery()
    - Use shadcn/ui Select, Input, Button, Popover components
    - _Requirements: 3.6, 5.4, 10.6_

  - [ ] 10.2 Implement AuditTrailTable component
    - Create file `src/frontend/src/components/AuditTrailTable.tsx`
    - shadcn/ui DataTable with columns: timestamp, user (display_name or user_id fallback), record type, record ID, operation, change reason
    - Sortable columns: timestamp, user, record type, operation type (click header to toggle sort)
    - Row click opens AuditEventDetailPanel
    - Operation type badges: INSERT (green), UPDATE (blue), DELETE (red)
    - Change reason column: truncate long text with tooltip on hover
    - Changed fields shown as comma-separated list (max 10, "+N more" indicator)
    - Transaction ID shown as subtle correlation badge when multiple events share same ID
    - Loading state: skeleton rows while fetching
    - Empty state: "No audit events match the current filters" message
    - Pagination controls at bottom: "Load more" button or page navigation using cursor
    - Display total count: "Showing X of Y events"
    - _Requirements: 2.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ] 10.3 Implement AuditEventDetailPanel component
    - Create file `src/frontend/src/components/AuditEventDetailPanel.tsx`
    - Slide-over panel (shadcn/ui Sheet) triggered by row click in table
    - Display full event metadata: timestamp, user, record type, record ID, operation, change reason (full text)
    - Display field_changes as a table:
      - For UPDATE: two columns (Previous Value, New Value) with changed fields highlighted
      - For INSERT: single column (Initial Value) for all fields
      - For DELETE: single column (Final Value) for all fields
    - JSON values formatted with syntax highlighting (for complex field values)
    - Close button and click-outside-to-close behavior
    - Loading state while fetching detail
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 10.4 Implement AuditExportButton component
    - Create file `src/frontend/src/components/AuditExportButton.tsx`
    - "Export to PDF" button using shadcn/ui Button
    - On click: call store.triggerExport()
    - Sync response (≤10k events): trigger browser download of PDF file
    - Async response (>10k events): show toast notification "Export started, you'll be notified when ready"
    - Poll export status every 5 seconds when async export is pending
    - When completed: show toast with download link
    - When failed: show error toast with message
    - Disabled state when no events match current filters (totalCount === 0)
    - Show tooltip "No events to export" when disabled
    - _Requirements: 7.7, 7.8, 7.9_

  - [ ] 10.5 Implement AuditTrailPage
    - Create file `src/frontend/src/pages/AuditTrailPage.tsx`
    - Route: `/admin/audit-trail`
    - Page layout: header with title "Audit Trail", filter bar, data table, export button
    - Compose AuditTrailFilters, AuditTrailTable, AuditEventDetailPanel, AuditExportButton
    - On mount: call store.fetchEvents() to load initial data
    - Frontend route guard: verify user holds system_admin, doc_admin, or it_admin role; redirect to /unauthorized if not
    - Page title and breadcrumb consistent with existing admin pages
    - _Requirements: 9.3, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ] 10.6 Register route and add navigation link
    - Add route `/admin/audit-trail` to the React Router configuration with AuditTrailPage component
    - Add route guard checking for system_admin, doc_admin, or it_admin roles
    - Add "Audit Trail" navigation link in the admin sidebar/menu (consistent with existing admin nav items)
    - _Requirements: 9.3, 10.1_

- [ ] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Frontend tests
  - [ ]* 12.1 Write property-based tests for frontend (fast-check)
    - Create file `src/frontend/src/__tests__/audit-trail.property.test.ts`
    - Property test: filter state management — generate random filter combinations, verify store state correctly reflects applied filters after setFilters()
    - Property test: event formatting/truncation — generate events with change_reason of varying lengths, verify display truncation logic is consistent
    - Property test: pagination cursor handling — generate sequences of page fetches, verify no duplicate events appear in accumulated results
    - Property test: changed_fields display — generate events with 0-50 changed fields, verify display shows max 10 with "+N more" indicator when total > 10
    - Use fast-check with `{ numRuns: 100 }` configuration
    - _Requirements: 1.3, 2.4, 3.6, 10.2_

  - [ ]* 12.2 Write unit tests for frontend components (Vitest + Testing Library)
    - Create file `src/frontend/src/__tests__/audit-trail.test.tsx`
    - Test AuditTrailTable renders columns correctly with mock data
    - Test AuditTrailTable loading state shows skeleton rows
    - Test AuditTrailTable empty state shows "no results" message
    - Test AuditTrailTable column sorting interaction (click header toggles sort)
    - Test AuditTrailTable row click opens detail panel
    - Test AuditTrailFilters renders all filter controls
    - Test AuditTrailFilters filter change triggers store update
    - Test AuditTrailFilters clear button resets all filters
    - Test AuditEventDetailPanel displays field changes for UPDATE (old/new values)
    - Test AuditEventDetailPanel displays initial values for INSERT
    - Test AuditEventDetailPanel displays final values for DELETE
    - Test AuditExportButton disabled when totalCount is 0
    - Test AuditExportButton triggers export on click
    - Test AuditExportButton shows async status feedback
    - Test AuditTrailPage route guard redirects unauthorized users
    - Test AuditTrailPage fetches events on mount
    - _Requirements: 2.4, 3.6, 5.4, 6.1–6.5, 7.7, 7.8, 9.3, 10.1–10.6_

- [ ] 13. Integration tests
  - [ ]* 13.1 Write backend integration tests
    - Create file `src/backend/tests/integration/test_audit_trail_integration.py`
    - Test full request flow: API → AuditTrailService → Version Tables → Response (with seeded test data)
    - Test multi-tenant isolation: create events for two companies, verify each company only sees their own events
    - Test PDF generation end-to-end: seed events, trigger export, verify PDF is valid and contains correct events
    - Test Celery task dispatch for large exports (mock >10k event count threshold)
    - Test access log creation: verify audit_access_log entry created on each API request
    - Test immutability enforcement end-to-end: PUT/PATCH/DELETE all return 403
    - Test RBAC enforcement: unauthorized roles get 403, authorized roles (system_admin, doc_admin, it_admin) get 200
    - Test cursor pagination end-to-end: iterate all pages, verify complete dataset with no gaps or duplicates
    - Test search + filter combination: verify AND logic across multiple criteria
    - Test event detail for each operation type (INSERT, UPDATE, DELETE)
    - _Requirements: 1.1–1.7, 2.1–2.3, 3.1–3.5, 4.1–4.3, 5.1–5.3, 6.1–6.5, 7.1–7.10, 8.1–8.4, 9.1–9.4, 11.1–11.3_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (16 properties)
- Unit tests validate specific examples and edge cases
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + Testing Library + fast-check
- All backend services use async SQLAlchemy sessions (asyncpg)
- The audit_trail router uses `Depends(require_permission("audit_logs", "read"))` for RBAC enforcement
- AuditMiddleware does NOT apply X-Change-Reason enforcement to audit trail endpoints since they are read-only (POST /export is the only mutation-like endpoint but it creates exports, not audit records)
- The audit_access_log table is append-only with no UPDATE/DELETE operations — immutability enforced at API layer
- SQLAlchemy-Continuum version tables are queried directly (no materialized view) to avoid maintenance overhead
- Cursor-based pagination uses composite cursor (timestamp, transaction_id, record_type) for stable ordering across millions of rows
- PDF exports ≤10,000 events are synchronous; >10,000 events dispatch to Celery with 300s timeout
- Generated PDFs are stored in MinIO under `exports/audit-trail/` with 72-hour retention
- The AuditTrailService resolves user_display_name via JOIN to users table with graceful fallback to None
- Frontend uses shadcn/ui components consistent with existing AlcoaBase admin interface
- The Zustand store manages all audit trail state including filters, pagination, and export status
- Route guard at `/admin/audit-trail` checks for system_admin, doc_admin, or it_admin roles

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 3, "tasks": ["2.2", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "4.2", "4.3", "4.4", "4.5"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["6.2"] },
    { "id": 6, "tasks": ["7.1", "7.2", "7.3", "7.4"] },
    { "id": 7, "tasks": ["7.5", "7.6", "7.7", "7.8"] },
    { "id": 8, "tasks": ["9.1"] },
    { "id": 9, "tasks": ["9.2"] },
    { "id": 10, "tasks": ["10.1", "10.2", "10.3", "10.4"] },
    { "id": 11, "tasks": ["10.5", "10.6"] },
    { "id": 12, "tasks": ["12.1", "12.2"] },
    { "id": 13, "tasks": ["13.1"] }
  ]
}
```
