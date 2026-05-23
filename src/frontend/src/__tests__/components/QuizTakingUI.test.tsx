import { describe, it, expect, afterEach, vi, beforeEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QuizTakingUI } from "../../components/training/QuizTakingUI";
import type { QuizQuestion, QuizAttemptResult } from "../../components/training/types";

/**
 * Unit tests for QuizTakingUI component.
 *
 * Validates: Requirements 7.1, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock the training store
const mockSubmitQuiz = vi.fn();
const mockQuizPassCache: Record<string, { has_passed: boolean; best_score: number | null }> = {};

vi.mock("../../stores/trainingStore", () => ({
  useTrainingStore: Object.assign(
    () => ({
      submitQuiz: mockSubmitQuiz,
      quizPassCache: mockQuizPassCache,
      quizSubmitError: null,
    }),
    {
      getState: () => ({
        quizSubmitError: null,
      }),
    }
  ),
}));

// Mock shuffleAnswerOptions to return a predictable order (correct_answer + distractors)
vi.mock("../../components/training/utils", () => ({
  shuffleAnswerOptions: (q: QuizQuestion) => [q.correct_answer, ...q.distractors],
}));

// ---------------------------------------------------------------------------
// Test Fixtures
// ---------------------------------------------------------------------------

const quizQuestions: QuizQuestion[] = [
  {
    question_id: "q1",
    question: "What is the first step?",
    correct_answer: "Put on PPE",
    distractors: ["Open container", "Read label"],
    sop_section_ref: "Section 1",
  },
  {
    question_id: "q2",
    question: "What should you check?",
    correct_answer: "Chemical label",
    distractors: ["Weather", "Email"],
    sop_section_ref: "Section 2",
  },
];

const passResult: QuizAttemptResult = {
  attempt_id: 1,
  score: 2,
  total_questions: 2,
  passed: true,
  passing_score_threshold: 0.8,
  correct_answers: { q1: "Put on PPE", q2: "Chemical label" },
  attempted_at: "2024-01-15T10:00:00Z",
};

const failResult: QuizAttemptResult = {
  attempt_id: 2,
  score: 0,
  total_questions: 2,
  passed: false,
  passing_score_threshold: 0.8,
  correct_answers: { q1: "Put on PPE", q2: "Chemical label" },
  attempted_at: "2024-01-15T11:00:00Z",
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("QuizTakingUI", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset quizPassCache
    Object.keys(mockQuizPassCache).forEach((key) => delete mockQuizPassCache[key]);
  });

  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Idle state: "Take Quiz" button
  // -------------------------------------------------------------------------

  describe("idle state", () => {
    it("renders 'Take Quiz' button for approved content with quiz questions", () => {
      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      const button = screen.getByRole("button", { name: /start comprehension quiz/i });
      expect(button).toBeDefined();
      expect(button.textContent).toContain("Take Quiz");
    });

    it("does not render when content status is not approved", () => {
      const { container } = render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="draft"
        />
      );

      expect(container.innerHTML).toBe("");
    });

    it("does not render when quiz questions are empty", () => {
      const { container } = render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={[]}
          contentStatus="approved"
        />
      );

      expect(container.innerHTML).toBe("");
    });
  });

  // -------------------------------------------------------------------------
  // Already passed: "Quiz Passed" badge
  // -------------------------------------------------------------------------

  describe("quiz passed badge", () => {
    it("shows 'Quiz Passed' badge when user has already passed", () => {
      mockQuizPassCache["abc-123_v1.0"] = { has_passed: true, best_score: 5 };

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      expect(screen.getByText(/Quiz Passed/)).toBeDefined();
      expect(screen.getByText(/5\/2/)).toBeDefined();
      expect(screen.queryByRole("button", { name: /start comprehension quiz/i })).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Taking state: submit disabled until all answered
  // -------------------------------------------------------------------------

  describe("taking state", () => {
    it("disables submit button until all questions are answered", () => {
      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      // Start the quiz
      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));

      // Submit button should be disabled
      const submitButton = screen.getByRole("button", { name: /submit quiz answers/i });
      expect(submitButton.hasAttribute("disabled")).toBe(true);

      // Answer first question
      const q1Options = screen.getByText("Put on PPE");
      fireEvent.click(q1Options);

      // Still disabled (only 1 of 2 answered)
      expect(submitButton.hasAttribute("disabled")).toBe(true);

      // Answer second question
      const q2Options = screen.getByText("Chemical label");
      fireEvent.click(q2Options);

      // Now enabled
      expect(submitButton.hasAttribute("disabled")).toBe(false);
    });

    it("shows progress indicator with answered count", () => {
      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));

      expect(screen.getByText("0 of 2 answered")).toBeDefined();

      // Answer one question
      fireEvent.click(screen.getByText("Put on PPE"));

      expect(screen.getByText("1 of 2 answered")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Submitting state: loading indicator
  // -------------------------------------------------------------------------

  describe("submitting state", () => {
    it("shows loading state during submission", async () => {
      // Make submitQuiz hang (never resolve) to observe loading state
      mockSubmitQuiz.mockImplementation(
        () => new Promise(() => {}) // never resolves
      );

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      // Start quiz and answer all questions
      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));
      fireEvent.click(screen.getByText("Put on PPE"));
      fireEvent.click(screen.getByText("Chemical label"));

      // Submit
      fireEvent.click(screen.getByRole("button", { name: /submit quiz answers/i }));

      // Should show "Submitting..." text and button should be disabled
      await waitFor(() => {
        expect(screen.getByText("Submitting...")).toBeDefined();
      });

      const submitButton = screen.getByRole("button", { name: /submit quiz answers/i });
      expect(submitButton.hasAttribute("disabled")).toBe(true);
    });
  });

  // -------------------------------------------------------------------------
  // Results state: success/failure
  // -------------------------------------------------------------------------

  describe("results state", () => {
    it("displays results panel on successful submission", async () => {
      mockSubmitQuiz.mockResolvedValue(passResult);

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      // Start quiz, answer all, submit
      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));
      fireEvent.click(screen.getByText("Put on PPE"));
      fireEvent.click(screen.getByText("Chemical label"));
      fireEvent.click(screen.getByRole("button", { name: /submit quiz answers/i }));

      // Wait for results
      await waitFor(() => {
        expect(screen.getByText("2/2")).toBeDefined();
      });

      // Should show the score and pass message
      expect(
        screen.getByText("Quiz passed! You may now mark this training task as complete.")
      ).toBeDefined();
    });

    it("shows success message on pass", async () => {
      mockSubmitQuiz.mockResolvedValue(passResult);

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));
      fireEvent.click(screen.getByText("Put on PPE"));
      fireEvent.click(screen.getByText("Chemical label"));
      fireEvent.click(screen.getByRole("button", { name: /submit quiz answers/i }));

      await waitFor(() => {
        expect(
          screen.getByText("Quiz passed! You may now mark this training task as complete.")
        ).toBeDefined();
      });

      // Should NOT show "Retake Quiz" button on pass
      expect(screen.queryByRole("button", { name: /retake the quiz/i })).toBeNull();
    });

    it("shows failure message on fail with retake button", async () => {
      mockSubmitQuiz.mockResolvedValue(failResult);

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));
      fireEvent.click(screen.getByText("Put on PPE"));
      fireEvent.click(screen.getByText("Chemical label"));
      fireEvent.click(screen.getByRole("button", { name: /submit quiz answers/i }));

      await waitFor(() => {
        expect(
          screen.getByText(
            "Quiz not passed. You need at least 80% correct answers. Please review the training material and try again."
          )
        ).toBeDefined();
      });

      // Should show "Retake Quiz" button
      expect(screen.getByRole("button", { name: /retake the quiz/i })).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Error handling: network error with retry
  // -------------------------------------------------------------------------

  describe("error handling", () => {
    it("handles network error with retry button", async () => {
      mockSubmitQuiz.mockResolvedValue(null);

      // Mock getState to return a network error message
      const { useTrainingStore } = await import("../../stores/trainingStore");
      vi.mocked(useTrainingStore).getState = vi.fn().mockReturnValue({
        quizSubmitError: "Network error: Failed to fetch",
      });

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));
      fireEvent.click(screen.getByText("Put on PPE"));
      fireEvent.click(screen.getByText("Chemical label"));
      fireEvent.click(screen.getByRole("button", { name: /submit quiz answers/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
      });

      // Should show retry button for network errors
      expect(screen.getByRole("button", { name: /retry quiz submission/i })).toBeDefined();
    });

    it("handles 400/404 errors without retry button", async () => {
      mockSubmitQuiz.mockResolvedValue(null);

      // Mock getState to return a non-retryable error
      const { useTrainingStore } = await import("../../stores/trainingStore");
      vi.mocked(useTrainingStore).getState = vi.fn().mockReturnValue({
        quizSubmitError: "Quiz is not available: training content is not in approved status",
      });

      render(
        <QuizTakingUI
          contentId="abc-123_v1.0"
          userId={42}
          quizQuestions={quizQuestions}
          contentStatus="approved"
        />
      );

      fireEvent.click(screen.getByRole("button", { name: /start comprehension quiz/i }));
      fireEvent.click(screen.getByText("Put on PPE"));
      fireEvent.click(screen.getByText("Chemical label"));
      fireEvent.click(screen.getByRole("button", { name: /submit quiz answers/i }));

      await waitFor(() => {
        expect(screen.getByRole("alert")).toBeDefined();
      });

      // Should show the error message
      expect(
        screen.getByText("Quiz is not available: training content is not in approved status")
      ).toBeDefined();

      // Should NOT show retry button for 400/404 errors
      expect(screen.queryByRole("button", { name: /retry quiz submission/i })).toBeNull();
    });
  });
});
