import { Button } from "@/components/ui/button";
import { Upload, FileText, Tag, History } from "lucide-react";

export function DocumentsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Documents</h2>
          <p className="text-sm text-muted-foreground">
            Manage documents, versions, and tags
          </p>
        </div>
        <Button>
          <Upload className="h-4 w-4 mr-2" aria-hidden="true" />
          Upload Document
        </Button>
      </div>

      {/* Document list placeholder */}
      <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
        <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
        <p className="text-lg font-medium">No documents yet</p>
        <p className="text-sm mt-1">Upload your first document to get started</p>
      </div>

      {/* Tag management placeholder */}
      <section aria-label="Tag management">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Tag className="h-4 w-4" aria-hidden="true" />
          Tags
        </h3>
        <p className="text-sm text-muted-foreground mt-1">
          Tag management will be available here
        </p>
      </section>

      {/* Version history placeholder */}
      <section aria-label="Version history">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <History className="h-4 w-4" aria-hidden="true" />
          Version History
        </h3>
        <p className="text-sm text-muted-foreground mt-1">
          Select a document to view its version history
        </p>
      </section>
    </div>
  );
}
