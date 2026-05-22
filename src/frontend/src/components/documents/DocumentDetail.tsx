import { useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowLeft, Plus, Tag } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentResponse } from "@/types/document";
import { useDocumentStore } from "@/stores/documentStore";
import { useWorkflowStore } from "@/stores/workflowStore";
import { useWorkflowExecutionStore } from "@/stores/workflowExecutionStore";
import { VersionHistoryPanel } from "./VersionHistoryPanel";
import { VersionDetailView } from "./VersionDetailView";
import { VersionComparisonView } from "./VersionComparisonView";
import { WorkflowStatePanel } from "./WorkflowStatePanel";
import { WorkflowHistoryTimeline } from "./WorkflowHistoryTimeline";

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

  // Workflow definition store — used to check if document has a matching active workflow
  const workflows = useWorkflowStore((state) => state.workflows);
  const fetchWorkflowList = useWorkflowStore((state) => state.fetchWorkflowList);

  // Workflow execution store — for reading the new state after transition
  const lastTransitionResult = useWorkflowExecutionStore(
    (s) => s.lastTransitionResult
  );

  // URL query params for ?tab=workflow
  const [searchParams] = useSearchParams();
  const isWorkflowTab = searchParams.get("tab") === "workflow";

  // Ref for scrolling WorkflowStatePanel into view
  const workflowPanelRef = useRef<HTMLDivElement>(null);

  // Fetch workflow definitions on mount to determine if document has a matching workflow
  useEffect(() => {
    if (workflows.length === 0) {
      fetchWorkflowList();
    }
  }, [workflows.length, fetchWorkflowList]);

  // Determine if the document has a tag matching an active workflow definition's document_tag
  const hasMatchingWorkflow = useMemo(() => {
    if (!document.tags || document.tags.length === 0) return false;
    const documentTagStrings = document.tags.map((t) => t.tag);
    return workflows.some(
      (w) => w.is_active && documentTagStrings.includes(w.document_tag)
    );
  }, [document.tags, workflows]);

  // Handle ?tab=workflow: scroll WorkflowStatePanel into view within 500ms
  useEffect(() => {
    if (isWorkflowTab && hasMatchingWorkflow && workflowPanelRef.current) {
      const timer = setTimeout(() => {
        workflowPanelRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [isWorkflowTab, hasMatchingWorkflow]);

  // Derive the displayed current_status — update after successful transition
  const displayStatus = lastTransitionResult?.success
    ? lastTransitionResult.new_state
    : document.current_status;

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
                {displayStatus}
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

      {/* Workflow State Panel — rendered when document has a matching active workflow */}
      {hasMatchingWorkflow && document.document_uuid && (
        <div ref={workflowPanelRef}>
          <WorkflowStatePanel
            documentUuid={document.document_uuid}
            defaultExpanded={isWorkflowTab ? true : undefined}
          />
        </div>
      )}

      {/* Workflow History Timeline — rendered when document has a matching active workflow */}
      {hasMatchingWorkflow && document.document_uuid && (
        <WorkflowHistoryTimeline
          documentUuid={document.document_uuid}
          defaultExpanded={isWorkflowTab}
        />
      )}

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
