import { ArrowLeft, Plus, History, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentResponse } from "@/types/document";

interface DocumentDetailProps {
  document: DocumentResponse;
  onNewVersion: () => void;
  onBack: () => void;
}

export function DocumentDetail({
  document,
  onNewVersion,
  onBack,
}: DocumentDetailProps) {
  return (
    <div className="space-y-6">
      {/* Header with back button and actions */}
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="gap-1"
          aria-label="Back to document list"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back
        </Button>
        <Button onClick={onNewVersion} size="sm" className="gap-1">
          <Plus className="h-4 w-4" aria-hidden="true" />
          New Version
        </Button>
      </div>

      {/* Document metadata */}
      <div className="border border-border rounded-md p-4 space-y-4">
        <h2 className="text-lg font-semibold">{document.title}</h2>

        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Document UUID</dt>
            <dd className="font-medium">{document.document_uuid}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Folder Path</dt>
            <dd className="font-medium">{document.folder_path}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Document Type</dt>
            <dd className="font-medium">{document.document_type}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Status</dt>
            <dd>
              <span className="inline-block text-xs px-2 py-0.5 bg-muted rounded font-medium">
                {document.current_status}
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Created By</dt>
            <dd className="font-medium">{document.created_by}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Created At</dt>
            <dd className="font-medium">
              {new Date(document.created_at).toLocaleString()}
            </dd>
          </div>
        </dl>

        {/* Tags */}
        {document.tags.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1 text-sm text-muted-foreground">
              <Tag className="h-3 w-3" aria-hidden="true" />
              <span>Tags</span>
            </div>
            <div className="flex flex-wrap gap-2" role="list" aria-label="Document tags">
              {document.tags.map((tag) => (
                <span
                  key={tag.id}
                  role="listitem"
                  className="inline-flex items-center text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full font-medium"
                >
                  {tag.tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Version history */}
      <div className="border border-border rounded-md p-4 space-y-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <h3 className="text-sm font-semibold">Version History</h3>
        </div>

        {document.versions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No versions available</p>
        ) : (
          <div className="space-y-2" role="list" aria-label="Version history">
            {document.versions.map((version) => (
              <div
                key={version.id}
                role="listitem"
                className="flex items-start gap-3 p-2 border-l-2 border-primary/30 pl-4"
              >
                <div className="flex-1">
                  <p className="text-sm font-medium">
                    v{version.major_version}.{version.minor_version}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(version.uploaded_at).toLocaleString()}
                  </p>
                  {version.change_reason && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {version.change_reason}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
