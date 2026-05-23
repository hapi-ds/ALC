import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { render, screen, cleanup, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TrainingGateGuard } from "../../../components/training/TrainingGateGuard";
import { useTrainingStore } from "../../../stores/trainingStore";
import { useAuthStore } from "../../../stores/authStore";

/**
 * Unit tests for TrainingGateGuard component.
 *
 * Validates: Requirements 8.1–8.7, 11.10
 */

// ---------------------------------------------------------------------------
// Mock stores
// ---------------------------------------------------------------------------

vi.mock("../../../stores/trainingStore", () => ({
  useTrainingStore: vi.fn(),
}));

vi.mock("../../../stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockedUseTrainingStore = useTrainingStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function createMockTrainingStore(overrides: Record<string, unknown> = {}) {
  return {
    checkTrainingGate: vi.fn().mockReturnValue(null),
    fetchTrainingTasks: vi.fn().mockResolvedValue(undefined),
    hasFetchedTasks: false,
    checkQuizPassed: vi.fn().mockResolvedValue(true),
    quizPassCache: {},
    isCheckingQuizPass: false,
    quizPassError: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingGateGuard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedUseAuthStore.mockImplementation((selector: (state: unknown) => unknown) => {
      const state = { user: { id: 42, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["user"] } };
      return selector(state);
    });
    mockedUseTrainingStore.mockReturnValue(createMockTrainingStore());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Gate pass-through for non-InTraining statuses (Requirement 8.7)
  // -------------------------------------------------------------------------

  describe("pass-through for non-InTraining statuses", () => {
    it("renders children directly when sopStatus is 'Active'", () => {
      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="Active"
        >
          <div data-testid="child-content">Document Content</div>
        </TrainingGateGuard>
      );

      expect(screen.getByTestId("child-content")).toBeDefined();
      expect(screen.getByText("Document Content")).toBeDefined();
    });

    it("renders children directly when sopStatus is 'Draft'", () => {
      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="Draft"
        >
          <div data-testid="child-content">Draft Document</div>
        </TrainingGateGuard>
      );

      expect(screen.getByTestId("child-content")).toBeDefined();
    });

    it("renders children directly when sopStatus is empty string", () => {
      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus=""
        >
          <div data-testid="child-content">Content</div>
        </TrainingGateGuard>
      );

      expect(screen.getByTestId("child-content")).toBeDefined();
    });

    it("does not call checkTrainingGate for non-InTraining statuses", () => {
      const checkTrainingGate = vi.fn();
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({ checkTrainingGate, hasFetchedTasks: true })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="Active"
        >
          <div>Content</div>
        </TrainingGateGuard>
      );

      expect(checkTrainingGate).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Gate blocking for incomplete training (Requirement 8.2)
  // -------------------------------------------------------------------------

  describe("blocking for incomplete training", () => {
    it("shows blocking message with role='alert' when training is incomplete", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: true,
          checkTrainingGate: vi.fn().mockReturnValue(false),
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="2.0"
          sopStatus="InTraining"
        >
          <div data-testid="child-content">Should not appear</div>
        </TrainingGateGuard>
      );

      // Should show blocking message
      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(screen.getByText("Training Required")).toBeDefined();
      expect(screen.getByText(/Valid training record for this SOP Version 2.0 is missing/)).toBeDefined();

      // Children should NOT be rendered
      expect(screen.queryByTestId("child-content")).toBeNull();
    });

    it("provides a link to /training when blocking", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: true,
          checkTrainingGate: vi.fn().mockReturnValue(false),
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div>Content</div>
        </TrainingGateGuard>
      );

      const link = screen.getByRole("link", { name: /go to training/i });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toBe("/training");
    });
  });

  // -------------------------------------------------------------------------
  // Gate allowing for complete training (Requirement 8.3)
  // -------------------------------------------------------------------------

  describe("allowing for complete training", () => {
    it("renders children when training is complete and quiz is passed", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: true,
          checkTrainingGate: vi.fn().mockReturnValue(true),
          quizPassCache: {
            "sop-123_v1.0": {
              content_id: "sop-123_v1.0",
              user_id: 42,
              has_passed: true,
              best_score: 5,
            },
          },
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div data-testid="child-content">Protected Document</div>
        </TrainingGateGuard>
      );

      expect(screen.getByTestId("child-content")).toBeDefined();
      expect(screen.getByText("Protected Document")).toBeDefined();
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Loading state (Requirement 8.1, 8.5)
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("shows loading indicator when hasFetchedTasks is false", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: false,
          fetchTrainingTasks: vi.fn().mockReturnValue(new Promise(() => {})), // never resolves
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div data-testid="child-content">Content</div>
        </TrainingGateGuard>
      );

      expect(screen.getByText(/Verifying training status/)).toBeDefined();
      expect(screen.queryByTestId("child-content")).toBeNull();
    });

    it("triggers fetchTrainingTasks when tasks not yet loaded", () => {
      const fetchTrainingTasks = vi.fn().mockReturnValue(new Promise(() => {}));
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: false,
          fetchTrainingTasks,
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div>Content</div>
        </TrainingGateGuard>
      );

      expect(fetchTrainingTasks).toHaveBeenCalledWith(42);
    });
  });

  // -------------------------------------------------------------------------
  // Timeout behavior (Requirement 8.5)
  // -------------------------------------------------------------------------

  describe("timeout behavior", () => {
    it("shows error state after 10 seconds timeout", async () => {
      const fetchTrainingTasks = vi.fn().mockReturnValue(new Promise(() => {})); // never resolves
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: false,
          fetchTrainingTasks,
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div data-testid="child-content">Content</div>
        </TrainingGateGuard>
      );

      // Initially shows loading
      expect(screen.getByText(/Verifying training status/)).toBeDefined();

      // Advance time by 10 seconds
      await act(async () => {
        vi.advanceTimersByTime(10_000);
      });

      // Should show timeout error
      expect(screen.getByText("Unable to verify training status")).toBeDefined();
      expect(screen.getByText(/timed out/)).toBeDefined();
      expect(screen.queryByTestId("child-content")).toBeNull();
    });

    it("shows retry button after timeout", async () => {
      const fetchTrainingTasks = vi.fn().mockReturnValue(new Promise(() => {}));
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: false,
          fetchTrainingTasks,
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div>Content</div>
        </TrainingGateGuard>
      );

      await act(async () => {
        vi.advanceTimersByTime(10_000);
      });

      const retryButton = screen.getByRole("button", { name: /retry/i });
      expect(retryButton).toBeDefined();
    });

    it("does not show timeout if fetch resolves before 10 seconds", async () => {
      let resolvePromise: () => void;
      const fetchPromise = new Promise<void>((resolve) => {
        resolvePromise = resolve;
      });
      const fetchTrainingTasks = vi.fn().mockReturnValue(fetchPromise);

      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: false,
          fetchTrainingTasks,
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div>Content</div>
        </TrainingGateGuard>
      );

      // Advance 5 seconds (less than timeout)
      await act(async () => {
        vi.advanceTimersByTime(5_000);
      });

      // Resolve the fetch
      await act(async () => {
        resolvePromise!();
      });

      // Should not show timeout error
      expect(screen.queryByText("Unable to verify training status")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Gate check with null result (loading needed) (Requirement 8.1)
  // -------------------------------------------------------------------------

  describe("gate check returns null", () => {
    it("shows loading when checkTrainingGate returns null", () => {
      mockedUseTrainingStore.mockReturnValue(
        createMockTrainingStore({
          hasFetchedTasks: true,
          checkTrainingGate: vi.fn().mockReturnValue(null),
        })
      );

      renderWithRouter(
        <TrainingGateGuard
          sopDocumentUuid="sop-123"
          sopVersion="1.0"
          sopStatus="InTraining"
        >
          <div data-testid="child-content">Content</div>
        </TrainingGateGuard>
      );

      expect(screen.getByText(/Verifying training status/)).toBeDefined();
      expect(screen.queryByTestId("child-content")).toBeNull();
    });
  });
});
