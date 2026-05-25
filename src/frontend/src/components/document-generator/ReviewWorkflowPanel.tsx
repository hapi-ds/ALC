/**
 * ReviewWorkflowPanel
 *
 * Lists AI-generated documents filterable by content_status, document_type,
 * and date range. Provides approve/reject buttons with a comment textarea
 * for each document. Calls reviewDocument and fetchGeneratedDocuments from
 * the documentGeneratorStore.
 *
 * Requirements: 6.2, 6.5
 */

import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import type { GeneratedDocument, GeneratedDocFilters } from "@/types/documentGenerator";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const CONTENT_STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "pending_review", label: "Pending Review" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

const DOCUMENT_TYPE_OPTIONS = [
  { value: "", label: "All types" },
  { value: "URS", label: "URS" },
  { value: "MVP", label: "MVP" },
  { value: "SOP", label: "SOP" },
  { value: "Protocol", label: "Protocol" },
  { value: "Report", label: "Report" },
];

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// Status Badge
// ---------------------------------------------------------------------------

function ContentStatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending_review: "bg-yellow-100 text-yellow-800",
    approved: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
  };

  const labels: Record<string, string> = {
    pending_review: "Pending Review",
    approved: "Approved",
    rejected: "Rejected",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-muted text-muted-foreground"}`}
      aria-label={`Status: ${labels[status] ?? status}`}
    >
      {labels[status] ?? status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Review Action Card
// ---------------------------------------------------------------------------

interface ReviewActionProps {
  document: GeneratedDocument;
  onReviewComplete: () => void;
}

function ReviewAction({ document, onReviewComplete }: ReviewActionProps) {
  const { reviewDocument, isLoading } = useDocumentGeneratorStore();
  const [comment, setComment] = useState("");
  const [showActions, setShowActions] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const canReview = document.content_status === "pending_review";

  const handleReview = useCallback(
    async (action: "approve" | "reject") => {
      setActionError(null);

      if (action === "reject" && !comment.trim()) {
        setActionError("A comment is required when rejecting a document.");
        return;
      }

      const result = await reviewDocument(
        document.id,
        {
          action,
          reviewer_comments: comment.trim() || undefined,
        },
        `${action === "approve" ? "Approved" : "Rejected"} AI-generated document: ${document.title}`,
      );

      if (result) {
        setComment("");
        setShowActions(false);
        onReviewComplete();
      }
    },
    [comment, document.id, document.title, reviewDocument, onReviewComplete],
  );

  if (!canReview) {
    return null;
  }

  return (
    <div className="mt-2">
      {!showActions ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setShowActions(true)}
          aria-label={`Review ${document.title}`}
        >
          Review
        </Button>
      ) : (
        <div className="space-y-2 rounded-md border p-3 bg-muted/20">
          <label htmlFor={`review-comment-${document.id}`} className="text-xs font-medium">
            Reviewer Comment
            <span className="text-muted-foreground ml-1">(required for reject)</span>
          </label>
          <textarea
            id={`review-comment-${document.id}`}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Enter review comments…"
            maxLength={2000}
            rows={3}
            className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-y"
            aria-describedby={actionError ? `review-error-${document.id}` : undefined}
          />
          {actionError && (
            <p id={`review-error-${document.id}`} className="text-xs text-destructive" role="alert">
              {actionError}
            </p>
          )}
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => handleReview("approve")}
              disabled={isLoading}
              aria-label={`Approve ${document.title}`}
            >
              <Check className="h-3 w-3" aria-hidden="true" />
              Approve
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => handleReview("reject")}
              disabled={isLoading}
              aria-label={`Reject ${document.title}`}
            >
              <X className="h-3 w-3" aria-hidden="true" />
              Reject
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowActions(false);
                setComment("");
                setActionError(null);
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReviewWorkflowPanel
// ---------------------------------------------------------------------------

export function ReviewWorkflowPanel() {
  const {
    generatedDocuments,
    generatedDocumentsTotal,
    isLoading,
    error,
    fetchGeneratedDocuments,
  } = useDocumentGeneratorStore();

  const [filters, setFilters] = useState<GeneratedDocFilters>({
    page: 1,
    page_size: PAGE_SIZE,
  });

  // Fetch documents on mount and when filters change
  useEffect(() => {
    fetchGeneratedDocuments(filters);
  }, [filters, fetchGeneratedDocuments]);

  const handleFilterChange = useCallback(
    (key: keyof GeneratedDocFilters, value: string) => {
      setFilters((prev) => ({
        ...prev,
        [key]: value || undefined,
        page: 1, // Reset to first page on filter change
      }));
    },
    [],
  );

  const handleReviewComplete = useCallback(() => {
    fetchGeneratedDocuments(filters);
  }, [filters, fetchGeneratedDocuments]);

  const currentPage = filters.page ?? 1;
  const totalPages = Math.ceil(generatedDocumentsTotal / PAGE_SIZE) || 1;

  return (
    <section aria-label="Review workflow" className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Review Workflow</h3>
        <p className="text-sm text-muted-foreground">
          Approve or reject AI-generated documents before they enter the active document ecosystem.
        </p>
      </div>

      {/* Filters */}
      <div
        className="flex flex-wrap items-end gap-3"
        role="search"
        aria-label="Generated document filters"
      >
        <div className="min-w-[160px]">
          <label htmlFor="filter-content-status" className="text-xs font-medium block mb-1">
            Status
          </label>
          <select
            id="filter-content-status"
            value={filters.content_status ?? ""}
            onChange={(e) => handleFilterChange("content_status", e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {CONTENT_STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[140px]">
          <label htmlFor="filter-document-type" className="text-xs font-medium block mb-1">
            Document Type
          </label>
          <select
            id="filter-document-type"
            value={filters.document_type ?? ""}
            onChange={(e) => handleFilterChange("document_type", e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {DOCUMENT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="min-w-[140px]">
          <label htmlFor="filter-date-from" className="text-xs font-medium block mb-1">
            From Date
          </label>
          <input
            id="filter-date-from"
            type="date"
            value={filters.date_from ?? ""}
            onChange={(e) => handleFilterChange("date_from", e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>

        <div className="min-w-[140px]">
          <label htmlFor="filter-date-to" className="text-xs font-medium block mb-1">
            To Date
          </label>
          <input
            id="filter-date-to"
            type="date"
            value={filters.date_to ?? ""}
            onChange={(e) => handleFilterChange("date_to", e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="text-sm text-destructive" role="alert">
          {error}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="py-6 text-center text-sm text-muted-foreground" aria-live="polite">
          Loading generated documents…
        </div>
      )}

      {/* Document List */}
      {!isLoading && generatedDocuments.length === 0 && (
        <div className="py-6 text-center text-sm text-muted-foreground">
          No generated documents found matching the current filters.
        </div>
      )}

      {!isLoading && generatedDocuments.length > 0 && (
        <ul className="space-y-3" aria-label="Generated documents list">
          {generatedDocuments.map((doc) => (
            <li
              key={doc.id}
              className="rounded-lg border p-4 hover:bg-muted/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="text-sm font-medium truncate">{doc.title}</h4>
                    <ContentStatusBadge status={doc.content_status} />
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>Type: {doc.document_type}</span>
                    <span>Template: {doc.template_name}</span>
                    <span>
                      Generated:{" "}
                      {new Date(doc.generated_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                </div>
              </div>

              <ReviewAction document={doc} onReviewComplete={handleReviewComplete} />
            </li>
          ))}
        </ul>
      )}

      {/* Pagination */}
      {generatedDocumentsTotal > PAGE_SIZE && (
        <div
          className="flex items-center justify-between py-4"
          role="navigation"
          aria-label="Review documents pagination"
        >
          <p className="text-sm text-muted-foreground">
            {generatedDocumentsTotal} {generatedDocumentsTotal === 1 ? "document" : "documents"} total
          </p>

          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setFilters((prev) => ({ ...prev, page: currentPage - 1 }))}
              disabled={currentPage <= 1}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" aria-hidden="true" />
              Previous
            </Button>

            <span className="text-sm text-muted-foreground">
              Page {currentPage} of {totalPages}
            </span>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setFilters((prev) => ({ ...prev, page: currentPage + 1 }))}
              disabled={currentPage >= totalPages}
              aria-label="Next page"
            >
              Next
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
