/**
 * AuditEventDetailPanel — Slide-over panel displaying full audit event details.
 *
 * Triggered by row click in the AuditTrailTable. Uses shadcn/ui Sheet (Radix Dialog)
 * for the slide-over behavior with click-outside-to-close.
 *
 * Displays:
 *   - Full event metadata (timestamp, user, record type, record ID, operation, change reason)
 *   - Field changes table:
 *     - UPDATE: Previous Value / New Value columns with highlighting
 *     - INSERT: Initial Value column
 *     - DELETE: Final Value column
 *   - JSON syntax highlighting for complex field values
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */

import { useAuditTrailStore } from "../stores/useAuditTrailStore";
import type { AuditEventDetail, FieldChange } from "../types/auditTrail";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "./ui/sheet";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a timestamp string to a human-readable date/time.
 */
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  });
}

/**
 * Format a value for display. Objects/arrays get JSON syntax highlighting,
 * primitives are displayed as-is.
 */
function isComplexValue(value: unknown): boolean {
  return (
    value !== null &&
    value !== undefined &&
    typeof value === "object"
  );
}

/**
 * Render a JSON value with basic syntax highlighting using Tailwind classes.
 */
function JsonHighlight({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-gray-400 italic">null</span>;
  }

  if (!isComplexValue(value)) {
    if (typeof value === "string") {
      return <span className="text-green-600 dark:text-green-400">"{value}"</span>;
    }
    if (typeof value === "number") {
      return <span className="text-blue-600 dark:text-blue-400">{String(value)}</span>;
    }
    if (typeof value === "boolean") {
      return (
        <span className="text-purple-600 dark:text-purple-400">
          {String(value)}
        </span>
      );
    }
    return <span>{String(value)}</span>;
  }

  // Complex value — format as indented JSON with highlighting
  const jsonStr = JSON.stringify(value, null, 2);
  return (
    <pre className="text-xs font-mono bg-gray-50 dark:bg-gray-900 rounded p-2 overflow-x-auto whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
      <code>{jsonStr}</code>
    </pre>
  );
}

/**
 * Render a field value cell — uses JSON highlighting for complex values,
 * simple text for primitives.
 */
function FieldValueCell({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-gray-400 italic">null</span>;
  }

  if (isComplexValue(value)) {
    return <JsonHighlight value={value} />;
  }

  return <JsonHighlight value={value} />;
}

// ---------------------------------------------------------------------------
// Operation badge
// ---------------------------------------------------------------------------

