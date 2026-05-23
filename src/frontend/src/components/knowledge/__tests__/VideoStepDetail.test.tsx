/**
 * Unit tests for VideoStepDetail component.
 *
 * Tests cover:
 * - Frame thumbnails rendering for step's timestamp range
 * - Placeholder display when no frames available
 * - Full description text display
 * - Audio transcript text display when available
 * - No transcript message when audio is unavailable
 * - Close button functionality
 * - Timestamp formatting in header
 *
 * Requirements: 11.4
 */

import { describe, it, expect, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { VideoStepDetail } from "../VideoStepDetail";
import type { VideoStepInfo } from "@/types/videoAlignment";

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function createStep(overrides: Partial<VideoStepInfo> = {}): VideoStepInfo {
  return {
    description: "Operator puts on protective gloves and adjusts safety goggles",
    timestamp_start: 10,
    timestamp_end: 25,
    audio_transcript: "Now we put on our protective gloves before handling the chemicals.",
    frame_thumbnails: [
      "/frames/frame_00010.png",
      "/frames/frame_00015.png",
      "/frames/frame_00020.png",
    ],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("VideoStepDetail", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // 1. Frame thumbnails
  // -------------------------------------------------------------------------

  describe("Frame Thumbnails", () => {
    it("renders frame thumbnails when available", () => {
      const step = createStep();
      render(<VideoStepDetail step={step} />);

      const images = screen.getAllByRole("img");
      expect(images).toHaveLength(3);
      expect(images[0]).toHaveAttribute("src", "/frames/frame_00010.png");
      expect(images[1]).toHaveAttribute("src", "/frames/frame_00015.png");
      expect(images[2]).toHaveAttribute("src", "/frames/frame_00020.png");
    });

    it("renders alt text with frame index and timestamp", () => {
      const step = createStep({ timestamp_start: 65 });
      render(<VideoStepDetail step={step} />);

      const images = screen.getAllByRole("img");
      expect(images[0]).toHaveAttribute("alt", "Frame 1 at 1:05");
    });

    it("shows placeholder when no frame thumbnails available", () => {
      const step = createStep({ frame_thumbnails: [] });
      render(<VideoStepDetail step={step} />);

      expect(screen.getByText("No frame thumbnails available")).toBeInTheDocument();
      expect(screen.queryAllByRole("img")).toHaveLength(0);
    });

    it("displays Frame Thumbnails label", () => {
      const step = createStep();
      render(<VideoStepDetail step={step} />);

      expect(screen.getByText("Frame Thumbnails")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 2. Full description
  // -------------------------------------------------------------------------

  describe("Description", () => {
    it("renders the full step description", () => {
      const step = createStep({
        description: "Operator calibrates the pH meter using buffer solution",
      });
      render(<VideoStepDetail step={step} />);

      expect(
        screen.getByText("Operator calibrates the pH meter using buffer solution")
      ).toBeInTheDocument();
    });

    it("displays Description label", () => {
      const step = createStep();
      render(<VideoStepDetail step={step} />);

      expect(screen.getByText("Description")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 3. Audio transcript
  // -------------------------------------------------------------------------

  describe("Audio Transcript", () => {
    it("renders audio transcript text when available", () => {
      const step = createStep({
        audio_transcript: "Please ensure all safety equipment is in place.",
      });
      render(<VideoStepDetail step={step} />);

      expect(
        screen.getByText("Please ensure all safety equipment is in place.")
      ).toBeInTheDocument();
    });

    it("shows no transcript message when audio_transcript is null", () => {
      const step = createStep({ audio_transcript: null });
      render(<VideoStepDetail step={step} />);

      expect(
        screen.getByText("No audio transcript available for this step.")
      ).toBeInTheDocument();
    });

    it("shows no transcript message when audio_transcript is undefined", () => {
      const step = createStep({ audio_transcript: undefined });
      render(<VideoStepDetail step={step} />);

      expect(
        screen.getByText("No audio transcript available for this step.")
      ).toBeInTheDocument();
    });

    it("shows no transcript message when audio_transcript is empty string", () => {
      const step = createStep({ audio_transcript: "   " });
      render(<VideoStepDetail step={step} />);

      expect(
        screen.getByText("No audio transcript available for this step.")
      ).toBeInTheDocument();
    });

    it("displays Audio Transcript label", () => {
      const step = createStep();
      render(<VideoStepDetail step={step} />);

      expect(screen.getByText("Audio Transcript")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 4. Header and timestamp
  // -------------------------------------------------------------------------

  describe("Header", () => {
    it("displays formatted timestamp range in header", () => {
      const step = createStep({ timestamp_start: 65, timestamp_end: 130 });
      render(<VideoStepDetail step={step} />);

      // 65s = 1:05, 130s = 2:10
      expect(screen.getByText("Step Detail (1:05 – 2:10)")).toBeInTheDocument();
    });

    it("formats zero timestamps correctly", () => {
      const step = createStep({ timestamp_start: 0, timestamp_end: 5 });
      render(<VideoStepDetail step={step} />);

      expect(screen.getByText("Step Detail (0:00 – 0:05)")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 5. Close button
  // -------------------------------------------------------------------------

  describe("Close Button", () => {
    it("renders close button when onClose is provided", () => {
      const onClose = vi.fn();
      const step = createStep();
      render(<VideoStepDetail step={step} onClose={onClose} />);

      const closeBtn = screen.getByLabelText("Close step detail");
      expect(closeBtn).toBeInTheDocument();
    });

    it("calls onClose when close button is clicked", () => {
      const onClose = vi.fn();
      const step = createStep();
      render(<VideoStepDetail step={step} onClose={onClose} />);

      fireEvent.click(screen.getByLabelText("Close step detail"));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("does not render close button when onClose is not provided", () => {
      const step = createStep();
      render(<VideoStepDetail step={step} />);

      expect(screen.queryByLabelText("Close step detail")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 6. Accessibility
  // -------------------------------------------------------------------------

  describe("Accessibility", () => {
    it("has proper aria-label on the container", () => {
      const step = createStep();
      render(<VideoStepDetail step={step} />);

      expect(screen.getByLabelText("Video step detail")).toBeInTheDocument();
    });
  });
});
