# AlcoaBase (ALC) 🧬

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)](#)

**AlcoaBase (ALC)** is a 100% local, open-source Document & Knowledge Management System. It unites ALCOA+ data integrity with AI, featuring deterministic PDF protocol generation and automated corresponding report data processing, training-gated workflows, RAG, and automated Computer System Validation.

Designed specifically for highly regulated environments (e.g., Pharma, Biotech, Manufacturing), AlcoaBase provides a completely air-gapped solution that bridges the gap between strict compliance and cutting-edge artificial intelligence.

---

## ✨ Core Features

* 🤖 **Multi-Agent "Always-On" Auditing**
  Submit documents for parallel review by N AI auditor agents. A supervisory Master Auditor synthesizes findings into a unified executive summary with consensus detection, contradiction flagging, compliance scoring, and prioritized action items. Includes compliance scorecards, missing link detection, and anomaly monitoring.
* 🛡️ **ALCOA+ Data Integrity & Audit Trail**
  Cryptographic digital signatures (PAdES), strict versioning, and immutable database audit logs for every action (Who, What, When, Why). Every mutating API request requires an `X-Change-Reason` header for full traceability.
* 📄 **Deterministic PDF-to-Database Mapping for Protocols and Reports**
  A visual JSON-driven form builder that creates both React web forms and offline-capable PDFs. Using a proprietary **Dual-UUID** concept, data entered into offline PDFs is flawlessly extracted and mapped directly to relational PostgreSQL tables upon upload.
* 🧠 **Local AI & Retrieval-Augmented Generation (RAG)**
  Ask questions against all your documents. Built for high-performance inference (optimized for NVIDIA Blackwell GPUs via `vLLM`) while maintaining 100% data sovereignty.
* ⚙️ **Dynamic BPMN Workflows & Execution**
  Admins can visually design individual document lifecycles based on meta tags (Draft → Review → Approved → InTraining → Active) using a drag-and-drop BPMN editor. Users execute transitions directly from the document detail page with mandatory change reasons, gate indicators (signature/training), risk-level warnings, and a full audit history timeline.
* 🎓 **Training-Gated Execution with Comprehension Quiz (RBAC/ABAC)**
  Strict access control ensures users can only execute tasks or create reports for specific Standard Operating Procedures (SOPs) if they possess a valid training record AND have passed a comprehension quiz for that exact document version. Quiz attempts are immutable (append-only) for full ALCOA+ audit compliance.
* 🧠 **AI-Enhanced Training Ecosystem**
  Transforms static training into an adaptive learning platform. AI generates personalized schedules, training materials (summaries, walkthroughs, presentations), comprehension quizzes with semantic grading, and interactive "Virtual Audit" role-play sessions. Dynamic feedback points users to exact source paragraphs when they answer incorrectly.
* 📝 **AI Document Generator (Template-Based)**
  Generate regulatory documents from registered Master Templates. The system extracts template structure (headings, numbering, placeholders), retrieves relevant knowledge base content, and synthesizes section-by-section content using AI. Includes immutable provenance audit trails, cross-reference extraction, and a mandatory human review workflow before documents enter the active ecosystem.
* 🔄 **AI-Driven Change Impact Analysis**
  Automatically detects when documents are updated and identifies affected downstream documents and training tasks. Builds a dependency graph from cross-references, database links, and semantic similarity. Performs section-level gap analysis with severity ratings (critical/major/minor) and AI-generated remediation suggestions. Produces immutable audit reports and notifies document owners of required updates.
* 🔗 **AI-Powered Traceability & Gap Discovery**
  Automatically generates Traceability Matrices by crawling requirements documents (URS) and mapping them to test cases (IQ/OQ/PQ/MVP) using three-pass matching (exact ID, cross-reference, semantic similarity). Detects orphan requirements and test cases, computes coverage metrics and compliance readiness scores, and integrates with Change Impact Analysis to flag stale links when requirements change.
* ✅ **Automated Computer System Validation (CSV)**
  A built-in, isolated testing environment. On command, a dedicated Playwright container performs End-to-End (E2E) UI tests, signs documents, verifies database states, and generates a tamper-proof Validation Certificate for FDA/EMA audits.
* 🔐 **Granular Role-Based Access Control (RBAC)**
  Five specialized roles (System Admin, Document Admin, IT Admin, Member, Viewer) with resource-action permission matrices. Permission templates define document-type-specific access rules using a "most restrictive wins" policy. Full user lifecycle management with audit-compliant deactivation, password reset, and company membership management.
* ⚙️ **Centralized System Configuration**
  Administrators manage AI hardware settings, storage quotas, backup schedules, health monitoring, and service status from a single dashboard. All changes are audited with X-Change-Reason headers, versioned via snapshots, and reversible through atomic rollback. Includes real-time health monitoring of all infrastructure services with configurable thresholds.
* 📋 **Centralized Audit Trail Viewer**
  A dedicated admin page aggregating all audit events across all record types into a unified, searchable, filterable chronological view. Supports PDF export for FDA/EMA regulatory submissions with A4 formatting, cursor-based pagination for million-row datasets, and complete immutability enforcement per ALCOA+ and 21 CFR Part 11. Every access to the audit trail is itself logged for meta-auditing.
* 🛡️ **AI Risk & Compliance Framework**
  A cross-cutting governance layer that classifies all AI operations into risk tiers (High, Medium, Low) and enforces tier-appropriate controls at runtime. High-risk operations require human-in-the-loop (HITL) review before outputs become visible; medium-risk operations block automated actions until reviewed; low-risk operations return immediately. Includes per-company risk profile customization, 72-hour checkpoint expiry, immutable operation logs at configurable audit depth, and a visual risk matrix dashboard. Supports regulatory alignment with 21 CFR Part 11, EU AI Act, GMP, GLP, GCP, and ISO 13485.
* 🏢 **ALC Corporate Environment Setup**
  A dedicated seeding service that provisions the canonical "AlcoaBase Corporate" tenant with a complete governance environment: predefined user pool (IT Admin, Doc Admin, Quality Manager, Standard User), regulatory baseline (ISO 27001, ISO 9001, EU AI Act), governance folder structure, AI risk profile, agent activations, and a BPMN governance workflow. Fully idempotent and atomic — safe to re-run at any time via CLI or REST API.
* 📜 **User Requirement Specifications (URS) for ALC**
  Automated generation of a formal Enhanced URS document within the ALC corporate governance environment. Maps all platform capabilities to traceable Requirement IDs (REQ-{MODULE}-{NN}) for regulatory audit submissions. Integrates with the governance workflow and provides cross-reference anchors for all other governance documents.
* 📋 **Cross-Sector AI Regulatory Guidelines**
  Generates 4 AI usage policy documents (1 master cross-sector + 3 sector-specific modules for Pharma/GMP, MedTech/ISO 13485, and IVD/IVDR). Integrates with the AI Risk & Compliance Framework to reference risk tier classifications and HITL requirements. Uploaded as governed documents with full lifecycle workflow.
* 📖 **Documentation Suite: User & Admin Guides**
  Programmatic generation of comprehensive User Guide (12 sections, 28+ procedures) and Technical Admin Guide (12 sections, 25+ procedures). Includes step-by-step procedures with screenshot placeholders, cross-references to URS requirements and AI Guidelines, inter-guide links, and a Related Governance Documents section. Supports versioning on re-execution.
* 🔬 **Literature Search Engine & External API Gateways**
  Secure, multi-tenant gateway to external scientific literature databases (PubMed, Crossref, arXiv). Plugin/adapter architecture for adding new sources without code changes. Per-company API key management with AES-256-GCM encryption at rest. Hierarchical rate limiting (system-wide and per-company), circuit breaker resilience, full audit trail of all outbound API calls, proxy/firewall routing, and async search dispatch for long-running queries.
* 📥 **Automated Literature Ingestion Pipeline**
  Dual-stage asynchronous pipeline consuming literature search results: metadata and abstracts are stored immediately, while full-text retrieval proceeds in the background via Unpaywall DOI resolution. Downloads (PDF, HTML, XML/JATS) are sanitized into a unified StructuredContent schema. Per-company storage quotas with warning/rejection thresholds, configurable retention policies with automatic cleanup, Redis-based concurrency control, SHA-256 integrity verification, and complete audit trail for regulatory traceability.
* 🔎 **High-Dimensional Embedding & Hybrid Search**
  Automatic semantic embedding generation from ingested literature using vLLM, indexed alongside BM25 keyword fields in per-company OpenSearch indices. Hybrid search combines keyword matching with kNN semantic similarity via reciprocal rank fusion (RRF). Unified search spans both public literature and private internal documents. Per-company configurable chunking, batch re-indexing on model changes, graceful BM25-only degradation, and partition tagging for provenance filtering.
* 🔬 **AI-Powered Literature Review & Synthesis Agents**
  Automates systematic literature reviews (SLRs) with an AI screener agent that evaluates papers against PICO criteria and custom inclusion/exclusion rules. Produces structured screening decisions with confidence scores, rationale, and matched criteria references. Supports full SLR lifecycle with PRISMA flow statistics, human override workflows, inter-rater reliability (Cohen's kappa), and regulatory-compliant report generation. Contradiction detection automatically cross-references newly indexed literature against internal SOPs and validation plans, creating severity-classified alerts (critical/major/minor) with automatic escalation for critical findings. Novelty flagging identifies papers covering topics not yet addressed by internal documentation.
* 📚 **Literature Search Dashboard & Citation Management**
  A dedicated faceted search interface connecting all literature infrastructure into a user-friendly workflow. Execute hybrid BM25+kNN searches with journal, source, date, MeSH, and device class filters. One-click internalization converts public papers into governed internal Documents with full lifecycle tracking. Organize internalized papers into Citation Collections for regulatory submissions (MDR clinical evaluations, PMS reports). Link papers to URS requirements or test cases for traceability evidence chains. Export results as CSV or PDF with optional PRISMA flow diagrams. Every search execution, internalization, and citation action is logged immutably for FDA/EMA audit compliance.
* 🏥 **Medical Device Vigilance & Post-Market Surveillance**
  Continuous, automated vigilance monitoring for medical device companies. Register products with regulatory metadata (UDI, device class, intended purpose), define targeted search profiles with Boolean query construction and cron-based scheduling, and let the system automatically detect safety signals using a specialized "Vigilance Analyst" AI agent. Signals are severity-classified (critical/major/minor) per MDR Article 87 criteria. Critical signals trigger parallel escalation: impact analysis, contradiction detection, admin notification, and SLR inclusion. Auto-generated Periodic Safety Reports document all activity with disposition matrices, regulatory compliance sections, and a status lifecycle (generated → reviewed → approved → submitted) for MDR/IVDR submissions.

---

## 🏗️ Architecture & Tech Stack

AlcoaBase cleanly separates structured, compliance-critical data from unstructured, semantic AI operations.

**Frontend:**
* React (Vite) + TypeScript
* Tailwind CSS & shadcn/ui
* Zustand (State Management)
* `@hello-pangea/dnd` & `react-hook-form` (Visual Form Builder)

**Backend:**
* Python (FastAPI)
* SQLAlchemy 2.0 + SQLAlchemy-Continuum (Automated Audit Tables)
* SpiffWorkflow (BPMN Workflow Engine)
* Celery + Redis (Background Jobs)
* ReportLab & PyMuPDF (PDF Generation & UUID Extraction)
* watchfiles (Agent YAML hot-reload)

**Data & AI Layer:**
* PostgreSQL (Source of truth, GLP records, User roles)
* MinIO (S3-compatible object storage for physical PDFs)
* OpenSearch (Vector database for RAG and hybrid lexical/semantic search)
* vLLM (Local LLM inference — hybrid architecture with dedicated embedding instance + shared chat/OCR instance)
* httpx (Async HTTP client with connection pooling for vLLM communication)

**Validation:**
* Playwright (Automated E2E testing for the CSV module)

---

## 📊 Implementation Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1.1 | Multi-Tenancy / Company Separation | ✅ Complete |
| 1.2 | Setup Wizard | ✅ Complete |
| 1.3 | Authentication & Session Management | ✅ Complete |
| 2.1 | Document Upload & List | ✅ Complete |
| 2.2 | Virtual Folders | ✅ Complete |
| 2.3 | Document Versioning UI | ✅ Complete |
| 2.4 | Template Builder (Drag & Drop) | ✅ Complete |
| 2.5 | Report Data Entry & PDF Extraction | ✅ Complete |
| 3.1 | BPMN Workflow Visual Editor | ✅ Complete |
| 3.2 | Workflow Execution & State Transitions | ✅ Complete |
| 3.3 | Training Management UI | ✅ Complete |
| 3.4 | Electronic Signatures UI | ✅ Complete |
| 3.5 | Comprehension Quiz & Dual Gate | ✅ Complete |
| 4.1 | Search UI Integration | ✅ Complete |
| 4.2 | RAG Knowledge Base UI | ✅ Complete |
| 4.3 | AI Model Integration (vLLM) | ✅ Complete |
| 4.4 | Multimodal Knowledge Base | ✅ Complete |
| 5.1 | Modular Agent Registry & Personality Framework | ✅ Complete |
| 5.2 | Multi-Agent "Always-On" Auditing | ✅ Complete |
| 5.3 | AI-Enhanced Training Ecosystem | ✅ Complete |
| 5.4 | AI Document Generator (Template-Based) | ✅ Complete |
| 5.5 | AI-Driven Change Impact Analysis | ✅ Complete |
| 5.6 | AI-Powered Traceability & Gap Discovery | ✅ Complete |
| 6.1 | Admin Dashboard — User Management | ✅ Complete |
| 6.2 | Admin Dashboard — System Configuration | ✅ Complete |
| 6.3 | Audit Trail Viewer | ✅ Complete |
| 8.1 | AI Risk & Compliance Framework | ✅ Complete |
| 8.2 | ALC Corporate Environment Setup | ✅ Complete |
| 8.3 | User Requirement Specifications (URS) for ALC | ✅ Complete |
| 8.4 | Cross-Sector AI Regulatory Guidelines | ✅ Complete |
| 8.5 | Documentation Suite: User & Admin Guides | ✅ Complete |
| 9.1 | Literature Search Engine & External API Gateways | ✅ Complete |
| 9.2 | Automated Ingestion Pipeline | ✅ Complete |
| 9.3 | High-Dimensional Embedding & Hybrid Search | ✅ Complete |
| 9.4 | AI-Powered Literature Review & Synthesis Agents | ✅ Complete |
| 9.5 | Medical Device Vigilance & Post-Market Surveillance | ✅ Complete |
| 9.6 | Literature Search, Citation UI & Audit Trail Mapping | ✅ Complete |

See the full roadmap in [`todo.md`](todo.md).

---

## 📖 Documentation

Comprehensive user guides for all platform features are available in the [`docs/`](docs/) directory, organized by domain with a master index:

**→ [Documentation Index](docs/INDEX.md)** — Start here for a structured overview of all 28 guides.

| Section | Guides |
|---------|--------|
| **Getting Started** | [Setup Wizard](docs/setup-wizard-guide.md) · [Document Upload](docs/document-upload-guide.md) |
| **Document Lifecycle** | [Workflow Editor](docs/workflow-editor-guide.md) · [Workflow Execution](docs/workflow-execution-guide.md) · [Electronic Signatures](docs/electronic-signatures-guide.md) · [Training](docs/training-management-guide.md) · [Quiz](docs/quiz-comprehension-guide.md) |
| **Search & Knowledge** | [Search & RAG](docs/search-knowledge-guide.md) · [AI Inference](docs/ai-inference-guide.md) |
| **AI Intelligence** | [Agents](docs/agent-management-guide.md) · [Multi-Agent Auditing](docs/multi-agent-auditing-guide.md) · [Document Generator](docs/ai-document-generator-guide.md) · [Training Ecosystem](docs/ai-training-ecosystem-guide.md) · [Impact Analysis](docs/change-impact-analysis-guide.md) · [Traceability](docs/traceability-gap-discovery-guide.md) |
| **Literature Research** | [Search Engine](docs/literature-search-guide.md) · [Ingestion](docs/literature-ingestion-guide.md) · [Embedding & Search](docs/literature-embedding-hybrid-search-guide.md) · [Review Agents](docs/literature-review-synthesis-guide.md) · [Vigilance & PMS](docs/medical-device-vigilance-pms-guide.md) · [Citation UI](docs/literature-search-citation-ui-guide.md) |
| **Administration** | [User Management](docs/admin-dashboard-user-management-guide.md) · [System Config](docs/admin-system-configuration-guide.md) · [Audit Trail](docs/audit-trail-viewer-guide.md) · [AI Risk Framework](docs/ai-risk-compliance-framework-guide.md) |
| **Corporate Governance** | [Corporate Environment](docs/alc-corporate-environment-guide.md) · [AI Guidelines](docs/cross-sector-ai-guidelines-guide.md) · [Documentation Suite](docs/documentation-suite-guide.md) |

---

## 🚀 Getting Started

AlcoaBase is designed to be deployed quickly via Docker Compose.

### Prerequisites
* Docker & Docker Compose
* [uv](https://docs.astral.sh/uv/getting-started/installation/) — used for all Python dependency management and CLI tooling
* (Optional but recommended) NVIDIA GPU with container toolkit installed for AI features. *A CPU-mock mode is available for local testing.*

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-org/alcoabase.git](https://github.com/your-org/alcoabase.git)
   cd alcoabase
   ```
   
2. **Start the environment:**
   ```bash
   docker compose up -d
   ```
   
3. **Run the Setup Wizard:**

   Open your browser and navigate to http://localhost:3000. You will be greeted by the AlcoaBase Setup Wizard. Follow the steps to create your root administrator account, configure your AI hardware settings, and (optionally) seed the database with demo users, BPMN workflows, and SOPs.

---

## 🧪 Testing

AlcoaBase has three test layers. All use `uv run pytest` from the `src/backend/` directory.

### Unit & Property Tests

Fast, no external dependencies. Runs against in-memory SQLite.

```bash
cd src/backend
uv run pytest --tb=short -q
```

Property-based tests use [Hypothesis](https://hypothesis.readthedocs.io/) to validate correctness invariants (tenant isolation, membership rules, migration backfill, quiz scoring, training gate dual verification, etc.).

### Integration Tests

Tests the full FastAPI request lifecycle (middleware → dependency → route → DB) using an async in-memory SQLite database. No Docker required.

```bash
cd src/backend
uv run pytest tests/integration/ -v
```

### Smoke Tests (against Docker Compose)

Hits the real backend running on PostgreSQL to validate migrations, constraint behavior, and end-to-end flows.

```bash
# 1. Start the stack
docker compose up -d

# 2. Wait for healthy backend, then run the migration
docker compose exec backend alembic upgrade head

# 3. Run smoke tests
cd src/backend
uv run pytest tests/smoke/ -v

# Optional: point at a different host
SMOKE_TEST_BASE_URL=http://your-host:8080 uv run pytest tests/smoke/ -v
```

Smoke tests generate unique slugs per run, so they're safe to execute repeatedly without cleanup.

### Manual Test Protocols & Reports

Structured manual test protocols and execution reports for system-level validation are maintained in:

- **Protocols** (reusable step-by-step procedures): `docs/test-protocols/`
- **Reports** (executed test results with tester sign-off): `docs/test-reports/`

Each protocol follows a GxP-compliant format with prerequisites, expected results, pass/fail recording, and deviation tracking. Protocols cover Phase 10 of the roadmap (Setup, Documents, Workflows, Training, AI, Admin).

To run a fresh validation cycle:

```bash
make reset-db && make migrate && make setup
# Then execute protocols in order: 10.1.1 → 10.1.2 → 10.1.3 → ...
```

---

## ✅ Computer System Validation (CSV)

To prove to auditors that your local instance of AlcoaBase functions exactly as specified, you can trigger the automated CSV process.

1. Navigate to the Admin Dashboard -> Validation.
2. Click **"Run Full System Validation"**.
3. A dedicated, isolated testing user will automatically run through complete lifecycles (creation, approval, PDF generation, signing, and data extraction).
4. Upon completion, a digitally signed CSV Report (PDF) will be deposited directly into your AlcoaBase document repository.

---

## 🤝 Contributing

We welcome contributions! Whether it's improving the AI prompts, adding new PDF field types, or enhancing the BPMN engine, please check out our [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 🔒 Air-Gapped Deployment

AlcoaBase is designed for fully air-gapped environments where no internet connectivity is available. All AI inference runs locally using pre-downloaded model weights.

### Model Download (Internet-Connected Machine)

Before deploying to an air-gapped environment, download the required model weights on a machine with internet access.

First, sync the project dependencies (this installs `huggingface-cli` via the `huggingface-hub` package):

```bash
# From the project root
cd src/backend
uv sync
```

Then download models into the **project-root** `models/` directory. AlcoaBase provides two model profiles — pick the one that matches your hardware.

> **Note:** Some models (e.g., Llama) require accepting a license on [huggingface.co](https://huggingface.co) and authenticating first:
> ```bash
> uv run --project src/backend huggingface-cli login
> ```

#### Small Profile (default — fits on a single 24 GB GPU)

Best for development, testing, and smaller deployments. These are the defaults in `.env.example`.

| Role | Model | Active Params | Download Size |
|------|-------|--------------|---------------|
| Chat / Generation | `Qwen/Qwen3.6-35B-A3B` (MoE) | ~3B | ~8 GB |
| Embedding | `Qwen/Qwen3-Embedding-0.6B` | 0.6B | ~1.2 GB |
| Vision / OCR | `google/gemma-4-E4B-it` | ~4B | ~8 GB |

```bash
cd ../..
mkdir -p models

# Chat: Qwen3.6 35B MoE (only ~3B active params per token)
uv run --project src/backend hf download Qwen/Qwen3.6-35B-A3B --local-dir models/qwen3.6-35b-a3b

# Embedding: Qwen3-Embedding 0.6B (1024-dim output)
uv run --project src/backend hf download Qwen/Qwen3-Embedding-8B --local-dir models/qwen3-embedding-8b
# or Qwen/Qwen3-Embedding-8B
# or Qwen/Qwen3-Embedding-0.6B

# Vision/OCR: Gemma 4 E4B (native vision + OCR)
uv run --project src/backend hf download google/gemma-4-E4B-it --local-dir models/gemma-4-e4b-it
```

#### Large Profile (production — requires ≥80 GB VRAM)

For production deployments on high-end hardware (e.g., NVIDIA A100/H100/Blackwell).

| Role | Model | Params | Download Size |
|------|-------|--------|---------------|
| Chat / Generation | `meta-llama/Llama-3.3-70B-Instruct` | 70B | ~140 GB |
| Embedding | `Qwen/Qwen3-Embedding-8B` | 8B | ~16 GB |
| Vision / OCR | `Qwen/Qwen2.5-VL-72B-Instruct` | 72B | ~145 GB |

```bash
cd ../..
mkdir -p models

# Chat: Llama 3.3 70B Instruct (requires license acceptance on HuggingFace)
uv run --project src/backend hf download meta-llama/Llama-3.3-70B-Instruct --local-dir models/llama-3.3-70b-instruct

# Embedding: Qwen3-Embedding 8B (#1 on MTEB multilingual leaderboard, 1024-dim)
uv run --project src/backend hf download Qwen/Qwen3-Embedding-8B --local-dir models/qwen3-embedding-8b

# Vision/OCR: Qwen2.5-VL 72B
uv run --project src/backend hf download Qwen/Qwen2.5-VL-72B-Instruct --local-dir models/qwen2.5-vl-72b-instruct
```

> **Switching profiles:** Update the `MODEL_*` variables in your `.env` to point to the downloaded weights. Both profiles use the same embedding dimension (1024), so no OpenSearch index rebuild is needed when upgrading.

### Transfer to Air-Gapped Environment

Transfer the `models/` directory to the target machine via approved media (USB drive, internal network share, etc.):

```bash
# Example: copy to target machine
rsync -avP models/ target-machine:/path/to/alcoabase/models/
```

### Configuration

Configure the model paths in your `.env` file. The defaults match the **Small Profile**:

```env
# Model Manager Mode: gpu (production), cpu (fallback), mock (development)
MODEL_MANAGER_MODE=gpu

# ── Chat / Generation LLM ──
# SMALL (default):
MODEL_CHAT_NAME=Qwen/Qwen3.6-35B-A3B
MODEL_CHAT_PATH=/models/qwen3.6-35b-a3b
MODEL_CHAT_MAX_GPU_MEMORY_GB=24
# LARGE (uncomment to upgrade):
# MODEL_CHAT_NAME=meta-llama/Llama-3.3-70B-Instruct
# MODEL_CHAT_PATH=/models/llama-3.3-70b-instruct
# MODEL_CHAT_MAX_GPU_MEMORY_GB=60

# ── Multilingual Embedding Model ──
# SMALL (default):
MODEL_EMBEDDING_NAME=Qwen/Qwen3-Embedding-0.6B
MODEL_EMBEDDING_PATH=/models/qwen3-embedding-0.6b
MODEL_EMBEDDING_DIMENSION=1024
# LARGE (uncomment to upgrade):
# MODEL_EMBEDDING_NAME=Qwen/Qwen3-Embedding-8B
# MODEL_EMBEDDING_PATH=/models/qwen3-embedding-8b
# MODEL_EMBEDDING_DIMENSION=1024

# ── Vision / OCR Model ──
# SMALL (default):
MODEL_OCR_NAME=google/gemma-4-E4B-it
MODEL_OCR_PATH=/models/gemma-4-e4b-it
# LARGE (uncomment to upgrade):
# MODEL_OCR_NAME=Qwen/Qwen2.5-VL-72B-Instruct
# MODEL_OCR_PATH=/models/qwen2.5-vl-72b-instruct

# GPU Configuration
GPU_DEVICE_ID=0
```

### Docker Compose Volume Mount

The `docker-compose.yml` mounts the models directory into the vLLM container (configured via `MODEL_WEIGHTS_PATH` in `.env`, defaults to `./models`):

```yaml
services:
  vllm:
    volumes:
      - ${MODEL_WEIGHTS_PATH:-./models}:/models:ro
```

### Network Isolation

AI containers are configured with no outbound internet access. The Docker Compose network configuration ensures:
- The vLLM container has no external network access
- All inter-service communication uses the internal Docker network
- No document content, embeddings, or queries leave the deployment

### Development Without GPU (Mock Mode)

For local development and testing without GPU hardware:

```env
MODEL_MANAGER_MODE=mock
```

Mock mode returns:
- Random vectors of the correct embedding dimension (1024) for embedding requests
- Placeholder text responses for LLM completion requests
- Simulated OCR text for scanned PDF processing

This allows full application testing without GPU hardware or downloaded model weights.

### AI Mode Switching

AlcoaBase supports three inference modes, controlled by `MODEL_MANAGER_MODE` in `.env`:

| Mode | Requirement | Command |
|------|-------------|---------|
| `mock` | None | `make up` (default) |
| `gpu` | NVIDIA GPU ≥ 24 GB VRAM + model weights | `make vllm-gpu` or set `MODEL_MANAGER_MODE=gpu` then `make up` |
| `cpu` | ≥ 32 GB RAM + model weights (very slow) | `make vllm-cpu` or set `MODEL_MANAGER_MODE=cpu` then `make up` |

`make up` reads `MODEL_MANAGER_MODE` from `.env` and automatically starts the corresponding vLLM container. You can also use the explicit commands:

```bash
make vllm-gpu      # Start vLLM with GPU (waits for health check)
make vllm-cpu      # Start vLLM in CPU mode (waits for health check)
make vllm-stop     # Stop vLLM (any mode)
make vllm-logs     # Tail vLLM container logs
```

The mode can also be switched at runtime via the Admin UI (System Config → AI Settings) or API:

```bash
curl -X PUT http://localhost:8080/api/system-config/ai-hardware \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Change-Reason: Switch to GPU mode" \
  -d '{"inference_mode":"gpu"}'
```

---
## AI Disclosure
This project was developed with assistance from AI coding tools, including kiro, opencode, qwen, claude. All outputs were reviewed, tested, and accepted by the maintainers. AI was used to support development; all architectural decisions and responsibility remain with the authors.

## Disclaimer
This software is provided as is, without warranty of any kind. The authors and contributors are not responsible for any damages, losses, or issues arising from its use, including design errors, hardware damage, manufacturing mistakes, or data loss. AI-generated suggestions are not a replacement for qualified engineering review, and any safety-critical use requires independent expert validation.

## 📄 License

This project is licensed under the [Apache 2.0 License](LICENSE).






   
