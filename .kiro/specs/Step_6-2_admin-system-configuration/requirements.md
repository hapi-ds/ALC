# Requirements Document

## Introduction

This document specifies the requirements for the Admin Dashboard — System Configuration feature (Phase 6.2) of AlcoaBase. The feature provides system administrators and IT administrators with a centralized interface to manage AI hardware settings, storage quotas, backup configuration, system health monitoring, and service status overview. All operations run within the air-gapped deployment model with no external API calls. Configuration changes are audited via X-Change-Reason and reversible. The system integrates with the existing RBAC engine from Phase 6.1, restricting access to `system_admin` and `it_admin` roles.

## Glossary

- **System_Configuration_Service**: The backend service responsible for reading, updating, and persisting system configuration settings (AI hardware, storage quotas, backup schedules) with full audit trail support.
- **Health_Monitor**: The backend service that performs lightweight periodic health checks against all infrastructure services (PostgreSQL, MinIO, OpenSearch, Redis, vLLM) and exposes aggregated status data.
- **Backup_Service**: The Celery-based async service responsible for triggering, scheduling, and managing PostgreSQL database backups with configurable retention policies.
- **Storage_Quota_Service**: The backend service that queries MinIO storage usage per company and manages advisory quota limits and alert thresholds.
- **Service_Registry**: The internal registry that tracks all running Docker Compose services, their versions, connection status, and resource utilization metrics.
- **Admin_Dashboard**: The frontend administrative interface providing system configuration, health monitoring, and service management views to authorized administrators.
- **Configuration_Snapshot**: A timestamped record of all configuration values at the moment of a change, enabling rollback to any previous state.
- **Alert_Threshold**: A configurable percentage of quota utilization that triggers a warning notification to administrators when exceeded.
- **Inference_Mode**: The operational mode of the AI model manager: "gpu" for production GPU inference, "cpu" for CPU-only inference, or "mock" for development/testing.

## Requirements

### Requirement 1: Access Control for System Configuration

**User Story:** As a system administrator, I want system configuration access restricted to authorized roles, so that only qualified personnel can modify infrastructure settings.

#### Acceptance Criteria

1. WHEN a user whose role lacks the "system_config" permission attempts to access a system configuration endpoint, THE System_Configuration_Service SHALL return HTTP 403 with an error message indicating the required permission and the action that was denied.
2. THE System_Configuration_Service SHALL enforce `require_permission("system_config", "read")` on all read endpoints and `require_permission("system_config", "update")` on all mutation endpoints.
3. WHEN a configuration change is submitted via a mutation endpoint (POST, PUT, PATCH, or DELETE), THE System_Configuration_Service SHALL require the X-Change-Reason header with a non-empty value of at most 500 characters and store the reason with the audit record.
4. THE System_Configuration_Service SHALL record all configuration changes as versioned records via SQLAlchemy-Continuum.
5. IF a request to a system configuration endpoint lacks a valid authentication token, THEN THE System_Configuration_Service SHALL return HTTP 401 before evaluating any role-based permissions.

### Requirement 2: AI Hardware Settings — View

**User Story:** As an IT administrator, I want to view current AI model configuration, so that I can verify the system is running with the correct models and resource allocation.

#### Acceptance Criteria

1. WHEN an authorized user navigates to the AI Hardware Settings page, THE Admin_Dashboard SHALL display the current chat model name, path, and maximum GPU memory allocation in GB.
2. WHEN an authorized user navigates to the AI Hardware Settings page, THE Admin_Dashboard SHALL display the current embedding model name, path, and vector dimension.
3. WHEN an authorized user navigates to the AI Hardware Settings page, THE Admin_Dashboard SHALL display the current OCR/vision model name and path.
4. WHEN an authorized user navigates to the AI Hardware Settings page, THE Admin_Dashboard SHALL display the current Inference_Mode (gpu, cpu, or mock) and GPU device ID.
5. WHEN an authorized user navigates to the AI Hardware Settings page, THE Admin_Dashboard SHALL display the vLLM service connection status as one of "reachable" or "unreachable" and the configured base URL for both the chat/OCR instance and the embedding instance.
6. IF the System_Configuration_Service fails to retrieve AI hardware settings, THEN THE Admin_Dashboard SHALL display an error message indicating the configuration could not be loaded and identify the unreachable service.
7. WHEN an authorized user navigates to the AI Hardware Settings page, THE Admin_Dashboard SHALL display configuration values reflecting the current persisted state at the time of page load without requiring manual refresh.

### Requirement 3: AI Hardware Settings — Update

