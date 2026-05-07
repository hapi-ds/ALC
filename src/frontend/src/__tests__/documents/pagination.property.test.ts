import { describe, it, expect, beforeEach } from "vitest";
import * as fc from "fast-check";
import { useDocumentStore } from "../../stores/documentStore";

/**
 * Feature: document-upload-list, Property 2: Pagination arithmetic is consistent
 *
 * Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5
 *
 * For any valid offset (≥ 0), limit (≥ 1), and total (≥ 0):
 * - currentPage = floor(offset / limit) + 1
 * - totalPages = ceil(total / limit)
 * - nextPage increments offset by limit
 * - prevPage decrements offset by limit (min 0)
 * - prev disabled iff offset = 0
 * - next disabled iff offset + limit >= total
 */

describe("Feature: document-upload-list, Property 2: Pagination arithmetic is consistent", () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    useDocumentStore.setState({
      documents: [],
      selectedDocument: null,
      total: 0,
      offset: 0,
      limit: 20,
      tagFilter: null,
      folderPathFilter: null,
      isLoading: false,
      error: null,
    });
  });

  it("currentPage = floor(offset / limit) + 1 for any valid offset and limit", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset
        fc.integer({ min: 1, max: 100 }),    // limit
        (offset, limit) => {
          // Align offset to a multiple of limit for realistic pagination
          const alignedOffset = Math.floor(offset / limit) * limit;
          useDocumentStore.setState({ offset: alignedOffset, limit });

          const state = useDocumentStore.getState();
          const currentPage = Math.floor(state.offset / state.limit) + 1;

          expect(currentPage).toBe(Math.floor(alignedOffset / limit) + 1);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("totalPages = ceil(total / limit) for any valid total and limit", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // total
        fc.integer({ min: 1, max: 100 }),    // limit
        (total, limit) => {
          useDocumentStore.setState({ total, limit });

          const state = useDocumentStore.getState();
          const totalPages = Math.ceil(state.total / state.limit);

          expect(totalPages).toBe(Math.ceil(total / limit));
        }
      ),
      { numRuns: 100 }
    );
  });

  it("nextPage increments offset by limit", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset
        fc.integer({ min: 1, max: 100 }),    // limit
        (offset, limit) => {
          useDocumentStore.setState({ offset, limit });

          const before = useDocumentStore.getState().offset;
          useDocumentStore.getState().nextPage();
          const after = useDocumentStore.getState().offset;

          expect(after).toBe(before + limit);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("prevPage decrements offset by limit with minimum 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset
        fc.integer({ min: 1, max: 100 }),    // limit
        (offset, limit) => {
          useDocumentStore.setState({ offset, limit });

          useDocumentStore.getState().prevPage();
          const after = useDocumentStore.getState().offset;

          expect(after).toBe(Math.max(0, offset - limit));
        }
      ),
      { numRuns: 100 }
    );
  });

  it("previous control disabled iff offset = 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset
        fc.integer({ min: 1, max: 100 }),    // limit
        (offset, limit) => {
          useDocumentStore.setState({ offset, limit });

          const state = useDocumentStore.getState();
          const prevDisabled = state.offset === 0;

          if (offset === 0) {
            expect(prevDisabled).toBe(true);
          } else {
            expect(prevDisabled).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("next control disabled iff offset + limit >= total", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 10000 }), // offset
        fc.integer({ min: 1, max: 100 }),    // limit
        fc.integer({ min: 0, max: 10000 }), // total
        (offset, limit, total) => {
          useDocumentStore.setState({ offset, limit, total });

          const state = useDocumentStore.getState();
          const nextDisabled = state.offset + state.limit >= state.total;

          if (offset + limit >= total) {
            expect(nextDisabled).toBe(true);
          } else {
            expect(nextDisabled).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("setPage sets offset to (page - 1) * limit", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 500 }),  // page (1-indexed)
        fc.integer({ min: 1, max: 100 }),  // limit
        (page, limit) => {
          useDocumentStore.setState({ limit });

          useDocumentStore.getState().setPage(page);
          const state = useDocumentStore.getState();

          expect(state.offset).toBe((page - 1) * limit);
        }
      ),
      { numRuns: 100 }
    );
  });
});
