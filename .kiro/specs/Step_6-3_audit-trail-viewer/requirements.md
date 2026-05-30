# Requirements Document

## Introduction

This document specifies the requirements for the Audit Trail Viewer (Phase 6.3) of AlcoaBase. The feature provides a centralized, searchable, and filterable audit log UI that aggregates all audit events across the system. It answers the regulatory questions: who did what, when, and why. The viewer supports export to PDF for FDA/EMA regulatory submissions and enforces complete immutability of audit records per ALCOA+ and 21 CFR Part 11 requirements.

The Audit Trail Viewer builds on the existing SQLAlchemy-Continuum version tables, AuditMiddleware (X-Change-Reason enforcement), and the per-record AuditService. It extends these foundations into a cross-record, cross-type aggregated view accessible to authorized administrators.

## Glossary

- **Audit_Trail_Service**: The backend service responsible for querying, filtering, and aggregating audit events across all record types and version tables into a unified chronological view.
- **Audit_Trail_Viewer**: The frontend page at `/admin/audit-trail` that displays the centralized audit log with search, filter, and export capabilities.
- **Audit_Event**: A single immutable record representing one change operation, containing: user identity, timestamp, record type, record ID, operation type, change reason, and column-level change details.
- **Audit_PDF_Exporter**: The backend service that generates regulatory-compliant PDF documents from filtered audit trail data using ReportLab.
- **Version_Table**: A SQLAlchemy-Continuum-managed table that stores column snapshots for every INSERT, UPDATE, and DELETE operation on an audited model.
- **Operation_Type**: The classification of a change: INSERT (record creation), UPDATE (record modification), or DELETE (record removal).
- **Change_Reason**: The human-readable justification for a mutation, captured from the X-Change-Reason HTTP header by the AuditMiddleware.
- **Transaction_ID**: A monotonically increasing identifier assigned by SQLAlchemy-Continuum that groups all changes made within a single HTTP request.
- **Authorized_Role**: One of system_admin, doc_admin, or it_admin — the roles permitted read-only access to the audit trail.

## Requirements

### Requirement 1: Centralized Audit Event Aggregation

**User Story:** As a system administrator, I want a unified view of all audit events across all record types, so that I can monitor system-wide activity without navigating to individual records.

#### Acceptance Criteria

1. THE Audit_Trail_Service SHALL aggregate audit events from all Version_Tables (documents, templates, reports, workflows, signatures, training_tasks, training_records) into a unified chronological response.
2. WHEN the Audit_Trail_Viewer requests audit events, THE Audit_Trail_Service SHALL return events ordered by timestamp descending (most recent first) within 2 seconds for a single page of results.
3. THE Audit_Trail_Service SHALL include for each Audit_Event: user identity, server-side UTC timestamp, record type, record ID, Operation_Type, Change_Reason, and a list of changed field names (maximum 10 field names displayed, with a count indicator if more fields were modified).
4. THE Audit_Trail_Service SHALL resolve user identity to display name where available, falling back to user ID when the user record is unavailable.
5. WHEN multiple changes occur within a single Transaction_ID, THE Audit_Trail_Service SHALL group related changes and present the Transaction_ID as a correlation identifier.
6. IF a Version_Table query fails during aggregation, THEN THE Audit_Trail_Service SHALL return results from the remaining accessible Version_Tables and include a warning indicating which record types could not be retrieved.
7. IF an Audit_Event has no Change_Reason recorded, THEN THE Audit_Trail_Service SHALL return the Change_Reason field as null without omitting the event from results.

### Requirement 2: Paginated Audit Event Retrieval

**User Story:** As an administrator, I want the audit trail to load efficiently even with millions of entries, so that I can browse the log without performance degradation.

#### Acceptance Criteria

1. THE Audit_Trail_Service SHALL support cursor-based pagination for audit event retrieval.
2. WHEN a page of audit events is requested, THE Audit_Trail_Service SHALL return a configurable page size (default 50, maximum 200) along with a cursor for the next page.
3. THE Audit_Trail_Service SHALL return the total count of matching events for the current filter criteria.
4. THE Audit_Trail_Viewer SHALL display pagination controls allowing navigation between pages of results.

