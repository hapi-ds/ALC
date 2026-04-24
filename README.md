# AlcoaBase (ALC) 🧬

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-%2320232a.svg?style=flat&logo=react&logoColor=%2361DAFB)](#)

**AlcoaBase (ALC)** is a 100% local, open-source Document & Knowledge Management System. It unites ALCOA+ data integrity with AI, featuring deterministic PDF protocol generation and automated corresponding report data processing, training-gated workflows, RAG, and automated Computer System Validation.

Designed specifically for highly regulated environments (e.g., Pharma, Biotech, Manufacturing), AlcoaBase provides a completely air-gapped solution that bridges the gap between strict compliance and cutting-edge artificial intelligence.

---

## ✨ Core Features

* 🛡️ **ALCOA+ Data Integrity & Audit Trail**
  Cryptographic digital signatures (PAdES), strict versioning, and immutable database audit logs for every action (Who, What, When, Why).
* 📄 **Deterministic PDF-to-Database Mapping**
  A visual JSON-driven form builder that creates both React web forms and offline-capable PDFs. Using a proprietary **Dual-UUID** concept, data entered into offline PDFs is flawlessly extracted and mapped directly to relational PostgreSQL tables upon upload.
* 🧠 **Local AI & Retrieval-Augmented Generation (RAG)**
  Ask questions against all your documents. Built for high-performance inference (optimized for NVIDIA Blackwell GPUs via `vLLM`) while maintaining 100% data sovereignty.
* ⚙️ **Dynamic BPMN Workflows**
  Admins can visually design document lifecycles (Draft -> Review -> Approved -> InTraining -> Active) using a drag-and-drop BPMN editor, executed securely by the Python backend.
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
