import { Draggable } from "@hello-pangea/dnd";
import { GripVertical, X } from "lucide-react";
import type { CanvasFieldData } from "@/types/template";

export interface CanvasFieldProps {
  field: CanvasFieldData;
  index: number;
  isSelected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}

export function CanvasField({
  field,
  index,
  isSelected,
  onSelect,
  onRemove,
}: CanvasFieldProps) {
  return (
    <Draggable draggableId={field.id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${
            isSelected
              ? "border-blue-500 bg-blue-50"
              : "border-border bg-background"
          } ${snapshot.isDragging ? "shadow-md ring-2 ring-ring" : ""}`}
          onClick={onSelect}
          role="listitem"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onSelect();
            }
          }}
        >
          {/* Drag handle */}
          <div
            {...provided.dragHandleProps}
            className="flex shrink-0 cursor-grab items-center focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            aria-label="Drag to reorder"
          >
            <GripVertical
              className="h-4 w-4 text-muted-foreground"
              aria-hidden="true"
            />
          </div>

          {/* Label */}
          <span className="flex-1 truncate text-foreground">{field.label}</span>

          {/* Type badge */}
          <span className="shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
            {field.type}
          </span>

          {/* Remove button */}
          <button
            type="button"
            aria-label="Remove field"
            className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            onKeyDown={(e) => {
              if (e.key === "Delete" || e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                onRemove();
              }
            }}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      )}
    </Draggable>
  );
}
