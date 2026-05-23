import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { ChatInput } from "@/components/knowledge/ChatInput";

/**
 * Unit tests for ChatInput component.
 *
 * Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 9.6, 9.9
 */

function renderChatInput(overrides: Partial<{
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  maxLength: number;
}> = {}) {
  const props = {
    value: overrides.value ?? "",
    onChange: overrides.onChange ?? vi.fn(),
    onSubmit: overrides.onSubmit ?? vi.fn(),
    disabled: overrides.disabled ?? false,
    maxLength: overrides.maxLength ?? 2000,
  };
  return { ...render(<ChatInput {...props} />), props };
}

describe("ChatInput", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders textarea with placeholder and aria-label", () => {
    renderChatInput();

    const textarea = screen.getByRole("textbox");
    expect(textarea).not.toBeNull();
    expect(textarea.getAttribute("placeholder")).toBe(
      "Ask a question about your documents..."
    );
    expect(textarea.getAttribute("aria-label")).toBe("Chat message input");
  });

  it("renders Send button with aria-label", () => {
    renderChatInput();

    const button = screen.getByRole("button", { name: "Send message" });
    expect(button).not.toBeNull();
    expect(button.getAttribute("aria-label")).toBe("Send message");
  });

  it("submits on Enter when non-empty", () => {
    const onSubmit = vi.fn();
    renderChatInput({ value: "Hello world", onSubmit });

    const textarea = screen.getByRole("textbox");
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("inserts newline on Shift+Enter (does not submit)", () => {
    const onSubmit = vi.fn();
    renderChatInput({ value: "Hello world", onSubmit });

    const textarea = screen.getByRole("textbox");
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables both elements when disabled=true", () => {
    renderChatInput({ disabled: true, value: "Some text" });

    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    const button = screen.getByRole("button", { name: "Send message" }) as HTMLButtonElement;

    expect(textarea.disabled).toBe(true);
    expect(button.disabled).toBe(true);
  });

  it("shows character count near limit (> 1800 chars)", () => {
    const longValue = "a".repeat(1850);
    renderChatInput({ value: longValue, maxLength: 2000 });

    // Should display "1850/2000"
    expect(screen.getByText("1850/2000")).not.toBeNull();
  });

  it("does not show character count when below 1800 chars", () => {
    renderChatInput({ value: "short text", maxLength: 2000 });

    expect(screen.queryByText(/\/2000/)).toBeNull();
  });

  it("prevents input beyond 2000 characters", () => {
    const onChange = vi.fn();
    renderChatInput({ value: "", onChange, maxLength: 2000 });

    const textarea = screen.getByRole("textbox");

    // Simulate typing a value that exceeds maxLength
    const overLimitValue = "x".repeat(2100);
    fireEvent.change(textarea, { target: { value: overLimitValue } });

    // onChange should be called with the value capped at maxLength
    expect(onChange).toHaveBeenCalledWith("x".repeat(2000));
  });

  it("does not submit when empty/whitespace", () => {
    const onSubmit = vi.fn();

    // Test with empty string
    renderChatInput({ value: "", onSubmit });
    const textarea = screen.getByRole("textbox");
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });
    expect(onSubmit).not.toHaveBeenCalled();

    cleanup();

    // Test with whitespace-only string
    renderChatInput({ value: "   \n\t  ", onSubmit });
    const textarea2 = screen.getByRole("textbox");
    fireEvent.keyDown(textarea2, { key: "Enter", shiftKey: false });
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
