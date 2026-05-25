/**
 * TemplateListPanel
 *
 * Paginated list of registered templates displayed as cards. Each card shows
 * the template name, document type target, status, and section count from
 * the analysis. Clicking a template loads its full analysis for preview.
 *
 * Requirements: 1.5, 1.6
 */

import { useEffect, useState, useCallback } from "react";
import { ChevronLeft, ChevronRight, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import { AnalysisPreview } from "./AnalysisPreview";

const PAGE_SIZE = 20;

// ---------------------------------------------------------------------------
// TemplateCard
// ---------------------------------------------------------------------------

interface TemplateCardProps {
  template: {
    id: number;
    template_name: string;
    document_type_target: string;
    status: string;
    template_analysis: { total_sections: number } | null;
  };
  isSelected: boolean;
  onSelect: (id: number) => void;
}

function TemplateCard({ template, isSelected, onSelect }: TemplateCardProps) {
  const sectionCount = template.template_analysis?.total_sections ?? 0;

  return (
    <div
      role="listitem"
      tabIndex={0}
      onClick={() => onSelect(template.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(template.id);
        }
      }}
      className={`rounded-lg border p-4 cursor-pointer transition-colors ${
        isSelected
          ? "border-primary bg-primary/5 ring-1 ring-primary"
          : "hover:bg-accent/50"
      }`}
      aria-selected={isSelected}
      aria-label={`Template: ${template.template_name}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-medium truncate">{template.template_name}</h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            {template.document_type_target}
          </p>
        </div>
        <span
          className={`text-xs px-2 py-0.5 rounded shrink-0 ${
            template.status === "ready"
              ? "bg-green-100 text-green-800"
              : template.status === "analyzing"
                ? "bg-amber-100 text-amber-800"
                : template.status === "failed"
                  ? "bg-red-100 text-red-800"
                  : "bg-muted text-muted-foreground"
          }`}
        >
          {template.status}
        </span>
      </div>
      <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <FileText className="h-3 w-3" aria-hidden="true" />
          {sectionCount} {sectionCount === 1 ? "section" : "sections"}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TemplateListPanel
// ---------------------------------------------------------------------------

export function TemplateListPanel() {
  const {
    templates,
    templatesTotal,
    selectedTemplate,
    templateAnalysis,
    isLoading,
    fetchTemplates,
    getTemplateAnalysis,
  } = useDocumentGeneratorStore();

  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Fetch templates on mount and when offset changes
  useEffect(() => {
    fetchTemplates(undefined, PAGE_SIZE, offset);
  }, [fetchTemplates, offset]);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.ceil(templatesTotal / PAGE_SIZE) || 1;
  const isPrevDisabled = offset === 0;
  const isNextDisabled = offset + PAGE_SIZE >= templatesTotal;

  const handlePrev = useCallback(() => {
    setOffset((prev) => Math.max(0, prev - PAGE_SIZE));
  }, []);

  const handleNext = useCallback(() => {
    setOffset((prev) => prev + PAGE_SIZE);
  }, []);

  const handleSelectTemplate = useCallback(
    (id: number) => {
      setSelectedId(id);
      getTemplateAnalysis(id);
    },
    [getTemplateAnalysis],
  );

  return (
    <section aria-labelledby="template-list-heading" className="space-y-4">
      <h3 id="template-list-heading" className="text-lg font-semibold">
        Registered Templates
      </h3>

      {/* Loading state */}
      {isLoading && templates.length === 0 && (
        <div className="flex items-center justify-center py-8" role="status" aria-label="Loading templates">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="ml-2 text-sm text-muted-foreground">Loading templates...</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && templates.length === 0 && (
        <div className="text-center py-8 text-muted-foreground">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
          <p className="text-sm">No templates registered yet.</p>
          <p className="text-xs mt-1">
            Use the form above to register a .docx file as a Master Template.
          </p>
        </div>
      )}

      {/* Template cards */}
      {templates.length > 0 && (
        <>
          <div
            role="list"
            aria-label="Template list"
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            {templates.map((template) => (
              <TemplateCard
                key={template.id}
                template={template}
                isSelected={selectedId === template.id}
                onSelect={handleSelectTemplate}
              />
            ))}
          </div>

          {/* Pagination */}
          <nav
            className="flex items-center justify-between py-2"
            role="navigation"
            aria-label="Template list pagination"
          >
            <p className="text-sm text-muted-foreground">
              {templatesTotal} {templatesTotal === 1 ? "template" : "templates"} total
            </p>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handlePrev}
                disabled={isPrevDisabled}
                aria-label="Previous page"
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleNext}
                disabled={isNextDisabled}
                aria-label="Next page"
              >
                Next
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </nav>
        </>
      )}

      {/* Analysis Preview */}
      {selectedId && selectedTemplate && templateAnalysis && (
        <div className="rounded-lg border p-4 mt-4">
          <h4 className="text-sm font-semibold mb-3">
            Analysis: {selectedTemplate.template_name}
          </h4>
          <AnalysisPreview analysis={templateAnalysis} />
        </div>
      )}
    </section>
  );
}
