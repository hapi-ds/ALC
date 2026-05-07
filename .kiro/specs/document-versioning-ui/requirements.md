# Requirements Document

## Introduction

This feature enhances the document versioning user interface in AlcoaBase. The existing frontend has a basic version history list and a version upload dialog. This spec covers building a dedicated version history panel with rich metadata display, diff metadata between versions, a version comparison view, version download capability, improved upload UX with validation, version status indicators, and the ability to view details of any specific version. The backend API is already complete — this is purely a frontend feature.

## Glossary

- **Version_History_Panel**: A dedicated UI panel that displays the complete version timeline for a document, including metadata for each version entry.
- **Diff_Metadata_View**: A UI component that computes and displays metadata differences between two selected versions (file hash comparison, upload date delta, uploader changes).
- **Version_Comparison_View**: A side-by-side layout showing metadata of two selected versions for direct comparison.
- **Version_Detail_View**: A detailed view showing all metadata fields for a single selected version.
- **Version_Status_Indicator**: A visual badge or label distinguishing the current (latest) version from previous versions.
- **Version_Upload_Form**: The enhanced form for uploading a new document version with file selection, version type, and change reason.
- **Document_Store**: The Zustand store managing document state, including version-related actions.
- **API_Client**: The frontend HTTP client (`apiClient`) used to communicate with the backend API.

## Requirements

### Requirement 1: Version History Panel

**User Story:** As a document manager, I want to see a rich timeline of all versions for a document, so that I can understand the full revision history at a glance.

#### Acceptance Criteria

1. WHEN a user navigates to a document detail page, THE Version_History_Panel SHALL display all versions sorted from newest to oldest by descending major version then descending minor version.
2. THE Version_History_Panel SHALL display the version number (major.minor), upload date in the user's locale format (date and time), uploader ID, and change reason for each version entry, with the change reason truncated to 120 characters followed by an ellipsis if it exceeds that length.
3. THE Version_History_Panel SHALL display the file hash (truncated to first 12 characters) for each version entry.
4. WHEN the document has zero versions, THE Version_History_Panel SHALL display an empty state message indicating no versions are available.
5. THE Version_History_Panel SHALL render as a vertical timeline with visual connectors between version entries.
6. IF the change_reason field is null for a version entry, THEN THE Version_History_Panel SHALL display "No reason provided" as placeholder text in place of the change reason.

### Requirement 2: Version Status Indicators

**User Story:** As a document manager, I want to clearly see which version is the current one, so that I can distinguish it from previous versions.

#### Acceptance Criteria

1. THE Version_Status_Indicator SHALL mark the version with the highest (major_version, minor_version) tuple as "Current", comparing major_version first and minor_version second.
2. THE Version_Status_Indicator SHALL mark all other versions as "Previous".
3. THE Version_Status_Indicator SHALL display a badge with the label text "Current" or "Previous", where the "Current" badge uses a different background color than the "Previous" badge.
4. WHEN a new version is uploaded, THE Version_Status_Indicator SHALL update the new version's badge to "Current" and change the previously-current version's badge to "Previous" without requiring a full page reload.
5. THE Version_Status_Indicator SHALL include an accessible label on each badge so that screen readers convey the status ("Current" or "Previous") to assistive technology users.

### Requirement 3: Version Detail View

**User Story:** As a document manager, I want to view all metadata for a specific version, so that I can inspect its details including storage key and full file hash.

#### Acceptance Criteria

1. WHEN a user selects a version from the Version_History_Panel, THE Version_Detail_View SHALL display all metadata fields: version number (major.minor format), storage key, full file hash, uploaded by, uploaded at, and change reason.
2. THE Version_Detail_View SHALL display the full SHA-256 file hash (64 hexadecimal characters) in a monospace font with a copy-to-clipboard button that displays a confirmation indicator for 3 seconds after a successful copy.
3. THE Version_Detail_View SHALL format the uploaded_at timestamp in the user's browser locale format with both date and time.
4. IF the change_reason field is null, THEN THE Version_Detail_View SHALL display "No reason provided" as placeholder text.
5. IF the version data fails to load, THEN THE Version_Detail_View SHALL display an error message indicating the version could not be retrieved and provide a retry option.

### Requirement 4: Diff Metadata Between Versions

**User Story:** As a document manager, I want to see what changed between two versions, so that I can understand the nature of each revision.

#### Acceptance Criteria

1. WHEN a user selects two versions for comparison, THE Diff_Metadata_View SHALL display whether the file hash changed between the two versions.
2. WHEN a user selects two versions for comparison, THE Diff_Metadata_View SHALL display the absolute time elapsed between the two upload dates in a human-readable format showing the number of days, hours, and minutes.
3. WHEN a user selects two versions for comparison, THE Diff_Metadata_View SHALL indicate whether the uploader changed between versions.
4. WHEN a user selects two versions for comparison, THE Diff_Metadata_View SHALL compare the following metadata fields: file_hash, uploaded_by, uploaded_at, and change_reason, and display fields that differ with a distinct background color to distinguish them from unchanged fields.
5. IF the file hashes are identical between two versions, THEN THE Diff_Metadata_View SHALL display a notice indicating the file content is unchanged.
6. IF fewer than two versions exist for the document, THEN THE Diff_Metadata_View SHALL disable the comparison action and display a message indicating that at least two versions are required for comparison.

