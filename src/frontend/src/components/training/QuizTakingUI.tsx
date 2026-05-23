import { useState, useMemo } from "react";
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Trophy,
  RotateCcw,
} from "lucide-react";
import type { QuizQuestion, QuizAttemptResult } from "./types";
import { shuffleAnswerOptions } from "./utils";
import { useTrainingStore } from "../../stores/trainingStore";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type QuizState = "idle" | "taking" | "submitting" | "results" | "error";

interface QuizTakingUIProps {
  contentId: string;
  userId: number;
  quizQuestions: QuizQuestion[];
  contentStatus: "draft" | "pending_review" | "approved" | "rejected";
}

interface ErrorInfo {
  message: string;
  isRetryable: boolean;
}

// ---------------------------------------------------------------------------
// QuizTakingUI
// ---------------------------------------------------------------------------

/**
 * Interactive quiz-taking component rendered within the TrainingContentViewer.
 *
 * States:
 * - idle: Shows "Take Quiz" button or "Quiz Passed" badge
 * - taking: Sequential question form with radio buttons and progress
 * - submitting: Loading state on submit button
 * - results: Score display with per-question feedback
 * - error: Error message with conditional retry
 */
export function QuizTakingUI({
  contentId,
  userId,
  quizQuestions,
  contentStatus,
}: QuizTakingUIProps) {
  const [quizState, setQuizState] = useState<QuizState>("idle");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizAttemptResult | null>(null);
  const [errorInfo, setErrorInfo] = useState<ErrorInfo | null>(null);

  const { submitQuiz, quizPassCache } = useTrainingStore();

  // Check if user has already passed this quiz
  const passStatus = quizPassCache[contentId];
  const hasPassed = passStatus?.has_passed ?? false;
  const bestScore = passStatus?.best_score ?? null;

  // Randomize answer options once when quiz starts
  const shuffledOptions = useMemo(() => {
    if (quizState !== "taking" && quizState !== "submitting") return {};
    const optionsMap: Record<string, string[]> = {};
    for (const q of quizQuestions) {
      optionsMap[q.question_id] = shuffleAnswerOptions(q);
    }
    return optionsMap;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quizQuestions, quizState === "taking"]);

  const totalQuestions = quizQuestions.length;
  const answeredCount = Object.keys(answers).length;
  const allAnswered = answeredCount === totalQuestions;

  // Don't render if content is not approved or has no quiz questions
  if (contentStatus !== "approved" || quizQuestions.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="quiz-taking-heading" className="space-y-4">
      <h3 id="quiz-taking-heading" className="text-sm font-semibold">
        Comprehension Quiz
      </h3>

      {quizState === "idle" && (
        <IdleState
          hasPassed={hasPassed}
          bestScore={bestScore}
          totalQuestions={totalQuestions}
          onStartQuiz={() => {
            setAnswers({});
            setResult(null);
            setErrorInfo(null);
            setQuizState("taking");
          }}
        />
      )}

      {(quizState === "taking" || quizState === "submitting") && (
        <TakingState
          quizQuestions={quizQuestions}
          shuffledOptions={shuffledOptions}
          answers={answers}
          answeredCount={answeredCount}
          totalQuestions={totalQuestions}
          allAnswered={allAnswered}
          isSubmitting={quizState === "submitting"}
          onAnswerChange={(questionId, answer) => {
            setAnswers((prev) => ({ ...prev, [questionId]: answer }));
          }}
          onSubmit={async () => {
            setQuizState("submitting");
            try {
              const response = await submitQuiz(contentId, userId, answers);
              if (response) {
                setResult(response);
                setQuizState("results");
              } else {
                // submitQuiz returned null — check store error
                const storeError = useTrainingStore.getState().quizSubmitError;
                handleSubmitError(storeError, setErrorInfo, setQuizState);
              }
            } catch (err) {
              handleSubmitError(err, setErrorInfo, setQuizState);
            }
          }}
        />
      )}

      {quizState === "results" && result && (
        <ResultsState
          result={result}
          quizQuestions={quizQuestions}
          answers={answers}
          onRetake={() => {
            setAnswers({});
            setResult(null);
            setQuizState("taking");
          }}
        />
      )}

      {quizState === "error" && errorInfo && (
        <ErrorState
          errorInfo={errorInfo}
          onRetry={async () => {
            setQuizState("submitting");
            setErrorInfo(null);
            try {
              const response = await submitQuiz(contentId, userId, answers);
              if (response) {
                setResult(response);
                setQuizState("results");
              } else {
                const storeError = useTrainingStore.getState().quizSubmitError;
                handleSubmitError(storeError, setErrorInfo, setQuizState);
              }
            } catch (err) {
              handleSubmitError(err, setErrorInfo, setQuizState);
            }
          }}
        />
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Error handling helper
// ---------------------------------------------------------------------------

function handleSubmitError(
  error: unknown,
  setErrorInfo: (info: ErrorInfo) => void,
  setQuizState: (state: QuizState) => void
) {
  let message = "An unexpected error occurred. Please try again.";
  let isRetryable = true;

  if (error && typeof error === "object") {
    const err = error as Record<string, unknown>;

    // Check for HTTP status codes indicating non-retryable errors
    if (err.status === 400 || err.status === 404) {
      isRetryable = false;
      if (typeof err.body === "string") {
        try {
          const parsed = JSON.parse(err.body);
          if (typeof parsed.detail === "string") {
            message = parsed.detail;
          }
        } catch {
          message = err.body;
        }
      }
    } else if (typeof err.message === "string") {
      message = err.message;
    }
  } else if (typeof error === "string") {
    message = error;
    // String errors from the store are typically parsed error messages
    // Check if they indicate non-retryable conditions
    if (
      error.includes("not found") ||
      error.includes("not in approved status") ||
      error.includes("not available")
    ) {
      isRetryable = false;
    }
  }

  setErrorInfo({ message, isRetryable });
  setQuizState("error");
}

// ---------------------------------------------------------------------------
// Idle State
// ---------------------------------------------------------------------------

function IdleState({
  hasPassed,
  bestScore,
  totalQuestions,
  onStartQuiz,
}: {
  hasPassed: boolean;
  bestScore: number | null;
  totalQuestions: number;
  onStartQuiz: () => void;
}) {
  if (hasPassed) {
    return (
      <div className="inline-flex items-center gap-2 rounded-full bg-green-100 px-4 py-2 text-sm font-medium text-green-700">
        <Trophy className="h-4 w-4" aria-hidden="true" />
        <span>
          Quiz Passed
          {bestScore !== null && ` (${bestScore}/${totalQuestions})`}
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onStartQuiz}
      className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      aria-label="Start comprehension quiz"
    >
      Take Quiz
    </button>
  );
}

// ---------------------------------------------------------------------------
// Taking State
// ---------------------------------------------------------------------------

function TakingState({
  quizQuestions,
  shuffledOptions,
  answers,
  answeredCount,
  totalQuestions,
  allAnswered,
  isSubmitting,
  onAnswerChange,
  onSubmit,
}: {
  quizQuestions: QuizQuestion[];
  shuffledOptions: Record<string, string[]>;
  answers: Record<string, string>;
  answeredCount: number;
  totalQuestions: number;
  allAnswered: boolean;
  isSubmitting: boolean;
  onAnswerChange: (questionId: string, answer: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="space-y-4">
      {/* Progress indicator */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {answeredCount} of {totalQuestions} answered
        </p>
        <div className="h-2 w-32 rounded-full bg-gray-200 overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-300"
            style={{
              width: `${totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0}%`,
            }}
            role="progressbar"
            aria-valuenow={answeredCount}
            aria-valuemin={0}
            aria-valuemax={totalQuestions}
            aria-label="Quiz progress"
          />
        </div>
      </div>

      {/* Questions */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="space-y-4"
      >
        {quizQuestions.map((question, index) => (
          <fieldset
            key={question.question_id}
            className="rounded-lg border p-4 space-y-3"
          >
            <legend className="px-2 text-sm font-medium">
              {index + 1}. {question.question}
            </legend>

            <div
              className="space-y-2"
              role="radiogroup"
              aria-label={question.question}
            >
              {(shuffledOptions[question.question_id] ?? []).map(
                (option, optIdx) => (
                  <label
                    key={optIdx}
                    className={`flex items-center gap-2 text-sm cursor-pointer rounded-md p-2 transition-colors ${
                      answers[question.question_id] === option
                        ? "bg-primary/10 border border-primary/30"
                        : "hover:bg-muted/50"
                    }`}
                  >
                    <input
                      type="radio"
                      name={`quiz-answer-${question.question_id}`}
                      value={option}
                      checked={answers[question.question_id] === option}
                      onChange={() =>
                        onAnswerChange(question.question_id, option)
                      }
                      disabled={isSubmitting}
                      className="h-4 w-4 text-primary border-gray-300 focus:ring-primary"
                      aria-label={`Option: ${option}`}
                    />
                    <span>{option}</span>
                  </label>
                )
              )}
            </div>
          </fieldset>
        ))}

        {/* Submit button */}
        <button
          type="submit"
          disabled={!allAnswered || isSubmitting}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Submit quiz answers"
        >
          {isSubmitting && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          {isSubmitting ? "Submitting..." : "Submit Quiz"}
        </button>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Results State
// ---------------------------------------------------------------------------

function ResultsState({
  result,
  quizQuestions,
  answers,
  onRetake,
}: {
  result: QuizAttemptResult;
  quizQuestions: QuizQuestion[];
  answers: Record<string, string>;
  onRetake: () => void;
}) {
  const passed = result.passed;

  return (
    <div className="space-y-4">
      {/* Score display */}
      <div
        className={`rounded-lg border p-4 ${
          passed
            ? "border-green-200 bg-green-50"
            : "border-red-200 bg-red-50"
        }`}
        role="alert"
      >
        <div className="flex items-center gap-3">
          {passed ? (
            <CheckCircle className="h-6 w-6 text-green-600" aria-hidden="true" />
          ) : (
            <XCircle className="h-6 w-6 text-red-600" aria-hidden="true" />
          )}
          <div>
            <p
              className={`text-lg font-semibold ${
                passed ? "text-green-800" : "text-red-800"
              }`}
            >
              {result.score}/{result.total_questions}
            </p>
            <p
              className={`text-sm ${
                passed ? "text-green-700" : "text-red-700"
              }`}
            >
              {passed
                ? "Quiz passed! You may now mark this training task as complete."
                : "Quiz not passed. You need at least 80% correct answers. Please review the training material and try again."}
            </p>
          </div>
        </div>
      </div>

      {/* Per-question feedback */}
      <div className="space-y-3">
        <h4 className="text-sm font-medium">Question Review</h4>
        {quizQuestions.map((question, index) => {
          const userAnswer = answers[question.question_id] ?? "";
          const correctAnswer = result.correct_answers[question.question_id];
          const isCorrect = userAnswer === correctAnswer;

          return (
            <div
              key={question.question_id}
              className={`rounded-md border p-3 text-sm ${
                isCorrect
                  ? "border-green-200 bg-green-50/50"
                  : "border-red-200 bg-red-50/50"
              }`}
            >
              <div className="flex items-start gap-2">
                {isCorrect ? (
                  <CheckCircle
                    className="h-4 w-4 text-green-600 shrink-0 mt-0.5"
                    aria-hidden="true"
                  />
                ) : (
                  <XCircle
                    className="h-4 w-4 text-red-600 shrink-0 mt-0.5"
                    aria-hidden="true"
                  />
                )}
                <div className="flex-1">
                  <p className="font-medium">
                    {index + 1}. {question.question}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Your answer: {userAnswer || "(not answered)"}
                  </p>
                  {!isCorrect && correctAnswer && (
                    <p className="mt-0.5 text-green-700 font-medium">
                      Correct answer: {correctAnswer}
                    </p>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Action buttons */}
      {!passed && (
        <button
          type="button"
          onClick={onRetake}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          aria-label="Retake the quiz"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Retake Quiz
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Error State
// ---------------------------------------------------------------------------

function ErrorState({
  errorInfo,
  onRetry,
}: {
  errorInfo: ErrorInfo;
  onRetry: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 p-4 space-y-3"
    >
      <div className="flex items-start gap-2">
        <AlertCircle
          className="h-5 w-5 text-red-600 shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <p className="text-sm text-red-700">{errorInfo.message}</p>
      </div>
      {errorInfo.isRetryable && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
          aria-label="Retry quiz submission"
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
