# Design Document: Document Upload & List

## Overview

This feature wires the existing scaffolded Documents page in the React frontend to the real FastAPI backend, implementing the complete document lifecycle: fetching/listing documents with pagination and filtering, uploading new documents via a modal dialog, viewing document detail with version history, and creating new versions. Additionally, it delivers a standalone Python CLI tool (`bulk-upload`) for recursively uploading an entire directory tree of documents to the API.

The design spans two deliverables:
1. **Frontend Integration** — Zustand store wired to real API endpoints, multipart upload support in the API client, and fully interactive UI components (list, filters, pagination, upload dialog, detail view, version upload).
2. **Bulk Upload CLI** — A Python CLI script using `httpx` and `argparse` that authenticates via Bearer token, walks a directory tree, and uploads each file with derived metadata.

## Architecture

```mermaid
graph TD
    subgraph Frontend [React Frontend]
        DP[DocumentsPage]
        DS[documentStore - Zustand]
        AC[apiClient]
        UD[UploadDialog]
        DL[DocumentList]
        DD[DocumentDetail]
        VH[VersionHistory]
        PG[Pagination]
        FT[FilterBar]
    end

    subgraph Backend [FastAPI Backend]
        API[/api/v1/documents]
        SVC[DocumentService]
        DB[(PostgreSQL)]
        S3[(MinIO)]
    end

    subgraph CLI [Bulk Upload CLI]
        BU[bulk_upload.py]
    end

    DP --> DS
    DS --> AC
    AC -->|multipart/json| API
    API --> SVC
    SVC --> DB
    SVC --> S3

    BU -->|multipart + Bearer| API

    DP --> UD
    DP --> DL
    DP --> DD
    DP --> PG
    DP --> FT
    DD --> VH
```

### Key Design Decisions

1. **Multipart upload via dedicated `apiClient.upload()` method** — The existing `apiClient` sets `Content-Type: application/json` for non-GET requests. File uploads require `multipart/form-data` where the browser must set the boundary automatically. A new `upload()` method omits the Content-Type header and accepts a `FormData` body directly.

2. **Zustand store as single source of truth** — All document state (list, pagination metadata, selected document, loading/error states) lives in the `documentStore`. Components subscribe to slices they need.

3. **CLI uses `httpx` (already a backend dependency)** — Rather than adding `requests`, we reuse `httpx` which is already in the backend's dependency list and supports sync multipart uploads cleanly.

4. **Pagination via offset/limit** — Matches the existing backend API contract. The store tracks `offset`, `limit`, and `total` to compute page position.

## Components and Interfaces

### Frontend Components

| Component | Responsibility |
|-----------|---------------|
| `DocumentsPage` | Page-level orchestrator; mounts store fetch, renders sub-components |
| `DocumentList` | Renders table/list of documents with UUID, title, type, status, tags, date |
| `DocumentDetail` | Shows full metadata + version history for a selected document |
| `UploadDialog` | Modal with file picker (drag-and-drop), form fields, validation, submit |
| `VersionUploadDialog` | Modal for uploading a new version (file, version type, change reason) |
| `FilterBar` | Tag dropdown + folder path input for filtering |
| `Pagination` | Previous/Next controls with page position display |

### API Client Extension

```typescript
// New method added to apiClient
upload<T>(url: string, formData: FormData, options?: ApiClientOptions): Promise<T>
```

This method:
- Does NOT set `Content-Type` (browser sets `multipart/form-data; boundary=...`)
- Attaches Bearer token from current session
- Attaches `X-Company-Id` and `X-User-Id` tenant headers
- Supports 401 retry with token refresh (same as existing `request()`)

### Document Store Interface

```typescript
interface DocumentState {
  // Data
  documents: DocumentResponse[];
  selectedDocument: DocumentResponse | null;
  total: number;

  // Pagination
  offset: number;
  limit: number;

  // Filters
  tagFilter: string | null;
  folderPathFilter: string | null;

  // UI state
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchDocuments: () => Promise<void>;
  fetchDocument: (uuid: string) => Promise<void>;
  uploadDocument: (formData: FormData) => Promise<void>;
  createVersion: (uuid: string, formData: FormData) => Promise<void>;
  setPage: (page: number) => void;
  nextPage: () => void;
  prevPage: () => void;
  setTagFilter: (tag: string | null) => void;
  setFolderPathFilter: (path: string | null) => void;
  clearFilters: () => void;
}
```

### Bulk Upload CLI Interface

```
usage: bulk_upload.py [-h] --directory DIR --api-url URL --company-id ID
                     --user-id ID [--token TOKEN] [--document-type TYPE]
                     [--tags TAGS] [--dry-run]

Bulk upload documents from a directory tree to the AlcoaBase API.

required arguments:
  --directory DIR       Root directory to recursively walk
  --api-url URL         Base API URL (e.g., http://localhost:8000)
  --company-id ID       Company ID for X-Company-Id header
  --user-id ID          User ID for upload attribution

optional arguments:
  --token TOKEN         Bearer token (or set ALCOABASE_TOKEN env var)
  --document-type TYPE  Document type for all uploads (default: "General")
  --tags TAGS           Comma-separated tags to apply to all uploads
  --dry-run             List files without uploading
```

