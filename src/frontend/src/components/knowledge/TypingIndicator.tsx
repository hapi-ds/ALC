/**
 * TypingIndicator renders an animated dots pattern in an assistant-style bubble
 * to indicate the system is processing a query.
 *
 * - Left-aligned assistant bubble matching ChatMessage assistant styling
 * - Three animated dots with staggered bounce delays
 * - Screen reader accessible via aria-live region
 *
 * Validates: Requirements 6.1, 6.3
 */
export function TypingIndicator() {
  return (
    <div className="flex justify-start w-full">
      <div className="min-w-[120px] max-w-[90%] md:max-w-[80%] rounded-lg px-4 py-3 bg-gray-100 dark:bg-gray-800">
        {/* Visually hidden aria-live announcement for screen readers */}
        <span className="sr-only" aria-live="polite">
          Assistant is typing
        </span>

        {/* Animated dots */}
        <div className="flex items-center gap-1.5" aria-hidden="true">
          <span className="h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:0ms]" />
          <span className="h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:150ms]" />
          <span className="h-2 w-2 rounded-full bg-gray-400 dark:bg-gray-500 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}
