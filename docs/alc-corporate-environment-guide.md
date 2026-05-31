# ALC Corporate Environment Setup Guide

## Overview

The ALC Corporate Environment Setup provisions a dedicated "AlcoaBase Corporate" tenant within the multi-tenancy framework. This tenant serves as:

1. A canonical reference environment demonstrating all platform capabilities
2. An internal management hub for ALC corporate operations and governance
3. The home tenant for governance documents (URS, AI Regulatory Guidelines, User Guides, Admin Guides)
4. A standardized configuration baseline for a software/platform company

The environment is created via a dedicated seeding mechanism that is **idempotent** (safe to run multiple times) and **atomic** (all-or-nothing — partial failures leave no orphaned data).

---

## Prerequisites

- AlcoaBase must be running with the Setup Wizard completed (Phase 1.2)
- A system administrator account must exist
- The database must be accessible

---

## Running the Seed

### Option 1: CLI Command

The recommended approach for initial setup or scripted deployments:

```bash
cd src/backend
uv run python -m alcoabase.scripts.seed_alc_corporate
```

On success, the command prints a JSON report to stdout and exits with code 0:

```json
{
  "company_id": 2,
  "company_slug": "alc-corporate",
  "users_created": ["alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"],
  "users_skipped": [],
  "folders_created": ["Governance — User Requirement Specifications", "..."],
  "folders_skipped": [],
  "risk_profile_created": true,
  "regulatory_baseline_created": true,
  "audit_config_created": true,
  "agents_activated": ["Master Auditor", "..."],
  "agents_skipped": [],
  "workflow_created": true,
  "total_duration_ms": 450
}
```

On failure, error details are printed to stderr and the exit code is 1. No partial data is left in the database.

### Option 2: REST API

For programmatic access from admin dashboards or automation scripts:

```
POST /api/admin/seed-alc-corporate
```

**Required headers:**

| Header | Value |
|--------|-------|
| `Authorization` | `Bearer {token}` (system_administrator role) |
| `X-User-Id` | Your user ID |
| `X-Company-Id` | Your current company ID |
| `X-Change-Reason` | Reason for the operation (audit trail) |

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Success — returns `SeedReport` JSON |
| 400 | Missing `X-Change-Reason` header |
| 401 | Not authenticated |
| 403 | Insufficient permissions (requires system_administrator) |
| 500 | Seeding failed — returns error details |

---

## What Gets Created

### 1. ALC Company Entity

| Attribute | Value |
|-----------|-------|
| Slug | `alc-corporate` (reserved, cannot be used by other tenants) |
| Display Name | AlcoaBase Corporate |
| Regulatory Framework | ISO_27001 |
| Audit Config | review_quorum: 2, auto_audit_on_upload: true, severity_threshold: medium |

### 2. Corporate User Pool

| Username | Role | Email |
|----------|------|-------|
| `alc-it-admin` | system_administrator | it-admin@alc.local |
| `alc-doc-admin` | document_administrator | doc-admin@alc.local |
| `alc-quality-mgr` | quality_manager | quality@alc.local |
| `alc-user` | user | user@alc.local |

All accounts are created with the password from the `ALC_SEED_DEFAULT_PASSWORD` environment variable (default: `AlcCorp2024!`). Change this immediately in production.

The root admin user (created during Setup Wizard) also receives a membership in the ALC company if not already present.

### 3. Regulatory Baseline

Two `SystemConfiguration` rows are created:

- **alc_regulatory_baseline**: ISO_27001, ISO_9001, EU_AI_Act frameworks; 10-year document retention; signature and training requirements; 7-year audit log retention; 365-day review cycle
- **alc_audit_config**: review_quorum 2, auto_audit_on_upload enabled, medium severity threshold, ALC-GOV default workflow tag

### 4. Governance Folder Structure

Six virtual folders for organizing governance documents:

| Folder | Tag Filter |
|--------|-----------|
| Governance — User Requirement Specifications | URS, ALC-GOV |
| Governance — AI Regulatory Guidelines | AI-Guidelines, ALC-GOV |
| Governance — User Guides | User-Guide, ALC-GOV |
| Governance — Admin Guides | Admin-Guide, ALC-GOV |
| Governance — Risk Framework | Risk-Framework, ALC-GOV |
| Governance — All Documents | ALC-GOV |

### 5. AI Risk Profile

A `CompanyRiskProfile` named "ALC Corporate Risk Profile" is created with:
- Regulatory frameworks: ISO_27001, ISO_9001, EU_AI_Act
- No tier overrides (uses system defaults for all 8 AI task types)

### 6. Agent Activations

All globally defined AI agent archetypes are activated for the ALC company with default configurations.

### 7. Governance Workflow

A BPMN workflow definition named "ALC Governance Document Lifecycle" with document tag `ALC-GOV`:

```
Draft → Review → Approved → InTraining → Active → Retired
```

- Signature required on: Review → Approved
- Training triggered on: Approved → InTraining

---

## Idempotency

The seed is fully idempotent. Running it multiple times is safe:

- Existing entities are detected by their unique identifiers (slug, username, category, folder name, document tag)
- Skipped entities are reported in the `*_skipped` arrays of the SeedReport
- No existing data is modified or overwritten
- The second run completes successfully with all entities reported as skipped

---

## Slug Reservation

The slug `alc-corporate` is reserved system-wide. Any attempt to create a company with this slug via the Setup Wizard or Companies API will be rejected with a 422 error. This prevents accidental conflicts with the ALC corporate tenant.

---

## Configuration

### Environment Variable

| Variable | Default | Description |
|----------|---------|-------------|
| `ALC_SEED_DEFAULT_PASSWORD` | `AlcCorp2024!` | Initial password for all ALC corporate user accounts |

Set this in your `.env` file before running the seed. All created users will have this password. Change it immediately after initial setup in production environments.

---

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| "Missing or inactive AITaskType records" | Risk framework seed hasn't run | Run the AI Risk Framework seed (Phase 8.1) first |
| "ALC IT Administrator user not found" | User provisioning failed | Check for email conflicts in the user table |
| Exit code 1 with DB error | Database unreachable | Verify PostgreSQL is running and connection string is correct |
| API returns 401 | Invalid or missing auth token | Authenticate with a system_administrator account |
| API returns 400 | Missing X-Change-Reason header | Add the required header to your request |

---

## Related Features

- [Setup Wizard](setup-wizard-guide.md) — Initial platform setup (must complete first)
- [AI Risk & Compliance Framework](ai-risk-compliance-framework-guide.md) — Risk tier governance (provides AITaskType records)
- [Agent Management](agent-management-guide.md) — Agent definitions activated by the seed
- [Workflow Editor](workflow-editor-guide.md) — BPMN workflow design (governance workflow is pre-created)
