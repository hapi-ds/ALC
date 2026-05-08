import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Loader2, AlertCircle, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTemplateBuilderStore } from "@/stores/templateBuilderStore";
import { VersionHistoryPanel } from "@/components/templates/VersionHistoryPanel";
import { DownloadPdfButton } from "@/components/templates/DownloadPdfButton";
import { ChangeReasonDialog } from "@/components/templates/ChangeReasonDialog";
import { apiClient } from "@/lib/apiClient";
import type {
  TemplateResponse,
  TemplateVersionResponse,
  CanvasItem,
  CanvasContentBlockElement,
  CanvasFieldElement,
} from "@/types/template";

/**
 * Template detail page at route `/templates/:uuid`.
 *
 * Displays the active version of a template with:
 * - Template name, document UUID, and active version info
 * - Read-only canvas view of the active version's schema
 * - VersionHistoryPanel on the side for browsing version history
 * - DownloadPdfButton for the active version
 * - "Create New Version" button that loads the active version into the builder
 */
export function TemplateDetailPage() {
  const { uuid } = useParams<{ uuid: string }>();
  const navigate = useNavigate();

  const [template, setTemplate] = useState<TemplateResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showChangeReasonDialog, setShowChangeReasonDialog] = useState(false);

  // Store state for version viewing
  const items = useTemplateBuilderStore((s) => s.items);
  const activeVersion = useTemplateBuilderStore((s) => s.activeVersion);
  const versions = useTemplateBuilderStore((s) => s.versions);
  const loadVersionIntoCanvas = useTemplateBuilderStore(
    (s) => s.loadVersionIntoCanvas
  );
  const resetBuilder = useTemplateBuilderStore((s) => s.resetBuilder);

  // Fetch template data on mount
  useEffect(() => {
    if (!uuid) return;

    const fetchTemplate = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await apiClient.get<TemplateResponse>(
          `/api/templates/${uuid}`
        );
        setTemplate(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load template"
        );
      } finally {
        setIsLoading(false);
      }
    };

    fetchTemplate();
  }, [uuid]);

  // Load active version into canvas when versions are fetched
  useEffect(() => {
    if (versions.length > 0 && !activeVersion) {
      const active = versions.find((v) => v.is_active);
      if (active) {
        loadVersionIntoCanvas(active);
      }
    }
  }, [versions, activeVersion, loadVersionIntoCanvas]);

  // Clean up store on unmount
  useEffect(() => {
    return () => {
      resetBuilder();
    };
  }, [resetBuilder]);

  const handleCreateNewVersion = useCallback(() => {
    setShowChangeReasonDialog(true);
  }, []);

  const handleChangeReasonSubmit = useCallback(
    (reason: string) => {
      setShowChangeReasonDialog(false);
      // Load the active version into the builder for editing and navigate
      if (activeVersion) {
        loadVersionIntoCanvas(activeVersion);
      }
      // Navigate to the builder page with state indicating version creation
      navigate("/templates/new", {
        state: {
          fromVersion: activeVersion,
          templateUuid: uuid,
          changeReason: reason,
        },
      });
    },
    [activeVersion, loadVersionIntoCanvas, navigate, uuid]
  );

  const handleVersionSelect = useCallback(
    (_version: TemplateVersionResponse) => {
      // Version is loaded into canvas by VersionHistoryPanel via store
    },
    []
  );

  if (!uuid) {
    return (
      <div className="p-6 text-center text-muted-foreground">
        No template UUID provided.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center py-12"
        aria-label="Loading template"
      >
        <Loader2
          className="h-6 w-6 animate-spin text-muted-foreground"
          aria-hidden="true"
        />
        <span className="sr-only">Loading template</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-4 p-6">
        <div
          role="alert"
          className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
        <Button variant="outline" onClick={() => navigate("/templates")}>
          <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
          Back to Templates
        </Button>
      </div>
    );
  }

  const isReadOnly = template?.status === "ReadOnly";
  const displayedVersion = activeVersion;
  const versionLabel = displayedVersion
    ? `v${displayedVersion.version_number}`
    : "Draft";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/templates")}
            aria-label="Back to templates"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">
              {template?.name ?? "Template"}
            </h1>
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span className="font-mono">{template?.document_uuid}</span>
              <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                {versionLabel}
              </span>
              {displayedVersion && !displayedVersion.is_active && (
                <span className="inline-flex items-center rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-700">
                  Historical Version
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          {isReadOnly && (
            <Button onClick={handleCreateNewVersion}>
              <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
              Create New Version
            </Button>
          )}
          {uuid && <DownloadPdfButton documentUuid={uuid} />}
        </div>
      </div>

      {/* Main content: Canvas + Version History */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        {/* Read-only canvas view */}
        <div className="lg:col-span-3">
          <div className="rounded-lg border border-border">
            <div className="border-b border-border bg-muted/30 px-4 py-3">
              <h2 className="text-sm font-medium text-muted-foreground">
                Template Schema
                {displayedVersion && (
                  <span className="ml-2 text-xs">
                    (Version {displayedVersion.version_number} —{" "}
                    {displayedVersion.is_active ? "Active" : "Historical"})
                  </span>
                )}
              </h2>
            </div>
            <div className="p-4">
              <ReadOnlyCanvas items={items} />
            </div>
          </div>
        </div>

        {/* Version History Panel */}
        <div className="lg:col-span-1">
          <div className="rounded-lg border border-border">
            <VersionHistoryPanel
              documentUuid={uuid}
              isReadOnly={isReadOnly}
              onCreateNewVersion={handleCreateNewVersion}
              onVersionSelect={handleVersionSelect}
            />
          </div>
        </div>
      </div>

      {/* Change Reason Dialog */}
      <ChangeReasonDialog
        isOpen={showChangeReasonDialog}
        onClose={() => setShowChangeReasonDialog(false)}
        onSubmit={handleChangeReasonSubmit}
        title="Create New Version"
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReadOnlyCanvas — renders canvas items without drag-and-drop or editing
// ---------------------------------------------------------------------------

interface ReadOnlyCanvasProps {
  items: CanvasItem[];
}

function ReadOnlyCanvas({ items }: ReadOnlyCanvasProps) {
  const sortedItems = [...items].sort(
    (a, b) => a.fieldOrder - b.fieldOrder
  );

  if (sortedItems.length === 0) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-sm text-muted-foreground">
        <p>No schema elements to display.</p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-2"
      role="list"
      aria-label="Template schema elements (read-only)"
    >
      {sortedItems.map((item) => (
        <ReadOnlyCanvasItem key={item.id} item={item} />
      ))}
    </div>
  );
}

function ReadOnlyCanvasItem({ item }: { item: CanvasItem }) {
  if (item.element_type === "content_block") {
    return <ReadOnlyContentBlock item={item} />;
  }
  return <ReadOnlyField item={item} />;
}

function ReadOnlyField({ item }: { item: CanvasFieldElement }) {
  return (
    <div
      className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm"
      role="listitem"
    >
      <span className="flex-1 truncate text-foreground">
        {item.label}
        {item.required && (
          <span className="ml-1 text-red-500" aria-label="Required">
            *
          </span>
        )}
      </span>
      <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
        {item.type}
      </span>
      {item.help_text && (
        <span className="text-xs italic text-muted-foreground">
          {item.help_text}
        </span>
      )}
    </div>
  );
}

function ReadOnlyContentBlock({ item }: { item: CanvasContentBlockElement }) {
  return (
    <div
      className="rounded-md border border-border bg-muted/10 px-3 py-2 text-sm"
      role="listitem"
    >
      {renderReadOnlyContent(item)}
    </div>
  );
}

function renderReadOnlyContent(item: CanvasContentBlockElement) {
  switch (item.content_type) {
    case "heading_h1":
      return (
        <span className="text-xl font-bold text-foreground">
          {item.text || "Section Title"}
        </span>
      );
    case "heading_h2":
      return (
        <span className="text-lg font-semibold text-foreground">
          {item.text || "Section Title"}
        </span>
      );
    case "heading_h3":
      return (
        <span className="text-base font-semibold text-foreground">
          {item.text || "Section Title"}
        </span>
      );
    case "paragraph":
      return (
        <span className="text-foreground">
          {item.text || "Enter instructions or description here"}
        </span>
      );
    case "divider":
      return <hr className="border-t border-border" />;
    default:
      return null;
  }
}
