import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { TrainingMaterialViewer } from "../../components/training/TrainingMaterialViewer";
import type { TrainingMaterial } from "../../types/training-ecosystem";

/**
 * Unit tests for TrainingMaterialViewer component.
 *
 * Validates: Requirements 10.4
 */

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeMaterial(
  type: string,
  contentData: Record<string, unknown>,
  overrides: Partial<TrainingMaterial> = {}
): TrainingMaterial {
  return {
    id: Math.floor(Math.random() * 1000),
    document_id: 10,
    document_version_id: 1,
    material_type: type,
    content_data: contentData,
    learning_objectives: ["Understand key concepts", "Apply procedures safely"],
    estimated_duration_minutes: 15,
    status: "approved",
    generated_by_agent_id: "educational-specialist",
    inference_duration_ms: 3200,
    reviewed_by: 5,
    reviewed_at: "2024-02-01T10:00:00Z",
    created_at: "2024-01-15T10:00:00Z",
    ...overrides,
  };
}

const executiveSummaryMaterial = makeMaterial("executive_summary", {
  summary: "This SOP covers chemical handling procedures for the laboratory.",
  key_points: [
    "Always wear PPE",
    "Follow spill cleanup procedures",
    "Report incidents immediately",
  ],
  conclusion: "Adherence to these procedures ensures workplace safety.",
});

const detailedWalkthroughMaterial = makeMaterial("detailed_walkthrough", {
  introduction: "This walkthrough covers the step-by-step process.",
  steps: [
    { title: "Preparation", content: "Gather all required materials.", notes: "Check inventory first" },
    { title: "Execution", content: "Follow the procedure carefully." },
    { title: "Cleanup", content: "Dispose of waste properly." },
  ],
});

const presentationMaterial = makeMaterial("presentation_outline", {
  slides: [
    { title: "Introduction", content: "Overview of the SOP", speaker_notes: "Welcome the audience" },
    { title: "Key Procedures", content: "Step-by-step guide" },
    { title: "Summary", content: "Recap of important points" },
  ],
});

