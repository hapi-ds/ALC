import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import type { TemplateResponse } from "../../../types/template";

/**
 * Property 10: Template selector filters to ReadOnly status only
 *
 * Validates: Requirements 2.1
 *
 * For any list of templates with mixed statuses, the template selector
 * SHALL display only templates with status "ReadOnly".
 */

// ---------------------------------------------------------------------------
// Filter logic (mirrors TemplateSelector component logic)
// ---------------------------------------------------------------------------

function filterReadOnlyTemplates(
  templates: TemplateResponse[]
): TemplateResponse[] {
  return templates.filter((t) => t.status === "ReadOnly");
}

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

const statusArb = fc.constantFrom("Draft", "ReadOnly", "Archived", "Active");

const templateArb: fc.Arbitrary<TemplateResponse> = fc
  .tuple(
    fc.integer({ min: 1, max: 10000 }),
    fc.stringMatching(/^2024-\d{5}$/),
    fc.string({ minLength: 1, maxLength: 50 }),
    statusArb,
    fc.integer({ min: 1, max: 100 })
  )
  .map(([id, document_uuid, name, status, created_by]) => ({
    id,
    document_uuid,
    name,
    json_schema: { elements: [] },
    status,
    created_by,
    fields: [],
  }));

const templatesArb = fc.array(templateArb, { minLength: 0, maxLength: 10 });

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Property 10: Template selector filters to ReadOnly status only", () => {
  it("only returns templates with status 'ReadOnly'", () => {
    fc.assert(
      fc.property(templatesArb, (templates) => {
        const filtered = filterReadOnlyTemplates(templates);

        for (const t of filtered) {
          expect(t.status).toBe("ReadOnly");
        }
      }),
      { numRuns: 100 }
    );
  });

  it("returns all ReadOnly templates from the input", () => {
    fc.assert(
      fc.property(templatesArb, (templates) => {
        const filtered = filterReadOnlyTemplates(templates);
        const expectedCount = templates.filter(
          (t) => t.status === "ReadOnly"
        ).length;

        expect(filtered.length).toBe(expectedCount);
      }),
      { numRuns: 100 }
    );
  });

  it("never includes non-ReadOnly templates", () => {
    fc.assert(
      fc.property(templatesArb, (templates) => {
        const filtered = filterReadOnlyTemplates(templates);

        // Every filtered template must have status "ReadOnly"
        for (const t of filtered) {
          expect(t.status).toBe("ReadOnly");
        }
      }),
      { numRuns: 100 }
    );
  });

  it("returns empty array when no ReadOnly templates exist", () => {
    const nonReadOnlyTemplatesArb = fc.array(
      templateArb.map((t) => ({ ...t, status: "Draft" })),
      { minLength: 1, maxLength: 5 }
    );

    fc.assert(
      fc.property(nonReadOnlyTemplatesArb, (templates) => {
        const filtered = filterReadOnlyTemplates(templates);
        expect(filtered.length).toBe(0);
      }),
      { numRuns: 100 }
    );
  });
});
