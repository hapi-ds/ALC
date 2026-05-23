/**
 * Training Management Store (Zustand)
 *
 * Centralized state management for training tasks, content, status,
 * content review, and training gate enforcement.
 */

import { create } from "zustand";
import { apiClient } from "../lib/apiClient";
import type {
  TrainingTask,
  TrainingStatus,
  TrainingContent,
  TrainingStatistics,
  TaskFilter,
  GateCache,
  QuizAttemptResult,
  QuizPassStatus,
  QuizResultsResponse,
} from "../components/training/types";
import {
  computeStatistics,
  extractErrorMessage,
  buildGateCacheKey,
  invalidateGateCacheEntry,
  checkGateFromTasks,
  deriveContentId,
} from "../components/training/utils";

// ---------------------------------------------------------------------------
// Store Interface
// ---------------------------------------------------------------------------

export interface TrainingStoreState {
  // Task state
  tasks: TrainingTask[];
  isLoadingTasks: boolean;
  tasksError: string | null;
  filter: TaskFilter;
  hasFetchedTasks: boolean;

  // Statistics (computed from tasks)
  statistics: TrainingStatistics;

  // Task completion
  isCompleting: boolean;
  completionError: string | null;

  // Content state
  currentContent: TrainingContent | null;
  isLoadingContent: boolean;
  contentError: string | null;

  // Admin status
  sopStatus: TrainingStatus | null;
  isLoadingStatus: boolean;
  statusError: string | null;

  // Content review
  pendingReviewItems: TrainingContent[];
  isReviewing: boolean;
  reviewError: string | null;

  // Gate state
  gateCache: GateCache;
  isCheckingGate: boolean;

  // Quiz state
  currentQuizAttempt: QuizAttemptResult | null;
  isSubmittingQuiz: boolean;
  quizSubmitError: string | null;
  quizResults: Record<string, QuizAttemptResult[]>;
  isLoadingQuizResults: boolean;
  quizResultsError: string | null;
  quizPassCache: Record<string, QuizPassStatus>;
  isCheckingQuizPass: boolean;
  quizPassError: string | null;

  // Actions
  fetchTrainingTasks: (userId: number) => Promise<void>;
  completeTrainingTask: (
    taskId: number,
    userId: number,
    changeReason: string
  ) => Promise<boolean>;
  fetchTrainingContent: (contentId: string) => Promise<void>;
  fetchTrainingStatus: (sopUuid: string, version: string) => Promise<void>;
  approveContent: (
    contentId: string,
    reviewerId: number,
    notes: string
  ) => Promise<boolean>;
  rejectContent: (
    contentId: string,
    reviewerId: number,
    notes: string
  ) => Promise<boolean>;
  setFilter: (filter: TaskFilter) => void;
  checkTrainingGate: (
    sopDocumentUuid: string,
    sopVersion: string,
    userId: number
  ) => boolean | null;
  clearGateCache: () => void;

  // Quiz actions
  submitQuiz: (
    contentId: string,
    userId: number,
    answers: Record<string, string>
  ) => Promise<QuizAttemptResult | null>;
  fetchQuizResults: (contentId: string, userId: number) => Promise<void>;
  checkQuizPassed: (
    contentId: string,
    userId: number
  ) => Promise<boolean | null>;
  clearQuizPassCache: () => void;
}

// ---------------------------------------------------------------------------
// Initial statistics (empty state)
// ---------------------------------------------------------------------------

