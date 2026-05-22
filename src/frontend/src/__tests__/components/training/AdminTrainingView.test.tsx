import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { AdminTrainingView } from "../../../components/training/AdminTrainingView";
import type {
  TrainingTask,
  TrainingStatus,
  TrainingContent,
} from "../../../components/training/types";
import { useTrainingStore } from "../../../stores/trainingStore";

/**
 * Unit tests for AdminTrainingView component.
 *
 * Validates: Requirements 6.1–6.9, 7.1–7.9
 */

// ---------------------------------------------------------------------------
// Mock the training store
// ---------------------------------------------------------------------------

vi.mock("../../../stores/trainingStore", () => ({
  useTrainingStore: vi.fn(),
}));

const mockedUseTrainingStore = useTrainingStore as unknown as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Test Fixtures
// ---------------------------------------------------------------------------

const taskA1: TrainingTask = {
  id: 1,
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  assigned_user_id: 10,
  task_title: "Training for Chemical Handling",
  is_completed: true,
  completed_at: "2024-02-15T10:00:00Z",
  created_at: "2024-01-01T08:00:00Z",
};

const taskA2: TrainingTask = {
  id: 2,
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  assigned_user_id: 20,
  task_title: "Training for Chemical Handling",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-02T08:00:00Z",
};

const taskB1: TrainingTask = {
  id: 3,
  sop_document_uuid: "sop-bbb-222",
  sop_version: "2.0",
  assigned_user_id: 10,
  task_title: "Training for Lab Safety",
  is_completed: true,
  completed_at: "2024-03-10T14:00:00Z",
  created_at: "2024-02-01T08:00:00Z",
};

const allTasks: TrainingTask[] = [taskA1, taskA2, taskB1];

const statusComplete: TrainingStatus = {
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  total_tasks: 5,
  completed_tasks: 5,
  is_complete: true,
};

const statusPartial: TrainingStatus = {
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  total_tasks: 10,
  completed_tasks: 6,
  is_complete: false,
};

const statusEmpty: TrainingStatus = {
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  total_tasks: 0,
  completed_tasks: 0,
  is_complete: false,
};

const pendingReviewItem: TrainingContent = {
  content_id: "sop-aaa-111_v1.0",
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  summary: "Chemical handling training content",
  quiz_questions: [],
  procedural_steps: [],
  safety_points: [],
  status: "pending_review",
  generated_at: "2024-01-15T10:00:00Z",
  reviewed_by: null,
  reviewed_at: null,
  review_notes: "",
};

// ---------------------------------------------------------------------------
// Default mock store state
// ---------------------------------------------------------------------------

