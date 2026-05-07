import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { DragDropContext } from "@hello-pangea/dnd";
import { BuilderCanvas } from "../../components/templates/BuilderCanvas";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";

/**
 * Unit tests for BuilderCanvas component.
 *
 * Validates: Requirements 1.3, 1.4, 3.2, 4.1, 4.2, 4.5, 4.6, 4.7, 5.5
 */

function renderBuilderCanvas() {
  return render(
    <DragDropContext onDragEnd={() => {}}>
      <BuilderCanvas />
    </DragDropContext>
  );
}

function resetStore() {
  useTemplateBuilderStore.setState({
    fields: [],
    selectedFieldId: null,
    fieldErrors: {},
    templateName: "",
    isSaving: false,
    saveError: null,
    saveSuccess: false,
    savedTemplate: null,
    isDirty: false,
    nameError: null,
  });
}

describe("BuilderCanvas", () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows placeholder message when fields array is empty", () => {
    renderBuilderCanvas();

    expect(
      screen.getByText("Drag fields from the palette to build your template")
    ).toBeDefined();
  });

  it("renders CanvasField items in ascending fieldOrder sequence", () => {
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-3", label: "Third", type: "Boolean", fieldOrder: 2 },
        { id: "field-1", label: "First", type: "Text", fieldOrder: 0 },
        { id: "field-2", label: "Second", type: "Integer", fieldOrder: 1 },
      ],
    });

    renderBuilderCanvas();

    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("First");
    expect(items[1].textContent).toContain("Second");
    expect(items[2].textContent).toContain("Third");
  });

  it("applies selection highlight to the selected field", () => {
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-1", label: "Alpha", type: "Text", fieldOrder: 0 },
        { id: "field-2", label: "Beta", type: "Float", fieldOrder: 1 },
      ],
      selectedFieldId: "field-2",
    });

    renderBuilderCanvas();

    const items = screen.getAllByRole("listitem");

    // The selected field (field-2, "Beta") should have the blue highlight classes
    expect(items[1].className).toContain("border-blue-500");
    expect(items[1].className).toContain("bg-blue-50");

    // The unselected field should not have the blue highlight
    expect(items[0].className).not.toContain("border-blue-500");
    expect(items[0].className).not.toContain("bg-blue-50");
  });

  it("shows placeholder again when last field is removed", () => {
    // Start with one field
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "Only", type: "Date", fieldOrder: 0 }],
    });

    const { unmount } = renderBuilderCanvas();

    // Verify field is rendered
    expect(screen.getAllByRole("listitem")).toHaveLength(1);

    unmount();

    // Remove the field via store
    useTemplateBuilderStore.setState({ fields: [] });

    // Re-render with empty fields
    renderBuilderCanvas();

    expect(
      screen.getByText("Drag fields from the palette to build your template")
    ).toBeDefined();
  });

  it("renders correct number of fields", () => {
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-1", label: "Name", type: "Text", fieldOrder: 0 },
        { id: "field-2", label: "Age", type: "Integer", fieldOrder: 1 },
        { id: "field-3", label: "Active", type: "Boolean", fieldOrder: 2 },
        { id: "field-4", label: "Start Date", type: "Date", fieldOrder: 3 },
      ],
    });

    renderBuilderCanvas();

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
  });
});
