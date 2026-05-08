import { create } from "zustand";
import type {
  FieldType,
  CanvasFieldData,
  CanvasFieldElement,
  CanvasContentBlockElement,
  CanvasItem,
  ContentBlockType,
  FieldConfig,
  TextFieldConfig,
  FloatFieldConfig,
  IntegerFieldConfig,
  DateFieldConfig,
  BooleanFieldConfig,
  TemplateCreatePayload,
  LegacyTemplateCreatePayload,
  SerializedElement,
  SerializedFieldElement,
  SerializedContentBlockElement,
  TemplateResponse,
  TemplateVersionResponse,
  VersionCreatePayload,
} from "../types/template";

import { apiClient, ApiError } from "../lib/apiClient";
import { getAccessToken } from "../lib/tokenStorage";
import { useAuthStore } from "./authStore";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_FIELDS = 50;
const MAX_LABEL_LENGTH = 200;
const MAX_NAME_LENGTH = 500;
const MAX_HELP_TEXT_LENGTH = 500;
const MAX_HEADER_TEXT_LENGTH = 200;
const MAX_PARAGRAPH_TEXT_LENGTH = 2000;

// ---------------------------------------------------------------------------
// Field Configuration Validation
// ---------------------------------------------------------------------------

/**
 * Validates a regex pattern string.
 * Returns an error message if invalid, null if valid or empty.
 */
export function validateRegexPattern(pattern: string | undefined): string | null {
  if (pattern === undefined || pattern === "") {
    return null;
  }
  try {
    new RegExp(pattern);
    return null;
  } catch {
    return "Invalid regular expression pattern";
  }
}

/**
 * Validates that min ≤ max for numeric values.
 * Returns an error message if min > max, null otherwise.
 */
export function validateMinMax(
  min: number | undefined,
  max: number | undefined,
  label: string
): string | null {
  if (min === undefined || max === undefined) {
    return null;
  }
  if (min > max) {
    return `Minimum ${label} must not exceed maximum ${label}`;
  }
  return null;
}

/**
 * Validates that min_date ≤ max_date for ISO 8601 date strings.
 * Returns an error message if min > max, null otherwise.
 */
export function validateDateRange(
  minDate: string | undefined,
  maxDate: string | undefined
): string | null {
  if (!minDate || !maxDate) {
    return null;
  }
  const min = new Date(minDate);
  const max = new Date(maxDate);
  if (isNaN(min.getTime())) {
    return "Minimum date is not a valid ISO 8601 date";
  }
  if (isNaN(max.getTime())) {
    return "Maximum date is not a valid ISO 8601 date";
  }
  if (min > max) {
    return "Minimum date must not be later than maximum date";
  }
  return null;
}

/**
 * Validates a default value against the field type constraints.
 * Returns an error message if invalid, null if valid or empty.
 */
export function validateDefaultValue(
  value: string | null,
  fieldType: FieldType
): string | null {
  if (value === null || value === "") {
    return null;
  }
  switch (fieldType) {
    case "Integer": {
      const parsed = Number(value);
      if (!Number.isInteger(parsed) || isNaN(parsed)) {
        return "Default value must be a valid integer";
      }
      return null;
    }
    case "Float": {
      const parsed = Number(value);
      if (isNaN(parsed)) {
        return "Default value must be a valid number";
      }
      return null;
    }
    case "Date": {
      const date = new Date(value);
      if (isNaN(date.getTime())) {
        return "Default value must be a valid ISO 8601 date";
      }
      return null;
    }
    case "Boolean": {
      if (value !== "true" && value !== "false") {
        return 'Default value must be "true" or "false"';
      }
      return null;
    }
    case "Text":
      // Any non-empty string is valid for text
      return null;
  }
}

/**
 * Validates a field configuration and returns all errors as an array of strings.
 * Returns an empty array if the config is valid.
 */
