/**
 * ActionItemTracker — Kanban-style board for managing review action items.
 *
 * Displays action items in columns by status: Open, In Progress, Resolved, Dismissed.
 * Drag-and-drop between columns triggers a status update with a change reason prompt.
 *
 * Uses @hello-pangea/dnd for drag-and-drop interactions.
 * Calls the Zustand store's updateActionItem action on status change.
 *
 * Validates: Requirements 11.5, 5.4
 */

import { useState, useCallback, useMemo } from "react";
import {
  DragDropContext,
  Droppable,
  Draggable,
  type DropResult,
} from "@hello-pangea/dnd";
import type { ActionItem } from "../../lib/reviews-api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ActionItemStatus = "Open" | "InProgress" | "Resolved" | "Dismissed";

export interface ActionItemTrackerProps {
  /** Action items to display on the board. */
  items: ActionItem[];
  /** Session ID for the action items (used in update calls). */
  sessionId: number;
  /** Callback to update an action item's status with a change reason. */
  onUpdateItem: (
    sessionId: number,
    itemId: number,
    data: { status: string; resolution_note?: string | null },
    changeReason: string,
  ) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Ordered columns for the kanban board. */
const COLUMNS: { id: ActionItemStatus; label: string }[] = [
  { id: "Open", label: "Open" },
  { id: "InProgress", label: "In Progress" },
  { id: "Resolved", label: "Resolved" },
  { id: "Dismissed", label: "Dismissed" },
];

/** Color coding for severity badges. */
const SEVERITY_COLORS: Record<string, string> = {
  Critical: "bg-red-100 text-red-800 border-red-200",
  Major: "bg-orange-100 text-orange-800 border-orange-200",
  Minor: "bg-yellow-100 text-yellow-800 border-yellow-200",
  Informational: "bg-blue-100 text-blue-800 border-blue-200",
};

/** Column header accent colors. */
const COLUMN_COLORS: Record<ActionItemStatus, string> = {
  Open: "border-t-blue-500",
  InProgress: "border-t-amber-500",
  Resolved: "border-t-green-500",
  Dismissed: "border-t-gray-400",
};

/** Column header badge colors. */
const COLUMN_BADGE_COLORS: Record<ActionItemStatus, string> = {
  Open: "bg-blue-100 text-blue-700",
  InProgress: "bg-amber-100 text-amber-700",
  Resolved: "bg-green-100 text-green-700",
  Dismissed: "bg-gray-100 text-gray-600",
};

// ---------------------------------------------------------------------------
// Change Reason Modal
// ---------------------------------------------------------------------------

interface ChangeReasonModalProps {
  isOpen: boolean;
  targetStatus: ActionItemStatus | null;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

function ChangeReasonModal({
  isOpen,
  targetStatus,
  onConfirm,
  onCancel,
}: ChangeReasonModalProps) {
  const [reason, setReason] = useState("");

  if (!isOpen || !targetStatus) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (reason.trim()) {
      onConfirm(reason.trim());
      setReason("");
    }
  };

