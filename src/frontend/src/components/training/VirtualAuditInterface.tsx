/**
 * VirtualAuditInterface
 *
 * Chat-style interface for the Virtual Audit role-play engine.
 * - Auditor questions are left-aligned
 * - User responses are right-aligned
 * - Per-turn score indicators (green ≥0.70, yellow ≥0.40, red <0.40)
 * - Progress bar showing turns completed vs total_turns
 * - Response input with 2000 character limit indicator
 *
 * Requirements: 10.5
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useTrainingEcosystemStore } from "@/stores/trainingEcosystemStore";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_RESPONSE_LENGTH = 2000;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ChatMessage {
  role: "auditor" | "user";
  content: string;
  score?: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getScoreColor(score: number): string {
  if (score >= 0.7) return "bg-green-100 text-green-800 border-green-200";
  if (score >= 0.4) return "bg-yellow-100 text-yellow-800 border-yellow-200";
  return "bg-red-100 text-red-800 border-red-200";
}

function getScoreLabel(score: number): string {
  if (score >= 0.7) return "Good";
  if (score >= 0.4) return "Fair";
  return "Needs improvement";
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function VirtualAuditInterface() {
  const [responseText, setResponseText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    activeSession,
    lastEvaluation,
    isLoadingSession,
    isSubmittingResponse,
    sessionError,
    responseError,
    submitResponse,
  } = useTrainingEcosystemStore();

  // Scroll to bottom when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // When a new evaluation comes in, add messages
  useEffect(() => {
    if (lastEvaluation) {
      // Compute average score from evaluation dimensions
      const evalValues = Object.values(lastEvaluation.evaluation);
      const avgScore =
        evalValues.length > 0
          ? evalValues.reduce((sum, v) => sum + v, 0) / evalValues.length
          : 0;

      // Update the last user message with score
      setMessages((prev) => {
        const updated = [...prev];
        const lastUserIdx = updated.findLastIndex((m) => m.role === "user");
        if (lastUserIdx >= 0 && updated[lastUserIdx].score === undefined) {
          updated[lastUserIdx] = { ...updated[lastUserIdx], score: avgScore };
        }
        return updated;
      });

      // Add next auditor question if session is not complete
      if (lastEvaluation.next_question) {
        setMessages((prev) => [
          ...prev,
          { role: "auditor", content: lastEvaluation.next_question! },
        ]);
      }
    }
  }, [lastEvaluation]);

  // Handle starting a session (for demo, we'd need document selection)
  // The session is started from the parent page; here we just display it

  // Add first question when session starts
  useEffect(() => {
    if (activeSession && activeSession.session_data) {
      const sessionData = activeSession.session_data as {
        turns?: Array<{ question: string; response?: string; evaluation?: Record<string, number> }>;
        first_question?: string;
      };

      const newMessages: ChatMessage[] = [];

      if (sessionData.first_question) {
        newMessages.push({ role: "auditor", content: sessionData.first_question });
      }

      if (sessionData.turns) {
        for (const turn of sessionData.turns) {
          if (turn.question && newMessages[newMessages.length - 1]?.content !== turn.question) {
            newMessages.push({ role: "auditor", content: turn.question });
          }
          if (turn.response) {
            const evalValues = turn.evaluation ? Object.values(turn.evaluation) : [];
            const score =
              evalValues.length > 0
                ? evalValues.reduce((sum, v) => sum + v, 0) / evalValues.length
                : undefined;
            newMessages.push({ role: "user", content: turn.response, score });
          }
        }
      }

      if (newMessages.length > 0) {
        setMessages(newMessages);
      }
    }
  }, [activeSession?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = useCallback(() => {
    if (!responseText.trim() || !activeSession || isSubmittingResponse) return;
    if (responseText.length > MAX_RESPONSE_LENGTH) return;

    // Add user message to chat
    setMessages((prev) => [...prev, { role: "user", content: responseText }]);

    // Submit to API
    submitResponse(activeSession.id, responseText);
    setResponseText("");
  }, [responseText, activeSession, isSubmittingResponse, submitResponse]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const charCount = responseText.length;
  const isOverLimit = charCount > MAX_RESPONSE_LENGTH;
  const isSessionComplete = activeSession?.status === "completed";

  // No active session state
  if (!activeSession && !isLoadingSession) {
    return (
      <section aria-label="Virtual audit" className="space-y-4">
        <h3 className="text-lg font-semibold">Virtual Audit</h3>
        <div className="rounded-lg border border-dashed p-8 text-center">
          <Bot className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm text-muted-foreground">
            Start a virtual audit session from your training schedule to demonstrate document comprehension.
          </p>
        </div>
      </section>
    );
  }

  // Loading state
  if (isLoadingSession) {
    return (
      <section aria-label="Virtual audit" className="space-y-4">
        <h3 className="text-lg font-semibold">Virtual Audit</h3>
        <div className="flex items-center justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="ml-2 text-sm text-muted-foreground">Starting session...</span>
        </div>
      </section>
    );
  }

  // Compute progress
  const turnsCompleted = activeSession?.turns_completed ?? 0;
  const totalTurns = activeSession?.total_turns ?? 1;
  const progressPercent = Math.round((turnsCompleted / totalTurns) * 100);

  return (
    <section aria-label="Virtual audit" className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Virtual Audit</h3>
        {activeSession?.overall_score != null && (
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
              getScoreColor(activeSession.overall_score)
            )}
          >
            Score: {Math.round(activeSession.overall_score * 100)}%
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Turn {turnsCompleted} of {totalTurns}</span>
          <span>{progressPercent}%</span>
        </div>
        <div
          className="h-2 w-full rounded-full bg-muted overflow-hidden"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Audit progress: ${turnsCompleted} of ${totalTurns} turns completed`}
        >
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Error display */}
      {(sessionError || responseError) && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3">
          <p className="text-sm text-destructive">{sessionError || responseError}</p>
        </div>
      )}

      {/* Chat messages */}
      <div
        className="rounded-lg border bg-muted/20 p-4 space-y-4 max-h-[500px] overflow-y-auto"
        aria-label="Audit conversation"
        role="log"
        aria-live="polite"
      >
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={cn(
              "flex gap-3",
              msg.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            {msg.role === "auditor" && (
              <div className="shrink-0 h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                <Bot className="h-4 w-4 text-primary" aria-hidden="true" />
              </div>
            )}

            <div
              className={cn(
                "max-w-[75%] rounded-lg px-4 py-3",
                msg.role === "auditor"
                  ? "bg-card border text-foreground"
                  : "bg-primary text-primary-foreground"
              )}
            >
              <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

              {/* Score indicator for user messages */}
              {msg.role === "user" && msg.score !== undefined && (
                <div className="mt-2 pt-2 border-t border-primary-foreground/20">
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
                      getScoreColor(msg.score)
                    )}
                  >
                    {getScoreLabel(msg.score)} ({Math.round(msg.score * 100)}%)
                  </span>
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div className="shrink-0 h-8 w-8 rounded-full bg-secondary flex items-center justify-center">
                <User className="h-4 w-4 text-secondary-foreground" aria-hidden="true" />
              </div>
            )}
          </div>
        ))}

        {/* Submitting indicator */}
        {isSubmittingResponse && (
          <div className="flex gap-3 justify-start">
            <div className="shrink-0 h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="h-4 w-4 text-primary" aria-hidden="true" />
            </div>
            <div className="bg-card border rounded-lg px-4 py-3">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden="true" />
              <span className="sr-only">Evaluating response...</span>
            </div>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Session complete message */}
      {isSessionComplete && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-center">
          <p className="text-sm font-medium text-green-800">
            Session complete!{" "}
            {activeSession?.passed
              ? "You passed the virtual audit."
              : "You did not meet the passing threshold."}
          </p>
          {activeSession?.overall_score != null && (
            <p className="mt-1 text-xs text-green-700">
              Final score: {Math.round(activeSession.overall_score * 100)}% (passing: 70%)
            </p>
          )}
        </div>
      )}

      {/* Response input */}
      {!isSessionComplete && activeSession && (
        <div className="space-y-2">
          <div className="relative">
            <textarea
              ref={textareaRef}
              value={responseText}
              onChange={(e) => setResponseText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your response... (Shift+Enter for new line)"
              disabled={isSubmittingResponse}
              maxLength={MAX_RESPONSE_LENGTH + 100} // Allow slight overflow for UX
              rows={3}
              className={cn(
                "w-full rounded-lg border bg-background px-4 py-3 pr-12 text-sm resize-none",
                "focus:outline-none focus:ring-2 focus:ring-primary/50",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                isOverLimit && "border-destructive focus:ring-destructive/50"
              )}
              aria-label="Your response to the auditor"
              aria-describedby="char-count"
            />
            <Button
              variant="ghost"
              size="icon"
              onClick={handleSubmit}
              disabled={!responseText.trim() || isOverLimit || isSubmittingResponse}
              className="absolute right-2 bottom-2"
              aria-label="Send response"
            >
              <Send className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>

          {/* Character count */}
          <div id="char-count" className="flex justify-end">
            <span
              className={cn(
                "text-xs",
                isOverLimit ? "text-destructive font-medium" : "text-muted-foreground"
              )}
            >
              {charCount}/{MAX_RESPONSE_LENGTH}
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
