import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { serializeTemplate, deserializeTemplate } from "../templateBuilderStore";
import type {
  CanvasItem,
  CanvasFieldElement,
  CanvasContentBlockElement,
  FieldType,
  ContentBlockType,
  TextFieldConfig,
  FloatFieldConfig,
  IntegerFieldConfig,
  DateFieldConfig,
  BooleanFieldConfig,
  FieldConfig,
  TemplateCreatePayload,
} from "../../types/template";

/**
 * Feature: template-builder-enhancements, Property 1: Serialization Round-Trip
 *
 * Validates: Requirements 18.5, 18.1, 18.2, 18.3, 18.4
 *
 * For any valid canvas state containing at least one field element (with any
 * combination of field types, configurations, content blocks, and ordering),
 * serializing the canvas to the backend payload format and then deserializing
 * back to a canvas element list SHALL preserve each element's type, label/text,
 * configuration properties, and relative order.
 */

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

const fieldTypeArb: fc.Arbitrary<FieldType> = fc.constantFrom(
  "Text",
  "Float",
  "Integer",
  "Date",
  "Boolean"
);

const contentBlockTypeArb: fc.Arbitrary<ContentBlockType> = fc.constantFrom(
  "heading_h1",
  "heading_h2",
  "heading_h3",
  "paragraph",
  "divider"
);

