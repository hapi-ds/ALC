import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingTaskList } from "../../../components/training/TrainingTaskList";
import type { TrainingTask, TaskFilter } from "../../../components/training/types";

/**
 * Unit tests for TrainingTaskList component.
 *
 * Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 11.2
 */

const pendingTask1: TrainingTask = {
  id: 1,
  sop_document_uuid: "abc-123",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Chemical Handling Training",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-10T08:00:00Z",
};

const pendingTask2: TrainingTask = {
  id: 2,
  sop_document_uuid: "def-456",
  sop_version: "2.0",
  assigned_user_id: 42,
  task_title: "Lab Safety Procedures",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-15T10:00:00Z",
};

const completedTask1: TrainingTask = {
  id: 3,
  sop_document_uuid: "ghi-789",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Equipment Maintenance",
  is_completed: true,
  completed_at: "2024-02-20T14:30:00Z",
  created_at: "2024-01-05T09:00:00Z",
};

const completedTask2: TrainingTask = {
  id: 4,
  sop_document_uuid: "jkl-012",
  sop_version: "3.0",
  assigned_user_id: 42,
  task_title: "Waste Disposal Protocol",
  is_completed: true,
  completed_at: "2024-02-25T16:00:00Z",
  created_at: "2024-01-08T11:00:00Z",
};

const allTasks = [pendingTask1, pendingTask2, completedTask1, completedTask2];

