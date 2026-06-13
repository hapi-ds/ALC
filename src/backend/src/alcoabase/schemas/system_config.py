"""Pydantic request/response schemas for system configuration endpoints.

Provides validated schemas for AI hardware settings, storage quotas,
backup configuration, health monitoring, service status, and
configuration snapshots/rollback.

References:
    - Design doc: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 2.1–2.7, 3.1–3.3, 5.1–5.6, 6.1–6.6, 7.1–7.5, 8.1–8.5,
      9.1–9.6, 10.1–10.9, 12.1–12.5, 13.1–13.5, 14.1–14.7, 15.1–15.5
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Request Schemas ---


class AIHardwareConfigUpdate(BaseModel):
    """Request body for PUT /api/system-config/ai-hardware.

    All fields are optional; only provided fields are updated.

    Attributes:
        model_chat_name: Name of the chat model.
        model_chat_path: Filesystem path to the chat model weights.
        model_chat_max_gpu_memory_gb: Maximum GPU memory allocation in GB.
        model_embedding_name: Name of the embedding model.
        model_embedding_path: Filesystem path to the embedding model weights.
        model_embedding_dimension: Vector dimension of the embedding model.
        model_ocr_name: Name of the OCR/vision model.
        model_ocr_path: Filesystem path to the OCR model weights.
        inference_mode: Operational mode for AI inference.
        gpu_device_id: CUDA device ID for GPU inference.
    """

    model_chat_name: str | None = None
    model_chat_path: str | None = None
    model_chat_max_gpu_memory_gb: int | None = Field(None, gt=0)
    model_embedding_name: str | None = None
    model_embedding_path: str | None = None
    model_embedding_dimension: int | None = Field(None, gt=0)
    model_ocr_name: str | None = None
    model_ocr_path: str | None = None
    inference_mode: Literal["gpu", "cpu", "mock"] | None = None
    gpu_device_id: int | None = Field(None, ge=0)
    vllm_chat_url: str | None = None
    vllm_embedding_url: str | None = None


class StorageQuotaUpdate(BaseModel):
    """Request body for PUT /api/system-config/storage/quotas/{company_id}.

    Attributes:
        quota_limit_bytes: Storage quota limit in bytes.
        alert_threshold_pct: Percentage threshold (1-99) for quota warning alerts.
    """

    quota_limit_bytes: int | None = Field(None, gt=0)
    alert_threshold_pct: int | None = Field(None, ge=1, le=99)


class BackupScheduleUpdate(BaseModel):
    """Request body for PUT /api/system-config/backups/schedule.

    Attributes:
        cron_expression: 5-field cron expression defining backup frequency.
    """

    cron_expression: str = Field(..., min_length=9, max_length=100)


class RetentionPolicyUpdate(BaseModel):
    """Request body for PUT /api/system-config/backups/retention.

    Attributes:
        retention_days: Number of days to retain backups (1-365).
    """

    retention_days: int = Field(..., ge=1, le=365)


class HealthCheckConfigUpdate(BaseModel):
    """Request body for PUT /api/system-config/health/config.

    Attributes:
        polling_interval_seconds: Interval between health checks (10-300s).
        degraded_threshold_seconds: Response time threshold for degraded status (1-30s).
        unreachable_timeout_seconds: Timeout for unreachable classification (5-60s).
    """

    polling_interval_seconds: int = Field(..., ge=10, le=300)
    degraded_threshold_seconds: int = Field(..., ge=1, le=30)
    unreachable_timeout_seconds: int = Field(..., ge=5, le=60)


# --- Response Schemas ---


class AIHardwareConfigResponse(BaseModel):
    """Response for GET /api/system-config/ai-hardware.

    Attributes:
        model_chat_name: Name of the chat model.
        model_chat_path: Filesystem path to the chat model weights.
        model_chat_max_gpu_memory_gb: Maximum GPU memory allocation in GB.
        model_embedding_name: Name of the embedding model.
        model_embedding_path: Filesystem path to the embedding model weights.
        model_embedding_dimension: Vector dimension of the embedding model.
        model_ocr_name: Name of the OCR/vision model.
        model_ocr_path: Filesystem path to the OCR model weights.
        inference_mode: Current operational mode for AI inference.
        gpu_device_id: CUDA device ID for GPU inference.
        vllm_chat_url: Base URL for the vLLM chat/OCR instance.
        vllm_embedding_url: Base URL for the vLLM embedding instance.
        vllm_chat_status: Connection status of the chat vLLM instance.
        vllm_embedding_status: Connection status of the embedding vLLM instance.
    """

    model_chat_name: str
    model_chat_path: str
    model_chat_max_gpu_memory_gb: int
    model_embedding_name: str
    model_embedding_path: str
    model_embedding_dimension: int
    model_ocr_name: str
    model_ocr_path: str
    inference_mode: Literal["gpu", "cpu", "mock"]
    gpu_device_id: int
    vllm_chat_url: str
    vllm_embedding_url: str
    vllm_chat_status: Literal["reachable", "unreachable"]
    vllm_embedding_status: Literal["reachable", "unreachable"]

    model_config = ConfigDict(from_attributes=True)


class VLLMStatusResponse(BaseModel):
    """Response for GET /api/system-config/ai-hardware/vllm-status.

    Attributes:
        status: Current vLLM service status.
        elapsed_time: Seconds elapsed since restart was triggered (None if not restarting).
        error: Last known error message (None if healthy).
    """

    status: Literal["running", "restarting", "error", "unreachable"]
    elapsed_time: float | None = None
    error: str | None = None


class ServiceHealthStatusResponse(BaseModel):
    """Health status for a single monitored service.

    Attributes:
        service_name: Name of the monitored service.
        status: Current health classification.
        response_time_ms: Last measured response time in milliseconds.
        last_checked: Timestamp of the last health check.
        uptime_pct_24h: Uptime percentage over the last 24 hours.
        avg_response_time_5min: Average response time over the last 5 minutes.
    """

    service_name: str
    status: Literal["healthy", "degraded", "unreachable"]
    response_time_ms: float | None = None
    last_checked: datetime
    uptime_pct_24h: float
    avg_response_time_5min: float | None = None

    model_config = ConfigDict(from_attributes=True)


class BackupRecordResponse(BaseModel):
    """Response schema for a single backup record.

    Attributes:
        id: Backup record database ID.
        task_id: Celery task ID for the backup job.
        backup_type: Whether the backup was scheduled or manually triggered.
        status: Current status of the backup task.
        started_at: Timestamp when backup execution started.
        completed_at: Timestamp when backup completed or failed.
        file_size_bytes: Size of the backup file in bytes.
        duration_seconds: Duration of the backup in seconds.
        error_message: Error message if the backup failed.
    """

    id: int
    task_id: str
    backup_type: Literal["scheduled", "manual"]
    status: Literal["queued", "running", "completed", "failed"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    file_size_bytes: int | None = None
    duration_seconds: float | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ConfigDiffItem(BaseModel):
    """A single configuration key difference between two states.

    Attributes:
        key: Dotted configuration key (e.g., "ai_hardware.model_chat_name").
        old_value: Value in the snapshot or previous state.
        new_value: Value in the current state.
    """

    key: str
    old_value: Any = None
    new_value: Any = None


class ConfigurationSnapshotResponse(BaseModel):
    """Response schema for a configuration snapshot in history list.

    Attributes:
        id: Snapshot database ID.
        created_at: Timestamp when the snapshot was created.
        created_by_name: Username of the user who triggered the change.
        change_reason: The X-Change-Reason provided at the time of change.
        is_rollback: Whether this snapshot was created by a rollback action.
        changed_keys: List of configuration keys modified in this snapshot.
    """

    id: int
    created_at: datetime
    created_by_name: str
    change_reason: str
    is_rollback: bool
    changed_keys: list[str]

    model_config = ConfigDict(from_attributes=True)


class RollbackConfirmation(BaseModel):
    """Response for POST /api/system-config/snapshots/{id}/rollback.

    Attributes:
        snapshot_id: ID of the snapshot that was restored.
        snapshot_timestamp: Timestamp of the restored snapshot.
        acting_user: Username of the user who performed the rollback.
        changed_categories: List of configuration categories that were changed.
        diff: List of configuration differences applied during rollback.
        services_requiring_restart: Services that need restart for changes to take effect.
    """

    snapshot_id: int
    snapshot_timestamp: datetime
    acting_user: str
    changed_categories: list[str]
    diff: list[ConfigDiffItem]
    services_requiring_restart: list[str]


class CompanyStorageUsageResponse(BaseModel):
    """Storage usage data for a single company.

    Attributes:
        company_id: Company database ID.
        company_name: Company display name.
        usage_bytes: Current storage usage in bytes.
        human_readable: Human-readable storage usage (e.g., "1.23 GB").
        quota_status: Current quota status classification.
        quota_limit_bytes: Configured quota limit in bytes (None if no quota).
        alert_threshold_pct: Configured alert threshold percentage (None if not set).
    """

    company_id: int
    company_name: str
    usage_bytes: int
    human_readable: str
    quota_status: Literal["normal", "quota_warning", "quota_exceeded"]
    quota_limit_bytes: int | None = None
    alert_threshold_pct: int | None = None

    model_config = ConfigDict(from_attributes=True)


class StorageTotalsResponse(BaseModel):
    """Aggregate storage usage across all companies.

    Attributes:
        total_used_bytes: Total storage used across all companies.
        total_capacity_bytes: Total available MinIO storage capacity.
        human_readable_used: Human-readable total usage (e.g., "45.67 GB").
        human_readable_capacity: Human-readable total capacity (e.g., "500.00 GB").
    """

    total_used_bytes: int
    total_capacity_bytes: int
    human_readable_used: str
    human_readable_capacity: str


class ServiceInfoResponse(BaseModel):
    """Detailed information about a running Docker service.

    Attributes:
        container_name: Docker container name.
        service_name: Logical service name (e.g., "postgresql", "redis").
        running_state: Current container state (e.g., "running", "stopped").
        version: Software version reported by the service.
        uptime: Container uptime as a human-readable string.
        cpu_percent: Current CPU usage percentage.
        memory_used_mb: Current memory usage in MB.
        memory_limit_mb: Container memory limit in MB (None if unlimited).
        host: Service host address.
        port: Service port number.
    """

    container_name: str
    service_name: str
    running_state: str
    version: str
    uptime: str
    cpu_percent: float
    memory_used_mb: float
    memory_limit_mb: float | None = None
    host: str
    port: int

    model_config = ConfigDict(from_attributes=True)


class ResourceMetricsResponse(BaseModel):
    """Resource utilization data point for a service.

    Attributes:
        service_name: Logical service name.
        cpu_percent: CPU usage percentage at the recorded time.
        memory_used_mb: Memory usage in MB at the recorded time.
        memory_limit_mb: Container memory limit in MB (None if unlimited).
        recorded_at: Timestamp when the metric was recorded.
    """

    service_name: str
    cpu_percent: float
    memory_used_mb: float
    memory_limit_mb: float | None = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)
