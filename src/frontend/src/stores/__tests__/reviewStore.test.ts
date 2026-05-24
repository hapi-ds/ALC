import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { useReviewStore } from "../reviewStore";
import type {
  ReviewSession,
  ActionItem,
  ComplianceScorecard,
  PaginatedResponse,
} from "../../lib/reviews-api";

// Mock the reviews-api module
vi.mock("../../lib/reviews-api", () => ({
  fetchReviewSessions: vi.fn(),
  fetchReviewSessionDetail: vi.fn(),
  submitReview: vi.fn(),
  approveSession: vi.fn(),
  rejectSession: vi.fn(),
  fetchActionItems: vi.fn(),
  updateActionItem: vi.fn(),
  fetchComplianceScorecard: vi.fn(),
}));

// Mock apiClient (needed for ApiError import)
vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
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

import {
  fetchReviewSessions,
  fetchReviewSessionDetail,
  submitReview,
  approveSession,
  rejectSession,
  fetchActionItems,
  updateActionItem,
  fetchComplianceScorecard,
} from "../../lib/reviews-api";
import { ApiError } from "../../lib/apiClient";

const mockedFetchSessions = fetchReviewSessions as ReturnType<typeof vi.fn>;
const mockedFetchDetail = fetchReviewSessionDetail as ReturnType<typeof vi.fn>;
const mockedSubmitReview = submitReview as ReturnType<typeof vi.fn>;
const mockedApproveSession = approveSession as ReturnType<typeof vi.fn>;
const mockedRejectSession = rejectSession as ReturnType<typeof vi.fn>;
const mockedFetchActionItems = fetchActionItems as ReturnType<typeof vi.fn>;
const mockedUpdateActionItem = updateActionItem as ReturnType<typeof vi.fn>;
const mockedFetchScorecard = fetchComplianceScorecard as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<ReviewSession> = {}): ReviewSession {
  return {
    id: 1,
    document_id: 10,
    document_title: "Test SOP",
    document_type: "SOP",
    status: "Completed",
    compliance_score: 85.0,
    summary_failed: false,
    submitted_by: 1,
    submitted_at: "2024-03-15T10:00:00Z",
    completed_at: "2024-03-15T10:30:00Z",
    agent_reviews: null,
    master_summary: null,
    ...overrides,
  };
}

function makeActionItem(overrides: Partial<ActionItem> = {}): ActionItem {
  return {
    id: 1,
    finding_id: "F-001",
    title: "Missing version control",
    description: "Document lacks proper version control headers",
    severity: "Major",
    status: "Open",
    assigned_to: null,
    resolved_at: null,
    resolution_note: null,
    created_at: "2024-03-15T10:30:00Z",
    updated_at: null,
    ...overrides,
  };
}

