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
} from "../components/training/types";
import {
  computeStatistics,
  extractErrorMessage,
  buildGateCacheKey,
  invalidateGateCacheEntry,
  checkGateFromTasks,
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
      }

      set({
        tasks,
        statistics,
        gateCache,
        isCompleting: false,
      });

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
}));
