import { useDeferredValue } from "react";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type {
  CanvasItem,
  CanvasFieldElement,
  CanvasContentBlockElement,
  TextFieldConfig,
  FloatFieldConfig,
  IntegerFieldConfig,
  DateFieldConfig,
  BooleanFieldConfig,
} from "../../types/template";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface PdfPreviewPanelProps {
  /** Whether the preview panel is visible */
  isOpen: boolean;
  /** Callback to close the panel */
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Sub-components for rendering field config hints
// ---------------------------------------------------------------------------

function TextFieldHints({ config }: { config: TextFieldConfig }) {
  const hints: string[] = [];
  if (config.max_length !== undefined) {
    hints.push(`max ${config.max_length} chars`);
  }
  if (hints.length === 0) return null;
  return <span className="text-xs text-gray-400 italic">{hints.join(" · ")}</span>;
}

function FloatFieldHints({ config }: { config: FloatFieldConfig }) {
  const hints: string[] = [];
  if (config.decimal_precision !== undefined) {
    hints.push(`${config.decimal_precision} decimal places`);
  }
  if (config.min_value !== undefined && config.max_value !== undefined) {
    hints.push(`Range: ${config.min_value}–${config.max_value}`);
  }
  if (hints.length === 0) return null;
  return <span className="text-xs text-gray-400 italic">{hints.join(" · ")}</span>;
}

function IntegerFieldHints({ config }: { config: IntegerFieldConfig }) {
  const hints: string[] = [];
  if (config.min_value !== undefined && config.max_value !== undefined) {
    hints.push(`Range: ${config.min_value}–${config.max_value}`);
  }
  if (hints.length === 0) return null;
  return <span className="text-xs text-gray-400 italic">{hints.join(" · ")}</span>;
}

function DateFieldHints({ config }: { config: DateFieldConfig }) {
  if (!config.date_format) return null;
  return <span className="text-xs text-gray-400 italic">{config.date_format}</span>;
}

function BooleanFieldHints({ config }: { config: BooleanFieldConfig }) {
  const trueLabel = config.true_label || "True";
  const falseLabel = config.false_label || "False";
  return (
    <span className="text-xs text-gray-400 italic">
      {trueLabel} / {falseLabel}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Field preview renderer
// ---------------------------------------------------------------------------

function FieldPreview({ field }: { field: CanvasFieldElement }) {
  const config = field.config;

  // Determine unit label for numeric fields
  const unitLabel =
    field.type === "Float"
      ? (config as FloatFieldConfig).unit_label
      : field.type === "Integer"
        ? (config as IntegerFieldConfig).unit_label
        : undefined;

  return (
    <div className="mb-4">
      {/* Label row */}
      <div className="flex items-baseline gap-1 mb-1">
        <span className="text-sm font-medium text-gray-800">
          {field.label}
        </span>
        {field.required && (
          <span className="text-red-500 font-bold" aria-label="required">*</span>
        )}
        {unitLabel && (
          <span className="text-xs text-gray-500 ml-1">({unitLabel})</span>
        )}
      </div>

      {/* Help text */}
      {field.help_text && (
        <p className="text-xs text-gray-500 mb-1">{field.help_text}</p>
      )}

      {/* Input representation */}
      <div className="border border-gray-300 rounded px-2 py-1.5 bg-white text-sm text-gray-400 min-h-[32px] flex items-center gap-2">
        {field.default_value ? (
          <span className="text-gray-600">{field.default_value}</span>
        ) : (
          <span className="text-gray-300">
            {getFieldPlaceholder(field)}
          </span>
        )}
      </div>

      {/* Config hints */}
      <div className="mt-1">
        {field.type === "Text" && <TextFieldHints config={config as TextFieldConfig} />}
        {field.type === "Float" && <FloatFieldHints config={config as FloatFieldConfig} />}
        {field.type === "Integer" && <IntegerFieldHints config={config as IntegerFieldConfig} />}
        {field.type === "Date" && <DateFieldHints config={config as DateFieldConfig} />}
        {field.type === "Boolean" && <BooleanFieldHints config={config as BooleanFieldConfig} />}
      </div>
    </div>
  );
}

/**
 * Returns a placeholder string for the field input representation.
 */
function getFieldPlaceholder(field: CanvasFieldElement): string {
  switch (field.type) {
    case "Text": {
      const tc = field.config as TextFieldConfig;
      return tc.placeholder || "Enter text...";
    }
    case "Float":
      return "0.00";
    case "Integer":
      return "0";
    case "Date": {
      const dc = field.config as DateFieldConfig;
      return dc.date_format || "YYYY-MM-DD";
    }
    case "Boolean":
      return "Select...";
    default:
      return "Enter value...";
  }
}

// ---------------------------------------------------------------------------
// Content block preview renderer
// ---------------------------------------------------------------------------

function ContentBlockPreview({ block }: { block: CanvasContentBlockElement }) {
  switch (block.content_type) {
    case "heading_h1":
      return (
        <h2 className="text-xl font-bold text-gray-900 mb-3 mt-4">
          {block.text || "Section Title"}
        </h2>
      );
    case "heading_h2":
      return (
        <h3 className="text-lg font-semibold text-gray-800 mb-2 mt-3">
          {block.text || "Section Title"}
        </h3>
      );
    case "heading_h3":
      return (
        <h4 className="text-base font-semibold text-gray-700 mb-2 mt-2">
          {block.text || "Section Title"}
        </h4>
      );
    case "paragraph":
      return (
        <p className="text-sm text-gray-600 mb-3 leading-relaxed">
          {block.text || "Enter instructions or description here"}
        </p>
      );
    case "divider":
      return <hr className="border-t border-gray-300 my-4" />;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Item preview dispatcher
// ---------------------------------------------------------------------------

function ItemPreview({ item }: { item: CanvasItem }) {
  if (item.element_type === "field") {
    return <FieldPreview field={item as CanvasFieldElement} />;
  }
  return <ContentBlockPreview block={item as CanvasContentBlockElement} />;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * PdfPreviewPanel renders a live HTML/CSS approximation of the PDF layout.
 * It subscribes to the template builder store and uses React 19's useDeferredValue
 * to avoid excessive re-renders during rapid typing (achieving ~500ms debounce).
 *
 * The panel opens via a "Preview" toggle button and renders as a right-side panel.
 * Closing the panel preserves all builder state unchanged.
 */
export function PdfPreviewPanel({ isOpen, onClose }: PdfPreviewPanelProps) {
  // Subscribe to store state
  const items = useTemplateBuilderStore((s) => s.items);
  const templateName = useTemplateBuilderStore((s) => s.templateName);
  const activeVersion = useTemplateBuilderStore((s) => s.activeVersion);

  // Use React 19's useDeferredValue for debounce-like behavior.
  // This defers re-renders during rapid state changes (typing),
  // allowing React to prioritize user input over preview updates.
  const deferredItems = useDeferredValue(items);
  const deferredTemplateName = useDeferredValue(templateName);

  if (!isOpen) return null;

  // Sort items by fieldOrder for rendering
  const sortedItems = [...deferredItems].sort(
    (a, b) => a.fieldOrder - b.fieldOrder
  );

  // Determine version display
  const versionDisplay = activeVersion
    ? `v${activeVersion.version_number}`
    : "Draft";

  return (
    <div
      className="flex h-full flex-col bg-white"
      role="complementary"
      aria-label="PDF Preview"
    >
      {/* Panel header */}
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-700">PDF Preview</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          aria-label="Close preview"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* Preview content — scrollable */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* PDF page approximation */}
        <div className="mx-auto max-w-md rounded border border-gray-200 bg-white p-6 shadow-sm">
          {/* Header */}
          <div className="mb-6 border-b border-gray-200 pb-4">
            <h1 className="text-lg font-bold text-gray-900">
              {deferredTemplateName || "Untitled Template"}
            </h1>
            <span className="text-xs text-gray-500">{versionDisplay}</span>
          </div>

          {/* Items */}
          {sortedItems.length === 0 ? (
            <p className="text-sm text-gray-400 italic">
              No fields or content blocks added yet.
            </p>
          ) : (
            sortedItems.map((item) => (
              <ItemPreview key={item.id} item={item} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
