/**
 * TrainingMaterialViewer
 *
 * Renders approved training materials in format-specific layouts:
 * - executive_summary → card with key points
 * - detailed_walkthrough → step-by-step accordion
 * - presentation_outline → slide-deck carousel
 * - safety_highlights → warning panel with distinct border and icon
 *
 * Requirements: 10.4
 */

import { useState } from "react";
import {
  FileText,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  AlertTriangle,
  BookOpen,
  Presentation,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TrainingMaterial } from "@/types/training-ecosystem";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrainingMaterialViewerProps {
  materials: TrainingMaterial[];
  isLoading: boolean;
  documentId: number | null;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Executive Summary — rendered as a card with key points. */
function ExecutiveSummaryCard({ material }: { material: TrainingMaterial }) {
  const content = material.content_data as {
    summary?: string;
    key_points?: string[];
    conclusion?: string;
  };

  return (
    <article
      className="rounded-lg border bg-card p-6 shadow-sm"
      aria-label="Executive summary"
    >
      <div className="flex items-center gap-2 mb-4">
        <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
        <h4 className="text-base font-semibold">Executive Summary</h4>
      </div>

      {content.summary && (
        <p className="text-sm text-foreground leading-relaxed mb-4">
          {content.summary}
        </p>
      )}

      {content.key_points && content.key_points.length > 0 && (
        <div className="space-y-2">
          <h5 className="text-sm font-medium text-muted-foreground">Key Points</h5>
          <ul className="list-disc list-inside space-y-1">
            {content.key_points.map((point, idx) => (
              <li key={idx} className="text-sm text-foreground">
                {point}
              </li>
            ))}
          </ul>
        </div>
      )}

      {content.conclusion && (
        <p className="mt-4 text-sm text-muted-foreground italic">
          {content.conclusion}
        </p>
      )}

      {/* Learning objectives */}
      {material.learning_objectives.length > 0 && (
        <div className="mt-4 pt-4 border-t">
          <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
            Learning Objectives
          </h5>
          <ul className="space-y-1">
            {material.learning_objectives.map((obj, idx) => (
              <li key={idx} className="text-xs text-muted-foreground">
                • {obj}
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-3 text-xs text-muted-foreground">
        Estimated duration: {material.estimated_duration_minutes} min
      </p>
    </article>
  );
}

/** Detailed Walkthrough — rendered as an accordion with expandable steps. */
function DetailedWalkthroughAccordion({ material }: { material: TrainingMaterial }) {
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const content = material.content_data as {
    steps?: Array<{ title: string; content: string; notes?: string }>;
    introduction?: string;
  };

  const toggleStep = (index: number) => {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  return (
    <article
      className="rounded-lg border bg-card shadow-sm"
      aria-label="Detailed walkthrough"
    >
      <div className="flex items-center gap-2 p-6 pb-4">
        <BookOpen className="h-5 w-5 text-primary" aria-hidden="true" />
        <h4 className="text-base font-semibold">Detailed Walkthrough</h4>
      </div>

      {content.introduction && (
        <p className="px-6 pb-4 text-sm text-muted-foreground">
          {content.introduction}
        </p>
      )}

      {content.steps && content.steps.length > 0 && (
        <div className="border-t divide-y">
          {content.steps.map((step, idx) => {
            const isExpanded = expandedSteps.has(idx);
            return (
              <div key={idx}>
                <button
                  type="button"
                  onClick={() => toggleStep(idx)}
                  aria-expanded={isExpanded}
                  aria-controls={`walkthrough-step-${idx}`}
                  className="flex w-full items-center gap-3 px-6 py-3 text-left hover:bg-muted/50 transition-colors"
                >
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  )}
                  <span className="text-sm font-medium">
                    Step {idx + 1}: {step.title}
                  </span>
                </button>
                {isExpanded && (
                  <div
                    id={`walkthrough-step-${idx}`}
                    className="px-6 pb-4 pl-13"
                  >
                    <p className="text-sm text-foreground leading-relaxed">
                      {step.content}
                    </p>
                    {step.notes && (
                      <p className="mt-2 text-xs text-muted-foreground italic">
                        Note: {step.notes}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <div className="px-6 py-3 border-t">
        <p className="text-xs text-muted-foreground">
          Estimated duration: {material.estimated_duration_minutes} min
        </p>
      </div>
    </article>
  );
}

/** Presentation Outline — rendered as a slide-deck carousel. */
function PresentationCarousel({ material }: { material: TrainingMaterial }) {
  const [currentSlide, setCurrentSlide] = useState(0);

  const content = material.content_data as {
    slides?: Array<{ title: string; content: string; speaker_notes?: string }>;
  };

  const slides = content.slides ?? [];
  const totalSlides = slides.length;

  const goNext = () => {
    if (currentSlide < totalSlides - 1) setCurrentSlide(currentSlide + 1);
  };

  const goPrev = () => {
    if (currentSlide > 0) setCurrentSlide(currentSlide - 1);
  };

  if (totalSlides === 0) {
    return (
      <div className="rounded-lg border p-6 text-center text-sm text-muted-foreground">
        No presentation slides available.
      </div>
    );
  }

  const slide = slides[currentSlide];

  return (
    <article
      className="rounded-lg border bg-card shadow-sm"
      aria-label="Presentation outline"
    >
      <div className="flex items-center gap-2 p-6 pb-4">
        <Presentation className="h-5 w-5 text-primary" aria-hidden="true" />
        <h4 className="text-base font-semibold">Presentation Outline</h4>
      </div>

      {/* Slide content */}
      <div className="px-6 pb-4" aria-live="polite" aria-atomic="true">
        <div className="rounded-lg border bg-muted/30 p-6 min-h-[160px]">
          <h5 className="text-sm font-semibold mb-3">{slide.title}</h5>
          <p className="text-sm text-foreground leading-relaxed">{slide.content}</p>
          {slide.speaker_notes && (
            <p className="mt-3 text-xs text-muted-foreground italic border-t pt-2">
              Speaker notes: {slide.speaker_notes}
            </p>
          )}
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between px-6 py-3 border-t">
        <Button
          variant="outline"
          size="sm"
          onClick={goPrev}
          disabled={currentSlide === 0}
          aria-label="Previous slide"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Previous
        </Button>
        <span className="text-xs text-muted-foreground">
          Slide {currentSlide + 1} of {totalSlides}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={goNext}
          disabled={currentSlide === totalSlides - 1}
          aria-label="Next slide"
        >
          Next
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </article>
  );
}

/** Safety Highlights — rendered as a warning panel with distinct border and icon. */
function SafetyHighlightsPanel({ material }: { material: TrainingMaterial }) {
  const content = material.content_data as {
    warnings?: string[];
    precautions?: string[];
    emergency_procedures?: string[];
    ppe_requirements?: string[];
  };

  return (
    <article
      className="rounded-lg border-2 border-amber-400 bg-amber-50 shadow-sm"
      aria-label="Safety highlights"
    >
      <div className="flex items-center gap-2 p-6 pb-4">
        <Shield className="h-5 w-5 text-amber-600" aria-hidden="true" />
        <h4 className="text-base font-semibold text-amber-900">
          Safety Highlights
        </h4>
      </div>

      <div className="px-6 pb-6 space-y-4">
        {content.warnings && content.warnings.length > 0 && (
          <div>
            <h5 className="text-sm font-medium text-amber-800 flex items-center gap-1.5 mb-2">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
              Warnings
            </h5>
            <ul className="space-y-1">
              {content.warnings.map((warning, idx) => (
                <li key={idx} className="text-sm text-amber-900 pl-5 relative before:content-['⚠'] before:absolute before:left-0">
                  {warning}
                </li>
              ))}
            </ul>
          </div>
        )}

        {content.precautions && content.precautions.length > 0 && (
          <div>
            <h5 className="text-sm font-medium text-amber-800 mb-2">Precautions</h5>
            <ul className="list-disc list-inside space-y-1">
              {content.precautions.map((item, idx) => (
                <li key={idx} className="text-sm text-amber-900">{item}</li>
              ))}
            </ul>
          </div>
        )}

        {content.emergency_procedures && content.emergency_procedures.length > 0 && (
          <div>
            <h5 className="text-sm font-medium text-amber-800 mb-2">Emergency Procedures</h5>
            <ol className="list-decimal list-inside space-y-1">
              {content.emergency_procedures.map((proc, idx) => (
                <li key={idx} className="text-sm text-amber-900">{proc}</li>
              ))}
            </ol>
          </div>
        )}

        {content.ppe_requirements && content.ppe_requirements.length > 0 && (
          <div>
            <h5 className="text-sm font-medium text-amber-800 mb-2">PPE Requirements</h5>
            <ul className="list-disc list-inside space-y-1">
              {content.ppe_requirements.map((ppe, idx) => (
                <li key={idx} className="text-sm text-amber-900">{ppe}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="px-6 py-3 border-t border-amber-300">
        <p className="text-xs text-amber-700">
          Estimated duration: {material.estimated_duration_minutes} min
        </p>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Loading Skeleton
// ---------------------------------------------------------------------------

function MaterialSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading materials">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="rounded-lg border p-6 space-y-3">
          <div className="h-5 w-1/3 rounded bg-muted animate-pulse" />
          <div className="h-4 w-full rounded bg-muted animate-pulse" />
          <div className="h-4 w-2/3 rounded bg-muted animate-pulse" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function TrainingMaterialViewer({
  materials,
  isLoading,
  documentId,
}: TrainingMaterialViewerProps) {
  // Filter to only approved materials for trainee view
  const approvedMaterials = materials.filter(
    (m) => m.status === "approved"
  );

  if (isLoading) {
    return (
      <section aria-label="Training materials" className="space-y-4">
        <h3 className="text-lg font-semibold">Training Materials</h3>
        <MaterialSkeleton />
      </section>
    );
  }

  if (!documentId) {
    return (
      <section aria-label="Training materials" className="space-y-4">
        <h3 className="text-lg font-semibold">Training Materials</h3>
        <div className="rounded-lg border border-dashed p-8 text-center">
          <BookOpen className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm text-muted-foreground">
            Select a training item from your schedule to view its materials.
          </p>
        </div>
      </section>
    );
  }

  if (approvedMaterials.length === 0) {
    return (
      <section aria-label="Training materials" className="space-y-4">
        <h3 className="text-lg font-semibold">Training Materials</h3>
        <div className="rounded-lg border border-dashed p-8 text-center">
          <FileText className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
          <p className="mt-2 text-sm text-muted-foreground">
            No approved materials available for this document yet.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section aria-label="Training materials" className="space-y-6">
      <h3 className="text-lg font-semibold">Training Materials</h3>

      {approvedMaterials.map((material) => {
        const type = material.material_type.toLowerCase();

        switch (type) {
          case "executive_summary":
            return <ExecutiveSummaryCard key={material.id} material={material} />;
          case "detailed_walkthrough":
            return <DetailedWalkthroughAccordion key={material.id} material={material} />;
          case "presentation_outline":
            return <PresentationCarousel key={material.id} material={material} />;
          case "safety_highlights":
            return <SafetyHighlightsPanel key={material.id} material={material} />;
          default:
            // Fallback: render as a generic card
            return (
              <article key={material.id} className="rounded-lg border p-6">
                <h4 className="text-sm font-semibold capitalize">
                  {material.material_type.replace(/_/g, " ")}
                </h4>
                <pre className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap">
                  {JSON.stringify(material.content_data, null, 2)}
                </pre>
              </article>
            );
        }
      })}
    </section>
  );
}