export function validateFieldConfig(
  config: FieldConfig,
  fieldType: FieldType
): string[] {
  const errors: string[] = [];

  switch (fieldType) {
    case "Text": {
      const c = config as TextFieldConfig;
      const minMaxError = validateMinMax(c.min_length, c.max_length, "length");
      if (minMaxError) errors.push(minMaxError);
      const regexError = validateRegexPattern(c.regex_pattern);
      if (regexError) errors.push(regexError);
      break;
    }
    case "Float": {
      const c = config as FloatFieldConfig;
      const minMaxError = validateMinMax(c.min_value, c.max_value, "value");
      if (minMaxError) errors.push(minMaxError);
      if (c.decimal_precision !== undefined && (c.decimal_precision < 0 || c.decimal_precision > 10)) {
        errors.push("Decimal precision must be between 0 and 10");
      }
      if (c.unit_label !== undefined && c.unit_label.length > 50) {
        errors.push("Unit label must not exceed 50 characters");
      }
      break;
    }
    case "Integer": {
      const c = config as IntegerFieldConfig;
      const minMaxError = validateMinMax(c.min_value, c.max_value, "value");
      if (minMaxError) errors.push(minMaxError);
      if (c.step_size !== undefined && c.step_size <= 0) {
        errors.push("Step size must be a positive integer");
      }
      if (c.unit_label !== undefined && c.unit_label.length > 50) {
        errors.push("Unit label must not exceed 50 characters");
      }
      break;
    }
    case "Date": {
      const c = config as DateFieldConfig;
      const dateError = validateDateRange(c.min_date, c.max_date);
      if (dateError) errors.push(dateError);
      break;
    }
    case "Boolean": {
      const c = config as BooleanFieldConfig;
      if (c.true_label !== undefined && c.true_label.length === 0) {
        errors.push("True label is required");
      }
      if (c.true_label !== undefined && c.true_label.length > 50) {
        errors.push("True label must not exceed 50 characters");
      }
      if (c.false_label !== undefined && c.false_label.length === 0) {
        errors.push("False label is required");
      }
      if (c.false_label !== undefined && c.false_label.length > 50) {
        errors.push("False label must not exceed 50 characters");
      }
      break;
    }
  }

  return errors;
}

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface TemplateBuilderState {
  // Canvas state (new: items is the primary state)
  items: CanvasItem[];
  templateName: string;
  selectedFieldId: string | null;

  /**
   * @deprecated Use `items` instead. Backward-compatible accessor that returns
   * only field elements as CanvasFieldData (without enhanced properties).
   */
  fields: CanvasFieldData[];

  // Save state
  isSaving: boolean;
  saveError: string | null;
  saveSuccess: boolean;
  savedTemplate: TemplateResponse | null;

  // Dirty tracking
  isDirty: boolean;

  // PDF download state
  isDownloading: boolean;
  downloadError: string | null;

  // Validation
  nameError: string | null;
  fieldErrors: Record<string, string>;

  // Versioning state
  versions: TemplateVersionResponse[];
  activeVersion: TemplateVersionResponse | null;
  isCreatingVersion: boolean;
  versionError: string | null;

  // Actions — enhanced
  addField: (type: FieldType, dropIndex: number) => void;
  addContentBlock: (contentType: ContentBlockType, dropIndex: number) => void;
  removeItem: (itemId: string) => void;
  reorderItem: (sourceIndex: number, destinationIndex: number) => void;

  /** @deprecated Use removeItem instead */
  removeField: (fieldId: string) => void;
  /** @deprecated Use reorderItem instead */
  reorderField: (sourceIndex: number, destinationIndex: number) => void;

  selectField: (fieldId: string | null) => void;
  updateFieldLabel: (fieldId: string, label: string) => void;
  updateFieldType: (fieldId: string, type: FieldType) => void;
  updateFieldConfig: (fieldId: string, partialConfig: Partial<FieldConfig>) => void;
  updateFieldRequired: (fieldId: string, required: boolean) => void;
  updateFieldHelpText: (fieldId: string, helpText: string) => void;
  updateFieldDefaultValue: (fieldId: string, defaultValue: string) => void;
  updateContentBlockText: (blockId: string, text: string) => void;
  updateContentBlockLevel: (
    blockId: string,
    level: "heading_h1" | "heading_h2" | "heading_h3"
  ) => void;
  setTemplateName: (name: string) => void;
  saveTemplate: () => Promise<void>;
  resetBuilder: () => void;
  markClean: () => void;

  // Versioning actions
  createVersion: (documentUuid: string, changeReason: string) => Promise<void>;
  fetchVersionHistory: (documentUuid: string) => Promise<void>;
  fetchVersion: (documentUuid: string, versionNumber: number) => Promise<void>;
  loadVersionIntoCanvas: (version: TemplateVersionResponse) => void;

  // PDF download action
  downloadPdf: (documentUuid: string) => Promise<void>;

  // Derived
  canSave: () => boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Recalculates fieldOrder values to form a contiguous 0-based sequence.
 * Mutates the array in place and returns it.
 */
function recalculateFieldOrder(items: CanvasItem[]): CanvasItem[] {
  for (let i = 0; i < items.length; i++) {
    items[i].fieldOrder = i;
  }
  return items;
}

/**
 * Returns the default FieldConfig for a given field type.
 */
export function getDefaultFieldConfig(type: FieldType): FieldConfig {
  switch (type) {
    case "Text":
      return {} as TextFieldConfig;
    case "Float":
      return {} as FloatFieldConfig;
    case "Integer":
      return { step_size: 1 } as IntegerFieldConfig;
    case "Date":
      return { date_format: "YYYY-MM-DD" } as DateFieldConfig;
    case "Boolean":
      return { true_label: "True", false_label: "False" } as BooleanFieldConfig;
  }
}

/**
 * Returns the default text for a content block type.
 */
function getDefaultContentBlockText(
  contentType: ContentBlockType
): string | null {
  switch (contentType) {
    case "heading_h1":
    case "heading_h2":
    case "heading_h3":
      return "Section Title";
    case "paragraph":
      return "Enter instructions or description here";
    case "divider":
      return null;
  }
}

/**
 * Derives the backward-compatible `fields` array from items.
 * Extracts only field elements and maps them to CanvasFieldData shape.
 */
function deriveFields(items: CanvasItem[]): CanvasFieldData[] {
  return items
    .filter((item): item is CanvasFieldElement => item.element_type === "field")
    .map((item) => ({
      id: item.id,
      label: item.label,
      type: item.type,
      fieldOrder: item.fieldOrder,
    }));
}

/**
 * Validates a template name.
 * Returns an error message string or null if valid.
 */
export function validateTemplateName(name: string): string | null {
  if (name.trim().length === 0) {
    return "Template name is required";
  }
  if (name.length > MAX_NAME_LENGTH) {
    return "Template name must not exceed 500 characters";
  }
  return null;
}

/**
 * Validates a field label.
 * Returns an error message string or null if valid.
 */
export function validateFieldLabel(label: string): string | null {
  if (label.length === 0) {
    return "Label is required";
  }
  if (label.length > MAX_LABEL_LENGTH) {
    return "Label must not exceed 200 characters";
  }
  return null;
}

/**
 * Validates content block text based on the content type.
 * Headers (heading_h1/h2/h3): text required, max 200 chars.
 * Paragraphs: text required, max 2000 chars.
 * Dividers: no validation needed (text is null).
 * Returns an error message string or null if valid.
 */
export function validateContentBlockText(
  contentType: ContentBlockType,
  text: string | null
): string | null {
  if (contentType === "divider") {
    return null;
  }

  if (
    contentType === "heading_h1" ||
    contentType === "heading_h2" ||
    contentType === "heading_h3"
  ) {
    if (!text || text.trim().length === 0) {
      return "Header text is required";
    }
    if (text.length > MAX_HEADER_TEXT_LENGTH) {
      return `Header text must not exceed ${MAX_HEADER_TEXT_LENGTH} characters`;
    }
    return null;
  }

  if (contentType === "paragraph") {
    if (!text || text.trim().length === 0) {
      return "Paragraph text is required";
    }
    if (text.length > MAX_PARAGRAPH_TEXT_LENGTH) {
      return `Paragraph text must not exceed ${MAX_PARAGRAPH_TEXT_LENGTH} characters`;
    }
    return null;
  }

  return null;
}

/**
 * Serializes canvas items into the enhanced backend-expected payload format.
 * Sorts items by fieldOrder ascending and maps to SerializedElement array
 * with element_type discriminator.
 *
 * Also accepts legacy CanvasFieldData[] for backward compatibility — in that case,
 * produces the legacy { fields: [...] } format.
 */
export function serializeTemplate(
  items: CanvasItem[] | CanvasFieldData[],
  templateName: string,
  userId: number
): TemplateCreatePayload | LegacyTemplateCreatePayload {
  // Detect legacy CanvasFieldData[] (items without element_type property)
  if (items.length > 0 && !("element_type" in items[0])) {
    // Legacy path: produce old format for backward compatibility
    const fields = items as CanvasFieldData[];
    return {
      name: templateName.trim(),
      json_schema: {
        fields: [...fields]
          .sort((a, b) => a.fieldOrder - b.fieldOrder)
          .map((f) => ({ label: f.label, type: f.type })),
      },
      user_id: userId,
    } as LegacyTemplateCreatePayload;
  }

  // Enhanced path: produce new elements format
  const canvasItems = items as CanvasItem[];
  const sortedItems = [...canvasItems].sort((a, b) => a.fieldOrder - b.fieldOrder);

  const elements: SerializedElement[] = sortedItems.map((item) => {
    if (item.element_type === "field") {
      const field = item as CanvasFieldElement;
      return {
        element_type: "field",
        label: field.label,
        type: field.type,
        required: field.required,
        help_text: field.help_text,
        default_value: field.default_value,
        config: field.config,
      } as SerializedFieldElement;
    } else {
      const block = item as CanvasContentBlockElement;
      return {
        element_type: "content_block",
        content_type: block.content_type,
        text: block.text,
      } as SerializedContentBlockElement;
    }
  });

  return {
    name: templateName.trim(),
    json_schema: {
      elements,
    },
    user_id: userId,
  } as TemplateCreatePayload;
}

/**
 * Deserializes a json_schema with elements array back into CanvasItem[] with
 * proper IDs and contiguous fieldOrder values.
 * Used for loading version schemas back into the canvas state.
 */
export function deserializeTemplate(
  jsonSchema: { elements: SerializedElement[] }
): CanvasItem[] {
  const elements = jsonSchema.elements;

  const items: CanvasItem[] = elements.map((element, index) => {
    if (element.element_type === "field") {
      const field = element as SerializedFieldElement;
      return {
        id: crypto.randomUUID(),
        element_type: "field" as const,
        label: field.label,
        type: field.type,
        fieldOrder: index,
        required: field.required,
        help_text: field.help_text,
        default_value: field.default_value,
        config: field.config ?? getDefaultFieldConfig(field.type),
      } satisfies CanvasFieldElement;
    } else {
      const block = element as SerializedContentBlockElement;
      return {
        id: crypto.randomUUID(),
        element_type: "content_block" as const,
        content_type: block.content_type,
        text: block.text,
        fieldOrder: index,
      } satisfies CanvasContentBlockElement;
    }
  });

  return items;
}

// ---------------------------------------------------------------------------
// Initial State
// ---------------------------------------------------------------------------

const initialState = {
  items: [] as CanvasItem[],
  fields: [] as CanvasFieldData[],
  templateName: "",
  selectedFieldId: null as string | null,
  isSaving: false,
  saveError: null as string | null,
  saveSuccess: false,
  savedTemplate: null as TemplateResponse | null,
  isDirty: false,
  nameError: null as string | null,
  fieldErrors: {} as Record<string, string>,
  versions: [] as TemplateVersionResponse[],
  activeVersion: null as TemplateVersionResponse | null,
  isCreatingVersion: false,
  versionError: null as string | null,
  isDownloading: false,
  downloadError: null as string | null,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

/**
 * Resolves the canonical items array from the current state.
 * If `items` is empty but `fields` has data (backward-compatible setState),
 * converts `fields` to CanvasFieldElement items.
 * If `fields` was explicitly set (e.g., via setState in tests) and differs
 * from what `items` would derive, prefer `fields` as the source of truth
 * for backward compatibility.
 */
function resolveItems(state: { items: CanvasItem[]; fields: CanvasFieldData[] }): CanvasItem[] {
  // If items has data and fields is consistent (derived from items), use items
  if (state.items.length > 0) {
    // Check if fields was explicitly set to something different from items
    const derivedFields = deriveFields(state.items);
    const fieldsMatch =
      derivedFields.length === state.fields.length &&
      derivedFields.every(
        (df, i) =>
          df.id === state.fields[i]?.id &&
          df.label === state.fields[i]?.label &&
          df.type === state.fields[i]?.type &&
          df.fieldOrder === state.fields[i]?.fieldOrder
      );

    if (fieldsMatch) {
      return state.items;
    }

    // Fields was set externally (e.g., via setState in tests) — rebuild items from fields
    if (state.fields.length === 0) {
      return [];
    }
    return state.fields.map((f) => ({
      id: f.id,
      element_type: "field" as const,
      label: f.label,
      type: f.type,
      fieldOrder: f.fieldOrder,
      required: false,
      help_text: null,
      default_value: null,
      config: getDefaultFieldConfig(f.type),
    }));
  }

  if (state.fields.length > 0) {
    // Backward compatibility: convert legacy fields to CanvasFieldElement items
    return state.fields.map((f) => ({
      id: f.id,
      element_type: "field" as const,
      label: f.label,
      type: f.type,
      fieldOrder: f.fieldOrder,
      required: false,
      help_text: null,
      default_value: null,
      config: getDefaultFieldConfig(f.type),
    }));
  }
  return [];
}

export const useTemplateBuilderStore = create<TemplateBuilderState>(
  (set, get) => ({
    ...initialState,

    addField: (type: FieldType, dropIndex: number) => {
      const items = resolveItems(get());

      // Enforce 50-field maximum (only count field elements)
      const fieldCount = items.filter((i) => i.element_type === "field").length;
      if (fieldCount >= MAX_FIELDS) {
        return;
      }

      // Clamp dropIndex to valid range
      const clampedIndex = Math.max(0, Math.min(dropIndex, items.length));

      const newField: CanvasFieldElement = {
        id: crypto.randomUUID(),
        element_type: "field",
        label: `${type} Field`,
        type,
        fieldOrder: clampedIndex,
        required: false,
        help_text: null,
        default_value: null,
        config: getDefaultFieldConfig(type),
      };

      // Insert at the drop index
      const updatedItems = [...items];
      updatedItems.splice(clampedIndex, 0, newField);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedItems);

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        isDirty: true,
      });
    },

    addContentBlock: (contentType: ContentBlockType, dropIndex: number) => {
      const items = resolveItems(get());

      // Clamp dropIndex to valid range
      const clampedIndex = Math.max(0, Math.min(dropIndex, items.length));

      const newBlock: CanvasContentBlockElement = {
        id: crypto.randomUUID(),
        element_type: "content_block",
        content_type: contentType,
        text: getDefaultContentBlockText(contentType),
        fieldOrder: clampedIndex,
      };

      // Insert at the drop index
      const updatedItems = [...items];
      updatedItems.splice(clampedIndex, 0, newBlock);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedItems);

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        isDirty: true,
      });
    },

    removeItem: (itemId: string) => {
      const items = resolveItems(get());
      const { selectedFieldId } = get();

      const updatedItems = items.filter((i) => i.id !== itemId);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedItems);

      // Clear selection if the removed item was selected
      const newSelectedFieldId =
        selectedFieldId === itemId ? null : selectedFieldId;

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        selectedFieldId: newSelectedFieldId,
        isDirty: true,
      });
    },

    removeField: (fieldId: string) => {
      // Backward-compatible alias for removeItem
      get().removeItem(fieldId);
    },

    reorderItem: (sourceIndex: number, destinationIndex: number) => {
      // No-op if same position
      if (sourceIndex === destinationIndex) {
        return;
      }

      const items = resolveItems(get());

      const updatedItems = [...items];
      const [movedItem] = updatedItems.splice(sourceIndex, 1);
      updatedItems.splice(destinationIndex, 0, movedItem);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedItems);

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        isDirty: true,
      });
    },

    reorderField: (sourceIndex: number, destinationIndex: number) => {
      // Backward-compatible alias for reorderItem
      get().reorderItem(sourceIndex, destinationIndex);
    },

    selectField: (fieldId: string | null) => {
      set({ selectedFieldId: fieldId });
    },

    updateFieldLabel: (fieldId: string, label: string) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      const updatedItems = items.map((item) =>
        item.element_type === "field" && item.id === fieldId
          ? { ...item, label }
          : item
      );

      // Validate the label
      const error = validateFieldLabel(label);
      const updatedErrors = { ...fieldErrors };
      if (error) {
        updatedErrors[fieldId] = error;
      } else {
        delete updatedErrors[fieldId];
      }

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateFieldType: (fieldId: string, type: FieldType) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      const updatedItems = items.map((item) =>
        item.element_type === "field" && item.id === fieldId
          ? { ...item, type, config: getDefaultFieldConfig(type), default_value: null }
          : item
      );

      // Clear any config validation errors for this field since config was reset
      const updatedErrors = { ...fieldErrors };
      delete updatedErrors[fieldId];

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateFieldConfig: (fieldId: string, partialConfig: Partial<FieldConfig>) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      let targetField: CanvasFieldElement | undefined;
      const updatedItems = items.map((item) => {
        if (item.element_type === "field" && item.id === fieldId) {
          const mergedConfig = { ...item.config, ...partialConfig };
          const updated = { ...item, config: mergedConfig };
          targetField = updated;
          return updated;
        }
        return item;
      });

      // Validate the merged config
      const updatedErrors = { ...fieldErrors };
      if (targetField) {
        const configErrors = validateFieldConfig(targetField.config, targetField.type);
        if (configErrors.length > 0) {
          updatedErrors[fieldId] = configErrors.join("; ");
        } else {
          delete updatedErrors[fieldId];
        }
      }

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateFieldRequired: (fieldId: string, required: boolean) => {
      const items = resolveItems(get());

      const updatedItems = items.map((item) =>
        item.element_type === "field" && item.id === fieldId
          ? { ...item, required }
          : item
      );

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        isDirty: true,
      });
    },

    updateFieldHelpText: (fieldId: string, helpText: string) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      const updatedItems = items.map((item) =>
        item.element_type === "field" && item.id === fieldId
          ? { ...item, help_text: helpText || null }
          : item
      );

      // Validate help text length
      const updatedErrors = { ...fieldErrors };
      if (helpText.length > MAX_HELP_TEXT_LENGTH) {
        updatedErrors[fieldId] = `Help text must not exceed ${MAX_HELP_TEXT_LENGTH} characters`;
      } else {
        // Re-validate config to ensure we preserve config errors
        const targetItem = updatedItems.find(
          (i) => i.element_type === "field" && i.id === fieldId
        ) as CanvasFieldElement | undefined;
        if (targetItem) {
          const configErrors = validateFieldConfig(targetItem.config, targetItem.type);
          if (configErrors.length > 0) {
            updatedErrors[fieldId] = configErrors.join("; ");
          } else {
            delete updatedErrors[fieldId];
          }
        } else {
          delete updatedErrors[fieldId];
        }
      }

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateFieldDefaultValue: (fieldId: string, defaultValue: string) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      // Find the field to get its type for validation
      const targetItem = items.find(
        (i) => i.element_type === "field" && i.id === fieldId
      ) as CanvasFieldElement | undefined;

      if (!targetItem) return;

      const updatedItems = items.map((item) =>
        item.element_type === "field" && item.id === fieldId
          ? { ...item, default_value: defaultValue || null }
          : item
      );

      // Validate default value against field type
      const updatedErrors = { ...fieldErrors };
      const defaultError = validateDefaultValue(defaultValue || null, targetItem.type);
      const configErrors = validateFieldConfig(targetItem.config, targetItem.type);

      const allErrors: string[] = [];
      if (configErrors.length > 0) allErrors.push(...configErrors);
      if (defaultError) allErrors.push(defaultError);

      if (allErrors.length > 0) {
        updatedErrors[fieldId] = allErrors.join("; ");
      } else {
        delete updatedErrors[fieldId];
      }

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateContentBlockText: (blockId: string, text: string) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      const updatedItems = items.map((item) => {
        if (item.element_type === "content_block" && item.id === blockId) {
          return { ...item, text };
        }
        return item;
      });

      // Find the block to validate against its content_type
      const block = items.find(
        (item): item is CanvasContentBlockElement =>
          item.element_type === "content_block" && item.id === blockId
      );

      const updatedErrors = { ...fieldErrors };
      if (block) {
        const error = validateContentBlockText(block.content_type, text);
        if (error) {
          updatedErrors[blockId] = error;
        } else {
          delete updatedErrors[blockId];
        }
      }

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateContentBlockLevel: (
      blockId: string,
      level: "heading_h1" | "heading_h2" | "heading_h3"
    ) => {
      const items = resolveItems(get());
      const { fieldErrors } = get();

      const updatedItems = items.map((item) => {
        if (item.element_type === "content_block" && item.id === blockId) {
          const block = item as CanvasContentBlockElement;
          // Only allow level changes on heading content blocks
          if (
            block.content_type === "heading_h1" ||
            block.content_type === "heading_h2" ||
            block.content_type === "heading_h3"
          ) {
            return { ...block, content_type: level };
          }
        }
        return item;
      });

      // Re-validate text after level change (max length is the same for all headings)
      const block = updatedItems.find(
        (item): item is CanvasContentBlockElement =>
          item.element_type === "content_block" && item.id === blockId
      );

      const updatedErrors = { ...fieldErrors };
      if (block) {
        const error = validateContentBlockText(block.content_type, block.text);
        if (error) {
          updatedErrors[blockId] = error;
        } else {
          delete updatedErrors[blockId];
        }
      }

      set({
        items: updatedItems,
        fields: deriveFields(updatedItems),
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    setTemplateName: (name: string) => {
      const nameError = validateTemplateName(name);
      set({ templateName: name, nameError, isDirty: true });
    },

    saveTemplate: async () => {
      const canSave = get().canSave();
      if (!canSave) {
        return;
      }

      set({ isSaving: true, saveError: null, saveSuccess: false });

      try {
        const { templateName } = get();
        const items = resolveItems(get());
        const userId = useAuthStore.getState().user?.id ?? 1;

        const payload = serializeTemplate(items, templateName, userId);

        const response = await apiClient.post<TemplateResponse>(
          "/api/templates",
          payload,
          { changeReason: "Template created via builder" }
        );

        set({
          savedTemplate: response,
          saveSuccess: true,
          isSaving: false,
        });
        get().markClean();
      } catch (error: unknown) {
        let saveError = "Failed to save template. Please try again.";

        if (error instanceof ApiError) {
          if (error.status === 400 || error.status === 422) {
            try {
              const parsed = JSON.parse(error.body);
              if (parsed.detail) {
                saveError = typeof parsed.detail === "string"
                  ? parsed.detail
                  : JSON.stringify(parsed.detail);
              }
            } catch {
              saveError = error.body || saveError;
            }
          } else {
            // Other API errors (500, 403, etc.)
            saveError = `Save failed (${error.status}). Please try again.`;
          }
        } else if (error instanceof Error) {
          saveError = error.message === "Session expired"
            ? "Session expired. Please log in again."
            : "Failed to save template. Please try again.";
        }

        set({ saveError, isSaving: false });
      }
    },

    resetBuilder: () => {
      set({ ...initialState });
    },

    markClean: () => {
      set({ isDirty: false });
    },

    createVersion: async (documentUuid: string, changeReason: string) => {
      const canSave = get().canSave();
      if (!canSave) {
        return;
      }

      set({ isCreatingVersion: true, versionError: null });

      try {
        const items = resolveItems(get());
        const userId = useAuthStore.getState().user?.id ?? 1;

        // Serialize current canvas state into the version payload
        const sortedItems = [...items].sort((a, b) => a.fieldOrder - b.fieldOrder);
        const elements: SerializedElement[] = sortedItems.map((item) => {
          if (item.element_type === "field") {
            const field = item as CanvasFieldElement;
            return {
              element_type: "field",
              label: field.label,
              type: field.type,
              required: field.required,
              help_text: field.help_text,
              default_value: field.default_value,
              config: field.config,
            } as SerializedFieldElement;
          } else {
            const block = item as CanvasContentBlockElement;
            return {
              element_type: "content_block",
              content_type: block.content_type,
              text: block.text,
            } as SerializedContentBlockElement;
          }
        });

        const payload: VersionCreatePayload = {
          json_schema: { elements },
          user_id: userId,
        };

        const response = await apiClient.post<TemplateVersionResponse>(
          `/api/templates/${documentUuid}/versions`,
          payload,
          { changeReason }
        );

        // Update versions list: mark all previous as inactive, add new version
        const updatedVersions = get().versions.map((v) => ({
          ...v,
          is_active: false,
        }));
        updatedVersions.unshift(response);

        set({
          versions: updatedVersions,
          activeVersion: response,
          isCreatingVersion: false,
        });
        get().markClean();
      } catch (error: unknown) {
        let versionError = "Failed to create version. Please try again.";

        if (error instanceof ApiError) {
          if (error.status === 409) {
            versionError = "Another version is being created. Please try again.";
          } else if (error.status === 400 || error.status === 422) {
            try {
              const parsed = JSON.parse(error.body);
              if (parsed.detail) {
                versionError = typeof parsed.detail === "string"
                  ? parsed.detail
                  : JSON.stringify(parsed.detail);
              }
            } catch {
              versionError = error.body || versionError;
            }
          } else if (error.status === 404) {
            versionError = "Template not found.";
          } else {
            versionError = `Version creation failed (${error.status}). Please try again.`;
          }
        } else if (error instanceof Error) {
          versionError = error.message === "Session expired"
            ? "Session expired. Please log in again."
            : "Failed to create version. Please try again.";
        }

        set({ versionError, isCreatingVersion: false });
      }
    },

    fetchVersionHistory: async (documentUuid: string) => {
      set({ versionError: null });

      try {
        const versions = await apiClient.get<TemplateVersionResponse[]>(
          `/api/templates/${documentUuid}/versions`
        );

        // Sort descending by version_number (newest first)
        const sorted = [...versions].sort(
          (a, b) => b.version_number - a.version_number
        );

        // Determine active version
        const active = sorted.find((v) => v.is_active) ?? null;

        set({ versions: sorted, activeVersion: active });
      } catch (error: unknown) {
        let versionError = "Failed to load version history.";

        if (error instanceof ApiError) {
          if (error.status === 404) {
            versionError = "Template not found.";
          } else {
            versionError = `Failed to load version history (${error.status}).`;
          }
        } else if (error instanceof Error) {
          versionError = error.message === "Session expired"
            ? "Session expired. Please log in again."
            : "Failed to load version history.";
        }

        set({ versionError });
      }
    },

    fetchVersion: async (documentUuid: string, versionNumber: number) => {
      set({ versionError: null });

      try {
        const version = await apiClient.get<TemplateVersionResponse>(
          `/api/templates/${documentUuid}/versions/${versionNumber}`
        );

        set({ activeVersion: version });
      } catch (error: unknown) {
        let versionError = "Failed to load version.";

        if (error instanceof ApiError) {
          if (error.status === 404) {
            versionError = "Version not found.";
          } else {
            versionError = `Failed to load version (${error.status}).`;
          }
        } else if (error instanceof Error) {
          versionError = error.message === "Session expired"
            ? "Session expired. Please log in again."
            : "Failed to load version.";
        }

        set({ versionError });
      }
    },

    loadVersionIntoCanvas: (version: TemplateVersionResponse) => {
      // Deserialize the version's json_schema into canvas items
      const jsonSchema = version.json_schema as { elements?: SerializedElement[] };

      if (!jsonSchema.elements || !Array.isArray(jsonSchema.elements)) {
        set({ versionError: "Invalid version schema format." });
        return;
      }

      const items = deserializeTemplate({ elements: jsonSchema.elements });

      set({
        items,
        fields: deriveFields(items),
        selectedFieldId: null,
        isDirty: false,
        fieldErrors: {},
        versionError: null,
      });
    },

    downloadPdf: async (documentUuid: string) => {
      set({ isDownloading: true, downloadError: null });

      try {
        // Build headers manually since apiClient doesn't support blob responses
        const headers: Record<string, string> = {
          "X-Change-Reason": "PDF downloaded for offline data collection",
        };

        const token = getAccessToken();
        if (token) {
          headers["Authorization"] = `Bearer ${token}`;
        }

        const authState = useAuthStore.getState();
        if (authState.user?.id != null) {
          headers["X-User-Id"] = String(authState.user.id);
        }
        if (authState.activeCompanyId != null) {
          headers["X-Company-Id"] = String(authState.activeCompanyId);
        }

        const response = await fetch(
          `/api/templates/${documentUuid}/download-pdf`,
          {
            method: "POST",
            headers,
            credentials: "include",
          }
        );

        if (!response.ok) {
          if (response.status === 404) {
            set({ downloadError: "Template not found", isDownloading: false });
            return;
          }
          if (response.status === 400) {
            set({ downloadError: "Not downloadable", isDownloading: false });
            return;
          }
          set({ downloadError: "Download failed", isDownloading: false });
          return;
        }

        // Extract filename from Content-Disposition header
        const contentDisposition = response.headers.get("Content-Disposition");
        let filename = `template_${documentUuid}.pdf`;
        if (contentDisposition) {
          const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
          if (match?.[1]) {
            filename = match[1];
          }
        }

        // Handle blob response and trigger download
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        // Clean up the blob URL
        URL.revokeObjectURL(url);

        set({ isDownloading: false });
      } catch {
        set({ downloadError: "Download failed", isDownloading: false });
      }
    },

    canSave: () => {
      const { templateName, isSaving, fieldErrors } = get();
      const items = resolveItems(get());

      // Name must be valid (non-empty, non-whitespace, <= 500 chars)
      if (templateName.trim().length === 0) {
        return false;
      }
      if (templateName.length > MAX_NAME_LENGTH) {
        return false;
      }

      // Must have at least one field element
      const fieldItems = items.filter((i) => i.element_type === "field");
      if (fieldItems.length === 0) {
        return false;
      }

      // All field elements must have non-empty labels
      const hasEmptyLabel = fieldItems.some(
        (f) => (f as CanvasFieldElement).label.trim().length === 0
      );
      if (hasEmptyLabel) {
        return false;
      }

      // Must have no field validation errors (cross-field constraints, regex, etc.)
      if (Object.keys(fieldErrors).length > 0) {
        return false;
      }

      // Content blocks with required text must not have empty text
      const contentBlocks = items.filter(
        (i): i is CanvasContentBlockElement => i.element_type === "content_block"
      );
      const hasEmptyContentBlockText = contentBlocks.some((block) => {
        // Headers and paragraphs require non-empty text; dividers do not
        if (
          block.content_type === "heading_h1" ||
          block.content_type === "heading_h2" ||
          block.content_type === "heading_h3" ||
          block.content_type === "paragraph"
        ) {
          return !block.text || block.text.trim().length === 0;
        }
        return false;
      });
      if (hasEmptyContentBlockText) {
        return false;
      }

      // Must not be currently saving
      if (isSaving) {
        return false;
      }

      return true;
    },
  })
);
