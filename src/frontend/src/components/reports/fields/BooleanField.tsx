import type { BooleanFieldConfig } from "@/types/template";

export interface BooleanFieldProps {
  fieldUuid: string;
  label: string;
  required: boolean;
  helpText: string | null;
  defaultValue: string | null;
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error: string | null;
  disabled?: boolean;
  config: BooleanFieldConfig;
}

/**
 * Boolean field component for report data entry.
 * Renders a checkbox/toggle with configurable true_label and false_label.
 * Includes label, required indicator, help text, and error display.
 */
export function BooleanField({
  fieldUuid,
  label,
  required,
  helpText,
  value,
  onChange,
  onBlur,
  error,
  disabled = false,
  config,
}: BooleanFieldProps) {
  const inputId = `field-${fieldUuid}`;
  const helpId = helpText ? `${inputId}-help` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;

  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  const trueLabel = config.true_label ?? "True";
  const falseLabel = config.false_label ?? "False";

  const isChecked = value === "true";

  const handleChange = () => {
    onChange(isChecked ? "false" : "true");
  };

  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm font-medium text-gray-700">
        {label}
        {required && (
          <span className="ml-0.5 text-red-500" aria-hidden="true">
            *
          </span>
        )}
      </span>

      <div className="flex items-center gap-3">
        <label
          htmlFor={inputId}
          className="flex cursor-pointer items-center gap-2"
        >
          <input
            id={inputId}
            type="checkbox"
            checked={isChecked}
            onChange={handleChange}
            onBlur={onBlur}
            disabled={disabled}
            aria-required={required}
            aria-invalid={!!error}
            aria-describedby={describedBy}
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
          />
          <span className="text-sm text-gray-700">
            {isChecked ? trueLabel : falseLabel}
          </span>
        </label>
      </div>

      {helpText && (
        <p id={helpId} className="text-xs text-gray-500">
          {helpText}
        </p>
      )}

      {error && (
        <p id={errorId} className="text-xs text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
