# Admin Dashboard — System Configuration Guide

This guide covers the System Configuration page available to **System Administrators** and **IT Administrators**. It provides centralized management of AI hardware settings, storage quotas, backup configuration, health monitoring, and service status — all within the air-gapped deployment model.

## Accessing System Configuration

Navigate to **Admin → System Configuration** from the sidebar, or visit `/admin/system-config` directly. The page requires the `system_config` permission (granted to `system_admin` and `it_admin` roles).

The interface is organized into six tabs:

| Tab | Purpose |
|-----|---------|
| AI Settings | Manage AI model paths, GPU allocation, inference mode, vLLM status |
| Storage | View per-company storage usage, configure quotas and alert thresholds |
| Backups | Schedule automated backups, set retention policies, trigger manual backups |
| Health | Monitor infrastructure service health, configure check parameters |
| Services | View Docker container status, resource utilization, and version info |
| History | Browse configuration change history, view diffs, rollback to previous states |

---

## AI Settings Tab

### Viewing Configuration

Displays the current AI model configuration including:
- **Chat Model** — name, filesystem path, max GPU memory allocation
- **Embedding Model** — name, path, vector dimension
- **OCR/Vision Model** — name, path
- **Inference Mode** — `gpu` (production), `cpu` (fallback), or `mock` (development)
- **GPU Device ID** — CUDA device for inference
- **vLLM Connection** — base URLs and live reachability status for both chat and embedding instances

### Updating Configuration

1. Edit any field in the form
2. Click **Save Changes**
3. Provide a change reason in the audit dialog (required for ALCOA+ compliance)
4. A "restart required" banner appears if vLLM-related fields were changed

### Restarting vLLM

After changing model paths or inference mode, click **Restart vLLM** on the status card. The service restarts with a 180-second timeout. An elapsed time counter shows progress, and the status auto-refreshes every 5 seconds until the service is healthy again.

---

## Storage Tab

### Viewing Usage

Shows per-company MinIO storage consumption with:
- Company name and usage in bytes + human-readable format (e.g., "5.23 GB")
- Visual progress bar showing usage as a percentage of the configured quota
- Color-coded status: **Normal** (green), **Warning** (amber), **Exceeded** (red)
- Aggregate totals across all companies

Data is cached for 60 seconds. If MinIO is unreachable, stale cached data is displayed with a staleness indicator.

### Configuring Quotas

1. Select a company from the dropdown
2. Set the **Quota Limit** in GB (leave empty for unlimited)
3. Set the **Alert Threshold** percentage (1–99) — triggers a warning indicator when usage exceeds this percentage of the quota
4. Click **Save Quota** and provide a change reason

Quotas are advisory — they do not block uploads but provide visual warnings to administrators.

---

## Backups Tab

### Backup Schedule

Displays the current automated backup schedule in both cron format and human-readable description (e.g., "Daily at 02:00 UTC"). Edit the cron expression to change the schedule.

### Retention Policy

Shows how many days backups are retained and the current backup count. Expired backups are automatically cleaned up daily at 03:00 UTC. At least one backup is always retained regardless of retention period.

### Manual Backup

Click **Trigger Manual Backup** to start an immediate PostgreSQL database dump. The backup is compressed with gzip and uploaded to MinIO. A progress indicator shows the backup status (queued → running → completed/failed). Only one backup can run at a time — concurrent attempts are rejected with a 409 error.

### Backup History

A table showing all backups with timestamp, type (scheduled/manual), status, file size, duration, and any error messages.

---

## Health Tab

### Service Health Grid

Displays real-time health status for all monitored infrastructure services:
- **PostgreSQL** — connection check via `SELECT 1`
- **MinIO** — bucket listing check
- **OpenSearch** — cluster health endpoint
- **Redis** — PING command
- **vLLM** — `/health` endpoint

Each service card shows:
- Color-coded status indicator (green/yellow/red)
- Uptime percentage over the last 24 hours
- Average response time over the last 5 minutes
- Last check timestamp

The grid auto-refreshes at the configured polling interval.

### Health Check Configuration

