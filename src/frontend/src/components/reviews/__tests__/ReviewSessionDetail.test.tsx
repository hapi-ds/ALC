import { describe, it, expect, vi, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for ReviewSessionDetail component
 *
 * Tests: session header, progress tracker, agent reports, master summary,
 * approve/reject buttons, change reason modal.
 *
 * Validates: Requirements 11.2, 5.2, 5.6, 5.7
 */

import { ReviewSessionDetail } from "../ReviewSessionDetail";
import type { ReviewSession, AgentReview, MasterSummary } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createAgentReview(overrides: Partial<AgentReview> = {}): AgentReview {
  return {
    id: 1,
    agent_definition_id: 10,
    agent_name: "Regulatory Compliance Auditor",
    agent_archetype: "regulatory-compliance-auditor",
    status: "Completed",
    report_data: {
      summary: "Document meets basic compliance requirements.",
      overall_status: "Pass",
      findings: [
        {
          severity: "Minor",
          chapter: "Chapter 2",
          description: "Missing revision date",
          recommendation: "Add revision date to header",
        },
      ],
      chapter_results: [
        { chapter: "Chapter 1", status: "Pass" },
        { chapter: "Chapter 2", status: "Needs Attention" },
      ],
    },
    error_reason: null,
    inference_duration_ms: 4500,
    started_at: "2024-01-15T10:00:00Z",
    completed_at: "2024-01-15T10:00:04Z",
    ...overrides,
  };
}

function createMasterSummary(overrides: Partial<MasterSummary> = {}): MasterSummary {
  return {
    id: 1,
    compliance_score: 85.5,
    risk_assessment: "Good",
    executive_summary: "The document is largely compliant with minor issues.",
    consensus_findings: [
      { severity: "Minor", chapter: "Chapter 2", description: "Missing revision date" },
    ],
    contradictions: [
      { severity: "Major", chapter: "Chapter 3", description: "Agents disagree on data integrity" },
    ],
    prioritized_action_items: [
      { title: "Add revision date to Chapter 2 header" },
      { title: "Clarify data integrity section" },
    ],
    ...overrides,
  };
}

function createSession(overrides: Partial<ReviewSession> = {}): ReviewSession {
  return {
    id: 1,
    document_id: 100,
    document_title: "SOP-001 Manufacturing Process",
    document_type: "SOP",
    status: "Completed",
    compliance_score: 85.5,
    summary_failed: false,
    submitted_by: 1,
    submitted_at: "2024-01-15T09:00:00Z",
    completed_at: "2024-01-15T10:05:00Z",
    agent_reviews: [
      createAgentReview({ id: 1, agent_name: "Regulatory Compliance Auditor" }),
      createAgentReview({ id: 2, agent_name: "Data Integrity Specialist", agent_archetype: "data-integrity-specialist" }),
    ],
    master_summary: createMasterSummary(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ReviewSessionDetail", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Session Header
  // -------------------------------------------------------------------------
  it("renders session header with document title and status", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText("SOP-001 Manufacturing Process")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("SOP")).toBeInTheDocument();
    // Score appears in both header and master summary
    expect(screen.getAllByText("85.5%").length).toBeGreaterThanOrEqual(1);
  });

  it("shows summary_failed warning when applicable", () => {
    const session = createSession({ summary_failed: true, master_summary: null });
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(
      screen.getByText(/Master summary generation failed/)
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Progress Tracker
  // -------------------------------------------------------------------------
  it("renders progress tracker with agent count", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    // Text is split across elements, use a matcher function
    expect(screen.getByLabelText("2 of 2 agents completed")).toBeInTheDocument();
    expect(screen.getAllByText("Regulatory Compliance Auditor").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Data Integrity Specialist").length).toBeGreaterThanOrEqual(1);
  });

  it("shows elapsed time for completed agents", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    // 4500ms = 4s
    const timeElements = screen.getAllByText("4s");
    expect(timeElements.length).toBeGreaterThan(0);
  });

  it("shows error reason for failed agents", () => {
    const session = createSession({
      agent_reviews: [
        createAgentReview({ id: 1, status: "Failed", error_reason: "timeout" }),
        createAgentReview({ id: 2, status: "Completed" }),
      ],
    });
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    // Both Failed and Completed count as "completed" in the progress tracker
    expect(screen.getByLabelText("2 of 2 agents completed")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Master Summary
  // -------------------------------------------------------------------------
  it("renders master summary with score and risk assessment", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText("Master Auditor Summary")).toBeInTheDocument();
    // Score appears in multiple places
    expect(screen.getAllByText("85.5%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Good")).toBeInTheDocument();
    expect(
      screen.getByText("The document is largely compliant with minor issues.")
    ).toBeInTheDocument();
  });

  it("renders consensus findings and contradictions", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText("Consensus Findings (1)")).toBeInTheDocument();
    expect(screen.getByText("Contradictions (1)")).toBeInTheDocument();
    expect(screen.getByText("Prioritized Action Items (2)")).toBeInTheDocument();
  });

  it("does not render master summary when not available", () => {
    const session = createSession({ master_summary: null });
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.queryByText("Master Auditor Summary")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Agent Reports (expandable)
  // -------------------------------------------------------------------------
  it("renders expandable agent report cards", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByText("Individual Agent Reports")).toBeInTheDocument();

    // Cards are collapsed by default — findings table not visible
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("expands agent report card on click to show findings table", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    // Click the first agent card header
    const buttons = screen.getAllByRole("button", { expanded: false });
    const agentButton = buttons.find((btn) =>
      btn.textContent?.includes("Regulatory Compliance Auditor")
    );
    expect(agentButton).toBeDefined();
    fireEvent.click(agentButton!);

    // Now the findings table should be visible
    expect(screen.getByRole("table")).toBeInTheDocument();
    // "Missing revision date" appears in both consensus findings and the table
    expect(screen.getAllByText("Missing revision date").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Add revision date to header")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Approve/Reject Buttons
  // -------------------------------------------------------------------------
  it("shows approve and reject buttons for completed sessions", () => {
    const session = createSession({ status: "Completed" });
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /Approve/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reject/i })).toBeInTheDocument();
  });

  it("does not show approve/reject buttons for non-completed sessions", () => {
    const session = createSession({ status: "InProgress" });
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: /Approve/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Reject/i })).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Change Reason Modal
  // -------------------------------------------------------------------------
  it("opens change reason modal on approve click", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Approve Review")).toBeInTheDocument();
    expect(screen.getByLabelText("Change Reason")).toBeInTheDocument();
  });

  it("opens change reason modal on reject click", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Reject Review")).toBeInTheDocument();
  });

  it("calls onApprove with change reason when confirmed", () => {
    const onApprove = vi.fn();
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={onApprove}
        onReject={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve/i }));

    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "Reviewed and approved" } });

    fireEvent.click(screen.getByRole("button", { name: /Confirm Approval/i }));

    expect(onApprove).toHaveBeenCalledWith("Reviewed and approved");
  });

  it("calls onReject with change reason when confirmed", () => {
    const onReject = vi.fn();
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={onReject}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Reject/i }));

    const textarea = screen.getByLabelText("Change Reason");
    fireEvent.change(textarea, { target: { value: "Critical findings unresolved" } });

    fireEvent.click(screen.getByRole("button", { name: /Confirm Rejection/i }));

    expect(onReject).toHaveBeenCalledWith("Critical findings unresolved");
  });

  it("disables confirm button when change reason is empty", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve/i }));

    const confirmButton = screen.getByRole("button", { name: /Confirm Approval/i });
    expect(confirmButton).toBeDisabled();
  });

  it("closes modal on cancel", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Approve/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Error display
  // -------------------------------------------------------------------------
  it("displays approve error message", () => {
    const session = createSession();
    render(
      <ReviewSessionDetail
        session={session}
        approveError="Only completed sessions can be approved"
        onApprove={vi.fn()}
        onReject={vi.fn()}
      />
    );

    expect(
      screen.getByText("Only completed sessions can be approved")
    ).toBeInTheDocument();
  });
});
