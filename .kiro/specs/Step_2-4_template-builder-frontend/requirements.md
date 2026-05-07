# Requirements Document

## Introduction

This feature implements the Template Builder frontend — a JSON-driven visual form builder using @hello-pangea/dnd for drag-and-drop interactions. The builder provides a three-panel layout: a field palette for selecting field types, a canvas area for arranging fields via drag-and-drop, and a field configuration panel for editing field properties. Users design template schemas visually and save them to the backend via `POST /api/templates`. The saved template schema drives deterministic PDF generation for offline data collection (REQ-PDF-01 in the URS).

## Glossary

- **Template_Builder**: The main React page component that hosts the three-panel drag-and-drop form builder interface.
- **Field_Palette**: The left panel component displaying available field types (Text, Float, Integer, Date, Boolean) as draggable items.
- **Builder_Canvas**: The center panel component where users drop and reorder fields to compose the template schema.
- **Configuration_Panel**: The right panel component that displays editable properties (label, type) for the currently selected field on the canvas.
- **Template_Store**: The Zustand state store at `src/frontend/src/stores/templateStore.ts` managing template builder state, field list, and API interactions.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, and tenant headers.
- **Template_API**: The FastAPI router at `/api/templates` providing template CRUD and PDF download endpoints.
- **Template_Schema**: The JSON object sent to the backend containing the template name and an array of field definitions (label, type).
- **Field_UUID**: A unique identifier in FLD-XXXXXXXX format assigned by the backend to each field upon template creation.
- **Document_UUID**: A unique identifier in YYYY-NNNNN format assigned by the backend to the template upon creation.
- **Canvas_Field**: A field instance placed on the Builder_Canvas, containing a client-side temporary ID, label, type, and display order.
- **DnD_Context**: The @hello-pangea/dnd DragDropContext component that wraps the builder and handles drag events between the Field_Palette and Builder_Canvas.

## Requirements

### Requirement 1: Three-Panel Builder Layout

**User Story:** As a template author, I want a clear three-panel layout with a field palette, canvas, and configuration panel, so that I can visually compose form templates.

#### Acceptance Criteria

1. WHEN the user navigates to the Template_Builder, THE Template_Builder SHALL render three distinct panels in the following order from left to right: Field_Palette, Builder_Canvas, and Configuration_Panel.
2. THE Field_Palette SHALL display exactly one draggable item for each supported field type: Text, Float, Integer, Date, and Boolean (5 items total).
3. IF no fields have been added to the Builder_Canvas, THEN THE Builder_Canvas SHALL display a drop zone placeholder indicating that fields can be dragged onto the canvas.
4. IF no Canvas_Field is selected, THEN THE Configuration_Panel SHALL display a message indicating that a field must be selected to view its configuration.
5. THE Template_Builder SHALL be wrapped in a DnD_Context to enable drag-and-drop interactions between panels.
6. WHEN the user selects a Canvas_Field on the Builder_Canvas, THE Configuration_Panel SHALL display the configuration options for the selected field.

### Requirement 2: Drag Fields from Palette to Canvas

**User Story:** As a template author, I want to drag field types from the palette onto the canvas, so that I can add fields to my template.

#### Acceptance Criteria

1. WHEN the user drags a field type from the Field_Palette and drops it onto the Builder_Canvas, THE Template_Store SHALL add a new Canvas_Field with the dropped field type, a generated client-side temporary ID (UUID v4 format), a default label equal to the field type name followed by the word "Field" (e.g., "Text Field", "Float Field"), and a field_order equal to the 0-based drop position index.
2. WHEN a new Canvas_Field is inserted at a position occupied by existing fields, THE Template_Store SHALL increment the field_order of all Canvas_Fields at or after the drop position index by 1 to maintain a contiguous 0-based sequence.
3. WHEN a field is dropped onto the Builder_Canvas, THE Builder_Canvas SHALL render the new Canvas_Field at the drop position showing its label and type.
4. THE Field_Palette items SHALL remain available after a drag operation completes, allowing the user to add multiple fields of the same type.
5. IF the user drops a field outside the Builder_Canvas, THEN THE Template_Store SHALL not add a new Canvas_Field and the Builder_Canvas SHALL remain unchanged.
6. THE Builder_Canvas SHALL accept a maximum of 50 Canvas_Fields; IF the user attempts to drop a field when 50 fields are already present, THEN THE Template_Builder SHALL display a validation message indicating the maximum field limit has been reached and SHALL not add the field.

