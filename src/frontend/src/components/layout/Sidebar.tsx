import { NavLink } from "react-router-dom";
import {
  FileText,
  FolderOpen,
  Layout,
  GitBranch,
  GraduationCap,
  Sparkles,
  Search,
  MessageSquare,
  Bot,
  ShieldCheck,
  PenTool,
  ClipboardCheck,
  ClipboardList,
  Settings,
  BarChart3,
  Activity,
  GitMerge,
  Users,
  Shield,
  FileKey,
  ScrollText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";

const navItems = [
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/folders", label: "Virtual Folders", icon: FolderOpen },
  { to: "/templates", label: "Templates", icon: Layout },
  { to: "/reports", label: "Reports", icon: ClipboardList },
  { to: "/workflows", label: "Workflows", icon: GitBranch },
  { to: "/training", label: "Training", icon: GraduationCap },
  { to: "/training/ecosystem", label: "AI Training", icon: Sparkles },
  { to: "/search", label: "Search", icon: Search },
  { to: "/knowledge", label: "Knowledge Chat", icon: MessageSquare },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/validation", label: "Validation", icon: ShieldCheck },
  { to: "/signatures", label: "Signatures", icon: PenTool },
  { to: "/review", label: "Document Review", icon: ClipboardCheck },
  { to: "/reviews", label: "Audit Reviews", icon: BarChart3 },
  { to: "/impact-analysis", label: "Impact Analysis", icon: Activity },
  { to: "/traceability", label: "Traceability", icon: GitMerge },
  { to: "/admin", label: "Admin", icon: Settings },
];

const adminNavItems = [
  { to: "/admin/users", label: "User Management", icon: Users },
  { to: "/admin/roles", label: "Role Management", icon: Shield },
  { to: "/admin/permission-templates", label: "Permission Templates", icon: FileKey },
  { to: "/admin/audit-trail", label: "Audit Trail", icon: ScrollText },
];

/** Roles that grant access to the Administration section */
const ADMIN_ROLES = ["system_admin", "doc_admin", "it_admin", "admin"];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const showAdminSection =
    user?.roles?.some((role) => ADMIN_ROLES.includes(role)) ?? false;

  return (
    <aside className="w-64 border-r border-border bg-muted/30 flex flex-col h-full">
      <div className="p-4 border-b border-border">
        <h1 className="text-xl font-bold text-foreground">AlcoaBase</h1>
        <p className="text-xs text-muted-foreground mt-1">
          GxP Document Management
        </p>
      </div>
      <nav className="flex-1 overflow-y-auto p-2" aria-label="Main navigation">
        <ul className="space-y-1">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )
                }
              >
                <item.icon className="h-4 w-4" aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>

        {showAdminSection && (
          <>
            <div className="mt-4 mb-2 px-3">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Administration
              </h2>
            </div>
            <ul className="space-y-1">
              {adminNavItems.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                        isActive
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                      )
                    }
                  >
                    <item.icon className="h-4 w-4" aria-hidden="true" />
                    <span>{item.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>
    </aside>
  );
}
