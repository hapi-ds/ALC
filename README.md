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

## 🧪 Computer System Validation (CSV)

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

Before deploying to an air-gapped environment, download the required model weights on a machine with internet access:

```bash
# Create the models directory
mkdir -p /models

# Download the chat/generation model (Llama 3.3 70B Instruct)
huggingface-cli download meta-llama/Llama-3.3-70B-Instruct \
  --local-dir /models/llama-3.3-70b-instruct

# Download the multilingual embedding model
huggingface-cli download intfloat/multilingual-e5-large-instruct \
  --local-dir /models/multilingual-e5-large-instruct

# Download the OCR/vision model (Qwen2.5-VL 72B)
huggingface-cli download Qwen/Qwen2.5-VL-72B-Instruct \
  --local-dir /models/qwen2.5-vl-72b-instruct
```

### Transfer to Air-Gapped Environment

Transfer the `/models/` directory to the target machine via approved media (USB drive, internal network share, etc.):

```bash
# Example: copy to target machine
rsync -avP /models/ target-machine:/models/
```

### Configuration

Configure the model paths in your `.env` file:

```env
# Model Manager Mode: gpu (production), cpu (fallback), mock (development)
MODEL_MANAGER_MODE=gpu

# Chat/Generation Model
MODEL_CHAT_NAME=meta-llama/Llama-3.3-70B-Instruct
MODEL_CHAT_PATH=/models/llama-3.3-70b-instruct
MODEL_CHAT_MAX_GPU_MEMORY_GB=60

# Multilingual Embedding Model
MODEL_EMBEDDING_NAME=intfloat/multilingual-e5-large-instruct
MODEL_EMBEDDING_PATH=/models/multilingual-e5-large-instruct
MODEL_EMBEDDING_DIMENSION=1024

# OCR/Vision Model
MODEL_OCR_NAME=Qwen/Qwen2.5-VL-72B-Instruct
MODEL_OCR_PATH=/models/qwen2.5-vl-72b-instruct

# GPU Configuration
GPU_DEVICE_ID=0
```

### Docker Compose Volume Mount

The `docker-compose.yml` mounts the models directory into the vLLM container:

```yaml
services:
  vllm:
    volumes:
      - /models:/models:ro
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





   
