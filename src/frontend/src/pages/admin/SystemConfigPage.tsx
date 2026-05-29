/**
 * SystemConfigPage
 *
 * Admin page for system configuration management. Provides tabbed navigation
 * between AI Settings, Storage, Backups, Health, Services, and History sections.
 *
 * Route: /admin/system-config
 * Requirements: 2.1–2.7, 5.1–5.6, 7.4, 8.4, 9.2–9.4, 10.3, 11.1–11.6, 12.1–12.5, 13.3, 14.2, 14.4
 */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Cpu, HardDrive, Database, Activity, Server, History } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { BackupScheduleForm } from "@/components/admin/BackupScheduleForm";
import { BackupHistoryTable } from "@/components/admin/BackupHistoryTable";
import { BackupTriggerButton } from "@/components/admin/BackupTriggerButton";
import { StorageUsageList } from "@/components/admin/StorageUsageList";
import { QuotaEditForm } from "@/components/admin/QuotaEditForm";
import { HealthStatusGrid } from "@/components/admin/HealthStatusGrid";
import { HealthConfigForm } from "@/components/admin/HealthConfigForm";
import { ServiceInfoList } from "@/components/admin/ServiceInfoList";
import { ResourceUtilizationCharts } from "@/components/admin/ResourceUtilizationCharts";
import { SnapshotHistoryList } from "@/components/admin/SnapshotHistoryList";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { CompanyStorageUsage } from "@/types/systemConfig";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TabId = "ai-settings" | "storage" | "backups" | "health" | "services" | "history";

interface TabDefinition {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: TabDefinition[] = [
  { id: "ai-settings", label: "AI Settings", icon: Cpu },
  { id: "storage", label: "Storage", icon: HardDrive },
  { id: "backups", label: "Backups", icon: Database },
  { id: "health", label: "Health", icon: Activity },
  { id: "services", label: "Services", icon: Server },
  { id: "history", label: "History", icon: History },
];

const VALID_TAB_IDS = new Set<string>(TABS.map((t) => t.id));

// ---------------------------------------------------------------------------
// SystemConfigPage
// ---------------------------------------------------------------------------

export function SystemConfigPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const defaultTab: TabId = tabParam && VALID_TAB_IDS.has(tabParam) ? (tabParam as TabId) : "ai-settings";

  // Storage tab state: selected company for quota editing
  const [selectedCompany, setSelectedCompany] = useState<CompanyStorageUsage | null>(null);
  const { storageUsage } = useSystemConfigStore();

  const handleTabChange = (value: string) => {
    setSearchParams({ tab: value });
  };

  return (
    <main role="main" aria-label="System Configuration" className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold">System Configuration</h2>
        <p className="text-sm text-muted-foreground">
          Manage AI hardware, storage quotas, backups, health monitoring, and services
        </p>
      </div>

      {/* Tabbed layout */}
      <Tabs defaultValue={defaultTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full grid-cols-6">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <TabsTrigger key={tab.id} value={tab.id} className="gap-1.5">
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">{tab.label}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* AI Settings Tab */}
        <TabsContent value="ai-settings">
          <div className="rounded-lg border border-border p-6">
            <h3 className="text-lg font-semibold mb-2">AI Hardware Settings</h3>
            <p className="text-sm text-muted-foreground">
              Configure AI model paths, GPU allocation, and inference mode. Manage vLLM service status.
            </p>
          </div>
        </TabsContent>

        {/* Storage Tab */}
        <TabsContent value="storage">
          <div className="rounded-lg border border-border p-6 space-y-6">
            <div>
              <h3 className="text-lg font-semibold mb-1">Storage &amp; Quotas</h3>
              <p className="text-sm text-muted-foreground">
                View per-company storage usage and configure quota limits and alert thresholds.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {/* Usage list */}
              <div>
                <h4 className="text-sm font-semibold text-foreground mb-3">Usage by Company</h4>
                <StorageUsageList />
                {/* Company selection for quota editing */}
                {storageUsage.length > 0 && (
                  <div className="mt-4">
                    <label
                      htmlFor="select-company-quota"
                      className="block text-sm font-medium text-foreground mb-1"
                    >
                      Select company to edit quota
                    </label>
                    <select
                      id="select-company-quota"
                      value={selectedCompany?.company_id ?? ""}
                      onChange={(e) => {
                        const id = Number(e.target.value);
                        const found = storageUsage.find((c) => c.company_id === id) ?? null;
                        setSelectedCompany(found);
                      }}
                      className="block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                      <option value="">— Select a company —</option>
                      {storageUsage.map((c) => (
                        <option key={c.company_id} value={c.company_id}>
                          {c.company_name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Quota edit form */}
              <div>
                <h4 className="text-sm font-semibold text-foreground mb-3">Quota Configuration</h4>
                <QuotaEditForm
                  company={selectedCompany}
                  onClose={() => setSelectedCompany(null)}
                />
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Backups Tab */}
        <TabsContent value="backups">
          <div className="rounded-lg border border-border p-6 space-y-8">
            <div>
              <h3 className="text-lg font-semibold mb-2">Backup Configuration</h3>
              <p className="text-sm text-muted-foreground mb-6">
                Manage backup schedules, retention policies, trigger manual backups, and view backup history.
              </p>
              <BackupTriggerButton />
            </div>
            <BackupScheduleForm />
            <BackupHistoryTable />
          </div>
        </TabsContent>

        {/* Health Tab */}
        <TabsContent value="health">
          <div className="rounded-lg border border-border p-6 space-y-8">
            <div>
              <h3 className="text-lg font-semibold mb-1">System Health</h3>
              <p className="text-sm text-muted-foreground">
                Monitor real-time health status of infrastructure services and configure health check parameters.
              </p>
            </div>

            <HealthStatusGrid />
            <HealthConfigForm />
          </div>
        </TabsContent>

        {/* Services Tab */}
        <TabsContent value="services">
          <div className="rounded-lg border border-border p-6 space-y-8">
            <div>
              <h3 className="text-lg font-semibold mb-1">Service Status</h3>
              <p className="text-sm text-muted-foreground">
                View Docker service information, resource utilization, and container metrics.
              </p>
            </div>
            <ServiceInfoList />
            <ResourceUtilizationCharts />
          </div>
        </TabsContent>

        {/* History Tab */}
        <TabsContent value="history">
          <div className="rounded-lg border border-border p-6 space-y-4">
            <div>
              <h3 className="text-lg font-semibold mb-1">Configuration History</h3>
              <p className="text-sm text-muted-foreground">
                View configuration change history and rollback to previous states.
              </p>
            </div>
            <SnapshotHistoryList />
          </div>
        </TabsContent>
      </Tabs>
    </main>
  );
}
