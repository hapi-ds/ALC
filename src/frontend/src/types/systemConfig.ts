// TypeScript types for admin system configuration (Phase 6.2).
// Mirrors backend Pydantic schemas in src/backend/src/alcoabase/schemas/system_config.py

// --- AI Hardware ---

export interface AIHardwareConfig {
  model_chat_name: string;
  model_chat_path: string;
  model_chat_max_gpu_memory_gb: number;
  model_embedding_name: string;
  model_embedding_path: string;
  model_embedding_dimension: number;
  model_ocr_name: string;
  model_ocr_path: string;
  inference_mode: "gpu" | "cpu" | "mock";
  gpu_device_id: number;
  vllm_chat_url: string;
  vllm_embedding_url: string;
  vllm_chat_status: "reachable" | "unreachable";
  vllm_embedding_status: "reachable" | "unreachable";
}

export interface AIHardwareUpdate {
  model_chat_name?: string;
  model_chat_path?: string;
  model_chat_max_gpu_memory_gb?: number;
  model_embedding_name?: string;
  model_embedding_path?: string;
  model_embedding_dimension?: number;
  model_ocr_name?: string;
  model_ocr_path?: string;
  inference_mode?: "gpu" | "cpu" | "mock";
  gpu_device_id?: number;
}

export interface VLLMStatus {
  status: "running" | "restarting" | "error" | "unreachable";
  elapsed_time: number | null;
  error: string | null;
}

// --- Storage Quotas ---

export interface CompanyStorageUsage {
  company_id: number;
  company_name: string;
  usage_bytes: number;
  human_readable: string;
  quota_status: "normal" | "quota_warning" | "quota_exceeded";
  quota_limit_bytes: number | null;
  alert_threshold_pct: number | null;
}

export interface StorageTotals {
  total_used_bytes: number;
  total_capacity_bytes: number;
  human_readable_used: string;
  human_readable_capacity: string;
}

export interface StorageQuotaUpdate {
  quota_limit_bytes?: number | null;
  alert_threshold_pct?: number | null;
}

// --- Backup Configuration ---

export interface BackupSchedule {
  cron_expression: string;
  human_readable: string;
}

export interface RetentionPolicy {
  retention_days: number;
  backup_count: number;
}

export interface BackupRecord {
  id: number;
  task_id: string;
  backup_type: "scheduled" | "manual";
  status: "queued" | "running" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  error_message: string | null;
}

// --- Health Monitoring ---

export interface ServiceHealthStatus {
  service_name: string;
  status: "healthy" | "degraded" | "unreachable";
  response_time_ms: number | null;
  last_checked: string;
  uptime_pct_24h: number;
  avg_response_time_5min: number | null;
}

export interface HealthCheckConfig {
  polling_interval_seconds: number;
  degraded_threshold_seconds: number;
  unreachable_timeout_seconds: number;
}

// --- Service Status ---

export interface ServiceInfo {
  container_name: string;
  service_name: string;
  running_state: string;
  version: string;
  uptime: string;
  cpu_percent: number;
  memory_used_mb: number;
  memory_limit_mb: number | null;
  host: string;
  port: number;
}

export interface ResourceMetrics {
  service_name: string;
  cpu_percent: number;
  memory_used_mb: number;
  memory_limit_mb: number | null;
  recorded_at: string;
}

// --- Configuration Snapshots & Rollback ---

export interface ConfigurationSnapshot {
  id: number;
  created_at: string;
  created_by_name: string;
  change_reason: string;
  is_rollback: boolean;
  changed_keys: string[];
}

export interface ConfigDiffItem {
  key: string;
  old_value: unknown;
  new_value: unknown;
}

export interface RollbackConfirmation {
  snapshot_id: number;
  snapshot_timestamp: string;
  acting_user: string;
  changed_categories: string[];
  diff: ConfigDiffItem[];
  services_requiring_restart: string[];
}

// --- Pagination ---

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

// --- Loading & Error State ---

export interface LoadingState {
  [key: string]: boolean;
}

export interface ErrorState {
  [key: string]: string | null;
}
