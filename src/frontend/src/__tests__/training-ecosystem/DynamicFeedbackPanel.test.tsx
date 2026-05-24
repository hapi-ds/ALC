import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { DynamicFeedbackPanel } from "../../components/training/DynamicFeedbackPanel";
import type { DynamicFeedback } from "../../types/training-ecosystem";

/**
 * Unit tests for DynamicFeedbackPanel component.
 *
 * Validates: Requirements 10.6
 */

// Mock the API module
vi.mock("../../lib/training-ecosystem-api", () => ({
  getFeedback: vi.fn(),
}));

import { getFeedback } from "../../lib/training-ecosystem-api";

const mockedGetFeedback = getFeedback as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const sampleFeedback: DynamicFeedback = {
  correct_answer: "Always wear nitrile gloves and safety goggles when handling chemicals.",
  paragraph_text:
    "Personnel must wear appropriate PPE including nitrile gloves and safety goggles at all times when handling hazardous chemicals in the laboratory environment.",
  section_reference: "Section 4.2 - Personal Protective Equipment",
  page_number: 12,
  explanation:
    "The source paragraph explicitly states that nitrile gloves and safety goggles are required PPE for chemical handling, directly answering the question about required protective equipment.",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("DynamicFeedbackPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Empty state (no feedback)
  // -------------------------------------------------------------------------

  describe("empty state", () => {
    it("renders placeholder message when no feedback and no questionId", () => {
      render(<DynamicFeedbackPanel />);

      expect(
        screen.getByText(/feedback will appear here when you answer a question incorrectly/i)
      ).toBeDefined();
    });

    it("has section with aria-label 'Dynamic feedback'", () => {
      render(<DynamicFeedbackPanel />);

      expect(screen.getByLabelText("Dynamic feedback")).toBeDefined();
    });

    it("shows 'Load Feedback' button when questionId is provided", () => {
      render(<DynamicFeedbackPanel questionId={42} />);

      expect(screen.getByRole("button", { name: /load feedback/i })).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Pre-loaded feedback
  // -------------------------------------------------------------------------

  describe("pre-loaded feedback", () => {
    it("renders correct answer highlighted in green section", () => {
      render(<DynamicFeedbackPanel feedback={sampleFeedback} />);

      expect(screen.getByText("Correct Answer")).toBeDefined();
      expect(
        screen.getByText(sampleFeedback.correct_answer)
      ).toBeDefined();
    });

    it("renders source paragraph text", () => {
      render(<DynamicFeedbackPanel feedback={sampleFeedback} />);

      expect(screen.getByText("Source Paragraph")).toBeDefined();
      expect(screen.getByText(sampleFeedback.paragraph_text)).toBeDefined();
    });

    it("renders section reference as a link", () => {
      render(<DynamicFeedbackPanel feedback={sampleFeedback} />);

      const link = screen.getByRole("link", {
        name: /view section.*in document viewer/i,
      });
      expect(link).toBeDefined();
      expect(link.getAttribute("href")).toContain(
        encodeURIComponent(sampleFeedback.section_reference)
      );
    });

    it("displays section reference text", () => {
      render(<DynamicFeedbackPanel feedback={sampleFeedback} />);

      expect(
        screen.getByText(`Section: ${sampleFeedback.section_reference}`)
      ).toBeDefined();
    });

    it("displays page number when available", () => {
      render(<DynamicFeedbackPanel feedback={sampleFeedback} />);

      expect(screen.getByText("(Page 12)")).toBeDefined();
    });

    it("does not display page number when null", () => {
      const feedbackNoPage = { ...sampleFeedback, page_number: null };
      render(<DynamicFeedbackPanel feedback={feedbackNoPage} />);

      expect(screen.queryByText(/Page/)).toBeNull();
    });

    it("renders explanation text", () => {
      render(<DynamicFeedbackPanel feedback={sampleFeedback} />);

      expect(screen.getByText("Explanation")).toBeDefined();
      expect(screen.getByText(sampleFeedback.explanation)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Fetching feedback
  // -------------------------------------------------------------------------

  describe("fetching feedback", () => {
    it("fetches feedback when Load Feedback button is clicked", async () => {
      mockedGetFeedback.mockResolvedValue(sampleFeedback);

      render(<DynamicFeedbackPanel questionId={42} />);

      const button = screen.getByRole("button", { name: /load feedback/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(mockedGetFeedback).toHaveBeenCalledWith(42);
      });

      await waitFor(() => {
        expect(screen.getByText(sampleFeedback.correct_answer)).toBeDefined();
      });
    });

    it("shows error message on 403 (no failed attempts)", async () => {
      mockedGetFeedback.mockRejectedValue(new Error("403 Forbidden"));

      render(<DynamicFeedbackPanel questionId={42} />);

      const button = screen.getByRole("button", { name: /load feedback/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(
          screen.getByText(/feedback is only available after a failed attempt/i)
        ).toBeDefined();
      });
    });

    it("shows generic error message on other failures", async () => {
      mockedGetFeedback.mockRejectedValue(new Error("Network error"));

      render(<DynamicFeedbackPanel questionId={42} />);

      const button = screen.getByRole("button", { name: /load feedback/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(screen.getByText("Network error")).toBeDefined();
      });
    });

    it("shows retry button on error", async () => {
      mockedGetFeedback.mockRejectedValue(new Error("Server error"));

      render(<DynamicFeedbackPanel questionId={42} />);

      const button = screen.getByRole("button", { name: /load feedback/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
      });
    });
  });
});
