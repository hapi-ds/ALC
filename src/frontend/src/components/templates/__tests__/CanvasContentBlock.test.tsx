import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { DragDropContext, Droppable } from "@hello-pangea/dnd";
import { CanvasContentBlock } from "../CanvasContentBlock";
import { ContentBlockConfigPanel } from "../ContentBlockConfigPanel";
import { useTemplateBuilderStore } from "../../../stores/templateBuilderStore";
import type { CanvasContentBlockElement } from "../../../types/template";

/**
 * Unit tests for CanvasContentBlock and ContentBlockConfigPanel components.
 *
 * Validates: Requirements 7.6, 8.6, 9.3, 9.4
 */

function renderInDndContext(ui: React.ReactElement) {
  return render(
    <DragDropContext onDragEnd={() => {}}>
      <Droppable droppableId="test-droppable">
        {(provided) => (
          <div ref={provided.innerRef} {...provided.droppableProps}>
            {ui}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </DragDropContext>
  );
}

function resetStore() {
  useTemplateBuilderStore.setState({
    items: [],
    fields: [],
    selectedFieldId: null,
    fieldErrors: {},
    templateName: "",
    isSaving: false,
    saveError: null,
    saveSuccess: false,
    savedTemplate: null,
    isDirty: false,
    nameError: null,
  });
}

// ---------------------------------------------------------------------------
// CanvasContentBlock Tests
// ---------------------------------------------------------------------------

describe("CanvasContentBlock", () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders heading_h1 with text-xl font-bold styling", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-1",
      element_type: "content_block",
      content_type: "heading_h1",
      text: "Main Section",
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={false}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    const heading = screen.getByText("Main Section");
    expect(heading.className).toContain("text-xl");
    expect(heading.className).toContain("font-bold");
  });

  it("renders heading_h2 with text-lg font-semibold styling", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-2",
      element_type: "content_block",
      content_type: "heading_h2",
      text: "Sub Section",
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={false}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    const heading = screen.getByText("Sub Section");
    expect(heading.className).toContain("text-lg");
    expect(heading.className).toContain("font-semibold");
  });

  it("renders heading_h3 with text-base font-semibold styling", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-3",
      element_type: "content_block",
      content_type: "heading_h3",
      text: "Minor Section",
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={false}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    const heading = screen.getByText("Minor Section");
    expect(heading.className).toContain("text-base");
    expect(heading.className).toContain("font-semibold");
  });

  it("renders paragraph with text content", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-4",
      element_type: "content_block",
      content_type: "paragraph",
      text: "Instructions for data entry",
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={false}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    expect(screen.getByText("Instructions for data entry")).toBeDefined();
  });

  it("renders divider as an hr element", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-5",
      element_type: "content_block",
      content_type: "divider",
      text: null,
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={false}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    const hr = document.querySelector("hr");
    expect(hr).not.toBeNull();
  });

  it("renders default text when heading text is null", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-6",
      element_type: "content_block",
      content_type: "heading_h1",
      text: null,
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={false}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    expect(screen.getByText("Section Title")).toBeDefined();
  });

  it("applies selection highlight when isSelected is true", () => {
    const item: CanvasContentBlockElement = {
      id: "cb-7",
      element_type: "content_block",
      content_type: "heading_h1",
      text: "Selected Block",
      fieldOrder: 0,
    };

    renderInDndContext(
      <CanvasContentBlock
        item={item}
        index={0}
        isSelected={true}
        onSelect={() => {}}
        onDelete={() => {}}
      />
    );

    const listItem = screen.getByRole("listitem");
    expect(listItem.className).toContain("border-blue-500");
    expect(listItem.className).toContain("bg-blue-50");
  });
});

// ---------------------------------------------------------------------------
// ContentBlockConfigPanel Tests
// ---------------------------------------------------------------------------

describe("ContentBlockConfigPanel", () => {
  beforeEach(() => {
    resetStore();
  });

  afterEach(() => {
    cleanup();
  });

  it("shows text input for heading content blocks", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-h1",
          element_type: "content_block",
          content_type: "heading_h1",
          text: "My Header",
          fieldOrder: 0,
        },
      ],
    });

    render(<ContentBlockConfigPanel blockId="cb-h1" />);

    expect(screen.getByText("Header Properties")).toBeDefined();
    const input = screen.getByLabelText("Header Text") as HTMLInputElement;
    expect(input).toBeDefined();
    expect(input.value).toBe("My Header");
    expect(input.maxLength).toBe(200);
  });

  it("shows heading level dropdown for heading content blocks", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-h2",
          element_type: "content_block",
          content_type: "heading_h2",
          text: "Sub Header",
          fieldOrder: 0,
        },
      ],
    });

    render(<ContentBlockConfigPanel blockId="cb-h2" />);

    const select = screen.getByLabelText("Heading Level") as HTMLSelectElement;
    expect(select).toBeDefined();
    expect(select.value).toBe("heading_h2");

    const options = select.querySelectorAll("option");
    expect(options).toHaveLength(3);
    expect(options[0].value).toBe("heading_h1");
    expect(options[1].value).toBe("heading_h2");
    expect(options[2].value).toBe("heading_h3");
  });

  it("shows textarea for paragraph content blocks", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-para",
          element_type: "content_block",
          content_type: "paragraph",
          text: "Some instructions",
          fieldOrder: 0,
        },
      ],
    });

    render(<ContentBlockConfigPanel blockId="cb-para" />);

    expect(screen.getByText("Paragraph Properties")).toBeDefined();
    const textarea = screen.getByLabelText("Paragraph Text") as HTMLTextAreaElement;
    expect(textarea).toBeDefined();
    expect(textarea.value).toBe("Some instructions");
    expect(textarea.maxLength).toBe(2000);
  });

  it("shows 'No configurable properties' for divider content blocks", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-div",
          element_type: "content_block",
          content_type: "divider",
          text: null,
          fieldOrder: 0,
        },
      ],
    });

    render(<ContentBlockConfigPanel blockId="cb-div" />);

    expect(screen.getByText("No configurable properties")).toBeDefined();
  });

  it("displays character count for heading text", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-h1",
          element_type: "content_block",
          content_type: "heading_h1",
          text: "Hello",
          fieldOrder: 0,
        },
      ],
    });

    render(<ContentBlockConfigPanel blockId="cb-h1" />);

    expect(screen.getByText("5/200 characters")).toBeDefined();
  });

  it("displays character count for paragraph text", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-para",
          element_type: "content_block",
          content_type: "paragraph",
          text: "Short text",
          fieldOrder: 0,
        },
      ],
    });

    render(<ContentBlockConfigPanel blockId="cb-para" />);

    expect(screen.getByText("10/2000 characters")).toBeDefined();
  });

  it("displays validation error when present in fieldErrors", () => {
    useTemplateBuilderStore.setState({
      items: [
        {
          id: "cb-h1",
          element_type: "content_block",
          content_type: "heading_h1",
          text: "",
          fieldOrder: 0,
        },
      ],
      fieldErrors: { "cb-h1": "Header text is required" },
    });

    render(<ContentBlockConfigPanel blockId="cb-h1" />);

    const error = screen.getByRole("alert");
    expect(error.textContent).toBe("Header text is required");
  });

  it("returns null when block is not found", () => {
    useTemplateBuilderStore.setState({
      items: [],
    });

    const { container } = render(<ContentBlockConfigPanel blockId="nonexistent" />);
    expect(container.innerHTML).toBe("");
  });
});
