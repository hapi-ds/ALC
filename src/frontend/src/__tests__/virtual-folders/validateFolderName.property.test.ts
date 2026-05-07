import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { validateFolderName } from "../../lib/virtualFolderUtils";

/**
 * Feature: virtual-folders-frontend, Property 2: Folder name validation rejects whitespace-only input
 *
 * Validates: Requirements 2.2, 3.2
 *
 * For any string composed entirely of whitespace characters (spaces, tabs, newlines),
 * the folder name validation logic SHALL reject it.
 * For any string of 1–200 characters that contains at least one non-whitespace character,
 * the validation logic SHALL accept it.
 */

describe("Feature: virtual-folders-frontend, Property 2: Folder name validation rejects whitespace-only input", () => {
  it("rejects any string composed entirely of whitespace characters", () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(" ", "\t", "\n", "\r", "\f", "\v"), { minLength: 1, maxLength: 50 }).map((arr) => arr.join("")),
        (whitespaceOnly) => {
          const result = validateFolderName(whitespaceOnly);
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("accepts any string of 1–200 characters with at least one non-whitespace character", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length >= 1 && s.trim().length <= 200),
        (validName) => {
          const result = validateFolderName(validName);
          expect(result.valid).toBe(true);
          expect(result.error).toBeUndefined();
        }
      ),
      { numRuns: 100 }
    );
  });
});
