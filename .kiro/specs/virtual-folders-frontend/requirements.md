# Requirements Document

## Introduction

This feature connects the existing static Virtual Folders page in the React frontend to the real FastAPI backend API at `/api/virtual-folders`. It replaces hardcoded folder data with live API calls, implements full CRUD operations (create, rename, delete), provides a tag-based filter builder UI for defining folder criteria, and enables browsing documents within a selected folder. The backend is already complete — this is a frontend-only integration effort.

## Glossary

- **Virtual_Folders_Page**: The React page component at `src/frontend/src/pages/VirtualFoldersPage.tsx` that displays the folder list, CRUD controls, and folder document view.
- **Virtual_Folder_Store**: A Zustand state store managing virtual folder state, API interactions, and selected folder context.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and audit compliance headers.
- **Virtual_Folder_API**: The FastAPI router at `/api/virtual-folders` providing folder CRUD and document listing endpoints.
- **Tag_Filter**: A JSON object defining filter criteria for a virtual folder (e.g., `{"tags": ["SOP"]}`, `{"status": "Active"}`, or combined `{"tags": ["Report"], "status": "Draft"}`).
- **System_Default_Folder**: A virtual folder with `is_system_default: true` that cannot be deleted or renamed by users.
- **Create_Folder_Dialog**: A modal dialog component for creating a new virtual folder with name and tag filter configuration.
- **Edit_Folder_Dialog**: A modal dialog component for editing an existing virtual folder's name and tag filter.
- **Filter_Builder**: A UI component that allows users to visually construct Tag_Filter JSON expressions by selecting tags and status values.
- **Folder_Document_View**: A sub-view within the Virtual_Folders_Page that displays documents matching a selected folder's Tag_Filter.
- **Change_Reason_Header**: The `X-Change-Reason` HTTP header required on all mutating requests (POST, PUT, DELETE) for ALCOA+ audit compliance.

## Requirements

### Requirement 1: Fetch and Display Virtual Folder List

**User Story:** As a user, I want to see all virtual folders (system defaults and user-created) on the Virtual Folders page, so that I can browse document categories.

#### Acceptance Criteria

1. WHEN the Virtual_Folders_Page mounts, THE Virtual_Folder_Store SHALL fetch folders from the Virtual_Folder_API using `GET /api/virtual-folders`.
2. WHILE the Virtual_Folder_Store is loading folders, THE Virtual_Folders_Page SHALL display a loading indicator in place of the folder list.
3. WHEN the Virtual_Folder_API returns a successful response, THE Virtual_Folders_Page SHALL render each folder as a list item showing: the folder name, a comma-separated list of the tag names from the folder's tag_filter (e.g., "SOP, Report") or the status value if no tags are present, and a visual "System Default" badge if is_system_default is true.
4. THE Virtual_Folders_Page SHALL display System_Default_Folders before user-created folders in the list, preserving the sort order returned by the API (is_system_default DESC, name ASC).
5. WHEN the Virtual_Folder_API returns an empty result set, THE Virtual_Folders_Page SHALL display an empty state message indicating no folders exist.
6. IF the Virtual_Folder_API returns an error (HTTP status 4xx or 5xx), THEN THE Virtual_Folders_Page SHALL hide the loading indicator and display an error message indicating the folder list could not be loaded, along with a retry button that re-triggers the fetch.
7. IF the Virtual_Folder_API request does not respond within 15 seconds, THEN THE Virtual_Folders_Page SHALL abort the request and display the same error state as criterion 6.

### Requirement 2: Create Virtual Folder

**User Story:** As a user, I want to create a new virtual folder with a name and tag filter, so that I can organize documents into custom views.

#### Acceptance Criteria

