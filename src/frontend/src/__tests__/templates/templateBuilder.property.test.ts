import { describe, it, expect, beforeEach } from "vitest";
import * as fc from "fast-check";
import {
  useTemplateBuilderStore,
  validateFieldLabel,
  validateTemplateName,
  serializeTemplate,
} from "../../stores/templateBuilderStore";
import type { FieldType } from "../../types/template";

// ---------------------------------------------------------------------------
// Arbitraries
// ---------------------------------------------------------------------------

const fieldTypeArb = fc.constantFrom<FieldType>(
  "Text",
  "Float",
  "Integer",
  "Date",
  "Boolean"
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getState() {
  return useTemplateBuilderStore.getState();
}

function assertContiguousFieldOrder() {
  const { fields } = getState();
  for (let i = 0; i < fields.length; i++) {
    expect(fields[i].fieldOrder).toBe(i);
  }
}

const UUID_V4_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  useTemplateBuilderStore.getState().resetBuilder();
});

// ---------------------------------------------------------------------------
// Property 1: Field-order contiguous invariant
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 1: Field-order contiguous invariant

describe("Property 1: Field-order contiguous invariant", () => {
  /**
   * Validates: Requirements 2.2, 3.1, 5.2
   */
  it("after any sequence of add/remove/reorder operations, fieldOrder values always form 0..n-1", () => {
    const addOp = fc.record({
      kind: fc.constant("add" as const),
      type: fieldTypeArb,
    });
    const removeOp = fc.record({
      kind: fc.constant("remove" as const),
      index: fc.nat(),
    });
    const reorderOp = fc.record({
      kind: fc.constant("reorder" as const),
      from: fc.nat(),
      to: fc.nat(),
    });
    const operationArb = fc.oneof(addOp, removeOp, reorderOp);

    fc.assert(
      fc.property(fc.array(operationArb, { minLength: 1, maxLength: 20 }), (ops) => {
        useTemplateBuilderStore.getState().resetBuilder();

        for (const op of ops) {
          const { fields } = getState();
          const n = fields.length;

          if (op.kind === "add" && n < 50) {
            const dropIndex = n === 0 ? 0 : op.type.length % (n + 1);
            getState().addField(op.type, dropIndex);
          } else if (op.kind === "remove" && n > 0) {
            const idx = op.index % n;
            getState().removeField(fields[idx].id);
          } else if (op.kind === "reorder" && n > 1) {
            const from = op.from % n;
            const to = op.to % n;
            getState().reorderField(from, to);
          }

          // Invariant must hold after every operation
          assertContiguousFieldOrder();
        }
      }),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 2: Add field produces correct Canvas_Field
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 2: Add field produces correct Canvas_Field

describe("Property 2: Add field produces correct Canvas_Field", () => {
  /**
   * Validates: Requirements 2.1
   */
  it("addField produces correct type, default label, UUID v4 id, and fieldOrder at drop index", () => {
    fc.assert(
      fc.property(
        fieldTypeArb,
        fc.nat({ max: 10 }),
        fc.nat({ max: 50 }),
        (type, preCount, rawDropIndex) => {
          useTemplateBuilderStore.getState().resetBuilder();

          // Add some pre-existing fields
          const actualPreCount = Math.min(preCount, 49);
          for (let i = 0; i < actualPreCount; i++) {
            getState().addField("Text", i);
          }

          const dropIndex = Math.min(rawDropIndex, actualPreCount);
          const prevLength = getState().fields.length;

          getState().addField(type, dropIndex);

          const { fields } = getState();
          expect(fields.length).toBe(prevLength + 1);

          // The newly added field is at the drop index position
          const newField = fields[dropIndex];
          expect(newField.type).toBe(type);
          expect(newField.label).toBe(`${type} Field`);
          expect(newField.id).toMatch(UUID_V4_REGEX);
          expect(newField.fieldOrder).toBe(dropIndex);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 3: Reorder to same position is idempotent
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 3: Reorder to same position is idempotent

describe("Property 3: Reorder to same position is idempotent", () => {
  /**
   * Validates: Requirements 3.5
   */
  it("reordering from index i to index i leaves all fieldOrder values and field identities unchanged", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        fc.nat(),
        (fieldCount, rawIndex) => {
          useTemplateBuilderStore.getState().resetBuilder();

          for (let i = 0; i < fieldCount; i++) {
            getState().addField("Text", i);
          }

          const idx = rawIndex % fieldCount;
          const fieldsBefore = getState().fields.map((f) => ({
            id: f.id,
            fieldOrder: f.fieldOrder,
            label: f.label,
            type: f.type,
          }));

          getState().reorderField(idx, idx);

          const fieldsAfter = getState().fields.map((f) => ({
            id: f.id,
            fieldOrder: f.fieldOrder,
            label: f.label,
            type: f.type,
          }));

          expect(fieldsAfter).toEqual(fieldsBefore);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 4: Selection preserved across reorder
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 4: Selection preserved across reorder

describe("Property 4: Selection preserved across reorder", () => {
  /**
   * Validates: Requirements 3.6
   */
  it("selectedFieldId remains unchanged after any valid reorder operation", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2, max: 10 }),
        fc.nat(),
        fc.nat(),
        fc.nat(),
        (fieldCount, rawSelectedIdx, rawFrom, rawTo) => {
          useTemplateBuilderStore.getState().resetBuilder();

          for (let i = 0; i < fieldCount; i++) {
            getState().addField("Text", i);
          }

          const selectedIdx = rawSelectedIdx % fieldCount;
          const selectedId = getState().fields[selectedIdx].id;
          getState().selectField(selectedId);

          const from = rawFrom % fieldCount;
          const to = rawTo % fieldCount;
          getState().reorderField(from, to);

          expect(getState().selectedFieldId).toBe(selectedId);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 5: Field property update propagation
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 5: Field property update propagation

describe("Property 5: Field property update propagation", () => {
  /**
   * Validates: Requirements 4.3, 4.4
   */
  it("updateFieldLabel/updateFieldType correctly updates the field and reading it back returns the new value", () => {
    fc.assert(
      fc.property(
        fieldTypeArb,
        fieldTypeArb,
        fc.string({ minLength: 1, maxLength: 200 }),
        (initialType, newType, newLabel) => {
          useTemplateBuilderStore.getState().resetBuilder();

          getState().addField(initialType, 0);
          const fieldId = getState().fields[0].id;

          // Update label
          getState().updateFieldLabel(fieldId, newLabel);
          expect(getState().fields[0].label).toBe(newLabel);

          // Update type
          getState().updateFieldType(fieldId, newType);
          expect(getState().fields[0].type).toBe(newType);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 6: Field label validation
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 6: Field label validation

describe("Property 6: Field label validation", () => {
  /**
   * Validates: Requirements 4.5
   */
  it("empty strings return error, strings > 200 chars return error, all others return no error", () => {
    // Empty string always errors
    expect(validateFieldLabel("")).not.toBeNull();

    // Strings > 200 chars always error
    fc.assert(
      fc.property(
        fc.string({ minLength: 201, maxLength: 500 }),
        (longStr) => {
          expect(validateFieldLabel(longStr)).not.toBeNull();
        }
      ),
      { numRuns: 100 }
    );

    // Valid strings (1-200 chars) return no error
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }),
        (validStr) => {
          expect(validateFieldLabel(validStr)).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 7: Template name validation
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 7: Template name validation

describe("Property 7: Template name validation", () => {
  /**
   * Validates: Requirements 6.2
   */
  it("empty/whitespace-only strings return error, strings > 500 chars return error, all others return no error", () => {
    // Empty string always errors
    expect(validateTemplateName("")).not.toBeNull();

    // Whitespace-only strings always error
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(" ", "\t", "\n", "\r"), { minLength: 1, maxLength: 50 }).map(
          (chars) => chars.join("")
        ),
        (wsStr) => {
          expect(validateTemplateName(wsStr)).not.toBeNull();
        }
      ),
      { numRuns: 100 }
    );

    // Strings > 500 chars always error
    fc.assert(
      fc.property(
        fc.string({ minLength: 501, maxLength: 1000 }),
        (longStr) => {
          expect(validateTemplateName(longStr)).not.toBeNull();
        }
      ),
      { numRuns: 100 }
    );

    // Valid strings (1-500 chars with at least one non-whitespace) return no error
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0),
        (validStr) => {
          expect(validateTemplateName(validStr)).toBeNull();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 8: Remove field correctness
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 8: Remove field correctness

describe("Property 8: Remove field correctness", () => {
  /**
   * Validates: Requirements 5.1
   */
  it("removing a field decreases list length by 1 and the removed id no longer appears", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 15 }),
        fc.nat(),
        (fieldCount, rawIndex) => {
          useTemplateBuilderStore.getState().resetBuilder();

          for (let i = 0; i < fieldCount; i++) {
            getState().addField("Text", i);
          }

          const idx = rawIndex % fieldCount;
          const fieldToRemove = getState().fields[idx];
          const prevLength = getState().fields.length;

          getState().removeField(fieldToRemove.id);

          const { fields } = getState();
          expect(fields.length).toBe(prevLength - 1);
          expect(fields.find((f) => f.id === fieldToRemove.id)).toBeUndefined();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 9: Selection consistency on removal
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 9: Selection consistency on removal

describe("Property 9: Selection consistency on removal", () => {
  /**
   * Validates: Requirements 5.3, 5.4
   */
  it("removing the selected field clears selection; removing a non-selected field preserves selection", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2, max: 10 }),
        fc.nat(),
        fc.nat(),
        fc.boolean(),
        (fieldCount, rawSelectedIdx, rawRemoveIdx, removeSelected) => {
          useTemplateBuilderStore.getState().resetBuilder();

          for (let i = 0; i < fieldCount; i++) {
            getState().addField("Integer", i);
          }

          const selectedIdx = rawSelectedIdx % fieldCount;
          const selectedId = getState().fields[selectedIdx].id;
          getState().selectField(selectedId);

          if (removeSelected) {
            // Remove the selected field
            getState().removeField(selectedId);
            expect(getState().selectedFieldId).toBeNull();
          } else {
            // Remove a different field
            const otherIdx =
              rawRemoveIdx % fieldCount === selectedIdx
                ? (rawRemoveIdx + 1) % fieldCount
                : rawRemoveIdx % fieldCount;
            const otherId = getState().fields[otherIdx].id;
            getState().removeField(otherId);
            expect(getState().selectedFieldId).toBe(selectedId);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 13: Dirty state tracking
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 13: Dirty state tracking

describe("Property 13: Dirty state tracking", () => {
  /**
   * Validates: Requirements 11.1, 11.6
   */
  it("any mutation sets isDirty to true, and markClean sets it to false", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(
          "addField",
          "removeField",
          "reorderField",
          "updateFieldLabel",
          "updateFieldType",
          "setTemplateName"
        ),
        fieldTypeArb,
        fc.string({ minLength: 1, maxLength: 100 }),
        (mutation, type, strValue) => {
          useTemplateBuilderStore.getState().resetBuilder();

          // Ensure we start clean
          expect(getState().isDirty).toBe(false);

          // Pre-populate fields for mutations that need them
          if (
            mutation === "removeField" ||
            mutation === "reorderField" ||
            mutation === "updateFieldLabel" ||
            mutation === "updateFieldType"
          ) {
            getState().addField("Text", 0);
            getState().addField("Float", 1);
            // Reset dirty to test the specific mutation
            getState().markClean();
            expect(getState().isDirty).toBe(false);
          }

          // Apply the mutation
          switch (mutation) {
            case "addField":
              getState().addField(type, 0);
              break;
            case "removeField":
              getState().removeField(getState().fields[0].id);
              break;
            case "reorderField":
              getState().reorderField(0, 1);
              break;
            case "updateFieldLabel":
              getState().updateFieldLabel(getState().fields[0].id, strValue);
              break;
            case "updateFieldType":
              getState().updateFieldType(getState().fields[0].id, type);
              break;
            case "setTemplateName":
              getState().setTemplateName(strValue);
              break;
          }

          // After any mutation, isDirty must be true
          expect(getState().isDirty).toBe(true);

          // markClean resets it
          getState().markClean();
          expect(getState().isDirty).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 10: Serialization correctness
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 10: Serialization correctness

describe("Property 10: Serialization correctness", () => {
  /**
   * Validates: Requirements 7.1, 9.1, 9.2, 9.4
   */
  it("serializeTemplate produces correct name, fields ordered by fieldOrder, only label+type per entry, correct array length", () => {
    const validLabelArb = fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.length >= 1);
    const validNameArb = fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0);

    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 50 }),
        validNameArb,
        fc.nat({ max: 10000 }),
        (fieldCount, templateName, userId) => {
          // Generate fields with reversed fieldOrder to test sorting
          const fields: Array<{ id: string; label: string; type: string; fieldOrder: number }> = [];
          const orders = Array.from({ length: fieldCount }, (_, i) => i);
          orders.reverse();

          for (let i = 0; i < fieldCount; i++) {
            fields.push({
              id: crypto.randomUUID(),
              label: `Field ${i + 1}`,
              type: ["Text", "Float", "Integer", "Date", "Boolean"][i % 5],
              fieldOrder: orders[i],
            });
          }

          const payload = serializeTemplate(fields, templateName, userId);

          // (a) name equals trimmed templateName
          expect(payload.name).toBe(templateName.trim());

          // (b) json_schema.fields is ordered by ascending fieldOrder
          const sortedFields = [...fields].sort((a, b) => a.fieldOrder - b.fieldOrder);
          for (let i = 0; i < sortedFields.length; i++) {
            expect(payload.json_schema.fields[i].label).toBe(sortedFields[i].label);
            expect(payload.json_schema.fields[i].type).toBe(sortedFields[i].type);
          }

          // (c) each entry contains only label and type (no id, field_uuid, or field_order)
          for (const entry of payload.json_schema.fields) {
            const keys = Object.keys(entry);
            expect(keys).toContain("label");
            expect(keys).toContain("type");
            expect(keys).not.toContain("id");
            expect(keys).not.toContain("field_uuid");
            expect(keys).not.toContain("field_order");
            expect(keys).not.toContain("fieldOrder");
            expect(keys.length).toBe(2);
          }

          // (d) array length equals number of canvas fields
          expect(payload.json_schema.fields.length).toBe(fieldCount);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("serializeTemplate with randomly generated valid labels and types", () => {
    const validLabelArb = fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.length >= 1);
    const validNameArb = fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0);

    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.uuid(),
            label: validLabelArb,
            type: fieldTypeArb,
            fieldOrder: fc.nat({ max: 100 }),
          }),
          { minLength: 1, maxLength: 50 }
        ),
        validNameArb,
        fc.nat({ max: 10000 }),
        (fields, templateName, userId) => {
          // Assign unique contiguous fieldOrder values
          const fieldsWithOrder = fields.map((f, i) => ({ ...f, fieldOrder: i }));
          // Shuffle to test sorting
          const shuffled = [...fieldsWithOrder].sort(() => Math.random() - 0.5);

          const payload = serializeTemplate(shuffled, templateName, userId);

          // name equals trimmed templateName
          expect(payload.name).toBe(templateName.trim());

          // fields ordered by fieldOrder ascending
          const sorted = [...shuffled].sort((a, b) => a.fieldOrder - b.fieldOrder);
          for (let i = 0; i < sorted.length; i++) {
            expect(payload.json_schema.fields[i].label).toBe(sorted[i].label);
            expect(payload.json_schema.fields[i].type).toBe(sorted[i].type);
          }

          // correct array length
          expect(payload.json_schema.fields.length).toBe(fields.length);

          // only label and type per entry
          for (const entry of payload.json_schema.fields) {
            expect(Object.keys(entry).sort()).toEqual(["label", "type"]);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 11: Serialization round-trip preserves field data
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 11: Serialization round-trip preserves field data

describe("Property 11: Serialization round-trip preserves field data", () => {
  /**
   * Validates: Requirements 9.3
   */
  it("serializing and mapping back preserves each field's label and type in the same order", () => {
    const validLabelArb = fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.length >= 1);
    const validNameArb = fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0);

    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.uuid(),
            label: validLabelArb,
            type: fieldTypeArb,
            fieldOrder: fc.nat({ max: 100 }),
          }),
          { minLength: 1, maxLength: 50 }
        ),
        validNameArb,
        fc.nat({ max: 10000 }),
        (fields, templateName, userId) => {
          // Assign contiguous fieldOrder so we know the expected order
          const orderedFields = fields.map((f, i) => ({ ...f, fieldOrder: i }));

          const payload = serializeTemplate(orderedFields, templateName, userId);

          // Map serialized fields back and verify they match original order
          const serializedFields = payload.json_schema.fields;

          expect(serializedFields.length).toBe(orderedFields.length);

          for (let i = 0; i < orderedFields.length; i++) {
            expect(serializedFields[i].label).toBe(orderedFields[i].label);
            expect(serializedFields[i].type).toBe(orderedFields[i].type);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("serializing shuffled fields and mapping back preserves data in fieldOrder-sorted order", () => {
    const validLabelArb = fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.length >= 1);
    const validNameArb = fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0);

    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.uuid(),
            label: validLabelArb,
            type: fieldTypeArb,
          }),
          { minLength: 1, maxLength: 50 }
        ),
        validNameArb,
        fc.nat({ max: 10000 }),
        (fields, templateName, userId) => {
          // Assign fieldOrder in reverse to ensure sorting is tested
          const orderedFields = fields.map((f, i) => ({
            ...f,
            fieldOrder: fields.length - 1 - i,
          }));

          const payload = serializeTemplate(orderedFields, templateName, userId);

          // The serialized output should be sorted by fieldOrder ascending
          const expectedOrder = [...orderedFields].sort(
            (a, b) => a.fieldOrder - b.fieldOrder
          );

          for (let i = 0; i < expectedOrder.length; i++) {
            expect(payload.json_schema.fields[i].label).toBe(expectedOrder[i].label);
            expect(payload.json_schema.fields[i].type).toBe(expectedOrder[i].type);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ---------------------------------------------------------------------------
// Property 12: Submission guard
// ---------------------------------------------------------------------------
// Feature: template-builder-frontend, Property 12: Submission guard

describe("Property 12: Submission guard", () => {
  /**
   * Validates: Requirements 9.5
   */
  it("canSave returns false when fields are empty", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0),
        (validName) => {
          useTemplateBuilderStore.getState().resetBuilder();
          // Set a valid name but no fields
          getState().setTemplateName(validName);

          expect(getState().canSave()).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when any field has an empty label", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length > 0),
        fc.integer({ min: 1, max: 10 }),
        fc.nat(),
        (validName, fieldCount, rawEmptyIdx) => {
          useTemplateBuilderStore.getState().resetBuilder();
          getState().setTemplateName(validName);

          // Add fields
          for (let i = 0; i < fieldCount; i++) {
            getState().addField("Text", i);
          }

          // Set one field's label to empty
          const emptyIdx = rawEmptyIdx % fieldCount;
          const fieldId = getState().fields[emptyIdx].id;
          getState().updateFieldLabel(fieldId, "");

          expect(getState().canSave()).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when name is empty or whitespace-only", () => {
    const whitespaceOnlyArb = fc
      .array(fc.constantFrom(" ", "\t", "\n", "\r"), { minLength: 0, maxLength: 20 })
      .map((chars) => chars.join(""));

    fc.assert(
      fc.property(whitespaceOnlyArb, (emptyOrWsName) => {
        useTemplateBuilderStore.getState().resetBuilder();
        getState().setTemplateName(emptyOrWsName);

        // Add at least one valid field
        getState().addField("Text", 0);

        expect(getState().canSave()).toBe(false);
      }),
      { numRuns: 100 }
    );
  });
});