**User Story:** As a system administrator, I want to update AI model configuration, so that I can switch between model profiles or adjust GPU allocation without editing environment files manually.

#### Acceptance Criteria

1. WHEN a system_admin submits updated AI hardware settings, THE System_Configuration_Service SHALL validate that the specified model path exists on the filesystem.
2. WHEN a system_admin changes the Inference_Mode, THE System_Configuration_Service SHALL accept only the values "gpu", "cpu", or "mock".
3. WHEN a system_admin updates GPU memory allocation, THE System_Configuration_Service SHALL validate that the value is a positive integer not exceeding available GPU memory.
4. WHEN AI hardware settings are updated, THE System_Configuration_Service SHALL create a Configuration_Snapshot before applying changes.
5. WHEN AI hardware settings are updated, THE Admin_Dashboard SHALL display a confirmation indicating that a vLLM service restart is required for changes to take effect.
6. IF the specified model path does not exist, THEN THE System_Configuration_Service SHALL return HTTP 422 with a descriptive validation error.

### Requirement 4: vLLM Service Restart

**User Story:** As a system administrator, I want to trigger a vLLM service restart from the dashboard, so that updated AI configuration takes effect without SSH access to the server.

#### Acceptance Criteria

1. WHEN a system_admin triggers a vLLM restart, THE System_Configuration_Service SHALL issue a Docker container restart command for the vLLM service.
2. WHILE the vLLM service is restarting, THE Admin_Dashboard SHALL display a "restarting" status indicator with elapsed time.
3. WHEN the vLLM service restart completes, THE Health_Monitor SHALL verify the service is healthy before updating the status to "running".
4. IF the vLLM service fails to restart within 180 seconds, THEN THE Admin_Dashboard SHALL display an error status with the last known error message.
5. THE System_Configuration_Service SHALL record the restart event in the audit trail with the acting user and X-Change-Reason.

### Requirement 5: Storage Quota — View Usage

**User Story:** As an IT administrator, I want to view storage usage per company, so that I can monitor disk consumption and plan capacity.

#### Acceptance Criteria

1. WHEN an authorized user navigates to the Storage Quotas page, THE Admin_Dashboard SHALL display a list of all companies with their company name, current MinIO storage usage in exact bytes, and a human-readable representation using binary units (KB, MB, GB, TB) rounded to two decimal places.
2. WHEN an authorized user navigates to the Storage Quotas page, THE Admin_Dashboard SHALL display the total storage used across all companies and the total available MinIO storage capacity, both in bytes and human-readable format.
3. WHEN a company has a configured quota limit, THE Admin_Dashboard SHALL display a visual progress indicator (bar or gauge) showing that company's usage as a percentage of its quota limit, rounded to one decimal place.
4. IF a company has no configured quota limit, THEN THE Admin_Dashboard SHALL display the progress indicator in a disabled state with a label indicating that no quota is configured.
5. WHEN a company's usage exceeds its Alert_Threshold percentage of the configured quota limit, THE Admin_Dashboard SHALL visually distinguish that company's row with a warning indicator differentiable from rows in normal status.
6. IF the Storage_Quota_Service cannot retrieve usage data from MinIO within 10 seconds, THEN THE Admin_Dashboard SHALL display an error indicator on the Storage Quotas page stating that storage data is temporarily unavailable, and SHALL display the timestamp of the last successful data retrieval.

### Requirement 6: Storage Quota — Configuration

**User Story:** As a system administrator, I want to set storage quota limits and alert thresholds per company, so that I can prevent uncontrolled storage growth and receive early warnings.

#### Acceptance Criteria

1. WHEN a system_admin sets a quota limit for a company, THE Storage_Quota_Service SHALL store the limit in bytes associated with the company ID.
2. WHEN a system_admin sets an Alert_Threshold for a company, THE Storage_Quota_Service SHALL accept a percentage value between 1 and 99.
3. WHEN a company's storage usage exceeds its Alert_Threshold percentage of the quota limit, THE Storage_Quota_Service SHALL flag the company as "quota warning" in subsequent status queries.
4. WHEN a company's storage usage exceeds its quota limit, THE Storage_Quota_Service SHALL flag the company as "quota exceeded" in subsequent status queries without blocking uploads.
5. THE Storage_Quota_Service SHALL record all quota configuration changes in the audit trail with the X-Change-Reason header value.
6. THE Admin_Dashboard SHALL display the configured quota limit and alert threshold for each company in an editable form.

### Requirement 7: Backup Configuration — Schedule

**User Story:** As a system administrator, I want to configure automated database backup schedules, so that data is protected against loss without manual intervention.

#### Acceptance Criteria

