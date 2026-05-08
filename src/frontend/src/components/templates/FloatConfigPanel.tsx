import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldElement, FloatFieldConfig } from "../../types/template";

interface FloatConfigPanelProps {
  fieldId: string;
}

export function FloatConfigPanel({ fieldId }: FloatConfigPanelProps) {
  const items = useTemplateBuilderStore((s) => s.items);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateFieldConfig = useTemplateBuilderStore((s) => s.updateFieldConfig);

  const field = items.find(
    (item): item is CanvasFieldElement =>
      item.element_type === "field" && item.id === fieldId
  );

  if (!field) {
    return null;
  }

  const config = field.config as FloatFieldConfig;
  const error = fieldErrors[fieldId] ?? null;
  const errorId = `float-config-error-${fieldId}`;

  const handleDecimalPrecisionChange = (value: string) => {
    const parsed = value === "" ? undefined : Number(value);
    updateFieldConfig(fieldId, { decimal_precision: parsed } as Partial<FloatFieldConfig>);
  };

  const handleMinValueChange = (value: string) => {
    const parsed = value === "" ? undefined : Number(value);
    updateFieldConfig(fieldId, { min_value: parsed } as Partial<FloatFieldConfig>);
  };

  const handleMaxValueChange = (value: string) => {
    const parsed = value === "" ? undefined : Number(value);
    updateFieldConfig(fieldId, { max_value: parsed } as Partial<FloatFieldConfig>);
  };

  const handleUnitLabelChange = (value: string) => {
    updateFieldConfig(fieldId, { unit_label: value || undefined } as Partial<FloatFieldConfig>);
  };

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold uppercase text-gray-500">
        Float Configuration
      </h3>

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`decimal-precision-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Decimal Precision
        </label>
        <input
          id={`decimal-precision-${fieldId}`}
          type="number"
          min={0}
          max={10}
          step={1}
          value={config.decimal_precision ?? ""}
          onChange={(e) => handleDecimalPrecisionChange(e.target.value)}
          placeholder="0–10"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500">
          Number of decimal places (0–10)
        </p>
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`min-value-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Minimum Value
        </label>
        <input
          id={`min-value-${fieldId}`}
          type="number"
          step="any"
          value={config.min_value ?? ""}
          onChange={(e) => handleMinValueChange(e.target.value)}
          placeholder="No minimum"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`max-value-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Maximum Value
        </label>
        <input
          id={`max-value-${fieldId}`}
          type="number"
          step="any"
          value={config.max_value ?? ""}
          onChange={(e) => handleMaxValueChange(e.target.value)}
          placeholder="No maximum"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label
          htmlFor={`unit-label-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Unit Label
        </label>
        <input
          id={`unit-label-${fieldId}`}
          type="text"
          maxLength={50}
          value={config.unit_label ?? ""}
          onChange={(e) => handleUnitLabelChange(e.target.value)}
          placeholder='e.g., mg/L, °C, pH'
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500">
          Max 50 characters
        </p>
      </div>

      {error && (
        <p id={errorId} className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