function makeScorecard(overrides: Partial<ComplianceScorecard> = {}): ComplianceScorecard {
  return {
    overall_score: 82.5,
    risk_band: "Good",
    trend: "improving",
    total_documents_reviewed: 15,
    documents_with_critical_findings: 2,
    documents_with_open_action_items: 5,
    score_by_document_type: { SOP: 90.0, Protocol: 75.0 },
    last_updated: "2024-03-15T12:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("reviewStore", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useReviewStore.getState().reset();
    vi.clearAllMocks();
  });

  afterEach(() => {
    useReviewStore.getState().stopPolling();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // fetchSessions
  // -------------------------------------------------------------------------

  describe("fetchSessions", () => {
    it("sets loading state and fetches sessions successfully", async () => {
      const sessions = [makeSession({ id: 1 }), makeSession({ id: 2 })];
      const response: PaginatedResponse<ReviewSession> = { items: sessions, total: 2 };
      mockedFetchSessions.mockResolvedValue(response);

      await useReviewStore.getState().fetchSessions();

      const state = useReviewStore.getState();
      expect(state.sessions).toEqual(sessions);
      expect(state.sessionsTotal).toBe(2);
      expect(state.isLoadingSessions).toBe(false);
      expect(state.sessionsError).toBeNull();
    });

    it("passes filter params to the API", async () => {
      mockedFetchSessions.mockResolvedValue({ items: [], total: 0 });

      await useReviewStore.getState().fetchSessions({ status: "Completed", limit: 10 });

      expect(mockedFetchSessions).toHaveBeenCalledWith({ status: "Completed", limit: 10 });
    });

    it("sets error on failure", async () => {
      mockedFetchSessions.mockRejectedValue(
        new ApiError(500, '{"detail":"Server error"}', "/api/reviews"),
      );

      await useReviewStore.getState().fetchSessions();

      const state = useReviewStore.getState();
      expect(state.sessionsError).toBe("Server error");
      expect(state.isLoadingSessions).toBe(false);
    });

    it("clears previous error on new request", async () => {
      mockedFetchSessions.mockRejectedValueOnce(new Error("Network error"));
      await useReviewStore.getState().fetchSessions();
      expect(useReviewStore.getState().sessionsError).toBe("Network error");

      mockedFetchSessions.mockResolvedValueOnce({ items: [], total: 0 });
      await useReviewStore.getState().fetchSessions();
      expect(useReviewStore.getState().sessionsError).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // fetchSessionDetail
  // -------------------------------------------------------------------------

  describe("fetchSessionDetail", () => {
    it("fetches session detail and action items", async () => {
      const session = makeSession({ id: 5, status: "Completed" });
      const items = [makeActionItem({ id: 1 }), makeActionItem({ id: 2 })];
      mockedFetchDetail.mockResolvedValue(session);
      mockedFetchActionItems.mockResolvedValue(items);

      await useReviewStore.getState().fetchSessionDetail(5);

      const state = useReviewStore.getState();
      expect(state.currentSession).toEqual(session);
      expect(state.actionItems).toEqual(items);
      expect(state.isLoadingDetail).toBe(false);
      expect(state.isLoadingActionItems).toBe(false);
    });

    it("sets error on detail fetch failure", async () => {
      mockedFetchDetail.mockRejectedValue(
        new ApiError(404, '{"detail":"Review session not found"}', "/api/reviews/99"),
      );

      await useReviewStore.getState().fetchSessionDetail(99);

      const state = useReviewStore.getState();
      expect(state.detailError).toBe("Review session not found");
      expect(state.isLoadingDetail).toBe(false);
    });

    it("starts polling when session is Pending", async () => {
      const session = makeSession({ id: 3, status: "Pending" });
      mockedFetchDetail.mockResolvedValue(session);
      mockedFetchActionItems.mockResolvedValue([]);

      await useReviewStore.getState().fetchSessionDetail(3);

      expect(useReviewStore.getState().pollingIntervalId).not.toBeNull();
    });

    it("starts polling when session is InProgress", async () => {
      const session = makeSession({ id: 4, status: "InProgress" });
      mockedFetchDetail.mockResolvedValue(session);
      mockedFetchActionItems.mockResolvedValue([]);

      await useReviewStore.getState().fetchSessionDetail(4);

      expect(useReviewStore.getState().pollingIntervalId).not.toBeNull();
    });

    it("does not start polling when session is Completed", async () => {
      const session = makeSession({ id: 6, status: "Completed" });
      mockedFetchDetail.mockResolvedValue(session);
      mockedFetchActionItems.mockResolvedValue([]);

      await useReviewStore.getState().fetchSessionDetail(6);

      expect(useReviewStore.getState().pollingIntervalId).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // submitReview
  // -------------------------------------------------------------------------

  describe("submitReview", () => {
    it("submits review and returns session", async () => {
      const session = makeSession({ id: 10, status: "Pending" });
      mockedSubmitReview.mockResolvedValue(session);

      const result = await useReviewStore.getState().submitReview(
        { document_id: 1, document_version_id: 2 },
        "Submitting for compliance review",
      );

      expect(result).toEqual(session);
      expect(useReviewStore.getState().isSubmitting).toBe(false);
      expect(useReviewStore.getState().submitError).toBeNull();
    });

    it("prepends session to list when list is populated", async () => {
      const existing = makeSession({ id: 1 });
      useReviewStore.setState({ sessions: [existing], sessionsTotal: 1 });

      const newSession = makeSession({ id: 10, status: "Pending" });
      mockedSubmitReview.mockResolvedValue(newSession);

      await useReviewStore.getState().submitReview(
        { document_id: 1, document_version_id: 2 },
        "Review submission",
      );

      const state = useReviewStore.getState();
      expect(state.sessions).toHaveLength(2);
      expect(state.sessions[0]).toEqual(newSession);
      expect(state.sessionsTotal).toBe(2);
    });

    it("sets error and throws on failure", async () => {
      mockedSubmitReview.mockRejectedValue(
        new ApiError(409, '{"detail":"Document already has an active review session"}', "/api/reviews"),
      );

      await expect(
        useReviewStore.getState().submitReview(
          { document_id: 1, document_version_id: 2 },
          "Review",
        ),
      ).rejects.toThrow();

      const state = useReviewStore.getState();
      expect(state.submitError).toBe("Document already has an active review session");
      expect(state.isSubmitting).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // approveSession / rejectSession
  // -------------------------------------------------------------------------

  describe("approveSession", () => {
    it("approves session and updates state", async () => {
      const approved = makeSession({ id: 1, status: "Approved" });
      mockedApproveSession.mockResolvedValue(approved);
      useReviewStore.setState({ sessions: [makeSession({ id: 1 })] });

      await useReviewStore.getState().approveSession(1, "Approved after review");

      const state = useReviewStore.getState();
      expect(state.currentSession).toEqual(approved);
      expect(state.isApproving).toBe(false);
      expect(state.sessions[0].status).toBe("Approved");
    });

    it("sets error on approval failure", async () => {
      mockedApproveSession.mockRejectedValue(
        new ApiError(409, '{"detail":"Only completed sessions can be approved"}', "/api/reviews/1/approve"),
      );

      await useReviewStore.getState().approveSession(1, "Approve");

      expect(useReviewStore.getState().approveError).toBe("Only completed sessions can be approved");
      expect(useReviewStore.getState().isApproving).toBe(false);
    });
  });

  describe("rejectSession", () => {
    it("rejects session and updates state", async () => {
      const rejected = makeSession({ id: 1, status: "Rejected" });
      mockedRejectSession.mockResolvedValue(rejected);
      useReviewStore.setState({ sessions: [makeSession({ id: 1 })] });

      await useReviewStore.getState().rejectSession(1, "Findings not addressed");

      const state = useReviewStore.getState();
      expect(state.currentSession).toEqual(rejected);
      expect(state.isApproving).toBe(false);
      expect(state.sessions[0].status).toBe("Rejected");
    });
  });

  // -------------------------------------------------------------------------
  // updateActionItem
  // -------------------------------------------------------------------------

  describe("updateActionItem", () => {
    it("updates action item in local state", async () => {
      const original = makeActionItem({ id: 1, status: "Open" });
      const updated = makeActionItem({ id: 1, status: "InProgress" });
      useReviewStore.setState({ actionItems: [original] });
      mockedUpdateActionItem.mockResolvedValue(updated);

      await useReviewStore.getState().updateActionItem(1, 1, { status: "InProgress" }, "Starting work");

      expect(useReviewStore.getState().actionItems[0].status).toBe("InProgress");
    });

    it("sets error and throws on failure", async () => {
      useReviewStore.setState({ actionItems: [makeActionItem()] });
      mockedUpdateActionItem.mockRejectedValue(
        new ApiError(400, '{"detail":"Invalid status transition"}', "/api/reviews/1/action-items/1"),
      );

      await expect(
        useReviewStore.getState().updateActionItem(1, 1, { status: "Invalid" }, "Test"),
      ).rejects.toThrow();

      expect(useReviewStore.getState().actionItemsError).toBe("Invalid status transition");
    });
  });

  // -------------------------------------------------------------------------
  // fetchScorecard
  // -------------------------------------------------------------------------

  describe("fetchScorecard", () => {
    it("fetches scorecard successfully", async () => {
      const scorecard = makeScorecard();
      mockedFetchScorecard.mockResolvedValue(scorecard);

      await useReviewStore.getState().fetchScorecard();

      const state = useReviewStore.getState();
      expect(state.scorecard).toEqual(scorecard);
      expect(state.isLoadingScorecard).toBe(false);
      expect(state.scorecardError).toBeNull();
    });

    it("sets error on scorecard fetch failure", async () => {
      mockedFetchScorecard.mockRejectedValue(new Error("Network error"));

      await useReviewStore.getState().fetchScorecard();

      expect(useReviewStore.getState().scorecardError).toBe("Network error");
      expect(useReviewStore.getState().isLoadingScorecard).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // Polling
  // -------------------------------------------------------------------------

  describe("polling", () => {
    it("polls every 10 seconds and updates session", async () => {
      const inProgress = makeSession({ id: 7, status: "InProgress" });
      const completed = makeSession({ id: 7, status: "Completed" });
      mockedFetchActionItems.mockResolvedValue([]);

      // Start polling
      useReviewStore.getState().startPolling(7);
      expect(useReviewStore.getState().pollingIntervalId).not.toBeNull();

      // After first poll interval, session is still InProgress
      mockedFetchDetail.mockResolvedValueOnce(inProgress);
      await vi.advanceTimersByTimeAsync(10_000);
      expect(useReviewStore.getState().currentSession).toEqual(inProgress);
      expect(useReviewStore.getState().pollingIntervalId).not.toBeNull();

      // After second poll interval, session completes — polling should stop
      mockedFetchDetail.mockResolvedValueOnce(completed);
      await vi.advanceTimersByTimeAsync(10_000);
      expect(useReviewStore.getState().currentSession).toEqual(completed);
      expect(useReviewStore.getState().pollingIntervalId).toBeNull();
    });

    it("does not start duplicate polling intervals", () => {
      useReviewStore.getState().startPolling(1);
      const firstId = useReviewStore.getState().pollingIntervalId;

      useReviewStore.getState().startPolling(1);
      const secondId = useReviewStore.getState().pollingIntervalId;

      expect(firstId).toBe(secondId);
    });

    it("stopPolling clears the interval", () => {
      useReviewStore.getState().startPolling(1);
      expect(useReviewStore.getState().pollingIntervalId).not.toBeNull();

      useReviewStore.getState().stopPolling();
      expect(useReviewStore.getState().pollingIntervalId).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // reset
  // -------------------------------------------------------------------------

  describe("reset", () => {
    it("resets all state and stops polling", () => {
      useReviewStore.setState({
        sessions: [makeSession()],
        sessionsTotal: 1,
        currentSession: makeSession(),
        actionItems: [makeActionItem()],
        scorecard: makeScorecard(),
        isSubmitting: true,
        submitError: "some error",
      });
      useReviewStore.getState().startPolling(1);

      useReviewStore.getState().reset();

      const state = useReviewStore.getState();
      expect(state.sessions).toEqual([]);
      expect(state.sessionsTotal).toBe(0);
      expect(state.currentSession).toBeNull();
      expect(state.actionItems).toEqual([]);
      expect(state.scorecard).toBeNull();
      expect(state.isSubmitting).toBe(false);
      expect(state.submitError).toBeNull();
      expect(state.pollingIntervalId).toBeNull();
    });
  });
});
