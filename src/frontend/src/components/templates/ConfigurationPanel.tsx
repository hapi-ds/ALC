import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldElement, CanvasItem, FieldType } from "../../types/template";
import { TextConfigPanel } from "./TextConfigPanel";
import { FloatConfigPanel } from "./FloatConfigPanel";
import { IntegerConfigPanel } from "./IntegerConfigPanel";
import { DateConfigPanel } from "./DateConfigPanel";
import { BooleanConfigPanel } from "./BooleanConfigPanel";
import { ContentBlockConfigPanel } from "./ContentBlockConfigPanel";

const FIELD_TYPE_OPTIONS: FieldType[] = [
  "Text",
  "Float",
  "Integer",
  "Date",
  "Boolean",
];

const MAX_HELP_TEXT_LENGTH = 500;

export function ConfigurationPanel() {
  const items = useTemplateBuilderStore((s) => s.items);
  const fields = useTemplateBuilderStore((s) => s.fields);
  const selectedFieldId = useTemplateBuilderStore((s) => s.selectedFieldId);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateFieldLabel = useTemplateBuilderStore((s) => s.updateFieldLabel);
  const updateFieldType = useTemplateBuilderStore((s) => s.updateFieldType);
  const updateFieldRequired = useTemplateBuilderStore((s) => s.updateFieldRequired);
  const updateFieldHelpText = useTemplateBuilderStore((s) => s.updateFieldHelpText);
  const updateFieldDefaultValue = useTemplateBuilderStore((s) => s.updateFieldDefaultValue);

  // Resolve items: prefer items, fall back to fields for backward compatibility
  const resolvedItems: CanvasItem[] = items.length > 0
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

  // Find the selected item in resolved items
  const selectedItem = selectedFieldId
    ? resolvedItems.find((item) => item.id === selectedFieldId) ?? null
    : null;

  // No selection: show placeholder
  if (!selectedItem) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-sm text-gray-500">
        <p>Select a field to configure its properties</p>
      </div>
    );
  }

  // Content block: route to ContentBlockConfigPanel
  if (selectedItem.element_type === "content_block") {
    return (
      <div className="flex flex-col gap-4 p-4">
        <h2 className="text-sm font-semibold text-gray-700">Content Block Configuration</h2>
        <ContentBlockConfigPanel blockId={selectedItem.id} />
      </div>
    );
  }

  // Field: show common properties + type-specific panel
  const selectedField = selectedItem as CanvasFieldElement;
  const error = fieldErrors[selectedField.id] ?? null;
  const errorId = `field-label-error-${selectedField.id}`;
  const helpTextLength = selectedField.help_text?.length ?? 0;
  const helpTextError =
    helpTextLength > MAX_HELP_TEXT_LENGTH
      ? `Help text must not exceed ${MAX_HELP_TEXT_LENGTH} characters`
      : null;

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-sm font-semibold text-gray-700">Field Configuration</h2>

      {/* Label */}
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

      {/* Type */}
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

      {/* Common Properties Section */}
      <div className="border-t border-gray-200 pt-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-3">
          Common Properties
        </h3>

        {/* Required Toggle */}
        <div className="flex items-center justify-between mb-3">
          <label
            htmlFor={`field-required-${selectedField.id}`}
            className="text-sm font-medium text-gray-700"
          >
            Required
          </label>
          <button
            id={`field-required-${selectedField.id}`}
            type="button"
            role="switch"
            aria-checked={selectedField.required}
            onClick={() => updateFieldRequired(selectedField.id, !selectedField.required)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
              selectedField.required ? "bg-blue-600" : "bg-gray-200"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                selectedField.required ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        {/* Help Text */}
        <div className="flex flex-col gap-1 mb-3">
          <label
            htmlFor={`field-help-text-${selectedField.id}`}
            className="text-sm font-medium text-gray-700"
          >
            Help Text
          </label>
          <input
            id={`field-help-text-${selectedField.id}`}
            type="text"
            value={selectedField.help_text ?? ""}
            onChange={(e) => updateFieldHelpText(selectedField.id, e.target.value)}
            maxLength={MAX_HELP_TEXT_LENGTH}
            placeholder="Optional help text for data collectors"
            aria-describedby={helpTextError ? `field-help-text-error-${selectedField.id}` : undefined}
            aria-invalid={helpTextError ? true : undefined}
            className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              helpTextError ? "border-red-500" : "border-gray-300"
            }`}
          />
          <span className="text-xs text-gray-400">
            {helpTextLength}/{MAX_HELP_TEXT_LENGTH} characters
          </span>
          {helpTextError && (
            <p
              id={`field-help-text-error-${selectedField.id}`}
              className="text-xs text-red-600"
              role="alert"
            >
              {helpTextError}
            </p>
          )}
        </div>

        {/* Default Value */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`field-default-value-${selectedField.id}`}
            className="text-sm font-medium text-gray-700"
          >
            Default Value
          </label>
          <input
            id={`field-default-value-${selectedField.id}`}
            type="text"
            value={selectedField.default_value ?? ""}
            onChange={(e) => updateFieldDefaultValue(selectedField.id, e.target.value)}
            placeholder={getDefaultValuePlaceholder(selectedField.type)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Type-Specific Configuration */}
      <div className="border-t border-gray-200 pt-4">
        <TypeSpecificPanel fieldId={selectedField.id} fieldType={selectedField.type} />
      </div>
    </div>
  );
}

/**
 * Routes to the appropriate type-specific configuration panel.
 */
function TypeSpecificPanel({ fieldId, fieldType }: { fieldId: string; fieldType: FieldType }) {
  switch (fieldType) {
    case "Text":
      return <TextConfigPanel fieldId={fieldId} />;
    case "Float":
      return <FloatConfigPanel fieldId={fieldId} />;
    case "Integer":
      return <IntegerConfigPanel fieldId={fieldId} />;
    case "Date":
      return <DateConfigPanel fieldId={fieldId} />;
    case "Boolean":
      return <BooleanConfigPanel fieldId={fieldId} />;
    default:
      return null;
  }
}

/**
 * Returns a placeholder string for the Default Value input based on field type.
 */
function getDefaultValuePlaceholder(fieldType: FieldType): string {
  switch (fieldType) {
    case "Text":
      return "Default text value";
    case "Float":
      return "e.g., 7.0";
    case "Integer":
      return "e.g., 100";
    case "Date":
      return "e.g., 2024-01-01";
    case "Boolean":
      return '"true" or "false"';
    default:
      return "Default value";
  }
}
