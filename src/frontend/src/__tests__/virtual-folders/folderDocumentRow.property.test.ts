import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { render } from "@testing-library/react";
import { FolderDocumentRow } from "@/components/virtual-folders/FolderDocumentRow";
import type { DocumentResponse, DocumentTag, DocumentVersion } from "@/types/document";

/**
 * Property 5: Document row renders all required fields
 *
 * For any valid DocumentResponse object, the rendered document row in the
 * Folder_Document_View SHALL display the document's title, document_type,
 * current_status, tag names, and created_at timestamp.
 *
 * **Validates: Requirements 6.3**
 */

// --- Arbitraries ---

const isoDateArb: fc.Arbitrary<string> = fc
  .integer({ min: 1577836800000, max: 1924905600000 })
  .map((ms) => new Date(ms).toISOString());

const documentTagArb: fc.Arbitrary<DocumentTag> = fc.record({
  id: fc.nat({ max: 100000 }),
  tag: fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9 _-]{0,28}[a-zA-Z0-9]$/).filter(
    (s) => s.length >= 2
  ),
});

const documentVersionArb: fc.Arbitrary<DocumentVersion> = fc.record({
  id: fc.nat({ max: 100000 }),
  major_version: fc.nat({ max: 99 }),
  minor_version: fc.nat({ max: 99 }),
  storage_key: fc.string({ minLength: 1, maxLength: 50 }),
  file_hash: fc.stringMatching(/^[a-f0-9]{16,64}$/),
  uploaded_by: fc.nat({ max: 100000 }),
  uploaded_at: isoDateArb,
  change_reason: fc.oneof(
    fc.constant(null),
    fc.stringMatching(/^[a-zA-Z0-9][a-zA-Z0-9 .,!?-]{0,48}[a-zA-Z0-9]$/).filter(
      (s) => s.length >= 2
    )
  ),
});

const documentResponseArb: fc.Arbitrary<DocumentResponse> = fc.record({
  id: fc.nat({ max: 100000 }),
  document_uuid: fc.uuid(),
  title: fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9 _-]{0,48}[a-zA-Z0-9]$/).filter(
    (s) => s.length >= 2
  ),
  folder_path: fc.stringMatching(/^\/[a-zA-Z0-9][a-zA-Z0-9/_-]{0,48}$/).filter(
    (s) => s.length >= 2
  ),
  document_type: fc.constantFrom("SOP", "Protocol", "Report", "General", "Policy", "Form"),
  current_status: fc.constantFrom("Draft", "In Review", "Approved", "Archived"),
  created_by: fc.nat({ max: 100000 }),
  created_at: isoDateArb,
  tags: fc.array(documentTagArb, { minLength: 1, maxLength: 5 }),
  versions: fc.array(documentVersionArb, { minLength: 0, maxLength: 3 }),
});

// Ensure unique IDs for tags and versions within each document
const documentWithUniqueIdsArb: fc.Arbitrary<DocumentResponse> = documentResponseArb.map(
  (doc) => ({
    ...doc,
    tags: doc.tags.map((tag, i) => ({ ...tag, id: i + 1 })),
    versions: doc.versions.map((v, i) => ({ ...v, id: i + 1 })),
  })
);

describe("Feature: virtual-folders-frontend, Property 5: Document row renders all required fields", () => {
  it("renders title, document_type, current_status, tag names, and created_at for any DocumentResponse", () => {
    fc.assert(
      fc.property(documentWithUniqueIdsArb, (document) => {
        const { container } = render(
          FolderDocumentRow({ document }) as any
        );

        const textContent = container.textContent || "";

        // title is rendered
        expect(textContent).toContain(document.title);

        // document_type is rendered
        expect(textContent).toContain(document.document_type);

        // current_status is rendered
        expect(textContent).toContain(document.current_status);

        // tag names are rendered (joined with ", ")
        const tagNames = document.tags.map((t) => t.tag).join(", ");
        expect(textContent).toContain(tagNames);

        // created_at is rendered as formatted date
        const formattedDate = new Date(document.created_at).toLocaleDateString();
        expect(textContent).toContain(formattedDate);
      }),
      { numRuns: 100 }
    );
  });
});
