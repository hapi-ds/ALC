import { useState, useMemo } from "react";
import {
  AlertTriangle,
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
} from "lucide-react";
import type { TrainingContent, QuizQuestion } from "./types";
import { shouldRenderSection, shuffleAnswerOptions } from "./utils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrainingContentViewerProps {
  content: TrainingContent | null;
  isLoading: boolean;
  error: string | null;
  mode?: "view" | "review";
  onRetry?: () => void;
  onApprove?: () => void;
  onReject?: () => void;
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function ContentSkeleton() {
  return (
    <div className="animate-pulse space-y-6" aria-busy="true" aria-label="Loading training content">
      {/* Summary skeleton */}
      <div className="space-y-2">
        <div className="h-5 w-32 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="h-4 w-3/4 rounded bg-muted" />
      </div>
      {/* Steps skeleton */}
      <div className="space-y-2">
        <div className="h-5 w-40 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="h-4 w-5/6 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
      </div>
      {/* Safety skeleton */}
      <div className="space-y-2">
        <div className="h-5 w-36 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="h-4 w-2/3 rounded bg-muted" />
      </div>
      {/* Quiz skeleton */}
      <div className="space-y-2">
        <div className="h-5 w-36 rounded bg-muted" />
        <div className="h-4 w-full rounded bg-muted" />
        <div className="h-4 w-1/2 rounded bg-muted" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quiz Question Component
// ---------------------------------------------------------------------------

function QuizQuestionItem({ question }: { question: QuizQuestion }) {
  const [revealed, setRevealed] = useState(false);

  // Shuffle options once per mount
  const options = useMemo(() => shuffleAnswerOptions(question), [question]);

  return (
    <fieldset className="rounded-lg border p-4 space-y-3">
      <legend className="px-2 text-sm font-medium">{question.question}</legend>

      <div className="space-y-2" role="radiogroup" aria-label={question.question}>
        {options.map((option, idx) => (
          <label key={idx} className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="radio"
              name={`quiz-${question.question_id}`}
              value={option}
              className="h-4 w-4 text-primary border-gray-300 focus:ring-primary"
            />
            <span>{option}</span>
          </label>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setRevealed(!revealed)}
        aria-expanded={revealed}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
      >
        {revealed ? (
          <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        {revealed ? "Hide Answer" : "Reveal Answer"}
      </button>

      {revealed && (
        <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm space-y-1">
          <p className="font-medium text-green-800">
            Correct Answer: {question.correct_answer}
          </p>
          <p className="text-green-700 text-xs">
            SOP Reference: {question.sop_section_ref}
          </p>
        </div>
      )}
    </fieldset>
  );
}

// ---------------------------------------------------------------------------
// TrainingContentViewer
// ---------------------------------------------------------------------------

/**
 * Presentational component that renders training content.
 * It does NOT make API calls — content is fetched by the parent and passed as props.
 */
export function TrainingContentViewer({
  content,
  isLoading,
  error,
  mode = "view",
  onRetry,
  onApprove,
  onReject,
}: TrainingContentViewerProps) {
  // Loading state
  if (isLoading) {
    return <ContentSkeleton />;
  }

  // Error state (network/server errors)
  if (error) {
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-6 text-center space-y-3">
        <p className="text-sm text-red-700">{error}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 transition-colors"
            aria-label="Retry loading content"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  // No content (404 / not yet generated)
  if (!content) {
    return (
      <div className="rounded-lg border p-6 text-center space-y-2">
        <p className="text-sm text-muted-foreground">
          Training content is not available for this task.
        </p>
        <p className="text-xs text-muted-foreground">
          Content will be generated by the training coordinator.
        </p>
      </div>
    );
  }

  // Content status: rejected
  if (content.status === "rejected") {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-start gap-3" role="alert">
          <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-amber-800">
            This content is under revision and may not reflect the current SOP.
          </p>
        </div>
      </div>
    );
  }

  // Content status: pending_review or draft
  if (content.status === "pending_review" || content.status === "draft") {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-blue-300 bg-blue-50 p-4 flex items-start gap-3" role="alert">
          <AlertTriangle className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-blue-800">
            This content is awaiting review and has not been approved.
          </p>
        </div>
        {/* In review mode, still show content for reviewer */}
        {mode === "review" && <ContentSections content={content} />}
        {mode === "review" && (
          <ReviewActions onApprove={onApprove} onReject={onReject} />
        )}
      </div>
    );
  }

  // Content status: approved — render full content
  return (
    <div className="space-y-6">
      <ContentSections content={content} />
      {mode === "review" && (
        <ReviewActions onApprove={onApprove} onReject={onReject} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Content Sections
// ---------------------------------------------------------------------------

function ContentSections({ content }: { content: TrainingContent }) {
  return (
    <>
      {/* Summary */}
      {content.summary && (
        <section aria-labelledby="content-summary-heading">
          <h3 id="content-summary-heading" className="text-sm font-semibold mb-2">
            Summary
          </h3>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {content.summary}
          </p>
        </section>
      )}

      {/* Procedural Steps */}
      {shouldRenderSection(content.procedural_steps) && (
        <section aria-labelledby="content-steps-heading">
          <h3 id="content-steps-heading" className="text-sm font-semibold mb-3">
            Procedural Steps
          </h3>
          <ol className="space-y-3">
            {content.procedural_steps.map((step) => (
              <li
                key={step.step_number}
                className={`rounded-md p-3 text-sm ${
                  step.is_safety_critical
                    ? "border-l-4 border-red-500 bg-red-50"
                    : "border border-gray-200"
                }`}
              >
                <div className="flex items-start gap-2">
                  {step.is_safety_critical && (
                    <AlertTriangle
                      className="h-4 w-4 text-amber-600 shrink-0 mt-0.5"
                      aria-hidden="true"
                    />
                  )}
                  <div className="flex-1">
                    <span className="font-medium">Step {step.step_number}:</span>{" "}
                    {step.description}
                    {step.is_safety_critical && step.safety_note && (
                      <p className="mt-1 text-xs text-red-700 font-medium">
                        ⚠ Safety Note: {step.safety_note}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Safety Points */}
      {shouldRenderSection(content.safety_points) && (
        <section aria-labelledby="content-safety-heading">
          <h3 id="content-safety-heading" className="text-sm font-semibold mb-3">
            Safety Points
          </h3>
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
            <div className="flex items-start gap-2 mb-2">
              <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" aria-hidden="true" />
              <span className="text-sm font-medium text-amber-800">Important Safety Information</span>
            </div>
            <ul className="list-disc list-inside space-y-1 ml-7">
              {content.safety_points.map((point, idx) => (
                <li key={idx} className="text-sm text-amber-900">
                  {point}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* Quiz Questions */}
      {shouldRenderSection(content.quiz_questions) && (
        <section aria-labelledby="content-quiz-heading">
          <h3 id="content-quiz-heading" className="text-sm font-semibold mb-3">
            Quiz Questions
          </h3>
          <div className="space-y-4">
            {content.quiz_questions.map((question) => (
              <QuizQuestionItem key={question.question_id} question={question} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Review Actions (Admin mode)
// ---------------------------------------------------------------------------

function ReviewActions({
  onApprove,
  onReject,
}: {
  onApprove?: () => void;
  onReject?: () => void;
}) {
  return (
    <div className="flex items-center gap-3 pt-4 border-t">
      {onApprove && (
        <button
          type="button"
          onClick={onApprove}
          className="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 transition-colors"
        >
          <CheckCircle className="h-4 w-4" aria-hidden="true" />
          Approve
        </button>
      )}
      {onReject && (
        <button
          type="button"
          onClick={onReject}
          className="inline-flex items-center gap-1.5 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors"
        >
          <XCircle className="h-4 w-4" aria-hidden="true" />
          Reject
        </button>
      )}
    </div>
  );
}
