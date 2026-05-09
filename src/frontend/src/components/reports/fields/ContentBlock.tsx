import type { ContentBlockType } from "@/types/template";

export interface ContentBlockProps {
  blockType: ContentBlockType;
  text: string | null;
}

/**
 * Non-interactive content block element for report forms.
 * Renders headings, paragraphs, or dividers based on block_type.
 */
export function ContentBlock({ blockType, text }: ContentBlockProps) {
  switch (blockType) {
    case "heading_h1":
      return (
        <h2 className="text-xl font-bold text-gray-900 mt-6 mb-2">
          {text}
        </h2>
      );
    case "heading_h2":
      return (
        <h3 className="text-lg font-semibold text-gray-800 mt-4 mb-1">
          {text}
        </h3>
      );
    case "heading_h3":
      return (
        <h4 className="text-base font-medium text-gray-700 mt-3 mb-1">
          {text}
        </h4>
      );
    case "paragraph":
      return (
        <p className="text-sm text-gray-600 my-2">
          {text}
        </p>
      );
    case "divider":
      return <hr className="my-4 border-gray-200" aria-hidden="true" />;
    default:
      return null;
  }
}
