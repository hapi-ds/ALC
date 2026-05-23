import { useRef, useCallback, forwardRef, useImperativeHandle } from "react";
import type { KeyboardEvent, ChangeEvent } from "react";
import { Send } from "lucide-react";

export interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  maxLength: number;
}

export interface ChatInputHandle {
  focus: () => void;
}

/**
 * ChatInput renders a multi-line textarea with a Send button for submitting
 * chat messages to the knowledge base.
 *
 * - Enter submits (when trimmed input is non-empty), Shift+Enter inserts newline
 * - Both textarea and button disabled when `disabled=true`
 * - Shows character count indicator when approaching limit (> 1800 chars)
 * - Prevents input beyond maxLength characters
 * - Does not submit when empty/whitespace
 *
 * Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 9.6, 9.9
 */
export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ value, onChange, onSubmit, disabled, maxLength }, ref) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      focus: () => {
        textareaRef.current?.focus();
      },
    }));

    const canSubmit = value.trim().length > 0 && !disabled;

    const handleChange = useCallback(
      (e: ChangeEvent<HTMLTextAreaElement>) => {
        const newValue = e.target.value;
        // Enforce maxLength cap
        if (newValue.length <= maxLength) {
          onChange(newValue);
        } else {
          onChange(newValue.slice(0, maxLength));
        }
      },
      [onChange, maxLength]
    );

    const handleKeyDown = useCallback(
      (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          if (canSubmit) {
            onSubmit();
          }
        }
      },
      [canSubmit, onSubmit]
    );

    const handleSendClick = useCallback(() => {
      if (canSubmit) {
        onSubmit();
      }
    }, [canSubmit, onSubmit]);

    const showCharCount = value.length > 1800;

    return (
      <div className="flex items-end gap-2 p-3 border-t border-border bg-background">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents..."
            aria-label="Chat message input"
            disabled={disabled}
            rows={3}
            className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          />
          {showCharCount && (
            <span
              className={`absolute bottom-2 right-2 text-xs ${
                value.length >= maxLength
                  ? "text-destructive font-medium"
                  : "text-muted-foreground"
              }`}
              aria-live="polite"
            >
              {value.length}/{maxLength}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleSendClick}
          disabled={disabled || !canSubmit}
          aria-label="Send message"
          className="inline-flex items-center justify-center rounded-md h-10 w-10 bg-primary text-primary-foreground hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    );
  }
);
