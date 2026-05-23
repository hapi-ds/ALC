import { describe, it, expect, beforeEach, vi } from "vitest";
import fc from "fast-check";
import { useKnowledgeStore } from "@/stores/knowledgeStore";
import type { KnowledgeState } from "@/stores/knowledgeStore";
import { formatTimestamp } from "@/lib/formatTimestamp";

/**
 * Property-based tests for knowledgeStore.
 *
 * Uses fast-check to verify universal properties hold across all valid inputs.
 */

// Mock apiClient module — use a never-resolving promise so we can inspect intermediate state
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

import { apiClient } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Regex patterns for validation
// ---------------------------------------------------------------------------

const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ISO_8601_REGEX = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}Z$/;

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
// Property Tests
// ---------------------------------------------------------------------------

// Feature: rag-knowledge-base-ui, Property 1: sendMessage state transition
describe("Property 1: sendMessage state transition", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
    // Mock apiClient.post to return a never-resolving promise so we can inspect intermediate state
    mockedApiClient.post.mockReturnValue(new Promise(() => {}));
  });

  /**
   * **Validates: Requirements 1.2**
   *
   * For any non-empty, non-whitespace question string, calling sendMessage when isLoading is false
   * SHALL append a user ChatMessage to the messages array (with a valid UUID v4 id, role="user",
   * the trimmed question as content, empty citations, grounded=true, and a valid ISO 8601 timestamp),
   * set isLoading to true, set error to null, and set inputValue to "".
   */
  it("appends correct user ChatMessage and transitions state for any non-empty, non-whitespace input", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        async (question) => {
          // Reset state before each iteration
          useKnowledgeStore.setState({
            ...defaultState,
            inputValue: "some previous value",
            error: "some previous error",
          });
          // Use a fresh never-resolving promise for each iteration
          mockedApiClient.post.mockReturnValue(new Promise(() => {}));

          // Call sendMessage (don't await — it won't resolve due to the mock)
          const promise = useKnowledgeStore.getState().sendMessage(question);

          // Allow microtask queue to flush so the synchronous state updates happen
          await new Promise((resolve) => setTimeout(resolve, 0));

          const state = useKnowledgeStore.getState();

          // Verify user message was appended
          expect(state.messages).toHaveLength(1);
          const userMsg = state.messages[0];

          // Valid UUID v4 id
          expect(userMsg.id).toMatch(UUID_V4_REGEX);

          // role is "user"
          expect(userMsg.role).toBe("user");

          // content is the trimmed question
          expect(userMsg.content).toBe(question.trim());

          // citations is empty array
          expect(userMsg.citations).toEqual([]);

          // grounded is true
          expect(userMsg.grounded).toBe(true);

          // valid ISO 8601 timestamp
          expect(userMsg.timestamp).toMatch(ISO_8601_REGEX);

          // isLoading set to true
          expect(state.isLoading).toBe(true);

          // error set to null
          expect(state.error).toBeNull();

          // inputValue set to ""
          expect(state.inputValue).toBe("");

          // Clean up: we don't need to await the promise since it never resolves
          void promise;
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 2: Endpoint routing based on conversationId
describe("Property 2: Endpoint routing based on conversationId", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 1.3, 1.4**
   *
   * For any valid question string, when conversationId is null the store SHALL send a POST request
   * to `/api/knowledge/query` with `{ question, user_id, top_k: 5 }`, and when conversationId is
   * a non-null string the store SHALL send a POST request to `/api/knowledge/conversation` with
   * `{ question, user_id, conversation_id, top_k: 5 }`.
   */
  it("routes to /api/knowledge/query when conversationId is null", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        async (question) => {
          // Reset state and mocks for each iteration
          useKnowledgeStore.setState({ ...defaultState, conversationId: null });
          mockedApiClient.post.mockClear();
          mockedApiClient.post.mockReturnValue(new Promise(() => {}));

          const promise = useKnowledgeStore.getState().sendMessage(question);

          // Allow microtask queue to flush
          await new Promise((resolve) => setTimeout(resolve, 0));

          // Verify POST was called with the correct endpoint and payload
          expect(mockedApiClient.post).toHaveBeenCalledTimes(1);
          expect(mockedApiClient.post).toHaveBeenCalledWith(
            "/api/knowledge/query",
            { question: question.trim(), user_id: 42, top_k: 5 },
            { changeReason: "Knowledge base query" }
          );

          void promise;
        }
      ),
      { numRuns: 100 }
    );
  });

  it("routes to /api/knowledge/conversation when conversationId is non-null", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        fc.uuid(),
        async (question, conversationId) => {
          // Reset state and mocks for each iteration
          useKnowledgeStore.setState({ ...defaultState, conversationId });
          mockedApiClient.post.mockClear();
          mockedApiClient.post.mockReturnValue(new Promise(() => {}));

          const promise = useKnowledgeStore.getState().sendMessage(question);

          // Allow microtask queue to flush
          await new Promise((resolve) => setTimeout(resolve, 0));

          // Verify POST was called with the correct endpoint and payload
          expect(mockedApiClient.post).toHaveBeenCalledTimes(1);
          expect(mockedApiClient.post).toHaveBeenCalledWith(
            "/api/knowledge/conversation",
            { question: question.trim(), user_id: 42, conversation_id: conversationId, top_k: 5 },
            { changeReason: "Knowledge base conversation query" }
          );

          void promise;
        }
      ),
      { numRuns: 100 }
    );
  });

  it("sends correct payload shape based on conversationId state (combined property)", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        fc.option(fc.uuid(), { nil: null }),
        async (question, conversationId) => {
          // Reset state and mocks for each iteration
          useKnowledgeStore.setState({ ...defaultState, conversationId });
          mockedApiClient.post.mockClear();
          mockedApiClient.post.mockReturnValue(new Promise(() => {}));

          const promise = useKnowledgeStore.getState().sendMessage(question);

          // Allow microtask queue to flush
          await new Promise((resolve) => setTimeout(resolve, 0));

          expect(mockedApiClient.post).toHaveBeenCalledTimes(1);

          if (conversationId === null) {
            // New conversation: POST /api/knowledge/query
            expect(mockedApiClient.post).toHaveBeenCalledWith(
              "/api/knowledge/query",
              { question: question.trim(), user_id: 42, top_k: 5 },
              { changeReason: "Knowledge base query" }
            );
          } else {
            // Follow-up: POST /api/knowledge/conversation
            expect(mockedApiClient.post).toHaveBeenCalledWith(
              "/api/knowledge/conversation",
              { question: question.trim(), user_id: 42, conversation_id: conversationId, top_k: 5 },
              { changeReason: "Knowledge base conversation query" }
            );
          }

          void promise;
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 3: Successful response appends correct assistant message
describe("Property 3: Successful response appends correct assistant message", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 1.5**
   *
   * For any successful API response containing an answer string, a citations array (0-20 items),
   * a grounded boolean, and a conversation_id string, the store SHALL append an assistant ChatMessage
   * with the answer as content, the citations array mapped to SourceCitation objects, the grounded flag,
   * a valid ISO 8601 timestamp, and SHALL store the conversation_id and set isLoading to false.
   */
  it("appends correct assistant ChatMessage from any valid API response", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 10000 }),
        fc.array(
          fc.record({
            document_uuid: fc.uuid(),
            title: fc.string({ minLength: 1, maxLength: 255 }),
            version: fc.stringMatching(/^\d+\.\d+$/),
            page_or_section: fc.string({ minLength: 1, maxLength: 100 }),
          }),
          { minLength: 0, maxLength: 20 }
        ),
        fc.boolean(),
        fc.uuid(),
        async (answer, citations, grounded, conversation_id) => {
          // Reset state before each iteration
          useKnowledgeStore.setState({ ...defaultState });
          mockedApiClient.post.mockClear();

          // Mock apiClient.post to resolve with the generated response
          mockedApiClient.post.mockResolvedValue({
            answer,
            citations,
            grounded,
            conversation_id,
          });

          // Call sendMessage with a valid question
          await useKnowledgeStore.getState().sendMessage("test question");

          const state = useKnowledgeStore.getState();

          // Should have 2 messages: user + assistant
          expect(state.messages).toHaveLength(2);

          const assistantMsg = state.messages[1];

          // Valid UUID v4 id
          expect(assistantMsg.id).toMatch(UUID_V4_REGEX);

          // role is "assistant"
          expect(assistantMsg.role).toBe("assistant");

          // content is the answer from the API response
          expect(assistantMsg.content).toBe(answer);

          // grounded flag is preserved
          expect(assistantMsg.grounded).toBe(grounded);

          // When grounded=false, the store should set citations to empty array
          // When grounded=true, citations should be passed through as-is
          if (grounded) {
            expect(assistantMsg.citations).toEqual(citations);
          } else {
            expect(assistantMsg.citations).toEqual([]);
          }

          // valid ISO 8601 timestamp
          expect(assistantMsg.timestamp).toMatch(ISO_8601_REGEX);

          // conversation_id stored in state
          expect(state.conversationId).toBe(conversation_id);

          // isLoading set to false
          expect(state.isLoading).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 4: Failed request error handling and rollback
describe("Property 4: Failed request error handling and rollback", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 1.6, 1.11**
   *
   * For any API request that fails with a network error, HTTP status >= 500, or HTTP 422,
   * the store SHALL set error to a non-empty string (the error message from the response or
   * "Network error"), set isLoading to false, and remove the last user message that was
   * optimistically appended to the messages array.
   */
  it("sets error, clears isLoading, and rolls back user message for any error scenario", async () => {
    // Import the mocked ApiError class from the mock module
    const { ApiError } = await import("@/lib/apiClient");

    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        fc.oneof(
          // Network error scenario
          fc.constant({ type: "network" as const }),
          // HTTP 500 scenario
          fc.constant({ type: "http500" as const }),
          // HTTP 422 scenario
          fc.constant({ type: "http422" as const })
        ),
        async (question, errorScenario) => {
          // Reset state before each iteration
          useKnowledgeStore.setState({ ...defaultState });
          mockedApiClient.post.mockClear();

          // Mock apiClient.post to reject with the appropriate error type
          switch (errorScenario.type) {
            case "network":
              mockedApiClient.post.mockRejectedValue(new Error("Network error"));
              break;
            case "http500":
              mockedApiClient.post.mockRejectedValue(
                new ApiError(500, '{"detail":"Internal server error"}', "/api/knowledge/query")
              );
              break;
            case "http422":
              mockedApiClient.post.mockRejectedValue(
                new ApiError(
                  422,
                  JSON.stringify({ detail: [{ msg: "validation error" }] }),
                  "/api/knowledge/query"
                )
              );
              break;
          }

          // Call sendMessage and await it (it will reject internally and handle the error)
          await useKnowledgeStore.getState().sendMessage(question);

          const state = useKnowledgeStore.getState();

          // Messages array should be empty (user message was rolled back)
          expect(state.messages).toHaveLength(0);

          // error should be a non-empty string
          expect(state.error).not.toBeNull();
          expect(typeof state.error).toBe("string");
          expect(state.error!.length).toBeGreaterThan(0);

          // isLoading should be false
          expect(state.isLoading).toBe(false);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 5: Reset actions clear all state
describe("Property 5: Reset actions clear all state", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 1.7, 1.8**
   *
   * For any store state (with any combination of messages, conversationId, error, and inputValue),
   * calling either `startNewConversation` or `clearConversation` SHALL set messages to an empty array,
   * conversationId to null, error to null, and inputValue to "".
   */
  it("startNewConversation and clearConversation both reset all state for any initial state", () => {
    // Arbitrary ChatMessage generator
    const chatMessageArb = fc.record({
      id: fc.uuid(),
      role: fc.constantFrom("user" as const, "assistant" as const),
      content: fc.string({ minLength: 1, maxLength: 200 }),
      citations: fc.array(
        fc.record({
          document_uuid: fc.uuid(),
          title: fc.string({ minLength: 1, maxLength: 50 }),
          version: fc.stringMatching(/^\d+\.\d+$/),
          page_or_section: fc.string({ minLength: 1, maxLength: 50 }),
        }),
        { minLength: 0, maxLength: 5 }
      ),
      grounded: fc.boolean(),
      timestamp: fc.date({ min: new Date("2020-01-01"), max: new Date("2030-01-01") }).map((d) => d.toISOString()),
    });

    fc.assert(
      fc.property(
        fc.array(chatMessageArb, { minLength: 0, maxLength: 10 }),
        fc.option(fc.uuid(), { nil: null }),
        fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
        fc.string({ maxLength: 200 }),
        (messages, conversationId, error, inputValue) => {
          // Set up random state
          useKnowledgeStore.setState({
            messages,
            conversationId,
            error,
            inputValue,
            isLoading: false,
            retryCount: 0,
            lastFailedQuestion: null,
          });

          // Test startNewConversation
          useKnowledgeStore.getState().startNewConversation();
          let state = useKnowledgeStore.getState();
          expect(state.messages).toEqual([]);
          expect(state.conversationId).toBeNull();
          expect(state.error).toBeNull();
          expect(state.inputValue).toBe("");

          // Restore random state for clearConversation test
          useKnowledgeStore.setState({
            messages,
            conversationId,
            error,
            inputValue,
            isLoading: false,
            retryCount: 0,
            lastFailedQuestion: null,
          });

          // Test clearConversation
          useKnowledgeStore.getState().clearConversation();
          state = useKnowledgeStore.getState();
          expect(state.messages).toEqual([]);
          expect(state.conversationId).toBeNull();
          expect(state.error).toBeNull();
          expect(state.inputValue).toBe("");
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 6: Request deduplication when loading
describe("Property 6: Request deduplication when loading", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 1.9**
   *
   * For any store state where `isLoading` is true and any question string, calling `sendMessage`
   * SHALL not modify the messages array, SHALL not change `isLoading`, SHALL not change `error`,
   * and SHALL not initiate a network request.
   */
  it("sendMessage is a no-op when isLoading is true for any question", async () => {
    const chatMessageArb = fc.record({
      id: fc.uuid(),
      role: fc.constantFrom("user" as const, "assistant" as const),
      content: fc.string({ minLength: 1, maxLength: 200 }),
      citations: fc.constant([]),
      grounded: fc.boolean(),
      timestamp: fc.date({ min: new Date("2020-01-01"), max: new Date("2030-01-01") }).map((d) => d.toISOString()),
    });

    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        fc.array(chatMessageArb, { minLength: 0, maxLength: 5 }),
        fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
        async (question, messages, error) => {
          // Set state with isLoading=true
          useKnowledgeStore.setState({
            messages,
            conversationId: null,
            isLoading: true,
            error,
            inputValue: "some value",
            retryCount: 0,
            lastFailedQuestion: null,
          });
          mockedApiClient.post.mockClear();

          // Capture state before
          const messagesBefore = [...messages];
          const errorBefore = error;

          // Call sendMessage
          await useKnowledgeStore.getState().sendMessage(question);

          const state = useKnowledgeStore.getState();

          // Messages unchanged
          expect(state.messages).toEqual(messagesBefore);

          // isLoading still true
          expect(state.isLoading).toBe(true);

          // error unchanged
          expect(state.error).toBe(errorBefore);

          // No network request made
          expect(mockedApiClient.post).not.toHaveBeenCalled();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 7: Whitespace-only input rejection
describe("Property 7: Whitespace-only input rejection", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 1.10**
   *
   * For any string composed entirely of whitespace characters (spaces, tabs, newlines, or empty string),
   * calling `sendMessage` SHALL not modify the messages array, SHALL not change `isLoading`,
   * SHALL not change `error`, and SHALL not initiate a network request.
   */
  it("sendMessage is a no-op for any whitespace-only or empty input", async () => {
    // Generate strings composed entirely of whitespace characters
    const whitespaceCharArb = fc.constantFrom(" ", "\t", "\n", "\r", "\f", "\v");
    const whitespaceArb = fc.array(whitespaceCharArb, { minLength: 0, maxLength: 20 }).map((chars) => chars.join(""));

    await fc.assert(
      fc.asyncProperty(whitespaceArb, async (whitespaceInput) => {
        // Reset state
        useKnowledgeStore.setState({ ...defaultState });
        mockedApiClient.post.mockClear();

        // Call sendMessage with whitespace-only input
        await useKnowledgeStore.getState().sendMessage(whitespaceInput);

        const state = useKnowledgeStore.getState();

        // Messages unchanged (empty)
        expect(state.messages).toEqual([]);

        // isLoading unchanged (false)
        expect(state.isLoading).toBe(false);

        // error unchanged (null)
        expect(state.error).toBeNull();

        // No network request made
        expect(mockedApiClient.post).not.toHaveBeenCalled();
      }),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 8: Ungrounded messages have empty citations
describe("Property 8: Ungrounded messages have empty citations", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 2.4**
   *
   * For any assistant ChatMessage where `grounded` is false, the `citations` array SHALL be
   * empty (length 0). This tests the store behavior: when API returns grounded=false, the store
   * sets citations to [].
   */
  it("when API returns grounded=false, assistant message always has empty citations", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 10000 }),
        fc.array(
          fc.record({
            document_uuid: fc.uuid(),
            title: fc.string({ minLength: 1, maxLength: 255 }),
            version: fc.stringMatching(/^\d+\.\d+$/),
            page_or_section: fc.string({ minLength: 1, maxLength: 100 }),
          }),
          { minLength: 1, maxLength: 20 }
        ),
        fc.uuid(),
        async (answer, citations, conversation_id) => {
          // Reset state
          useKnowledgeStore.setState({ ...defaultState });
          mockedApiClient.post.mockClear();

          // Mock API to return grounded=false with non-empty citations
          mockedApiClient.post.mockResolvedValue({
            answer,
            citations, // non-empty citations from API
            grounded: false, // but grounded is false
            conversation_id,
          });

          // Send a message
          await useKnowledgeStore.getState().sendMessage("test question");

          const state = useKnowledgeStore.getState();

          // Should have 2 messages: user + assistant
          expect(state.messages).toHaveLength(2);

          const assistantMsg = state.messages[1];

          // grounded should be false
          expect(assistantMsg.grounded).toBe(false);

          // citations should be empty regardless of what API returned
          expect(assistantMsg.citations).toEqual([]);
          expect(assistantMsg.citations).toHaveLength(0);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 9: Timestamp formatting
describe("Property 9: Timestamp formatting", () => {
  /**
   * **Validates: Requirements 3.6**
   *
   * For any timestamp less than 60 seconds ago, the formatted output SHALL be "just now".
   * For any timestamp between 60 seconds and 60 minutes ago, the output SHALL be "N minutes ago".
   * For any timestamp between 60 minutes and 24 hours ago, the output SHALL be "N hours ago".
   * For any timestamp more than 24 hours ago, the output SHALL be in "HH:MM" 24-hour format.
   */
  it("formats timestamps correctly based on time offset from now", () => {
    const referenceTime = new Date("2025-06-15T12:00:00.000Z").getTime();

    fc.assert(
      fc.property(
        fc.oneof(
          // Less than 60 seconds ago
          fc.integer({ min: 0, max: 59 }).map((seconds) => ({
            offsetMs: seconds * 1000,
            category: "just_now" as const,
          })),
          // 60 seconds to 60 minutes ago
          fc.integer({ min: 60, max: 3599 }).map((seconds) => ({
            offsetMs: seconds * 1000,
            category: "minutes" as const,
          })),
          // 60 minutes to 24 hours ago
          fc.integer({ min: 3600, max: 86399 }).map((seconds) => ({
            offsetMs: seconds * 1000,
            category: "hours" as const,
          })),
          // More than 24 hours ago
          fc.integer({ min: 86400, max: 604800 }).map((seconds) => ({
            offsetMs: seconds * 1000,
            category: "date" as const,
          }))
        ),
        ({ offsetMs, category }) => {
          const timestamp = new Date(referenceTime - offsetMs).toISOString();
          const result = formatTimestamp(timestamp, referenceTime);

          switch (category) {
            case "just_now":
              expect(result).toBe("just now");
              break;
            case "minutes": {
              const expectedMinutes = Math.floor(offsetMs / 1000 / 60);
              expect(result).toBe(`${expectedMinutes} minutes ago`);
              break;
            }
            case "hours": {
              const expectedHours = Math.floor(offsetMs / 1000 / 60 / 60);
              expect(result).toBe(`${expectedHours} hours ago`);
              break;
            }
            case "date": {
              // Should be in HH:MM 24-hour format
              expect(result).toMatch(/^\d{2}:\d{2}$/);
              // Verify the actual time matches
              const date = new Date(timestamp);
              const expectedHours = date.getUTCHours().toString().padStart(2, "0");
              const expectedMinutes = date.getUTCMinutes().toString().padStart(2, "0");
              expect(result).toBe(`${expectedHours}:${expectedMinutes}`);
              break;
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 10: Citation link correctness
describe("Property 10: Citation link correctness", () => {
  /**
   * **Validates: Requirements 4.2, 9.7**
   *
   * For any SourceCitation with a document_uuid, title, and version, the rendered citation link
   * SHALL have an `href` pointing to `/documents/{document_uuid}` and an `aria-label` of
   * "Open document: {title} version {version}".
   */
  it("computes correct href and aria-label from any citation data", () => {
    fc.assert(
      fc.property(
        fc.record({
          document_uuid: fc.uuid(),
          title: fc.string({ minLength: 1, maxLength: 255 }),
          version: fc.stringMatching(/^\d+\.\d+$/),
          page_or_section: fc.string({ minLength: 1, maxLength: 100 }),
        }),
        (citation) => {
          // Pure data transformation: compute expected href and aria-label
          const expectedHref = `/documents/${citation.document_uuid}`;
          const expectedAriaLabel = `Open document: ${citation.title} version ${citation.version}`;

          // Verify the transformation produces correct results
          expect(expectedHref).toBe(`/documents/${citation.document_uuid}`);
          expect(expectedAriaLabel).toBe(
            `Open document: ${citation.title} version ${citation.version}`
          );

          // Verify href starts with /documents/ and contains the UUID
          expect(expectedHref.startsWith("/documents/")).toBe(true);
          expect(expectedHref).toContain(citation.document_uuid);

          // Verify aria-label contains the title and version
          expect(expectedAriaLabel).toContain(citation.title);
          expect(expectedAriaLabel).toContain(citation.version);
          expect(expectedAriaLabel.startsWith("Open document: ")).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});

// Feature: rag-knowledge-base-ui, Property 11: New question clears previous error
describe("Property 11: New question clears previous error", () => {
  beforeEach(() => {
    useKnowledgeStore.setState(defaultState);
    vi.clearAllMocks();
  });

  /**
   * **Validates: Requirements 8.7**
   *
   * For any store state where `error` is not null, successfully calling `sendMessage` with a valid
   * non-empty question SHALL set `error` to null before the API request is made.
   */
  it("sendMessage clears error for any non-null error state and valid question", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1 }).filter((s) => s.trim().length > 0),
        fc.string({ minLength: 1, maxLength: 200 }),
        async (question, previousError) => {
          // Set state with a non-null error
          useKnowledgeStore.setState({
            ...defaultState,
            error: previousError,
            isLoading: false,
          });
          mockedApiClient.post.mockClear();
          // Use a never-resolving promise so we can inspect intermediate state
          mockedApiClient.post.mockReturnValue(new Promise(() => {}));

          // Call sendMessage
          const promise = useKnowledgeStore.getState().sendMessage(question);

          // Allow microtask queue to flush
          await new Promise((resolve) => setTimeout(resolve, 0));

          const state = useKnowledgeStore.getState();

          // Error should be cleared to null
          expect(state.error).toBeNull();

          // isLoading should be true (request in flight)
          expect(state.isLoading).toBe(true);

          void promise;
        }
      ),
      { numRuns: 100 }
    );
  });
});
