import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { FieldType } from "../../types/template";

const FIELD_TYPE_OPTIONS: FieldType[] = [
  "Text",
  "Float",
  "Integer",
  "Date",
  "Boolean",
];

export function ConfigurationPanel() {
  const fields = useTemplateBuilderStore((s) => s.fields);
  const selectedFieldId = useTemplateBuilderStore((s) => s.selectedFieldId);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateFieldLabel = useTemplateBuilderStore((s) => s.updateFieldLabel);
  const updateFieldType = useTemplateBuilderStore((s) => s.updateFieldType);

  const selectedField = selectedFieldId
    ? fields.find((f) => f.id === selectedFieldId) ?? null
    : null;

  if (!selectedField) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-sm text-gray-500">
        <p>Select a field to configure its properties</p>
      </div>
    );
  }

  const error = fieldErrors[selectedField.id] ?? null;
  const errorId = `field-label-error-${selectedField.id}`;

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-sm font-semibold text-gray-700">Field Configuration</h2>

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`field-label-${selectedField.id}`}
          className="text-sm font-medium text-gray-700"
        >
          Label
        </label>
        <input
          id={`field-label-${selectedField.id}`}
          type="text"
          value={selectedField.label}
          onChange={(e) => updateFieldLabel(selectedField.id, e.target.value)}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
          className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            error ? "border-red-500" : "border-gray-300"
          }`}
        />
        {error && (
          <p id={errorId} className="text-xs text-red-600" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`field-type-${selectedField.id}`}
          className="text-sm font-medium text-gray-700"
        >
          Type
        </label>
        <select
          id={`field-type-${selectedField.id}`}
          value={selectedField.type}
          onChange={(e) =>
            updateFieldType(selectedField.id, e.target.value as FieldType)
          }
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {FIELD_TYPE_OPTIONS.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
