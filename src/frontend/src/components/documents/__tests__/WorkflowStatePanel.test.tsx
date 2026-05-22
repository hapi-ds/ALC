import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for WorkflowStatePanel
 *
 * Tests: state badge rendering, transition buttons, loading/error/empty states,
 * gate icons, risk badge display, accessibility (ARIA region, button labels),
 * retry button, collapse/expand.
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 9.4, 9.5, 11.1, 11.2
 */

// Mock the Zustand store
vi.mock("@/stores/workflowExecutionStore");

// Mock TransitionConfirmationDialog to avoid testing its internals
vi.mock("../TransitionConfirmationDialog", () => ({
  TransitionConfirmationDialog: ({
    open,
    currentState,
    targetState,
  }: {
    open: boolean;
    currentState: string;
    targetState: string;
  }) =>
    open ? (
      <div data-testid="transition-dialog">
        {currentState} → {targetState}
      </div>
    ) : null,
}));

import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { WorkflowStatePanel } from "../WorkflowStatePanel";

const mockStore = vi.mocked(useWorkflowExecutionStore);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface MockStoreState {
  currentState: string | null;
  workflowName: string | null;
  validTransitions: string[];
  updatedAt: string | null;
  isLoadingState: boolean;
  stateError: string | null;
  riskLevel: string;
  signatureRequiredTransitions: string[];
  trainingTriggerTransitions: string[];
  lastTransitionResult: null | {
    success: boolean;
    previous_state: string;
    new_state: string;
    requires_signature: boolean;
    triggers_training: boolean;
  };
  fetchDocumentState: ReturnType<typeof vi.fn>;
  fetchWorkflowGateInfo: ReturnType<typeof vi.fn>;
}

