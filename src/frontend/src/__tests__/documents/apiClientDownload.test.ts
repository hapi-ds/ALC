/**
 * Unit tests for apiClient.download() and triggerBrowserDownload utility.
 *
 * Validates: Requirements 7.1, 7.2, 7.3
 *
 * - apiClient.download() returns Blob on success (7.1)
 * - apiClient.download() throws ApiError on 401/403/404 (7.3)
 * - triggerBrowserDownload creates anchor, triggers click, revokes URL (7.2)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { apiClient, ApiError } from "@/lib/apiClient";
import * as tokenStorage from "@/lib/tokenStorage";
import { triggerBrowserDownload } from "@/lib/fileDownload";

// Mock tokenStorage
vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
}));

// Mock global fetch
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("apiClient.download", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (tokenStorage.getAccessToken as ReturnType<typeof vi.fn>).mockReturnValue(
      "test-token-abc"
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a Blob on successful response", async () => {
    const fakeBlob = new Blob(["pdf content here"], {
      type: "application/pdf",
    });
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      blob: () => Promise.resolve(fakeBlob),
    });

    const result = await apiClient.download(
      "/api/documents/doc-uuid/versions/1/0/download"
    );

    expect(result).toBeInstanceOf(Blob);
    expect(result.size).toBe(fakeBlob.size);
    expect(result.type).toBe("application/pdf");
  });

  it("throws ApiError with status 403 on forbidden response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      text: () => Promise.resolve('{"detail": "Insufficient permissions"}'),
    });

    await expect(
      apiClient.download("/api/documents/doc-uuid/versions/1/0/download")
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(403);
      expect((err as ApiError).body).toContain("Insufficient permissions");
      return true;
    });
  });

  it("throws ApiError with status 404 on not found response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      text: () =>
        Promise.resolve('{"detail": "Document version not found"}'),
    });

    await expect(
      apiClient.download("/api/documents/missing/versions/1/0/download")
    ).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
      return true;
    });
  });

  it("throws error on 401 when token refresh fails", async () => {
    // First call returns 401
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: () => Promise.resolve('{"detail": "Not authenticated"}'),
    });

    // Refresh attempt fails
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
    });

    await expect(
      apiClient.download("/api/documents/doc-uuid/versions/1/0/download")
    ).rejects.toThrow("Session expired");
  });
});

describe("triggerBrowserDownload", () => {
  let mockCreateObjectURL: ReturnType<typeof vi.fn>;
  let mockRevokeObjectURL: ReturnType<typeof vi.fn>;
  let mockAnchor: {
    href: string;
    download: string;
    style: { display: string };
    click: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    mockCreateObjectURL = vi.fn().mockReturnValue("blob:http://localhost/fake-url");
    mockRevokeObjectURL = vi.fn();

    vi.stubGlobal("URL", {
      createObjectURL: mockCreateObjectURL,
      revokeObjectURL: mockRevokeObjectURL,
    });

    mockAnchor = {
      href: "",
      download: "",
      style: { display: "" },
      click: vi.fn(),
    };

    vi.spyOn(document, "createElement").mockReturnValue(
      mockAnchor as unknown as HTMLElement
    );
    vi.spyOn(document.body, "appendChild").mockImplementation(
      (node) => node as HTMLElement
    );
    vi.spyOn(document.body, "removeChild").mockImplementation(
      (node) => node as HTMLElement
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates an object URL from the blob", () => {
    const blob = new Blob(["test data"], { type: "application/pdf" });

    triggerBrowserDownload(blob, "report.pdf");

    expect(mockCreateObjectURL).toHaveBeenCalledWith(blob);
  });

  it("sets anchor href to the object URL and download to the filename", () => {
    const blob = new Blob(["content"], { type: "text/plain" });

    triggerBrowserDownload(blob, "notes.txt");

    expect(mockAnchor.href).toBe("blob:http://localhost/fake-url");
    expect(mockAnchor.download).toBe("notes.txt");
  });

  it("clicks the anchor element to trigger the save dialog", () => {
    const blob = new Blob(["data"], { type: "application/octet-stream" });

    triggerBrowserDownload(blob, "file.bin");

    expect(mockAnchor.click).toHaveBeenCalledTimes(1);
  });

  it("appends and removes the anchor from the DOM", () => {
    const blob = new Blob(["data"], { type: "application/pdf" });

    triggerBrowserDownload(blob, "doc.pdf");

    expect(document.body.appendChild).toHaveBeenCalledWith(mockAnchor);
    expect(document.body.removeChild).toHaveBeenCalledWith(mockAnchor);
  });

  it("revokes the object URL for cleanup", () => {
    const blob = new Blob(["bytes"], { type: "image/png" });

    triggerBrowserDownload(blob, "image.png");

    expect(mockRevokeObjectURL).toHaveBeenCalledWith(
      "blob:http://localhost/fake-url"
    );
  });

  it("revokes the object URL even if click throws", () => {
    mockAnchor.click.mockImplementation(() => {
      throw new Error("click failed");
    });

    const blob = new Blob(["data"], { type: "text/plain" });

    expect(() => triggerBrowserDownload(blob, "file.txt")).toThrow(
      "click failed"
    );
    expect(mockRevokeObjectURL).toHaveBeenCalledWith(
      "blob:http://localhost/fake-url"
    );
  });

  it("trims whitespace from filename and defaults to 'download' for empty names", () => {
    const blob = new Blob(["data"], { type: "text/plain" });

    triggerBrowserDownload(blob, "   ");

    expect(mockAnchor.download).toBe("download");
  });

  it("hides the anchor element with display:none", () => {
    const blob = new Blob(["data"], { type: "application/pdf" });

    triggerBrowserDownload(blob, "report.pdf");

    expect(mockAnchor.style.display).toBe("none");
  });
});
