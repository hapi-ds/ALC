import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { CitationList } from "@/components/knowledge/CitationList";
import type { SourceCitation } from "@/stores/knowledgeStore";

/**
 * Unit tests for CitationList component.
 *
 * Validates: Requirements 4.1, 4.2, 4.3, 4.5, 4.6, 9.7
 */

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    Link: ({
      children,
      to,
      ...props
    }: {
      children: React.ReactNode;
      to: string;
      [key: string]: unknown;
    }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  };
});

function makeCitations(count: number): SourceCitation[] {
  return Array.from({ length: count }, (_, i) => ({
    document_uuid: `doc-uuid-${String(i + 1).padStart(3, "0")}`,
    title: `Document ${i + 1}`,
    version: `${i + 1}.0`,
    page_or_section: `Section ${i + 1}.1`,
  }));
}

function renderCitationList(
  citations: SourceCitation[],
  defaultExpanded?: boolean
) {
  return render(
    <MemoryRouter>
      <CitationList citations={citations} defaultExpanded={defaultExpanded} />
    </MemoryRouter>
  );
}

describe("CitationList", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders collapsed with source count (e.g., '3 sources')", () => {
    const citations = makeCitations(3);
    renderCitationList(citations);

    // Summary button shows count label
    expect(screen.getByText("3 sources")).not.toBeNull();

    // Citation list should NOT be visible when collapsed
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("renders '1 source' for a single citation", () => {
    const citations = makeCitations(1);
    renderCitationList(citations);

    expect(screen.getByText("1 source")).not.toBeNull();
  });

  it("expands on click to show citation details", async () => {
    const user = userEvent.setup();
    const citations = makeCitations(3);
    renderCitationList(citations);

    // Initially collapsed — no list visible
    expect(screen.queryByRole("list")).toBeNull();

    // Click the toggle button
    const toggleButton = screen.getByRole("button");
    await user.click(toggleButton);

    // Now the list should be visible
    const list = screen.getByRole("list");
    expect(list).not.toBeNull();

    // All 3 citation titles should be visible
    expect(screen.getByText("Document 1")).not.toBeNull();
    expect(screen.getByText("Document 2")).not.toBeNull();
    expect(screen.getByText("Document 3")).not.toBeNull();
  });

  it("renders title as link to /documents/{document_uuid}", async () => {
    const user = userEvent.setup();
    const citations: SourceCitation[] = [
      {
        document_uuid: "abc-123-def",
        title: "SOP Cleaning",
        version: "1.0",
        page_or_section: "Page 5",
      },
    ];
    renderCitationList(citations);

    // Expand the list
    await user.click(screen.getByRole("button"));

    // The title should be a link pointing to /documents/{document_uuid}
    const link = screen.getByRole("link", { name: /Open document: SOP Cleaning version 1\.0/ });
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe("/documents/abc-123-def");
  });

  it("renders version badge and page_or_section text", async () => {
    const user = userEvent.setup();
    const citations: SourceCitation[] = [
      {
        document_uuid: "doc-uuid-001",
        title: "Policy-X",
        version: "2.1",
        page_or_section: "Section 3.2",
      },
    ];
    renderCitationList(citations);

    // Expand the list
    await user.click(screen.getByRole("button"));

    // Version badge should show "v2.1"
    expect(screen.getByText("v2.1")).not.toBeNull();

    // Page/section text should be visible
    expect(screen.getByText("Section 3.2")).not.toBeNull();
  });

  it("limits display to 50 citations", async () => {
    const user = userEvent.setup();
    const citations = makeCitations(55);
    renderCitationList(citations);

    // Summary should show the full count
    expect(screen.getByText("55 sources")).not.toBeNull();

    // Expand the list
    await user.click(screen.getByRole("button"));

    // Only 50 items should be rendered in the list
    const listItems = screen.getAllByRole("listitem");
    expect(listItems.length).toBe(50);

    // Document 50 should be present
    expect(screen.getByText("Document 50")).not.toBeNull();

    // Document 51 should NOT be present
    expect(screen.queryByText("Document 51")).toBeNull();
  });

  it("link has correct aria-label 'Open document: {title} version {version}'", async () => {
    const user = userEvent.setup();
    const citations: SourceCitation[] = [
      {
        document_uuid: "doc-uuid-abc",
        title: "Training Manual",
        version: "3.2",
        page_or_section: "Chapter 1",
      },
      {
        document_uuid: "doc-uuid-xyz",
        title: "Safety Protocol",
        version: "1.0",
        page_or_section: "Page 12",
      },
    ];
    renderCitationList(citations);

    // Expand the list
    await user.click(screen.getByRole("button"));

    // Check aria-labels on links
    const link1 = screen.getByLabelText(
      "Open document: Training Manual version 3.2"
    );
    expect(link1).not.toBeNull();
    expect(link1.getAttribute("href")).toBe("/documents/doc-uuid-abc");

    const link2 = screen.getByLabelText(
      "Open document: Safety Protocol version 1.0"
    );
    expect(link2).not.toBeNull();
    expect(link2.getAttribute("href")).toBe("/documents/doc-uuid-xyz");
  });

  it("does not render anything when citations array is empty", () => {
    const { container } = renderCitationList([]);
    expect(container.innerHTML).toBe("");
  });

  it("collapses back on second click", async () => {
    const user = userEvent.setup();
    const citations = makeCitations(2);
    renderCitationList(citations);

    const toggleButton = screen.getByRole("button");

    // Expand
    await user.click(toggleButton);
    expect(screen.getByRole("list")).not.toBeNull();

    // Collapse
    await user.click(toggleButton);
    expect(screen.queryByRole("list")).toBeNull();
  });

  it("renders expanded by default when defaultExpanded is true", () => {
    const citations = makeCitations(2);
    renderCitationList(citations, true);

    // List should be visible immediately
    expect(screen.getByRole("list")).not.toBeNull();
    expect(screen.getByText("Document 1")).not.toBeNull();
    expect(screen.getByText("Document 2")).not.toBeNull();
  });
});
