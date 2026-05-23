import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { TypingIndicator } from "@/components/knowledge/TypingIndicator";

/**
 * Unit tests for TypingIndicator component.
 *
 * Validates: Requirements 6.1
 */

describe("TypingIndicator", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders 3 animated dot spans with animate-bounce class", () => {
    const { container } = render(<TypingIndicator />);

    const dots = container.querySelectorAll("span.animate-bounce");
    expect(dots.length).toBe(3);
  });

  it("renders dots inside an assistant-style bubble with bg-gray-100 and rounded-lg", () => {
    const { container } = render(<TypingIndicator />);

    const bubble = container.querySelector(".bg-gray-100.rounded-lg");
    expect(bubble).not.toBeNull();
  });

  it("has aria-live='polite' region with 'Assistant is typing' text", () => {
    render(<TypingIndicator />);

    const liveRegion = screen.getByText("Assistant is typing");
    expect(liveRegion).not.toBeNull();
    expect(liveRegion.getAttribute("aria-live")).toBe("polite");
  });

  it("hides the aria-live text visually with sr-only class", () => {
    render(<TypingIndicator />);

    const liveRegion = screen.getByText("Assistant is typing");
    expect(liveRegion.classList.contains("sr-only")).toBe(true);
  });

  it("renders dots container with aria-hidden='true'", () => {
    const { container } = render(<TypingIndicator />);

    const dotsContainer = container.querySelector("[aria-hidden='true']");
    expect(dotsContainer).not.toBeNull();
    // The dots container should hold the 3 animated dots
    const dots = dotsContainer!.querySelectorAll("span.animate-bounce");
    expect(dots.length).toBe(3);
  });

  it("renders left-aligned with justify-start", () => {
    const { container } = render(<TypingIndicator />);

    const wrapper = container.firstElementChild;
    expect(wrapper?.classList.contains("justify-start")).toBe(true);
  });
});
