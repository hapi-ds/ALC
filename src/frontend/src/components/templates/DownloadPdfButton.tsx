import { Download, Loader2, AlertCircle } from "lucide-react";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import { Button } from "../ui/button";

interface DownloadPdfButtonProps {
  /** The document UUID of the template to download */
  documentUuid: string;
}

/**
 * DownloadPdfButton triggers a PDF download for a template via the store's
 * downloadPdf action.
 *
 * The store action sends POST /api/templates/{document_uuid}/download-pdf
 * with X-Change-Reason header. On success it creates a blob URL and triggers
 * a file download using the filename from Content-Disposition.
 *
 * This component shows a loading spinner and disables the button while the
 * request is in flight. On error, displays an inline error message that maps
 * HTTP status codes to user-friendly text:
 *   404 → "Template not found"
 *   400 → "Not downloadable"
 *   network → "Download failed"
 *
 * Re-enables the button on error so the user can retry.
 */
export function DownloadPdfButton({ documentUuid }: DownloadPdfButtonProps) {
  const isDownloading = useTemplateBuilderStore((s) => s.isDownloading);
  const downloadError = useTemplateBuilderStore((s) => s.downloadError);
  const downloadPdf = useTemplateBuilderStore((s) => s.downloadPdf);

  const handleClick = () => {
    downloadPdf(documentUuid);
  };

  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        type="button"
        variant="outline"
        onClick={handleClick}
        disabled={isDownloading}
        aria-busy={isDownloading}
        aria-label="Download PDF"
        className="min-w-[140px]"
      >
        {isDownloading ? (
          <span className="inline-flex items-center gap-2">
            <Loader2
              className="h-4 w-4 animate-spin"
              aria-hidden="true"
            />
            Downloading…
          </span>
        ) : (
          <span className="inline-flex items-center gap-2">
            <Download className="h-4 w-4" aria-hidden="true" />
            Download PDF
          </span>
        )}
      </Button>

      {/* Error message */}
      {downloadError && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-center gap-1.5 text-sm text-destructive"
        >
          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{downloadError}</span>
        </div>
      )}
    </div>
  );
}
