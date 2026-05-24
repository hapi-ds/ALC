import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TrainingEcosystemPage } from "../../pages/TrainingEcosystemPage";
import { useTrainingEcosystemStore } from "../../stores/trainingEcosystemStore";
import { useAuthStore } from "../../stores/authStore";

/**
 * Unit tests for TrainingEcosystemPage component.
 *
 * Validates: Requirements 10.1, 10.2, 10.9
 */

vi.mock("../../stores/trainingEcosystemStore", () => ({
  useTrainingEcosystemStore: vi.fn(),
}));

vi.mock("../../stores/authStore", () => ({
  useAuthStore: vi.fn(),
}));

// Mock child components to isolate page-level behavior
vi.mock("../../components/training/TrainingSchedulePanel", () => ({
  TrainingSchedulePanel: ({ schedule, isLoading, error }: { schedule: unknown; isLoading: boolean; error: string | null }) => (
    <div data-testid="schedule-panel">
      {isLoading && <span>Loading schedule...</span>}
      {error && <span>Error: {error}</span>}
      {schedule && <span>Schedule loaded</span>}
    </div>
  ),
}));

vi.mock("../../components/training/SkillGapAlert", () => ({
  SkillGapAlert: ({ gaps }: { gaps: unknown[] }) => (
    <div data-testid="skill-gap-alert">Gaps: {gaps.length}</div>
  ),
}));

vi.mock("../../components/training/TrainingMaterialViewer", () => ({
  TrainingMaterialViewer: () => <div data-testid="material-viewer">Materials</div>,
}));

vi.mock("../../components/training/VirtualAuditInterface", () => ({
  VirtualAuditInterface: () => <div data-testid="virtual-audit">Virtual Audit</div>,
}));

vi.mock("../../components/training/DynamicFeedbackPanel", () => ({
  DynamicFeedbackPanel: () => <div data-testid="feedback-panel">Feedback</div>,
}));

vi.mock("../../components/training/JobMonitor", () => ({
  JobMonitor: ({ jobs }: { jobs: unknown[] }) => (
    <div data-testid="job-monitor">Jobs: {jobs.length}</div>
  ),
}));

const mockedUseStore = useTrainingEcosystemStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Default mock state
// ---------------------------------------------------------------------------

const defaultStoreState = {
  schedule: null,
  skillGaps: [],
  materials: {},
  pendingJobs: [],
  isLoadingSchedule: false,
  isLoadingGaps: false,
  isLoadingMaterials: false,
  scheduleError: null,
  gapsError: null,
  fetchSchedule: vi.fn(),
  fetchGaps: vi.fn(),
  fetchMaterials: vi.fn(),
  startPolling: vi.fn(),
  stopPolling: vi.fn(),
};

function renderPage(initialRoute = "/training/ecosystem") {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <TrainingEcosystemPage />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingEcosystemPage", () => {
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
  // Page structure
  // -------------------------------------------------------------------------

  describe("page structure", () => {
    it("renders page heading", () => {
      renderPage();

      expect(screen.getByText("AI Training Ecosystem")).toBeDefined();
    });

    it("renders main landmark with aria-label", () => {
      renderPage();

      expect(screen.getByRole("main", { name: /ai training ecosystem/i })).toBeDefined();
    });

    it("renders tab navigation with all tabs", () => {
      renderPage();

      expect(screen.getByRole("tablist")).toBeDefined();
      expect(screen.getByRole("tab", { name: "Schedule" })).toBeDefined();
      expect(screen.getByRole("tab", { name: "Materials" })).toBeDefined();
      expect(screen.getByRole("tab", { name: "Assessments" })).toBeDefined();
      expect(screen.getByRole("tab", { name: "Virtual Audit" })).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Tab navigation
  // -------------------------------------------------------------------------

  describe("tab navigation", () => {
    it("shows schedule panel by default", () => {
      renderPage();

      expect(screen.getByTestId("schedule-panel")).toBeDefined();
    });

    it("shows materials panel when Materials tab is clicked", () => {
      renderPage();

      fireEvent.click(screen.getByRole("tab", { name: "Materials" }));

      expect(screen.getByTestId("material-viewer")).toBeDefined();
    });

    it("shows assessments panel when Assessments tab is clicked", () => {
      renderPage();

      fireEvent.click(screen.getByRole("tab", { name: "Assessments" }));

      expect(screen.getByTestId("feedback-panel")).toBeDefined();
    });

    it("shows virtual audit panel when Virtual Audit tab is clicked", () => {
      renderPage();

      fireEvent.click(screen.getByRole("tab", { name: "Virtual Audit" }));

      expect(screen.getByTestId("virtual-audit")).toBeDefined();
    });

    it("marks active tab with aria-selected=true", () => {
      renderPage();

      const scheduleTab = screen.getByRole("tab", { name: "Schedule" });
      expect(scheduleTab.getAttribute("aria-selected")).toBe("true");

      const materialsTab = screen.getByRole("tab", { name: "Materials" });
      expect(materialsTab.getAttribute("aria-selected")).toBe("false");
    });
  });

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  describe("data fetching", () => {
    it("calls fetchSchedule and fetchGaps on mount with user id", () => {
      const fetchSchedule = vi.fn();
      const fetchGaps = vi.fn();
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        fetchSchedule,
        fetchGaps,
      });

      renderPage();

      expect(fetchSchedule).toHaveBeenCalledWith(42);
      expect(fetchGaps).toHaveBeenCalledWith(42);
    });
  });

  // -------------------------------------------------------------------------
  // Skill Gap Alert
  // -------------------------------------------------------------------------

  describe("skill gap alert", () => {
    it("shows alert when critical gaps exist", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        skillGaps: [
          { id: 1, priority: "Critical", document_id: 1, document_title: "Doc", gap_type: "missing_training", days_overdue: 5, blocks_access: true, identified_at: "2024-01-01" },
        ],
      });

      renderPage();

      expect(screen.getByTestId("skill-gap-alert")).toBeDefined();
    });

    it("shows alert when high priority gaps exist", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        skillGaps: [
          { id: 1, priority: "High", document_id: 1, document_title: "Doc", gap_type: "missing_training", days_overdue: 15, blocks_access: false, identified_at: "2024-01-01" },
        ],
      });

      renderPage();

      expect(screen.getByTestId("skill-gap-alert")).toBeDefined();
    });

    it("does not show alert when only low/medium gaps exist", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        skillGaps: [
          { id: 1, priority: "Low", document_id: 1, document_title: "Doc", gap_type: "missing_training", days_overdue: null, blocks_access: false, identified_at: "2024-01-01" },
        ],
      });

      renderPage();

      expect(screen.queryByTestId("skill-gap-alert")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Job Monitor
  // -------------------------------------------------------------------------

  describe("job monitor", () => {
    it("shows job monitor when pending jobs exist", () => {
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        pendingJobs: [{ job_id: "job-1", status: "pending" }],
      });

      renderPage();

      expect(screen.getByTestId("job-monitor")).toBeDefined();
    });

    it("does not show job monitor when no pending jobs", () => {
      renderPage();

      expect(screen.queryByTestId("job-monitor")).toBeNull();
    });

    it("starts polling when pending jobs exist", () => {
      const startPolling = vi.fn();
      mockedUseStore.mockReturnValue({
        ...defaultStoreState,
        pendingJobs: [{ job_id: "job-1", status: "pending" }],
        startPolling,
      });

      renderPage();

      expect(startPolling).toHaveBeenCalled();
    });
  });
});
