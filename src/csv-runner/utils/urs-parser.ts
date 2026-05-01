/**
 * URS Parser - Extracts REQ-XX-NN identifiers from Requirements/URS.md.
 *
 * Reads the URS markdown file and uses regex to find all requirement
 * identifiers following the pattern REQ-{MODULE}-{NUMBER}.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Regex pattern matching URS requirement identifiers.
 * Format: REQ-{2-4 uppercase letters}-{2 digits}
 * Examples: REQ-DM-01, REQ-PDF-01, REQ-CSV-02
 */
const REQ_ID_PATTERN = /REQ-[A-Z]{2,4}-\d{2}/g;

/**
 * Parse a URS markdown file and extract all REQ-XX-NN identifiers.
 *
 * @param filePath - Absolute or relative path to the URS.md file.
 * @returns Array of unique REQ-ID strings found in the file, in order of first appearance.
 */
export function parseURS(filePath: string): string[] {
  const resolvedPath = resolve(filePath);
  const content = readFileSync(resolvedPath, "utf-8");
  const matches = content.match(REQ_ID_PATTERN);

  if (!matches) {
    return [];
  }

  // Deduplicate while preserving order of first appearance
  const seen = new Set<string>();
  const unique: string[] = [];

  for (const id of matches) {
    if (!seen.has(id)) {
      seen.add(id);
      unique.push(id);
    }
  }

  return unique;
}
