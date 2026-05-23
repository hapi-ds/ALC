import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface SearchPaginationProps {
  offset: number;
  limit: number;
  totalAvailable: number;
  onNext: () => void;
  onPrevious: () => void;
}

export function SearchPagination({
  offset,
  limit,
  totalAvailable,
  onNext,
  onPrevious,
}: SearchPaginationProps) {
  if (totalAvailable <= limit) {
    return null;
  }

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(totalAvailable / limit);

  const isPrevDisabled = offset === 0;
  const isNextDisabled = offset + limit >= totalAvailable;

  return (
    <div
      className="flex items-center justify-center gap-2 py-4"
      role="navigation"
      aria-label="Search results pagination"
    >
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onPrevious}
        disabled={isPrevDisabled}
        aria-label="Go to previous page"
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
        onClick={onNext}
        disabled={isNextDisabled}
        aria-label="Go to next page"
      >
        Next
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </Button>
    </div>
  );
}
