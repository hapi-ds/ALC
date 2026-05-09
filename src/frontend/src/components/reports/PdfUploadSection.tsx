import { useState, useRef, useCallback } from "react";
import { FileUp, Loader2, AlertCircle, File as FileIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB

export interface PdfUploadSectionProps {
  onUpload: (file: File) => void;
  isUploading: boolean;
  uploadError?: string | null;
}

/**
 * Formats a file size in bytes to a human-readable string (KB or MB).
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * PDF upload section for the Report Data Entry page.
 *
 * Accepts only .pdf files up to 20MB. Shows file preview with name/size
 * after selection, a "Change File" option, upload confirmation button,
 * progress indicator during upload, and error display.
 */
export function PdfUploadSection({
  onUpload,
  isUploading,
  uploadError,
}: PdfUploadSectionProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sizeError, setSizeError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0] ?? null;
      // Reset input value so the same file can be re-selected
      event.target.value = "";

      if (!file) {
        return;
      }

      if (file.size > MAX_FILE_SIZE_BYTES) {
        setSizeError(
          `File exceeds the maximum allowed size of 20 MB. Selected file is ${formatFileSize(file.size)}.`
        );
        setSelectedFile(null);
        return;
      }

      setSizeError(null);
      setSelectedFile(file);
    },
    []
  );

  const handleChangeFile = useCallback(() => {
    setSizeError(null);
    setSelectedFile(null);
    fileInputRef.current?.click();
  }, []);

  const handleSelectFile = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleUploadConfirm = useCallback(() => {
    if (selectedFile) {
      onUpload(selectedFile);
    }
  }, [selectedFile, onUpload]);

  return (
    <section aria-labelledby="pdf-upload-heading" className="space-y-4">
      <h3
        id="pdf-upload-heading"
        className="text-base font-semibold text-foreground"
      >
        Upload Completed PDF
      </h3>

      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,.pdf"
        onChange={handleFileChange}
        className="sr-only"
        aria-label="Select PDF file for upload"
        tabIndex={-1}
      />

      {/* File selection area */}
      {!selectedFile ? (
        <div className="border-2 border-dashed border-border rounded-lg p-6 text-center">
          <FileUp
            className="h-8 w-8 mx-auto mb-2 text-muted-foreground"
            aria-hidden="true"
          />
          <p className="text-sm font-medium text-foreground">
            Select a PDF file to upload
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Only .pdf files up to 20 MB are accepted
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={handleSelectFile}
            disabled={isUploading}
          >
            Select File
          </Button>
        </div>
      ) : (
        /* File preview */
        <div className="rounded-lg border border-border bg-muted/30 p-4">
          <div className="flex items-center gap-3">
            <FileIcon
              className="h-8 w-8 text-primary shrink-0"
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground truncate">
                {selectedFile.name}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatFileSize(selectedFile.size)}
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleChangeFile}
              disabled={isUploading}
            >
              Change File
            </Button>
          </div>

          {/* Upload confirmation button */}
          <div className="mt-4">
            <Button
              type="button"
              onClick={handleUploadConfirm}
              disabled={isUploading}
              className="w-full"
            >
              {isUploading ? (
                <>
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                  Uploading…
                </>
              ) : (
                "Upload PDF"
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Progress indicator (shown during upload) */}
      {isUploading && (
        <div
          className="flex items-center gap-2 text-sm text-muted-foreground"
          role="status"
          aria-live="polite"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span>Uploading and extracting data from PDF…</span>
        </div>
      )}

      {/* Size validation error */}
      {sizeError && (
        <div
          className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          aria-live="polite"
        >
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>{sizeError}</span>
        </div>
      )}

      {/* Upload error from parent */}
      {uploadError && !sizeError && (
        <div
          className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
          aria-live="polite"
        >
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>{uploadError}</span>
        </div>
      )}
    </section>
  );
}
