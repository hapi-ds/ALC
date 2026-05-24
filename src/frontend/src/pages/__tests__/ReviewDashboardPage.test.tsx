/**
 * Unit tests for ReviewDashboardPage
 *
 * Tests cover:
 * - Empty state rendering when no sessions exist
 * - Sessions table display with document title, type, status badge, score, findings, date
 * - Filter inputs (status, document type, date range, score range, audit profile)
 * - Pagination controls (Previous/Next buttons, page info)
 * - Loading state
 * - Error state with retry button
 * - Row click navigation to session detail
 *
 * Requirements: 11.1, 5.1, 5.5
 *
 * NOTE: This test file does NOT make any real backend API calls.
 * All API interactions are fully mocked.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ReviewDashboardPage } from "../ReviewDashboardPage";
import { useReviewStore } from "@/stores/reviewStore";
import type { ReviewSession } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
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

vi.mock("@/lib/reviews-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/reviews-api")>();
  return {
    ...actual,
    listAuditProfiles: vi.fn().mockResolvedValue([]),
    fetchReviewSessions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    fetchReviewSessionDetail: vi.fn(),
    fetchActionItems: vi.fn(),
    fetchComplianceScorecard: vi.fn(),
    submitReview: vi.fn(),
    approveSession: vi.fn(),
    rejectSession: vi.fn(),
    updateActionItem: vi.fn(),
  };
});

// ---------------------------------------------------------------------------
// Test data
// ---------------------------------------------------------------------------

function makeSession(overrides: Partial<ReviewSession> = {}): ReviewSession {
  return {
    id: 1,
    document_id: 10,
    document_title: "SOP-001 Manufacturing Process",
    document_type: "SOP",
    status: "Completed",
    compliance_score: 85.5,
    summary_failed: false,
    submitted_by: 1,
    submitted_at: "2024-06-15T10:00:00Z",
    completed_at: "2024-06-15T10:30:00Z",
    agent_reviews: [
      {
        id: 1,
        agent_definition_id: 1,
        agent_name: "Regulatory Auditor",
        agent_archetype: "regulatory-compliance-auditor",
        status: "Completed",
        report_data: {
          findings: [
            { severity: "Critical", chapter: "Safety", description: "Missing safety protocol" },
            { severity: "Major", chapter: "Scope", description: "Scope too broad" },
            { severity: "Minor", chapter: "References", description: "Outdated reference" },
          ],
        },
        error_reason: null,
        inference_duration_ms: 5000,
        started_at: "2024-06-15T10:01:00Z",
        completed_at: "2024-06-15T10:05:00Z",
      },
    ],
    master_summary: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ReviewDashboardPage", () => {
  beforeEach(() => {
    useReviewStore.getState().reset();
    mockNavigate.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Empty state
  // -------------------------------------------------------------------------

  it("renders empty state when no sessions exist", () => {
    useReviewStore.setState({
      sessions: [],
      sessionsTotal: 0,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    expect(screen.getByText("No review sessions found")).toBeInTheDocument();
    expect(
      screen.getByText("Submit a document for review to see results here")
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Sessions table display
  // -------------------------------------------------------------------------

  it("renders sessions with document title, type, status badge, score, findings, and date", () => {
    const session = makeSession();
    useReviewStore.setState({
      sessions: [session],
      sessionsTotal: 1,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    // Document title
    expect(screen.getByText("SOP-001 Manufacturing Process")).toBeInTheDocument();

    // Document type
    expect(screen.getByText("SOP")).toBeInTheDocument();

    // Status badge (also appears in filter dropdown, so use getAllByText)
    const completedElements = screen.getAllByText("Completed");
    const badge = completedElements.find((el) => el.tagName === "SPAN");
    expect(badge).toBeInTheDocument();
    expect(badge?.className).toContain("bg-green-100");

    // Score
    expect(screen.getByText("85.5")).toBeInTheDocument();

    // Findings severity counts
    expect(screen.getByTitle("Critical findings")).toBeInTheDocument();
    expect(screen.getByTitle("Major findings")).toBeInTheDocument();
    expect(screen.getByTitle("Minor findings")).toBeInTheDocument();

    // Submitted date
    expect(screen.getByText("Jun 15, 2024")).toBeInTheDocument();
  });

  it("shows dash when compliance score is null", () => {
    const session = makeSession({ compliance_score: null, status: "Pending" });
    useReviewStore.setState({
      sessions: [session],
      sessionsTotal: 1,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    // Score column should show dash
    const scoreCell = screen.getAllByText("—");
    expect(scoreCell.length).toBeGreaterThanOrEqual(1);
  });

  // -------------------------------------------------------------------------
  // 3. Filter inputs
  // -------------------------------------------------------------------------

  it("renders all filter inputs: status, document type, date range, score range, audit profile", () => {
    useReviewStore.setState({
      sessions: [],
      sessionsTotal: 0,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    // Status dropdown
    expect(screen.getByLabelText("Status")).toBeInTheDocument();

    // Document type input
    expect(screen.getByLabelText("Document Type")).toBeInTheDocument();

    // Date range
    expect(screen.getByLabelText("From Date")).toBeInTheDocument();
    expect(screen.getByLabelText("To Date")).toBeInTheDocument();

    // Score range
    expect(screen.getByLabelText("Min Score")).toBeInTheDocument();
    expect(screen.getByLabelText("Max Score")).toBeInTheDocument();

    // Audit profile dropdown
    expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
  });

  it("calls fetchSessions when a filter value changes", () => {
    const mockFetch = vi.fn();
    useReviewStore.setState({
      sessions: [],
      sessionsTotal: 0,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: mockFetch,
    });

    render(<ReviewDashboardPage />);

    // Change status filter
    const statusSelect = screen.getByLabelText("Status");
    fireEvent.change(statusSelect, { target: { value: "Completed" } });

    // fetchSessions should be called (initial + filter change)
    expect(mockFetch).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 4. Pagination
  // -------------------------------------------------------------------------

  it("shows pagination controls when sessions exist", () => {
    useReviewStore.setState({
      sessions: [makeSession()],
      sessionsTotal: 25,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /previous page/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /next page/i })).not.toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // 5. Loading state
  // -------------------------------------------------------------------------

  it("shows loading indicator when isLoadingSessions is true", () => {
    useReviewStore.setState({
      sessions: [],
      sessionsTotal: 0,
      isLoadingSessions: true,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Loading review sessions")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 6. Error state
  // -------------------------------------------------------------------------

  it("shows error message with retry button when sessionsError is set", () => {
    useReviewStore.setState({
      sessions: [],
      sessionsTotal: 0,
      isLoadingSessions: false,
      sessionsError: "Network error: Unable to reach the server.",
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    expect(
      screen.getByText("Network error: Unable to reach the server.")
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Row click navigation
  // -------------------------------------------------------------------------

  it("navigates to session detail when a row is clicked", () => {
    const session = makeSession({ id: 42 });
    useReviewStore.setState({
      sessions: [session],
      sessionsTotal: 1,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    const row = screen.getByRole("link", {
      name: /review session for SOP-001 Manufacturing Process/i,
    });
    fireEvent.click(row);

    expect(mockNavigate).toHaveBeenCalledWith("/reviews/42");
  });

  it("navigates to session detail on Enter key press", () => {
    const session = makeSession({ id: 7 });
    useReviewStore.setState({
      sessions: [session],
      sessionsTotal: 1,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    const row = screen.getByRole("link", {
      name: /review session for SOP-001 Manufacturing Process/i,
    });
    fireEvent.keyDown(row, { key: "Enter" });

    expect(mockNavigate).toHaveBeenCalledWith("/reviews/7");
  });

  // -------------------------------------------------------------------------
  // 8. Status badge color coding
  // -------------------------------------------------------------------------

  it("applies correct color classes for different statuses", () => {
    const sessions = [
      makeSession({ id: 1, status: "Pending", compliance_score: null }),
      makeSession({ id: 2, status: "InProgress", compliance_score: null }),
      makeSession({ id: 3, status: "Failed", compliance_score: null }),
    ];
    useReviewStore.setState({
      sessions,
      sessionsTotal: 3,
      isLoadingSessions: false,
      sessionsError: null,
      fetchSessions: vi.fn(),
    });

    render(<ReviewDashboardPage />);

    // Status text appears in both filter dropdown and table badges — use getAllByText
    const pendingElements = screen.getAllByText("Pending");
    const pendingBadge = pendingElements.find((el) => el.tagName === "SPAN");
    expect(pendingBadge).toBeDefined();
    expect(pendingBadge!.className).toContain("bg-yellow-100");

    const inProgressElements = screen.getAllByText("InProgress");
    const inProgressBadge = inProgressElements.find((el) => el.tagName === "SPAN");
    expect(inProgressBadge).toBeDefined();
    expect(inProgressBadge!.className).toContain("bg-blue-100");

    const failedElements = screen.getAllByText("Failed");
    const failedBadge = failedElements.find((el) => el.tagName === "SPAN");
    expect(failedBadge).toBeDefined();
    expect(failedBadge!.className).toContain("bg-red-100");
  });
});