function OperationBadge({ operation }: { operation: string }) {
  const colors: Record<string, string> = {
    INSERT: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    UPDATE: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    DELETE: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[operation] ?? "bg-gray-100 text-gray-800"}`}
    >
      {operation}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Field Changes Table
// ---------------------------------------------------------------------------

function FieldChangesTable({
  fieldChanges,
  operationType,
}: {
  fieldChanges: FieldChange[];
  operationType: "INSERT" | "UPDATE" | "DELETE";
}) {
  if (fieldChanges.length === 0) {
    return (
      <p className="text-sm text-gray-500 italic">No field changes recorded.</p>
    );
  }

  if (operationType === "UPDATE") {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-1/4">
                Field
              </th>
              <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-[37.5%]">
                Previous Value
              </th>
              <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-[37.5%]">
                New Value
              </th>
            </tr>
          </thead>
          <tbody>
            {fieldChanges.map((change) => (
              <tr
                key={change.field_name}
                className="border-b border-gray-100 dark:border-gray-800 bg-yellow-50/50 dark:bg-yellow-900/10"
              >
                <td className="py-2 px-3 font-mono text-xs font-semibold text-gray-700 dark:text-gray-200">
                  {change.field_name}
                </td>
                <td className="py-2 px-3">
                  <FieldValueCell value={change.old_value} />
                </td>
                <td className="py-2 px-3">
                  <FieldValueCell value={change.new_value} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (operationType === "INSERT") {
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-1/3">
                Field
              </th>
              <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-2/3">
                Initial Value
              </th>
            </tr>
          </thead>
          <tbody>
            {fieldChanges.map((change) => (
              <tr
                key={change.field_name}
                className="border-b border-gray-100 dark:border-gray-800"
              >
                <td className="py-2 px-3 font-mono text-xs font-semibold text-gray-700 dark:text-gray-200">
                  {change.field_name}
                </td>
                <td className="py-2 px-3">
                  <FieldValueCell value={change.new_value} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // DELETE
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700">
            <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-1/3">
              Field
            </th>
            <th className="text-left py-2 px-3 font-medium text-gray-600 dark:text-gray-300 w-2/3">
              Final Value
            </th>
          </tr>
        </thead>
        <tbody>
          {fieldChanges.map((change) => (
            <tr
              key={change.field_name}
              className="border-b border-gray-100 dark:border-gray-800"
            >
              <td className="py-2 px-3 font-mono text-xs font-semibold text-gray-700 dark:text-gray-200">
                {change.field_name}
              </td>
              <td className="py-2 px-3">
                <FieldValueCell value={change.old_value} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-3/4" />
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
      <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-2/3" />
      <div className="mt-6 space-y-3">
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-full" />
        <div className="h-3 bg-gray-200 dark:bg-gray-700 rounded w-5/6" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Event metadata section
// ---------------------------------------------------------------------------

function EventMetadata({ event }: { event: AuditEventDetail }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
      <div>
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          Timestamp
        </span>
        <p className="font-medium text-gray-900 dark:text-gray-100">
          {formatTimestamp(event.timestamp)}
        </p>
      </div>
      <div>
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          User
        </span>
        <p className="font-medium text-gray-900 dark:text-gray-100">
          {event.user_display_name ?? `User #${event.user_id}`}
        </p>
      </div>
      <div>
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          Record Type
        </span>
        <p className="font-medium text-gray-900 dark:text-gray-100 capitalize">
          {event.record_type}
        </p>
      </div>
      <div>
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          Record ID
        </span>
        <p className="font-medium text-gray-900 dark:text-gray-100">
          {event.record_id}
        </p>
      </div>
      <div>
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          Operation
        </span>
        <p className="mt-0.5">
          <OperationBadge operation={event.operation_type} />
        </p>
      </div>
      <div>
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          Transaction ID
        </span>
        <p className="font-medium text-gray-900 dark:text-gray-100">
          {event.transaction_id}
        </p>
      </div>
      <div className="col-span-2">
        <span className="text-gray-500 dark:text-gray-400 text-xs uppercase tracking-wide">
          Change Reason
        </span>
        <p className="font-medium text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
          {event.change_reason ?? (
            <span className="text-gray-400 italic">No reason provided</span>
          )}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface AuditEventDetailPanelProps {
  /** Whether the panel is open */
  open: boolean;
  /** Callback when the panel should close */
  onOpenChange: (open: boolean) => void;
}

export function AuditEventDetailPanel({
  open,
  onOpenChange,
}: AuditEventDetailPanelProps) {
  const selectedEvent = useAuditTrailStore((state) => state.selectedEvent);
  const isLoading = useAuditTrailStore((state) => state.isLoading);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Audit Event Detail</SheetTitle>
          <SheetDescription>
            Full change details for the selected audit event.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6">
          {isLoading && <DetailSkeleton />}

          {!isLoading && !selectedEvent && (
            <p className="text-sm text-gray-500 italic">
              No event selected.
            </p>
          )}

          {!isLoading && selectedEvent && (
            <div className="space-y-6">
              {/* Event metadata */}
              <EventMetadata event={selectedEvent} />

              {/* Divider */}
              <hr className="border-gray-200 dark:border-gray-700" />

              {/* Field changes */}
              <div>
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3">
                  Field Changes
                  {selectedEvent.field_changes.length > 0 && (
                    <span className="ml-2 text-xs font-normal text-gray-500">
                      ({selectedEvent.field_changes.length} field
                      {selectedEvent.field_changes.length !== 1 ? "s" : ""})
                    </span>
                  )}
                </h3>
                <FieldChangesTable
                  fieldChanges={selectedEvent.field_changes}
                  operationType={selectedEvent.operation_type}
                />
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
