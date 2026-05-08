import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldElement, DateFieldConfig } from "../../types/template";

interface DateConfigPanelProps {
  fieldId: string;
}

/** Available date format options for the dropdown */
const DATE_FORMAT_OPTIONS = [
  "YYYY-MM-DD",
  "DD/MM/YYYY",
  "MM/DD/YYYY",
  "DD-MMM-YYYY",
] as const;

/**
 * Configuration panel for Date field type-specific properties.
 * Renders inputs for min_date (ISO 8601), max_date (ISO 8601),
 * and date_format (dropdown selection).
 * Performs inline validation: valid ISO 8601 dates, min ≤ max.
 */
export function DateConfigPanel({ fieldId }: DateConfigPanelProps) {
  const items = useTemplateBuilderStore((s) => s.items);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateFieldConfig = useTemplateBuilderStore((s) => s.updateFieldConfig);

  const field = items.find(
    (item): item is CanvasFieldElement =>
      item.element_type === "field" && item.id === fieldId
  );

  if (!field || field.type !== "Date") {
    return null;
  }

  const config = field.config as DateFieldConfig;
  const error = fieldErrors[fieldId] ?? null;
  const errorId = `date-config-error-${fieldId}`;

  const handleMinDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    updateFieldConfig(fieldId, {
      min_date: value || undefined,
    } as Partial<DateFieldConfig>);
  };

  const handleMaxDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    updateFieldConfig(fieldId, {
      max_date: value || undefined,
    } as Partial<DateFieldConfig>);
  };

  const handleDateFormatChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value as DateFieldConfig["date_format"];
    updateFieldConfig(fieldId, {
      date_format: value || undefined,
    } as Partial<DateFieldConfig>);
  };

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-gray-700">Date Properties</h3>

      {/* Min Date */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`date-min-date-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Minimum Date
        </label>
        <input
          id={`date-min-date-${fieldId}`}
          type="date"
          value={config.min_date ?? ""}
          onChange={handleMinDateChange}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500">
          ISO 8601 format (YYYY-MM-DD)
        </p>
      </div>

      {/* Max Date */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`date-max-date-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Maximum Date
        </label>
        <input
          id={`date-max-date-${fieldId}`}
          type="date"
          value={config.max_date ?? ""}
          onChange={handleMaxDateChange}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500">
          ISO 8601 format (YYYY-MM-DD)
        </p>
      </div>

      {/* Date Format */}
      <div className="flex flex-col gap-1">
        <label
          htmlFor={`date-format-${fieldId}`}
          className="text-sm font-medium text-gray-700"
        >
          Date Format
        </label>
        <select
          id={`date-format-${fieldId}`}
          value={config.date_format ?? "YYYY-MM-DD"}
          onChange={handleDateFormatChange}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {DATE_FORMAT_OPTIONS.map((format) => (
            <option key={format} value={format}>
              {format}
            </option>
          ))}
        </select>
        <p className="text-xs text-gray-500">
          Display format for the date field in the PDF
        </p>
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
