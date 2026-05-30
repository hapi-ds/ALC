# AI Risk & Compliance Framework — User Guide

## Overview

The AI Risk & Compliance Framework is a cross-cutting governance layer that classifies all AI-powered operations in AlcoaBase into risk tiers (High, Medium, Low) and enforces tier-appropriate controls at runtime. It ensures that AI outputs in GxP-regulated environments receive proportional validation, human review, and audit logging based on their potential impact.

The framework integrates transparently with existing AI features — Document Generator, Multi-Agent Auditing, RAG Knowledge Base, Training Ecosystem, Change Impact Analysis, and Traceability Discovery — without requiring changes to how users interact with those features.

---

## Key Concepts

### Risk Tiers

| Tier | Description | Examples |
|------|-------------|----------|
| **High** | AI output enters approval workflows or directly affects regulated processes | Document Generation, Multi-Agent Audit, Training Content |
| **Medium** | AI output informs human decisions but does not modify records directly | Change Impact Analysis, Traceability Gap Discovery |
| **Low** | AI output retrieves or summarizes existing content without creating records | RAG Knowledge Query, Document Search, Template Analysis |

### Control Sets

Each tier has a defined set of controls enforced automatically:

| Control | High | Medium | Low |
|---------|------|--------|-----|
| HITL Checkpoint | Required (blocks visibility) | Required (blocks automation) | Not required |
| Audit Depth | Full (all inputs/outputs/reasoning) | Standard (inputs/outputs/model) | Minimal (timestamp/status) |
| Validations | Format + Cross-reference + Completeness | Format only | None |
| Output Label | — | `ai_assisted` | `ai_generated` |
| Expiry Window | 72 hours | 72 hours | — |
| Rate Limit | — | — | 100/user/hour |

### HITL Checkpoints

Human-in-the-Loop checkpoints are mandatory review gates for High and Medium tier operations. When an AI operation completes:

- **High tier**: Output is held invisible until a qualified reviewer (system_admin or doc_admin) approves it
- **Medium tier**: Output is visible but cannot trigger automated actions until reviewed
- **Low tier**: Output is returned immediately with an `ai_generated` tag

Checkpoints expire after 72 hours if not reviewed. Expired outputs are marked invalid and must be regenerated.

---

## Administration UI

Access the framework at **Admin → AI Risk Framework** (`/admin/ai-risk-framework`). This page is restricted to users with `system_admin` or `doc_admin` roles.

### Dashboard Tab

The dashboard provides an at-a-glance view of AI governance status:

- **Operations (30d)**: Total AI operations in the last 30 days, broken down by tier
- **Pending Checkpoints**: Number of HITL checkpoints awaiting review
- **Expired Checkpoints**: Checkpoints that passed the 72-hour window without review
- **Blocked Operations**: Operations blocked by the Control Gate (missing controls, unregistered task types)
- **Active Profile**: The company's current risk profile name
- **Risk Matrix**: A 3×3 grid showing task types positioned by impact and likelihood, color-coded by tier

### Task Types Tab

A paginated registry of all AI task types in the system. Each row shows:

- Display name and module reference
- Default risk tier (system-defined)
- Company tier (if overridden by your profile)
- Active/Inactive status

Click any row to expand and view risk factors and the applicable control set.

### Risk Profile Tab

Manage your company's risk tier customization:

- **View** the current active profile with all tier overrides
- **Create** a new profile to override default tier assignments
- **History** shows all previous profiles (deactivated profiles are preserved for audit)

When creating overrides:
- **Escalation** (raising a tier) requires only a justification
- **De-escalation** (lowering a tier) requires justification ≥50 characters, a regulatory reference, and approval by a system_admin or doc_admin

### HITL Queue Tab

Lists all pending checkpoints sorted by expiry (nearest first). For each checkpoint:

- Operation type, creation date, expiry date, and status
- Click **Review** to open the detail panel showing AI output metadata
- **Approve** or **Reject** with reviewer comments (comments required for rejection)

Concurrent reviews are handled safely — if two reviewers submit simultaneously, only the first succeeds.

### Operation Logs Tab

A filterable, paginated log of all AI operations:

- Filter by task type, tier, date range, and outcome (passed/blocked)
- Each entry shows timestamp, task type, tier, audit depth, gate result, duration, and model used

---

## How It Works (For Developers)

### The `@risk_controlled` Decorator

AI service methods are wrapped with the `@risk_controlled` decorator:

```python
from alcoabase.services.risk_controlled import risk_controlled

@risk_controlled(task_type_id="document_generation")
async def generate(self, instructions: str, user_id: int, company_id: int, ...):
    # Your AI logic here
    return generated_content
```

The decorator:
1. Resolves the effective risk tier for the task type and company
2. Runs pre-execution checks (HITL reviewer availability, audit trail writability)
3. Executes the wrapped function
4. Logs the operation at tier-appropriate audit depth
5. Creates a HITL checkpoint for High/Medium tiers
6. Returns a tier-appropriate response structure

If `company_id` or `user_id` is not provided, the decorator operates in pass-through mode (useful for background tasks).

### Registering New AI Task Types

Any new AI feature must register a task type before invoking inference:

1. Add the task type to the seed data in `services/risk_framework_seed.py`
2. Run the seed function (or create via the API)
3. Apply the `@risk_controlled` decorator to the inference method

Unregistered task types are blocked by the Control Gate at runtime.

### API Endpoints

All endpoints are under `/api/risk-framework/` and require:
- `X-Company-Id` header (tenant scoping)
- `system_admin` or `doc_admin` role
- `X-Change-Reason` header for mutations (POST/PUT)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/task-types` | List all task types (paginated) |
| GET | `/task-types/{id}` | Get task type detail |
| GET | `/tiers` | List all tier definitions |
| GET | `/tiers/{level}` | Get single tier definition |
| POST | `/profiles` | Create risk profile |
| GET | `/profiles` | Get active profile |
| PUT | `/profiles/{id}` | Update profile |
| GET | `/profiles/history` | Profile change history |
| GET | `/checkpoints` | List HITL checkpoints (filterable) |
| POST | `/checkpoints/{id}/review` | Approve/reject checkpoint |
| GET | `/operation-logs` | List operation logs (filterable) |
| GET | `/dashboard-stats` | Dashboard statistics |

---

## Checkpoint Expiry

A background Celery task runs every 15 minutes to expire stale checkpoints:

- Finds all pending checkpoints where `expires_at < now`
- Marks them as `expired`
- Expired outputs cannot be approved or used in downstream workflows
- The operation must be re-run to generate fresh output

This is idempotent — running it multiple times has no additional effect.

---

## Audit Trail Integration

The framework integrates with AlcoaBase's existing audit infrastructure:

- **AIOperationLog** and **ControlEnforcementLog** are immutable (no UPDATE/DELETE permitted)
- High/Medium tier logs are written synchronously before returning results — if the write fails, the AI output is not returned
- Failed operations are logged at the same audit depth with status "failure"
- All records are scoped to the company via `X-Company-Id`

Retention policies:
- High tier logs: 7 years minimum
- Medium tier logs: 3 years minimum
- Low tier logs: 1 year minimum

---

## Regulatory Alignment

The framework supports alignment with multiple regulatory standards:

- **21 CFR Part 11** — Electronic records and signatures
- **EU GMP Annex 11** — Computerized systems
- **EU AI Act** — Risk-based AI governance
- **ISO 13485** — Medical device quality management
- **GLP/GCP** — Good Laboratory/Clinical Practice

Companies can specify their applicable frameworks in their risk profile, and tier assignments can be customized to match their specific regulatory context.
