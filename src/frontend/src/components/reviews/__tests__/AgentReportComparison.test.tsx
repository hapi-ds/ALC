import { describe, it, expect, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for AgentReportComparison component
 *
 * Tests: side-by-side rendering, synchronized scrolling, consensus highlighting,
 * contradiction highlighting, empty/insufficient state, finding extraction.
 *
 * Validates: Requirements 11.3
 */

import {
  AgentReportComparison,
  classifyFindings,
  makeFindingKey,
} from "../AgentReportComparison";
import type { AgentReview } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createAgentReview(
  overrides: Partial<AgentReview> & { id: number; agent_name: string },
): AgentReview {
  return {
    agent_definition_id: overrides.id,
    agent_archetype: null,
    status: "Completed",
    report_data: null,
    error_reason: null,
    inference_duration_ms: null,
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

function createReportData(findings: Array<{ chapter: string; severity: string; description: string }>) {
  return {
    summary: "Test summary",
    overall_status: "Pass",
    findings,
    chapter_results: [],
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AgentReportComparison", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // 1. Insufficient reports state
  // -------------------------------------------------------------------------
  it("shows message when fewer than 2 completed reports are provided", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData([]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    expect(
      screen.getByText("At least 2 completed agent reports are required for comparison."),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Renders side-by-side panels for 2 reports
  // -------------------------------------------------------------------------
  it("renders 2 report panels side-by-side", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Regulatory Auditor",
        report_data: createReportData([
          { chapter: "Chapter 1", severity: "Critical", description: "Missing signature" },
        ]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Data Integrity Specialist",
        report_data: createReportData([
          { chapter: "Chapter 1", severity: "Critical", description: "Missing signature" },
        ]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    expect(screen.getByText("Regulatory Auditor")).toBeInTheDocument();
    expect(screen.getByText("Data Integrity Specialist")).toBeInTheDocument();
    expect(screen.getByText("Agent Report Comparison")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Renders up to 4 panels
  // -------------------------------------------------------------------------
  it("renders up to 4 report panels", () => {
    const reviews: AgentReview[] = [
      createAgentReview({ id: 1, agent_name: "Agent A", report_data: createReportData([]) }),
      createAgentReview({ id: 2, agent_name: "Agent B", report_data: createReportData([]) }),
      createAgentReview({ id: 3, agent_name: "Agent C", report_data: createReportData([]) }),
      createAgentReview({ id: 4, agent_name: "Agent D", report_data: createReportData([]) }),
      createAgentReview({ id: 5, agent_name: "Agent E", report_data: createReportData([]) }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    expect(screen.getByText("Agent A")).toBeInTheDocument();
    expect(screen.getByText("Agent B")).toBeInTheDocument();
    expect(screen.getByText("Agent C")).toBeInTheDocument();
    expect(screen.getByText("Agent D")).toBeInTheDocument();
    // Agent E should not be rendered (limit is 4)
    expect(screen.queryByText("Agent E")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 4. Filters out non-completed reviews
  // -------------------------------------------------------------------------
  it("only shows completed reviews with report data", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Completed Agent",
        status: "Completed",
        report_data: createReportData([]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Failed Agent",
        status: "Failed",
        report_data: null,
      }),
      createAgentReview({
        id: 3,
        agent_name: "Another Completed",
        status: "Completed",
        report_data: createReportData([]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    expect(screen.getByText("Completed Agent")).toBeInTheDocument();
    expect(screen.getByText("Another Completed")).toBeInTheDocument();
    expect(screen.queryByText("Failed Agent")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Consensus findings get green border
  // -------------------------------------------------------------------------
  it("highlights consensus findings with green border", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData([
          { chapter: "Chapter 1", severity: "Critical", description: "Missing approval" },
        ]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Agent B",
        report_data: createReportData([
          { chapter: "Chapter 1", severity: "Critical", description: "No approval found" },
        ]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    // Both findings should be marked as consensus
    const consensusCards = screen.getAllByTestId(/report-panel/);
    const allCards = document.querySelectorAll('[data-classification="consensus"]');
    expect(allCards.length).toBe(2);

    allCards.forEach((card) => {
      expect(card.className).toContain("border-green-500");
    });
  });

  // -------------------------------------------------------------------------
  // 6. Contradiction findings get red border
  // -------------------------------------------------------------------------
  it("highlights contradiction findings with red border", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData([
          { chapter: "Chapter 2", severity: "Critical", description: "Severe issue" },
        ]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Agent B",
        report_data: createReportData([
          { chapter: "Chapter 2", severity: "Informational", description: "Minor note" },
        ]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    const contradictionCards = document.querySelectorAll('[data-classification="contradiction"]');
    expect(contradictionCards.length).toBe(2);

    contradictionCards.forEach((card) => {
      expect(card.className).toContain("border-red-500");
    });
  });

  // -------------------------------------------------------------------------
  // 7. Neutral findings have default border
  // -------------------------------------------------------------------------
  it("renders neutral findings with default border", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData([
          { chapter: "Chapter 1", severity: "Minor", description: "Typo found" },
        ]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Agent B",
        report_data: createReportData([
          { chapter: "Chapter 3", severity: "Major", description: "Different chapter" },
        ]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    const neutralCards = document.querySelectorAll('[data-classification="neutral"]');
    expect(neutralCards.length).toBe(2);

    neutralCards.forEach((card) => {
      expect(card.className).toContain("border-border");
    });
  });

  // -------------------------------------------------------------------------
  // 8. Displays finding count per panel
  // -------------------------------------------------------------------------
  it("displays finding count in panel header", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData([
          { chapter: "Ch1", severity: "Critical", description: "Issue 1" },
          { chapter: "Ch2", severity: "Major", description: "Issue 2" },
        ]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Agent B",
        report_data: createReportData([
          { chapter: "Ch1", severity: "Minor", description: "Issue 1" },
        ]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    expect(screen.getByText("2 findings")).toBeInTheDocument();
    expect(screen.getByText("1 finding")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 9. Renders legend
  // -------------------------------------------------------------------------
  it("renders the comparison legend", () => {
    const reviews: AgentReview[] = [
      createAgentReview({ id: 1, agent_name: "Agent A", report_data: createReportData([]) }),
      createAgentReview({ id: 2, agent_name: "Agent B", report_data: createReportData([]) }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    expect(screen.getByText("Consensus")).toBeInTheDocument();
    expect(screen.getByText("Contradiction")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Synchronized scrolling
  // -------------------------------------------------------------------------
  it("synchronizes scroll position across panels", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData(
          Array.from({ length: 20 }, (_, i) => ({
            chapter: `Chapter ${i}`,
            severity: "Minor",
            description: `Finding ${i}`,
          })),
        ),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Agent B",
        report_data: createReportData(
          Array.from({ length: 20 }, (_, i) => ({
            chapter: `Chapter ${i}`,
            severity: "Minor",
            description: `Finding ${i}`,
          })),
        ),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    const panel0 = screen.getByTestId("report-panel-0");
    const panel1 = screen.getByTestId("report-panel-1");

    // Simulate scroll on panel 0
    Object.defineProperty(panel0, "scrollTop", { value: 100, writable: true });
    Object.defineProperty(panel0, "scrollLeft", { value: 0, writable: true });
    fireEvent.scroll(panel0);

    // Panel 1 should have its scrollTop set to match
    expect(panel1.scrollTop).toBe(100);
  });

  // -------------------------------------------------------------------------
  // 11. Shows "No findings" for empty reports
  // -------------------------------------------------------------------------
  it("shows 'No findings' for reports without findings", () => {
    const reviews: AgentReview[] = [
      createAgentReview({
        id: 1,
        agent_name: "Agent A",
        report_data: createReportData([]),
      }),
      createAgentReview({
        id: 2,
        agent_name: "Agent B",
        report_data: createReportData([]),
      }),
    ];

    render(<AgentReportComparison agentReviews={reviews} />);

    const noFindings = screen.getAllByText("No findings");
    expect(noFindings).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// Unit tests for classifyFindings logic
// ---------------------------------------------------------------------------

describe("classifyFindings", () => {
  it("marks findings as consensus when 2+ reports share same chapter+severity", () => {
    const allFindings = [
      [{ chapter: "Ch1", severity: "Critical", description: "A" }],
      [{ chapter: "Ch1", severity: "Critical", description: "B" }],
    ];

    const result = classifyFindings(allFindings);
    expect(result.get(makeFindingKey("Ch1", "Critical"))).toBe("consensus");
  });

  it("marks findings as contradiction when one has Critical/Major and another has nothing", () => {
    const allFindings = [
      [{ chapter: "Ch1", severity: "Critical", description: "Severe" }],
      [{ chapter: "Ch1", severity: "Informational", description: "Just a note" }],
    ];

    const result = classifyFindings(allFindings);
    expect(result.get(makeFindingKey("Ch1", "Critical"))).toBe("contradiction");
    expect(result.get(makeFindingKey("Ch1", "Informational"))).toBe("contradiction");
  });

  it("returns empty map for empty findings", () => {
    const result = classifyFindings([[], []]);
    expect(result.size).toBe(0);
  });

  it("marks as neutral when findings don't overlap", () => {
    const allFindings = [
      [{ chapter: "Ch1", severity: "Minor", description: "A" }],
      [{ chapter: "Ch2", severity: "Major", description: "B" }],
    ];

    const result = classifyFindings(allFindings);
    // Neither should be consensus or contradiction
    expect(result.has(makeFindingKey("Ch1", "Minor"))).toBe(false);
    expect(result.has(makeFindingKey("Ch2", "Major"))).toBe(false);
  });

  it("contradiction takes precedence over consensus", () => {
    // 3 reports: 2 have Critical for Ch1, 1 has only Informational for Ch1
    const allFindings = [
      [{ chapter: "Ch1", severity: "Critical", description: "A" }],
      [{ chapter: "Ch1", severity: "Critical", description: "B" }],
      [{ chapter: "Ch1", severity: "Informational", description: "C" }],
    ];

    const result = classifyFindings(allFindings);
    // Critical should be contradiction (not consensus) because there's a conflict
    expect(result.get(makeFindingKey("Ch1", "Critical"))).toBe("contradiction");
  });
});
