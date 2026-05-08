import { describe, it, expect, beforeEach, vi } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: template-builder-enhancements, Property 8: canSave Reflects Validation State
 *
 * Validates: Requirements 20.1, 20.6, 18.6, 18.7
 *
 * For any canvas state, the canSave() function SHALL return false if any of the
 * following conditions hold:
 *   (a) template name is empty or exceeds 500 characters
 *   (b) no field elements exist
 *   (c) any field has an empty label
 *   (d) any field has a cross-field constraint violation (fieldErrors non-empty)
 *   (e) content blocks with required text have empty text
 *   (f) save is in progress
 * Otherwise it SHALL return true.
 */

// Mock apiClient and auth dependencies (no actual API calls in this test)
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    constructor(status: number, body: string) {
      super(body);
      this.status = status;
      this.body = body;
    }
  },
  setAuthStoreAccessor: vi.fn(),
  setClearSessionFn: vi.fn(),
}));

vi.mock("@/lib/tokenStorage", () => ({
  getAccessToken: vi.fn(),
  setAccessToken: vi.fn(),
  clearAccessToken: vi.fn(),
  getTokenExpiry: vi.fn(),
}));

vi.mock("../authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 1 },
      activeCompanyId: 1,
    }),
    setState: vi.fn(),
  },
}));

import { useTemplateBuilderStore } from "../templateBuilderStore";
import type {
  FieldType,
  ContentBlockType,
  CanvasFieldElement,
  CanvasContentBlockElement,
  CanvasItem,
} from "../../types/template";

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

/** Generate a non-empty label (1-200 chars) */
const validLabelArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter((s) => s.trim().length > 0);

/** Generate a valid template name (1-500 chars, non-whitespace-only) */
const validTemplateNameArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 100 })
  .filter((s) => s.trim().length > 0 && s.length <= 500);

/** Generate a valid content block text for headers/paragraphs */
const validContentTextArb: fc.Arbitrary<string> = fc
  .string({ minLength: 1, maxLength: 50 })
  .filter((s) => s.trim().length > 0);

/** Generate a valid field element with no validation errors */
const validFieldElementArb: fc.Arbitrary<CanvasFieldElement> = fc.record({
  id: fc.uuid(),
  element_type: fc.constant("field" as const),
  label: validLabelArb,
  type: fieldTypeArb,
  fieldOrder: fc.constant(0), // will be recalculated
  required: fc.boolean(),
  help_text: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
  default_value: fc.constant(null),
  config: fc.constant({}),
});

/** Generate a valid content block element (with valid text for non-dividers) */
const validContentBlockArb: fc.Arbitrary<CanvasContentBlockElement> = contentBlockTypeArb.chain(
  (contentType) => {
    const text =
      contentType === "divider"
        ? fc.constant(null)
        : validContentTextArb.map((t) => t as string | null);

    return fc.record({
      id: fc.uuid(),
      element_type: fc.constant("content_block" as const),
      content_type: fc.constant(contentType),
      text,
      fieldOrder: fc.constant(0),
    });
  }
);

/** Generate a valid canvas state: at least one field, valid names, no errors */
const validCanvasStateArb = fc.record({
  templateName: validTemplateNameArb,
  fields: fc.array(validFieldElementArb, { minLength: 1, maxLength: 5 }),
  contentBlocks: fc.array(validContentBlockArb, { minLength: 0, maxLength: 3 }),
});

// ---------------------------------------------------------------------------
// Error condition generators
// ---------------------------------------------------------------------------

/** (a) Invalid template name: empty or exceeds 500 chars */
const invalidTemplateNameArb: fc.Arbitrary<string> = fc.oneof(
  // Empty or whitespace-only
  fc.constantFrom("", "   ", "\t", "\n"),
  // Exceeds 500 characters
  fc.string({ minLength: 501, maxLength: 510 })
);

/** (c) Field with empty label */
const fieldWithEmptyLabelArb: fc.Arbitrary<CanvasFieldElement> = fc.record({
  id: fc.uuid(),
  element_type: fc.constant("field" as const),
  label: fc.constantFrom("", "   ", "\t"),
  type: fieldTypeArb,
  fieldOrder: fc.constant(0),
  required: fc.boolean(),
  help_text: fc.constant(null),
  default_value: fc.constant(null),
  config: fc.constant({}),
});

