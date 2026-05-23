import { describe, it, expect, beforeEach, vi } from "vitest";
import { useKnowledgeStore } from "@/stores/knowledgeStore";
import type { KnowledgeState } from "@/stores/knowledgeStore";

/**
 * Unit tests for knowledgeStore actions.
 *
 * Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11
 */

// Mock apiClient module
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

// Mock authStore module
vi.mock("@/stores/authStore", () => ({
  useAuthStore: {
    getState: () => ({
      user: { id: 42, username: "testuser", email: "test@example.com", full_name: "Test User", roles: ["user"] },
    }),
  },
}));

import { apiClient, ApiError } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeQueryResponse(overrides: Record<string, unknown> = {}) {
  return {
    answer: "The SOP requires documentation of all changes.",
    citations: [
      {
        document_uuid: "doc-uuid-001",
        title: "SOP-001 Change Control",
        version: "1.0",
        page_or_section: "Section 3.2",
      },
    ],
    grounded: true,
    conversation_id: "conv-uuid-123",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default state for reset between tests
// ---------------------------------------------------------------------------

const defaultState: Partial<KnowledgeState> = {
  messages: [],
  conversationId: null,
  isLoading: false,
  error: null,
  inputValue: "",
  retryCount: 0,
  lastFailedQuestion: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("knowledgeStore", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has correct defaults", () => {
      useKnowledgeStore.setState(defaultState);
      const state = useKnowledgeStore.getState();

      expect(state.messages).toEqual([]);
      expect(state.conversationId).toBeNull();
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.inputValue).toBe("");
    });
  });

  // -------------------------------------------------------------------------
  // sendMessage()
  // -------------------------------------------------------------------------

  describe("sendMessage()", () => {
    it("appends user message and calls /api/knowledge/query when no conversationId", async () => {
      mockedApiClient.post.mockResolvedValue(makeQueryResponse());

      await useKnowledgeStore.getState().sendMessage("What is the SOP?");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/knowledge/query",
        { question: "What is the SOP?", user_id: 42, top_k: 5 },
        { changeReason: "Knowledge base query" },
      );

      const state = useKnowledgeStore.getState();
      // Should have user message + assistant message
      expect(state.messages).toHaveLength(2);
      expect(state.messages[0].role).toBe("user");
      expect(state.messages[0].content).toBe("What is the SOP?");
      expect(state.messages[0].citations).toEqual([]);
      expect(state.messages[0].grounded).toBe(true);
    });

    it("calls /api/knowledge/conversation when conversationId exists", async () => {
      useKnowledgeStore.setState({ conversationId: "conv-existing-456" });
      mockedApiClient.post.mockResolvedValue(makeQueryResponse());

      await useKnowledgeStore.getState().sendMessage("Follow-up question?");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/knowledge/conversation",
        {
          question: "Follow-up question?",
          user_id: 42,
          conversation_id: "conv-existing-456",
          top_k: 5,
        },
        { changeReason: "Knowledge base conversation query" },
      );
    });

    it("stores conversation_id from response", async () => {
      mockedApiClient.post.mockResolvedValue(makeQueryResponse({ conversation_id: "new-conv-789" }));

      await useKnowledgeStore.getState().sendMessage("Test question");

      const state = useKnowledgeStore.getState();
      expect(state.conversationId).toBe("new-conv-789");
    });

    it("handles successful response with citations", async () => {
      const response = makeQueryResponse({
        answer: "Here is the answer.",
        citations: [
          { document_uuid: "doc-1", title: "Doc One", version: "2.0", page_or_section: "Page 5" },
          { document_uuid: "doc-2", title: "Doc Two", version: "1.1", page_or_section: "Section 4" },
        ],
        grounded: true,
      });
      mockedApiClient.post.mockResolvedValue(response);

      await useKnowledgeStore.getState().sendMessage("Question with citations");

      const state = useKnowledgeStore.getState();
      const assistantMsg = state.messages[1];
      expect(assistantMsg.role).toBe("assistant");
      expect(assistantMsg.content).toBe("Here is the answer.");
      expect(assistantMsg.citations).toHaveLength(2);
      expect(assistantMsg.citations[0].document_uuid).toBe("doc-1");
      expect(assistantMsg.citations[1].title).toBe("Doc Two");
      expect(assistantMsg.grounded).toBe(true);
      expect(state.isLoading).toBe(false);
    });

    it("handles ungrounded response (grounded=false, empty citations)", async () => {
      const response = makeQueryResponse({
        answer: "I could not find relevant information.",
        citations: [
          { document_uuid: "doc-1", title: "Doc One", version: "1.0", page_or_section: "Page 1" },
        ],
        grounded: false,
      });
      mockedApiClient.post.mockResolvedValue(response);

      await useKnowledgeStore.getState().sendMessage("Unknown topic");

      const state = useKnowledgeStore.getState();
      const assistantMsg = state.messages[1];
      expect(assistantMsg.grounded).toBe(false);
      // When grounded=false, citations should be empty
      expect(assistantMsg.citations).toEqual([]);
    });

    it("handles HTTP 500 error with rollback (removes user message)", async () => {
      const error = new ApiError(500, '{"detail":"Internal server error"}', "/api/knowledge/query");
      mockedApiClient.post.mockRejectedValue(error);

      await useKnowledgeStore.getState().sendMessage("Failing question");

      const state = useKnowledgeStore.getState();
      // User message should be rolled back
      expect(state.messages).toEqual([]);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeTruthy();
      expect(state.lastFailedQuestion).toBe("Failing question");
    });

    it("handles HTTP 422 with validation detail", async () => {
      const error = new ApiError(
        422,
        JSON.stringify({ detail: [{ msg: "String should have at least 1 character" }] }),
        "/api/knowledge/query",
      );
      mockedApiClient.post.mockRejectedValue(error);

      await useKnowledgeStore.getState().sendMessage("x");

      const state = useKnowledgeStore.getState();
      expect(state.error).toBe("String should have at least 1 character");
      expect(state.messages).toEqual([]);
      expect(state.isLoading).toBe(false);
    });

    it("skips when isLoading=true (deduplication)", async () => {
      useKnowledgeStore.setState({ isLoading: true });

      await useKnowledgeStore.getState().sendMessage("Should be skipped");

      expect(mockedApiClient.post).not.toHaveBeenCalled();
      const state = useKnowledgeStore.getState();
      expect(state.messages).toEqual([]);
    });

    it("rejects empty string", async () => {
      await useKnowledgeStore.getState().sendMessage("");

      expect(mockedApiClient.post).not.toHaveBeenCalled();
      const state = useKnowledgeStore.getState();
      expect(state.messages).toEqual([]);
      expect(state.isLoading).toBe(false);
    });

    it("rejects whitespace-only string", async () => {
      await useKnowledgeStore.getState().sendMessage("   \t\n  ");

      expect(mockedApiClient.post).not.toHaveBeenCalled();
      const state = useKnowledgeStore.getState();
      expect(state.messages).toEqual([]);
      expect(state.isLoading).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // retryLastMessage()
  // -------------------------------------------------------------------------

  describe("retryLastMessage()", () => {
    it("re-sends last failed question", async () => {
      useKnowledgeStore.setState({
        lastFailedQuestion: "Retry this question",
        retryCount: 0,
      });
      mockedApiClient.post.mockResolvedValue(makeQueryResponse());

      await useKnowledgeStore.getState().retryLastMessage();

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/knowledge/query",
        expect.objectContaining({ question: "Retry this question" }),
        expect.any(Object),
      );
    });

    it("increments retryCount", async () => {
      useKnowledgeStore.setState({
        lastFailedQuestion: "Retry question",
        retryCount: 1,
      });
      mockedApiClient.post.mockResolvedValue(makeQueryResponse());

      await useKnowledgeStore.getState().retryLastMessage();

      // retryCount was 1, incremented to 2 before sendMessage
      // On success, sendMessage resets retryCount to 0
      const state = useKnowledgeStore.getState();
      expect(state.retryCount).toBe(0); // reset on success
    });

    it("does nothing when retryCount >= 3", async () => {
      useKnowledgeStore.setState({
        lastFailedQuestion: "Exhausted question",
        retryCount: 3,
      });

      await useKnowledgeStore.getState().retryLastMessage();

      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });

    it("does nothing when lastFailedQuestion is null", async () => {
      useKnowledgeStore.setState({
        lastFailedQuestion: null,
        retryCount: 0,
      });

      await useKnowledgeStore.getState().retryLastMessage();

      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // startNewConversation()
  // -------------------------------------------------------------------------

  describe("startNewConversation()", () => {
    it("resets all state", () => {
      useKnowledgeStore.setState({
        messages: [
          {
            id: "msg-1",
            role: "user",
            content: "Hello",
            citations: [],
            grounded: true,
            timestamp: new Date().toISOString(),
          },
        ],
        conversationId: "conv-123",
        error: "Some error",
        inputValue: "partial input",
        retryCount: 2,
        lastFailedQuestion: "failed q",
      });

      useKnowledgeStore.getState().startNewConversation();

      const state = useKnowledgeStore.getState();
      expect(state.messages).toEqual([]);
      expect(state.conversationId).toBeNull();
      expect(state.error).toBeNull();
      expect(state.inputValue).toBe("");
      expect(state.retryCount).toBe(0);
      expect(state.lastFailedQuestion).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // clearConversation()
  // -------------------------------------------------------------------------

  describe("clearConversation()", () => {
    it("resets all state", () => {
      useKnowledgeStore.setState({
        messages: [
          {
            id: "msg-1",
            role: "assistant",
            content: "Answer",
            citations: [{ document_uuid: "d1", title: "T", version: "1.0", page_or_section: "S1" }],
            grounded: true,
            timestamp: new Date().toISOString(),
          },
        ],
        conversationId: "conv-456",
        error: "Old error",
        inputValue: "some text",
        retryCount: 1,
        lastFailedQuestion: "old question",
      });

      useKnowledgeStore.getState().clearConversation();

      const state = useKnowledgeStore.getState();
      expect(state.messages).toEqual([]);
      expect(state.conversationId).toBeNull();
      expect(state.error).toBeNull();
      expect(state.inputValue).toBe("");
      expect(state.retryCount).toBe(0);
      expect(state.lastFailedQuestion).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // setInputValue()
  // -------------------------------------------------------------------------

  describe("setInputValue()", () => {
    it("updates inputValue", () => {
      useKnowledgeStore.getState().setInputValue("Hello world");

      expect(useKnowledgeStore.getState().inputValue).toBe("Hello world");
    });

    it("caps at 2000 characters", () => {
      const longInput = "a".repeat(2500);

      useKnowledgeStore.getState().setInputValue(longInput);

      expect(useKnowledgeStore.getState().inputValue).toHaveLength(2000);
      expect(useKnowledgeStore.getState().inputValue).toBe("a".repeat(2000));
    });
  });
});
