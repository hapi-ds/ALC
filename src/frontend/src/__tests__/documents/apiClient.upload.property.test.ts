import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: document-upload-list, Property 8: API client upload method sets correct headers
 *
 * Validates: Requirements 9.1, 9.2, 9.3
 *
 * For any access token, userId, and companyId, verify:
 * - Authorization header equals `Bearer {token}`
 * - X-Company-Id header equals the companyId
 * - X-User-Id header equals the userId
 * - Content-Type is NOT set to `application/json`
 */

// Mock tokenStorage before importing apiClient
vi.mock("../../lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
}));

import { apiClient, setAuthStoreAccessor } from "../../lib/apiClient";
import { getAccessToken } from "../../lib/tokenStorage";

describe("Feature: document-upload-list, Property 8: API client upload method sets correct headers", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    vi.resetAllMocks();
    globalThis.fetch = mockFetch;
  });

  afterEach(() => {
    setAuthStoreAccessor(() => ({ userId: null, companyId: null }));
    vi.restoreAllMocks();
  });

  it("sets Authorization to Bearer {token} for any access token", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 300 }),
        async (token) => {
          mockFetch.mockReset();
          mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve(""),
          });
          vi.mocked(getAccessToken).mockReturnValue(token);
          setAuthStoreAccessor(() => ({ userId: 1, companyId: 1 }));

          const formData = new FormData();
          formData.append("file", new Blob(["test"]), "test.txt");

          await apiClient.upload("/api/v1/documents", formData);

          expect(mockFetch).toHaveBeenCalledTimes(1);
          const [, init] = mockFetch.mock.calls[0];
          const headers = init.headers as Record<string, string>;
          expect(headers["Authorization"]).toBe(`Bearer ${token}`);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("sets X-Company-Id and X-User-Id headers from auth context", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 100000 }),
        fc.integer({ min: 1, max: 100000 }),
        async (userId, companyId) => {
          mockFetch.mockReset();
          mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve(""),
          });
          vi.mocked(getAccessToken).mockReturnValue("some-token");
          setAuthStoreAccessor(() => ({ userId, companyId }));

          const formData = new FormData();
          formData.append("file", new Blob(["test"]), "test.txt");

          await apiClient.upload("/api/v1/documents", formData);

          expect(mockFetch).toHaveBeenCalledTimes(1);
          const [, init] = mockFetch.mock.calls[0];
          const headers = init.headers as Record<string, string>;
          expect(headers["X-Company-Id"]).toBe(String(companyId));
          expect(headers["X-User-Id"]).toBe(String(userId));
        }
      ),
      { numRuns: 100 }
    );
  });

  it("does NOT set Content-Type to application/json", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 300 }),
        fc.integer({ min: 1, max: 100000 }),
        fc.integer({ min: 1, max: 100000 }),
        async (token, userId, companyId) => {
          mockFetch.mockReset();
          mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve(""),
          });
          vi.mocked(getAccessToken).mockReturnValue(token);
          setAuthStoreAccessor(() => ({ userId, companyId }));

          const formData = new FormData();
          formData.append("file", new Blob(["content"]), "doc.pdf");

          await apiClient.upload("/api/v1/documents", formData);

          expect(mockFetch).toHaveBeenCalledTimes(1);
          const [, init] = mockFetch.mock.calls[0];
          const headers = init.headers as Record<string, string>;
          expect(headers["Content-Type"]).not.toBe("application/json");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("sets all correct headers together for any token, userId, and companyId", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 300 }),
        fc.integer({ min: 1, max: 100000 }),
        fc.integer({ min: 1, max: 100000 }),
        async (token, userId, companyId) => {
          mockFetch.mockReset();
          mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: () => Promise.resolve({}),
            text: () => Promise.resolve(""),
          });
          vi.mocked(getAccessToken).mockReturnValue(token);
          setAuthStoreAccessor(() => ({ userId, companyId }));

          const formData = new FormData();
          formData.append("file", new Blob(["data"]), "file.txt");

          await apiClient.upload("/api/v1/documents", formData);

          expect(mockFetch).toHaveBeenCalledTimes(1);
          const [, init] = mockFetch.mock.calls[0];
          const headers = init.headers as Record<string, string>;

          // Req 9.2: Bearer token attached
          expect(headers["Authorization"]).toBe(`Bearer ${token}`);
          // Req 9.3: Tenant headers attached
          expect(headers["X-Company-Id"]).toBe(String(companyId));
          expect(headers["X-User-Id"]).toBe(String(userId));
          // Req 9.1: Content-Type is NOT application/json
          expect(headers["Content-Type"]).not.toBe("application/json");
        }
      ),
      { numRuns: 100 }
    );
  });
});
