/**
 * DynamicFeedbackPanel
 *
 * Displays paragraph-level feedback for incorrectly answered questions:
 * - Correct answer highlighted in green
 * - Source paragraph with relevant sentence highlighted
 * - Section reference as clickable link navigating to document viewer
 * - LLM-generated explanation text
 *
 * Requirements: 10.6
 */

import { useState, useCallback } from "react";
import { CheckCircle, BookOpen, ExternalLink, Lightbulb, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getFeedback } from "@/lib/training-ecosystem-api";
import type { DynamicFeedback } from "@/types/training-ecosystem";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface DynamicFeedbackPanelProps {
  /** If provided, auto-fetches feedback for this question. */
  questionId?: number;
  /** Pre-loaded feedback data (alternative to questionId). */
  feedback?: DynamicFeedback | null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DynamicFeedbackPanel({
  questionId,
  feedback: externalFeedback,
}: DynamicFeedbackPanelProps = {}) {
  const [feedback, setFeedback] = useState<DynamicFeedback | null>(
    externalFeedback ?? null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inputQuestionId] = useState("");

  const fetchFeedbackForQuestion = useCallback(async (qId: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await getFeedback(qId);
      setFeedback(result);
    } catch (err) {
      if (err instanceof Error) {
        if (err.message.includes("403")) {
          setError("Feedback is only available after a failed attempt on this question.");
        } else {
          setError(err.message);
        }
      } else {
        setError("Failed to load feedback.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Auto-fetch if questionId prop is provided
  const handleFetchClick = useCallback(() => {
    const qId = questionId ?? parseInt(inputQuestionId, 10);
    if (!isNaN(qId) && qId > 0) {
      fetchFeedbackForQuestion(qId);
    }
  }, [questionId, inputQuestionId, fetchFeedbackForQuestion]);

  // No feedback loaded — show prompt
  if (!feedback && !isLoading && !error) {
    return (
      <section aria-label="Dynamic feedback" className="space-y-4">
        <h3 className="text-lg font-semibold">Assessment Feedback</h3>

        {!questionId && (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <Lightbulb className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
            <p className="mt-2 text-sm text-muted-foreground">
              Feedback will appear here when you answer a question incorrectly.
              It provides the correct answer, source paragraph, and an explanation.
            </p>
          </div>
        )}

        {questionId && (
          <Button variant="outline" size="sm" onClick={handleFetchClick}>
            <Search className="h-4 w-4 mr-1" aria-hidden="true" />
            Load Feedback
          </Button>
        )}
      </section>
    );
  }

  // Loading state
  if (isLoading) {
    return (
      <section aria-label="Dynamic feedback" className="space-y-4">
        <h3 className="text-lg font-semibold">Assessment Feedback</h3>
        <div className="rounded-lg border p-6 space-y-3">
          <div className="h-4 w-1/3 rounded bg-muted animate-pulse" />
          <div className="h-4 w-full rounded bg-muted animate-pulse" />
          <div className="h-4 w-2/3 rounded bg-muted animate-pulse" />
        </div>
      </section>
    );
  }

  // Error state
  if (error) {
    return (
      <section aria-label="Dynamic feedback" className="space-y-4">
        <h3 className="text-lg font-semibold">Assessment Feedback</h3>
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-4">
          <p className="text-sm text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={handleFetchClick} className="mt-2">
            Retry
          </Button>
        </div>
      </section>
    );
  }

  // Feedback loaded
  return (
    <section aria-label="Dynamic feedback" className="space-y-4">
      <h3 className="text-lg font-semibold">Assessment Feedback</h3>

      <div className="space-y-4">
        {/* Correct answer */}
        <div className="rounded-lg border border-green-200 bg-green-50 p-4">
          <div className="flex items-start gap-3">
            <CheckCircle className="h-5 w-5 shrink-0 text-green-600 mt-0.5" aria-hidden="true" />
            <div>
              <h4 className="text-sm font-medium text-green-800">Correct Answer</h4>
              <p className="mt-1 text-sm text-green-900">{feedback!.correct_answer}</p>
            </div>
          </div>
        </div>

        {/* Source paragraph */}
        <div className="rounded-lg border p-4">
          <div className="flex items-start gap-3">
            <BookOpen className="h-5 w-5 shrink-0 text-primary mt-0.5" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-medium text-foreground">Source Paragraph</h4>
              <blockquote className="mt-2 border-l-4 border-primary/30 pl-4 text-sm text-foreground leading-relaxed italic">
                {feedback!.paragraph_text}
              </blockquote>

              {/* Section reference link */}
              <div className="mt-3 flex items-center gap-2">
                <a
                  href={`/documents?section=${encodeURIComponent(feedback!.section_reference)}`}
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                  aria-label={`View section ${feedback!.section_reference} in document viewer`}
                >
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  Section: {feedback!.section_reference}
                </a>
                {feedback!.page_number != null && (
                  <span className="text-xs text-muted-foreground">
                    (Page {feedback!.page_number})
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Explanation */}
        <div className="rounded-lg border bg-muted/30 p-4">
          <div className="flex items-start gap-3">
            <Lightbulb className="h-5 w-5 shrink-0 text-amber-500 mt-0.5" aria-hidden="true" />
            <div>
              <h4 className="text-sm font-medium text-foreground">Explanation</h4>
              <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
                {feedback!.explanation}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
