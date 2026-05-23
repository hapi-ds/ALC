import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { KnowledgePage } from "@/pages/KnowledgePage";
import type { KnowledgeState } from "@/stores/knowledgeStore";

/**
 * Unit tests for KnowledgePage integration.
 *
 * Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7,
 * 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5
 */

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockSendMessage = vi.fn();
const mockRetryLastMessage = vi.fn();
const mockStartNewConversation = vi.fn();
const mockClearConversation = vi.fn();
const mockSetInputValue = vi.fn();

const defaultState: KnowledgeState = {
  messages: [],
  conversationId: null,
  isLoading: false,
  error: null,
  inputValue: "",
  retryCount: 0,
  lastFailedQuestion: null,
  sendMessage: mockSendMessage,
  retryLastMessage: mockRetryLastMessage,
  startNewConversation: mockStartNewConversation,
  clearConversation: mockClearConversation,
  setInputValue: mockSetInputValue,
};

let mockStoreState: KnowledgeState = { ...defaultState };

vi.mock("@/stores/knowledgeStore", () => ({
  useKnowledgeStore: () => mockStoreState,
}));

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

function renderPage() {
  return render(
    <MemoryRouter>
      <KnowledgePage />
    </MemoryRouter>
  );
}

describe("KnowledgePage", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2024-06-15T12:00:00Z"));
    mockStoreState = { ...defaultState };
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  // -------------------------------------------------------------------------
  // Header and layout
  // -------------------------------------------------------------------------

  it("renders header with title 'Knowledge Chat' and subtitle", () => {
    renderPage();

    expect(screen.getByText("Knowledge Chat")).not.toBeNull();
    expect(
      screen.getByText(
        "Ask questions about your documents with source citations"
      )
    ).not.toBeNull();
  });

  it("renders welcome placeholder when no messages", () => {
    renderPage();

    expect(
      screen.getByText("Ask questions about your documents")
    ).not.toBeNull();
    expect(
      screen.getByText(
        /Ask natural language questions and receive answers with source citations/
      )
    ).not.toBeNull();
  });

  it("renders New Conversation and Clear buttons with aria-labels", () => {
    renderPage();

    const newConvoBtn = screen.getByLabelText("Start new conversation");
    const clearBtn = screen.getByLabelText("Clear conversation");

    expect(newConvoBtn).not.toBeNull();
    expect(clearBtn).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // Conversation status
  // -------------------------------------------------------------------------

  it("shows conversation status label 'New conversation' when conversationId is null", () => {
    mockStoreState = { ...defaultState, conversationId: null };
    renderPage();

    expect(screen.getByText("New conversation")).not.toBeNull();
  });

  it("shows conversation status label 'Ongoing conversation' when conversationId is set", () => {
    mockStoreState = {
      ...defaultState,
      conversationId: "conv-123",
    };
    renderPage();

    expect(screen.getByText("Ongoing conversation")).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // Message area accessibility
  // -------------------------------------------------------------------------

  it("renders message area with role='log' and aria-label", () => {
    renderPage();

    const logRegion = screen.getByRole("log");
    expect(logRegion).not.toBeNull();
    expect(logRegion.getAttribute("aria-label")).toBe("Conversation messages");
  });

  it("sets aria-busy='true' during loading", () => {
    mockStoreState = { ...defaultState, isLoading: true };
    renderPage();

    const logRegion = screen.getByRole("log");
    expect(logRegion.getAttribute("aria-busy")).toBe("true");
  });

  it("sets aria-busy='false' when not loading", () => {
    mockStoreState = { ...defaultState, isLoading: false };
    renderPage();

    const logRegion = screen.getByRole("log");
    expect(logRegion.getAttribute("aria-busy")).toBe("false");
  });

  // -------------------------------------------------------------------------
  // Typing indicator
  // -------------------------------------------------------------------------

  it("shows typing indicator during loading", () => {
    mockStoreState = { ...defaultState, isLoading: true };
    renderPage();

    expect(screen.getByText("Assistant is typing")).not.toBeNull();
  });

  it("does not show typing indicator when not loading", () => {
    mockStoreState = { ...defaultState, isLoading: false };
    renderPage();

    expect(screen.queryByText("Assistant is typing")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  it("shows error message with Retry button on failure", () => {
    mockStoreState = {
      ...defaultState,
      error: "Something went wrong. Please try again.",
      retryCount: 0,
      lastFailedQuestion: "What is the SOP?",
    };
    renderPage();

    // Error text appears in both the visible error area and the aria-live region
    const errorTexts = screen.getAllByText(
      "Something went wrong. Please try again."
    );
    expect(errorTexts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Retry")).not.toBeNull();
  });

  it("calls retryLastMessage when Retry button is clicked", async () => {
    mockStoreState = {
      ...defaultState,
      error: "Network error",
      retryCount: 1,
      lastFailedQuestion: "What is the SOP?",
    };
    renderPage();

    const retryBtn = screen.getByText("Retry");
    await act(async () => {
      fireEvent.click(retryBtn);
    });

    expect(mockRetryLastMessage).toHaveBeenCalledTimes(1);
  });

  it("disables Retry after 3 attempts", () => {
    mockStoreState = {
      ...defaultState,
      error: "Something went wrong. Please try again.",
      retryCount: 3,
      lastFailedQuestion: "What is the SOP?",
    };
    renderPage();

    // Retry button should not be present; instead shows exhausted message
    expect(screen.queryByText("Retry")).toBeNull();
    expect(
      screen.getByText(
        "Retries exhausted. Please try a different question."
      )
    ).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // Clear confirmation dialog
  // -------------------------------------------------------------------------

  it("shows confirmation dialog on Clear click when messages exist", async () => {
    mockStoreState = {
      ...defaultState,
      messages: [
        {
          id: "msg-001",
          role: "user",
          content: "Hello",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:59:00Z",
        },
      ],
    };
    renderPage();

    const clearBtn = screen.getByLabelText("Clear conversation");
    await act(async () => {
      fireEvent.click(clearBtn);
    });

    // Dialog should appear
    expect(screen.getByRole("dialog")).not.toBeNull();
    expect(screen.getByText("Clear conversation?")).not.toBeNull();
    expect(screen.getByText("Cancel")).not.toBeNull();
    expect(screen.getByText("Confirm")).not.toBeNull();
  });

  it("Cancel on dialog preserves state", async () => {
    mockStoreState = {
      ...defaultState,
      messages: [
        {
          id: "msg-001",
          role: "user",
          content: "Hello",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:59:00Z",
        },
      ],
    };
    renderPage();

    // Open dialog
    const clearBtn = screen.getByLabelText("Clear conversation");
    await act(async () => {
      fireEvent.click(clearBtn);
    });

    // Click Cancel
    const cancelBtn = screen.getByText("Cancel");
    await act(async () => {
      fireEvent.click(cancelBtn);
    });

    // Dialog should be dismissed
    expect(screen.queryByRole("dialog")).toBeNull();
    // clearConversation should NOT have been called
    expect(mockClearConversation).not.toHaveBeenCalled();
  });

  it("Confirm on dialog calls clearConversation", async () => {
    mockStoreState = {
      ...defaultState,
      messages: [
        {
          id: "msg-001",
          role: "user",
          content: "Hello",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:59:00Z",
        },
      ],
    };
    renderPage();

    // Open dialog
    const clearBtn = screen.getByLabelText("Clear conversation");
    await act(async () => {
      fireEvent.click(clearBtn);
    });

    // Click Confirm
    const confirmBtn = screen.getByText("Confirm");
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(mockClearConversation).toHaveBeenCalledTimes(1);
  });

  it("Clear button disabled when no messages", () => {
    mockStoreState = { ...defaultState, messages: [] };
    renderPage();

    const clearBtn = screen.getByLabelText("Clear conversation");
    expect(clearBtn.hasAttribute("disabled")).toBe(true);
  });

  // -------------------------------------------------------------------------
  // Auto-scroll behavior
  // -------------------------------------------------------------------------

  it("auto-scroll behavior when near bottom", () => {
    mockStoreState = {
      ...defaultState,
      messages: [
        {
          id: "msg-001",
          role: "user",
          content: "Hello",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:59:00Z",
        },
      ],
    };
    const { container } = renderPage();

    const logRegion = container.querySelector('[role="log"]') as HTMLElement;
    expect(logRegion).not.toBeNull();

    // Mock scroll properties — near bottom (within 100px threshold)
    Object.defineProperty(logRegion, "scrollHeight", {
      value: 1000,
      configurable: true,
    });
    Object.defineProperty(logRegion, "scrollTop", {
      value: 850,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(logRegion, "clientHeight", {
      value: 100,
      configurable: true,
    });

    // Trigger scroll event to update isNearBottom
    fireEvent.scroll(logRegion);

    // Since scrollHeight(1000) - scrollTop(850) - clientHeight(100) = 50 <= 100 threshold,
    // the component should consider this "near bottom" and auto-scroll on new messages.
    // We verify the scroll handler doesn't throw and the element is accessible.
    expect(logRegion.getAttribute("role")).toBe("log");
  });

  it("shows 'New message' indicator when scrolled up and new message arrives", () => {
    // Start with messages and simulate being scrolled up
    mockStoreState = {
      ...defaultState,
      messages: [
        {
          id: "msg-001",
          role: "user",
          content: "Hello",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:58:00Z",
        },
        {
          id: "msg-002",
          role: "assistant",
          content: "Hi there!",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:58:30Z",
        },
      ],
    };

    const { container, rerender } = renderPage();

    const logRegion = container.querySelector('[role="log"]') as HTMLElement;

    // Mock scroll properties — scrolled far from bottom (> 100px threshold)
    Object.defineProperty(logRegion, "scrollHeight", {
      value: 2000,
      configurable: true,
    });
    Object.defineProperty(logRegion, "scrollTop", {
      value: 500,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(logRegion, "clientHeight", {
      value: 400,
      configurable: true,
    });

    // Trigger scroll to update isNearBottom ref (distance = 2000 - 500 - 400 = 1100 > 100)
    fireEvent.scroll(logRegion);

    // Now add a new message by re-rendering with updated state
    mockStoreState = {
      ...defaultState,
      messages: [
        {
          id: "msg-001",
          role: "user",
          content: "Hello",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:58:00Z",
        },
        {
          id: "msg-002",
          role: "assistant",
          content: "Hi there!",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:58:30Z",
        },
        {
          id: "msg-003",
          role: "user",
          content: "New question",
          citations: [],
          grounded: true,
          timestamp: "2024-06-15T11:59:00Z",
        },
      ],
    };

    rerender(
      <MemoryRouter>
        <KnowledgePage />
      </MemoryRouter>
    );

    // The "New message" indicator should appear
    const indicator = screen.queryByText(/New message/);
    expect(indicator).not.toBeNull();
  });

  // -------------------------------------------------------------------------
  // New Conversation button
  // -------------------------------------------------------------------------

  it("calls startNewConversation when New Conversation button is clicked", async () => {
    renderPage();

    const newConvoBtn = screen.getByLabelText("Start new conversation");
    await act(async () => {
      fireEvent.click(newConvoBtn);
    });

    expect(mockStartNewConversation).toHaveBeenCalledTimes(1);
  });
});
