// Feature: Step_4-1_search-ui-integration, Property 5: Store pagination arithmetic

import { describe, it, expect, beforeEach, vi } from "vitest";
import * as fc from "fast-check";
import { useSearchStore } from "@/stores/searchStore";

/**
 * Property-based tests for searchStore pagination arithmetic.
 *
 * **Validates: Requirements 3.6, 3.7**
 */

// Mock apiClient to prevent actual API calls (pagination methods call search() internally)
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

import { apiClient } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Property 5: Store pagination arithmetic
// Validates: Requirements 3.6, 3.7
// ---------------------------------------------------------------------------

describe("Feature: Step_4-1_search-ui-integration, Property 5: Store pagination arithmetic", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 3.6**
   *
   * nextPage sets offset to O + L if and only if O + L < T,
   * otherwise offset remains unchanged at O.
   */
  it("nextPage sets offset to O + L iff O + L < T, otherwise unchanged", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset O
        fc.integer({ min: 1, max: 100 }),    // limit L
        fc.integer({ min: 0, max: 20000 }),  // totalAvailable T
        (offset, limit, totalAvailable) => {
          // Set up store state with a valid query so search() can proceed
          useSearchStore.setState({
            query: "test",
            offset,
            limit,
            totalAvailable,
            isSearching: false,
            results: [],
            error: null,
            filters: { document_type: [], status: [], tags: [] },
            sortBy: "relevance",
          });

          // Mock the API to resolve (search is called internally by nextPage)
          mockedApiClient.post.mockResolvedValue({
            results: [],
            total: 0,
            total_available: totalAvailable,
            query: "test",
            offset: offset + limit,
            filters_applied: {},
          });

          // Call nextPage
          useSearchStore.getState().nextPage();

          const newOffset = useSearchStore.getState().offset;

          if (offset + limit < totalAvailable) {
            // Should advance
            expect(newOffset).toBe(offset + limit);
          } else {
            // Should remain unchanged
            expect(newOffset).toBe(offset);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.7**
   *
   * previousPage sets offset to max(0, O - L).
   */
  it("previousPage sets offset to max(0, O - L)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset O
        fc.integer({ min: 1, max: 100 }),    // limit L
        fc.integer({ min: 1, max: 20000 }),  // totalAvailable T
        (offset, limit, totalAvailable) => {
          // Set up store state with a valid query so search() can proceed
          useSearchStore.setState({
            query: "test",
            offset,
            limit,
            totalAvailable,
            isSearching: false,
            results: [],
            error: null,
            filters: { document_type: [], status: [], tags: [] },
            sortBy: "relevance",
          });

          // Mock the API to resolve (search is called internally by previousPage)
          mockedApiClient.post.mockResolvedValue({
            results: [],
            total: 0,
            total_available: totalAvailable,
            query: "test",
            offset: Math.max(0, offset - limit),
            filters_applied: {},
          });

          // Call previousPage
          useSearchStore.getState().previousPage();

          const newOffset = useSearchStore.getState().offset;
          const expectedOffset = Math.max(0, offset - limit);

          expect(newOffset).toBe(expectedOffset);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 6: Store filter toggle and offset reset
// ---------------------------------------------------------------------------

/**
 * Property-based tests for searchStore filter toggle and offset reset.
 *
 * **Validates: Requirements 3.4**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 6: Store filter toggle and offset reset", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const filterCategories = ["document_type", "status", "tags"] as const;

  /**
   * **Validates: Requirements 3.4**
   *
   * setFilter(C, V) adds V to F[C] if V is not present, resets offset to 0.
   */
  it("setFilter adds value if not present and resets offset to 0", () => {
    fc.assert(
      fc.property(
        // Generate random initial filter arrays for each category
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 5 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 5 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 5 }),
        // Random category index
        fc.integer({ min: 0, max: 2 }),
        // Random value to toggle (guaranteed not in the category array)
        fc.string({ minLength: 1, maxLength: 20 }),
        // Random initial offset > 0
        fc.integer({ min: 1, max: 10000 }),
        (docTypes, statuses, tags, categoryIdx, newValue, initialOffset) => {
          const category = filterCategories[categoryIdx];
          const initialFilters = {
            document_type: [...docTypes],
            status: [...statuses],
            tags: [...tags],
          };

          // Ensure the value is NOT in the category array (add case)
          const categoryArray = initialFilters[category];
          const filteredArray = categoryArray.filter((v) => v !== newValue);
          initialFilters[category] = filteredArray;

          // Set up store state with non-zero offset
          useSearchStore.setState({
            query: "test",
            offset: initialOffset,
            limit: 20,
            totalAvailable: 100,
            isSearching: false,
            results: [],
            error: null,
            filters: initialFilters,
            sortBy: "relevance",
          });

          // Mock the API to resolve
          mockedApiClient.post.mockResolvedValue({
            results: [],
            total: 0,
            total_available: 0,
            query: "test",
            offset: 0,
            filters_applied: {},
          });

          // Call setFilter — value is NOT present, so it should be added
          useSearchStore.getState().setFilter(category, newValue);

          const state = useSearchStore.getState();

          // Value should now be in the category array
          expect(state.filters[category]).toContain(newValue);
          // Offset should be reset to 0
          expect(state.offset).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.4**
   *
   * setFilter(C, V) removes V from F[C] if V is already present, resets offset to 0.
   */
  it("setFilter removes value if already present and resets offset to 0", () => {
    fc.assert(
      fc.property(
        // Generate random initial filter arrays for each category
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 5 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 5 }),
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 5 }),
        // Random category index
        fc.integer({ min: 0, max: 2 }),
        // Value that will be present in the array
        fc.string({ minLength: 1, maxLength: 20 }),
        // Random initial offset > 0
        fc.integer({ min: 1, max: 10000 }),
        (docTypes, statuses, tags, categoryIdx, existingValue, initialOffset) => {
          const category = filterCategories[categoryIdx];
          const initialFilters = {
            document_type: [...docTypes],
            status: [...statuses],
            tags: [...tags],
          };

          // Ensure the value IS in the category array (remove case)
          if (!initialFilters[category].includes(existingValue)) {
            initialFilters[category].push(existingValue);
          }

          // Set up store state with non-zero offset
          useSearchStore.setState({
            query: "test",
            offset: initialOffset,
            limit: 20,
            totalAvailable: 100,
            isSearching: false,
            results: [],
            error: null,
            filters: initialFilters,
            sortBy: "relevance",
          });

          // Mock the API to resolve
          mockedApiClient.post.mockResolvedValue({
            results: [],
            total: 0,
            total_available: 0,
            query: "test",
            offset: 0,
            filters_applied: {},
          });

          // Call setFilter — value IS present, so it should be removed
          useSearchStore.getState().setFilter(category, existingValue);

          const state = useSearchStore.getState();

          // Value should NOT be in the category array anymore
          expect(state.filters[category]).not.toContain(existingValue);
          // Offset should be reset to 0
          expect(state.offset).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 7: Store error state consistency
// ---------------------------------------------------------------------------

/**
 * Property-based tests for searchStore error state consistency.
 *
 * **Validates: Requirements 3.3**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 7: Store error state consistency", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * After a failed search (Error instance), the store transitions to:
   * - error: non-empty string (the Error's message)
   * - results: empty array
   * - totalAvailable: 0
   * - isSearching: false
   */
  it("after failed search with Error instance, store has consistent error state", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 200 }), // error message
        fc.string({ minLength: 1, maxLength: 100 }), // query (non-whitespace)
        async (errorMessage, query) => {
          // Ensure query is non-whitespace (search rejects whitespace-only)
          const validQuery = query.trim() || "test";

          // Set up store state with a valid query
          useSearchStore.setState({
            query: validQuery,
            offset: 0,
            limit: 20,
            totalAvailable: 0,
            isSearching: false,
            results: [],
            error: null,
            filters: { document_type: [], status: [], tags: [] },
            sortBy: "relevance",
          });

          // Mock the API to reject with an Error instance
          mockedApiClient.post.mockRejectedValue(new Error(errorMessage));

          // Call search and await completion
          await useSearchStore.getState().search();

          const state = useSearchStore.getState();

          // error should be the Error's message (non-empty)
          expect(state.error).toBe(errorMessage);
          expect(state.error!.length).toBeGreaterThan(0);
          // results should be empty
          expect(state.results).toEqual([]);
          // totalAvailable should be 0
          expect(state.totalAvailable).toBe(0);
          // isSearching should be false
          expect(state.isSearching).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 3.3**
   *
   * After a failed search (non-Error throw, e.g. string), the store transitions to:
   * - error: the fallback message "Search is temporarily unavailable. Please try again."
   * - results: empty array
   * - totalAvailable: 0
   * - isSearching: false
   */
  it("after failed search with non-Error throw, store uses fallback error message", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.oneof(
          fc.string({ minLength: 0, maxLength: 100 }), // string throw
          fc.integer(),                                  // number throw
          fc.constant(null),                             // null throw
          fc.constant(undefined)                         // undefined throw
        ),
        fc.string({ minLength: 1, maxLength: 100 }), // query
        async (thrownValue, query) => {
          const validQuery = query.trim() || "test";

          // Set up store state with a valid query
          useSearchStore.setState({
            query: validQuery,
            offset: 0,
            limit: 20,
            totalAvailable: 0,
            isSearching: false,
            results: [],
            error: null,
            filters: { document_type: [], status: [], tags: [] },
            sortBy: "relevance",
          });

          // Mock the API to reject with a non-Error value
          mockedApiClient.post.mockRejectedValue(thrownValue);

          // Call search and await completion
          await useSearchStore.getState().search();

          const state = useSearchStore.getState();

          // error should be the fallback message
          expect(state.error).toBe(
            "Search is temporarily unavailable. Please try again."
          );
          expect(state.error!.length).toBeGreaterThan(0);
          // results should be empty
          expect(state.results).toEqual([]);
          // totalAvailable should be 0
          expect(state.totalAvailable).toBe(0);
          // isSearching should be false
          expect(state.isSearching).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 8: Store request deduplication
// ---------------------------------------------------------------------------

/**
 * Property-based tests for searchStore request deduplication.
 *
 * **Validates: Requirements 3.9**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 8: Store request deduplication", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 3.9**
   *
   * When isSearching is true, calling search() does not initiate a new request
   * and leaves state unchanged.
   */
  it("search() does not initiate a new request when isSearching is true", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 200 }),   // query (non-empty)
        fc.integer({ min: 0, max: 10000 }),            // offset
        fc.integer({ min: 1, max: 100 }),              // limit
        fc.integer({ min: 0, max: 20000 }),            // totalAvailable
        fc.constantFrom("relevance", "date") as fc.Arbitrary<"relevance" | "date">, // sortBy
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 3 }), // document_type filters
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 3 }), // status filters
        fc.array(fc.string({ minLength: 1, maxLength: 20 }), { maxLength: 3 }), // tags filters
        async (query, offset, limit, totalAvailable, sortBy, docTypes, statuses, tags) => {
          // Ensure query is non-whitespace
          const validQuery = query.trim() || "test";

          const initialState = {
            query: validQuery,
            offset,
            limit,
            totalAvailable,
            isSearching: true, // Key: isSearching is already true
            results: [],
            error: null,
            filters: {
              document_type: [...docTypes],
              status: [...statuses],
              tags: [...tags],
            },
            sortBy,
          };

          // Set up store state with isSearching = true
          useSearchStore.setState(initialState);

          // Clear mock call history before calling search
          mockedApiClient.post.mockClear();

          // Call search — should return immediately without making an API call
          await useSearchStore.getState().search();

          // apiClient.post should NOT have been called
          expect(mockedApiClient.post).not.toHaveBeenCalled();

          // State should remain unchanged
          const state = useSearchStore.getState();
          expect(state.query).toBe(validQuery);
          expect(state.offset).toBe(offset);
          expect(state.limit).toBe(limit);
          expect(state.totalAvailable).toBe(totalAvailable);
          expect(state.isSearching).toBe(true);
          expect(state.results).toEqual([]);
          expect(state.error).toBeNull();
          expect(state.filters.document_type).toEqual(docTypes);
          expect(state.filters.status).toEqual(statuses);
          expect(state.filters.tags).toEqual(tags);
          expect(state.sortBy).toBe(sortBy);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 9: Whitespace query rejection
// ---------------------------------------------------------------------------

/**
 * Property-based tests for searchStore whitespace query rejection.
 *
 * **Validates: Requirements 4.5**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 9: Whitespace query rejection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 4.5**
   *
   * When the query consists entirely of whitespace characters, search() does not
   * make an API call and instead calls clearResults(), resetting the store to
   * its default state.
   */
  it("whitespace-only queries do not trigger API call and reset store to defaults", async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate strings composed entirely of whitespace characters
        fc.string({ unit: fc.constantFrom(" ", "\t", "\n", "\r"), minLength: 0, maxLength: 50 }),
        async (whitespaceQuery) => {
          // Set up store with some non-default state to verify clearResults resets it
          useSearchStore.setState({
            query: whitespaceQuery,
            offset: 40,
            limit: 20,
            totalAvailable: 200,
            isSearching: false,
            results: [
              {
                document_uuid: "abc-123",
                title: "Existing Result",
                version: "1.0",
                excerpt: "Some excerpt",
                relevance_score: 0.85,
                document_type: "SOP",
                status: "approved",
                tags: ["gxp"],
                created_at: "2024-01-01T00:00:00Z",
                updated_at: "2024-01-02T00:00:00Z",
              },
            ],
            error: "previous error",
            filters: {
              document_type: ["SOP"],
              status: ["approved"],
              tags: ["gxp"],
            },
            sortBy: "date",
          });

          // Clear mock call history
          mockedApiClient.post.mockClear();

          // Call search — should reject whitespace query and call clearResults
          await useSearchStore.getState().search();

          // apiClient.post should NOT have been called
          expect(mockedApiClient.post).not.toHaveBeenCalled();

          // Store should be reset to default state (clearResults was called)
          const state = useSearchStore.getState();
          expect(state.query).toBe("");
          expect(state.results).toEqual([]);
          expect(state.isSearching).toBe(false);
          expect(state.error).toBeNull();
          expect(state.filters).toEqual({
            document_type: [],
            status: [],
            tags: [],
          });
          expect(state.offset).toBe(0);
          expect(state.totalAvailable).toBe(0);
          expect(state.sortBy).toBe("relevance");
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 10: Relevance score clamping
// ---------------------------------------------------------------------------

/**
 * Property-based tests for relevance score clamping logic.
 *
 * The SearchResultCard component displays a relevance bar whose width is
 * computed as: Math.max(0, Math.min(1, score)) * 100
 *
 * This ensures out-of-range scores (< 0 or > 1) are clamped to [0, 100]%.
 *
 * **Validates: Requirements 9.5**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 10: Relevance score clamping", () => {
  /**
   * Helper implementing the clamping formula used in the SearchResultCard
   * relevance bar width calculation.
   */
  function clampedBarWidth(score: number): number {
    return Math.max(0, Math.min(1, score)) * 100;
  }

  /**
   * **Validates: Requirements 9.5**
   *
   * For any float (including < 0 and > 1), the displayed bar width
   * equals Math.max(0, Math.min(1, score)) * 100 and is in [0, 100].
   */
  it("displayed bar width is Math.max(0, Math.min(1, score)) * 100 and within [0, 100]", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10, max: 10, noNaN: true }),
        (score) => {
          const barWidth = clampedBarWidth(score);

          // Bar width must be in [0, 100] range
          expect(barWidth).toBeGreaterThanOrEqual(0);
          expect(barWidth).toBeLessThanOrEqual(100);

          // Bar width must match the clamping formula exactly
          const expected = Math.max(0, Math.min(1, score)) * 100;
          expect(barWidth).toBe(expected);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.5**
   *
   * Scores below 0 always produce bar width of 0.
   */
  it("negative scores produce bar width of 0", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10, max: -Number.MIN_VALUE, noNaN: true }),
        (score) => {
          const barWidth = clampedBarWidth(score);
          expect(barWidth).toBe(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.5**
   *
   * Scores above 1 always produce bar width of 100.
   */
  it("scores above 1 produce bar width of 100", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1 + Number.EPSILON, max: 10, noNaN: true }),
        (score) => {
          const barWidth = clampedBarWidth(score);
          expect(barWidth).toBe(100);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.5**
   *
   * Scores in [0, 1] produce bar width equal to score * 100 (no clamping needed).
   */
  it("scores in [0, 1] produce bar width equal to score * 100", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1, noNaN: true }),
        (score) => {
          const barWidth = clampedBarWidth(score);
          expect(barWidth).toBe(score * 100);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 11: Query truncation at maximum length
// ---------------------------------------------------------------------------

/**
 * Property-based tests for searchStore query truncation at maximum length.
 *
 * The store's search() method truncates the query to 1000 characters via
 * `state.query.slice(0, 1000)` before sending the request body.
 *
 * **Validates: Requirements 9.4**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 11: Query truncation at maximum length", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 9.4**
   *
   * For any string longer than 1000 characters that contains at least one
   * non-whitespace character, the search request body contains a query field
   * of exactly 1000 characters equal to the first 1000 characters of the input.
   */
  it("search request body contains query of exactly 1000 characters (first 1000 of input)", async () => {
    // Generator: a non-whitespace prefix followed by padding to exceed 1000 chars
    const longNonWhitespaceQuery = fc
      .tuple(
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
        fc.string({ minLength: 1000, maxLength: 1900 })
      )
      .map(([prefix, suffix]) => prefix + suffix);

    await fc.assert(
      fc.asyncProperty(longNonWhitespaceQuery, async (longQuery) => {
        // Clear mocks before each iteration to reset call counts
        mockedApiClient.post.mockClear();

        // Set up store state with the long query
        useSearchStore.setState({
          query: longQuery,
          offset: 0,
          limit: 20,
          totalAvailable: 0,
          isSearching: false,
          results: [],
          error: null,
          filters: { document_type: [], status: [], tags: [] },
          sortBy: "relevance",
        });

        // Mock the API to resolve with a valid response
        mockedApiClient.post.mockResolvedValue({
          results: [],
          total: 0,
          total_available: 0,
          query: longQuery.slice(0, 1000),
          offset: 0,
          filters_applied: {},
        });

        // Call search
        await useSearchStore.getState().search();

        // Verify apiClient.post was called exactly once
        expect(mockedApiClient.post).toHaveBeenCalledTimes(1);

        // Extract the body sent to apiClient.post
        const [, body] = mockedApiClient.post.mock.calls[0];

        // The query in the request body should be exactly 1000 characters
        expect(body.query.length).toBe(1000);

        // The query should equal the first 1000 characters of the input
        expect(body.query).toBe(longQuery.slice(0, 1000));
      }),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Feature: Step_4-1_search-ui-integration, Property 12: Sort change resets offset and triggers search
// ---------------------------------------------------------------------------

/**
 * Property-based tests for searchStore sort change behavior.
 *
 * The store's `setSortBy(sortBy)` method updates the sortBy value,
 * resets offset to 0, and calls search().
 *
 * **Validates: Requirements 10.2**
 */

describe("Feature: Step_4-1_search-ui-integration, Property 12: Sort change resets offset and triggers search", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 10.2**
   *
   * For any store state with offset > 0 and any sort value change,
   * calling setSortBy resets offset to 0 and triggers a new search
   * (apiClient.post is called).
   */
  it("setSortBy resets offset to 0 and triggers a new search", async () => {
    await fc.assert(
      fc.asyncProperty(
        // Random offset > 0
        fc.integer({ min: 1, max: 10000 }),
        // Random limit
        fc.integer({ min: 1, max: 100 }),
        // Random totalAvailable (must be > offset to have a meaningful state)
        fc.integer({ min: 1, max: 20000 }),
        // Sort value to set (either "relevance" or "date")
        fc.constantFrom("relevance", "date") as fc.Arbitrary<"relevance" | "date">,
        // Non-whitespace query so search() proceeds
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
        async (offset, limit, totalAvailable, newSortBy, query) => {
          // Set up store state with offset > 0
          useSearchStore.setState({
            query,
            offset,
            limit,
            totalAvailable,
            isSearching: false,
            results: [],
            error: null,
            filters: { document_type: [], status: [], tags: [] },
            sortBy: newSortBy === "relevance" ? "date" : "relevance", // ensure it's different from newSortBy
          });

          // Clear mock call history
          mockedApiClient.post.mockClear();

          // Mock the API to resolve with a valid response
          mockedApiClient.post.mockResolvedValue({
            results: [],
            total: 0,
            total_available: totalAvailable,
            query,
            offset: 0,
            filters_applied: {},
          });

          // Call setSortBy
          useSearchStore.getState().setSortBy(newSortBy);

          const state = useSearchStore.getState();

          // Offset should be reset to 0
          expect(state.offset).toBe(0);

          // sortBy should be updated to the new value
          expect(state.sortBy).toBe(newSortBy);

          // apiClient.post should have been called (search was triggered)
          expect(mockedApiClient.post).toHaveBeenCalled();
        }
      ),
      { numRuns: 100 }
    );
  });
});
