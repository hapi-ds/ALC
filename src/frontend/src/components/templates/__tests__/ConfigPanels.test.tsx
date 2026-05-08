import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { useTemplateBuilderStore } from "../../../stores/templateBuilderStore";
import { TextConfigPanel } from "../TextConfigPanel";
import { FloatConfigPanel } from "../FloatConfigPanel";
import { IntegerConfigPanel } from "../IntegerConfigPanel";
import { DateConfigPanel } from "../DateConfigPanel";
import { BooleanConfigPanel } from "../BooleanConfigPanel";
import type {
  CanvasFieldElement,
  TextFieldConfig,
  FloatFieldConfig,
  IntegerFieldConfig,
  DateFieldConfig,
  BooleanFieldConfig,
} from "../../../types/template";

/**
 * Unit tests for type-specific configuration panels.
 *
 * Validates: Requirements 2.1, 3.1, 4.1, 5.1, 6.1
 *
 * Each test suite:
 * 1. Sets up the store with a field of the appropriate type
 * 2. Renders the panel
 * 3. Verifies correct inputs are rendered
 * 4. Verifies inline validation errors display when fieldErrors has an entry
 */

function makeTextField(overrides?: Partial<CanvasFieldElement>): CanvasFieldElement {
  return {
    id: "text-field-1",
    element_type: "field",
    label: "Test Text",
    type: "Text",
    fieldOrder: 0,
    required: false,
    help_text: null,
    default_value: null,
    config: {
      min_length: undefined,
      max_length: undefined,
      placeholder: undefined,
      regex_pattern: undefined,
    } as TextFieldConfig,
    ...overrides,
  };
}

function makeFloatField(overrides?: Partial<CanvasFieldElement>): CanvasFieldElement {
  return {
    id: "float-field-1",
    element_type: "field",
    label: "Test Float",
    type: "Float",
    fieldOrder: 0,
    required: false,
    help_text: null,
    default_value: null,
    config: {
      decimal_precision: undefined,
      min_value: undefined,
      max_value: undefined,
      unit_label: undefined,
    } as FloatFieldConfig,
    ...overrides,
  };
}

function makeIntegerField(overrides?: Partial<CanvasFieldElement>): CanvasFieldElement {
  return {
    id: "integer-field-1",
    element_type: "field",
    label: "Test Integer",
    type: "Integer",
    fieldOrder: 0,
    required: false,
    help_text: null,
    default_value: null,
    config: {
      min_value: undefined,
      max_value: undefined,
      step_size: 1,
      unit_label: undefined,
    } as IntegerFieldConfig,
    ...overrides,
  };
}

function makeDateField(overrides?: Partial<CanvasFieldElement>): CanvasFieldElement {
  return {
    id: "date-field-1",
    element_type: "field",
    label: "Test Date",
    type: "Date",
    fieldOrder: 0,
    required: false,
    help_text: null,
    default_value: null,
    config: {
      min_date: undefined,
      max_date: undefined,
      date_format: undefined,
    } as DateFieldConfig,
    ...overrides,
  };
}

function makeBooleanField(overrides?: Partial<CanvasFieldElement>): CanvasFieldElement {
  return {
    id: "boolean-field-1",
    element_type: "field",
    label: "Test Boolean",
    type: "Boolean",
    fieldOrder: 0,
    required: false,
    help_text: null,
    default_value: null,
    config: {
      true_label: "True",
      false_label: "False",
    } as BooleanFieldConfig,
    ...overrides,
  };
}

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

