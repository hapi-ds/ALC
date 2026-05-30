/**
 * AIRiskFrameworkPage
 *
 * Admin page for the AI Risk & Compliance Framework. Provides tabbed navigation
 * between Dashboard, Task Types, Risk Profile, HITL Queue, and Operation Logs.
 *
 * Route: /admin/ai-risk-framework
 * Restricted to system_admin and doc_admin roles.
 *
 * Requirements: 7.1, 7.7
 */

import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  LayoutDashboard,
  ListChecks,
  ShieldCheck,
  ClipboardCheck,
  ScrollText,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Loader2,
  AlertCircle,
  AlertTriangle,
  Clock,
  ShieldOff,
  Activity,
  User,
  Plus,
  History,
  Trash2,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/stores/authStore";
import { useRiskFrameworkStore } from "@/stores/riskFrameworkStore";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { getTaskType, getProfileHistory } from "@/lib/riskFrameworkApi";
import type {
  AITaskTypeDetailResponse,
  TierDefinitionResponse,
  OperationLogParams,
  CompanyRiskProfileResponse,
  PaginatedResult,
  RiskTierOverrideEntry,
  HITLCheckpointResponse,
} from "@/lib/riskFrameworkApi";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TabId = "dashboard" | "task-types" | "risk-profile" | "hitl-queue" | "operation-logs";

interface TabDefinition {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: TabDefinition[] = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "task-types", label: "Task Types", icon: ListChecks },
  { id: "risk-profile", label: "Risk Profile", icon: ShieldCheck },
  { id: "hitl-queue", label: "HITL Queue", icon: ClipboardCheck },
  { id: "operation-logs", label: "Operation Logs", icon: ScrollText },
];

const VALID_TAB_IDS = new Set<string>(TABS.map((t) => t.id));

/** Roles permitted to access this page */
const AUTHORIZED_ROLES = ["system_admin", "doc_admin"];

// ---------------------------------------------------------------------------
// Risk Matrix Configuration
// ---------------------------------------------------------------------------

/**
 * Default task type positions in the 3x3 risk matrix.
 * Impact (vertical): 0=Low, 1=Medium, 2=High
 * Likelihood (horizontal): 0=Low, 1=Medium, 2=High
 * Tier determines color coding.
 */
interface RiskMatrixEntry {
  taskTypeId: string;
  displayName: string;
  tier: "high" | "medium" | "low";
  impact: 0 | 1 | 2;
  likelihood: 0 | 1 | 2;
}

const DEFAULT_RISK_MATRIX_ENTRIES: RiskMatrixEntry[] = [
  { taskTypeId: "document_generation", displayName: "Doc Gen", tier: "high", impact: 2, likelihood: 2 },
  { taskTypeId: "multi_agent_audit", displayName: "Multi-Agent Audit", tier: "high", impact: 2, likelihood: 1 },
  { taskTypeId: "training_content_generation", displayName: "Training Gen", tier: "high", impact: 2, likelihood: 1 },
  { taskTypeId: "change_impact_analysis", displayName: "Change Impact", tier: "medium", impact: 1, likelihood: 1 },
  { taskTypeId: "traceability_gap_discovery", displayName: "Traceability", tier: "medium", impact: 1, likelihood: 0 },
  { taskTypeId: "rag_knowledge_query", displayName: "RAG Query", tier: "low", impact: 0, likelihood: 2 },
  { taskTypeId: "document_search", displayName: "Doc Search", tier: "low", impact: 0, likelihood: 2 },
  { taskTypeId: "template_analysis", displayName: "Template Analysis", tier: "low", impact: 0, likelihood: 0 },
];

const TIER_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-800 border-red-200",
  medium: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-green-100 text-green-800 border-green-200",
};

// ---------------------------------------------------------------------------
// DashboardTab — Summary cards + Risk Matrix
// ---------------------------------------------------------------------------

