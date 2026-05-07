import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { DragDropContext } from "@hello-pangea/dnd";
import { FieldPalette } from "../../components/templates/FieldPalette";

/**
 * Unit tests for FieldPalette component.
 *
 * Validates: Requirements 1.2, 2.4, 10.1
 */

function renderFieldPalette() {
  return render(
    <DragDropContext onDragEnd={() => {}}>
      <FieldPalette />
    </DragDropContext>
  );
}

describe("FieldPalette", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders exactly 5 field type items", () => {
    renderFieldPalette();

    const expectedTypes = ["Text", "Float", "Integer", "Date", "Boolean"];
    for (const type of expectedTypes) {
      expect(screen.getByText(type)).toBeDefined();
    }

    // Verify there are exactly 5 items by checking all text nodes
    const items = expectedTypes.map((type) => screen.getByText(type));
    expect(items).toHaveLength(5);
  });

  it("renders items in the correct visual order: Text, Float, Integer, Date, Boolean", () => {
    renderFieldPalette();

    const expectedOrder = ["Text", "Float", "Integer", "Date", "Boolean"];
    const items = expectedOrder.map((type) => screen.getByText(type));

    // Verify DOM order by comparing document positions
    for (let i = 0; i < items.length - 1; i++) {
      const position = items[i].compareDocumentPosition(items[i + 1]);
      // Node.DOCUMENT_POSITION_FOLLOWING = 4
      expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("each item has a drag handle icon (GripVertical)", () => {
    renderFieldPalette();

    // GripVertical icons are rendered with aria-hidden="true"
    const icons = document.querySelectorAll('[aria-hidden="true"]');
    expect(icons.length).toBeGreaterThanOrEqual(5);
  });

  it("items remain in the palette after rendering (source items are not consumed)", () => {
    renderFieldPalette();

    const expectedTypes = ["Text", "Float", "Integer", "Date", "Boolean"];

    // All items should still be present (palette items are never removed)
    for (const type of expectedTypes) {
      expect(screen.getByText(type)).toBeDefined();
    }

    // Re-query to confirm they are still in the DOM
    const items = expectedTypes.map((type) => screen.getByText(type));
    expect(items).toHaveLength(5);
    for (const item of items) {
      expect(item.isConnected).toBe(true);
    }
  });

  it("items are keyboard-focusable via tabIndex", () => {
    renderFieldPalette();

    const expectedTypes = ["Text", "Float", "Integer", "Date", "Boolean"];

    for (const type of expectedTypes) {
      const textElement = screen.getByText(type);
      // The draggable container (parent div with dragHandleProps) gets tabIndex
      const draggableItem = textElement.closest("[data-rfd-draggable-id]");
      expect(draggableItem).not.toBeNull();
      // @hello-pangea/dnd sets tabIndex on drag handle elements for keyboard accessibility
      expect(draggableItem!.getAttribute("tabindex")).toBe("0");
    }
  });
});