### Requirement 3: Reorder Fields on Canvas via Drag-and-Drop

**User Story:** As a template author, I want to reorder fields on the canvas by dragging them, so that I can control the display order of fields in the template.

#### Acceptance Criteria

1. WHEN the user drags a Canvas_Field to a new position within the Builder_Canvas, THE Template_Store SHALL update the field_order of all Canvas_Fields to maintain a contiguous zero-based sequence reflecting the new arrangement.
2. WHEN a reorder operation completes, THE Builder_Canvas SHALL re-render the fields in ascending field_order sequence.
3. THE Builder_Canvas SHALL display a visible drag handle element on each Canvas_Field to indicate it is draggable.
4. WHILE a Canvas_Field is being dragged, THE Builder_Canvas SHALL display a visual placeholder element at the target drop position indicating where the field will be inserted.
5. IF the user drops a Canvas_Field at its original position, THEN THE Template_Store SHALL not modify any field_order values.
6. IF a Canvas_Field is selected when a reorder operation completes, THEN THE Template_Store SHALL preserve the current selection.

### Requirement 4: Select and Configure Fields

**User Story:** As a template author, I want to select a field on the canvas and edit its properties in the configuration panel, so that I can customize field labels and types.

#### Acceptance Criteria

1. WHEN the user clicks a Canvas_Field on the Builder_Canvas, THE Template_Store SHALL set that field as the selected field and THE Builder_Canvas SHALL visually highlight the selected Canvas_Field with a distinct border or background to distinguish it from unselected fields.
2. WHEN a Canvas_Field is selected, THE Configuration_Panel SHALL display an editable text input for the field label and a dropdown selector for the field type populated with the options: Text, Float, Integer, Date, and Boolean.
3. WHEN the user modifies the label in the Configuration_Panel, THE Template_Store SHALL update the corresponding Canvas_Field label on each input change event so the Builder_Canvas reflects the current label value without requiring a separate save action.
4. WHEN the user changes the field type in the Configuration_Panel dropdown, THE Template_Store SHALL update the corresponding Canvas_Field type.
5. THE Configuration_Panel SHALL validate the label on each input change and indicate an error state if the label is empty or exceeds 200 characters.
6. IF the label is empty, THEN THE Configuration_Panel SHALL display a validation error message indicating a label is required and THE Template_Store SHALL NOT clear the existing label from the Canvas_Field until a valid value is provided.
7. IF the label exceeds 200 characters, THEN THE Configuration_Panel SHALL display a validation error message indicating the maximum length has been exceeded.
8. WHEN the user clicks a different Canvas_Field, THE Template_Store SHALL update the selection to the newly clicked field and THE Configuration_Panel SHALL display the properties of the newly selected field.

### Requirement 5: Remove Fields from Canvas

**User Story:** As a template author, I want to remove fields from the canvas, so that I can correct mistakes while building a template.

#### Acceptance Criteria

1. WHEN the user clicks the remove action on a Canvas_Field, THE Template_Store SHALL remove that field from the canvas field list and THE Builder_Canvas SHALL no longer render the removed Canvas_Field.
2. WHEN a Canvas_Field is removed, THE Template_Store SHALL recalculate field_order values for remaining fields as a zero-based contiguous sequence (0, 1, 2, ...) reflecting their current visual order.
3. IF the removed field was the currently selected field, THEN THE Template_Store SHALL clear the selection and THE Configuration_Panel SHALL return to its empty state.
4. IF the removed field was not the currently selected field, THEN THE Template_Store SHALL preserve the current selection unchanged.
5. WHEN the last Canvas_Field is removed from the Builder_Canvas, THE Builder_Canvas SHALL display the drop zone placeholder message.

