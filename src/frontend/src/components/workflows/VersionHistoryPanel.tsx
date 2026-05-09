import { useEffect, useCallback } from 'react';
import { RotateCcw, Loader2, AlertCircle } from 'lucide-react';
import { useWorkflowStore, type WorkflowVersionSummary } from '@/stores/workflowStore';
import { Button } from '@/components/ui/button';

/**
 * VersionHistoryPanel component for the Workflow Editor.
 *
 * Displays a list of versions with version number, timestamp, author, and change reason.
 * Shows loading indicator while fetching and error state with retry button.
 * Clicking a version loads it into BpmnEditor in read-only preview mode.
 * "Restore" button on historical versions calls store's restoreVersion.
 *
 * Requirements: 8.3, 8.4, 8.5, 8.8, 8.9
 */

interface VersionHistoryPanelProps {
  /** The workflow ID to fetch version history for */
  workflowId: number;
  /** Callback when a version is selected for preview */
  onVersionSelect?: (versionNumber: number) => void;
}

export function VersionHistoryPanel({ workflowId, onVersionSelect }: VersionHistoryPanelProps) {
  const versions = useWorkflowStore((s) => s.versions);
  const selectedVersion = useWorkflowStore((s) => s.selectedVersion);
  const isLoadingVersions = useWorkflowStore((s) => s.isLoadingVersions);
  const versionsError = useWorkflowStore((s) => s.versionsError);
  const currentWorkflow = useWorkflowStore((s) => s.currentWorkflow);
  const fetchVersionHistory = useWorkflowStore((s) => s.fetchVersionHistory);
  const fetchVersion = useWorkflowStore((s) => s.fetchVersion);
  const restoreVersion = useWorkflowStore((s) => s.restoreVersion);

  // Fetch version history on mount or when workflowId changes
  useEffect(() => {
    if (workflowId) {
      fetchVersionHistory(workflowId);
    }
  }, [workflowId, fetchVersionHistory]);

  const handleRetry = useCallback(() => {
    fetchVersionHistory(workflowId);
  }, [workflowId, fetchVersionHistory]);

  const handleVersionClick = useCallback(
    (version: WorkflowVersionSummary) => {
      fetchVersion(workflowId, version.version_number);
      onVersionSelect?.(version.version_number);
    },
    [workflowId, fetchVersion, onVersionSelect]
  );

  const handleRestore = useCallback(() => {
    if (selectedVersion) {
      restoreVersion(selectedVersion);
    }
  }, [selectedVersion, restoreVersion]);

  const currentVersionNumber = currentWorkflow?.current_version_number;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4" aria-label="Version History">
      {/* Header */}
      <h4 className="text-sm font-semibold text-gray-700">Version History</h4>

      {/* Loading state */}
      {isLoadingVersions && (
        <div className="flex items-center justify-center py-6" role="status" aria-label="Loading version history">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" aria-hidden="true" />
          <span className="ml-2 text-sm text-gray-500">Loading versions...</span>
        </div>
      )}

      {/* Error state */}
      {versionsError && !isLoadingVersions && (
        <div className="flex flex-col items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-4" role="alert">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-red-500" aria-hidden="true" />
            <p className="text-sm text-red-700">{versionsError}</p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRetry}
            aria-label="Retry loading version history"
          >
            Retry
          </Button>
        </div>
      )}

      {/* Empty state */}
      {!isLoadingVersions && !versionsError && versions.length === 0 && (
        <p className="text-sm text-gray-500 py-2">No version history available.</p>
      )}

      {/* Restore button for selected historical version */}
      {selectedVersion && selectedVersion.version_number !== currentVersionNumber && (
        <div className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-3 py-2">
          <p className="flex-1 text-xs text-blue-700">
            Previewing version {selectedVersion.version_number}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleRestore}
            aria-label={`Restore version ${selectedVersion.version_number}`}
          >
            <RotateCcw className="h-3 w-3" aria-hidden="true" />
            Restore
          </Button>
        </div>
      )}

      {/* Version list */}
      {!isLoadingVersions && !versionsError && versions.length > 0 && (
        <ul className="flex flex-col gap-2" role="list" aria-label="Workflow versions">
          {versions.map((version) => (
            <VersionEntry
              key={version.version_number}
              version={version}
              isCurrent={version.version_number === currentVersionNumber}
              isSelected={selectedVersion?.version_number === version.version_number}
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
  version: WorkflowVersionSummary;
  isCurrent: boolean;
  isSelected: boolean;
  onClick: () => void;
}

function VersionEntry({ version, isCurrent, isSelected, onClick }: VersionEntryProps) {
  const formattedDate = formatTimestamp(version.created_at);

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        aria-current={isSelected ? 'true' : undefined}
        className={`w-full rounded-md border px-3 py-2 text-left transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 ${
          isSelected
            ? 'border-blue-300 bg-blue-50'
            : 'border-gray-200 bg-white'
        }`}
      >
        <div className="flex items-center gap-2">
          {/* Version number badge */}
          <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-gray-700">
            v{version.version_number}
          </span>

          {/* Current version indicator */}
          {isCurrent && (
            <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
              Current
            </span>
          )}
        </div>

        {/* Change reason */}
        {version.change_reason && (
          <p className="mt-1 text-xs text-gray-600 truncate">
            {version.change_reason}
          </p>
        )}

        {/* Metadata row */}
        <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
          <span>{formattedDate}</span>
          <span aria-hidden="true">·</span>
          <span>User {version.created_by}</span>
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
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoString;
  }
}
