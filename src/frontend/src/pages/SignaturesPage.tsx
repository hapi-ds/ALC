/**
 * SignaturesPage Component
 *
 * Full Signatures Overview page displaying a paginated, filterable, sortable
 * list of all signature records accessible to the current user.
 *
 * Records are sourced from the signatureStore's `records` map (flattened from
 * all document keys). The page shows records that have been loaded by other
 * views (e.g., document detail pages).
 *
 * This component does NOT call backend APIs directly — it delegates to
 * signatureStore.fetchSignatureRecords(documentUuid) which calls:
 *   GET /api/signatures/records/{document_uuid}
 *
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  PenTool,
  Copy,
  Check,
  ChevronUp,
  ChevronDown,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSignatureStore } from "@/stores/signatureStore";
import {
  filterSignatureRecords,
  sortSignatureRecords,
} from "@/lib/signatureUtils";
import type { SignatureRecordResponse } from "@/types/signature";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;
const DEBOUNCE_MS = 300;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortField = "signed_at" | "signer_user_id" | "document_uuid";
type SortDirection = "asc" | "desc";

// ---------------------------------------------------------------------------
// SignaturesPage
// ---------------------------------------------------------------------------

export function SignaturesPage() {
  const navigate = useNavigate();

  // Store state
  const records = useSignatureStore((s) => s.records);
  const isLoadingRecords = useSignatureStore((s) => s.isLoadingRecords);
  const recordsError = useSignatureStore((s) => s.recordsError);

  // Local component state: pagination
  const [page, setPage] = useState(1);

  // Local component state: filters
  const [documentUuidFilter, setDocumentUuidFilter] = useState("");
  const [debouncedDocumentUuid, setDebouncedDocumentUuid] = useState("");
  const [transitionFilter, setTransitionFilter] = useState("");
  const [dateStart, setDateStart] = useState<string>("");
  const [dateEnd, setDateEnd] = useState<string>("");

  // Local component state: sort
  const [sortField, setSortField] = useState<SortField>("signed_at");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Copy-to-clipboard state
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Debounce ref for document UUID filter
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---------------------------------------------------------------------------
  // Debounce document UUID filter input (300ms)
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      setDebouncedDocumentUuid(documentUuidFilter);
      setPage(1);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [documentUuidFilter]);

  // ---------------------------------------------------------------------------
  // Flatten all records from the store's records map
  // ---------------------------------------------------------------------------

  const allRecords: SignatureRecordResponse[] = useMemo(() => {
    const flat: SignatureRecordResponse[] = [];
    for (const docRecords of Object.values(records)) {
      flat.push(...docRecords);
    }
    return flat;
  }, [records]);

  // ---------------------------------------------------------------------------
  // Distinct transitions for the dropdown filter
  // ---------------------------------------------------------------------------

  const distinctTransitions: string[] = useMemo(() => {
    const set = new Set<string>();
    for (const record of allRecords) {
      set.add(record.transition);
    }
    return Array.from(set).sort();
  }, [allRecords]);

  // ---------------------------------------------------------------------------
  // Apply filters
  // ---------------------------------------------------------------------------

  const filteredRecords = useMemo(() => {
    return filterSignatureRecords(allRecords, {
      documentUuid: debouncedDocumentUuid,
      transition: transitionFilter,
      dateStart: dateStart || null,
      dateEnd: dateEnd ? dateEnd + "T23:59:59.999Z" : null,
    });
  }, [allRecords, debouncedDocumentUuid, transitionFilter, dateStart, dateEnd]);

  // ---------------------------------------------------------------------------
  // Apply sort
  // ---------------------------------------------------------------------------

  const sortedRecords = useMemo(() => {
    if (sortField === "signed_at") {
      return sortSignatureRecords(filteredRecords, sortDirection);
    }

    // For other fields, sort manually
    return [...filteredRecords].sort((a, b) => {
      let comparison = 0;
      if (sortField === "signer_user_id") {
        comparison = a.signer_user_id - b.signer_user_id;
      } else if (sortField === "document_uuid") {
        comparison = a.document_uuid.localeCompare(b.document_uuid);
      }
      return sortDirection === "desc" ? -comparison : comparison;
    });
  }, [filteredRecords, sortField, sortDirection]);

  // ---------------------------------------------------------------------------
  // Pagination
  // ---------------------------------------------------------------------------

  const totalCount = sortedRecords.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const startIndex = (page - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, totalCount);
  const paginatedRecords = sortedRecords.slice(startIndex, endIndex);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function handleTransitionFilterChange(value: string) {
    setTransitionFilter(value);
    setPage(1);
  }

  function handleDateStartChange(value: string) {
    setDateStart(value);
    setPage(1);
  }

  function handleDateEndChange(value: string) {
    setDateEnd(value);
    setPage(1);
  }

  function handleSortClick(field: SortField) {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  }

  const handleDocumentClick = useCallback(
    (documentUuid: string) => {
      navigate(`/documents?uuid=${documentUuid}`);
    },
    [navigate]
  );

  async function handleCopyHash(hash: string) {
    try {
      await navigator.clipboard.writeText(hash);
      setCopiedHash(hash);
      setTimeout(() => setCopiedHash(null), 2000);
    } catch {
      // Silently fail if clipboard API is unavailable
    }
  }

  function handleRetry() {
    // Re-fetch all known document records via the store action
    // (store calls GET /api/signatures/records/{document_uuid})
    const { fetchSignatureRecords } = useSignatureStore.getState();
    for (const docUuid of Object.keys(records)) {
      fetchSignatureRecords(docUuid);
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
  // Sort indicator component
  // ---------------------------------------------------------------------------

  function SortIndicator({ field }: { field: SortField }) {
    if (sortField !== field) {
      return (
        <span className="ml-1 inline-flex flex-col opacity-30">
          <ChevronUp className="h-3 w-3 -mb-1" aria-hidden="true" />
          <ChevronDown className="h-3 w-3" aria-hidden="true" />
        </span>
      );
    }
    return sortDirection === "asc" ? (
      <ChevronUp className="ml-1 h-3.5 w-3.5 inline" aria-hidden="true" />
    ) : (
      <ChevronDown className="ml-1 h-3.5 w-3.5 inline" aria-hidden="true" />
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Skeleton loading state
  // ---------------------------------------------------------------------------

  function renderSkeletons() {
    return (
      <div className="space-y-2" aria-label="Loading signature records">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="rounded-md border border-border p-4 animate-pulse"
          >
            <div className="flex gap-4">
              <div className="h-4 w-48 rounded bg-muted" />
              <div className="h-4 w-16 rounded bg-muted" />
              <div className="h-4 w-32 rounded bg-muted" />
              <div className="h-4 w-40 rounded bg-muted" />
              <div className="h-4 w-24 rounded bg-muted" />
              <div className="h-4 w-36 rounded bg-muted" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Error state
  // ---------------------------------------------------------------------------

  function renderError() {
    return (
      <div className="flex items-center gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-4">
        <AlertTriangle
          className="h-5 w-5 text-destructive shrink-0"
          aria-hidden="true"
        />
        <p className="text-sm text-destructive flex-1">
          Unable to load signature records.
        </p>
        <Button variant="outline" size="sm" onClick={handleRetry}>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
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
      <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
        <PenTool
          className="h-12 w-12 mx-auto mb-4 opacity-50"
          aria-hidden="true"
        />
        <p className="text-lg font-medium">No electronic signatures found.</p>
        <p className="text-sm mt-1">
          Signatures are created when workflow transitions require signing.
        </p>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-2">
          <PenTool className="h-5 w-5 text-primary" aria-hidden="true" />
          <h2 className="text-2xl font-bold">Electronic Signatures</h2>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          Overview of all signature records across documents
        </p>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-end gap-3">
        {/* Document UUID filter */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-document-uuid"
            className="text-xs font-medium text-muted-foreground"
          >
            Document UUID
          </label>
          <input
            id="filter-document-uuid"
            type="text"
            value={documentUuidFilter}
            onChange={(e) => setDocumentUuidFilter(e.target.value)}
            placeholder="Search by UUID..."
            className="h-9 w-56 px-3 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Transition filter dropdown */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-transition"
            className="text-xs font-medium text-muted-foreground"
          >
            Transition
          </label>
          <select
            id="filter-transition"
            value={transitionFilter}
            onChange={(e) => handleTransitionFilterChange(e.target.value)}
            className="h-9 w-48 px-2 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">All transitions</option>
            {distinctTransitions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>

        {/* Date range: start */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-date-start"
            className="text-xs font-medium text-muted-foreground"
          >
            From
          </label>
          <input
            id="filter-date-start"
            type="date"
            value={dateStart}
            onChange={(e) => handleDateStartChange(e.target.value)}
            className="h-9 w-40 px-2 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Date range: end */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-date-end"
            className="text-xs font-medium text-muted-foreground"
          >
            To
          </label>
          <input
            id="filter-date-end"
            type="date"
            value={dateEnd}
            onChange={(e) => handleDateEndChange(e.target.value)}
            className="h-9 w-40 px-2 text-sm border border-border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>

      {/* Loading state */}
      {isLoadingRecords && allRecords.length === 0 && renderSkeletons()}

      {/* Error state */}
      {recordsError && renderError()}

      {/* Empty state */}
      {!isLoadingRecords && !recordsError && totalCount === 0 && renderEmpty()}

      {/* Records table */}
      {!recordsError && totalCount > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">
                    <button
                      type="button"
                      onClick={() => handleSortClick("document_uuid")}
                      className="inline-flex items-center hover:text-foreground transition-colors"
                      aria-label="Sort by document UUID"
                    >
                      Document
                      <SortIndicator field="document_uuid" />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 font-medium">
                    <button
                      type="button"
                      onClick={() => handleSortClick("signer_user_id")}
                      className="inline-flex items-center hover:text-foreground transition-colors"
                      aria-label="Sort by signer"
                    >
                      Signer
                      <SortIndicator field="signer_user_id" />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 font-medium">
                    Transition
                  </th>
                  <th className="text-left px-4 py-3 font-medium">Reason</th>
                  <th className="text-left px-4 py-3 font-medium">
                    <button
                      type="button"
                      onClick={() => handleSortClick("signed_at")}
                      className="inline-flex items-center hover:text-foreground transition-colors"
                      aria-label="Sort by signed date"
                    >
                      Signed At
                      <SortIndicator field="signed_at" />
                    </button>
                  </th>
                  <th className="text-left px-4 py-3 font-medium">Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paginatedRecords.map((record) => {
                  const truncatedHash =
                    record.signature_hash.substring(0, 16) + "\u2026";
                  const isCopied = copiedHash === record.signature_hash;

                  return (
                    <tr
                      key={`${record.document_uuid}-${record.id}`}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      {/* Document UUID (clickable link) */}
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            handleDocumentClick(record.document_uuid)
                          }
                          className="text-primary hover:underline font-mono text-xs truncate max-w-[200px] block"
                          title={record.document_uuid}
                        >
                          {record.document_uuid}
                        </button>
                      </td>

                      {/* Signer user ID */}
                      <td className="px-4 py-3">
                        User #{record.signer_user_id}
                      </td>

                      {/* Transition */}
                      <td className="px-4 py-3">{record.transition}</td>

                      {/* Reason */}
                      <td className="px-4 py-3 max-w-[200px] truncate">
                        {record.reason || "\u2014"}
                      </td>

                      {/* Signed at (locale-formatted) */}
                      <td className="px-4 py-3 whitespace-nowrap">
                        {formatTimestamp(record.signed_at)}
                      </td>

                      {/* Signature hash (truncated + copy button) */}
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5">
                          <code className="text-xs bg-muted px-1 py-0.5 rounded">
                            {truncatedHash}
                          </code>
                          <button
                            type="button"
                            onClick={() =>
                              handleCopyHash(record.signature_hash)
                            }
                            className="inline-flex items-center justify-center h-6 w-6 rounded hover:bg-muted transition-colors"
                            aria-label={
                              isCopied
                                ? "Copied signature hash"
                                : "Copy full signature hash to clipboard"
                            }
                            title={isCopied ? "Copied!" : "Copy full hash"}
                          >
                            {isCopied ? (
                              <Check
                                className="h-3.5 w-3.5 text-green-600"
                                aria-hidden="true"
                              />
                            ) : (
                              <Copy
                                className="h-3.5 w-3.5 text-muted-foreground"
                                aria-hidden="true"
                              />
                            )}
                          </button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination controls */}
      {totalCount > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing {startIndex + 1}–{endIndex} of {totalCount} records
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
