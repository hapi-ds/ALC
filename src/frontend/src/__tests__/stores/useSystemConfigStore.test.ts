import { describe, it, expect, beforeEach, vi } from "vitest";
import { useSystemConfigStore } from "@/stores/useSystemConfigStore";
import type { SystemConfigState } from "@/stores/useSystemConfigStore";

/**
 * Unit tests for useSystemConfigStore actions.
 *
 * Validates: Requirements 2.1, 5.1, 7.4, 9.2, 11.4
 */

// Mock apiClient module
vi.mock("@/lib/apiClient", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly body: string;
    readonly url: string;
    constructor(status: number, body: string, url: string) {
      super(`API error ${status} on ${url}`);
      this.name = "ApiError";
      this.status = status;
      this.body = body;
      this.url = url;
    }
  },
}));

import { apiClient } from "@/lib/apiClient";

const mockedApiClient = apiClient as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAIHardwareConfig() {
  return {
    model_chat_name: "gemma-4-e4b-it",
    model_chat_path: "/models/gemma-4-e4b-it",
    model_chat_max_gpu_memory_gb: 24,
    model_embedding_name: "bge-small-en",
    model_embedding_path: "/models/bge-small-en",
    model_embedding_dimension: 384,
    model_ocr_name: "gemma-4-e4b-it",
    model_ocr_path: "/models/gemma-4-e4b-it",
    inference_mode: "gpu" as const,
    gpu_device_id: 0,
    vllm_chat_url: "http://vllm:8000",
    vllm_embedding_url: "http://vllm:8001",
    vllm_chat_status: "reachable" as const,
    vllm_embedding_status: "reachable" as const,
  };
}

function makeVLLMStatus() {
  return { status: "running" as const, elapsed_time: null, error: null };
}

function makeStorageUsageResponse() {
  return {
    companies: [
      {
        company_id: 1,
        company_name: "Acme Corp",
        usage_bytes: 1073741824,
        human_readable: "1.00 GB",
        quota_status: "normal" as const,
        quota_limit_bytes: 10737418240,
        alert_threshold_pct: 80,
      },
    ],
    totals: {
      total_used_bytes: 1073741824,
      total_capacity_bytes: 107374182400,
      human_readable_used: "1.00 GB",
      human_readable_capacity: "100.00 GB",
    },
  };
}

function makeQuotasResponse() {
  return {
    quotas: [
      { company_id: 1, quota_limit_bytes: 10737418240, alert_threshold_pct: 80 },
      { company_id: 2, quota_limit_bytes: null, alert_threshold_pct: null },
    ],
  };
}

function makeBackupSchedule() {
  return { cron_expression: "0 2 * * *", human_readable: "Daily at 02:00 UTC" };
}

function makeRetentionPolicy() {
  return { retention_days: 30, backup_count: 15 };
}

function makeBackupHistory() {
  return {
    backups: [
      {
        id: 1,
        task_id: "task-abc-123",
        backup_type: "manual" as const,
        status: "completed" as const,
        started_at: "2024-06-01T02:00:00Z",
        completed_at: "2024-06-01T02:05:00Z",
        file_size_bytes: 52428800,
        duration_seconds: 300,
        error_message: null,
      },
    ],
  };
}

function makeHealthStatusResponse() {
  return {
    services: [
      {
        service_name: "postgresql",
        status: "healthy" as const,
        response_time_ms: 12.5,
        last_checked: "2024-06-01T12:00:00Z",
        uptime_pct_24h: 99.9,
        avg_response_time_5min: 11.2,
      },
      {
        service_name: "redis",
        status: "healthy" as const,
        response_time_ms: 2.1,
        last_checked: "2024-06-01T12:00:00Z",
        uptime_pct_24h: 100.0,
        avg_response_time_5min: 1.8,
      },
    ],
  };
}

function makeHealthConfig() {
  return {
    polling_interval_seconds: 30,
    degraded_threshold_seconds: 5,
    unreachable_timeout_seconds: 10,
  };
}

function makeServicesResponse() {
  return {
    services: [
      {
        container_name: "alcoabase-postgres",
        service_name: "postgresql",
        running_state: "running",
        version: "16.2",
        uptime: "5d 12h",
        cpu_percent: 3.2,
        memory_used_mb: 256,
        memory_limit_mb: 1024,
        host: "localhost",
        port: 5432,
      },
    ],
  };
}

