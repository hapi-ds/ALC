import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";

export function FolderPagination() {
  const {
    documentsOffset,
    documentsLimit,
    selectedFolderDocuments,
    nextDocumentsPage,
    prevDocumentsPage,
  } = useVirtualFolderStore();

  const isPrevDisabled = documentsOffset === 0;
  const isNextDisabled = selectedFolderDocuments.length < documentsLimit;

  return (
    <div
      className="flex items-center justify-end py-4"
      role="navigation"
      aria-label="Folder documents pagination"
    >
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={prevDocumentsPage}
          disabled={isPrevDisabled}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Previous
        </Button>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={nextDocumentsPage}
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
