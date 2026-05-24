# Project Structure

```
ALC/
├── src/
│   ├── backend/                    # Python FastAPI backend
│   │   ├── src/alcoabase/         # Main package (src layout)
│   │   │   ├── api/              # Route handlers (one file per domain)
│   │   │   │   └── router.py    # Central router aggregation
│   │   │   ├── models/           # SQLAlchemy ORM models
│   │   │   ├── schemas/          # Pydantic request/response schemas
│   │   │   ├── services/         # Business logic layer
│   │   │   ├── middleware/       # FastAPI middleware (audit, setup guard, CSV tagging)
│   │   │   ├── dependencies/     # FastAPI dependency injection (tenant resolution)
│   │   │   ├── tasks/            # Celery async tasks
│   │   │   ├── config.py         # Pydantic settings (env vars)
│   │   │   ├── database.py       # Engine/session factory
│   │   │   └── main.py           # FastAPI app entrypoint
│   │   ├── alembic/              # Database migrations
│   │   ├── scripts/              # CLI utilities (bulk_upload, ensure_tables)
│   │   ├── tests/                # All backend tests
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   ├── properties/       # Hypothesis property-based tests
│   │   │   ├── smoke/            # Tests against running Docker stack
│   │   │   └── conftest.py       # Shared fixtures
│   │   └── pyproject.toml        # uv project config
│   │
│   ├── frontend/                  # React + Vite frontend
│   │   └── src/
│   │       ├── components/       # Reusable UI components (shadcn/ui based)
│   │       ├── pages/            # Route-level page components
│   │       ├── stores/           # Zustand state stores
│   │       ├── hooks/            # Custom React hooks
│   │       ├── lib/              # Utilities (apiClient, helpers)
│   │       ├── types/            # TypeScript type definitions
│   │       └── __tests__/        # Vitest + Testing Library tests
│   │
│   └── csv-runner/               # Playwright E2E validation container
│
├── agents/                        # AI agent YAML definitions (hot-reloaded)
│   ├── archetypes/               # Base personality profiles
│   ├── examples/                 # Concrete agent instances
│   └── schema/                   # JSON Schema for agent definitions
│
├── docs/                          # User-facing feature guides (markdown)
├── Requirements/                  # URS and risk-based testing docs
├── models/                        # Downloaded AI model weights (gitignored)
├── docker-compose.yml            # Full stack orchestration
├── Makefile                      # Developer shortcuts
└── .env / .env.example           # Environment configuration
```

## Architecture Patterns

- **Layered backend**: API routes → Services → Models/DB. Routes are thin; business logic lives in services.
- **One router file per domain**: Each feature (documents, workflows, training, etc.) has its own router in `api/`.
- **Multi-tenancy via headers**: `X-Company-Id` header + dependency injection resolves tenant context.
- **Audit-first design**: Every model uses SQLAlchemy-Continuum for automatic versioning. Middleware enforces `X-Change-Reason` on mutations.
- **src/ layout**: Backend uses `src/alcoabase/` to prevent import bleed during testing.
- **Frontend page-based routing**: Pages map 1:1 to routes. Shared state in Zustand stores, not prop drilling.
- **Agent definitions are data**: YAML files in `agents/` are mounted read-only into the backend container and hot-reloaded via watchfiles.