### Requirement 3: Filtering by User, Date Range, Record Type, and Operation Type

**User Story:** As an auditor, I want to filter audit events by specific criteria, so that I can narrow down the trail to relevant activity during an investigation.

#### Acceptance Criteria

1. WHEN a user filter is applied, THE Audit_Trail_Service SHALL return only Audit_Events attributed to the specified user.
2. WHEN a date range filter is applied, THE Audit_Trail_Service SHALL return only Audit_Events with timestamps within the specified start and end dates (inclusive).
3. WHEN a record type filter is applied, THE Audit_Trail_Service SHALL return only Audit_Events from the specified record type (documents, templates, reports, workflows, signatures, training_tasks, training_records).
4. WHEN an operation type filter is applied, THE Audit_Trail_Service SHALL return only Audit_Events matching the specified Operation_Type (INSERT, UPDATE, or DELETE).
5. WHEN multiple filters are applied simultaneously, THE Audit_Trail_Service SHALL combine all filters using logical AND.
6. THE Audit_Trail_Viewer SHALL provide filter controls for user selection, date range picker, record type dropdown, and operation type dropdown.

### Requirement 4: Multi-Tenant Scoping

**User Story:** As an administrator of a specific company, I want the audit trail to show only events from my company, so that tenant isolation is maintained.

#### Acceptance Criteria

1. THE Audit_Trail_Service SHALL scope all audit event queries to the company identified by the X-Company-Id header.
2. WHEN a system_admin queries the audit trail, THE Audit_Trail_Service SHALL allow an optional parameter to view events across all companies.
3. THE Audit_Trail_Service SHALL reject requests without a valid X-Company-Id header with HTTP 400.

### Requirement 5: Full-Text Search

**User Story:** As an auditor, I want to search across change reasons and record metadata, so that I can find specific audit events by keyword.

#### Acceptance Criteria

1. WHEN a search query is submitted, THE Audit_Trail_Service SHALL match against Change_Reason text, record type, user display name, and record identifiers.
2. THE Audit_Trail_Service SHALL support partial matching (substring search) for the search query.
3. WHEN a search query is combined with filters, THE Audit_Trail_Service SHALL apply the search within the filtered result set.
4. THE Audit_Trail_Viewer SHALL provide a search input field that triggers search on submission.

### Requirement 6: Audit Event Detail View

**User Story:** As an auditor, I want to drill into a specific audit event to see the full column-level changes, so that I can understand exactly what was modified.

#### Acceptance Criteria

1. WHEN an Audit_Event is selected in the Audit_Trail_Viewer, THE Audit_Trail_Viewer SHALL display the complete column-level change details showing previous and new values for each modified field.
2. THE Audit_Trail_Service SHALL provide a detail endpoint that returns the full Version_Table snapshot for a specific Audit_Event.
3. WHEN the Operation_Type is INSERT, THE Audit_Trail_Viewer SHALL display all initial field values without a previous-value comparison.
4. WHEN the Operation_Type is UPDATE, THE Audit_Trail_Viewer SHALL highlight fields that changed between the previous version and the current version.
5. WHEN the Operation_Type is DELETE, THE Audit_Trail_Viewer SHALL display the final field values before deletion.

### Requirement 7: PDF Export for Regulatory Submissions

**User Story:** As a quality manager, I want to export filtered audit trail data to PDF, so that I can include it in FDA/EMA regulatory submission packages.

#### Acceptance Criteria

