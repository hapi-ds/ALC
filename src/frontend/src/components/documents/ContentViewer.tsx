import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Download, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/apiClient";
import { triggerBrowserDownload } from "@/lib/fileDownload";
import { renderMarkdown } from "@/lib/renderMarkdown";

interface ContentViewerProps {
  documentUuid: string;
  majorVersion: number;
  minorVersion: number;
  contentType: string;
}

/** Timeout in milliseconds for content fetches. */
const FETCH_TIMEOUT_MS = 30_000;

/**
 * Builds the content endpoint URL for a given document version.
 */
function buildContentUrl(
  documentUuid: string,
  majorVersion: number,
  minorVersion: number
): string {
  return `/api/documents/${documentUuid}/versions/${majorVersion}/${minorVersion}/content`;
}

/**
 * Builds the download endpoint URL for a given document version.
 */
function buildDownloadUrl(
  documentUuid: string,
  majorVersion: number,
  minorVersion: number
): string {
  return `/api/documents/${documentUuid}/versions/${majorVersion}/${minorVersion}/download`;
}

/**
 * ContentViewer renders document content inline based on content type.
 *
 * - PDF: renders via an `<iframe>` pointing to the content endpoint
 * - Markdown: fetches raw content and renders as HTML
 * - Unsupported: shows an informational message with a download fallback button
 */
export function ContentViewer({
  documentUuid,
  majorVersion,
  minorVersion,
  contentType,
}: ContentViewerProps) {
  const isPdf = contentType === "application/pdf";
  const isMarkdown =
    contentType === "text/markdown" || contentType === "text/x-markdown";

  // For markdown: loading state, error state, and rendered HTML
  const [markdownHtml, setMarkdownHtml] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // AbortController ref for cleanup and timeout
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchMarkdown = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setMarkdownHtml("");

    // Cancel any previous in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const url = buildContentUrl(documentUuid, majorVersion, minorVersion);

      // Race between the actual download and a timeout
      const timeoutPromise = new Promise<never>((_, reject) => {
        const id = setTimeout(() => {
          controller.abort();
          reject(new Error("Request timed out. Please try again."));
        }, FETCH_TIMEOUT_MS);
        // Allow GC if the controller is aborted externally
        controller.signal.addEventListener("abort", () => clearTimeout(id));
      });

      const blob = await Promise.race([
        apiClient.download(url),
        timeoutPromise,
      ]);

      // If the component unmounted or version changed, bail out
      if (controller.signal.aborted) return;

      const text = await blob.text();
      const html = renderMarkdown(text);
      setMarkdownHtml(html);
    } catch (err: unknown) {
      // Don't update state if we were aborted due to cleanup
      if (controller.signal.aborted && !(err instanceof Error && err.message.includes("timed out"))) {
        return;
      }
      if (err instanceof Error) {
        setError(err.message || "Failed to load content.");
      } else {
        setError("Failed to load content.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [documentUuid, majorVersion, minorVersion]);

  // Fetch markdown content on mount and when version changes
  useEffect(() => {
    if (isMarkdown) {
      fetchMarkdown();
    }

    return () => {
      // Cleanup: abort in-flight request on unmount or version change
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [isMarkdown, fetchMarkdown]);

  const handleDownload = async () => {
    try {
      const url = buildDownloadUrl(documentUuid, majorVersion, minorVersion);
      const blob = await apiClient.download(url);
      triggerBrowserDownload(blob, `document-${documentUuid}.${getExtension(contentType)}`);
    } catch {
      // Silently fail — the DownloadButton component handles toast on error
    }
  };

  // --- PDF Rendering ---
  if (isPdf) {
    const contentUrl = buildContentUrl(documentUuid, majorVersion, minorVersion);
    return (
      <div
        className="border border-border rounded-md overflow-hidden"
        data-testid="content-viewer-pdf"
      >
        <iframe
          src={contentUrl}
          className="w-full h-[600px]"
          title="PDF document preview"
          aria-label="PDF document preview"
        />
      </div>
    );
  }

  // --- Markdown Rendering ---
  if (isMarkdown) {
    if (isLoading) {
      return (
        <div
          className="flex items-center justify-center p-6 border border-border rounded-md"
          role="status"
          aria-label="Loading document content"
          data-testid="content-viewer-loading"
        >
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="ml-2 text-sm text-muted-foreground">Loading content…</span>
        </div>
      );
    }

    if (error) {
      return (
        <div
          className="flex flex-col items-center gap-3 p-6 border border-border rounded-md"
          role="alert"
          aria-label="Content loading error"
          data-testid="content-viewer-error"
        >
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <p className="text-sm">{error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchMarkdown}>
            <RefreshCw className="h-4 w-4 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      );
    }

    return (
      <div
        className="border border-border rounded-md p-4 prose prose-sm dark:prose-invert max-w-none"
        data-testid="content-viewer-markdown"
        dangerouslySetInnerHTML={{ __html: markdownHtml }}
      />
    );
  }

  // --- Unsupported Types ---
  return (
    <div
      className="flex flex-col items-center gap-4 p-6 border border-border rounded-md"
      data-testid="content-viewer-unsupported"
    >
      <div className="text-center space-y-1">
        <p className="text-sm text-muted-foreground">
          This file format cannot be previewed.
        </p>
        <p className="text-xs text-muted-foreground">
          Content type: <code className="bg-muted px-1 rounded">{contentType}</code>
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={handleDownload}>
        <Download className="h-4 w-4 mr-1" aria-hidden="true" />
        Download File
      </Button>
    </div>
  );
}

/**
 * Returns a file extension for common content types.
 */
function getExtension(contentType: string): string {
  const map: Record<string, string> = {
    "application/pdf": "pdf",
    "text/markdown": "md",
    "text/x-markdown": "md",
    "text/plain": "txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "image/png": "png",
    "image/jpeg": "jpg",
  };
  return map[contentType] ?? "bin";
}
