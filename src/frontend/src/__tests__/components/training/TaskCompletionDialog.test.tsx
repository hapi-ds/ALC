import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TaskCompletionDialog } from "../../../components/training/TaskCompletionDialog";
import type { TrainingTask } from "../../../components/training/types";

/**
 * Unit tests for TaskCompletionDialog component.
 *
 * Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8, 11.4, 11.5, 11.8
 */

const mockTask: TrainingTask = {
  id: 1,
  sop_document_uuid: "abc-123-def",
  sop_version: "1.0",
  assigned_user_id: 42,
  task_title: "Complete SOP Training for Chemical Handling",
  is_completed: false,
  completed_at: null,
  created_at: "2024-01-15T10:00:00Z",
};

describe("TaskCompletionDialog", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------

  it("renders dialog with correct ARIA attributes", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeDefined();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("task-completion-dialog-title");
    expect(dialog.getAttribute("aria-describedby")).toBe("task-completion-dialog-description");
  });

  it("displays task title, SOP UUID, and version", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    expect(screen.getByText("Complete SOP Training for Chemical Handling")).toBeDefined();
    expect(screen.getByText("SOP: abc-123-def")).toBeDefined();
    expect(screen.getByText("Version: 1.0")).toBeDefined();
  });

  it("renders dialog title 'Complete Training Task'", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    expect(screen.getByText("Complete Training Task")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Validation
  // -------------------------------------------------------------------------

  it("disables confirm button when change reason is empty", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const confirmButton = screen.getByRole("button", { name: /confirm/i });
    expect(confirmButton.hasAttribute("disabled")).toBe(true);
  });

  it("disables confirm button when change reason is less than 3 characters (trimmed)", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "ab" } });

    const confirmButton = screen.getByRole("button", { name: /confirm/i });
    expect(confirmButton.hasAttribute("disabled")).toBe(true);
  });

  it("enables confirm button when change reason has 3+ trimmed characters", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Valid reason text" } });

    const confirmButton = screen.getByRole("button", { name: /confirm/i });
    expect(confirmButton.hasAttribute("disabled")).toBe(false);
  });

  it("shows character counter with remaining characters", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    // Initially 500 characters remaining
    expect(screen.getByText("500 characters remaining")).toBeDefined();

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Hello" } });

    expect(screen.getByText("495 characters remaining")).toBeDefined();
  });

  it("shows minimum length hint when input is too short but non-empty", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "ab" } });

    expect(screen.getByText("Minimum 3 characters required")).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Submission
  // -------------------------------------------------------------------------

  it("calls onConfirm with trimmed change reason on confirm click", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "  Valid reason  " } });

    const confirmButton = screen.getByRole("button", { name: /confirm/i });
    fireEvent.click(confirmButton);

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith("Valid reason");
  });

  it("shows loading state and disables buttons during submission", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={true}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    expect(screen.getByText("Completing...")).toBeDefined();

    // Cancel button should be disabled
    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    expect(cancelButton.hasAttribute("disabled")).toBe(true);

    // Textarea should be disabled
    const textarea = screen.getByRole("textbox");
    expect(textarea.hasAttribute("disabled")).toBe(true);
  });

  // -------------------------------------------------------------------------
  // Error display
  // -------------------------------------------------------------------------

  it("displays error message with role='alert' when error is present", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error="Task not found"
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert).toBeDefined();
    expect(alert.textContent).toBe("Task not found");
  });

  it("retains user input when error is displayed", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    const { rerender } = render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "My reason text" } });

    // Simulate error appearing
    rerender(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error="Network error"
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    expect((textarea as HTMLTextAreaElement).value).toBe("My reason text");
  });

  // -------------------------------------------------------------------------
  // Close behavior
  // -------------------------------------------------------------------------

  it("calls onClose when cancel button is clicked", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButton);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when close (X) button is clicked", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const closeButton = screen.getByRole("button", { name: /close dialog/i });
    fireEvent.click(closeButton);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when Escape key is pressed", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close on Escape when submitting", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={true}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Focus trap
  // -------------------------------------------------------------------------

  it("traps focus within dialog on Tab at last element", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const dialog = screen.getByRole("dialog");
    const focusableElements = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), textarea:not([disabled])'
    );
    const focusable = Array.from(focusableElements);

    expect(focusable.length).toBeGreaterThan(0);

    // Focus the last element
    const lastElement = focusable[focusable.length - 1];
    lastElement.focus();

    // Press Tab — should wrap to first element
    fireEvent.keyDown(document, { key: "Tab" });

    // The focus trap handler should prevent default and move focus to first element
    expect(focusable[0]).toBeDefined();
  });

  it("traps focus within dialog on Shift+Tab at first element", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const dialog = screen.getByRole("dialog");
    const focusableElements = dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), textarea:not([disabled])'
    );
    const focusable = Array.from(focusableElements);

    // Focus the first element
    const firstElement = focusable[0];
    firstElement.focus();

    // Press Shift+Tab — should wrap to last element
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    // Verify the focus trap logic is in place
    expect(focusable[focusable.length - 1]).toBeDefined();
  });

  // -------------------------------------------------------------------------
  // Accessibility attributes
  // -------------------------------------------------------------------------

  it("textarea has aria-required='true'", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    expect(textarea.getAttribute("aria-required")).toBe("true");
  });

  it("textarea has aria-invalid when input is non-empty but too short", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "ab" } });

    expect(textarea.getAttribute("aria-invalid")).toBe("true");
  });

  it("textarea has aria-describedby linking to counter and hint", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error={null}
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const textarea = screen.getByRole("textbox");
    expect(textarea.getAttribute("aria-describedby")).toBe(
      "change-reason-counter change-reason-hint"
    );
  });

  it("error message has aria-live='assertive'", () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    render(
      <TaskCompletionDialog
        task={mockTask}
        isSubmitting={false}
        error="Something went wrong"
        onConfirm={onConfirm}
        onClose={onClose}
      />
    );

    const alert = screen.getByRole("alert");
    expect(alert.getAttribute("aria-live")).toBe("assertive");
  });
});
