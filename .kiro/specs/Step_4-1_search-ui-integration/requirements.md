# Requirements Document

## Introduction

This feature integrates the Search UI (frontend) with the existing hybrid search API (backend), transforming the static search page shell into a fully functional search experience. The implementation connects the SearchPage component to the searchStore and apiClient, extends the backend search API to support faceted filtering and enriched metadata, and delivers a polished user experience with relevance score visualization, text excerpt highlighting, faceted filtering by document type/status/tags, pagination, debounced search-as-you-type, keyboard navigation, and comprehensive accessibility support. The backend search logic itself remains a placeholder (keyword matching); this phase focuses on the API contract extensions and full frontend integration.

## Glossary

- **Search_Page**: The React page component at `/search` that provides the search input, faceted filter sidebar, result list, and pagination controls.
- **Search_Store**: The Zustand state store (`searchStore.ts`) managing search query, results, filters, pagination state, loading/error states, and exposing actions for search execution.
- **Search_API**: The FastAPI router at `POST /api/search` that accepts structured search requests and returns ranked results with metadata.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and the `X-Change-Reason` audit header.
- **Faceted_Filter**: A UI control that allows narrowing search results by discrete metadata categories (document_type, status, tags) sent as filter parameters in the search request.
- **Relevance_Score**: A floating-point value between 0.0 and 1.0 representing how closely a result matches the query, displayed as a visual bar in the result card.
- **Search_Result_Card**: A UI component rendering a single search result with title, version, relevance score bar, highlighted excerpt, and metadata badges.
- **Debounce_Timer**: A delay mechanism (300ms) that prevents excessive API calls while the user is actively typing, triggering search only after typing pauses.
- **Knowledge_Service**: The backend service performing hybrid search (BM25 + kNN placeholder) with ABAC filtering and CSV record exclusion.
- **ABAC_Filter**: Attribute-Based Access Control filtering applied server-side to ensure users only see documents they are permitted to access.

## Requirements

### Requirement 1: Extended Search API Request Schema

**User Story:** As a frontend developer, I want the search API to accept filter and pagination parameters, so that the UI can implement faceted filtering and paginated result navigation.

#### Acceptance Criteria

1. THE Search_API SHALL accept the following additional optional fields in the `SearchRequest` body: `filters` (object with optional keys `document_type` as list of strings, `status` as list of strings, and `tags` as list of strings), `offset` (integer, minimum 0, default 0), and `sort_by` (string enum of "relevance" or "date", default "relevance").
2. WHEN `filters` is provided with one or more non-empty lists, THE Knowledge_Service SHALL include only documents whose metadata matches at least one value in each specified filter category (AND logic between categories, OR logic within a category).
3. WHEN `offset` is provided, THE Knowledge_Service SHALL skip the first `offset` results before returning up to `limit` results, enabling offset-based pagination.
4. WHEN `sort_by` is "date", THE Knowledge_Service SHALL sort results by the document `updated_at` field descending (most recent first) instead of by relevance score.
5. IF `offset` is negative, THEN THE Search_API SHALL return HTTP 422 with a validation error indicating that offset must be non-negative.
6. IF `filters` contains an empty object (no keys or all keys are empty lists), THEN THE Search_API SHALL treat the request as unfiltered and return all matching results.

### Requirement 2: Extended Search API Response Schema

**User Story:** As a frontend developer, I want search results to include document metadata and total count for pagination, so that the UI can display rich result cards and calculate page navigation.

#### Acceptance Criteria

1. THE Search_API SHALL return each result with the following additional fields beyond the existing schema: `document_type` (string or null), `status` (string or null), `tags` (list of strings, empty list if none), `created_at` (ISO 8601 datetime string or null), and `updated_at` (ISO 8601 datetime string or null).
2. THE Search_API SHALL return a `total_available` field (integer) in the response representing the total number of matching results before pagination is applied, enabling the frontend to calculate total pages.
3. THE Search_API SHALL return an `offset` field (integer) in the response echoing the offset used, so the frontend can track current pagination position.
4. THE Search_API SHALL return a `filters_applied` field (object mirroring the filters from the request, or an empty object if no filters were applied) to confirm which filters are active.
5. WHEN no results match the query and filters, THE Search_API SHALL return an empty `results` list with `total` set to 0, `total_available` set to 0, and the `query` echoed back.

### Requirement 3: Search Store Implementation

**User Story:** As a frontend developer, I want the search store to manage the complete search lifecycle (query, filters, pagination, results, loading, errors), so that all search-related components share consistent state.

#### Acceptance Criteria

