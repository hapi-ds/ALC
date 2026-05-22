/**
 * Unit tests for SignatureDialog and sub-components
 *
 * Tests cover:
 * - SignatureDialog rendering (open/closed, document info display)
 * - Step rendering (reauth → sign → success)
 * - ReAuthForm (button disabled/enabled, error display)
 * - ReasonSelector (dropdown options, character counter, validation)
 * - TokenCountdown (format, warning styling)
 * - Cancel/Escape behavior
 *
 * Requirements: 1.2, 1.3, 2.1, 2.2, 2.6, 3.1, 3.3, 4.1, 4.3, 4.4, 4.6
 *
 * NOTE: This test file does NOT make any real backend API calls.
 * All API interactions are fully mocked via vi.mock("@/lib/apiClient").
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { SignatureDialog } from "../SignatureDialog";
import { ReAuthForm } from "../ReAuthForm";
import { ReasonSelector } from "../ReasonSelector";
import { TokenCountdown } from "../TokenCountdown";
import { useSignatureStore } from "@/stores/signatureStore";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import type { SignatureDialogContext } from "@/types/signature";

// ---------------------------------------------------------------------------
// Mocks — no real API calls are made; all backend interactions are mocked.
// ---------------------------------------------------------------------------

vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 1,
    }),
    setState: vi.fn(),
  },
}));

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

const mockDialogContext: SignatureDialogContext = {
  document_uuid: "doc-abc-123",
  document_version_id: 5,
  transition: "Review\u2192Approved",
  documentTitle: "SOP-001 Standard Operating Procedure",
};

// ---------------------------------------------------------------------------
// SignatureDialog rendering tests
// ---------------------------------------------------------------------------

describe("SignatureDialog rendering", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
    useWorkflowExecutionStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("does not render when isDialogOpen is false", () => {
    const { container } = render(<SignatureDialog />);
    expect(container.innerHTML).toBe("");
  });

  it("renders the dialog when isDialogOpen is true with dialogContext set", () => {
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
    });

    render(<SignatureDialog />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByText("Electronic Signature Required")
    ).toBeInTheDocument();
  });

  it("shows document title, current state, target state from dialogContext", () => {
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
    });

    render(<SignatureDialog />);

    expect(
      screen.getByText("SOP-001 Standard Operating Procedure")
    ).toBeInTheDocument();
    // Current state → Target state display
    expect(screen.getByText(/Review \u2192 Approved/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Step rendering tests
// ---------------------------------------------------------------------------

describe("Step rendering", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
    useWorkflowExecutionStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("initially shows the ReAuthForm (reauth step)", () => {
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
    });

    render(<SignatureDialog />);

    // ReAuthForm should be visible with its password input
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /verify identity/i })
    ).toBeInTheDocument();
  });

  it("shows sign step after signatureToken transitions from null to non-null", async () => {
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
      signatureToken: null,
    });

    const { rerender } = render(<SignatureDialog />);

    // Initially shows reauth step
    expect(screen.getByLabelText("Password")).toBeInTheDocument();

    // Simulate successful re-auth by setting the token
    useSignatureStore.setState({
      signatureToken: "token-abc-123",
      tokenExpiresAt: Date.now() + 120000,
      remainingSeconds: 120,
      _password: "testpass",
    });

    rerender(<SignatureDialog />);

    // After token is set, ReAuthForm's useEffect detects the transition and calls onSuccess
    await waitFor(() => {
      expect(screen.getByText("Token validity:")).toBeInTheDocument();
    });

    // ReasonSelector should be visible
    expect(screen.getByLabelText("Reason for Signature")).toBeInTheDocument();
    expect(screen.getByLabelText("Signature Note")).toBeInTheDocument();

    // TokenCountdown should show remaining seconds
    expect(screen.getByRole("timer")).toBeInTheDocument();
    expect(screen.getByText("120s")).toBeInTheDocument();
  });

  it("after signing success (lastSignResult becomes non-null), shows the success step with signer info", async () => {
    // Start in sign step by setting token directly
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
      signatureToken: null,
    });

    const { rerender } = render(<SignatureDialog />);

    // Transition to sign step
    useSignatureStore.setState({
      signatureToken: "token-abc",
      tokenExpiresAt: Date.now() + 120000,
      remainingSeconds: 100,
      _password: "pass",
    });

    rerender(<SignatureDialog />);

    await waitFor(() => {
      expect(screen.getByText("Token validity:")).toBeInTheDocument();
    });

    // Now simulate signing success
    useSignatureStore.setState({
      lastSignResult: {
        success: true,
        signature_hash:
          "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        signature_record_id: 42,
        stamp: {
          signer_name: "John Doe",
          signed_at: "2024-06-15T10:30:00Z",
          reason: "Approval: Approved by QA Manager",
          transition: "Review\u2192Approved",
        },
      },
    });

    rerender(<SignatureDialog />);

    await waitFor(() => {
      expect(
        screen.getByText("Signature Applied Successfully")
      ).toBeInTheDocument();
    });

    // Signer info
    expect(screen.getByText("John Doe")).toBeInTheDocument();
    expect(
      screen.getByText("Approval: Approved by QA Manager")
    ).toBeInTheDocument();
    // Truncated hash
    expect(screen.getByText("abcdef1234567890\u2026")).toBeInTheDocument();
    // Continue button
    expect(
      screen.getByRole("button", { name: /continue/i })
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ReAuthForm tests
// ---------------------------------------------------------------------------

describe("ReAuthForm", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('"Verify Identity" button is disabled when password input is empty', () => {
    render(
      <ReAuthForm
        onSuccess={vi.fn()}
        isLocked={false}
        lockoutRemaining={0}
      />
    );

    const button = screen.getByRole("button", { name: /verify identity/i });
    expect(button).toBeDisabled();
  });

  it('"Verify Identity" button is enabled when password has at least 1 character', () => {
    render(
      <ReAuthForm
        onSuccess={vi.fn()}
        isLocked={false}
        lockoutRemaining={0}
      />
    );

    const input = screen.getByLabelText("Password");
    fireEvent.change(input, { target: { value: "a" } });

    const button = screen.getByRole("button", { name: /verify identity/i });
    expect(button).not.toBeDisabled();
  });

  it("shows error message when reAuthError is set", () => {
    useSignatureStore.setState({
      reAuthError: "Invalid password. Please try again.",
    });

    render(
      <ReAuthForm
        onSuccess={vi.fn()}
        isLocked={false}
        lockoutRemaining={0}
      />
    );

    expect(
      screen.getByText("Invalid password. Please try again.")
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ReasonSelector tests
// ---------------------------------------------------------------------------

describe("ReasonSelector", () => {
  afterEach(() => {
    cleanup();
  });

  it("dropdown has 4 options (placeholder + Author/Review/Approval)", () => {
    render(
      <ReasonSelector
        reasonCategory=""
        signatureNote=""
        onReasonCategoryChange={vi.fn()}
        onSignatureNoteChange={vi.fn()}
        disabled={false}
      />
    );

    const select = screen.getByLabelText(
      "Reason for Signature"
    ) as HTMLSelectElement;
    const options = select.querySelectorAll("option");
    expect(options).toHaveLength(4);
    expect(options[0]).toHaveTextContent("Select a reason...");
    expect(options[1]).toHaveTextContent("Author");
    expect(options[2]).toHaveTextContent("Review");
    expect(options[3]).toHaveTextContent("Approval");
  });

  it("character counter shows current count out of 200", () => {
    render(
      <ReasonSelector
        reasonCategory="Author"
        signatureNote="Hello"
        onReasonCategoryChange={vi.fn()}
        onSignatureNoteChange={vi.fn()}
        disabled={false}
      />
    );

    expect(screen.getByText("5/200")).toBeInTheDocument();
  });

  it("validation message appears on blur when note is too short", () => {
    render(
      <ReasonSelector
        reasonCategory="Author"
        signatureNote="ab"
        onReasonCategoryChange={vi.fn()}
        onSignatureNoteChange={vi.fn()}
        disabled={false}
      />
    );

    const noteInput = screen.getByLabelText("Signature Note");
    fireEvent.blur(noteInput);

    expect(
      screen.getByText("Signature note must contain at least 3 characters")
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// TokenCountdown tests
// ---------------------------------------------------------------------------

describe("TokenCountdown", () => {
  afterEach(() => {
    cleanup();
  });

  it('displays remaining seconds in "{N}s" format', () => {
    render(<TokenCountdown remainingSeconds={85} />);
    expect(screen.getByRole("timer")).toHaveTextContent("85s");
  });

  it("shows warning styling when remainingSeconds <= 30", () => {
    render(<TokenCountdown remainingSeconds={25} />);
    const timer = screen.getByRole("timer");
    expect(timer.className).toContain("text-amber-600");
  });

  it("shows neutral styling when remainingSeconds > 30", () => {
    render(<TokenCountdown remainingSeconds={60} />);
    const timer = screen.getByRole("timer");
    expect(timer.className).toContain("text-muted-foreground");
    expect(timer.className).not.toContain("text-amber-600");
  });
});

// ---------------------------------------------------------------------------
// Cancel/Escape tests
// ---------------------------------------------------------------------------

describe("Cancel/Escape", () => {
  beforeEach(() => {
    useSignatureStore.getState().reset();
    useWorkflowExecutionStore.getState().reset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("Cancel button calls closeSignatureDialog", () => {
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
    });

    render(<SignatureDialog />);

    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButton);

    // After clicking cancel, the dialog should close
    const state = useSignatureStore.getState();
    expect(state.isDialogOpen).toBe(false);
  });

  it("Escape key calls closeSignatureDialog", () => {
    useSignatureStore.setState({
      isDialogOpen: true,
      dialogContext: mockDialogContext,
    });

    render(<SignatureDialog />);

    // Press Escape
    fireEvent.keyDown(document, { key: "Escape" });

    // Dialog should be closed
    const state = useSignatureStore.getState();
    expect(state.isDialogOpen).toBe(false);
  });
});