function makeResourceMetricsResponse() {
  return {
    metrics: [
      {
        service_name: "postgresql",
        cpu_percent: 3.2,
        memory_used_mb: 256,
        memory_limit_mb: 1024,
        recorded_at: "2024-06-01T12:00:00Z",
      },
    ],
  };
}

function makeSnapshotsResponse() {
  return {
    snapshots: [
      {
        id: 1,
        created_at: "2024-06-01T10:00:00Z",
        created_by_name: "admin",
        change_reason: "Updated AI model",
        is_rollback: false,
        changed_keys: ["ai_hardware.model_chat_name"],
      },
    ],
    pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
  };
}

function makeRollbackConfirmation() {
  return {
    snapshot_id: 1,
    snapshot_timestamp: "2024-06-01T10:00:00Z",
    acting_user: "admin",
    changed_categories: ["ai_hardware"],
    diff: [{ key: "ai_hardware.model_chat_name", old_value: "new-model", new_value: "gemma-4-e4b-it" }],
    services_requiring_restart: ["vllm"],
  };
}

// ---------------------------------------------------------------------------
// Default state for reset between tests
// ---------------------------------------------------------------------------

const defaultState: Partial<SystemConfigState> = {
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
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useSystemConfigStore", () => {
  beforeEach(() => {
    useSystemConfigStore.setState(defaultState);
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Initial state
  // -------------------------------------------------------------------------

  describe("initial state", () => {
    it("has correct defaults", () => {
      useSystemConfigStore.setState(defaultState);
      const state = useSystemConfigStore.getState();

      expect(state.aiHardware).toBeNull();
      expect(state.vllmStatus).toBeNull();
      expect(state.storageUsage).toEqual([]);
      expect(state.storageTotals).toBeNull();
      expect(state.quotas).toEqual({});
      expect(state.backupSchedule).toBeNull();
      expect(state.retentionPolicy).toBeNull();
      expect(state.backupHistory).toEqual([]);
      expect(state.activeBackupTaskId).toBeNull();
      expect(state.healthStatus).toEqual([]);
      expect(state.healthConfig).toBeNull();
      expect(state.healthPollingInterval).toBe(30);
      expect(state.services).toEqual([]);
      expect(state.resourceMetrics).toEqual({});
      expect(state.snapshots).toEqual([]);
      expect(state.snapshotsPagination).toEqual({ page: 1, page_size: 20, total: 0, total_pages: 0 });
      expect(state.loading).toEqual({});
      expect(state.errors).toEqual({});
    });
  });

  // -------------------------------------------------------------------------
  // fetchAIHardware()
  // -------------------------------------------------------------------------

  describe("fetchAIHardware()", () => {
    it("fetches AI hardware config and stores it", async () => {
      mockedApiClient.get.mockResolvedValue(makeAIHardwareConfig());

      await useSystemConfigStore.getState().fetchAIHardware();

      const state = useSystemConfigStore.getState();
      expect(state.aiHardware).not.toBeNull();
      expect(state.aiHardware!.model_chat_name).toBe("gemma-4-e4b-it");
      expect(state.aiHardware!.inference_mode).toBe("gpu");
      expect(state.loading.aiHardware).toBe(false);
      expect(state.errors.aiHardware).toBeNull();
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeAIHardwareConfig());

      await useSystemConfigStore.getState().fetchAIHardware();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/ai-hardware");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Network failure"));

      await useSystemConfigStore.getState().fetchAIHardware();

      const state = useSystemConfigStore.getState();
      expect(state.errors.aiHardware).toBe("Network failure");
      expect(state.loading.aiHardware).toBe(false);
    });

    it("sets loading true during request", async () => {
      mockedApiClient.get.mockImplementation(() => new Promise(() => {}));

      useSystemConfigStore.getState().fetchAIHardware();

      await vi.waitFor(() => {
        expect(useSystemConfigStore.getState().loading.aiHardware).toBe(true);
      });
    });
  });

  // -------------------------------------------------------------------------
  // updateAIHardware()
  // -------------------------------------------------------------------------

  describe("updateAIHardware()", () => {
    it("sends PUT with data and X-Change-Reason", async () => {
      mockedApiClient.put.mockResolvedValue(makeAIHardwareConfig());

      await useSystemConfigStore.getState().updateAIHardware(
        { model_chat_name: "new-model" },
        "Switching to new model",
      );

      expect(mockedApiClient.put).toHaveBeenCalledWith(
        "/api/system-config/ai-hardware",
        { model_chat_name: "new-model" },
        { changeReason: "Switching to new model" },
      );
    });

    it("updates aiHardware state on success", async () => {
      const updated = { ...makeAIHardwareConfig(), model_chat_name: "new-model" };
      mockedApiClient.put.mockResolvedValue(updated);

      await useSystemConfigStore.getState().updateAIHardware(
        { model_chat_name: "new-model" },
        "reason",
      );

      expect(useSystemConfigStore.getState().aiHardware!.model_chat_name).toBe("new-model");
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.put.mockRejectedValue(new Error("Validation failed"));

      await expect(
        useSystemConfigStore.getState().updateAIHardware({ model_chat_path: "/bad/path" }, "reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.aiHardware).toBe("Validation failed");
      expect(useSystemConfigStore.getState().loading.aiHardware).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // restartVLLM()
  // -------------------------------------------------------------------------

  describe("restartVLLM()", () => {
    it("sends POST with X-Change-Reason to restart endpoint", async () => {
      mockedApiClient.post.mockResolvedValue({});

      await useSystemConfigStore.getState().restartVLLM("Applying new model config");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/system-config/ai-hardware/restart-vllm",
        undefined,
        { changeReason: "Applying new model config" },
      );
    });

    it("sets vllmStatus to restarting on success", async () => {
      mockedApiClient.post.mockResolvedValue({});

      await useSystemConfigStore.getState().restartVLLM("reason");

      const state = useSystemConfigStore.getState();
      expect(state.vllmStatus).not.toBeNull();
      expect(state.vllmStatus!.status).toBe("restarting");
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("Docker timeout"));

      await expect(
        useSystemConfigStore.getState().restartVLLM("reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.vllmRestart).toBe("Docker timeout");
    });
  });

  // -------------------------------------------------------------------------
  // fetchVLLMStatus()
  // -------------------------------------------------------------------------

  describe("fetchVLLMStatus()", () => {
    it("fetches vLLM status and stores it", async () => {
      mockedApiClient.get.mockResolvedValue(makeVLLMStatus());

      await useSystemConfigStore.getState().fetchVLLMStatus();

      const state = useSystemConfigStore.getState();
      expect(state.vllmStatus).not.toBeNull();
      expect(state.vllmStatus!.status).toBe("running");
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeVLLMStatus());

      await useSystemConfigStore.getState().fetchVLLMStatus();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/ai-hardware/vllm-status");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Service unavailable"));

      await useSystemConfigStore.getState().fetchVLLMStatus();

      expect(useSystemConfigStore.getState().errors.vllmStatus).toBe("Service unavailable");
    });
  });

  // -------------------------------------------------------------------------
  // fetchStorageUsage()
  // -------------------------------------------------------------------------

  describe("fetchStorageUsage()", () => {
    it("fetches storage usage and stores companies + totals", async () => {
      mockedApiClient.get.mockResolvedValue(makeStorageUsageResponse());

      await useSystemConfigStore.getState().fetchStorageUsage();

      const state = useSystemConfigStore.getState();
      expect(state.storageUsage).toHaveLength(1);
      expect(state.storageUsage[0].company_name).toBe("Acme Corp");
      expect(state.storageTotals).not.toBeNull();
      expect(state.storageTotals!.total_used_bytes).toBe(1073741824);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeStorageUsageResponse());

      await useSystemConfigStore.getState().fetchStorageUsage();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/storage/usage");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("MinIO timeout"));

      await useSystemConfigStore.getState().fetchStorageUsage();

      expect(useSystemConfigStore.getState().errors.storageUsage).toBe("MinIO timeout");
      expect(useSystemConfigStore.getState().loading.storageUsage).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // fetchQuotas()
  // -------------------------------------------------------------------------

  describe("fetchQuotas()", () => {
    it("fetches quotas and stores as map by company_id", async () => {
      mockedApiClient.get.mockResolvedValue(makeQuotasResponse());

      await useSystemConfigStore.getState().fetchQuotas();

      const state = useSystemConfigStore.getState();
      expect(state.quotas[1]).toEqual({ quota_limit_bytes: 10737418240, alert_threshold_pct: 80 });
      expect(state.quotas[2]).toEqual({ quota_limit_bytes: null, alert_threshold_pct: null });
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeQuotasResponse());

      await useSystemConfigStore.getState().fetchQuotas();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/storage/quotas");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Forbidden"));

      await useSystemConfigStore.getState().fetchQuotas();

      expect(useSystemConfigStore.getState().errors.quotas).toBe("Forbidden");
    });
  });

  // -------------------------------------------------------------------------
  // updateQuota()
  // -------------------------------------------------------------------------

  describe("updateQuota()", () => {
    it("sends PUT with data and X-Change-Reason", async () => {
      mockedApiClient.put.mockResolvedValue({});

      await useSystemConfigStore.getState().updateQuota(
        1,
        { quota_limit_bytes: 5368709120, alert_threshold_pct: 90 },
        "Increasing quota",
      );

      expect(mockedApiClient.put).toHaveBeenCalledWith(
        "/api/system-config/storage/quotas/1",
        { quota_limit_bytes: 5368709120, alert_threshold_pct: 90 },
        { changeReason: "Increasing quota" },
      );
    });

    it("updates local quotas state on success", async () => {
      mockedApiClient.put.mockResolvedValue({});
      useSystemConfigStore.setState({ quotas: { 1: { quota_limit_bytes: 1000, alert_threshold_pct: 80 } } });

      await useSystemConfigStore.getState().updateQuota(
        1,
        { quota_limit_bytes: 2000 },
        "reason",
      );

      const state = useSystemConfigStore.getState();
      expect(state.quotas[1].quota_limit_bytes).toBe(2000);
      expect(state.quotas[1].alert_threshold_pct).toBe(80); // unchanged
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.put.mockRejectedValue(new Error("Invalid threshold"));

      await expect(
        useSystemConfigStore.getState().updateQuota(1, { alert_threshold_pct: 150 }, "reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.quotas).toBe("Invalid threshold");
    });
  });

  // -------------------------------------------------------------------------
  // fetchBackupSchedule() / updateBackupSchedule()
  // -------------------------------------------------------------------------

  describe("fetchBackupSchedule()", () => {
    it("fetches backup schedule and stores it", async () => {
      mockedApiClient.get.mockResolvedValue(makeBackupSchedule());

      await useSystemConfigStore.getState().fetchBackupSchedule();

      const state = useSystemConfigStore.getState();
      expect(state.backupSchedule).not.toBeNull();
      expect(state.backupSchedule!.cron_expression).toBe("0 2 * * *");
      expect(state.backupSchedule!.human_readable).toBe("Daily at 02:00 UTC");
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeBackupSchedule());

      await useSystemConfigStore.getState().fetchBackupSchedule();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/backups/schedule");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Not found"));

      await useSystemConfigStore.getState().fetchBackupSchedule();

      expect(useSystemConfigStore.getState().errors.backupSchedule).toBe("Not found");
    });
  });

  describe("updateBackupSchedule()", () => {
    it("sends PUT with cron_expression and X-Change-Reason", async () => {
      mockedApiClient.put.mockResolvedValue(makeBackupSchedule());

      await useSystemConfigStore.getState().updateBackupSchedule("0 3 * * *", "Changing to 3am");

      expect(mockedApiClient.put).toHaveBeenCalledWith(
        "/api/system-config/backups/schedule",
        { cron_expression: "0 3 * * *" },
        { changeReason: "Changing to 3am" },
      );
    });

    it("updates backupSchedule state on success", async () => {
      const updated = { cron_expression: "0 3 * * *", human_readable: "Daily at 03:00 UTC" };
      mockedApiClient.put.mockResolvedValue(updated);

      await useSystemConfigStore.getState().updateBackupSchedule("0 3 * * *", "reason");

      expect(useSystemConfigStore.getState().backupSchedule!.human_readable).toBe("Daily at 03:00 UTC");
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.put.mockRejectedValue(new Error("Invalid cron"));

      await expect(
        useSystemConfigStore.getState().updateBackupSchedule("bad", "reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.backupSchedule).toBe("Invalid cron");
    });
  });

  // -------------------------------------------------------------------------
  // triggerBackup()
  // -------------------------------------------------------------------------

  describe("triggerBackup()", () => {
    it("sends POST with X-Change-Reason to trigger endpoint", async () => {
      mockedApiClient.post.mockResolvedValue({ task_id: "task-xyz-789" });

      await useSystemConfigStore.getState().triggerBackup("Pre-deployment backup");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/system-config/backups/trigger",
        undefined,
        { changeReason: "Pre-deployment backup" },
      );
    });

    it("stores activeBackupTaskId on success", async () => {
      mockedApiClient.post.mockResolvedValue({ task_id: "task-xyz-789" });

      await useSystemConfigStore.getState().triggerBackup("reason");

      expect(useSystemConfigStore.getState().activeBackupTaskId).toBe("task-xyz-789");
    });

    it("sets error and re-throws on concurrent backup (409)", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("Backup already running"));

      await expect(
        useSystemConfigStore.getState().triggerBackup("reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.triggerBackup).toBe("Backup already running");
    });
  });

  // -------------------------------------------------------------------------
  // fetchBackupHistory()
  // -------------------------------------------------------------------------

  describe("fetchBackupHistory()", () => {
    it("fetches backup history and stores it", async () => {
      mockedApiClient.get.mockResolvedValue(makeBackupHistory());

      await useSystemConfigStore.getState().fetchBackupHistory();

      const state = useSystemConfigStore.getState();
      expect(state.backupHistory).toHaveLength(1);
      expect(state.backupHistory[0].task_id).toBe("task-abc-123");
      expect(state.backupHistory[0].status).toBe("completed");
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeBackupHistory());

      await useSystemConfigStore.getState().fetchBackupHistory();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/backups/history");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Server error"));

      await useSystemConfigStore.getState().fetchBackupHistory();

      expect(useSystemConfigStore.getState().errors.backupHistory).toBe("Server error");
    });
  });

  // -------------------------------------------------------------------------
  // pollBackupStatus()
  // -------------------------------------------------------------------------

  describe("pollBackupStatus()", () => {
    it("fetches backup status by task_id", async () => {
      const record = {
        id: 1,
        task_id: "task-abc-123",
        backup_type: "manual" as const,
        status: "running" as const,
        started_at: "2024-06-01T02:00:00Z",
        completed_at: null,
        file_size_bytes: null,
        duration_seconds: null,
        error_message: null,
      };
      mockedApiClient.get.mockResolvedValue(record);

      await useSystemConfigStore.getState().pollBackupStatus("task-abc-123");

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/backups/status/task-abc-123");
    });

    it("clears activeBackupTaskId when status is completed", async () => {
      useSystemConfigStore.setState({ activeBackupTaskId: "task-abc-123", backupHistory: [] });
      const record = {
        id: 1,
        task_id: "task-abc-123",
        backup_type: "manual" as const,
        status: "completed" as const,
        started_at: "2024-06-01T02:00:00Z",
        completed_at: "2024-06-01T02:05:00Z",
        file_size_bytes: 52428800,
        duration_seconds: 300,
        error_message: null,
      };
      mockedApiClient.get.mockResolvedValue(record);

      await useSystemConfigStore.getState().pollBackupStatus("task-abc-123");

      expect(useSystemConfigStore.getState().activeBackupTaskId).toBeNull();
    });

    it("clears activeBackupTaskId when status is failed", async () => {
      useSystemConfigStore.setState({ activeBackupTaskId: "task-abc-123", backupHistory: [] });
      const record = {
        id: 1,
        task_id: "task-abc-123",
        backup_type: "manual" as const,
        status: "failed" as const,
        started_at: "2024-06-01T02:00:00Z",
        completed_at: null,
        file_size_bytes: null,
        duration_seconds: null,
        error_message: "pg_dump failed",
      };
      mockedApiClient.get.mockResolvedValue(record);

      await useSystemConfigStore.getState().pollBackupStatus("task-abc-123");

      expect(useSystemConfigStore.getState().activeBackupTaskId).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // fetchHealthStatus()
  // -------------------------------------------------------------------------

  describe("fetchHealthStatus()", () => {
    it("fetches health status and stores services", async () => {
      mockedApiClient.get.mockResolvedValue(makeHealthStatusResponse());

      await useSystemConfigStore.getState().fetchHealthStatus();

      const state = useSystemConfigStore.getState();
      expect(state.healthStatus).toHaveLength(2);
      expect(state.healthStatus[0].service_name).toBe("postgresql");
      expect(state.healthStatus[0].status).toBe("healthy");
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeHealthStatusResponse());

      await useSystemConfigStore.getState().fetchHealthStatus();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/health/status");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Timeout"));

      await useSystemConfigStore.getState().fetchHealthStatus();

      expect(useSystemConfigStore.getState().errors.healthStatus).toBe("Timeout");
      expect(useSystemConfigStore.getState().loading.healthStatus).toBe(false);
    });
  });

  // -------------------------------------------------------------------------
  // fetchHealthConfig() / updateHealthConfig()
  // -------------------------------------------------------------------------

  describe("fetchHealthConfig()", () => {
    it("fetches health config and stores it", async () => {
      mockedApiClient.get.mockResolvedValue(makeHealthConfig());

      await useSystemConfigStore.getState().fetchHealthConfig();

      const state = useSystemConfigStore.getState();
      expect(state.healthConfig).not.toBeNull();
      expect(state.healthConfig!.polling_interval_seconds).toBe(30);
      expect(state.healthPollingInterval).toBe(30);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeHealthConfig());

      await useSystemConfigStore.getState().fetchHealthConfig();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/health/config");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Forbidden"));

      await useSystemConfigStore.getState().fetchHealthConfig();

      expect(useSystemConfigStore.getState().errors.healthConfig).toBe("Forbidden");
    });
  });

  describe("updateHealthConfig()", () => {
    it("sends PUT with data and X-Change-Reason", async () => {
      const updated = { polling_interval_seconds: 60, degraded_threshold_seconds: 10, unreachable_timeout_seconds: 30 };
      mockedApiClient.put.mockResolvedValue(updated);

      await useSystemConfigStore.getState().updateHealthConfig(
        { polling_interval_seconds: 60 },
        "Reducing check frequency",
      );

      expect(mockedApiClient.put).toHaveBeenCalledWith(
        "/api/system-config/health/config",
        { polling_interval_seconds: 60 },
        { changeReason: "Reducing check frequency" },
      );
    });

    it("updates healthConfig and healthPollingInterval on success", async () => {
      const updated = { polling_interval_seconds: 60, degraded_threshold_seconds: 10, unreachable_timeout_seconds: 30 };
      mockedApiClient.put.mockResolvedValue(updated);

      await useSystemConfigStore.getState().updateHealthConfig({ polling_interval_seconds: 60 }, "reason");

      const state = useSystemConfigStore.getState();
      expect(state.healthConfig!.polling_interval_seconds).toBe(60);
      expect(state.healthPollingInterval).toBe(60);
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.put.mockRejectedValue(new Error("Invalid interval"));

      await expect(
        useSystemConfigStore.getState().updateHealthConfig({ polling_interval_seconds: 5 }, "reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.healthConfig).toBe("Invalid interval");
    });
  });

  // -------------------------------------------------------------------------
  // fetchServices() / fetchResourceMetrics()
  // -------------------------------------------------------------------------

  describe("fetchServices()", () => {
    it("fetches services and stores them", async () => {
      mockedApiClient.get.mockResolvedValue(makeServicesResponse());

      await useSystemConfigStore.getState().fetchServices();

      const state = useSystemConfigStore.getState();
      expect(state.services).toHaveLength(1);
      expect(state.services[0].service_name).toBe("postgresql");
      expect(state.services[0].running_state).toBe("running");
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeServicesResponse());

      await useSystemConfigStore.getState().fetchServices();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/services");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Docker socket unavailable"));

      await useSystemConfigStore.getState().fetchServices();

      expect(useSystemConfigStore.getState().errors.services).toBe("Docker socket unavailable");
    });
  });

  describe("fetchResourceMetrics()", () => {
    it("fetches resource metrics for a service and stores them", async () => {
      mockedApiClient.get.mockResolvedValue(makeResourceMetricsResponse());

      await useSystemConfigStore.getState().fetchResourceMetrics("postgresql");

      const state = useSystemConfigStore.getState();
      expect(state.resourceMetrics.postgresql).toHaveLength(1);
      expect(state.resourceMetrics.postgresql[0].cpu_percent).toBe(3.2);
    });

    it("calls correct endpoint with service name", async () => {
      mockedApiClient.get.mockResolvedValue(makeResourceMetricsResponse());

      await useSystemConfigStore.getState().fetchResourceMetrics("redis");

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/services/redis/metrics");
    });

    it("preserves metrics for other services", async () => {
      useSystemConfigStore.setState({
        resourceMetrics: { redis: [{ service_name: "redis", cpu_percent: 1.0, memory_used_mb: 64, memory_limit_mb: 256, recorded_at: "2024-06-01T12:00:00Z" }] },
      });
      mockedApiClient.get.mockResolvedValue(makeResourceMetricsResponse());

      await useSystemConfigStore.getState().fetchResourceMetrics("postgresql");

      const state = useSystemConfigStore.getState();
      expect(state.resourceMetrics.redis).toHaveLength(1);
      expect(state.resourceMetrics.postgresql).toHaveLength(1);
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("Metrics unavailable"));

      await useSystemConfigStore.getState().fetchResourceMetrics("postgresql");

      expect(useSystemConfigStore.getState().errors.resourceMetrics).toBe("Metrics unavailable");
    });
  });

  // -------------------------------------------------------------------------
  // fetchSnapshots() / rollbackToSnapshot()
  // -------------------------------------------------------------------------

  describe("fetchSnapshots()", () => {
    it("fetches snapshots and stores them with pagination", async () => {
      mockedApiClient.get.mockResolvedValue(makeSnapshotsResponse());

      await useSystemConfigStore.getState().fetchSnapshots(1);

      const state = useSystemConfigStore.getState();
      expect(state.snapshots).toHaveLength(1);
      expect(state.snapshots[0].change_reason).toBe("Updated AI model");
      expect(state.snapshotsPagination.total).toBe(1);
    });

    it("calls correct endpoint with page param", async () => {
      mockedApiClient.get.mockResolvedValue(makeSnapshotsResponse());

      await useSystemConfigStore.getState().fetchSnapshots(2);

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/snapshots?page=2&page_size=20");
    });

    it("defaults to page 1 when no page provided", async () => {
      mockedApiClient.get.mockResolvedValue(makeSnapshotsResponse());

      await useSystemConfigStore.getState().fetchSnapshots();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/snapshots?page=1&page_size=20");
    });

    it("sets error on failure", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("DB error"));

      await useSystemConfigStore.getState().fetchSnapshots();

      expect(useSystemConfigStore.getState().errors.snapshots).toBe("DB error");
    });
  });

  describe("rollbackToSnapshot()", () => {
    it("sends POST with X-Change-Reason to rollback endpoint", async () => {
      mockedApiClient.post.mockResolvedValue(makeRollbackConfirmation());

      await useSystemConfigStore.getState().rollbackToSnapshot(1, "Reverting bad config");

      expect(mockedApiClient.post).toHaveBeenCalledWith(
        "/api/system-config/snapshots/1/rollback",
        undefined,
        { changeReason: "Reverting bad config" },
      );
    });

    it("returns rollback confirmation on success", async () => {
      mockedApiClient.post.mockResolvedValue(makeRollbackConfirmation());

      const result = await useSystemConfigStore.getState().rollbackToSnapshot(1, "reason");

      expect(result.snapshot_id).toBe(1);
      expect(result.changed_categories).toContain("ai_hardware");
      expect(result.services_requiring_restart).toContain("vllm");
    });

    it("sets error and re-throws on validation failure", async () => {
      mockedApiClient.post.mockRejectedValue(new Error("Validation failed: invalid model path"));

      await expect(
        useSystemConfigStore.getState().rollbackToSnapshot(1, "reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.rollback).toBe("Validation failed: invalid model path");
    });
  });

  // -------------------------------------------------------------------------
  // Loading states and error handling
  // -------------------------------------------------------------------------

  describe("loading states and error handling", () => {
    it("sets loading true at start and false on success", async () => {
      let resolvePromise: (value: unknown) => void;
      const promise = new Promise((resolve) => { resolvePromise = resolve; });
      mockedApiClient.get.mockReturnValue(promise);

      const fetchPromise = useSystemConfigStore.getState().fetchAIHardware();

      await vi.waitFor(() => {
        expect(useSystemConfigStore.getState().loading.aiHardware).toBe(true);
      });

      resolvePromise!(makeAIHardwareConfig());
      await fetchPromise;

      expect(useSystemConfigStore.getState().loading.aiHardware).toBe(false);
    });

    it("sets loading true at start and false on error", async () => {
      mockedApiClient.get.mockRejectedValue(new Error("fail"));

      await useSystemConfigStore.getState().fetchHealthStatus();

      expect(useSystemConfigStore.getState().loading.healthStatus).toBe(false);
    });

    it("clears previous error on new request", async () => {
      useSystemConfigStore.setState({ errors: { aiHardware: "Previous error" } });
      mockedApiClient.get.mockResolvedValue(makeAIHardwareConfig());

      await useSystemConfigStore.getState().fetchAIHardware();

      expect(useSystemConfigStore.getState().errors.aiHardware).toBeNull();
    });

    it("tracks loading independently per action", async () => {
      mockedApiClient.get
        .mockResolvedValueOnce(makeAIHardwareConfig())
        .mockImplementationOnce(() => new Promise(() => {}));

      await useSystemConfigStore.getState().fetchAIHardware();
      useSystemConfigStore.getState().fetchHealthStatus();

      await vi.waitFor(() => {
        expect(useSystemConfigStore.getState().loading.aiHardware).toBe(false);
        expect(useSystemConfigStore.getState().loading.healthStatus).toBe(true);
      });
    });

    it("tracks errors independently per action", async () => {
      mockedApiClient.get
        .mockRejectedValueOnce(new Error("AI error"))
        .mockRejectedValueOnce(new Error("Health error"));

      await useSystemConfigStore.getState().fetchAIHardware();
      await useSystemConfigStore.getState().fetchHealthStatus();

      const state = useSystemConfigStore.getState();
      expect(state.errors.aiHardware).toBe("AI error");
      expect(state.errors.healthStatus).toBe("Health error");
    });
  });

  // -------------------------------------------------------------------------
  // Retention policy actions
  // -------------------------------------------------------------------------

  describe("fetchRetentionPolicy()", () => {
    it("fetches retention policy and stores it", async () => {
      mockedApiClient.get.mockResolvedValue(makeRetentionPolicy());

      await useSystemConfigStore.getState().fetchRetentionPolicy();

      const state = useSystemConfigStore.getState();
      expect(state.retentionPolicy).not.toBeNull();
      expect(state.retentionPolicy!.retention_days).toBe(30);
      expect(state.retentionPolicy!.backup_count).toBe(15);
    });

    it("calls correct endpoint", async () => {
      mockedApiClient.get.mockResolvedValue(makeRetentionPolicy());

      await useSystemConfigStore.getState().fetchRetentionPolicy();

      expect(mockedApiClient.get).toHaveBeenCalledWith("/api/system-config/backups/retention");
    });
  });

  describe("updateRetentionPolicy()", () => {
    it("sends PUT with retention_days and X-Change-Reason", async () => {
      mockedApiClient.put.mockResolvedValue({ retention_days: 60, backup_count: 30 });

      await useSystemConfigStore.getState().updateRetentionPolicy(60, "Extending retention");

      expect(mockedApiClient.put).toHaveBeenCalledWith(
        "/api/system-config/backups/retention",
        { retention_days: 60 },
        { changeReason: "Extending retention" },
      );
    });

    it("updates retentionPolicy state on success", async () => {
      mockedApiClient.put.mockResolvedValue({ retention_days: 60, backup_count: 30 });

      await useSystemConfigStore.getState().updateRetentionPolicy(60, "reason");

      expect(useSystemConfigStore.getState().retentionPolicy!.retention_days).toBe(60);
    });

    it("sets error and re-throws on failure", async () => {
      mockedApiClient.put.mockRejectedValue(new Error("Out of range"));

      await expect(
        useSystemConfigStore.getState().updateRetentionPolicy(500, "reason"),
      ).rejects.toThrow();

      expect(useSystemConfigStore.getState().errors.retentionPolicy).toBe("Out of range");
    });
  });
});
