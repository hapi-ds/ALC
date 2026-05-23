// Feature: Step_3-5_training-gated-access-control, Property 13: Quiz pass cache consistency
// Feature: Step_3-5_training-gated-access-control, Property 14: Gate cache invalidation on state change

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import * as fc from "fast-check";
import { useTrainingStore } from "@/stores/trainingStore";
import type { QuizPassStatus } from "@/components/training/types";

// Mock apiClient module
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
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
}));

import { apiClient } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Reset the store to a clean initial state for quiz-related tests */
function resetStore() {
  useTrainingStore.setState({
    quizPassCache: {},
    isCheckingQuizPass: false,
    quizPassError: null,
    gateCache: {},
    isCheckingGate: false,
    currentQuizAttempt: null,
    isSubmittingQuiz: false,
    quizSubmitError: null,
    quizResults: {},
    isLoadingQuizResults: false,
    quizResultsError: null,
    tasks: [],
    isLoadingTasks: false,
    tasksError: null,
    filter: "all",
    hasFetchedTasks: false,
    statistics: { pending: 0, completed: 0, total: 0, completionPercentage: null },
    isCompleting: false,
    completionError: null,
    currentContent: null,
    isLoadingContent: false,
    contentError: null,
    sopStatus: null,
    isLoadingStatus: false,
    statusError: null,
    pendingReviewItems: [],
    isReviewing: false,
    reviewError: null,
  });
}

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generator for a valid content_id in the format {uuid}_v{version} */
const arbContentId: fc.Arbitrary<string> = fc
  .tuple(
    fc.uuid(),
    fc
      .array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), {
        minLength: 1,
        maxLength: 5,
      })
      .map((chars) => chars.join(""))
  )
  .map(([uuid, version]) => `${uuid}_v${version}`);

/** Generator for a positive user ID */
const arbUserId: fc.Arbitrary<number> = fc.integer({ min: 1, max: 100000 });

/** Generator for a boolean quiz pass status */
const arbHasPassed: fc.Arbitrary<boolean> = fc.boolean();

/** Generator for a best_score (nullable integer) */
const arbBestScore: fc.Arbitrary<number | null> = fc.oneof(
  fc.constant(null),
  fc.integer({ min: 0, max: 50 })
);

// ---------------------------------------------------------------------------
// Property 13: Quiz pass cache consistency
// Validates: Requirements 10.5, 10.8
// ---------------------------------------------------------------------------

