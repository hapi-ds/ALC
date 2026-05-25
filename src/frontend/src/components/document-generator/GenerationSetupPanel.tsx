/**
 * GenerationSetupPanel
 *
 * Form component for starting a new template-based document generation job.
 * Provides inputs for template selection, title, generation instructions,
 * reference document IDs, and output folder path.
 *
 * Requirements: 2.1, 7.1
 */

import { useState, useEffect, useCallback } from "react";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";
import { Button } from "@/components/ui/button";
import type { GenerateFromTemplateRequest } from "@/types/documentGenerator";

// ---------------------------------------------------------------------------
// GenerationSetupPanel
// ---------------------------------------------------------------------------

export function GenerationSetupPanel() {
  const {
    templates,
    fetchTemplates,
    startGeneration,
    isGenerating,
    error,
  } = useDocumentGeneratorStore();

  const [templateId, setTemplateId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [referenceDocIds, setReferenceDocIds] = useState("");
  const [outputFolderPath, setOutputFolderPath] = useState("");
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Fetch templates on mount for the selector
  useEffect(() => {
    fetchTemplates(undefined, 100, 0);
  }, [fetchTemplates]);

  const validate = useCallback((): boolean => {
    const errors: Record<string, string> = {};

    if (!templateId) {
      errors.templateId = "Please select a template";
    }
    if (!title.trim()) {
      errors.title = "Title is required";
    } else if (title.length > 500) {
      errors.title = "Title must be 500 characters or fewer";
    }
    if (!instructions.trim()) {
      errors.instructions = "Generation instructions are required";
    } else if (instructions.length > 10000) {
      errors.instructions = "Instructions must be 10,000 characters or fewer";
    }
    if (!outputFolderPath.trim()) {
      errors.outputFolderPath = "Output folder path is required";
    } else if (outputFolderPath.length > 1000) {
      errors.outputFolderPath = "Output folder path must be 1,000 characters or fewer";
    }

    // Validate reference document IDs format (comma-separated integers)
    if (referenceDocIds.trim()) {
      const ids = referenceDocIds.split(",").map((s) => s.trim());
      const invalidIds = ids.filter((id) => id && (isNaN(Number(id)) || !Number.isInteger(Number(id)) || Number(id) <= 0));
      if (invalidIds.length > 0) {
        errors.referenceDocIds = "Reference document IDs must be positive integers separated by commas";
      } else if (ids.filter((id) => id).length > 20) {
        errors.referenceDocIds = "Maximum 20 reference documents allowed";
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  }, [templateId, title, instructions, outputFolderPath, referenceDocIds]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) return;

    const parsedRefIds = referenceDocIds.trim()
      ? referenceDocIds
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s)
          .map(Number)
      : undefined;

    const request: GenerateFromTemplateRequest = {
      template_id: Number(templateId),
      title: title.trim(),
      generation_instructions: instructions.trim(),
      output_folder_path: outputFolderPath.trim(),
      ...(parsedRefIds && parsedRefIds.length > 0 && { reference_document_ids: parsedRefIds }),
    };

    await startGeneration(request, "Template-based document generation initiated");
  };

  return (
    <form
      onSubmit={handleSubmit}
      aria-label="Generation setup form"
      className="space-y-5"
    >
      {/* Template Selector */}
      <div className="space-y-1.5">
        <label
          htmlFor="gen-template-select"
          className="block text-sm font-medium"
        >
          Template <span aria-hidden="true" className="text-destructive">*</span>
        </label>
        <select
          id="gen-template-select"
          value={templateId}
          onChange={(e) => setTemplateId(e.target.value)}
          aria-required="true"
          aria-invalid={!!validationErrors.templateId}
          aria-describedby={validationErrors.templateId ? "gen-template-error" : undefined}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        >
          <option value="">Select a template…</option>
          {templates.map((t) => (
            <option key={t.id} value={String(t.id)}>
              {t.template_name} ({t.document_type_target})
            </option>
          ))}
        </select>
        {validationErrors.templateId && (
          <p id="gen-template-error" role="alert" className="text-xs text-destructive">
            {validationErrors.templateId}
          </p>
        )}
      </div>

      {/* Title Input */}
      <div className="space-y-1.5">
        <label htmlFor="gen-title" className="block text-sm font-medium">
          Document Title <span aria-hidden="true" className="text-destructive">*</span>
        </label>
        <input
          id="gen-title"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g., User Requirements Specification — Module X"
          maxLength={500}
          aria-required="true"
          aria-invalid={!!validationErrors.title}
          aria-describedby={validationErrors.title ? "gen-title-error" : undefined}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
        {validationErrors.title && (
          <p id="gen-title-error" role="alert" className="text-xs text-destructive">
            {validationErrors.title}
          </p>
        )}
      </div>

      {/* Generation Instructions Textarea */}
      <div className="space-y-1.5">
        <label htmlFor="gen-instructions" className="block text-sm font-medium">
          Generation Instructions <span aria-hidden="true" className="text-destructive">*</span>
        </label>
        <textarea
          id="gen-instructions"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          placeholder="Describe what the AI should generate. Include context about the document's purpose, scope, and any specific requirements…"
          rows={5}
          maxLength={10000}
          aria-required="true"
          aria-invalid={!!validationErrors.instructions}
          aria-describedby="gen-instructions-hint gen-instructions-error"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring resize-y"
        />
        <p id="gen-instructions-hint" className="text-xs text-muted-foreground">
          {instructions.length.toLocaleString()} / 10,000 characters
        </p>
        {validationErrors.instructions && (
          <p id="gen-instructions-error" role="alert" className="text-xs text-destructive">
            {validationErrors.instructions}
          </p>
        )}
      </div>

      {/* Reference Document IDs */}
      <div className="space-y-1.5">
        <label htmlFor="gen-ref-docs" className="block text-sm font-medium">
          Reference Document IDs
        </label>
        <input
          id="gen-ref-docs"
          type="text"
          value={referenceDocIds}
          onChange={(e) => setReferenceDocIds(e.target.value)}
          placeholder="e.g., 12, 34, 56 (comma-separated, max 20)"
          aria-describedby="gen-ref-docs-hint gen-ref-docs-error"
          aria-invalid={!!validationErrors.referenceDocIds}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <p id="gen-ref-docs-hint" className="text-xs text-muted-foreground">
          Optional. Comma-separated document IDs to use as primary source material.
        </p>
        {validationErrors.referenceDocIds && (
          <p id="gen-ref-docs-error" role="alert" className="text-xs text-destructive">
            {validationErrors.referenceDocIds}
          </p>
        )}
      </div>

      {/* Output Folder Path */}
      <div className="space-y-1.5">
        <label htmlFor="gen-output-path" className="block text-sm font-medium">
          Output Folder Path <span aria-hidden="true" className="text-destructive">*</span>
        </label>
        <input
          id="gen-output-path"
          type="text"
          value={outputFolderPath}
          onChange={(e) => setOutputFolderPath(e.target.value)}
          placeholder="e.g., /documents/generated/urs"
          maxLength={1000}
          aria-required="true"
          aria-invalid={!!validationErrors.outputFolderPath}
          aria-describedby={validationErrors.outputFolderPath ? "gen-output-error" : undefined}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
        {validationErrors.outputFolderPath && (
          <p id="gen-output-error" role="alert" className="text-xs text-destructive">
            {validationErrors.outputFolderPath}
          </p>
        )}
      </div>

      {/* Error display from store */}
      {error && (
        <div role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 p-3">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      )}

      {/* Generate Button */}
      <Button
        type="submit"
        disabled={isGenerating}
        aria-busy={isGenerating}
        className="w-full"
      >
        {isGenerating ? "Starting Generation…" : "Generate Document"}
      </Button>
    </form>
  );
}
