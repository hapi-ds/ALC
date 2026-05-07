import { useState, useEffect, useRef, type FormEvent, type DragEvent } from "react";
import { createPortal } from "react-dom";
import { Loader2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentStore } from "@/stores/documentStore";

export interface UploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface FormErrors {
  file?: string;
  title?: string;
  folder_path?: string;
  document_type?: string;
}

const DOCUMENT_TYPES = ["SOP", "Protocol", "Report", "General", "Policy", "Form"];

export function UploadDialog({ open, onOpenChange }: UploadDialogProps) {
  const { uploadDocument, isLoading } = useDocumentStore();

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [tags, setTags] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Reset form state when dialog opens
  useEffect(() => {
    if (open) {
      setFile(null);
      setTitle("");
      setFolderPath("");
      setDocumentType("");
      setTags("");
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
    }

    const trimmedTitle = title.trim();
    if (trimmedTitle.length === 0) {
      newErrors.title = "Title is required.";
    } else if (trimmedTitle.length > 500) {
      newErrors.title = "Title must not exceed 500 characters.";
    }

    const trimmedPath = folderPath.trim();
    if (trimmedPath.length === 0) {
      newErrors.folder_path = "Folder path is required.";
    } else if (trimmedPath.length > 1000) {
      newErrors.folder_path = "Folder path must not exceed 1000 characters.";
    }

    if (!documentType) {
      newErrors.document_type = "Document type is required.";
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
    formData.append("title", title.trim());
    formData.append("folder_path", folderPath.trim());
    formData.append("document_type", documentType);
    formData.append("tags", tags.trim());

    try {
      await uploadDocument(formData);
      onOpenChange(false);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Upload failed. Please try again.";
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
        aria-labelledby="upload-dialog-title"
        className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="upload-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Upload Document
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
              className={`relative border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                isDragOver
                  ? "border-primary bg-primary/5"
                  : errors.file
                    ? "border-destructive"
                    : "border-border hover:border-primary/50"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
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
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                onChange={(e) => {
                  handleFileSelect(e.target.files?.[0] ?? null);
                  // Reset input value so the same file can be re-selected
                  e.target.value = "";
                }}
                tabIndex={-1}
              />
              {file ? (
                <div className="flex items-center justify-center gap-2">
                  <Upload className="h-5 w-5 text-primary" aria-hidden="true" />
                  <span className="text-sm font-medium text-foreground">{file.name}</span>
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

          {/* Title */}
          <div className="mb-4">
            <label
              htmlFor="upload-title"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Title <span aria-hidden="true">*</span>
            </label>
            <input
              id="upload-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={500}
              disabled={isLoading}
              aria-invalid={errors.title ? "true" : undefined}
              aria-describedby={errors.title ? "upload-title-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.title ? "border-destructive" : "border-input"
              }`}
              placeholder="Enter document title"
            />
            {errors.title && (
              <p id="upload-title-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.title}
              </p>
            )}
          </div>

          {/* Folder Path */}
          <div className="mb-4">
            <label
              htmlFor="upload-folder-path"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Folder Path <span aria-hidden="true">*</span>
            </label>
            <input
              id="upload-folder-path"
              type="text"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              maxLength={1000}
              disabled={isLoading}
              aria-invalid={errors.folder_path ? "true" : undefined}
              aria-describedby={errors.folder_path ? "upload-folder-path-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.folder_path ? "border-destructive" : "border-input"
              }`}
              placeholder="e.g., /quality/sops"
            />
            {errors.folder_path && (
              <p id="upload-folder-path-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.folder_path}
              </p>
            )}
          </div>

          {/* Document Type */}
          <div className="mb-4">
            <label
              htmlFor="upload-document-type"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Document Type <span aria-hidden="true">*</span>
            </label>
            <select
              id="upload-document-type"
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              disabled={isLoading}
              aria-invalid={errors.document_type ? "true" : undefined}
              aria-describedby={errors.document_type ? "upload-document-type-error" : undefined}
              className={`flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                errors.document_type ? "border-destructive" : "border-input"
              }`}
            >
              <option value="">Select a document type</option>
              {DOCUMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            {errors.document_type && (
              <p id="upload-document-type-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.document_type}
              </p>
            )}
          </div>

          {/* Tags */}
          <div className="mb-6">
            <label
              htmlFor="upload-tags"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Tags <span className="text-muted-foreground font-normal">(optional, comma-separated)</span>
            </label>
            <input
              id="upload-tags"
              type="text"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              disabled={isLoading}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="e.g., quality, review, batch-record"
            />
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
              {isLoading ? "Uploading…" : "Upload"}
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
