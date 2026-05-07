import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, FileText, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTemplateListStore } from "@/stores/templateListStore";
import type { TemplateResponse } from "@/types/template";

export function TemplateListPage() {
  const { templates, isLoading, error, fetchTemplates } =
    useTemplateListStore();
  const navigate = useNavigate();

  // 200ms delay before showing loading indicator to avoid flash for fast responses
  const [showLoading, setShowLoading] = useState(false);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    if (isLoading) {
      timeoutId = setTimeout(() => {
        setShowLoading(true);
      }, 200);
    } else {
      setShowLoading(false);
    }

    return () => {
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    };
  }, [isLoading]);

  // Sort templates by document_uuid descending (most recently created first)
  const sortedTemplates = [...templates].sort((a, b) =>
    b.document_uuid.localeCompare(a.document_uuid)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Templates</h2>
          <p className="text-sm text-muted-foreground">
            Manage your document templates
          </p>
        </div>
        <Button onClick={() => navigate("/templates/new")}>
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          New Template
        </Button>
      </div>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{error}</p>
        </div>
      )}

      {/* Loading indicator (shown after 200ms delay) */}
      {showLoading && (
        <div
          className="flex items-center justify-center py-8"
          aria-label="Loading templates"
        >
          <Loader2
            className="h-6 w-6 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
          <span className="sr-only">Loading templates</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && templates.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileText
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">
            No templates have been created yet.
          </p>
          <p className="text-sm mt-1">
            Click "New Template" to create your first template.
          </p>
        </div>
      )}

      {/* Template list */}
      {!isLoading && !error && sortedTemplates.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left p-3 font-medium">Document UUID</th>
                <th className="text-left p-3 font-medium">Name</th>
                <th className="text-left p-3 font-medium">Status</th>
                <th className="text-left p-3 font-medium">Fields</th>
              </tr>
            </thead>
            <tbody>
              {sortedTemplates.map((template: TemplateResponse) => (
                <tr
                  key={template.id}
                  className="border-b border-border last:border-b-0 hover:bg-accent/50"
                >
                  <td className="p-3 font-mono text-xs">
                    {template.document_uuid}
                  </td>
                  <td className="p-3">{template.name}</td>
                  <td className="p-3">
                    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                      {template.status}
                    </span>
                  </td>
                  <td className="p-3">{template.fields.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
