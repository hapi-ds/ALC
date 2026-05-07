# Requirements Document

## Introduction

This feature wires up the existing Documents page in the React frontend to the real FastAPI backend API, implementing the full document upload flow (file picker → multipart POST → list refresh), displaying document metadata, tags, and version information. Additionally, it delivers a standalone Python CLI tool for bulk-uploading an entire directory tree of documents via the API, enabling company-wide document imports.

## Glossary

- **Documents_Page**: The React page component at `src/frontend/src/pages/DocumentsPage.tsx` that displays the document list, upload controls, and document details.
- **Document_Store**: The Zustand state store at `src/frontend/src/stores/documentStore.ts` managing document state and API interactions.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, and tenant headers.
- **Document_API**: The FastAPI router at `/api/v1/documents` providing document CRUD, versioning, and search endpoints.
- **Upload_Dialog**: A modal dialog component that collects file selection, title, folder path, document type, and tags before submitting.
- **Bulk_Upload_CLI**: A standalone Python command-line program that recursively walks a directory tree and uploads each file to the Document_API.
- **Document_UUID**: A unique identifier in YYYY-NNNNN format assigned by the backend upon document creation.
- **Multipart_POST**: An HTTP POST request with `multipart/form-data` encoding used to upload files alongside form fields.
- **Tenant_Header**: The `X-Company-Id` HTTP header used to scope API requests to a specific company.

## Requirements

### Requirement 1: Fetch and Display Document List

**User Story:** As a user, I want to see my company's documents listed on the Documents page, so that I can browse and find documents quickly.

#### Acceptance Criteria

1. WHEN the Documents_Page mounts, THE Document_Store SHALL fetch documents from the Document_API using `GET /api/v1/documents` with the current Tenant_Header.
2. WHILE the Document_Store is loading documents, THE Documents_Page SHALL display a loading indicator.
3. WHEN the Document_API returns a successful response, THE Documents_Page SHALL render each document showing its Document_UUID, title, document_type, current_status, tags, and creation date.
4. THE Documents_Page SHALL display the name of the company the user is currently logged into.
5. WHEN the Document_API returns an empty result set, THE Documents_Page SHALL display an empty state message indicating no documents exist.
6. IF the Document_API returns an error, THEN THE Documents_Page SHALL display an error message describing the failure.

### Requirement 2: Paginated Document Browsing

**User Story:** As a user, I want to page through large document lists, so that I can navigate without loading all documents at once.

#### Acceptance Criteria

1. THE Document_Store SHALL request documents with `offset` and `limit` query parameters.
2. WHEN the user navigates to the next page, THE Document_Store SHALL fetch the next set of documents using an incremented offset.
3. THE Documents_Page SHALL display the total document count and current page position.
4. WHEN the user is on the first page, THE Documents_Page SHALL disable the previous-page control.
5. WHEN the user is on the last page, THE Documents_Page SHALL disable the next-page control.

### Requirement 3: Filter Documents by Tag and Folder

**User Story:** As a user, I want to filter documents by tag or folder path, so that I can narrow down the list to relevant documents.

#### Acceptance Criteria

1. WHEN the user selects a tag filter, THE Document_Store SHALL include the `tag` query parameter in the API request.
2. WHEN the user enters a folder path filter, THE Document_Store SHALL include the `folder_path` query parameter in the API request.
3. WHEN filters are applied, THE Documents_Page SHALL reset pagination to the first page.
4. WHEN the user clears all filters, THE Document_Store SHALL fetch the unfiltered document list.

### Requirement 4: Single Document Upload

**User Story:** As a user, I want to upload a document with metadata, so that it is stored and tracked in the system.

#### Acceptance Criteria

1. WHEN the user clicks the Upload Document button, THE Documents_Page SHALL open the Upload_Dialog.
2. THE Upload_Dialog SHALL provide a file picker that accepts file selection via click or drag-and-drop.
3. THE Upload_Dialog SHALL require the user to provide a title, folder path, and document type before submission.
4. THE Upload_Dialog SHALL allow the user to enter comma-separated tags.
5. WHEN the user submits the Upload_Dialog, THE Document_Store SHALL send a Multipart_POST to `POST /api/v1/documents` containing the file, title, folder_path, document_type, tags, and user_id.
6. WHILE the upload is in progress, THE Upload_Dialog SHALL display a progress indicator and disable the submit button.
7. WHEN the upload completes successfully, THE Document_Store SHALL refresh the document list and THE Upload_Dialog SHALL close.
8. IF the upload fails, THEN THE Upload_Dialog SHALL display the error message returned by the Document_API.

### Requirement 5: Display Document Detail with Metadata

**User Story:** As a user, I want to view a document's full metadata, tags, and version history, so that I can understand its current state.

#### Acceptance Criteria

