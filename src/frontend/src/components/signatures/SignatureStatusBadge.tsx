/**
 * SignatureStatusBadge Component
 *
 * Displays a small inline badge with a pen-tool icon and signature count
 * on document list items. Shows a tooltip on hover/focus with the most
 * recent signer's display name, transition, and locale-formatted timestamp.
 *
 * Returns null when signatureCount is 0.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */

import { PenTool } from "lucide-react";
import { formatBadgeCount } from "@/lib/signatureUtils";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SignatureStatusBadgeProps {
  documentUuid: string;
  signatureCount: number;
  latestSigner?: {
    displayName: string;
    transition: string;
    signedAt: string;
  };
}

// ---------------------------------------------------------------------------
// SignatureStatusBadge
// ---------------------------------------------------------------------------

export function SignatureStatusBadge({
  signatureCount,
  latestSigner,
}: SignatureStatusBadgeProps) {
  // Not rendered when signatureCount is 0 (Requirement 7.3)
  if (signatureCount === 0) {
    return null;
  }

  const badgeText = formatBadgeCount(signatureCount);
  const ariaLabel = `${signatureCount > 99 ? "99+" : signatureCount} signature${signatureCount === 1 ? "" : "s"} applied`;

  // Format the tooltip timestamp in the user's locale
  const tooltipContent = latestSigner
    ? `${latestSigner.displayName} · ${latestSigner.transition} · ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(latestSigner.signedAt))}`
    : undefined;

  return (
    <span
      className="relative inline-flex items-center gap-1 group"
      aria-label={ariaLabel}
      tabIndex={0}
    >
      <PenTool className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
      <span className="text-xs font-medium text-muted-foreground">{badgeText}</span>

      {/* Tooltip on hover/focus (Requirement 7.4) */}
      {tooltipContent && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block group-focus:block whitespace-nowrap rounded bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md border z-50"
        >
          {tooltipContent}
        </span>
      )}
    </span>
  );
}
