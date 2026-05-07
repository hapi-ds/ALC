import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useDocumentStore } from "@/stores/documentStore";
import { apiClient, ApiError } from "@/lib/apiClient";
import type { DocumentVersion } from "@/types/document";

// Mock apiClient module - the store uses apiClient.get for fetchVersion
// Endpoint verified: GET /api/documents/{uuid}/versions/{major}/{minor}
vi.mock("@/lib/apiClient", () => {
  const ApiError = class ApiError extends Error {
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
  };

  return {
    apiClient: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      upload: vi.fn(),
    },
    ApiError,
  };
});

// Mock tokenStorage - used by downloadVersion for auth header
vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(() => "mock-token"),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
}));

const mockedApiClient = vi.mocked(apiClient);

const mockVersion: DocumentVersion = {
  id: 1,
  major_version: 1,
  minor_version: 0,
  storage_key: "docs/abc123/v1.0.pdf",
  file_hash: "a".repeat(64),
  uploaded_by: 42,
  uploaded_at: "2024-01-15T10:30:00Z",
  change_reason: "Initial upload",
};

describe("documentStore version actions", () => {
  beforeEach(() => {
    useDocumentStore.setState({
      selectedVersion: null,
      isVersionLoading: false,
      versionError: null,
      downloadingVersionId: null,
      comparisonOpen: false,
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("fetchVersion", () => {
    it("sets selectedVersion on success and clears loading state", async () => {
      mockedApiClient.get.mockResolvedValueOnce(mockVersion);

      await useDocumentStore.getState().fetchVersion("doc-uuid-123", 1, 0);

      const state = useDocumentStore.getState();
      expect(state.selectedVersion).toEqual(mockVersion);
      expect(state.isVersionLoading).toBe(false);
      expect(state.versionError).toBeNull();
    });

    it("sets loading state before API call", async () => {
      let loadingDuringCall = false;
      let selectedDuringCall: DocumentVersion | null = { id: 999 } as DocumentVersion;

      mockedApiClient.get.mockImplementationOnce(() => {
        const state = useDocumentStore.getState();
        loadingDuringCall = state.isVersionLoading;
        selectedDuringCall = state.selectedVersion;
        return Promise.resolve(mockVersion);
      });

      await useDocumentStore.getState().fetchVersion("doc-uuid-123", 1, 0);

      expect(loadingDuringCall).toBe(true);
      expect(selectedDuringCall).toBeNull();
    });

    it("sets versionError to 'Version not found' on 404", async () => {
      mockedApiClient.get.mockRejectedValueOnce(
        new ApiError(404, "Not Found", "/api/documents/doc-uuid/versions/1/0")
      );

      await useDocumentStore.getState().fetchVersion("doc-uuid", 1, 0);

      const state = useDocumentStore.getState();
      expect(state.versionError).toBe("Version not found");
      expect(state.selectedVersion).toBeNull();
      expect(state.isVersionLoading).toBe(false);
    });

    it("sets versionError from error message on non-404 error", async () => {
      mockedApiClient.get.mockRejectedValueOnce(
        new ApiError(500, "Internal Server Error", "/api/documents/doc-uuid/versions/1/0")
      );

      await useDocumentStore.getState().fetchVersion("doc-uuid", 1, 0);

      const state = useDocumentStore.getState();
      expect(state.versionError).toBe(
        "API error 500 on /api/documents/doc-uuid/versions/1/0"
      );
      expect(state.selectedVersion).toBeNull();
      expect(state.isVersionLoading).toBe(false);
    });

    it("handles generic Error (network failure)", async () => {
      mockedApiClient.get.mockRejectedValueOnce(new Error("Network failure"));

      await useDocumentStore.getState().fetchVersion("doc-uuid", 1, 0);

      const state = useDocumentStore.getState();
      expect(state.versionError).toBe("Network failure");
      expect(state.selectedVersion).toBeNull();
      expect(state.isVersionLoading).toBe(false);
    });

    it("calls the correct API endpoint", async () => {
      mockedApiClient.get.mockResolvedValueOnce(mockVersion);

      await useDocumentStore.getState().fetchVersion("my-doc-uuid", 2, 3);

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/documents/my-doc-uuid/versions/2/3"
      );
    });
  });

  describe("downloadVersion", () => {
    it("creates blob URL and triggers download", async () => {
      const mockBlob = new Blob(["file content"], { type: "application/pdf" });
      const mockResponse = {
        ok: true,
        blob: vi.fn().mockResolvedValue(mockBlob),
      };

      const fetchSpy = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValueOnce(mockResponse as unknown as Response);

      const mockUrl = "blob:http://localhost/mock-blob-url";
      const createObjectURLSpy = vi
        .spyOn(URL, "createObjectURL")
        .mockReturnValue(mockUrl);
      const revokeObjectURLSpy = vi
        .spyOn(URL, "revokeObjectURL")
        .mockImplementation(() => {});

      const mockAnchor = { href: "", download: "", click: vi.fn() };
      const createElementSpy = vi
        .spyOn(document, "createElement")
        .mockReturnValue(mockAnchor as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, "appendChild").mockImplementation((n) => n);
      vi.spyOn(document.body, "removeChild").mockImplementation((n) => n);

      await useDocumentStore
        .getState()
        .downloadVersion("doc-uuid-123", mockVersion, "TestDocument");

      // Verify fetch called with correct download URL
      expect(fetchSpy).toHaveBeenCalledWith(
        "/api/documents/doc-uuid-123/versions/1/0/download",
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: "Bearer mock-token",
          }),
          credentials: "include",
        })
      );

      // Verify blob URL created
      expect(createObjectURLSpy).toHaveBeenCalledWith(mockBlob);

      // Verify anchor configured and clicked
      expect(createElementSpy).toHaveBeenCalledWith("a");
      expect(mockAnchor.href).toBe(mockUrl);
      expect(mockAnchor.download).toBe("TestDocument_v1.0");
      expect(mockAnchor.click).toHaveBeenCalled();

      // Verify URL revoked
      expect(revokeObjectURLSpy).toHaveBeenCalledWith(mockUrl);

      // Verify downloadingVersionId cleared
      expect(useDocumentStore.getState().downloadingVersionId).toBeNull();
    });

    it("sets downloadingVersionId during download", async () => {
      let downloadingIdDuringFetch: number | null = null;

      const mockBlob = new Blob(["content"]);
      vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => {
        downloadingIdDuringFetch = useDocumentStore.getState().downloadingVersionId;
        return Promise.resolve({
          ok: true,
          blob: () => Promise.resolve(mockBlob),
        } as Response);
      });

      vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock");
      vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
      vi.spyOn(document, "createElement").mockReturnValue({
        href: "",
        download: "",
        click: vi.fn(),
      } as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, "appendChild").mockImplementation((n) => n);
      vi.spyOn(document.body, "removeChild").mockImplementation((n) => n);

      await useDocumentStore.getState().downloadVersion("doc-uuid", mockVersion, "Doc");

      expect(downloadingIdDuringFetch).toBe(mockVersion.id);
      expect(useDocumentStore.getState().downloadingVersionId).toBeNull();
    });

    it("clears downloadingVersionId on fetch error", async () => {
      vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new Error("Network error"));

      await useDocumentStore.getState().downloadVersion("doc-uuid", mockVersion, "Doc");

      expect(useDocumentStore.getState().downloadingVersionId).toBeNull();
    });
  });

  describe("clearSelectedVersion", () => {
    it("resets selectedVersion, versionError, and isVersionLoading", () => {
      useDocumentStore.setState({
        selectedVersion: mockVersion,
        versionError: "Some error",
        isVersionLoading: true,
      });

      useDocumentStore.getState().clearSelectedVersion();

      const state = useDocumentStore.getState();
      expect(state.selectedVersion).toBeNull();
      expect(state.versionError).toBeNull();
      expect(state.isVersionLoading).toBe(false);
    });
  });

  describe("selectVersionFromCache", () => {
    it("sets selectedVersion and clears versionError", () => {
      useDocumentStore.setState({
        versionError: "Previous error",
        selectedVersion: null,
      });

      useDocumentStore.getState().selectVersionFromCache(mockVersion);

      const state = useDocumentStore.getState();
      expect(state.selectedVersion).toEqual(mockVersion);
      expect(state.versionError).toBeNull();
    });
  });

  describe("setComparisonOpen", () => {
    it("sets comparisonOpen to true", () => {
      useDocumentStore.getState().setComparisonOpen(true);
      expect(useDocumentStore.getState().comparisonOpen).toBe(true);
    });

    it("sets comparisonOpen to false", () => {
      useDocumentStore.setState({ comparisonOpen: true });
      useDocumentStore.getState().setComparisonOpen(false);
      expect(useDocumentStore.getState().comparisonOpen).toBe(false);
    });
  });
});
