import { create } from "zustand";
import type {
  FieldType,
  CanvasFieldData,
  TemplateCreatePayload,
  TemplateResponse,
} from "../types/template";
import { apiClient, ApiError } from "../lib/apiClient";
import { useAuthStore } from "./authStore";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_FIELDS = 50;
const MAX_LABEL_LENGTH = 200;
const MAX_NAME_LENGTH = 500;

// ---------------------------------------------------------------------------
// State Interface
// ---------------------------------------------------------------------------

export interface TemplateBuilderState {
  // Canvas state
  fields: CanvasFieldData[];
  templateName: string;
  selectedFieldId: string | null;

  // Save state
  isSaving: boolean;
  saveError: string | null;
  saveSuccess: boolean;
  savedTemplate: TemplateResponse | null;

  // Dirty tracking
  isDirty: boolean;

  // Validation
  nameError: string | null;
  fieldErrors: Record<string, string>;

  // Actions
  addField: (type: FieldType, dropIndex: number) => void;
  removeField: (fieldId: string) => void;
  reorderField: (sourceIndex: number, destinationIndex: number) => void;
  selectField: (fieldId: string | null) => void;
  updateFieldLabel: (fieldId: string, label: string) => void;
  updateFieldType: (fieldId: string, type: FieldType) => void;
  setTemplateName: (name: string) => void;
  saveTemplate: () => Promise<void>;
  resetBuilder: () => void;
  markClean: () => void;

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
function recalculateFieldOrder(fields: CanvasFieldData[]): CanvasFieldData[] {
  for (let i = 0; i < fields.length; i++) {
    fields[i].fieldOrder = i;
  }
  return fields;
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
 * Serializes canvas fields and template name into the backend-expected payload format.
 * Sorts fields by fieldOrder ascending and maps to {label, type} only,
 * excluding id, field_uuid, and field_order.
 */
export function serializeTemplate(
  fields: CanvasFieldData[],
  templateName: string,
  userId: number
): TemplateCreatePayload {
  return {
    name: templateName.trim(),
    json_schema: {
      fields: [...fields]
        .sort((a, b) => a.fieldOrder - b.fieldOrder)
        .map((f) => ({ label: f.label, type: f.type })),
    },
    user_id: userId,
  };
}

// ---------------------------------------------------------------------------
// Initial State
// ---------------------------------------------------------------------------

const initialState = {
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
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTemplateBuilderStore = create<TemplateBuilderState>(
  (set, get) => ({
    ...initialState,

    addField: (type: FieldType, dropIndex: number) => {
      const { fields } = get();

      // Enforce 50-field maximum
      if (fields.length >= MAX_FIELDS) {
        return;
      }

      // Clamp dropIndex to valid range
      const clampedIndex = Math.max(0, Math.min(dropIndex, fields.length));

      const newField: CanvasFieldData = {
        id: crypto.randomUUID(),
        label: `${type} Field`,
        type,
        fieldOrder: clampedIndex,
      };

      // Insert at the drop index
      const updatedFields = [...fields];
      updatedFields.splice(clampedIndex, 0, newField);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedFields);

      set({ fields: updatedFields, isDirty: true });
    },

    removeField: (fieldId: string) => {
      const { fields, selectedFieldId } = get();

      const updatedFields = fields.filter((f) => f.id !== fieldId);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedFields);

      // Clear selection if the removed field was selected
      const newSelectedFieldId =
        selectedFieldId === fieldId ? null : selectedFieldId;

      set({
        fields: updatedFields,
        selectedFieldId: newSelectedFieldId,
        isDirty: true,
      });
    },

    reorderField: (sourceIndex: number, destinationIndex: number) => {
      // No-op if same position
      if (sourceIndex === destinationIndex) {
        return;
      }

      const { fields } = get();

      const updatedFields = [...fields];
      const [movedField] = updatedFields.splice(sourceIndex, 1);
      updatedFields.splice(destinationIndex, 0, movedField);

      // Recalculate contiguous fieldOrder
      recalculateFieldOrder(updatedFields);

      set({ fields: updatedFields, isDirty: true });
    },

    selectField: (fieldId: string | null) => {
      set({ selectedFieldId: fieldId });
    },

    updateFieldLabel: (fieldId: string, label: string) => {
      const { fields, fieldErrors } = get();

      const updatedFields = fields.map((f) =>
        f.id === fieldId ? { ...f, label } : f
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
        fields: updatedFields,
        fieldErrors: updatedErrors,
        isDirty: true,
      });
    },

    updateFieldType: (fieldId: string, type: FieldType) => {
      const { fields } = get();

      const updatedFields = fields.map((f) =>
        f.id === fieldId ? { ...f, type } : f
      );

      set({ fields: updatedFields, isDirty: true });
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
        const { fields, templateName } = get();
        const userId = useAuthStore.getState().user?.id ?? 1;

        const payload = serializeTemplate(fields, templateName, userId);

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

    canSave: () => {
      const { templateName, fields, isSaving } = get();

      // Name must be valid (non-empty, non-whitespace, <= 500 chars)
      if (templateName.trim().length === 0) {
        return false;
      }
      if (templateName.length > MAX_NAME_LENGTH) {
        return false;
      }

      // Must have at least one field
      if (fields.length === 0) {
        return false;
      }

      // All fields must have non-empty labels
      const hasEmptyLabel = fields.some((f) => f.label.trim().length === 0);
      if (hasEmptyLabel) {
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