describe("Feature: Step_3-5_training-gated-access-control, Property 13: Quiz pass cache consistency", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 10.5**
   *
   * First checkQuizPassed call makes a network request and caches the result;
   * subsequent calls return the cached value without making additional network requests.
   */
  it("first call makes network request and caches; subsequent calls return cached value without network request", async () => {
    await fc.assert(
      fc.asyncProperty(
        arbContentId,
        arbUserId,
        arbHasPassed,
        arbBestScore,
        async (contentId, userId, hasPassed, bestScore) => {
          // Reset state and mocks for each iteration
          resetStore();
          vi.clearAllMocks();

          // Mock the API response
          const mockResponse: QuizPassStatus = {
            content_id: contentId,
            user_id: userId,
            has_passed: hasPassed,
            best_score: bestScore,
          };
          mockedApiClient.get.mockResolvedValue(mockResponse);

          // First call: should make a network request
          const result1 = await useTrainingStore
            .getState()
            .checkQuizPassed(contentId, userId);

          expect(result1).toBe(hasPassed);
          expect(mockedApiClient.get).toHaveBeenCalledTimes(1);
          expect(mockedApiClient.get).toHaveBeenCalledWith(
            `/api/training/quiz/passed/${contentId}?user_id=${userId}`
          );

          // Verify the value is cached
          const cachedEntry = useTrainingStore.getState().quizPassCache[contentId];
          expect(cachedEntry).toBeDefined();
          expect(cachedEntry.has_passed).toBe(hasPassed);

          // Second call: should return cached value without network request
          vi.clearAllMocks();
          const result2 = await useTrainingStore
            .getState()
            .checkQuizPassed(contentId, userId);

          expect(result2).toBe(hasPassed);
          expect(mockedApiClient.get).not.toHaveBeenCalled();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 14: Gate cache invalidation on state change
// Validates: Requirements 9.5, 10.8
// ---------------------------------------------------------------------------

describe("Feature: Step_3-5_training-gated-access-control, Property 14: Gate cache invalidation on state change", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 9.5, 10.8**
   *
   * When submitQuiz returns passed=true, the gate cache entry for that SOP
   * is invalidated and the quizPassCache entry is updated to reflect the pass.
   */
  it("quiz pass invalidates gate cache entry and updates quizPassCache", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.uuid(),
        fc
          .array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), {
            minLength: 1,
            maxLength: 5,
          })
          .map((chars) => chars.join("")),
        arbUserId,
        fc.integer({ min: 1, max: 50 }),
        fc.integer({ min: 1, max: 50 }),
        async (sopUuid, sopVersion, userId, score, totalQuestions) => {
          const contentId = `${sopUuid}_v${sopVersion}`;
          const gateCacheKey = `${sopUuid}_${sopVersion}`;

          // Reset state with pre-populated gate cache
          resetStore();
          vi.clearAllMocks();

          useTrainingStore.setState({
            gateCache: { [gateCacheKey]: false },
            isSubmittingQuiz: false,
            quizSubmitError: null,
          });

          // Mock a passing quiz submission response
          mockedApiClient.post.mockResolvedValue({
            attempt_id: 1,
            score,
            total_questions: totalQuestions,
            passed: true,
            passing_score_threshold: 0.8,
            correct_answers: {},
            attempted_at: "2024-01-15T10:30:00Z",
          });

          // Submit quiz
          const answers: Record<string, string> = {};
          await useTrainingStore
            .getState()
            .submitQuiz(contentId, userId, answers);

          const state = useTrainingStore.getState();

          // Gate cache entry should be invalidated (removed)
          expect(state.gateCache).not.toHaveProperty(gateCacheKey);

          // quizPassCache should be updated to reflect the pass
          expect(state.quizPassCache[contentId]).toBeDefined();
          expect(state.quizPassCache[contentId].has_passed).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 9.5, 10.8**
   *
   * When completeTrainingTask succeeds, the quizPassCache entry for the
   * derived content_id is invalidated and the gate cache entry is removed.
   */
  it("task completion invalidates quizPassCache and gate cache entries", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.uuid(),
        fc
          .array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), {
            minLength: 1,
            maxLength: 5,
          })
          .map((chars) => chars.join("")),
        arbUserId,
        fc.integer({ min: 1, max: 100000 }),
        async (sopUuid, sopVersion, userId, taskId) => {
          const contentId = `${sopUuid}_v${sopVersion}`;
          const gateCacheKey = `${sopUuid}_${sopVersion}`;

          // Reset state fully
          resetStore();
          vi.clearAllMocks();

          // Set up state with a task, pre-populated caches
          useTrainingStore.setState({
            tasks: [
              {
                id: taskId,
                sop_document_uuid: sopUuid,
                sop_version: sopVersion,
                assigned_user_id: userId,
                task_title: "Complete SOP Training",
                is_completed: false,
                completed_at: null,
                created_at: "2024-01-01T00:00:00Z",
              },
            ],
            quizPassCache: {
              [contentId]: {
                content_id: contentId,
                user_id: userId,
                has_passed: true,
                best_score: 4,
              },
            },
            gateCache: { [gateCacheKey]: false },
            isCompleting: false,
            completionError: null,
            statistics: { pending: 1, completed: 0, total: 1, completionPercentage: 0 },
          });

          // Mock successful task completion
          mockedApiClient.post.mockResolvedValue({
            id: taskId,
            is_completed: true,
            completed_at: "2024-03-01T12:00:00Z",
          });

          await useTrainingStore
            .getState()
            .completeTrainingTask(taskId, userId, "Training completed");

          const state = useTrainingStore.getState();

          // Gate cache entry should be invalidated (removed)
          expect(state.gateCache).not.toHaveProperty(gateCacheKey);

          // quizPassCache entry for the derived content_id should be invalidated (removed)
          expect(state.quizPassCache).not.toHaveProperty(contentId);
        }
      ),
      { numRuns: 100 }
    );
  });
});


