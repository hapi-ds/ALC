import { Button } from "@/components/ui/button";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";
import {
  ChevronLeft,
  ChevronRight,
  MoreHorizontal,
} from "lucide-react";

/**
 * Generates an array of page numbers (and ellipsis markers) to display,
 * showing at most ~5 page buttons with ellipsis for large page counts.
 */
function getPageRange(
  currentPage: number,
  totalPages: number,
): (number | "ellipsis-start" | "ellipsis-end")[] {
  if (totalPages <= 5) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages: (number | "ellipsis-start" | "ellipsis-end")[] = [];

  // Always show first page
  pages.push(1);

  if (currentPage > 3) {
    pages.push("ellipsis-start");
  }

  // Pages around the current page
  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);

  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (currentPage < totalPages - 2) {
    pages.push("ellipsis-end");
  }

  // Always show last page
  pages.push(totalPages);

  return pages;
}

/**
 * PaginationControls renders page navigation for literature search results.
 * Displays previous/next buttons, page numbers with ellipsis for large sets,
 * and a result count summary.
 *
 * Renders nothing when pagination data is not available.
 */
export default function PaginationControls() {
  const pagination = useLiteratureSearchStore((s) => s.pagination);
  const isLoading = useLiteratureSearchStore((s) => s.isLoading);
  const executeSearch = useLiteratureSearchStore((s) => s.executeSearch);

  if (!pagination) {
    return null;
  }

  const { total_results, page, page_size, total_pages } = pagination;

  if (total_pages <= 1 && total_results === 0) {
    return null;
  }

  const start = (page - 1) * page_size + 1;
  const end = Math.min(page * page_size, total_results);

  const isFirstPage = page === 1;
  const isLastPage = page === total_pages;

  const pageRange = getPageRange(page, total_pages);

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > total_pages || newPage === page) return;
    void executeSearch(newPage);
  };

  return (
    <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
      <p className="text-sm text-muted-foreground">
        Showing {start}&ndash;{end} of {total_results} results
      </p>

      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={isFirstPage || isLoading}
          onClick={() => handlePageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
          <span className="sr-only sm:not-sr-only">Previous</span>
        </Button>

        {pageRange.map((item) => {
          if (item === "ellipsis-start" || item === "ellipsis-end") {
            return (
              <span
                key={item}
                className="flex h-8 w-8 items-center justify-center"
                aria-hidden="true"
              >
                <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
              </span>
            );
          }

          return (
            <Button
              key={item}
              variant={item === page ? "default" : "outline"}
              size="sm"
              className="h-8 w-8 p-0"
              disabled={isLoading}
              onClick={() => handlePageChange(item)}
              aria-label={`Page ${item}`}
              aria-current={item === page ? "page" : undefined}
            >
              {item}
            </Button>
          );
        })}

        <Button
          variant="outline"
          size="sm"
          disabled={isLastPage || isLoading}
          onClick={() => handlePageChange(page + 1)}
          aria-label="Next page"
        >
          <span className="sr-only sm:not-sr-only">Next</span>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