function createMockStoreState(overrides: Record<string, unknown> = {}) {
  return {
    sopStatus: null,
    isLoadingStatus: false,
    statusError: null,
    fetchTrainingStatus: vi.fn(),
    pendingReviewItems: [],
    isReviewing: false,
    reviewError: null,
    approveContent: vi.fn().mockResolvedValue(true),
    rejectContent: vi.fn().mockResolvedValue(true),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AdminTrainingView", () => {
  beforeEach(() => {
    mockedUseTrainingStore.mockReturnValue(createMockStoreState());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Admin-only visibility (Requirement 6.1)
  // -------------------------------------------------------------------------

  describe("admin-only visibility", () => {
    it("renders nothing when isAdmin is false", () => {
      const { container } = render(
        <AdminTrainingView tasks={allTasks} isAdmin={false} />
      );

      expect(container.innerHTML).toBe("");
    });

    it("renders content when isAdmin is true", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Should render the SOP selector
      expect(screen.getByLabelText("Select SOP:")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // SOP selector population and selection (Requirement 6.7)
  // -------------------------------------------------------------------------

  describe("SOP selector", () => {
    it("populates SOP selector with unique SOP pairs from tasks", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      const selector = screen.getByLabelText("Select SOP:") as HTMLSelectElement;
      expect(selector).toBeDefined();

      // Should have 2 unique SOP pairs: sop-aaa-111 v1.0 and sop-bbb-222 v2.0
      const options = selector.querySelectorAll("option");
      expect(options.length).toBe(2);
      expect(options[0].textContent).toContain("sop-aaa-111");
      expect(options[0].textContent).toContain("v1.0");
      expect(options[1].textContent).toContain("sop-bbb-222");
      expect(options[1].textContent).toContain("v2.0");
    });

    it("fetches training status for the first SOP pair on mount", () => {
      const fetchTrainingStatus = vi.fn();
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ fetchTrainingStatus })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(fetchTrainingStatus).toHaveBeenCalledWith("sop-aaa-111", "1.0");
    });

    it("fetches training status when SOP selection changes", () => {
      const fetchTrainingStatus = vi.fn();
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ fetchTrainingStatus, sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      const selector = screen.getByLabelText("Select SOP:") as HTMLSelectElement;
      fireEvent.change(selector, { target: { value: "1" } });

      // Should fetch for the second SOP pair
      expect(fetchTrainingStatus).toHaveBeenCalledWith("sop-bbb-222", "2.0");
    });

    it("shows empty state when tasks array is empty", () => {
      render(<AdminTrainingView tasks={[]} isAdmin={true} />);

      expect(
        screen.getByText("No SOP training data available.")
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Progress bar and status display (Requirements 6.2, 6.4)
  // -------------------------------------------------------------------------

  describe("progress bar and status display", () => {
    it("displays progress bar with correct percentage", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // 6 out of 10 = 60%
      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toBeDefined();
      expect(progressbar.getAttribute("aria-valuenow")).toBe("60");
      expect(progressbar.getAttribute("aria-valuemin")).toBe("0");
      expect(progressbar.getAttribute("aria-valuemax")).toBe("100");
    });

    it("displays percentage text", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.getByText("60%")).toBeDefined();
    });

    it("displays stats summary with total, completed, and pending counts", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // "10" appears in both stats (total_tasks) and user table (user_id), use getAllByText
      expect(screen.getAllByText("10").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("6")).toBeDefined(); // completed
      expect(screen.getByText("4")).toBeDefined(); // pending (10 - 6)
      expect(screen.getByText("Total Tasks")).toBeDefined();
      // "Completed" and "Pending" appear in both stats labels and user table badges
      expect(screen.getAllByText("Completed").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Pending").length).toBeGreaterThanOrEqual(1);
    });

    it("displays 100% progress when all tasks are complete", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusComplete })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar.getAttribute("aria-valuenow")).toBe("100");
      expect(screen.getByText("100%")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Training Complete badge (Requirement 6.5)
  // -------------------------------------------------------------------------

  describe("Training Complete badge", () => {
    it("shows 'Training Complete' badge when is_complete is true", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusComplete })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.getByText("Training Complete")).toBeDefined();
    });

    it("does not show 'Training Complete' badge when is_complete is false", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.queryByText("Training Complete")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // User breakdown table (Requirement 6.3)
  // -------------------------------------------------------------------------

  describe("user breakdown table", () => {
    it("renders user breakdown table with correct data", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Table headers
      expect(screen.getByText("User ID")).toBeDefined();
      expect(screen.getByText("Status")).toBeDefined();
      expect(screen.getByText("Completed At")).toBeDefined();

      // User IDs for tasks matching the first SOP pair (sop-aaa-111, v1.0)
      // "10" appears in both stats (total_tasks) and table (user_id), use getAllByText
      expect(screen.getAllByText("10").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("20")).toBeDefined();
    });

    it("shows 'Completed' badge for completed users", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // taskA1 is completed, taskA2 is pending
      const completedBadges = screen.getAllByText("Completed");
      const pendingBadges = screen.getAllByText("Pending");
      expect(completedBadges.length).toBeGreaterThanOrEqual(1);
      expect(pendingBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("shows completion date for completed users and dash for pending", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Pending user should show "—"
      expect(screen.getByText("—")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Empty state (Requirement 6.9)
  // -------------------------------------------------------------------------

  describe("empty state", () => {
    it("shows empty state when total_tasks is 0", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusEmpty })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(
        screen.getByText(
          "No training tasks have been assigned for the selected SOP version."
        )
      ).toBeDefined();
    });

    it("does not show progress bar or table when total_tasks is 0", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ sopStatus: statusEmpty })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.queryByRole("progressbar")).toBeNull();
      expect(screen.queryByText("User Breakdown")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Loading state (Requirement 6.8)
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("shows loading skeleton when isLoadingStatus is true", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ isLoadingStatus: true })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      const skeleton = screen.getByLabelText("Loading training status");
      expect(skeleton).toBeDefined();
      expect(skeleton.getAttribute("aria-busy")).toBe("true");
    });

    it("does not show status content while loading", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ isLoadingStatus: true, sopStatus: statusPartial })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.queryByRole("progressbar")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Error state (Requirement 6.6)
  // -------------------------------------------------------------------------

  describe("error state", () => {
    it("shows error message with role='alert' when statusError is set", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({
          statusError: "Server error: Something went wrong.",
        })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(
        screen.getByText("Server error: Something went wrong.")
      ).toBeDefined();
    });

    it("shows retry button that re-invokes fetchTrainingStatus", () => {
      const fetchTrainingStatus = vi.fn();
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({
          statusError: "Network error",
          fetchTrainingStatus,
        })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      const retryButton = screen.getByRole("button", {
        name: /retry loading/i,
      });
      expect(retryButton).toBeDefined();
      fireEvent.click(retryButton);

      // Should re-fetch for the currently selected SOP
      expect(fetchTrainingStatus).toHaveBeenCalledWith("sop-aaa-111", "1.0");
    });

    it("does not show error when isLoadingStatus is true", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({
          statusError: "Some error",
          isLoadingStatus: true,
        })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Content review section (Requirements 7.1–7.9)
  // -------------------------------------------------------------------------

  describe("content review section", () => {
    it("renders Content Review heading", () => {
      mockedUseTrainingStore.mockReturnValue(createMockStoreState());

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(screen.getByText("Content Review")).toBeDefined();
    });

    it("shows empty state when no pending review items", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ pendingReviewItems: [] })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(
        screen.getByText("No content items are awaiting review.")
      ).toBeDefined();
    });

    it("shows pending review items as clickable buttons", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ pendingReviewItems: [pendingReviewItem] })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Should show the SOP UUID and version for the pending item
      expect(screen.getByText("sop-aaa-111 v1.0")).toBeDefined();
    });

    it("shows content viewer with approve/reject when item is selected", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ pendingReviewItems: [pendingReviewItem] })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Click on the pending review item
      const itemButton = screen.getByText("sop-aaa-111 v1.0");
      fireEvent.click(itemButton);

      // Should show approve and reject buttons (from TrainingContentViewer in review mode)
      expect(
        screen.getByRole("button", { name: /approve/i })
      ).toBeDefined();
      expect(
        screen.getByRole("button", { name: /reject/i })
      ).toBeDefined();
    });

    it("shows back button when item is selected", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ pendingReviewItems: [pendingReviewItem] })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Click on the pending review item
      fireEvent.click(screen.getByText("sop-aaa-111 v1.0"));

      // Should show back button
      expect(screen.getByText("← Back to review queue")).toBeDefined();
    });

    it("returns to review queue when back button is clicked", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({ pendingReviewItems: [pendingReviewItem] })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Select item
      fireEvent.click(screen.getByText("sop-aaa-111 v1.0"));

      // Click back
      fireEvent.click(screen.getByText("← Back to review queue"));

      // Should show the item list again
      expect(screen.getByText("sop-aaa-111 v1.0")).toBeDefined();
      expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    });

    it("shows review error when reviewError is set", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({
          pendingReviewItems: [pendingReviewItem],
          reviewError: "Content not in reviewable state",
        })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      expect(
        screen.getByText("Content not in reviewable state")
      ).toBeDefined();
    });

    it("disables approve/reject buttons when isReviewing is true", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockStoreState({
          pendingReviewItems: [pendingReviewItem],
          isReviewing: true,
        })
      );

      render(<AdminTrainingView tasks={allTasks} isAdmin={true} />);

      // Select item
      fireEvent.click(screen.getByText("sop-aaa-111 v1.0"));

      // When isReviewing is true, onApprove/onReject are set to undefined
      // so the buttons should not be rendered
      expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
    });
  });
});