function DashboardLoadingSkeleton() {
  return (
    <div className="space-y-6">
      {/* Summary cards skeleton */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      {/* Risk matrix skeleton */}
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

function RiskMatrixCell({ entries }: { entries: RiskMatrixEntry[] }) {
  if (entries.length === 0) {
    return <div className="h-full min-h-[60px]" />;
  }
  return (
    <div className="flex flex-wrap gap-1 p-1">
      {entries.map((entry) => (
        <span
          key={entry.taskTypeId}
          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium border ${TIER_COLORS[entry.tier]}`}
          title={entry.taskTypeId}
        >
          {entry.displayName}
        </span>
      ))}
    </div>
  );
}

function RiskMatrix() {
  const impactLabels = ["High", "Medium", "Low"];
  const likelihoodLabels = ["Low", "Medium", "High"];

  // Build a 3x3 grid: rows are impact (High=2 at top, Low=0 at bottom)
  // columns are likelihood (Low=0 at left, High=2 at right)
  const grid: RiskMatrixEntry[][][] = [
    // Row 0: impact=High (2)
    [[], [], []],
    // Row 1: impact=Medium (1)
    [[], [], []],
    // Row 2: impact=Low (0)
    [[], [], []],
  ];

  for (const entry of DEFAULT_RISK_MATRIX_ENTRIES) {
    // Map impact 2→row 0, 1→row 1, 0→row 2
    const row = 2 - entry.impact;
    const col = entry.likelihood;
    grid[row][col].push(entry);
  }

  // Background colors for cells based on combined risk level
  const cellBg: string[][] = [
    // Row 0 (High impact): Low likelihood=amber, Medium=red-light, High=red
    ["bg-amber-50", "bg-red-50", "bg-red-100"],
    // Row 1 (Medium impact): Low=green-light, Medium=amber-light, High=amber
    ["bg-green-50", "bg-amber-50", "bg-red-50"],
    // Row 2 (Low impact): Low=green, Medium=green-light, High=amber-light
    ["bg-green-100", "bg-green-50", "bg-amber-50"],
  ];

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[500px]">
        <div className="flex">
          {/* Y-axis label */}
          <div className="flex flex-col justify-center items-center w-8 mr-2">
            <span className="text-xs font-medium text-muted-foreground -rotate-90 whitespace-nowrap">
              Impact
            </span>
          </div>

          {/* Grid area */}
          <div className="flex-1">
            {/* Matrix grid */}
            <div className="grid grid-cols-[60px_1fr_1fr_1fr] gap-px border rounded-lg overflow-hidden bg-border">
              {/* Header row */}
              <div className="bg-muted p-2" />
              {likelihoodLabels.map((label) => (
                <div key={label} className="bg-muted p-2 text-center text-xs font-medium text-muted-foreground">
                  {label}
                </div>
              ))}

              {/* Data rows */}
              {grid.map((row, rowIdx) => (
                <React.Fragment key={`row-${rowIdx}`}>
                  <div className="bg-muted p-2 flex items-center justify-center">
                    <span className="text-xs font-medium text-muted-foreground">
                      {impactLabels[rowIdx]}
                    </span>
                  </div>
                  {row.map((cellEntries, colIdx) => (
                    <div
                      key={`cell-${rowIdx}-${colIdx}`}
                      className={`${cellBg[rowIdx][colIdx]} p-2 min-h-[60px] flex items-center justify-center`}
                    >
                      <RiskMatrixCell entries={cellEntries} />
                    </div>
                  ))}
                </React.Fragment>
              ))}
            </div>

            {/* X-axis label */}
            <div className="text-center mt-2">
              <span className="text-xs font-medium text-muted-foreground">Likelihood</span>
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mt-4 justify-center">
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded bg-red-200 border border-red-300" />
            <span className="text-xs text-muted-foreground">High Tier</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded bg-amber-200 border border-amber-300" />
            <span className="text-xs text-muted-foreground">Medium Tier</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded bg-green-200 border border-green-300" />
            <span className="text-xs text-muted-foreground">Low Tier</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function DashboardTab() {
  const dashboardStats = useRiskFrameworkStore((s) => s.dashboardStats);
  const loading = useRiskFrameworkStore((s) => s.loading.dashboardStats);
  const error = useRiskFrameworkStore((s) => s.error.dashboardStats);

  if (loading) {
    return <DashboardLoadingSkeleton />;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-6">
        <h3 className="text-lg font-semibold text-destructive mb-2">Error Loading Dashboard</h3>
        <p className="text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }

  const stats = dashboardStats;
  const highOps = stats?.operations_by_tier?.high ?? 0;
  const mediumOps = stats?.operations_by_tier?.medium ?? 0;
  const lowOps = stats?.operations_by_tier?.low ?? 0;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Operations by Tier */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Operations (30d)</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{highOps + mediumOps + lowOps}</div>
            <div className="flex gap-1.5 mt-1">
              <Badge variant="destructive" className="text-[10px] px-1.5 py-0">
                H:{highOps}
              </Badge>
              <Badge variant="default" className="text-[10px] px-1.5 py-0">
                M:{mediumOps}
              </Badge>
              <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                L:{lowOps}
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* Pending Checkpoints */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending Checkpoints</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.pending_checkpoints ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Awaiting review</p>
          </CardContent>
        </Card>

        {/* Expired Checkpoints */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Expired Checkpoints</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.expired_checkpoints ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Past 72h window</p>
          </CardContent>
        </Card>

        {/* Blocked Operations */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Blocked Operations</CardTitle>
            <ShieldOff className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.blocked_operations ?? 0}</div>
            <p className="text-xs text-muted-foreground mt-1">Gate denied</p>
          </CardContent>
        </Card>

        {/* Active Profile */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Profile</CardTitle>
            <User className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div className="text-lg font-bold truncate" title={stats?.active_profile_name ?? "Default"}>
              {stats?.active_profile_name ?? "Default"}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Risk profile</p>
          </CardContent>
        </Card>
      </div>

      {/* Risk Matrix */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Risk Matrix</CardTitle>
          <p className="text-sm text-muted-foreground">
            AI task types positioned by impact severity and likelihood, color-coded by risk tier
          </p>
        </CardHeader>
        <CardContent>
          <RiskMatrix />
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tier Badge Helper
// ---------------------------------------------------------------------------

function TierBadge({ tier }: { tier: string }) {
  return (
    <Badge variant="outline" className={TIER_COLORS[tier] ?? ""}>
      {tier.charAt(0).toUpperCase() + tier.slice(1)}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Task Types Tab — Loading Skeleton
// ---------------------------------------------------------------------------

function TaskTypesTableSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4">
          <Skeleton className="h-4 w-4" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task Types Tab — Expanded Row Detail
// ---------------------------------------------------------------------------

function TaskTypeExpandedRow({ taskTypeId }: { taskTypeId: string }) {
  const [detail, setDetail] = useState<AITaskTypeDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getTaskType(taskTypeId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load details");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [taskTypeId]);

  if (loading) {
    return (
      <TableRow>
        <TableCell colSpan={6} className="bg-muted/30 px-8 py-4">
          <div className="space-y-2">
            <Skeleton className="h-4 w-60" />
            <Skeleton className="h-4 w-80" />
          </div>
        </TableCell>
      </TableRow>
    );
  }

  if (error || !detail) {
    return (
      <TableRow>
        <TableCell colSpan={6} className="bg-muted/30 px-8 py-4">
          <p className="text-sm text-destructive">{error ?? "No details available"}</p>
        </TableCell>
      </TableRow>
    );
  }

  return (
    <TableRow>
      <TableCell colSpan={6} className="bg-muted/30 px-8 py-4">
        <div className="space-y-4">
          {/* Risk Factors */}
          <div>
            <h4 className="text-sm font-medium mb-1">Risk Factors</h4>
            {detail.risk_factors.length > 0 ? (
              <ul className="list-disc list-inside text-sm text-muted-foreground space-y-0.5">
                {detail.risk_factors.map((factor, idx) => (
                  <li key={idx}>{factor}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No risk factors defined.</p>
            )}
          </div>

          {/* Control Set */}
          {detail.control_set && (
            <div>
              <h4 className="text-sm font-medium mb-1">Control Set ({detail.control_set.display_name})</h4>
              <ControlSetDetail controlSet={detail.control_set} />
            </div>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

function ControlSetDetail({ controlSet }: { controlSet: TierDefinitionResponse }) {
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm text-muted-foreground">
      <div>HITL Required: <span className="font-medium text-foreground">{controlSet.hitl_required ? "Yes" : "No"}</span></div>
      <div>HITL Blocks Visibility: <span className="font-medium text-foreground">{controlSet.hitl_blocks_visibility ? "Yes" : "No"}</span></div>
      <div>Audit Depth: <span className="font-medium text-foreground">{controlSet.audit_depth}</span></div>
      <div>Provenance Required: <span className="font-medium text-foreground">{controlSet.provenance_required ? "Yes" : "No"}</span></div>
      {controlSet.expiry_hours != null && (
        <div>Expiry: <span className="font-medium text-foreground">{controlSet.expiry_hours}h</span></div>
      )}
      {controlSet.rate_limit != null && (
        <div>Rate Limit: <span className="font-medium text-foreground">{controlSet.rate_limit}/user/hour</span></div>
      )}
      {controlSet.output_label && (
        <div>Output Label: <span className="font-medium text-foreground">{controlSet.output_label}</span></div>
      )}
      {controlSet.validations.length > 0 && (
        <div className="col-span-2">
          Validations: <span className="font-medium text-foreground">{controlSet.validations.join(", ")}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task Types Tab
// ---------------------------------------------------------------------------

const PAGE_SIZE = 20;

function TaskTypesTab() {
  const fetchTaskTypes = useRiskFrameworkStore((s) => s.fetchTaskTypes);
  const taskTypes = useRiskFrameworkStore((s) => s.taskTypes);
  const loading = useRiskFrameworkStore((s) => s.loading.taskTypes);
  const error = useRiskFrameworkStore((s) => s.error.taskTypes);

  const [page, setPage] = useState(0);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchTaskTypes({ limit: PAGE_SIZE, offset: page * PAGE_SIZE });
  }, [fetchTaskTypes, page]);

  const toggleRow = useCallback((taskTypeId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(taskTypeId)) {
        next.delete(taskTypeId);
      } else {
        next.add(taskTypeId);
      }
      return next;
    });
  }, []);

  const totalPages = taskTypes ? Math.ceil(taskTypes.total / PAGE_SIZE) : 0;

  if (loading && !taskTypes) {
    return (
      <div className="rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-4">AI Task Types</h3>
        <TaskTypesTableSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-border p-6">
        <h3 className="text-lg font-semibold mb-2">AI Task Types</h3>
        <p className="text-sm text-destructive">Error loading task types: {error}</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border p-6">
      <h3 className="text-lg font-semibold mb-4">AI Task Types</h3>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>Display Name</TableHead>
            <TableHead>Module</TableHead>
            <TableHead>Default Tier</TableHead>
            <TableHead>Company Tier</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {taskTypes && taskTypes.items.length > 0 ? (
            taskTypes.items.map((taskType) => {
              const isExpanded = expandedRows.has(taskType.task_type_id);
              return (
                <React.Fragment key={taskType.id}>
                  <TableRow
                    className="cursor-pointer"
                    onClick={() => toggleRow(taskType.task_type_id)}
                    aria-expanded={isExpanded}
                  >
                    <TableCell>
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="h-4 w-4" aria-hidden="true" />
                      )}
                    </TableCell>
                    <TableCell className="font-medium">{taskType.display_name}</TableCell>
                    <TableCell className="text-muted-foreground">{taskType.module_reference}</TableCell>
                    <TableCell><TierBadge tier={taskType.default_risk_tier} /></TableCell>
                    <TableCell>
                      {taskType.company_tier ? (
                        <TierBadge tier={taskType.company_tier} />
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={taskType.is_active ? "secondary" : "outline"}>
                        {taskType.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                  {isExpanded && (
                    <TaskTypeExpandedRow taskTypeId={taskType.task_type_id} />
                  )}
                </React.Fragment>
              );
            })
          ) : (
            <TableRow>
              <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                No task types found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages} ({taskTypes?.total ?? 0} total)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0 || loading}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1 || loading}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function RiskProfileTab() {
  const activeProfile = useRiskFrameworkStore((s) => s.activeProfile);
  const loading = useRiskFrameworkStore((s) => s.loading.profile);
  const error = useRiskFrameworkStore((s) => s.error.profile);
  const fetchProfile = useRiskFrameworkStore((s) => s.fetchProfile);
  const storeCreateProfile = useRiskFrameworkStore((s) => s.createProfile);

  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  if (loading && !activeProfile) {
    return <RiskProfileLoadingSkeleton />;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-6">
        <h3 className="text-lg font-semibold text-destructive mb-2">Error Loading Profile</h3>
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={() => fetchProfile()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Company Risk Profile</h3>
          <p className="text-sm text-muted-foreground">
            Manage tier overrides and regulatory framework alignment
          </p>
        </div>
        <div className="flex gap-2">
          <Dialog open={showHistoryDialog} onOpenChange={setShowHistoryDialog}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <History className="h-4 w-4 mr-1.5" aria-hidden="true" />
                History
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Profile History</DialogTitle>
                <DialogDescription>
                  Previous risk profile configurations for your company
                </DialogDescription>
              </DialogHeader>
              <ProfileHistoryViewer />
            </DialogContent>
          </Dialog>

          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1.5" aria-hidden="true" />
                New Profile
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Risk Profile</DialogTitle>
                <DialogDescription>
                  Create a new company risk profile. This will deactivate the current active profile.
                </DialogDescription>
              </DialogHeader>
              <CreateProfileForm
                onSuccess={() => {
                  setShowCreateDialog(false);
                  fetchProfile();
                }}
                onCancel={() => setShowCreateDialog(false)}
              />
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Current Profile View */}
      {activeProfile ? (
        <ActiveProfileView profile={activeProfile} />
      ) : (
        <Card>
          <CardContent className="py-8 text-center">
            <ShieldCheck className="h-12 w-12 mx-auto text-muted-foreground mb-3" aria-hidden="true" />
            <h4 className="text-base font-medium mb-1">No Custom Profile</h4>
            <p className="text-sm text-muted-foreground mb-4">
              Your company is using the system default risk profile. Create a custom profile to override tier assignments.
            </p>
            <Button size="sm" onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-1.5" aria-hidden="true" />
              Create Profile
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk Profile — Loading Skeleton
// ---------------------------------------------------------------------------

function RiskProfileLoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-72" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-28" />
        </div>
      </div>
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-60" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk Profile — Active Profile View
// ---------------------------------------------------------------------------

function ActiveProfileView({ profile }: { profile: CompanyRiskProfileResponse }) {
  return (
    <div className="space-y-4">
      {/* Profile Info Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">{profile.profile_name}</CardTitle>
              {profile.description && (
                <CardDescription className="mt-1">{profile.description}</CardDescription>
              )}
            </div>
            <Badge variant="default">Active</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Regulatory Frameworks */}
          <div>
            <h4 className="text-sm font-medium mb-2">Regulatory Frameworks</h4>
            <div className="flex flex-wrap gap-1.5">
              {profile.regulatory_frameworks.length > 0 ? (
                profile.regulatory_frameworks.map((fw) => (
                  <Badge key={fw} variant="secondary">
                    {fw}
                  </Badge>
                ))
              ) : (
                <span className="text-sm text-muted-foreground">None specified</span>
              )}
            </div>
          </div>

          {/* Metadata */}
          <div className="flex gap-6 text-xs text-muted-foreground border-t pt-3">
            <span>Created: {new Date(profile.created_at).toLocaleDateString()}</span>
            {profile.updated_at && (
              <span>Updated: {new Date(profile.updated_at).toLocaleDateString()}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Overrides Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tier Overrides ({profile.overrides.length})</CardTitle>
          <CardDescription>
            Custom risk tier assignments that override system defaults
          </CardDescription>
        </CardHeader>
        <CardContent>
          {profile.overrides.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Task Type</TableHead>
                  <TableHead>Assigned Tier</TableHead>
                  <TableHead>Justification</TableHead>
                  <TableHead>Regulatory Ref</TableHead>
                  <TableHead>Approved By</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profile.overrides.map((override) => (
                  <TableRow key={override.id}>
                    <TableCell className="font-mono text-xs">{override.task_type_id}</TableCell>
                    <TableCell>
                      <TierBadge tier={override.assigned_tier} />
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-sm" title={override.justification}>
                      {override.justification}
                    </TableCell>
                    <TableCell className="text-sm">
                      {override.regulatory_reference ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell className="text-sm">
                      {override.approved_by ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No tier overrides configured. Using system defaults for all task types.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk Profile — Create Profile Form
// ---------------------------------------------------------------------------

interface OverrideFormEntry {
  task_type_id: string;
  assigned_tier: "high" | "medium" | "low";
  justification: string;
  regulatory_reference: string;
  approved_by: string;
  isDeEscalation: boolean;
}

const DEFAULT_TIERS = ["high", "medium", "low"] as const;

/** Determine if an override is a de-escalation based on assigned tier vs typical defaults */
function isDeEscalation(assignedTier: string): boolean {
  // De-escalation means assigning a lower tier. Since we don't know the default
  // tier for each task type in the form, we flag any "low" or "medium" assignment
  // as potentially de-escalation and require the regulatory_reference field.
  // The backend will validate the actual de-escalation rules.
  return assignedTier === "low" || assignedTier === "medium";
}

function CreateProfileForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const storeCreateProfile = useRiskFrameworkStore((s) => s.createProfile);
  const loading = useRiskFrameworkStore((s) => s.loading.profile);

  const [profileName, setProfileName] = useState("");
  const [regulatoryFrameworks, setRegulatoryFrameworks] = useState("");
  const [overrides, setOverrides] = useState<OverrideFormEntry[]>([]);
  const [changeReason, setChangeReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const addOverride = () => {
    setOverrides((prev) => [
      ...prev,
      {
        task_type_id: "",
        assigned_tier: "medium",
        justification: "",
        regulatory_reference: "",
        approved_by: "",
        isDeEscalation: true,
      },
    ]);
  };

  const removeOverride = (index: number) => {
    setOverrides((prev) => prev.filter((_, i) => i !== index));
  };

  const updateOverride = (index: number, field: keyof OverrideFormEntry, value: string) => {
    setOverrides((prev) =>
      prev.map((entry, i) => {
        if (i !== index) return entry;
        const updated = { ...entry, [field]: value };
        if (field === "assigned_tier") {
          updated.isDeEscalation = isDeEscalation(value);
        }
        return updated;
      })
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Basic validation
    if (profileName.length < 3) {
      setFormError("Profile name must be at least 3 characters.");
      return;
    }

    const frameworks = regulatoryFrameworks
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    if (frameworks.length === 0) {
      setFormError("At least one regulatory framework is required.");
      return;
    }

    if (!changeReason.trim()) {
      setFormError("Change reason is required for audit compliance.");
      return;
    }

    // Build overrides payload
    const overridePayload: RiskTierOverrideEntry[] = overrides.map((o) => ({
      task_type_id: o.task_type_id,
      assigned_tier: o.assigned_tier,
      justification: o.justification,
      regulatory_reference: o.regulatory_reference || null,
      approved_by: o.approved_by || null,
    }));

    try {
      await storeCreateProfile(
        {
          profile_name: profileName,
          regulatory_frameworks: frameworks,
          overrides: overridePayload,
        },
        changeReason
      );
      toast.success("Risk profile created successfully.");
      onSuccess();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to create profile";
      setFormError(msg);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {formError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
          {formError}
        </div>
      )}

      {/* Profile Name */}
      <div className="space-y-1.5">
        <label htmlFor="profile-name" className="text-sm font-medium">
          Profile Name <span className="text-destructive">*</span>
        </label>
        <Input
          id="profile-name"
          value={profileName}
          onChange={(e) => setProfileName(e.target.value)}
          placeholder="e.g., GMP Production Profile"
          minLength={3}
          maxLength={200}
          required
        />
      </div>

      {/* Regulatory Frameworks */}
      <div className="space-y-1.5">
        <label htmlFor="regulatory-frameworks" className="text-sm font-medium">
          Regulatory Frameworks <span className="text-destructive">*</span>
        </label>
        <Input
          id="regulatory-frameworks"
          value={regulatoryFrameworks}
          onChange={(e) => setRegulatoryFrameworks(e.target.value)}
          placeholder="GMP, GLP, 21 CFR Part 11 (comma-separated)"
        />
        <p className="text-xs text-muted-foreground">
          Comma-separated list of applicable regulatory frameworks
        </p>
      </div>

      {/* Overrides */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium">Tier Overrides</label>
          <Button type="button" variant="outline" size="sm" onClick={addOverride}>
            <Plus className="h-3.5 w-3.5 mr-1" aria-hidden="true" />
            Add Override
          </Button>
        </div>

        {overrides.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-3 border rounded-md border-dashed">
            No overrides added. The profile will use system defaults for all task types.
          </p>
        )}

        {overrides.map((override, idx) => (
          <OverrideFormRow
            key={idx}
            index={idx}
            override={override}
            onUpdate={updateOverride}
            onRemove={removeOverride}
          />
        ))}
      </div>

      {/* Change Reason */}
      <div className="space-y-1.5">
        <label htmlFor="change-reason" className="text-sm font-medium">
          Change Reason <span className="text-destructive">*</span>
        </label>
        <Input
          id="change-reason"
          value={changeReason}
          onChange={(e) => setChangeReason(e.target.value)}
          placeholder="Reason for creating this profile (audit trail)"
          required
        />
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
        <Button type="submit" disabled={loading}>
          {loading && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" aria-hidden="true" />}
          Create Profile
        </Button>
      </DialogFooter>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Risk Profile — Override Form Row
// ---------------------------------------------------------------------------

function OverrideFormRow({
  index,
  override,
  onUpdate,
  onRemove,
}: {
  index: number;
  override: OverrideFormEntry;
  onUpdate: (index: number, field: keyof OverrideFormEntry, value: string) => void;
  onRemove: (index: number) => void;
}) {
  return (
    <div className="rounded-md border p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Override #{index + 1}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onRemove(index)}
          aria-label={`Remove override ${index + 1}`}
        >
          <Trash2 className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Task Type ID */}
        <div className="space-y-1">
          <label className="text-xs font-medium">Task Type ID</label>
          <Input
            value={override.task_type_id}
            onChange={(e) => onUpdate(index, "task_type_id", e.target.value)}
            placeholder="e.g., document_generation"
            className="text-xs"
          />
        </div>

        {/* Assigned Tier */}
        <div className="space-y-1">
          <label className="text-xs font-medium">Assigned Tier</label>
          <select
            value={override.assigned_tier}
            onChange={(e) => onUpdate(index, "assigned_tier", e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {DEFAULT_TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier.charAt(0).toUpperCase() + tier.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Justification */}
      <div className="space-y-1">
        <label className="text-xs font-medium">Justification</label>
        <Input
          value={override.justification}
          onChange={(e) => onUpdate(index, "justification", e.target.value)}
          placeholder="Minimum 50 characters for de-escalation overrides"
          className="text-xs"
        />
      </div>

      {/* De-escalation fields */}
      {override.isDeEscalation && (
        <>
          <div className="rounded-md bg-amber-50 border border-amber-200 p-2.5 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" aria-hidden="true" />
            <div className="text-xs text-amber-800">
              <p className="font-medium">De-escalation Override</p>
              <p className="mt-0.5">
                This override may lower the risk tier. A regulatory reference is required and the override must be approved by a system_admin or doc_admin.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Regulatory Reference */}
            <div className="space-y-1">
              <label className="text-xs font-medium">
                Regulatory Reference <span className="text-destructive">*</span>
              </label>
              <Input
                value={override.regulatory_reference}
                onChange={(e) => onUpdate(index, "regulatory_reference", e.target.value)}
                placeholder="e.g., EU AI Act Art. 6(2)"
                className="text-xs"
              />
            </div>

            {/* Approved By */}
            <div className="space-y-1">
              <label className="text-xs font-medium">
                Approved By <span className="text-destructive">*</span>
              </label>
              <Input
                value={override.approved_by}
                onChange={(e) => onUpdate(index, "approved_by", e.target.value)}
                placeholder="User ID of approver"
                className="text-xs"
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Risk Profile — Profile History Viewer
// ---------------------------------------------------------------------------

function ProfileHistoryViewer() {
  const [history, setHistory] = useState<PaginatedResult<CompanyRiskProfileResponse> | null>(null);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 10;

  const fetchHistory = useCallback(async (currentOffset: number) => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const result = await getProfileHistory({ limit, offset: currentOffset });
      setHistory(result);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Failed to load profile history");
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHistory(offset);
  }, [fetchHistory, offset]);

  if (historyLoading) {
    return (
      <div className="space-y-3 py-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-32" />
          </div>
        ))}
      </div>
    );
  }

  if (historyError) {
    return (
      <div className="py-4 text-center">
        <p className="text-sm text-destructive">{historyError}</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => fetchHistory(offset)}>
          Retry
        </Button>
      </div>
    );
  }

  if (!history || history.items.length === 0) {
    return (
      <div className="py-6 text-center">
        <p className="text-sm text-muted-foreground">No profile history found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {history.items.map((profile) => (
        <div
          key={profile.id}
          className="rounded-md border p-3 space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{profile.profile_name}</span>
            <Badge variant={profile.is_active ? "default" : "secondary"}>
              {profile.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
          {profile.description && (
            <p className="text-xs text-muted-foreground">{profile.description}</p>
          )}
          <div className="flex flex-wrap gap-1">
            {profile.regulatory_frameworks.map((fw) => (
              <Badge key={fw} variant="outline" className="text-[10px]">
                {fw}
              </Badge>
            ))}
          </div>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <span>Created: {new Date(profile.created_at).toLocaleDateString()}</span>
            <span>Overrides: {profile.overrides.length}</span>
          </div>
        </div>
      ))}

      {/* Pagination */}
      {history.total > limit && (
        <div className="flex items-center justify-between pt-2 border-t">
          <span className="text-xs text-muted-foreground">
            Showing {offset + 1}–{Math.min(offset + limit, history.total)} of {history.total}
          </span>
          <div className="flex gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + limit >= history.total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function HITLQueueTab() {
  const PAGE_SIZE = 20;
  const [currentPage, setCurrentPage] = useState(0);
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false);
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<HITLCheckpointResponse | null>(null);
  const [reviewerComments, setReviewerComments] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const checkpoints = useRiskFrameworkStore((s) => s.checkpoints);
  const loading = useRiskFrameworkStore((s) => s.loading.checkpoints);
  const error = useRiskFrameworkStore((s) => s.error.checkpoints);
  const fetchCheckpoints = useRiskFrameworkStore((s) => s.fetchCheckpoints);
  const reviewCheckpointAction = useRiskFrameworkStore((s) => s.reviewCheckpoint);

  // Fetch checkpoints on mount and page change
  useEffect(() => {
    fetchCheckpoints({ limit: PAGE_SIZE, offset: currentPage * PAGE_SIZE });
  }, [fetchCheckpoints, currentPage]);

  const totalPages = checkpoints ? Math.ceil(checkpoints.total / PAGE_SIZE) : 0;

  const handleReviewClick = (checkpoint: HITLCheckpointResponse) => {
    setSelectedCheckpoint(checkpoint);
    setReviewerComments("");
    setReviewDialogOpen(true);
  };

  const handleReviewSubmit = async (action: "approve" | "reject") => {
    if (!selectedCheckpoint) return;

    if (action === "reject" && !reviewerComments.trim()) {
      toast.error("Reviewer comments are required for rejections.");
      return;
    }

    setIsSubmitting(true);
    try {
      await reviewCheckpointAction(
        selectedCheckpoint.id,
        {
          action,
          reviewer_comments: reviewerComments.trim() || null,
        },
        `${action === "approve" ? "Approved" : "Rejected"} HITL checkpoint for operation ${selectedCheckpoint.operation_id}`
      );
      toast.success(`Checkpoint ${action === "approve" ? "approved" : "rejected"} successfully.`);
      setReviewDialogOpen(false);
      setSelectedCheckpoint(null);
    } catch {
      toast.error(`Failed to ${action} checkpoint.`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getStatusBadgeVariant = (status: HITLCheckpointResponse["status"]): "default" | "secondary" | "destructive" | "outline" => {
    switch (status) {
      case "pending":
        return "outline";
      case "approved":
        return "secondary";
      case "rejected":
        return "destructive";
      case "expired":
        return "destructive";
      default:
        return "outline";
    }
  };

  if (loading && !checkpoints) {
    return (
      <div className="rounded-lg border border-border p-6">
        <div className="flex items-center gap-2 mb-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm text-muted-foreground">Loading HITL checkpoints...</span>
        </div>
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-border p-6">
        <p className="text-sm text-destructive">Error loading checkpoints: {error}</p>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => fetchCheckpoints({ limit: PAGE_SIZE, offset: 0 })}>
          Retry
        </Button>
      </div>
    );
  }

  const items = checkpoints?.items ?? [];

  return (
    <div className="rounded-lg border border-border p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">HITL Checkpoint Queue</h3>
          <p className="text-sm text-muted-foreground">
            Pending human-in-the-loop checkpoints sorted by expiry, with review actions.
          </p>
        </div>
        {checkpoints && (
          <span className="text-sm text-muted-foreground">
            {checkpoints.total} checkpoint{checkpoints.total !== 1 ? "s" : ""} total
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <ClipboardCheck className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">No checkpoints found.</p>
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Operation Type</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((checkpoint) => (
                <TableRow key={checkpoint.id}>
                  <TableCell className="font-medium">{checkpoint.task_type_id}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(checkpoint.created_at)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(checkpoint.expires_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={getStatusBadgeVariant(checkpoint.status)}>
                      {checkpoint.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleReviewClick(checkpoint)}
                    >
                      Review
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* Pagination controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <span className="text-sm text-muted-foreground">
                Page {currentPage + 1} of {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage === 0}
                  onClick={() => setCurrentPage((p) => p - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={currentPage >= totalPages - 1}
                  onClick={() => setCurrentPage((p) => p + 1)}
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Review Detail Dialog */}
      <Dialog open={reviewDialogOpen} onOpenChange={setReviewDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Review HITL Checkpoint</DialogTitle>
            <DialogDescription>
              Review the AI output and approve or reject this checkpoint.
            </DialogDescription>
          </DialogHeader>

          {selectedCheckpoint && (
            <div className="space-y-4">
              {/* Operation metadata */}
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="font-medium text-muted-foreground">Operation Type</span>
                  <p className="mt-0.5">{selectedCheckpoint.task_type_id}</p>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">Operation ID</span>
                  <p className="mt-0.5 font-mono text-xs">{selectedCheckpoint.operation_id}</p>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">Created</span>
                  <p className="mt-0.5">{formatDate(selectedCheckpoint.created_at)}</p>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">Expires</span>
                  <p className="mt-0.5">{formatDate(selectedCheckpoint.expires_at)}</p>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">Status</span>
                  <p className="mt-0.5">
                    <Badge variant={getStatusBadgeVariant(selectedCheckpoint.status)}>
                      {selectedCheckpoint.status}
                    </Badge>
                  </p>
                </div>
                <div>
                  <span className="font-medium text-muted-foreground">Reviewer Role</span>
                  <p className="mt-0.5">{selectedCheckpoint.assigned_reviewer_role}</p>
                </div>
              </div>

              {/* AI Output Reference */}
              <div>
                <span className="text-sm font-medium text-muted-foreground">AI Output Reference</span>
                <div className="mt-1 rounded-md border border-border bg-muted/50 p-3">
                  <p className="text-sm font-mono break-all">{selectedCheckpoint.ai_output_reference}</p>
                </div>
              </div>

              {/* Reviewer comments */}
              <div>
                <label htmlFor="reviewer-comments" className="text-sm font-medium text-muted-foreground">
                  Reviewer Comments
                </label>
                <Textarea
                  id="reviewer-comments"
                  placeholder="Add your review comments here (required for rejections)..."
                  value={reviewerComments}
                  onChange={(e) => setReviewerComments(e.target.value)}
                  maxLength={2000}
                  className="mt-1"
                  rows={4}
                  disabled={selectedCheckpoint.status !== "pending" || isSubmitting}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  {reviewerComments.length}/2000 characters
                </p>
              </div>
            </div>
          )}

          <DialogFooter>
            {selectedCheckpoint?.status === "pending" ? (
              <div className="flex gap-2 w-full sm:w-auto">
                <Button
                  variant="destructive"
                  onClick={() => handleReviewSubmit("reject")}
                  disabled={isSubmitting}
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  Reject
                </Button>
                <Button
                  onClick={() => handleReviewSubmit("approve")}
                  disabled={isSubmitting}
                >
                  {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  Approve
                </Button>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                This checkpoint is already {selectedCheckpoint?.status}. No actions available.
              </p>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Operation Logs Tab — Constants and Helpers
// ---------------------------------------------------------------------------

const LOGS_PAGE_SIZE = 20;

const GATE_RESULT_STYLES: Record<string, string> = {
  passed: "bg-green-100 text-green-800 border-green-200",
  blocked: "bg-red-100 text-red-800 border-red-200",
};

function GateResultBadge({ result }: { result: string }) {
  return (
    <Badge variant="outline" className={GATE_RESULT_STYLES[result] ?? ""}>
      {result.charAt(0).toUpperCase() + result.slice(1)}
    </Badge>
  );
}

function formatDateTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Operation Logs Tab
// ---------------------------------------------------------------------------

function OperationLogsTab() {
  const fetchOperationLogs = useRiskFrameworkStore((s) => s.fetchOperationLogs);
  const operationLogs = useRiskFrameworkStore((s) => s.operationLogs);
  const taskTypes = useRiskFrameworkStore((s) => s.taskTypes);
  const fetchTaskTypes = useRiskFrameworkStore((s) => s.fetchTaskTypes);
  const loading = useRiskFrameworkStore((s) => s.loading.operationLogs);
  const error = useRiskFrameworkStore((s) => s.error.operationLogs);

  // Filter state
  const [filterTaskType, setFilterTaskType] = useState<string>("");
  const [filterTier, setFilterTier] = useState<string>("");
  const [filterOutcome, setFilterOutcome] = useState<string>("");
  const [filterStartDate, setFilterStartDate] = useState<string>("");
  const [filterEndDate, setFilterEndDate] = useState<string>("");
  const [page, setPage] = useState(0);

  // Fetch task types for the filter dropdown (if not already loaded)
  useEffect(() => {
    if (!taskTypes) {
      fetchTaskTypes({ limit: 100, offset: 0 });
    }
  }, [taskTypes, fetchTaskTypes]);

  // Build params and fetch logs when filters or page change
  const fetchLogs = useCallback(() => {
    const params: OperationLogParams = {
      limit: LOGS_PAGE_SIZE,
      offset: page * LOGS_PAGE_SIZE,
    };
    if (filterTaskType) params.task_type_id = filterTaskType;
    if (filterTier) params.risk_tier = filterTier as "high" | "medium" | "low";
    if (filterStartDate) params.start_date = filterStartDate;
    if (filterEndDate) params.end_date = filterEndDate;
    // The backend OperationLogParams doesn't have a gate_result filter directly,
    // but we pass it as part of the params if the API supports it.
    // For now, we filter client-side for outcome if needed.
    fetchOperationLogs(params);
  }, [fetchOperationLogs, page, filterTaskType, filterTier, filterStartDate, filterEndDate]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Reset page when filters change
  const handleFilterChange = useCallback(() => {
    setPage(0);
  }, []);

  const totalPages = operationLogs ? Math.ceil(operationLogs.total / LOGS_PAGE_SIZE) : 0;

  // Client-side outcome filter (if API doesn't support it directly)
  const filteredItems = operationLogs?.items.filter((log) => {
    if (filterOutcome && log.gate_result !== filterOutcome) return false;
    return true;
  }) ?? [];

  return (
    <div className="rounded-lg border border-border p-6 space-y-4">
      <h3 className="text-lg font-semibold">Operation Logs</h3>

      {/* Filter Controls */}
      <div className="flex flex-wrap items-end gap-3">
        {/* Task Type Filter */}
        <div className="space-y-1">
          <label htmlFor="filter-task-type" className="text-xs font-medium text-muted-foreground">
            Task Type
          </label>
          <Select
            id="filter-task-type"
            value={filterTaskType}
            onChange={(e) => { setFilterTaskType(e.target.value); handleFilterChange(); }}
            className="w-48"
          >
            <option value="">All Task Types</option>
            {taskTypes?.items.map((tt) => (
              <option key={tt.task_type_id} value={tt.task_type_id}>
                {tt.display_name}
              </option>
            ))}
          </Select>
        </div>

        {/* Tier Filter */}
        <div className="space-y-1">
          <label htmlFor="filter-tier" className="text-xs font-medium text-muted-foreground">
            Tier
          </label>
          <Select
            id="filter-tier"
            value={filterTier}
            onChange={(e) => { setFilterTier(e.target.value); handleFilterChange(); }}
            className="w-32"
          >
            <option value="">All Tiers</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </Select>
        </div>

        {/* Outcome Filter */}
        <div className="space-y-1">
          <label htmlFor="filter-outcome" className="text-xs font-medium text-muted-foreground">
            Outcome
          </label>
          <Select
            id="filter-outcome"
            value={filterOutcome}
            onChange={(e) => { setFilterOutcome(e.target.value); handleFilterChange(); }}
            className="w-32"
          >
            <option value="">All</option>
            <option value="passed">Passed</option>
            <option value="blocked">Blocked</option>
          </Select>
        </div>

        {/* Start Date Filter */}
        <div className="space-y-1">
          <label htmlFor="filter-start-date" className="text-xs font-medium text-muted-foreground">
            From
          </label>
          <input
            id="filter-start-date"
            type="date"
            value={filterStartDate}
            onChange={(e) => { setFilterStartDate(e.target.value); handleFilterChange(); }}
            className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>

        {/* End Date Filter */}
        <div className="space-y-1">
          <label htmlFor="filter-end-date" className="text-xs font-medium text-muted-foreground">
            To
          </label>
          <input
            id="filter-end-date"
            type="date"
            value={filterEndDate}
            onChange={(e) => { setFilterEndDate(e.target.value); handleFilterChange(); }}
            className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>

        {/* Clear Filters */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setFilterTaskType("");
            setFilterTier("");
            setFilterOutcome("");
            setFilterStartDate("");
            setFilterEndDate("");
            setPage(0);
          }}
          className="text-xs"
        >
          Clear Filters
        </Button>
      </div>

      {/* Loading State */}
      {loading && !operationLogs && (
        <div className="flex items-center justify-center py-12" aria-label="Loading operation logs">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Loading operation logs</span>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>Error loading operation logs: {error}</p>
        </div>
      )}

      {/* Table */}
      {!error && operationLogs && (
        <>
          {filteredItems.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              No operation logs found matching the current filters.
            </div>
          ) : (
            <div className="relative">
              {/* Loading overlay for subsequent fetches */}
              {loading && (
                <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
                </div>
              )}

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Task Type</TableHead>
                    <TableHead>Tier</TableHead>
                    <TableHead>Audit Depth</TableHead>
                    <TableHead>Outcome</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Model</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredItems.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="whitespace-nowrap text-sm">
                        {formatDateTime(log.created_at)}
                      </TableCell>
                      <TableCell className="font-medium text-sm">
                        {log.task_type_id}
                      </TableCell>
                      <TableCell>
                        <TierBadge tier={log.risk_tier} />
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-xs">
                          {log.audit_depth}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <GateResultBadge result={log.gate_result} />
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {log.inference_duration_ms != null
                          ? `${log.inference_duration_ms}ms`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {log.model_name ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Pagination Controls */}
          {totalPages > 0 && (
            <div className="flex items-center justify-between pt-4">
              <p className="text-sm text-muted-foreground">
                Showing {operationLogs.offset + 1}–
                {Math.min(operationLogs.offset + LOGS_PAGE_SIZE, operationLogs.total)} of{" "}
                {operationLogs.total} logs
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0 || loading}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1 || loading}
                  aria-label="Next page"
                >
                  Next
                  <ChevronRight className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AIRiskFrameworkPage
// ---------------------------------------------------------------------------

export function AIRiskFrameworkPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuthStore((s) => s.user);
  const fetchDashboardStats = useRiskFrameworkStore((s) => s.fetchDashboardStats);

  // Role-based access check — redirect unauthorized users
  useEffect(() => {
    const hasAuthorizedRole =
      user?.roles?.some((role) => AUTHORIZED_ROLES.includes(role)) ?? false;

    if (user && !hasAuthorizedRole) {
      toast.error("Access denied. This page requires system_admin or doc_admin role.");
      navigate("/", { replace: true });
    }
  }, [user, navigate]);

  // Fetch dashboard stats on mount
  useEffect(() => {
    fetchDashboardStats();
  }, [fetchDashboardStats]);

  // Tab state from URL
  const tabParam = searchParams.get("tab");
  const defaultTab: TabId =
    tabParam && VALID_TAB_IDS.has(tabParam) ? (tabParam as TabId) : "dashboard";

  const handleTabChange = (value: string) => {
    setSearchParams({ tab: value });
  };

  return (
    <main role="main" aria-label="AI Risk & Compliance Framework" className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold">AI Risk & Compliance Framework</h2>
        <p className="text-sm text-muted-foreground">
          Manage risk classifications, control enforcement, HITL checkpoints, and audit compliance for AI operations
        </p>
      </div>

      {/* Tabbed layout */}
      <Tabs defaultValue={defaultTab} onValueChange={handleTabChange}>
        <TabsList className="grid w-full grid-cols-5">
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

        <TabsContent value="dashboard">
          <DashboardTab />
        </TabsContent>

        <TabsContent value="task-types">
          <TaskTypesTab />
        </TabsContent>

        <TabsContent value="risk-profile">
          <RiskProfileTab />
        </TabsContent>

        <TabsContent value="hitl-queue">
          <HITLQueueTab />
        </TabsContent>

        <TabsContent value="operation-logs">
          <OperationLogsTab />
        </TabsContent>
      </Tabs>
    </main>
  );
}
