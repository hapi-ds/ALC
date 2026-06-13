# AlcoaBase Administrator Guide

| Field | Value |
|-------|-------|
| **Audience** | System Administrators, IT Administrators, Document Administrators |

---

## 1. System Architecture Overview

AlcoaBase runs as a Docker Compose stack with the following services:

| Service | Purpose | Port |
|---------|---------|------|
| PostgreSQL 16 | Primary database (documents, users, audit trail) | 5432 |
| MinIO | Object storage (document files, PDFs, exports) | 9000/9001 |
| OpenSearch 2.16 | Full-text + vector search engine | 9200 |
| Redis 7 | Celery task broker, caching | 6379 |
| Backend (FastAPI) | REST API, business logic | 8080 |
| Celery Worker | Background tasks (health checks, AI jobs, backups) | — |
| Frontend (React) | Web UI served via nginx | 3000 |
| vLLM | AI inference (GPU/CPU/mock modes) | 8000 |

---

## 2. Initial Setup

### 2.1 First-Time Deployment

```bash
# 1. Start all services
make up

# 2. Apply database migrations
make migrate

# 3. Run the setup wizard (creates admin, company, configures AI)
make setup

# 4. (Optional) Seed ALC corporate governance environment
make seed-alc
```

### 2.2 AI Mode Configuration

Set `MODEL_MANAGER_MODE` in `.env` before starting:

| Mode | Use Case | Requirements |
|------|----------|-------------|
| `mock` | Development/testing | None — returns placeholder responses |
| `gpu` | Production | NVIDIA GPU ≥ 24 GB VRAM + model weights |
| `cpu` | Limited hardware | ≥ 32 GB RAM (very slow) |

Switch at runtime via Admin UI: **System Config → AI Settings → Inference Mode**

### 2.3 Model Weights

Download before first GPU/CPU start:

```bash
# Chat model
huggingface-cli download Qwen/Qwen3.6-35B-A3B --local-dir llm_models/qwen3.6-35b-a3b

# Embedding model
huggingface-cli download Qwen/Qwen3-Embedding-0.6B --local-dir llm_models/qwen3-embedding-0.6b
```

---

## 3. User Management

### 3.1 Creating Users

**Admin UI:** System Config → User Management → Create User

Required fields:
- Username (unique)
- Email (unique)
- Full name
- Role assignment

A temporary password is generated automatically. The user must change it on first login.

### 3.2 Role Assignments

| Role | Capabilities |
|------|-------------|
| `system_admin` | Full access to all features including user management, system config |
| `doc_admin` | Document lifecycle management, workflow design, training management |
| `it_admin` | System configuration, health monitoring, audit trail access |
| `member` | Standard document operations (read, write, submit for review) |
| `viewer` | Read-only access to documents and reports |

### 3.3 Deactivating Users

Deactivated users cannot login but their records are preserved for audit compliance. This is a soft operation — ALCOA+ requires we never delete user records.

---

## 4. System Configuration

Navigate to **Admin → System Config** for:

### 4.1 AI Settings Tab
- View/switch inference mode (GPU/CPU/Mock)
- Monitor vLLM connectivity status
- View configured model paths and GPU allocation

### 4.2 Storage Tab
- View per-company storage usage
- Configure quota limits and alert thresholds
- Storage is backed by MinIO (S3-compatible)

### 4.3 Backups Tab
- Configure backup schedule (cron expression)
- Set retention period (days)
- Trigger manual backup
- View backup history

### 4.4 Health Tab
- Real-time status of all infrastructure services
- Uptime percentage (24h) and average response time (5min)
- Configure health check thresholds (degraded/unreachable)

### 4.5 Services Tab
- Docker container status and resource utilization
- Service connection details

---

## 5. Audit Trail

### 5.1 Viewing Events

Navigate to **Admin → Audit Trail** for a unified chronological view of all system events:
- Filter by user, date range, operation type
- Substring search across event details
- Cursor-based pagination for large datasets

### 5.2 PDF Export

For regulatory submissions:
1. Apply desired filters
2. Click **Export to PDF**
3. Exports < 10,000 events are synchronous
4. Larger exports run in background (check status via polling)
5. Download the signed PDF within 72 hours

### 5.3 What Gets Logged

Every mutating operation is recorded with:
- Who (user_id, username)
- What (operation type, record type, record id)
- When (server-side UTC timestamp)
- Why (X-Change-Reason header value)
- Where (company_id, IP address)

---

## 6. Workflow Design

### 6.1 Creating Workflows

**Admin UI:** Workflows → New Workflow

1. Name the workflow and assign a document tag (e.g., "sop", "report")
2. Use the visual BPMN editor to design states and transitions
3. Mark transitions that require:
   - Electronic signature
   - Training completion
4. Set the risk level (low/medium/high/critical)
5. Save — the workflow becomes available for documents matching the tag

### 6.2 Workflow Versioning

Editing a workflow creates a new version. Previous versions are preserved. Documents in-progress continue on their original workflow version.

---

## 7. AI Risk Framework

### 7.1 Company Risk Profiles

Each company gets a risk profile that maps AI task types to risk tiers. Customize via **Admin → AI Risk Framework**.

### 7.2 HITL Checkpoints

High-risk AI operations create checkpoints that require human review:
- Checkpoints appear in the HITL queue
- Reviewers must have `system_admin` or `doc_admin` role
- Unreviewed checkpoints expire after 72 hours (outputs invalidated)

### 7.3 Operation Logs

All AI operations are logged at tier-appropriate depth:
- **High tier:** Full input/output (up to 50K chars), all metadata
- **Medium tier:** Summary input/output, core metadata
- **Low tier:** Timestamp, user, task type only

---

## 8. Troubleshooting

### 8.1 Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| "System setup required" on all endpoints | Migrations not run or setup incomplete | `make migrate && make setup` |
| 403 on admin pages | Role mismatch in company_memberships | Check `role` field = `system_admin` |
| vLLM unreachable | Container not started or model load failed | `make vllm-gpu` and check `make vllm-logs` |
| Health check all unreachable | Celery beat not running | Verify `--beat` flag in celery-worker command |
| Documents 400 error | Company context not set | Ensure X-Company-Id header matches user membership |

### 8.2 Useful Commands

```bash
make health          # Check all service status
make vllm-logs       # View vLLM startup/inference logs
make migrate         # Apply pending migrations
make reset-db        # DESTRUCTIVE: wipe and recreate database
docker compose logs backend --tail=50   # Recent backend logs
```

### 8.3 Database Reset (Development Only)

```bash
make reset-db && make migrate && make setup
```

⚠️ **WARNING:** This destroys all data. Never use in production.

---

## 9. Security Considerations

- **Secrets:** Never commit `.env` to version control. Use strong passwords.
- **Network:** The AI network (`alcoabase-ai-net`) has no outbound internet access.
- **Signatures:** In production, configure PAdES with real certificates (`SIGNATURE_MODE=pades`).
- **Backups:** Store backup files off-system. The built-in backups are local only.
- **Updates:** Pin all Docker image versions. Test upgrades in staging first.

---

*End of Document*
