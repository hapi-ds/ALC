/**
 * TokenCountdown Component
 *
 * Visual countdown timer displayed in the Signature Dialog showing the
 * remaining validity of the signature token. Displays remaining seconds
 * in "{N}s" format with a warning indicator when ≤ 30 seconds remain.
 *
 * Requirements: 3.1, 3.2, 3.3
 */

import { Clock } from "lucide-react";
import { shouldShowWarning } from "@/lib/signatureUtils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TokenCountdownProps {
  remainingSeconds: number;
}

// ---------------------------------------------------------------------------
// TokenCountdown
// ---------------------------------------------------------------------------

export function TokenCountdown({ remainingSeconds }: TokenCountdownProps) {
  const warning = shouldShowWarning(remainingSeconds);

  return (
    <span
      role="timer"
      aria-live="polite"
      className={
        warning
          ? "inline-flex items-center gap-1 text-amber-600 text-sm font-medium"
          : "text-muted-foreground text-sm"
      }
    >
      {warning && (
        <Clock className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {remainingSeconds}s
    </span>
  );
}
