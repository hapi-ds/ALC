import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingContentViewer } from "../../../components/training/TrainingContentViewer";
import type { TrainingContent } from "../../../components/training/types";

/**
 * Unit tests for TrainingContentViewer component.
 *
 * Validates: Requirements 4.1–4.11, 7.2, 7.5
 */

// ---------------------------------------------------------------------------
// Test Fixtures
// ---------------------------------------------------------------------------

const approvedContent: TrainingContent = {
  content_id: "abc-123_v1.0",
  sop_document_uuid: "abc-123",
  sop_version: "1.0",
  summary: "This training covers chemical handling procedures.",
  quiz_questions: [
    {
      question_id: "q1",
      question: "What is the first step in chemical handling?",
      correct_answer: "Put on PPE",
      distractors: ["Open the container", "Read the label", "Call supervisor"],
      sop_section_ref: "Section 3.1",
    },
  ],
  procedural_steps: [
    {
      step_number: 1,
      description: "Put on personal protective equipment",
      is_safety_critical: true,
      safety_note: "Failure to wear PPE may result in chemical burns",
    },
    {
      step_number: 2,
      description: "Check the chemical label for hazard information",
      is_safety_critical: false,
      safety_note: "",
    },
  ],
  safety_points: [
    "Always wear gloves when handling chemicals",
    "Use fume hood for volatile substances",
  ],
  status: "approved",
  generated_at: "2024-01-15T10:00:00Z",
  reviewed_by: 1,
  reviewed_at: "2024-01-16T10:00:00Z",
  review_notes: "Looks good",
};

const rejectedContent: TrainingContent = {
  ...approvedContent,
  content_id: "abc-123_v1.0_rejected",
  status: "rejected",
};

const pendingReviewContent: TrainingContent = {
  ...approvedContent,
  content_id: "abc-123_v1.0_pending",
  status: "pending_review",
  reviewed_by: null,
  reviewed_at: null,
  review_notes: "",
};

const draftContent: TrainingContent = {
  ...approvedContent,
  content_id: "abc-123_v1.0_draft",
  status: "draft",
  reviewed_by: null,
  reviewed_at: null,
  review_notes: "",
};