### Requirement 6: Template Name Input

**User Story:** As a template author, I want to provide a name for my template, so that it can be identified in the template list.

#### Acceptance Criteria

1. THE Template_Builder SHALL display a text input for the template name above the Builder_Canvas.
2. THE Template_Builder SHALL validate that the template name contains at least 1 non-whitespace character and does not exceed 500 characters, treating whitespace-only input as empty.
3. WHEN the template name input value changes, THE Template_Builder SHALL display an inline validation error adjacent to the input field if the current value is empty, contains only whitespace, or exceeds 500 characters, and SHALL disable the save action until the name is valid.
4. IF the user attempts to save a template with a name that already exists within the same tenant, THEN THE Template_Builder SHALL display an inline validation error indicating the name is already in use and SHALL prevent submission.

### Requirement 7: Save Template Schema to Backend

**User Story:** As a template author, I want to save my completed template to the backend, so that it is persisted and can be used for PDF generation.

#### Acceptance Criteria

1. WHEN the user clicks the Save button, THE Template_Store SHALL construct a Template_Schema JSON object containing the template name and an array of field definitions with field_label, field_type, and field_order for each Canvas_Field, ordered ascending by field_order.
2. WHEN the user clicks Save, THE Template_Store SHALL send a POST request to `POST /api/templates` with the Template_Schema as the JSON body, including the `X-Change-Reason` header set to "Template created via builder".
3. WHILE the save request is in progress, THE Template_Builder SHALL display a loading indicator on the Save button and disable the button to prevent duplicate submissions.
4. WHEN the Template_API returns a successful 201 response, THE Template_Store SHALL store the returned template (including backend-assigned Document_UUID and Field_UUIDs), remove the loading indicator, re-enable the Save button, and THE Template_Builder SHALL display a success notification that auto-dismisses after 5 seconds.
5. IF the Template_API returns a 400 error, THEN THE Template_Builder SHALL remove the loading indicator, re-enable the Save button, and display the validation error message extracted from the response body.
6. IF the Template_API returns a non-400 error or the request fails due to a network error, THEN THE Template_Builder SHALL remove the loading indicator, re-enable the Save button, and display an error notification indicating the save operation failed.
7. IF the user attempts to save with zero fields on the canvas, THEN THE Template_Store SHALL not send the save request.
8. IF the user attempts to save with zero fields on the canvas, THEN THE Template_Builder SHALL display a validation message indicating at least one field is required.
9. IF the user attempts to save with a blank or empty template name, THEN THE Template_Builder SHALL display a validation message indicating a template name is required and SHALL not send the save request.
10. WHEN the Template_API returns a successful 201 response, THE Template_Store SHALL set the template status to "ReadOnly" in the local state to reflect the backend-assigned immutable status.

### Requirement 8: Template List View

**User Story:** As a template author, I want to see a list of existing templates, so that I can review previously created templates.

#### Acceptance Criteria

