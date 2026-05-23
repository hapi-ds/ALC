import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChatMessage } from "@/components/knowledge/ChatMessage";
import type { ChatMessage as ChatMessageType } from "@/stores/knowledgeStore";

/**
 * Unit tests for ChatMessage component.
 *
 * Validates: Requirements 3.1, 3.2, 3.6, 3.7, 2.3
 */

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    Link: ({ children, to, ...props }: { children: React.ReactNode; to: string; [key: string]: unknown }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  };
});

function renderMessage(message: ChatMessageType, onCitationClick?: (uuid: string) => void) {
  return render(
    <MemoryRouter>
      <ChatMessage message={message} onCitationClick={onCitationClick} />
    </MemoryRouter>
  );
}

describe("ChatMessage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Fix "now" to a known time for timestamp testing
    vi.setSystemTime(new Date("2024-06-15T12:00:00Z"));
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("renders user message right-aligned with correct background class", () => {
    const message: ChatMessageType = {
      id: "msg-001",
      role: "user",
      content: "What is the SOP for cleaning?",
      citations: [],
      grounded: true,
      timestamp: "2024-06-15T11:59:30Z",
    };

    const { container } = renderMessage(message);

    // Outer wrapper should have justify-end for right alignment
    const outerDiv = container.firstElementChild as HTMLElement;
    expect(outerDiv.className).toContain("justify-end");

    // Bubble should have blue background class
    const bubble = outerDiv.firstElementChild as HTMLElement;
    expect(bubble.className).toContain("bg-blue-100");
  });

  it("renders assistant message left-aligned with correct background class", () => {
    const message: ChatMessageType = {
      id: "msg-002",
      role: "assistant",
      content: "The SOP for cleaning involves...",
      citations: [],
      grounded: true,
      timestamp: "2024-06-15T11:59:30Z",
    };

    const { container } = renderMessage(message);

    // Outer wrapper should have justify-start for left alignment
    const outerDiv = container.firstElementChild as HTMLElement;
    expect(outerDiv.className).toContain("justify-start");

    // Bubble should have gray background class
    const bubble = outerDiv.firstElementChild as HTMLElement;
    expect(bubble.className).toContain("bg-gray-100");
  });

  it("renders markdown content as HTML (headings, bold, lists, code blocks)", () => {
    const message: ChatMessageType = {
      id: "msg-003",
      role: "assistant",
      content: "# Heading\n\n**Bold text**\n\n- Item 1\n- Item 2\n\n```\ncode block\n```",
      citations: [],
      grounded: true,
      timestamp: "2024-06-15T11:59:30Z",
    };

    const { container } = renderMessage(message);

    // The component uses dangerouslySetInnerHTML, so we check for rendered HTML elements
    const markdownDiv = container.querySelector("[class*='prose-sm']") as HTMLElement;
    expect(markdownDiv).not.toBeNull();

    // Check heading is rendered as HTML
    const heading = markdownDiv.querySelector("h1");
    expect(heading).not.toBeNull();
    expect(heading!.textContent).toBe("Heading");

    // Check bold text
    const bold = markdownDiv.querySelector("strong");
    expect(bold).not.toBeNull();
    expect(bold!.textContent).toBe("Bold text");

    // Check list items
    const listItems = markdownDiv.querySelectorAll("li");
    expect(listItems.length).toBeGreaterThanOrEqual(2);

    // Check code block
    const codeBlock = markdownDiv.querySelector("pre code");
    expect(codeBlock).not.toBeNull();
    expect(codeBlock!.textContent).toBe("code block");
  });

  it("renders ungrounded message with muted styling and info icon", () => {
    const message: ChatMessageType = {
      id: "msg-004",
      role: "assistant",
      content: "I could not find relevant information.",
      citations: [],
      grounded: false,
      timestamp: "2024-06-15T11:59:30Z",
    };

    const { container } = renderMessage(message);

    // Bubble should have opacity-75 for muted styling
    const outerDiv = container.firstElementChild as HTMLElement;
    const bubble = outerDiv.firstElementChild as HTMLElement;
    expect(bubble.className).toContain("opacity-75");

    // Should show the info icon indicator text
    expect(screen.getByText("No relevant content found in knowledge base")).not.toBeNull();

    // Info icon should be present (rendered as SVG with aria-hidden)
    const infoIcon = bubble.querySelector('svg[aria-hidden="true"]');
    expect(infoIcon).not.toBeNull();
  });

  it("displays relative timestamp correctly", () => {
    // "just now" — 30 seconds ago
    const messageJustNow: ChatMessageType = {
      id: "msg-005a",
      role: "user",
      content: "Hello",
      citations: [],
      grounded: true,
      timestamp: "2024-06-15T11:59:30Z", // 30 seconds before "now"
    };

    const { container: c1 } = renderMessage(messageJustNow);
    const time1 = c1.querySelector("time");
    expect(time1!.textContent).toBe("just now");

    cleanup();

    // "N minutes ago" — 5 minutes ago
    const messageMinutes: ChatMessageType = {
      id: "msg-005b",
      role: "user",
      content: "Hello",
      citations: [],
      grounded: true,
      timestamp: "2024-06-15T11:55:00Z", // 5 minutes before "now"
    };

    const { container: c2 } = renderMessage(messageMinutes);
    const time2 = c2.querySelector("time");
    expect(time2!.textContent).toBe("5 minutes ago");

    cleanup();

    // "N hours ago" — 3 hours ago
    const messageHours: ChatMessageType = {
      id: "msg-005c",
      role: "user",
      content: "Hello",
      citations: [],
      grounded: true,
      timestamp: "2024-06-15T09:00:00Z", // 3 hours before "now"
    };

    const { container: c3 } = renderMessage(messageHours);
    const time3 = c3.querySelector("time");
    expect(time3!.textContent).toBe("3 hours ago");

    cleanup();

    // "HH:MM" — more than 24 hours ago
    const messageOld: ChatMessageType = {
      id: "msg-005d",
      role: "user",
      content: "Hello",
      citations: [],
      grounded: true,
      timestamp: "2024-06-13T14:30:00Z", // ~2 days ago, 14:30 UTC
    };

    const { container: c4 } = renderMessage(messageOld);
    const time4 = c4.querySelector("time");
    expect(time4!.textContent).toBe("14:30");
  });

  it("renders CitationList for assistant messages with citations", () => {
    const message: ChatMessageType = {
      id: "msg-006",
      role: "assistant",
      content: "According to the SOP...",
      citations: [
        {
          document_uuid: "doc-uuid-001",
          title: "SOP-001 Cleaning",
          version: "1.0",
          page_or_section: "Section 3.2",
        },
        {
          document_uuid: "doc-uuid-002",
          title: "Policy-X",
          version: "2.1",
          page_or_section: "Page 5",
        },
      ],
      grounded: true,
      timestamp: "2024-06-15T11:59:30Z",
    };

    renderMessage(message);

    // CitationList renders a summary label with count
    expect(screen.getByText("2 sources")).not.toBeNull();
  });

  it("does not render CitationList for ungrounded messages", () => {
    const message: ChatMessageType = {
      id: "msg-007",
      role: "assistant",
      content: "I could not find relevant information.",
      citations: [],
      grounded: false,
      timestamp: "2024-06-15T11:59:30Z",
    };

    renderMessage(message);

    // Should not show any sources label
    expect(screen.queryByText(/sources?/)).toBeNull();
  });
});
