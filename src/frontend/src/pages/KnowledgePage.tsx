import { useState, useRef, useEffect, useCallback } from "react";
import { MessageSquare, Plus, Trash2, AlertCircle } from "lucide-react";
import { useKnowledgeStore } from "@/stores/knowledgeStore";
import { ChatMessage } from "@/components/knowledge/ChatMessage";
import { TypingIndicator } from "@/components/knowledge/TypingIndicator";
import { ChatInput } from "@/components/knowledge/ChatInput";
import type { ChatInputHandle } from "@/components/knowledge/ChatInput";

/**
 * KnowledgePage provides the full chat-style interface for querying the
 * document knowledge base using the existing RAG pipeline backend.
 *
 * Layout: full-height flex column — header → scrollable message area → input area anchored at bottom.
 *
 * Validates: Requirements 3.3, 3.4, 3.5, 5.4, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7,
 * 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
 */
export function KnowledgePage() {
  const {
    messages,
    conversationId,
    isLoading,
    error,
    inputValue,
    retryCount,
    sendMessage,
    retryLastMessage,
    startNewConversation,
    clearConversation,
    setInputValue,
  } = useKnowledgeStore();

  const [showClearDialog, setShowClearDialog] = useState(false);
  const [showNewMessageIndicator, setShowNewMessageIndicator] = useState(false);

  const messageAreaRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);
  const isNearBottomRef = useRef(true);
  const prevMessageCountRef = useRef(messages.length);

  // ---------------------------------------------------------------------------
  // Auto-scroll behavior
  // ---------------------------------------------------------------------------

  const checkIfNearBottom = useCallback(() => {
    const el = messageAreaRef.current;
    if (!el) return;
    const threshold = 100;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    isNearBottomRef.current = distanceFromBottom <= threshold;

    // Hide indicator when user scrolls to bottom
    if (isNearBottomRef.current) {
      setShowNewMessageIndicator(false);
    }
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = messageAreaRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    setShowNewMessageIndicator(false);
  }, []);

  // Auto-scroll on new messages or when loading (to keep typing indicator visible)
  useEffect(() => {
    const messageCount = messages.length;
    const hasNewMessage = messageCount > prevMessageCountRef.current;
    prevMessageCountRef.current = messageCount;

    if (hasNewMessage || isLoading) {
      if (isNearBottomRef.current) {
        scrollToBottom();
      } else if (hasNewMessage) {
        setShowNewMessageIndicator(true);
      }
    }
  }, [messages.length, isLoading, scrollToBottom]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleSubmit = useCallback(() => {
    sendMessage(inputValue);
    // Return focus to input after submit
    setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [sendMessage, inputValue]);

  const handleRetry = useCallback(() => {
    retryLastMessage();
    // Return focus to input after retry
    setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [retryLastMessage]);

  const handleNewConversation = useCallback(() => {
    startNewConversation();
    setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [startNewConversation]);

  const handleClearClick = useCallback(() => {
    if (messages.length === 0) return;
    setShowClearDialog(true);
  }, [messages.length]);

  const handleClearConfirm = useCallback(() => {
    clearConversation();
    setShowClearDialog(false);
    // Return focus to input after clear
    setTimeout(() => chatInputRef.current?.focus(), 0);
  }, [clearConversation]);

  const handleClearCancel = useCallback(() => {
    setShowClearDialog(false);
  }, []);

  const handleNewMessageClick = useCallback(() => {
    scrollToBottom();
  }, [scrollToBottom]);

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------

  const hasMessages = messages.length > 0;
  const conversationStatus = conversationId ? "Ongoing conversation" : "New conversation";
  const retriesExhausted = retryCount >= 3;

  // Get the latest assistant message content for aria-live announcements
  const lastMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const liveAnnouncement = (() => {
    if (error) return error;
    if (lastMessage?.role === "assistant") return lastMessage.content;
    return "";
  })();

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-border">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-2xl font-bold">Knowledge Chat</h2>
            <p className="text-sm text-muted-foreground">
              Ask questions about your documents with source citations
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-muted-foreground hidden sm:inline">
              {conversationStatus}
            </span>
            <button
              type="button"
              onClick={handleNewConversation}
              aria-label="Start new conversation"
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline">New Conversation</span>
            </button>
            <button
              type="button"
              onClick={handleClearClick}
              disabled={!hasMessages}
              aria-label="Clear conversation"
              className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium border border-border hover:bg-accent disabled:pointer-events-none disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          </div>
        </div>
      </div>

      {/* Message area */}
      <div
        ref={messageAreaRef}
        role="log"
        aria-label="Conversation messages"
        aria-busy={isLoading}
        onScroll={checkIfNearBottom}
        className="flex-1 overflow-y-auto px-4 py-4 relative"
      >
        {/* Welcome placeholder when no messages */}
        {!hasMessages && !error && (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
              <h3 className="text-lg font-medium">Ask questions about your documents</h3>
              <p className="text-sm mt-1 max-w-md">
                Ask natural language questions and receive answers with source citations from your indexed documents.
              </p>
            </div>
          </div>
        )}

        {/* Messages */}
        {hasMessages && (
          <div className="space-y-4">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
          </div>
        )}

        {/* Typing indicator */}
        {isLoading && (
          <div className="mt-4">
            <TypingIndicator />
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-destructive/10 border border-destructive/20">
            <AlertCircle className="h-5 w-5 text-destructive shrink-0 mt-0.5" aria-hidden="true" />
            <div className="flex-1 min-w-0">
              <p className="text-sm text-destructive">{error}</p>
              {retriesExhausted ? (
                <p className="text-xs text-muted-foreground mt-1">
                  Retries exhausted. Please try a different question.
                </p>
              ) : (
                <button
                  type="button"
                  onClick={handleRetry}
                  className="mt-1 text-xs font-medium text-primary hover:underline"
                >
                  Retry
                </button>
              )}
            </div>
          </div>
        )}

        {/* New message indicator (floating) */}
        {showNewMessageIndicator && (
          <button
            type="button"
            onClick={handleNewMessageClick}
            className="sticky bottom-2 left-1/2 -translate-x-1/2 z-10 inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium bg-primary text-primary-foreground shadow-md hover:bg-primary/90"
          >
            New message ↓
          </button>
        )}
      </div>

      {/* aria-live region for announcing new messages and errors */}
      <div aria-live="polite" className="sr-only">
        {liveAnnouncement}
      </div>

      {/* Chat input */}
      <div className="shrink-0">
        <ChatInput
          ref={chatInputRef}
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleSubmit}
          disabled={isLoading}
          maxLength={2000}
        />
      </div>

      {/* Clear confirmation dialog */}
      {showClearDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          role="dialog"
          aria-modal="true"
          aria-labelledby="clear-dialog-title"
        >
          <div className="bg-background border border-border rounded-lg p-6 max-w-sm mx-4 shadow-lg">
            <h3 id="clear-dialog-title" className="text-lg font-semibold mb-2">
              Clear conversation?
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              This conversation will be permanently removed. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleClearCancel}
                className="rounded-md px-4 py-2 text-sm font-medium border border-border hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleClearConfirm}
                className="rounded-md px-4 py-2 text-sm font-medium bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
