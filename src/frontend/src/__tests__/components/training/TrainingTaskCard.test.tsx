import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingTaskCard } from "../../../components/training/TrainingTaskCard";
import type { TrainingTask } from "../../../components/training/types";
import { useTrainingStore } from "../../../stores/trainingStore";
import { useAuthStore } from "../../../stores/authStore";

/**
 * Unit tests for TrainingTaskCard component.
 *
 * Validates: Requirements 2.1, 2.6, 2.7, 8.1, 8.2, 8.4, 8.5, 11.3
 */

vi.mock("../../../stores/trainingStore", () => ({
  useTrainingStore: vi.fn(),
}));

vi.mock("../../../stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockedUseTrainingStore = useTrainingStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

const pendingTask: TrainingTask = {
  id: 1,
  sop_document_uuid: "abc-123-def",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Complete SOP Training for Chemical Handling",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-15T10:00:00Z",
};

const completedTask: TrainingTask = {
  id: 2,
  sop_document_uuid: "xyz-789-ghi",
  sop_version: "2.1",
  assigned_user_id: 42,
  task_title: "Review Safety Procedures for Lab Equipment",
  is_completed: true,
  completed_at: "2024-02-20T14:30:00Z",
  created_at: "2024-01-10T08:00:00Z",
};

// Default mock state: quiz passed for the pending task's content_id
const defaultTrainingStoreState = {
  quizPassCache: {
    "abc-123-def_v1.0": { content_id: "abc-123-def_v1.0", user_id: 42, has_passed: true, best_score: 4 },
  },
  isCheckingQuizPass: false,
  quizPassError: null,
  checkQuizPassed: vi.fn(),
};

describe("TrainingTaskCard", () => {
  beforeEach(() => {
    mockedUseAuthStore.mockImplementation((selector: (state: unknown) => unknown) => {
      const state = { user: { id: 42, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["user"] } };
      return selector(state);
    });
    mockedUseTrainingStore.mockReturnValue(defaultTrainingStoreState);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders with role='article' and correct aria-label for pending task", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const article = screen.getByRole("article");
    expect(article).toBeDefined();
    expect(article.getAttribute("aria-label")).toBe(
      "Complete SOP Training for Chemical Handling - Pending"
    );
  });

  it("renders with correct aria-label for completed task", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={completedTask} onMarkComplete={onMarkComplete} />);

    const article = screen.getByRole("article");
    expect(article.getAttribute("aria-label")).toBe(
      "Review Safety Procedures for Lab Equipment - Completed"
    );
  });

  it("displays task title, SOP UUID, and version", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    expect(screen.getByText("Complete SOP Training for Chemical Handling")).toBeDefined();
    expect(screen.getByText("SOP: abc-123-def")).toBeDefined();
    expect(screen.getByText("Version: 1.0")).toBeDefined();
  });

  it("truncates title at 80 characters with ellipsis", () => {
    const longTitle = "A".repeat(100);
    const longTitleTask: TrainingTask = {
      ...pendingTask,
      task_title: longTitle,
    };
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={longTitleTask} onMarkComplete={onMarkComplete} />);

    const expectedTruncated = "A".repeat(80) + "\u2026";
    expect(screen.getByText(expectedTruncated)).toBeDefined();
  });

  it("shows 'Mark Complete' button for pending tasks when quiz passed", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const button = screen.getByRole("button", { name: /mark complete/i });
    expect(button).toBeDefined();
    expect(button.hasAttribute("disabled")).toBe(false);
  });

  it("calls onMarkComplete with the task when 'Mark Complete' is clicked and quiz passed", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const button = screen.getByRole("button", { name: /mark complete/i });
    fireEvent.click(button);

    expect(onMarkComplete).toHaveBeenCalledTimes(1);
    expect(onMarkComplete).toHaveBeenCalledWith(pendingTask);
  });

  it("shows 'Completed' badge for completed tasks", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={completedTask} onMarkComplete={onMarkComplete} />);

    expect(screen.getByText("Completed")).toBeDefined();
    expect(screen.queryByRole("button", { name: /mark complete/i })).toBeNull();
  });

  it("displays completion timestamp for completed tasks", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={completedTask} onMarkComplete={onMarkComplete} />);

    // The completed_at timestamp should be formatted and displayed
    const completedText = screen.getByText(/Completed:/);
    expect(completedText).toBeDefined();
  });

  it("does not display completion timestamp for pending tasks", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    expect(screen.queryByText(/Completed:/)).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Quiz pass guard tests (Requirements 8.1, 8.2, 8.4, 8.5)
  // -------------------------------------------------------------------------

  it("disables 'Mark Complete' button with tooltip when quiz not passed", () => {
    mockedUseTrainingStore.mockReturnValue({
      ...defaultTrainingStoreState,
      quizPassCache: {
        "abc-123-def_v1.0": { content_id: "abc-123-def_v1.0", user_id: 42, has_passed: false, best_score: 2 },
      },
    });

    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const button = screen.getByRole("button", { name: /mark complete/i });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(button.getAttribute("title")).toBe("Pass the quiz to enable task completion");
  });

  it("enables 'Mark Complete' button when quizPassCache shows true for content_id", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const button = screen.getByRole("button", { name: /mark complete/i });
    expect(button.hasAttribute("disabled")).toBe(false);

    fireEvent.click(button);
    expect(onMarkComplete).toHaveBeenCalledWith(pendingTask);
  });

  it("shows loading spinner while checking quiz pass status", () => {
    mockedUseTrainingStore.mockReturnValue({
      ...defaultTrainingStoreState,
      quizPassCache: {},
      isCheckingQuizPass: true,
    });

    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    expect(screen.getByText("Checking…")).toBeDefined();
    expect(screen.queryByRole("button", { name: /mark complete/i })).toBeNull();
  });

  it("shows error icon with retry button on network failure", () => {
    mockedUseTrainingStore.mockReturnValue({
      ...defaultTrainingStoreState,
      quizPassCache: {},
      isCheckingQuizPass: false,
      quizPassError: "Network error",
    });

    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    expect(screen.getByText("Error")).toBeDefined();
    const retryButton = screen.getByRole("button", { name: /retry quiz pass check/i });
    expect(retryButton).toBeDefined();
  });

  it("calls checkQuizPassed when retry button is clicked", () => {
    const mockCheckQuizPassed = vi.fn();
    mockedUseTrainingStore.mockReturnValue({
      ...defaultTrainingStoreState,
      quizPassCache: {},
      isCheckingQuizPass: false,
      quizPassError: "Network error",
      checkQuizPassed: mockCheckQuizPassed,
    });

    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const retryButton = screen.getByRole("button", { name: /retry quiz pass check/i });
    fireEvent.click(retryButton);

    expect(mockCheckQuizPassed).toHaveBeenCalledWith("abc-123-def_v1.0", 42);
  });

  it("calls checkQuizPassed on mount for pending tasks", () => {
    const mockCheckQuizPassed = vi.fn();
    mockedUseTrainingStore.mockReturnValue({
      ...defaultTrainingStoreState,
      quizPassCache: {},
      checkQuizPassed: mockCheckQuizPassed,
    });

    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    expect(mockCheckQuizPassed).toHaveBeenCalledWith("abc-123-def_v1.0", 42);
  });

  it("does not call checkQuizPassed for completed tasks", () => {
    const mockCheckQuizPassed = vi.fn();
    mockedUseTrainingStore.mockReturnValue({
      ...defaultTrainingStoreState,
      checkQuizPassed: mockCheckQuizPassed,
    });

    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={completedTask} onMarkComplete={onMarkComplete} />);

    expect(mockCheckQuizPassed).not.toHaveBeenCalled();
  });
});