// ---------------------------------------------------------------------------
// Property 11: Frontend training gate dual verification
// Validates: Requirements 9.1
// ---------------------------------------------------------------------------

import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import React from "react";

// Mock only the auth store for TrainingGateGuard rendering.
// The training store is NOT mocked — we use the real store with setState.
vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore as useAuthStoreMock } from "@/stores/authStore";
import { TrainingGateGuard } from "@/components/training/TrainingGateGuard";

const mockedUseAuthStore = useAuthStoreMock as unknown as ReturnType<typeof vi.fn>;

/** Generator for SOP UUID */
const arbSopUuid: fc.Arbitrary<string> = fc.uuid();

/** Generator for SOP version string */
const arbSopVersion: fc.Arbitrary<string> = fc
  .array(fc.constantFrom("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "."), {
    minLength: 1,
    maxLength: 5,
  })
  .map((chars) => chars.join(""));

describe("Feature: Step_3-5_training-gated-access-control, Property 11: Frontend training gate dual verification", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 9.1**
   *
   * TrainingGateGuard allows navigation (renders children) if and only if
   * BOTH the training task is completed AND the quiz is passed.
   * All other combinations block navigation (show alert role).
   */
  it("allows navigation iff both task completed AND quiz passed", () => {
    fc.assert(
      fc.property(
        arbSopUuid,
        arbSopVersion,
        arbUserId,
        fc.boolean(), // taskCompleted
        fc.boolean(), // quizPassed
        (sopUuid, sopVersion, userId, taskCompleted, quizPassed) => {
          cleanup();
          vi.clearAllMocks();

          const contentId = `${sopUuid}_v${sopVersion}`;

          // Build quizPassCache based on quizPassed flag
          const quizPassCache: Record<string, { content_id: string; user_id: number; has_passed: boolean; best_score: number | null }> = {};
          if (taskCompleted) {
            // Only populate quiz cache when task is complete (component only checks quiz after task passes)
            quizPassCache[contentId] = {
              content_id: contentId,
              user_id: userId,
              has_passed: quizPassed,
              best_score: quizPassed ? 5 : null,
            };
          }

          // Set up the real training store state for the component to read
          useTrainingStore.setState({
            hasFetchedTasks: true,
            tasks: taskCompleted
              ? [
                  {
                    id: 1,
                    sop_document_uuid: sopUuid,
                    sop_version: sopVersion,
                    assigned_user_id: userId,
                    task_title: "Complete SOP Training",
                    is_completed: true,
                    completed_at: "2024-01-15T10:00:00Z",
                    created_at: "2024-01-01T00:00:00Z",
                  },
                ]
              : [],
            quizPassCache,
            isCheckingQuizPass: false,
            quizPassError: null,
            gateCache: {},
            isCheckingGate: false,
          });

          // Mock useAuthStore to provide user
          mockedUseAuthStore.mockImplementation((selector: (state: unknown) => unknown) => {
            const state = {
              user: { id: userId, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["user"] },
            };
            return selector(state);
          });

          const childEl = React.createElement("div", { "data-testid": "protected-content" }, "Protected Content");
          const guardEl = React.createElement(
            TrainingGateGuard,
            { sopDocumentUuid: sopUuid, sopVersion: sopVersion, sopStatus: "InTraining" },
            childEl
          );
          const routerEl = React.createElement(MemoryRouter, null, guardEl);

          render(routerEl);

          const childContent = screen.queryByTestId("protected-content");
          const alertElement = screen.queryByRole("alert");

          if (taskCompleted && quizPassed) {
            // Both conditions met → children rendered, no alert
            expect(childContent).not.toBeNull();
            expect(alertElement).toBeNull();
          } else {
            // At least one condition fails → blocked, alert shown
            expect(childContent).toBeNull();
            expect(alertElement).not.toBeNull();
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
