import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for WorkflowHistoryTimeline
 *
 * Tests: loading/error/empty states, entry rendering, collapse/expand,
 * "Show all" button, "Show more" toggle for truncated reasons,
 * accessibility (ordered list, aria-live).
 *
 * Validates: Requirements 4.1, 4.3, 4.5, 4.6, 4.7, 4.8, 11.4, 11.6
 */

// Mock the Zustand store
vi.mock("@/stores/workflowExecutionStore");

import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { WorkflowHistoryTimeline } from "../WorkflowHistoryTimeline";
import type { TransitionHistoryEntry } from "@/types/workflow";

const mockStore = vi.mocked(useWorkflowExecutionStore);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface MockStoreState {
  history: TransitionHistoryEntry[];
  isLoadingHistory: boolean;
  historyError: string | null;
  fetchTransitionHistory: ReturnType<typeof vi.fn>;
}

function createDefaultState(
  overrides: Partial<MockStoreState> = {}
): MockStoreState {
  return {
    history: [],
    isLoadingHistory: false,
    historyError: null,
    fetchTransitionHistory: vi.fn(),
    ...overrides,
  };
}

function setupMockStore(overrides: Partial<MockStoreState> = {}) {
  const state = createDefaultState(overrides);
  mockStore.mockImplementation((selector: unknown) => {
    if (typeof selector === "function") {
      return (selector as (s: MockStoreState) => unknown)(state);
    }
    return state;
  });
  return state;
}

function makeEntry(
  id: number,
  overrides: Partial<TransitionHistoryEntry> = {}
): TransitionHistoryEntry {
  return {
    id,
    document_id: 1,
    user_id: 42,
    previous_state: "Draft",
    new_state: "Review",
    timestamp: "2024-06-01T12:00:00Z",
    change_reason: null,
    ...overrides,
  };
}

