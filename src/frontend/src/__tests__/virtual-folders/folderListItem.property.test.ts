import * as fc from "fast-check";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import React from "react";
import { FolderListItem } from "../../components/virtual-folders/FolderListItem";
import type { VirtualFolderResponse } from "../../types/virtualFolder";

/**
 * Property 4: System default folder protection in rendering
 *
 * For any VirtualFolderResponse where is_system_default is true, the rendered
 * folder list item SHALL display a "System" badge AND SHALL NOT render edit or
 * delete action controls.
 *
 * **Validates: Requirements 4.8, 5.1, 5.2, 5.3**
 */

const validStatuses = ["Draft", "Active", "Approved", "InTraining", "Retired"] as const;
const validSortOrders = ["created_at_desc", "created_at_asc", "name_asc", "name_desc"] as const;

/**
 * Generator for a VirtualFolderResponse with configurable is_system_default.
 */
function virtualFolderArb(isSystemDefault: boolean): fc.Arbitrary<VirtualFolderResponse> {
  return fc.record({
    id: fc.integer({ min: 1, max: 10000 }),
    name: fc.string({ minLength: 1, maxLength: 100 }).filter((s) => s.trim().length > 0),
    tag_filter: fc.record({
      tags: fc.option(
        fc.array(fc.string({ minLength: 1, maxLength: 30 }), { minLength: 1, maxLength: 5 }),
        { nil: undefined }
      ),
      status: fc.option(fc.constantFrom(...validStatuses), { nil: undefined }),
    }),
    sort_order: fc.constantFrom(...validSortOrders),
    is_system_default: fc.constant(isSystemDefault),
    created_by: fc.integer({ min: 1, max: 1000 }),
    created_at: fc.option(
      fc.integer({ min: 1577836800000, max: 1767225600000 }).map((ts) => new Date(ts).toISOString()),
      { nil: null }
    ),
  });
}

describe("virtual-folders-frontend properties", () => {
  it("Feature: virtual-folders-frontend, Property 4: System default folder protection in rendering (system default shows badge, no edit/delete)", () => {
    const noop = () => {};

    fc.assert(
      fc.property(virtualFolderArb(true), (folder) => {
        const { container } = render(
          React.createElement(FolderListItem, {
            folder,
            onClick: noop,
            onEdit: noop,
            onDelete: noop,
          })
        );

        // Assert: "System" badge is rendered
        expect(container.textContent).toContain("System");

        // Assert: No edit button (aria-label containing "Edit") is rendered
        const editButton = container.querySelector('[aria-label*="Edit"]');
        expect(editButton).toBeNull();

        // Assert: No delete button (aria-label containing "Delete") is rendered
        const deleteButton = container.querySelector('[aria-label*="Delete"]');
        expect(deleteButton).toBeNull();
      }),
      { numRuns: 100 }
    );
  });

  it("Feature: virtual-folders-frontend, Property 4: System default folder protection in rendering (non-system-default shows edit/delete, no System badge)", () => {
    const noop = () => {};

    fc.assert(
      fc.property(virtualFolderArb(false), (folder) => {
        const { container } = render(
          React.createElement(FolderListItem, {
            folder,
            onClick: noop,
            onEdit: noop,
            onDelete: noop,
          })
        );

        // Assert: "System" badge is NOT rendered
        const spans = container.querySelectorAll("span");
        const systemBadge = Array.from(spans).find(
          (span) => span.textContent?.trim() === "System"
        );
        expect(systemBadge).toBeUndefined();

        // Assert: Edit button IS rendered
        const editButton = container.querySelector('[aria-label*="Edit"]');
        expect(editButton).not.toBeNull();

        // Assert: Delete button IS rendered
        const deleteButton = container.querySelector('[aria-label*="Delete"]');
        expect(deleteButton).not.toBeNull();
      }),
      { numRuns: 100 }
    );
  });
});
