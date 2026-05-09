import type { DateFieldConfig } from "@/types/template";

export interface DateFieldProps {
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
  config: DateFieldConfig;
}

/**
 * Date input field component for report data entry.
 * Renders a date picker with the configured date_format (defaults to YYYY-MM-DD).
 * Includes label, required indicator, help text, and error display.
 */
export function DateField({
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
}: DateFieldProps) {
  const inputId = `field-${fieldUuid}`;
  const helpId = helpText ? `${inputId}-help` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;

  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  const dateFormat = config.date_format ?? "YYYY-MM-DD";

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

      <input
        id={inputId}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        disabled={disabled}
        min={config.min_date}
        max={config.max_date}
        required={required}
        aria-required={required}
        aria-invalid={!!error}
        aria-describedby={describedBy}
        className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50 ${
          error ? "border-red-500" : "border-gray-300"
        }`}
      />

      {helpText && (
        <p id={helpId} className="text-xs text-gray-500">
          {helpText}
        </p>
      )}

      {!helpText && (
        <p className="text-xs text-gray-400">
          Format: {dateFormat}
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
