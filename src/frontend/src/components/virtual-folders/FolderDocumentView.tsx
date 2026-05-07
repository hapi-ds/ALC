import { ArrowLeft, Loader2, AlertCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";
import { FolderDocumentRow } from "./FolderDocumentRow";
import { FolderPagination } from "./FolderPagination";
import type { VirtualFolderResponse } from "../../types/virtualFolder";

interface FolderDocumentViewProps {
  folder: VirtualFolderResponse;
  onBack: () => void;
}

export function FolderDocumentView({ folder, onBack }: FolderDocumentViewProps) {
  const { selectedFolderDocuments, isDocumentsLoading, documentsError } =
    useVirtualFolderStore();

  return (
    <div className="space-y-6">
      {/* Header with back navigation and folder name */}
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onBack}
          aria-label="Back to folder list"
        >
          <ArrowLeft className="h-4 w-4 mr-1" aria-hidden="true" />
          Back
        </Button>
        <h2 className="text-2xl font-bold">{folder.name}</h2>
      </div>

      {/* Error state */}
      {documentsError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{documentsError}</p>
        </div>
      )}

      {/* Loading state */}
      {isDocumentsLoading && (
        <div
          className="flex items-center justify-center py-8"
          aria-label="Loading documents"
        >
          <Loader2
            className="h-6 w-6 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
          <span className="sr-only">Loading documents</span>
        </div>
      )}

      {/* Empty state */}
      {!isDocumentsLoading && !documentsError && selectedFolderDocuments.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
          <p className="text-lg font-medium">No documents match this folder's filter</p>
        </div>
      )}

      {/* Document list */}
      {!isDocumentsLoading && !documentsError && selectedFolderDocuments.length > 0 && (
        <div className="grid gap-2" role="list" aria-label="Folder documents">
          {selectedFolderDocuments.map((doc) => (
            <FolderDocumentRow key={doc.id} document={doc} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {!isDocumentsLoading && !documentsError && selectedFolderDocuments.length > 0 && (
        <FolderPagination />
      )}
    </div>
  );
}
