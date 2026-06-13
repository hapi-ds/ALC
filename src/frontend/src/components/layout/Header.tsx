import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { LogOut, User, Building2, ChevronDown } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { apiClient } from "@/lib/apiClient";

interface CompanyOption {
  company_id: number;
  company_slug: string;
  role: string;
  display_name?: string;
}

export function Header() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const activeCompanyId = useAuthStore((s) => s.activeCompanyId);
  const activeCompanySlug = useAuthStore((s) => s.activeCompanySlug);

  const [companies, setCompanies] = useState<CompanyOption[]>([]);
  const [isCompanyMenuOpen, setIsCompanyMenuOpen] = useState(false);

  useEffect(() => {
    async function fetchCompanies() {
      try {
        const me = await apiClient.get<{
          companies: CompanyOption[];
        }>("/api/v1/auth/me");
        // Also fetch company display names
        try {
          const companyList = await apiClient.get<Array<{ id: number; slug: string; display_name: string }>>("/api/companies");
          const displayNames = new Map(companyList.map((c) => [c.id, c.display_name]));
          setCompanies(
            (me.companies ?? []).map((c) => ({
              ...c,
              display_name: displayNames.get(c.company_id) ?? c.company_slug,
            }))
          );
        } catch {
          setCompanies(me.companies ?? []);
        }
      } catch {
        // Non-critical
      }
    }
    fetchCompanies();
  }, []);

  const handleCompanySwitch = (companyId: number, companySlug: string) => {
    useAuthStore.setState({
      activeCompanyId: companyId,
      activeCompanySlug: companySlug,
    });
    localStorage.setItem("alcoabase_active_company_id", String(companyId));
    localStorage.setItem("alcoabase_active_company_slug", companySlug);
    setIsCompanyMenuOpen(false);
    // Reload to refresh all data with new company context
    window.location.reload();
  };

  const activeCompanyLabel =
    companies.find((c) => c.company_id === activeCompanyId)?.display_name ??
    activeCompanySlug ??
    "No company";

  return (
    <header className="h-14 border-b border-border bg-background flex items-center justify-between px-6">
      <div className="text-sm text-muted-foreground">
        AlcoaBase — Local GxP Document & Knowledge Management
      </div>
      <div className="flex items-center gap-3">
        {/* Company Switcher */}
        {companies.length > 1 && (
          <div className="relative">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsCompanyMenuOpen(!isCompanyMenuOpen)}
              aria-label="Switch company"
              aria-expanded={isCompanyMenuOpen}
            >
              <Building2 className="h-4 w-4 mr-1" aria-hidden="true" />
              <span className="max-w-[150px] truncate">{activeCompanyLabel}</span>
              <ChevronDown className="h-3 w-3 ml-1" aria-hidden="true" />
            </Button>
            {isCompanyMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-56 bg-popover border border-border rounded-md shadow-md z-50">
                <ul className="py-1" role="menu">
                  {companies.map((c) => (
                    <li key={c.company_id} role="menuitem">
                      <button
                        className={`w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors ${
                          c.company_id === activeCompanyId
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-foreground"
                        }`}
                        onClick={() =>
                          handleCompanySwitch(c.company_id, c.company_slug)
                        }
                      >
                        {c.display_name ?? c.company_slug}
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({c.role})
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* User info */}
        <Button variant="ghost" size="sm" aria-label="User profile">
          <User className="h-4 w-4" aria-hidden="true" />
          <span className="ml-1">{user?.full_name ?? user?.username ?? "User"}</span>
        </Button>

        {/* Logout */}
        <Button
          variant="ghost"
          size="icon"
          aria-label="Sign out"
          onClick={() => void logout()}
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </header>
  );
}
