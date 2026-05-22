import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: Step_3-2_workflow-execution-state-transitions
 *
 * Property 8: Store loading state machine (fetchDocumentState)
 *
 * For any call to fetchDocumentState(documentUuid), the store SHALL transition through states:
 * (1) set isLoadingState=true and stateError=null,
 * (2) make the GET request,
 * (3) on success: store the response fields and set isLoadingState=false,
 *     OR on failure: set stateError to the error message and set isLoadingState=false.
 * At no point SHALL isLoadingState remain true after the request completes or fails.
 *
 * Validates: Requirements 7.3, 7.7
 */

// Mock apiClient — all API calls are mocked, no real network requests are made.
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

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Arbitrary non-empty document UUID string */
const documentUuidArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 100 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary state name */
const stateNameArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter((s) => s.trim().length > 0);

/** Arbitrary valid transitions array */
const validTransitionsArb: fc.Arbitrary<string[]> = fc.array(stateNameArb, {
  minLength: 0,
  maxLength: 5,
});

/** Arbitrary ISO timestamp string (avoids invalid date issues with fc.date) */
const isoTimestampArb: fc.Arbitrary<string> = fc
  .integer({ min: 1577836800000, max: 1893456000000 }) // 2020-01-01 to 2030-01-01 in ms
  .map((ms) => new Date(ms).toISOString());

/** Arbitrary successful DocumentStateResponse */
const documentStateResponseArb = fc.record({
  document_uuid: documentUuidArb,
  current_state: stateNameArb,
  workflow_name: stateNameArb,
  valid_transitions: validTransitionsArb,
  updated_at: fc.option(isoTimestampArb, { nil: null }),
});

/** Arbitrary error message */
const errorMessageArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 200 })
  .filter((s) => s.trim().length > 0);

// ---------------------------------------------------------------------------
// Property 8: Store loading state machine (fetchDocumentState)
// ---------------------------------------------------------------------------

