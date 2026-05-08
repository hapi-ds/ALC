import { useState } from "react";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldElement, BooleanFieldConfig } from "../../types/template";

interface BooleanConfigPanelProps {
  fieldId: string;
}

interface LabelErrors {
  true_label: string | null;
  false_label: string | null;
}

function validateLabel(value: string): string | null {
  if (value.length === 0) {
    return "Label is required";
  }
  if (value.length > 50) {
    return "Label must not exceed 50 characters";
  }
  return null;
}

export function BooleanConfigPanel({ fieldId }: BooleanConfigPanelProps) {
  const items = useTemplateBuilderStore((s) => s.items);
  const updateFieldConfig = useTemplateBuilderStore((s) => s.updateFieldConfig);

  const field = items.find(
    (item): item is CanvasFieldElement =>
      item.element_type === "field" && item.id === fieldId
  );

  const config = (field?.config ?? {}) as BooleanFieldConfig;
  const trueLabel = config.true_label ?? "True";
  const falseLabel = config.false_label ?? "False";

  const [errors, setErrors] = useState<LabelErrors>({
    true_label: null,
    false_label: null,
  });

  const handleTrueLabelChange = (value: string) => {
    const error = validateLabel(value);
    setErrors((prev) => ({ ...prev, true_label: error }));
    updateFieldConfig(fieldId, { true_label: value } as Partial<BooleanFieldConfig>);
  };

  const handleFalseLabelChange = (value: string) => {
    const error = validateLabel(value);
    setErrors((prev) => ({ ...prev, false_label: error }));
    updateFieldConfig(fieldId, { false_label: value } as Partial<BooleanFieldConfig>);
  };

  if (!field) {
    return null;
  }

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-gray-700">Boolean Configuration</h3>

      {/* True Label */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`boolean-true-label-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          True Label
        </label>
        <input
          id={`boolean-true-label-${fieldId}`}
          type="text"
          value={trueLabel}
          maxLength={50}
          onChange={(e) => handleTrueLabelChange(e.target.value)}
          aria-describedby={errors.true_label ? `boolean-true-label-error-${fieldId}` : undefined}
          aria-invalid={errors.true_label ? true : undefined}
          className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.true_label ? "border-red-500" : "border-gray-300"
          }`}
        />
        {errors.true_label && (
          <p
            id={`boolean-true-label-error-${fieldId}`}
            className="text-xs text-red-600"
            role="alert"
          >
            {errors.true_label}
          </p>
        )}
      </div>

      {/* False Label */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`boolean-false-label-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          False Label
        </label>
        <input
          id={`boolean-false-label-${fieldId}`}
          type="text"
          value={falseLabel}
          maxLength={50}
          onChange={(e) => handleFalseLabelChange(e.target.value)}
          aria-describedby={errors.false_label ? `boolean-false-label-error-${fieldId}` : undefined}
          aria-invalid={errors.false_label ? true : undefined}
          className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.false_label ? "border-red-500" : "border-gray-300"
          }`}
        />
        {errors.false_label && (
          <p
            id={`boolean-false-label-error-${fieldId}`}
            className="text-xs text-red-600"
            role="alert"
          >
            {errors.false_label}
          </p>
        )}
      </div>
    </div>
  );
}