function makeEntries(count: number): TransitionHistoryEntry[] {
  return Array.from({ length: count }, (_, i) =>
    makeEntry(i + 1, {
      previous_state: i % 2 === 0 ? "Draft" : "Review",
      new_state: i % 2 === 0 ? "Review" : "Approved",
      timestamp: `2024-06-0${Math.min(i + 1, 9)}T12:00:00Z`,
      user_id: 10 + i,
    })
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WorkflowHistoryTimeline", () => {
  const defaultProps = { documentUuid: "doc-uuid-abc" };

  beforeEach(() => {
    setupMockStore();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Loading state
  // -------------------------------------------------------------------------
  it("renders loading skeleton with aria-live announcement", () => {
    setupMockStore({ isLoadingHistory: true });

    render(<WorkflowHistoryTimeline {...defaultProps} />);

    expect(screen.getByRole("region")).toHaveAttribute(
      "aria-label",
      "Workflow Transition History"
    );
    expect(
      screen.getByText("Loading transition history...")
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Error state
  // -------------------------------------------------------------------------
  it("renders error message and retry button", () => {
    setupMockStore({ historyError: "Failed to load history" });

    render(<WorkflowHistoryTimeline {...defaultProps} />);

    expect(screen.getByText("Failed to load history")).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: /retry loading transition history/i,
      })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Retry button calls fetchTransitionHistory
  // -------------------------------------------------------------------------
  it("clicking retry calls fetchTransitionHistory", () => {
    const fetchTransitionHistory = vi.fn();
    setupMockStore({
      historyError: "Network error",
      fetchTransitionHistory,
    });

    render(<WorkflowHistoryTimeline {...defaultProps} />);

    const retryButton = screen.getByRole("button", {
      name: /retry loading transition history/i,
    });
    fireEvent.click(retryButton);

    // Called on mount + once on retry click
    expect(fetchTransitionHistory).toHaveBeenCalledWith("doc-uuid-abc");
  });

  // -------------------------------------------------------------------------
  // 4. Empty state
  // -------------------------------------------------------------------------
  it('shows "No transition history available" when history is empty and expanded', () => {
    setupMockStore({ history: [] });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    expect(
      screen.getByText(
        "No transition history available for this document."
      )
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Renders entries with correct data
  // -------------------------------------------------------------------------
  it("renders entries with state badges, user ID, and timestamp", () => {
    const entries = [
      makeEntry(1, {
        previous_state: "Draft",
        new_state: "Review",
        user_id: 7,
        timestamp: "2024-06-15T10:30:00Z",
      }),
    ];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    // State badges
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    // User ID
    expect(screen.getByText(/User #7/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 6. Directional arrow between states
  // -------------------------------------------------------------------------
  it("arrow icon is present between previous and new state", () => {
    const entries = [makeEntry(1)];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    // The ArrowRight icon has aria-hidden="true"
    const listItem = screen.getByRole("listitem");
    const arrowIcon = listItem.querySelector('[aria-hidden="true"]');
    expect(arrowIcon).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Collapse/expand behavior
  // -------------------------------------------------------------------------
  it("defaults to collapsed, clicking header expands", () => {
    const entries = [makeEntry(1)];
    setupMockStore({ history: entries });

    render(<WorkflowHistoryTimeline {...defaultProps} />);

    // Defaults to collapsed — no list items visible
    const headerButton = screen.getByRole("button", {
      name: /transition history/i,
    });
    expect(headerButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(headerButton);
    expect(headerButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("list")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. Shows only 5 entries when expanded
  // -------------------------------------------------------------------------
  it("shows only 5 entries when expanded with more than 5 entries", () => {
    const entries = makeEntries(8);
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    const listItems = screen.getAllByRole("listitem");
    expect(listItems).toHaveLength(5);
  });

  // -------------------------------------------------------------------------
  // 9. "Show all" button appears when > 5 entries
  // -------------------------------------------------------------------------
  it('"Show all" button appears when there are more than 5 entries', () => {
    const entries = makeEntries(7);
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    const showAllButton = screen.getByRole("button", {
      name: /show all 7 transition history entries/i,
    });
    expect(showAllButton).toBeInTheDocument();
    expect(showAllButton).toHaveTextContent("Show all (7)");
  });

  // -------------------------------------------------------------------------
  // 10. "Show all" reveals all entries
  // -------------------------------------------------------------------------
  it('"Show all" reveals all entries up to 50', () => {
    const entries = makeEntries(10);
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    // Initially only 5
    expect(screen.getAllByRole("listitem")).toHaveLength(5);

    // Click "Show all"
    const showAllButton = screen.getByRole("button", {
      name: /show all 10 transition history entries/i,
    });
    fireEvent.click(showAllButton);

    // Now all 10 visible
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
  });

  // -------------------------------------------------------------------------
  // 11. Change reason displayed
  // -------------------------------------------------------------------------
  it("shows change reason text for entries that have one", () => {
    const entries = [
      makeEntry(1, { change_reason: "Reviewed by QA team" }),
    ];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    expect(screen.getByText("Reviewed by QA team")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 12. Change reason truncated at 120 chars
  // -------------------------------------------------------------------------
  it("long change reasons are truncated with ellipsis", () => {
    const longReason = "A".repeat(150);
    const entries = [makeEntry(1, { change_reason: longReason })];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    // Should show truncated text (120 chars + "…")
    const truncated = "A".repeat(120) + "\u2026";
    expect(screen.getByText(truncated)).toBeInTheDocument();
    // Full text should NOT be visible
    expect(screen.queryByText(longReason)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 13. "Show more" toggle for truncated reasons
  // -------------------------------------------------------------------------
  it('"Show more" toggle reveals full text of truncated reason', () => {
    const longReason = "B".repeat(150);
    const entries = [makeEntry(1, { change_reason: longReason })];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    // Click "Show more"
    const showMoreButton = screen.getByRole("button", {
      name: /show more of change reason/i,
    });
    fireEvent.click(showMoreButton);

    // Full text now visible
    expect(screen.getByText(longReason)).toBeInTheDocument();

    // Button now says "Show less"
    expect(
      screen.getByRole("button", { name: /show less of change reason/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 14. Ordered list structure (ol/li)
  // -------------------------------------------------------------------------
  it("uses ol element with li children for timeline entries", () => {
    const entries = [makeEntry(1), makeEntry(2)];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    const list = screen.getByRole("list");
    expect(list.tagName).toBe("OL");

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    items.forEach((item) => {
      expect(item.tagName).toBe("LI");
    });
  });

  // -------------------------------------------------------------------------
  // 15. aria-live region
  // -------------------------------------------------------------------------
  it('has aria-live="polite" for loading announcements', () => {
    const entries = [makeEntry(1)];
    setupMockStore({ history: entries });

    render(
      <WorkflowHistoryTimeline {...defaultProps} defaultExpanded={true} />
    );

    const liveRegion = screen.getByText("Transition history loaded.");
    expect(liveRegion.closest('[aria-live="polite"]')).toBeInTheDocument();
  });
});