  const handleCancel = () => {
    setReason("");
    onCancel();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="change-reason-title"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h3 id="change-reason-title" className="text-lg font-semibold text-foreground">
          Change Reason Required
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Moving item to <span className="font-medium">{targetStatus === "InProgress" ? "In Progress" : targetStatus}</span>.
          Please provide a reason for this change (ALCOA+ compliance).
        </p>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <textarea
            className="w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            rows={3}
            placeholder="Enter change reason..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-label="Change reason"
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={handleCancel}
              className="rounded-md border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!reason.trim()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Confirm
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ActionItemTracker({
  items,
  sessionId,
  onUpdateItem,
}: ActionItemTrackerProps) {
  const [pendingDrop, setPendingDrop] = useState<{
    itemId: number;
    targetStatus: ActionItemStatus;
  } | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  /** Group items by status into columns. */
  const columnItems = useMemo(() => {
    const grouped: Record<ActionItemStatus, ActionItem[]> = {
      Open: [],
      InProgress: [],
      Resolved: [],
      Dismissed: [],
    };

    for (const item of items) {
      const status = item.status as ActionItemStatus;
      if (grouped[status]) {
        grouped[status].push(item);
      }
    }

    return grouped;
  }, [items]);

  /** Handle drag end — prompt for change reason before updating. */
  const handleDragEnd = useCallback(
    (result: DropResult) => {
      const { destination, source, draggableId } = result;

      // Dropped outside a droppable or in the same column
      if (!destination || destination.droppableId === source.droppableId) {
        return;
      }

      const targetStatus = destination.droppableId as ActionItemStatus;
      const itemId = parseInt(draggableId, 10);

      // Show the change reason modal
      setPendingDrop({ itemId, targetStatus });
    },
    [],
  );

  /** Confirm the status change with the provided reason. */
  const handleConfirmChange = useCallback(
    async (reason: string) => {
      if (!pendingDrop) return;

      setIsUpdating(true);
      try {
        await onUpdateItem(
          sessionId,
          pendingDrop.itemId,
          { status: pendingDrop.targetStatus },
          reason,
        );
      } catch {
        // Error handling is managed by the store
      } finally {
        setIsUpdating(false);
        setPendingDrop(null);
      }
    },
    [pendingDrop, sessionId, onUpdateItem],
  );

  /** Cancel the pending drop. */
  const handleCancelChange = useCallback(() => {
    setPendingDrop(null);
  }, []);

  // Empty state
  if (items.length === 0) {
    return (
      <div
        className="rounded-lg border border-border p-6 text-center text-muted-foreground"
        role="region"
        aria-label="Action item tracker"
      >
        <p>No action items</p>
      </div>
    );
  }

  return (
    <div role="region" aria-label="Action item tracker" className="space-y-3">
      <h3 className="text-sm font-medium text-foreground">Action Items</h3>

      <DragDropContext onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          {COLUMNS.map((column) => (
            <div
              key={column.id}
              className={`rounded-lg border border-border border-t-4 ${COLUMN_COLORS[column.id]} bg-muted/30`}
            >
              {/* Column header */}
              <div className="flex items-center justify-between px-3 py-2">
                <h4 className="text-xs font-semibold text-foreground">
                  {column.label}
                </h4>
                <span
                  className={`inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-xs font-medium ${COLUMN_BADGE_COLORS[column.id]}`}
                >
                  {columnItems[column.id].length}
                </span>
              </div>

              {/* Droppable area */}
              <Droppable droppableId={column.id}>
                {(provided, snapshot) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.droppableProps}
                    className={`min-h-[120px] space-y-2 px-2 pb-2 transition-colors ${
                      snapshot.isDraggingOver ? "bg-muted/60" : ""
                    }`}
                  >
                    {columnItems[column.id].map((item, index) => (
                      <Draggable
                        key={item.id}
                        draggableId={String(item.id)}
                        index={index}
                        isDragDisabled={isUpdating}
                      >
                        {(dragProvided, dragSnapshot) => (
                          <div
                            ref={dragProvided.innerRef}
                            {...dragProvided.draggableProps}
                            {...dragProvided.dragHandleProps}
                            className={`rounded-md border border-border bg-white p-3 shadow-sm transition-shadow ${
                              dragSnapshot.isDragging
                                ? "shadow-lg ring-2 ring-ring"
                                : "hover:shadow-md"
                            }`}
                            aria-label={`Action item: ${item.title}`}
                          >
                            {/* Severity badge */}
                            <span
                              className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                                SEVERITY_COLORS[item.severity] || "bg-gray-100 text-gray-700 border-gray-200"
                              }`}
                            >
                              {item.severity}
                            </span>

                            {/* Title */}
                            <p className="mt-1.5 text-xs font-medium text-foreground line-clamp-2">
                              {item.title}
                            </p>

                            {/* Description preview */}
                            {item.description && (
                              <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">
                                {item.description}
                              </p>
                            )}

                            {/* Resolution note (for resolved/dismissed items) */}
                            {item.resolution_note && (
                              <p className="mt-1.5 rounded bg-muted/50 px-1.5 py-1 text-[10px] text-muted-foreground italic line-clamp-1">
                                {item.resolution_note}
                              </p>
                            )}
                          </div>
                        )}
                      </Draggable>
                    ))}
                    {provided.placeholder}
                  </div>
                )}
              </Droppable>
            </div>
          ))}
        </div>
      </DragDropContext>

      {/* Change reason modal */}
      <ChangeReasonModal
        isOpen={pendingDrop !== null}
        targetStatus={pendingDrop?.targetStatus ?? null}
        onConfirm={handleConfirmChange}
        onCancel={handleCancelChange}
      />
    </div>
  );
}
