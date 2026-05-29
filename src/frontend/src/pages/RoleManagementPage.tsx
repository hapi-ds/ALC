import { useEffect, useState } from "react";
import { Shield, Loader2, AlertCircle, Lock, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAdminStore } from "@/stores/adminStore";
import { PermissionMatrixView } from "@/components/admin/PermissionMatrixView";
import type { RoleWithCount } from "@/types/admin";

/** Human-readable labels for role names. */
const ROLE_LABELS: Record<string, string> = {
  system_admin: "System Admin",
  doc_admin: "Document Admin",
  it_admin: "IT Admin",
  member: "Member",
  viewer: "Viewer",
};

export function RoleManagementPage() {
  const {
    roles,
    currentRole,
    isLoading,
    error,
    fetchRoles,
    fetchRoleDetail,
  } = useAdminStore();

  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(null);

  // 200ms delay before showing loading indicator to avoid flash
  const [showLoading, setShowLoading] = useState(false);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

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

  const handleRoleSelect = (role: RoleWithCount) => {
    setSelectedRoleId(role.id);
    fetchRoleDetail(role.id);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">Role Management</h2>
        <p className="text-sm text-muted-foreground">
          View roles and their permission assignments
        </p>
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

      {/* Loading indicator */}
      {showLoading && !roles.length && (
        <div
          className="flex items-center justify-center py-8"
          aria-label="Loading roles"
        >
          <Loader2
            className="h-6 w-6 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
          <span className="sr-only">Loading roles</span>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && roles.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <Shield
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">No roles found.</p>
          <p className="text-sm mt-1">
            Roles are provisioned automatically when a company is created.
          </p>
        </div>
      )}

      {/* Role list and permission matrix */}
      {roles.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Role list */}
          <div className="lg:col-span-1 space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground mb-3">
              Available Roles
            </h3>
            {roles.map((role) => (
              <button
                key={role.id}
                type="button"
                onClick={() => handleRoleSelect(role)}
                className={cn(
                  "w-full text-left border rounded-lg p-4 transition-colors",
                  "hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  selectedRoleId === role.id
                    ? "border-primary bg-primary/5"
                    : "border-border"
                )}
                aria-pressed={selectedRoleId === role.id}
                aria-label={`Select role ${ROLE_LABELS[role.name] ?? role.name}`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Shield
                      className="h-4 w-4 text-primary"
                      aria-hidden="true"
                    />
                    <span className="font-medium">
                      {ROLE_LABELS[role.name] ?? role.name}
                    </span>
                  </div>
                  {role.is_system && (
                    <span
                      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400"
                      title="System-defined role (non-editable)"
                    >
                      <Lock className="h-3 w-3" aria-hidden="true" />
                      System
                    </span>
                  )}
                </div>
                {role.description && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {role.description}
                  </p>
                )}
                <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
                  <Users className="h-3 w-3" aria-hidden="true" />
                  <span>
                    {role.user_count} {role.user_count === 1 ? "user" : "users"}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* Permission matrix */}
          <div className="lg:col-span-2">
            {selectedRoleId && currentRole ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Permissions for{" "}
                    <span className="text-foreground font-semibold">
                      {ROLE_LABELS[currentRole.name] ?? currentRole.name}
                    </span>
                  </h3>
                  {currentRole.is_system && (
                    <span className="text-xs text-muted-foreground italic">
                      System-defined — permissions cannot be modified
                    </span>
                  )}
                </div>
                <PermissionMatrixView role={currentRole} />
              </div>
            ) : (
              <div className="border border-border rounded-lg p-8 text-center text-muted-foreground h-full flex flex-col items-center justify-center">
                <Shield
                  className="h-10 w-10 mb-3 opacity-30"
                  aria-hidden="true"
                />
                <p className="text-sm">
                  Select a role to view its permission matrix
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