1. WHEN the user selects a document from the list, THE Documents_Page SHALL fetch the document detail from `GET /api/v1/documents/{document_uuid}`.
2. THE Documents_Page SHALL display the document's title, Document_UUID, folder_path, document_type, current_status, created_by, and created_at.
3. THE Documents_Page SHALL display all tags associated with the document as visual badges.
4. THE Documents_Page SHALL display the version history showing each version's major_version, minor_version, uploaded_at, and change_reason.

### Requirement 6: Create New Document Version

**User Story:** As a user, I want to upload a new version of an existing document with a change reason, so that the document history is maintained.

#### Acceptance Criteria

1. WHEN the user is viewing a document detail, THE Documents_Page SHALL provide a "New Version" action.
2. WHEN the user triggers the New Version action, THE Documents_Page SHALL display a version upload form requesting a file, version type (major or minor), and change reason.
3. WHEN the user submits the version form, THE Document_Store SHALL send a Multipart_POST to `POST /api/v1/documents/{document_uuid}/versions` containing the file, version_type, change_reason, and user_id.
4. WHEN the version upload completes successfully, THE Document_Store SHALL refresh the document detail including the updated version list.
5. IF the version upload fails, THEN THE Documents_Page SHALL display the error message returned by the Document_API.

### Requirement 7: Bulk Upload CLI — Directory Tree Walk

**User Story:** As an administrator, I want to bulk-import an entire directory tree of documents via a CLI tool, so that I can onboard a company's existing document library efficiently.

#### Acceptance Criteria

1. THE Bulk_Upload_CLI SHALL accept a root directory path, API base URL, company ID, and user ID as command-line arguments.
2. THE Bulk_Upload_CLI SHALL recursively walk the specified directory tree and identify all files for upload.
3. FOR EACH file found, THE Bulk_Upload_CLI SHALL derive the folder_path from the file's relative path within the root directory.
4. FOR EACH file found, THE Bulk_Upload_CLI SHALL derive a default title from the filename without extension.
5. THE Bulk_Upload_CLI SHALL send a Multipart_POST to `POST /api/v1/documents` for each file, including the derived title, folder_path, a configurable default document_type, and the Tenant_Header.
6. WHILE uploading, THE Bulk_Upload_CLI SHALL display progress indicating the current file number out of total files.
7. IF an individual file upload fails, THEN THE Bulk_Upload_CLI SHALL log the error with the file path and continue processing remaining files.
8. WHEN all files have been processed, THE Bulk_Upload_CLI SHALL print a summary showing total files processed, successful uploads, and failed uploads.

### Requirement 8: Bulk Upload CLI — Configuration and Authentication

**User Story:** As an administrator, I want the bulk upload tool to authenticate properly and support configuration, so that it works securely against the production API.

#### Acceptance Criteria

1. THE Bulk_Upload_CLI SHALL accept an API authentication token via command-line argument or environment variable.
2. THE Bulk_Upload_CLI SHALL include the authentication token as a Bearer token in the Authorization header of each request.
3. THE Bulk_Upload_CLI SHALL include the company ID as the `X-Company-Id` header in each request.
4. WHERE the user provides a `--document-type` option, THE Bulk_Upload_CLI SHALL use the specified value for all uploads.
5. WHERE the user provides a `--tags` option, THE Bulk_Upload_CLI SHALL apply the specified comma-separated tags to all uploads.
6. WHERE the user provides a `--dry-run` option, THE Bulk_Upload_CLI SHALL list all files that would be uploaded without sending any requests.
7. THE Bulk_Upload_CLI SHALL validate that the root directory exists and is readable before starting the upload process.

### Requirement 9: Multipart Upload via API Client

**User Story:** As a developer, I want the API client to support multipart form data uploads, so that file uploads work correctly with authentication and tenant headers.

#### Acceptance Criteria

1. THE API_Client SHALL provide a method for sending Multipart_POST requests that does not set `Content-Type: application/json`.
2. THE API_Client multipart method SHALL attach the Bearer token from the current session.
3. THE API_Client multipart method SHALL attach the Tenant_Header (X-Company-Id and X-User-Id) from the current auth context.
4. WHEN a multipart request receives a 401 response, THE API_Client SHALL attempt token refresh and retry the request once.

### Requirement 10: Upload Validation and File Constraints

**User Story:** As a user, I want clear feedback on file constraints before uploading, so that I do not waste time on invalid uploads.

#### Acceptance Criteria

1. THE Upload_Dialog SHALL validate that a file has been selected before allowing submission.
2. THE Upload_Dialog SHALL validate that the title field is not empty and does not exceed 500 characters.
3. THE Upload_Dialog SHALL validate that the folder_path field is not empty and does not exceed 1000 characters.
4. IF the user attempts to submit with validation errors, THEN THE Upload_Dialog SHALL highlight the invalid fields with descriptive error messages.
