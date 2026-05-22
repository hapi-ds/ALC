import { describe, it, expect, beforeEach, vi } from "vitest";

/**
 * Unit tests for workflowExecutionStore signature integration
 *
 * Tests the signature interception logic added to `executeTransition`:
 * - Transition intercepted when signature required
 * - Transition proceeds when skipSignatureCheck=true
 * - Transition proceeds normally when no signature required
 * - Transition proceeds when signatureRequiredTransitions is empty
 *
 * Requirements: 10.1, 10.2, 10.3, 1.6
 */

// Mock apiClient — all API calls are mocked; no real backend calls are made.
// Verified endpoints from workflowExecutionStore.ts:
//   POST /api/workflows/transition
//   GET  /api/workflows/state/{document_uuid}
//   GET  /api/workflows/state/{document_uuid}/history
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

import { useWorkflowExecutionStore } from "../workflowExecutionStore";
import { useSignatureStore } from "../signatureStore";
import { apiClient } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe("workflowExecutionStore signature integration", () => {
  beforeEach(() => {
    useWorkflowExecutionStore.getState().reset();
    useSignatureStore.getState().reset();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Transition intercepted when signature required
  // -------------------------------------------------------------------------
  describe("transition intercepted when signature required", () => {
    it("returns false and opens signature dialog instead of calling API", async () => {
      // Set currentState to "Review" and signatureRequiredTransitions to ["Review→Approved"]
      useWorkflowExecutionStore.setState({
        currentState: "Review",
        signatureRequiredTransitions: ["Review→Approved"],
      });

      // Call executeTransition without skipSignatureCheck
      const result = await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-123", "Approved", "reason");

      // Assert: returns false (transition not executed directly)
      expect(result).toBe(false);

      // Assert: signatureStore.isDialogOpen is true
      const sigState = useSignatureStore.getState();
      expect(sigState.isDialogOpen).toBe(true);

      // Assert: dialogContext has the correct document_uuid and transition
      expect(sigState.dialogContext).not.toBeNull();
      expect(sigState.dialogContext!.document_uuid).toBe("doc-123");
      expect(sigState.dialogContext!.transition).toBe("Review→Approved");

      // Assert: the transition API was NOT called
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // 2. Transition proceeds when skipSignatureCheck=true
  // -------------------------------------------------------------------------
  describe("transition proceeds when skipSignatureCheck=true", () => {
    it("calls the transition API and does not open signature dialog", async () => {
      // Set currentState to "Review" and signatureRequiredTransitions to ["Review→Approved"]
      useWorkflowExecutionStore.setState({
        currentState: "Review",
        signatureRequiredTransitions: ["Review→Approved"],
      });

      // Mock the transition API to resolve successfully
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Review",
        new_state: "Approved",
        requires_signature: true,
        triggers_training: false,
      });
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-123",
        current_state: "Approved",
        workflow_name: "SOP Workflow",
        valid_transitions: [],
        updated_at: "2024-06-15T11:00:00Z",
      });

      // Call executeTransition with skipSignatureCheck=true
      const result = await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-123", "Approved", "reason", true);

      // Assert: the transition API WAS called
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/workflows/transition",
        { document_uuid: "doc-123", target_state: "Approved" },
        { changeReason: "reason" }
      );

      // Assert: signatureStore.isDialogOpen remains false
      const sigState = useSignatureStore.getState();
      expect(sigState.isDialogOpen).toBe(false);

      // Assert: transition succeeded
      expect(result).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // 3. Transition proceeds normally when no signature required
  // -------------------------------------------------------------------------
  describe("transition proceeds normally when no signature required", () => {
    it("calls the transition API when transition is not in signature-required list", async () => {
      // Set currentState to "Draft" and signatureRequiredTransitions to ["Review→Approved"]
      useWorkflowExecutionStore.setState({
        currentState: "Draft",
        signatureRequiredTransitions: ["Review→Approved"],
      });

      // Mock the transition API to resolve successfully
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Draft",
        new_state: "Review",
        requires_signature: false,
        triggers_training: false,
      });
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-123",
        current_state: "Review",
        workflow_name: "SOP Workflow",
        valid_transitions: ["Approved"],
        updated_at: "2024-06-15T11:00:00Z",
      });

      // Call executeTransition without skipSignatureCheck
      // The transition "Draft→Review" is NOT in the signature-required list
      const result = await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-123", "Review", "reason");

      // Assert: the transition API WAS called
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/workflows/transition",
        { document_uuid: "doc-123", target_state: "Review" },
        { changeReason: "reason" }
      );

      // Assert: signatureStore.isDialogOpen remains false
      const sigState = useSignatureStore.getState();
      expect(sigState.isDialogOpen).toBe(false);

      // Assert: transition succeeded
      expect(result).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // 4. Transition proceeds when signatureRequiredTransitions is empty
  // -------------------------------------------------------------------------
  describe("transition proceeds when signatureRequiredTransitions is empty", () => {
    it("calls the transition API when no transitions require signatures", async () => {
      // Set currentState to "Review" and signatureRequiredTransitions to []
      useWorkflowExecutionStore.setState({
        currentState: "Review",
        signatureRequiredTransitions: [],
      });

      // Mock the transition API to resolve successfully
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Review",
        new_state: "Approved",
        requires_signature: false,
        triggers_training: false,
      });
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-123",
        current_state: "Approved",
        workflow_name: "SOP Workflow",
        valid_transitions: [],
        updated_at: "2024-06-15T11:00:00Z",
      });

      // Call executeTransition without skipSignatureCheck
      const result = await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-123", "Approved", "reason");

      // Assert: the transition API WAS called
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/workflows/transition",
        { document_uuid: "doc-123", target_state: "Approved" },
        { changeReason: "reason" }
      );

      // Assert: signatureStore.isDialogOpen remains false
      const sigState = useSignatureStore.getState();
      expect(sigState.isDialogOpen).toBe(false);

      // Assert: transition succeeded
      expect(result).toBe(true);
    });
  });
});
