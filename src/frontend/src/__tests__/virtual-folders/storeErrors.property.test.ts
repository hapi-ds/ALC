import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fc from "fast-check";
import { useVirtualFolderStore } from "../../stores/virtualFolderStore";
import { apiClient } from "../../lib/apiClient";

/**
 * Feature: virtual-folders-frontend, Property 9: Failed store actions set error and clear loading
 *
 * Validates: Requirements 9.6
 *
 * For any store action (fetchFolders, createFolder, updateFolder, deleteFolder,
 * fetchFolderDocuments) that encounters an API error, the store SHALL set the
 * corresponding error property to a non-empty string and set the corresponding
 * loading property to false.
 */

vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockedApiClient = vi.mocked(apiClient);

const errorMessageArb = fc.string({ minLength: 1, maxLength: 200 });

function resetStore() {
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
}

describe("Feature: virtual-folders-frontend, Property 9: Failed store actions set error and clear loading", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  it("fetchFolders: error sets foldersError to non-empty string and isFoldersLoading to false", async () => {
    await fc.assert(
      fc.asyncProperty(errorMessageArb, async (errorMsg) => {
        resetStore();
        mockedApiClient.get.mockRejectedValueOnce(new Error(errorMsg));

        await useVirtualFolderStore.getState().fetchFolders();

        const state = useVirtualFolderStore.getState();
        expect(state.foldersError).toBeTruthy();
        expect(typeof state.foldersError).toBe("string");
        expect(state.foldersError!.length).toBeGreaterThan(0);
        expect(state.isFoldersLoading).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("fetchFolderDocuments: error sets documentsError to non-empty string and isDocumentsLoading to false", async () => {
    await fc.assert(
      fc.asyncProperty(errorMessageArb, async (errorMsg) => {
        resetStore();
        mockedApiClient.get.mockRejectedValueOnce(new Error(errorMsg));

        await useVirtualFolderStore.getState().fetchFolderDocuments(1);

        const state = useVirtualFolderStore.getState();
        expect(state.documentsError).toBeTruthy();
        expect(typeof state.documentsError).toBe("string");
        expect(state.documentsError!.length).toBeGreaterThan(0);
        expect(state.isDocumentsLoading).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("createFolder: error sets foldersError to non-empty string and isFoldersLoading to false", async () => {
    await fc.assert(
      fc.asyncProperty(errorMessageArb, async (errorMsg) => {
        resetStore();
        mockedApiClient.post.mockRejectedValueOnce(new Error(errorMsg));

        try {
          await useVirtualFolderStore
            .getState()
            .createFolder("Test Folder", { tags: ["SOP"] }, "created_at_desc");
        } catch {
          // createFolder re-throws the error, which is expected
        }

        const state = useVirtualFolderStore.getState();
        expect(state.foldersError).toBeTruthy();
        expect(typeof state.foldersError).toBe("string");
        expect(state.foldersError!.length).toBeGreaterThan(0);
        expect(state.isFoldersLoading).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("updateFolder: error sets foldersError to non-empty string and isFoldersLoading to false", async () => {
    await fc.assert(
      fc.asyncProperty(errorMessageArb, async (errorMsg) => {
        resetStore();
        mockedApiClient.put.mockRejectedValueOnce(new Error(errorMsg));

        try {
          await useVirtualFolderStore
            .getState()
            .updateFolder(1, { name: "Updated Name" });
        } catch {
          // updateFolder re-throws the error, which is expected
        }

        const state = useVirtualFolderStore.getState();
        expect(state.foldersError).toBeTruthy();
        expect(typeof state.foldersError).toBe("string");
        expect(state.foldersError!.length).toBeGreaterThan(0);
        expect(state.isFoldersLoading).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("deleteFolder: error sets foldersError to non-empty string and isFoldersLoading to false", async () => {
    await fc.assert(
      fc.asyncProperty(errorMessageArb, async (errorMsg) => {
        resetStore();
        mockedApiClient.delete.mockRejectedValueOnce(new Error(errorMsg));

        try {
          await useVirtualFolderStore
            .getState()
            .deleteFolder(1, "Removing unused folder");
        } catch {
          // deleteFolder re-throws the error, which is expected
        }

        const state = useVirtualFolderStore.getState();
        expect(state.foldersError).toBeTruthy();
        expect(typeof state.foldersError).toBe("string");
        expect(state.foldersError!.length).toBeGreaterThan(0);
        expect(state.isFoldersLoading).toBe(false);
      }),
      { numRuns: 100 }
    );
  });
});
