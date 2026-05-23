import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, act, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Integration tests for TrainingPage.
 *
 * Validates: Requirements 1.1–1.5, 2.1–2.7, 4.11
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock apiClient (already used by trainingStore)
vi.mock("../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    url: string;
    constructor(status: number, body: string, url: string = "/api/training") {
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

// Mock authStore — default to admin user
const mockAuthState = {
  user: {
    id: 42,
    username: "testuser",
    email: "test@example.com",
    full_name: "Test User",
    roles: ["admin"],
  },
  isAuthenticated: true,
  activeCompanyId: 1,
  activeCompanySlug: "test-company",
};

vi.mock("../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: typeof mockAuthState) => unknown) => {
      if (selector) return selector(mockAuthState);
      return mockAuthState;
    }),
    {
      getState: () => mockAuthState,
    }
  ),
}));

// Import after mocks
import { apiClient } from "../../lib/apiClient";
import { useTrainingStore } from "../../stores/trainingStore";
import { TrainingPage } from "../../pages/TrainingPage";
import type { TrainingTask, TrainingContent } from "../../components/training/types";

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const pendingTask: TrainingTask = {
  id: 1,
  sop_document_uuid: "sop-abc-123",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Chemical Handling Safety Training",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-10T08:00:00Z",
};

const completedTask: TrainingTask = {
  id: 2,
  sop_document_uuid: "sop-def-456",
  sop_version: "2.0",
  assigned_user_id: 42,
  task_title: "Lab Equipment Maintenance",
  is_completed: true,
  completed_at: "2024-02-20T14:30:00Z",
  created_at: "2024-01-05T09:00:00Z",
};

const mockContent: TrainingContent = {
  content_id: "sop-abc-123_v1.0",
  sop_document_uuid: "sop-abc-123",
  sop_version: "1.0",
  summary: "This training covers chemical handling safety procedures.",
  quiz_questions: [
    {
      question_id: "q1",
      question: "What is the first step in chemical handling?",
      correct_answer: "Read the SDS",
      distractors: ["Pour it out", "Smell it"],
      sop_section_ref: "Section 2.1",
    },
  ],
  procedural_steps: [
    {
      step_number: 1,
      description: "Read the Safety Data Sheet",
      is_safety_critical: true,
      safety_note: "Always read SDS before handling any chemical",
    },
  ],
  safety_points: ["Always wear PPE when handling chemicals"],
  status: "approved",
  generated_at: "2024-01-01T00:00:00Z",
  reviewed_by: 10,
  reviewed_at: "2024-01-02T00:00:00Z",
  review_notes: "Approved",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useTrainingStore.setState({
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
    gateCache: {},
    isCheckingGate: false,
    currentQuizAttempt: null,
    isSubmittingQuiz: false,
    quizSubmitError: null,
    quizResults: null,
    isLoadingQuizResults: false,
    quizResultsError: null,
    quizPassCache: {},
    isCheckingQuizPass: false,
    quizPassError: null,
  });
}

