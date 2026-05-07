import { ArrowLeft, Plus, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentResponse } from "@/types/document";
import { useDocumentStore } from "@/stores/documentStore";
import { VersionHistoryPanel } from "./VersionHistoryPanel";
import { VersionDetailView } from "./VersionDetailView";
import { VersionComparisonView } from "./VersionComparisonView";

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
  const selectedVersion = useDocumentStore((state) => state.selectedVersion);
  const isVersionLoading = useDocumentStore((state) => state.isVersionLoading);
  const versionError = useDocumentStore((state) => state.versionError);
  const comparisonOpen = useDocumentStore((state) => state.comparisonOpen);

  const fetchVersion = useDocumentStore((state) => state.fetchVersion);
  const downloadVersion = useDocumentStore((state) => state.downloadVersion);
  const setComparisonOpen = useDocumentStore((state) => state.setComparisonOpen);
  const clearSelectedVersion = useDocumentStore((state) => state.clearSelectedVersion);

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

      {/* Version History Panel */}
      <VersionHistoryPanel
        versions={document.versions}
        documentTitle={document.title}
        onSelectVersion={(version) =>
          fetchVersion(document.document_uuid, version.major_version, version.minor_version)
        }
        onDownload={(version) =>
          downloadVersion(document.document_uuid, version, document.title)
        }
        onCompare={() => setComparisonOpen(true)}
      />

      {/* Version Detail View - shown when a version is selected, loading, or errored */}
      {(selectedVersion || isVersionLoading || versionError) && (
        <VersionDetailView
          version={selectedVersion}
          isLoading={isVersionLoading}
          error={versionError}
          onRetry={() => {
            if (selectedVersion) {
              fetchVersion(
                document.document_uuid,
                selectedVersion.major_version,
                selectedVersion.minor_version
              );
            }
          }}
          onDownload={(version) =>
            downloadVersion(document.document_uuid, version, document.title)
          }
          onClose={clearSelectedVersion}
        />
      )}

      {/* Version Comparison View - portal dialog */}
      <VersionComparisonView
        open={comparisonOpen}
        onOpenChange={setComparisonOpen}
        versions={document.versions}
      />
    </div>
  );
}
