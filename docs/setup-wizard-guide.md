# Setup Wizard User Guide

## Overview

The Setup Wizard is the first-run initialization flow for AlcoaBase. It runs exactly once on a fresh deployment and guides the deploying administrator through creating the Root Admin account, establishing the Initial Company (tenant), configuring the AI Hardware Mode, and optionally seeding demo data.

Until the Setup Wizard is completed, the system blocks all non-setup API access (returning HTTP 503), ensuring the platform is properly initialized before any regulated operations begin. After completion, the setup endpoints become permanently inaccessible (HTTP 403).

### Setup Flow Summary

1. **First-Run Detection** — The Setup Guard detects the system is uninitialized.
2. **Root Admin Creation** — Create the initial administrator account.
3. **Initial Company Creation** — Establish the first tenant organization.
4. **AI Hardware Mode Selection** — Configure the inference backend.
5. **Demo Data Seeding** (optional) — Load sample content for evaluation.
6. **Setup Completion** — Finalize and lock the wizard permanently.

---

## Prerequisites

### Required Infrastructure

The following services must be running and accessible before starting the Setup Wizard:

| Service | Purpose | Default Endpoint |
|---------|---------|-----------------|
| **PostgreSQL** | Primary database for users, companies, setup state | `localhost:5432` |
| **Redis** | Celery task broker | `localhost:6379` |
| **MinIO** | S3-compatible object storage for documents | `localhost:9000` |
| **OpenSearch** | Vector storage and hybrid search | `localhost:9200` |
| **vLLM** (optional) | Local LLM inference server | `localhost:8000` |

> **Note:** vLLM is only required if you plan to select "gpu" or "cpu" as the AI Hardware Mode. If you select "mock" mode, vLLM connectivity is not validated.

### Environment Variables

Configure the following environment variables in your `.env` file before starting the application:

```bash
# Database (PostgreSQL) — required
DATABASE_URL=postgresql+asyncpg://alcoabase:changeme_postgres@localhost:5432/alcoabase

# MinIO (Object Storage) — required
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=alcoabase
MINIO_SECRET_KEY=changeme_minio
MINIO_BUCKET=alcoabase

# Redis (Task Broker) — required
REDIS_URL=redis://:changeme_redis@localhost:6379/0

# OpenSearch (Vector Search) — required
OPENSEARCH_URL=http://localhost:9200

# vLLM (LLM Inference) — required for gpu/cpu mode
VLLM_BASE_URL=http://localhost:8000

# Application Security — required
SECRET_KEY=changeme_secret_key_generate_a_random_value

# Model Manager Mode — initial default (overridden during setup)
MODEL_MANAGER_MODE=mock
```

> **Security:** Replace all `changeme_*` values with strong, randomly generated secrets before deploying. The `SECRET_KEY` is used for JWT token signing and must be kept confidential.

### Network Connectivity

- The AlcoaBase application must be able to reach PostgreSQL, Redis, MinIO, and OpenSearch on their configured endpoints.
- If using "gpu" or "cpu" AI Hardware Mode, the vLLM endpoint must be reachable from the application container.
- The client (browser or API consumer) must be able to reach the AlcoaBase API server.

### Access Credentials

- PostgreSQL credentials are embedded in `DATABASE_URL`.
- MinIO credentials are set via `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`.
- Redis password is embedded in `REDIS_URL`.
- No pre-existing user credentials are needed — the Root Admin account is created during setup.

---

## Step-by-Step Instructions

### Step 0: First-Run Detection

When the AlcoaBase application starts, the Setup Guard middleware queries the `setup_status` table in the database:

- If no `setup_status` record exists, or the record has `is_complete = false`, the system is treated as **uninitialized**.
- If a `setup_status` record exists with `is_complete = true`, the system operates normally.

While uninitialized:
- All API requests to non-setup endpoints receive an HTTP **503** response.
- Only `/api/v1/setup/**`, `/health`, `/docs`, and `/openapi.json` are accessible.

**Check the current setup status:**

```bash
curl -X GET http://localhost:8000/api/v1/setup/status
```

**Response (fresh deployment):**

```json
{
  "is_complete": false,
  "admin_created": false,
  "company_created": false,
  "ai_mode_configured": false,
  "demo_data_seeded": false
}
```

---

### Step 1: Root Admin Creation

Create the Root Admin account — the initial administrator with full system-level privileges across all tenants.

**Endpoint:** `POST /api/v1/setup/admin`
**Authentication:** None required (no user exists yet)

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/setup/admin \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "SecureP@ss2024!",
    "full_name": "System Administrator"
  }'
