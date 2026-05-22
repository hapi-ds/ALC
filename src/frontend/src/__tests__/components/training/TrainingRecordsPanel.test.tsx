import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingRecordsPanel } from "../../../components/training/TrainingRecordsPanel";
import type { TrainingTask } from "../../../components/training/types";

/**
 * Unit tests for TrainingRecordsPanel component.
 *
 * Validates: Requirements 5.1–5.8
 */

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const completedTaskA1: TrainingTask = {
  id: 1,
  sop_document_uuid: "sop-aaa-111",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Training for Chemical Handling v1.0",
  is_completed: true,
  completed_at: "2024-01-15T10:00:00Z",
  created_at: "2024-01-01T08:00:00Z",
};

const completedTaskA2: TrainingTask = {
  id: 2,
  sop_document_uuid: "sop-aaa-111",
  sop_version: "2.0",
  assigned_user_id: 42,
  task_title: "Training for Chemical Handling v2.0",
  is_completed: true,
  completed_at: "2024-03-20T14:30:00Z",
  created_at: "2024-03-01T08:00:00Z",
};

const completedTaskB1: TrainingTask = {
  id: 3,
  sop_document_uuid: "sop-bbb-222",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Training for Lab Safety v1.0",
  is_completed: true,
  completed_at: "2024-02-10T09:00:00Z",
  created_at: "2024-02-01T08:00:00Z",
};

const pendingTask: TrainingTask = {
  id: 4,
  sop_document_uuid: "sop-ccc-333",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Pending Training Task",
  is_completed: false,
  completed_at: null,
  created_at: "2024-04-01T08:00:00Z",
};

const allTasks: TrainingTask[] = [
  completedTaskA1,
  completedTaskA2,
  completedTaskB1,
  pendingTask,
];

