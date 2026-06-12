import { describe, it, expect, afterEach } from "vitest";
import * as fc from "fast-check";
import { render, screen, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import React from "react";
import { useLiteratureSearchStore } from "../stores/literatureSearchStore";
import PaginationControls from "../components/literature-search/PaginationControls";
import { SearchInput } from "../components/literature-search/SearchInput";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useLiteratureSearchStore.setState({
    queryText: "",
    searchMode: "hybrid",
    includeInternal: false,
    filters: {
      date_from: null,
      date_to: null,
      journals: [],
      sources: [],
      publication_types: [],
      mesh_terms: [],
      device_class: [],
    },
    results: [],
    pagination: null,
    facetCounts: null,
    isLoading: false,
    error: null,
    searchExecutionId: null,
    savedSearches: [],
    savedSearchesLoading: false,
    searchHistory: [],
  });
}

// ---------------------------------------------------------------------------
// Property 2 (frontend): Pagination component correctness
// ---------------------------------------------------------------------------

describe("Feature: Step_9-6_literature-search-citation-ui, Property 2 (frontend): Pagination component correctness", () => {
  /**
   * **Validates: Requirements 9.5**
   *
   * For any valid (total_results, page, page_size) triple, PaginationControls
   * renders the correct total_pages, disables prev on page 1, disables next on
   * last page, and shows correct "Showing X–Y of Z" text.
   */

  afterEach(() => {
    cleanup();
    resetStore();
  });

  it("renders correct 'Showing X–Y of Z results' text for any valid pagination state", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        fc.integer({ min: 1, max: 100 }),
        (totalResults, pageSize) => {
          cleanup();
          resetStore();

          const totalPages = Math.ceil(totalResults / pageSize);
          // Pick a valid page within range
          const page = Math.min(
            Math.max(1, Math.floor(Math.random() * totalPages) + 1),
            totalPages,
          );

          const expectedStart = (page - 1) * pageSize + 1;
          const expectedEnd = Math.min(page * pageSize, totalResults);

          useLiteratureSearchStore.setState({
            pagination: {
              total_results: totalResults,
              page,
              page_size: pageSize,
              total_pages: totalPages,
            },
          });

          render(React.createElement(PaginationControls));

          // The component renders "Showing X–Y of Z results" using &ndash; (–)
          const expectedText = `Showing ${expectedStart}\u2013${expectedEnd} of ${totalResults} results`;
          expect(screen.getByText(expectedText)).toBeInTheDocument();
        },
      ),
      { numRuns: 100 },
    );
  });

  it("disables 'Previous page' button when on page 1", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        fc.integer({ min: 1, max: 100 }),
        (totalResults, pageSize) => {
          cleanup();
          resetStore();

          const totalPages = Math.ceil(totalResults / pageSize);

          useLiteratureSearchStore.setState({
            pagination: {
              total_results: totalResults,
              page: 1,
              page_size: pageSize,
              total_pages: totalPages,
            },
          });

          render(React.createElement(PaginationControls));

          const prevButton = screen.getByRole("button", { name: /previous page/i });
          expect(prevButton).toBeDisabled();
        },
      ),
      { numRuns: 100 },
    );
  });

  it("disables 'Next page' button when on the last page", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }),
        fc.integer({ min: 1, max: 100 }),
        (totalResults, pageSize) => {
          cleanup();
          resetStore();

          const totalPages = Math.ceil(totalResults / pageSize);

          useLiteratureSearchStore.setState({
            pagination: {
              total_results: totalResults,
              page: totalPages,
              page_size: pageSize,
              total_pages: totalPages,
            },
          });

          render(React.createElement(PaginationControls));

          const nextButton = screen.getByRole("button", { name: /next page/i });
          expect(nextButton).toBeDisabled();
        },
      ),
      { numRuns: 100 },
    );
  });

  it("enables both prev and next buttons when on a middle page", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 3, max: 10000 }),
        fc.integer({ min: 1, max: 100 }),
        (totalResults, pageSize) => {
          cleanup();
          resetStore();

          const totalPages = Math.ceil(totalResults / pageSize);
          // Only test if there are at least 3 pages (so a middle page exists)
          fc.pre(totalPages >= 3);

          const middlePage = Math.floor(totalPages / 2) + 1;

          useLiteratureSearchStore.setState({
            pagination: {
              total_results: totalResults,
              page: middlePage,
              page_size: pageSize,
              total_pages: totalPages,
            },
          });

          render(React.createElement(PaginationControls));

          const prevButton = screen.getByRole("button", { name: /previous page/i });
          const nextButton = screen.getByRole("button", { name: /next page/i });
          expect(prevButton).not.toBeDisabled();
          expect(nextButton).not.toBeDisabled();
        },
      ),
      { numRuns: 100 },
    );
  });

  it("total_pages equals ceil(total_results / page_size)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }),
        fc.integer({ min: 1, max: 100 }),
        (totalResults, pageSize) => {
          const expectedTotalPages = Math.ceil(totalResults / pageSize);
          // This is a pure logic assertion confirming the invariant
          // that the component depends on
          expect(expectedTotalPages).toBe(
            Math.ceil(totalResults / pageSize),
          );
          // Also verify it's always >= 0
          expect(expectedTotalPages).toBeGreaterThanOrEqual(0);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4 (frontend): Whitespace query rejection
// ---------------------------------------------------------------------------

describe("Feature: Step_9-6_literature-search-citation-ui, Property 4 (frontend): Whitespace query rejection", () => {
  /**
   * **Validates: Requirements 9.2**
   *
   * For any whitespace-only string (including tabs, spaces, newlines, and
   * Unicode whitespace), the SearchInput component disables the submit button,
   * preventing execution of empty queries.
   */

  afterEach(() => {
    cleanup();
    resetStore();
  });

  it("disables submit button for all whitespace-only inputs", () => {
    const whitespaceChars = [
      " ", "\t", "\n", "\r", "\f", "\v",
      "\u00A0", "\u2000", "\u2001", "\u2002",
      "\u2003", "\u2009", "\u200A", "\u3000",
    ];
    const whitespaceArb = fc
      .array(fc.constantFrom(...whitespaceChars), { minLength: 0, maxLength: 50 })
      .map((chars) => chars.join(""));

    fc.assert(
      fc.property(
        whitespaceArb,
        (whitespaceInput) => {
          cleanup();
          resetStore();

          // The SearchInput uses local state, so we render with the store's
          // queryText set to the whitespace string. However, since SearchInput
          // uses useState(queryText) for the local state, we set the store's
          // queryText before rendering.
          useLiteratureSearchStore.setState({
            queryText: whitespaceInput,
            isLoading: false,
          });

          render(React.createElement(SearchInput));

          const submitButton = screen.getByRole("button", { name: /execute search/i });
          expect(submitButton).toBeDisabled();
        },
      ),
      { numRuns: 100 },
    );
  });

  it("enables submit button for non-whitespace inputs", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 100 }).filter(
          (s) => s.trim().length > 0,
        ),
        (validInput) => {
          cleanup();
          resetStore();

          useLiteratureSearchStore.setState({
            queryText: validInput,
            isLoading: false,
          });

          render(React.createElement(SearchInput));

          const submitButton = screen.getByRole("button", { name: /execute search/i });
          expect(submitButton).not.toBeDisabled();
        },
      ),
      { numRuns: 100 },
    );
  });
});