const textFieldConfigArb: fc.Arbitrary<TextFieldConfig> = fc.record(
  {
    min_length: fc.option(fc.integer({ min: 0, max: 1000 }), { nil: undefined }),
    max_length: fc.option(fc.integer({ min: 1, max: 5000 }), { nil: undefined }),
    placeholder: fc.option(
      fc.string({ minLength: 0, maxLength: 200 }),
      { nil: undefined }
    ),
    regex_pattern: fc.option(
      fc.constantFrom("^[a-z]+$", "\\d{3}-\\d{4}", "[A-Z]{2,5}", undefined),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const floatFieldConfigArb: fc.Arbitrary<FloatFieldConfig> = fc.record(
  {
    decimal_precision: fc.option(fc.integer({ min: 0, max: 10 }), { nil: undefined }),
    min_value: fc.option(fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
    max_value: fc.option(fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }), { nil: undefined }),
    unit_label: fc.option(
      fc.string({ minLength: 1, maxLength: 50 }),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const integerFieldConfigArb: fc.Arbitrary<IntegerFieldConfig> = fc.record(
  {
    min_value: fc.option(fc.integer({ min: -100000, max: 100000 }), { nil: undefined }),
    max_value: fc.option(fc.integer({ min: -100000, max: 100000 }), { nil: undefined }),
    step_size: fc.option(fc.integer({ min: 1, max: 100 }), { nil: undefined }),
    unit_label: fc.option(
      fc.string({ minLength: 1, maxLength: 50 }),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

const dateFormatArb = fc.constantFrom(
  "YYYY-MM-DD" as const,
  "DD/MM/YYYY" as const,
  "MM/DD/YYYY" as const,
  "DD-MMM-YYYY" as const
);

const dateFieldConfigArb: fc.Arbitrary<DateFieldConfig> = fc.record(
  {
    min_date: fc.option(
      fc.constantFrom("2020-01-01", "2023-06-15", "2024-12-31"),
      { nil: undefined }
    ),
    max_date: fc.option(
      fc.constantFrom("2025-01-01", "2030-12-31", "2028-06-30"),
      { nil: undefined }
    ),
    date_format: fc.option(dateFormatArb, { nil: undefined }),
  },
  { requiredKeys: [] }
);

const booleanFieldConfigArb: fc.Arbitrary<BooleanFieldConfig> = fc.record(
  {
    true_label: fc.option(
      fc.string({ minLength: 1, maxLength: 50 }),
      { nil: undefined }
    ),
    false_label: fc.option(
      fc.string({ minLength: 1, maxLength: 50 }),
      { nil: undefined }
    ),
  },
  { requiredKeys: [] }
);

function fieldConfigForType(type: FieldType): fc.Arbitrary<FieldConfig> {
  switch (type) {
    case "Text":
      return textFieldConfigArb;
    case "Float":
      return floatFieldConfigArb;
    case "Integer":
      return integerFieldConfigArb;
    case "Date":
      return dateFieldConfigArb;
    case "Boolean":
      return booleanFieldConfigArb;
  }
}

const canvasFieldElementArb: fc.Arbitrary<CanvasFieldElement> = fieldTypeArb.chain(
  (type) =>
    fc.record({
      id: fc.uuid(),
      element_type: fc.constant("field" as const),
      label: fc.string({ minLength: 1, maxLength: 200 }),
      type: fc.constant(type),
      fieldOrder: fc.constant(0), // Will be recalculated
      required: fc.boolean(),
      help_text: fc.option(fc.string({ minLength: 1, maxLength: 500 }), {
        nil: null,
      }),
      default_value: fc.option(fc.string({ minLength: 1, maxLength: 100 }), {
        nil: null,
      }),
      config: fieldConfigForType(type),
    })
);

const canvasContentBlockElementArb: fc.Arbitrary<CanvasContentBlockElement> =
  contentBlockTypeArb.chain((contentType) =>
    fc.record({
      id: fc.uuid(),
      element_type: fc.constant("content_block" as const),
      content_type: fc.constant(contentType),
      text:
        contentType === "divider"
          ? fc.constant(null)
          : fc.option(fc.string({ minLength: 1, maxLength: 200 }), { nil: null }),
      fieldOrder: fc.constant(0), // Will be recalculated
    })
  );

const canvasItemArb: fc.Arbitrary<CanvasItem> = fc.oneof(
  { weight: 3, arbitrary: canvasFieldElementArb },
  { weight: 2, arbitrary: canvasContentBlockElementArb }
);

/**
 * Generates a valid CanvasItem[] array with at least one field element
 * and contiguous fieldOrder values.
 */
const canvasItemsArb: fc.Arbitrary<CanvasItem[]> = fc
  .tuple(
    // Ensure at least one field element
    canvasFieldElementArb,
    fc.array(canvasItemArb, { minLength: 0, maxLength: 15 })
  )
  .map(([requiredField, rest]) => {
    const items = [requiredField, ...rest];
    // Assign contiguous fieldOrder values
    return items.map((item, index) => ({ ...item, fieldOrder: index }));
  });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Strips undefined values from a config object for comparison purposes,
 * since JSON serialization drops undefined values.
 */
function stripUndefined(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value !== undefined) {
      result[key] = value;
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Property Test
// ---------------------------------------------------------------------------

describe("Feature: template-builder-enhancements, Property 1: Serialization Round-Trip", () => {
  it("serialize → deserialize preserves element type, label/text, config, and relative order", () => {
    fc.assert(
      fc.property(canvasItemsArb, (items) => {
        // Serialize
        const payload = serializeTemplate(
          items,
          "Test Template",
          1
        ) as TemplateCreatePayload;

        // Verify payload has elements format
        expect(payload.json_schema.elements).toBeDefined();
        expect(payload.json_schema.elements.length).toBe(items.length);

        // Deserialize
        const deserialized = deserializeTemplate(payload.json_schema);

        // Verify same number of elements
        expect(deserialized.length).toBe(items.length);

        // Verify each element preserves type, label/text, config, and relative order
        for (let i = 0; i < items.length; i++) {
          const original = items[i];
          const restored = deserialized[i];

          // Element type preserved
          expect(restored.element_type).toBe(original.element_type);

          // Relative order preserved (fieldOrder should be contiguous 0-based)
          expect(restored.fieldOrder).toBe(i);

          if (original.element_type === "field" && restored.element_type === "field") {
            const origField = original as CanvasFieldElement;
            const restoredField = restored as CanvasFieldElement;

            // Label preserved
            expect(restoredField.label).toBe(origField.label);
            // Field type preserved
            expect(restoredField.type).toBe(origField.type);
            // Required preserved
            expect(restoredField.required).toBe(origField.required);
            // Help text preserved
            expect(restoredField.help_text).toBe(origField.help_text);
            // Default value preserved
            expect(restoredField.default_value).toBe(origField.default_value);
            // Config preserved (strip undefined for comparison since JSON drops them)
            const originalConfig = stripUndefined(
              origField.config as unknown as Record<string, unknown>
            );
            const restoredConfig = stripUndefined(
              restoredField.config as unknown as Record<string, unknown>
            );
            expect(restoredConfig).toEqual(originalConfig);
          } else if (
            original.element_type === "content_block" &&
            restored.element_type === "content_block"
          ) {
            const origBlock = original as CanvasContentBlockElement;
            const restoredBlock = restored as CanvasContentBlockElement;

            // Content type preserved
            expect(restoredBlock.content_type).toBe(origBlock.content_type);
            // Text preserved
            expect(restoredBlock.text).toBe(origBlock.text);
          }

          // IDs are regenerated (new UUIDs), so we don't compare them
        }
      }),
      { numRuns: 100 }
    );
  });
});
