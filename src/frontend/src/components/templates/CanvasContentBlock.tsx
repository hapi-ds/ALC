import { Draggable } from "@hello-pangea/dnd";
import { GripVertical, X, Type, Minus } from "lucide-react";
import type { CanvasContentBlockElement } from "@/types/template";

export interface CanvasContentBlockProps {
  item: CanvasContentBlockElement;
  index: number;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export function CanvasContentBlock({
  item,
  index,
  isSelected,
  onSelect,
  onDelete,
}: CanvasContentBlockProps) {
  return (
    <Draggable draggableId={item.id} index={index}>
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

          {/* Content rendering based on content_type */}
          <div className="flex-1 truncate">
            {renderContent(item)}
          </div>

          {/* Delete button */}
          <button
            type="button"
            aria-label="Delete content block"
            className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            onKeyDown={(e) => {
              if (e.key === "Delete" || e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                onDelete();
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

function renderContent(item: CanvasContentBlockElement) {
  switch (item.content_type) {
    case "heading_h1":
      return (
        <span className="text-xl font-bold text-foreground">
          {item.text || "Section Title"}
        </span>
      );
    case "heading_h2":
      return (
        <span className="text-lg font-semibold text-foreground">
          {item.text || "Section Title"}
        </span>
      );
    case "heading_h3":
      return (
        <span className="text-base font-semibold text-foreground">
          {item.text || "Section Title"}
        </span>
      );
    case "paragraph":
      return (
        <span className="flex items-center gap-1.5 rounded bg-gray-50 px-1.5 py-0.5 text-foreground">
          <Type className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="truncate">
            {item.text || "Enter instructions or description here"}
          </span>
        </span>
      );
    case "divider":
      return (
        <span className="flex w-full items-center gap-2">
          <Minus className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <hr className="flex-1 border-t border-border" />
        </span>
      );
    default:
      return null;
  }
}
