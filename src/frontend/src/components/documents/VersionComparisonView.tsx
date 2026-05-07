import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import { X, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentVersion } from "@/types/document";
import { sortVersionsDescending } from "@/lib/versionUtils";
import { DiffMetadataView } from "./DiffMetadataView";

export interface VersionComparisonViewProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  versions: DocumentVersion[];
}

/** Format a version label as "v{major}.{minor}" */
function versionLabel(v: DocumentVersion): string {
  return `v${v.major_version}.${v.minor_version}`;
}

/** Metadata fields to compare side-by-side */
const COMPARISON_FIELDS: {
  key: keyof DocumentVersion;
  label: string;
}[] = [
  { key: "major_version", label: "Version" },
  { key: "file_hash", label: "File Hash" },
  { key: "uploaded_by", label: "Uploaded By" },
  { key: "uploaded_at", label: "Uploaded At" },
  { key: "change_reason", label: "Change Reason" },
  { key: "storage_key", label: "Storage Key" },
];

/** Get the display string for a field value */
function getFieldDisplay(version: DocumentVersion, key: keyof DocumentVersion): string {
  switch (key) {
    case "major_version":
      return versionLabel(version);
    case "uploaded_by":
      return `User ${version.uploaded_by}`;
    case "uploaded_at":
      return new Date(version.uploaded_at).toLocaleString();
    case "change_reason":
      return version.change_reason ?? "No reason provided";
    default:
      return String(version[key]);
  }
}

export function VersionComparisonView({ open, onOpenChange, versions }: VersionComparisonViewProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  const sorted = useMemo(() => sortVersionsDescending(versions), [versions]);

  // Default: second-most-recent on left, most-recent on right
  const [leftId, setLeftId] = useState<number | null>(null);
  const [rightId, setRightId] = useState<number | null>(null);

  // Reset selections when dialog opens or versions change
  useEffect(() => {
    if (open && sorted.length >= 2) {
      setLeftId(sorted[1].id);
      setRightId(sorted[0].id);
    } else if (open && sorted.length === 1) {
      setLeftId(sorted[0].id);
      setRightId(sorted[0].id);
    }
  }, [open, sorted]);

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
          'select, button, [tabindex]:not([tabindex="-1"])'
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

  const leftVersion = useMemo(
    () => sorted.find((v) => v.id === leftId) ?? null,
    [sorted, leftId]
  );
  const rightVersion = useMemo(
    () => sorted.find((v) => v.id === rightId) ?? null,
    [sorted, rightId]
  );

  const isSameVersion = leftId !== null && rightId !== null && leftId === rightId;

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
        aria-labelledby="version-comparison-dialog-title"
        className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="version-comparison-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            Compare Versions
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Version selectors */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <label
              htmlFor="comparison-left-version"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Left Version
            </label>
            <select
              id="comparison-left-version"
              value={leftId ?? ""}
              onChange={(e) => setLeftId(Number(e.target.value))}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {sorted.map((v) => (
                <option key={v.id} value={v.id}>
                  {versionLabel(v)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="comparison-right-version"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Right Version
            </label>
            <select
              id="comparison-right-version"
              value={rightId ?? ""}
              onChange={(e) => setRightId(Number(e.target.value))}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              {sorted.map((v) => (
                <option key={v.id} value={v.id}>
                  {versionLabel(v)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Same version notice */}
        {isSameVersion && (
          <div
            className="mb-4 flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground"
            role="alert"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>Both sides show the same version. Select different versions to see differences.</span>
          </div>
        )}

        {/* Side-by-side metadata grid */}
        {leftVersion && rightVersion && (
          <>
            <div className="rounded-md border border-border overflow-hidden mb-6">
              {/* Grid header */}
              <div className="grid grid-cols-[1fr_1fr_1fr] bg-muted/50 border-b border-border">
                <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase">
                  Field
                </div>
                <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase border-l border-border">
                  {versionLabel(leftVersion)} (Left)
                </div>
                <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase border-l border-border">
                  {versionLabel(rightVersion)} (Right)
                </div>
              </div>

              {/* Metadata rows */}
              {COMPARISON_FIELDS.map(({ key, label }) => {
                const leftValue = getFieldDisplay(leftVersion, key);
                const rightValue = getFieldDisplay(rightVersion, key);
                const isDifferent = !isSameVersion && leftValue !== rightValue;
                const rowBg = isDifferent ? "bg-amber-50 dark:bg-amber-950/20" : "";

                return (
                  <div
                    key={key}
                    className={`grid grid-cols-[1fr_1fr_1fr] border-b border-border last:border-b-0 ${rowBg}`}
                  >
                    <div className="px-3 py-2 text-sm font-medium text-foreground">
                      {label}
                    </div>
                    <div className="px-3 py-2 text-sm text-foreground break-all border-l border-border">
                      {leftValue}
                    </div>
                    <div className="px-3 py-2 text-sm text-foreground break-all border-l border-border">
                      {rightValue}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Diff summary */}
            {!isSameVersion && (
              <div>
                <h3 className="text-sm font-medium text-foreground mb-3">Differences Summary</h3>
                <DiffMetadataView left={leftVersion} right={rightVersion} />
              </div>
            )}
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
