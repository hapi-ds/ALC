import { useEffect, useState } from "react";
import { Upload, FileText, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentStore } from "@/stores/documentStore";
import { useAuthStore } from "@/stores/authStore";
import {
  DocumentDetail,
  DocumentList,
  FilterBar,
  Pagination,
  UploadDialog,
  VersionUploadDialog,
} from "@/components/documents";

export function DocumentsPage() {
  const {
    documents,
    selectedDocument,
    isLoading,
    error,
    fetchDocuments,
    fetchDocument,
  } = useDocumentStore();

  const activeCompanySlug = useAuthStore((s) => s.activeCompanySlug);

  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [versionDialogOpen, setVersionDialogOpen] = useState(false);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  function handleDocumentClick(documentUuid: string) {
    fetchDocument(documentUuid);
  }

  function handleBackToList() {
    useDocumentStore.setState({ selectedDocument: null });
  }

  // Detail view
  if (selectedDocument) {
    return (
      <div className="space-y-6">
        <DocumentDetail
          document={selectedDocument}
          onBack={handleBackToList}
          onNewVersion={() => setVersionDialogOpen(true)}
        />
        <VersionUploadDialog
          open={versionDialogOpen}
          onOpenChange={setVersionDialogOpen}
          documentUuid={selectedDocument.document_uuid}
        />
      </div>
    );
  }

  // List view
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Documents</h2>
          {activeCompanySlug && (
            <p className="text-sm text-muted-foreground">
              {activeCompanySlug}
            </p>
          )}
        </div>
        <Button onClick={() => setUploadDialogOpen(true)}>
          <Upload className="h-4 w-4 mr-2" aria-hidden="true" />
          Upload Document
        </Button>
      </div>

      {/* Filter bar */}
      <FilterBar />

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
      )}

      {/* Loading indicator */}
      {isLoading && (
        <div className="flex items-center justify-center py-8" aria-label="Loading documents">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Loading documents</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && documents.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
          <p className="text-lg font-medium">No documents yet</p>
          <p className="text-sm mt-1">Upload your first document to get started</p>
        </div>
      )}

      {/* Document list */}
      {!isLoading && documents.length > 0 && (
        <DocumentList documents={documents} onDocumentClick={handleDocumentClick} />
      )}

      {/* Pagination */}
      {!isLoading && documents.length > 0 && <Pagination />}

      {/* Upload dialog */}
      <UploadDialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen} />
    </div>
  );
}