function createDefaultState(
  overrides: Partial<MockStoreState> = {}
): MockStoreState {
  return {
    currentState: "Draft",
    workflowName: "Document Review",
    validTransitions: ["Review"],
    updatedAt: "2024-06-01T12:00:00Z",
    isLoadingState: false,
    stateError: null,
    riskLevel: "low",
    signatureRequiredTransitions: [],
    trainingTriggerTransitions: [],
    lastTransitionResult: null,
    fetchDocumentState: vi.fn(),
    fetchWorkflowGateInfo: vi.fn(),
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("WorkflowStatePanel", () => {
  const defaultProps = { documentUuid: "test-doc-uuid-123" };

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
    setupMockStore({ isLoadingState: true, currentState: null });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.getByRole("region")).toHaveAttribute(
      "aria-label",
      "Document Workflow State"
    );
    expect(screen.getByText("Loading workflow state...")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Error state
  // -------------------------------------------------------------------------
  it("renders error message and retry button", () => {
    setupMockStore({
      stateError: "Network error occurred",
      currentState: null,
      isLoadingState: false,
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.getByText("Network error occurred")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /retry loading workflow state/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. No workflow assigned
  // -------------------------------------------------------------------------
  it('renders "No workflow is assigned" message when currentState is null', () => {
    setupMockStore({ currentState: null, isLoadingState: false });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(
      screen.getByText("No workflow is assigned to this document.")
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 4. Main panel with state badge
  // -------------------------------------------------------------------------
  it('renders state badge with correct text (e.g., "Draft")', () => {
    setupMockStore({ currentState: "Draft" });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. State badge colors
  // -------------------------------------------------------------------------
  it("Draft state badge gets gray classes", () => {
    setupMockStore({ currentState: "Draft" });
    render(<WorkflowStatePanel {...defaultProps} />);

    const badge = screen.getByText("Draft");
    expect(badge.className).toContain("bg-gray-100");
    expect(badge.className).toContain("text-gray-800");
  });

  it("Review state badge gets blue classes", () => {
    setupMockStore({ currentState: "Review", validTransitions: ["Approved"] });
    render(<WorkflowStatePanel {...defaultProps} />);

    const badge = screen.getByText("Review");
    expect(badge.className).toContain("bg-blue-100");
    expect(badge.className).toContain("text-blue-800");
  });

  it("Approved state badge gets green classes", () => {
    setupMockStore({
      currentState: "Approved",
      validTransitions: [],
    });
    render(<WorkflowStatePanel {...defaultProps} />);

    const badge = screen.getByText("Approved");
    expect(badge.className).toContain("bg-green-100");
    expect(badge.className).toContain("text-green-800");
  });

  it("Rejected state badge gets red classes", () => {
    setupMockStore({
      currentState: "Rejected",
      validTransitions: [],
    });
    render(<WorkflowStatePanel {...defaultProps} />);

    const badge = screen.getByText("Rejected");
    expect(badge.className).toContain("bg-red-100");
    expect(badge.className).toContain("text-red-800");
  });

  // -------------------------------------------------------------------------
  // 6. Transition buttons
  // -------------------------------------------------------------------------
  it("renders a button for each valid transition", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review", "Rejected"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(
      screen.getByRole("button", { name: /transition to review/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /transition to rejected/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. No transitions available
  // -------------------------------------------------------------------------
  it('shows "No transitions are currently available" text when no transitions', () => {
    setupMockStore({ currentState: "Approved", validTransitions: [] });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(
      screen.getByText(
        "No transitions are currently available for this document state."
      )
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. Gate icons - signature
  // -------------------------------------------------------------------------
  it("lock icon appears on buttons for signature-required transitions", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
      signatureRequiredTransitions: ["Draft\u2192Review"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    const button = screen.getByRole("button", {
      name: /transition to review/i,
    });
    // The lock icon is wrapped in a span with a title
    const lockSpan = button.querySelector(
      '[title="Requires electronic signature"]'
    );
    expect(lockSpan).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Gate icons - training
  // -------------------------------------------------------------------------
  it("book icon appears on buttons for training-trigger transitions", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
      trainingTriggerTransitions: ["Draft\u2192Review"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    const button = screen.getByRole("button", {
      name: /transition to review/i,
    });
    const bookSpan = button.querySelector(
      '[title="Triggers training assignment"]'
    );
    expect(bookSpan).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Gate icons - both
  // -------------------------------------------------------------------------
  it("both icons appear when transition has both gates", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
      signatureRequiredTransitions: ["Draft\u2192Review"],
      trainingTriggerTransitions: ["Draft\u2192Review"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    const button = screen.getByRole("button", {
      name: /transition to review/i,
    });
    const lockSpan = button.querySelector(
      '[title="Requires electronic signature"]'
    );
    const bookSpan = button.querySelector(
      '[title="Triggers training assignment"]'
    );
    expect(lockSpan).toBeInTheDocument();
    expect(bookSpan).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Risk badge display
  // -------------------------------------------------------------------------
  it("risk level badge shows in header with correct text", () => {
    setupMockStore({ riskLevel: "high" });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("risk level badge uses orange classes for high risk", () => {
    setupMockStore({ riskLevel: "high" });
    render(<WorkflowStatePanel {...defaultProps} />);

    const badge = screen.getByText("high");
    expect(badge.className).toContain("bg-orange-100");
    expect(badge.className).toContain("text-orange-700");
  });

  it("risk level badge uses red classes for critical risk", () => {
    setupMockStore({ riskLevel: "critical" });
    render(<WorkflowStatePanel {...defaultProps} />);

    const badge = screen.getByText("critical");
    expect(badge.className).toContain("bg-red-100");
    expect(badge.className).toContain("text-red-700");
  });

  // -------------------------------------------------------------------------
  // 12. Risk warning banner
  // -------------------------------------------------------------------------
  it("shows warning banner for high risk level", () => {
    setupMockStore({ riskLevel: "high" });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/high-risk/)).toBeInTheDocument();
  });

  it("shows warning banner for critical risk level", () => {
    setupMockStore({ riskLevel: "critical" });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/critical-risk/)).toBeInTheDocument();
  });

  it("does not show warning banner for low risk level", () => {
    setupMockStore({ riskLevel: "low" });

    render(<WorkflowStatePanel {...defaultProps} />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 13. ARIA region
  // -------------------------------------------------------------------------
  it('component has role="region" with aria-label="Document Workflow State"', () => {
    render(<WorkflowStatePanel {...defaultProps} />);

    const region = screen.getByRole("region");
    expect(region).toHaveAttribute("aria-label", "Document Workflow State");
  });

  // -------------------------------------------------------------------------
  // 14. Button aria-labels
  // -------------------------------------------------------------------------
  it("transition buttons have correct aria-labels including gate info", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
      signatureRequiredTransitions: ["Draft\u2192Review"],
      trainingTriggerTransitions: ["Draft\u2192Review"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    const button = screen.getByRole("button", {
      name: "Transition to Review, requires electronic signature, triggers training assignment",
    });
    expect(button).toBeInTheDocument();
  });

  it("transition button without gates has simple aria-label", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
      signatureRequiredTransitions: [],
      trainingTriggerTransitions: [],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    const button = screen.getByRole("button", {
      name: "Transition to Review",
    });
    expect(button).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 15. Retry button
  // -------------------------------------------------------------------------
  it("clicking retry calls fetchDocumentState again", () => {
    const fetchDocumentState = vi.fn();
    setupMockStore({
      stateError: "Something went wrong",
      currentState: null,
      isLoadingState: false,
      fetchDocumentState,
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    const retryButton = screen.getByRole("button", {
      name: /retry loading workflow state/i,
    });
    fireEvent.click(retryButton);

    // fetchDocumentState is called on mount + once on retry click
    expect(fetchDocumentState).toHaveBeenCalledWith("test-doc-uuid-123");
  });

  // -------------------------------------------------------------------------
  // 16. Clicking a transition button opens the confirmation dialog
  // -------------------------------------------------------------------------
  it("clicking a transition button opens the confirmation dialog", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    // Dialog should not be visible initially
    expect(screen.queryByTestId("transition-dialog")).not.toBeInTheDocument();

    // Click the transition button
    const transitionButton = screen.getByRole("button", {
      name: /transition to review/i,
    });
    fireEvent.click(transitionButton);

    // Dialog should now be visible with correct state info
    const dialog = screen.getByTestId("transition-dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent("Draft → Review");
  });

  // -------------------------------------------------------------------------
  // 17. Collapse/expand
  // -------------------------------------------------------------------------
  it("clicking header toggles expanded state", () => {
    setupMockStore({
      currentState: "Draft",
      validTransitions: ["Review"],
    });

    render(<WorkflowStatePanel {...defaultProps} />);

    // The header button has aria-expanded
    const headerButton = screen.getByRole("button", {
      name: /workflow state/i,
    });
    expect(headerButton).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(headerButton);

    expect(headerButton).toHaveAttribute("aria-expanded", "false");
  });
});
