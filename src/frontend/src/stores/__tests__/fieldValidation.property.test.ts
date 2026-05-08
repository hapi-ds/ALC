import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { validateDefaultValue, validateMinMax, validateDateRange, validateRegexPattern } from "../templateBuilderStore";
import type { FieldType } from "@/types/template";

/**
 * Feature: template-builder-enhancements, Property 3: Default Value Type Validation
 *
 * Validates: Requirements 1.5, 1.6
 *
 * For any field type and any candidate default value string, the default value
 * validation function SHALL accept the value if and only if it conforms to the
 * type constraints (parseable as integer for Integer, parseable as float for Float,
 * valid ISO 8601 date for Date, "true" or "false" for Boolean, any non-empty string
 * for Text).
 */
describe("Feature: template-builder-enhancements, Property 3: Default Value Type Validation", () => {
  // Generators
  const fieldTypeArb: fc.Arbitrary<FieldType> = fc.constantFrom(
    "Text",
    "Float",
    "Integer",
    "Date",
    "Boolean"
  );

  // Generate valid integers (no decimals)
  const validIntegerStringArb = fc.integer().map((n) => n.toString());

  // Generate invalid integers (decimal numbers, non-numeric strings)
  const invalidIntegerStringArb = fc.oneof(
    fc.double({ noNaN: true, noDefaultInfinity: true })
      .filter((n) => !Number.isInteger(n))
      .map((n) => n.toString()),
    fc.string({ minLength: 1 }).filter((s) => {
      const parsed = Number(s);
      return isNaN(parsed) || !Number.isInteger(parsed);
    })
  );

  // Generate valid float strings (any parseable number)
  const validFloatStringArb = fc
    .double({ noNaN: true, noDefaultInfinity: true })
    .map((n) => n.toString());

  // Generate invalid float strings (non-numeric)
  const invalidFloatStringArb = fc
    .string({ minLength: 1 })
    .filter((s) => isNaN(Number(s)));

  // Generate valid ISO 8601 date strings
  const validDateStringArb = fc
    .date({
      min: new Date("1900-01-01"),
      max: new Date("2100-12-31"),
    })
    .map((d) => d.toISOString().split("T")[0]);

  // Generate invalid date strings
  const invalidDateStringArb = fc
    .string({ minLength: 1 })
    .filter((s) => isNaN(new Date(s).getTime()));

  // Generate valid boolean strings
  const validBooleanStringArb = fc.constantFrom("true", "false");

  // Generate invalid boolean strings
  const invalidBooleanStringArb = fc
    .string({ minLength: 1 })
    .filter((s) => s !== "true" && s !== "false");

  // Generate valid text strings (any non-empty string)
  const validTextStringArb = fc.string({ minLength: 1 });

  it("accepts valid integer strings and rejects invalid ones", () => {
    // Valid integers should be accepted
    fc.assert(
      fc.property(validIntegerStringArb, (value) => {
        const result = validateDefaultValue(value, "Integer");
        expect(result).toBeNull();
      }),
      { numRuns: 100 }
    );

    // Invalid integers should be rejected
    fc.assert(
      fc.property(invalidIntegerStringArb, (value) => {
        const result = validateDefaultValue(value, "Integer");
        expect(result).not.toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("accepts valid float strings and rejects invalid ones", () => {
    // Valid floats should be accepted
    fc.assert(
      fc.property(validFloatStringArb, (value) => {
        const result = validateDefaultValue(value, "Float");
        expect(result).toBeNull();
      }),
      { numRuns: 100 }
    );

    // Invalid floats should be rejected
    fc.assert(
      fc.property(invalidFloatStringArb, (value) => {
        const result = validateDefaultValue(value, "Float");
        expect(result).not.toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("accepts valid ISO 8601 date strings and rejects invalid ones", () => {
    // Valid dates should be accepted
    fc.assert(
      fc.property(validDateStringArb, (value) => {
        const result = validateDefaultValue(value, "Date");
        expect(result).toBeNull();
      }),
      { numRuns: 100 }
    );

    // Invalid dates should be rejected
    fc.assert(
      fc.property(invalidDateStringArb, (value) => {
        const result = validateDefaultValue(value, "Date");
        expect(result).not.toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("accepts only 'true' or 'false' for Boolean fields", () => {
    // Valid booleans should be accepted
    fc.assert(
      fc.property(validBooleanStringArb, (value) => {
        const result = validateDefaultValue(value, "Boolean");
        expect(result).toBeNull();
      }),
      { numRuns: 100 }
    );

    // Invalid booleans should be rejected
    fc.assert(
      fc.property(invalidBooleanStringArb, (value) => {
        const result = validateDefaultValue(value, "Boolean");
        expect(result).not.toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("accepts any non-empty string for Text fields", () => {
    fc.assert(
      fc.property(validTextStringArb, (value) => {
        const result = validateDefaultValue(value, "Text");
        expect(result).toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("accepts null or empty string for any field type (no default value set)", () => {
    fc.assert(
      fc.property(fieldTypeArb, (fieldType) => {
        expect(validateDefaultValue(null, fieldType)).toBeNull();
        expect(validateDefaultValue("", fieldType)).toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("for any random (FieldType, string) pair, acceptance matches type constraints", () => {
    const randomNonEmptyStringArb = fc.string({ minLength: 1 });

    fc.assert(
      fc.property(fieldTypeArb, randomNonEmptyStringArb, (fieldType, value) => {
        const result = validateDefaultValue(value, fieldType);
        const isAccepted = result === null;

        // Determine expected acceptance based on type constraints
        let shouldAccept: boolean;
        switch (fieldType) {
          case "Integer": {
            const parsed = Number(value);
            shouldAccept = !isNaN(parsed) && Number.isInteger(parsed);
            break;
          }
          case "Float": {
            shouldAccept = !isNaN(Number(value));
            break;
          }
          case "Date": {
            shouldAccept = !isNaN(new Date(value).getTime());
            break;
          }
          case "Boolean": {
            shouldAccept = value === "true" || value === "false";
            break;
          }
          case "Text": {
            shouldAccept = true; // Any non-empty string is valid
            break;
          }
        }

        expect(isAccepted).toBe(shouldAccept);
      }),
      { numRuns: 100 }
    );
  });
});


/**
 * Feature: template-builder-enhancements, Property 2: Cross-Field Min/Max Constraint Validation
 *
 * Validates: Requirements 2.4, 3.5, 4.4, 5.4, 20.3, 20.4, 20.5
 *
 * For any field configuration where both a minimum and maximum bound are specified
 * (min_length/max_length for Text, min_value/max_value for Float and Integer,
 * min_date/max_date for Date), the validation function SHALL return an error if and
 * only if the minimum exceeds the maximum, and SHALL return no error when minimum is
 * less than or equal to maximum.
 */
describe("Feature: template-builder-enhancements, Property 2: Cross-Field Min/Max Constraint Validation", () => {
  describe("validateMinMax — numeric pairs", () => {
    it("returns null (no error) when min <= max", () => {
      fc.assert(
        fc.property(
          fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.constantFrom("length", "value"),
          (min, offset, label) => {
            // Ensure max >= min by adding a non-negative offset
            const max = min + Math.abs(offset);
            const result = validateMinMax(min, max, label);
            expect(result).toBeNull();
          }
        ),
        { numRuns: 100 }
      );
    });

    it("returns an error when min > max", () => {
      fc.assert(
        fc.property(
          fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.constantFrom("length", "value"),
          (a, b, label) => {
            // Ensure min > max by sorting and using the larger as min
            const min = Math.max(a, b);
            const max = Math.min(a, b);
            fc.pre(min > max);
            const result = validateMinMax(min, max, label);
            expect(result).not.toBeNull();
            expect(result).toContain("must not exceed");
          }
        ),
        { numRuns: 100 }
      );
    });

    it("returns null when either min or max is undefined", () => {
      fc.assert(
        fc.property(
          fc.option(fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })),
          fc.option(fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })),
          fc.constantFrom("length", "value"),
          (min, max, label) => {
            // Only test cases where at least one is undefined
            fc.pre(min === null || max === null);
            const result = validateMinMax(
              min ?? undefined,
              max ?? undefined,
              label
            );
            expect(result).toBeNull();
          }
        ),
        { numRuns: 100 }
      );
    });

    it("returns null when min equals max (boundary case)", () => {
      fc.assert(
        fc.property(
          fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          fc.constantFrom("length", "value"),
          (value, label) => {
            const result = validateMinMax(value, value, label);
            expect(result).toBeNull();
          }
        ),
        { numRuns: 100 }
      );
    });
  });

  describe("validateDateRange — date pairs", () => {
    // Generator for valid ISO date strings using integer components to avoid invalid dates
    const isoDateArb = fc
      .integer({ min: 1900, max: 2100 })
      .chain((year) =>
        fc.integer({ min: 1, max: 12 }).chain((month) =>
          fc.integer({ min: 1, max: 28 }).map((day) => {
            const y = String(year).padStart(4, "0");
            const m = String(month).padStart(2, "0");
            const d = String(day).padStart(2, "0");
            return `${y}-${m}-${d}`;
          })
        )
      );

    it("returns null (no error) when minDate <= maxDate", () => {
      fc.assert(
        fc.property(
          isoDateArb,
          isoDateArb,
          (dateA, dateB) => {
            // Sort so min <= max
            const [minDate, maxDate] =
              dateA <= dateB ? [dateA, dateB] : [dateB, dateA];
            const result = validateDateRange(minDate, maxDate);
            expect(result).toBeNull();
          }
        ),
        { numRuns: 100 }
      );
    });

    it("returns an error when minDate > maxDate", () => {
      fc.assert(
        fc.property(
          isoDateArb,
          isoDateArb,
          (dateA, dateB) => {
            // Only test when dates are different and we can make min > max
            fc.pre(dateA !== dateB);
            const [minDate, maxDate] =
              dateA > dateB ? [dateA, dateB] : [dateB, dateA];
            const result = validateDateRange(minDate, maxDate);
            expect(result).not.toBeNull();
            expect(result).toContain("must not be later than");
          }
        ),
        { numRuns: 100 }
      );
    });

    it("returns null when either minDate or maxDate is undefined", () => {
      fc.assert(
        fc.property(
          fc.option(isoDateArb),
          fc.option(isoDateArb),
          (minDate, maxDate) => {
            // Only test cases where at least one is undefined/empty
            fc.pre(minDate === null || maxDate === null);
            const result = validateDateRange(
              minDate ?? undefined,
              maxDate ?? undefined
            );
            expect(result).toBeNull();
          }
        ),
        { numRuns: 100 }
      );
    });

    it("returns null when minDate equals maxDate (boundary case)", () => {
      fc.assert(
        fc.property(isoDateArb, (date) => {
          const result = validateDateRange(date, date);
          expect(result).toBeNull();
        }),
        { numRuns: 100 }
      );
    });
  });
});


/**
 * Feature: template-builder-enhancements, Property 4: Regex Pattern Validity
 *
 * Validates: Requirements 2.5, 2.6
 *
 * For any string provided as a regex pattern, the regex validation function SHALL
 * accept the string if and only if it is a syntactically valid JavaScript regular
 * expression (i.e., `new RegExp(pattern)` does not throw).
 */
describe("Feature: template-builder-enhancements, Property 4: Regex Pattern Validity", () => {
  /**
   * Helper: determines if a string is a valid regex by attempting construction.
   * This is the oracle function that mirrors the implementation's logic.
   */
  function isValidRegex(pattern: string): boolean {
    try {
      new RegExp(pattern);
      return true;
    } catch {
      return false;
    }
  }

  // Generator for known-valid regex patterns
  const validRegexArb: fc.Arbitrary<string> = fc.oneof(
    // Simple literal strings (always valid regex)
    fc.string({ minLength: 1, maxLength: 50 }).filter((s) => isValidRegex(s)),
    // Common regex patterns
    fc.constantFrom(
      "^[a-z]+$",
      "\\d{3}-\\d{4}",
      "[A-Z][a-z]*",
      "^\\w+@\\w+\\.\\w+$",
      "\\b\\w+\\b",
      "(foo|bar|baz)",
      "^.{1,100}$",
      "[0-9]{2,4}",
      "(?:abc)+",
      "a{2,5}"
    )
  );

  // Generator for known-invalid regex patterns (unbalanced brackets, bad quantifiers, etc.)
  const invalidRegexArb: fc.Arbitrary<string> = fc.constantFrom(
    "[",
    "(",
    "(?",
    "[a-",
    "*",
    "+",
    "?",
    "{",
    "\\",
    "(?P<name)",
    "[z-a]",
    "(?<=a{2,})",
    "((((",
    "[\\",
    "(?<)",
    "a{2,1}"
  ).filter((s) => !isValidRegex(s));

  // Generator for arbitrary strings (mix of valid and invalid)
  const arbitraryPatternArb: fc.Arbitrary<string> = fc.string({ minLength: 1, maxLength: 200 });

  it("accepts valid regex patterns (returns null)", () => {
    fc.assert(
      fc.property(validRegexArb, (pattern) => {
        const result = validateRegexPattern(pattern);
        expect(result).toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("rejects invalid regex patterns (returns error message)", () => {
    fc.assert(
      fc.property(invalidRegexArb, (pattern) => {
        const result = validateRegexPattern(pattern);
        expect(result).not.toBeNull();
        expect(result).toBe("Invalid regular expression pattern");
      }),
      { numRuns: 100 }
    );
  });

  it("for any arbitrary string, acceptance matches whether new RegExp(pattern) succeeds", () => {
    fc.assert(
      fc.property(arbitraryPatternArb, (pattern) => {
        const result = validateRegexPattern(pattern);
        const isAccepted = result === null;
        const expectedAccepted = isValidRegex(pattern);
        expect(isAccepted).toBe(expectedAccepted);
      }),
      { numRuns: 100 }
    );
  });

  it("returns null for undefined or empty string (no pattern set)", () => {
    expect(validateRegexPattern(undefined)).toBeNull();
    expect(validateRegexPattern("")).toBeNull();
  });
});
