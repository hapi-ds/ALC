import { Settings, Users, Shield, Database } from "lucide-react";

export function AdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Admin Dashboard</h2>
        <p className="text-sm text-muted-foreground">
          User management, role assignment, and system configuration
        </p>
      </div>

      {/* Admin sections */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border border-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-3">
            <Users className="h-5 w-5 text-primary" aria-hidden="true" />
            <h3 className="font-semibold">User Management</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Create, edit, and deactivate user accounts
          </p>
        </div>

        <div className="border border-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="h-5 w-5 text-primary" aria-hidden="true" />
            <h3 className="font-semibold">Role Assignment</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Assign roles and ABAC permissions to users
          </p>
        </div>

        <div className="border border-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-3">
            <Database className="h-5 w-5 text-primary" aria-hidden="true" />
            <h3 className="font-semibold">System Configuration</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Database, storage, and AI model settings
          </p>
        </div>

        <div className="border border-border rounded-lg p-6">
          <div className="flex items-center gap-2 mb-3">
            <Settings className="h-5 w-5 text-primary" aria-hidden="true" />
            <h3 className="font-semibold">Audit Configuration</h3>
          </div>
          <p className="text-sm text-muted-foreground">
            Configure audit trail retention and export settings
          </p>
        </div>
      </div>
    </div>
  );
}
