import { describe, it, expect, beforeEach } from "vitest";
import { useTemplateBuilderStore } from "../templateBuilderStore";

describe("templateBuilderStore", () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    useTemplateBuilderStore.getState().resetBuilder();
  });

  describe("addField", () => {
    it("adds a field with correct type, default label, and fieldOrder", () => {
      const { addField } = useTemplateBuilderStore.getState();

      addField("Text", 0);

      const { fields } = useTemplateBuilderStore.getState();
      expect(fields).toHaveLength(1);
      expect(fields[0].type).toBe("Text");
      expect(fields[0].label).toBe("Text Field");
      expect(fields[0].fieldOrder).toBe(0);
      expect(fields[0].id).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
      );
    });

    it("inserts at the correct drop index and shifts existing fields", () => {
      const { addField } = useTemplateBuilderStore.getState();

      addField("Text", 0);
      addField("Float", 1);
      addField("Integer", 1); // Insert between Text and Float

      const { fields } = useTemplateBuilderStore.getState();
      expect(fields).toHaveLength(3);
      expect(fields[0].type).toBe("Text");
      expect(fields[0].fieldOrder).toBe(0);
      expect(fields[1].type).toBe("Integer");
      expect(fields[1].fieldOrder).toBe(1);
      expect(fields[2].type).toBe("Float");
      expect(fields[2].fieldOrder).toBe(2);
    });

    it("enforces 50-field maximum", () => {
      const { addField } = useTemplateBuilderStore.getState();

      for (let i = 0; i < 50; i++) {
        addField("Text", i);
      }

      expect(useTemplateBuilderStore.getState().fields).toHaveLength(50);

      // 51st field should not be added
      addField("Text", 50);
      expect(useTemplateBuilderStore.getState().fields).toHaveLength(50);
    });

    it("sets isDirty to true", () => {
      const { addField } = useTemplateBuilderStore.getState();
      expect(useTemplateBuilderStore.getState().isDirty).toBe(false);

      addField("Text", 0);
      expect(useTemplateBuilderStore.getState().isDirty).toBe(true);
    });
  });

  describe("removeField", () => {
    it("removes a field by id and recalculates fieldOrder", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      addField("Float", 1);
      addField("Integer", 2);

      const fields = useTemplateBuilderStore.getState().fields;
      const middleId = fields[1].id;

      useTemplateBuilderStore.getState().removeField(middleId);

      const updatedFields = useTemplateBuilderStore.getState().fields;
      expect(updatedFields).toHaveLength(2);
      expect(updatedFields[0].fieldOrder).toBe(0);
      expect(updatedFields[1].fieldOrder).toBe(1);
      expect(updatedFields.find((f) => f.id === middleId)).toBeUndefined();
    });

    it("clears selection if removed field was selected", () => {
      const { addField, selectField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      selectField(fieldId);
      expect(useTemplateBuilderStore.getState().selectedFieldId).toBe(fieldId);

      useTemplateBuilderStore.getState().removeField(fieldId);
      expect(useTemplateBuilderStore.getState().selectedFieldId).toBeNull();
    });

    it("preserves selection if removed field was not selected", () => {
      const { addField, selectField } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      addField("Float", 1);

      const fields = useTemplateBuilderStore.getState().fields;
      selectField(fields[0].id);

      useTemplateBuilderStore.getState().removeField(fields[1].id);
      expect(useTemplateBuilderStore.getState().selectedFieldId).toBe(
        fields[0].id
      );
    });
  });

  describe("reorderField", () => {
    it("moves field from source to destination and recalculates fieldOrder", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      addField("Float", 1);
      addField("Integer", 2);

      const originalFields = useTemplateBuilderStore.getState().fields;
      const firstId = originalFields[0].id;

      useTemplateBuilderStore.getState().reorderField(0, 2);

      const reorderedFields = useTemplateBuilderStore.getState().fields;
      expect(reorderedFields[2].id).toBe(firstId);
      expect(reorderedFields[0].fieldOrder).toBe(0);
      expect(reorderedFields[1].fieldOrder).toBe(1);
      expect(reorderedFields[2].fieldOrder).toBe(2);
    });

    it("is a no-op when source equals destination", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      addField("Float", 1);

      // Reset dirty to test no-op doesn't set it
      useTemplateBuilderStore.setState({ isDirty: false });

      const fieldsBefore = useTemplateBuilderStore.getState().fields;
      useTemplateBuilderStore.getState().reorderField(0, 0);
      const fieldsAfter = useTemplateBuilderStore.getState().fields;

      expect(fieldsAfter).toEqual(fieldsBefore);
      expect(useTemplateBuilderStore.getState().isDirty).toBe(false);
    });

    it("preserves selectedFieldId across reorder", () => {
      const { addField, selectField } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      addField("Float", 1);
      addField("Integer", 2);

      const fields = useTemplateBuilderStore.getState().fields;
      selectField(fields[1].id);

      useTemplateBuilderStore.getState().reorderField(0, 2);

      expect(useTemplateBuilderStore.getState().selectedFieldId).toBe(
        fields[1].id
      );
    });
  });

  describe("selectField", () => {
    it("sets selectedFieldId", () => {
      const { addField, selectField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      selectField(fieldId);
      expect(useTemplateBuilderStore.getState().selectedFieldId).toBe(fieldId);
    });

    it("can clear selection with null", () => {
      const { addField, selectField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      selectField(fieldId);
      selectField(null);
      expect(useTemplateBuilderStore.getState().selectedFieldId).toBeNull();
    });
  });

  describe("updateFieldLabel", () => {
    it("updates the label of the specified field", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      useTemplateBuilderStore.getState().updateFieldLabel(fieldId, "My Label");

      const field = useTemplateBuilderStore.getState().fields[0];
      expect(field.label).toBe("My Label");
    });

    it("sets fieldError for empty label", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      useTemplateBuilderStore.getState().updateFieldLabel(fieldId, "");

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[fieldId]).toBe("Label is required");
    });

    it("sets fieldError for label exceeding 200 chars", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      const longLabel = "a".repeat(201);
      useTemplateBuilderStore.getState().updateFieldLabel(fieldId, longLabel);

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[fieldId]).toBe("Label must not exceed 200 characters");
    });

    it("clears fieldError for valid label", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      useTemplateBuilderStore.getState().updateFieldLabel(fieldId, "");
      useTemplateBuilderStore
        .getState()
        .updateFieldLabel(fieldId, "Valid Label");

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[fieldId]).toBeUndefined();
    });
  });

  describe("updateFieldType", () => {
    it("updates the type of the specified field", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      useTemplateBuilderStore.getState().updateFieldType(fieldId, "Integer");

      const field = useTemplateBuilderStore.getState().fields[0];
      expect(field.type).toBe("Integer");
    });

    it("sets isDirty to true", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      useTemplateBuilderStore.setState({ isDirty: false });

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      useTemplateBuilderStore.getState().updateFieldType(fieldId, "Float");

      expect(useTemplateBuilderStore.getState().isDirty).toBe(true);
    });
  });

  describe("setTemplateName", () => {
    it("sets the template name and clears error for valid name", () => {
      useTemplateBuilderStore.getState().setTemplateName("My Template");

      const state = useTemplateBuilderStore.getState();
      expect(state.templateName).toBe("My Template");
      expect(state.nameError).toBeNull();
      expect(state.isDirty).toBe(true);
    });

    it("sets error for empty name", () => {
      useTemplateBuilderStore.getState().setTemplateName("");

      const { nameError } = useTemplateBuilderStore.getState();
      expect(nameError).toBe("Template name is required");
    });

    it("sets error for whitespace-only name", () => {
      useTemplateBuilderStore.getState().setTemplateName("   ");

      const { nameError } = useTemplateBuilderStore.getState();
      expect(nameError).toBe("Template name is required");
    });

    it("sets error for name exceeding 500 chars", () => {
      const longName = "a".repeat(501);
      useTemplateBuilderStore.getState().setTemplateName(longName);

      const { nameError } = useTemplateBuilderStore.getState();
      expect(nameError).toBe("Template name must not exceed 500 characters");
    });
  });

  describe("canSave", () => {
    it("returns false when name is empty", () => {
      const { addField } = useTemplateBuilderStore.getState();
      addField("Text", 0);

      expect(useTemplateBuilderStore.getState().canSave()).toBe(false);
    });

    it("returns false when fields are empty", () => {
      useTemplateBuilderStore.getState().setTemplateName("My Template");

      expect(useTemplateBuilderStore.getState().canSave()).toBe(false);
    });

    it("returns false when any field has empty label", () => {
      const { addField, setTemplateName } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      setTemplateName("My Template");

      const fieldId = useTemplateBuilderStore.getState().fields[0].id;
      useTemplateBuilderStore.getState().updateFieldLabel(fieldId, "");

      expect(useTemplateBuilderStore.getState().canSave()).toBe(false);
    });

    it("returns false when isSaving is true", () => {
      const { addField, setTemplateName } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      setTemplateName("My Template");
      useTemplateBuilderStore.setState({ isSaving: true });

      expect(useTemplateBuilderStore.getState().canSave()).toBe(false);
    });

    it("returns true when all conditions are met", () => {
      const { addField, setTemplateName } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      setTemplateName("My Template");

      expect(useTemplateBuilderStore.getState().canSave()).toBe(true);
    });
  });

  describe("markClean", () => {
    it("resets isDirty to false", () => {
      const { addField, markClean } = useTemplateBuilderStore.getState();
      addField("Text", 0);
      expect(useTemplateBuilderStore.getState().isDirty).toBe(true);

      markClean();
      expect(useTemplateBuilderStore.getState().isDirty).toBe(false);
    });
  });

  describe("resetBuilder", () => {
    it("resets all state to initial values", () => {
      const { addField, setTemplateName, selectField } =
        useTemplateBuilderStore.getState();
      addField("Text", 0);
      setTemplateName("My Template");
      selectField(useTemplateBuilderStore.getState().fields[0].id);

      useTemplateBuilderStore.getState().resetBuilder();

      const state = useTemplateBuilderStore.getState();
      expect(state.fields).toHaveLength(0);
      expect(state.templateName).toBe("");
      expect(state.selectedFieldId).toBeNull();
      expect(state.isDirty).toBe(false);
      expect(state.isSaving).toBe(false);
      expect(state.saveError).toBeNull();
      expect(state.saveSuccess).toBe(false);
    });
  });

  describe("updateContentBlockText", () => {
    it("updates the text of a heading content block", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, "New Header");

      const item = useTemplateBuilderStore.getState().items[0];
      expect(item.element_type).toBe("content_block");
      if (item.element_type === "content_block") {
        expect(item.text).toBe("New Header");
      }
    });

    it("updates the text of a paragraph content block", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("paragraph", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, "Some instructions");

      const item = useTemplateBuilderStore.getState().items[0];
      if (item.element_type === "content_block") {
        expect(item.text).toBe("Some instructions");
      }
    });

    it("sets fieldError for empty header text", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h2", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore.getState().updateContentBlockText(blockId, "");

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[blockId]).toBe("Header text is required");
    });

    it("sets fieldError for whitespace-only header text", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h3", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore.getState().updateContentBlockText(blockId, "   ");

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[blockId]).toBe("Header text is required");
    });

    it("sets fieldError for header text exceeding 200 chars", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      const longText = "a".repeat(201);
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, longText);

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[blockId]).toBe(
        "Header text must not exceed 200 characters"
      );
    });

    it("sets fieldError for empty paragraph text", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("paragraph", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore.getState().updateContentBlockText(blockId, "");

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[blockId]).toBe("Paragraph text is required");
    });

    it("sets fieldError for paragraph text exceeding 2000 chars", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("paragraph", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      const longText = "a".repeat(2001);
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, longText);

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[blockId]).toBe(
        "Paragraph text must not exceed 2000 characters"
      );
    });

    it("clears fieldError for valid header text", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore.getState().updateContentBlockText(blockId, "");
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, "Valid Header");

      const { fieldErrors } = useTemplateBuilderStore.getState();
      expect(fieldErrors[blockId]).toBeUndefined();
    });

    it("sets isDirty to true", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);
      useTemplateBuilderStore.setState({ isDirty: false });

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, "Updated");

      expect(useTemplateBuilderStore.getState().isDirty).toBe(true);
    });
  });

  describe("updateContentBlockLevel", () => {
    it("changes heading level from h1 to h2", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockLevel(blockId, "heading_h2");

      const item = useTemplateBuilderStore.getState().items[0];
      if (item.element_type === "content_block") {
        expect(item.content_type).toBe("heading_h2");
      }
    });

    it("changes heading level from h3 to h1", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h3", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockLevel(blockId, "heading_h1");

      const item = useTemplateBuilderStore.getState().items[0];
      if (item.element_type === "content_block") {
        expect(item.content_type).toBe("heading_h1");
      }
    });

    it("does not change level for non-heading content blocks", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("paragraph", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockLevel(blockId, "heading_h2");

      const item = useTemplateBuilderStore.getState().items[0];
      if (item.element_type === "content_block") {
        expect(item.content_type).toBe("paragraph");
      }
    });

    it("preserves existing text when changing level", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockText(blockId, "My Header");
      useTemplateBuilderStore
        .getState()
        .updateContentBlockLevel(blockId, "heading_h3");

      const item = useTemplateBuilderStore.getState().items[0];
      if (item.element_type === "content_block") {
        expect(item.text).toBe("My Header");
        expect(item.content_type).toBe("heading_h3");
      }
    });

    it("sets isDirty to true", () => {
      const { addContentBlock } = useTemplateBuilderStore.getState();
      addContentBlock("heading_h1", 0);
      useTemplateBuilderStore.setState({ isDirty: false });

      const blockId = useTemplateBuilderStore.getState().items[0].id;
      useTemplateBuilderStore
        .getState()
        .updateContentBlockLevel(blockId, "heading_h2");

      expect(useTemplateBuilderStore.getState().isDirty).toBe(true);
    });
  });
});
