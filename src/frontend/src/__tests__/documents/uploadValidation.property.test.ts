import { describe, it, expect } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: document-upload-list, Property 5: Upload form field validation
 *
 * Validates: Requirements 4.3, 10.1, 10.2, 10.3
 *
 * For any title string: valid iff trimmed length 1–500.
 * For any folder_path: valid iff trimmed length 1–1000.
 * Submission blocked if file is null, title invalid, or folder_path invalid.
 */

// Pure validation functions matching UploadDialog.tsx logic

function validateTitle(title: string): string | undefined {
  const trimmed = title.trim();
  if (trimmed.length === 0) {
    return "Title is required.";
  } else if (trimmed.length > 500) {
    return "Title must not exceed 500 characters.";
  }
  return undefined;
}

function validateFolderPath(folderPath: string): string | undefined {
  const trimmed = folderPath.trim();
  if (trimmed.length === 0) {
    return "Folder path is required.";
  } else if (trimmed.length > 1000) {
    return "Folder path must not exceed 1000 characters.";
  }
  return undefined;
}

function validateFile(file: File | null): string | undefined {
  if (!file) {
    return "Please select a file to upload.";
  }
  return undefined;
}

interface FormState {
  file: File | null;
  title: string;
  folderPath: string;
  documentType: string;
}

function validate(state: FormState): Record<string, string> {
  const errors: Record<string, string> = {};

  const fileError = validateFile(state.file);
  if (fileError) errors.file = fileError;

  const titleError = validateTitle(state.title);
  if (titleError) errors.title = titleError;

  const folderPathError = validateFolderPath(state.folderPath);
  if (folderPathError) errors.folder_path = folderPathError;

  if (!state.documentType) {
    errors.document_type = "Document type is required.";
  }

  return errors;
}

function isSubmissionBlocked(state: FormState): boolean {
  return Object.keys(validate(state)).length > 0;
}

describe("Feature: document-upload-list, Property 5: Upload form field validation", () => {
  it("title is valid iff trimmed length is between 1 and 500 inclusive", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 600 }),
        (title) => {
          const trimmedLength = title.trim().length;
          const error = validateTitle(title);
          const isValid = error === undefined;

          if (trimmedLength >= 1 && trimmedLength <= 500) {
            expect(isValid).toBe(true);
          } else {
            expect(isValid).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("title with only whitespace is invalid (trimmed length is 0)", () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(" ", "\t", "\n", "\r"), { minLength: 0, maxLength: 20 }).map((arr) => arr.join("")),
        (whitespace) => {
          const error = validateTitle(whitespace);
          expect(error).toBe("Title is required.");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("title exceeding 500 trimmed characters produces max-length error", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 501, maxLength: 700 }).filter((s) => s.trim().length > 500),
        (title) => {
          const error = validateTitle(title);
          expect(error).toBe("Title must not exceed 500 characters.");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("folder_path is valid iff trimmed length is between 1 and 1000 inclusive", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 0, maxLength: 1100 }),
        (folderPath) => {
          const trimmedLength = folderPath.trim().length;
          const error = validateFolderPath(folderPath);
          const isValid = error === undefined;

          if (trimmedLength >= 1 && trimmedLength <= 1000) {
            expect(isValid).toBe(true);
          } else {
            expect(isValid).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("folder_path with only whitespace is invalid (trimmed length is 0)", () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(" ", "\t", "\n", "\r"), { minLength: 0, maxLength: 20 }).map((arr) => arr.join("")),
        (whitespace) => {
          const error = validateFolderPath(whitespace);
          expect(error).toBe("Folder path is required.");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("folder_path exceeding 1000 trimmed characters produces max-length error", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1001, maxLength: 1200 }).filter((s) => s.trim().length > 1000),
        (folderPath) => {
          const error = validateFolderPath(folderPath);
          expect(error).toBe("Folder path must not exceed 1000 characters.");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("submission is blocked when file is null", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 100 }),  // valid title
        fc.string({ minLength: 1, maxLength: 100 }),  // valid folder_path
        fc.constantFrom("SOP", "Protocol", "Report", "General"),
        (title, folderPath, documentType) => {
          const state: FormState = {
            file: null,
            title,
            folderPath,
            documentType,
          };
          expect(isSubmissionBlocked(state)).toBe(true);
          const errors = validate(state);
          expect(errors.file).toBe("Please select a file to upload.");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("submission is blocked when title is invalid", () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(""),                                          // empty
          fc.array(fc.constantFrom(" ", "\t"), { minLength: 1, maxLength: 10 }).map((arr) => arr.join("")), // whitespace only
          fc.string({ minLength: 501, maxLength: 600 }).filter((s) => s.trim().length > 500) // too long
        ),
        fc.string({ minLength: 1, maxLength: 100 }),  // valid folder_path
        fc.constantFrom("SOP", "Protocol", "Report", "General"),
        (title, folderPath, documentType) => {
          const mockFile = new File(["content"], "test.pdf", { type: "application/pdf" });
          const state: FormState = {
            file: mockFile,
            title,
            folderPath,
            documentType,
          };
          expect(isSubmissionBlocked(state)).toBe(true);
          const errors = validate(state);
          expect(errors.title).toBeDefined();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("submission is blocked when folder_path is invalid", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 100 }),  // valid title
        fc.oneof(
          fc.constant(""),                                            // empty
          fc.array(fc.constantFrom(" ", "\t"), { minLength: 1, maxLength: 10 }).map((arr) => arr.join("")), // whitespace only
          fc.string({ minLength: 1001, maxLength: 1200 }).filter((s) => s.trim().length > 1000) // too long
        ),
        fc.constantFrom("SOP", "Protocol", "Report", "General"),
        (title, folderPath, documentType) => {
          const mockFile = new File(["content"], "test.pdf", { type: "application/pdf" });
          const state: FormState = {
            file: mockFile,
            title,
            folderPath,
            documentType,
          };
          expect(isSubmissionBlocked(state)).toBe(true);
          const errors = validate(state);
          expect(errors.folder_path).toBeDefined();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("submission is allowed when file is present, title valid, and folder_path valid", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 500 }).filter((s) => s.trim().length >= 1 && s.trim().length <= 500),
        fc.string({ minLength: 1, maxLength: 1000 }).filter((s) => s.trim().length >= 1 && s.trim().length <= 1000),
        fc.constantFrom("SOP", "Protocol", "Report", "General"),
        (title, folderPath, documentType) => {
          const mockFile = new File(["content"], "test.pdf", { type: "application/pdf" });
          const state: FormState = {
            file: mockFile,
            title,
            folderPath,
            documentType,
          };
          expect(isSubmissionBlocked(state)).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});
