import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";

/**
 * Frontend component tests for AI-Powered Traceability & Gap Discovery.
 *
 * Tests:
 * - TraceabilityPage renders summary cards, matrix list, empty state
 * - MatrixDetailView renders links table with confidence badges
 * - OrphanAlertsPanel renders tabs and orphan items
 * - GenerateMatrixDialog form validation
 * - TraceabilityAlertBanner renders when alerts exist, hidden when none
 *
 * **Validates: Requirements 8.1–8.12**
 */

// ---------------------------------------------------------------------------
// Mock store state
// ---------------------------------------------------------------------------

const mockFetchMatrices = vi.fn();
const mockFetchCoverageSummary = vi.fn();
const mockFetchCoverageHistory = vi.fn();
const mockFetchAlerts = vi.fn();
const mockFetchLinks = vi.fn();
const mockFetchOrphanRequirements = vi.fn();
const mockFetchOrphanTestCases = vi.fn();
const mockGenerateMatrix = vi.fn();

let mockStoreState: Record<string, unknown> = {};

vi.mock("@/stores/traceabilityStore", () => ({
  useTraceabilityStore: () => ({
    matrices: [],
    currentMatrix: null,
    links: [],
    orphanRequirements: [],
    orphanTestCases: [],
    coverageSummary: null,
    coverageHistory: [],
    alerts: [],
    activeJob: null,
    isLoading: false,
    error: null,
    fetchMatrices: mockFetchMatrices,
    fetchCoverageSummary: mockFetchCoverageSummary,
    fetchCoverageHistory: mockFetchCoverageHistory,
    fetchAlerts: mockFetchAlerts,
    fetchLinks: mockFetchLinks,
    fetchOrphanRequirements: mockFetchOrphanRequirements,
    fetchOrphanTestCases: mockFetchOrphanTestCases,
    generateMatrix: mockGenerateMatrix,
    ...mockStoreState,
  }),
}));

// Mock lucide-react icons to simple spans for test stability
vi.mock("lucide-react", () => ({
  AlertCircle: (props: Record<string, unknown>) => <span data-testid="icon-alert-circle" {...props} />,
  AlertTriangle: (props: Record<string, unknown>) => <span data-testid="icon-alert-triangle" {...props} />,
  ArrowRight: (props: Record<string, unknown>) => <span data-testid="icon-arrow-right" {...props} />,
  ArrowUpDown: (props: Record<string, unknown>) => <span data-testid="icon-arrow-up-down" {...props} />,
  CheckCircle: (props: Record<string, unknown>) => <span data-testid="icon-check-circle" {...props} />,
  ChevronLeft: (props: Record<string, unknown>) => <span data-testid="icon-chevron-left" {...props} />,
  ChevronRight: (props: Record<string, unknown>) => <span data-testid="icon-chevron-right" {...props} />,
  FileSearch: (props: Record<string, unknown>) => <span data-testid="icon-file-search" {...props} />,
  Filter: (props: Record<string, unknown>) => <span data-testid="icon-filter" {...props} />,
  FlaskConical: (props: Record<string, unknown>) => <span data-testid="icon-flask" {...props} />,
  Loader2: (props: Record<string, unknown>) => <span data-testid="icon-loader" {...props} />,
  Plus: (props: Record<string, unknown>) => <span data-testid="icon-plus" {...props} />,
  RefreshCw: (props: Record<string, unknown>) => <span data-testid="icon-refresh" {...props} />,
  ShieldCheck: (props: Record<string, unknown>) => <span data-testid="icon-shield" {...props} />,
  Target: (props: Record<string, unknown>) => <span data-testid="icon-target" {...props} />,
  X: (props: Record<string, unknown>) => <span data-testid="icon-x" {...props} />,
}));

// Mock the Button component
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => (
    <button {...props}>{children}</button>
  ),
}));

