import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useForm, type SubmitHandler } from "react-hook-form";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminStore } from "@/stores/adminStore";
import type { PermissionTemplate, RoleActionMapping } from "@/types/admin";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PermissionTemplateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** If provided, the dialog is in edit mode. Otherwise, create mode. */
  template: PermissionTemplate | null;
}

interface FormValues {
  name: string;
  description: string;
  document_type: string;
  changeReason: string;
  // Role permissions stored as individual booleans
  system_admin_read: boolean;
  system_admin_write: boolean;
  system_admin_approve: boolean;
  doc_admin_read: boolean;
  doc_admin_write: boolean;
  doc_admin_approve: boolean;
  it_admin_read: boolean;
  it_admin_write: boolean;
  it_admin_approve: boolean;
  member_read: boolean;
  member_write: boolean;
  member_approve: boolean;
  viewer_read: boolean;
  viewer_write: boolean;
  viewer_approve: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ROLES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"] as const;
const ACTIONS = ["read", "write", "approve"] as const;

const ROLE_LABELS: Record<string, string> = {
  system_admin: "System Admin",
  doc_admin: "Doc Admin",
  it_admin: "IT Admin",
  member: "Member",
  viewer: "Viewer",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildRolePermissions(values: FormValues): RoleActionMapping[] {
  const mappings: RoleActionMapping[] = [];

  for (const role of ROLES) {
    const actions: ("read" | "write" | "approve")[] = [];
    for (const action of ACTIONS) {
      const key = `${role}_${action}` as keyof FormValues;
      if (values[key]) {
        actions.push(action);
      }
    }
    if (actions.length > 0) {
      mappings.push({ role, actions });
    }
  }

  return mappings;
}

function getDefaultValues(template: PermissionTemplate | null): FormValues {
  const defaults: FormValues = {
    name: template?.name ?? "",
    description: template?.description ?? "",
    document_type: template?.document_type ?? "",
    changeReason: "",
    system_admin_read: false,
    system_admin_write: false,
    system_admin_approve: false,
    doc_admin_read: false,
    doc_admin_write: false,
    doc_admin_approve: false,
    it_admin_read: false,
    it_admin_write: false,
    it_admin_approve: false,
    member_read: false,
    member_write: false,
    member_approve: false,
    viewer_read: false,
    viewer_write: false,
    viewer_approve: false,
  };

  if (template?.role_permissions) {
    for (const role of ROLES) {
      const actions = template.role_permissions[role] ?? [];
      for (const action of ACTIONS) {
        const key = `${role}_${action}` as keyof FormValues;
        (defaults[key] as boolean) = actions.includes(action);
      }
    }
  }

  return defaults;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PermissionTemplateDialog({
  open,
  onOpenChange,
  template,
}: PermissionTemplateDialogProps) {
  const { createPermissionTemplate, updatePermissionTemplate, isLoading } =
    useAdminStore();

  const isEditMode = template !== null;

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: getDefaultValues(template),
  });

  // Reset form when dialog opens or template changes
  useEffect(() => {
    if (open) {
      reset(getDefaultValues(template));
    }
  }, [open, template, reset]);

  // Escape key handling
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onOpenChange(false);
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  const onSubmit: SubmitHandler<FormValues> = async (values) => {
    const rolePermissions = buildRolePermissions(values);

    if (rolePermissions.length === 0) {
      return;
    }

    try {
      if (isEditMode) {
        await updatePermissionTemplate(
          template.id,
          {
            name: values.name,
            description: values.description || null,
            role_permissions: rolePermissions,
          },
          values.changeReason
        );
      } else {
        await createPermissionTemplate(
          {
            name: values.name,
            description: values.description || null,
            document_type: values.document_type,
            role_permissions: rolePermissions,
          },
          values.changeReason
        );
      }
      onOpenChange(false);
    } catch {
      // Error is handled by the store and displayed via the page error banner
    }
  };

  if (!open) return null;

  const inputClassName = (hasError: boolean) =>
    `flex h-9 w-full rounded-md border bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
      hasError ? "border-destructive" : "border-input"
    }`;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onOpenChange(false);
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="permission-template-dialog-title"
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2
            id="permission-template-dialog-title"
            className="text-lg font-semibold text-foreground"
          >
            {isEditMode ? "Edit Permission Template" : "Create Permission Template"}
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} noValidate>
          {/* Name */}
          <div className="mb-4">
            <label
              htmlFor="template-name"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Name <span aria-hidden="true">*</span>
            </label>
            <input
              id="template-name"
              type="text"
              disabled={isLoading}
              aria-invalid={errors.name ? "true" : undefined}
              aria-describedby={errors.name ? "template-name-error" : undefined}
              className={inputClassName(!!errors.name)}
              placeholder="e.g., Internal SOP Template"
              {...register("name", {
                required: "Template name is required",
                minLength: { value: 1, message: "Name is required" },
                maxLength: { value: 200, message: "Name must not exceed 200 characters" },
              })}
            />
            {errors.name && (
              <p id="template-name-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.name.message}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="mb-4">
            <label
              htmlFor="template-description"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Description{" "}
              <span className="text-muted-foreground font-normal">(optional)</span>
            </label>
            <textarea
              id="template-description"
              rows={2}
              disabled={isLoading}
              className="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-none"
              placeholder="Describe the purpose of this template"
              {...register("description", {
                maxLength: { value: 1000, message: "Description must not exceed 1000 characters" },
              })}
            />
            {errors.description && (
              <p className="mt-1 text-sm text-destructive" role="alert">
                {errors.description.message}
              </p>
            )}
          </div>

          {/* Document Type */}
          <div className="mb-4">
            <label
              htmlFor="template-document-type"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Document Type <span aria-hidden="true">*</span>
            </label>
            <input
              id="template-document-type"
              type="text"
              disabled={isLoading || isEditMode}
              aria-invalid={errors.document_type ? "true" : undefined}
              aria-describedby={errors.document_type ? "template-document-type-error" : undefined}
              className={inputClassName(!!errors.document_type)}
              placeholder="e.g., SOP, Protocol, Report"
              {...register("document_type", {
                required: "Document type is required",
                minLength: { value: 1, message: "Document type is required" },
                maxLength: { value: 100, message: "Document type must not exceed 100 characters" },
              })}
            />
            {isEditMode && (
              <p className="mt-1 text-xs text-muted-foreground">
                Document type cannot be changed after creation.
              </p>
            )}
            {errors.document_type && (
              <p id="template-document-type-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.document_type.message}
              </p>
            )}
          </div>

          {/* Role Permissions Matrix */}
          <div className="mb-4">
            <label className="mb-1.5 block text-sm font-medium text-foreground">
              Role Permissions <span aria-hidden="true">*</span>
            </label>
            <p className="mb-2 text-xs text-muted-foreground">
              Select which actions each role can perform on documents of this type.
            </p>
            <div className="border border-border rounded-md overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="text-left p-2 font-medium">Role</th>
                    <th className="text-center p-2 font-medium">Read</th>
                    <th className="text-center p-2 font-medium">Write</th>
                    <th className="text-center p-2 font-medium">Approve</th>
                  </tr>
                </thead>
                <tbody>
                  {ROLES.map((role) => (
                    <tr
                      key={role}
                      className="border-b border-border last:border-b-0"
                    >
                      <td className="p-2 font-medium">{ROLE_LABELS[role]}</td>
                      {ACTIONS.map((action) => {
                        const fieldName = `${role}_${action}` as keyof FormValues;
                        return (
                          <td key={action} className="p-2 text-center">
                            <input
                              type="checkbox"
                              disabled={isLoading}
                              aria-label={`${ROLE_LABELS[role]} can ${action}`}
                              className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
                              {...register(fieldName)}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Change Reason */}
          <div className="mb-6">
            <label
              htmlFor="template-change-reason"
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Change Reason <span aria-hidden="true">*</span>
            </label>
            <input
              id="template-change-reason"
              type="text"
              disabled={isLoading}
              aria-invalid={errors.changeReason ? "true" : undefined}
              aria-describedby={errors.changeReason ? "template-change-reason-error" : undefined}
              className={inputClassName(!!errors.changeReason)}
              placeholder="Reason for this change (required for audit trail)"
              {...register("changeReason", {
                required: "Change reason is required for audit compliance",
              })}
            />
            {errors.changeReason && (
              <p id="template-change-reason-error" className="mt-1 text-sm text-destructive" role="alert">
                {errors.changeReason.message}
              </p>
            )}
          </div>

          {/* Action buttons */}
          <div className="flex gap-3">
            <Button type="submit" className="flex-1" disabled={isLoading}>
              {isLoading && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isLoading
                ? isEditMode
                  ? "Saving…"
                  : "Creating…"
                : isEditMode
                  ? "Save Changes"
                  : "Create Template"}
            </Button>
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
}
