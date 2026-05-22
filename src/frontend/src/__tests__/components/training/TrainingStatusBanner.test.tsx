import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TrainingStatusBanner } from "../../../components/training/TrainingStatusBanner";
import { useTrainingStore } from "../../../stores/trainingStore";
import { useAuthStore } from "../../../stores/authStore";
import type { TrainingTask } from "../../../components/training/types";

/**
 * Unit tests for TrainingStatusBanner component.
 *
 * Validates: Requirements 10.1–10.6
 */

// ---------------------------------------------------------------------------
// Mock stores
// ---------------------------------------------------------------------------

vi.mock("../../../stores/trainingStore", () => ({
  useTrainingStore: vi.fn(),
}));

vi.mock("../../../stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockedUseTrainingStore = useTrainingStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

const completedTask: TrainingTask = {
  id: 1,
  sop_document_uuid: "sop-abc-123",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Chemical Handling Training",
  is_completed: true,
  completed_at: "2024-03-15T10:30:00Z",
  created_at: "2024-01-01T08:00:00Z",
};

const pendingTask: TrainingTask = {
  id: 2,
  sop_document_uuid: "sop-abc-123",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Chemical Handling Training",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-01T08:00:00Z",
};

function createMockTrainingStore(overrides: Record<string, unknown> = {}) {
  return {
    tasks: [] as TrainingTask[],
    isLoadingTasks: false,
    tasksError: null,
    hasFetchedTasks: true,
    fetchTrainingTasks: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingStatusBanner", () => {
  beforeEach(() => {
    mockedUseAuthStore.mockImplementation((selector: (state: unknown) => unknown) => {
      const state = { user: { id: 42, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["user"] } };
      return selector(state);
    });
    mockedUseTrainingStore.mockReturnValue(createMockTrainingStore());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Hidden for non-InTraining documents (Requirement 10.4)
  // -------------------------------------------------------------------------

  describe("hidden for non-InTraining documents", () => {
    it("renders nothing when sopStatus is 'Active'", () => {
      const { container } = renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="Active"
          sopName="Chemical Handling SOP"
        />
      );

      expect(container.innerHTML).toBe("");
    });

    it("renders nothing when sopStatus is 'Draft'", () => {
      const { container } = renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="Draft"
          sopName="Chemical Handling SOP"
        />
      );

      expect(container.innerHTML).toBe("");
    });

    it("renders nothing when sopStatus is empty string", () => {
      const { container } = renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus=""
          sopName="Chemical Handling SOP"
        />
      );

      expect(container.innerHTML).toBe("");
    });
  });

  // -------------------------------------------------------------------------
  // Training pending - amber banner (Requirement 10.2)
  // -------------------------------------------------------------------------

  describe("pending training state", () => {
    it("shows amber/warning banner when training is pending", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasks: [pendingTask],
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      expect(
        screen.getByText(/Training required: You have not completed training for Chemical Handling SOP v1.0/)
      ).toBeDefined();
      expect(screen.getByText(/Complete training to gain full access/)).toBeDefined();
    });

    it("includes 'View Training' link to /training", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasks: [pendingTask],
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      const link = screen.getByRole("link", { name: /view training/i });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toBe("/training");
    });

    it("uses sopDocumentUuid as display name when sopName is not provided", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasks: [pendingTask],
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        />
      );

      expect(
        screen.getByText(/Training required: You have not completed training for sop-abc-123 v1.0/)
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Training complete - green banner (Requirement 10.3)
  // -------------------------------------------------------------------------

  describe("completed training state", () => {
    it("shows green/success banner when training is complete", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasks: [completedTask],
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      expect(
        screen.getByText(/Training complete: You have completed training for Chemical Handling SOP v1.0/)
      ).toBeDefined();
    });

    it("shows completion date in the banner", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasks: [completedTask],
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      // The completion date should be formatted and displayed
      expect(screen.getByText(/Completed on/)).toBeDefined();
    });

    it("includes 'View Training' link in completed state", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasks: [completedTask],
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      const link = screen.getByRole("link", { name: /view training/i });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toBe("/training");
    });
  });

  // -------------------------------------------------------------------------
  // Loading state (Requirement 10.5)
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("shows skeleton when isLoadingTasks is true", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          isLoadingTasks: true,
          hasFetchedTasks: false,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      expect(screen.getByLabelText("Loading training status")).toBeDefined();
    });

    it("shows skeleton when hasFetchedTasks is false", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          isLoadingTasks: false,
          hasFetchedTasks: false,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      expect(screen.getByLabelText("Loading training status")).toBeDefined();
    });

    it("triggers fetchTrainingTasks when tasks not yet loaded", () => {
      const fetchTrainingTasks = vi.fn().mockResolvedValue(undefined);
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: false,
          fetchTrainingTasks,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      expect(fetchTrainingTasks).toHaveBeenCalledWith(42);
    });
  });

  // -------------------------------------------------------------------------
  // Error state (Requirement 10.6)
  // -------------------------------------------------------------------------

  describe("error state", () => {
    it("shows error message with role='alert' when tasksError is set", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasksError: "Network error: Unable to reach the server.",
          hasFetchedTasks: true,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(screen.getByText("Unable to load training status")).toBeDefined();
    });

    it("shows retry button that re-invokes fetchTrainingTasks", () => {
      const fetchTrainingTasks = vi.fn().mockResolvedValue(undefined);
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          tasksError: "Server error",
          hasFetchedTasks: true,
          fetchTrainingTasks,
        })
      );

      renderWithRouter(
        <TrainingStatusBanner
          sopDocumentUuid="sop-abc-123"
          sopVersion="1.0"
          sopStatus="InTraining"
          sopName="Chemical Handling SOP"
        />
      );

      const retryButton = screen.getByRole("button", { name: /retry/i });
      expect(retryButton).toBeDefined();
      fireEvent.click(retryButton);

      expect(fetchTrainingTasks).toHaveBeenCalledWith(42);
    });
  });
});