## Data Models

### Frontend TypeScript Types

```typescript
// src/frontend/src/types/document.ts

export interface DocumentTag {
  id: number;
  tag: string;
}

export interface DocumentVersion {
  id: number;
  major_version: number;
  minor_version: number;
  storage_key: string;
  file_hash: string;
  uploaded_by: number;
  uploaded_at: string;
  change_reason: string | null;
}

export interface DocumentResponse {
  id: number;
  document_uuid: string;
  title: string;
  folder_path: string;
  document_type: string;
  current_status: string;
  created_by: number;
  created_at: string;
  tags: DocumentTag[];
  versions: DocumentVersion[];
}

export interface DocumentSearchResponse {
  items: DocumentResponse[];
  total: number;
}

export interface UploadFormData {
  file: File;
  title: string;
  folder_path: string;
  document_type: string;
  tags: string; // comma-separated
}

export interface VersionUploadFormData {
  file: File;
  version_type: "major" | "minor";
  change_reason: string;
}
```

### Backend — No Model Changes Required

The existing `Document`, `DocumentTag`, and `DocumentVersion` SQLAlchemy models already support all required fields. The existing Pydantic schemas (`DocumentResponse`, `DocumentSearchResponse`, `DocumentVersionResponse`) match the API contract needed by the frontend.

### CLI Data Flow

```
Directory Tree → File Discovery → Metadata Derivation → Multipart POST
                                                         ↓
                                                    API Response
                                                         ↓
                                                  Progress + Summary
```

For each file:
- `title` = filename stem (without extension)
- `folder_path` = relative directory path from root
- `document_type` = CLI `--document-type` argument (default: "General")
- `tags` = CLI `--tags` argument (default: empty)

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Document list renders all required fields

*For any* array of valid DocumentResponse objects, rendering the document list should produce output containing each document's document_uuid, title, document_type, current_status, at least one tag string, and created_at date.

**Validates: Requirements 1.3**

### Property 2: Pagination arithmetic is consistent

*For any* valid offset (≥ 0), limit (≥ 1), and total (≥ 0), the computed current page number should equal `floor(offset / limit) + 1`, the total pages should equal `ceil(total / limit)`, calling nextPage should set offset to `offset + limit`, calling prevPage should set offset to `max(0, offset - limit)`, the previous control should be disabled if and only if offset is 0, and the next control should be disabled if and only if `offset + limit >= total`.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

### Property 3: Applying a filter resets pagination to first page

*For any* current offset greater than 0, applying either a tag filter or a folder path filter should reset the offset to 0.

**Validates: Requirements 3.3**

### Property 4: Active filters map to API query parameters

*For any* non-null tag string and/or non-null folder_path string set in the store, the resulting API request URL should contain the corresponding `tag` and/or `folder_path` query parameters with those exact values.

**Validates: Requirements 3.1, 3.2**

### Property 5: Upload form field validation

*For any* string value for title, it should pass validation if and only if its trimmed length is between 1 and 500 characters inclusive. *For any* string value for folder_path, it should pass validation if and only if its trimmed length is between 1 and 1000 characters inclusive. *For any* form state, submission should be prevented if file is null, title is invalid, or folder_path is invalid.

**Validates: Requirements 4.3, 10.1, 10.2, 10.3**

### Property 6: Multipart FormData construction preserves all fields

*For any* valid upload form data (file, title, folder_path, document_type, tags) or version form data (file, version_type, change_reason), the constructed FormData object should contain entries for every required field with values matching the input.

**Validates: Requirements 4.5, 6.3**

### Property 7: Document detail renders all metadata, tags, and versions

*For any* valid DocumentResponse with N tags and M versions, the rendered detail view should display the document's title, document_uuid, folder_path, document_type, current_status, created_by, and created_at, plus exactly N tag badges with correct text, plus M version entries each showing major_version, minor_version, uploaded_at, and change_reason.

**Validates: Requirements 5.2, 5.3, 5.4**

### Property 8: API client upload method sets correct headers

*For any* access token, userId, and companyId in the auth context, the `apiClient.upload()` method should produce a request where: the `Authorization` header equals `Bearer {token}`, the `X-Company-Id` header equals the companyId, the `X-User-Id` header equals the userId, and the `Content-Type` header is NOT set to `application/json`.

**Validates: Requirements 9.1, 9.2, 9.3**

### Property 9: CLI path-to-metadata derivation

*For any* root directory path and any file path that is a descendant of that root, the derived `folder_path` should equal the relative directory portion (parent path relative to root), and the derived `title` should equal the filename without its last extension (the stem).

**Validates: Requirements 7.3, 7.4**

### Property 10: CLI directory walk discovers all files

