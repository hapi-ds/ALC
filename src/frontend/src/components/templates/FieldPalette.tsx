import { Droppable, Draggable } from "@hello-pangea/dnd";
import { GripVertical } from "lucide-react";
import type { FieldType, ContentBlockType } from "@/types/template";

const FIELD_TYPES: FieldType[] = ["Text", "Float", "Integer", "Date", "Boolean"];

const CONTENT_ITEMS: { label: string; contentType: ContentBlockType }[] = [
  { label: "Section Header (H1)", contentType: "heading_h1" },
  { label: "Section Header (H2)", contentType: "heading_h2" },
  { label: "Section Header (H3)", contentType: "heading_h3" },
  { label: "Paragraph Text", contentType: "paragraph" },
  { label: "Divider", contentType: "divider" },
];

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
                draggableId={`palette-field-${type}`}
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

      <h2 className="mb-3 mt-6 text-sm font-semibold text-foreground">
        Content
      </h2>
      <Droppable droppableId="content-palette" isDropDisabled={true}>
        {(provided) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className="flex flex-col gap-2"
          >
            {CONTENT_ITEMS.map((item, index) => (
              <Draggable
                key={item.contentType}
                draggableId={`palette-content-${item.contentType}`}
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
                    <span>{item.label}</span>
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