1. WHEN the Templates page mounts, THE Template_Store SHALL fetch templates from `GET /api/templates` with the current tenant headers (X-Company-Id, X-User-Id).
2. WHILE the Template_Store is loading templates, THE Templates page SHALL display a loading indicator within 200 milliseconds of the fetch request being initiated.
3. WHEN the Template_API returns a successful response, THE Templates page SHALL render each template as a list item showing its Document_UUID, name, status, and field count (the number of entries in the template's fields array), ordered by Document_UUID descending (most recently created first).
4. WHEN the Template_API returns an empty list, THE Templates page SHALL display an empty state message indicating that no templates have been created yet.
5. IF the Template_API returns an error (HTTP status 4xx or 5xx), THEN THE Templates page SHALL hide the loading indicator and display an error message indicating that templates could not be loaded.
6. IF the Template_API does not respond within 30 seconds, THEN THE Templates page SHALL hide the loading indicator and display a timeout error message indicating that the request timed out.
7. WHEN the user clicks "New Template", THE Templates page SHALL navigate to the Template_Builder in creation mode.

### Requirement 9: Template Schema Serialization

**User Story:** As a developer, I want the template schema to serialize correctly to the backend-expected JSON format, so that templates are created without errors.

#### Acceptance Criteria

1. WHEN the user triggers template creation, THE Template_Store SHALL serialize the canvas fields into the format: `{ "name": string (1–500 characters), "json_schema": { "fields": [{ "label": string (1–200 characters), "type": "Text" | "Float" | "Integer" | "Date" | "Boolean" }] }, "user_id": number }`.
2. THE Template_Store SHALL order fields in the serialized `json_schema.fields` array by their `field_order` value in ascending numeric order.
3. WHEN the Template_Store serializes a canvas state containing at least one field with a non-empty label and a valid type, THEN deserializing the backend response SHALL produce a field list where each entry matches the original label and type in the same order.
4. THE Template_Store SHALL exclude the `field_uuid`, `field_order`, and any client-generated `id` properties from the serialized payload sent to the backend.
5. IF the canvas state contains zero fields or any field has an empty label, THEN THE Template_Store SHALL prevent submission and not send a request to the backend.

### Requirement 10: Keyboard Accessibility

**User Story:** As a user relying on keyboard navigation, I want to operate the template builder without a mouse, so that the tool is accessible.

#### Acceptance Criteria

1. THE Field_Palette items SHALL be focusable via keyboard Tab navigation in the order they appear visually (Text, Float, Integer, Date, Boolean).
2. THE Canvas_Fields SHALL be focusable via keyboard Tab navigation in field_order sequence (ascending).
3. THE Configuration_Panel form inputs SHALL be reachable via keyboard Tab navigation.
4. WHEN a Canvas_Field has focus, THE Builder_Canvas SHALL visually indicate the focused field with an outline that has a minimum contrast ratio of 3:1 against adjacent colors and a minimum thickness of 2px, conforming to WCAG 2.4.7.
5. THE Template_Builder SHALL support @hello-pangea/dnd keyboard drag-and-drop interactions: Space to lift a focused item, arrow keys to move it within the list, Space to drop it at the current position, and Escape to cancel the drag and return the item to its original position.
6. WHEN a Canvas_Field has focus, THE Builder_Canvas SHALL allow the user to activate the remove action for that field via keyboard (Enter or Delete key on the remove control), without requiring a mouse click.
7. WHILE a keyboard drag-and-drop operation is in progress, THE Template_Builder SHALL provide screen-reader-accessible live announcements indicating the current drag state (item lifted, current position, item dropped, or drag cancelled).
8. THE Template_Builder SHALL maintain a logical tab order progressing from the template name input, to the Field_Palette, to the Builder_Canvas, to the Configuration_Panel, and finally to the Save button.

### Requirement 11: Unsaved Changes Warning

**User Story:** As a template author, I want to be warned before navigating away with unsaved changes, so that I do not accidentally lose my work.

#### Acceptance Criteria

1. WHILE the Builder_Canvas contains one or more Canvas_Fields that have been added, removed, or reordered since the last successful save, or the template name has been modified since the last successful save, THE Template_Store SHALL track the builder state as "dirty".
2. WHILE the state is dirty, WHEN the user attempts to navigate away from the Template_Builder via in-app routing or browser back/forward navigation, THE Template_Builder SHALL display a confirmation dialog warning about unsaved changes and presenting a confirm option and a cancel option.
3. WHILE the state is dirty, WHEN the user attempts to close the browser tab or refresh the page, THE Template_Builder SHALL trigger the browser's native beforeunload confirmation prompt.
4. WHEN the user selects the confirm option in the unsaved changes dialog, THE Template_Builder SHALL allow the navigation to proceed.
5. WHEN the user selects the cancel option in the unsaved changes dialog, THE Template_Builder SHALL keep the user on the Template_Builder page with all Canvas_Fields and template name preserved.
6. WHEN the Template_API returns a successful 201 response after a save operation, THE Template_Store SHALL reset the builder state from "dirty" to clean.
