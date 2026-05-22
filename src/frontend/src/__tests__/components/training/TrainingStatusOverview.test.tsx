import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { TrainingStatusOverview } from "../../../components/training/TrainingStatusOverview";
import type { TrainingStatistics } from "../../../components/training/types";

/**
 * Unit tests for TrainingStatusOverview component.
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.5
 */

const populatedStats: TrainingStatistics = {
  pending: 3,
  completed: 7,
  total: 10,
  completionPercentage: 70,
};

const emptyStats: TrainingStatistics = {
  pending: 0,
  completed: 0,
  total: 0,
  completionPercentage: null,
};

describe("TrainingStatusOverview", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  it("renders skeleton placeholders when isLoading is true", () => {
    render(<TrainingStatusOverview statistics={emptyStats} isLoading={true} />);

    const region = screen.getByRole("region", { name: "Training Status Overview" });
    expect(region).toBeDefined();

    // Should announce loading via aria-live
    expect(screen.getByText("Loading training statistics...")).toBeDefined();
  });

  it("does not render stat values when loading", () => {
    render(<TrainingStatusOverview statistics={populatedStats} isLoading={true} />);

    // Stat values should not be visible during loading
    expect(screen.queryByText("3")).toBeNull();
    expect(screen.queryByText("7")).toBeNull();
    expect(screen.queryByText("10")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Populated state
  // -------------------------------------------------------------------------

  it("renders three stat cards with correct values", () => {
    render(<TrainingStatusOverview statistics={populatedStats} isLoading={false} />);

    expect(screen.getByText("Pending")).toBeDefined();
    expect(screen.getByText("3")).toBeDefined();

    expect(screen.getByText("Completed")).toBeDefined();
    expect(screen.getByText("7")).toBeDefined();

    expect(screen.getByText("Total Tasks")).toBeDefined();
    expect(screen.getByText("10")).toBeDefined();
  });

  it("displays completion percentage when total > 0", () => {
    render(<TrainingStatusOverview statistics={populatedStats} isLoading={false} />);

    expect(screen.getByText("70%")).toBeDefined();
  });

  it("displays 'N/A' for completion percentage when total is 0", () => {
    render(<TrainingStatusOverview statistics={emptyStats} isLoading={false} />);

    expect(screen.getByText("N/A")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Empty state (zero tasks)
  // -------------------------------------------------------------------------

  it("renders stat cards with 0 values when no tasks exist", () => {
    render(<TrainingStatusOverview statistics={emptyStats} isLoading={false} />);

    // All three stat cards should show 0
    const zeros = screen.getAllByText("0");
    expect(zeros.length).toBe(3);
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  it("has role='region' with accessible label", () => {
    render(<TrainingStatusOverview statistics={populatedStats} isLoading={false} />);

    const region = screen.getByRole("region", { name: "Training Status Overview" });
    expect(region).toBeDefined();
  });

  it("marks icons as aria-hidden", () => {
    const { container } = render(
      <TrainingStatusOverview statistics={populatedStats} isLoading={false} />
    );

    // All icon wrappers should have aria-hidden="true"
    const hiddenElements = container.querySelectorAll('[aria-hidden="true"]');
    expect(hiddenElements.length).toBeGreaterThan(0);
  });
});
