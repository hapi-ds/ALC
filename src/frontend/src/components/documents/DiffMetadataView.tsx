import { FileCheck, Clock, User } from "lucide-react";

import type { DocumentVersion } from "@/types/document";
import { computeVersionDiff, formatTimeDelta } from "@/lib/versionUtils";

interface DiffMetadataViewProps {
  left: DocumentVersion;
  right: DocumentVersion;
}

export function DiffMetadataView({ left, right }: DiffMetadataViewProps) {
  const diff = computeVersionDiff(left, right);
  const timeDeltaStr = formatTimeDelta(diff.timeDelta);

  const changedBg = "bg-amber-50 dark:bg-amber-950/20";

  return (
    <div className="space-y-3" role="region" aria-label="Version differences summary">
      {/* File hash comparison */}
      <div
        className={`flex items-start gap-3 rounded-md p-3 ${diff.hashChanged ? changedBg : ""}`}
      >
        <FileCheck
          className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
          aria-hidden="true"
        />
        <div>
          <p className="text-sm font-medium">File Content</p>
          {diff.hashChanged ? (
            <p className="text-xs text-muted-foreground">
              File hash changed between versions
            </p>
          ) : (
            <p className="text-xs text-green-700 dark:text-green-400">
              File content unchanged
            </p>
          )}
        </div>
      </div>

      {/* Time elapsed */}
      <div className="flex items-start gap-3 rounded-md p-3">
        <Clock
          className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
          aria-hidden="true"
        />
        <div>
          <p className="text-sm font-medium">Time Between Uploads</p>
          <p className="text-xs text-muted-foreground">{timeDeltaStr}</p>
        </div>
      </div>

      {/* Uploader comparison */}
      <div
        className={`flex items-start gap-3 rounded-md p-3 ${diff.uploaderChanged ? changedBg : ""}`}
      >
        <User
          className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0"
          aria-hidden="true"
        />
        <div>
          <p className="text-sm font-medium">Uploader</p>
          {diff.uploaderChanged ? (
            <p className="text-xs text-muted-foreground">
              Uploader changed (User {left.uploaded_by} → User {right.uploaded_by})
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">
              Same uploader (User {left.uploaded_by})
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