1. WHEN a system_admin configures a backup schedule, THE Backup_Service SHALL accept a cron expression defining the backup frequency.
2. THE Backup_Service SHALL validate that the cron expression is syntactically correct before accepting the configuration.
3. WHEN a backup schedule is configured, THE Backup_Service SHALL register the schedule with the Celery beat scheduler for periodic execution.
4. THE Admin_Dashboard SHALL display the current backup schedule in both cron format and a human-readable description (e.g., "Daily at 02:00 UTC").
5. WHEN a backup schedule is updated, THE System_Configuration_Service SHALL create a Configuration_Snapshot and record the change in the audit trail.

### Requirement 8: Backup Configuration — Retention Policy

**User Story:** As a system administrator, I want to configure backup retention policies, so that old backups are automatically cleaned up while maintaining sufficient recovery points.

#### Acceptance Criteria

1. WHEN a system_admin configures a retention policy, THE Backup_Service SHALL accept a retention period in days (minimum 1 day, maximum 365 days).
2. WHEN the retention period expires for a backup, THE Backup_Service SHALL delete the expired backup file from storage during the next scheduled cleanup.
3. THE Backup_Service SHALL retain at least one backup regardless of retention policy to prevent complete data loss.
4. THE Admin_Dashboard SHALL display the current retention policy and the number of backups currently stored.
5. WHEN a retention policy is updated, THE System_Configuration_Service SHALL record the change in the audit trail with the X-Change-Reason header value.

### Requirement 9: Backup — Manual Trigger and History

**User Story:** As a system administrator, I want to trigger manual backups and view backup history, so that I can create recovery points before risky operations and verify backup integrity.

#### Acceptance Criteria

1. WHEN a system_admin triggers a manual backup, THE Backup_Service SHALL dispatch an asynchronous Celery task to perform the PostgreSQL database dump.
2. WHILE a backup is in progress, THE Admin_Dashboard SHALL display a progress indicator with the backup task status (queued, running, completed, failed).
3. WHEN a backup completes, THE Backup_Service SHALL record the backup metadata: timestamp, file size, duration, and storage location.
4. THE Admin_Dashboard SHALL display a backup history table showing all backups with timestamp, size, duration, type (scheduled or manual), and status.
5. IF a backup task fails, THEN THE Backup_Service SHALL record the failure reason and THE Admin_Dashboard SHALL display the error message in the backup history.
6. THE Backup_Service SHALL prevent concurrent backup executions by rejecting a manual trigger while another backup is already running.

### Requirement 10: System Health Monitoring — Service Health Checks

**User Story:** As an IT administrator, I want to see real-time health status of all infrastructure services, so that I can detect and respond to outages quickly.

#### Acceptance Criteria

1. THE Health_Monitor SHALL perform periodic health checks against PostgreSQL, MinIO, OpenSearch, Redis, and vLLM services by verifying each service accepts and responds to a connection-level request.
2. THE Health_Monitor SHALL execute health checks at a configurable interval with a default of 30 seconds and a minimum allowed interval of 10 seconds.
3. THE Health_Monitor SHALL classify each service status as "healthy" when the service responds within the configured threshold without errors, "degraded" when the service responds but exceeds the configured response time threshold, or "unreachable" when the service fails to respond within the timeout period or returns a connection error.
4. WHEN a service response time exceeds a configurable threshold (default 5 seconds), THE Health_Monitor SHALL classify the service as "degraded".
5. WHEN a service fails to respond within a configurable timeout period (default 10 seconds) or returns a connection error, THE Health_Monitor SHALL classify the service as "unreachable".
6. THE Health_Monitor SHALL store the last 100 health check results per service for trend analysis, where each result includes the service name, timestamp, status classification, and measured response time in milliseconds.
7. THE Health_Monitor SHALL complete each health check cycle for all monitored services within 10 seconds total by executing checks concurrently.
8. THE Health_Monitor SHALL expose the current health status of all services and their stored history through an API endpoint accessible to authenticated administrators.
9. WHEN a service status transitions from "healthy" to "degraded" or "unreachable", THE Health_Monitor SHALL record the transition event including the previous status, new status, and timestamp.

### Requirement 11: System Health Monitoring — Dashboard Display

**User Story:** As an IT administrator, I want a visual health dashboard showing service status at a glance, so that I can quickly identify problems without reading logs.

#### Acceptance Criteria

