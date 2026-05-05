"""AlcoaBase FastAPI application entry point.

Run with:
    uvicorn alcoabase.main:app --reload

This module configures:
- CORS middleware (permissive for development, configurable for production)
- Audit middleware (user_id, reason_for_change, server-side UTC timestamp)
- CSV tagging middleware (validation record tagging)
- Lifespan handler for startup/shutdown events (database connections, etc.)
- Health check endpoint for Docker health probes
- Main API router aggregating all domain sub-routers
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alcoabase.api.router import api_router
from alcoabase.middleware import AuditMiddleware, CSVTaggingMiddleware, SetupGuardMiddleware


# ---------------------------------------------------------------------------
# Lifespan handler — startup and shutdown events
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle.

    Startup:
        - Initialize database connection pool
        - Verify external service connectivity (MinIO, Redis, OpenSearch)
    Shutdown:
        - Close database connection pool
        - Gracefully disconnect from external services
    """
    # --- Startup ---
    from alcoabase.database import close_db, init_db

    await init_db()
    yield
    # --- Shutdown ---
    await close_db()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AlcoaBase",
    description=(
        "Local Document & Knowledge Management System "
        "for GxP-regulated environments."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
# In development, allow all origins. For production deployments, restrict
# allowed_origins via environment configuration (Task 1.4 config.py).

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict via Settings.cors_origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Audit Middleware
# ---------------------------------------------------------------------------
# Injects user_id, reason_for_change, and server-side UTC timestamp into
# the request state for SQLAlchemy-Continuum transaction context.

app.add_middleware(AuditMiddleware)


# ---------------------------------------------------------------------------
# CSV Tagging Middleware
# ---------------------------------------------------------------------------
# Tags requests from the CSV Test User so that records created during
# validation runs are marked with is_csv_validation_record = True.

app.add_middleware(CSVTaggingMiddleware)


# ---------------------------------------------------------------------------
# Setup Guard Middleware
# ---------------------------------------------------------------------------
# Guards all endpoints based on system initialization state. When the system
# is uninitialized, only setup endpoints, health check, and docs are accessible.
# After setup completion, setup endpoints are permanently blocked (403).
# Registered last so it executes first (LIFO middleware stack).

app.add_middleware(SetupGuardMiddleware)


# ---------------------------------------------------------------------------
# Health Check Endpoint
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint for Docker health probes.

    Returns:
        JSON object with status "ok" when the application is running.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Register API Router
# ---------------------------------------------------------------------------

app.include_router(api_router)
