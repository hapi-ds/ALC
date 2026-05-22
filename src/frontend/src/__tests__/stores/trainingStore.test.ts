import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTrainingStore } from "@/stores/trainingStore";
import type { TrainingTask, TrainingContent, TrainingStatus } from "@/components/training/types";

/**
 * Unit tests for trainingStore actions.
 *
 * Validates: Requirements 9.1–9.10, 12.6
 */

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

import { apiClient, ApiError } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeTask(overrides: Partial<TrainingTask> = {}): TrainingTask {
  return {
    id: 1,
    sop_document_uuid: "SOP-001",
    sop_version: "1.0",
    assigned_user_id: 42,
    task_title: "Complete SOP Training",
    is_completed: false,
    completed_at: null,
    created_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeContent(overrides: Partial<TrainingContent> = {}): TrainingContent {
  return {
    content_id: "SOP-001_v1.0",
    sop_document_uuid: "SOP-001",
    sop_version: "1.0",
    summary: "Training summary content",
    quiz_questions: [],
    procedural_steps: [],
    safety_points: [],
    status: "approved",
    generated_at: "2024-01-01T00:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: "",
    ...overrides,
  };
}

function makeStatus(overrides: Partial<TrainingStatus> = {}): TrainingStatus {
  return {
    sop_document_uuid: "SOP-001",
    sop_version: "1.0",
    total_tasks: 5,
    completed_tasks: 3,
    is_complete: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Initial state for reset
// ---------------------------------------------------------------------------

const initialState = {
  tasks: [],
  isLoadingTasks: false,
  tasksError: null,
  filter: "all" as const,
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
  gateCache: {},
  isCheckingGate: false,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("trainingStore", () => {
  beforeEach(() => {
    useTrainingStore.setState(initialState);
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // fetchTrainingTasks
  // -------------------------------------------------------------------------

  describe("fetchTrainingTasks", () => {
    it("sets isLoadingTasks to true and clears tasksError on start", async () => {
      useTrainingStore.setState({ tasksError: "previous error" });

      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useTrainingStore.getState().fetchTrainingTasks(42);

      await vi.waitFor(() => {
        const state = useTrainingStore.getState();
        expect(state.isLoadingTasks).toBe(true);
        expect(state.tasksError).toBeNull();
      });
    });

    it("stores tasks, computes statistics, and sets hasFetchedTasks on success", async () => {
      const tasks = [
        makeTask({ id: 1, is_completed: false }),
        makeTask({ id: 2, is_completed: true, completed_at: "2024-02-01T00:00:00Z" }),
        makeTask({ id: 3, is_completed: false }),
      ];
      mockedApiClient.get.mockResolvedValue(tasks);

      await useTrainingStore.getState().fetchTrainingTasks(42);

      const state = useTrainingStore.getState();
      expect(state.tasks).toEqual(tasks);
      expect(state.isLoadingTasks).toBe(false);
      expect(state.tasksError).toBeNull();
      expect(state.hasFetchedTasks).toBe(true);
      expect(state.statistics).toEqual({
        pending: 2,
        completed: 1,
        total: 3,
        completionPercentage: 33,
      });
      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/training/tasks?user_id=42");
    });

    it("sets tasksError on ApiError with JSON detail", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(500, JSON.stringify({ detail: "Database connection failed" }), "/api/training/tasks?user_id=42"),
      );

      await useTrainingStore.getState().fetchTrainingTasks(42);

      const state = useTrainingStore.getState();
      expect(state.tasksError).toBe("Database connection failed");
      expect(state.isLoadingTasks).toBe(false);
      expect(state.hasFetchedTasks).toBe(true);
    });

    it("sets tasksError with fallback message on network error", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Failed to fetch"));

      await useTrainingStore.getState().fetchTrainingTasks(42);

      const state = useTrainingStore.getState();
      expect(state.tasksError).toBe("Failed to fetch");
      expect(state.isLoadingTasks).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // completeTrainingTask
  // -------------------------------------------------------------------------

  describe("completeTrainingTask", () => {
    it("updates task, recomputes statistics, and returns true on success", async () => {
      const tasks = [
        makeTask({ id: 1, is_completed: false, sop_document_uuid: "SOP-001", sop_version: "1.0" }),
        makeTask({ id: 2, is_completed: true, completed_at: "2024-02-01T00:00:00Z" }),
      ];
      useTrainingStore.setState({ tasks, statistics: { pending: 1, completed: 1, total: 2, completionPercentage: 50 } });

      mockedApiClient.post.mockResolvedValue({
        id: 1,
        is_completed: true,
        completed_at: "2024-03-01T12:00:00Z",
      });

      const result = await useTrainingStore.getState().completeTrainingTask(1, 42, "Training completed");

      expect(result).toBe(true);
      const state = useTrainingStore.getState();
      expect(state.isCompleting).toBe(false);
      expect(state.completionError).toBeNull();

      // Task should be updated
      const updatedTask = state.tasks.find((t) => t.id === 1);
      expect(updatedTask?.is_completed).toBe(true);
      expect(updatedTask?.completed_at).toBe("2024-03-01T12:00:00Z");

      // Statistics should be recomputed
      expect(state.statistics).toEqual({
        pending: 0,
        completed: 2,
        total: 2,
        completionPercentage: 100,
      });

      // Verify API call with changeReason option
      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/training/tasks/1/complete?user_id=42",
        undefined,
        { changeReason: "Training completed" },
      );
    });

    it("sets completionError and returns false on 400 error", async () => {
      useTrainingStore.setState({ tasks: [makeTask({ id: 1 })] });

      mockedApiClient.post.mockRejectedValue(
        new ApiError(400, JSON.stringify({ detail: "Task already completed" }), "/api/training/tasks/1/complete"),
      );

      const result = await useTrainingStore.getState().completeTrainingTask(1, 42, "reason");

      expect(result).toBe(false);
      const state = useTrainingStore.getState();
      expect(state.completionError).toBe("Task already completed");
      expect(state.isCompleting).toBe(false);
    });

    it("sets completionError and returns false on network error", async () => {
      useTrainingStore.setState({ tasks: [makeTask({ id: 1 })] });

      mockedApiClient.post.mockRejectedValue(new Error("Network error"));

      const result = await useTrainingStore.getState().completeTrainingTask(1, 42, "reason");

      expect(result).toBe(false);
      const state = useTrainingStore.getState();
      expect(state.completionError).toBe("Network error");
      expect(state.isCompleting).toBe(false);
    });

    it("invalidates gate cache for the completed task's SOP", async () => {
      const tasks = [
        makeTask({ id: 1, sop_document_uuid: "SOP-001", sop_version: "1.0" }),
      ];
      useTrainingStore.setState({
        tasks,
        gateCache: { "SOP-001_1.0": false, "SOP-002_2.0": true },
      });

      mockedApiClient.post.mockResolvedValue({
        id: 1,
        is_completed: true,
        completed_at: "2024-03-01T12:00:00Z",
      });

      await useTrainingStore.getState().completeTrainingTask(1, 42, "done");

      const state = useTrainingStore.getState();
      // The cache entry for SOP-001_1.0 should be removed
      expect(state.gateCache).not.toHaveProperty("SOP-001_1.0");
      // Other cache entries should remain
      expect(state.gateCache["SOP-002_2.0"]).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // fetchTrainingContent
  // -------------------------------------------------------------------------

  describe("fetchTrainingContent", () => {
    it("stores content and sets isLoadingContent=false on success", async () => {
      const content = makeContent();
      mockedApiClient.get.mockResolvedValue(content);

      await useTrainingStore.getState().fetchTrainingContent("SOP-001_v1.0");

      const state = useTrainingStore.getState();
      expect(state.currentContent).toEqual(content);
      expect(state.isLoadingContent).toBe(false);
      expect(state.contentError).toBeNull();
      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/training/content/SOP-001_v1.0");
    });

    it("sets contentError on 404 response", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(404, JSON.stringify({ detail: "Content not found" }), "/api/training/content/SOP-001_v1.0"),
      );

      await useTrainingStore.getState().fetchTrainingContent("SOP-001_v1.0");

      const state = useTrainingStore.getState();
      expect(state.contentError).toBe("Content not found");
      expect(state.isLoadingContent).toBe(false);
      expect(state.currentContent).toBeNull();
    });

    it("sets contentError on network error", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network timeout"));

      await useTrainingStore.getState().fetchTrainingContent("SOP-001_v1.0");

      const state = useTrainingStore.getState();
      expect(state.contentError).toBe("Network timeout");
      expect(state.isLoadingContent).toBe(false);
    });

    it("clears previous content when starting a new fetch", async () => {
      useTrainingStore.setState({ currentContent: makeContent(), contentError: "old error" });

      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useTrainingStore.getState().fetchTrainingContent("SOP-002_v2.0");

      await vi.waitFor(() => {
        const state = useTrainingStore.getState();
        expect(state.isLoadingContent).toBe(true);
        expect(state.contentError).toBeNull();
        expect(state.currentContent).toBeNull();
      });
    });
  });

  // -------------------------------------------------------------------------
  // fetchTrainingStatus
  // -------------------------------------------------------------------------

  describe("fetchTrainingStatus", () => {
    it("stores status and sets isLoadingStatus=false on success", async () => {
      const status = makeStatus();
      mockedApiClient.get.mockResolvedValue(status);

      await useTrainingStore.getState().fetchTrainingStatus("SOP-001", "1.0");

      const state = useTrainingStore.getState();
      expect(state.sopStatus).toEqual(status);
      expect(state.isLoadingStatus).toBe(false);
      expect(state.statusError).toBeNull();
      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/training/status/SOP-001/1.0");
    });

    it("sets statusError on failure", async () => {
      mockedApiClient.get.mockRejectedValue(
        new ApiError(500, JSON.stringify({ detail: "Internal server error" }), "/api/training/status/SOP-001/1.0"),
      );

      await useTrainingStore.getState().fetchTrainingStatus("SOP-001", "1.0");

      const state = useTrainingStore.getState();
      expect(state.statusError).toBe("Internal server error");
      expect(state.isLoadingStatus).toBe(false);
      expect(state.sopStatus).toBeNull();
    });

    it("sets isLoadingStatus to true and clears statusError on start", async () => {
      useTrainingStore.setState({ statusError: "old error" });

      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useTrainingStore.getState().fetchTrainingStatus("SOP-001", "1.0");

      await vi.waitFor(() => {
        const state = useTrainingStore.getState();
        expect(state.isLoadingStatus).toBe(true);
        expect(state.statusError).toBeNull();
      });
    });
  });

  // -------------------------------------------------------------------------
  // approveContent
  // -------------------------------------------------------------------------

  describe("approveContent", () => {
    it("removes item from pendingReviewItems and returns true on success", async () => {
      const content1 = makeContent({ content_id: "c1" });
      const content2 = makeContent({ content_id: "c2" });
      useTrainingStore.setState({ pendingReviewItems: [content1, content2] });

      mockedApiClient.post.mockResolvedValue({});

      const result = await useTrainingStore.getState().approveContent("c1", 10, "Looks good");

      expect(result).toBe(true);
      const state = useTrainingStore.getState();
      expect(state.pendingReviewItems).toHaveLength(1);
      expect(state.pendingReviewItems[0].content_id).toBe("c2");
      expect(state.isReviewing).toBe(false);
      expect(state.reviewError).toBeNull();

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/training/content/c1/approve",
        { reviewer_id: 10, notes: "Looks good" },
        { changeReason: "Training content approved" },
      );
    });

    it("sets reviewError and returns false on failure", async () => {
      useTrainingStore.setState({ pendingReviewItems: [makeContent({ content_id: "c1" })] });

      mockedApiClient.post.mockRejectedValue(
        new ApiError(400, JSON.stringify({ detail: "Content not in reviewable state" }), "/api/training/content/c1/approve"),
      );

      const result = await useTrainingStore.getState().approveContent("c1", 10, "notes");

      expect(result).toBe(false);
      const state = useTrainingStore.getState();
      expect(state.reviewError).toBe("Content not in reviewable state");
      expect(state.isReviewing).toBe(false);
    });

    it("sets reviewError on network error", async () => {
      useTrainingStore.setState({ pendingReviewItems: [makeContent({ content_id: "c1" })] });

      mockedApiClient.post.mockRejectedValue(new Error("Connection refused"));

      const result = await useTrainingStore.getState().approveContent("c1", 10, "notes");

      expect(result).toBe(false);
      expect(useTrainingStore.getState().reviewError).toBe("Connection refused");
    });
  });

  // -------------------------------------------------------------------------
  // rejectContent
  // -------------------------------------------------------------------------

  describe("rejectContent", () => {
    it("removes item from pendingReviewItems and returns true on success", async () => {
      const content1 = makeContent({ content_id: "c1" });
      const content2 = makeContent({ content_id: "c2" });
      useTrainingStore.setState({ pendingReviewItems: [content1, content2] });

      mockedApiClient.post.mockResolvedValue({});

      const result = await useTrainingStore.getState().rejectContent("c1", 10, "Needs revision");

      expect(result).toBe(true);
      const state = useTrainingStore.getState();
      expect(state.pendingReviewItems).toHaveLength(1);
      expect(state.pendingReviewItems[0].content_id).toBe("c2");
      expect(state.isReviewing).toBe(false);
      expect(state.reviewError).toBeNull();

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/training/content/c1/reject",
        { reviewer_id: 10, notes: "Needs revision" },
        { changeReason: "Training content rejected" },
      );
    });

    it("sets reviewError and returns false on failure", async () => {
      useTrainingStore.setState({ pendingReviewItems: [makeContent({ content_id: "c1" })] });

      mockedApiClient.post.mockRejectedValue(
        new ApiError(400, JSON.stringify({ detail: "Content not in reviewable state" }), "/api/training/content/c1/reject"),
      );

      const result = await useTrainingStore.getState().rejectContent("c1", 10, "bad content");

      expect(result).toBe(false);
      const state = useTrainingStore.getState();
      expect(state.reviewError).toBe("Content not in reviewable state");
      expect(state.isReviewing).toBe(false);
    });

    it("sets reviewError on network error", async () => {
      useTrainingStore.setState({ pendingReviewItems: [makeContent({ content_id: "c1" })] });

      mockedApiClient.post.mockRejectedValue(new Error("Network failure"));

      const result = await useTrainingStore.getState().rejectContent("c1", 10, "notes");

      expect(result).toBe(false);
      expect(useTrainingStore.getState().reviewError).toBe("Network failure");
    });
  });

  // -------------------------------------------------------------------------
  // Request deduplication (Requirement 12.6)
  // -------------------------------------------------------------------------

  describe("request deduplication", () => {
    it("does not initiate a new fetchTrainingTasks request while isLoadingTasks is true", async () => {
      useTrainingStore.setState({ isLoadingTasks: true });

      await useTrainingStore.getState().fetchTrainingTasks(42);

      expect(mockedApiClient.get).not.toHaveBeenCalled();
    });

    it("does not initiate a new completeTrainingTask request while isCompleting is true", async () => {
      useTrainingStore.setState({ isCompleting: true });

      const result = await useTrainingStore.getState().completeTrainingTask(1, 42, "reason");

      expect(result).toBe(false);
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });

    it("does not initiate a new fetchTrainingContent request while isLoadingContent is true", async () => {
      useTrainingStore.setState({ isLoadingContent: true });

      await useTrainingStore.getState().fetchTrainingContent("SOP-001_v1.0");

      expect(mockedApiClient.get).not.toHaveBeenCalled();
    });

    it("does not initiate a new fetchTrainingStatus request while isLoadingStatus is true", async () => {
      useTrainingStore.setState({ isLoadingStatus: true });

      await useTrainingStore.getState().fetchTrainingStatus("SOP-001", "1.0");

      expect(mockedApiClient.get).not.toHaveBeenCalled();
    });

    it("does not initiate a new approveContent request while isReviewing is true", async () => {
      useTrainingStore.setState({ isReviewing: true });

      const result = await useTrainingStore.getState().approveContent("c1", 10, "notes");

      expect(result).toBe(false);
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });

    it("does not initiate a new rejectContent request while isReviewing is true", async () => {
      useTrainingStore.setState({ isReviewing: true });

      const result = await useTrainingStore.getState().rejectContent("c1", 10, "notes");

      expect(result).toBe(false);
      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Gate cache behavior (Requirements 9.5, 9.4)
  // -------------------------------------------------------------------------

  describe("checkTrainingGate - gate cache behavior", () => {
    it("returns null when tasks have not been fetched yet", () => {
      useTrainingStore.setState({ hasFetchedTasks: false, tasks: [] });

      const result = useTrainingStore.getState().checkTrainingGate("SOP-001", "1.0", 42);

      expect(result).toBeNull();
    });

    it("returns cached value on cache hit without recomputing", () => {
      useTrainingStore.setState({
        hasFetchedTasks: true,
        tasks: [],
        gateCache: { "SOP-001_1.0": true },
      });

      const result = useTrainingStore.getState().checkTrainingGate("SOP-001", "1.0", 42);

      expect(result).toBe(true);
    });

    it("computes and caches result on cache miss - training complete", () => {
      const tasks = [
        makeTask({ id: 1, sop_document_uuid: "SOP-001", sop_version: "1.0", is_completed: true, completed_at: "2024-01-01T00:00:00Z" }),
      ];
      useTrainingStore.setState({ hasFetchedTasks: true, tasks, gateCache: {} });

      const result = useTrainingStore.getState().checkTrainingGate("SOP-001", "1.0", 42);

      expect(result).toBe(true);
      // Should be cached now
      expect(useTrainingStore.getState().gateCache["SOP-001_1.0"]).toBe(true);
    });

    it("computes and caches result on cache miss - training incomplete", () => {
      const tasks = [
        makeTask({ id: 1, sop_document_uuid: "SOP-001", sop_version: "1.0", is_completed: false }),
      ];
      useTrainingStore.setState({ hasFetchedTasks: true, tasks, gateCache: {} });

      const result = useTrainingStore.getState().checkTrainingGate("SOP-001", "1.0", 42);

      expect(result).toBe(false);
      expect(useTrainingStore.getState().gateCache["SOP-001_1.0"]).toBe(false);
    });

    it("returns false when no matching task exists", () => {
      const tasks = [
        makeTask({ id: 1, sop_document_uuid: "SOP-002", sop_version: "2.0", is_completed: true, completed_at: "2024-01-01T00:00:00Z" }),
      ];
      useTrainingStore.setState({ hasFetchedTasks: true, tasks, gateCache: {} });

      const result = useTrainingStore.getState().checkTrainingGate("SOP-001", "1.0", 42);

      expect(result).toBe(false);
    });

    it("clearGateCache resets the cache to empty", () => {
      useTrainingStore.setState({
        gateCache: { "SOP-001_1.0": true, "SOP-002_2.0": false },
      });

      useTrainingStore.getState().clearGateCache();

      expect(useTrainingStore.getState().gateCache).toEqual({});
    });

    it("gate cache is invalidated when completeTrainingTask succeeds", async () => {
      const tasks = [
        makeTask({ id: 1, sop_document_uuid: "SOP-001", sop_version: "1.0", is_completed: false }),
      ];
      useTrainingStore.setState({
        tasks,
        hasFetchedTasks: true,
        gateCache: { "SOP-001_1.0": false },
      });

      mockedApiClient.post.mockResolvedValue({
        id: 1,
        is_completed: true,
        completed_at: "2024-03-01T12:00:00Z",
      });

      await useTrainingStore.getState().completeTrainingTask(1, 42, "done");

      // Cache entry should be removed
      expect(useTrainingStore.getState().gateCache).not.toHaveProperty("SOP-001_1.0");
    });
  });

  // -------------------------------------------------------------------------
  // setFilter
  // -------------------------------------------------------------------------

  describe("setFilter", () => {
    it("updates the filter state", () => {
      useTrainingStore.getState().setFilter("pending");
      expect(useTrainingStore.getState().filter).toBe("pending");

      useTrainingStore.getState().setFilter("completed");
      expect(useTrainingStore.getState().filter).toBe("completed");

      useTrainingStore.getState().setFilter("all");
      expect(useTrainingStore.getState().filter).toBe("all");
    });
  });
});