1. THE Search_Store SHALL maintain state for: `query` (string), `results` (array of search result objects), `isSearching` (boolean), `error` (string or null), `filters` (object with `document_type`, `status`, and `tags` arrays), `offset` (integer), `limit` (integer, default 20), `totalAvailable` (integer), and `sortBy` (string, default "relevance").
2. WHEN the `search` action is called, THE Search_Store SHALL set `isSearching` to true, clear `error`, send a POST request to `/api/search` via the API_Client with the current `query`, `filters`, `offset`, `limit`, and `sort_by` in the body and `X-Change-Reason` set to "Document search query", store the response results and `total_available` on success, and set `isSearching` to false.
3. IF the search request fails due to a network or server error, THEN THE Search_Store SHALL set `error` to the error message, set `results` to an empty array, set `totalAvailable` to 0, and set `isSearching` to false.
4. WHEN a filter is toggled via `setFilter(category, value)`, THE Search_Store SHALL add or remove the value from the specified filter category array, reset `offset` to 0, and automatically trigger a new search with the updated filters.
5. WHEN `setQuery` is called, THE Search_Store SHALL update the `query` state without triggering a search (the debounce mechanism in the UI component handles search triggering).
6. WHEN `nextPage` is called, THE Search_Store SHALL increment `offset` by `limit` (only if `offset + limit < totalAvailable`) and trigger a new search.
7. WHEN `previousPage` is called, THE Search_Store SHALL decrement `offset` by `limit` (minimum 0) and trigger a new search.
8. WHEN `clearResults` is called, THE Search_Store SHALL reset `query` to empty string, `results` to empty array, `filters` to empty arrays, `offset` to 0, `totalAvailable` to 0, `error` to null, and `sortBy` to "relevance".
9. THE Search_Store SHALL skip execution of the `search` action if `isSearching` is already true (request deduplication to prevent concurrent searches).

### Requirement 4: Search Page — Query Input and Debounced Search

**User Story:** As a user, I want to type a search query and see results appear automatically after a brief pause, so that I get immediate feedback without needing to click a button.

#### Acceptance Criteria

1. WHEN the user types in the search input field, THE Search_Page SHALL update the Search_Store query state on each keystroke and start a 300ms debounce timer that triggers the `search` action when the timer expires without further input.
2. WHEN the user presses the Enter key while the search input is focused, THE Search_Page SHALL immediately cancel any pending debounce timer and trigger the `search` action with the current query value.
3. WHEN the user presses the Escape key while the search input is focused, THE Search_Page SHALL clear the search input, call `clearResults` on the Search_Store, and return focus to the search input.
4. WHEN the user clicks the "Search" button, THE Search_Page SHALL immediately cancel any pending debounce timer and trigger the `search` action with the current query value.
5. IF the query is empty or contains only whitespace when a search would be triggered, THEN THE Search_Page SHALL not send a search request and SHALL call `clearResults` on the Search_Store.
6. THE Search_Page SHALL display the search input with a placeholder text "Search documents..." and a search icon, matching the existing UI shell layout.

### Requirement 5: Search Results Display

**User Story:** As a user, I want search results displayed with titles, relevance indicators, and text excerpts with highlighted terms, so that I can quickly assess which documents are relevant to my query.

#### Acceptance Criteria

1. WHEN search results are returned, THE Search_Page SHALL render each result as a Search_Result_Card containing: the document title as a clickable link, the document version as a badge, a horizontal relevance score bar (width proportional to `relevance_score`, 0-100%), the text excerpt with query terms visually highlighted using a `<mark>` element, and metadata badges for document_type and status.
2. WHEN the user clicks a result title or the result card, THE Search_Page SHALL navigate to the document detail page at `/documents/{document_uuid}`.
3. THE Search_Page SHALL display the total result count above the result list in the format "{total_available} results found for '{query}'".
4. WHILE `isSearching` is true, THE Search_Page SHALL display a loading skeleton placeholder in the results area (pulsing placeholder cards) and disable the search button.
5. WHEN the results array is empty and `isSearching` is false and a query has been submitted, THE Search_Page SHALL display an empty state with the message "No results found for '{query}'" and a suggestion to "Try different keywords or adjust your filters".
6. WHEN no search has been performed yet (initial page load), THE Search_Page SHALL display the existing placeholder state with the search icon and instructional text "Enter a query to search across all documents".
7. IF the Search_Store `error` is not null, THEN THE Search_Page SHALL display an error alert with the error message and a "Retry" button that re-triggers the search action with the current query and filters.

### Requirement 6: Faceted Filtering Sidebar

**User Story:** As a user, I want to filter search results by document type, status, and tags using a sidebar, so that I can narrow down results to find specific categories of documents.

#### Acceptance Criteria