describe("TrainingTaskList", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("renders loading skeleton when isLoading is true", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    const { container } = render(
      <TrainingTaskList
        tasks={[]}
        filter="all"
        isLoading={true}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    // Should show loading skeleton with aria-busy
    const skeleton = container.querySelector('[aria-busy="true"]');
    expect(skeleton).not.toBeNull();
    expect(screen.getByLabelText("Loading training tasks")).toBeDefined();
  });

  it("does not render task cards when loading", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="all"
        isLoading={true}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.queryByText("Chemical Handling Training")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  it("renders error panel with message and retry button", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[]}
        filter="all"
        isLoading={false}
        error="Network error: Unable to reach the server."
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeDefined();
    expect(screen.getByText("Network error: Unable to reach the server.")).toBeDefined();

    const retryButton = screen.getByRole("button", { name: /retry loading/i });
    expect(retryButton).toBeDefined();
  });

  it("calls onRetry when retry button is clicked", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[]}
        filter="all"
        isLoading={false}
        error="Server error"
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const retryButton = screen.getByRole("button", { name: /retry loading/i });
    fireEvent.click(retryButton);

    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("error panel has aria-live='assertive'", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[]}
        filter="all"
        isLoading={false}
        error="Something went wrong"
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert.getAttribute("aria-live")).toBe("assertive");
  });

  // -------------------------------------------------------------------------
  // Empty states
  // -------------------------------------------------------------------------

  it("shows 'No training tasks assigned' when filter is 'all' and no tasks", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[]}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.getByText("No training tasks assigned")).toBeDefined();
  });

  it("shows 'No pending tasks' message when filter is 'pending' and no pending tasks", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[completedTask1]}
        filter="pending"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.getByText(/No pending tasks/)).toBeDefined();
  });

  it("shows 'No completed tasks yet' when filter is 'completed' and no completed tasks", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[pendingTask1]}
        filter="completed"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.getByText("No completed tasks yet")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Populated state
  // -------------------------------------------------------------------------

  it("renders all task cards when filter is 'all'", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.getByText("Chemical Handling Training")).toBeDefined();
    expect(screen.getByText("Lab Safety Procedures")).toBeDefined();
    expect(screen.getByText("Equipment Maintenance")).toBeDefined();
    expect(screen.getByText("Waste Disposal Protocol")).toBeDefined();
  });

  it("renders only pending tasks when filter is 'pending'", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="pending"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.getByText("Chemical Handling Training")).toBeDefined();
    expect(screen.getByText("Lab Safety Procedures")).toBeDefined();
    expect(screen.queryByText("Equipment Maintenance")).toBeNull();
    expect(screen.queryByText("Waste Disposal Protocol")).toBeNull();
  });

  it("renders only completed tasks when filter is 'completed'", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="completed"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    expect(screen.queryByText("Chemical Handling Training")).toBeNull();
    expect(screen.queryByText("Lab Safety Procedures")).toBeNull();
    expect(screen.getByText("Equipment Maintenance")).toBeDefined();
    expect(screen.getByText("Waste Disposal Protocol")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Sort order
  // -------------------------------------------------------------------------

  it("sorts pending tasks before completed tasks (pending by created_at asc)", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const articles = screen.getAllByRole("article");
    // Pending tasks first (created_at ascending): pendingTask1 (Jan 10) then pendingTask2 (Jan 15)
    // Then completed tasks (completed_at descending): completedTask2 (Feb 25) then completedTask1 (Feb 20)
    expect(articles[0].getAttribute("aria-label")).toBe("Chemical Handling Training - Pending");
    expect(articles[1].getAttribute("aria-label")).toBe("Lab Safety Procedures - Pending");
    expect(articles[2].getAttribute("aria-label")).toBe("Waste Disposal Protocol - Completed");
    expect(articles[3].getAttribute("aria-label")).toBe("Equipment Maintenance - Completed");
  });

  // -------------------------------------------------------------------------
  // Filter interactions
  // -------------------------------------------------------------------------

  it("renders filter controls as a radiogroup with correct ARIA", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const radiogroup = screen.getByRole("radiogroup", { name: "Filter training tasks" });
    expect(radiogroup).toBeDefined();

    const radios = screen.getAllByRole("radio");
    expect(radios.length).toBe(3);
  });

  it("marks the active filter as aria-checked='true'", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="pending"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const radios = screen.getAllByRole("radio");
    const allRadio = radios.find((r) => r.textContent === "All");
    const pendingRadio = radios.find((r) => r.textContent === "Pending");
    const completedRadio = radios.find((r) => r.textContent === "Completed");

    expect(allRadio?.getAttribute("aria-checked")).toBe("false");
    expect(pendingRadio?.getAttribute("aria-checked")).toBe("true");
    expect(completedRadio?.getAttribute("aria-checked")).toBe("false");
  });

  it("calls onFilterChange when a filter option is clicked", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const radios = screen.getAllByRole("radio");
    const pendingRadio = radios.find((r) => r.textContent === "Pending");
    fireEvent.click(pendingRadio!);

    expect(onFilterChange).toHaveBeenCalledTimes(1);
    expect(onFilterChange).toHaveBeenCalledWith("pending");
  });

  it("calls onFilterChange with 'completed' when Completed filter is clicked", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={allTasks}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const radios = screen.getAllByRole("radio");
    const completedRadio = radios.find((r) => r.textContent === "Completed");
    fireEvent.click(completedRadio!);

    expect(onFilterChange).toHaveBeenCalledWith("completed");
  });

  // -------------------------------------------------------------------------
  // Task card interactions
  // -------------------------------------------------------------------------

  it("passes onMarkComplete to task cards", () => {
    const onFilterChange = vi.fn();
    const onMarkComplete = vi.fn();
    const onRetry = vi.fn();

    render(
      <TrainingTaskList
        tasks={[pendingTask1]}
        filter="all"
        isLoading={false}
        error={null}
        onFilterChange={onFilterChange}
        onMarkComplete={onMarkComplete}
        onRetry={onRetry}
      />
    );

    const markCompleteButton = screen.getByRole("button", { name: /mark complete/i });
    fireEvent.click(markCompleteButton);

    expect(onMarkComplete).toHaveBeenCalledTimes(1);
    expect(onMarkComplete).toHaveBeenCalledWith(pendingTask1);
  });
});