1. WHEN the user clicks the "Create Folder" button, THE Virtual_Folders_Page SHALL open the Create_Folder_Dialog.
2. THE Create_Folder_Dialog SHALL require the user to provide a folder name between 1 and 200 characters, rejecting names that are empty or contain only whitespace, and SHALL display inline validation feedback when the name does not meet these constraints.
3. THE Create_Folder_Dialog SHALL provide the Filter_Builder for constructing a Tag_Filter expression and SHALL disable the submit button until the user has constructed a non-empty Tag_Filter.
4. THE Create_Folder_Dialog SHALL allow the user to select a sort order from the following options: "created_at_desc", "created_at_asc", "name_asc", "name_desc", with "created_at_desc" selected by default.
5. WHEN the user submits the Create_Folder_Dialog, THE Virtual_Folder_Store SHALL send a POST request to `POST /api/virtual-folders` with the name, tag_filter, and sort_order, including the Change_Reason_Header.
6. WHEN the creation completes successfully, THE Virtual_Folder_Store SHALL refresh the folder list and THE Create_Folder_Dialog SHALL close.
7. IF the Virtual_Folder_API returns a 400 error indicating a duplicate name, THEN THE Create_Folder_Dialog SHALL display a validation message stating the folder name already exists.
8. IF the Virtual_Folder_API returns a non-400 error or the request fails due to a network error, THEN THE Create_Folder_Dialog SHALL display an error message indicating the folder could not be created, re-enable the submit button, and preserve the user's entered data.
9. WHILE the creation request is in progress, THE Create_Folder_Dialog SHALL disable the submit button and display a loading indicator.

### Requirement 3: Edit Virtual Folder

**User Story:** As a user, I want to rename a folder or update its tag filter, so that I can adjust my document views over time.

#### Acceptance Criteria

1. WHEN the user triggers the edit action on a folder, THE Virtual_Folders_Page SHALL open the Edit_Folder_Dialog pre-populated with the folder's current name, Tag_Filter, and sort order.
2. THE Edit_Folder_Dialog SHALL allow the user to modify the folder name, accepting 1–200 characters and rejecting input that is empty or contains only whitespace.
3. THE Edit_Folder_Dialog SHALL provide the Filter_Builder pre-populated with the folder's current Tag_Filter.
4. THE Edit_Folder_Dialog SHALL allow the user to modify the sort order value, accepting 0–50 characters.
5. WHEN the user submits the Edit_Folder_Dialog, THE Virtual_Folder_Store SHALL send a PUT request to `PUT /api/virtual-folders/{id}` containing only the fields whose values differ from the pre-populated values, including the Change_Reason_Header.
6. WHEN the update completes successfully, THE Virtual_Folder_Store SHALL refresh the folder list and THE Edit_Folder_Dialog SHALL close.
7. IF the Virtual_Folder_API returns a 400 error indicating a duplicate name, THEN THE Edit_Folder_Dialog SHALL display a validation message stating the folder name already exists.
8. IF the Virtual_Folder_API returns a non-duplicate-name error (network failure, timeout, or server error), THEN THE Edit_Folder_Dialog SHALL display an error message indicating the update failed and SHALL retain the user's entered values.
9. WHILE the update request is in progress, THE Edit_Folder_Dialog SHALL disable the submit button and display a loading indicator.
10. WHEN the user triggers the cancel action on the Edit_Folder_Dialog, THE Edit_Folder_Dialog SHALL close without sending a request and without modifying the folder.

### Requirement 4: Delete Virtual Folder

**User Story:** As a user, I want to delete a user-created virtual folder, so that I can remove views I no longer need.

#### Acceptance Criteria

1. WHEN the user triggers the delete action on a user-created folder, THE Virtual_Folders_Page SHALL display a confirmation dialog stating the folder will be permanently removed and providing a text input for the user to enter a change reason.
2. IF the user cancels the confirmation dialog, THEN THE Virtual_Folders_Page SHALL close the dialog and take no further action.
3. WHEN the user confirms deletion, THE Virtual_Folder_Store SHALL send a DELETE request to `DELETE /api/virtual-folders/{id}`, including the Change_Reason_Header populated with the user-entered change reason from the confirmation dialog.
4. WHILE the delete request is in progress, THE confirmation dialog SHALL disable the confirm button and display a loading indicator.
5. WHEN the deletion completes successfully, THE Virtual_Folder_Store SHALL remove the folder from the local state, refresh the folder list, and if the deleted folder was the currently selected folder, navigate the user back to the folder list view.
6. IF the Virtual_Folder_API returns a 404 error, THEN THE Virtual_Folders_Page SHALL display an error message indicating the folder was not found and refresh the folder list.
7. IF the Virtual_Folder_API returns a 400 error indicating a system default folder, THEN THE Virtual_Folders_Page SHALL display an error message stating system default folders cannot be deleted.
8. THE Virtual_Folders_Page SHALL NOT display the delete action on System_Default_Folders.