1. THE Search_Page SHALL render a filter sidebar to the left of the results list containing three collapsible filter sections: "Document Type", "Status", and "Tags".
2. WHEN search results are returned, THE Search_Page SHALL populate each filter section with checkbox options derived from the distinct values present in the current result set metadata (document_type, status, tags fields).
3. WHEN the user checks or unchecks a filter checkbox, THE Search_Page SHALL call `setFilter` on the Search_Store with the category and value, triggering a new filtered search with offset reset to 0.
4. THE Search_Page SHALL visually indicate active filters by showing a count badge on each filter section header (e.g., "Status (2)") and displaying selected filter values as removable chips above the results list.
5. WHEN the user clicks a filter chip's remove button, THE Search_Page SHALL remove that filter value from the Search_Store and trigger a new search.
6. THE Search_Page SHALL provide a "Clear all filters" button that resets all filter arrays to empty and triggers a new unfiltered search.
7. WHILE no search has been performed or results are empty, THE Search_Page SHALL display the filter sidebar sections in a disabled/collapsed state with a message "Perform a search to see available filters".

### Requirement 7: Pagination Controls

**User Story:** As a user, I want to navigate through pages of search results, so that I can browse beyond the initial set of results.

#### Acceptance Criteria

1. WHEN `totalAvailable` exceeds `limit`, THE Search_Page SHALL render pagination controls below the results list showing: a "Previous" button, current page indicator in the format "Page {current_page} of {total_pages}", and a "Next" button.
2. WHEN the user clicks "Next", THE Search_Page SHALL call `nextPage` on the Search_Store, scroll the results area to the top, and display the next page of results.
3. WHEN the user clicks "Previous", THE Search_Page SHALL call `previousPage` on the Search_Store, scroll the results area to the top, and display the previous page of results.
4. WHILE the current offset is 0, THE Search_Page SHALL disable the "Previous" button.
5. WHILE `offset + limit >= totalAvailable`, THE Search_Page SHALL disable the "Next" button.
6. WHEN `totalAvailable` is less than or equal to `limit`, THE Search_Page SHALL hide the pagination controls entirely.

### Requirement 8: Accessibility and ARIA Support

**User Story:** As a user relying on assistive technology, I want the search interface to be fully accessible, so that I can effectively search and browse results using a screen reader or keyboard.

#### Acceptance Criteria

1. THE Search_Page SHALL include an `aria-label="Search documents"` on the search input and `role="search"` on the containing form element.
2. WHEN search results are loaded or updated, THE Search_Page SHALL announce the result count to screen readers using an `aria-live="polite"` region with the text "{total_available} results found" (or "No results found" when empty).
3. THE Search_Page SHALL ensure all interactive elements (search input, search button, filter checkboxes, pagination buttons, result links) are reachable via keyboard Tab navigation in a logical order.
4. THE Search_Page SHALL provide `aria-label` attributes on pagination buttons ("Go to previous page", "Go to next page") and filter checkboxes ("Filter by {category}: {value}").
5. WHILE `isSearching` is true, THE Search_Page SHALL set `aria-busy="true"` on the results container to inform assistive technology that content is loading.
6. THE Search_Page SHALL ensure all relevance score bars have `role="meter"`, `aria-valuenow` set to the score percentage, `aria-valuemin="0"`, `aria-valuemax="100"`, and `aria-label="Relevance score: {percentage}%"`.

### Requirement 9: Error Handling and Edge Cases

**User Story:** As a user, I want graceful handling of errors and edge cases during search, so that I always understand the system state and can recover from failures.

#### Acceptance Criteria

1. IF the search API returns HTTP 422 (validation error), THEN THE Search_Page SHALL display an inline error message below the search input indicating the validation issue (e.g., "Query must be between 1 and 1000 characters").
2. IF the search API returns HTTP 500 or a network timeout, THEN THE Search_Page SHALL display an error alert with the message "Search is temporarily unavailable. Please try again." and a "Retry" button.
3. IF the user's session expires during a search (API_Client throws "Session expired"), THEN THE Search_Page SHALL not display a search error and SHALL allow the API_Client's existing redirect-to-login flow to handle the session expiry.
4. WHEN the user submits a query that exceeds 1000 characters, THE Search_Page SHALL truncate the query to 1000 characters before sending the request and display a brief notification "Query truncated to 1000 characters".
5. IF the search API returns results where `relevance_score` is outside the 0.0-1.0 range, THEN THE Search_Page SHALL clamp the displayed score to the 0.0-1.0 range for the visual bar rendering.

### Requirement 10: Sort Control

**User Story:** As a user, I want to switch between sorting results by relevance and by date, so that I can find either the most relevant or the most recently updated documents.

#### Acceptance Criteria

1. THE Search_Page SHALL display a sort dropdown above the results list with options "Most Relevant" (value "relevance") and "Most Recent" (value "date"), defaulting to "Most Relevant".
2. WHEN the user changes the sort selection, THE Search_Store SHALL update `sortBy` to the selected value, reset `offset` to 0, and trigger a new search with the updated sort parameter.
3. THE Search_Page SHALL visually indicate the currently active sort option in the dropdown.

