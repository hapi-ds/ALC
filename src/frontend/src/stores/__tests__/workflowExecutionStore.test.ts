import { describe, it, expect, beforeEach, vi } from "vitest";

/**
 * Unit tests for workflowExecutionStore
 *
 * These tests cover specific scenarios with known inputs, complementing
 * the property-based tests in workflowExecutionStore.property.test.ts.
 *
 * Requirements: 7.3, 7.4, 7.5, 7.6, 7.7
 */

// Mock apiClient — same pattern as the property test file.
// Verified endpoints from workflowExecutionStore.ts:
//   GET  /api/workflows/state/{document_uuid}
//   POST /api/workflows/transition
//   GET  /api/workflows/state/{document_uuid}/history
//   GET  /api/workflows
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
import { apiClient, ApiError } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe("workflowExecutionStore unit tests", () => {
  beforeEach(() => {
    useWorkflowExecutionStore.getState().reset();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. fetchDocumentState — success case
  // -------------------------------------------------------------------------
  describe("fetchDocumentState — success", () => {
    it("populates state correctly from API response", async () => {
      const mockResponse = {
        document_uuid: "abc-123",
        current_state: "Review",
        workflow_name: "SOP Workflow",
        valid_transitions: ["Approved", "Rejected"],
        updated_at: "2024-06-15T10:30:00Z",
      };

      mockedApiClient.get.mockResolvedValue(mockResponse);

      await useWorkflowExecutionStore.getState().fetchDocumentState("abc-123");

      const state = useWorkflowExecutionStore.getState();
      expect(state.documentUuid).toBe("abc-123");
      expect(state.currentState).toBe("Review");
      expect(state.workflowName).toBe("SOP Workflow");
      expect(state.validTransitions).toEqual(["Approved", "Rejected"]);
      expect(state.updatedAt).toBe("2024-06-15T10:30:00Z");
      expect(state.isLoadingState).toBe(false);
      expect(state.stateError).toBeNull();
    });

    it("calls GET with the correct URL", async () => {
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-456",
        current_state: "Draft",
        workflow_name: "Test",
        valid_transitions: [],
        updated_at: null,
      });

      await useWorkflowExecutionStore.getState().fetchDocumentState("doc-456");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/workflows/state/doc-456"
      );
    });

    it("handles null updated_at", async () => {
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-789",
        current_state: "Draft",
        workflow_name: "Protocol Workflow",
        valid_transitions: ["Review"],
        updated_at: null,
      });

      await useWorkflowExecutionStore.getState().fetchDocumentState("doc-789");

      const state = useWorkflowExecutionStore.getState();
      expect(state.updatedAt).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 2. fetchDocumentState — error case
  // -------------------------------------------------------------------------
  describe("fetchDocumentState — error", () => {
    it("sets stateError on API failure", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(500, "Internal Server Error", "/api/workflows/state/abc-123")
      );

      await useWorkflowExecutionStore.getState().fetchDocumentState("abc-123");

      const state = useWorkflowExecutionStore.getState();
      expect(state.stateError).not.toBeNull();
      expect(state.stateError!.length).toBeGreaterThan(0);
      expect(state.isLoadingState).toBe(false);
    });

    it("sets stateError with parsed detail from JSON body", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(
          404,
          JSON.stringify({ detail: "No workflow state found for document: xyz" }),
          "/api/workflows/state/xyz"
        )
      );

      await useWorkflowExecutionStore.getState().fetchDocumentState("xyz");

      const state = useWorkflowExecutionStore.getState();
      expect(state.stateError).toBe(
        "No workflow state found for document: xyz"
      );
    });

    it("handles non-ApiError exceptions", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network failure"));

      await useWorkflowExecutionStore.getState().fetchDocumentState("abc-123");

      const state = useWorkflowExecutionStore.getState();
      expect(state.stateError).toBe("Network failure");
      expect(state.isLoadingState).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // 3. executeTransition — success case
  // -------------------------------------------------------------------------
  describe("executeTransition — success", () => {
    it("returns true on successful transition", async () => {
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Draft",
        new_state: "Review",
        requires_signature: false,
        triggers_training: false,
      });
      mockedApiClient.get.mockImplementation(async (url: string) => {
        if (url.includes("/history")) {
          return [];
        }
        return {
          document_uuid: "doc-1",
          current_state: "Review",
          workflow_name: "SOP Workflow",
          valid_transitions: ["Approved"],
          updated_at: "2024-06-15T11:00:00Z",
        };
      });

      const result = await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Review", "Moving to review phase");

      expect(result).toBe(true);
    });

    it("calls POST with correct URL, body, and changeReason option", async () => {
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Draft",
        new_state: "Review",
        requires_signature: false,
        triggers_training: false,
      });
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-1",
        current_state: "Review",
        workflow_name: "SOP Workflow",
        valid_transitions: [],
        updated_at: null,
      });

      await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Review", "Submitting for review");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/workflows/transition",
        { document_uuid: "doc-1", target_state: "Review" },
        { changeReason: "Submitting for review" }
      );
    });

    it("refreshes state and history after success", async () => {
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Draft",
        new_state: "Review",
        requires_signature: false,
        triggers_training: false,
      });
      mockedApiClient.get.mockImplementation(async (url: string) => {
        if (url.includes("/history")) {
          return [
            {
              id: 1,
              document_id: 10,
              user_id: 1,
              previous_state: "Draft",
              new_state: "Review",
              timestamp: "2024-06-15T11:00:00Z",
              change_reason: "Submitting for review",
            },
          ];
        }
        return {
          document_uuid: "doc-1",
          current_state: "Review",
          workflow_name: "SOP Workflow",
          valid_transitions: ["Approved", "Rejected"],
          updated_at: "2024-06-15T11:00:00Z",
        };
      });

      await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Review", "Submitting for review");

      // Verify GET was called for both state and history
      const getCalls = mockedApiClient.get.mock.calls.map(
        (call: unknown[]) => call[0]
      );
      expect(getCalls).toContain("/api/workflows/state/doc-1");
      expect(getCalls).toContain("/api/workflows/state/doc-1/history");

      // Verify store was updated with refreshed data
      const state = useWorkflowExecutionStore.getState();
      expect(state.currentState).toBe("Review");
      expect(state.history).toHaveLength(1);
      expect(state.history[0].new_state).toBe("Review");
    });

    it("stores lastTransitionResult correctly", async () => {
      mockedApiClient.post.mockResolvedValue({
        success: true,
        previous_state: "Review",
        new_state: "Approved",
        requires_signature: true,
        triggers_training: true,
      });
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-1",
        current_state: "Approved",
        workflow_name: "SOP Workflow",
        valid_transitions: [],
        updated_at: null,
      });

      await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Approved", "Final approval");

      const state = useWorkflowExecutionStore.getState();
      expect(state.lastTransitionResult).toEqual({
        success: true,
        previous_state: "Review",
        new_state: "Approved",
        requires_signature: true,
        triggers_training: true,
      });
    });
  });

  // -------------------------------------------------------------------------
  // 4. executeTransition — error case
  // -------------------------------------------------------------------------
  describe("executeTransition — error", () => {
    it("returns false on failure", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          400,
          JSON.stringify({ detail: "Invalid transition" }),
          "/api/workflows/transition"
        )
      );

      const result = await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Approved", "Trying to approve");

      expect(result).toBe(false);
    });

    it("sets transitionError on failure", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(
          400,
          JSON.stringify({
            detail:
              "Invalid transition: 'Draft' \u2192 'Approved' is not allowed by the workflow definition",
          }),
          "/api/workflows/transition"
        )
      );

      await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Approved", "Trying to approve");

      const state = useWorkflowExecutionStore.getState();
      expect(state.transitionError).toBe(
        "Invalid transition: 'Draft' \u2192 'Approved' is not allowed by the workflow definition"
      );
      expect(state.isTransitioning).toBe(false);
    });

    it("does not call GET (no refresh) on failure", async () => {
      mockedApiClient.post.mockRejectedValue(
        new ApiError(500, "Server error", "/api/workflows/transition")
      );

      await useWorkflowExecutionStore
        .getState()
        .executeTransition("doc-1", "Review", "Reason");

      expect(mockedApiClient.get).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // 5. fetchTransitionHistory — success case
  // -------------------------------------------------------------------------
  describe("fetchTransitionHistory — success", () => {
    it("populates history array correctly", async () => {
      const mockHistory = [
        {
          id: 3,
          document_id: 10,
          user_id: 2,
          previous_state: "Review",
          new_state: "Approved",
          timestamp: "2024-06-15T14:00:00Z",
          change_reason: "Approved after review",
        },
        {
          id: 2,
          document_id: 10,
          user_id: 1,
          previous_state: "Draft",
          new_state: "Review",
          timestamp: "2024-06-15T10:00:00Z",
          change_reason: "Submitting for review",
        },
      ];

      mockedApiClient.get.mockResolvedValue(mockHistory);

      await useWorkflowExecutionStore
        .getState()
        .fetchTransitionHistory("doc-10");

      const state = useWorkflowExecutionStore.getState();
      expect(state.history).toHaveLength(2);
      expect(state.history[0].id).toBe(3);
      expect(state.history[0].new_state).toBe("Approved");
      expect(state.history[1].id).toBe(2);
      expect(state.history[1].new_state).toBe("Review");
      expect(state.isLoadingHistory).toBe(false);
      expect(state.historyError).toBeNull();
    });

    it("calls GET with the correct history URL", async () => {
      mockedApiClient.get.mockResolvedValue([]);

      await useWorkflowExecutionStore
        .getState()
        .fetchTransitionHistory("my-doc-uuid");

      expect(mockedApiClient.get).toHaveBeenCalledWith(
        "/api/workflows/state/my-doc-uuid/history"
      );
    });

    it("handles empty history array", async () => {
      mockedApiClient.get.mockResolvedValue([]);

      await useWorkflowExecutionStore
        .getState()
        .fetchTransitionHistory("doc-new");

      const state = useWorkflowExecutionStore.getState();
      expect(state.history).toEqual([]);
      expect(state.isLoadingHistory).toBe(false);
      expect(state.historyError).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 6. fetchTransitionHistory — error case
  // -------------------------------------------------------------------------
  describe("fetchTransitionHistory — error", () => {
    it("sets historyError on failure", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(
          404,
          JSON.stringify({
            detail: "No workflow state found for document: missing-doc",
          }),
          "/api/workflows/state/missing-doc/history"
        )
      );

      await useWorkflowExecutionStore
        .getState()
        .fetchTransitionHistory("missing-doc");

      const state = useWorkflowExecutionStore.getState();
      expect(state.historyError).toBe(
        "No workflow state found for document: missing-doc"
      );
      expect(state.isLoadingHistory).toBe(false);
      expect(state.history).toEqual([]);
    });

    it("handles network errors", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Connection refused"));

      await useWorkflowExecutionStore
        .getState()
        .fetchTransitionHistory("doc-1");

      const state = useWorkflowExecutionStore.getState();
      expect(state.historyError).toBe("Connection refused");
      expect(state.isLoadingHistory).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // 7. reset() — verify all state returns to initial values
  // -------------------------------------------------------------------------
  describe("reset()", () => {
    it("returns all state to initial values", async () => {
      // First, put the store in a non-initial state
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-1",
        current_state: "Approved",
        workflow_name: "SOP Workflow",
        valid_transitions: [],
        updated_at: "2024-06-15T10:00:00Z",
      });
      await useWorkflowExecutionStore.getState().fetchDocumentState("doc-1");

      // Manually set additional state
      useWorkflowExecutionStore.setState({
        isTransitioning: true,
        transitionError: "Some error",
        lastTransitionResult: {
          success: true,
          previous_state: "Draft",
          new_state: "Approved",
          requires_signature: true,
          triggers_training: true,
        },
        history: [
          {
            id: 1,
            document_id: 1,
            user_id: 1,
            previous_state: "Draft",
            new_state: "Review",
            timestamp: "2024-01-01T00:00:00Z",
            change_reason: "test",
          },
        ],
        isLoadingHistory: true,
        historyError: "History error",
        signatureRequiredTransitions: ["Draft\u2192Review"],
        trainingTriggerTransitions: ["Review\u2192Approved"],
        riskLevel: "critical",
        isLoadingGateInfo: true,
      });

      // Act
      useWorkflowExecutionStore.getState().reset();

      // Assert all fields are initial
      const state = useWorkflowExecutionStore.getState();
      expect(state.documentUuid).toBeNull();
      expect(state.currentState).toBeNull();
      expect(state.workflowName).toBeNull();
      expect(state.validTransitions).toEqual([]);
      expect(state.updatedAt).toBeNull();
      expect(state.isLoadingState).toBe(false);
      expect(state.stateError).toBeNull();
      expect(state.isTransitioning).toBe(false);
      expect(state.transitionError).toBeNull();
      expect(state.lastTransitionResult).toBeNull();
      expect(state.history).toEqual([]);
      expect(state.isLoadingHistory).toBe(false);
      expect(state.historyError).toBeNull();
      expect(state.signatureRequiredTransitions).toEqual([]);
      expect(state.trainingTriggerTransitions).toEqual([]);
      expect(state.riskLevel).toBe("low");
      expect(state.isLoadingGateInfo).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // 8. clearTransitionState() — verify only transition-related state is cleared
  // -------------------------------------------------------------------------
  describe("clearTransitionState()", () => {
    it("clears only transition-related state", async () => {
      // Set up some document state
      mockedApiClient.get.mockResolvedValue({
        document_uuid: "doc-1",
        current_state: "Review",
        workflow_name: "SOP Workflow",
        valid_transitions: ["Approved", "Rejected"],
        updated_at: "2024-06-15T10:00:00Z",
      });
      await useWorkflowExecutionStore.getState().fetchDocumentState("doc-1");

      // Set transition-related state
      useWorkflowExecutionStore.setState({
        transitionError: "Transition failed",
        lastTransitionResult: {
          success: false,
          previous_state: "Review",
          new_state: "Approved",
          requires_signature: false,
          triggers_training: false,
        },
      });

      // Act
      useWorkflowExecutionStore.getState().clearTransitionState();

      // Assert: transition state is cleared
      const state = useWorkflowExecutionStore.getState();
      expect(state.transitionError).toBeNull();
      expect(state.lastTransitionResult).toBeNull();

      // Assert: document state is preserved
      expect(state.documentUuid).toBe("doc-1");
      expect(state.currentState).toBe("Review");
      expect(state.workflowName).toBe("SOP Workflow");
      expect(state.validTransitions).toEqual(["Approved", "Rejected"]);
      expect(state.updatedAt).toBe("2024-06-15T10:00:00Z");
      expect(state.isLoadingState).toBe(false);
      expect(state.stateError).toBeNull();
    });

    it("does not affect history state", () => {
      // Set history state
      useWorkflowExecutionStore.setState({
        history: [
          {
            id: 1,
            document_id: 1,
            user_id: 1,
            previous_state: "Draft",
            new_state: "Review",
            timestamp: "2024-01-01T00:00:00Z",
            change_reason: "test",
          },
        ],
        historyError: "Some history error",
        transitionError: "Transition error to clear",
        lastTransitionResult: {
          success: true,
          previous_state: "Draft",
          new_state: "Review",
          requires_signature: false,
          triggers_training: false,
        },
      });

      // Act
      useWorkflowExecutionStore.getState().clearTransitionState();

      // Assert: history is preserved
      const state = useWorkflowExecutionStore.getState();
      expect(state.history).toHaveLength(1);
      expect(state.historyError).toBe("Some history error");

      // Assert: transition state is cleared
      expect(state.transitionError).toBeNull();
      expect(state.lastTransitionResult).toBeNull();
    });

    it("does not affect gate info state", () => {
      useWorkflowExecutionStore.setState({
        signatureRequiredTransitions: ["Draft\u2192Review"],
        trainingTriggerTransitions: ["Review\u2192Approved"],
        riskLevel: "high",
        transitionError: "Error to clear",
        lastTransitionResult: {
          success: true,
          previous_state: "Draft",
          new_state: "Review",
          requires_signature: true,
          triggers_training: false,
        },
      });

      // Act
      useWorkflowExecutionStore.getState().clearTransitionState();

      // Assert: gate info is preserved
      const state = useWorkflowExecutionStore.getState();
      expect(state.signatureRequiredTransitions).toEqual(["Draft\u2192Review"]);
      expect(state.trainingTriggerTransitions).toEqual(["Review\u2192Approved"]);
      expect(state.riskLevel).toBe("high");

      // Assert: transition state is cleared
      expect(state.transitionError).toBeNull();
      expect(state.lastTransitionResult).toBeNull();
    });
  });
});