### Requirement 5: System Default Folder Protection

**User Story:** As a user, I want system default folders to be visually distinct and protected from modification, so that I always have access to standard document views.

#### Acceptance Criteria

1. THE Virtual_Folders_Page SHALL display a "System" badge on each System_Default_Folder.
2. THE Virtual_Folders_Page SHALL NOT display the delete action on System_Default_Folders.
3. THE Virtual_Folders_Page SHALL NOT display the edit action on System_Default_Folders.
4. THE Virtual_Folders_Page SHALL render each System_Default_Folder with a folder icon that is visually different from the icon used for user-created folders, so that the two folder types are distinguishable without reading the badge text.
5. IF the Virtual_Folder_API returns a 400 error when a delete or edit operation is attempted on a System_Default_Folder, THEN THE Virtual_Folders_Page SHALL display an error message indicating that system default folders cannot be modified.

### Requirement 6: Browse Documents Within a Folder

**User Story:** As a user, I want to click on a folder and see the documents matching its filter, so that I can quickly access relevant documents.

#### Acceptance Criteria

1. WHEN the user clicks on a folder in the list, THE Virtual_Folders_Page SHALL navigate to the Folder_Document_View for that folder.
2. WHEN the Folder_Document_View loads, THE Virtual_Folder_Store SHALL fetch documents from `GET /api/virtual-folders/{id}/documents` with offset=0 and limit=20.
3. THE Folder_Document_View SHALL display each document as a row showing its document_uuid, title, document_type, current_status, tag names, and created_at timestamp, ordered by created_at descending.
4. THE Folder_Document_View SHALL display the folder name as a heading and provide a back navigation link that returns the user to the folder list.
5. WHILE the Virtual_Folder_Store is fetching documents, THE Folder_Document_View SHALL display a loading indicator.
6. WHEN the Virtual_Folder_API returns an empty document list, THE Folder_Document_View SHALL display an empty state message indicating no documents match the folder's filter.
7. IF the Virtual_Folder_API returns an error, THEN THE Folder_Document_View SHALL display an error message indicating the fetch failed and hide the document list.

### Requirement 7: Paginated Document Browsing Within Folder

**User Story:** As a user, I want to page through documents within a folder, so that I can navigate large result sets.

#### Acceptance Criteria

1. THE Virtual_Folder_Store SHALL request folder documents with `offset` and `limit` query parameters, where `offset` defaults to 0 and `limit` defaults to 20 (minimum 1, maximum 100).
2. WHEN the user navigates to the next page, THE Virtual_Folder_Store SHALL fetch the next set of documents by incrementing the current offset by the current `limit` value.
3. WHEN the user navigates to the previous page, THE Virtual_Folder_Store SHALL fetch the previous set of documents by decrementing the current offset by the current `limit` value, with a minimum offset of 0.
4. WHILE the current offset is 0, THE Folder_Document_View SHALL disable the previous-page control.
5. WHILE the number of documents returned by the last fetch is less than the current `limit` value, THE Folder_Document_View SHALL disable the next-page control.
6. IF the folder documents fetch fails, THEN THE Virtual_Folder_Store SHALL store an error message and set the loading state to false.

### Requirement 8: Tag Filter Builder UI

**User Story:** As a user, I want a visual interface for building tag filter expressions, so that I can define folder criteria without writing JSON manually.

#### Acceptance Criteria

