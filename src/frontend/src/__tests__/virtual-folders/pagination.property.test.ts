import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fc from "fast-check";
import { useVirtualFolderStore } from "../../stores/virtualFolderStore";

/**
 * Feature: virtual-folders-frontend, Property 6: Pagination offset calculation
 *
 * Validates: Requirements 7.2, 7.3
 *
 * For any non-negative integer offset and positive integer limit,
 * calling nextDocumentsPage SHALL produce offset + limit,
 * and calling prevDocumentsPage SHALL produce max(0, offset - limit).
 */

vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

const offsetArb = fc.integer({ min: 0, max: 1000 });
const limitArb = fc.integer({ min: 1, max: 100 });

describe("Feature: virtual-folders-frontend, Property 6: Pagination offset calculation", () => {
  beforeEach(() => {
    useVirtualFolderStore.setState({
      folders: [],
      selectedFolder: null,
      selectedFolderDocuments: [],
      documentsOffset: 0,
      documentsLimit: 20,
      isFoldersLoading: false,
      foldersError: null,
      isDocumentsLoading: false,
      documentsError: null,
      lastFetchedAt: null,
    });
  });

  it("nextDocumentsPage produces offset + limit", () => {
    fc.assert(
      fc.property(offsetArb, limitArb, (offset, limit) => {
        // Set up store state with random offset and limit, and a selected folder
        useVirtualFolderStore.setState({
          documentsOffset: offset,
          documentsLimit: limit,
          selectedFolder: {
            id: 1,
            name: "Test",
            tag_filter: {},
            sort_order: "created_at_desc",
            is_system_default: false,
            created_by: 1,
            created_at: null,
          },
        });

        // Call nextDocumentsPage
        useVirtualFolderStore.getState().nextDocumentsPage();

        // Assert the new offset is offset + limit
        const newOffset = useVirtualFolderStore.getState().documentsOffset;
        expect(newOffset).toBe(offset + limit);
      }),
      { numRuns: 100 }
    );
  });

  it("prevDocumentsPage produces max(0, offset - limit)", () => {
    fc.assert(
      fc.property(offsetArb, limitArb, (offset, limit) => {
        // Set up store state with random offset and limit, and a selected folder
        useVirtualFolderStore.setState({
          documentsOffset: offset,
          documentsLimit: limit,
          selectedFolder: {
            id: 1,
            name: "Test",
            tag_filter: {},
            sort_order: "created_at_desc",
            is_system_default: false,
            created_by: 1,
            created_at: null,
          },
        });

        // Call prevDocumentsPage
        useVirtualFolderStore.getState().prevDocumentsPage();

        // Assert the new offset is max(0, offset - limit)
        const newOffset = useVirtualFolderStore.getState().documentsOffset;
        expect(newOffset).toBe(Math.max(0, offset - limit));
      }),
      { numRuns: 100 }
    );
  });
});
