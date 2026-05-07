import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentStore } from "@/stores/documentStore";

export function Pagination() {
  const { offset, limit, total, prevPage, nextPage, fetchDocuments } =
    useDocumentStore();

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  const isPrevDisabled = offset === 0;
  const isNextDisabled = offset + limit >= total;

  async function handlePrev() {
    prevPage();
    await fetchDocuments();
  }

  async function handleNext() {
    nextPage();
    await fetchDocuments();
  }

  return (
    <div className="flex items-center justify-between py-4" role="navigation" aria-label="Pagination">
      <p className="text-sm text-muted-foreground">
        {total} {total === 1 ? "document" : "documents"} total
      </p>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handlePrev}
          disabled={isPrevDisabled}
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
          onClick={handleNext}
          disabled={isNextDisabled}
          aria-label="Next page"
        >
          Next
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
