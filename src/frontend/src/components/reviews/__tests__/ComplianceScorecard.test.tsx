import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for ComplianceScorecard component
 *
 * Tests: gauge rendering, risk band display with colors, trend indicator,
 * document type bar chart, loading/error/empty states, summary stats.
 *
 * Validates: Requirements 11.6, 6.1, 6.2, 6.3
 */

import type { ComplianceScorecard as ScorecardData } from "@/lib/reviews-api";

// Mock the review store
const mockFetchScorecard = vi.fn();

vi.mock("@/stores/reviewStore", () => ({
  useReviewStore: vi.fn(),
}));

import { useReviewStore } from "@/stores/reviewStore";
import { ComplianceScorecard } from "../ComplianceScorecard";

const mockedUseReviewStore = vi.mocked(useReviewStore);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockScorecard(overrides: Partial<ScorecardData> = {}): ScorecardData {
  return {
    overall_score: 82.5,
    risk_band: "Good",
    trend: "improving",
    total_documents_reviewed: 45,
    documents_with_critical_findings: 3,
    documents_with_open_action_items: 7,
    score_by_document_type: {
      SOP: 88.0,
      Protocol: 75.5,
      "Deviation Report": 62.0,
    },
    last_updated: "2024-06-15T10:30:00Z",
    ...overrides,
  };
}

