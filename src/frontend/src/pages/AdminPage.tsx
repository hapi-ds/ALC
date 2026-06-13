import { Link } from "react-router-dom";
import {
  Settings,
  Users,
  Shield,
  Database,
  ScrollText,
  FileKey,
  Brain,
} from "lucide-react";

const adminSections = [
  {
    to: "/admin/users",
    icon: Users,
    title: "User Management",
    description: "Create, edit, and deactivate user accounts",
  },
  {
    to: "/admin/roles",
    icon: Shield,
    title: "Role Management",
    description: "Assign roles and manage group permissions",
  },
  {
    to: "/admin/permission-templates",
    icon: FileKey,
    title: "Permission Templates",
    description: "Define standard access sets for document types",
  },
  {
    to: "/admin/system-config",
    icon: Database,
    title: "System Configuration",
    description: "AI hardware, storage quotas, and service health",
  },
  {
    to: "/admin/audit-trail",
    icon: ScrollText,
    title: "Audit Trail",
    description: "Searchable audit log — who, what, when, why",
  },
  {
    to: "/admin/ai-risk-framework",
    icon: Brain,
    title: "AI Risk Framework",
    description: "Risk tiering, HITL controls, and compliance profiles",
  },
];

export function AdminPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Admin Dashboard</h2>
        <p className="text-sm text-muted-foreground">
          User management, role assignment, and system configuration
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {adminSections.map((section) => (
          <Link
            key={section.to}
            to={section.to}
            className="border border-border rounded-lg p-6 hover:bg-accent/50 hover:border-primary/30 transition-colors group"
          >
            <div className="flex items-center gap-2 mb-3">
              <section.icon
                className="h-5 w-5 text-primary group-hover:text-primary"
                aria-hidden="true"
              />
              <h3 className="font-semibold">{section.title}</h3>
            </div>
            <p className="text-sm text-muted-foreground">
              {section.description}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
