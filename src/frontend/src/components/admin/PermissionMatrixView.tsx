import { Check, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RoleDetail } from "@/types/admin";

/**
 * Resource types displayed as rows in the permission matrix.
 * Matches the backend RESOURCE_TYPES constant.
 */
const RESOURCE_TYPES = [
  "documents",
  "workflows",
  "users",
  "audit_logs",
  "templates",
  "training",
  "signatures",
  "system_config",
] as const;

/**
 * Actions displayed as columns in the permission matrix.
 * Matches the backend ACTIONS constant.
 */
const ACTIONS = ["create", "read", "update", "delete", "approve"] as const;

/** Human-readable labels for resource types. */
const RESOURCE_LABELS: Record<string, string> = {
  documents: "Documents",
  workflows: "Workflows",
  users: "Users",
  audit_logs: "Audit Logs",
  templates: "Templates",
  training: "Training",
  signatures: "Signatures",
  system_config: "System Config",
};

/** Human-readable labels for actions. */
const ACTION_LABELS: Record<string, string> = {
  create: "Create",
  read: "Read",
  update: "Update",
  delete: "Delete",
  approve: "Approve",
};

interface PermissionMatrixViewProps {
  /** The role detail containing the permissions map. */
  role: RoleDetail;
}

/**
 * Grid showing resource types (rows) × actions (columns) with visual
 * indicators for granted/denied permissions.
 */
export function PermissionMatrixView({ role }: PermissionMatrixViewProps) {
  const permissions = role.permissions;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <table className="w-full text-sm" aria-label={`Permission matrix for ${role.name}`}>
        <thead>
          <tr className="border-b border-border bg-muted/50">
            <th className="text-left p-3 font-medium">Resource</th>
            {ACTIONS.map((action) => (
              <th
                key={action}
                className="text-center p-3 font-medium"
              >
                {ACTION_LABELS[action]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {RESOURCE_TYPES.map((resource) => {
            const grantedActions = permissions[resource] ?? [];
            return (
              <tr
                key={resource}
                className="border-b border-border last:border-b-0"
              >
                <td className="p-3 font-medium">
                  {RESOURCE_LABELS[resource]}
                </td>
                {ACTIONS.map((action) => {
                  const isGranted = grantedActions.includes(action);
                  return (
                    <td key={action} className="text-center p-3">
                      {isGranted ? (
                        <span
                          className={cn(
                            "inline-flex items-center justify-center h-6 w-6 rounded-full",
                            "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          )}
                          aria-label={`${ACTION_LABELS[action]} granted for ${RESOURCE_LABELS[resource]}`}
                        >
                          <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        </span>
                      ) : (
                        <span
                          className={cn(
                            "inline-flex items-center justify-center h-6 w-6 rounded-full",
                            "bg-muted text-muted-foreground/40"
                          )}
                          aria-label={`${ACTION_LABELS[action]} denied for ${RESOURCE_LABELS[resource]}`}
                        >
                          <X className="h-3.5 w-3.5" aria-hidden="true" />
                        </span>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
