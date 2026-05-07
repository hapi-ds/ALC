import { Download, Loader2 } from "lucide-react";
import type { DocumentVersion } from "@/types/document";
import {
  sortVersionsDescending,
  isCurrentVersion,
  truncateText,
} from "@/lib/versionUtils";
import { VersionStatusBadge } from "./VersionStatusBadge";
import { useDocumentStore } from "@/stores/documentStore";
import { Button } from "@/components/ui/button";

interface VersionHistoryPanelProps {
  versions: DocumentVersion[];
  documentTitle: string;
  onSelectVersion: (version: DocumentVersion) => void;
  onDownload: (version: DocumentVersion) => void;
  onCompare: () => void;
}

export function VersionHistoryPanel({
  versions,
  documentTitle,
  onSelectVersion,
  onDownload,
  onCompare,
}: VersionHistoryPanelProps) {
  const downloadingVersionId = useDocumentStore(
    (state) => state.downloadingVersionId
  );

  const sortedVersions = sortVersionsDescending(versions);

  if (versions.length === 0) {
    return (
      <div className="rounded-lg border p-6">
        <h3 className="text-lg font-semibold mb-4">Version History</h3>
        <p className="text-muted-foreground text-sm">
          No versions available for this document.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">
          Version History — {documentTitle}
        </h3>
        <Button
          variant="outline"
          size="sm"
          onClick={onCompare}
          disabled={versions.length < 2}
        >
          Compare Versions
        </Button>
      </div>

      <div className="relative ml-3">
        {/* Vertical timeline line */}
        <div className="absolute left-0 top-0 bottom-0 w-px bg-border" />

        <div className="space-y-4">
          {sortedVersions.map((version) => {
            const isCurrent = isCurrentVersion(version, versions);
            const isDownloading = downloadingVersionId === version.id;

            return (
              <div key={version.id} className="relative pl-6">
                {/* Timeline dot */}
                <div
                  className={`absolute left-0 top-2 -translate-x-1/2 h-3 w-3 rounded-full border-2 ${
                    isCurrent
                      ? "bg-primary border-primary"
                      : "bg-background border-muted-foreground"
                  }`}
                />

                <button
                  type="button"
                  className="w-full text-left rounded-md border p-3 hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => onSelectVersion(version)}
                  aria-label={`Version ${version.major_version}.${version.minor_version}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">
                        v{version.major_version}.{version.minor_version}
                      </span>
                      <VersionStatusBadge isCurrent={isCurrent} />
                    </div>

                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDownload(version);
                      }}
                      disabled={isDownloading}
                      aria-label={`Download version ${version.major_version}.${version.minor_version}`}
                    >
                      {isDownloading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </Button>
                  </div>

                  <div className="mt-1 text-xs text-muted-foreground space-y-0.5">
                    <p>
                      {new Date(version.uploaded_at).toLocaleString()} — User #
                      {version.uploaded_by}
                    </p>
                    <p>
                      {version.change_reason
                        ? truncateText(version.change_reason, 120)
                        : "No reason provided"}
                    </p>
                    <p className="font-mono">
                      {truncateText(version.file_hash, 12)}
                    </p>
                  </div>
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
