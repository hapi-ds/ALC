# Tech Stack & Build System

## Backend

- **Language**: Python 3.12+
- **Framework**: FastAPI + Uvicorn
- **ORM**: SQLAlchemy 2.0 (async via asyncpg) + SQLAlchemy-Continuum (audit tables)
- **Migrations**: Alembic
- **Validation**: Pydantic v2, pydantic-settings for env config
- **Task Queue**: Celery + Redis
- **PDF**: ReportLab (generation), PyMuPDF (extraction)
- **Workflows**: SpiffWorkflow (BPMN engine)
- **Signatures**: pyhanko (PAdES)
- **AI/RAG**: llama-index, dspy, httpx (vLLM client)
- **Search**: opensearch-py
- **Storage**: aioboto3 (MinIO S3-compatible)
- **Testing**: pytest, pytest-asyncio, Hypothesis (property-based), respx (HTTP mocking)
- **Linting**: Ruff
- **Package Manager**: uv (exclusively — never pip/poetry/conda)

## Frontend

- **Language**: TypeScript
- **Framework**: React 19 (Vite)
- **Styling**: Tailwind CSS 4 + shadcn/ui (Radix primitives)
- **State**: Zustand
- **Forms**: react-hook-form
- **Drag & Drop**: @hello-pangea/dnd
- **BPMN**: bpmn-js
- **Routing**: react-router-dom v7
- **Testing**: Vitest + Testing Library + fast-check (property-based)
- **Linting**: ESLint + typescript-eslint

## Infrastructure

- **Orchestration**: Docker Compose
- **Database**: PostgreSQL 16
- **Object Storage**: MinIO
- **Search/Vectors**: OpenSearch 2.16
- **Cache/Queue**: Redis 7
- **AI Inference**: vLLM (OpenAI-compatible API)
- **Validation**: Playwright (CSV runner container)

## Common Commands

All backend commands run from `src/backend/`:

```bash
# Run all backend tests (unit + property)
cd src/backend && uv run pytest --tb=short -q

# Run integration tests
cd src/backend && uv run pytest tests/integration/ -v

# Lint backend
cd src/backend && uv run ruff check .

# Type check
cd src/backend && uv run ty check
```

All frontend commands run from `src/frontend/`:

```bash
# Run frontend tests
cd src/frontend && npx vitest run

# Lint frontend
cd src/frontend && npm run lint

# Build frontend
cd src/frontend && npm run build
```

Docker / infrastructure:

```bash
# Start all services
make up

# Run migrations
make migrate

# Full setup wizard (creates admin, company, seeds demo data)
make setup

# Health check all services
make health

# Run all tests (backend + frontend)
make test
```