### Requirement 5: Version Comparison View

**User Story:** As a document manager, I want to compare two versions side by side, so that I can see all metadata differences in context.

#### Acceptance Criteria

1. THE Version_Comparison_View SHALL display two versions in a side-by-side layout with the following metadata fields aligned row-by-row: version number, file_hash, uploaded_by, uploaded_at, change_reason, and storage_key.
2. WHEN a user opens the Version_Comparison_View, THE Version_Comparison_View SHALL default to comparing the two versions with the highest major.minor numbers (most recent on the right, second most recent on the left).
3. WHEN a user changes a dropdown selector value, THE Version_Comparison_View SHALL update the corresponding side to display the newly selected version's metadata.
4. THE Version_Comparison_View SHALL highlight metadata fields that differ between the two selected versions using a visually distinct background color compared to unchanged fields.
5. IF the user selects the same version for both sides, THEN THE Version_Comparison_View SHALL display a notice indicating both sides show the same version and SHALL NOT highlight any fields as different.
6. IF the document has fewer than 2 versions, THEN THE Version_History_Panel SHALL disable the "Compare Versions" button.

### Requirement 6: Version Download

**User Story:** As a document manager, I want to download any version of a document, so that I can access previous file revisions.

#### Acceptance Criteria

1. THE Version_History_Panel SHALL display a download button for each version entry.
2. WHEN a user clicks the download button for a version, THE API_Client SHALL request the file using the version's storage key and trigger a browser file-save dialog with the filename formatted as the original document name suffixed with the version number (e.g., "DocumentName_v1.0.ext").
3. THE Version_Detail_View SHALL include a download button for the currently displayed version.
4. WHILE a download is in progress, THE download button SHALL display a loading indicator and be disabled to prevent duplicate requests.
5. IF a download request fails due to a network error or a non-2xx API response, THEN THE API_Client SHALL display an error notification indicating the download failed and re-enable the download button.
6. IF a download does not complete within 30 seconds, THEN THE API_Client SHALL abort the request, display a timeout error notification, and re-enable the download button.

### Requirement 7: Enhanced Version Upload

**User Story:** As a document manager, I want a clear and validated upload experience when creating new versions, so that I can avoid errors and provide proper change documentation.

#### Acceptance Criteria

1. THE Version_Upload_Form SHALL validate that the selected file has a size greater than 0 bytes and does not exceed 500 MB.
2. THE Version_Upload_Form SHALL validate that the change reason, after trimming leading and trailing whitespace, is between 1 and 2000 characters.
3. THE Version_Upload_Form SHALL display the selected file's name and size (formatted in KB for files under 1 MB, or MB with one decimal place for files 1 MB and above) before submission.
4. WHEN the upload succeeds, THE Version_Upload_Form SHALL close and the Version_History_Panel SHALL refresh to show the new version.
5. IF the upload fails, THEN THE Version_Upload_Form SHALL display the error message returned by the API and remain open for correction.
6. WHILE an upload is in progress, THE Version_Upload_Form SHALL disable the submit button and display a loading indicator.
7. THE Version_Upload_Form SHALL support drag-and-drop file selection in addition to the file picker button.
8. THE Version_Upload_Form SHALL require the user to select a version type ("major" or "minor") before submission and display a validation error if no version type is selected.

### Requirement 8: Version Fetching from API

**User Story:** As a developer, I want the Document_Store to support fetching individual version details, so that the UI can display version-specific data.

#### Acceptance Criteria

1. THE Document_Store SHALL provide a `fetchVersion` action that accepts a document UUID (string), major version (integer), and minor version (integer) as parameters and calls GET /api/documents/{document_uuid}/versions/{major_version}/{minor_version}.
2. WHEN `fetchVersion` is called, THE Document_Store SHALL set loading state to true, clear any existing error state, and clear the current `selectedVersion` to null before initiating the API request.
3. WHEN the API returns a successful response, THE Document_Store SHALL store the fetched version object in a `selectedVersion` state field and set loading state to false.
4. IF the API returns a 404 for a version request, THEN THE Document_Store SHALL set loading state to false, set `selectedVersion` to null, and set an error state with the message "Version not found".
5. IF the API returns a non-404 error or the network request fails, THEN THE Document_Store SHALL set loading state to false, set `selectedVersion` to null, and set an error state with a message derived from the error response.
6. WHILE a version fetch is in progress, THE Document_Store SHALL maintain loading state as true until the request completes with either success or failure.