const EMPTY_STATISTICS: TrainingStatistics = {
  pending: 0,
  completed: 0,
  total: 0,
  completionPercentage: null,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTrainingStore = create<TrainingStoreState>((set, get) => ({
  // Task state
  tasks: [],
  isLoadingTasks: false,
  tasksError: null,
  filter: "all",
  hasFetchedTasks: false,

  // Statistics
  statistics: EMPTY_STATISTICS,

  // Task completion
  isCompleting: false,
  completionError: null,

  // Content state
  currentContent: null,
  isLoadingContent: false,
  contentError: null,

  // Admin status
  sopStatus: null,
  isLoadingStatus: false,
  statusError: null,

  // Content review
  pendingReviewItems: [],
  isReviewing: false,
  reviewError: null,

  // Gate state
  gateCache: {},
  isCheckingGate: false,

  // Quiz state
  currentQuizAttempt: null,
  isSubmittingQuiz: false,
  quizSubmitError: null,
  quizResults: {},
  isLoadingQuizResults: false,
  quizResultsError: null,
  quizPassCache: {},
  isCheckingQuizPass: false,
  quizPassError: null,

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  fetchTrainingTasks: async (userId: number) => {
    // Request deduplication
    if (get().isLoadingTasks) return;

    set({ isLoadingTasks: true, tasksError: null });

    try {
      const tasks = await apiClient.get<TrainingTask[]>(
        `/api/training/tasks?user_id=${userId}`
      );
      const statistics = computeStatistics(tasks);
      set({
        tasks,
        statistics,
        isLoadingTasks: false,
        hasFetchedTasks: true,
      });
    } catch (error) {
      set({
        tasksError: extractErrorMessage(error),
        isLoadingTasks: false,
        hasFetchedTasks: true,
      });
    }
  },

  completeTrainingTask: async (
    taskId: number,
    userId: number,
    changeReason: string
  ) => {
    // Request deduplication
    if (get().isCompleting) return false;

    set({ isCompleting: true, completionError: null });

    try {
      const response = await apiClient.post<{
        id: number;
        is_completed: boolean;
        completed_at: string;
      }>(`/api/training/tasks/${taskId}/complete?user_id=${userId}`, undefined, {
        changeReason,
      });

      // Update the task in the local array
      const tasks = get().tasks.map((task) =>
        task.id === taskId
          ? {
              ...task,
              is_completed: true,
              completed_at: response.completed_at,
            }
          : task
      );

      // Recompute statistics
      const statistics = computeStatistics(tasks);

      // Invalidate gate cache for this task's SOP
      const completedTask = get().tasks.find((t) => t.id === taskId);
      let gateCache = get().gateCache;
      if (completedTask) {
        gateCache = invalidateGateCacheEntry(
          gateCache,
          completedTask.sop_document_uuid,
          completedTask.sop_version
        );

        // Also invalidate quizPassCache for the derived content_id
        const contentId = deriveContentId(
          completedTask.sop_document_uuid,
          completedTask.sop_version
        );
        const quizPassCache = { ...get().quizPassCache };
        delete quizPassCache[contentId];

        set({
          tasks,
          statistics,
          gateCache,
          quizPassCache,
          isCompleting: false,
        });
      } else {
        set({
          tasks,
          statistics,
          gateCache,
          isCompleting: false,
        });
      }

      return true;
    } catch (error) {
      set({
        completionError: extractErrorMessage(error),
        isCompleting: false,
      });
      return false;
    }
  },

  fetchTrainingContent: async (contentId: string) => {
    // Request deduplication
    if (get().isLoadingContent) return;

    set({ isLoadingContent: true, contentError: null, currentContent: null });

    try {
      const content = await apiClient.get<TrainingContent>(
        `/api/training/content/${contentId}`
      );
      set({ currentContent: content, isLoadingContent: false });
    } catch (error) {
      set({
        contentError: extractErrorMessage(error),
        isLoadingContent: false,
      });
    }
  },

  fetchTrainingStatus: async (sopUuid: string, version: string) => {
    // Request deduplication
    if (get().isLoadingStatus) return;

    set({ isLoadingStatus: true, statusError: null });

    try {
      const status = await apiClient.get<TrainingStatus>(
        `/api/training/status/${sopUuid}/${version}`
      );
      set({ sopStatus: status, isLoadingStatus: false });
    } catch (error) {
      set({
        statusError: extractErrorMessage(error),
        isLoadingStatus: false,
      });
    }
  },

  approveContent: async (
    contentId: string,
    reviewerId: number,
    notes: string
  ) => {
    // Request deduplication
    if (get().isReviewing) return false;

    set({ isReviewing: true, reviewError: null });

    try {
      await apiClient.post(
        `/api/training/content/${contentId}/approve`,
        { reviewer_id: reviewerId, notes },
        { changeReason: "Training content approved" }
      );

      // Remove from pending review items
      const pendingReviewItems = get().pendingReviewItems.filter(
        (item) => item.content_id !== contentId
      );

      set({ pendingReviewItems, isReviewing: false });
      return true;
    } catch (error) {
      set({
        reviewError: extractErrorMessage(error),
        isReviewing: false,
      });
      return false;
    }
  },

  rejectContent: async (
    contentId: string,
    reviewerId: number,
    notes: string
  ) => {
    // Request deduplication
    if (get().isReviewing) return false;

    set({ isReviewing: true, reviewError: null });

    try {
      await apiClient.post(
        `/api/training/content/${contentId}/reject`,
        { reviewer_id: reviewerId, notes },
        { changeReason: "Training content rejected" }
      );

      // Remove from pending review items
      const pendingReviewItems = get().pendingReviewItems.filter(
        (item) => item.content_id !== contentId
      );

      set({ pendingReviewItems, isReviewing: false });
      return true;
    } catch (error) {
      set({
        reviewError: extractErrorMessage(error),
        isReviewing: false,
      });
      return false;
    }
  },

  setFilter: (filter: TaskFilter) => {
    set({ filter });
  },

  checkTrainingGate: (
    sopDocumentUuid: string,
    sopVersion: string,
    _userId: number
  ) => {
    const { gateCache, tasks, hasFetchedTasks } = get();

    // If tasks haven't been fetched yet, return null to signal loading needed
    if (!hasFetchedTasks) {
      return null;
    }

    // Check cache first
    const cacheKey = buildGateCacheKey(sopDocumentUuid, sopVersion);
    if (cacheKey in gateCache) {
      return gateCache[cacheKey];
    }

    // Check from local tasks
    const result = checkGateFromTasks(tasks, sopDocumentUuid, sopVersion);

    // Cache the result
    set({ gateCache: { ...gateCache, [cacheKey]: result } });

    return result;
  },

  clearGateCache: () => {
    set({ gateCache: {} });
  },

  // ---------------------------------------------------------------------------
  // Quiz Actions
  // ---------------------------------------------------------------------------

  submitQuiz: async (
    contentId: string,
    userId: number,
    answers: Record<string, string>
  ) => {
    // Request deduplication
    if (get().isSubmittingQuiz) return null;

    set({ isSubmittingQuiz: true, quizSubmitError: null });

    try {
      const result = await apiClient.post<QuizAttemptResult>(
        `/api/training/quiz/submit`,
        { content_id: contentId, user_id: userId, answers },
        { changeReason: "Quiz attempt submitted" }
      );

      // Store the result
      set({ currentQuizAttempt: result, isSubmittingQuiz: false });

      // If the quiz was passed, update quizPassCache and invalidate gate cache
      if (result.passed) {
        const quizPassCache = { ...get().quizPassCache };
        quizPassCache[contentId] = {
          content_id: contentId,
          user_id: userId,
          has_passed: true,
          best_score: result.score,
        };

        // Invalidate gate cache for the corresponding SOP
        // content_id format: {sop_document_uuid}_v{sop_version}
        const parts = contentId.split("_v");
        let gateCache = get().gateCache;
        if (parts.length >= 2) {
          const sopDocumentUuid = parts[0];
          const sopVersion = parts.slice(1).join("_v");
          gateCache = invalidateGateCacheEntry(
            gateCache,
            sopDocumentUuid,
            sopVersion
          );
        }

        set({ quizPassCache, gateCache });
      }

      return result;
    } catch (error) {
      set({
        quizSubmitError: extractErrorMessage(error),
        isSubmittingQuiz: false,
      });
      return null;
    }
  },

  fetchQuizResults: async (contentId: string, userId: number) => {
    // Request deduplication
    if (get().isLoadingQuizResults) return;

    set({ isLoadingQuizResults: true, quizResultsError: null });

    try {
      const response = await apiClient.get<QuizResultsResponse>(
        `/api/training/quiz/results/${contentId}?user_id=${userId}`
      );

      const quizResults = { ...get().quizResults };
      quizResults[contentId] = response.results.map((entry) => ({
        attempt_id: entry.attempt_id,
        score: entry.score,
        total_questions: entry.total_questions,
        passed: entry.passed,
        passing_score_threshold: 0.8,
        correct_answers: {},
        attempted_at: entry.attempted_at,
      }));

      set({ quizResults, isLoadingQuizResults: false });
    } catch (error) {
      set({
        quizResultsError: extractErrorMessage(error),
        isLoadingQuizResults: false,
      });
    }
  },

  checkQuizPassed: async (contentId: string, userId: number) => {
    // Cache-first strategy: return cached value if available
    const cached = get().quizPassCache[contentId];
    if (cached !== undefined) {
      return cached.has_passed;
    }

    // Request deduplication
    if (get().isCheckingQuizPass) return null;

    set({ isCheckingQuizPass: true, quizPassError: null });

    try {
      const response = await apiClient.get<QuizPassStatus>(
        `/api/training/quiz/passed/${contentId}?user_id=${userId}`
      );

      const quizPassCache = { ...get().quizPassCache };
      quizPassCache[contentId] = response;

      set({ quizPassCache, isCheckingQuizPass: false });

      return response.has_passed;
    } catch (error) {
      set({
        quizPassError: extractErrorMessage(error),
        isCheckingQuizPass: false,
      });
      return null;
    }
  },

  clearQuizPassCache: () => {
    set({ quizPassCache: {}, quizPassError: null, isCheckingQuizPass: false });
  },
}));