*For any* directory tree structure (with arbitrary nesting depth and file count), the walk function should return exactly the set of all regular files contained within the tree, with no duplicates and no omissions.

**Validates: Requirements 7.2**

### Property 11: CLI request construction includes all required fields and headers

*For any* valid file metadata (title, folder_path, document_type, tags) and CLI configuration (token, company_id, user_id), the constructed HTTP request should: include `Authorization: Bearer {token}`, include `X-Company-Id: {company_id}`, use multipart/form-data encoding, and contain form fields for file, title, folder_path, document_type, tags, and user_id.

**Validates: Requirements 7.5, 8.2, 8.3, 8.4, 8.5**

### Property 12: CLI summary counts are arithmetically correct

*For any* sequence of N upload attempts where S succeed and F fail, the printed summary should report total=N, successful=S, failed=F, and N = S + F.

**Validates: Requirements 7.8**

## Error Handling

### Frontend Error Handling

| Scenario | Behavior |
|----------|----------|
| API returns 4xx/5xx on document list fetch | Store sets `error` string; page displays error banner with message |
| API returns 401 on any request | `apiClient` attempts token refresh; on failure, clears session and redirects to login |
| Upload fails (network or server error) | Upload dialog displays error message from response body; submit button re-enabled |
| Version upload fails | Detail view displays error toast/banner; form remains open for retry |
| Empty API response | Page shows empty state with "No documents yet" message |
| File validation fails client-side | Form fields highlighted with inline error messages; submission blocked |

### CLI Error Handling

| Scenario | Behavior |
|----------|----------|
| Root directory does not exist | Exit immediately with descriptive error message (exit code 1) |
| Root directory not readable | Exit immediately with permission error (exit code 1) |
| Individual file upload fails (4xx/5xx) | Log error with file path and HTTP status; continue to next file |
| Network timeout on upload | Log timeout error with file path; continue to next file |
| Invalid/missing auth token | First request fails with 401; log auth error and exit (exit code 1) |
| No files found in directory | Print "No files found" message and exit cleanly (exit code 0) |

### Error Message Format

Frontend errors are displayed as-is from the API response `detail` field. The CLI formats errors as:
```
ERROR [{file_path}]: {status_code} - {response_detail}
```

## Testing Strategy

### Frontend Testing (vitest + fast-check)

**Unit Tests (example-based):**
- Component mount triggers fetchDocuments (Req 1.1)
- Loading state shows spinner (Req 1.2)
- Empty state message when no documents (Req 1.5)
- Error state displays error message (Req 1.6)
- Upload button opens dialog (Req 4.1)
- File picker accepts drag-and-drop (Req 4.2)
- Upload progress indicator shown during upload (Req 4.6)
- Successful upload closes dialog and refreshes list (Req 4.7)
- Failed upload shows error in dialog (Req 4.8)
- Document click fetches detail (Req 5.1)
- New Version button present in detail view (Req 6.1)
- Version form shows correct fields (Req 6.2)
- Successful version upload refreshes detail (Req 6.4)
- 401 triggers refresh and retry (Req 9.4)

**Property Tests (fast-check, minimum 100 iterations each):**
- Property 1: Document list field rendering — Feature: document-upload-list, Property 1
- Property 2: Pagination arithmetic — Feature: document-upload-list, Property 2
- Property 3: Filter resets pagination — Feature: document-upload-list, Property 3
- Property 4: Filters map to query params — Feature: document-upload-list, Property 4
- Property 5: Upload form validation — Feature: document-upload-list, Property 5
- Property 6: FormData construction — Feature: document-upload-list, Property 6
- Property 7: Detail view rendering — Feature: document-upload-list, Property 7
- Property 8: Upload method headers — Feature: document-upload-list, Property 8

### Backend CLI Testing (pytest + hypothesis)

**Unit Tests (example-based):**
- CLI accepts token from env var (Req 8.1)
- Dry-run lists files without HTTP calls (Req 8.6)
- Non-existent directory exits with error (Req 8.7)
- Single file failure doesn't stop processing (Req 7.7)

**Property Tests (hypothesis, minimum 100 iterations each):**
- Property 9: Path-to-metadata derivation — Feature: document-upload-list, Property 9
- Property 10: Directory walk completeness — Feature: document-upload-list, Property 10
- Property 11: Request construction — Feature: document-upload-list, Property 11
- Property 12: Summary counts — Feature: document-upload-list, Property 12

### Test File Locations

- Frontend: `src/frontend/src/__tests__/documents/` (unit + property tests)
- CLI: `src/backend/tests/test_bulk_upload/` (unit + property tests)

### Property-Based Testing Configuration

- **Frontend**: `fast-check` (already in devDependencies), configured with `{ numRuns: 100 }`
- **Backend**: `hypothesis` (already in dev dependencies), configured with `@settings(max_examples=100)`
- Each property test tagged with: `Feature: document-upload-list, Property {N}: {title}`

