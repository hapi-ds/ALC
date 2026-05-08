import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { ConfigurationPanel } from "../../components/templates/ConfigurationPanel";
import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";

/**
 * Unit tests for ConfigurationPanel component.
 *
 * Validates: Requirements 1.4, 1.6, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 10.3
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

describe("ConfigurationPanel", () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    cleanup();
  });

  it("displays empty state message when no field is selected", () => {
    render(<ConfigurationPanel />);
    expect(
      screen.getByText("Select a field to configure its properties")
    ).toBeDefined();
  });

  it("displays label input and type dropdown when a field is selected", () => {
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "Name", type: "Text", fieldOrder: 0 }],
      selectedFieldId: "field-1",
    });

    render(<ConfigurationPanel />);

    const labelInput = screen.getByLabelText("Label") as HTMLInputElement;
    expect(labelInput).toBeDefined();
    expect(labelInput.value).toBe("Name");

    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement;
    expect(typeSelect).toBeDefined();
    expect(typeSelect.value).toBe("Text");
  });

  it("renders all five field type options in the dropdown", () => {
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "Test", type: "Text", fieldOrder: 0 }],
      selectedFieldId: "field-1",
    });

    render(<ConfigurationPanel />);

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(5);
    expect(options.map((o) => o.textContent)).toEqual([
      "Text",
      "Float",
      "Integer",
      "Date",
      "Boolean",
    ]);
  });

  it("updates field label in store on input change", () => {
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "Old", type: "Text", fieldOrder: 0 }],
      selectedFieldId: "field-1",
    });

    render(<ConfigurationPanel />);

    const labelInput = screen.getByLabelText("Label");
    fireEvent.change(labelInput, { target: { value: "New Label" } });

    const state = useTemplateBuilderStore.getState();
    expect(state.fields[0].label).toBe("New Label");
  });

  it("updates field type in store on dropdown change", () => {
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-1", label: "Amount", type: "Text", fieldOrder: 0 },
      ],
      selectedFieldId: "field-1",
    });

    render(<ConfigurationPanel />);

    const typeSelect = screen.getByLabelText("Type");
    fireEvent.change(typeSelect, { target: { value: "Float" } });

    const state = useTemplateBuilderStore.getState();
    expect(state.fields[0].type).toBe("Float");
  });

  it("shows validation error when label is empty", () => {
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "", type: "Text", fieldOrder: 0 }],
      selectedFieldId: "field-1",
      fieldErrors: { "field-1": "Label is required" },
    });

    render(<ConfigurationPanel />);

    const errorElement = document.getElementById("field-label-error-field-1");
    expect(errorElement).not.toBeNull();
    expect(errorElement!.textContent).toBe("Label is required");

    const labelInput = screen.getByLabelText("Label") as HTMLInputElement;
    expect(labelInput.getAttribute("aria-invalid")).toBe("true");
  });

  it("shows validation error when label exceeds 200 characters", () => {
    const longLabel = "a".repeat(201);
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-1", label: longLabel, type: "Text", fieldOrder: 0 },
      ],
      selectedFieldId: "field-1",
      fieldErrors: {
        "field-1": "Label must not exceed 200 characters",
      },
    });

    render(<ConfigurationPanel />);

    const errorElement = document.getElementById("field-label-error-field-1");
    expect(errorElement).not.toBeNull();
    expect(errorElement!.textContent).toBe(
      "Label must not exceed 200 characters"
    );
  });

  it("links validation error to input via aria-describedby", () => {
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "", type: "Text", fieldOrder: 0 }],
      selectedFieldId: "field-1",
      fieldErrors: { "field-1": "Label is required" },
    });

    render(<ConfigurationPanel />);

    const input = screen.getByLabelText("Label") as HTMLInputElement;
    const errorId = input.getAttribute("aria-describedby");
    expect(errorId).toBeTruthy();

    const errorElement = document.getElementById(errorId!);
    expect(errorElement).not.toBeNull();
    expect(errorElement!.textContent).toBe("Label is required");
  });

  it("form inputs are reachable via keyboard Tab navigation", () => {
    useTemplateBuilderStore.setState({
      fields: [{ id: "field-1", label: "Test", type: "Text", fieldOrder: 0 }],
      selectedFieldId: "field-1",
    });

    render(<ConfigurationPanel />);

    const labelInput = screen.getByLabelText("Label") as HTMLInputElement;
    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement;

    // Both inputs should have proper tabIndex (default 0 for form elements)
    expect(labelInput.tabIndex).toBe(0);
    expect(typeSelect.tabIndex).toBe(0);
  });

  it("updates display when a different field is selected", () => {
    useTemplateBuilderStore.setState({
      fields: [
        { id: "field-1", label: "First", type: "Text", fieldOrder: 0 },
        { id: "field-2", label: "Second", type: "Integer", fieldOrder: 1 },
      ],
      selectedFieldId: "field-2",
    });

    render(<ConfigurationPanel />);

    const labelInput = screen.getByLabelText("Label") as HTMLInputElement;
    const typeSelect = screen.getByLabelText("Type") as HTMLSelectElement;

    expect(labelInput.value).toBe("Second");
    expect(typeSelect.value).toBe("Integer");
  });
});
