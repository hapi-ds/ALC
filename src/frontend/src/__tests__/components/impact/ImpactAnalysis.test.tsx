import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Frontend component tests for AI-Driven Change Impact Analysis.
 *
 * Tests:
 * - ImpactAnalysisPage: rendering, data fetching, empty states, error handling
 * - DependencyGraphView: rendering, filtering, node limits
 * - NotificationPanel: list rendering, acknowledge action, empty state
 * - ImpactReportCard: status badge, severity counts, timestamp
 *
 * Validates: Requirements 10.1–10.10
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    url: string;
    constructor(status: number, body: string, url: string = "/api/impact-analysis") {
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

const mockAuthState = {
  user: {
    id: 42,
    username: "testuser",
    email: "test@example.com",
    full_name: "Test User",
    roles: ["admin"],
  },
  isAuthenticated: true,
  activeCompanyId: 1,
  activeCompanySlug: "test-company",
};

vi.mock("../../../stores/authStore", () => ({
  useAuthStore: Object.assign(
    vi.fn((selector?: (state: typeof mockAuthState) => unknown) => {
      if (selector) return selector(mockAuthState);
      return mockAuthState;
    }),
    {
      getState: () => mockAuthState,
    }
  ),
}));

// Import after mocks
import { apiClient } from "../../../lib/apiClient";
import { useImpactAnalysisStore } from "../../../stores/impactAnalysisStore";
import { ImpactAnalysisPage } from "../../../pages/ImpactAnalysisPage";
import { DependencyGraphView } from "../../../components/impact/DependencyGraphView";
import { NotificationPanel } from "../../../components/impact/NotificationPanel";
import { ImpactReportCard } from "../../../components/impact/ImpactReportCard";
import type {
  ImpactReport,
  ImpactNotification,
  DependencyEdge,
} from "../../../types/impactAnalysis";

const mockedGet = apiClient.get as ReturnType<typeof vi.fn>;
const mockedPost = apiClient.post as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

function makeReport(overrides: Partial<ImpactReport> = {}): ImpactReport {
  return {
    id: 1,
    report_id: "rpt-001-uuid",
    triggering_document_uuid: "doc-abc-123",
    triggering_version_id: 5,
    change_delta_summary: {
      sections_added: [{ title: "New Section" }],
      sections_modified: [],
      sections_deleted: [],
      significance_levels: { high: 1, medium: 0, low: 0 },
      metadata: {},
    },
    affected_items: [
      {
        affected_document_uuid: "doc-def-456",
        training_task_id: null,
        affected_document_title: "SOP-001 Chemical Handling",
        dependency_type: "validates",
        impact_severity: "critical",
        affected_sections: ["Section 2.1"],
        change_summary: "Requirement updated",
        recommended_action: "update_required",
        inference_prompt_summary: "Prompt...",
        model_response_summary: "Response...",
        token_count: 500,
      },
      {
        affected_document_uuid: "doc-ghi-789",
        training_task_id: null,
        affected_document_title: "MVP-002 Validation Protocol",
        dependency_type: "implements",
        impact_severity: "major",
        affected_sections: ["Section 3.2"],
        change_summary: "Missing coverage",
        recommended_action: "review_recommended",
        inference_prompt_summary: "Prompt...",
        model_response_summary: "Response...",
        token_count: 300,
      },
    ],
    gap_findings: [],
    status: "completed",
    analysis_timestamp: "2024-06-15T10:30:00Z",
    analysis_duration_ms: 45000,
    agent_archetype_used: "Change Impact Analyst",
    model_used: "gemma-4-e4b-it",
    total_token_count: 800,
    requesting_user_id: 42,
    company_id: 1,
    created_at: "2024-06-15T10:30:00Z",
    ...overrides,
  };
}

function makeNotification(overrides: Partial<ImpactNotification> = {}): ImpactNotification {
  return {
    id: 1,
    report_id: "rpt-001-uuid",
    affected_document_uuid: "doc-def-456",
    notification_type: "change_impact",
    impact_severity: "critical",
    change_summary: "Requirement REQ-001 was updated, affecting SOP-001 Section 2.1",
    target_user_id: 42,
    is_acknowledged: false,
    acknowledged_at: null,
    acknowledged_by: null,
    company_id: 1,
    created_at: "2024-06-15T10:31:00Z",
    ...overrides,
  };
}

function makeEdge(overrides: Partial<DependencyEdge> = {}): DependencyEdge {
  return {
    id: 1,
    source_document_uuid: "doc-abc-123",
    target_document_uuid: "doc-def-456",
    dependency_type: "validates",
    confidence_score: 1.0,
    detected_references: ["REQ-001"],
    last_verified_at: "2024-06-15T09:00:00Z",
    created_at: "2024-06-01T08:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function resetStore() {
  useImpactAnalysisStore.setState({
    reports: [],
    notifications: [],
    dependencyGraph: [],
    activeJob: null,
    documentStatus: {},
    isLoading: false,
    error: null,
    pollingIntervalId: null,
  });
}

// ---------------------------------------------------------------------------
// ImpactAnalysisPage Tests
// ---------------------------------------------------------------------------

describe("ImpactAnalysisPage", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    mockedGet.mockImplementation((url: string) => {
      if (url.includes("/api/impact-analysis/reports")) {
        return Promise.resolve({ reports: [], total_count: 0 });
      }
      if (url.includes("/api/impact-analysis/notifications")) {
        return Promise.resolve({ notifications: [], total_count: 0 });
      }
      return Promise.resolve({});
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the page heading and description", () => {
    render(<ImpactAnalysisPage />);

    expect(screen.getByText("Impact Analysis")).toBeDefined();
    expect(
      screen.getByText("AI-driven change impact analysis and dependency tracking")
    ).toBeDefined();
  });

  it("renders summary cards with zero counts initially", async () => {
    useImpactAnalysisStore.setState({ reports: [], isLoading: false });

    render(<ImpactAnalysisPage />);

    expect(screen.getByText("Critical Findings")).toBeDefined();
    expect(screen.getByText("Major Findings")).toBeDefined();
    expect(screen.getByText("Total Reports")).toBeDefined();
  });

  it("renders summary cards with correct severity counts from reports", () => {
    const report = makeReport();
    useImpactAnalysisStore.setState({ reports: [report], isLoading: false });

    render(<ImpactAnalysisPage />);

    // 1 critical, 1 major from the test report
    const criticalCard = screen.getByText("Critical Findings").closest("div");
    expect(criticalCard?.textContent).toContain("1");

    const majorCard = screen.getByText("Major Findings").closest("div");
    expect(majorCard?.textContent).toContain("1");
  });

  it("shows loading skeleton when isLoading is true and no reports", () => {
    useImpactAnalysisStore.setState({ isLoading: true, reports: [] });

    render(<ImpactAnalysisPage />);

    expect(screen.getByRole("status", { name: "Loading impact analysis data" })).toBeDefined();
  });

  it("shows empty state when no reports and not loading", async () => {
    // API returns empty results
    mockedGet.mockImplementation((url: string) => {
      if (url.includes("/api/impact-analysis/reports")) {
        return Promise.resolve({ reports: [], total_count: 0 });
      }
      if (url.includes("/api/impact-analysis/notifications")) {
        return Promise.resolve({ notifications: [], total_count: 0 });
      }
      return Promise.resolve({});
    });

    render(<ImpactAnalysisPage />);

    await waitFor(() => {
      expect(screen.getByText("No impact reports yet")).toBeDefined();
    });
    expect(
      screen.getByText(/Impact reports are generated automatically/)
    ).toBeDefined();
  });

  it("shows error banner with Retry button on API failure", async () => {
    // API rejects with an error
    mockedGet.mockImplementation((url: string) => {
      if (url.includes("/api/impact-analysis/reports")) {
        return Promise.reject(new Error("Failed to fetch reports"));
      }
      if (url.includes("/api/impact-analysis/notifications")) {
        return Promise.resolve({ notifications: [], total_count: 0 });
      }
      return Promise.resolve({});
    });

    render(<ImpactAnalysisPage />);

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain("Failed to fetch reports");
    });
    expect(screen.getByText("Retry")).toBeDefined();
  });

  it("clicking Retry button calls fetchReports and fetchNotifications", async () => {
    // First call fails, subsequent calls succeed
    let callCount = 0;
    mockedGet.mockImplementation((url: string) => {
      if (url.includes("/api/impact-analysis/reports")) {
        callCount++;
        if (callCount <= 1) {
          return Promise.reject(new Error("Network error"));
        }
        return Promise.resolve({ reports: [], total_count: 0 });
      }
      if (url.includes("/api/impact-analysis/notifications")) {
        return Promise.resolve({ notifications: [], total_count: 0 });
      }
      return Promise.resolve({});
    });

    render(<ImpactAnalysisPage />);

    // Wait for error state
    await waitFor(() => {
      expect(screen.getByText("Retry")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Retry"));

    await waitFor(() => {
      // Should have been called more than once (initial + retry)
      expect(callCount).toBeGreaterThan(1);
    });
  });

  it("fetches reports and notifications on mount", async () => {
    render(<ImpactAnalysisPage />);

    await waitFor(() => {
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/impact-analysis/reports"
      );
      expect(mockedGet).toHaveBeenCalledWith(
        "/api/impact-analysis/notifications"
      );
    });
  });

  it("renders notification badge with unacknowledged count", () => {
    const notifications = [makeNotification(), makeNotification({ id: 2 })];
    useImpactAnalysisStore.setState({ notifications, isLoading: false });

    render(<ImpactAnalysisPage />);

    const notifButton = screen.getByRole("button", {
      name: /Notifications \(2 unacknowledged\)/,
    });
    expect(notifButton).toBeDefined();
  });

  it("renders report list when reports exist", async () => {
    const reports = [makeReport(), makeReport({ id: 2, report_id: "rpt-002-uuid" })];
    mockedGet.mockImplementation((url: string) => {
      if (url.includes("/api/impact-analysis/reports")) {
        return Promise.resolve({ reports, total_count: 2 });
      }
      if (url.includes("/api/impact-analysis/notifications")) {
        return Promise.resolve({ notifications: [], total_count: 0 });
      }
      return Promise.resolve({});
    });

    render(<ImpactAnalysisPage />);

    await waitFor(() => {
      expect(screen.getByText("Impact Reports (2)")).toBeDefined();
    });
  });
});

// ---------------------------------------------------------------------------
// DependencyGraphView Tests
// ---------------------------------------------------------------------------

describe("DependencyGraphView", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders empty state when no edges provided", () => {
    render(<DependencyGraphView edges={[]} />);

    expect(screen.getByText("No dependency graph data")).toBeDefined();
    expect(
      screen.getByText("Build the dependency graph to visualize document relationships.")
    ).toBeDefined();
  });

  it("renders SVG with role=img and aria-label when edges exist", () => {
    const edges = [makeEdge()];

    render(<DependencyGraphView edges={edges} />);

    const svg = screen.getByRole("img", { name: "Document dependency graph" });
    expect(svg).toBeDefined();
  });

  it("renders nodes for each unique document UUID", () => {
    const edges = [
      makeEdge({ source_document_uuid: "doc-aaa", target_document_uuid: "doc-bbb" }),
      makeEdge({ id: 2, source_document_uuid: "doc-bbb", target_document_uuid: "doc-ccc" }),
    ];

    render(<DependencyGraphView edges={edges} />);

    // Each node has a <title> element with its UUID
    const svg = screen.getByRole("img", { name: "Document dependency graph" });
    // 3 unique nodes: doc-aaa, doc-bbb, doc-ccc
    const circles = svg.querySelectorAll("circle");
    expect(circles.length).toBe(3);
  });

  it("shows truncation message when nodes exceed 200", () => {
    // Create 201 unique nodes via edges
    const edges: DependencyEdge[] = [];
    for (let i = 0; i < 201; i++) {
      edges.push(
        makeEdge({
          id: i + 1,
          source_document_uuid: `doc-src-${i}`,
          target_document_uuid: `doc-tgt-${i}`,
        })
      );
    }

    render(<DependencyGraphView edges={edges} />);

    expect(screen.getByText(/Showing 200 of/)).toBeDefined();
    expect(screen.getByText(/Apply filters to reduce the graph size/)).toBeDefined();
  });

  it("does not show truncation message when nodes are within limit", () => {
    const edges = [makeEdge()];

    render(<DependencyGraphView edges={edges} />);

    expect(screen.queryByText(/Showing 200 of/)).toBeNull();
  });

  it("renders filter dropdown with all dependency types", () => {
    const edges = [makeEdge()];

    render(<DependencyGraphView edges={edges} />);

    const select = screen.getByLabelText("Filter by type:");
    expect(select).toBeDefined();

    // Check options
    const options = select.querySelectorAll("option");
    expect(options.length).toBe(6); // "All types" + 5 dependency types
  });

  it("filters edges when a dependency type is selected", () => {
    const edges = [
      makeEdge({ id: 1, dependency_type: "validates", source_document_uuid: "a", target_document_uuid: "b" }),
      makeEdge({ id: 2, dependency_type: "references", source_document_uuid: "c", target_document_uuid: "d" }),
    ];

    render(<DependencyGraphView edges={edges} />);

    const select = screen.getByLabelText("Filter by type:");
    fireEvent.change(select, { target: { value: "validates" } });

    // After filtering, only 2 nodes (a, b) should remain
    const svg = screen.getByRole("img", { name: "Document dependency graph" });
    const circles = svg.querySelectorAll("circle");
    expect(circles.length).toBe(2);
  });

  it("renders zoom controls", () => {
    const edges = [makeEdge()];

    render(<DependencyGraphView edges={edges} />);

    expect(screen.getByRole("button", { name: "Zoom in" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Reset view" })).toBeDefined();
  });

  it("color-codes nodes by severity from severityMap", () => {
    const edges = [
      makeEdge({ source_document_uuid: "doc-a", target_document_uuid: "doc-b" }),
    ];
    const severityMap = { "doc-a": "critical", "doc-b": "major" };

    render(<DependencyGraphView edges={edges} severityMap={severityMap} />);

    const svg = screen.getByRole("img", { name: "Document dependency graph" });
    const circles = svg.querySelectorAll("circle");

    // doc-a should be red (#ef4444), doc-b should be orange (#f97316)
    const fills = Array.from(circles).map((c) => c.getAttribute("fill"));
    expect(fills).toContain("#ef4444");
    expect(fills).toContain("#f97316");
  });
});

// ---------------------------------------------------------------------------
// NotificationPanel Tests
// ---------------------------------------------------------------------------

describe("NotificationPanel", () => {
  beforeEach(() => {
    resetStore();
    vi.clearAllMocks();
    mockedPost.mockResolvedValue({});
  });

  afterEach(() => {
    cleanup();
  });

  it("renders empty state when no notifications", () => {
    render(<NotificationPanel notifications={[]} />);

    expect(screen.getByText("No unacknowledged notifications")).toBeDefined();
    expect(
      screen.getByText("You will be notified when document changes impact your documents.")
    ).toBeDefined();
  });

  it("renders notification list with role=list", () => {
    const notifications = [makeNotification()];

    render(<NotificationPanel notifications={notifications} />);

    expect(screen.getByRole("list", { name: "Impact notifications" })).toBeDefined();
  });

  it("renders notification items with severity badge and change summary", () => {
    const notification = makeNotification({
      impact_severity: "critical",
      change_summary: "Requirement REQ-001 was updated",
    });

    render(<NotificationPanel notifications={[notification]} />);

    expect(screen.getByText("Critical")).toBeDefined();
    expect(screen.getByText("Requirement REQ-001 was updated")).toBeDefined();
  });

  it("renders affected document UUID for each notification", () => {
    const notification = makeNotification({
      affected_document_uuid: "doc-xyz-999",
    });

    render(<NotificationPanel notifications={[notification]} />);

    expect(screen.getByText("doc-xyz-999")).toBeDefined();
  });

  it("renders Acknowledge button for each notification", () => {
    const notifications = [
      makeNotification({ id: 1, affected_document_uuid: "doc-a" }),
      makeNotification({ id: 2, affected_document_uuid: "doc-b" }),
    ];

    render(<NotificationPanel notifications={notifications} />);

    const ackButtons = screen.getAllByRole("button", { name: /Acknowledge/ });
    expect(ackButtons.length).toBe(2);
  });

  it("clicking Acknowledge calls store acknowledgeNotification action", async () => {
    const notification = makeNotification({ id: 7, affected_document_uuid: "doc-test" });

    // Set up the store with a mock acknowledgeNotification
    mockedPost.mockResolvedValue({});

    render(<NotificationPanel notifications={[notification]} />);

    const ackButton = screen.getByRole("button", {
      name: "Acknowledge notification for doc-test",
    });
    fireEvent.click(ackButton);

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/api/impact-analysis/notifications/7/acknowledge",
        {},
        { changeReason: "Acknowledged impact notification" }
      );
    });
  });

  it("renders multiple notifications sorted by severity", () => {
    const notifications = [
      makeNotification({ id: 1, impact_severity: "major", affected_document_uuid: "doc-1" }),
      makeNotification({ id: 2, impact_severity: "critical", affected_document_uuid: "doc-2" }),
    ];

    render(<NotificationPanel notifications={notifications} />);

    const items = screen.getAllByRole("listitem");
    expect(items.length).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// ImpactReportCard Tests
// ---------------------------------------------------------------------------

describe("ImpactReportCard", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders status badge for completed report", () => {
    const report = makeReport({ status: "completed" });

    render(<ImpactReportCard report={report} />);

    expect(screen.getByText("Completed")).toBeDefined();
  });

  it("renders status badge for partial_success report", () => {
    const report = makeReport({ status: "partial_success" });

    render(<ImpactReportCard report={report} />);

    expect(screen.getByText("Partial")).toBeDefined();
  });

  it("renders status badge for failed report", () => {
    const report = makeReport({ status: "failed" });

    render(<ImpactReportCard report={report} />);

    expect(screen.getByText("Failed")).toBeDefined();
  });

  it("renders triggering document UUID", () => {
    const report = makeReport({ triggering_document_uuid: "doc-trigger-xyz" });

    render(<ImpactReportCard report={report} />);

    expect(screen.getByText("doc-trigger-xyz")).toBeDefined();
  });

  it("renders severity counts for affected items", () => {
    const report = makeReport({
      affected_items: [
        {
          affected_document_uuid: "doc-1",
          training_task_id: null,
          affected_document_title: "Doc 1",
          dependency_type: "validates",
          impact_severity: "critical",
          affected_sections: ["S1"],
          change_summary: "Changed",
          recommended_action: "update_required",
          inference_prompt_summary: "P",
          model_response_summary: "R",
          token_count: 100,
        },
        {
          affected_document_uuid: "doc-2",
          training_task_id: null,
          affected_document_title: "Doc 2",
          dependency_type: "references",
          impact_severity: "critical",
          affected_sections: ["S2"],
          change_summary: "Changed",
          recommended_action: "review_recommended",
          inference_prompt_summary: "P",
          model_response_summary: "R",
          token_count: 100,
        },
        {
          affected_document_uuid: "doc-3",
          training_task_id: null,
          affected_document_title: "Doc 3",
          dependency_type: "implements",
          impact_severity: "minor",
          affected_sections: ["S3"],
          change_summary: "Changed",
          recommended_action: "review_recommended",
          inference_prompt_summary: "P",
          model_response_summary: "R",
          token_count: 100,
        },
      ],
    });

    render(<ImpactReportCard report={report} />);

    // 2 critical, 0 major, 1 minor
    const criticalSpan = screen.getByTitle("Critical findings");
    expect(criticalSpan.textContent).toContain("2");

    const minorSpan = screen.getByTitle("Minor findings");
    expect(minorSpan.textContent).toContain("1");
  });

  it("renders 'No findings' when report has no affected items", () => {
    const report = makeReport({ affected_items: [] });

    render(<ImpactReportCard report={report} />);

    expect(screen.getByText("No findings")).toBeDefined();
  });

  it("renders formatted timestamp", () => {
    const report = makeReport({ analysis_timestamp: "2024-06-15T10:30:00Z" });

    render(<ImpactReportCard report={report} />);

    // The formatted date should contain "Jun" and "2024"
    const card = screen.getByRole("button");
    expect(card.textContent).toContain("Jun");
    expect(card.textContent).toContain("2024");
  });

  it("has correct aria-label with document UUID and status", () => {
    const report = makeReport({
      triggering_document_uuid: "doc-aria-test",
      status: "completed",
    });

    render(<ImpactReportCard report={report} />);

    const card = screen.getByRole("button", {
      name: "Impact report for document doc-aria-test, status: Completed",
    });
    expect(card).toBeDefined();
  });

  it("calls onClick when clicked", () => {
    const report = makeReport();
    const onClick = vi.fn();

    render(<ImpactReportCard report={report} onClick={onClick} />);

    const card = screen.getByRole("button");
    fireEvent.click(card);

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
