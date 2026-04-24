# Contributing to AlcoaBase (ALC)

First off, thank you for considering contributing to AlcoaBase! 🎉

AlcoaBase is built for highly regulated environments (Pharma, Biotech, etc.). Because it handles ALCOA+ data integrity, deterministic PDF mapping, and Computer System Validation (CSV), we have strict standards for code quality, testing, and database management. 

However, don't let that intimidate you! We welcome contributions of all kinds: bug reports, feature requests, documentation improvements, and code patches. This document will guide you through the process.

---

## 🛑 Important: The Golden Rule of AlcoaBase

**Do no harm to the Audit Trail or Determinism.**
AlcoaBase relies on `SQLAlchemy-Continuum` for immutable audit trails and strict UUID-to-database mapping for offline PDFs. 
* **Never** submit code that bypasses the ORM to alter database records silently. 
* **Never** alter the schema of published PDF templates.
* All state changes must flow through the defined SpiffWorkflow processes and be fully auditable.

---

## 🛠️ How Can I Contribute?

### 1. Reporting Bugs
If you find a bug, please open an issue using the **Bug Report** template. Include:
* Your operating system and deployment method (Docker version).
* Steps to reproduce the behavior.
* Expected vs. actual behavior.
* Relevant logs (from FastAPI, Celery, or the React console).

### 2. Suggesting Enhancements
We love new ideas, especially regarding AI/RAG capabilities and workflow improvements. Open an issue using the **Feature Request** template. Please provide a clear use case and explain how it benefits the GLP/regulated community.

### 3. Code Contributions
Ready to write some code? Great! Here is our standard workflow:

1. **Fork the repository** to your own GitHub account.
2. **Clone your fork** locally.
3. **Create a branch** for your feature or bugfix:
   `git checkout -b feature/your-feature-name` or `git checkout -b fix/issue-number`
4. **Develop and test** your changes.
5. **Commit** using Conventional Commits (see below).
6. **Push** your branch and open a **Pull Request (PR)** against the `main` branch.

---

## 💻 Local Development Setup

To develop AlcoaBase locally, you will need Docker, Python 3.12+, and Node.js (v20+).

1. Spin up the development infrastructure (Postgres, MinIO, OpenSearch, Redis):
   ```bash
   docker compose -f docker-compose.dev.yml up -d
   ```
   *(Note: For local development without a GPU, the dev-compose file automatically configures the AI stack to use CPU-mock models.)*

2. **Backend Setup:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   uvicorn main:app --reload
   ```

3. **Frontend Setup:**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

---

## 📏 Coding Standards

To ensure a stable and readable codebase, please adhere to the following tools and standards:

### Backend (Python/FastAPI)
* **Formatting:** We use [`ruff`](https://docs.astral.sh/ruff/) and [`black`](https://black.readthedocs.io/). Run `black .` and `ruff check . --fix` before committing.
* **Typing:** Strict type hinting is enforced via `mypy`.
* **Database Migrations:** If you change an SQLAlchemy model, you **must** generate an Alembic migration (`alembic revision --autogenerate -m "description"`). Ensure the migration does not break existing Audit Trail (`Continuum`) tables.

### Frontend (React/TypeScript)
* **Formatting/Linting:** We use `ESLint` and `Prettier`. Run `npm run lint` before committing.
* **Components:** Use the established `shadcn/ui` and `TailwindCSS` patterns. Avoid introducing new third-party component libraries without discussion.

---

## 🧪 Testing and Validation (CSV)

Because AlcoaBase includes automated Computer System Validation (CSV), testing is not optional.

* **Unit/Integration Tests (Backend):** Write tests for new API endpoints and backend logic using `pytest`.
  ```bash
  pytest tests/
  ```
* **E2E / CSV Tests (Playwright):** If your feature alters the UI, the PDF generation, or the core workflows, you **must** update or add Playwright tests. The CSV suite must pass entirely before a PR is merged.
  ```bash
  cd e2e-tests
  npx playwright test
  ```

---

## 📝 Commit Message Convention

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification. This helps us auto-generate release notes and versioning.

Examples:
* `feat: add multiple choice quiz generator for SOP training`
* `fix(pdf): correct coordinate offset in ReportLab generation`
* `docs: update README with new environment variables`
* `test: add Playwright coverage for user creation wizard`

---

## 🕵️‍♂️ Pull Request Review Process

1. When you submit a PR, our CI/CD pipeline will automatically run `ruff`, `eslint`, `pytest`, and the Playwright CSV suite.
2. A core maintainer will review your code for security, compliance, and performance.
3. We may ask for changes. Don't be discouraged! It's part of the process to keep the system audit-ready.
4. Once approved and all CI checks pass, your PR will be merged.

Thank you for helping us build the best open-source QMS in the world!
```