Tune monitoring sensitivity:
- **Polling Interval** (10–300 seconds) — how often checks run
- **Degraded Threshold** (1–30 seconds) — response time above this marks a service as "degraded"
- **Unreachable Timeout** (5–60 seconds) — no response within this time marks "unreachable"

Changes apply on the next check cycle without requiring a service restart.

---

## Services Tab

### Service Information

A table of all Docker Compose services showing:
- Service name and container name
- Running state (running, exited, not found)
- Software version (from container labels or image tags)
- Container uptime
- CPU usage percentage
- Memory usage with container limit and 90% warning indicator

### Resource Utilization Charts

Select a service to view CPU and memory trends over the last 60 minutes as sparkline charts. A red dashed line indicates the container memory limit. An amber warning icon appears when memory usage exceeds 90% of the limit.

---

## History Tab

### Configuration Change History

A paginated list (20 per page) of all configuration changes showing:
- Timestamp and acting user
- Change reason (from X-Change-Reason header)
- Rollback badge (if the change was a rollback operation)
- List of changed configuration keys

### Viewing Diffs

Click the **Diff** button on any snapshot to expand an inline view showing the old value (from the snapshot) and current value for each changed key.

### Rolling Back

1. Click **Rollback** on any snapshot
2. Review the diff preview showing what will change
3. Enter a change reason
4. Click **Confirm Rollback**

Rollback is atomic — if any value in the snapshot fails current validation rules, the entire rollback is rejected without applying partial changes. After a successful rollback, the system reports which configuration categories changed and whether any services require a restart.

---

## Audit Trail

All configuration changes are fully audited:
- Every mutation requires an **X-Change-Reason** header (enforced by the API)
- Configuration models use SQLAlchemy-Continuum for automatic versioning
- Pre-change snapshots are created before every update
- Rollback operations create new snapshots referencing the target

---

## API Endpoints

All endpoints are prefixed with `/api/system-config`. Read endpoints require `system_config:read`, mutation endpoints require `system_config:update`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ai-hardware` | Get AI hardware configuration |
| PUT | `/ai-hardware` | Update AI hardware configuration |
| POST | `/ai-hardware/restart-vllm` | Trigger vLLM container restart |
| GET | `/ai-hardware/vllm-status` | Get vLLM health/restart status |
| GET | `/storage/usage` | Get per-company storage usage |
| GET | `/storage/quotas` | Get all quota configurations |
| PUT | `/storage/quotas/{company_id}` | Set quota limit and threshold |
| GET | `/backups/schedule` | Get current backup schedule |
| PUT | `/backups/schedule` | Update backup schedule (cron) |
| GET | `/backups/retention` | Get retention policy |
| PUT | `/backups/retention` | Update retention policy |
| POST | `/backups/trigger` | Trigger manual backup |
| GET | `/backups/history` | Get backup history |
| GET | `/backups/status/{task_id}` | Get backup task status |
| GET | `/health/status` | Get current health status |
| GET | `/health/history/{service}` | Get health check history |
| GET | `/health/config` | Get health check configuration |
| PUT | `/health/config` | Update health check configuration |
| GET | `/services` | Get all service info + stats |
| GET | `/services/{service}/metrics` | Get resource utilization history |
| GET | `/snapshots` | Get configuration snapshot history |
| GET | `/snapshots/{id}/diff` | Get diff for a snapshot |
| POST | `/snapshots/{id}/rollback` | Rollback to a snapshot |

---

## Troubleshooting

| Issue | Resolution |
|-------|-----------|
| Storage data shows "stale" | MinIO is unreachable. Check the MinIO container status in the Services tab. |
| vLLM restart times out (180s) | Check Docker logs: `docker logs alcoabase-vllm`. The model may be too large for available GPU memory. |
| Health checks all "unreachable" | Verify the backend container can reach other services on the Docker network. Check `docker network inspect`. |
| Rollback rejected with validation error | The snapshot contains values that no longer pass validation (e.g., a model path that was deleted). Review the error message for the specific failing key. |
| Backup trigger returns 409 | A backup is already queued or running. Wait for it to complete or check the backup history for stuck jobs. |