/** (e) Content block with empty required text (heading or paragraph) */
const contentBlockWithEmptyTextArb: fc.Arbitrary<CanvasContentBlockElement> = fc.record({
  id: fc.uuid(),
  element_type: fc.constant("content_block" as const),
  content_type: fc.constantFrom(
    "heading_h1" as ContentBlockType,
    "heading_h2" as ContentBlockType,
    "heading_h3" as ContentBlockType,
    "paragraph" as ContentBlockType
  ),
  text: fc.constantFrom(null, "", "   "),
  fieldOrder: fc.constant(0),
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildItems(
  fields: CanvasFieldElement[],
  contentBlocks: CanvasContentBlockElement[]
): CanvasItem[] {
  const items: CanvasItem[] = [...fields, ...contentBlocks];
  // Assign contiguous fieldOrder
  items.forEach((item, i) => {
    item.fieldOrder = i;
  });
  return items;
}

/**
 * Derives the backward-compatible fields array from items (same as store logic).
 */
function deriveFields(items: CanvasItem[]) {
  return items
    .filter((item) => item.element_type === "field")
    .map((item) => {
      const f = item as CanvasFieldElement;
      return {
        id: f.id,
        label: f.label,
        type: f.type,
        fieldOrder: f.fieldOrder,
      };
    });
}

/**
 * Oracle function: independently computes whether canSave should return false.
 */
function shouldCanSaveBeFalse(
  templateName: string,
  items: CanvasItem[],
  fieldErrors: Record<string, string>,
  isSaving: boolean
): boolean {
  // (a) template name is empty or exceeds 500 chars
  if (templateName.trim().length === 0 || templateName.length > 500) {
    return true;
  }

  // (b) no field elements exist
  const fieldItems = items.filter((i) => i.element_type === "field") as CanvasFieldElement[];
  if (fieldItems.length === 0) {
    return true;
  }

  // (c) any field has an empty label
  if (fieldItems.some((f) => f.label.trim().length === 0)) {
    return true;
  }

  // (d) fieldErrors non-empty
  if (Object.keys(fieldErrors).length > 0) {
    return true;
  }

  // (e) content blocks with required text have empty text
  const contentBlocks = items.filter(
    (i): i is CanvasContentBlockElement => i.element_type === "content_block"
  );
  if (
    contentBlocks.some((block) => {
      if (
        block.content_type === "heading_h1" ||
        block.content_type === "heading_h2" ||
        block.content_type === "heading_h3" ||
        block.content_type === "paragraph"
      ) {
        return !block.text || block.text.trim().length === 0;
      }
      return false;
    })
  ) {
    return true;
  }

  // (f) save is in progress
  if (isSaving) {
    return true;
  }

  return false;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Feature: template-builder-enhancements, Property 8: canSave Reflects Validation State", () => {
  beforeEach(() => {
    useTemplateBuilderStore.getState().resetBuilder();
  });

  it("canSave returns true for valid canvas states with no error conditions", () => {
    fc.assert(
      fc.property(validCanvasStateArb, ({ templateName, fields, contentBlocks }) => {
        useTemplateBuilderStore.getState().resetBuilder();

        const items = buildItems(fields, contentBlocks);

        useTemplateBuilderStore.setState({
          templateName,
          items,
          fields: deriveFields(items),
          fieldErrors: {},
          isSaving: false,
          nameError: null,
        });

        const result = useTemplateBuilderStore.getState().canSave();
        expect(result).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when template name is empty or exceeds 500 chars", () => {
    fc.assert(
      fc.property(
        invalidTemplateNameArb,
        fc.array(validFieldElementArb, { minLength: 1, maxLength: 3 }),
        (templateName, fields) => {
          useTemplateBuilderStore.getState().resetBuilder();

          const items = buildItems(fields, []);

          useTemplateBuilderStore.setState({
            templateName,
            items,
            fields: deriveFields(items),
            fieldErrors: {},
            isSaving: false,
            nameError: null,
          });

          const result = useTemplateBuilderStore.getState().canSave();
          expect(result).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when no field elements exist (only content blocks)", () => {
    fc.assert(
      fc.property(
        validTemplateNameArb,
        fc.array(validContentBlockArb, { minLength: 0, maxLength: 5 }),
        (templateName, contentBlocks) => {
          useTemplateBuilderStore.getState().resetBuilder();

          // No field elements, only content blocks
          const items = buildItems([], contentBlocks);

          useTemplateBuilderStore.setState({
            templateName,
            items,
            fields: deriveFields(items),
            fieldErrors: {},
            isSaving: false,
            nameError: null,
          });

          const result = useTemplateBuilderStore.getState().canSave();
          expect(result).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when any field has an empty label", () => {
    fc.assert(
      fc.property(
        validTemplateNameArb,
        fc.array(validFieldElementArb, { minLength: 0, maxLength: 3 }),
        fieldWithEmptyLabelArb,
        (templateName, validFields, badField) => {
          useTemplateBuilderStore.getState().resetBuilder();

          // Include at least the bad field (which has an empty label)
          const allFields = [...validFields, badField];
          const items = buildItems(allFields, []);

          useTemplateBuilderStore.setState({
            templateName,
            items,
            fields: deriveFields(items),
            fieldErrors: {},
            isSaving: false,
            nameError: null,
          });

          const result = useTemplateBuilderStore.getState().canSave();
          expect(result).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when fieldErrors is non-empty (cross-field constraint violation)", () => {
    fc.assert(
      fc.property(
        validCanvasStateArb,
        fc.string({ minLength: 1, maxLength: 50 }),
        ({ templateName, fields, contentBlocks }, errorMsg) => {
          useTemplateBuilderStore.getState().resetBuilder();

          const items = buildItems(fields, contentBlocks);
          // Set a field error on the first field
          const fieldErrors: Record<string, string> = {
            [fields[0].id]: errorMsg,
          };

          useTemplateBuilderStore.setState({
            templateName,
            items,
            fields: deriveFields(items),
            fieldErrors,
            isSaving: false,
            nameError: null,
          });

          const result = useTemplateBuilderStore.getState().canSave();
          expect(result).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when content blocks with required text have empty text", () => {
    fc.assert(
      fc.property(
        validTemplateNameArb,
        fc.array(validFieldElementArb, { minLength: 1, maxLength: 3 }),
        contentBlockWithEmptyTextArb,
        (templateName, fields, badBlock) => {
          useTemplateBuilderStore.getState().resetBuilder();

          const items = buildItems(fields, [badBlock]);

          useTemplateBuilderStore.setState({
            templateName,
            items,
            fields: deriveFields(items),
            fieldErrors: {},
            isSaving: false,
            nameError: null,
          });

          const result = useTemplateBuilderStore.getState().canSave();
          expect(result).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("canSave returns false when save is in progress", () => {
    fc.assert(
      fc.property(validCanvasStateArb, ({ templateName, fields, contentBlocks }) => {
        useTemplateBuilderStore.getState().resetBuilder();

        const items = buildItems(fields, contentBlocks);

        useTemplateBuilderStore.setState({
          templateName,
          items,
          fields: deriveFields(items),
          fieldErrors: {},
          isSaving: true,
          nameError: null,
        });

        const result = useTemplateBuilderStore.getState().canSave();
        expect(result).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("canSave returns false iff any validation condition holds (combined random states)", () => {
    // Generate random canvas states with random error conditions mixed in
    const randomCanvasStateArb = fc.record({
      templateName: fc.oneof(validTemplateNameArb, invalidTemplateNameArb),
      fields: fc.array(
        fc.oneof(validFieldElementArb, fieldWithEmptyLabelArb),
        { minLength: 0, maxLength: 5 }
      ),
      contentBlocks: fc.array(
        fc.oneof(validContentBlockArb, contentBlockWithEmptyTextArb),
        { minLength: 0, maxLength: 3 }
      ),
      hasFieldErrors: fc.boolean(),
      isSaving: fc.boolean(),
    });

    fc.assert(
      fc.property(randomCanvasStateArb, ({ templateName, fields, contentBlocks, hasFieldErrors, isSaving }) => {
        useTemplateBuilderStore.getState().resetBuilder();

        const items = buildItems(fields, contentBlocks);

        const fieldErrors: Record<string, string> = {};
        if (hasFieldErrors && fields.length > 0) {
          fieldErrors[fields[0].id] = "Minimum value must not exceed maximum value";
        }

        useTemplateBuilderStore.setState({
          templateName,
          items,
          fields: deriveFields(items),
          fieldErrors,
          isSaving,
          nameError: null,
        });

        const result = useTemplateBuilderStore.getState().canSave();
        const expectedFalse = shouldCanSaveBeFalse(templateName, items, fieldErrors, isSaving);

        expect(result).toBe(!expectedFalse);
      }),
      { numRuns: 100 }
    );
  });
});
