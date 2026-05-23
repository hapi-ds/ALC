# Implementation Plan: Search UI Integration

## Overview

This plan implements the full search UI integration by extending the backend search API with filtering, pagination, and sorting support, then rewriting the frontend searchStore and SearchPage from stubs into a fully functional search experience with faceted filtering, debounced search-as-you-type, pagination, sort controls, and comprehensive accessibility. The implementation proceeds from backend schema extensions → backend service logic → backend property tests → frontend store → frontend components → frontend property tests → integration wiring.

## Tasks

- [x] 1. Backend API schema and service extensions
  - [x] 1.1 Extend SearchRequest and SearchResponse schemas
    - Add `SearchFilters` model with `document_type`, `status`, `tags` (all `list[str]` with `default_factory=list`)
    - Extend `SearchRequest` with `filters: SearchFilters | None = Field(default=None)`, `offset: int = Field(default=0, ge=0)`, `sort_by: Literal["relevance", "date"] = Field(default="relevance")`
    - Extend `SearchResultResponse` with `document_type: str | None = None`, `status: str | None = None`, `tags: list[str] = Field(default_factory=list)`, `created_at: str | None = None`, `updated_at: str | None = None`
    - Extend `SearchResponse` with `total_available: int`, `offset: int`, `filters_applied: dict[str, list[str]] = Field(default_factory=dict)`
    - Add `from typing import Literal` import
    - Target file: `src/backend/src/alcoabase/api/search.py`
    - _Requirements: 1.1, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 1.2 Extend KnowledgeService.hybrid_search signature and logic
    - Update `hybrid_search` method signature to accept `filters: dict[str, list[str]] | None = None`, `offset: int = 0`, `sort_by: str = "relevance"`
    - Change return type to `tuple[list[SearchResult], int]` (results, total_available)
    - Add `SearchResult` dataclass fields: `document_type`, `status`, `tags`, `created_at`, `updated_at`
    - Implement filter logic: AND between categories, OR within a category — iterate results and keep only those matching all non-empty filter categories
    - Implement sort logic: if `sort_by == "date"`, sort by `updated_at` descending; otherwise sort by `relevance_score` descending
    - Implement pagination: compute `total_available = len(filtered_results)`, then slice `filtered_results[offset:offset+limit]`
    - Target file: `src/backend/src/alcoabase/services/knowledge_service.py`
    - _Requirements: 1.2, 1.3, 1.4, 2.2_

  - [x] 1.3 Update search router endpoint handler
    - Update `hybrid_search` endpoint to map `request.filters` to a dict (filtering out empty lists)
    - Unpack the tuple return `(results, total_available)` from the service call
    - Pass `filters`, `offset`, `sort_by` to the service
    - Build `filters_applied` dict from request filters (non-empty lists only)
    - Map extended result fields (`document_type`, `status`, `tags`, `created_at`, `updated_at`) into `SearchResultResponse`
    - Return extended `SearchResponse` with `total_available`, `offset`, `filters_applied`
    - Target file: `src/backend/src/alcoabase/api/search.py`
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2. Backend property tests
  - [x] 2.1 Write property test for filter AND/OR semantics
    - **Property 1: Filter logic preserves AND/OR semantics**
    - Generate random document sets with varied `document_type`, `status`, `tags` metadata
    - Generate random filter combinations (subsets of existing metadata values)
    - Verify: results contain only documents matching at least one value per non-empty filter category, AND this holds for all non-empty categories simultaneously
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: Step_4-1_search-ui-integration, Property 1: Filter logic preserves AND/OR semantics`
    - Target file: `src/backend/tests/test_search_properties.py`
    - **Validates: Requirements 1.2**

  - [x] 2.2 Write property test for offset pagination slice
    - **Property 2: Offset pagination produces correct slice**
    - Generate result sets of varying sizes and valid offsets (0 ≤ offset < N)
    - Verify: paginated results equal `full_results[offset:offset+limit]` and `total_available` equals N
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: Step_4-1_search-ui-integration, Property 2: Offset pagination produces correct slice`
    - Target file: `src/backend/tests/test_search_properties.py`
    - **Validates: Requirements 1.3, 2.2**

  - [x] 2.3 Write property test for date sort ordering
    - **Property 3: Date sort produces descending order**
    - Generate documents with random `updated_at` timestamps
    - Verify: when `sort_by="date"`, each result's `updated_at` ≥ next result's `updated_at`
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: Step_4-1_search-ui-integration, Property 3: Date sort produces descending order`
    - Target file: `src/backend/tests/test_search_properties.py`
    - **Validates: Requirements 1.4**

  - [x] 2.4 Write property test for response echo and metadata fields
    - **Property 4: Response echoes request parameters**
    - Generate random valid search requests with various offsets and filters
    - Verify: response `offset` equals request offset, `filters_applied` equals non-empty filter categories
    - **Property 13: Result metadata fields always present**
    - Verify: every result contains `document_type`, `status`, `tags`, `created_at`, `updated_at` fields (null/empty-list valid)
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: Step_4-1_search-ui-integration, Property 4: Response echoes request parameters`
    - Tag: `# Feature: Step_4-1_search-ui-integration, Property 13: Result metadata fields always present`
    - Target file: `src/backend/tests/test_search_properties.py`
    - **Validates: Requirements 2.3, 2.4, 2.1**