1. THE Filter_Builder SHALL provide a multi-select input that displays available tags retrieved from the DocumentTag table, allowing the user to select between 1 and 20 tags to include in the filter.
2. THE Filter_Builder SHALL provide a dropdown for selecting a single document status value from the set: "Draft", "Active", "Approved", "InTraining", "Retired".
3. THE Filter_Builder SHALL allow combining tag selection and status selection into a single Tag_Filter expression by automatically merging both selections when present.
4. WHEN the user selects tags, THE Filter_Builder SHALL produce a Tag_Filter with the structure `{"tags": [selected_tags]}`.
5. WHEN the user selects a status, THE Filter_Builder SHALL produce a Tag_Filter with the structure `{"status": selected_status}`.
6. WHEN the user selects both tags and a status, THE Filter_Builder SHALL produce a combined Tag_Filter with the structure `{"tags": [selected_tags], "status": selected_status}`.
7. WHEN the user changes a tag or status selection, THE Filter_Builder SHALL update the displayed JSON preview of the resulting Tag_Filter within 300 milliseconds.
8. IF no tags and no status are selected, THEN THE Filter_Builder SHALL display the preview as an empty object `{}` and SHALL disable the confirmation action until at least one tag or one status is selected.
9. WHEN the user deselects all tags from the multi-select while a status is still selected, THE Filter_Builder SHALL produce a Tag_Filter with only the status field: `{"status": selected_status}`.

### Requirement 9: Virtual Folder Store State Management

**User Story:** As a developer, I want a dedicated Zustand store for virtual folder state, so that folder data and operations are centralized and testable.

#### Acceptance Criteria

1. THE Virtual_Folder_Store SHALL maintain a `folders` array property containing all fetched VirtualFolderResponse objects, initialized as an empty array.
2. THE Virtual_Folder_Store SHALL maintain a `selectedFolder` property (VirtualFolderResponse or null, initialized as null) and a `selectedFolderDocuments` array property (DocumentResponse[], initialized as empty array) representing the currently selected folder and its documents.
3. THE Virtual_Folder_Store SHALL expose the following actions: `fetchFolders` (no parameters), `createFolder` (accepts name, tag_filter, sort_order), `updateFolder` (accepts folder id and updatable fields: name, tag_filter, sort_order), `deleteFolder` (accepts folder id), and `fetchFolderDocuments` (accepts folder id).
4. THE Virtual_Folder_Store SHALL track loading and error states using separate property pairs: `isFoldersLoading` (boolean) and `foldersError` (string or null) for folder list operations, and `isDocumentsLoading` (boolean) and `documentsError` (string or null) for document fetch operations.
5. WHEN a mutating action (create, update, delete) succeeds, THE Virtual_Folder_Store SHALL automatically call `fetchFolders` to refresh the folder list.
6. IF a store action's API call fails, THEN THE Virtual_Folder_Store SHALL set the corresponding error property to the error message string and set the corresponding loading property to false.
7. THE Virtual_Folder_Store SHALL include the Change_Reason_Header value as an `X-Change-Reason` HTTP header in all mutating API requests (create, update, delete) sent via the API_Client, passing a descriptive reason string for each operation.
8. WHEN `fetchFolders` is called, THE Virtual_Folder_Store SHALL set `isFoldersLoading` to true and `foldersError` to null before making the API request, and set `isFoldersLoading` to false upon completion.

### Requirement 10: Navigation Between Folder List and Folder View

**User Story:** As a user, I want seamless navigation between the folder list and the document view within a folder, so that I can move between views without losing context.

#### Acceptance Criteria

1. WHEN the user clicks a folder, THE Virtual_Folders_Page SHALL transition to the Folder_Document_View by rendering the document list component in place without triggering a full browser page reload.
2. WHEN the Virtual_Folders_Page transitions to the Folder_Document_View, THE Virtual_Folders_Page SHALL update the browser URL to include the selected folder identifier (e.g., /folders/:folderId) so that browser back/forward navigation and direct linking are supported.
3. THE Folder_Document_View SHALL display a back button that, when activated, returns the user to the folder list view.
4. WHEN the user navigates back to the folder list via the back button or browser back action, THE Virtual_Folders_Page SHALL display the previously loaded folder list from its cached state without re-fetching from the server, unless more than 300 seconds have elapsed since the last fetch.
5. WHEN the user navigates directly to a folder URL containing a folder identifier, THE Virtual_Folders_Page SHALL load and display the Folder_Document_View for that folder.
6. IF the folder identifier in the URL does not match any existing folder, THEN THE Virtual_Folders_Page SHALL display the folder list view and show an error message indicating the folder was not found.
