import { useState } from "react";
import { Copy, Check, Download, Loader2, X, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentVersion } from "@/types/document";

interface VersionDetailViewProps {
  version: DocumentVersion | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  onDownload: (version: DocumentVersion) => void;
  onClose: () => void;
}

export function VersionDetailView({
  version,
  isLoading,
  error,
  onRetry,
  onDownload,
  onClose,
}: VersionDetailViewProps) {
  const [copied, setCopied] = useState(false);

  const handleCopyHash = async () => {
    if (!version) return;
    try {
      await navigator.clipboard.writeText(version.file_hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      // Gracefully degrade — no confirmation shown, no crash
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-6" aria-label="Loading version details">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="ml-2 text-sm text-muted-foreground">Loading version details…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 p-6" aria-label="Version error">
        <p className="text-sm text-destructive">{error}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Retry
        </Button>
      </div>
    );
  }

  if (!version) {
    return null;
  }

  return (
    <div className="rounded-lg border p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">
          Version {version.major_version}.{version.minor_version}
        </h3>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close version detail">
          <X className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>

      <dl className="grid gap-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Version Number</dt>
          <dd className="font-medium">
            {version.major_version}.{version.minor_version}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground">Storage Key</dt>
          <dd className="font-medium break-all">{version.storage_key}</dd>
        </div>

        <div>
          <dt className="text-muted-foreground">File Hash</dt>
          <dd className="flex items-center gap-2">
            <code className="font-mono text-xs break-all">{version.file_hash}</code>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0"
              onClick={handleCopyHash}
              aria-label={copied ? "Copied" : "Copy file hash"}
            >
              {copied ? (
                <Check className="h-3 w-3 text-green-600" aria-hidden="true" />
              ) : (
                <Copy className="h-3 w-3" aria-hidden="true" />
              )}
            </Button>
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground">Uploaded By</dt>
          <dd className="font-medium">{version.uploaded_by}</dd>
        </div>

        <div>
          <dt className="text-muted-foreground">Uploaded At</dt>
          <dd className="font-medium">
            {new Date(version.uploaded_at).toLocaleString()}
          </dd>
        </div>

        <div>
          <dt className="text-muted-foreground">Change Reason</dt>
          <dd className="font-medium">
            {version.change_reason ?? (
              <span className="italic text-muted-foreground">No reason provided</span>
            )}
          </dd>
        </div>
      </dl>

      <div className="pt-2">
        <Button variant="outline" size="sm" onClick={() => onDownload(version)}>
          <Download className="h-4 w-4" aria-hidden="true" />
          Download
        </Button>
      </div>
    </div>
  );
}
