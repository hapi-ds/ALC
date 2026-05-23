/**
 * Unit tests for AlignmentSummaryPanel component.
 *
 * Tests cover:
 * - Alignment score display with correct color coding
 * - Total video steps count
 * - Total SOP steps count
 * - Matched steps count
 * - Missing steps count
 * - Extra steps count
 * - Reordered steps count
 * - Report generation date
 * - Linked SOP title with clickable link
 *
 * Requirements: 11.5
 */

import { describe, it, expect, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { AlignmentSummaryPanel } from "../AlignmentSummaryPanel";
import type { DiscrepancyReportWithSOP } from "@/types/videoAlignment";

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function createReport(overrides: Partial<DiscrepancyReportWithSOP> = {}): DiscrepancyReportWithSOP {
  return {
    alignment_score: 0.75,
    matched_steps: [
      {
        video_step_description: "Step A",
        sop_step_text: "SOP Step A",
        similarity_score: 0.9,
        video_timestamp_start: 0,
        video_timestamp_end: 10,
      },
      {
        video_step_description: "Step B",
        sop_step_text: "SOP Step B",
        similarity_score: 0.85,
        video_timestamp_start: 10,
        video_timestamp_end: 20,
      },
      {
        video_step_description: "Step C",
        sop_step_text: "SOP Step C",
        similarity_score: 0.88,
        video_timestamp_start: 20,
        video_timestamp_end: 30,
      },
    ],
    missing_steps: [
      {
        step_description: "Missing step",
        source: "video",
        severity: "major",
        recommendation: "Add to SOP",
      },
    ],
    extra_steps: [
      {
        step_description: "Extra step",
        source: "sop",
        severity: "minor",
        recommendation: "Review",
      },
      {
        step_description: "Another extra",
        source: "sop",
        severity: "minor",
        recommendation: "Review",
      },
    ],
    order_mismatches: [
      {
        video_step_description: "Reordered step",
        sop_step_text: "SOP reordered",
        video_position: 2,
        sop_position: 5,
        severity: "major",
      },
    ],
    total_video_steps: 8,
    total_sop_steps: 10,
    generated_at: "2024-06-15T14:30:00Z",
    requires_review: false,
    linked_sop: {
      document_uuid: "sop-uuid-123",
      title: "Cleaning Procedure SOP",
      version: "2.1",
      link: "/documents/sop-uuid-123",
    },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AlignmentSummaryPanel", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // 1. Alignment score
  // -------------------------------------------------------------------------

  describe("Alignment Score", () => {
    it("displays alignment score as percentage", () => {
      const report = createReport({ alignment_score: 0.75 });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Alignment score: 75%")).toBeInTheDocument();
      expect(screen.getByText("75% Alignment")).toBeInTheDocument();
    });

    it("uses green styling for score >= 80%", () => {
      const report = createReport({ alignment_score: 0.85 });
      render(<AlignmentSummaryPanel report={report} />);

      const badge = screen.getByLabelText("Alignment score: 85%");
      expect(badge.className).toContain("bg-green");
    });

    it("uses yellow styling for score 50-79%", () => {
      const report = createReport({ alignment_score: 0.65 });
      render(<AlignmentSummaryPanel report={report} />);

      const badge = screen.getByLabelText("Alignment score: 65%");
      expect(badge.className).toContain("bg-yellow");
    });

    it("uses red styling for score < 50%", () => {
      const report = createReport({ alignment_score: 0.3 });
      render(<AlignmentSummaryPanel report={report} />);

      const badge = screen.getByLabelText("Alignment score: 30%");
      expect(badge.className).toContain("bg-red");
    });
  });

  // -------------------------------------------------------------------------
  // 2. Step counts
  // -------------------------------------------------------------------------

  describe("Step Counts", () => {
    it("displays total video steps count", () => {
      const report = createReport({ total_video_steps: 12 });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Video steps count")).toHaveTextContent("12");
      expect(screen.getByText("Video Steps")).toBeInTheDocument();
    });

    it("displays total SOP steps count", () => {
      const report = createReport({ total_sop_steps: 15 });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("SOP steps count")).toHaveTextContent("15");
      expect(screen.getByText("SOP Steps")).toBeInTheDocument();
    });

    it("displays matched steps count", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "A",
            sop_step_text: "B",
            similarity_score: 0.9,
            video_timestamp_start: 0,
            video_timestamp_end: 5,
          },
          {
            video_step_description: "C",
            sop_step_text: "D",
            similarity_score: 0.85,
            video_timestamp_start: 5,
            video_timestamp_end: 10,
          },
        ],
      });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Matched steps count")).toHaveTextContent("2");
      expect(screen.getByText("Matched")).toBeInTheDocument();
    });

    it("displays missing steps count", () => {
      const report = createReport({
        missing_steps: [
          {
            step_description: "Missing 1",
            source: "video",
            severity: "major",
            recommendation: "Fix",
          },
          {
            step_description: "Missing 2",
            source: "video",
            severity: "critical",
            recommendation: "Fix now",
          },
        ],
      });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Missing steps count")).toHaveTextContent("2");
      expect(screen.getByText("Missing")).toBeInTheDocument();
    });

    it("displays extra steps count", () => {
      const report = createReport({
        extra_steps: [
          {
            step_description: "Extra 1",
            source: "sop",
            severity: "minor",
            recommendation: "Review",
          },
        ],
      });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Extra steps count")).toHaveTextContent("1");
      expect(screen.getByText("Extra")).toBeInTheDocument();
    });

    it("displays reordered steps count", () => {
      const report = createReport({
        order_mismatches: [
          {
            video_step_description: "Reordered",
            sop_step_text: "SOP",
            video_position: 1,
            sop_position: 4,
            severity: "major",
          },
          {
            video_step_description: "Reordered 2",
            sop_step_text: "SOP 2",
            video_position: 3,
            sop_position: 6,
            severity: "minor",
          },
        ],
      });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Reordered steps count")).toHaveTextContent("2");
      expect(screen.getByText("Reordered")).toBeInTheDocument();
    });

    it("displays zero counts correctly", () => {
      const report = createReport({
        matched_steps: [],
        missing_steps: [],
        extra_steps: [],
        order_mismatches: [],
        total_video_steps: 0,
        total_sop_steps: 0,
      });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Video steps count")).toHaveTextContent("0");
      expect(screen.getByLabelText("SOP steps count")).toHaveTextContent("0");
      expect(screen.getByLabelText("Matched steps count")).toHaveTextContent("0");
      expect(screen.getByLabelText("Missing steps count")).toHaveTextContent("0");
      expect(screen.getByLabelText("Extra steps count")).toHaveTextContent("0");
      expect(screen.getByLabelText("Reordered steps count")).toHaveTextContent("0");
    });
  });

  // -------------------------------------------------------------------------
  // 3. Generation date
  // -------------------------------------------------------------------------

  describe("Generation Date", () => {
    it("displays the report generation date", () => {
      const report = createReport({ generated_at: "2024-06-15T14:30:00Z" });
      render(<AlignmentSummaryPanel report={report} />);

      // The date is formatted via toLocaleString, so we check for the aria-label
      const dateEl = screen.getByLabelText(/Generated on/);
      expect(dateEl).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 4. Linked SOP
  // -------------------------------------------------------------------------

  describe("Linked SOP", () => {
    it("displays linked SOP title with version", () => {
      const report = createReport({
        linked_sop: {
          document_uuid: "sop-123",
          title: "Equipment Maintenance SOP",
          version: "3.0",
          link: "/documents/sop-123",
        },
      });
      render(<AlignmentSummaryPanel report={report} />);

      const link = screen.getByLabelText("Linked SOP: Equipment Maintenance SOP");
      expect(link).toBeInTheDocument();
      expect(link).toHaveTextContent("Equipment Maintenance SOP (v3.0)");
    });

    it("renders SOP title as a clickable link", () => {
      const report = createReport({
        linked_sop: {
          document_uuid: "sop-456",
          title: "Safety Protocol",
          version: "1.2",
          link: "/documents/sop-456",
        },
      });
      render(<AlignmentSummaryPanel report={report} />);

      const link = screen.getByLabelText("Linked SOP: Safety Protocol");
      expect(link.tagName).toBe("A");
      expect(link).toHaveAttribute("href", "/documents/sop-456");
    });

    it("does not render SOP link when linked_sop is undefined", () => {
      const report = createReport({ linked_sop: undefined });
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.queryByLabelText(/Linked SOP:/)).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 5. Accessibility
  // -------------------------------------------------------------------------

  describe("Accessibility", () => {
    it("has proper aria-label on the container", () => {
      const report = createReport();
      render(<AlignmentSummaryPanel report={report} />);

      expect(screen.getByLabelText("Alignment summary")).toBeInTheDocument();
    });
  });
});
