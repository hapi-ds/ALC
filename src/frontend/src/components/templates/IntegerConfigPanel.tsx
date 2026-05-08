import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldElement, IntegerFieldConfig } from "../../types/template";

interface IntegerConfigPanelProps {
  fieldId: string;
}

/**
 * Configuration panel for Integer field type.
 * Renders inputs for min_value, max_value, step_size, and unit_label
 * with inline validation from the store's fieldErrors.
 */
export function IntegerConfigPanel({ fieldId }: IntegerConfigPanelProps) {
  const items = useTemplateBuilderStore((s) => s.items);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateFieldConfig = useTemplateBuilderStore((s) => s.updateFieldConfig);

  const field = items.find(
    (item): item is CanvasFieldElement =>
      item.element_type === "field" && item.id === fieldId
  );

  if (!field || field.type !== "Integer") {
    return null;
  }

  const config = field.config as IntegerFieldConfig;
  const error = fieldErrors[fieldId] ?? null;
  const errorId = `integer-config-error-${fieldId}`;

  const handleMinValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const value = raw === "" ? undefined : parseInt(raw, 10);
    if (raw !== "" && isNaN(value as number)) return;
    updateFieldConfig(fieldId, { min_value: value } as Partial<IntegerFieldConfig>);
  };

  const handleMaxValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const value = raw === "" ? undefined : parseInt(raw, 10);
    if (raw !== "" && isNaN(value as number)) return;
    updateFieldConfig(fieldId, { max_value: value } as Partial<IntegerFieldConfig>);
  };

  const handleStepSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const value = raw === "" ? undefined : parseInt(raw, 10);
    if (raw !== "" && isNaN(value as number)) return;
    updateFieldConfig(fieldId, { step_size: value } as Partial<IntegerFieldConfig>);
  };

  const handleUnitLabelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    updateFieldConfig(fieldId, { unit_label: value || undefined } as Partial<IntegerFieldConfig>);
  };

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-gray-700">Integer Properties</h3>

      {/* Min Value */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`integer-min-value-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Minimum Value
        </label>
        <input
          id={`integer-min-value-${fieldId}`}
          type="number"
          value={config.min_value ?? ""}
          onChange={handleMinValueChange}
          placeholder="No minimum"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Max Value */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`integer-max-value-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Maximum Value
        </label>
        <input
          id={`integer-max-value-${fieldId}`}
          type="number"
          value={config.max_value ?? ""}
          onChange={handleMaxValueChange}
          placeholder="No maximum"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Step Size */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`integer-step-size-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Step Size
        </label>
        <input
          id={`integer-step-size-${fieldId}`}
          type="number"
          min={1}
          value={config.step_size ?? 1}
          onChange={handleStepSizeChange}
          placeholder="1"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500">Must be a positive integer</p>
      </div>

      {/* Unit Label */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`integer-unit-label-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Unit Label
        </label>
        <input
          id={`integer-unit-label-${fieldId}`}
          type="text"
          maxLength={50}
          value={config.unit_label ?? ""}
          onChange={handleUnitLabelChange}
          placeholder='e.g., "units", "kg", "items"'
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500">Max 50 characters</p>
      </div>

      {/* Inline validation errors */}
      {error && (
        <p id={errorId} className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
