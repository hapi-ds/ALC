/**
 * System Configuration Store — Zustand state management for admin system configuration.
 *
 * Manages state for AI hardware, storage quotas, backup configuration,
 * health monitoring, service status, and configuration snapshots/rollback.
 * All mutation actions include X-Change-Reason header for ALCOA+ audit compliance.
 */

import { create } from "zustand";
import { apiClient, ApiError } from "@/lib/apiClient";
import type {
  AIHardwareConfig,
  AIHardwareUpdate,
  VLLMStatus,
  CompanyStorageUsage,
  StorageTotals,
  StorageQuotaUpdate,
  BackupSchedule,
  RetentionPolicy,
  BackupRecord,
  ServiceHealthStatus,
  HealthCheckConfig,
  ServiceInfo,
  ResourceMetrics,
  ConfigurationSnapshot,
  ConfigDiffItem,
  RollbackConfirmation,
  PaginationMeta,
} from "@/types/systemConfig";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SystemConfigState {
  // AI Hardware
  aiHardware: AIHardwareConfig | null;
  vllmStatus: VLLMStatus | null;

  // Storage
  storageUsage: CompanyStorageUsage[];
  storageTotals: StorageTotals | null;
  quotas: Record<number, { quota_limit_bytes: number | null; alert_threshold_pct: number | null }>;

  // Backups
  backupSchedule: BackupSchedule | null;
  retentionPolicy: RetentionPolicy | null;
  backupHistory: BackupRecord[];
  activeBackupTaskId: string | null;

  // Health
  healthStatus: ServiceHealthStatus[];
  healthConfig: HealthCheckConfig | null;
  healthPollingInterval: number;

  // Services
  services: ServiceInfo[];
  resourceMetrics: Record<string, ResourceMetrics[]>;

  // Snapshots
  snapshots: ConfigurationSnapshot[];
  snapshotsPagination: PaginationMeta;

  // Loading states
  loading: Record<string, boolean>;
  errors: Record<string, string | null>;

  // Actions — AI Hardware
  fetchAIHardware: () => Promise<void>;
  updateAIHardware: (data: AIHardwareUpdate, reason: string) => Promise<void>;
  restartVLLM: (reason: string) => Promise<void>;
  fetchVLLMStatus: () => Promise<void>;

  // Actions — Storage
  fetchStorageUsage: () => Promise<void>;
  fetchQuotas: () => Promise<void>;
  updateQuota: (companyId: number, data: StorageQuotaUpdate, reason: string) => Promise<void>;

  // Actions — Backups
  fetchBackupSchedule: () => Promise<void>;
  updateBackupSchedule: (cron: string, reason: string) => Promise<void>;
  fetchRetentionPolicy: () => Promise<void>;
  updateRetentionPolicy: (days: number, reason: string) => Promise<void>;
  triggerBackup: (reason: string) => Promise<void>;
  fetchBackupHistory: () => Promise<void>;
  pollBackupStatus: (taskId: string) => Promise<void>;

  // Actions — Health
  fetchHealthStatus: () => Promise<void>;
  fetchHealthHistory: (service: string) => Promise<void>;
  fetchHealthConfig: () => Promise<void>;
  updateHealthConfig: (data: Partial<HealthCheckConfig>, reason: string) => Promise<void>;

  // Actions — Services
  fetchServices: () => Promise<void>;
  fetchServiceMetrics: (service: string) => Promise<void>;
  fetchResourceMetrics: (service: string) => Promise<void>;

  // Actions — Snapshots
  fetchSnapshots: (page?: number) => Promise<void>;
  fetchSnapshotDiff: (id: number) => Promise<ConfigDiffItem[]>;
  rollbackToSnapshot: (id: number, reason: string) => Promise<RollbackConfirmation>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setLoading(set: (partial: Partial<SystemConfigState>) => void, key: string, value: boolean) {
  set({ loading: { ...useSystemConfigStore.getState().loading, [key]: value } });
}

function setError(set: (partial: Partial<SystemConfigState>) => void, key: string, error: string | null) {
  set({ errors: { ...useSystemConfigStore.getState().errors, [key]: error } });
}

/** Extract a human-readable error message from an API error or generic error. */
function extractErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    try {
      const body = JSON.parse(error.body);
      if (body.detail) return body.detail;
    } catch {
      // body wasn't JSON — fall through
    }
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useSystemConfigStore = create<SystemConfigState>((set, get) => ({
  // Initial state
  aiHardware: null,
  vllmStatus: null,
  storageUsage: [],
  storageTotals: null,
  quotas: {},
  backupSchedule: null,
  retentionPolicy: null,
  backupHistory: [],
  activeBackupTaskId: null,
  healthStatus: [],
  healthConfig: null,
  healthPollingInterval: 30,
  services: [],
  resourceMetrics: {},
  snapshots: [],
  snapshotsPagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
  loading: {},
  errors: {},

  // ---------------------------------------------------------------------------
  // AI Hardware actions
  // ---------------------------------------------------------------------------

  fetchAIHardware: async () => {
    setLoading(set, "aiHardware", true);
    setError(set, "aiHardware", null);
    try {
      const response = await apiClient.get<AIHardwareConfig>("/api/system-config/ai-hardware");
      set({ aiHardware: response });
    } catch (error) {
      setError(set, "aiHardware", extractErrorMessage(error, "Failed to fetch AI hardware config"));
    } finally {
      setLoading(set, "aiHardware", false);
    }
  },

  updateAIHardware: async (data: AIHardwareUpdate, reason: string) => {
    setLoading(set, "aiHardware", true);
    setError(set, "aiHardware", null);
    try {
      const response = await apiClient.put<AIHardwareConfig>(
        "/api/system-config/ai-hardware",
        data,
        { changeReason: reason },
      );
      set({ aiHardware: response });
    } catch (error) {
      setError(set, "aiHardware", extractErrorMessage(error, "Failed to update AI hardware config"));
      throw error;
    } finally {
      setLoading(set, "aiHardware", false);
    }
  },

  restartVLLM: async (reason: string) => {
    setLoading(set, "vllmRestart", true);
    setError(set, "vllmRestart", null);
    try {
      await apiClient.post("/api/system-config/ai-hardware/restart-vllm", undefined, { changeReason: reason });
      set({ vllmStatus: { status: "restarting", elapsed_time: 0, error: null } });
    } catch (error) {
      setError(set, "vllmRestart", extractErrorMessage(error, "Failed to restart vLLM"));
      throw error;
    } finally {
      setLoading(set, "vllmRestart", false);
    }
  },

  fetchVLLMStatus: async () => {
    setLoading(set, "vllmStatus", true);
    setError(set, "vllmStatus", null);
    try {
      const response = await apiClient.get<VLLMStatus>("/api/system-config/ai-hardware/vllm-status");
      set({ vllmStatus: response });
    } catch (error) {
      setError(set, "vllmStatus", extractErrorMessage(error, "Failed to fetch vLLM status"));
    } finally {
      setLoading(set, "vllmStatus", false);
    }
  },

  // ---------------------------------------------------------------------------
  // Storage actions
  // ---------------------------------------------------------------------------

  fetchStorageUsage: async () => {
    setLoading(set, "storageUsage", true);
    setError(set, "storageUsage", null);
    try {
      const response = await apiClient.get<{ companies: CompanyStorageUsage[]; totals: StorageTotals }>(
        "/api/system-config/storage/usage",
      );
      set({ storageUsage: response.companies, storageTotals: response.totals });
    } catch (error) {
      setError(set, "storageUsage", extractErrorMessage(error, "Failed to fetch storage usage"));
    } finally {
      setLoading(set, "storageUsage", false);
    }
  },

  fetchQuotas: async () => {
    setLoading(set, "quotas", true);
    setError(set, "quotas", null);
    try {
      const response = await apiClient.get<{ quotas: Array<{ company_id: number; quota_limit_bytes: number | null; alert_threshold_pct: number | null }> }>(
        "/api/system-config/storage/quotas",
      );
      const quotasMap: Record<number, { quota_limit_bytes: number | null; alert_threshold_pct: number | null }> = {};
      for (const q of response.quotas) {
        quotasMap[q.company_id] = { quota_limit_bytes: q.quota_limit_bytes, alert_threshold_pct: q.alert_threshold_pct };
      }
      set({ quotas: quotasMap });
    } catch (error) {
      setError(set, "quotas", extractErrorMessage(error, "Failed to fetch quotas"));
    } finally {
      setLoading(set, "quotas", false);
    }
  },

  updateQuota: async (companyId: number, data: StorageQuotaUpdate, reason: string) => {
    setLoading(set, "quotas", true);
    setError(set, "quotas", null);
    try {
      await apiClient.put(
        `/api/system-config/storage/quotas/${companyId}`,
        data,
        { changeReason: reason },
      );
      // Update local state
      const currentQuotas = get().quotas;
      set({
        quotas: {
          ...currentQuotas,
          [companyId]: {
            quota_limit_bytes: data.quota_limit_bytes ?? currentQuotas[companyId]?.quota_limit_bytes ?? null,
            alert_threshold_pct: data.alert_threshold_pct ?? currentQuotas[companyId]?.alert_threshold_pct ?? null,
          },
        },
      });
    } catch (error) {
      setError(set, "quotas", extractErrorMessage(error, "Failed to update quota"));
      throw error;
    } finally {
      setLoading(set, "quotas", false);
    }
  },

  // ---------------------------------------------------------------------------
  // Backup actions
  // ---------------------------------------------------------------------------

  fetchBackupSchedule: async () => {
    setLoading(set, "backupSchedule", true);
    setError(set, "backupSchedule", null);
    try {
      const response = await apiClient.get<BackupSchedule>("/api/system-config/backups/schedule");
      set({ backupSchedule: response });
    } catch (error) {
      setError(set, "backupSchedule", extractErrorMessage(error, "Failed to fetch backup schedule"));
    } finally {
      setLoading(set, "backupSchedule", false);
    }
  },

  updateBackupSchedule: async (cron: string, reason: string) => {
    setLoading(set, "backupSchedule", true);
    setError(set, "backupSchedule", null);
    try {
      const response = await apiClient.put<BackupSchedule>(
        "/api/system-config/backups/schedule",
        { cron_expression: cron },
        { changeReason: reason },
      );
      set({ backupSchedule: response });
    } catch (error) {
      setError(set, "backupSchedule", extractErrorMessage(error, "Failed to update backup schedule"));
      throw error;
    } finally {
      setLoading(set, "backupSchedule", false);
    }
  },

  fetchRetentionPolicy: async () => {
    setLoading(set, "retentionPolicy", true);
    setError(set, "retentionPolicy", null);
    try {
      const response = await apiClient.get<RetentionPolicy>("/api/system-config/backups/retention");
      set({ retentionPolicy: response });
    } catch (error) {
      setError(set, "retentionPolicy", extractErrorMessage(error, "Failed to fetch retention policy"));
    } finally {
      setLoading(set, "retentionPolicy", false);
    }
  },

  updateRetentionPolicy: async (days: number, reason: string) => {
    setLoading(set, "retentionPolicy", true);
    setError(set, "retentionPolicy", null);
    try {
      const response = await apiClient.put<RetentionPolicy>(
        "/api/system-config/backups/retention",
        { retention_days: days },
        { changeReason: reason },
      );
      set({ retentionPolicy: response });
    } catch (error) {
      setError(set, "retentionPolicy", extractErrorMessage(error, "Failed to update retention policy"));
      throw error;
    } finally {
      setLoading(set, "retentionPolicy", false);
    }
  },

  triggerBackup: async (reason: string) => {
    setLoading(set, "triggerBackup", true);
    setError(set, "triggerBackup", null);
    try {
      const response = await apiClient.post<{ task_id: string }>(
        "/api/system-config/backups/trigger",
        undefined,
        { changeReason: reason },
      );
      set({ activeBackupTaskId: response.task_id });
    } catch (error) {
      setError(set, "triggerBackup", extractErrorMessage(error, "Failed to trigger backup"));
      throw error;
    } finally {
      setLoading(set, "triggerBackup", false);
    }
  },

  fetchBackupHistory: async () => {
    setLoading(set, "backupHistory", true);
    setError(set, "backupHistory", null);
    try {
      const response = await apiClient.get<BackupRecord[] | { backups: BackupRecord[] }>("/api/system-config/backups/history");
      const backups = Array.isArray(response) ? response : (response.backups ?? []);
      set({ backupHistory: backups });
    } catch (error) {
      setError(set, "backupHistory", extractErrorMessage(error, "Failed to fetch backup history"));
    } finally {
      setLoading(set, "backupHistory", false);
    }
  },

  pollBackupStatus: async (taskId: string) => {
    setLoading(set, "backupStatus", true);
    setError(set, "backupStatus", null);
    try {
      const response = await apiClient.get<BackupRecord>(`/api/system-config/backups/status/${taskId}`);
      // Update the backup in history if it exists
      const history = get().backupHistory;
      const idx = history.findIndex((b) => b.task_id === taskId);
      if (idx >= 0) {
        const updated = [...history];
        updated[idx] = response;
        set({ backupHistory: updated });
      }
      // Clear active task if completed or failed
      if (response.status === "completed" || response.status === "failed") {
        set({ activeBackupTaskId: null });
      }
    } catch (error) {
      setError(set, "backupStatus", extractErrorMessage(error, "Failed to poll backup status"));
    } finally {
      setLoading(set, "backupStatus", false);
    }
  },

  // ---------------------------------------------------------------------------
  // Health actions
  // ---------------------------------------------------------------------------

  fetchHealthStatus: async () => {
    setLoading(set, "healthStatus", true);
    setError(set, "healthStatus", null);
    try {
      const response = await apiClient.get<ServiceHealthStatus[] | { services: ServiceHealthStatus[] }>("/api/system-config/health/status");
      // Handle both array response and wrapped { services: [...] } format
      const services = Array.isArray(response) ? response : (response.services ?? []);
      set({ healthStatus: services });
    } catch (error) {
      setError(set, "healthStatus", extractErrorMessage(error, "Failed to fetch health status"));
    } finally {
      setLoading(set, "healthStatus", false);
    }
  },

  fetchHealthHistory: async (service: string) => {
    setLoading(set, "healthHistory", true);
    setError(set, "healthHistory", null);
    try {
      await apiClient.get(`/api/system-config/health/history/${service}`);
    } catch (error) {
      setError(set, "healthHistory", extractErrorMessage(error, "Failed to fetch health history"));
    } finally {
      setLoading(set, "healthHistory", false);
    }
  },

  fetchHealthConfig: async () => {
    setLoading(set, "healthConfig", true);
    setError(set, "healthConfig", null);
    try {
      const response = await apiClient.get<HealthCheckConfig>("/api/system-config/health/config");
      set({ healthConfig: response, healthPollingInterval: response.polling_interval_seconds });
    } catch (error) {
      setError(set, "healthConfig", extractErrorMessage(error, "Failed to fetch health config"));
    } finally {
      setLoading(set, "healthConfig", false);
    }
  },

  updateHealthConfig: async (data: Partial<HealthCheckConfig>, reason: string) => {
    setLoading(set, "healthConfig", true);
    setError(set, "healthConfig", null);
    try {
      const response = await apiClient.put<HealthCheckConfig>(
        "/api/system-config/health/config",
        data,
        { changeReason: reason },
      );
      set({ healthConfig: response, healthPollingInterval: response.polling_interval_seconds });
    } catch (error) {
      setError(set, "healthConfig", extractErrorMessage(error, "Failed to update health config"));
      throw error;
    } finally {
      setLoading(set, "healthConfig", false);
    }
  },

  // ---------------------------------------------------------------------------
  // Service actions
  // ---------------------------------------------------------------------------

  fetchServices: async () => {
    setLoading(set, "services", true);
    setError(set, "services", null);
    try {
      const response = await apiClient.get<ServiceInfo[] | { services: ServiceInfo[] }>("/api/system-config/services");
      const services = Array.isArray(response) ? response : (response.services ?? []);
      set({ services });
    } catch (error) {
      setError(set, "services", extractErrorMessage(error, "Failed to fetch services"));
    } finally {
      setLoading(set, "services", false);
    }
  },

  fetchServiceMetrics: async (service: string) => {
    setLoading(set, "resourceMetrics", true);
    setError(set, "resourceMetrics", null);
    try {
      const response = await apiClient.get<{ metrics: ResourceMetrics[] }>(
        `/api/system-config/services/${service}/metrics`,
      );
      const current = get().resourceMetrics;
      set({ resourceMetrics: { ...current, [service]: response.metrics } });
    } catch (error) {
      setError(set, "resourceMetrics", extractErrorMessage(error, "Failed to fetch service metrics"));
    } finally {
      setLoading(set, "resourceMetrics", false);
    }
  },

  fetchResourceMetrics: async (service: string) => {
    setLoading(set, "resourceMetrics", true);
    setError(set, "resourceMetrics", null);
    try {
      const response = await apiClient.get<{ metrics: ResourceMetrics[] }>(
        `/api/system-config/services/${service}/metrics`,
      );
      const current = get().resourceMetrics;
      set({ resourceMetrics: { ...current, [service]: response.metrics } });
    } catch (error) {
      setError(set, "resourceMetrics", extractErrorMessage(error, "Failed to fetch resource metrics"));
    } finally {
      setLoading(set, "resourceMetrics", false);
    }
  },

  // ---------------------------------------------------------------------------
  // Snapshot actions
  // ---------------------------------------------------------------------------

  fetchSnapshots: async (page = 1) => {
    setLoading(set, "snapshots", true);
    setError(set, "snapshots", null);
    try {
      const response = await apiClient.get<{
        snapshots: ConfigurationSnapshot[];
        pagination: PaginationMeta;
      }>(`/api/system-config/snapshots?page=${page}&page_size=20`);
      set({ snapshots: response.snapshots, snapshotsPagination: response.pagination });
    } catch (error) {
      setError(set, "snapshots", extractErrorMessage(error, "Failed to fetch snapshots"));
    } finally {
      setLoading(set, "snapshots", false);
    }
  },

  fetchSnapshotDiff: async (id: number) => {
    setLoading(set, "snapshotDiff", true);
    setError(set, "snapshotDiff", null);
    try {
      const response = await apiClient.get<{ diff: ConfigDiffItem[] }>(
        `/api/system-config/snapshots/${id}/diff`,
      );
      return response.diff;
    } catch (error) {
      setError(set, "snapshotDiff", extractErrorMessage(error, "Failed to fetch snapshot diff"));
      throw error;
    } finally {
      setLoading(set, "snapshotDiff", false);
    }
  },

  rollbackToSnapshot: async (id: number, reason: string) => {
    setLoading(set, "rollback", true);
    setError(set, "rollback", null);
    try {
      const response = await apiClient.post<RollbackConfirmation>(
        `/api/system-config/snapshots/${id}/rollback`,
        undefined,
        { changeReason: reason },
      );
      return response;
    } catch (error) {
      setError(set, "rollback", extractErrorMessage(error, "Failed to rollback to snapshot"));
      throw error;
    } finally {
      setLoading(set, "rollback", false);
    }
  },
}));
