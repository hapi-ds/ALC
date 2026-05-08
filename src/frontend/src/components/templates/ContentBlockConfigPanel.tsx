import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasContentBlockElement } from "../../types/template";

interface ContentBlockConfigPanelProps {
  blockId: string;
}

/**
 * Configuration panel for content block elements.
 * - For headings (H1/H2/H3): renders text input (max 200 chars) + heading level dropdown.
 * - For paragraphs: renders multi-line textarea (max 2000 chars).
 * - For dividers: shows "No configurable properties" message.
 * Displays inline validation errors from the store's fieldErrors.
 */
export function ContentBlockConfigPanel({ blockId }: ContentBlockConfigPanelProps) {
  const items = useTemplateBuilderStore((s) => s.items);
  const fieldErrors = useTemplateBuilderStore((s) => s.fieldErrors);
  const updateContentBlockText = useTemplateBuilderStore((s) => s.updateContentBlockText);
  const updateContentBlockLevel = useTemplateBuilderStore((s) => s.updateContentBlockLevel);

  const block = items.find(
    (item): item is CanvasContentBlockElement =>
      item.element_type === "content_block" && item.id === blockId
  );

  if (!block) {
    return null;
  }

  const error = fieldErrors[blockId] ?? null;
  const contentType = block.content_type;

  // Divider: no configurable properties
  if (contentType === "divider") {
    return (
      <div className="flex flex-col gap-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Divider Properties
        </h3>
        <p className="text-sm text-gray-500 italic">
          No configurable properties
        </p>
      </div>
    );
  }

  // Heading (H1/H2/H3)
  if (
    contentType === "heading_h1" ||
    contentType === "heading_h2" ||
    contentType === "heading_h3"
  ) {
    const textLength = block.text?.length ?? 0;

    return (
      <div className="flex flex-col gap-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Header Properties
        </h3>

        {/* Header Text */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`header-text-${blockId}`}
            className="text-sm font-medium text-gray-700"
          >
            Header Text
          </label>
          <input
            id={`header-text-${blockId}`}
            type="text"
            maxLength={200}
            value={block.text ?? ""}
            onChange={(e) => updateContentBlockText(blockId, e.target.value)}
            placeholder="Enter header text"
            aria-describedby={error ? `header-text-error-${blockId}` : undefined}
            aria-invalid={error ? true : undefined}
            className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              error ? "border-red-500" : "border-gray-300"
            }`}
          />
          <span className="text-xs text-gray-400">
            {textLength}/200 characters
          </span>
        </div>

        {/* Heading Level Dropdown */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`header-level-${blockId}`}
            className="text-sm font-medium text-gray-700"
          >
            Heading Level
          </label>
          <select
            id={`header-level-${blockId}`}
            value={contentType}
            onChange={(e) =>
              updateContentBlockLevel(
                blockId,
                e.target.value as "heading_h1" | "heading_h2" | "heading_h3"
              )
            }
            className="rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="heading_h1">H1</option>
            <option value="heading_h2">H2</option>
            <option value="heading_h3">H3</option>
          </select>
        </div>

        {/* Inline validation error */}
        {error && (
          <p
            id={`header-text-error-${blockId}`}
            className="text-xs text-red-600"
            role="alert"
          >
            {error}
          </p>
        )}
      </div>
    );
  }

  // Paragraph
  if (contentType === "paragraph") {
    const textLength = block.text?.length ?? 0;

    return (
      <div className="flex flex-col gap-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
          Paragraph Properties
        </h3>

        {/* Paragraph Text */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor={`paragraph-text-${blockId}`}
            className="text-sm font-medium text-gray-700"
          >
            Paragraph Text
          </label>
          <textarea
            id={`paragraph-text-${blockId}`}
            maxLength={2000}
            rows={5}
            value={block.text ?? ""}
            onChange={(e) => updateContentBlockText(blockId, e.target.value)}
            placeholder="Enter instructions or description here"
            aria-describedby={error ? `paragraph-text-error-${blockId}` : undefined}
            aria-invalid={error ? true : undefined}
            className={`rounded-md border px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y ${
              error ? "border-red-500" : "border-gray-300"
            }`}
          />
          <span className="text-xs text-gray-400">
            {textLength}/2000 characters
          </span>
        </div>

        {/* Inline validation error */}
        {error && (
          <p
            id={`paragraph-text-error-${blockId}`}
            className="text-xs text-red-600"
            role="alert"
          >
            {error}
          </p>
        )}
      </div>
    );
  }

  return null;
}