describe("Feature: Step_3-2_workflow-execution-state-transitions, Property 8: Store loading state machine", () => {
  beforeEach(() => {
    useWorkflowExecutionStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useWorkflowExecutionStore.getState().reset();
  });

  it("reset() always returns the store to its initial state regardless of current state", () => {
    fc.assert(
      fc.property(
        documentUuidArb,
        stateNameArb,
        stateNameArb,
        validTransitionsArb,
        errorMessageArb,
        (docUuid, currentState, workflowName, transitions, errorMsg) => {
          // Arrange: put the store in an arbitrary non-initial state
          useWorkflowExecutionStore.setState({
            documentUuid: docUuid,
            currentState: currentState,
            workflowName: workflowName,
            validTransitions: transitions,
            isLoadingState: true,
            stateError: errorMsg,
            isTransitioning: true,
            transitionError: errorMsg,
            isLoadingHistory: true,
            historyError: errorMsg,
          });

          // Act
          useWorkflowExecutionStore.getState().reset();

          // Assert: all fields are back to initial values
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
        }
      ),
      { numRuns: 100 }
    );
  });

  it("after fetchDocumentState succeeds, currentState and validTransitions are populated and isLoadingState is false", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        documentStateResponseArb,
        async (docUuid, response) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange: mock successful API response
          mockedApiClient.get.mockResolvedValue(response);

          // Act
          await useWorkflowExecutionStore.getState().fetchDocumentState(docUuid);

          // Assert
          const state = useWorkflowExecutionStore.getState();
          expect(state.isLoadingState).toBe(false);
          expect(state.stateError).toBeNull();
          expect(state.currentState).toBe(response.current_state);
          expect(state.validTransitions).toEqual(response.valid_transitions);
          expect(state.workflowName).toBe(response.workflow_name);
          expect(state.updatedAt).toBe(response.updated_at);
          expect(state.documentUuid).toBe(docUuid);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("after fetchDocumentState fails, stateError is set and isLoadingState is false", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        errorMessageArb,
        async (docUuid, errorMsg) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange: mock API failure
          mockedApiClient.get.mockRejectedValue(
            new ApiError(500, errorMsg, `/api/workflows/state/${docUuid}`)
          );

          // Act
          await useWorkflowExecutionStore.getState().fetchDocumentState(docUuid);

          // Assert
          const state = useWorkflowExecutionStore.getState();
          expect(state.isLoadingState).toBe(false);
          expect(state.stateError).not.toBeNull();
          expect(state.stateError!.length).toBeGreaterThan(0);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("isLoadingState is true during fetch and false after completion (success or failure)", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        fc.boolean(),
        documentStateResponseArb,
        errorMessageArb,
        async (docUuid, shouldSucceed, successResponse, errorMsg) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Track isLoadingState during the fetch
          let loadingDuringFetch = false;

          if (shouldSucceed) {
            mockedApiClient.get.mockImplementation(async () => {
              // Capture loading state during the API call
              loadingDuringFetch =
                useWorkflowExecutionStore.getState().isLoadingState;
              return successResponse;
            });
          } else {
            mockedApiClient.get.mockImplementation(async () => {
              // Capture loading state during the API call
              loadingDuringFetch =
                useWorkflowExecutionStore.getState().isLoadingState;
              throw new ApiError(
                500,
                errorMsg,
                `/api/workflows/state/${docUuid}`
              );
            });
          }

          // Act
          await useWorkflowExecutionStore.getState().fetchDocumentState(docUuid);

          // Assert: loading was true during the fetch
          expect(loadingDuringFetch).toBe(true);

          // Assert: loading is false after completion
          const state = useWorkflowExecutionStore.getState();
          expect(state.isLoadingState).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 9: executeTransition API call construction
// ---------------------------------------------------------------------------

/**
 * Feature: Step_3-2_workflow-execution-state-transitions
 *
 * Property 9: executeTransition API call construction
 *
 * For any valid documentUuid, targetState, and changeReason strings, calling
 * executeTransition(documentUuid, targetState, changeReason) SHALL result in a
 * POST request to `/api/workflows/transition` with body
 * { document_uuid: documentUuid, target_state: targetState } and the changeReason
 * passed via the apiClient's changeReason option (which sets the X-Change-Reason header).
 *
 * Validates: Requirements 2.3, 7.4
 */

/** Arbitrary change reason string (3-500 chars trimmed, matching valid input) */
const changeReasonArb: fc.Arbitrary<string> = fc
  .string({ minLength: 3, maxLength: 500 })
  .filter((s) => s.trim().length >= 3);

describe("Feature: Step_3-2_workflow-execution-state-transitions, Property 9: executeTransition API call construction", () => {
  beforeEach(() => {
    useWorkflowExecutionStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useWorkflowExecutionStore.getState().reset();
  });

  it("calls apiClient.post with the correct URL `/api/workflows/transition`", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        async (docUuid, targetState, changeReason) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange: mock successful transition response
          mockedApiClient.post.mockResolvedValue({
            success: true,
            previous_state: "Draft",
            new_state: targetState,
            requires_signature: false,
            triggers_training: false,
          });
          // Mock the subsequent re-fetch calls
          mockedApiClient.get.mockResolvedValue({
            document_uuid: docUuid,
            current_state: targetState,
            workflow_name: "TestWorkflow",
            valid_transitions: [],
            updated_at: null,
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: POST was called with the correct URL
          expect(mockedApiClient.post).toHaveBeenCalledWith(
            "/api/workflows/transition",
            expect.anything(),
            expect.anything()
          );
        }
      ),
      { numRuns: 100 }
    );
  });

  it("sends request body containing document_uuid and target_state matching inputs", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        async (docUuid, targetState, changeReason) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange
          mockedApiClient.post.mockResolvedValue({
            success: true,
            previous_state: "Draft",
            new_state: targetState,
            requires_signature: false,
            triggers_training: false,
          });
          mockedApiClient.get.mockResolvedValue({
            document_uuid: docUuid,
            current_state: targetState,
            workflow_name: "TestWorkflow",
            valid_transitions: [],
            updated_at: null,
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: body contains document_uuid and target_state
          const callArgs = mockedApiClient.post.mock.calls[0];
          const body = callArgs[1];
          expect(body).toEqual({
            document_uuid: docUuid,
            target_state: targetState,
          });
        }
      ),
      { numRuns: 100 }
    );
  });

  it("passes changeReason as the third argument (options object with { changeReason })", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        async (docUuid, targetState, changeReason) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange
          mockedApiClient.post.mockResolvedValue({
            success: true,
            previous_state: "Draft",
            new_state: targetState,
            requires_signature: false,
            triggers_training: false,
          });
          mockedApiClient.get.mockResolvedValue({
            document_uuid: docUuid,
            current_state: targetState,
            workflow_name: "TestWorkflow",
            valid_transitions: [],
            updated_at: null,
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: third argument is the options object with changeReason
          const callArgs = mockedApiClient.post.mock.calls[0];
          const options = callArgs[2];
          expect(options).toEqual({ changeReason });
        }
      ),
      { numRuns: 100 }
    );
  });

  it("isTransitioning is true during the API call and false after (success or failure)", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        fc.boolean(),
        errorMessageArb,
        async (docUuid, targetState, changeReason, shouldSucceed, errorMsg) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Track isTransitioning during the API call
          let transitioningDuringCall = false;

          if (shouldSucceed) {
            mockedApiClient.post.mockImplementation(async () => {
              transitioningDuringCall =
                useWorkflowExecutionStore.getState().isTransitioning;
              return {
                success: true,
                previous_state: "Draft",
                new_state: targetState,
                requires_signature: false,
                triggers_training: false,
              };
            });
            mockedApiClient.get.mockResolvedValue({
              document_uuid: docUuid,
              current_state: targetState,
              workflow_name: "TestWorkflow",
              valid_transitions: [],
              updated_at: null,
            });
          } else {
            mockedApiClient.post.mockImplementation(async () => {
              transitioningDuringCall =
                useWorkflowExecutionStore.getState().isTransitioning;
              throw new ApiError(
                400,
                errorMsg,
                "/api/workflows/transition"
              );
            });
          }

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: isTransitioning was true during the call
          expect(transitioningDuringCall).toBe(true);

          // Assert: isTransitioning is false after completion
          const state = useWorkflowExecutionStore.getState();
          expect(state.isTransitioning).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("returns true on success and false on failure", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        fc.boolean(),
        errorMessageArb,
        async (docUuid, targetState, changeReason, shouldSucceed, errorMsg) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          if (shouldSucceed) {
            mockedApiClient.post.mockResolvedValue({
              success: true,
              previous_state: "Draft",
              new_state: targetState,
              requires_signature: false,
              triggers_training: false,
            });
            mockedApiClient.get.mockResolvedValue({
              document_uuid: docUuid,
              current_state: targetState,
              workflow_name: "TestWorkflow",
              valid_transitions: [],
              updated_at: null,
            });
          } else {
            mockedApiClient.post.mockRejectedValue(
              new ApiError(400, errorMsg, "/api/workflows/transition")
            );
          }

          // Act
          const result = await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert
          if (shouldSucceed) {
            expect(result).toBe(true);
          } else {
            expect(result).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 10: Successful transition triggers state and history refresh
// ---------------------------------------------------------------------------

/**
 * Feature: Step_3-2_workflow-execution-state-transitions
 *
 * Property 10: Successful transition triggers state and history refresh
 *
 * For any successful transition (backend returns success: true), the store SHALL
 * automatically invoke fetchDocumentState and fetchTransitionHistory for the same
 * documentUuid, ensuring the UI reflects the new state and updated history without
 * manual refresh. On failure (POST throws), the re-fetch calls should NOT be made.
 *
 * Validates: Requirements 2.5, 7.5
 */

/** Arbitrary transition history entry */
const historyEntryArb = fc.record({
  id: fc.integer({ min: 1, max: 100000 }),
  document_id: fc.integer({ min: 1, max: 100000 }),
  user_id: fc.integer({ min: 1, max: 100000 }),
  previous_state: stateNameArb,
  new_state: stateNameArb,
  timestamp: isoTimestampArb,
  change_reason: fc.option(
    fc.string({ minLength: 3, maxLength: 200 }).filter((s) => s.trim().length >= 3),
    { nil: null }
  ),
});

describe("Feature: Step_3-2_workflow-execution-state-transitions, Property 10: Successful transition triggers state and history refresh", () => {
  beforeEach(() => {
    useWorkflowExecutionStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useWorkflowExecutionStore.getState().reset();
  });

  it("after a successful transition, both fetchDocumentState and fetchTransitionHistory GET calls are made for the same documentUuid", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        stateNameArb,
        fc.array(historyEntryArb, { minLength: 0, maxLength: 5 }),
        async (docUuid, targetState, changeReason, newState, historyEntries) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange: mock successful POST transition
          mockedApiClient.post.mockResolvedValue({
            success: true,
            previous_state: "Draft",
            new_state: newState,
            requires_signature: false,
            triggers_training: false,
          });

          // Mock GET calls for state and history refresh
          mockedApiClient.get.mockImplementation(async (url: string) => {
            if (url === `/api/workflows/state/${docUuid}`) {
              return {
                document_uuid: docUuid,
                current_state: newState,
                workflow_name: "TestWorkflow",
                valid_transitions: [],
                updated_at: new Date().toISOString(),
              };
            }
            if (url === `/api/workflows/state/${docUuid}/history`) {
              return historyEntries;
            }
            return {};
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: GET was called with the state URL for this documentUuid
          const getCalls = mockedApiClient.get.mock.calls.map(
            (call: unknown[]) => call[0]
          );
          expect(getCalls).toContain(`/api/workflows/state/${docUuid}`);
          expect(getCalls).toContain(
            `/api/workflows/state/${docUuid}/history`
          );
        }
      ),
      { numRuns: 100 }
    );
  });

  it("on failed transition (POST throws), no GET re-fetch calls are made", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        errorMessageArb,
        async (docUuid, targetState, changeReason, errorMsg) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Arrange: mock failed POST transition
          mockedApiClient.post.mockRejectedValue(
            new ApiError(400, errorMsg, "/api/workflows/transition")
          );

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: no GET calls were made (no re-fetch on failure)
          expect(mockedApiClient.get).not.toHaveBeenCalled();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("the GET calls for state and history are made AFTER the POST succeeds (not before)", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        async (docUuid, targetState, changeReason) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          // Track call order
          const callOrder: string[] = [];

          mockedApiClient.post.mockImplementation(async () => {
            callOrder.push("POST");
            return {
              success: true,
              previous_state: "Draft",
              new_state: targetState,
              requires_signature: false,
              triggers_training: false,
            };
          });

          mockedApiClient.get.mockImplementation(async (url: string) => {
            callOrder.push(`GET:${url}`);
            if (url === `/api/workflows/state/${docUuid}`) {
              return {
                document_uuid: docUuid,
                current_state: targetState,
                workflow_name: "TestWorkflow",
                valid_transitions: [],
                updated_at: null,
              };
            }
            if (url === `/api/workflows/state/${docUuid}/history`) {
              return [];
            }
            return {};
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: POST comes before any GET calls
          const postIndex = callOrder.indexOf("POST");
          const getStateIndex = callOrder.findIndex((c) =>
            c.startsWith(`GET:/api/workflows/state/${docUuid}`)
          );
          const getHistoryIndex = callOrder.findIndex(
            (c) => c === `GET:/api/workflows/state/${docUuid}/history`
          );

          expect(postIndex).toBeGreaterThanOrEqual(0);
          expect(getStateIndex).toBeGreaterThan(postIndex);
          expect(getHistoryIndex).toBeGreaterThan(postIndex);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("after a successful executeTransition, apiClient.get is called exactly twice (state + history)", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        async (docUuid, targetState, changeReason) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          mockedApiClient.post.mockResolvedValue({
            success: true,
            previous_state: "Draft",
            new_state: targetState,
            requires_signature: false,
            triggers_training: false,
          });
          mockedApiClient.get.mockImplementation(async (url: string) => {
            if (url.includes("/history")) {
              return [];
            }
            return {
              document_uuid: docUuid,
              current_state: targetState,
              workflow_name: "TestWorkflow",
              valid_transitions: [],
              updated_at: null,
            };
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: apiClient.get was called exactly twice after the POST
          expect(mockedApiClient.get).toHaveBeenCalledTimes(2);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("after a successful executeTransition, lastTransitionResult contains the transition response fields", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        stateNameArb,
        fc.boolean(),
        fc.boolean(),
        async (docUuid, targetState, changeReason, previousState, reqSig, trigTraining) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          const transitionResp = {
            success: true,
            previous_state: previousState,
            new_state: targetState,
            requires_signature: reqSig,
            triggers_training: trigTraining,
          };

          mockedApiClient.post.mockResolvedValue(transitionResp);
          mockedApiClient.get.mockImplementation(async (url: string) => {
            if (url.includes("/history")) {
              return [];
            }
            return {
              document_uuid: docUuid,
              current_state: targetState,
              workflow_name: "TestWorkflow",
              valid_transitions: [],
              updated_at: null,
            };
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: lastTransitionResult matches the response
          const state = useWorkflowExecutionStore.getState();
          expect(state.lastTransitionResult).not.toBeNull();
          expect(state.lastTransitionResult!.success).toBe(true);
          expect(state.lastTransitionResult!.previous_state).toBe(previousState);
          expect(state.lastTransitionResult!.new_state).toBe(targetState);
          expect(state.lastTransitionResult!.requires_signature).toBe(reqSig);
          expect(state.lastTransitionResult!.triggers_training).toBe(trigTraining);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("after a successful executeTransition, the store's currentState is updated from the state refresh response", async () => {
    await fc.assert(
      fc.asyncProperty(
        documentUuidArb,
        stateNameArb,
        changeReasonArb,
        documentStateResponseArb,
        fc.array(historyEntryArb, { minLength: 0, maxLength: 3 }),
        async (docUuid, targetState, changeReason, stateResp, historyResp) => {
          useWorkflowExecutionStore.getState().reset();
          vi.clearAllMocks();

          mockedApiClient.post.mockResolvedValue({
            success: true,
            previous_state: "Draft",
            new_state: targetState,
            requires_signature: false,
            triggers_training: false,
          });
          mockedApiClient.get.mockImplementation(async (url: string) => {
            if (url.includes("/history")) {
              return historyResp;
            }
            return stateResp;
          });

          // Act
          await useWorkflowExecutionStore
            .getState()
            .executeTransition(docUuid, targetState, changeReason);

          // Assert: currentState reflects the refreshed state from the GET response
          const state = useWorkflowExecutionStore.getState();
          expect(state.currentState).toBe(stateResp.current_state);
          expect(state.workflowName).toBe(stateResp.workflow_name);
          expect(state.validTransitions).toEqual(stateResp.valid_transitions);
        }
      ),
      { numRuns: 100 }
    );
  });
});


