import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingTaskCard } from "../../../components/training/TrainingTaskCard";
import type { TrainingTask } from "../../../components/training/types";

/**
 * Unit tests for TrainingTaskCard component.
 *
 * Validates: Requirements 2.1, 2.6, 2.7, 11.3
 */

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

describe("TrainingTaskCard", () => {
  afterEach(() => {
    cleanup();
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

  it("shows 'Mark Complete' button for pending tasks", () => {
    const onMarkComplete = vi.fn();
    render(<TrainingTaskCard task={pendingTask} onMarkComplete={onMarkComplete} />);

    const button = screen.getByRole("button", { name: /mark complete/i });
    expect(button).toBeDefined();
  });

  it("calls onMarkComplete with the task when 'Mark Complete' is clicked", () => {
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
});
