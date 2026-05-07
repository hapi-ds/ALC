import { useEffect, useState, useCallback } from "react";
import { DragDropContext, type DropResult } from "@hello-pangea/dnd";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { FieldType } from "../../types/template";
import { FieldPalette } from "./FieldPalette";
import { BuilderCanvas } from "./BuilderCanvas";
import { ConfigurationPanel } from "./ConfigurationPanel";
import { TemplateNameInput } from "./TemplateNameInput";
import { SaveButton } from "./SaveButton";

export function TemplateBuilder() {
  const fields = useTemplateBuilderStore((s) => s.fields);
  const addField = useTemplateBuilderStore((s) => s.addField);
  const reorderField = useTemplateBuilderStore((s) => s.reorderField);
  const saveSuccess = useTemplateBuilderStore((s) => s.saveSuccess);
  const saveError = useTemplateBuilderStore((s) => s.saveError);

  const [showSuccess, setShowSuccess] = useState(false);
  const [showError, setShowError] = useState(false);
  const [maxFieldsMessage, setMaxFieldsMessage] = useState(false);

  // Auto-dismiss success notification after 5 seconds
  useEffect(() => {
    if (saveSuccess) {
      setShowSuccess(true);
      const timer = setTimeout(() => {
        setShowSuccess(false);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [saveSuccess]);

  // Show error notification when saveError changes to non-null
  useEffect(() => {
    if (saveError) {
      setShowError(true);
    } else {
      setShowError(false);
    }
  }, [saveError]);

  // Auto-dismiss max fields message after 3 seconds
  useEffect(() => {
    if (maxFieldsMessage) {
      const timer = setTimeout(() => {
        setMaxFieldsMessage(false);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [maxFieldsMessage]);

  const onDragEnd = useCallback(
    (result: DropResult) => {
      const { source, destination, draggableId } = result;
      if (!destination) return; // dropped outside

      if (
        source.droppableId === "field-palette" &&
        destination.droppableId === "builder-canvas"
      ) {
        // Enforce 50-field max with UI message
        if (fields.length >= 50) {
          setMaxFieldsMessage(true);
          return;
        }
        const fieldType = draggableId.replace(
          "palette-",
          ""
        ) as FieldType;
        addField(fieldType, destination.index);
      } else if (
        source.droppableId === "builder-canvas" &&
        destination.droppableId === "builder-canvas"
      ) {
        reorderField(source.index, destination.index);
      }
    },
    [fields.length, addField, reorderField]
  );

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div className="flex h-full flex-col">
        {/* Notifications */}
        {showSuccess && (
          <div
            role="status"
            aria-live="polite"
            className="mb-4 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
          >
            Template saved successfully.
          </div>
        )}
        {showError && saveError && (
          <div
            role="alert"
            className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {saveError}
          </div>
        )}
        {maxFieldsMessage && (
          <div
            role="alert"
            className="mb-4 rounded-md border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
          >
            Maximum of 50 fields reached
          </div>
        )}

        {/* Three-panel layout */}
        <div className="flex flex-1 gap-0 overflow-hidden rounded-lg border border-border">
          {/* Left panel: Field Palette */}
          <FieldPalette />

          {/* Center panel: Name input + Canvas + Save button */}
          <div className="flex flex-1 flex-col p-4">
            <TemplateNameInput />
            <div className="flex-1 overflow-y-auto">
              <BuilderCanvas />
            </div>
            <div className="mt-4">
              <SaveButton />
            </div>
          </div>

          {/* Right panel: Configuration Panel */}
          <div className="w-72 shrink-0 border-l border-border">
            <ConfigurationPanel />
          </div>
        </div>
      </div>
    </DragDropContext>
  );
}