function setStoreWithTasks(tasks: TrainingTask[]) {
  const pending = tasks.filter((t) => !t.is_completed).length;
  const completed = tasks.filter((t) => t.is_completed).length;
  const total = tasks.length;
  useTrainingStore.setState({
    tasks,
    isLoadingTasks: false,
    tasksError: null,
    hasFetchedTasks: true,
    statistics: {
      pending,
      completed,
      total,
      completionPercentage: total > 0 ? Math.round((completed / total) * 100) : null,
    },
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingPage Integration", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    // Default: API calls resolve with test data
    mockedGet.mockImplementation((url: string) => {
      if (url.includes("/api/training/tasks")) {
        return Promise.resolve([pendingTask, completedTask]);
      }
      if (url.includes("/api/training/content/")) {
        return Promise.resolve(mockContent);
      }
      if (url.includes("/api/training/quiz/passed/")) {
        return Promise.resolve({
          content_id: "sop-abc-123_v1.0",
          user_id: 42,
          has_passed: true,
          best_score: 1,
        });
      }
      return Promise.resolve([]);
    });
  });

  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Page render
  // -------------------------------------------------------------------------

  describe("Page render", () => {
    it("renders with role='main' and aria-label='Training Management'", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const main = screen.getByRole("main");
      expect(main).toBeDefined();
      expect(main.getAttribute("aria-label")).toBe("Training Management");
    });

    it("displays Training Dashboard heading", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      expect(screen.getByText("Training Dashboard")).toBeDefined();
    });

    it("shows loading state with aria-live announcement", () => {
      useTrainingStore.setState({ isLoadingTasks: true });

      render(<TrainingPage />);

      // aria-live region should announce loading
      const liveRegion = screen.getByText("Loading training tasks...");
      expect(liveRegion).toBeDefined();
      expect(liveRegion.closest("[aria-live]")?.getAttribute("aria-live")).toBe("polite");
    });

    it("fetches training tasks on mount", async () => {
      render(<TrainingPage />);

      await waitFor(() => {
        expect(mockedGet).toHaveBeenCalledWith(
          "/api/training/tasks?user_id=42"
        );
      });
    });
  });

  // -------------------------------------------------------------------------
  // Tab navigation
  // -------------------------------------------------------------------------

  describe("Tab navigation", () => {
    it("renders tab navigation with My Tasks, Records, and Admin tabs for admin user", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const tablist = screen.getByRole("tablist", { name: "Training sections" });
      expect(tablist).toBeDefined();

      const tabs = screen.getAllByRole("tab");
      expect(tabs.length).toBe(3);
      expect(tabs[0].textContent).toBe("My Tasks");
      expect(tabs[1].textContent).toBe("Records");
      expect(tabs[2].textContent).toBe("Admin: SOP Training Status");
    });

    it("hides Admin tab when user does not have admin role", () => {
      // Override auth mock to non-admin
      const originalRoles = mockAuthState.user.roles;
      mockAuthState.user.roles = ["user"];

      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const tabs = screen.getAllByRole("tab");
      expect(tabs.length).toBe(2);
      expect(tabs[0].textContent).toBe("My Tasks");
      expect(tabs[1].textContent).toBe("Records");

      // Restore admin role for other tests
      mockAuthState.user.roles = originalRoles;
    });

    it("My Tasks tab is selected by default", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const myTasksTab = screen.getByRole("tab", { name: "My Tasks" });
      expect(myTasksTab.getAttribute("aria-selected")).toBe("true");
    });

    it("clicking Records tab shows records panel", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const recordsTab = screen.getByRole("tab", { name: "Records" });
      fireEvent.click(recordsTab);

      expect(recordsTab.getAttribute("aria-selected")).toBe("true");

      // The tabpanel should now be labeled by the records tab
      const tabpanel = screen.getByRole("tabpanel");
      expect(tabpanel.getAttribute("aria-labelledby")).toBe("tab-records");
    });

    it("clicking My Tasks tab shows task list after switching away", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      // Switch to Records first
      const recordsTab = screen.getByRole("tab", { name: "Records" });
      fireEvent.click(recordsTab);

      // Switch back to My Tasks
      const myTasksTab = screen.getByRole("tab", { name: "My Tasks" });
      fireEvent.click(myTasksTab);

      expect(myTasksTab.getAttribute("aria-selected")).toBe("true");

      const tabpanel = screen.getByRole("tabpanel");
      expect(tabpanel.getAttribute("aria-labelledby")).toBe("tab-tasks");
    });

    it("clicking Admin tab shows admin view", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const adminTab = screen.getByRole("tab", { name: "Admin: SOP Training Status" });
      fireEvent.click(adminTab);

      expect(adminTab.getAttribute("aria-selected")).toBe("true");

      const tabpanel = screen.getByRole("tabpanel");
      expect(tabpanel.getAttribute("aria-labelledby")).toBe("tab-admin");
    });

    it("tab panels have correct aria-controls linking", () => {
      setStoreWithTasks([pendingTask, completedTask]);

      render(<TrainingPage />);

      const tabs = screen.getAllByRole("tab");
      // Each tab should have aria-controls pointing to its panel
      expect(tabs[0].getAttribute("aria-controls")).toBe("tabpanel-tasks");
      expect(tabs[1].getAttribute("aria-controls")).toBe("tabpanel-records");
      expect(tabs[2].getAttribute("aria-controls")).toBe("tabpanel-admin");
    });
  });

  // -------------------------------------------------------------------------
  // Task selection → content viewer flow
  // -------------------------------------------------------------------------

  describe("Task selection and content viewer", () => {
    it("clicking a task card triggers content fetch", async () => {
      setStoreWithTasks([pendingTask, completedTask]);

      await act(async () => {
        render(<TrainingPage />);
      });

      // Wait for tasks to render after the fetch resolves
      await waitFor(() => {
        expect(screen.getByRole("article", {
          name: "Chemical Handling Safety Training - Pending",
        })).toBeDefined();
      });

      const taskCard = screen.getByRole("article", {
        name: "Chemical Handling Safety Training - Pending",
      });
      fireEvent.click(taskCard);

      await waitFor(() => {
        expect(mockedGet).toHaveBeenCalledWith(
          "/api/training/content/sop-abc-123_v1.0"
        );
      });
    });

    it("shows Training Content heading after task selection", async () => {
      setStoreWithTasks([pendingTask, completedTask]);
      useTrainingStore.setState({ currentContent: mockContent });

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByRole("article", {
          name: "Chemical Handling Safety Training - Pending",
        })).toBeDefined();
      });

      const taskCard = screen.getByRole("article", {
        name: "Chemical Handling Safety Training - Pending",
      });
      fireEvent.click(taskCard);

      expect(screen.getByText("Training Content")).toBeDefined();
    });

    it("shows placeholder message when no task is selected and tasks exist", async () => {
      setStoreWithTasks([pendingTask, completedTask]);

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(
          screen.getByText("Select a training task to view its content, quiz, and key points")
        ).toBeDefined();
      });
    });

    it("fetches content with correct content_id derived from task", async () => {
      setStoreWithTasks([pendingTask, completedTask]);

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByRole("article", {
          name: "Lab Equipment Maintenance - Completed",
        })).toBeDefined();
      });

      const taskCard = screen.getByRole("article", {
        name: "Lab Equipment Maintenance - Completed",
      });
      fireEvent.click(taskCard);

      await waitFor(() => {
        expect(mockedGet).toHaveBeenCalledWith(
          "/api/training/content/sop-def-456_v2.0"
        );
      });
    });
  });

  // -------------------------------------------------------------------------
  // Task completion flow
  // -------------------------------------------------------------------------

  describe("Task completion flow", () => {
    it("clicking Mark Complete opens the completion dialog", async () => {
      setStoreWithTasks([pendingTask, completedTask]);
      // Set quiz pass cache so Mark Complete button is enabled
      useTrainingStore.setState({
        quizPassCache: {
          "sop-abc-123_v1.0": {
            content_id: "sop-abc-123_v1.0",
            user_id: 42,
            has_passed: true,
            best_score: 1,
          },
        },
      });

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /mark complete/i })).toBeDefined();
      });

      const markCompleteButton = screen.getByRole("button", { name: /mark complete/i });
      fireEvent.click(markCompleteButton);

      // Dialog should appear
      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeDefined();
    });

    it("confirming completion calls completeTrainingTask with correct params", async () => {
      setStoreWithTasks([pendingTask, completedTask]);
      useTrainingStore.setState({
        quizPassCache: {
          "sop-abc-123_v1.0": {
            content_id: "sop-abc-123_v1.0",
            user_id: 42,
            has_passed: true,
            best_score: 1,
          },
        },
      });

      mockedPost.mockResolvedValueOnce({
        id: 1,
        is_completed: true,
        completed_at: "2024-03-01T10:00:00Z",
      });

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /mark complete/i })).toBeDefined();
      });

      // Open dialog
      const markCompleteButton = screen.getByRole("button", { name: /mark complete/i });
      fireEvent.click(markCompleteButton);

      // Enter change reason
      const input = screen.getByRole("textbox");
      fireEvent.change(input, { target: { value: "Training completed successfully" } });

      // Click confirm
      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      await act(async () => {
        fireEvent.click(confirmButton);
      });

      await waitFor(() => {
        expect(mockedPost).toHaveBeenCalledWith(
          "/api/training/tasks/1/complete?user_id=42",
          undefined,
          { changeReason: "Training completed successfully" }
        );
      });
    });

    it("closing dialog via cancel does not trigger completion", async () => {
      setStoreWithTasks([pendingTask, completedTask]);
      useTrainingStore.setState({
        quizPassCache: {
          "sop-abc-123_v1.0": {
            content_id: "sop-abc-123_v1.0",
            user_id: 42,
            has_passed: true,
            best_score: 1,
          },
        },
      });

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /mark complete/i })).toBeDefined();
      });

      // Open dialog
      const markCompleteButton = screen.getByRole("button", { name: /mark complete/i });
      fireEvent.click(markCompleteButton);

      // Close dialog via cancel button
      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      fireEvent.click(cancelButton);

      // Dialog should be gone
      expect(screen.queryByRole("dialog")).toBeNull();
      // No POST call
      expect(mockedPost).not.toHaveBeenCalled();
    });

    it("dialog closes after successful completion", async () => {
      setStoreWithTasks([pendingTask, completedTask]);
      useTrainingStore.setState({
        quizPassCache: {
          "sop-abc-123_v1.0": {
            content_id: "sop-abc-123_v1.0",
            user_id: 42,
            has_passed: true,
            best_score: 1,
          },
        },
      });

      mockedPost.mockResolvedValueOnce({
        id: 1,
        is_completed: true,
        completed_at: "2024-03-01T10:00:00Z",
      });

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /mark complete/i })).toBeDefined();
      });

      // Open dialog
      const markCompleteButton = screen.getByRole("button", { name: /mark complete/i });
      fireEvent.click(markCompleteButton);

      // Enter change reason and confirm
      const input = screen.getByRole("textbox");
      fireEvent.change(input, { target: { value: "Completed training review" } });

      const confirmButton = screen.getByRole("button", { name: /confirm/i });
      await act(async () => {
        fireEvent.click(confirmButton);
      });

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).toBeNull();
      });
    });
  });

  // -------------------------------------------------------------------------
  // Statistics display
  // -------------------------------------------------------------------------

  describe("Statistics display", () => {
    it("displays N/A percentage when no tasks", async () => {
      // Override mock to return empty tasks for this test
      mockedGet.mockImplementation((url: string) => {
        if (url.includes("/api/training/tasks")) {
          return Promise.resolve([]);
        }
        return Promise.resolve([]);
      });

      setStoreWithTasks([]);

      await act(async () => {
        render(<TrainingPage />);
      });

      await waitFor(() => {
        expect(screen.getByText("N/A")).toBeDefined();
      });
    });

    it("displays completion percentage when tasks exist", async () => {
      setStoreWithTasks([pendingTask, completedTask]);

      await act(async () => {
        render(<TrainingPage />);
      });

      // 1 completed out of 2 = 50%
      await waitFor(() => {
        expect(screen.getByText("50%")).toBeDefined();
      });
    });
  });
});