```

**Password Policy requirements:**
- Minimum 12 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one special character (non-alphanumeric)

**Successful Response (201 Created):**

```json
{
  "user_id": 1,
  "username": "admin",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

> **Important:** Save the `access_token` value. It is required as a Bearer token for all subsequent setup steps.

---

### Step 2: Initial Company Creation

Create the Initial Company — the first tenant organization that provides context for documents and users.

**Endpoint:** `POST /api/v1/setup/company`
**Authentication:** Bearer token from Step 1

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/setup/company \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "display_name": "Acme Pharmaceuticals",
    "slug": "acme-pharma",
    "regulatory_framework": "GMP"
  }'
```

**Field details:**
- `display_name` (required): Human-readable company name (1–300 characters).
- `slug` (optional): URL-safe identifier. If omitted, one is auto-generated from the display name. Must contain only lowercase letters, digits, and hyphens.
- `regulatory_framework` (required): The regulatory standard the company operates under (e.g., "GMP", "GLP", "GCP", "GDP").

**Successful Response (201 Created):**

```json
{
  "company_id": 1,
  "slug": "acme-pharma",
  "display_name": "Acme Pharmaceuticals"
}
```

The Root Admin is automatically assigned as a Company Admin of the Initial Company.

---

### Step 3: AI Hardware Mode Selection

Configure how the AI inference backend operates. This determines whether the model manager uses GPU acceleration, CPU-only inference, or mock responses.

**Endpoint:** `POST /api/v1/setup/ai-mode`
**Authentication:** Bearer token from Step 1

**Request:**

```bash
curl -X POST http://localhost:8000/api/v1/setup/ai-mode \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "mode": "gpu"
  }'
```

**Available modes:**

| Mode | Description | Connectivity Check |
|------|-------------|-------------------|
| `gpu` | Production GPU inference via vLLM | Yes — validates vLLM endpoint is reachable |
| `cpu` | CPU-only inference via vLLM | Yes — validates vLLM endpoint is reachable |
| `mock` | Development/testing with mock responses | No — skips connectivity validation |

**Successful Response (200 OK):**

```json
{
  "mode": "gpu",
  "connectivity_warning": null
}
```

**Response with connectivity warning:**

```json
{
  "mode": "gpu",
  "connectivity_warning": "vLLM GPU endpoint unreachable at http://localhost:8000. The service may need to be started separately."
}
```

> **Note:** Connectivity warnings are non-blocking. The AI Hardware Mode is saved even if the vLLM service is not currently reachable. You can start the vLLM service later.

---

### Step 4: Demo Data Seeding (Optional)

Optionally seed the platform with sample documents, templates, virtual folders, and workflow definitions for evaluation purposes.

Demo data seeding is controlled by the `seed_demo_data` flag in the setup completion request (Step 5). If you want demo data, set it to `true`; otherwise set it to `false` or omit it.

**What gets seeded:**
- Sample documents within the Initial Company scope
- Document templates appropriate to the regulatory framework
- Virtual folder structure
- Sample workflow definitions
- All seeded records are tagged with `is_demo_data = true` for future identification and removal

---

### Step 5: Setup Completion

Finalize the Setup Wizard. This step validates that all required steps (Root Admin creation, Initial Company creation, AI Hardware Mode selection) are complete, optionally seeds demo data, and permanently locks the setup endpoints.

**Endpoint:** `POST /api/v1/setup/complete`
**Authentication:** Bearer token from Step 1

**Request (with demo data):**

```bash
curl -X POST http://localhost:8000/api/v1/setup/complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "seed_demo_data": true
  }'
```

**Request (without demo data):**

```bash
curl -X POST http://localhost:8000/api/v1/setup/complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "seed_demo_data": false
  }'
