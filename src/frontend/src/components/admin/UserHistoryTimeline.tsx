import { Clock, User } from "lucide-react";
import type { UserHistoryEntry } from "@/types/admin";

interface UserHistoryTimelineProps {
  entries: UserHistoryEntry[];
}

/**
 * Timeline view of user change history.
 * Displays version, timestamp, changed_by, change_reason, and field diffs
 * for each audit entry in reverse chronological order.
 */
export function UserHistoryTimeline({ entries }: UserHistoryTimelineProps) {
  if (entries.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        No change history available.
      </div>
    );
  }

  return (
    <div className="relative space-y-0">
      {/* Vertical timeline line */}
      <div className="absolute left-4 top-2 bottom-2 w-px bg-border" aria-hidden="true" />

      <ol className="space-y-6" aria-label="User change history timeline">
        {entries.map((entry) => (
          <li key={entry.version_id} className="relative pl-10">
            {/* Timeline dot */}
            <div
              className="absolute left-2.5 top-1.5 h-3 w-3 rounded-full border-2 border-primary bg-background"
              aria-hidden="true"
            />

            <div className="rounded-lg border border-border p-4">
              {/* Header: version + timestamp */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className="font-medium text-foreground">
                  Version {entry.version_id}
                </span>
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  <time dateTime={entry.changed_at}>
                    {formatTimestamp(entry.changed_at)}
                  </time>
                </span>
                <span className="flex items-center gap-1 text-muted-foreground">
                  <User className="h-3.5 w-3.5" aria-hidden="true" />
                  {entry.changed_by_username}
                </span>
              </div>

              {/* Change reason */}
              <p className="mt-2 text-sm text-muted-foreground italic">
                &ldquo;{entry.change_reason}&rdquo;
              </p>

              {/* Field diffs */}
              {Object.keys(entry.changes).length > 0 && (
                <div className="mt-3">
                  <table className="w-full text-sm" aria-label="Field changes">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="pb-1 pr-4 font-medium">Field</th>
                        <th className="pb-1 pr-4 font-medium">Previous</th>
                        <th className="pb-1 font-medium">New</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(entry.changes).map(([field, diff]) => (
                        <tr key={field} className="border-b border-border last:border-0">
                          <td className="py-1.5 pr-4 font-medium text-foreground">
                            {formatFieldName(field)}
                          </td>
                          <td className="py-1.5 pr-4 text-red-600 line-through">
                            {formatValue(diff.old)}
                          </td>
                          <td className="py-1.5 text-green-600">
                            {formatValue(diff.new)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Format an ISO timestamp into a human-readable date/time string. */
function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Convert snake_case field names to Title Case for display. */
function formatFieldName(field: string): string {
  return field
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Format a diff value for display, handling null/undefined/boolean. */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
