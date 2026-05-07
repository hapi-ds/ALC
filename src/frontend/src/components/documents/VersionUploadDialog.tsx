import { useState, useEffect, useRef, type FormEvent, type DragEvent } from "react";
import { createPortal } from "react-dom";
import { Loader2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentStore } from "@/stores/documentStore";
import { validateFileSize, validateChangeReason, formatFileSize } from "@/lib/versionUtils";

export interface VersionUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentUuid: string;
}

interface FormErrors {
  file?: string;
  version_type?: string;
  change_reason?: string;
}

export function VersionUploadDialog({ open, onOpenChange, documentUuid }: VersionUploadDialogProps) {
  const { createVersion, isLoading } = useDocumentStore();

  const [file, setFile] = useState<File | null>(null);
  const [versionType, setVersionType] = useState<"major" | "minor" | "">("");
  const [changeReason, setChangeReason] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Reset form state when dialog opens
  useEffect(() => {
    if (open) {
      setFile(null);
      setVersionType("");
      setChangeReason("");
      setErrors({});
      setSubmitError(null);
      setIsDragOver(false);
    }
  }, [open]);

  // Focus trap and escape key handling
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onOpenChange(false);
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'input, select, button, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement?.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement?.focus();
          }
        }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  function validate(): FormErrors {
    const newErrors: FormErrors = {};

    if (!file) {
      newErrors.file = "Please select a file to upload.";
    } else {
      const fileSizeResult = validateFileSize(file);
      if (!fileSizeResult.valid) {
        newErrors.file = fileSizeResult.error;
      }
    }

    if (!versionType) {
      newErrors.version_type = "Please select a version type.";
    }

    const reasonResult = validateChangeReason(changeReason);
    if (!reasonResult.valid) {
      newErrors.change_reason = reasonResult.error;
    }

    return newErrors;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    const validationErrors = validate();
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    setSubmitError(null);

    const formData = new FormData();
    formData.append("file", file!);
    formData.append("version_type", versionType);
    formData.append("change_reason", changeReason.trim());

    try {
      await createVersion(documentUuid, formData);
      onOpenChange(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Version upload failed. Please try again.";
      setSubmitError(message);
    }
  }

  function handleFileSelect(selectedFile: File | null) {
    setFile(selectedFile);
    if (selectedFile && errors.file) {
      setErrors((prev) => ({ ...prev, file: undefined }));
    }
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);

    const droppedFile = e.dataTransfer.files[0] ?? null;
    handleFileSelect(droppedFile);
  }

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => { if (e.target === e.currentTarget) onOpenChange(false); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="version-upload-dialog-title"
        className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="version-upload-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Upload New Version
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Submit error */}
        {submitError && (
          <div
            className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
            role="alert"
            aria-live="polite"
          >
            {submitError}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          {/* File picker with drag-and-drop */}
          <div className="mb-4">
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              File <span aria-hidden="true">*</span>
            </label>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                isDragOver
                  ? "border-primary bg-primary/5"
                  : errors.file
                    ? "border-destructive"
                    : "border-border hover:border-primary/50"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              aria-label="Select file to upload"
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="sr-only"
                onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
                tabIndex={-1}
              />
              {file ? (
                <div className="flex items-center justify-center gap-2">
                  <Upload className="h-5 w-5 text-primary" aria-hidden="true" />
                  <span className="text-sm font-medium text-foreground">{file.name}</span>
                  <span className="text-sm text-muted-foreground">({formatFileSize(file.size)})</span>
                </div>
              ) : (
                <>
                  <Upload className="h-6 w-6 mx-auto mb-2 text-muted-foreground" aria-hidden="true" />
                  <p className="text-sm text-muted-foreground">
                    Drag and drop or click to select a file
                  </p>
                </>
              )}
            </div>
            {errors.file && (
              <p className="mt-1 text-sm text-destructive" role="alert">
                {errors.file}
              </p>
            )}
          </div>

          {/* Version Type */}
          <div className="mb-4">
            <label
              htmlFor="version-type"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Version Type <span aria-hidden="true">*</span>
            </label>
            <select
              id="version-type"
              value={versionType}
              onChange={(e) => setVersionType(e.target.value as "major" | "minor" | "")}
              disabled={isLoading}
              aria-invalid={errors.version_type ? "true" : undefined}
              aria-describedby={errors.version_type ? "version-type-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.version_type ? "border-destructive" : "border-input"
              }`}
            >
              <option value="">Select version type</option>
              <option value="major">Major</option>
              <option value="minor">Minor</option>
            </select>
            {errors.version_type && (
              <p id="version-type-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.version_type}
              </p>
            )}
          </div>

          {/* Change Reason */}
          <div className="mb-6">
            <label
              htmlFor="change-reason"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Change Reason <span aria-hidden="true">*</span>
            </label>
            <textarea
              id="change-reason"
              value={changeReason}
              onChange={(e) => setChangeReason(e.target.value)}
              disabled={isLoading}
              rows={3}
              aria-invalid={errors.change_reason ? "true" : undefined}
              aria-describedby={errors.change_reason ? "change-reason-error" : undefined}
              className={`flex w-full rounded-md border bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none ${
                errors.change_reason ? "border-destructive" : "border-input"
              }`}
              placeholder="Describe what changed in this version"
            />
            {errors.change_reason && (
              <p id="change-reason-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.change_reason}
              </p>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <Button
              type="submit"
              className="flex-1"
              disabled={isLoading}
            >
              {isLoading && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isLoading ? "Uploading…" : "Upload Version"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