```

**Successful Response (200 OK):**

```json
{
  "message": "Setup completed successfully",
  "completed_at": "2024-01-15T10:30:00Z"
}
```

After completion:
- The Setup Status is set to complete with a recorded timestamp and Root Admin identifier.
- The Setup Guard immediately allows all normal API traffic without requiring an application restart.
- All setup endpoints (`/api/v1/setup/**`) return HTTP **403** permanently.
- This action is **irreversible** — no API endpoint exists to reset the Setup Status.

---

## Troubleshooting

### HTTP 503 — "System setup required"

**Symptom:** All non-setup API requests return:

```json
{
  "detail": "System setup required",
  "setup_url": "/api/v1/setup/"
}
```

**Cause:** The system is uninitialized. The Setup Wizard has not been completed.

**Resolution:**
1. Check the current setup progress: `GET /api/v1/setup/status`
2. Complete the remaining setup steps as described above.
3. Once `POST /api/v1/setup/complete` succeeds, normal API access is restored immediately.

---

### HTTP 403 — "Setup already completed"

**Symptom:** Requests to `/api/v1/setup/**` endpoints return:

```json
{
  "detail": "Setup already completed"
}
```

**Cause:** The Setup Wizard has already been completed. Setup endpoints are permanently locked.

**Resolution:** This is expected behavior. The setup flow is designed to run exactly once. Use the normal application endpoints for ongoing administration. The Setup Status cannot be reset through the API.

---

### Password Validation Errors (HTTP 422)

**Symptom:** The `POST /api/v1/setup/admin` request is rejected with a validation error.

**Example response:**

```json
{
  "detail": "Password does not meet policy requirements",
  "error_code": "PASSWORD_POLICY_VIOLATION",
  "violations": [
    "Password must be at least 12 characters",
    "Password must contain at least one uppercase letter",
    "Password must contain at least one special character"
  ]
}
```

**Resolution:** Ensure the password meets all Password Policy requirements:
- At least 12 characters long
- Contains at least one uppercase letter (A–Z)
- Contains at least one lowercase letter (a–z)
- Contains at least one digit (0–9)
- Contains at least one special character (e.g., `!@#$%^&*`)

---

### Slug Validation Errors (HTTP 422)

**Symptom:** The `POST /api/v1/setup/company` request is rejected due to an invalid slug.

**Example response:**

```json
{
  "detail": "Invalid slug format",
  "error_code": "INVALID_SLUG",
  "violations": [
    "Slug must contain only lowercase letters, digits, and hyphens"
  ]
}
```

**Resolution:**
- Use only lowercase letters (`a-z`), digits (`0-9`), and hyphens (`-`).
- Do not start or end with a hyphen.
- Do not use consecutive hyphens.
- Alternatively, omit the `slug` field entirely and let the system auto-generate one from the `display_name`.

---

### Connectivity Warnings for AI Hardware Mode

**Symptom:** The `POST /api/v1/setup/ai-mode` response includes a `connectivity_warning`:

```json
{
  "mode": "gpu",
  "connectivity_warning": "vLLM GPU endpoint unreachable at http://localhost:8000. The service may need to be started separately."
}
```

**Cause:** The vLLM inference server is not reachable at the configured `VLLM_BASE_URL`.

**Resolution:**
- This warning is **non-blocking** — the AI Hardware Mode is saved regardless.
- Verify the vLLM service is running: `curl http://localhost:8000/health`
- Check the `VLLM_BASE_URL` environment variable points to the correct host and port.
- If running in Docker, ensure the vLLM container is on the same network as the AlcoaBase application.
- If you do not have GPU/CPU inference available yet, select `mock` mode for development and change it later via application configuration.

---

### Interrupted Setup Resumption

**Symptom:** The setup process was interrupted (e.g., network failure, container restart) and you need to resume.

**Resolution:**

1. **Check current progress:**

```bash
curl -X GET http://localhost:8000/api/v1/setup/status
```

The response shows which steps are already complete:

```json
{
  "is_complete": false,
  "admin_created": true,
  "company_created": true,
  "ai_mode_configured": false,
  "demo_data_seeded": false
}
```

2. **Resume from the next incomplete step.** In this example, proceed with AI Hardware Mode selection (Step 3).

3. **If you lost the access token:** You will need to re-authenticate. Since the Root Admin already exists, use the standard login endpoint (if available) or check application logs for the token issued during admin creation.

> **Note:** The Setup Status is stored in a dedicated database table and survives application restarts and container re-creation. Partial progress is never lost.

---

### Conflict Errors (HTTP 409)

**Symptom:** A setup step returns a 409 Conflict error.

**Examples:**

```json
{"detail": "Root admin account already exists", "error_code": "ADMIN_ALREADY_EXISTS"}
```

```json
{"detail": "Initial company already exists", "error_code": "COMPANY_ALREADY_EXISTS"}
```

**Cause:** The step has already been completed successfully. This is the idempotency guard preventing duplicate records.

**Resolution:** Skip this step and proceed to the next one. Use `GET /api/v1/setup/status` to determine which steps remain.

---

### Incomplete Setup Steps (HTTP 400)

**Symptom:** The `POST /api/v1/setup/complete` request is rejected:

```json
{
  "detail": "Cannot complete setup: required steps are incomplete",
  "error_code": "SETUP_INCOMPLETE"
}
```

**Cause:** Not all required steps have been completed before attempting to finalize.

**Resolution:** Check `GET /api/v1/setup/status` and complete any steps where the corresponding field is `false`. All three required steps (admin creation, company creation, AI mode configuration) must be complete before calling the completion endpoint.

---

## Glossary Reference

| Term | Definition |
|------|-----------|
| **Setup Wizard** | The first-run initialization flow that configures AlcoaBase before normal operation. |
| **Root Admin** | The initial administrator account with full system-level privileges across all tenants. |
| **Initial Company** | The first Company (tenant) entity created during setup. |
| **AI Hardware Mode** | The operational mode for the model manager: "gpu", "cpu", or "mock". |
| **Setup Guard** | The middleware that blocks all non-setup API access while the system is uninitialized. |
| **Setup Status** | A persistent database flag indicating whether the Setup Wizard has been completed. |
| **Demo Seed** | Optional sample data loaded during setup for evaluation purposes. |
| **Password Policy** | Complexity rules for passwords: min 12 chars, uppercase, lowercase, digit, special character. |