describe("TextConfigPanel", () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it("renders correct inputs for Text field type", () => {
    const field = makeTextField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<TextConfigPanel fieldId={field.id} />);

    expect(screen.getByLabelText("Minimum Length")).toBeDefined();
    expect(screen.getByLabelText("Maximum Length")).toBeDefined();
    expect(screen.getByLabelText("Placeholder")).toBeDefined();
    expect(screen.getByLabelText("Regex Pattern")).toBeDefined();
  });

  it("renders inputs with correct types", () => {
    const field = makeTextField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<TextConfigPanel fieldId={field.id} />);

    const minLength = screen.getByLabelText("Minimum Length") as HTMLInputElement;
    const maxLength = screen.getByLabelText("Maximum Length") as HTMLInputElement;
    const placeholder = screen.getByLabelText("Placeholder") as HTMLInputElement;
    const regex = screen.getByLabelText("Regex Pattern") as HTMLInputElement;

    expect(minLength.type).toBe("number");
    expect(maxLength.type).toBe("number");
    expect(placeholder.type).toBe("text");
    expect(regex.type).toBe("text");
  });

  it("displays configured values from the store", () => {
    const field = makeTextField({
      config: {
        min_length: 5,
        max_length: 100,
        placeholder: "Enter text",
        regex_pattern: "^[A-Z]+$",
      },
    });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<TextConfigPanel fieldId={field.id} />);

    const minLength = screen.getByLabelText("Minimum Length") as HTMLInputElement;
    const maxLength = screen.getByLabelText("Maximum Length") as HTMLInputElement;
    const placeholder = screen.getByLabelText("Placeholder") as HTMLInputElement;
    const regex = screen.getByLabelText("Regex Pattern") as HTMLInputElement;

    expect(minLength.value).toBe("5");
    expect(maxLength.value).toBe("100");
    expect(placeholder.value).toBe("Enter text");
    expect(regex.value).toBe("^[A-Z]+$");
  });

  it("displays inline validation error when fieldErrors has an entry", () => {
    const field = makeTextField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: { [field.id]: "Minimum length must not exceed maximum length" },
    });

    render(<TextConfigPanel fieldId={field.id} />);

    const errorEl = screen.getByRole("alert");
    expect(errorEl).toBeDefined();
    expect(errorEl.textContent).toBe("Minimum length must not exceed maximum length");
  });

  it("does not display error when fieldErrors is empty for this field", () => {
    const field = makeTextField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: {},
    });

    render(<TextConfigPanel fieldId={field.id} />);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("returns null when field is not of type Text", () => {
    const field = makeFloatField({ id: "text-field-1" });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    const { container } = render(<TextConfigPanel fieldId={field.id} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("FloatConfigPanel", () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it("renders correct inputs for Float field type", () => {
    const field = makeFloatField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<FloatConfigPanel fieldId={field.id} />);

    expect(screen.getByLabelText("Decimal Precision")).toBeDefined();
    expect(screen.getByLabelText("Minimum Value")).toBeDefined();
    expect(screen.getByLabelText("Maximum Value")).toBeDefined();
    expect(screen.getByLabelText("Unit Label")).toBeDefined();
  });

  it("renders inputs with correct types and constraints", () => {
    const field = makeFloatField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<FloatConfigPanel fieldId={field.id} />);

    const precision = screen.getByLabelText("Decimal Precision") as HTMLInputElement;
    const minValue = screen.getByLabelText("Minimum Value") as HTMLInputElement;
    const maxValue = screen.getByLabelText("Maximum Value") as HTMLInputElement;
    const unitLabel = screen.getByLabelText("Unit Label") as HTMLInputElement;

    expect(precision.type).toBe("number");
    expect(precision.min).toBe("0");
    expect(precision.max).toBe("10");
    expect(minValue.type).toBe("number");
    expect(maxValue.type).toBe("number");
    expect(unitLabel.type).toBe("text");
  });

  it("displays configured values from the store", () => {
    const field = makeFloatField({
      config: {
        decimal_precision: 3,
        min_value: 0.5,
        max_value: 14.0,
        unit_label: "mg/L",
      },
    });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<FloatConfigPanel fieldId={field.id} />);

    const precision = screen.getByLabelText("Decimal Precision") as HTMLInputElement;
    const minValue = screen.getByLabelText("Minimum Value") as HTMLInputElement;
    const maxValue = screen.getByLabelText("Maximum Value") as HTMLInputElement;
    const unitLabel = screen.getByLabelText("Unit Label") as HTMLInputElement;

    expect(precision.value).toBe("3");
    expect(minValue.value).toBe("0.5");
    expect(maxValue.value).toBe("14");
    expect(unitLabel.value).toBe("mg/L");
  });

  it("displays inline validation error when fieldErrors has an entry", () => {
    const field = makeFloatField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: { [field.id]: "Minimum value must not exceed maximum value" },
    });

    render(<FloatConfigPanel fieldId={field.id} />);

    const errorEl = screen.getByRole("alert");
    expect(errorEl).toBeDefined();
    expect(errorEl.textContent).toBe("Minimum value must not exceed maximum value");
  });

  it("does not display error when fieldErrors is empty for this field", () => {
    const field = makeFloatField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: {},
    });

    render(<FloatConfigPanel fieldId={field.id} />);

    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("IntegerConfigPanel", () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it("renders correct inputs for Integer field type", () => {
    const field = makeIntegerField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<IntegerConfigPanel fieldId={field.id} />);

    expect(screen.getByLabelText("Minimum Value")).toBeDefined();
    expect(screen.getByLabelText("Maximum Value")).toBeDefined();
    expect(screen.getByLabelText("Step Size")).toBeDefined();
    expect(screen.getByLabelText("Unit Label")).toBeDefined();
  });

  it("renders inputs with correct types", () => {
    const field = makeIntegerField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<IntegerConfigPanel fieldId={field.id} />);

    const minValue = screen.getByLabelText("Minimum Value") as HTMLInputElement;
    const maxValue = screen.getByLabelText("Maximum Value") as HTMLInputElement;
    const stepSize = screen.getByLabelText("Step Size") as HTMLInputElement;
    const unitLabel = screen.getByLabelText("Unit Label") as HTMLInputElement;

    expect(minValue.type).toBe("number");
    expect(maxValue.type).toBe("number");
    expect(stepSize.type).toBe("number");
    expect(unitLabel.type).toBe("text");
  });

  it("displays configured values from the store", () => {
    const field = makeIntegerField({
      config: {
        min_value: 0,
        max_value: 1000,
        step_size: 5,
        unit_label: "units",
      },
    });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<IntegerConfigPanel fieldId={field.id} />);

    const minValue = screen.getByLabelText("Minimum Value") as HTMLInputElement;
    const maxValue = screen.getByLabelText("Maximum Value") as HTMLInputElement;
    const stepSize = screen.getByLabelText("Step Size") as HTMLInputElement;
    const unitLabel = screen.getByLabelText("Unit Label") as HTMLInputElement;

    expect(minValue.value).toBe("0");
    expect(maxValue.value).toBe("1000");
    expect(stepSize.value).toBe("5");
    expect(unitLabel.value).toBe("units");
  });

  it("displays default step size of 1", () => {
    const field = makeIntegerField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<IntegerConfigPanel fieldId={field.id} />);

    const stepSize = screen.getByLabelText("Step Size") as HTMLInputElement;
    expect(stepSize.value).toBe("1");
  });

  it("displays inline validation error when fieldErrors has an entry", () => {
    const field = makeIntegerField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: { [field.id]: "Minimum value must not exceed maximum value" },
    });

    render(<IntegerConfigPanel fieldId={field.id} />);

    const errorEl = screen.getByRole("alert");
    expect(errorEl).toBeDefined();
    expect(errorEl.textContent).toBe("Minimum value must not exceed maximum value");
  });

  it("does not display error when fieldErrors is empty for this field", () => {
    const field = makeIntegerField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: {},
    });

    render(<IntegerConfigPanel fieldId={field.id} />);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("returns null when field is not of type Integer", () => {
    const field = makeTextField({ id: "integer-field-1" });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    const { container } = render(<IntegerConfigPanel fieldId={field.id} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("DateConfigPanel", () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it("renders correct inputs for Date field type", () => {
    const field = makeDateField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<DateConfigPanel fieldId={field.id} />);

    expect(screen.getByLabelText("Minimum Date")).toBeDefined();
    expect(screen.getByLabelText("Maximum Date")).toBeDefined();
    expect(screen.getByLabelText("Date Format")).toBeDefined();
  });

  it("renders date inputs and format dropdown with correct types", () => {
    const field = makeDateField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<DateConfigPanel fieldId={field.id} />);

    const minDate = screen.getByLabelText("Minimum Date") as HTMLInputElement;
    const maxDate = screen.getByLabelText("Maximum Date") as HTMLInputElement;
    const format = screen.getByLabelText("Date Format") as HTMLSelectElement;

    expect(minDate.type).toBe("date");
    expect(maxDate.type).toBe("date");
    expect(format.tagName.toLowerCase()).toBe("select");
  });

  it("renders all four date format options", () => {
    const field = makeDateField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<DateConfigPanel fieldId={field.id} />);

    const options = screen.getByLabelText("Date Format").querySelectorAll("option");
    const values = Array.from(options).map((o) => o.textContent);
    expect(values).toEqual(["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MMM-YYYY"]);
  });

  it("defaults date format to YYYY-MM-DD", () => {
    const field = makeDateField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<DateConfigPanel fieldId={field.id} />);

    const format = screen.getByLabelText("Date Format") as HTMLSelectElement;
    expect(format.value).toBe("YYYY-MM-DD");
  });

  it("displays configured values from the store", () => {
    const field = makeDateField({
      config: {
        min_date: "2024-01-01",
        max_date: "2024-12-31",
        date_format: "DD/MM/YYYY",
      },
    });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<DateConfigPanel fieldId={field.id} />);

    const minDate = screen.getByLabelText("Minimum Date") as HTMLInputElement;
    const maxDate = screen.getByLabelText("Maximum Date") as HTMLInputElement;
    const format = screen.getByLabelText("Date Format") as HTMLSelectElement;

    expect(minDate.value).toBe("2024-01-01");
    expect(maxDate.value).toBe("2024-12-31");
    expect(format.value).toBe("DD/MM/YYYY");
  });

  it("displays inline validation error when fieldErrors has an entry", () => {
    const field = makeDateField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: { [field.id]: "Minimum date must not be later than maximum date" },
    });

    render(<DateConfigPanel fieldId={field.id} />);

    const errorEl = screen.getByRole("alert");
    expect(errorEl).toBeDefined();
    expect(errorEl.textContent).toBe("Minimum date must not be later than maximum date");
  });

  it("does not display error when fieldErrors is empty for this field", () => {
    const field = makeDateField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
      fieldErrors: {},
    });

    render(<DateConfigPanel fieldId={field.id} />);

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("returns null when field is not of type Date", () => {
    const field = makeTextField({ id: "date-field-1" });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    const { container } = render(<DateConfigPanel fieldId={field.id} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("BooleanConfigPanel", () => {
  beforeEach(() => resetStore());
  afterEach(() => cleanup());

  it("renders correct inputs for Boolean field type", () => {
    const field = makeBooleanField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<BooleanConfigPanel fieldId={field.id} />);

    expect(screen.getByLabelText("True Label")).toBeDefined();
    expect(screen.getByLabelText("False Label")).toBeDefined();
  });

  it("renders text inputs for both labels", () => {
    const field = makeBooleanField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<BooleanConfigPanel fieldId={field.id} />);

    const trueLabel = screen.getByLabelText("True Label") as HTMLInputElement;
    const falseLabel = screen.getByLabelText("False Label") as HTMLInputElement;

    expect(trueLabel.type).toBe("text");
    expect(falseLabel.type).toBe("text");
  });

  it("displays default values of 'True' and 'False'", () => {
    const field = makeBooleanField();
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<BooleanConfigPanel fieldId={field.id} />);

    const trueLabel = screen.getByLabelText("True Label") as HTMLInputElement;
    const falseLabel = screen.getByLabelText("False Label") as HTMLInputElement;

    expect(trueLabel.value).toBe("True");
    expect(falseLabel.value).toBe("False");
  });

  it("displays custom configured labels from the store", () => {
    const field = makeBooleanField({
      config: {
        true_label: "Pass",
        false_label: "Fail",
      },
    });
    useTemplateBuilderStore.setState({
      items: [field],
      selectedFieldId: field.id,
    });

    render(<BooleanConfigPanel fieldId={field.id} />);

    const trueLabel = screen.getByLabelText("True Label") as HTMLInputElement;
    const falseLabel = screen.getByLabelText("False Label") as HTMLInputElement;

    expect(trueLabel.value).toBe("Pass");
    expect(falseLabel.value).toBe("Fail");
  });

  it("displays inline validation error when true label is cleared", () => {
    const field = makeBooleanField();
    useTemplateBuilderStore.setState({
      items: [field],
      fields: [{ id: field.id, label: field.label, type: field.type, fieldOrder: field.fieldOrder }],
      selectedFieldId: field.id,
    });

    render(<BooleanConfigPanel fieldId={field.id} />);

    const trueLabel = screen.getByLabelText("True Label") as HTMLInputElement;
    fireEvent.change(trueLabel, { target: { value: "" } });

    const errorEl = screen.getByText("Label is required");
    expect(errorEl).toBeDefined();
  });

  it("displays inline validation error for label exceeding 50 characters", () => {
    const field = makeBooleanField();
    useTemplateBuilderStore.setState({
      items: [field],
      fields: [{ id: field.id, label: field.label, type: field.type, fieldOrder: field.fieldOrder }],
      selectedFieldId: field.id,
    });

    render(<BooleanConfigPanel fieldId={field.id} />);

    const trueLabel = screen.getByLabelText("True Label") as HTMLInputElement;
    const longValue = "a".repeat(51);
    fireEvent.change(trueLabel, { target: { value: longValue } });

    const errorEl = screen.getByText("Label must not exceed 50 characters");
    expect(errorEl).toBeDefined();
  });

  it("returns null when field is not found", () => {
    useTemplateBuilderStore.setState({
      items: [],
      selectedFieldId: null,
    });

    const { container } = render(<BooleanConfigPanel fieldId="nonexistent" />);
    expect(container.innerHTML).toBe("");
  });
});
