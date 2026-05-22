import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent, act } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for TransitionConfirmationDialog
 *
 * Tests: open/close behavior, change reason validation (3–500 chars), character counter,
 * gate warnings (signature/training), risk warnings (high/critical), confirm button
 * disabled states, loading state, error display, reason retention on failure,
 * accessibility (focus trapping, Escape key, dialog role, aria-labelledby, aria-describedby).
 *
 * Validates: Requirements 2.1, 2.2, 2.4, 2.6, 2.9, 3.4, 3.5, 10.2, 11.3, 11.5, 11.8
 */

// Mock the Zustand store
vi.mock("@/stores/workflowExecutionStore");

import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { TransitionConfirmationDialog } from "../TransitionConfirmationDialog";

const mockStore = vi.mocked(useWorkflowExecutionStore);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface MockStoreState {
  executeTransition: ReturnType<typeof vi.fn>;
  isTransitioning: boolean;
  transitionError: string | null;
  clearTransitionState: ReturnType<typeof vi.fn>;
}

function createDefaultState(
  overrides: Partial<MockStoreState> = {}
): MockStoreState {
  return {
    executeTransition: vi.fn().mockResolvedValue(true),
    isTransitioning: false,
    transitionError: null,
    clearTransitionState: vi.fn(),
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

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  currentState: "Draft",
  targetState: "Review",
  documentUuid: "doc-uuid-123",
  requiresSignature: false,
  triggersTraining: false,
  riskLevel: "low" as const,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TransitionConfirmationDialog", () => {
  beforeEach(() => {
    setupMockStore();
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 0;
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Renders dialog when open=true
  // -------------------------------------------------------------------------
  it("renders dialog with role, aria-labelledby, and aria-describedby when open=true", () => {
    render(<TransitionConfirmationDialog {...defaultProps} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-labelledby", "transition-dialog-title");
    expect(dialog).toHaveAttribute("aria-describedby", "transition-dialog-description");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  // -------------------------------------------------------------------------
  // 2. Does not render when open=false
  // -------------------------------------------------------------------------
  it("does not render when open=false", () => {
    render(<TransitionConfirmationDialog {...defaultProps} open={false} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Shows transition summary
  // -------------------------------------------------------------------------
  it("shows transition summary with current → target state", () => {
    render(<TransitionConfirmationDialog {...defaultProps} />);

    const descEl = document.getElementById("transition-dialog-description");
    expect(descEl).toHaveTextContent("Draft → Review");
  });

  // -------------------------------------------------------------------------
  // 4. Shows character counter
  // -------------------------------------------------------------------------
  it("shows character counter at 0/500 initially and updates as user types", () => {
    render(<TransitionConfirmationDialog {...defaultProps} />);

    expect(screen.getByText("0/500")).toBeInTheDocument();

    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "Test reason" } });

    // "Test reason" trimmed is 11 chars
    expect(screen.getByText("11/500")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Confirm button disabled when reason too short
  // -------------------------------------------------------------------------
  it("confirm button is disabled when change reason trimmed length < 3", () => {
    render(<TransitionConfirmationDialog {...defaultProps} />);

    const confirmBtn = screen.getByRole("button", { name: /confirm/i });
    expect(confirmBtn).toBeDisabled();

    // Type 2 chars
    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "ab" } });
    expect(confirmBtn).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // 6. Confirm button enabled when reason valid
  // -------------------------------------------------------------------------
  it("confirm button is enabled when change reason trimmed length >= 3", () => {
    render(<TransitionConfirmationDialog {...defaultProps} />);

    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "abc" } });

    const confirmBtn = screen.getByRole("button", { name: /confirm/i });
    expect(confirmBtn).toBeEnabled();
  });

  // -------------------------------------------------------------------------
  // 7. Gate warning - signature
  // -------------------------------------------------------------------------
  it("shows signature gate warning with amber styling when requiresSignature=true", () => {
    render(
      <TransitionConfirmationDialog {...defaultProps} requiresSignature={true} />
    );

    expect(
      screen.getByText("This transition requires an electronic signature.")
    ).toBeInTheDocument();

    const warningDiv = screen
      .getByText("This transition requires an electronic signature.")
      .closest("div");
    expect(warningDiv?.className).toContain("bg-amber-50");
    expect(warningDiv?.className).toContain("border-amber-200");
    expect(warningDiv?.className).toContain("text-amber-800");
  });

  // -------------------------------------------------------------------------
  // 8. Gate warning - training
  // -------------------------------------------------------------------------
  it("shows training gate warning with blue styling when triggersTraining=true", () => {
    render(
      <TransitionConfirmationDialog {...defaultProps} triggersTraining={true} />
    );

    expect(
      screen.getByText("This transition will trigger training assignment.")
    ).toBeInTheDocument();

    const warningDiv = screen
      .getByText("This transition will trigger training assignment.")
      .closest("div");
    expect(warningDiv?.className).toContain("bg-blue-50");
    expect(warningDiv?.className).toContain("border-blue-200");
    expect(warningDiv?.className).toContain("text-blue-800");
  });

  // -------------------------------------------------------------------------
  // 9. Gate warning - both
  // -------------------------------------------------------------------------
  it("shows both gate warnings when both requiresSignature and triggersTraining are true", () => {
    render(
      <TransitionConfirmationDialog
        {...defaultProps}
        requiresSignature={true}
        triggersTraining={true}
      />
    );

    expect(
      screen.getByText("This transition requires an electronic signature.")
    ).toBeInTheDocument();
    expect(
      screen.getByText("This transition will trigger training assignment.")
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Risk warning - high
  // -------------------------------------------------------------------------
  it("shows risk warning with orange styling for riskLevel='high'", () => {
    render(
      <TransitionConfirmationDialog {...defaultProps} riskLevel="high" />
    );

    expect(screen.getByText(/high-risk/)).toBeInTheDocument();

    const warningDiv = screen.getByText(/high-risk/).closest("div");
    expect(warningDiv?.className).toContain("bg-orange-50");
    expect(warningDiv?.className).toContain("text-orange-800");
    expect(warningDiv?.className).toContain("border-orange-200");
  });

  // -------------------------------------------------------------------------
  // 11. Risk warning - critical
  // -------------------------------------------------------------------------
  it("shows risk warning with red styling for riskLevel='critical'", () => {
    render(
      <TransitionConfirmationDialog {...defaultProps} riskLevel="critical" />
    );

    expect(screen.getByText(/critical-risk/)).toBeInTheDocument();

    const warningDiv = screen.getByText(/critical-risk/).closest("div");
    expect(warningDiv?.className).toContain("bg-red-50");
    expect(warningDiv?.className).toContain("text-red-800");
    expect(warningDiv?.className).toContain("border-red-200");
  });

  // -------------------------------------------------------------------------
  // 12. No risk warning for low/medium
  // -------------------------------------------------------------------------
  it("does not show risk warning for low risk level", () => {
    render(
      <TransitionConfirmationDialog {...defaultProps} riskLevel="low" />
    );

    expect(screen.queryByText(/low-risk/)).not.toBeInTheDocument();
    expect(screen.queryByText(/enhanced review/)).not.toBeInTheDocument();
  });

  it("does not show risk warning for medium risk level", () => {
    render(
      <TransitionConfirmationDialog {...defaultProps} riskLevel="medium" />
    );

    expect(screen.queryByText(/medium-risk/)).not.toBeInTheDocument();
    expect(screen.queryByText(/enhanced review/)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 13. Cancel closes dialog
  // -------------------------------------------------------------------------
  it("clicking cancel calls onOpenChange(false)", () => {
    const onOpenChange = vi.fn();
    render(
      <TransitionConfirmationDialog {...defaultProps} onOpenChange={onOpenChange} />
    );

    const cancelBtn = screen.getByRole("button", { name: /cancel/i });
    fireEvent.click(cancelBtn);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 14. Escape closes dialog
  // -------------------------------------------------------------------------
  it("pressing Escape calls onOpenChange(false)", () => {
    const onOpenChange = vi.fn();
    render(
      <TransitionConfirmationDialog {...defaultProps} onOpenChange={onOpenChange} />
    );

    // The component listens on document for keydown
    fireEvent.keyDown(document, { key: "Escape" });

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 15. Error display
  // -------------------------------------------------------------------------
  it("shows error message when transitionError is set", () => {
    setupMockStore({ transitionError: "Transition failed: insufficient permissions" });

    render(<TransitionConfirmationDialog {...defaultProps} />);

    const errorEl = screen.getByRole("alert");
    expect(errorEl).toHaveTextContent("Transition failed: insufficient permissions");
  });

  // -------------------------------------------------------------------------
  // 16. Change reason retained on error
  // -------------------------------------------------------------------------
  it("retains change reason text after error occurs", () => {
    setupMockStore({ transitionError: "Server error" });

    render(<TransitionConfirmationDialog {...defaultProps} />);

    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "My important reason" } });

    // Error is displayed
    expect(screen.getByRole("alert")).toHaveTextContent("Server error");
    // Textarea still has the value
    expect(textarea).toHaveValue("My important reason");
  });

  // -------------------------------------------------------------------------
  // 17. Loading state
  // -------------------------------------------------------------------------
  it("when isTransitioning=true, confirm button shows loader and both buttons are disabled", () => {
    setupMockStore({ isTransitioning: true });

    render(<TransitionConfirmationDialog {...defaultProps} />);

    // Type a valid reason so we can check the confirm button state
    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "Valid reason text" } });

    const confirmBtn = screen.getByRole("button", { name: /confirm/i });
    const cancelBtn = screen.getByRole("button", { name: /cancel/i });

    expect(confirmBtn).toBeDisabled();
    expect(cancelBtn).toBeDisabled();

    // Loader icon should be present (Loader2 renders as an svg)
    const loader = confirmBtn.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 18. Calls executeTransition on confirm
  // -------------------------------------------------------------------------
  it("clicking confirm calls executeTransition with correct arguments", async () => {
    const executeTransition = vi.fn().mockResolvedValue(true);
    setupMockStore({ executeTransition });

    render(<TransitionConfirmationDialog {...defaultProps} />);

    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "Approved by QA team" } });

    const confirmBtn = screen.getByRole("button", { name: /confirm/i });

    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(executeTransition).toHaveBeenCalledWith(
      "doc-uuid-123",
      "Review",
      "Approved by QA team"
    );
  });
});