const contentNoSections: TrainingContent = {
  ...approvedContent,
  summary: "",
  quiz_questions: [],
  procedural_steps: [],
  safety_points: [],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingContentViewer", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("renders loading skeleton when isLoading is true", () => {
      render(
        <TrainingContentViewer content={null} isLoading={true} error={null} />
      );

      const skeleton = screen.getByLabelText("Loading training content");
      expect(skeleton).toBeDefined();
      expect(skeleton.getAttribute("aria-busy")).toBe("true");
    });

    it("does not render content sections while loading", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={true}
          error={null}
        />
      );

      // Should show skeleton, not content
      expect(screen.getByLabelText("Loading training content")).toBeDefined();
      expect(screen.queryByText("Summary")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------------

  describe("error state", () => {
    it("renders error message with role='alert'", () => {
      render(
        <TrainingContentViewer
          content={null}
          isLoading={false}
          error="Server error: Something went wrong."
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(
        screen.getByText("Server error: Something went wrong.")
      ).toBeDefined();
    });

    it("renders retry button when onRetry is provided", () => {
      const onRetry = vi.fn();
      render(
        <TrainingContentViewer
          content={null}
          isLoading={false}
          error="Network error"
          onRetry={onRetry}
        />
      );

      const retryButton = screen.getByRole("button", {
        name: /retry loading content/i,
      });
      expect(retryButton).toBeDefined();
      fireEvent.click(retryButton);
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it("does not render retry button when onRetry is not provided", () => {
      render(
        <TrainingContentViewer
          content={null}
          isLoading={false}
          error="Network error"
        />
      );

      expect(
        screen.queryByRole("button", { name: /retry/i })
      ).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // No content (null)
  // -------------------------------------------------------------------------

  describe("no content (null)", () => {
    it("renders 'not available' message when content is null", () => {
      render(
        <TrainingContentViewer content={null} isLoading={false} error={null} />
      );

      expect(
        screen.getByText("Training content is not available for this task.")
      ).toBeDefined();
      expect(
        screen.getByText(
          "Content will be generated by the training coordinator."
        )
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Content status: rejected
  // -------------------------------------------------------------------------

  describe("rejected content", () => {
    it("renders revision notice for rejected content", () => {
      render(
        <TrainingContentViewer
          content={rejectedContent}
          isLoading={false}
          error={null}
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(
        screen.getByText(
          "This content is under revision and may not reflect the current SOP."
        )
      ).toBeDefined();
    });

    it("does not render content sections for rejected content", () => {
      render(
        <TrainingContentViewer
          content={rejectedContent}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.queryByText("Summary")).toBeNull();
      expect(screen.queryByText("Procedural Steps")).toBeNull();
      expect(screen.queryByText("Quiz Questions")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Content status: pending_review
  // -------------------------------------------------------------------------

  describe("pending_review content", () => {
    it("renders awaiting review notice", () => {
      render(
        <TrainingContentViewer
          content={pendingReviewContent}
          isLoading={false}
          error={null}
        />
      );

      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(
        screen.getByText(
          "This content is awaiting review and has not been approved."
        )
      ).toBeDefined();
    });

    it("does not render content sections in view mode", () => {
      render(
        <TrainingContentViewer
          content={pendingReviewContent}
          isLoading={false}
          error={null}
          mode="view"
        />
      );

      expect(screen.queryByText("Summary")).toBeNull();
      expect(screen.queryByText("Procedural Steps")).toBeNull();
    });

    it("renders content sections in review mode", () => {
      render(
        <TrainingContentViewer
          content={pendingReviewContent}
          isLoading={false}
          error={null}
          mode="review"
        />
      );

      expect(screen.getByText("Summary")).toBeDefined();
      expect(screen.getByText("Procedural Steps")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Content status: draft
  // -------------------------------------------------------------------------

  describe("draft content", () => {
    it("renders awaiting review notice for draft content", () => {
      render(
        <TrainingContentViewer
          content={draftContent}
          isLoading={false}
          error={null}
        />
      );

      expect(
        screen.getByText(
          "This content is awaiting review and has not been approved."
        )
      ).toBeDefined();
    });

    it("does not render content sections in view mode for draft", () => {
      render(
        <TrainingContentViewer
          content={draftContent}
          isLoading={false}
          error={null}
          mode="view"
        />
      );

      expect(screen.queryByText("Summary")).toBeNull();
    });

    it("renders content sections in review mode for draft", () => {
      render(
        <TrainingContentViewer
          content={draftContent}
          isLoading={false}
          error={null}
          mode="review"
        />
      );

      expect(screen.getByText("Summary")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Content status: approved — full rendering
  // -------------------------------------------------------------------------

  describe("approved content", () => {
    it("renders summary section", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText("Summary")).toBeDefined();
      expect(
        screen.getByText(
          "This training covers chemical handling procedures."
        )
      ).toBeDefined();
    });

    it("renders procedural steps section", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText("Procedural Steps")).toBeDefined();
      expect(
        screen.getByText(/Put on personal protective equipment/)
      ).toBeDefined();
      expect(
        screen.getByText(/Check the chemical label for hazard information/)
      ).toBeDefined();
    });

    it("renders safety points section", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText("Safety Points")).toBeDefined();
      expect(
        screen.getByText("Always wear gloves when handling chemicals")
      ).toBeDefined();
      expect(
        screen.getByText("Use fume hood for volatile substances")
      ).toBeDefined();
    });

    it("renders quiz questions section", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText("Quiz Questions")).toBeDefined();
      expect(
        screen.getByText("What is the first step in chemical handling?")
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Conditional section rendering (empty arrays omitted)
  // -------------------------------------------------------------------------

  describe("conditional section rendering", () => {
    it("omits all sections when content has empty arrays and no summary", () => {
      render(
        <TrainingContentViewer
          content={contentNoSections}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.queryByText("Summary")).toBeNull();
      expect(screen.queryByText("Procedural Steps")).toBeNull();
      expect(screen.queryByText("Safety Points")).toBeNull();
      expect(screen.queryByText("Quiz Questions")).toBeNull();
    });

    it("renders only summary when other sections are empty", () => {
      const contentOnlySummary: TrainingContent = {
        ...contentNoSections,
        summary: "Only a summary here.",
      };
      render(
        <TrainingContentViewer
          content={contentOnlySummary}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText("Summary")).toBeDefined();
      expect(screen.getByText("Only a summary here.")).toBeDefined();
      expect(screen.queryByText("Procedural Steps")).toBeNull();
      expect(screen.queryByText("Safety Points")).toBeNull();
      expect(screen.queryByText("Quiz Questions")).toBeNull();
    });

    it("renders only procedural steps when other sections are empty", () => {
      const contentOnlySteps: TrainingContent = {
        ...contentNoSections,
        procedural_steps: [
          {
            step_number: 1,
            description: "Do the thing",
            is_safety_critical: false,
            safety_note: "",
          },
        ],
      };
      render(
        <TrainingContentViewer
          content={contentOnlySteps}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.queryByText("Summary")).toBeNull();
      expect(screen.getByText("Procedural Steps")).toBeDefined();
      expect(screen.queryByText("Safety Points")).toBeNull();
      expect(screen.queryByText("Quiz Questions")).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Safety-critical step highlighting
  // -------------------------------------------------------------------------

  describe("safety-critical step highlighting", () => {
    it("highlights safety-critical steps with distinct styling", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      // The safety-critical step should have the safety note displayed
      expect(
        screen.getByText(
          /Safety Note: Failure to wear PPE may result in chemical burns/
        )
      ).toBeDefined();
    });

    it("does not show safety note for non-critical steps", () => {
      const contentNonCritical: TrainingContent = {
        ...approvedContent,
        procedural_steps: [
          {
            step_number: 1,
            description: "A normal step",
            is_safety_critical: false,
            safety_note: "",
          },
        ],
      };
      render(
        <TrainingContentViewer
          content={contentNonCritical}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.queryByText(/Safety Note:/)).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Quiz answer shuffling and reveal toggle
  // -------------------------------------------------------------------------

  describe("quiz answer shuffling and reveal toggle", () => {
    it("displays all answer options (correct + distractors)", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      // All options should be present regardless of order
      expect(screen.getByText("Put on PPE")).toBeDefined();
      expect(screen.getByText("Open the container")).toBeDefined();
      expect(screen.getByText("Read the label")).toBeDefined();
      expect(screen.getByText("Call supervisor")).toBeDefined();
    });

    it("shows 'Reveal Answer' button initially", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      const revealButton = screen.getByRole("button", {
        name: /reveal answer/i,
      });
      expect(revealButton).toBeDefined();
      expect(revealButton.getAttribute("aria-expanded")).toBe("false");
    });

    it("reveals correct answer and SOP reference when toggle is clicked", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      const revealButton = screen.getByRole("button", {
        name: /reveal answer/i,
      });
      fireEvent.click(revealButton);

      expect(screen.getByText(/Correct Answer: Put on PPE/)).toBeDefined();
      expect(screen.getByText(/SOP Reference: Section 3.1/)).toBeDefined();
    });

    it("hides answer when toggle is clicked again", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
        />
      );

      const revealButton = screen.getByRole("button", {
        name: /reveal answer/i,
      });
      fireEvent.click(revealButton);

      // Now it should say "Hide Answer"
      const hideButton = screen.getByRole("button", {
        name: /hide answer/i,
      });
      expect(hideButton).toBeDefined();
      expect(hideButton.getAttribute("aria-expanded")).toBe("true");

      fireEvent.click(hideButton);

      // Answer should be hidden again
      expect(screen.queryByText(/Correct Answer: Put on PPE/)).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Review mode: approve/reject buttons
  // -------------------------------------------------------------------------

  describe("review mode", () => {
    it("renders approve and reject buttons in review mode for approved content", () => {
      const onApprove = vi.fn();
      const onReject = vi.fn();
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
          mode="review"
          onApprove={onApprove}
          onReject={onReject}
        />
      );

      expect(
        screen.getByRole("button", { name: /approve/i })
      ).toBeDefined();
      expect(
        screen.getByRole("button", { name: /reject/i })
      ).toBeDefined();
    });

    it("calls onApprove when approve button is clicked", () => {
      const onApprove = vi.fn();
      const onReject = vi.fn();
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
          mode="review"
          onApprove={onApprove}
          onReject={onReject}
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /approve/i }));
      expect(onApprove).toHaveBeenCalledTimes(1);
    });

    it("calls onReject when reject button is clicked", () => {
      const onApprove = vi.fn();
      const onReject = vi.fn();
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
          mode="review"
          onApprove={onApprove}
          onReject={onReject}
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /reject/i }));
      expect(onReject).toHaveBeenCalledTimes(1);
    });

    it("renders approve/reject buttons for pending_review content in review mode", () => {
      const onApprove = vi.fn();
      const onReject = vi.fn();
      render(
        <TrainingContentViewer
          content={pendingReviewContent}
          isLoading={false}
          error={null}
          mode="review"
          onApprove={onApprove}
          onReject={onReject}
        />
      );

      expect(
        screen.getByRole("button", { name: /approve/i })
      ).toBeDefined();
      expect(
        screen.getByRole("button", { name: /reject/i })
      ).toBeDefined();
    });

    it("does not render approve/reject buttons in view mode", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
          mode="view"
        />
      );

      expect(
        screen.queryByRole("button", { name: /approve/i })
      ).toBeNull();
      expect(
        screen.queryByRole("button", { name: /reject/i })
      ).toBeNull();
    });

    it("does not render approve button when onApprove is not provided", () => {
      render(
        <TrainingContentViewer
          content={approvedContent}
          isLoading={false}
          error={null}
          mode="review"
          onReject={vi.fn()}
        />
      );

      expect(
        screen.queryByRole("button", { name: /approve/i })
      ).toBeNull();
      expect(
        screen.getByRole("button", { name: /reject/i })
      ).toBeDefined();
    });
  });
});
