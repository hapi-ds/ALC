import { create } from "zustand";
import { apiClient, ApiError } from "../lib/apiClient";
import { useAuthStore } from "./authStore";

// ---------------------------------------------------------------------------
// Interfaces
// ---------------------------------------------------------------------------

export interface SourceCitation {
  document_uuid: string;
  title: string; // max 255 chars
  version: string; // semver-like, e.g. "1.0", "2.1"
  page_or_section: string; // max 100 chars
}

export interface ChatMessage {
  id: string; // UUID v4
  role: "user" | "assistant";
  content: string; // max 10,000 chars
  citations: SourceCitation[]; // 0-20 items
  grounded: boolean; // always true for user messages
  timestamp: string; // ISO 8601 UTC
}

export interface KnowledgeState {
  messages: ChatMessage[]; // max 200 per conversation
  conversationId: string | null;
  isLoading: boolean;
  error: string | null;
  inputValue: string;
  retryCount: number;
  lastFailedQuestion: string | null;

  sendMessage: (question: string) => Promise<void>;
  retryLastMessage: () => Promise<void>;
  startNewConversation: () => void;
  clearConversation: () => void;
  setInputValue: (value: string) => void;
}

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

interface KnowledgeQueryResponse {
  answer: string;
  citations: SourceCitation[];
  grounded: boolean;
  conversation_id: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateUUID(): string {
  return crypto.randomUUID();
}

function createTimestamp(): string {
  return new Date().toISOString();
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  messages: [],
  conversationId: null,
  isLoading: false,
  error: null,
  inputValue: "",
  retryCount: 0,
  lastFailedQuestion: null,

  sendMessage: async (question: string) => {
    const state = get();

    // Guard against concurrent calls
    if (state.isLoading) {
      return;
    }

    // Reject whitespace-only or empty input
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }

    // Create optimistic user message
    const userMessage: ChatMessage = {
      id: generateUUID(),
      role: "user",
      content: trimmed,
      citations: [],
      grounded: true,
      timestamp: createTimestamp(),
    };

    // Optimistically append user message, set loading, clear error and input
    set({
      messages: [...state.messages, userMessage],
      isLoading: true,
      error: null,
      inputValue: "",
    });

    try {
      const userId = useAuthStore.getState().user?.id;

      let response: KnowledgeQueryResponse;

      if (state.conversationId === null) {
        // New conversation — POST /api/knowledge/query
        response = await apiClient.post<KnowledgeQueryResponse>(
          "/api/knowledge/query",
          { question: trimmed, user_id: userId, top_k: 5 },
          { changeReason: "Knowledge base query" }
        );
      } else {
        // Follow-up — POST /api/knowledge/conversation
        response = await apiClient.post<KnowledgeQueryResponse>(
          "/api/knowledge/conversation",
          {
            question: trimmed,
            user_id: userId,
            conversation_id: state.conversationId,
            top_k: 5,
          },
          { changeReason: "Knowledge base conversation query" }
        );
      }

      // Create assistant message from response
      const assistantMessage: ChatMessage = {
        id: generateUUID(),
        role: "assistant",
        content: response.answer,
        citations: response.grounded ? response.citations : [],
        grounded: response.grounded,
        timestamp: createTimestamp(),
      };

      set({
        messages: [...get().messages, assistantMessage],
        conversationId: response.conversation_id,
        isLoading: false,
        retryCount: 0,
        lastFailedQuestion: null,
      });
    } catch (error: unknown) {
      // Determine error message
      let errorMessage: string;
      if (error instanceof ApiError) {
        // Try to extract validation detail for 422
        if (error.status === 422) {
          try {
            const parsed = JSON.parse(error.body);
            errorMessage =
              parsed.detail?.[0]?.msg || parsed.detail || error.message;
          } catch {
            errorMessage = error.message;
          }
        } else {
          errorMessage = error.message;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      } else {
        errorMessage = "Network error";
      }

      // Rollback: remove the optimistically-added user message
      const currentMessages = get().messages;
      const rolledBackMessages = currentMessages.filter(
        (msg) => msg.id !== userMessage.id
      );

      set({
        messages: rolledBackMessages,
        isLoading: false,
        error: errorMessage,
        lastFailedQuestion: trimmed,
      });
    }
  },

  retryLastMessage: async () => {
    const state = get();

    // Only retry if we have a failed question and haven't exceeded max retries
    if (state.lastFailedQuestion === null || state.retryCount >= 3) {
      return;
    }

    // Increment retry count before sending
    set({ retryCount: state.retryCount + 1 });

    // Re-send the last failed question
    await get().sendMessage(state.lastFailedQuestion);
  },

  startNewConversation: () => {
    set({
      messages: [],
      conversationId: null,
      error: null,
      inputValue: "",
      retryCount: 0,
      lastFailedQuestion: null,
    });
  },

  clearConversation: () => {
    set({
      messages: [],
      conversationId: null,
      error: null,
      inputValue: "",
      retryCount: 0,
      lastFailedQuestion: null,
    });
  },

  setInputValue: (value: string) => {
    // Cap at 2000 characters
    set({ inputValue: value.slice(0, 2000) });
  },
}));
