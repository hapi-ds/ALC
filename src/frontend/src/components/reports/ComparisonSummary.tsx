import { CheckCircle, AlertCircle } from "lucide-react";

export interface ComparisonSummaryProps {
  totalFields: number;
  matches: number;
  discrepancies: number;
}

/**
 * Summary bar for the comparison view showing total fields,
 * matches, discrepancies, and a verification message.
 */
export function ComparisonSummary({
  totalFields,
  matches,
  discrepancies,
}: ComparisonSummaryProps) {
  const isVerified = discrepancies === 0 && totalFields > 0;

  return (
    <div
      className="rounded-lg border border-gray-200 bg-white p-4 space-y-3"
      role="region"
      aria-label="Comparison summary"
    >
      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <p className="text-2xl font-bold text-gray-900">{totalFields}</p>
          <p className="text-xs text-gray-500">Total Fields</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-green-600">{matches}</p>
          <p className="text-xs text-gray-500">Matches</p>
        </div>
        <div>
          <p className="text-2xl font-bold text-red-600">{discrepancies}</p>
          <p className="text-xs text-gray-500">Discrepancies</p>
        </div>
      </div>

      {isVerified && (
        <div
          className="flex items-center gap-2 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700"
          role="status"
          aria-live="polite"
        >
          <CheckCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Data integrity verified — all fields match.</span>
        </div>
      )}

      {discrepancies > 0 && (
        <div
          className="flex items-center gap-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700"
          role="status"
          aria-live="polite"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {discrepancies} field{discrepancies > 1 ? "s" : ""} differ between
            extracted and entered values.
          </span>
        </div>
      )}
    </div>
  );
}