const safetyHighlightsMaterial = makeMaterial("safety_highlights", {
  warnings: ["Do not mix chemicals without supervision", "Ensure ventilation is active"],
  precautions: ["Wear gloves at all times", "Keep fire extinguisher accessible"],
  emergency_procedures: ["Evacuate immediately if alarm sounds", "Call emergency services"],
  ppe_requirements: ["Nitrile gloves", "Safety goggles", "Lab coat"],
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingMaterialViewer", () => {
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  describe("loading state", () => {
    it("renders loading skeleton with aria-label", () => {
      render(
        <TrainingMaterialViewer materials={[]} isLoading={true} documentId={10} />
      );

      expect(screen.getByLabelText("Loading materials")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Empty states
  // -------------------------------------------------------------------------

  describe("empty states", () => {
    it("shows select document message when documentId is null", () => {
      render(
        <TrainingMaterialViewer materials={[]} isLoading={false} documentId={null} />
      );

      expect(
        screen.getByText(/select a training item from your schedule/i)
      ).toBeDefined();
    });

    it("shows no materials message when materials array is empty", () => {
      render(
        <TrainingMaterialViewer materials={[]} isLoading={false} documentId={10} />
      );

      expect(
        screen.getByText(/no approved materials available/i)
      ).toBeDefined();
    });

    it("filters out non-approved materials", () => {
      const pendingMaterial = makeMaterial(
        "executive_summary",
        { summary: "Pending content" },
        { status: "pending_review" }
      );

      render(
        <TrainingMaterialViewer
          materials={[pendingMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(
        screen.getByText(/no approved materials available/i)
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Executive Summary rendering
  // -------------------------------------------------------------------------

  describe("executive_summary", () => {
    it("renders as a card with summary text", () => {
      render(
        <TrainingMaterialViewer
          materials={[executiveSummaryMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByLabelText("Executive summary")).toBeDefined();
      expect(
        screen.getByText("This SOP covers chemical handling procedures for the laboratory.")
      ).toBeDefined();
    });

    it("renders key points as a list", () => {
      render(
        <TrainingMaterialViewer
          materials={[executiveSummaryMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText("Always wear PPE")).toBeDefined();
      expect(screen.getByText("Follow spill cleanup procedures")).toBeDefined();
      expect(screen.getByText("Report incidents immediately")).toBeDefined();
    });

    it("renders conclusion text", () => {
      render(
        <TrainingMaterialViewer
          materials={[executiveSummaryMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(
        screen.getByText("Adherence to these procedures ensures workplace safety.")
      ).toBeDefined();
    });

    it("renders learning objectives", () => {
      render(
        <TrainingMaterialViewer
          materials={[executiveSummaryMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText(/Understand key concepts/)).toBeDefined();
      expect(screen.getByText(/Apply procedures safely/)).toBeDefined();
    });

    it("shows estimated duration", () => {
      render(
        <TrainingMaterialViewer
          materials={[executiveSummaryMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText(/15 min/)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Detailed Walkthrough rendering
  // -------------------------------------------------------------------------

  describe("detailed_walkthrough", () => {
    it("renders as an accordion with step titles", () => {
      render(
        <TrainingMaterialViewer
          materials={[detailedWalkthroughMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByLabelText("Detailed walkthrough")).toBeDefined();
      expect(screen.getByText(/Step 1: Preparation/)).toBeDefined();
      expect(screen.getByText(/Step 2: Execution/)).toBeDefined();
      expect(screen.getByText(/Step 3: Cleanup/)).toBeDefined();
    });

    it("expands step content when clicked", () => {
      render(
        <TrainingMaterialViewer
          materials={[detailedWalkthroughMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      // Content should not be visible initially
      expect(screen.queryByText("Gather all required materials.")).toBeNull();

      // Click to expand
      const stepButton = screen.getByText(/Step 1: Preparation/);
      fireEvent.click(stepButton);

      expect(screen.getByText("Gather all required materials.")).toBeDefined();
    });

    it("shows introduction text", () => {
      render(
        <TrainingMaterialViewer
          materials={[detailedWalkthroughMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(
        screen.getByText("This walkthrough covers the step-by-step process.")
      ).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Presentation Outline rendering
  // -------------------------------------------------------------------------

  describe("presentation_outline", () => {
    it("renders as a carousel with slide content", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByLabelText("Presentation outline")).toBeDefined();
      // First slide should be visible
      expect(screen.getByText("Introduction")).toBeDefined();
      expect(screen.getByText("Overview of the SOP")).toBeDefined();
    });

    it("shows slide counter", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText("Slide 1 of 3")).toBeDefined();
    });

    it("navigates to next slide", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      const nextButton = screen.getByLabelText("Next slide");
      fireEvent.click(nextButton);

      expect(screen.getByText("Key Procedures")).toBeDefined();
      expect(screen.getByText("Slide 2 of 3")).toBeDefined();
    });

    it("navigates to previous slide", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      // Go to slide 2
      fireEvent.click(screen.getByLabelText("Next slide"));
      // Go back to slide 1
      fireEvent.click(screen.getByLabelText("Previous slide"));

      expect(screen.getByText("Introduction")).toBeDefined();
      expect(screen.getByText("Slide 1 of 3")).toBeDefined();
    });

    it("disables previous button on first slide", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      const prevButton = screen.getByLabelText("Previous slide");
      expect(prevButton.hasAttribute("disabled")).toBe(true);
    });

    it("disables next button on last slide", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      // Navigate to last slide
      fireEvent.click(screen.getByLabelText("Next slide"));
      fireEvent.click(screen.getByLabelText("Next slide"));

      const nextButton = screen.getByLabelText("Next slide");
      expect(nextButton.hasAttribute("disabled")).toBe(true);
    });

    it("shows speaker notes when available", () => {
      render(
        <TrainingMaterialViewer
          materials={[presentationMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText(/Welcome the audience/)).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Safety Highlights rendering
  // -------------------------------------------------------------------------

  describe("safety_highlights", () => {
    it("renders as a warning panel with distinct styling", () => {
      render(
        <TrainingMaterialViewer
          materials={[safetyHighlightsMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByLabelText("Safety highlights")).toBeDefined();
    });

    it("renders warnings list", () => {
      render(
        <TrainingMaterialViewer
          materials={[safetyHighlightsMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText("Warnings")).toBeDefined();
      expect(screen.getByText("Do not mix chemicals without supervision")).toBeDefined();
      expect(screen.getByText("Ensure ventilation is active")).toBeDefined();
    });

    it("renders precautions list", () => {
      render(
        <TrainingMaterialViewer
          materials={[safetyHighlightsMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText("Precautions")).toBeDefined();
      expect(screen.getByText("Wear gloves at all times")).toBeDefined();
    });

    it("renders emergency procedures list", () => {
      render(
        <TrainingMaterialViewer
          materials={[safetyHighlightsMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText("Emergency Procedures")).toBeDefined();
      expect(screen.getByText("Evacuate immediately if alarm sounds")).toBeDefined();
    });

    it("renders PPE requirements list", () => {
      render(
        <TrainingMaterialViewer
          materials={[safetyHighlightsMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByText("PPE Requirements")).toBeDefined();
      expect(screen.getByText("Nitrile gloves")).toBeDefined();
      expect(screen.getByText("Safety goggles")).toBeDefined();
      expect(screen.getByText("Lab coat")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Multiple material types
  // -------------------------------------------------------------------------

  describe("multiple materials", () => {
    it("renders all approved material types", () => {
      render(
        <TrainingMaterialViewer
          materials={[
            executiveSummaryMaterial,
            detailedWalkthroughMaterial,
            presentationMaterial,
            safetyHighlightsMaterial,
          ]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByLabelText("Executive summary")).toBeDefined();
      expect(screen.getByLabelText("Detailed walkthrough")).toBeDefined();
      expect(screen.getByLabelText("Presentation outline")).toBeDefined();
      expect(screen.getByLabelText("Safety highlights")).toBeDefined();
    });
  });

  // -------------------------------------------------------------------------
  // Accessibility
  // -------------------------------------------------------------------------

  describe("accessibility", () => {
    it("has section with aria-label 'Training materials'", () => {
      render(
        <TrainingMaterialViewer
          materials={[executiveSummaryMaterial]}
          isLoading={false}
          documentId={10}
        />
      );

      expect(screen.getByLabelText("Training materials")).toBeDefined();
    });
  });
});
