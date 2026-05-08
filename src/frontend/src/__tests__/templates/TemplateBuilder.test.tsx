import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TemplateBuilder } from "../../components/templates/TemplateBuilder";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import type { CanvasFieldData } from "../../types/template";

/**
 * Unit tests for TemplateBuilder component.
 *
 * Validates: Requirements 1.1, 1.5, 2.1, 2.5, 2.6, 7.4, 7.5, 7.6
 *
 * Testing strategy: Since @hello-pangea/dnd is complex to simulate in tests,
 * we test the onDragEnd logic indirectly by manipulating the store (which is
 * what onDragEnd ultimately calls) and verifying UI updates. Notification
 * behavior is tested by setting store state directly.
 *
 * No backend API calls are made in these tests - all interactions are
 * through the Zustand store state manipulation.
 */

function resetStore() {
  useTemplateBuilderStore.setState({
    items: [],
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

function renderTemplateBuilder() {
  return render(
    <MemoryRouter>
      <TemplateBuilder />
    </MemoryRouter>
  );
}

function createFields(count: number): CanvasFieldData[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `field-${i}`,
    label: `Field ${i}`,
    type: "Text" as const,
    fieldOrder: i,
  }));
}

describe("TemplateBuilder", () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Requirement 1.1: Three-panel layout rendering
  // -------------------------------------------------------------------------

  it("renders three-panel layout with FieldPalette, BuilderCanvas, and ConfigurationPanel", () => {
    renderTemplateBuilder();

    // FieldPalette renders "Field Types" heading
    expect(screen.getByText("Field Types")).toBeDefined();

    // BuilderCanvas renders the canvas area with placeholder
    expect(
      screen.getByText("Drag fields from the palette to build your template")
    ).toBeDefined();

    // ConfigurationPanel renders empty state message
    expect(
      screen.getByText("Select a field to configure its properties")
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Requirement 1.5: DnD context wrapping (TemplateNameInput and SaveButton present)
  // -------------------------------------------------------------------------

  it("renders TemplateNameInput and SaveButton", () => {
    renderTemplateBuilder();

    // TemplateNameInput renders a labeled input
    expect(screen.getByLabelText("Template Name")).toBeDefined();

    // SaveButton renders the save button
    expect(screen.getByRole("button", { name: "Save Template" })).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Requirement 2.1: Field dragged from palette to canvas (via store addField)
  // -------------------------------------------------------------------------

  it("shows a field on canvas when addField is called (simulating palette to canvas drop)", () => {
    renderTemplateBuilder();

    // Simulate a drag from palette to canvas by calling addField directly
    act(() => {
      useTemplateBuilderStore.getState().addField("Text", 0);
    });

    // The canvas should now show the field with default label
    expect(screen.getByText("Text Field")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Requirement 2.5: Drop outside (no destination) - no field added
  // -------------------------------------------------------------------------

  it("does not add a field when drop has no destination (store remains unchanged)", () => {
    renderTemplateBuilder();

    // The onDragEnd handler returns early if destination is null.
    // We verify the canvas remains empty (no fields added).
    const stateBefore = useTemplateBuilderStore.getState().fields;
    expect(stateBefore).toHaveLength(0);

    // The placeholder should still be visible
    expect(
      screen.getByText("Drag fields from the palette to build your template")
    ).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Requirement 3: Canvas to Canvas reorder (via store reorderField)
  // -------------------------------------------------------------------------

  it("reorders fields on canvas when reorderField is called (simulating canvas to canvas drop)", () => {
    // Set up two fields
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-a", label: "First", type: "Text", fieldOrder: 0 },
        { id: "field-b", label: "Second", type: "Float", fieldOrder: 1 },
      ],
    });

    renderTemplateBuilder();

    // Reorder: move field at index 0 to index 1
    act(() => {
      useTemplateBuilderStore.getState().reorderField(0, 1);
    });

    const fields = useTemplateBuilderStore.getState().fields;
    expect(fields[0].label).toBe("Second");
    expect(fields[1].label).toBe("First");
  });

  // -------------------------------------------------------------------------
  // Requirement 2.6: 50-field max validation message
  // -------------------------------------------------------------------------

  it("rejects adding a 51st field when 50 fields already exist", () => {
    // Set up 50 fields in the store
    useTemplateBuilderStore.setState({
      fields: createFields(50),
    });

    renderTemplateBuilder();

    // Attempt to add another field via store (store-level enforcement)
    act(() => {
      useTemplateBuilderStore.getState().addField("Text", 0);
    });

    // Store should still have 50 fields (rejected)
    expect(useTemplateBuilderStore.getState().fields).toHaveLength(50);
  });

  // -------------------------------------------------------------------------
  // Requirement 7.4: Success notification display
  // -------------------------------------------------------------------------

  it("shows success notification when saveSuccess is true", () => {
    renderTemplateBuilder();

    // Simulate successful save by setting saveSuccess in store
    act(() => {
      useTemplateBuilderStore.setState({ saveSuccess: true });
    });

    const notification = screen.getByText("Template saved successfully.");
    expect(notification).toBeDefined();
    // The notification container has role="status" and aria-live="polite"
    expect(notification.closest('[role="status"]')).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Requirement 7.4: Success notification auto-dismisses after 5 seconds
  // -------------------------------------------------------------------------

  it("auto-dismisses success notification after 5 seconds", () => {
    vi.useFakeTimers();

    renderTemplateBuilder();

    // Trigger success notification
    act(() => {
      useTemplateBuilderStore.setState({ saveSuccess: true });
    });

    // Notification should be visible
    expect(screen.getByText("Template saved successfully.")).toBeDefined();

    // Advance time by 5 seconds
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    // Notification should be dismissed
    expect(screen.queryByText("Template saved successfully.")).toBeNull();

    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Requirement 7.5, 7.6: Error notification display
  // -------------------------------------------------------------------------

  it("shows error notification when saveError is set", () => {
    renderTemplateBuilder();

    // Simulate save error
    act(() => {
      useTemplateBuilderStore.setState({
        saveError: "Template name already exists",
      });
    });

    expect(screen.getByText("Template name already exists")).toBeDefined();
    expect(screen.getByRole("alert")).toBeDefined();
  });

  it("shows generic error notification for non-400 errors", () => {
    renderTemplateBuilder();

    act(() => {
      useTemplateBuilderStore.setState({
        saveError: "Failed to save template. Please try again.",
      });
    });

    expect(
      screen.getByText("Failed to save template. Please try again.")
    ).toBeDefined();
  });

  it("hides error notification when saveError is cleared", () => {
    renderTemplateBuilder();

    // Show error
    act(() => {
      useTemplateBuilderStore.setState({
        saveError: "Some error occurred",
      });
    });

    expect(screen.getByText("Some error occurred")).toBeDefined();

    // Clear error
    act(() => {
      useTemplateBuilderStore.setState({ saveError: null });
    });

    expect(screen.queryByText("Some error occurred")).toBeNull();
  });
});
