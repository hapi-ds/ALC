import { Info } from "lucide-react";
import type { ChatMessage as ChatMessageType } from "@/stores/knowledgeStore";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { renderMarkdown } from "@/lib/renderMarkdown";
import { CitationList } from "./CitationList";

interface ChatMessageProps {
  message: ChatMessageType;
  onCitationClick?: (documentUuid: string) => void;
}

/**
 * ChatMessage renders a single chat message bubble.
 *
 * - User messages: right-aligned with blue background, plain text content
 * - Assistant messages: left-aligned with gray background, markdown-rendered content,
 *   collapsible citation list below
 * - Ungrounded assistant messages: muted styling with info icon, no citations
 *
 * Validates: Requirements 3.1, 3.2, 3.6, 3.7, 2.3, 10.2, 10.4
 */
export function ChatMessage({ message, onCitationClick }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isUngrounded = message.role === "assistant" && !message.grounded;

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"} w-full`}
    >
      <div
        className={`
          min-w-[120px] max-w-[90%] md:max-w-[80%]
          rounded-lg px-4 py-3
          ${isUser
            ? "bg-blue-100 dark:bg-blue-900 text-foreground"
            : isUngrounded
              ? "bg-gray-100 dark:bg-gray-800 text-foreground opacity-75"
              : "bg-gray-100 dark:bg-gray-800 text-foreground"
          }
        `}
      >
        {/* Ungrounded indicator */}
        {isUngrounded && (
          <div className="flex items-center gap-1.5 mb-2 text-muted-foreground">
            <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="text-xs font-medium">
              No relevant content found in knowledge base
            </span>
          </div>
        )}

        {/* Message content */}
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap break-words">
            {message.content}
          </p>
        ) : (
          <div
            className="text-sm prose-sm break-words [&_pre]:my-2 [&_p]:my-1"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
          />
        )}

        {/* Citations (only for grounded assistant messages) */}
        {message.role === "assistant" && message.grounded && message.citations.length > 0 && (
          <CitationList
            citations={message.citations}
            onCitationClick={onCitationClick}
          />
        )}

        {/* Timestamp */}
        <div
          className={`text-xs mt-2 ${
            isUser ? "text-blue-600 dark:text-blue-300" : "text-muted-foreground"
          }`}
        >
          <time dateTime={message.timestamp}>
            {formatTimestamp(message.timestamp)}
          </time>
        </div>
      </div>
    </div>
  );
}
