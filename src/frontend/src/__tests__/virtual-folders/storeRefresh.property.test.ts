import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fc from "fast-check";
import { useVirtualFolderStore } from "../../stores/virtualFolderStore";
import { apiClient } from "../../lib/apiClient";

/**
 * Feature: virtual-folders-frontend, Property 8: Mutating store actions refresh folder list on success
 *
 * Validates: Requirements 9.5
 *
 * For any successful execution of createFolder, updateFolder, or deleteFolder,
 * the store SHALL call fetchFolders to refresh the folder list afterward.
 *
 * Verification: The apiClient is fully mocked. We assert that apiClient.get
 * was called with "/api/virtual-folders" after each successful mutation,
 * confirming fetchFolders was triggered internally by the store.
 */

vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue([]),
    post: vi.fn().mockResolvedValue({
      id: 1,
      name: "Test",
      tag_filter: {},
      sort_order: "created_at_desc",
      is_system_default: false,
      created_by: 1,
      created_at: null,
    }),
    put: vi.fn().mockResolvedValue({
      id: 1,
      name: "Test",
      tag_filter: {},
      sort_order: "created_at_desc",
      is_system_default: false,
      created_by: 1,
      created_at: null,
    }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

const mockedApiClient = vi.mocked(apiClient);

// Arbitraries for generating random valid inputs
const folderNameArb = fc.string({ minLength: 1, maxLength: 50 }).filter((s) => s.trim().length > 0);
const tagFilterArb = fc.record({
  tags: fc.option(
    fc.array(fc.constantFrom("SOP", "Protocol", "Report", "General", "Policy", "Form"), { minLength: 1, maxLength: 6 }),
    { nil: undefined }
  ),
  status: fc.option(
    fc.constantFrom("Draft", "Active", "Approved", "InTraining", "Retired"),
    { nil: undefined }
  ),
});
const sortOrderArb = fc.constantFrom("created_at_desc", "created_at_asc", "name_asc", "name_desc");
const folderIdArb = fc.integer({ min: 1, max: 1000 });

describe("Feature: virtual-folders-frontend, Property 8: Mutating store actions refresh folder list on success", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApiClient.get.mockResolvedValue([]);
    mockedApiClient.post.mockResolvedValue({
      id: 1,
      name: "Test",
      tag_filter: {},
      sort_order: "created_at_desc",
      is_system_default: false,
      created_by: 1,
      created_at: null,
    });
    mockedApiClient.put.mockResolvedValue({
      id: 1,
      name: "Test",
      tag_filter: {},
      sort_order: "created_at_desc",
      is_system_default: false,
      created_by: 1,
      created_at: null,
    });
    mockedApiClient.delete.mockResolvedValue(undefined);

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

  it("createFolder calls fetchFolders (GET /api/virtual-folders) after successful creation", async () => {
    await fc.assert(
      fc.asyncProperty(folderNameArb, tagFilterArb, sortOrderArb, async (name, tagFilter, sortOrder) => {
        vi.clearAllMocks();
        mockedApiClient.get.mockResolvedValue([]);
        mockedApiClient.post.mockResolvedValue({
          id: 1,
          name,
          tag_filter: tagFilter,
          sort_order: sortOrder,
          is_system_default: false,
          created_by: 1,
          created_at: null,
        });

        await useVirtualFolderStore.getState().createFolder(name, tagFilter, sortOrder);

        // Verify that GET /api/virtual-folders was called (fetchFolders triggered)
        const getCalls = mockedApiClient.get.mock.calls.filter(
          (call) => call[0] === "/api/virtual-folders"
        );
        expect(getCalls.length).toBeGreaterThanOrEqual(1);
      }),
      { numRuns: 100 }
    );
  });

  it("updateFolder calls fetchFolders (GET /api/virtual-folders) after successful update", async () => {
    await fc.assert(
      fc.asyncProperty(folderIdArb, folderNameArb, tagFilterArb, sortOrderArb, async (id, name, tagFilter, sortOrder) => {
        vi.clearAllMocks();
        mockedApiClient.get.mockResolvedValue([]);
        mockedApiClient.put.mockResolvedValue({
          id,
          name,
          tag_filter: tagFilter,
          sort_order: sortOrder,
          is_system_default: false,
          created_by: 1,
          created_at: null,
        });

        // Set up a folder in the store so updateFolder can find it
        useVirtualFolderStore.setState({
          folders: [{
            id,
            name: "Original",
            tag_filter: {},
            sort_order: "created_at_desc",
            is_system_default: false,
            created_by: 1,
            created_at: null,
          }],
        });

        await useVirtualFolderStore.getState().updateFolder(id, { name, tag_filter: tagFilter, sort_order: sortOrder });

        // Verify that GET /api/virtual-folders was called (fetchFolders triggered)
        const getCalls = mockedApiClient.get.mock.calls.filter(
          (call) => call[0] === "/api/virtual-folders"
        );
        expect(getCalls.length).toBeGreaterThanOrEqual(1);
      }),
      { numRuns: 100 }
    );
  });

  it("deleteFolder calls fetchFolders (GET /api/virtual-folders) after successful deletion", async () => {
    await fc.assert(
      fc.asyncProperty(folderIdArb, folderNameArb, async (id, reason) => {
        vi.clearAllMocks();
        mockedApiClient.get.mockResolvedValue([]);
        mockedApiClient.delete.mockResolvedValue(undefined);

        // Set up a folder in the store so deleteFolder can operate
        useVirtualFolderStore.setState({
          folders: [{
            id,
            name: "ToDelete",
            tag_filter: {},
            sort_order: "created_at_desc",
            is_system_default: false,
            created_by: 1,
            created_at: null,
          }],
        });

        await useVirtualFolderStore.getState().deleteFolder(id, reason);

        // Verify that GET /api/virtual-folders was called (fetchFolders triggered)
        const getCalls = mockedApiClient.get.mock.calls.filter(
          (call) => call[0] === "/api/virtual-folders"
        );
        expect(getCalls.length).toBeGreaterThanOrEqual(1);
      }),
      { numRuns: 100 }
    );
  });
});
