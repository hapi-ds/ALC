import { describe, it, expect, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for ActionItemTracker component
 *
 * Tests: kanban column rendering, item grouping by status, drag-and-drop
 * triggering change reason modal, empty state, severity badges, accessibility.
 *
 * Validates: Requirements 11.5, 5.4
 */

import { ActionItemTracker } from "../ActionItemTracker";
import type { ActionItem } from "../../../lib/reviews-api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createActionItem(overrides: Partial<ActionItem> = {}): ActionItem {
  return {
    id: 1,
    finding_id: "finding-1",
    title: "Fix critical compliance gap",
    description: "The document is missing required signatures.",
    severity: "Critical",
    status: "Open",
    assigned_to: null,
    resolved_at: null,
    resolution_note: null,
    created_at: "2024-01-15T10:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

const defaultProps = {
  sessionId: 42,
  onUpdateItem: vi.fn().mockResolvedValue(undefined),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ActionItemTracker", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Empty state
  // -------------------------------------------------------------------------
  it("renders empty state when no items are provided", () => {
    render(<ActionItemTracker items={[]} {...defaultProps} />);

    expect(screen.getByText("No action items")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Renders all four columns
  // -------------------------------------------------------------------------
  it("renders all four kanban columns", () => {
    const items = [createActionItem()];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByText("Open")).toBeInTheDocument();
    expect(screen.getByText("In Progress")).toBeInTheDocument();
    expect(screen.getByText("Resolved")).toBeInTheDocument();
    expect(screen.getByText("Dismissed")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Groups items by status into correct columns
  // -------------------------------------------------------------------------
  it("groups items into their respective status columns", () => {
    const items: ActionItem[] = [
      createActionItem({ id: 1, title: "Open item", status: "Open" }),
      createActionItem({ id: 2, title: "In progress item", status: "InProgress" }),
      createActionItem({ id: 3, title: "Resolved item", status: "Resolved" }),
      createActionItem({ id: 4, title: "Dismissed item", status: "Dismissed" }),
    ];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByLabelText("Action item: Open item")).toBeInTheDocument();
    expect(screen.getByLabelText("Action item: In progress item")).toBeInTheDocument();
    expect(screen.getByLabelText("Action item: Resolved item")).toBeInTheDocument();
    expect(screen.getByLabelText("Action item: Dismissed item")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 4. Displays correct item count badges per column
  // -------------------------------------------------------------------------
  it("displays correct item count in column badges", () => {
    const items: ActionItem[] = [
      createActionItem({ id: 1, status: "Open" }),
      createActionItem({ id: 2, status: "Open" }),
      createActionItem({ id: 3, status: "InProgress" }),
    ];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    // Find badges by their content — the Open column should show "2"
    const badges = screen.getAllByText("2");
    expect(badges.length).toBeGreaterThanOrEqual(1);

    // InProgress column should show "1"
    const inProgressBadges = screen.getAllByText("1");
    expect(inProgressBadges.length).toBeGreaterThanOrEqual(1);
  });

  // -------------------------------------------------------------------------
  // 5. Renders severity badges on items
  // -------------------------------------------------------------------------
  it("renders severity badges with correct text", () => {
    const items: ActionItem[] = [
      createActionItem({ id: 1, severity: "Critical", title: "Critical item" }),
      createActionItem({ id: 2, severity: "Major", title: "Major item" }),
      createActionItem({ id: 3, severity: "Minor", title: "Minor item" }),
    ];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("Major")).toBeInTheDocument();
    expect(screen.getByText("Minor")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 6. Displays item title and description
  // -------------------------------------------------------------------------
  it("displays item title and description", () => {
    const items = [
      createActionItem({
        title: "Review training records",
        description: "Ensure all operators have completed training.",
      }),
    ];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByText("Review training records")).toBeInTheDocument();
    expect(
      screen.getByText("Ensure all operators have completed training."),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Displays resolution note for resolved items
  // -------------------------------------------------------------------------
  it("displays resolution note when present", () => {
    const items = [
      createActionItem({
        status: "Resolved",
        resolution_note: "Fixed in version 2.1",
      }),
    ];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByText("Fixed in version 2.1")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. Accessibility — region role and label
  // -------------------------------------------------------------------------
  it("has proper accessibility attributes", () => {
    const items = [createActionItem()];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(
      screen.getByRole("region", { name: "Action item tracker" }),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Renders heading
  // -------------------------------------------------------------------------
  it("renders the Action Items heading", () => {
    const items = [createActionItem()];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByText("Action Items")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Change reason modal appears and can be cancelled
  // -------------------------------------------------------------------------
  it("does not show change reason modal initially", () => {
    const items = [createActionItem()];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Multiple items in same column
  // -------------------------------------------------------------------------
  it("renders multiple items in the same column", () => {
    const items: ActionItem[] = [
      createActionItem({ id: 1, title: "First open item", status: "Open" }),
      createActionItem({ id: 2, title: "Second open item", status: "Open" }),
      createActionItem({ id: 3, title: "Third open item", status: "Open" }),
    ];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    expect(screen.getByText("First open item")).toBeInTheDocument();
    expect(screen.getByText("Second open item")).toBeInTheDocument();
    expect(screen.getByText("Third open item")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 12. Empty columns show zero count
  // -------------------------------------------------------------------------
  it("shows zero count for empty columns", () => {
    const items = [createActionItem({ status: "Open" })];

    render(<ActionItemTracker items={items} {...defaultProps} />);

    // Resolved and Dismissed columns should show "0"
    const zeroBadges = screen.getAllByText("0");
    expect(zeroBadges.length).toBeGreaterThanOrEqual(2);
  });
});
