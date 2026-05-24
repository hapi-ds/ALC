import { describe, it, expect, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for SeverityHeatmap component
 *
 * Tests: grid rendering, color intensity, empty state, chapter sorting,
 * severity column ordering, accessibility attributes.
 *
 * Validates: Requirements 11.4, 5.3
 */

import { SeverityHeatmap } from "../SeverityHeatmap";
import type { HeatmapFinding } from "../SeverityHeatmap";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createFinding(
  chapter: string,
  severity: HeatmapFinding["severity"],
): HeatmapFinding {
  return { chapter, severity };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SeverityHeatmap", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // 1. Empty state
  // -------------------------------------------------------------------------
  it("renders empty state when no findings are provided", () => {
    render(<SeverityHeatmap findings={[]} />);

    expect(screen.getByText("No findings to display")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Renders grid with correct chapters on Y-axis
  // -------------------------------------------------------------------------
  it("renders chapters as rows in alphabetical order", () => {
    const findings: HeatmapFinding[] = [
      createFinding("Chapter 3: Results", "Major"),
      createFinding("Chapter 1: Introduction", "Critical"),
      createFinding("Chapter 2: Methods", "Minor"),
    ];

    render(<SeverityHeatmap findings={findings} />);

    const rows = screen.getAllByRole("row");
    // First row is header, then data rows in alphabetical order
    expect(rows).toHaveLength(4); // 1 header + 3 data rows

    // Check alphabetical ordering via row content
    expect(rows[1]).toHaveTextContent("Chapter 1: Introduction");
    expect(rows[2]).toHaveTextContent("Chapter 2: Methods");
    expect(rows[3]).toHaveTextContent("Chapter 3: Results");
  });

  // -------------------------------------------------------------------------
  // 3. Renders severity levels as columns
  // -------------------------------------------------------------------------
  it("renders all four severity levels as column headers", () => {
    const findings: HeatmapFinding[] = [createFinding("Chapter 1", "Critical")];

    render(<SeverityHeatmap findings={findings} />);

    const headers = screen.getAllByRole("columnheader");
    const headerTexts = headers.map((h) => h.textContent);

    expect(headerTexts).toContain("Critical");
    expect(headerTexts).toContain("Major");
    expect(headerTexts).toContain("Minor");
    expect(headerTexts).toContain("Informational");
  });

  // -------------------------------------------------------------------------
  // 4. Displays correct counts in cells
  // -------------------------------------------------------------------------
  it("displays finding counts in the correct cells", () => {
    const findings: HeatmapFinding[] = [
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 1", "Major"),
      createFinding("Chapter 2", "Minor"),
    ];

    render(<SeverityHeatmap findings={findings} />);

    // Chapter 1 has 2 Critical findings
    expect(
      screen.getByLabelText("Chapter 1, Critical: 2 findings"),
    ).toHaveTextContent("2");

    // Chapter 1 has 1 Major finding
    expect(
      screen.getByLabelText("Chapter 1, Major: 1 finding"),
    ).toHaveTextContent("1");

    // Chapter 2 has 1 Minor finding
    expect(
      screen.getByLabelText("Chapter 2, Minor: 1 finding"),
    ).toHaveTextContent("1");
  });

  // -------------------------------------------------------------------------
  // 5. Displays dash for zero-count cells
  // -------------------------------------------------------------------------
  it("displays dash for cells with zero findings", () => {
    const findings: HeatmapFinding[] = [
      createFinding("Chapter 1", "Critical"),
    ];

    render(<SeverityHeatmap findings={findings} />);

    // Chapter 1, Major should show dash
    expect(
      screen.getByLabelText("Chapter 1, Major: 0 findings"),
    ).toHaveTextContent("—");
  });

  // -------------------------------------------------------------------------
  // 6. Color intensity scales with count
  // -------------------------------------------------------------------------
  it("applies higher intensity color class for cells with more findings", () => {
    // Create findings where Chapter 1 has 4 Critical (max) and Chapter 2 has 1 Critical
    const findings: HeatmapFinding[] = [
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 2", "Critical"),
    ];

    render(<SeverityHeatmap findings={findings} />);

    const highCell = screen.getByLabelText("Chapter 1, Critical: 4 findings");
    const lowCell = screen.getByLabelText("Chapter 2, Critical: 1 finding");

    // High count cell should have darker red
    expect(highCell.className).toContain("bg-red-600");
    // Low count cell (1/4 = 0.25) should have lighter red
    expect(lowCell.className).toContain("bg-red-100");
  });

  // -------------------------------------------------------------------------
  // 7. Different severity colors
  // -------------------------------------------------------------------------
  it("uses correct color families for each severity level", () => {
    const findings: HeatmapFinding[] = [
      createFinding("Chapter 1", "Critical"),
      createFinding("Chapter 1", "Major"),
      createFinding("Chapter 1", "Minor"),
      createFinding("Chapter 1", "Informational"),
    ];

    render(<SeverityHeatmap findings={findings} />);

    const criticalCell = screen.getByLabelText("Chapter 1, Critical: 1 finding");
    const majorCell = screen.getByLabelText("Chapter 1, Major: 1 finding");
    const minorCell = screen.getByLabelText("Chapter 1, Minor: 1 finding");
    const infoCell = screen.getByLabelText("Chapter 1, Informational: 1 finding");

    // All have count 1 and max is 1, so ratio = 1.0 → highest intensity
    expect(criticalCell.className).toContain("bg-red");
    expect(majorCell.className).toContain("bg-orange");
    expect(minorCell.className).toContain("bg-yellow");
    expect(infoCell.className).toContain("bg-blue");
  });

  // -------------------------------------------------------------------------
  // 8. Accessibility — region role and label
  // -------------------------------------------------------------------------
  it("has proper accessibility attributes", () => {
    const findings: HeatmapFinding[] = [createFinding("Chapter 1", "Critical")];

    render(<SeverityHeatmap findings={findings} />);

    expect(
      screen.getByRole("region", { name: "Severity heatmap" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Severity heatmap grid" }),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Handles "Unknown" chapter for findings without chapter
  // -------------------------------------------------------------------------
  it("groups findings with empty chapter under 'Unknown'", () => {
    const findings: HeatmapFinding[] = [
      { severity: "Major", chapter: "" },
      { severity: "Major", chapter: "" },
    ];

    render(<SeverityHeatmap findings={findings} />);

    expect(
      screen.getByLabelText("Unknown, Major: 2 findings"),
    ).toHaveTextContent("2");
  });

  // -------------------------------------------------------------------------
  // 10. Title heading is rendered
  // -------------------------------------------------------------------------
  it("renders the heatmap title", () => {
    const findings: HeatmapFinding[] = [createFinding("Chapter 1", "Critical")];

    render(<SeverityHeatmap findings={findings} />);

    expect(screen.getByText("Finding Severity Heatmap")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Legend is rendered
  // -------------------------------------------------------------------------
  it("renders the intensity legend", () => {
    const findings: HeatmapFinding[] = [createFinding("Chapter 1", "Critical")];

    render(<SeverityHeatmap findings={findings} />);

    const legend = screen.getByLabelText("Heatmap legend");
    expect(legend).toBeInTheDocument();
    expect(legend).toHaveTextContent("Intensity:");
    expect(legend).toHaveTextContent("None");
    expect(legend).toHaveTextContent("Low");
    expect(legend).toHaveTextContent("Medium");
    expect(legend).toHaveTextContent("High");
  });
});