- [x] 3. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Frontend search store implementation
  - [x] 4.1 Rewrite searchStore with full state and actions
    - Rewrite `src/frontend/src/stores/searchStore.ts` from stub to full implementation
    - Define `SearchFilters` interface with `document_type: string[]`, `status: string[]`, `tags: string[]`
    - Define extended `SearchResult` interface with all metadata fields
    - Define `SearchState` interface with: `query`, `results`, `isSearching`, `error`, `filters`, `offset`, `limit` (default 20), `totalAvailable`, `sortBy`
    - Implement `search()`: guard against concurrent calls (`isSearching` check), truncate query to 1000 chars, reject whitespace-only queries (call `clearResults`), POST via `apiClient.post('/api/search', body, { changeReason: "Document search query" })`, store results and `totalAvailable` on success, handle errors
    - Implement `setFilter(category, value)`: toggle value in category array, reset offset to 0, call `search()`
    - Implement `setSortBy(sortBy)`: update sortBy, reset offset to 0, call `search()`
    - Implement `nextPage()`: increment offset by limit (only if `offset + limit < totalAvailable`), call `search()`
    - Implement `previousPage()`: decrement offset by limit (min 0), call `search()`
    - Implement `clearResults()`: reset all state to defaults
    - Target file: `src/frontend/src/stores/searchStore.ts`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 9.4, 9.5_

  - [x] 4.2 Write unit tests for searchStore
    - Test initial state has correct defaults
    - Test `search()` sends POST with correct body and `X-Change-Reason` header
    - Test `search()` sets `isSearching` during request
    - Test `search()` stores results on success
    - Test `search()` handles error response (sets error, clears results)
    - Test `search()` skips when `isSearching` is true (deduplication)
    - Test `search()` rejects whitespace-only queries
    - Test `search()` truncates query > 1000 chars
    - Test `setFilter()` toggles value correctly and triggers search
    - Test `setSortBy()` updates sort and triggers search
    - Test `setQuery()` updates without triggering search
    - Test `nextPage()`/`previousPage()` at boundaries
    - Test `clearResults()` resets all state
    - Target file: `src/frontend/src/__tests__/stores/searchStore.test.ts`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 5. Frontend search store property tests
  - [x] 5.1 Write property test for pagination arithmetic
    - **Property 5: Store pagination arithmetic**
    - Generate random offset O, limit L, totalAvailable T
    - Verify: `nextPage` sets offset to `O + L` iff `O + L < T`, otherwise unchanged; `previousPage` sets offset to `max(0, O - L)`
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 5: Store pagination arithmetic`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 3.6, 3.7**

  - [x] 5.2 Write property test for filter toggle and offset reset
    - **Property 6: Store filter toggle and offset reset**
    - Generate random filter states, category, and value
    - Verify: `setFilter(C, V)` adds V if not present or removes V if present; offset resets to 0 in both cases
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 6: Store filter toggle and offset reset`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 3.4**

  - [x] 5.3 Write property test for error state consistency
    - **Property 7: Store error state consistency**
    - Generate various error scenarios (network error, HTTP 500)
    - Verify: after failed search, `error` is non-empty string, `results` is empty, `totalAvailable` is 0, `isSearching` is false
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 7: Store error state consistency`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 3.3**

  - [x] 5.4 Write property test for request deduplication
    - **Property 8: Store request deduplication**
    - Verify: when `isSearching` is true, calling `search()` does not initiate a new request and leaves state unchanged
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 8: Store request deduplication`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 3.9**

  - [x] 5.5 Write property test for whitespace query rejection
    - **Property 9: Whitespace query rejection**
    - Generate strings composed entirely of whitespace
    - Verify: search is not triggered, `clearResults` is called, store resets to default state
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 9: Whitespace query rejection`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 4.5**

  - [x] 5.6 Write property test for relevance score clamping
    - **Property 10: Relevance score clamping**
    - Generate random floats (including < 0 and > 1)
    - Verify: displayed bar width is `Math.max(0, Math.min(1, score)) * 100`
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 10: Relevance score clamping`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 9.5**

  - [x] 5.7 Write property test for query truncation
    - **Property 11: Query truncation at maximum length**
    - Generate strings longer than 1000 characters
    - Verify: search request body contains query of exactly 1000 characters (first 1000 of input)
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 11: Query truncation at maximum length`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 9.4**

  - [x] 5.8 Write property test for sort change resets offset
    - **Property 12: Sort change resets offset and triggers search**
    - Generate random store states with offset > 0 and sort value changes
    - Verify: `setSortBy` resets offset to 0 and triggers a new search
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: Step_4-1_search-ui-integration, Property 12: Sort change resets offset and triggers search`
    - Target file: `src/frontend/src/__tests__/stores/searchProperties.test.ts`
    - **Validates: Requirements 10.2**

