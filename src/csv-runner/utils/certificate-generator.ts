/**
 * Validation Certificate PDF Generator.
 *
 * Generates a formal PDF validation certificate containing:
 * - Test results summary (pass/fail per REQ-ID)
 * - Timestamps (start, end, duration)
 * - Module versions
 * - Traceability matrix
 * - URS version hash (SHA-256)
 *
 * The certificate is signed via the Signature_Service API and stored
 * in the Document_Service as a "Validation Report".
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { TraceabilityMatrix } from "./traceability-matrix";

/**
 * Individual test result for a single requirement.
 */
export interface TestResult {
  /** The URS requirement identifier */
  reqId: string;
  /** Whether the test passed */
  passed: boolean;
  /** Duration in milliseconds */
  durationMs: number;
  /** Error message if failed */
  errorMessage?: string;
}

/**
 * Complete validation run results.
 */
export interface ValidationRunResults {
  /** Individual test results */
  testResults: TestResult[];
  /** ISO timestamp when the run started */
  startedAt: string;
  /** ISO timestamp when the run completed */
  completedAt: string;
  /** Total duration in milliseconds */
  totalDurationMs: number;
  /** Whether all tests passed (100% pass rate) */
  allPassed: boolean;
}

/**
 * Module version information included in the certificate.
 */
export interface ModuleVersions {
  /** AlcoaBase backend version */
  backendVersion: string;
  /** AlcoaBase frontend version */
  frontendVersion: string;
  /** CSV Runner version */
  csvRunnerVersion: string;
  /** Playwright version */
  playwrightVersion: string;
}

/**
 * The generated certificate data (to be rendered as PDF via backend API).
 */
export interface ValidationCertificate {
  /** Certificate title */
  title: string;
  /** ISO timestamp of certificate generation */
  generatedAt: string;
  /** SHA-256 hash of the URS.md file */
  ursVersionHash: string;
  /** Test results summary */
  results: ValidationRunResults;
  /** Traceability matrix */
  traceabilityMatrix: TraceabilityMatrix;
  /** Module versions */
  moduleVersions: ModuleVersions;
  /** Overall pass/fail status */
  status: "PASSED" | "FAILED";
  /** Number of passed tests */
  passedCount: number;
  /** Number of failed tests */
  failedCount: number;
  /** Total number of tests */
  totalTests: number;
}

/**
 * Compute the SHA-256 hash of the URS.md file for version tracking.
 *
 * @param ursFilePath - Path to the URS.md file.
 * @returns Hex-encoded SHA-256 hash string.
 */
export function computeURSHash(ursFilePath: string): string {
  const content = readFileSync(resolve(ursFilePath), "utf-8");
  return createHash("sha256").update(content, "utf-8").digest("hex");
}

/**
 * Generate a validation certificate from test results.
 *
 * @param results - The validation run results.
 * @param traceabilityMatrix - The requirement-to-test traceability matrix.
 * @param moduleVersions - Version information for all system modules.
 * @param ursFilePath - Path to the URS.md file for hash computation.
 * @returns The complete validation certificate data.
 */
export function generateCertificate(
  results: ValidationRunResults,
  traceabilityMatrix: TraceabilityMatrix,
  moduleVersions: ModuleVersions,
  ursFilePath: string
): ValidationCertificate {
  const passedCount = results.testResults.filter((r) => r.passed).length;
  const failedCount = results.testResults.filter((r) => !r.passed).length;
  const totalTests = results.testResults.length;

  return {
    title: "AlcoaBase Computer System Validation Certificate",
    generatedAt: new Date().toISOString(),
    ursVersionHash: computeURSHash(ursFilePath),
    results,
    traceabilityMatrix,
    moduleVersions,
    status: results.allPassed ? "PASSED" : "FAILED",
    passedCount,
    failedCount,
    totalTests,
  };
}

/**
 * Submit the certificate to the backend API for PDF generation, signing,
 * and storage as a "Validation Report" document.
 *
 * @param certificate - The validation certificate data.
 * @param baseUrl - The backend API base URL.
 * @returns The Document-UUID of the stored validation report.
 */
export async function submitCertificate(
  certificate: ValidationCertificate,
  baseUrl: string
): Promise<string> {
  const response = await fetch(`${baseUrl}/api/validation/certificate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSV-Test-User": "csv_validation_runner",
    },
    body: JSON.stringify(certificate),
  });

  if (!response.ok) {
    throw new Error(
      `Failed to submit certificate: ${response.status} ${response.statusText}`
    );
  }

  const data = (await response.json()) as { document_uuid: string };
  return data.document_uuid;
}
