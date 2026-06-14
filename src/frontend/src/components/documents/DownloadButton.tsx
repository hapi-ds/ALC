/**
 * DownloadButton component.
 *
 * Triggers a file download for a specific document version. Supports both
 * an icon-only variant (for compact surfaces like search results) and a
 * full button variant with text label.
 *
 * Requirements: 4.1, 4.3, 4.4
 */

import { useState, useCallback } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/apiClient";
import { triggerBrowserDownload } from "@/lib/fileDownload";

export interface DownloadButtonProps {
  /** UUID of the document to download */
  documentUuid: string;
  /** Specific version to download. When omitted, downloads the latest version. */
  version?: { major_version: number; minor_version: number };
  /** Document title used as the suggested filename in the save dialog */
  documentTitle: string;
  /** Render style: "icon" for a compact icon button, "button" for a full labeled button */
  variant?: "icon" | "button";
}

/**
 * Builds the download endpoint URL for a given document version.
 */
function buildDownloadUrl(
  documentUuid: string,
  version: { major_version: number; minor_version: number },
): string {
  return `/api/documents/${documentUuid}/versions/${version.major_version}/${version.minor_version}/download`;
}

export function DownloadButton({
  documentUuid,
  version,
  documentTitle,
  variant = "button",
}: DownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = useCallback(async () => {
    if (!version) {
      toast.error("Download unavailable", {
        description: "No version information available for this document.",
      });
      return;
    }

    setIsDownloading(true);
    try {
      const url = buildDownloadUrl(documentUuid, version);
      const blob = await apiClient.download(url);
      triggerBrowserDownload(blob, documentTitle);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "An unexpected error occurred.";
      toast.error("Download failed", { description: message });
    } finally {
      setIsDownloading(false);
    }
  }, [documentUuid, version, documentTitle]);

  if (variant === "icon") {
    return (
      <Button
        variant="ghost"
        size="icon"
        disabled={isDownloading}
        onClick={() => void handleDownload()}
        aria-label={isDownloading ? "Downloading…" : `Download ${documentTitle}`}
      >
        {isDownloading ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Download className="h-4 w-4" aria-hidden="true" />
        )}
      </Button>
    );
  }

  return (
    <Button
      variant="outline"
      size="default"
      disabled={isDownloading}
      onClick={() => void handleDownload()}
      aria-label={isDownloading ? "Downloading…" : `Download ${documentTitle}`}
    >
      {isDownloading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      ) : (
        <Download className="h-4 w-4" aria-hidden="true" />
      )}
      {isDownloading ? "Downloading…" : "Download"}
    </Button>
  );
}