- [x] 6. Checkpoint - Ensure all store tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Frontend search components
  - [x] 7.1 Implement SearchResultCard component
    - Create `src/frontend/src/components/search/SearchResultCard.tsx`
    - Accept props: `result: SearchResult`, `query: string`
    - Render document title as clickable link to `/documents/{document_uuid}`
    - Render version badge
    - Render relevance score bar with `role="meter"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"`, `aria-label="Relevance score: {percentage}%"`
    - Clamp relevance score to [0, 1] for bar width calculation
    - Render excerpt with query terms highlighted using `<mark>` elements (case-insensitive split and wrap)
    - Render metadata badges for `document_type` and `status`
    - _Requirements: 5.1, 5.2, 8.6, 9.5_

  - [x] 7.2 Implement FilterSidebar component
    - Create `src/frontend/src/components/search/FilterSidebar.tsx`
    - Accept props: `results`, `activeFilters`, `onFilterToggle`, `onClearAll`, `disabled`
    - Derive available filter options from distinct metadata values in current results
    - Render three collapsible sections: "Document Type", "Status", "Tags"
    - Each section shows checkboxes with `aria-label="Filter by {category}: {value}"`
    - Show count badge on section headers for active selections (e.g., "Status (2)")
    - Show "Clear all filters" button when any filter is active
    - Disable/collapse sections when `disabled` is true with message "Perform a search to see available filters"
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 8.4_

  - [x] 7.3 Implement SearchPagination component
    - Create `src/frontend/src/components/search/SearchPagination.tsx`
    - Accept props: `offset`, `limit`, `totalAvailable`, `onNext`, `onPrevious`
    - Render "Previous" button (disabled when offset=0), page indicator "Page {current} of {total}", "Next" button (disabled when `offset + limit >= totalAvailable`)
    - Hide entirely when `totalAvailable <= limit`
    - Add `aria-label` attributes: "Go to previous page", "Go to next page"
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.4_

  - [x] 7.4 Implement SortDropdown component
    - Create `src/frontend/src/components/search/SortDropdown.tsx`
    - Accept props: `value: "relevance" | "date"`, `onChange`
    - Render select/dropdown with options "Most Relevant" and "Most Recent"
    - Visually indicate currently active sort option
    - _Requirements: 10.1, 10.3_

  - [x] 7.5 Rewrite SearchPage with full integration
    - Rewrite `src/frontend/src/pages/SearchPage.tsx` from static shell to full implementation
    - Add `role="search"` form wrapper with `aria-label="Search documents"` on input
    - Implement debounced search-as-you-type (300ms timer using `useRef`/`setTimeout`)
    - Handle Enter key (immediate search, cancel debounce), Escape key (clear input and results)
    - Handle Search button click (immediate search, cancel debounce)
    - Reject whitespace-only queries (call `clearResults`)
    - Truncate query > 1000 chars before sending, show toast notification
    - Display active filter chips above results with remove buttons
    - Display result count: "{totalAvailable} results found for '{query}'"
    - Show loading skeleton (pulsing placeholder cards) when `isSearching`
    - Show empty state when no results: "No results found for '{query}'"
    - Show initial placeholder state when no search performed
    - Show error alert with "Retry" button when `error` is set
    - Show inline validation error for HTTP 422
    - Set `aria-busy="true"` on results container during loading
    - Add `aria-live="polite"` region announcing result count
    - Scroll results to top on pagination
    - Wire all components: `SearchResultCard`, `FilterSidebar`, `SearchPagination`, `SortDropdown`
    - Connect to `useSearchStore` for all state and actions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.3, 6.4, 6.5, 8.1, 8.2, 8.3, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5, 10.2_

