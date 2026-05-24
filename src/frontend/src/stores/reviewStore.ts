/**
 * Review Store (Zustand)
 *
 * Centralized state management for multi-agent review sessions:
 * listing sessions, viewing session details, managing action items,
 * compliance scorecard, and polling for in-progress sessions.
 *
 * Polling: refreshes the current session every 10 seconds when its status
 * is Pending or InProgress.
 *
 * Requirements: 11.7
 */

import { create } from "zustand";
import { ApiError } from "../lib/apiClient";
import {
  fetchReviewSessions,
  fetchReviewSessionDetail,
  submitReview as apiSubmitReview,
  approveSession as apiApproveSession,
  rejectSession as apiRejectSession,
  fetchActionItems,
  updateActionItem as apiUpdateActionItem,
  fetchComplianceScorecard,
} from "../lib/reviews-api";
import type {
  ReviewSession,
  ActionItem,
  ComplianceScorecard,
  ReviewSubmitRequest,
  ReviewListParams,
  ActionItemUpdateRequest,
} from "../lib/reviews-api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 10_000;
const POLLABLE_STATUSES = ["Pending", "InProgress"];

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface ReviewState {
  // Sessions list
  sessions: ReviewSession[];
  sessionsTotal: number;
  isLoadingSessions: boolean;
  sessionsError: string | null;

  // Current session detail
  currentSession: ReviewSession | null;
  isLoadingDetail: boolean;
  detailError: string | null;

  // Action items for current session
  actionItems: ActionItem[];
  isLoadingActionItems: boolean;
  actionItemsError: string | null;

  // Compliance scorecard
  scorecard: ComplianceScorecard | null;
  isLoadingScorecard: boolean;
  scorecardError: string | null;

  // Submission state
  isSubmitting: boolean;
  submitError: string | null;

  // Approve/Reject state
  isApproving: boolean;
  approveError: string | null;

  // Polling
  pollingIntervalId: ReturnType<typeof setInterval> | null;

  // Actions
  fetchSessions: (params?: ReviewListParams) => Promise<void>;
  fetchSessionDetail: (sessionId: number) => Promise<void>;
  submitReview: (request: ReviewSubmitRequest, changeReason: string) => Promise<ReviewSession>;
  approveSession: (sessionId: number, changeReason: string) => Promise<void>;
  rejectSession: (sessionId: number, changeReason: string) => Promise<void>;
  updateActionItem: (
    sessionId: number,
    itemId: number,
    data: ActionItemUpdateRequest,
    changeReason: string,
  ) => Promise<void>;
  fetchScorecard: () => Promise<void>;
  startPolling: (sessionId: number) => void;
  stopPolling: () => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const parsed = JSON.parse(error.body);
      return parsed.detail || parsed.message || error.message;
    } catch {
      return error.body || error.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred";
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useReviewStore = create<ReviewState>((set, get) => ({
  // Sessions list
  sessions: [],
  sessionsTotal: 0,
  isLoadingSessions: false,
  sessionsError: null,

  // Current session detail
  currentSession: null,
  isLoadingDetail: false,
  detailError: null,

  // Action items
  actionItems: [],
  isLoadingActionItems: false,
  actionItemsError: null,

  // Scorecard
  scorecard: null,
  isLoadingScorecard: false,
  scorecardError: null,

  // Submission
  isSubmitting: false,
  submitError: null,

  // Approve/Reject
  isApproving: false,
  approveError: null,

  // Polling
  pollingIntervalId: null,

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  fetchSessions: async (params?: ReviewListParams) => {
    set({ isLoadingSessions: true, sessionsError: null });

    try {
      const response = await fetchReviewSessions(params);
      set({
        sessions: response.items,
        sessionsTotal: response.total,
        isLoadingSessions: false,
      });
    } catch (error) {
      set({
        sessionsError: extractErrorMessage(error),
        isLoadingSessions: false,
      });
    }
  },

  fetchSessionDetail: async (sessionId: number) => {
    set({ isLoadingDetail: true, detailError: null });

    try {
      const session = await fetchReviewSessionDetail(sessionId);
      set({ currentSession: session, isLoadingDetail: false });

      // Fetch action items for this session
      set({ isLoadingActionItems: true, actionItemsError: null });
      try {
        const items = await fetchActionItems(sessionId);
        set({ actionItems: items, isLoadingActionItems: false });
      } catch (itemError) {
        set({
          actionItemsError: extractErrorMessage(itemError),
          isLoadingActionItems: false,
        });
      }

      // Start or stop polling based on session status
      if (POLLABLE_STATUSES.includes(session.status)) {
        get().startPolling(sessionId);
      } else {
        get().stopPolling();
      }
    } catch (error) {
      set({
        detailError: extractErrorMessage(error),
        isLoadingDetail: false,
      });
    }
  },

  submitReview: async (request: ReviewSubmitRequest, changeReason: string) => {
    set({ isSubmitting: true, submitError: null });

    try {
      const session = await apiSubmitReview(request, changeReason);
      set({ isSubmitting: false });

      // Prepend new session to list if list was previously fetched
      const { sessions } = get();
      if (sessions.length > 0) {
        set({ sessions: [session, ...sessions], sessionsTotal: get().sessionsTotal + 1 });
      }

      return session;
    } catch (error) {
      const message = extractErrorMessage(error);
      set({ submitError: message, isSubmitting: false });
      throw error;
    }
  },

  approveSession: async (sessionId: number, changeReason: string) => {
    set({ isApproving: true, approveError: null });

    try {
      const updated = await apiApproveSession(sessionId, changeReason);
      set({ currentSession: updated, isApproving: false });

      // Update session in list
      const { sessions } = get();
      set({
        sessions: sessions.map((s) => (s.id === sessionId ? { ...s, status: updated.status } : s)),
      });
    } catch (error) {
      set({
        approveError: extractErrorMessage(error),
        isApproving: false,
      });
    }
  },

  rejectSession: async (sessionId: number, changeReason: string) => {
    set({ isApproving: true, approveError: null });

    try {
      const updated = await apiRejectSession(sessionId, changeReason);
      set({ currentSession: updated, isApproving: false });

      // Update session in list
      const { sessions } = get();
      set({
        sessions: sessions.map((s) => (s.id === sessionId ? { ...s, status: updated.status } : s)),
      });
    } catch (error) {
      set({
        approveError: extractErrorMessage(error),
        isApproving: false,
      });
    }
  },

  updateActionItem: async (
    sessionId: number,
    itemId: number,
    data: ActionItemUpdateRequest,
    changeReason: string,
  ) => {
    try {
      const updated = await apiUpdateActionItem(sessionId, itemId, data, changeReason);

      // Update item in local state
      const { actionItems } = get();
      set({
        actionItems: actionItems.map((item) => (item.id === itemId ? updated : item)),
      });
    } catch (error) {
      set({ actionItemsError: extractErrorMessage(error) });
      throw error;
    }
  },

  fetchScorecard: async () => {
    set({ isLoadingScorecard: true, scorecardError: null });

    try {
      const scorecard = await fetchComplianceScorecard();
      set({ scorecard, isLoadingScorecard: false });
    } catch (error) {
      set({
        scorecardError: extractErrorMessage(error),
        isLoadingScorecard: false,
      });
    }
  },

  startPolling: (sessionId: number) => {
    const { pollingIntervalId } = get();

    // Don't start a new interval if one is already running
    if (pollingIntervalId !== null) {
      return;
    }

    const intervalId = setInterval(async () => {
      try {
        const session = await fetchReviewSessionDetail(sessionId);
        set({ currentSession: session });

        // Also refresh action items
        try {
          const items = await fetchActionItems(sessionId);
          set({ actionItems: items });
        } catch {
          // Non-blocking: action items refresh failure during polling is acceptable
        }

        // Stop polling if session is no longer in a pollable status
        if (!POLLABLE_STATUSES.includes(session.status)) {
          get().stopPolling();
        }
      } catch {
        // Polling errors are non-blocking — don't update error state
      }
    }, POLL_INTERVAL_MS);

    set({ pollingIntervalId: intervalId });
  },

  stopPolling: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId !== null) {
      clearInterval(pollingIntervalId);
      set({ pollingIntervalId: null });
    }
  },

  reset: () => {
    const { pollingIntervalId } = get();
    if (pollingIntervalId !== null) {
      clearInterval(pollingIntervalId);
    }

    set({
      sessions: [],
      sessionsTotal: 0,
      isLoadingSessions: false,
      sessionsError: null,
      currentSession: null,
      isLoadingDetail: false,
      detailError: null,
      actionItems: [],
      isLoadingActionItems: false,
      actionItemsError: null,
      scorecard: null,
      isLoadingScorecard: false,
      scorecardError: null,
      isSubmitting: false,
      submitError: null,
      isApproving: false,
      approveError: null,
      pollingIntervalId: null,
    });
  },
}));
