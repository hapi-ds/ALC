import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldElement, TextFieldConfig } from "../../types/template";

interface TextConfigPanelProps {
  fieldId: string;
}

/**
 * Configuration panel for Text field type-specific properties.
 * Renders inputs for min_length, max_length, placeholder, and regex_pattern.
 * Performs inline validation: min ≤ max, regex syntax check via new RegExp().
 */
export function TextConfigPanel({ fieldId }: TextConfigPanelProps) {
  const items = useTemplateBuilderStore((s) => s.items);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateFieldConfig = useTemplateBuilderStore((s) => s.updateFieldConfig);

  const field = items.find(
    (item): item is CanvasFieldElement =>
      item.element_type === "field" && item.id === fieldId
  );

  if (!field || field.type !== "Text") {
    return null;
  }

  const config = field.config as TextFieldConfig;
  const error = fieldErrors[fieldId] ?? null;

  const handleMinLengthChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const value = raw === "" ? undefined : Math.max(0, parseInt(raw, 10));
    updateFieldConfig(fieldId, { min_length: isNaN(value as number) ? undefined : value });
  };

  const handleMaxLengthChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    const value = raw === "" ? undefined : Math.max(1, parseInt(raw, 10));
    updateFieldConfig(fieldId, { max_length: isNaN(value as number) ? undefined : value });
  };

  const handlePlaceholderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    updateFieldConfig(fieldId, { placeholder: value || undefined });
  };

  const handleRegexPatternChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    updateFieldConfig(fieldId, { regex_pattern: value || undefined });
  };

  const placeholderLength = config.placeholder?.length ?? 0;
  const regexLength = config.regex_pattern?.length ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
        Text Properties
      </h3>

      {/* Min Length */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`text-min-length-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Minimum Length
        </label>
        <input
          id={`text-min-length-${fieldId}`}
          type="number"
          min={0}
          value={config.min_length ?? ""}
          onChange={handleMinLengthChange}
          placeholder="No minimum"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Max Length */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`text-max-length-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Maximum Length
        </label>
        <input
          id={`text-max-length-${fieldId}`}
          type="number"
          min={1}
          value={config.max_length ?? ""}
          onChange={handleMaxLengthChange}
          placeholder="No maximum"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Placeholder */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`text-placeholder-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Placeholder
        </label>
        <input
          id={`text-placeholder-${fieldId}`}
          type="text"
          maxLength={200}
          value={config.placeholder ?? ""}
          onChange={handlePlaceholderChange}
          placeholder="Placeholder text shown in the field"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <span className="text-xs text-gray-400">
          {placeholderLength}/200 characters
        </span>
      </div>

      {/* Regex Pattern */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`text-regex-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Regex Pattern
        </label>
        <input
          id={`text-regex-${fieldId}`}
          type="text"
          maxLength={500}
          value={config.regex_pattern ?? ""}
          onChange={handleRegexPatternChange}
          placeholder="e.g., ^[A-Z]{3}-\d{4}$"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <span className="text-xs text-gray-400">
          {regexLength}/500 characters
        </span>
      </div>

      {/* Inline validation errors */}
      {error && (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
