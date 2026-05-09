import { useEffect, useMemo } from "react";
import { Loader2, AlertCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTemplateListStore } from "@/stores/templateListStore";
import type { TemplateResponse } from "@/types/template";

export interface TemplateSelectorProps {
  onSelect: (template: TemplateResponse) => void;
  disabled?: boolean;
  preSelectedUuid?: string;
}

/**
 * Template selector for report creation.
 * Fetches templates via the template list store (GET /api/templates)
 * and displays only ReadOnly ones with name, Document_UUID, and field count.
 */
export function TemplateSelector({
  onSelect,
  disabled = false,
  preSelectedUuid,
}: TemplateSelectorProps) {
  const { templates, isLoading, error, fetchTemplates, versionSummaries } =
    useTemplateListStore();

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  // Filter to ReadOnly templates only
  const readOnlyTemplates = useMemo(
    () => templates.filter((t) => t.status === "ReadOnly"),
    [templates]
  );

  // Auto-select if preSelectedUuid is provided
  useEffect(() => {
    if (preSelectedUuid && readOnlyTemplates.length > 0) {
      const match = readOnlyTemplates.find(
        (t) => t.document_uuid === preSelectedUuid
      );
      if (match) {
        onSelect(match);
      }
    }
  }, [preSelectedUuid, readOnlyTemplates, onSelect]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8" role="status">
        <Loader2 className="h-5 w-5 animate-spin text-gray-400" aria-hidden="true" />
        <span className="ml-2 text-sm text-gray-500">Loading templates…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 text-red-600 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-sm text-red-700">{error}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={fetchTemplates}
            >
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (readOnlyTemplates.length === 0) {
    return (
      <div className="rounded-md border border-gray-200 bg-gray-50 p-6 text-center">
        <FileText className="h-8 w-8 mx-auto mb-2 text-gray-400" aria-hidden="true" />
        <p className="text-sm text-gray-600">
          No templates are available for report creation.
        </p>
        <p className="text-xs text-gray-500 mt-1">
          Templates must be in ReadOnly status to create reports.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-gray-700">Select a template</p>
      <div className="grid gap-2">
        {readOnlyTemplates.map((template) => {
          const summary = versionSummaries[template.document_uuid];
          const fieldCount = summary?.activeVersionFieldCount ?? template.fields.length;

          return (
            <button
              key={template.id}
              type="button"
              onClick={() => onSelect(template)}
              disabled={disabled}
              className="flex items-center justify-between rounded-md border border-gray-200 bg-white px-4 py-3 text-left transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {template.name}
                </p>
                <p className="text-xs text-gray-500">
                  {template.document_uuid}
                </p>
              </div>
              <span className="ml-3 shrink-0 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {fieldCount} field{fieldCount !== 1 ? "s" : ""}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
