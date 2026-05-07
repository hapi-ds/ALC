import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import { render } from "@testing-library/react";
import { DocumentList } from "@/components/documents/DocumentList";
import type { DocumentResponse, DocumentTag, DocumentVersion } from "@/types/document";

/**
 * Feature: document-upload-list, Property 1: Document list renders all required fields
 *
 * **Validates: Requirements 1.3**
 *
 * For any array of valid DocumentResponse objects, rendered output contains each document's
 * document_uuid, title, document_type, current_status, at least one tag, and created_at.
 */

// --- Arbitraries ---

const isoDateArb: fc.Arbitrary<string> = fc
  .integer({ min: 1577836800000, max: 1924905600000 })
  .map((ms) => new Date(ms).toISOString());

const documentTagArb: fc.Arbitrary<DocumentTag> = fc.record({
  id: fc.nat({ max: 100000 }),
  tag: fc.stringMatching(/^[a-zA-Z0-9][a-zA-Z0-9 _-]{0,28}[a-zA-Z0-9]$/).filter(
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

// Each document must have at least 1 tag per the property specification
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

// Generate arrays of 1-5 documents with unique document_uuids
const documentArrayArb: fc.Arbitrary<DocumentResponse[]> = fc
  .array(documentWithUniqueIdsArb, { minLength: 1, maxLength: 5 })
  .map((docs) =>
    docs.map((doc, i) => ({ ...doc, id: i + 1 }))
  );

describe("Feature: document-upload-list, Property 1: Document list renders all required fields", () => {
  it("renders document_uuid, title, document_type, current_status, at least one tag, and created_at for each document", () => {
    fc.assert(
      fc.property(documentArrayArb, (documents) => {
        const { container } = render(
          DocumentList({ documents, onDocumentClick: () => {} }) as any
        );

        const textContent = container.textContent || "";

        for (const doc of documents) {
          // document_uuid is rendered
          expect(textContent).toContain(doc.document_uuid);

          // title is rendered
          expect(textContent).toContain(doc.title);

          // document_type is rendered
          expect(textContent).toContain(doc.document_type);

          // current_status is rendered
          expect(textContent).toContain(doc.current_status);

          // At least one tag is rendered
          const hasAtLeastOneTag = doc.tags.some((tag) => textContent.includes(tag.tag));
          expect(hasAtLeastOneTag).toBe(true);

          // created_at is rendered (formatted via toLocaleDateString)
          const formattedDate = new Date(doc.created_at).toLocaleDateString();
          expect(textContent).toContain(formattedDate);
        }
      }),
      { numRuns: 100 }
    );
  });
});
