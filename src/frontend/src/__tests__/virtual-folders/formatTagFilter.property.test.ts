import * as fc from "fast-check";
import { describe, it, expect } from "vitest";
import { formatTagFilter } from "../../lib/virtualFolderUtils";
import type { TagFilter } from "../../types/virtualFolder";

/**
 * Property 1: Tag filter display text derivation
 *
 * For any valid TagFilter object, formatTagFilter SHALL produce a string that
 * contains every tag name from tag_filter.tags (if present and non-empty) and
 * the status value from tag_filter.status (if present), and SHALL return
 * "No filter" only when both fields are absent or empty.
 *
 * **Validates: Requirements 1.3**
 */
describe("virtual-folders-frontend properties", () => {
  it("Feature: virtual-folders-frontend, Property 1: Tag filter display text derivation", () => {
    fc.assert(
      fc.property(
        fc.record({
          tags: fc.option(
            fc.array(fc.string({ minLength: 1, maxLength: 50 }), { minLength: 0, maxLength: 20 }),
            { nil: undefined }
          ),
          status: fc.option(
            fc.constantFrom("Draft", "Active", "Approved", "InTraining", "Retired"),
            { nil: undefined }
          ),
        }),
        (filter: TagFilter) => {
          const result = formatTagFilter(filter);

          // When tags are present and non-empty, result must contain every tag name
          if (filter.tags && filter.tags.length > 0) {
            for (const tag of filter.tags) {
              expect(result).toContain(tag);
            }
          }

          // When status is present, result must contain the status value
          if (filter.status) {
            expect(result).toContain(filter.status);
          }

          // "No filter" is returned only when both tags and status are absent/empty
          if (!filter.tags?.length && !filter.status) {
            expect(result).toBe("No filter");
          }

          // Conversely, when either is present, result must NOT be "No filter"
          if ((filter.tags && filter.tags.length > 0) || filter.status) {
            expect(result).not.toBe("No filter");
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
