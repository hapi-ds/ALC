import { useEffect } from "react";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { TemplateVersionResponse } from "../../types/template";
import { Button } from "../ui/button";

interface VersionHistoryPanelProps {
  /** The document UUID of the template to display version history for */
  documentUuid: string;
  /** Whether the template is in ReadOnly status (enables "Create New Version" button) */
  isReadOnly?: boolean;
  /** Callback when user clicks "Create New Version" */
  onCreateNewVersion?: () => void;
  /** Callback when user selects a version to view */
  onVersionSelect?: (version: TemplateVersionResponse) => void;
}

/**
 * VersionHistoryPanel displays the version history for a template.
 *
 * Shown on the template detail page (route: /templates/:uuid).
 * Lists all versions in descending order (newest first) with version number badge,
 * creation timestamp, creator name, and active indicator.
 *
 * Clicking a version loads its schema into a read-only canvas view.
 * A "Create New Version" button is shown at the top for ReadOnly templates.
 */
export function VersionHistoryPanel({
  documentUuid,
  isReadOnly = false,
  onCreateNewVersion,
  onVersionSelect,
}: VersionHistoryPanelProps) {
  const versions = useTemplateBuilderStore((s) => s.versions);
  const activeVersion = useTemplateBuilderStore((s) => s.activeVersion);
  const versionError = useTemplateBuilderStore((s) => s.versionError);
  const fetchVersionHistory = useTemplateBuilderStore((s) => s.fetchVersionHistory);
  const loadVersionIntoCanvas = useTemplateBuilderStore((s) => s.loadVersionIntoCanvas);

  // Fetch version history on mount or when documentUuid changes
  useEffect(() => {
    if (documentUuid) {
      fetchVersionHistory(documentUuid);
    }
  }, [documentUuid, fetchVersionHistory]);

  const handleVersionClick = (version: TemplateVersionResponse) => {
    loadVersionIntoCanvas(version);
    onVersionSelect?.(version);
  };

  return (
    <div className="flex flex-col gap-3 p-4" aria-label="Version History">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-700">Version History</h2>
        {isReadOnly && (
          <Button
            type="button"
            size="sm"
            onClick={onCreateNewVersion}
            aria-label="Create New Version"
          >
            Create New Version
          </Button>
        )}
      </div>

      {/* Error state */}
      {versionError && (
        <div
          role="alert"
          className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          {versionError}
        </div>
      )}

      {/* Empty state */}
      {!versionError && versions.length === 0 && (
        <p className="text-sm text-gray-500">No versions available.</p>
      )}

      {/* Version list */}
      {versions.length > 0 && (
        <ul className="flex flex-col gap-2" role="list" aria-label="Template versions">
          {versions.map((version) => (
            <VersionEntry
              key={version.id}
              version={version}
              isSelected={activeVersion?.id === version.id}
              onClick={() => handleVersionClick(version)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// VersionEntry sub-component
// ---------------------------------------------------------------------------

interface VersionEntryProps {
  version: TemplateVersionResponse;
  isSelected: boolean;
  onClick: () => void;
}

function VersionEntry({ version, isSelected, onClick }: VersionEntryProps) {
  const formattedDate = formatTimestamp(version.created_at);
  const creatorName = `User ${version.created_by}`;

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        aria-current={isSelected ? "true" : undefined}
        className={`w-full rounded-md border px-3 py-2 text-left transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
          isSelected
            ? "border-blue-300 bg-blue-50"
            : "border-gray-200 bg-white"
        }`}
      >
        <div className="flex items-center gap-2">
          {/* Version number badge */}
          <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-700">
            v{version.version_number}
          </span>

          {/* Active indicator badge */}
          {version.is_active && (
            <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
              Active
            </span>
          )}
        </div>

        {/* Metadata row */}
        <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
          <span>{formattedDate}</span>
          <span aria-hidden="true">·</span>
          <span>{creatorName}</span>
        </div>
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Formats an ISO 8601 timestamp into a human-readable date/time string.
 */
function formatTimestamp(isoString: string): string {
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) {
      return isoString;
    }
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}
