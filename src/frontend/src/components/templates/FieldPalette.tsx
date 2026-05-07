import { Droppable, Draggable } from "@hello-pangea/dnd";
import { GripVertical } from "lucide-react";
import type { FieldType } from "@/types/template";

const FIELD_TYPES: FieldType[] = ["Text", "Float", "Integer", "Date", "Boolean"];

export function FieldPalette() {
  return (
    <div className="w-56 shrink-0 border-r border-border bg-muted/30 p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">
        Field Types
      </h2>
      <Droppable droppableId="field-palette" isDropDisabled={true}>
        {(provided) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className="flex flex-col gap-2"
          >
            {FIELD_TYPES.map((type, index) => (
              <Draggable
                key={type}
                draggableId={`palette-${type}`}
                index={index}
              >
                {(provided, snapshot) => (
                  <div
                    ref={provided.innerRef}
                    {...provided.draggableProps}
                    {...provided.dragHandleProps}
                    className={`flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium shadow-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                      snapshot.isDragging
                        ? "shadow-md ring-2 ring-ring"
                        : ""
                    }`}
                  >
                    <GripVertical
                      className="h-4 w-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <span>{type}</span>
                  </div>
                )}
              </Draggable>
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </div>
  );
}
