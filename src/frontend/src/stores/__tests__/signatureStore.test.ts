import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

/**
 * Unit tests for signatureStore
 *
 * These tests cover all state transitions for the signatureStore actions,
 * mocking apiClient calls to verify correct behavior on success and failure.
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11
 */

// Mock apiClient — all API calls are mocked; no real backend calls are made.
// Verified endpoints from signatureStore.ts:
//   POST /api/v1/auth/re-authenticate (auth uses /api/v1 prefix)
//   POST /api/signatures/sign (uses /api prefix)
//   GET  /api/signatures/records/{document_uuid} (uses /api prefix)
//   GET  /api/signatures/verify/{document_uuid} (uses /api prefix)
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
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
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

vi.mock("../authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 1,
    }),
    setState: vi.fn(),
  },
}));

import { useSignatureStore } from "../signatureStore";
import { apiClient, ApiError } from "@/lib/apiClient";
import type { SignatureDialogContext } from "@/types/signature";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe("signatureStore unit tests", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const mockDialogContext: SignatureDialogContext = {
    document_uuid: "doc-abc-123",
    document_version_id: 5,
    transition: "Review\u2192Approved",
    documentTitle: "SOP-001 Standard Operating Procedure",
  };

  // ---------------------------------------------------------------------------
  // 1. openSignatureDialog
  // ---------------------------------------------------------------------------
  describe("openSignatureDialog", () => {
    it("sets isDialogOpen=true and dialogContext to the provided context", () => {
      useSignatureStore.getState().openSignatureDialog(mockDialogContext);

      const state = useSignatureStore.getState();
      expect(state.isDialogOpen).toBe(true);
      expect(state.dialogContext).toEqual(mockDialogContext);
    });

    it("if already open, closes first (clears prior state) then opens with new context", () => {
      // Open with first context
      const firstContext: SignatureDialogContext = {
        document_uuid: "doc-first",
        document_version_id: 1,
        transition: "Draft\u2192Review",
        documentTitle: "First Document",
      };
      useSignatureStore.getState().openSignatureDialog(firstContext);

      // Set some state that closeSignatureDialog should clear
      useSignatureStore.setState({
        signError: "some error",
        lastSignResult: {
          success: true,
          signature_hash: "abc123",
          signature_record_id: 1,
          stamp: {
            signer_name: "Test",
            signed_at: "2024-01-01T00:00:00Z",
            reason: "Test",
            transition: "Draft\u2192Review",
          },
        },
        signatureToken: "old-token",
        tokenExpiresAt: Date.now() + 60000,
        remainingSeconds: 60,
      });

      // Open with second context (should close first)
      useSignatureStore.getState().openSignatureDialog(mockDialogContext);

      const state = useSignatureStore.getState();
      expect(state.isDialogOpen).toBe(true);
      expect(state.dialogContext).toEqual(mockDialogContext);
      // Prior state should be cleared by closeSignatureDialog
      expect(state.signError).toBeNull();
      expect(state.lastSignResult).toBeNull();
      expect(state.signatureToken).toBeNull();
      expect(state.tokenExpiresAt).toBeNull();
      expect(state.remainingSeconds).toBe(0);
    });
  });

  // ---------------------------------------------------------------------------
  // 2. closeSignatureDialog
  // ---------------------------------------------------------------------------
  describe("closeSignatureDialog", () => {
    it("sets isDialogOpen=false, dialogContext=null", () => {
      useSignatureStore.getState().openSignatureDialog(mockDialogContext);
      useSignatureStore.getState().closeSignatureDialog();

      const state = useSignatureStore.getState();
      expect(state.isDialogOpen).toBe(false);
      expect(state.dialogContext).toBeNull();
    });

    it("clears signError and lastSignResult", () => {
      useSignatureStore.setState({
        isDialogOpen: true,
        signError: "Some signing error",
        lastSignResult: {
          success: true,
          signature_hash: "hash123",
          signature_record_id: 1,
          stamp: {
            signer_name: "User",
            signed_at: "2024-01-01T00:00:00Z",
            reason: "Approval: test",
            transition: "Review\u2192Approved",
          },
        },
      });

      useSignatureStore.getState().closeSignatureDialog();

      const state = useSignatureStore.getState();
      expect(state.signError).toBeNull();
      expect(state.lastSignResult).toBeNull();
    });

    it("invokes clearToken (signatureToken=null, tokenExpiresAt=null, remainingSeconds=0)", () => {
      useSignatureStore.setState({
        isDialogOpen: true,
        signatureToken: "token-xyz",
        tokenExpiresAt: Date.now() + 120000,
        remainingSeconds: 100,
      });

      useSignatureStore.getState().closeSignatureDialog();

      const state = useSignatureStore.getState();
      expect(state.signatureToken).toBeNull();
      expect(state.tokenExpiresAt).toBeNull();
      expect(state.remainingSeconds).toBe(0);
    });
  });

  // ---------------------------------------------------------------------------
  // 3. reAuthenticate
  // ---------------------------------------------------------------------------
  describe("reAuthenticate", () => {
    it("on success: sets signatureToken, tokenExpiresAt, _password, isReAuthenticating=false", async () => {
      const mockResponse = {
        verified: true,
        signature_token: "sig-token-abc",
        expires_in: 120,
      };
      mockedApiClient.post.mockResolvedValue(mockResponse);

      const beforeTime = Date.now();
      await useSignatureStore.getState().reAuthenticate("myPassword123");
      const afterTime = Date.now();

      const state = useSignatureStore.getState();
      expect(state.signatureToken).toBe("sig-token-abc");
      expect(state.tokenExpiresAt).toBeGreaterThanOrEqual(beforeTime + 120000);
      expect(state.tokenExpiresAt).toBeLessThanOrEqual(afterTime + 120000);
      expect(state._password).toBe("myPassword123");
      expect(state.isReAuthenticating).toBe(false);
      expect(state.reAuthError).toBeNull();
    });

    it("calls POST with correct URL, body, and changeReason", async () => {
      mockedApiClient.post.mockResolvedValue({
        verified: true,
        signature_token: "token",
        expires_in: 120,
      });

      await useSignatureStore.getState().reAuthenticate("testPass");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/v1/auth/re-authenticate",
        { password: "testPass" },
        { changeReason: "Re-authentication for electronic signature" }
      );
    });

    it("on failure (401): sets reAuthError with extracted message, isReAuthenticating=false", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          401,
          JSON.stringify({ detail: "Invalid password. Please try again." }),
          "/api/v1/auth/re-authenticate"
        )
      );

      await useSignatureStore.getState().reAuthenticate("wrongPassword");

      const state = useSignatureStore.getState();
      expect(state.reAuthError).toBe("Invalid password. Please try again.");
      expect(state.isReAuthenticating).toBe(false);
      expect(state.signatureToken).toBeNull();
    });

    it("while in progress: isReAuthenticating=true, reAuthError=null", async () => {
      let resolvePromise: (value: unknown) => void;
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      mockedApiClient.post.mockReturnValue(pendingPromise);

      // Start the async operation (don't await)
      const promise = useSignatureStore.getState().reAuthenticate("password");

      // Check intermediate state
      const state = useSignatureStore.getState();
      expect(state.isReAuthenticating).toBe(true);
      expect(state.reAuthError).toBeNull();

      // Resolve to clean up
      resolvePromise!({
        verified: true,
        signature_token: "token",
        expires_in: 120,
      });
      await promise;
    });

    it("on failure with non-JSON body: falls back to body string", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          500,
          "Internal Server Error",
          "/api/v1/auth/re-authenticate"
        )
      );

      await useSignatureStore.getState().reAuthenticate("password");

      const state = useSignatureStore.getState();
      expect(state.reAuthError).toBe("Internal Server Error");
      expect(state.isReAuthenticating).toBe(false);
    });

    it("on network error (generic Error): uses error.message", async () => {
      mockedApiClient.post.mockRejectedValue(
        new Error("Network error: Unable to reach the server.")
      );

      await useSignatureStore.getState().reAuthenticate("password");

      const state = useSignatureStore.getState();
      expect(state.reAuthError).toBe(
        "Network error: Unable to reach the server."
      );
      expect(state.isReAuthenticating).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // 4. signDocument
  // ---------------------------------------------------------------------------
  describe("signDocument", () => {
    it("on success: sets lastSignResult, isSigning=false", async () => {
      const mockResponse = {
        success: true,
        signature_hash:
          "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        signature_record_id: 42,
        stamp: {
          signer_name: "John Doe",
          signed_at: "2024-06-15T10:30:00Z",
          reason: "Approval: Approved by QA Manager",
          transition: "Review\u2192Approved",
        },
      };
      mockedApiClient.post.mockResolvedValue(mockResponse);

      await useSignatureStore
        .getState()
        .signDocument(
          "doc-123",
          5,
          "Review\u2192Approved",
          "Approval: Approved by QA Manager",
          "password123"
        );

      const state = useSignatureStore.getState();
      expect(state.lastSignResult).toEqual(mockResponse);
      expect(state.isSigning).toBe(false);
      expect(state.signError).toBeNull();
    });

    it("sends correct X-Change-Reason header via changeReason option", async () => {
      mockedApiClient.post.mockResolvedValue({
        success: true,
        signature_hash: "hash",
        signature_record_id: 1,
        stamp: {
          signer_name: "User",
          signed_at: "2024-01-01T00:00:00Z",
          reason: "Review: Reviewed",
          transition: "Draft\u2192Review",
        },
      });

      await useSignatureStore
        .getState()
        .signDocument(
          "doc-456",
          3,
          "Draft\u2192Review",
          "Review: Reviewed",
          "pass"
        );

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/signatures/sign",
        {
          document_uuid: "doc-456",
          document_version_id: 3,
          transition: "Draft\u2192Review",
          reason: "Review: Reviewed",
          password: "pass",
        },
        { changeReason: "Electronic signature: Draft\u2192Review" }
      );
    });

    it("on failure (400): sets signError with extracted message, isSigning=false", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          400,
          JSON.stringify({ detail: "Document version not found" }),
          "/api/signatures/sign"
        )
      );

      await useSignatureStore
        .getState()
        .signDocument(
          "doc-123",
          99,
          "Review\u2192Approved",
          "Approval: test",
          "pass"
        );

      const state = useSignatureStore.getState();
      expect(state.signError).toBe("Document version not found");
      expect(state.isSigning).toBe(false);
      expect(state.lastSignResult).toBeNull();
    });

    it("on failure (401): sets signError, isSigning=false", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          401,
          JSON.stringify({
            detail: "Authentication expired. Please re-authenticate.",
          }),
          "/api/signatures/sign"
        )
      );

      await useSignatureStore
        .getState()
        .signDocument(
          "doc-123",
          5,
          "Review\u2192Approved",
          "Approval: test",
          "pass"
        );

      const state = useSignatureStore.getState();
      expect(state.signError).toBe(
        "Authentication expired. Please re-authenticate."
      );
      expect(state.isSigning).toBe(false);
    });

    it("while in progress: isSigning=true, signError=null", async () => {
      let resolvePromise: (value: unknown) => void;
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      mockedApiClient.post.mockReturnValue(pendingPromise);

      const promise = useSignatureStore
        .getState()
        .signDocument(
          "doc-123",
          5,
          "Review\u2192Approved",
          "Approval: test",
          "pass"
        );

      const state = useSignatureStore.getState();
      expect(state.isSigning).toBe(true);
      expect(state.signError).toBeNull();

      resolvePromise!({
        success: true,
        signature_hash: "hash",
        signature_record_id: 1,
        stamp: {
          signer_name: "User",
          signed_at: "2024-01-01T00:00:00Z",
          reason: "test",
          transition: "test",
        },
      });
      await promise;
    });

    it("on failure with non-JSON body: falls back to body string", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(500, "Server error", "/api/signatures/sign")
      );

      await useSignatureStore
        .getState()
        .signDocument(
          "doc-123",
          5,
          "Review\u2192Approved",
          "Approval: test",
          "pass"
        );

      const state = useSignatureStore.getState();
      expect(state.signError).toBe("Server error");
      expect(state.isSigning).toBe(false);
    });
  });

  // ---------------------------------------------------------------------------
  // 5. fetchSignatureRecords
  // ---------------------------------------------------------------------------
  describe("fetchSignatureRecords", () => {
    it("on success: stores records in map keyed by document_uuid, isLoadingRecords=false", async () => {
      const mockRecords = [
        {
          id: 1,
          document_uuid: "doc-abc",
          signer_user_id: 10,
          transition: "Draft\u2192Review",
          reason: "Author: Initial submission",
          signed_at: "2024-06-15T09:00:00Z",
          signature_hash: "hash1",
        },
        {
          id: 2,
          document_uuid: "doc-abc",
          signer_user_id: 20,
          transition: "Review\u2192Approved",
          reason: "Approval: Approved by QA",
          signed_at: "2024-06-15T10:00:00Z",
          signature_hash: "hash2",
        },
      ];
      mockedApiClient.get.mockResolvedValue(mockRecords);

      await useSignatureStore.getState().fetchSignatureRecords("doc-abc");

      const state = useSignatureStore.getState();
      expect(state.records["doc-abc"]).toEqual(mockRecords);
      expect(state.isLoadingRecords).toBe(false);
      expect(state.recordsError).toBeNull();
    });

    it("calls GET with the correct URL", async () => {
      mockedApiClient.get.mockResolvedValue([]);

      await useSignatureStore.getState().fetchSignatureRecords("my-doc-uuid");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/signatures/records/my-doc-uuid"
      );
    });

    it("preserves records for other documents when fetching new ones", async () => {
      // Pre-populate records for another document
      useSignatureStore.setState({
        records: {
          "doc-other": [
            {
              id: 99,
              document_uuid: "doc-other",
              signer_user_id: 5,
              transition: "Draft\u2192Review",
              reason: "Author: test",
              signed_at: "2024-01-01T00:00:00Z",
              signature_hash: "existing-hash",
            },
          ],
        },
      });

      mockedApiClient.get.mockResolvedValue([
        {
          id: 3,
          document_uuid: "doc-new",
          signer_user_id: 1,
          transition: "Review\u2192Approved",
          reason: "Approval: done",
          signed_at: "2024-06-15T12:00:00Z",
          signature_hash: "new-hash",
        },
      ]);

      await useSignatureStore.getState().fetchSignatureRecords("doc-new");

      const state = useSignatureStore.getState();
      expect(state.records["doc-other"]).toHaveLength(1);
      expect(state.records["doc-new"]).toHaveLength(1);
    });

    it("on failure: sets recordsError, isLoadingRecords=false", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(
          404,
          JSON.stringify({ detail: "Document not found" }),
          "/api/signatures/records/missing-doc"
        )
      );

      await useSignatureStore.getState().fetchSignatureRecords("missing-doc");

      const state = useSignatureStore.getState();
      expect(state.recordsError).toBe("Document not found");
      expect(state.isLoadingRecords).toBe(false);
    });

    it("while in progress: isLoadingRecords=true, recordsError=null", async () => {
      let resolvePromise: (value: unknown) => void;
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      mockedApiClient.get.mockReturnValue(pendingPromise);

      const promise = useSignatureStore
        .getState()
        .fetchSignatureRecords("doc-123");

      const state = useSignatureStore.getState();
      expect(state.isLoadingRecords).toBe(true);
      expect(state.recordsError).toBeNull();

      resolvePromise!([]);
      await promise;
    });
  });

  // ---------------------------------------------------------------------------
  // 6. verifySignatures
  // ---------------------------------------------------------------------------
  describe("verifySignatures", () => {
    it("on success: stores verifyResult, isVerifying=false", async () => {
      const mockVerifyResponse = {
        is_valid: true,
        signature_count: 2,
        signatures: [
          {
            signer_name: "John Doe",
            signed_at: "2024-06-15T10:30:00Z",
            reason: "Approval: Approved",
            is_valid: true,
          },
        ],
        tampered_from_index: -1,
      };
      mockedApiClient.get.mockResolvedValue(mockVerifyResponse);

      await useSignatureStore.getState().verifySignatures("doc-abc");

      const state = useSignatureStore.getState();
      expect(state.verifyResult).toEqual(mockVerifyResponse);
      expect(state.isVerifying).toBe(false);
      expect(state.verifyError).toBeNull();
    });

    it("calls GET with the correct URL", async () => {
      mockedApiClient.get.mockResolvedValue({
        is_valid: true,
        signature_count: 0,
        signatures: [],
        tampered_from_index: -1,
      });

      await useSignatureStore.getState().verifySignatures("doc-xyz");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/signatures/verify/doc-xyz"
      );
    });

    it("on failure: sets verifyError, isVerifying=false", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(
          500,
          JSON.stringify({ detail: "Verification service unavailable" }),
          "/api/signatures/verify/doc-abc"
        )
      );

      await useSignatureStore.getState().verifySignatures("doc-abc");

      const state = useSignatureStore.getState();
      expect(state.verifyError).toBe("Verification service unavailable");
      expect(state.isVerifying).toBe(false);
      expect(state.verifyResult).toBeNull();
    });

    it("while in progress: isVerifying=true, verifyError=null", async () => {
      let resolvePromise: (value: unknown) => void;
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      mockedApiClient.get.mockReturnValue(pendingPromise);

      const promise = useSignatureStore.getState().verifySignatures("doc-abc");

      const state = useSignatureStore.getState();
      expect(state.isVerifying).toBe(true);
      expect(state.verifyError).toBeNull();

      resolvePromise!({
        is_valid: true,
        signature_count: 0,
        signatures: [],
        tampered_from_index: -1,
      });
      await promise;
    });
  });

  // ---------------------------------------------------------------------------
  // 7. clearToken
  // ---------------------------------------------------------------------------
  describe("clearToken", () => {
    it("sets signatureToken=null, tokenExpiresAt=null, remainingSeconds=0", () => {
      useSignatureStore.setState({
        signatureToken: "some-token",
        tokenExpiresAt: Date.now() + 60000,
        remainingSeconds: 55,
      });

      useSignatureStore.getState().clearToken();

      const state = useSignatureStore.getState();
      expect(state.signatureToken).toBeNull();
      expect(state.tokenExpiresAt).toBeNull();
      expect(state.remainingSeconds).toBe(0);
    });
  });

  // ---------------------------------------------------------------------------
  // 8. reset
  // ---------------------------------------------------------------------------
  describe("reset", () => {
    it("clears all state to initial values", () => {
      // Put the store in a non-initial state
      useSignatureStore.setState({
        isReAuthenticating: true,
        reAuthError: "Some error",
        signatureToken: "token-123",
        tokenExpiresAt: Date.now() + 120000,
        isSigning: true,
        signError: "Sign error",
        lastSignResult: {
          success: true,
          signature_hash: "hash",
          signature_record_id: 1,
          stamp: {
            signer_name: "User",
            signed_at: "2024-01-01T00:00:00Z",
            reason: "test",
            transition: "test",
          },
        },
        records: {
          "doc-1": [
            {
              id: 1,
              document_uuid: "doc-1",
              signer_user_id: 1,
              transition: "Draft\u2192Review",
              reason: "Author: test",
              signed_at: "2024-01-01T00:00:00Z",
              signature_hash: "hash",
            },
          ],
        },
        isLoadingRecords: true,
        recordsError: "Records error",
        remainingSeconds: 45,
        isDialogOpen: true,
        dialogContext: mockDialogContext,
        _password: "secret",
        isVerifying: true,
        verifyError: "Verify error",
        verifyResult: {
          is_valid: true,
          signature_count: 1,
          signatures: [],
          tampered_from_index: -1,
        },
      });

      useSignatureStore.getState().reset();

      const state = useSignatureStore.getState();
      expect(state.isReAuthenticating).toBe(false);
      expect(state.reAuthError).toBeNull();
      expect(state.signatureToken).toBeNull();
      expect(state.tokenExpiresAt).toBeNull();
      expect(state.isSigning).toBe(false);
      expect(state.signError).toBeNull();
      expect(state.lastSignResult).toBeNull();
      expect(state.records).toEqual({});
      expect(state.isLoadingRecords).toBe(false);
      expect(state.recordsError).toBeNull();
      expect(state.remainingSeconds).toBe(0);
      expect(state.isDialogOpen).toBe(false);
      expect(state.dialogContext).toBeNull();
      expect(state._password).toBeNull();
      expect(state.isVerifying).toBe(false);
      expect(state.verifyError).toBeNull();
      expect(state.verifyResult).toBeNull();
    });
  });
});