1. WHEN an export is requested, THE Audit_PDF_Exporter SHALL generate a PDF document containing all audit events matching the current filter and search criteria.
2. THE Audit_PDF_Exporter SHALL include in the PDF header: company name, export date and time (UTC), applied filters, total event count, and the identity of the user who requested the export.
3. THE Audit_PDF_Exporter SHALL format each Audit_Event in the PDF with: sequential number, timestamp, user identity, record type, record ID, Operation_Type, and Change_Reason truncated to 500 characters with an ellipsis indicator if the original text exceeds that length.
4. THE Audit_PDF_Exporter SHALL generate the PDF using ReportLab with A4 page size, portrait orientation, a fixed-width font for tabular data, and a table-based layout with visible row separators and column headers repeated on each page.
5. WHEN the filtered result set exceeds 10,000 events, THE Audit_PDF_Exporter SHALL process the export as an asynchronous Celery task and deliver an in-app notification to the requesting user containing a download link when the PDF is ready, within a maximum processing time of 300 seconds.
6. THE Audit_PDF_Exporter SHALL include a footer on each page with page number, total pages, and a generation timestamp.
7. THE Audit_Trail_Viewer SHALL provide an "Export to PDF" button that triggers PDF generation with the currently applied filters.
8. IF the filtered result set contains zero audit events, THEN THE Audit_PDF_Exporter SHALL not generate a PDF and THE Audit_Trail_Viewer SHALL display a message indicating that no events match the current filters for export.
9. IF PDF generation fails due to a processing error or timeout, THEN THE Audit_PDF_Exporter SHALL return an error indication to the user stating that the export could not be completed, and SHALL NOT produce a partial or corrupted PDF file.
10. WHEN a PDF is generated asynchronously, THE Audit_PDF_Exporter SHALL retain the generated PDF file for download for a minimum of 72 hours before deletion.

### Requirement 8: Immutability Enforcement

**User Story:** As a regulatory compliance officer, I want assurance that audit trail entries cannot be modified or deleted, so that the audit trail maintains its evidentiary integrity.

#### Acceptance Criteria

1. THE Audit_Trail_Service SHALL reject all PUT, PATCH, and DELETE requests to audit trail endpoints with HTTP 403.
2. THE Audit_Trail_Service SHALL return an error message stating "Audit records are immutable per ALCOA+ and CFR 21 Part 11" for any rejected mutation attempt.
3. THE Audit_Trail_Viewer SHALL provide no UI controls for editing or deleting audit entries.
4. THE Audit_Trail_Service SHALL enforce immutability at the API layer regardless of the requesting user's role or permissions.

### Requirement 9: Role-Based Access Control

**User Story:** As a system administrator, I want audit trail access restricted to authorized roles, so that sensitive operational data is protected from unauthorized viewing.

#### Acceptance Criteria

1. THE Audit_Trail_Service SHALL grant read access to users with system_admin, doc_admin, or it_admin roles.
2. WHEN a user without an Authorized_Role attempts to access the audit trail, THE Audit_Trail_Service SHALL return HTTP 403.
3. THE Audit_Trail_Viewer SHALL be accessible only at the route `/admin/audit-trail` and protected by frontend route guards that verify the user holds an Authorized_Role.
4. THE Audit_Trail_Service SHALL enforce permission checks using the existing `require_permission` FastAPI dependency with the `audit_logs` resource type and `read` action.

### Requirement 10: Audit Trail Viewer Frontend Page

**User Story:** As an administrator, I want a dedicated page for browsing the audit trail, so that I can access all audit functionality from a single location.

#### Acceptance Criteria

1. THE Audit_Trail_Viewer SHALL be accessible at the route `/admin/audit-trail`.
2. THE Audit_Trail_Viewer SHALL display a data table with columns: timestamp, user, record type, record ID, operation, and change reason.
3. THE Audit_Trail_Viewer SHALL support column sorting by timestamp, user, record type, and operation type.
4. THE Audit_Trail_Viewer SHALL display a loading state while audit events are being fetched.
5. WHEN no audit events match the current filters, THE Audit_Trail_Viewer SHALL display an empty state message indicating no results were found.
6. THE Audit_Trail_Viewer SHALL use shadcn/ui components consistent with the existing AlcoaBase admin interface design.

### Requirement 11: Audit of Audit Trail Access

**User Story:** As a compliance officer, I want access to the audit trail itself to be logged, so that there is a record of who reviewed the audit data and when.

#### Acceptance Criteria

1. WHEN a user accesses the Audit_Trail_Viewer, THE Audit_Trail_Service SHALL log the access event including user identity, timestamp, and applied filters.
2. WHEN a PDF export is generated, THE Audit_Trail_Service SHALL log the export event including user identity, timestamp, applied filters, and the number of events exported.
3. THE Audit_Trail_Service SHALL store access logs in a dedicated audit_access_log table that follows the same immutability rules as the main audit trail.
