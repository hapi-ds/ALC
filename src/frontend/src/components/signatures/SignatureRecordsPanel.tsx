/**
 * SignatureRecordsPanel Component
 *
 * Displays signature records on the document detail page in a collapsible
 * section. Fetches records from signatureStore on mount, sorts them
 * descending by signed_at, and auto-refreshes when a new signature is
 * applied to the same document.
 *
 * Includes verification UI: a "Verify" button that triggers signature
 * verification, displays result banners (valid/invalid), highlights
 * tampered records, and shows certificate subjects for PAdES-mode records.
 *
 * This component does NOT call backend APIs directly — it delegates to
 * signatureStore.fetchSignatureRecords(documentUuid) and
 * signatureStore.verifySignatures(documentUuid).
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 11.12, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6
 */

import { useEffect, useRef, useState } from "react";
import {
  PenTool,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  Loader2,
  AlertTriangle,
  RefreshCw,
  ShieldCheck,
  CheckCircle,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSignatureStore } from "@/stores/signatureStore";
import { sortSignatureRecords } from "@/lib/signatureUtils";
import type { SignatureRecordResponse } from "@/types/signature";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface SignatureRecordsPanelProps {
  documentUuid: string;
}

// ---------------------------------------------------------------------------
// SignatureRecordsPanel
// ---------------------------------------------------------------------------

