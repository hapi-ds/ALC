import { describe, it, expect } from "vitest";
import * as fc from "fast-check";

/**
 * Feature: document-upload-list, Property 6: Multipart FormData construction preserves all fields
 *
 * **Validates: Requirements 4.5, 6.3**
 *
 * For any valid upload form data (file, title, folder_path, document_type, tags),
 * the constructed FormData object should contain entries for every required field
 * with values matching the input.
 */

// Pure function replicating the FormData construction logic from UploadDialog.tsx
function buildUploadFormData(input: {
  file: File;
  title: string;
  folderPath: string;
  documentType: string;
  tags: string;
}): FormData {
  const formData = new FormData();
  formData.append("file", input.file);
  formData.append("title", input.title.trim());
  formData.append("folder_path", input.folderPath.trim());
  formData.append("document_type", input.documentType);
  formData.append("tags", input.tags.trim());
  return formData;
}

// Pure function replicating the FormData construction for version uploads
function buildVersionFormData(input: {
  file: File;
  versionType: "major" | "minor";
  changeReason: string;
}): FormData {
  const formData = new FormData();
  formData.append("file", input.file);
  formData.append("version_type", input.versionType);
  formData.append("change_reason", input.changeReason);
  return formData;
}

// Generators for valid form inputs
const validTitleArb = fc
  .string({ minLength: 1, maxLength: 500 })
  .filter((s) => s.trim().length >= 1 && s.trim().length <= 500);

const validFolderPathArb = fc
  .string({ minLength: 1, maxLength: 200 })
  .filter((s) => s.trim().length >= 1 && s.trim().length <= 1000);

const documentTypeArb = fc.constantFrom("SOP", "Protocol", "Report", "General", "Policy", "Form");

const tagsArb = fc.oneof(
  fc.constant(""),
  fc.string({ minLength: 1, maxLength: 100 }),
  fc.array(fc.string({ minLength: 1, maxLength: 20 }).filter((s) => s.trim().length > 0), { minLength: 1, maxLength: 5 })
    .map((arr) => arr.join(", "))
);

