import { describe, it, expect, vi, beforeEach } from "vitest";
import * as fc from "fast-check";
import { render } from "@testing-library/react";
import { DocumentDetail } from "@/components/documents/DocumentDetail";
import type { DocumentResponse, DocumentTag, DocumentVersion } from "@/types/document";

// Mock the document store to avoid hook errors in property tests
vi.mock("@/stores/documentStore", () => ({
  useDocumentStore: (selector: (state: any) => any) => {
    const mockState = {
      selectedVersion: null,
      isVersionLoading: false,
      versionError: null,
      comparisonOpen: false,
      downloadingVersionId: null,
      fetchVersion: () => Promise.resolve(),
      downloadVersion: () => Promise.resolve(),
      setComparisonOpen: () => {},
      clearSelectedVersion: () => {},
    };
    return selector(mockState);
  },
}));

/**
 * Feature: document-upload-list, Property 7: Document detail renders all metadata, tags, and versions
 *
 * **Validates: Requirements 5.2, 5.3, 5.4**
 *
 * For any valid DocumentResponse with N tags and M versions, the rendered detail view
 * should display the document's title, document_uuid, folder_path, document_type,
 * current_status, created_by, and created_at, plus exactly N tag badges with correct text,
 * plus version history panel with version entries.
 */

// --- Arbitraries ---

// Generate ISO date strings directly to avoid Invalid Date issues during shrinking
const isoDateArb: fc.Arbitrary<string> = fc
  .integer({ min: 1577836800000, max: 1924905600000 }) // 2020-01-01 to 2030-12-31 in ms
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
    fc.stringMatching(/^[a-zA-Z0-9][a-zA-Z0-9 .,!?-]{0,98}[a-zA-Z0-9]$/).filter(
      (s) => s.length >= 2
    )
  ),
});

const documentResponseArb: fc.Arbitrary<DocumentResponse> = fc.record({
  id: fc.nat({ max: 100000 }),
  document_uuid: fc.uuid(),
  title: fc.stringMatching(/^[a-zA-Z][a-zA-Z0-9 _-]{0,98}[a-zA-Z0-9]$/).filter(
    (s) => s.length >= 2
  ),
  folder_path: fc.stringMatching(/^\/[a-zA-Z0-9][a-zA-Z0-9/_-]{0,98}$/).filter(
    (s) => s.length >= 2
  ),
  document_type: fc.constantFrom("SOP", "Protocol", "Report", "General", "Policy", "Form"),
  current_status: fc.constantFrom("Draft", "In Review", "Approved", "Archived"),
  created_by: fc.nat({ max: 100000 }),
  created_at: isoDateArb,
  tags: fc.array(documentTagArb, { minLength: 0, maxLength: 5 }),
  versions: fc.array(documentVersionArb, { minLength: 0, maxLength: 5 }),
});

// Helper to ensure unique tag/version IDs
const documentResponseWithUniqueIdsArb: fc.Arbitrary<DocumentResponse> = documentResponseArb.map(
  (doc) => ({
    ...doc,
    tags: doc.tags.map((tag, i) => ({ ...tag, id: i + 1 })),
    versions: doc.versions.map((v, i) => ({ ...v, id: i + 1 })),
  })
);

describe("Feature: document-upload-list, Property 7: Document detail renders all metadata, tags, and versions", () => {
  it("renders all metadata fields for any valid DocumentResponse", () => {
    fc.assert(
      fc.property(documentResponseWithUniqueIdsArb, (doc) => {
        const { container } = render(
          DocumentDetail({ document: doc, onNewVersion: () => {}, onBack: () => {} }) as any
        );

        const textContent = container.textContent || "";

        // Title rendered as h2
        expect(container.querySelector("h2")?.textContent).toBe(doc.title);

        // Metadata fields present in text content
        expect(textContent).toContain(doc.document_uuid);
        expect(textContent).toContain(doc.folder_path);
        expect(textContent).toContain(doc.document_type);
        expect(textContent).toContain(doc.current_status);
        expect(textContent).toContain(String(doc.created_by));
        // created_at is rendered via toLocaleString()
        expect(textContent).toContain(new Date(doc.created_at).toLocaleString());
      }),
      { numRuns: 100 }
    );
  });

  it("renders exactly N tag badges for a document with N tags", () => {
    fc.assert(
      fc.property(documentResponseWithUniqueIdsArb, (doc) => {
        const { container } = render(
          DocumentDetail({ document: doc, onNewVersion: () => {}, onBack: () => {} }) as any
        );

        const tagList = container.querySelector('[aria-label="Document tags"]');

        if (doc.tags.length === 0) {
          // Tags section not rendered when no tags
          expect(tagList).toBeNull();
        } else {
          // Tag list should exist
          expect(tagList).not.toBeNull();

          // Count tag badges (listitems within the tag list)
          const tagBadges = tagList!.querySelectorAll('[role="listitem"]');
          expect(tagBadges.length).toBe(doc.tags.length);

          // Each tag text is present
          doc.tags.forEach((tag, index) => {
            expect(tagBadges[index].textContent).toBe(tag.tag);
          });
        }
      }),
      { numRuns: 100 }
    );
  });

  it("renders version history panel with version entries", () => {
    fc.assert(
      fc.property(documentResponseWithUniqueIdsArb, (doc) => {
        const { container } = render(
          DocumentDetail({ document: doc, onNewVersion: () => {}, onBack: () => {} }) as any
        );

        const textContent = container.textContent || "";

        if (doc.versions.length === 0) {
          // Empty state message shown by VersionHistoryPanel
          expect(textContent).toContain("No versions available");
        } else {
          // Version History heading is present
          expect(textContent).toContain("Version History");

          // Each version number is rendered
          doc.versions.forEach((version) => {
            const versionString = `v${version.major_version}.${version.minor_version}`;
            expect(textContent).toContain(versionString);
          });
        }
      }),
      { numRuns: 100 }
    );
  });
});
