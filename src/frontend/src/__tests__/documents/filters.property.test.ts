import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";
import { useDocumentStore } from "../../stores/documentStore";
import { apiClient } from "../../lib/apiClient";

/**
 * Feature: document-upload-list, Property 3: Applying a filter resets pagination to first page
 *
 * Validates: Requirements 3.3
 *
 * For any current offset greater than 0, applying either a tag filter or a
 * folder path filter should reset the offset to 0.
 */

describe("Feature: document-upload-list, Property 3: Applying a filter resets pagination to first page", () => {
  beforeEach(() => {
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

  it("setTagFilter resets offset to 0 for any offset > 0 and any tag string", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // offset > 0
        fc.string({ minLength: 1, maxLength: 100 }), // non-empty tag
        (offset, tag) => {
          useDocumentStore.setState({ offset });

          useDocumentStore.getState().setTagFilter(tag);
          const state = useDocumentStore.getState();

          expect(state.offset).toBe(0);
          expect(state.tagFilter).toBe(tag);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("setFolderPathFilter resets offset to 0 for any offset > 0 and any folder path string", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // offset > 0
        fc.string({ minLength: 1, maxLength: 200 }), // non-empty folder path
        (offset, folderPath) => {
          useDocumentStore.setState({ offset });

          useDocumentStore.getState().setFolderPathFilter(folderPath);
          const state = useDocumentStore.getState();

          expect(state.offset).toBe(0);
          expect(state.folderPathFilter).toBe(folderPath);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("setTagFilter with null resets offset to 0 for any offset > 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // offset > 0
        (offset) => {
          useDocumentStore.setState({ offset, tagFilter: "existing-tag" });

          useDocumentStore.getState().setTagFilter(null);
          const state = useDocumentStore.getState();

          expect(state.offset).toBe(0);
          expect(state.tagFilter).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("setFolderPathFilter with null resets offset to 0 for any offset > 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // offset > 0
        (offset) => {
          useDocumentStore.setState({ offset, folderPathFilter: "/some/path" });

          useDocumentStore.getState().setFolderPathFilter(null);
          const state = useDocumentStore.getState();

          expect(state.offset).toBe(0);
          expect(state.folderPathFilter).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("clearFilters resets offset to 0 for any offset > 0", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10000 }), // offset > 0
        fc.string({ minLength: 1, maxLength: 100 }), // tag
        fc.string({ minLength: 1, maxLength: 200 }), // folder path
        (offset, tag, folderPath) => {
          useDocumentStore.setState({ offset, tagFilter: tag, folderPathFilter: folderPath });

          useDocumentStore.getState().clearFilters();
          const state = useDocumentStore.getState();

          expect(state.offset).toBe(0);
          expect(state.tagFilter).toBeNull();
          expect(state.folderPathFilter).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });
});

/**
 * Feature: document-upload-list, Property 4: Active filters map to API query parameters
 *
 * Validates: Requirements 3.1, 3.2
 *
 * For any non-null tag string and/or non-null folder_path string set in the store,
 * the resulting API request URL should contain the corresponding `tag` and/or
 * `folder_path` query parameters with those exact values.
 */

describe("Feature: document-upload-list, Property 4: Active filters map to API query parameters", () => {
  let capturedUrl: string;

  beforeEach(() => {
    capturedUrl = "";
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

    vi.spyOn(apiClient, "get").mockImplementation(async (url: string) => {
      capturedUrl = url;
      return { items: [], total: 0 };
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("when tagFilter is set, the API request URL contains the tag query param with that value", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
        async (tag) => {
          useDocumentStore.setState({ tagFilter: tag });

          await useDocumentStore.getState().fetchDocuments();

          const url = new URL(capturedUrl, "http://localhost");
          expect(url.searchParams.get("tag")).toBe(tag);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("when folderPathFilter is set, the API request URL contains the folder_path query param with that value", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length > 0),
        async (folderPath) => {
          useDocumentStore.setState({ folderPathFilter: folderPath });

          await useDocumentStore.getState().fetchDocuments();

          const url = new URL(capturedUrl, "http://localhost");
          expect(url.searchParams.get("folder_path")).toBe(folderPath);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("when both tagFilter and folderPathFilter are set, the API request URL contains both query params", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
        fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length > 0),
        async (tag, folderPath) => {
          useDocumentStore.setState({ tagFilter: tag, folderPathFilter: folderPath });

          await useDocumentStore.getState().fetchDocuments();

          const url = new URL(capturedUrl, "http://localhost");
          expect(url.searchParams.get("tag")).toBe(tag);
          expect(url.searchParams.get("folder_path")).toBe(folderPath);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("when tagFilter is null, the API request URL does not contain the tag query param", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length > 0),
        async (folderPath) => {
          useDocumentStore.setState({ tagFilter: null, folderPathFilter: folderPath });

          await useDocumentStore.getState().fetchDocuments();

          const url = new URL(capturedUrl, "http://localhost");
          expect(url.searchParams.has("tag")).toBe(false);
          expect(url.searchParams.get("folder_path")).toBe(folderPath);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("when folderPathFilter is null, the API request URL does not contain the folder_path query param", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
        async (tag) => {
          useDocumentStore.setState({ tagFilter: tag, folderPathFilter: null });

          await useDocumentStore.getState().fetchDocuments();

          const url = new URL(capturedUrl, "http://localhost");
          expect(url.searchParams.get("tag")).toBe(tag);
          expect(url.searchParams.has("folder_path")).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});