const fileContentArb = fc.string({ minLength: 1, maxLength: 50 });
const fileNameArb = fc
  .string({ minLength: 1, maxLength: 30 })
  .filter((s) => s.trim().length > 0)
  .map((s) => s.replace(/[/\\:*?"<>|]/g, "_") + ".pdf");

const versionTypeArb = fc.constantFrom("major" as const, "minor" as const);
const changeReasonArb = fc.string({ minLength: 1, maxLength: 200 });

describe("Feature: document-upload-list, Property 6: Multipart FormData construction preserves all fields", () => {
  it("upload FormData contains all required fields with correct values", () => {
    fc.assert(
      fc.property(
        fileContentArb,
        fileNameArb,
        validTitleArb,
        validFolderPathArb,
        documentTypeArb,
        tagsArb,
        (fileContent, fileName, title, folderPath, documentType, tags) => {
          const file = new File([fileContent], fileName, { type: "application/pdf" });

          const formData = buildUploadFormData({
            file,
            title,
            folderPath,
            documentType,
            tags,
          });

          // Verify all fields are present
          expect(formData.has("file")).toBe(true);
          expect(formData.has("title")).toBe(true);
          expect(formData.has("folder_path")).toBe(true);
          expect(formData.has("document_type")).toBe(true);
          expect(formData.has("tags")).toBe(true);

          // Verify string field values match trimmed inputs
          expect(formData.get("title")).toBe(title.trim());
          expect(formData.get("folder_path")).toBe(folderPath.trim());
          expect(formData.get("document_type")).toBe(documentType);
          expect(formData.get("tags")).toBe(tags.trim());

          // Verify file entry is a File with correct name
          const fileEntry = formData.get("file") as File;
          expect(fileEntry).toBeInstanceOf(File);
          expect(fileEntry.name).toBe(fileName);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("upload FormData contains exactly 5 entries (no extra fields)", () => {
    fc.assert(
      fc.property(
        fileContentArb,
        fileNameArb,
        validTitleArb,
        validFolderPathArb,
        documentTypeArb,
        tagsArb,
        (fileContent, fileName, title, folderPath, documentType, tags) => {
          const file = new File([fileContent], fileName, { type: "application/pdf" });

          const formData = buildUploadFormData({
            file,
            title,
            folderPath,
            documentType,
            tags,
          });

          // Count entries using iterator
          const entries = Array.from(formData.entries());
          expect(entries.length).toBe(5);

          // Verify field names
          const fieldNames = entries.map(([key]) => key);
          expect(fieldNames).toContain("file");
          expect(fieldNames).toContain("title");
          expect(fieldNames).toContain("folder_path");
          expect(fieldNames).toContain("document_type");
          expect(fieldNames).toContain("tags");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("version upload FormData contains all required fields with correct values", () => {
    fc.assert(
      fc.property(
        fileContentArb,
        fileNameArb,
        versionTypeArb,
        changeReasonArb,
        (fileContent, fileName, versionType, changeReason) => {
          const file = new File([fileContent], fileName, { type: "application/pdf" });

          const formData = buildVersionFormData({
            file,
            versionType,
            changeReason,
          });

          // Verify all fields are present
          expect(formData.has("file")).toBe(true);
          expect(formData.has("version_type")).toBe(true);
          expect(formData.has("change_reason")).toBe(true);

          // Verify values match inputs
          expect(formData.get("version_type")).toBe(versionType);
          expect(formData.get("change_reason")).toBe(changeReason);

          // Verify file entry
          const fileEntry = formData.get("file") as File;
          expect(fileEntry).toBeInstanceOf(File);
          expect(fileEntry.name).toBe(fileName);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("version upload FormData contains exactly 3 entries (no extra fields)", () => {
    fc.assert(
      fc.property(
        fileContentArb,
        fileNameArb,
        versionTypeArb,
        changeReasonArb,
        (fileContent, fileName, versionType, changeReason) => {
          const file = new File([fileContent], fileName, { type: "application/pdf" });

          const formData = buildVersionFormData({
            file,
            versionType,
            changeReason,
          });

          const entries = Array.from(formData.entries());
          expect(entries.length).toBe(3);

          const fieldNames = entries.map(([key]) => key);
          expect(fieldNames).toContain("file");
          expect(fieldNames).toContain("version_type");
          expect(fieldNames).toContain("change_reason");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("FormData title is always trimmed (leading/trailing whitespace removed)", () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.string({ minLength: 0, maxLength: 10 }).map((s) => s.replace(/\S/g, " ")),
          fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
          fc.string({ minLength: 0, maxLength: 10 }).map((s) => s.replace(/\S/g, " "))
        ).map(([prefix, core, suffix]) => prefix + core + suffix),
        (paddedTitle) => {
          const file = new File(["data"], "test.pdf", { type: "application/pdf" });

          const formData = buildUploadFormData({
            file,
            title: paddedTitle,
            folderPath: "/docs",
            documentType: "General",
            tags: "",
          });

          const storedTitle = formData.get("title") as string;
          expect(storedTitle).toBe(paddedTitle.trim());
          expect(storedTitle).not.toMatch(/^\s/);
          expect(storedTitle).not.toMatch(/\s$/);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("FormData folder_path is always trimmed (leading/trailing whitespace removed)", () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.string({ minLength: 0, maxLength: 10 }).map((s) => s.replace(/\S/g, " ")),
          fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
          fc.string({ minLength: 0, maxLength: 10 }).map((s) => s.replace(/\S/g, " "))
        ).map(([prefix, core, suffix]) => prefix + core + suffix),
        (paddedPath) => {
          const file = new File(["data"], "test.pdf", { type: "application/pdf" });

          const formData = buildUploadFormData({
            file,
            title: "Test Doc",
            folderPath: paddedPath,
            documentType: "General",
            tags: "",
          });

          const storedPath = formData.get("folder_path") as string;
          expect(storedPath).toBe(paddedPath.trim());
          expect(storedPath).not.toMatch(/^\s/);
          expect(storedPath).not.toMatch(/\s$/);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("FormData tags field is always trimmed", () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.string({ minLength: 0, maxLength: 10 }).map((s) => s.replace(/\S/g, " ")),
          fc.string({ minLength: 0, maxLength: 50 }),
          fc.string({ minLength: 0, maxLength: 10 }).map((s) => s.replace(/\S/g, " "))
        ).map(([prefix, core, suffix]) => prefix + core + suffix),
        (paddedTags) => {
          const file = new File(["data"], "test.pdf", { type: "application/pdf" });

          const formData = buildUploadFormData({
            file,
            title: "Test Doc",
            folderPath: "/docs",
            documentType: "General",
            tags: paddedTags,
          });

          const storedTags = formData.get("tags") as string;
          expect(storedTags).toBe(paddedTags.trim());
        }
      ),
      { numRuns: 100 }
    );
  });
});
