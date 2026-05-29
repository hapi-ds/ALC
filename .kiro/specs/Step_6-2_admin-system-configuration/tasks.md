# Implementation Plan: Admin Dashboard — System Configuration (Phase 6.2)

## Overview

This plan implements Phase 6.2 — Admin Dashboard System Configuration for AlcoaBase. The implementation follows a bottom-up approach: database models and Alembic migration first, then core services (SystemConfigurationService, HealthMonitor, BackupService, StorageQuotaService, ServiceRegistry), Celery tasks, the API router with all 23 endpoints, and finally the frontend (types, Zustand store, pages/components). Each task builds incrementally on previous work, ensuring no orphaned code.

## Tasks

- [x] 1. Database models, schemas, and migration
  - [x] 1.1 Create SQLAlchemy models for system configuration
    - Create file `src/backend/src/alcoabase/models/system_config.py`
    - Define `SystemConfiguration` model: id, category (String 50, unique, indexed), values (JSON), updated_at (DateTime TZ, server_default now, onupdate now), updated_by (FK users, nullable); use `AuditMixin` for SQLAlchemy-Continuum versioning
    - Define `ConfigurationSnapshot` model: id, snapshot_data (JSON), created_at (DateTime TZ, server_default now), created_by (FK users), change_reason (String 500), is_rollback (bool, default False), rollback_target_id (FK self, nullable), changed_keys (JSON, default list)
    - Define `BackupRecord` model: id, task_id (String 255, unique, indexed), backup_type (String 20), status (String 20), started_at (DateTime TZ, nullable), completed_at (DateTime TZ, nullable), file_size_bytes (int, nullable), storage_path (String 500, nullable), duration_seconds (float, nullable), error_message (nullable), triggered_by (FK users, nullable), created_at (DateTime TZ, server_default now)
    - Define `StorageQuota` model: id, company_id (FK companies, unique, indexed), quota_limit_bytes (int, nullable), alert_threshold_pct (int, nullable), updated_at, updated_by; use `AuditMixin`
    - Define `HealthCheckResult` model: id, service_name (String 50, indexed), status (String 20), response_time_ms (float, nullable), error_message (nullable), checked_at (DateTime TZ, server_default now, indexed), previous_status (String 20, nullable), is_transition (bool, default False); composite index on (service_name, checked_at)
    - Define `ResourceMetricPoint` model: id, service_name (String 50, indexed), cpu_percent (float), memory_used_mb (float), memory_limit_mb (float, nullable), recorded_at (DateTime TZ, server_default now, indexed); composite index on (service_name, recorded_at)
    - Register models in `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 1.4, 3.4, 5.1, 6.1, 7.5, 8.1, 9.3, 10.6, 10.9, 13.1, 14.1, 14.5_

  - [x] 1.2 Create Pydantic schemas for system configuration
    - Create file `src/backend/src/alcoabase/schemas/system_config.py`
    - Define request schemas: `AIHardwareConfigUpdate` (optional fields with Field validators: model_chat_name, model_chat_path, model_chat_max_gpu_memory_gb gt=0, model_embedding_name, model_embedding_path, model_embedding_dimension gt=0, model_ocr_name, model_ocr_path, inference_mode Literal["gpu","cpu","mock"], gpu_device_id ge=0)
    - Define `StorageQuotaUpdate` (quota_limit_bytes gt=0 optional, alert_threshold_pct ge=1 le=99 optional)
    - Define `BackupScheduleUpdate` (cron_expression String min_length=9 max_length=100)
    - Define `RetentionPolicyUpdate` (retention_days int ge=1 le=365)
    - Define `HealthCheckConfigUpdate` (polling_interval_seconds ge=10 le=300, degraded_threshold_seconds ge=1 le=30, unreachable_timeout_seconds ge=5 le=60)
    - Define response schemas: `AIHardwareConfigResponse`, `ServiceHealthStatusResponse`, `BackupRecordResponse`, `ConfigurationSnapshotResponse`, `RollbackConfirmation`, `CompanyStorageUsageResponse`, `StorageTotalsResponse`, `ServiceInfoResponse`, `ResourceMetricsResponse`, `VLLMStatusResponse`
    - _Requirements: 2.1–2.7, 3.1–3.3, 5.1–5.6, 6.1–6.6, 7.1–7.5, 8.1–8.5, 9.1–9.6, 10.1–10.9, 12.1–12.5, 13.1–13.5, 14.1–14.7, 15.1–15.5_

  - [x] 1.3 Create Alembic migration for system configuration tables
    - Generate migration with `alembic revision --autogenerate -m "add_system_configuration_tables"`
    - Upgrade: create `system_configurations` table, `configuration_snapshots` table, `backup_records` table, `storage_quotas` table, `health_check_results` table, `resource_metric_points` table
    - Add all indexes and constraints as defined in models
    - Data migration: seed initial configuration rows for categories "ai_hardware", "backup_schedule", "backup_retention", "health_check" with default values from .env
    - Downgrade: drop all six tables in reverse dependency order
    - _Requirements: 1.4, 14.1_

  - [x] 1.4 Write unit tests for Pydantic schema validation
    - Test field constraints: inference_mode Literal validation, gpu_memory gt=0, alert_threshold 1-99, retention_days 1-365, polling_interval 10-300, degraded_threshold 1-30, unreachable_timeout 5-60
    - Test AIHardwareConfigUpdate, StorageQuotaUpdate, BackupScheduleUpdate, RetentionPolicyUpdate, HealthCheckConfigUpdate serialization/deserialization
    - Test edge cases: boundary values, None optionals, invalid enum values
    - _Requirements: 3.2, 3.3, 6.2, 8.1, 15.1, 15.2, 15.3_

- [x] 2. Core service: SystemConfigurationService
  - [x] 2.1 Implement SystemConfigurationService
    - Create file `src/backend/src/alcoabase/services/system_config.py`
    - Implement `get_config(category, session)`: query SystemConfiguration by category, merge with .env defaults (DB overrides .env), return dict
    - Implement `update_config(category, data, user_id, reason, session)`: validate fields per category, create ConfigurationSnapshot (pre-change), UPDATE SystemConfiguration row, return ConfigUpdateResult with restart_required flag
    - Implement `create_snapshot(session)`: capture all configuration categories into single snapshot_data JSON, record changed_keys by diffing against previous snapshot
    - Implement `rollback_to_snapshot(snapshot_id, user_id, reason, session)`: load target snapshot, validate all values against current validation rules, reject entirely if any value fails (atomic), restore all categories, create new snapshot recording rollback action with rollback_target_id reference
    - Implement `get_snapshot_history(page, page_size, session)`: paginated query (20 per page default), return snapshots with user names and changed_keys
    - Implement `get_snapshot_diff(snapshot_id, session)`: compute diff between snapshot and current state, return list of ConfigDiff items
    - Implement `restart_vllm_service(user_id, reason)`: use Docker SDK to restart vLLM container with 180s timeout, record event in audit trail
    - Implement `validate_model_path(path)`: check filesystem existence of model path
    - _Requirements: 1.3, 1.4, 2.1–2.7, 3.1–3.6, 4.1–4.5, 14.1–14.7_

  - [x] 2.2 Write property test for X-Change-Reason header validation
    - **Property 2: X-Change-Reason Header Validation**
    - Generate random strings: verify accepted if non-empty (after trim) and ≤500 chars; rejected if empty, whitespace-only, or >500 chars
    - **Validates: Requirements 1.3**

  - [x] 2.3 Write property test for configuration value range validation
    - **Property 3: Configuration Value Range Validation**
    - Generate random integers for each range-constrained field, verify acceptance if and only if within defined bounds (GPU memory 1–max, alert threshold 1–99, retention 1–365, polling 10–300, degraded 1–30, unreachable 5–60)
    - **Validates: Requirements 3.3, 6.2, 8.1, 10.2, 15.1, 15.2, 15.3**

  - [x] 2.4 Write property test for inference mode enum validation
    - **Property 4: Inference Mode Enum Validation**
    - Generate random strings, verify accepted if and only if exactly "gpu", "cpu", or "mock"; all others rejected with 422
    - **Validates: Requirements 3.2**

  - [x] 2.5 Write property test for configuration diff computation
    - **Property 15: Configuration Diff Computation**
    - Generate two random configuration state dicts, verify diff returns exactly the set of keys whose values differ; keys present in one but not the other included; identical values excluded
    - **Validates: Requirements 14.2**

  - [x] 2.6 Write property test for configuration rollback round-trip
    - **Property 16: Configuration Rollback Round-Trip**
    - Generate valid config state, take snapshot, apply arbitrary valid changes, rollback to snapshot, verify resulting state identical to original snapshot
    - **Validates: Requirements 14.3**

  - [x] 2.7 Write property test for atomic rollback on validation failure
    - **Property 17: Atomic Rollback on Validation Failure**
    - Generate snapshots containing at least one value that fails current validation, attempt rollback, verify all config values unchanged (no partial application)
    - **Validates: Requirements 14.6**

  - [x] 2.8 Write unit tests for SystemConfigurationService
    - Test get_config merges DB values over .env defaults
    - Test update_config creates snapshot before applying changes
    - Test rollback_to_snapshot restores all categories atomically
    - Test rollback rejection when validation fails (no partial changes)
    - Test snapshot history pagination, diff computation
    - Test restart_vllm_service with mocked Docker SDK (success, timeout)
    - Test validate_model_path with existing and non-existing paths
    - _Requirements: 1.3, 1.4, 2.1–2.7, 3.1–3.6, 4.1–4.5, 14.1–14.7_

- [x] 3. Core service: HealthMonitor
  - [x] 3.1 Implement HealthMonitor service
    - Create file `src/backend/src/alcoabase/services/health_monitor.py`
    - Define `MONITORED_SERVICES = ["postgresql", "minio", "opensearch", "redis", "vllm"]`
    - Implement `check_all_services(session)`: execute all checks concurrently via `asyncio.gather` with 10s total timeout, store results, detect transitions
    - Implement `check_service(service_name)`: perform connection-level check per service type (pg: SELECT 1, minio: list_buckets, opensearch: cluster health, redis: PING, vllm: GET /health), measure response_time_ms
    - Implement `classify_status(response_time_ms, degraded_threshold_ms, timeout_ms)`: pure function returning "healthy" if < degraded, "degraded" if between degraded and timeout, "unreachable" if >= timeout or connection error
    - Implement `get_current_status(session)`: return latest health check result per service with uptime_pct_24h and avg_response_time_5min
    - Implement `get_service_history(service_name, limit, session)`: return last N results for a service (max 100)
    - Implement `get_uptime_percentage(service_name, hours, session)`: calculate percentage of "healthy" checks over time period
    - Implement bounded buffer logic: after storing new result, evict oldest if count > 100 per service
    - Detect status transitions: compare current status with previous, set is_transition=True and record previous_status when transitioning from "healthy" to "degraded"/"unreachable"
    - _Requirements: 10.1–10.9, 11.1–11.6_

  - [x] 3.2 Write property test for health status classification
    - **Property 11: Health Status Classification**
    - Generate random response_time_ms, degraded_threshold, and timeout values; verify classify_status returns "healthy" if response_time < degraded_threshold, "degraded" if between, "unreachable" if >= timeout or connection error; states are mutually exclusive and exhaustive
    - **Validates: Requirements 10.3, 10.4, 10.5**

  - [x] 3.3 Write property test for health check history bounded buffer
    - **Property 12: Health Check History Bounded Buffer**
    - Generate sequences of N health check results (N > 100) for a service, verify stored results never exceed 100 entries; oldest evicted when new result stored
    - **Validates: Requirements 10.6**

  - [x] 3.4 Write property test for health status transition detection
    - **Property 13: Health Status Transition Detection**
    - Generate sequences of health check results, verify transition event recorded if and only if current status differs from previous AND transition is from "healthy" to "degraded" or "unreachable"
    - **Validates: Requirements 10.9**

  - [x] 3.5 Write unit tests for HealthMonitor
    - Test check_service for each service type with mocked connections (healthy, degraded, unreachable)
    - Test classify_status pure function with boundary values
    - Test check_all_services concurrent execution within 10s
    - Test bounded buffer eviction logic
    - Test transition detection (healthy→degraded, healthy→unreachable, degraded→healthy no transition event)
    - Test get_uptime_percentage calculation
    - Test get_current_status aggregation with avg_response_time_5min
    - _Requirements: 10.1–10.9, 11.1–11.6_

- [x] 4. Core service: BackupService
  - [x] 4.1 Implement BackupService
    - Create file `src/backend/src/alcoabase/services/backup_service.py`
    - Implement `trigger_backup(user_id, reason, session)`: check is_backup_running (reject with 409 if active), create BackupRecord with status="queued", dispatch Celery task, return record
    - Implement `is_backup_running(session)`: query BackupRecord for status in ("queued", "running")
    - Implement `get_backup_history(session)`: return all BackupRecords ordered by created_at desc
    - Implement `get_backup_status(task_id)`: query BackupRecord by task_id, return current status
    - Implement `validate_cron_expression(expression)`: pure function, validate 5-field cron syntax (minute, hour, day-of-month, month, day-of-week), check range validity per field
    - Implement `cron_to_human_readable(expression)`: pure function, convert cron to human-readable string (e.g., "Daily at 02:00 UTC")
    - Implement `update_schedule(cron_expr, session)`: validate cron, update SystemConfiguration "backup_schedule" category, register with Celery beat
    - Implement `update_retention(days, session)`: validate 1-365 range, update SystemConfiguration "backup_retention" category
    - Implement `cleanup_expired_backups(session)`: query backups older than retention period, delete from MinIO, delete BackupRecords, BUT retain at least one backup regardless of age
    - _Requirements: 7.1–7.5, 8.1–8.5, 9.1–9.6_

  - [x] 4.2 Write property test for cron expression validation
    - **Property 7: Cron Expression Validation**
    - Generate random strings, verify validate_cron_expression returns True if and only if string is syntactically valid 5-field cron; invalid syntax, out-of-range values, malformed fields return False
    - **Validates: Requirements 7.1, 7.2**

  - [x] 4.3 Write property test for backup expiration logic
    - **Property 8: Backup Expiration Logic**
    - Generate backup records with random creation timestamps and retention periods in days, verify backup marked expired if and only if current_time - created_at > retention_days
    - **Validates: Requirements 8.2**

  - [x] 4.4 Write property test for minimum one backup retained
    - **Property 9: Minimum One Backup Retained**
    - Generate non-empty lists of backup records with various ages and retention periods, apply cleanup logic, verify at least one backup remains regardless of retention period
    - **Validates: Requirements 8.3**

  - [x] 4.5 Write property test for no concurrent backup executions
    - **Property 10: No Concurrent Backup Executions**
    - Generate sequences of backup trigger requests with varying active backup states, verify trigger rejected when status is "queued" or "running", accepted only when no active backup exists
    - **Validates: Requirements 9.6**

  - [x] 4.6 Write unit tests for BackupService
    - Test trigger_backup creates record and dispatches Celery task
    - Test concurrent backup rejection (409) when backup already running
    - Test validate_cron_expression with valid and invalid expressions
    - Test cron_to_human_readable conversion
    - Test update_schedule validates cron before persisting
    - Test update_retention validates range 1-365
    - Test cleanup_expired_backups deletes old backups but retains at least one
    - Test get_backup_history ordering, get_backup_status lookup
    - _Requirements: 7.1–7.5, 8.1–8.5, 9.1–9.6_

- [x] 5. Core service: StorageQuotaService
  - [x] 5.1 Implement StorageQuotaService
    - Create file `src/backend/src/alcoabase/services/storage_quota.py`
    - Implement `get_usage_per_company(session)`: use aioboto3 list_objects_v2 with prefix aggregation per company, cache results for 60s in Redis, return list of CompanyStorageUsage with company_name, usage_bytes, human_readable, quota_status
    - Implement `get_total_usage()`: aggregate all company usage + total MinIO capacity, return StorageTotals
    - Implement `set_quota(company_id, limit_bytes, session)`: upsert StorageQuota record for company
    - Implement `set_alert_threshold(company_id, threshold_pct, session)`: validate 1-99 range, upsert StorageQuota
    - Implement `compute_quota_status(usage_bytes, quota_bytes, threshold_pct)`: pure function returning "normal" if no quota or usage ≤ threshold% × quota, "quota_warning" if usage > threshold% × quota AND ≤ quota, "quota_exceeded" if usage > quota
    - Implement `format_bytes_human_readable(size_bytes)`: static pure function converting bytes to binary units (KB, MB, GB, TB) rounded to 2 decimal places
    - Handle MinIO timeout (10s) gracefully: return cached data with staleness indicator
    - _Requirements: 5.1–5.6, 6.1–6.6_

  - [x] 5.2 Write property test for human-readable byte formatting
    - **Property 5: Human-Readable Byte Formatting**
    - Generate non-negative integers representing bytes, verify format_bytes_human_readable produces string with binary units (KB, MB, GB, TB) rounded to 2 decimal places; parsing numeric portion × unit factor yields value within 0.01 of original / unit factor
    - **Validates: Requirements 5.1**

  - [x] 5.3 Write property test for quota status classification
    - **Property 6: Quota Status Classification**
    - Generate tuples of (usage_bytes, quota_limit_bytes, alert_threshold_pct), verify compute_quota_status returns "normal" if no quota OR usage ≤ threshold% × quota, "quota_warning" if usage > threshold% × quota AND ≤ quota, "quota_exceeded" if usage > quota; states mutually exclusive and exhaustive
    - **Validates: Requirements 5.3, 5.5, 6.3, 6.4**

  - [x] 5.4 Write unit tests for StorageQuotaService
    - Test get_usage_per_company with mocked aioboto3 (multiple companies, empty bucket)
    - Test get_total_usage aggregation
    - Test set_quota and set_alert_threshold upsert behavior
    - Test compute_quota_status pure function with boundary values
    - Test format_bytes_human_readable for 0, KB, MB, GB, TB ranges
    - Test MinIO timeout handling (returns cached data with staleness)
    - _Requirements: 5.1–5.6, 6.1–6.6_

- [x] 6. Core service: ServiceRegistry
  - [x] 6.1 Implement ServiceRegistry
    - Create file `src/backend/src/alcoabase/services/service_registry.py`
    - Define `DOCKER_SERVICES` mapping: postgresql→alcoabase-postgres, minio→alcoabase-minio, opensearch→alcoabase-opensearch, redis→alcoabase-redis, vllm→alcoabase-vllm, backend→alcoabase-backend, celery-worker→alcoabase-celery-worker, frontend→alcoabase-frontend
    - Implement `get_all_services()`: use Docker SDK to list containers matching DOCKER_SERVICES, return ServiceInfo with container_name, running_state, version, uptime
    - Implement `get_service_stats(container_name)`: get container stats (non-streaming), calculate cpu_percent, memory_used_mb, memory_limit_mb
    - Implement `get_resource_utilization()`: collect stats for all containers, return list of ResourceMetrics
    - Implement `restart_container(container_name)`: restart via Docker SDK with timeout, return RestartResult
    - Implement `get_container_version(container_name)`: extract version from container labels or image tag
    - Handle Docker socket unavailable gracefully: return cached data with staleness indicator
    - _Requirements: 12.1–12.5, 13.1–13.5_

  - [x] 6.2 Write property test for memory utilization warning threshold
    - **Property 14: Memory Utilization Warning Threshold**
    - Generate pairs of (memory_used_mb, memory_limit_mb) where memory_limit_mb > 0, verify warning flag set if and only if memory_used_mb / memory_limit_mb > 0.9
    - **Validates: Requirements 13.4**

  - [x] 6.3 Write unit tests for ServiceRegistry
    - Test get_all_services with mocked Docker SDK (running, stopped, missing containers)
    - Test get_service_stats CPU/memory calculation from Docker stats JSON
    - Test restart_container success and timeout scenarios
    - Test get_container_version extraction from labels/tags
    - Test Docker socket unavailable graceful degradation
    - _Requirements: 12.1–12.5, 13.1–13.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Celery tasks for system configuration
  - [x] 8.1 Implement Celery tasks for health checks, backups, and metrics
    - Create file `src/backend/src/alcoabase/tasks/system_config_tasks.py`
    - Implement `run_health_checks()`: instantiate HealthMonitor, call check_all_services, store results in DB, detect and record transitions; runs at configurable interval (default 30s)
    - Implement `run_backup(user_id, backup_type)`: update BackupRecord status to "running", execute pg_dump subprocess, compress output, upload to MinIO `backups/` prefix, update BackupRecord with file_size, duration, storage_path, status="completed"; on failure set status="failed" with error_message
    - Implement `cleanup_expired_backups()`: load retention config from DB, query expired backups, delete from MinIO, delete records, retain at least one; runs daily at 03:00 UTC
    - Implement `collect_resource_metrics()`: instantiate ServiceRegistry, collect stats for all containers, store ResourceMetricPoint records; runs at health check interval
    - Register all tasks in Celery beat schedule with appropriate intervals
    - Add dynamic schedule update: read polling_interval from DB config on each beat cycle
    - _Requirements: 7.3, 8.2, 8.3, 9.1, 9.2, 9.3, 9.5, 10.1, 10.2, 10.7, 13.1, 13.2_

  - [x] 8.2 Write unit tests for Celery tasks
    - Test run_health_checks stores results and detects transitions (mocked services)
    - Test run_backup lifecycle: queued→running→completed, queued→running→failed
    - Test cleanup_expired_backups respects retention and minimum-one-backup rule
    - Test collect_resource_metrics stores data points for all containers
    - Test dynamic schedule update reads from DB config
    - _Requirements: 7.3, 8.2, 8.3, 9.1–9.5, 10.1, 10.2, 13.1, 13.2_

- [x] 9. API router: system configuration endpoints
  - [x] 9.1 Implement system_config API router (AI hardware + vLLM endpoints)
    - Create file `src/backend/src/alcoabase/api/system_config.py`
    - Define router with prefix `/system-config`
    - Implement GET `/ai-hardware` → get AI hardware config (requires `system_config:read`)
    - Implement PUT `/ai-hardware` → update AI hardware config (requires `system_config:update`, X-Change-Reason); validate model path exists, return restart_required flag
    - Implement POST `/ai-hardware/restart-vllm` → trigger vLLM restart (requires `system_config:update`, X-Change-Reason); record in audit trail
    - Implement GET `/ai-hardware/vllm-status` → get vLLM health/restart status (requires `system_config:read`)
    - All endpoints use `Depends(require_permission("system_config", action))`
    - _Requirements: 1.1, 1.2, 1.5, 2.1–2.7, 3.1–3.6, 4.1–4.5_

  - [x] 9.2 Implement storage and quota endpoints
    - Add to `src/backend/src/alcoabase/api/system_config.py`
    - Implement GET `/storage/usage` → per-company storage usage with human-readable format (requires `system_config:read`)
    - Implement GET `/storage/quotas` → all quota configurations (requires `system_config:read`)
    - Implement PUT `/storage/quotas/{company_id}` → set quota limit and alert threshold (requires `system_config:update`, X-Change-Reason)
    - _Requirements: 5.1–5.6, 6.1–6.6_

  - [x] 9.3 Implement backup endpoints
    - Add to `src/backend/src/alcoabase/api/system_config.py`
    - Implement GET `/backups/schedule` → current backup schedule in cron + human-readable (requires `system_config:read`)
    - Implement PUT `/backups/schedule` → update backup schedule with cron validation (requires `system_config:update`, X-Change-Reason)
    - Implement GET `/backups/retention` → current retention policy (requires `system_config:read`)
    - Implement PUT `/backups/retention` → update retention policy (requires `system_config:update`, X-Change-Reason)
    - Implement POST `/backups/trigger` → trigger manual backup, reject if already running with 409 (requires `system_config:update`, X-Change-Reason)
    - Implement GET `/backups/history` → backup history list (requires `system_config:read`)
    - Implement GET `/backups/status/{task_id}` → backup task status (requires `system_config:read`)
    - _Requirements: 7.1–7.5, 8.1–8.5, 9.1–9.6_

  - [x] 9.4 Implement health monitoring endpoints
    - Add to `src/backend/src/alcoabase/api/system_config.py`
    - Implement GET `/health/status` → current health status for all services with uptime and avg response time (requires `system_config:read`)
    - Implement GET `/health/history/{service}` → health check history for a service (requires `system_config:read`)
    - Implement GET `/health/config` → current health check configuration (requires `system_config:read`)
    - Implement PUT `/health/config` → update health check parameters, apply on next cycle without restart (requires `system_config:update`, X-Change-Reason)
    - _Requirements: 10.1–10.9, 11.1–11.6, 15.1–15.5_

  - [x] 9.5 Implement service status and snapshot endpoints
    - Add to `src/backend/src/alcoabase/api/system_config.py`
    - Implement GET `/services` → all Docker services with stats, versions, connection info (requires `system_config:read`)
    - Implement GET `/services/{service}/metrics` → resource utilization history for last 60 minutes (requires `system_config:read`)
    - Implement GET `/snapshots` → paginated configuration snapshot history, 20 per page (requires `system_config:read`)
    - Implement GET `/snapshots/{id}/diff` → diff between snapshot and current state (requires `system_config:read`)
    - Implement POST `/snapshots/{id}/rollback` → rollback to snapshot with confirmation data (requires `system_config:update`, X-Change-Reason); reject atomically if validation fails
    - _Requirements: 12.1–12.5, 13.1–13.5, 14.1–14.7_

  - [x] 9.6 Register system_config router in central router
    - Add import and `include_router` call in `src/backend/src/alcoabase/api/router.py` for system_config router with prefix `/system-config`
    - _Requirements: 1.2_

  - [x] 9.7 Write property test for RBAC permission enforcement on system config endpoints
    - **Property 1: RBAC Permission Enforcement**
    - Generate users with roles lacking "system_config" permission, verify all system config endpoints return HTTP 403; generate users with "system_config" permission, verify requests not denied on permission grounds
    - **Validates: Requirements 1.1, 1.2**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Frontend: TypeScript types and Zustand store
  - [x] 11.1 Create TypeScript types for system configuration
    - Create file `src/frontend/src/types/systemConfig.ts`
    - Define interfaces: `AIHardwareConfig` (model names, paths, gpu memory, inference mode, vllm urls, vllm status), `AIHardwareUpdate`, `VLLMStatus` (status, elapsed_time, error)
    - Define interfaces: `CompanyStorageUsage` (company_id, company_name, usage_bytes, human_readable, quota_status, quota_limit_bytes, alert_threshold_pct), `StorageTotals` (total_used_bytes, total_capacity_bytes, human_readable_used, human_readable_capacity), `StorageQuotaUpdate`
    - Define interfaces: `BackupSchedule` (cron_expression, human_readable), `RetentionPolicy` (retention_days, backup_count), `BackupRecord` (id, task_id, backup_type, status, started_at, completed_at, file_size_bytes, duration_seconds, error_message)
    - Define interfaces: `ServiceHealthStatus` (service_name, status, response_time_ms, last_checked, uptime_pct_24h, avg_response_time_5min), `HealthCheckConfig` (polling_interval_seconds, degraded_threshold_seconds, unreachable_timeout_seconds)
    - Define interfaces: `ServiceInfo` (container_name, service_name, running_state, version, uptime, cpu_percent, memory_used_mb, memory_limit_mb, host, port), `ResourceMetrics` (service_name, cpu_percent, memory_used_mb, memory_limit_mb, recorded_at)
    - Define interfaces: `ConfigurationSnapshot` (id, created_at, created_by_name, change_reason, is_rollback, changed_keys), `ConfigDiffItem` (key, old_value, new_value), `RollbackConfirmation` (snapshot_id, snapshot_timestamp, acting_user, changed_categories, diff, services_requiring_restart)
    - Define `PaginationMeta`, loading/error state types
    - _Requirements: 2.1–2.7, 5.1–5.6, 7.4, 8.4, 9.2–9.4, 10.3, 11.1–11.6, 12.1–12.5, 13.3, 14.2, 14.4_

  - [x] 11.2 Create Zustand store for system configuration
    - Create file `src/frontend/src/stores/useSystemConfigStore.ts`
    - Implement state slices: aiHardware, vllmStatus, storageUsage, storageTotals, quotas, backupSchedule, retentionPolicy, backupHistory, activeBackupTaskId, healthStatus, healthConfig, healthPollingInterval, services, resourceMetrics, snapshots, snapshotsPagination, loading (Record<string, boolean>), errors (Record<string, string | null>)
    - Implement AI hardware actions: `fetchAIHardware()`, `updateAIHardware(data, reason)`, `restartVLLM(reason)`, `fetchVLLMStatus()`
    - Implement storage actions: `fetchStorageUsage()`, `fetchQuotas()`, `updateQuota(companyId, data, reason)`
    - Implement backup actions: `fetchBackupSchedule()`, `updateBackupSchedule(cron, reason)`, `fetchRetentionPolicy()`, `updateRetentionPolicy(days, reason)`, `triggerBackup(reason)`, `fetchBackupHistory()`, `pollBackupStatus(taskId)`
    - Implement health actions: `fetchHealthStatus()`, `fetchHealthHistory(service)`, `fetchHealthConfig()`, `updateHealthConfig(data, reason)`
    - Implement service actions: `fetchServices()`, `fetchServiceMetrics(service)`
    - Implement snapshot actions: `fetchSnapshots(page)`, `fetchSnapshotDiff(id)`, `rollbackToSnapshot(id, reason)`
    - All mutation actions include X-Change-Reason header via apiClient
    - Implement polling logic for health status auto-refresh at configurable interval
    - _Requirements: 2.1–2.7, 5.1–5.6, 6.1–6.6, 7.1–7.5, 8.1–8.5, 9.1–9.6, 10.1–10.9, 11.1–11.6, 12.1–12.5, 13.1–13.5, 14.1–14.7, 15.1–15.5_

  - [x] 11.3 Write unit tests for useSystemConfigStore
    - Test state transitions for all actions, error handling, loading states
    - Test X-Change-Reason header inclusion on all mutations
    - Test polling logic start/stop for health status
    - Test backup status polling lifecycle
    - Mock apiClient responses for all endpoints
    - _Requirements: 2.1, 5.1, 7.4, 9.2, 11.4_

- [x] 12. Frontend: SystemConfigPage and AI Hardware tab
  - [x] 12.1 Implement SystemConfigPage with tab layout
    - Create file `src/frontend/src/pages/admin/SystemConfigPage.tsx`
    - Implement tab-based layout with six tabs: AI Settings, Storage, Backups, Health, Services, History
    - Use shadcn/ui Tabs component for navigation
    - Each tab lazy-loads its content component
    - Add route `/admin/system-config` in router configuration
    - Add navigation link in admin sidebar (conditionally shown based on system_config permission)
    - _Requirements: 2.1, 5.1, 7.4, 9.4, 11.1, 12.1, 14.4_

  - [x] 12.2 Implement AI Hardware tab components
    - Create file `src/frontend/src/components/admin/AIHardwareForm.tsx`
    - Display current config: chat model (name, path, max GPU memory), embedding model (name, path, dimension), OCR model (name, path), inference mode, GPU device ID, vLLM URLs
    - Editable form using react-hook-form with validation (inference_mode dropdown, gpu_memory positive int)
    - On submit: prompt for X-Change-Reason, call updateAIHardware, display confirmation that vLLM restart required
    - Create file `src/frontend/src/components/admin/VLLMStatusCard.tsx`
    - Display vLLM connection status (reachable/unreachable) for chat and embedding instances
    - "Restart vLLM" button with confirmation dialog and X-Change-Reason prompt
    - While restarting: show "restarting" indicator with elapsed time counter
    - On timeout (180s): display error status with last known error
    - On success: show "running" status after health verification
    - Handle error state: display error message when config cannot be loaded
    - _Requirements: 2.1–2.7, 3.1–3.6, 4.1–4.5_

- [x] 13. Frontend: Storage and Backups tabs
  - [x] 13.1 Implement Storage tab components
    - Create file `src/frontend/src/components/admin/StorageUsageList.tsx`
    - Display list of companies: company name, usage in bytes + human-readable (binary units, 2 decimal places), quota status indicator
    - Display total storage used and total capacity (bytes + human-readable)
    - Visual progress bar per company showing usage as percentage of quota (rounded to 1 decimal place)
    - Disabled progress bar with "No quota configured" label when no quota set
    - Warning indicator (yellow/orange) when usage exceeds alert threshold
    - Error indicator when storage data unavailable (show last successful retrieval timestamp)
    - Create file `src/frontend/src/components/admin/QuotaEditForm.tsx`
    - Inline editable form per company: quota_limit_bytes, alert_threshold_pct (1-99)
    - On submit: prompt for X-Change-Reason, call updateQuota
    - _Requirements: 5.1–5.6, 6.1–6.6_

  - [x] 13.2 Implement Backups tab components
    - Create file `src/frontend/src/components/admin/BackupScheduleForm.tsx`
    - Display current schedule in cron format + human-readable description
    - Editable cron expression input with validation feedback
    - On submit: prompt for X-Change-Reason, call updateBackupSchedule
    - Display retention policy (days) with editable form, on submit call updateRetentionPolicy
    - Display current backup count
    - Create file `src/frontend/src/components/admin/BackupHistoryTable.tsx`
    - Table columns: timestamp, type (scheduled/manual badge), status (queued/running/completed/failed with color), size, duration, error message
    - Progress indicator for running backups
    - Create file `src/frontend/src/components/admin/BackupTriggerButton.tsx`
    - "Trigger Backup" button with X-Change-Reason prompt
    - Disabled state while backup is running (show active backup status)
    - Poll backup status while active
    - _Requirements: 7.1–7.5, 8.1–8.5, 9.1–9.6_

- [x] 14. Frontend: Health and Services tabs
  - [x] 14.1 Implement Health tab components
    - Create file `src/frontend/src/components/admin/HealthStatusGrid.tsx`
    - Display status card per service: service name, current status (color-coded: green=healthy, yellow=degraded, red=unreachable), uptime percentage (24h), last check timestamp, average response time (5 min)
    - Auto-refresh at configured polling interval without manual page reload
    - Alert notification when service transitions from healthy to degraded/unreachable (timestamped)
    - Create file `src/frontend/src/components/admin/HealthConfigForm.tsx`
    - Editable form: polling_interval_seconds (10-300), degraded_threshold_seconds (1-30), unreachable_timeout_seconds (5-60)
    - On submit: prompt for X-Change-Reason, call updateHealthConfig
    - Display note that changes apply on next check cycle without restart
    - _Requirements: 10.1–10.9, 11.1–11.6, 15.1–15.5_

  - [x] 14.2 Implement Services tab components
    - Create file `src/frontend/src/components/admin/ServiceInfoList.tsx`
    - Display all Docker services: container name, running state, version, connection params (host, port), uptime since last restart
    - Display resource utilization per service: CPU %, memory MB
    - Memory warning indicator when utilization > 90% of container limit
    - Display total system resource utilization (aggregate CPU + memory)
    - Create file `src/frontend/src/components/admin/ResourceUtilizationCharts.tsx`
    - Time-series line charts showing CPU and memory trends per service over last 60 minutes
    - Use a lightweight charting library (recharts or similar already in project)
    - _Requirements: 12.1–12.5, 13.1–13.5_

- [x] 15. Frontend: History tab and rollback
  - [x] 15.1 Implement History tab components
    - Create file `src/frontend/src/components/admin/SnapshotHistoryList.tsx`
    - Paginated list (20 per page): timestamp, user name, change reason, is_rollback badge, changed keys list
    - Pagination controls
    - "View Diff" button per snapshot → expand inline diff view showing old/new values per changed key
    - "Rollback" button per snapshot → open RollbackDialog
    - Create file `src/frontend/src/components/admin/RollbackDialog.tsx`
    - Confirmation dialog showing: snapshot timestamp, acting user, list of config keys that differ between current and target snapshot, affected categories, services requiring restart
    - X-Change-Reason input field (required)
    - On confirm: call rollbackToSnapshot, display result (changed categories, restart warnings)
    - On validation failure: display error indicating which key failed and why, no partial changes applied
    - _Requirements: 14.1–14.7_

  - [x] 15.2 Write frontend property tests (fast-check)
    - Create file `src/frontend/src/__tests__/system-config.property.test.ts`
    - **Property 5 (frontend)**: Byte formatting utility — generate non-negative integers, verify formatBytesHumanReadable produces correct binary unit string rounded to 2 decimal places
    - **Property 6 (frontend)**: Quota status display logic — generate (usage, quota, threshold) tuples, verify correct status classification for UI display
    - Test percentage calculation correctness for progress bars
    - _Requirements: 5.1, 5.3, 5.5_

  - [x] 15.3 Write frontend component tests
    - Create file `src/frontend/src/__tests__/SystemConfigPage.test.tsx`
    - Test SystemConfigPage tab rendering and navigation
    - Test AIHardwareForm display, validation, submit with X-Change-Reason
    - Test VLLMStatusCard status display, restart flow, timeout handling
    - Test StorageUsageList rendering, progress bars, warning indicators, error state
    - Test QuotaEditForm validation and submit
    - Test BackupScheduleForm cron display and validation
    - Test BackupHistoryTable rendering, status badges, progress indicator
    - Test BackupTriggerButton disabled state during active backup
    - Test HealthStatusGrid color coding, auto-refresh, alert notifications
    - Test HealthConfigForm validation and submit
    - Test ServiceInfoList rendering, memory warning indicator
    - Test SnapshotHistoryList pagination, diff view, rollback button
    - Test RollbackDialog confirmation flow, error display
    - _Requirements: 2.1–2.7, 4.1–4.5, 5.1–5.6, 6.1–6.6, 7.1–7.5, 8.1–8.5, 9.1–9.6, 10.1–10.9, 11.1–11.6, 12.1–12.5, 13.1–13.5, 14.1–14.7, 15.1–15.5_

- [x] 16. Integration tests
  - [x] 16.1 Write backend integration tests for system configuration API
    - Create file `src/backend/tests/integration/test_system_config_api.py`
    - Test RBAC enforcement: unauthorized user gets 403, authorized user gets 200
    - Test AI hardware CRUD: GET returns config, PUT updates with snapshot creation, invalid model path returns 422
    - Test vLLM restart endpoint: triggers restart, records audit event
    - Test storage endpoints: GET usage returns per-company data, PUT quota updates correctly
    - Test backup endpoints: GET schedule/retention, PUT schedule with valid/invalid cron, POST trigger (success + concurrent rejection 409), GET history/status
    - Test health endpoints: GET status returns all services, GET history returns bounded results, PUT config updates parameters
    - Test service endpoints: GET services returns Docker info, GET metrics returns time-series data
    - Test snapshot endpoints: GET paginated history, GET diff, POST rollback (success + validation failure)
    - Test X-Change-Reason enforcement on all mutation endpoints (missing → 400)
    - Test SQLAlchemy-Continuum version record creation on SystemConfiguration and StorageQuota updates
    - Test full configuration lifecycle: update → snapshot → update again → rollback → verify original state restored
    - _Requirements: 1.1–1.5, 2.1–2.7, 3.1–3.6, 4.1–4.5, 5.1–5.6, 6.1–6.6, 7.1–7.5, 8.1–8.5, 9.1–9.6, 10.1–10.9, 12.1–12.5, 13.1–13.5, 14.1–14.7, 15.1–15.5_

- [x] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (17 properties)
- Unit tests validate specific examples and edge cases
- Backend tests use pytest + Hypothesis; frontend tests use Vitest + Testing Library + fast-check
- All backend services use async SQLAlchemy sessions (asyncpg)
- The system_config router uses `Depends(require_permission("system_config", action))` from Phase 6.1's RBAC dependency
- AuditMiddleware automatically enforces X-Change-Reason on all `/api/system-config/*` mutations (not in exempt paths)
- SQLAlchemy-Continuum versioning is enabled via AuditMixin on SystemConfiguration and StorageQuota models
- Configuration persistence: PostgreSQL is primary store, .env provides bootstrap defaults; DB values override .env at runtime
- Docker SDK requires `/var/run/docker.sock` mounted read-only into the backend container
- Health checks run concurrently via asyncio.gather with 10s total timeout per cycle
- MinIO storage usage is cached in Redis for 60s to avoid excessive list_objects calls
- Backup files are stored in MinIO under `backups/` prefix, isolated from document storage
- The bounded buffer for health check results (100 per service) prevents unbounded DB growth
- Resource metrics are retained for 60 minutes only (rolling window)
- Celery Beat schedule for health checks and resource metrics is dynamically updated from DB config

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "3.1", "4.1", "5.1", "6.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "3.2", "3.3", "3.4", "3.5", "4.2", "4.3", "4.4", "4.5", "4.6", "5.2", "5.3", "5.4", "6.2", "6.3"] },
    { "id": 4, "tasks": ["8.1"] },
    { "id": 5, "tasks": ["8.2"] },
    { "id": 6, "tasks": ["9.1", "9.2", "9.3", "9.4", "9.5"] },
    { "id": 7, "tasks": ["9.6", "9.7"] },
    { "id": 8, "tasks": ["11.1"] },
    { "id": 9, "tasks": ["11.2", "11.3"] },
    { "id": 10, "tasks": ["12.1", "12.2"] },
    { "id": 11, "tasks": ["13.1", "13.2"] },
    { "id": 12, "tasks": ["14.1", "14.2"] },
    { "id": 13, "tasks": ["15.1", "15.2", "15.3"] },
    { "id": 14, "tasks": ["16.1"] }
  ]
}
```
