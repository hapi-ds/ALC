/**
 * Unit tests for VideoAlignment component.
 *
 * Tests cover:
 * - Alignment score badge rendering with correct color coding (green/yellow/red)
 * - Side-by-side comparison view with matched steps
 * - Visual connectors showing similarity scores
 * - Color-coded discrepancies (critical=red, major=orange, minor=yellow)
 * - Severity legend display
 * - Order mismatch rendering
 * - Missing and extra step rendering
 * - Requires review banner
 * - Summary statistics
 *
 * Requirements: 11.1, 11.2, 11.3
 */

import { describe, it, expect, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { VideoAlignment } from "../VideoAlignment";
import type { DiscrepancyReport } from "@/types/videoAlignment";

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function createReport(overrides: Partial<DiscrepancyReport> = {}): DiscrepancyReport {
  return {
    alignment_score: 0.85,
    matched_steps: [
      {
        video_step_description: "Operator dons gloves",
        sop_step_text: "Put on protective gloves",
        similarity_score: 0.92,
        video_timestamp_start: 10,
        video_timestamp_end: 25,
      },
    ],
    missing_steps: [],
    extra_steps: [],
    order_mismatches: [],
    total_video_steps: 5,
    total_sop_steps: 5,
    generated_at: "2024-06-15T14:00:00Z",
    requires_review: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VideoAlignment", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // 1. Alignment score badge color coding
  // -------------------------------------------------------------------------

  describe("Alignment Score Badge", () => {
    it("renders green badge for score >= 80%", () => {
      const report = createReport({ alignment_score: 0.85 });
      render(<VideoAlignment report={report} />);

      const badge = screen.getByLabelText("Alignment score: 85%");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("85%");
      expect(badge.className).toContain("bg-green");
    });

    it("renders green badge for exactly 80%", () => {
      const report = createReport({ alignment_score: 0.8 });
      render(<VideoAlignment report={report} />);

      const badge = screen.getByLabelText("Alignment score: 80%");
      expect(badge).toBeInTheDocument();
      expect(badge.className).toContain("bg-green");
    });

    it("renders yellow badge for score 50-79%", () => {
      const report = createReport({ alignment_score: 0.65 });
      render(<VideoAlignment report={report} />);

      const badge = screen.getByLabelText("Alignment score: 65%");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("65%");
      expect(badge.className).toContain("bg-yellow");
    });

    it("renders yellow badge for exactly 50%", () => {
      const report = createReport({ alignment_score: 0.5 });
      render(<VideoAlignment report={report} />);

      const badge = screen.getByLabelText("Alignment score: 50%");
      expect(badge).toBeInTheDocument();
      expect(badge.className).toContain("bg-yellow");
    });

    it("renders red badge for score < 50%", () => {
      const report = createReport({ alignment_score: 0.3 });
      render(<VideoAlignment report={report} />);

      const badge = screen.getByLabelText("Alignment score: 30%");
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent("30%");
      expect(badge.className).toContain("bg-red");
    });

    it("renders red badge for 0%", () => {
      const report = createReport({ alignment_score: 0 });
      render(<VideoAlignment report={report} />);

      const badge = screen.getByLabelText("Alignment score: 0%");
      expect(badge).toBeInTheDocument();
      expect(badge.className).toContain("bg-red");
    });
  });

  // -------------------------------------------------------------------------
  // 2. Side-by-side comparison view with matched steps
  // -------------------------------------------------------------------------

  describe("Matched Steps - Side-by-side Comparison", () => {
    it("renders matched steps with video step on left and SOP step on right", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "Operator dons gloves",
            sop_step_text: "Put on protective gloves",
            similarity_score: 0.92,
            video_timestamp_start: 10,
            video_timestamp_end: 25,
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Operator dons gloves")).toBeInTheDocument();
      expect(screen.getByText("Put on protective gloves")).toBeInTheDocument();
      expect(screen.getByText("Video Step")).toBeInTheDocument();
      expect(screen.getByText("SOP Step")).toBeInTheDocument();
    });

    it("displays similarity score as visual connector", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "Step A",
            sop_step_text: "Step B",
            similarity_score: 0.88,
            video_timestamp_start: 0,
            video_timestamp_end: 5,
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByLabelText("Similarity: 88%")).toBeInTheDocument();
    });

    it("displays timestamp range for video steps", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "Step A",
            sop_step_text: "Step B",
            similarity_score: 0.9,
            video_timestamp_start: 65,
            video_timestamp_end: 130,
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      // 65s = 1:05, 130s = 2:10
      expect(screen.getByText("1:05 – 2:10")).toBeInTheDocument();
    });

    it("renders multiple matched steps", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "First step",
            sop_step_text: "SOP first",
            similarity_score: 0.95,
            video_timestamp_start: 0,
            video_timestamp_end: 10,
          },
          {
            video_step_description: "Second step",
            sop_step_text: "SOP second",
            similarity_score: 0.82,
            video_timestamp_start: 10,
            video_timestamp_end: 20,
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("First step")).toBeInTheDocument();
      expect(screen.getByText("Second step")).toBeInTheDocument();
      expect(screen.getByText("Matched Steps (2)")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 3. Color-coded discrepancies
  // -------------------------------------------------------------------------

  describe("Discrepancy Color Coding", () => {
    it("renders critical discrepancies with red styling", () => {
      const report = createReport({
        missing_steps: [
          {
            step_description: "Safety check omitted",
            source: "video",
            severity: "critical",
            recommendation: "Add safety check to SOP",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Safety check omitted")).toBeInTheDocument();
      expect(screen.getByText("critical")).toBeInTheDocument();
      // The container should have red background classes
      const container = screen.getByText("critical").closest("div[class*='bg-red']");
      expect(container).not.toBeNull();
    });

    it("renders major discrepancies with orange styling", () => {
      const report = createReport({
        extra_steps: [
          {
            step_description: "Extra calibration step",
            source: "sop",
            severity: "major",
            recommendation: "Review if step is needed",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Extra calibration step")).toBeInTheDocument();
      expect(screen.getByText("major")).toBeInTheDocument();
      const container = screen.getByText("major").closest("div[class*='bg-orange']");
      expect(container).not.toBeNull();
    });

    it("renders minor discrepancies with yellow styling", () => {
      const report = createReport({
        missing_steps: [
          {
            step_description: "Minor documentation note",
            source: "video",
            severity: "minor",
            recommendation: "Consider adding to SOP",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Minor documentation note")).toBeInTheDocument();
      expect(screen.getByText("minor")).toBeInTheDocument();
      const container = screen.getByText("minor").closest("div[class*='bg-yellow']");
      expect(container).not.toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // 4. Severity legend
  // -------------------------------------------------------------------------

  describe("Severity Legend", () => {
    it("displays severity legend when discrepancies exist", () => {
      const report = createReport({
        missing_steps: [
          {
            step_description: "A step",
            source: "video",
            severity: "major",
            recommendation: "Fix it",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      const legend = screen.getByLabelText("Severity legend");
      expect(legend).toBeInTheDocument();
      expect(screen.getByText("Critical")).toBeInTheDocument();
      expect(screen.getByText("Major")).toBeInTheDocument();
      expect(screen.getByText("Minor")).toBeInTheDocument();
    });

    it("does not display severity legend when no discrepancies exist", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "Step",
            sop_step_text: "Step",
            similarity_score: 0.95,
            video_timestamp_start: 0,
            video_timestamp_end: 5,
          },
        ],
        missing_steps: [],
        extra_steps: [],
        order_mismatches: [],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.queryByLabelText("Severity legend")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 5. Order mismatches
  // -------------------------------------------------------------------------

  describe("Order Mismatches", () => {
    it("renders order mismatches with position indicators", () => {
      const report = createReport({
        order_mismatches: [
          {
            video_step_description: "Video step out of order",
            sop_step_text: "SOP step in different position",
            video_position: 3,
            sop_position: 7,
            severity: "major",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Video step out of order")).toBeInTheDocument();
      expect(screen.getByText("SOP step in different position")).toBeInTheDocument();
      expect(screen.getByText("Video Step (position 3)")).toBeInTheDocument();
      expect(screen.getByText("SOP Step (position 7)")).toBeInTheDocument();
      expect(screen.getByText("Order Mismatches (1)")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 6. Missing and extra steps
  // -------------------------------------------------------------------------

  describe("Missing and Extra Steps", () => {
    it("renders missing steps section with correct label", () => {
      const report = createReport({
        missing_steps: [
          {
            step_description: "Step only in video",
            source: "video",
            severity: "major",
            recommendation: "Add to SOP",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Missing from SOP (1)")).toBeInTheDocument();
      expect(screen.getByText("Step only in video")).toBeInTheDocument();
      expect(screen.getByText("Add to SOP")).toBeInTheDocument();
    });

    it("renders extra steps section with correct label", () => {
      const report = createReport({
        extra_steps: [
          {
            step_description: "Step only in SOP",
            source: "sop",
            severity: "minor",
            recommendation: "Verify if needed",
          },
        ],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Extra in SOP (1)")).toBeInTheDocument();
      expect(screen.getByText("Step only in SOP")).toBeInTheDocument();
      expect(screen.getByText("Verify if needed")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 7. Requires review banner
  // -------------------------------------------------------------------------

  describe("Requires Review", () => {
    it("shows review banner when requires_review is true", () => {
      const report = createReport({
        alignment_score: 0.3,
        requires_review: true,
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/requires review/i)).toBeInTheDocument();
    });

    it("does not show review banner when requires_review is false", () => {
      const report = createReport({
        alignment_score: 0.85,
        requires_review: false,
      });
      render(<VideoAlignment report={report} />);

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 8. Summary statistics
  // -------------------------------------------------------------------------

  describe("Summary Statistics", () => {
    it("displays total video steps, SOP steps, matched count, and discrepancy count", () => {
      const report = createReport({
        total_video_steps: 8,
        total_sop_steps: 10,
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
        missing_steps: [
          {
            step_description: "Missing",
            source: "video",
            severity: "major",
            recommendation: "Fix",
          },
        ],
        extra_steps: [
          {
            step_description: "Extra",
            source: "sop",
            severity: "minor",
            recommendation: "Review",
          },
        ],
        order_mismatches: [],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("8")).toBeInTheDocument();
      expect(screen.getByText("10")).toBeInTheDocument();
      expect(screen.getByText("Video Steps")).toBeInTheDocument();
      expect(screen.getByText("SOP Steps")).toBeInTheDocument();
      // Matched count and Discrepancies count are both "2" — use getAllByText
      const twos = screen.getAllByText("2");
      expect(twos.length).toBeGreaterThanOrEqual(2);
      expect(screen.getByText("Matched")).toBeInTheDocument();
      expect(screen.getByText("Discrepancies")).toBeInTheDocument();
    });

    it("displays report generation date", () => {
      const report = createReport({
        generated_at: "2024-06-15T14:00:00Z",
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText(/Report generated:/)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 9. Section heading
  // -------------------------------------------------------------------------

  describe("Section Structure", () => {
    it("renders Video Alignment heading", () => {
      const report = createReport();
      render(<VideoAlignment report={report} />);

      expect(screen.getByText("Video Alignment")).toBeInTheDocument();
    });

    it("renders as a section with proper aria-labelledby", () => {
      const report = createReport();
      render(<VideoAlignment report={report} />);

      const section = screen.getByRole("region", { name: "Video Alignment" });
      expect(section).toBeInTheDocument();
    });

    it("shows no discrepancies message when all steps match", () => {
      const report = createReport({
        matched_steps: [
          {
            video_step_description: "Step",
            sop_step_text: "Step",
            similarity_score: 0.95,
            video_timestamp_start: 0,
            video_timestamp_end: 5,
          },
        ],
        missing_steps: [],
        extra_steps: [],
        order_mismatches: [],
      });
      render(<VideoAlignment report={report} />);

      expect(screen.getByText(/No discrepancies found/)).toBeInTheDocument();
    });
  });
});
