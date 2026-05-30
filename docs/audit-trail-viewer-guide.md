# Audit Trail Viewer Guide

The Audit Trail Viewer provides a centralized, searchable, and filterable view of all audit events across AlcoaBase. It answers the regulatory questions: **who** did **what**, **when**, and **why** — aggregating changes from documents, templates, reports, workflows, signatures, and training records into a single chronological view.

---

## Accessing the Audit Trail

Navigate to **Admin → Audit Trail** in the sidebar, or go directly to `/admin/audit-trail`.

**Required roles:** `system_admin`, `doc_admin`, or `it_admin`. Users without one of these roles cannot access the audit trail.

---

## Browsing Audit Events

The main view displays a paginated table of audit events sorted by timestamp (most recent first). Each row shows:

| Column | Description |
|--------|-------------|
| Timestamp | When the change occurred (server-side UTC) |
| User | Who performed the action (display name or user ID fallback) |
| Record Type | What type of record was changed (documents, templates, etc.) |
| Record ID | The primary key of the affected record |
| Operation | INSERT (green), UPDATE (blue), or DELETE (red) badge |
| Change Reason | The justification provided via X-Change-Reason header |
| Changed Fields | Which fields were modified (max 10 shown, "+N more" if truncated) |

### Sorting

Click any sortable column header (Timestamp, User, Record Type, Operation) to toggle sort direction. The active sort column is highlighted.

### Pagination

Events load in pages of 50. Click **Load more** at the bottom to fetch the next page. The "Showing X of Y events" indicator tracks your position.

### Transaction Grouping

When multiple changes occur in a single HTTP request (same transaction), a subtle "TXN" badge appears next to the operation badge, allowing you to identify correlated changes.

---

## Filtering

The filter bar at the top provides:

- **User** — Searchable dropdown to filter by the user who performed the action
- **From / To** — Date range picker (inclusive) to narrow by time period
- **Record Type** — Dropdown: documents, templates, reports, workflows, signatures, training_tasks, training_records
- **Operation** — Dropdown: INSERT, UPDATE, DELETE
- **Search** — Free-text substring search across change reasons, record types, user names, and record IDs (press Enter to submit)

All filters combine with AND logic. Click **Clear filters** to reset everything.

---

## Event Detail View

Click any row to open the detail slide-over panel on the right. This shows:

- Full event metadata (timestamp, user, record type, record ID, operation, transaction ID, complete change reason text)
- **Field-level changes** displayed as a table:
  - **UPDATE**: Two columns showing Previous Value and New Value for each changed field (highlighted)
  - **INSERT**: Single column showing Initial Value for all fields
  - **DELETE**: Single column showing Final Value before deletion

Complex values (JSON objects, arrays) are formatted with syntax highlighting for readability.

Close the panel by clicking the X button or clicking outside the panel.

---

## PDF Export

Click **Export to PDF** in the page header to generate a regulatory-compliant PDF of the current filtered view.

### Export Behavior

- **≤ 10,000 events**: PDF generates immediately and downloads to your browser
- **> 10,000 events**: Export runs in the background. A toast notification appears: "Export started, you'll be notified when ready." The system polls every 5 seconds and shows a download link when complete.
- **0 events**: The button is disabled with a tooltip "No events to export"

### PDF Format

The generated PDF is formatted for FDA/EMA regulatory submissions:

- **Header**: Company name, export date/time (UTC), applied filters, total event count, requesting user identity
- **Table**: Sequential number, timestamp, user, record type, record ID, operation, change reason (truncated to 500 chars with "..." if longer)
- **Footer**: Page number, total pages, generation timestamp
- **Layout**: A4 portrait, fixed-width font (Courier), column headers repeated on each page, visible row separators

Exported PDFs are retained for 72 hours before automatic deletion.

---

## Cross-Company Queries (System Admin Only)

Users with the `system_admin` role can query audit events across all companies by adding `?cross_company=true` to the API request. This is not exposed in the UI but available via the API for compliance investigations spanning multiple tenants.

---

## Immutability

Audit records are **completely immutable**. There are no UI controls for editing or deleting audit entries. Any attempt to modify audit data via the API (PUT, PATCH, DELETE) returns HTTP 403 with the message:

> "Audit records are immutable per ALCOA+ and CFR 21 Part 11"

This applies regardless of the requesting user's role or permissions.

---

## Meta-Auditing (Audit of Audit Access)

Every access to the audit trail is itself logged:

- **View events**: Logged with user identity, timestamp, and applied filters
- **Export PDF**: Logged with user identity, timestamp, filters, and number of events exported

These access logs are stored in a dedicated `audit_access_log` table that follows the same immutability rules as the main audit trail.

---

## API Reference

All endpoints are prefixed with `/api/audit-trail` and require the `audit_logs:read` permission.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/audit-trail` | List/filter/search events (paginated) |
| GET | `/api/audit-trail/{record_type}/{record_id}/{transaction_id}` | Get full event detail |
| POST | `/api/audit-trail/export` | Trigger PDF export |
| GET | `/api/audit-trail/export/{job_id}` | Check async export status |

### Query Parameters (GET /api/audit-trail)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| cursor | string | null | Opaque pagination cursor |
| page_size | int | 50 | Events per page (1–200) |
| search | string | null | Substring search query |
| user_id | int | null | Filter by user ID |
| date_start | datetime | null | Filter start date (inclusive) |
| date_end | datetime | null | Filter end date (inclusive) |
| record_type | string | null | Filter by record type |
| operation_type | string | null | Filter: INSERT, UPDATE, or DELETE |
| cross_company | bool | false | Query all companies (system_admin only) |

### Required Headers

| Header | Purpose |
|--------|---------|
| Authorization: Bearer {token} | Authentication |
| X-Company-Id | Tenant scoping |

---

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| "No audit events match the current filters" | Adjust or clear filters. Events may not exist for the selected criteria. |
| Export button disabled | No events match current filters. Clear filters to see all events. |
| Export timeout | Large exports (>10k events) have a 300-second limit. Try narrowing filters to reduce the dataset. |
| Missing events from a record type | If a version table query fails, the viewer shows a warning banner listing which record types could not be retrieved. Other record types still display normally. |
| 403 on access | Your role must be system_admin, doc_admin, or it_admin. Contact your administrator. |