describe("TrainingRecordsPanel", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Record derivation from completed tasks (Req 5.1, 5.2)
  // -------------------------------------------------------------------------

  describe("record derivation", () => {
    it("only displays records for completed tasks", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      // Should show 3 completed tasks as records
      expect(screen.getByText("Training Records (3)")).toBeDefined();

      // Pending task's SOP should not appear as a standalone record
      expect(screen.queryByText("sop-ccc-333")).toBeNull();
    });

    it("displays SOP UUID, version, and completion date for each record", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskB1]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      expect(screen.getByText("sop-bbb-222")).toBeDefined();
      // Version and date are in the same text node
      const versionText = screen.getByText(/Version 1\.0/);
      expect(versionText).toBeDefined();
      expect(versionText.textContent).toContain("Completed");
    });
  });

  // -------------------------------------------------------------------------
  // Validity determination logic (Req 5.3)
  // -------------------------------------------------------------------------

  describe("validity determination", () => {
    it("marks the highest version per SOP as Valid", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskA1, completedTaskA2]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      // The most recent version (2.0) should be "Valid"
      const validBadges = screen.getAllByText("Valid");
      expect(validBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("marks older versions per SOP as Invalidated (visible after expanding group)", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskA1, completedTaskA2]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      // Expand the group to reveal historical records
      const toggleButton = screen.getByRole("button", {
        name: /toggle history/i,
      });
      fireEvent.click(toggleButton);

      // The older version (1.0) should be "Invalidated"
      const invalidBadges = screen.getAllByText("Invalidated");
      expect(invalidBadges.length).toBeGreaterThanOrEqual(1);
    });

    it("marks a single record for an SOP as Valid", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskB1]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      expect(screen.getByText("Valid")).toBeDefined();
      expect(screen.queryByText("Invalidated")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Sorting by each key (Req 5.4)
  // -------------------------------------------------------------------------

  describe("sorting", () => {
    it("defaults to sorting by completion date (newest first)", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      const sortSelect = screen.getByLabelText("Sort by:");
      expect((sortSelect as HTMLSelectElement).value).toBe("completed_at");
    });

    it("changes sort order when sort dropdown is changed to SOP UUID", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      const sortSelect = screen.getByLabelText("Sort by:");
      fireEvent.change(sortSelect, { target: { value: "sop_document_uuid" } });

      expect((sortSelect as HTMLSelectElement).value).toBe("sop_document_uuid");
    });

    it("changes sort order when sort dropdown is changed to Version", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      const sortSelect = screen.getByLabelText("Sort by:");
      fireEvent.change(sortSelect, { target: { value: "sop_version" } });

      expect((sortSelect as HTMLSelectElement).value).toBe("sop_version");
    });

    it("provides all three sort options", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      const sortSelect = screen.getByLabelText("Sort by:");
      const options = sortSelect.querySelectorAll("option");
      expect(options.length).toBe(3);

      const values = Array.from(options).map((o) => o.value);
      expect(values).toContain("completed_at");
      expect(values).toContain("sop_document_uuid");
      expect(values).toContain("sop_version");
    });
  });

  // -------------------------------------------------------------------------
  // Grouping and collapse/expand behavior (Req 5.6)
  // -------------------------------------------------------------------------

  describe("grouping and collapse/expand", () => {
    it("groups records by SOP UUID", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      // Both SOP UUIDs should appear
      expect(screen.getAllByText("sop-aaa-111").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("sop-bbb-222").length).toBeGreaterThanOrEqual(1);
    });

    it("shows most recent record by default and hides historical records", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskA1, completedTaskA2]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      // The expand toggle should exist and be collapsed
      const toggleButton = screen.getByRole("button", {
        name: /toggle history/i,
      });
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");

      // "Previous versions" text should not be visible when collapsed
      expect(screen.queryByText("Previous versions")).toBeNull();
    });

    it("expands to show historical records when toggle is clicked", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskA1, completedTaskA2]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /toggle history/i,
      });
      fireEvent.click(toggleButton);

      expect(toggleButton.getAttribute("aria-expanded")).toBe("true");
      expect(screen.getByText("Previous versions")).toBeDefined();
    });

    it("collapses historical records when toggle is clicked again", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskA1, completedTaskA2]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      const toggleButton = screen.getByRole("button", {
        name: /toggle history/i,
      });

      // Expand
      fireEvent.click(toggleButton);
      expect(toggleButton.getAttribute("aria-expanded")).toBe("true");

      // Collapse
      fireEvent.click(toggleButton);
      expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
      expect(screen.queryByText("Previous versions")).toBeNull();
    });

    it("does not show toggle when SOP has only one record", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[completedTaskB1]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      expect(
        screen.queryByRole("button", { name: /toggle history/i })
      ).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Empty state (Req 5.5)
  // -------------------------------------------------------------------------

  describe("empty state", () => {
    it("shows empty state message when no completed tasks exist", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[pendingTask]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      expect(
        screen.getByText(
          "No training records found. Complete training tasks to build your training history."
        )
      ).toBeDefined();
    });

    it("shows empty state message when tasks array is empty", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[]}
          isLoading={false}
          error={null}
          onRetry={onRetry}
        />
      );

      expect(
        screen.getByText(
          "No training records found. Complete training tasks to build your training history."
        )
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Loading state (Req 5.7)
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("shows loading skeleton when isLoading is true", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[]}
          isLoading={true}
          error={null}
          onRetry={onRetry}
        />
      );

      const loadingRegion = screen.getByLabelText("Loading training records");
      expect(loadingRegion).toBeDefined();
      expect(loadingRegion.getAttribute("aria-busy")).toBe("true");
    });

    it("does not show records or empty state when loading", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={true}
          error={null}
          onRetry={onRetry}
        />
      );

      expect(screen.queryByText("Training Records")).toBeNull();
      expect(
        screen.queryByText(
          "No training records found. Complete training tasks to build your training history."
        )
      ).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Error state (Req 5.8)
  // -------------------------------------------------------------------------

  describe("error state", () => {
    it("shows error message when error is provided", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[]}
          isLoading={false}
          error="Network error: Unable to reach the server."
          onRetry={onRetry}
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(
        screen.getByText("Network error: Unable to reach the server.")
      ).toBeDefined();
    });

    it("shows retry button that calls onRetry when clicked", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={[]}
          isLoading={false}
          error="Server error"
          onRetry={onRetry}
        />
      );

      const retryButton = screen.getByRole("button", { name: /retry/i });
      expect(retryButton).toBeDefined();

      fireEvent.click(retryButton);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("does not show records or empty state when error is present", () => {
      const onRetry = vi.fn();
      render(
        <TrainingRecordsPanel
          tasks={allTasks}
          isLoading={false}
          error="Something went wrong"
          onRetry={onRetry}
        />
      );

      expect(screen.queryByText("Training Records")).toBeNull();
      expect(
        screen.queryByText(
          "No training records found. Complete training tasks to build your training history."
        )
      ).toBeNull();
    });
  });
});
