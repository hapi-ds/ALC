import { useEffect, useState } from "react";
import {
  Plus,
  Pencil,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  Shield,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminStore } from "@/stores/adminStore";
import { PermissionTemplateDialog } from "@/components/admin/PermissionTemplateDialog";
import type { PermissionTemplate } from "@/types/admin";

export function PermissionTemplateManagementPage() {
  const {
    permissionTemplates,
    isLoading,
    error,
    fetchPermissionTemplates,
    deletePermissionTemplate,
  } = useAdminStore();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<PermissionTemplate | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    fetchPermissionTemplates();
  }, [fetchPermissionTemplates]);

  function handleCreate() {
    setEditingTemplate(null);
    setDialogOpen(true);
  }

  function handleEdit(template: PermissionTemplate) {
    setEditingTemplate(template);
    setDialogOpen(true);
  }

  async function handleDelete(template: PermissionTemplate) {
    setDeleteError(null);
    const reason = window.prompt(
      "Please provide a reason for deleting this template (required for audit trail):"
    );
    if (!reason) return;

    try {
      await deletePermissionTemplate(template.id, reason);
      await fetchPermissionTemplates();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to delete template";
      setDeleteError(message);
    }
  }

  function handleDialogClose() {
    setDialogOpen(false);
    setEditingTemplate(null);
    fetchPermissionTemplates();
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Permission Templates</h2>
          <p className="text-sm text-muted-foreground">
            Manage document-type permission templates for role-based access
          </p>
        </div>
        <Button onClick={handleCreate}>
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          Create Template
        </Button>
      </div>

      {/* Error banner */}
      {(error || deleteError) && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{deleteError || error}</p>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div
          className="flex items-center justify-center py-8"
          aria-label="Loading permission templates"
        >
          <Loader2
            className="h-6 w-6 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
          <span className="sr-only">Loading permission templates</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && permissionTemplates.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FileText
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">No permission templates yet.</p>
          <p className="text-sm mt-1">
            Click &quot;Create Template&quot; to define access rules for a document type.
          </p>
        </div>
      )}

      {/* Template list */}
      {!isLoading && !error && permissionTemplates.length > 0 && (
        <div className="border border-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left p-3 font-medium">Name</th>
                <th className="text-left p-3 font-medium">Document Type</th>
                <th className="text-left p-3 font-medium">Active Documents</th>
                <th className="text-left p-3 font-medium">Status</th>
                <th className="text-right p-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {permissionTemplates.map((template) => {
                const hasActiveDocuments = template.active_document_count > 0;

                return (
                  <tr
                    key={template.id}
                    className="border-b border-border last:border-b-0 hover:bg-accent/50"
                  >
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <Shield
                          className="h-4 w-4 text-muted-foreground"
                          aria-hidden="true"
                        />
                        <span className="font-medium">{template.name}</span>
                      </div>
                    </td>
                    <td className="p-3">
                      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground">
                        {template.document_type}
                      </span>
                    </td>
                    <td className="p-3">{template.active_document_count}</td>
                    <td className="p-3">
                      {template.is_default && (
                        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold bg-primary/10 text-primary">
                          Default
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(template)}
                          aria-label={`Edit template ${template.name}`}
                          className="h-8 px-2"
                        >
                          <Pencil className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <div className="relative group">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(template)}
                            disabled={hasActiveDocuments}
                            aria-label={
                              hasActiveDocuments
                                ? `Cannot delete template ${template.name} — it has active documents`
                                : `Delete template ${template.name}`
                            }
                            className="h-8 px-2 text-destructive hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4" aria-hidden="true" />
                          </Button>
                          {hasActiveDocuments && (
                            <div
                              role="tooltip"
                              className="absolute bottom-full right-0 mb-2 hidden group-hover:block w-48 rounded-md bg-popover border border-border p-2 text-xs text-popover-foreground shadow-md z-10"
                            >
                              Cannot delete: this template is assigned to{" "}
                              {template.active_document_count} active{" "}
                              {template.active_document_count === 1
                                ? "document"
                                : "documents"}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Dialog */}
      <PermissionTemplateDialog
        open={dialogOpen}
        onOpenChange={handleDialogClose}
        template={editingTemplate}
      />
    </div>
  );
}