- [x] 8. Frontend component tests
  - [x] 8.1 Write unit tests for SearchResultCard
    - Test renders title as link to `/documents/{uuid}`
    - Test renders version badge
    - Test renders relevance bar with correct ARIA attributes
    - Test clamps out-of-range relevance scores
    - Test highlights query terms in excerpt with `<mark>`
    - Test renders metadata badges for document_type and status
    - Test navigates on click
    - Target file: `src/frontend/src/__tests__/components/search/SearchResultCard.test.tsx`
    - _Requirements: 5.1, 5.2, 8.6, 9.5_

  - [x] 8.2 Write unit tests for FilterSidebar
    - Test renders three collapsible sections
    - Test derives options from result metadata
    - Test shows count badges for active selections
    - Test disabled state shows message
    - Test checkbox toggles call onFilterToggle
    - Test "Clear all filters" button calls onClearAll
    - Target file: `src/frontend/src/__tests__/components/search/FilterSidebar.test.tsx`
    - _Requirements: 6.1, 6.2, 6.4, 6.6, 6.7_

  - [x] 8.3 Write unit tests for SearchPagination
    - Test hidden when totalAvailable ≤ limit
    - Test disables Previous at offset=0
    - Test disables Next at last page
    - Test shows correct page indicator
    - Test buttons have correct aria-labels
    - Target file: `src/frontend/src/__tests__/components/search/SearchPagination.test.tsx`
    - _Requirements: 7.1, 7.4, 7.5, 7.6, 8.4_

  - [x] 8.4 Write unit tests for SortDropdown
    - Test renders both options
    - Test visually indicates active option
    - Test calls onChange on selection
    - Target file: `src/frontend/src/__tests__/components/search/SortDropdown.test.tsx`
    - _Requirements: 10.1, 10.3_

  - [x] 8.5 Write unit tests for SearchPage integration
    - Test renders search input with placeholder and icon
    - Test shows initial placeholder state
    - Test debounce fires after 300ms
    - Test Enter key triggers immediate search
    - Test Escape key clears input and results
    - Test shows loading skeleton during search
    - Test shows empty state when no results
    - Test shows error alert with retry button
    - Test shows inline validation error for 422
    - Test truncates long queries with notification
    - Test aria-live region announces result count
    - Test aria-busy set during loading
    - Target file: `src/frontend/src/__tests__/components/search/SearchPage.test.tsx`
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 5.3, 5.4, 5.5, 5.7, 8.1, 8.2, 8.5, 9.1, 9.4_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python/FastAPI with Hypothesis for PBT (`uv run pytest` from `src/backend/`)
- Frontend uses React/TypeScript/Zustand with Vitest and fast-check for PBT (`npx vitest run` from `src/frontend/`)
- API prefix is `/api` (NOT `/api/v1`) for search endpoint
- Search router prefix is `/search` (full path: `POST /api/search`)
- X-Change-Reason header required on POST requests (enforced by audit middleware)
- All filtering, pagination, and ABAC enforcement happens server-side; frontend never performs client-side filtering
- The `apiClient` handles 401 retry + redirect to login transparently

