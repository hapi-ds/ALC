import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for SubmitForReviewModal component
 *
 * Tests: rendering, profile selection, change reason validation,
 * submission flow, error handling, and accessibility.
 *
 * Validates: Requirements 11.8
 */

import { SubmitForReviewModal } from "../SubmitForReviewModal";
import type { AuditProfile } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockProfiles: AuditProfile[] = [
  {
    id: 1,
    company_id: 1,
    name: "GMP Full Review",
    description: "Full GMP compliance review",
    regulatory_frameworks: ["GMP"],
    assigned_agent_ids: [10, 11, 12],
    quorum: 2,
    severity_thresholds: { critical: 25, major: 10, minor: 3, informational: 0.5 },
    is_default: true,
    is_active: true,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: null,
  },
  {
    id: 2,
    company_id: 1,
    name: "ISO 13485 Quick",
    description: "Quick ISO review",
    regulatory_frameworks: ["ISO 13485"],
    assigned_agent_ids: [10, 11],
    quorum: 1,
    severity_thresholds: { critical: 25, major: 10, minor: 3, informational: 0.5 },
    is_default: false,
    is_active: true,
    created_at: "2024-01-02T00:00:00Z",
    updated_at: null,
  },
  {
    id: 3,
    company_id: 1,
    name: "Inactive Profile",
    description: null,
    regulatory_frameworks: ["GLP"],
    assigned_agent_ids: [10],
    quorum: 1,
    severity_thresholds: { critical: 25, major: 10, minor: 3, informational: 0.5 },
    is_default: false,
    is_active: false,
    created_at: "2024-01-03T00:00:00Z",
    updated_at: null,
  },
];

vi.mock("@/lib/reviews-api", () => ({
  listAuditProfiles: vi.fn(),
  submitReview: vi.fn(),
}));

import { listAuditProfiles, submitReview } from "@/lib/reviews-api";

const mockListAuditProfiles = vi.mocked(listAuditProfiles);
const mockSubmitReview = vi.mocked(submitReview);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const defaultProps = {
  open: true,
  onClose: vi.fn(),
  documentId: 42,
  documentVersionId: 7,
  documentTitle: "SOP-001 Manufacturing Process",
  onSubmitted: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SubmitForReviewModal", () => {
  beforeEach(() => {
    mockListAuditProfiles.mockResolvedValue(mockProfiles);
  });

  it("does not render when open is false", () => {
    render(<SubmitForReviewModal {...defaultProps} open={false} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the dialog when open is true", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Submit for Review" })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/SOP-001 Manufacturing Process/)
    ).toBeInTheDocument();
  });

  it("displays audit profile dropdown after loading", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    // Initially shows loading
    expect(screen.getByText("Loading profiles…")).toBeInTheDocument();

    // After profiles load, shows the select
    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Audit Profile") as HTMLSelectElement;
    // Default option + 2 active profiles (inactive is filtered out)
    expect(select.options).toHaveLength(3);
    expect(select.options[0].textContent).toContain("Use default (GMP Full Review)");
    expect(select.options[1].textContent).toContain("GMP Full Review");
    expect(select.options[2].textContent).toContain("ISO 13485 Quick");
  });

  it("shows default profile info text", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText(/Default: GMP Full Review \(2 agent quorum\)/)
      ).toBeInTheDocument();
    });
  });

  it("disables submit button when change reason is empty", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const submitButton = screen.getByRole("button", { name: /Submit for Review/i });
    expect(submitButton).toBeDisabled();
  });

  it("enables submit button when change reason is provided", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/Change Reason/i);
    fireEvent.change(input, { target: { value: "Routine compliance review" } });

    const submitButton = screen.getByRole("button", { name: /Submit for Review/i });
    expect(submitButton).not.toBeDisabled();
  });

  it("calls submitReview with default profile when no profile selected", async () => {
    mockSubmitReview.mockResolvedValue({
      id: 99,
      document_id: 42,
      document_title: "SOP-001",
      document_type: "SOP",
      status: "Pending",
      compliance_score: null,
      summary_failed: false,
      submitted_by: 1,
      submitted_at: "2024-01-15T10:00:00Z",
      completed_at: null,
      agent_reviews: null,
      master_summary: null,
    });

    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/Change Reason/i);
    fireEvent.change(input, { target: { value: "Annual review" } });

    const submitButton = screen.getByRole("button", { name: /Submit for Review/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockSubmitReview).toHaveBeenCalledWith(
        {
          document_id: 42,
          document_version_id: 7,
          audit_profile_id: null,
        },
        "Annual review"
      );
    });

    expect(defaultProps.onSubmitted).toHaveBeenCalledWith(99);
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it("calls submitReview with selected profile ID", async () => {
    mockSubmitReview.mockResolvedValue({
      id: 100,
      document_id: 42,
      document_title: "SOP-001",
      document_type: "SOP",
      status: "Pending",
      compliance_score: null,
      summary_failed: false,
      submitted_by: 1,
      submitted_at: "2024-01-15T10:00:00Z",
      completed_at: null,
      agent_reviews: null,
      master_summary: null,
    });

    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Audit Profile");
    fireEvent.change(select, { target: { value: "2" } });

    const input = screen.getByLabelText(/Change Reason/i);
    fireEvent.change(input, { target: { value: "ISO audit prep" } });

    const submitButton = screen.getByRole("button", { name: /Submit for Review/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockSubmitReview).toHaveBeenCalledWith(
        {
          document_id: 42,
          document_version_id: 7,
          audit_profile_id: 2,
        },
        "ISO audit prep"
      );
    });

    expect(defaultProps.onSubmitted).toHaveBeenCalledWith(100);
  });

  it("shows error message on 409 conflict", async () => {
    mockSubmitReview.mockRejectedValue(new Error("API error 409 on /api/reviews"));

    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/Change Reason/i);
    fireEvent.change(input, { target: { value: "Review needed" } });

    const submitButton = screen.getByRole("button", { name: /Submit for Review/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(
        screen.getByText(/already has an active review session/)
      ).toBeInTheDocument();
    });
  });

  it("shows error message on 422 no default profile", async () => {
    mockSubmitReview.mockRejectedValue(new Error("API error 422 on /api/reviews"));

    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    const input = screen.getByLabelText(/Change Reason/i);
    fireEvent.change(input, { target: { value: "Review needed" } });

    fireEvent.click(screen.getByRole("button", { name: /Submit for Review/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/No default audit profile configured/)
      ).toBeInTheDocument();
    });
  });

  it("closes on Escape key press", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.keyDown(document, { key: "Escape" });
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it("closes when clicking the X button", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Close dialog"));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it("closes when clicking Cancel button", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByLabelText("Audit Profile")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Cancel/i }));
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  it("handles profile loading error gracefully", async () => {
    mockListAuditProfiles.mockRejectedValue(new Error("Network error"));

    render(<SubmitForReviewModal {...defaultProps} />);

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load profiles/)
      ).toBeInTheDocument();
    });

    // Should still allow submission (will use default)
    const input = screen.getByLabelText(/Change Reason/i);
    fireEvent.change(input, { target: { value: "Review needed" } });

    const submitButton = screen.getByRole("button", { name: /Submit for Review/i });
    expect(submitButton).not.toBeDisabled();
  });

  it("has proper aria attributes for accessibility", async () => {
    render(<SubmitForReviewModal {...defaultProps} />);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "submit-review-dialog-title");

    const changeReasonInput = screen.getByLabelText(/Change Reason/i);
    expect(changeReasonInput).toHaveAttribute("aria-required", "true");
  });
});