export function SignatureRecordsPanel({
  documentUuid,
}: SignatureRecordsPanelProps) {
  const records = useSignatureStore((s) => s.records[documentUuid]);
  const isLoadingRecords = useSignatureStore((s) => s.isLoadingRecords);
  const recordsError = useSignatureStore((s) => s.recordsError);
  const lastSignResult = useSignatureStore((s) => s.lastSignResult);
  const dialogContext = useSignatureStore((s) => s.dialogContext);
  const fetchSignatureRecords = useSignatureStore(
    (s) => s.fetchSignatureRecords
  );

  // Verification state
  const isVerifying = useSignatureStore((s) => s.isVerifying);
  const verifyError = useSignatureStore((s) => s.verifyError);
  const verifyResult = useSignatureStore((s) => s.verifyResult);
  const verifySignatures = useSignatureStore((s) => s.verifySignatures);

  const [isExpanded, setIsExpanded] = useState<boolean | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Track lastSignResult to detect changes for auto-refresh
  const prevSignResultRef = useRef(lastSignResult);

  // ---------------------------------------------------------------------------
  // Fetch records on mount
  // ---------------------------------------------------------------------------

  useEffect(() => {
    fetchSignatureRecords(documentUuid);
  }, [documentUuid, fetchSignatureRecords]);

  // ---------------------------------------------------------------------------
  // Auto-refresh: watch lastSignResult for changes matching this document
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (
      lastSignResult &&
      lastSignResult !== prevSignResultRef.current &&
      dialogContext?.document_uuid === documentUuid
    ) {
      fetchSignatureRecords(documentUuid);
    }
    prevSignResultRef.current = lastSignResult;
  }, [lastSignResult, dialogContext, documentUuid, fetchSignatureRecords]);

  // ---------------------------------------------------------------------------
  // Default expanded state: expand when records exist, collapse when empty
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (isExpanded === null && records !== undefined) {
      setIsExpanded(records.length > 0);
    }
  }, [records, isExpanded]);

  // ---------------------------------------------------------------------------
  // Sorted records (descending by signed_at)
  // ---------------------------------------------------------------------------

  const sortedRecords: SignatureRecordResponse[] = records
    ? sortSignatureRecords(records, "desc")
    : [];

  const recordCount = records?.length ?? 0;

  // ---------------------------------------------------------------------------
  // Compute tampered indices for the sorted (descending) view.
  //
  // `tampered_from_index` refers to the original ascending order.
  // Records at index >= tampered_from_index in ascending order are invalid.
  // We need to map those to the descending-sorted view.
  // ---------------------------------------------------------------------------

  function isTamperedRecord(record: SignatureRecordResponse): boolean {
    if (!verifyResult || verifyResult.tampered_from_index < 0) return false;
    if (!records) return false;

    // Get the ascending-sorted records to find the original index
    const ascendingRecords = sortSignatureRecords(records, "asc");
    const ascIndex = ascendingRecords.findIndex((r) => r.id === record.id);
    return ascIndex >= verifyResult.tampered_from_index;
  }

  // ---------------------------------------------------------------------------
  // Copy to clipboard handler
  // ---------------------------------------------------------------------------

  async function handleCopyHash(hash: string) {
    try {
      await navigator.clipboard.writeText(hash);
      setCopiedHash(hash);
      setTimeout(() => setCopiedHash(null), 2000);
    } catch {
      // Silently fail if clipboard API is unavailable
    }
  }

  // ---------------------------------------------------------------------------
  // Format timestamp in user's locale
  // ---------------------------------------------------------------------------

  function formatTimestamp(isoString: string): string {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(isoString));
  }

  // ---------------------------------------------------------------------------
  // Render: Loading state (skeleton placeholders — 3 rows)
  // ---------------------------------------------------------------------------

  function renderSkeletons() {
    return (
      <div className="space-y-3" aria-label="Loading signature records">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="rounded-md border border-border p-3 space-y-2 animate-pulse"
          >
            <div className="h-4 w-1/3 rounded bg-muted" />
            <div className="h-3 w-2/3 rounded bg-muted" />
            <div className="h-3 w-1/2 rounded bg-muted" />
            <div className="h-3 w-1/4 rounded bg-muted" />
          </div>
        ))}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error state with Retry button
  // ---------------------------------------------------------------------------

  function renderError() {
    return (
      <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3">
        <AlertTriangle
          className="h-4 w-4 text-destructive shrink-0"
          aria-hidden="true"
        />
        <p className="text-sm text-destructive flex-1">
          Unable to load signature records.
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchSignatureRecords(documentUuid)}
          className="shrink-0"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Empty state
  // ---------------------------------------------------------------------------

  function renderEmpty() {
    return (
      <p className="text-sm text-muted-foreground py-3">
        No electronic signatures have been applied to this document.
      </p>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Verification result banner
  // ---------------------------------------------------------------------------

  function renderVerificationBanner() {
    if (verifyError) {
      return (
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3">
          <AlertTriangle
            className="h-4 w-4 text-destructive shrink-0"
            aria-hidden="true"
          />
          <p className="text-sm text-destructive flex-1">
            Verification failed: {verifyError}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => verifySignatures(documentUuid)}
            className="shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Retry
          </Button>
        </div>
      );
    }

    if (!verifyResult) return null;

    if (verifyResult.is_valid) {
      return (
        <div className="flex items-center gap-2 rounded-md border border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-950/30 p-3">
          <CheckCircle
            className="h-4 w-4 text-green-600 dark:text-green-400 shrink-0"
            aria-hidden="true"
          />
          <p className="text-sm text-green-700 dark:text-green-300 font-medium">
            All signatures valid
          </p>
        </div>
      );
    }

    return (
      <div className="flex items-center gap-2 rounded-md border border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-950/30 p-3">
        <AlertTriangle
          className="h-4 w-4 text-red-600 dark:text-red-400 shrink-0"
          aria-hidden="true"
        />
        <p className="text-sm text-red-700 dark:text-red-300 font-medium">
          Document integrity compromised
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Individual record card
  // ---------------------------------------------------------------------------

  function renderRecord(record: SignatureRecordResponse) {
    const truncatedHash = record.signature_hash.substring(0, 16) + "\u2026";
    const isCopied = copiedHash === record.signature_hash;
    const tampered = isTamperedRecord(record);

    return (
      <div
        key={record.id}
        className={`rounded-md border p-3 space-y-1.5 ${
          tampered
            ? "border-red-400 bg-red-50 dark:border-red-600 dark:bg-red-950/20"
            : "border-border"
        }`}
      >
        <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          {/* Signer */}
          <span className="text-muted-foreground">Signer:</span>
          <span className="font-medium">
            User #{record.signer_user_id}
          </span>

          {/* Transition */}
          <span className="text-muted-foreground">Transition:</span>
          <span>{record.transition}</span>

          {/* Reason */}
          <span className="text-muted-foreground">Reason:</span>
          <span>{record.reason || "\u2014"}</span>

          {/* Timestamp */}
          <span className="text-muted-foreground">Signed at:</span>
          <span>{formatTimestamp(record.signed_at)}</span>

          {/* Signature hash */}
          <span className="text-muted-foreground">Hash:</span>
          <span className="flex items-center gap-1.5">
            <code className="text-xs bg-muted px-1 py-0.5 rounded">
              {truncatedHash}
            </code>
            {tampered && (
              <span className="inline-flex items-center rounded bg-red-100 dark:bg-red-900/40 px-1.5 py-0.5 text-xs font-medium text-red-700 dark:text-red-300">
                Invalid
              </span>
            )}
            <button
              type="button"
              onClick={() => handleCopyHash(record.signature_hash)}
              className="inline-flex items-center justify-center h-6 w-6 rounded hover:bg-muted transition-colors"
              aria-label={
                isCopied
                  ? "Copied signature hash"
                  : "Copy full signature hash to clipboard"
              }
              title={isCopied ? "Copied!" : "Copy full hash"}
            >
              {isCopied ? (
                <Check className="h-3.5 w-3.5 text-green-600" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
              )}
            </button>
            {isCopied && (
              <span className="text-xs text-green-600">Copied!</span>
            )}
          </span>

          {/* Certificate subject (PAdES mode only) */}
          {record.certificate_subject && (
            <>
              <span className="text-muted-foreground">Certificate:</span>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Shield className="h-3 w-3 shrink-0" aria-hidden="true" />
                {record.certificate_subject}
              </span>
            </>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <section aria-labelledby="signature-records-heading" className="space-y-3">
      {/* Collapsible header */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex items-center gap-2 text-left group"
          aria-expanded={isExpanded ?? false}
          aria-controls="signature-records-content"
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          )}
          <PenTool className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <h3
            id="signature-records-heading"
            className="text-sm font-semibold group-hover:text-foreground"
          >
            Electronic Signatures ({recordCount})
          </h3>
          {isLoadingRecords && (
            <Loader2
              className="h-3.5 w-3.5 animate-spin text-muted-foreground"
              aria-hidden="true"
            />
          )}
        </button>

        {/* Verify Signatures button — visible when records exist */}
        {recordCount > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => verifySignatures(documentUuid)}
            disabled={isVerifying}
            className="ml-auto"
          >
            {isVerifying ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            Verify
          </Button>
        )}
      </div>

      {/* Collapsible content */}
      {(isExpanded ?? false) && (
        <div id="signature-records-content" className="space-y-3 pl-6">
          {/* Verification result banner (above records list) */}
          {renderVerificationBanner()}

          {isLoadingRecords && !records && renderSkeletons()}
          {recordsError && renderError()}
          {!isLoadingRecords && !recordsError && recordCount === 0 && renderEmpty()}
          {!recordsError && sortedRecords.length > 0 && (
            <div className="space-y-2">
              {sortedRecords.map(renderRecord)}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
