/**
 * AdminRouteGuard — Route guard that verifies the user holds an Authorized_Role.
 *
 * Authorized roles: system_admin, doc_admin, it_admin.
 * Redirects unauthorized users to the home page.
 *
 * Requirements: 9.3
 */

import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";

/** Roles permitted read-only access to the audit trail */
const AUTHORIZED_ROLES = ["system_admin", "doc_admin", "it_admin"];

interface AdminRouteGuardProps {
  children: React.ReactNode;
}

export function AdminRouteGuard({ children }: AdminRouteGuardProps) {
  const user = useAuthStore((s) => s.user);

  const hasAuthorizedRole =
    user?.roles?.some((role) => AUTHORIZED_ROLES.includes(role)) ?? false;

  if (!hasAuthorizedRole) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
