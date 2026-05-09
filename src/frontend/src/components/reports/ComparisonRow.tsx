import { Check, AlertTriangle, Minus } from "lucide-react";
import type { ComparisonFieldRow } from "@/types/report";

export interface ComparisonRowProps {
  row: ComparisonFieldRow;
}

/**
 * A single row in the comparison view displaying extracted vs. entered values.
 * Visually distinguishes match (green), discrepancy (red), and missing (gray).
 */
export function ComparisonRow({ row }: ComparisonRowProps) {
  const isMissing =
    row.extracted_value === null || row.entered_value === null;

  let statusIcon: React.ReactNode;
  let rowClass: string;

  if (row.is_match) {
    statusIcon = (
      <Check className="h-4 w-4 text-green-600" aria-hidden="true" />
    );
    rowClass = "bg-green-50 border-green-200";
  } else if (isMissing) {
    statusIcon = (
      <Minus className="h-4 w-4 text-gray-400" aria-hidden="true" />
    );
    rowClass = "bg-gray-50 border-gray-200";
  } else {
    statusIcon = (
      <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
    );
    rowClass = "bg-red-50 border-red-200";
  }

  const statusLabel = row.is_match
    ? "Match"
    : isMissing
      ? "Missing value"
      : "Discrepancy";

  return (
    <div
      className={`grid grid-cols-[1fr_2fr_2fr_auto] items-center gap-3 rounded-md border px-4 py-3 ${rowClass}`}
      role="row"
      aria-label={`${row.field_label}: ${statusLabel}`}
    >
      <span className="text-sm font-medium text-gray-700 truncate">
        {row.field_label}
      </span>

      <span className="text-sm text-gray-900 truncate">
        {row.extracted_value ?? (
          <span className="italic text-gray-400">—</span>
        )}
      </span>

      <span className="text-sm text-gray-900 truncate">
        {row.entered_value ?? (
          <span className="italic text-gray-400">—</span>
        )}
      </span>

      <span
        className="flex items-center"
        title={statusLabel}
        aria-label={statusLabel}
      >
        {statusIcon}
      </span>
    </div>
  );
}
