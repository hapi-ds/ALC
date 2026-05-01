/**
 * Unit tests for the URS parser utility.
 *
 * Tests that the parser correctly extracts REQ-XX-NN identifiers
 * from URS markdown files.
 */

import { test, expect } from "@playwright/test";
import { parseURS } from "../../utils/urs-parser";
import { writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const TEST_DIR = join(tmpdir(), "urs-parser-test-" + Date.now());

test.beforeAll(() => {
  mkdirSync(TEST_DIR, { recursive: true });
});

test.afterAll(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
});

test.describe("URS Parser", () => {
  test("should extract all REQ-IDs from a URS file", () => {
    const content = `
# URS
## Module 1
**REQ-DM-01: Document Input**
Some description.

## Module 2
**REQ-PDF-01: Generation**
**REQ-PDF-02: Extraction**
**REQ-PDF-03: Round-Trip**
`;
    const filePath = join(TEST_DIR, "test-urs-1.md");
    writeFileSync(filePath, content);

    const result = parseURS(filePath);
    expect(result).toEqual(["REQ-DM-01", "REQ-PDF-01", "REQ-PDF-02", "REQ-PDF-03"]);
  });

  test("should return empty array for file with no REQ-IDs", () => {
    const content = "# URS\nNo requirements here.\n";
    const filePath = join(TEST_DIR, "test-urs-empty.md");
    writeFileSync(filePath, content);

    const result = parseURS(filePath);
    expect(result).toEqual([]);
  });

  test("should deduplicate repeated REQ-IDs", () => {
    const content = `
**REQ-DM-01: First mention**
See REQ-DM-01 for details.
Also REQ-DM-01 is referenced here.
**REQ-PDF-01: Another**
`;
    const filePath = join(TEST_DIR, "test-urs-dedup.md");
    writeFileSync(filePath, content);

    const result = parseURS(filePath);
    expect(result).toEqual(["REQ-DM-01", "REQ-PDF-01"]);
  });

  test("should handle various REQ-ID formats (2-4 letter modules)", () => {
    const content = `
**REQ-DM-01**: two letters
**REQ-PDF-01**: three letters
**REQ-TRNG-01**: four letters
`;
    const filePath = join(TEST_DIR, "test-urs-formats.md");
    writeFileSync(filePath, content);

    const result = parseURS(filePath);
    expect(result).toEqual(["REQ-DM-01", "REQ-PDF-01", "REQ-TRNG-01"]);
  });

  test("should parse the actual Requirements/URS.md file", () => {
    const result = parseURS("Requirements/URS.md");
    // The actual URS.md contains these known REQ-IDs
    expect(result).toContain("REQ-DM-01");
    expect(result).toContain("REQ-PDF-01");
    expect(result).toContain("REQ-PDF-02");
    expect(result).toContain("REQ-PDF-03");
    expect(result).toContain("REQ-WF-01");
    expect(result).toContain("REQ-SIG-01");
    expect(result).toContain("REQ-TRN-01");
    expect(result).toContain("REQ-TRN-02");
    expect(result).toContain("REQ-AUD-01");
    expect(result).toContain("REQ-CSV-01");
    expect(result).toContain("REQ-CSV-02");
    expect(result.length).toBeGreaterThanOrEqual(11);
  });
});
