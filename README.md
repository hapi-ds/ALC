# AlcoaBase (ALC) 🧬

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)](#)

**AlcoaBase (ALC)** is a 100% local, open-source Document & Knowledge Management System. It unites ALCOA+ data integrity with AI, featuring deterministic PDF protocol generation and automated corresponding report data processing, training-gated workflows, RAG, and automated Computer System Validation.

Designed specifically for highly regulated environments (e.g., Pharma, Biotech, Manufacturing), AlcoaBase provides a completely air-gapped solution that bridges the gap between strict compliance and cutting-edge artificial intelligence.

---

## ✨ Core Features
Beside tradional document management (versioned storage of documents in folder structure with unique document number and meta tags for classification) following features are planned:

* 🛡️ **ALCOA+ Data Integrity & Audit Trail**
  Cryptographic digital signatures (PAdES), strict versioning, and immutable database audit logs for every action (Who, What, When, Why).
* 📄 **Deterministic PDF-to-Database Mapping for Protocols and Reports**
  A visual JSON-driven form builder that creates both React web forms and offline-capable PDFs. Using a proprietary **Dual-UUID** concept, data entered into offline PDFs is flawlessly extracted and mapped directly to relational PostgreSQL tables upon upload.
* 🧠 **Local AI & Retrieval-Augmented Generation (RAG)**
  Ask questions against all your documents. Built for high-performance inference (optimized for NVIDIA Blackwell GPUs via `vLLM`) while maintaining 100% data sovereignty.
* ⚙️ **Dynamic BPMN Workflows**
  Admins can visually design individual document lifecycles based on meta tags (Draft -> Review -> Approved -> InTraining -> Active) using a drag-and-drop BPMN editor, executed securely by the Python backend.
* 🎓 **Training-Gated Execution (RBAC/ABAC)**
  Strict access control ensures users can only execute tasks or create reports for specific Standard Operating Procedures (SOPs) if they possess a valid, digitally signed training record for that exact document version.
* ✅ **Automated Computer System Validation (CSV)**
  A built-in, isolated testing environment. On command, a dedicated Playwright container performs End-to-End (E2E) UI tests, signs documents, verifies database states, and generates a tamper-proof Validation Certificate for FDA/EMA audits.

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

**Data & AI Layer:**
* PostgreSQL (Source of truth, GLP records, User roles)
* MinIO (S3-compatible object storage for physical PDFs)
* OpenSearch (Vector database for RAG and hybrid lexical/semantic search)
* vLLM & LlamaIndex (Local LLM inference & orchestration)

**Validation:**
* Playwright (Automated E2E testing for the CSV module)

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

Property-based tests use [Hypothesis](https://hypothesis.readthedocs.io/) to validate correctness invariants (tenant isolation, membership rules, migration backfill, etc.).

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

---

## 📄 License

This project is licensed under the [Apache 2.0 License](LICENSE).
```





   
