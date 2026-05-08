import { Droppable } from "@hello-pangea/dnd";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import { CanvasField } from "./CanvasField";
import { CanvasContentBlock } from "./CanvasContentBlock";
import type { CanvasItem } from "@/types/template";

export function BuilderCanvas() {
  const items = useTemplateBuilderStore((s) => s.items);
  const fields = useTemplateBuilderStore((s) => s.fields);
  const selectedFieldId = useTemplateBuilderStore((s) => s.selectedFieldId);
  const selectField = useTemplateBuilderStore((s) => s.selectField);
  const removeItem = useTemplateBuilderStore((s) => s.removeItem);

  // Resolve items: prefer items array, fall back to fields for backward compat
  const resolvedItems: CanvasItem[] =
    items.length > 0
      ? items
      : fields.map((f) => ({
          id: f.id,
          element_type: "field" as const,
          label: f.label,
          type: f.type,
          fieldOrder: f.fieldOrder,
          required: false,
          help_text: null,
          default_value: null,
          config: {},
        }));

  const sortedItems = [...resolvedItems].sort(
    (a, b) => a.fieldOrder - b.fieldOrder
  );

  return (
    <Droppable droppableId="builder-canvas">
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.droppableProps}
          className={`min-h-[200px] flex-1 rounded-md border-2 border-dashed p-4 transition-colors ${
            snapshot.isDraggingOver
              ? "border-blue-400 bg-blue-50/50"
              : "border-border bg-background"
          }`}
          role="list"
          aria-label="Template fields canvas"
        >
          {sortedItems.length === 0 ? (
            <div className="flex h-full min-h-[160px] items-center justify-center text-sm text-muted-foreground">
              <p>Drag fields from the palette to build your template</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {sortedItems.map((item, index) => {
                if (item.element_type === "content_block") {
                  return (
                    <CanvasContentBlock
                      key={item.id}
                      item={item}
                      index={index}
                      isSelected={item.id === selectedFieldId}
                      onSelect={() => selectField(item.id)}
                      onDelete={() => removeItem(item.id)}
                    />
                  );
                }

                return (
                  <CanvasField
                    key={item.id}
                    field={item}
                    index={index}
                    isSelected={item.id === selectedFieldId}
                    onSelect={() => selectField(item.id)}
                    onRemove={() => removeItem(item.id)}
                  />
                );
              })}
            </div>
          )}
          {provided.placeholder}
        </div>
      )}
    </Droppable>
  );
}
