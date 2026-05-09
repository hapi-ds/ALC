import type { FloatFieldConfig } from "@/types/template";

export interface FloatFieldProps {
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
  config: FloatFieldConfig;
}

/**
 * Float input field component for report data entry.
 * Renders a numeric input accepting decimal values with decimal_precision,
 * unit_label display, label, required indicator, help text, and error display.
 */
export function FloatField({
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
}: FloatFieldProps) {
  const inputId = `field-${fieldUuid}`;
  const helpId = helpText ? `${inputId}-help` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;

  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  // Calculate step based on decimal_precision
  const step =
    config.decimal_precision !== undefined
      ? (1 / Math.pow(10, config.decimal_precision)).toString()
      : "any";

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={inputId} className="text-sm font-medium text-gray-700">
        {label}
        {required && (
          <span className="ml-0.5 text-red-500" aria-hidden="true">
            *
          </span>
        )}
      </label>

      <div className="flex items-center gap-2">
        <input
          id={inputId}
          type="number"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          disabled={disabled}
          step={step}
          min={config.min_value}
          max={config.max_value}
          required={required}
          aria-required={required}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={`flex-1 rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 ${
            error ? "border-red-500" : "border-gray-300"
          }`}
        />

        {config.unit_label && (
          <span className="shrink-0 text-sm text-gray-600">
            {config.unit_label}
          </span>
        )}
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
