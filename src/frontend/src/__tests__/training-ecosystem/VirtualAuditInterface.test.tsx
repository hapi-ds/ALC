import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { VirtualAuditInterface } from "../../components/training/VirtualAuditInterface";
import { useTrainingEcosystemStore } from "../../stores/trainingEcosystemStore";
import { useAuthStore } from "../../stores/authStore";

/**
 * Unit tests for VirtualAuditInterface component.
 *
 * Validates: Requirements 10.5
 */

// Mock scrollIntoView which is not available in jsdom
Element.prototype.scrollIntoView = vi.fn();

vi.mock("../../stores/trainingEcosystemStore", () => ({
  useTrainingEcosystemStore: vi.fn(),
}));

vi.mock("../../stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockedUseStore = useTrainingEcosystemStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const defaultStoreState = {
  activeSession: null,
  lastEvaluation: null,
  isLoadingSession: false,
  isSubmittingResponse: false,
  sessionError: null,
  responseError: null,
  startRolePlay: vi.fn(),
  submitResponse: vi.fn(),
};

const activeSession = {
  id: 1,
  user_id: 42,
  document_id: 10,
  status: "in_progress",
  overall_score: null,
  passed: null,
  turns_completed: 2,
  total_turns: 7,
  session_data: {
    first_question: "What is the purpose of this SOP?",
    turns: [
      {
        question: "What is the purpose of this SOP?",
        response: "It defines chemical handling procedures.",
        evaluation: { factual_accuracy: 0.8, completeness: 0.7, document_reference_quality: 0.6 },
      },
      {
        question: "What PPE is required?",
        response: "Gloves, goggles, and lab coat.",
        evaluation: { factual_accuracy: 0.9, completeness: 0.5, document_reference_quality: 0.3 },
      },
    ],
  },
  summary_data: null,
  started_at: "2024-01-15T10:00:00Z",
  completed_at: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VirtualAuditInterface", () => {
  beforeEach(() => {
    mockedUseAuthStore.mockImplementation((selector: (state: unknown) => unknown) => {
      const state = { user: { id: 42, username: "testuser" } };
      return selector(state);
    });
    mockedUseStore.mockReturnValue(defaultStoreState);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // No session state
  // -------------------------------------------------------------------------

  describe("no active session", () => {
    it("renders empty state message when no session and not loading", () => {
      render(<VirtualAuditInterface />);

      expect(
        screen.getByText(/start a virtual audit session/i)
      ).toBeDefined();
    });

    it("has section with aria-label 'Virtual audit'", () => {
      render(<VirtualAuditInterface />);

      expect(screen.getByLabelText("Virtual audit")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("shows loading indicator when session is starting", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        isLoadingSession: true,
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText("Starting session...")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Chat bubbles
  // -------------------------------------------------------------------------

  describe("chat bubbles", () => {
    it("renders auditor and user messages from session data", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      // Auditor questions
      expect(screen.getByText("What is the purpose of this SOP?")).toBeDefined();
      expect(screen.getByText("What PPE is required?")).toBeDefined();

      // User responses
      expect(screen.getByText("It defines chemical handling procedures.")).toBeDefined();
      expect(screen.getByText("Gloves, goggles, and lab coat.")).toBeDefined();
    });

    it("renders conversation log with role='log'", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByRole("log")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Score indicators
  // -------------------------------------------------------------------------

  describe("score indicators", () => {
    it("shows score labels for user messages with evaluations", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      // First response: avg of (0.8 + 0.7 + 0.6) / 3 = 0.7 → "Good"
      expect(screen.getByText(/Good/)).toBeDefined();
      // Second response: avg of (0.9 + 0.5 + 0.3) / 3 ≈ 0.567 → "Fair"
      expect(screen.getByText(/Fair/)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Turn progress
  // -------------------------------------------------------------------------

  describe("turn progress", () => {
    it("shows turn progress text", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText("Turn 2 of 7")).toBeDefined();
    });

    it("renders progress bar with correct percentage", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      const progressbar = screen.getByRole("progressbar");
      // 2/7 = 29%
      expect(progressbar.getAttribute("aria-valuenow")).toBe("29");
    });

    it("progress bar has descriptive aria-label", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      const progressbar = screen.getByRole("progressbar");
      expect(progressbar.getAttribute("aria-label")).toContain("2 of 7 turns completed");
    });
  });

  // -------------------------------------------------------------------------
  // Response input
  // -------------------------------------------------------------------------

  describe("response input", () => {
    it("renders textarea for response when session is active", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      const textarea = screen.getByLabelText("Your response to the auditor");
      expect(textarea).toBeDefined();
    });

    it("shows character count", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText("0/2000")).toBeDefined();
    });

    it("updates character count as user types", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      const textarea = screen.getByLabelText("Your response to the auditor");
      fireEvent.change(textarea, { target: { value: "Hello" } });

      expect(screen.getByText("5/2000")).toBeDefined();
    });

    it("has a send button", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByLabelText("Send response")).toBeDefined();
    });

    it("disables send button when textarea is empty", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
      });

      render(<VirtualAuditInterface />);

      const sendButton = screen.getByLabelText("Send response");
      expect(sendButton.hasAttribute("disabled")).toBe(true);
    });

    it("does not render input when session is completed", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession: { ...activeSession, status: "completed" },
      });

      render(<VirtualAuditInterface />);

      expect(screen.queryByLabelText("Your response to the auditor")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Session complete
  // -------------------------------------------------------------------------

  describe("session complete", () => {
    it("shows passed message when session is completed and passed", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession: {
          ...activeSession,
          status: "completed",
          passed: true,
          overall_score: 0.82,
        },
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText(/you passed the virtual audit/i)).toBeDefined();
      expect(screen.getByText(/Final score:.*82.*passing: 70%/)).toBeDefined();
    });

    it("shows failed message when session is completed and not passed", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession: {
          ...activeSession,
          status: "completed",
          passed: false,
          overall_score: 0.55,
        },
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText(/you did not meet the passing threshold/i)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Error display
  // -------------------------------------------------------------------------

  describe("error display", () => {
    it("shows session error when present", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
        sessionError: "Connection lost",
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText("Connection lost")).toBeDefined();
    });

    it("shows response error when present", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        activeSession,
        responseError: "Failed to submit response",
      });

      render(<VirtualAuditInterface />);

      expect(screen.getByText("Failed to submit response")).toBeDefined();
    });
  });
});
