import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingSchedulePanel } from "../../components/training/TrainingSchedulePanel";
import type { TrainingSchedule } from "../../types/training-ecosystem";

/**
 * Unit tests for TrainingSchedulePanel component.
 *
 * Validates: Requirements 10.1, 10.2, 10.9
 */

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSchedule(overrides: Partial<TrainingSchedule> = {}): TrainingSchedule {
  return {
    id: 1,
    user_id: 42,
    schedule_data: {
      items: [
        {
          document_id: 1,
          document_title: "Chemical Handling SOP",
          priority: "Critical",
          deadline: "2024-03-01T00:00:00Z",
          completed: false,
          blocks_access: true,
        },
        {
          document_id: 2,
          document_title: "Lab Safety Procedures",
          priority: "Low",
          deadline: "2024-06-01T00:00:00Z",
          completed: true,
          blocks_access: false,
        },
        {
          document_id: 3,
          document_title: "Equipment Maintenance Guide",
          priority: "High",
          deadline: "2024-04-01T00:00:00Z",
          completed: false,
          blocks_access: false,
        },
        {
          document_id: 4,
          document_title: "Quality Control Procedures",
          priority: "Medium",
          deadline: null,
          completed: false,
          blocks_access: false,
        },
      ],
    },
    compliance_percentage: 25.0,
    total_items: 4,
    completed_items: 1,
    generated_at: "2024-01-15T10:00:00Z",
    last_recalculated_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingSchedulePanel", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Priority sorting
  // -------------------------------------------------------------------------

  describe("priority sorting", () => {
    it("sorts items by priority (Critical first, then High, Medium, Low)", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const items = screen.getAllByRole("listitem");
      expect(items).toHaveLength(4);

      // First item should be Critical
      expect(items[0].textContent).toContain("Chemical Handling SOP");
      // Second should be High
      expect(items[1].textContent).toContain("Equipment Maintenance Guide");
      // Third should be Medium
      expect(items[2].textContent).toContain("Quality Control Procedures");
      // Fourth should be Low
      expect(items[3].textContent).toContain("Lab Safety Procedures");
    });

    it("sorts by deadline within same priority (earliest first)", () => {
      const schedule = makeSchedule({
        schedule_data: {
          items: [
            {
              document_id: 1,
              document_title: "Doc B",
              priority: "High",
              deadline: "2024-05-01T00:00:00Z",
              completed: false,
              blocks_access: false,
            },
            {
              document_id: 2,
              document_title: "Doc A",
              priority: "High",
              deadline: "2024-03-01T00:00:00Z",
              completed: false,
              blocks_access: false,
            },
          ],
        },
      });

      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const items = screen.getAllByRole("listitem");
      // Earlier deadline first
      expect(items[0].textContent).toContain("Doc A");
      expect(items[1].textContent).toContain("Doc B");
    });

    it("places items with null deadline after items with deadlines at same priority", () => {
      const schedule = makeSchedule({
        schedule_data: {
          items: [
            {
              document_id: 1,
              document_title: "No Deadline",
              priority: "Medium",
              deadline: null,
              completed: false,
              blocks_access: false,
            },
            {
              document_id: 2,
              document_title: "Has Deadline",
              priority: "Medium",
              deadline: "2024-04-01T00:00:00Z",
              completed: false,
              blocks_access: false,
            },
          ],
        },
      });

      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const items = screen.getAllByRole("listitem");
      expect(items[0].textContent).toContain("Has Deadline");
      expect(items[1].textContent).toContain("No Deadline");
    });
  });

  // -------------------------------------------------------------------------
  // Progress bar
  // -------------------------------------------------------------------------

  describe("progress bar", () => {
    it("renders a progressbar with correct percentage", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar).toBeDefined();
      expect(progressbar.getAttribute("aria-valuenow")).toBe("25");
      expect(progressbar.getAttribute("aria-valuemin")).toBe("0");
      expect(progressbar.getAttribute("aria-valuemax")).toBe("100");
    });

    it("shows completed count text", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      expect(screen.getByText("1 of 4 completed")).toBeDefined();
      expect(screen.getByText("25%")).toBeDefined();
    });

    it("shows 0% when no items are completed", () => {
      const schedule = makeSchedule({
        schedule_data: {
          items: [
            {
              document_id: 1,
              document_title: "Doc A",
              priority: "High",
              deadline: "2024-03-01T00:00:00Z",
              completed: false,
              blocks_access: false,
            },
          ],
        },
      });

      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar.getAttribute("aria-valuenow")).toBe("0");
    });

    it("shows 100% when all items are completed", () => {
      const schedule = makeSchedule({
        schedule_data: {
          items: [
            {
              document_id: 1,
              document_title: "Doc A",
              priority: "High",
              deadline: "2024-03-01T00:00:00Z",
              completed: true,
              blocks_access: false,
            },
            {
              document_id: 2,
              document_title: "Doc B",
              priority: "Low",
              deadline: null,
              completed: true,
              blocks_access: false,
            },
          ],
        },
      });

      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar.getAttribute("aria-valuenow")).toBe("100");
    });
  });

  // -------------------------------------------------------------------------
  // Empty state
  // -------------------------------------------------------------------------

  describe("empty state", () => {
    it("renders empty state message when schedule is null", () => {
      render(
        <TrainingSchedulePanel schedule={null} isLoading={false} error={null} />
      );

      expect(
        screen.getByText(/no training items scheduled/i)
      ).toBeDefined();
    });

    it("renders empty state message when schedule has no items", () => {
      const schedule = makeSchedule({ schedule_data: { items: [] } });
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      expect(
        screen.getByText(/no training items scheduled/i)
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Skeleton loading
  // -------------------------------------------------------------------------

  describe("skeleton loading", () => {
    it("renders skeleton loading state with aria-label", () => {
      render(
        <TrainingSchedulePanel schedule={null} isLoading={true} error={null} />
      );

      expect(screen.getByLabelText("Loading training schedule")).toBeDefined();
    });

    it("does not render items or progress bar while loading", () => {
      render(
        <TrainingSchedulePanel schedule={makeSchedule()} isLoading={true} error={null} />
      );

      expect(screen.queryByRole("progressbar")).toBeNull();
      expect(screen.queryByRole("listitem")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  describe("error state", () => {
    it("renders error message", () => {
      render(
        <TrainingSchedulePanel
          schedule={null}
          isLoading={false}
          error="Failed to load schedule"
        />
      );

      expect(screen.getByText("Failed to load schedule")).toBeDefined();
    });

    it("renders retry button when onRetry is provided", () => {
      const onRetry = vi.fn();
      render(
        <TrainingSchedulePanel
          schedule={null}
          isLoading={false}
          error="Network error"
          onRetry={onRetry}
        />
      );

      const retryButton = screen.getByRole("button", { name: /retry/i });
      fireEvent.click(retryButton);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });
  });

  // -------------------------------------------------------------------------
  // Item rendering
  // -------------------------------------------------------------------------

  describe("item rendering", () => {
    it("displays priority badges with correct text", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      expect(screen.getByText("Critical")).toBeDefined();
      expect(screen.getByText("High")).toBeDefined();
      expect(screen.getByText("Medium")).toBeDefined();
      expect(screen.getByText("Low")).toBeDefined();
    });

    it("shows 'Blocks access' indicator for items that block access", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      expect(screen.getByText("Blocks access")).toBeDefined();
    });

    it("shows 'Completed' badge for completed items", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      expect(screen.getByText("Completed")).toBeDefined();
    });

    it("shows 'Start Training' button for incomplete items", () => {
      const schedule = makeSchedule();
      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const buttons = screen.getAllByRole("button", { name: /start training/i });
      // 3 incomplete items
      expect(buttons).toHaveLength(3);
    });

    it("calls onStartTraining when 'Start Training' is clicked", () => {
      const onStartTraining = vi.fn();
      const schedule = makeSchedule({
        schedule_data: {
          items: [
            {
              document_id: 1,
              document_title: "Test Doc",
              priority: "High",
              deadline: "2024-03-01T00:00:00Z",
              completed: false,
              blocks_access: false,
            },
          ],
        },
      });

      render(
        <TrainingSchedulePanel
          schedule={schedule}
          isLoading={false}
          error={null}
          onStartTraining={onStartTraining}
        />
      );

      const button = screen.getByRole("button", { name: /start training for test doc/i });
      fireEvent.click(button);

      expect(onStartTraining).toHaveBeenCalledTimes(1);
      expect(onStartTraining).toHaveBeenCalledWith(
        expect.objectContaining({ document_id: 1, document_title: "Test Doc" })
      );
    });

    it("truncates long titles at 120 characters", () => {
      const longTitle = "A".repeat(150);
      const schedule = makeSchedule({
        schedule_data: {
          items: [
            {
              document_id: 1,
              document_title: longTitle,
              priority: "High",
              deadline: null,
              completed: false,
              blocks_access: false,
            },
          ],
        },
      });

      render(
        <TrainingSchedulePanel schedule={schedule} isLoading={false} error={null} />
      );

      const expectedTruncated = "A".repeat(120) + "\u2026";
      expect(screen.getByText(expectedTruncated)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  describe("accessibility", () => {
    it("has section with aria-label 'Training schedule'", () => {
      render(
        <TrainingSchedulePanel schedule={makeSchedule()} isLoading={false} error={null} />
      );

      expect(screen.getByLabelText("Training schedule")).toBeDefined();
    });

    it("has list with aria-label 'Training items'", () => {
      render(
        <TrainingSchedulePanel schedule={makeSchedule()} isLoading={false} error={null} />
      );

      expect(screen.getByLabelText("Training items")).toBeDefined();
    });

    it("progress bar has descriptive aria-label", () => {
      render(
        <TrainingSchedulePanel schedule={makeSchedule()} isLoading={false} error={null} />
      );

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar.getAttribute("aria-label")).toContain("Training progress");
    });
  });
});