function mockStoreState(overrides: Record<string, unknown> = {}) {
  mockedUseReviewStore.mockReturnValue({
    scorecard: null,
    isLoadingScorecard: false,
    scorecardError: null,
    fetchScorecard: mockFetchScorecard,
    ...overrides,
  } as ReturnType<typeof useReviewStore>);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ComplianceScorecard", () => {
  beforeEach(() => {
    mockFetchScorecard.mockClear();
    mockFetchScorecard.mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Loading state
  // -------------------------------------------------------------------------
  it("shows loading state when scorecard is loading", () => {
    mockStoreState({ isLoadingScorecard: true });

    render(<ComplianceScorecard />);

    expect(screen.getByLabelText("Compliance scorecard loading")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Error state
  // -------------------------------------------------------------------------
  it("shows error state with retry button when there is an error", () => {
    mockStoreState({ scorecardError: "Network error" });

    render(<ComplianceScorecard />);

    expect(screen.getByText("Error: Network error")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("calls fetchScorecard when retry button is clicked", () => {
    mockStoreState({ scorecardError: "Network error" });

    render(<ComplianceScorecard />);

    fireEvent.click(screen.getByText("Retry"));

    // Once on mount, once on retry click
    expect(mockFetchScorecard).toHaveBeenCalledTimes(2);
  });

  // -------------------------------------------------------------------------
  // 3. Empty state
  // -------------------------------------------------------------------------
  it("shows empty state when scorecard is null", () => {
    mockStoreState({ scorecard: null });

    render(<ComplianceScorecard />);

    expect(screen.getByText("No scorecard data available")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 4. Renders scorecard with gauge
  // -------------------------------------------------------------------------
  it("renders the compliance score gauge", () => {
    const scorecard = createMockScorecard({ overall_score: 82.5 });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(
      screen.getByLabelText("Compliance score gauge showing 82.5 out of 100"),
    ).toBeInTheDocument();
    expect(screen.getByText("82.5")).toBeInTheDocument();
    expect(screen.getByText("/ 100")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Risk band display with correct colors
  // -------------------------------------------------------------------------
  it("displays Excellent risk band with green styling", () => {
    const scorecard = createMockScorecard({ risk_band: "Excellent" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const badge = screen.getByLabelText("Risk band: Excellent");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-green-100");
    expect(badge.className).toContain("text-green-700");
  });

  it("displays Good risk band with blue styling", () => {
    const scorecard = createMockScorecard({ risk_band: "Good" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const badge = screen.getByLabelText("Risk band: Good");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-blue-100");
    expect(badge.className).toContain("text-blue-700");
  });

  it("displays Needs Attention risk band with yellow styling", () => {
    const scorecard = createMockScorecard({ risk_band: "Needs Attention" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const badge = screen.getByLabelText("Risk band: Needs Attention");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-yellow-100");
    expect(badge.className).toContain("text-yellow-700");
  });

  it("displays At Risk band with orange styling", () => {
    const scorecard = createMockScorecard({ risk_band: "At Risk" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const badge = screen.getByLabelText("Risk band: At Risk");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-orange-100");
    expect(badge.className).toContain("text-orange-700");
  });

  it("displays Critical risk band with red styling", () => {
    const scorecard = createMockScorecard({ risk_band: "Critical" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const badge = screen.getByLabelText("Risk band: Critical");
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain("bg-red-100");
    expect(badge.className).toContain("text-red-700");
  });

  // -------------------------------------------------------------------------
  // 6. Trend indicator
  // -------------------------------------------------------------------------
  it("shows improving trend with green arrow up", () => {
    const scorecard = createMockScorecard({ trend: "improving" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const trend = screen.getByLabelText("Trend: improving");
    expect(trend).toBeInTheDocument();
    expect(trend.className).toContain("text-green-700");
    expect(screen.getByText("Improving")).toBeInTheDocument();
  });

  it("shows declining trend with red arrow down", () => {
    const scorecard = createMockScorecard({ trend: "declining" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const trend = screen.getByLabelText("Trend: declining");
    expect(trend).toBeInTheDocument();
    expect(trend.className).toContain("text-red-700");
    expect(screen.getByText("Declining")).toBeInTheDocument();
  });

  it("shows stable trend with gray flat indicator", () => {
    const scorecard = createMockScorecard({ trend: "stable" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const trend = screen.getByLabelText("Trend: stable");
    expect(trend).toBeInTheDocument();
    expect(trend.className).toContain("text-gray-500");
    expect(screen.getByText("Stable")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Summary statistics
  // -------------------------------------------------------------------------
  it("displays summary statistics correctly", () => {
    const scorecard = createMockScorecard({
      total_documents_reviewed: 45,
      documents_with_critical_findings: 3,
      documents_with_open_action_items: 7,
    });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("Open Items")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. Document type bar chart
  // -------------------------------------------------------------------------
  it("renders bar chart with document type scores", () => {
    const scorecard = createMockScorecard({
      score_by_document_type: {
        SOP: 88.0,
        Protocol: 75.5,
        "Deviation Report": 62.0,
      },
    });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText("Score by Document Type")).toBeInTheDocument();
    expect(screen.getByText("SOP")).toBeInTheDocument();
    expect(screen.getByText("88.0")).toBeInTheDocument();
    expect(screen.getByText("Protocol")).toBeInTheDocument();
    expect(screen.getByText("75.5")).toBeInTheDocument();
    expect(screen.getByText("Deviation Report")).toBeInTheDocument();
    expect(screen.getByText("62.0")).toBeInTheDocument();
  });

  it("shows empty message when no document type data", () => {
    const scorecard = createMockScorecard({ score_by_document_type: {} });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText("No document type data available")).toBeInTheDocument();
  });

  it("renders progress bars with correct aria attributes", () => {
    const scorecard = createMockScorecard({
      score_by_document_type: { SOP: 90.0 },
    });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    const progressBar = screen.getByRole("progressbar", { name: "SOP: 90.0" });
    expect(progressBar).toBeInTheDocument();
    expect(progressBar).toHaveAttribute("aria-valuenow", "90");
    expect(progressBar).toHaveAttribute("aria-valuemin", "0");
    expect(progressBar).toHaveAttribute("aria-valuemax", "100");
  });

  // -------------------------------------------------------------------------
  // 9. Last updated timestamp
  // -------------------------------------------------------------------------
  it("displays last updated timestamp", () => {
    const scorecard = createMockScorecard({ last_updated: "2024-06-15T10:30:00Z" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText(/Last updated:/)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Fetches scorecard on mount
  // -------------------------------------------------------------------------
  it("calls fetchScorecard on mount", () => {
    mockStoreState({ scorecard: null });

    render(<ComplianceScorecard />);

    expect(mockFetchScorecard).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // 11. Accessibility
  // -------------------------------------------------------------------------
  it("has proper aria-label on the main container", () => {
    const scorecard = createMockScorecard();
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByLabelText("Compliance scorecard")).toBeInTheDocument();
  });

  it("renders document type list with proper role", () => {
    const scorecard = createMockScorecard({
      score_by_document_type: { SOP: 85.0 },
    });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(
      screen.getByRole("list", { name: "Score by document type" }),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 12. Edge case: score at boundaries
  // -------------------------------------------------------------------------
  it("handles score of 0 correctly", () => {
    const scorecard = createMockScorecard({ overall_score: 0, risk_band: "Critical" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText("0.0")).toBeInTheDocument();
    expect(screen.getByLabelText("Risk band: Critical")).toBeInTheDocument();
  });

  it("handles score of 100 correctly", () => {
    const scorecard = createMockScorecard({ overall_score: 100, risk_band: "Excellent" });
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText("100.0")).toBeInTheDocument();
    expect(screen.getByLabelText("Risk band: Excellent")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 13. Header
  // -------------------------------------------------------------------------
  it("displays Audit Readiness header", () => {
    const scorecard = createMockScorecard();
    mockStoreState({ scorecard });

    render(<ComplianceScorecard />);

    expect(screen.getByText("Audit Readiness")).toBeInTheDocument();
  });
});
