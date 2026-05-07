import { Droppable } from "@hello-pangea/dnd";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import { CanvasField } from "./CanvasField";

export function BuilderCanvas() {
  const fields = useTemplateBuilderStore((s) => s.fields);
  const selectedFieldId = useTemplateBuilderStore((s) => s.selectedFieldId);
  const selectField = useTemplateBuilderStore((s) => s.selectField);
  const removeField = useTemplateBuilderStore((s) => s.removeField);

  const sortedFields = [...fields].sort(
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
          {sortedFields.length === 0 ? (
            <div className="flex h-full min-h-[160px] items-center justify-center text-sm text-muted-foreground">
              <p>Drag fields from the palette to build your template</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {sortedFields.map((field, index) => (
                <CanvasField
                  key={field.id}
                  field={field}
                  index={index}
                  isSelected={field.id === selectedFieldId}
                  onSelect={() => selectField(field.id)}
                  onRemove={() => removeField(field.id)}
                />
              ))}
            </div>
          )}
          {provided.placeholder}
        </div>
      )}
    </Droppable>
  );
}
