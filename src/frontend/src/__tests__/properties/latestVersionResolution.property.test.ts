import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { resolveLatestVersion } from "../../lib/versionUtils";

// ---------------------------------------------------------------------------
// Arbitrary generators for version tuples
// ---------------------------------------------------------------------------

/**
 * Generator for a version object with non-negative major and minor version numbers.
 */
const arbVersion = fc.record({
  major_version: fc.integer({ min: 0, max: 1000 }),
  minor_version: fc.integer({ min: 0, max: 1000 }),
});

/**
 * Generator for a non-empty array of version objects.
 */
const arbNonEmptyVersions = fc.array(arbVersion, {
  minLength: 1,
  maxLength: 50,
});

// ---------------------------------------------------------------------------
// Property 5: Latest Version Resolution
// Validates: Requirements 4.3
// ---------------------------------------------------------------------------

describe("Feature: document-content-viewer, Property 5: Latest Version Resolution", () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * For any non-empty list of versions, the resolved latest version has the
   * maximum (major_version, minor_version) tuple compared lexicographically.
   */
  it("resolved latest version has the maximum (major, minor) tuple", () => {
    fc.assert(
      fc.property(arbNonEmptyVersions, (versions) => {
        const latest = resolveLatestVersion(versions);
        expect(latest).not.toBeNull();

        // Compute expected max manually
        const maxMajor = Math.max(...versions.map((v) => v.major_version));
        const versionsWithMaxMajor = versions.filter(
          (v) => v.major_version === maxMajor
        );
        const maxMinor = Math.max(
          ...versionsWithMaxMajor.map((v) => v.minor_version)
        );

        expect(latest!.major_version).toBe(maxMajor);
        expect(latest!.minor_version).toBe(maxMinor);
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 4.3**
   *
   * The latest version is always greater than or equal to every other version
   * in the list (no version has a higher (major, minor) tuple).
   */
  it("no version in the list has a higher (major, minor) tuple than the resolved latest", () => {
    fc.assert(
      fc.property(arbNonEmptyVersions, (versions) => {
        const latest = resolveLatestVersion(versions)!;

        for (const v of versions) {
          const isLessOrEqual =
            v.major_version < latest.major_version ||
            (v.major_version === latest.major_version &&
              v.minor_version <= latest.minor_version);
          expect(isLessOrEqual).toBe(true);
        }
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 4.3**
   *
   * The resolved latest version is always a member of the input array.
   */
  it("the resolved latest version exists in the input array", () => {
    fc.assert(
      fc.property(arbNonEmptyVersions, (versions) => {
        const latest = resolveLatestVersion(versions)!;

        const found = versions.some(
          (v) =>
            v.major_version === latest.major_version &&
            v.minor_version === latest.minor_version
        );
        expect(found).toBe(true);
      }),
      { numRuns: 200 }
    );
  });

  /**
   * **Validates: Requirements 4.3**
   *
   * For a single-element array, the resolved latest is that single element.
   */
  it("single-element array resolves to that element", () => {
    fc.assert(
      fc.property(arbVersion, (version) => {
        const latest = resolveLatestVersion([version]);
        expect(latest!.major_version).toBe(version.major_version);
        expect(latest!.minor_version).toBe(version.minor_version);
      }),
      { numRuns: 100 }
    );
  });

  /**
   * **Validates: Requirements 4.3**
   *
   * Resolving an empty array returns null.
   */
  it("empty array returns null", () => {
    const result = resolveLatestVersion([]);
    expect(result).toBeNull();
  });
});