1. WHEN an authorized user navigates to the System Health page, THE Admin_Dashboard SHALL display a status card for each monitored service showing current status, uptime percentage, and last check timestamp.
2. THE Admin_Dashboard SHALL use color-coded indicators: green for healthy, yellow for degraded, and red for unreachable.
3. THE Admin_Dashboard SHALL display the average response time for each service over the last 5 minutes.
4. THE Admin_Dashboard SHALL auto-refresh health data at the configured polling interval without requiring manual page reload.
5. WHEN a service transitions from healthy to degraded or unreachable, THE Admin_Dashboard SHALL display a timestamped alert notification.
6. THE Admin_Dashboard SHALL display an uptime percentage for each service calculated over the last 24 hours.

### Requirement 12: Service Status Overview — Service Information

**User Story:** As an IT administrator, I want to view detailed information about each running service, so that I can verify versions, connections, and resource consumption.

#### Acceptance Criteria

1. WHEN an authorized user navigates to the Service Status page, THE Admin_Dashboard SHALL display a list of all Docker Compose services with their container names and current running state.
2. THE Service_Registry SHALL report the software version for each service (PostgreSQL version, Redis version, OpenSearch version, vLLM version, MinIO version).
3. THE Service_Registry SHALL report the connection parameters for each service (host, port, connection pool status where applicable).
4. THE Admin_Dashboard SHALL display resource utilization per service: CPU usage percentage, memory usage in MB, and disk usage where applicable.
5. THE Admin_Dashboard SHALL display the container uptime (time since last restart) for each service.

### Requirement 13: Service Status Overview — Resource Utilization

**User Story:** As an IT administrator, I want to monitor resource utilization trends, so that I can identify capacity issues before they cause service degradation.

#### Acceptance Criteria

1. THE Service_Registry SHALL collect CPU and memory utilization metrics for each Docker container at the configured health check interval.
2. THE Service_Registry SHALL store the last 60 minutes of resource utilization data points per service for trend display.
3. THE Admin_Dashboard SHALL display a time-series chart showing CPU and memory utilization trends for each service over the last 60 minutes.
4. WHEN a service's memory utilization exceeds 90% of its container limit, THE Admin_Dashboard SHALL display a warning indicator for that service.
5. THE Admin_Dashboard SHALL display the total system resource utilization (aggregate CPU and memory across all containers).

### Requirement 14: Configuration Rollback

**User Story:** As a system administrator, I want to roll back configuration changes to a previous state, so that I can recover from misconfigurations without manual intervention.

#### Acceptance Criteria

1. THE System_Configuration_Service SHALL maintain a history of all Configuration_Snapshots, each recording the full set of configuration values, a timestamp, the acting user ID, and the X-Change-Reason provided at the time of the change.
2. WHEN a system_admin selects a Configuration_Snapshot for rollback, THE Admin_Dashboard SHALL display a confirmation prompt showing the snapshot timestamp, the acting user, and a list of configuration keys whose values differ between the current state and the selected snapshot, before proceeding with the rollback.
3. WHEN a system_admin confirms a rollback, THE System_Configuration_Service SHALL restore all configuration values to the state captured in the selected snapshot and return a response indicating which configuration categories were changed (AI hardware, storage quotas, backup schedule, health check) and whether any affected services require a restart.
4. THE Admin_Dashboard SHALL display a paginated configuration change history (20 entries per page) showing each snapshot with timestamp, user, change reason, and a list of configuration keys that were modified in that snapshot compared to the preceding snapshot.
5. WHEN a rollback is performed, THE System_Configuration_Service SHALL create a new Configuration_Snapshot recording the rollback action, the X-Change-Reason, and a reference to the target snapshot ID that was restored.
6. IF a rollback fails due to a validation error on a restored configuration value, THEN THE System_Configuration_Service SHALL reject the entire rollback without applying any partial changes and return an error message indicating which configuration key failed validation and why.
7. THE System_Configuration_Service SHALL retain Configuration_Snapshots for a minimum of 90 days.

### Requirement 15: Health Check Configuration

**User Story:** As a system administrator, I want to configure health check parameters, so that I can tune monitoring sensitivity to match the deployment environment.

#### Acceptance Criteria

1. WHEN a system_admin updates health check configuration, THE Health_Monitor SHALL accept a polling interval between 10 and 300 seconds.
2. WHEN a system_admin updates the degraded threshold, THE Health_Monitor SHALL accept a response time value between 1 and 30 seconds.
3. WHEN a system_admin updates the unreachable timeout, THE Health_Monitor SHALL accept a timeout value between 5 and 60 seconds.
4. WHEN health check configuration is updated, THE Health_Monitor SHALL apply the new parameters on the next check cycle without requiring a service restart.
5. THE System_Configuration_Service SHALL record health check configuration changes in the audit trail with the X-Change-Reason header value.