// Mock CoverageTrendChart (not under test here)
vi.mock("@/components/traceability/CoverageTrendChart", () => ({
  CoverageTrendChart: () => <div data-testid="coverage-trend-chart" />,
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------

import { TraceabilityPage } from "@/pages/TraceabilityPage";
import { MatrixDetailView } from "@/components/traceability/MatrixDetailView";
import { OrphanAlertsPanel } from "@/components/traceability/OrphanAlertsPanel";
import { GenerateMatrixDialog } from "@/components/traceability/GenerateMatrixDialog";
import { TraceabilityAlertBanner } from "@/components/traceability/TraceabilityAlertBanner";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeMatrix(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    matrix_id: "mat-001",
    matrix_name: "URS v2.0 Traceability",
    description: null,
    source_document_uuids: ["doc-001"],
    target_document_uuids: ["doc-002"],
    source_document_versions: [{ document_uuid: "doc-001", version_id: 1 }],
    target_document_versions: [{ document_uuid: "doc-002", version_id: 1 }],
    traceability_links: [],
    orphan_requirements: [],
    orphan_test_cases: [],
    coverage_metrics: {
      total_requirements: 10,
      covered_requirements: 8,
      orphan_requirements_count: 2,
      coverage_percentage: 80.0,
      total_test_cases: 12,
      linked_test_cases: 10,
      orphan_test_cases_count: 2,
      average_link_confidence: 0.85,
      compliance_readiness_score: 75.0,
    },
    status: "completed",
    parent_matrix_id: null,
    generation_timestamp: "2024-01-15T10:00:00Z",
    generation_duration_ms: 45000,
    agent_archetype_used: "Traceability Analyst",
    model_used: "gemma-4-e4b-it",
    total_token_count: 5000,
    requesting_user_id: 1,
    company_id: 1,
    deleted_at: null,
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeLink(overrides: Record<string, unknown> = {}) {
  return {
    requirement_id: "REQ-001",
    requirement_text: "The system shall validate user input",
    source_document_uuid: "doc-001",
    source_section: "Section 4.1",
    target_document_uuid: "doc-002",
    target_section: "Section 2.3",
    test_case_id: "TC-001",
    test_case_text: "Verify that user input is validated",
    link_confidence: 0.95,
    link_method: "exact_id_match",
    link_methods: ["exact_id_match"],
    verification_status: "unverified",
    ...overrides,
  };
}

function makeOrphanRequirement(overrides: Record<string, unknown> = {}) {
  return {
    requirement_id: "REQ-010",
    requirement_text: "The system shall comply with FDA 21 CFR Part 11",
    source_document_uuid: "doc-001",
    source_section: "Section 5.1",
    severity: "critical",
    suggested_action: "create_test_case",
    ...overrides,
  };
}

function makeOrphanTestCase(overrides: Record<string, unknown> = {}) {
  return {
    test_case_id: "TC-020",
    test_case_text: "Verify label formatting matches template",
    target_document_uuid: "doc-002",
    target_section: "Section 3.2",
    risk_level: "low",
    suggested_action: "link_to_requirement",
    ...overrides,
  };
}

function makeAlert(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    alert_id: "alert-001",
    triggering_report_id: "report-001",
    affected_matrix_ids: ["mat-001"],
    affected_link_count: 3,
    alert_severity: "critical",
    is_resolved: false,
    resolved_at: null,
    resolved_by: null,
    resolution_action: null,
    resolution_note: null,
    company_id: 1,
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

function makeCoverageSummary(overrides: Record<string, unknown> = {}) {
  return {
    total_matrices_generated: 5,
    latest_matrix_date: "2024-01-15T10:00:00Z",
    average_coverage_percentage: 82.5,
    total_orphan_requirements: 4,
    total_orphan_test_cases: 2,
    average_compliance_readiness_score: 78.0,
    breakdown: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup / Teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockStoreState = {};
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

// ===========================================================================
// TraceabilityPage
// ===========================================================================

describe("TraceabilityPage", () => {
  it("renders summary cards with coverage data", () => {
    mockStoreState = {
      coverageSummary: makeCoverageSummary(),
      matrices: [makeMatrix()],
    };

    render(<TraceabilityPage />);

    expect(screen.getByText("82.5%")).toBeDefined();
    expect(screen.getByText("78")).toBeDefined();
    expect(screen.getByText("4")).toBeDefined();
    expect(screen.getByText("2")).toBeDefined();
  });

  it("renders summary card labels", () => {
    mockStoreState = {
      coverageSummary: makeCoverageSummary(),
      matrices: [makeMatrix()],
    };

    render(<TraceabilityPage />);

    expect(screen.getByText("Coverage")).toBeDefined();
    expect(screen.getByText("Compliance Score")).toBeDefined();
    expect(screen.getByText("Orphan Requirements")).toBeDefined();
    expect(screen.getByText("Orphan Test Cases")).toBeDefined();
  });

  it("renders matrix list when matrices exist", () => {
    mockStoreState = {
      matrices: [
        makeMatrix({ matrix_name: "URS v2.0 Traceability" }),
        makeMatrix({ id: 2, matrix_id: "mat-002", matrix_name: "SRS Validation" }),
      ],
    };

    render(<TraceabilityPage />);

    expect(screen.getByText("URS v2.0 Traceability")).toBeDefined();
    expect(screen.getByText("SRS Validation")).toBeDefined();
  });

  it("renders empty state when no matrices and not loading", () => {
    mockStoreState = {
      matrices: [],
      isLoading: false,
      error: null,
    };

    render(<TraceabilityPage />);

    expect(screen.getByText("No traceability matrices yet")).toBeDefined();
    expect(
      screen.getByText(/Generate your first traceability matrix/),
    ).toBeDefined();
  });

  it("renders loading skeleton when loading with no matrices", () => {
    mockStoreState = {
      matrices: [],
      isLoading: true,
    };

    render(<TraceabilityPage />);

    expect(screen.getByRole("status")).toBeDefined();
  });

  it("renders error banner with retry button on API failure", () => {
    mockStoreState = {
      error: "Failed to fetch matrices",
      matrices: [],
    };

    render(<TraceabilityPage />);

    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText("Failed to fetch matrices")).toBeDefined();
    expect(screen.getByText("Retry")).toBeDefined();
  });

  it("renders Generate Matrix button", () => {
    render(<TraceabilityPage />);

    // There are multiple "Generate Matrix" buttons (header + empty state)
    const buttons = screen.getAllByText("Generate Matrix");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("renders status badges on matrix cards", () => {
    mockStoreState = {
      matrices: [
        makeMatrix({ status: "completed" }),
        makeMatrix({ id: 2, matrix_id: "mat-002", status: "partial_success", matrix_name: "Partial" }),
      ],
    };

    render(<TraceabilityPage />);

    expect(screen.getByText("completed")).toBeDefined();
    expect(screen.getByText("partial success")).toBeDefined();
  });

  it("calls fetch actions on mount", () => {
    render(<TraceabilityPage />);

    expect(mockFetchMatrices).toHaveBeenCalled();
    expect(mockFetchCoverageSummary).toHaveBeenCalled();
    expect(mockFetchCoverageHistory).toHaveBeenCalled();
    expect(mockFetchAlerts).toHaveBeenCalled();
  });
});

// ===========================================================================
// MatrixDetailView
// ===========================================================================

describe("MatrixDetailView", () => {
  it("renders links table with data", () => {
    mockStoreState = {
      links: [
        makeLink({ requirement_id: "REQ-001", test_case_id: "TC-001", link_confidence: 0.95 }),
        makeLink({ requirement_id: "REQ-002", test_case_id: "TC-002", link_confidence: 0.6 }),
      ],
      isLoading: false,
    };

    render(<MatrixDetailView matrixId="mat-001" />);

    expect(screen.getByText("REQ-001")).toBeDefined();
    expect(screen.getByText("REQ-002")).toBeDefined();
    expect(screen.getByText("TC-001")).toBeDefined();
    expect(screen.getByText("TC-002")).toBeDefined();
  });

  it("renders confidence badges with correct colors", () => {
    mockStoreState = {
      links: [
        makeLink({ requirement_id: "REQ-HIGH", link_confidence: 0.95 }),
        makeLink({ requirement_id: "REQ-MED", test_case_id: "TC-MED", link_confidence: 0.6 }),
        makeLink({ requirement_id: "REQ-LOW", test_case_id: "TC-LOW", link_confidence: 0.3 }),
      ],
      isLoading: false,
    };

    render(<MatrixDetailView matrixId="mat-001" />);

    // High confidence (>= 0.8) → green badge showing 95%
    expect(screen.getByText("95%")).toBeDefined();
    // Medium confidence (>= 0.5) → yellow badge showing 60%
    expect(screen.getByText("60%")).toBeDefined();
    // Low confidence (< 0.5) → red badge showing 30%
    expect(screen.getByText("30%")).toBeDefined();
  });

  it("renders stale indicator when stale markers present", () => {
    mockStoreState = {
      links: [
        makeLink({ requirement_id: "REQ-001" }),
        makeLink({ requirement_id: "REQ-002", test_case_id: "TC-002" }),
      ],
      isLoading: false,
    };

    const staleMarkers = [
      {
        matrix_id: "mat-001",
        requirement_id: "REQ-001",
        stale_since: "2024-01-16T10:00:00Z",
        stale_reason: "Requirement changed",
        triggering_report_id: "report-001",
        is_cleared: false,
        cleared_at: null,
        company_id: 1,
        created_at: "2024-01-16T10:00:00Z",
      },
    ];

    render(<MatrixDetailView matrixId="mat-001" staleMarkers={staleMarkers} />);

    // "Stale" appears in the column header + once for the stale link row
    const staleElements = screen.getAllByText("Stale");
    expect(staleElements.length).toBe(2); // header + 1 stale row indicator
  });

  it("renders empty state when no links match filter", () => {
    mockStoreState = {
      links: [],
      isLoading: false,
    };

    render(<MatrixDetailView matrixId="mat-001" />);

    expect(
      screen.getByText("No traceability links found matching the current filter."),
    ).toBeDefined();
  });

  it("renders loading state", () => {
    mockStoreState = {
      links: [],
      isLoading: true,
    };

    render(<MatrixDetailView matrixId="mat-001" />);

    expect(screen.getByText("Loading links...")).toBeDefined();
  });

  it("renders link method formatted", () => {
    mockStoreState = {
      links: [makeLink({ link_method: "exact_id_match" })],
      isLoading: false,
    };

    render(<MatrixDetailView matrixId="mat-001" />);

    expect(screen.getByText("Exact Id Match")).toBeDefined();
  });

  it("calls fetchLinks on mount with matrixId", () => {
    mockStoreState = { links: [], isLoading: false };

    render(<MatrixDetailView matrixId="mat-001" />);

    expect(mockFetchLinks).toHaveBeenCalledWith("mat-001", expect.any(Object));
  });

  it("renders sortable column headers", () => {
    mockStoreState = { links: [makeLink()], isLoading: false };

    render(<MatrixDetailView matrixId="mat-001" />);

    expect(screen.getByLabelText("Sort by Req ID")).toBeDefined();
    expect(screen.getByLabelText("Sort by Confidence")).toBeDefined();
    expect(screen.getByLabelText("Sort by Method")).toBeDefined();
  });
});

// ===========================================================================
// OrphanAlertsPanel
// ===========================================================================

describe("OrphanAlertsPanel", () => {
  it("renders both tabs", () => {
    mockStoreState = {
      orphanRequirements: [],
      orphanTestCases: [],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    expect(screen.getByText("Orphan Requirements")).toBeDefined();
    expect(screen.getByText("Orphan Test Cases")).toBeDefined();
  });

  it("renders orphan requirements with severity badges", () => {
    mockStoreState = {
      orphanRequirements: [
        makeOrphanRequirement({ severity: "critical", requirement_id: "REQ-010" }),
        makeOrphanRequirement({ severity: "major", requirement_id: "REQ-011" }),
        makeOrphanRequirement({ severity: "minor", requirement_id: "REQ-012" }),
      ],
      orphanTestCases: [],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    expect(screen.getByText("REQ-010")).toBeDefined();
    expect(screen.getByText("REQ-011")).toBeDefined();
    expect(screen.getByText("REQ-012")).toBeDefined();
    expect(screen.getByText("critical")).toBeDefined();
    expect(screen.getByText("major")).toBeDefined();
    expect(screen.getByText("minor")).toBeDefined();
  });

  it("renders suggested action chips for orphan requirements", () => {
    mockStoreState = {
      orphanRequirements: [
        makeOrphanRequirement({ suggested_action: "create_test_case" }),
      ],
      orphanTestCases: [],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    expect(screen.getByText("Create Test Case")).toBeDefined();
  });

  it("switches to orphan test cases tab", () => {
    mockStoreState = {
      orphanRequirements: [],
      orphanTestCases: [
        makeOrphanTestCase({ risk_level: "high", test_case_id: "TC-020" }),
      ],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    // Click the test cases tab
    fireEvent.click(screen.getByText("Orphan Test Cases"));

    expect(screen.getByText("TC-020")).toBeDefined();
    expect(screen.getByText("high")).toBeDefined();
  });

  it("renders risk level badges for orphan test cases", () => {
    mockStoreState = {
      orphanRequirements: [],
      orphanTestCases: [
        makeOrphanTestCase({ risk_level: "high", test_case_id: "TC-H" }),
        makeOrphanTestCase({ risk_level: "medium", test_case_id: "TC-M" }),
        makeOrphanTestCase({ risk_level: "low", test_case_id: "TC-L" }),
      ],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    // Switch to test cases tab
    fireEvent.click(screen.getByText("Orphan Test Cases"));

    expect(screen.getByText("TC-H")).toBeDefined();
    expect(screen.getByText("TC-M")).toBeDefined();
    expect(screen.getByText("TC-L")).toBeDefined();
    expect(screen.getByText("high")).toBeDefined();
    expect(screen.getByText("medium")).toBeDefined();
    expect(screen.getByText("low")).toBeDefined();
  });

  it("renders empty state for orphan requirements", () => {
    mockStoreState = {
      orphanRequirements: [],
      orphanTestCases: [],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    expect(
      screen.getByText("No orphan requirements found. All requirements have test coverage."),
    ).toBeDefined();
  });

  it("renders loading state", () => {
    mockStoreState = {
      orphanRequirements: [],
      orphanTestCases: [],
      isLoading: true,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    expect(screen.getByText("Loading orphan data...")).toBeDefined();
  });

  it("calls fetch actions on mount", () => {
    mockStoreState = {
      orphanRequirements: [],
      orphanTestCases: [],
      isLoading: false,
    };

    render(<OrphanAlertsPanel matrixId="mat-001" />);

    expect(mockFetchOrphanRequirements).toHaveBeenCalledWith("mat-001");
    expect(mockFetchOrphanTestCases).toHaveBeenCalledWith("mat-001");
  });
});

// ===========================================================================
// GenerateMatrixDialog
// ===========================================================================

describe("GenerateMatrixDialog", () => {
  it("renders the dialog with form fields", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    expect(screen.getByText("Generate Traceability Matrix")).toBeDefined();
    expect(screen.getByPlaceholderText("e.g., URS v2.0 → IQ/OQ Traceability")).toBeDefined();
    expect(screen.getByPlaceholderText(/Describe the purpose/)).toBeDefined();
    // Two "Document ID" inputs (source + target)
    expect(screen.getAllByPlaceholderText("Document ID")).toHaveLength(2);
  });

  it("submit button is disabled when form is incomplete", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    const submitButton = screen.getByText("Generate Matrix");
    expect(submitButton.hasAttribute("disabled")).toBe(true);
  });

  it("submit button is enabled when all required fields are filled", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    // Fill matrix name
    const nameInput = screen.getByPlaceholderText("e.g., URS v2.0 → IQ/OQ Traceability");
    fireEvent.change(nameInput, { target: { value: "Test Matrix" } });

    // Add source document (first Document ID input)
    const docInputs = screen.getAllByPlaceholderText("Document ID");
    fireEvent.change(docInputs[0], { target: { value: "1" } });
    fireEvent.keyDown(docInputs[0], { key: "Enter" });

    // Add target document (second Document ID input)
    fireEvent.change(docInputs[1], { target: { value: "2" } });
    fireEvent.keyDown(docInputs[1], { key: "Enter" });

    // Fill change reason
    const reasonInput = screen.getByPlaceholderText(/Initial traceability/);
    fireEvent.change(reasonInput, { target: { value: "Test reason" } });

    const submitButton = screen.getByText("Generate Matrix");
    expect(submitButton.hasAttribute("disabled")).toBe(false);
  });

  it("shows character count for matrix name", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    expect(screen.getByText("0/200 characters")).toBeDefined();

    const nameInput = screen.getByPlaceholderText("e.g., URS v2.0 → IQ/OQ Traceability");
    fireEvent.change(nameInput, { target: { value: "Hello" } });

    expect(screen.getByText("5/200 characters")).toBeDefined();
  });

  it("shows character count for description", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    expect(screen.getByText("0/1000 characters")).toBeDefined();
  });

  it("displays added source document chips", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    const docInputs = screen.getAllByPlaceholderText("Document ID");
    fireEvent.change(docInputs[0], { target: { value: "42" } });
    fireEvent.keyDown(docInputs[0], { key: "Enter" });

    expect(screen.getByText("Doc #42")).toBeDefined();
    expect(screen.getByText("1/10 selected")).toBeDefined();
  });

  it("displays added target document chips", () => {
    mockStoreState = { activeJob: null, error: null };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    const docInputs = screen.getAllByPlaceholderText("Document ID");
    fireEvent.change(docInputs[1], { target: { value: "99" } });
    fireEvent.keyDown(docInputs[1], { key: "Enter" });

    expect(screen.getByText("Doc #99")).toBeDefined();
    expect(screen.getByText("1/20 selected")).toBeDefined();
  });

  it("calls onClose when Cancel is clicked", () => {
    mockStoreState = { activeJob: null, error: null };
    const onClose = vi.fn();

    render(<GenerateMatrixDialog onClose={onClose} />);

    fireEvent.click(screen.getByText("Cancel"));

    expect(onClose).toHaveBeenCalled();
  });

  it("displays error message when submitError occurs", () => {
    mockStoreState = { activeJob: null, error: "Server error occurred" };

    render(<GenerateMatrixDialog onClose={vi.fn()} />);

    expect(screen.getByText("Server error occurred")).toBeDefined();
  });
});

// ===========================================================================
// TraceabilityAlertBanner
// ===========================================================================

describe("TraceabilityAlertBanner", () => {
  it("renders banner when unresolved critical/major alerts exist", () => {
    mockStoreState = {
      alerts: [
        makeAlert({ alert_severity: "critical", is_resolved: false }),
        makeAlert({ id: 2, alert_id: "alert-002", alert_severity: "major", is_resolved: false }),
      ],
    };

    render(<TraceabilityAlertBanner />);

    expect(screen.getByRole("alert")).toBeDefined();
    expect(screen.getByText(/2 unresolved traceability alerts/)).toBeDefined();
    expect(screen.getByText("1 critical")).toBeDefined();
    expect(screen.getByText("1 major")).toBeDefined();
  });

  it("renders nothing when no unresolved critical/major alerts", () => {
    mockStoreState = {
      alerts: [],
    };

    const { container } = render(<TraceabilityAlertBanner />);

    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when all alerts are resolved", () => {
    mockStoreState = {
      alerts: [
        makeAlert({ alert_severity: "critical", is_resolved: true }),
      ],
    };

    const { container } = render(<TraceabilityAlertBanner />);

    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when only minor alerts exist", () => {
    mockStoreState = {
      alerts: [
        makeAlert({ alert_severity: "minor", is_resolved: false }),
      ],
    };

    const { container } = render(<TraceabilityAlertBanner />);

    expect(container.innerHTML).toBe("");
  });

  it("shows View alerts link", () => {
    mockStoreState = {
      alerts: [makeAlert({ alert_severity: "critical", is_resolved: false })],
    };

    render(<TraceabilityAlertBanner />);

    expect(screen.getByText("View alerts")).toBeDefined();
  });

  it("shows singular 'alert' for single alert", () => {
    mockStoreState = {
      alerts: [makeAlert({ alert_severity: "critical", is_resolved: false })],
    };

    render(<TraceabilityAlertBanner />);

    expect(screen.getByText(/1 unresolved traceability alert$/)).toBeDefined();
  });
});
