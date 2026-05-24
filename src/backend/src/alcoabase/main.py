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

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alcoabase.api.router import api_router
from alcoabase.middleware import AuditMiddleware, CSVTaggingMiddleware, SetupGuardMiddleware

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan handler — startup and shutdown events
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle.

    Startup:
        - Initialize database connection pool
        - Verify external service connectivity (MinIO, Redis, OpenSearch)
        - Start agent file watcher for hot-reload
    Shutdown:
        - Stop agent file watcher
        - Close database connection pool
        - Shutdown inference services (close shared InferenceClient)
        - Gracefully disconnect from external services
    """
    # --- Startup ---
    from alcoabase.database import close_db, init_db

    await init_db()

    # Validate signature configuration
    _validate_signature_config()

    # Start agent file watcher for hot-reload
    await _start_agent_watcher()

    yield
    # --- Shutdown ---
    # Stop agent file watcher
    await _stop_agent_watcher()

    from alcoabase.services.service_factory import shutdown_services

    await shutdown_services()
    await close_db()


# ---------------------------------------------------------------------------
# Agent File Watcher lifecycle helpers
# ---------------------------------------------------------------------------

# Module-level reference to the AgentRegistryService for watcher lifecycle
_agent_registry_service = None


async def _start_agent_watcher() -> None:
    """Start the agent file watcher during application startup.

    Creates an AgentRegistryService instance (if not already created)
    and starts its file watcher for hot-reload of YAML agent definitions.
    Logs a warning and continues if the watcher fails to start.
    """
    global _agent_registry_service
    try:
        from pathlib import Path

        from alcoabase import database
        from alcoabase.services.agent_registry import AgentRegistryService
        from alcoabase.services.schema_validator import SchemaValidator

        # Resolve paths relative to the project root
        project_root = Path(__file__).parent.parent.parent.parent
        agents_dir = project_root / "agents" / "examples"
        archetypes_dir = project_root / "agents" / "archetypes"
        schema_dir = project_root / "agents" / "schema"

        session_factory = database._session_factory
        if session_factory is None:
            logger.warning(
                "Database session factory not available, skipping agent file watcher."
            )
            return

        schema_validator = SchemaValidator(schema_dir=schema_dir)
        _agent_registry_service = AgentRegistryService(
            session_factory=session_factory,
            schema_validator=schema_validator,
            agents_dir=agents_dir,
            archetypes_dir=archetypes_dir,
        )

        # Wire the service into the agents router for dependency injection
        from alcoabase.api.agents import set_agent_registry_service

        set_agent_registry_service(_agent_registry_service)

        await _agent_registry_service.start_watcher()
    except Exception as e:
        logger.warning("Failed to start agent file watcher: %s", e)


async def _stop_agent_watcher() -> None:
    """Stop the agent file watcher during application shutdown."""
    global _agent_registry_service
    if _agent_registry_service is not None:
        try:
            await _agent_registry_service.stop_watcher()
        except Exception as e:
            logger.warning("Error stopping agent file watcher: %s", e)


# ---------------------------------------------------------------------------
# Signature configuration validation
# ---------------------------------------------------------------------------


def _validate_signature_config() -> None:
    """Validate signature configuration at startup.

    When SIGNATURE_MODE=pades:
    - Validates SIGNATURE_KEY_PATH and SIGNATURE_CERT_PATH are set
    - Validates the key and cert files exist and are readable
    - Validates the private key can be loaded (with password if provided)
    - Validates the certificate matches the private key
    - If any check fails, raises RuntimeError to prevent startup

    When SIGNATURE_MODE is unrecognized (not "pades" or "hash"):
    - Logs a warning and defaults to "hash" mode behavior (no validation needed)

    When SIGNATURE_MODE=hash:
    - No validation needed, logs info message
    """
    from pathlib import Path

    from alcoabase.config import get_settings

    settings = get_settings()

    if settings.signature_mode == "hash":
        logger.info("Signature mode: hash (development/testing — no certificates required)")
        return

    if settings.signature_mode != "pades":
        logger.warning(
            "Unrecognized SIGNATURE_MODE='%s'. Defaulting to 'hash' mode.",
            settings.signature_mode,
        )
        return

    # PAdES mode — validate configuration
    logger.info("Signature mode: pades (production — validating certificate configuration)")

    # Check required paths are set
    if not settings.signature_key_path:
        raise RuntimeError(
            "SIGNATURE_MODE is 'pades' but SIGNATURE_KEY_PATH is not set. "
            "Provide the path to a PEM-encoded private key file."
        )
    if not settings.signature_cert_path:
        raise RuntimeError(
            "SIGNATURE_MODE is 'pades' but SIGNATURE_CERT_PATH is not set. "
            "Provide the path to a PEM-encoded certificate chain file."
        )

    # Check files exist
    key_path = Path(settings.signature_key_path)
    cert_path = Path(settings.signature_cert_path)

    if not key_path.exists():
        raise RuntimeError(
            f"SIGNATURE_KEY_PATH file does not exist: {key_path}"
        )
    if not cert_path.exists():
        raise RuntimeError(
            f"SIGNATURE_CERT_PATH file does not exist: {cert_path}"
        )

    # Try to load the private key and certificate
    try:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            PublicFormat,
            load_pem_private_key,
        )
        from cryptography.x509 import load_pem_x509_certificate

        # Load private key
        key_data = key_path.read_bytes()
        password = (
            settings.signature_key_password.encode("utf-8")
            if settings.signature_key_password
            else None
        )
        private_key = load_pem_private_key(key_data, password=password)

        # Load certificate
        cert_data = cert_path.read_bytes()
        certificate = load_pem_x509_certificate(cert_data)

        # Verify the certificate's public key matches the private key
        cert_public_key = certificate.public_key()
        private_public_key = private_key.public_key()

        # Compare public key bytes
        cert_pub_bytes = cert_public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )
        priv_pub_bytes = private_public_key.public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        )

        if cert_pub_bytes != priv_pub_bytes:
            raise RuntimeError(
                "Certificate public key does not match the private key. "
                "Ensure SIGNATURE_KEY_PATH and SIGNATURE_CERT_PATH correspond to the same key pair."
            )

        logger.info(
            "PAdES signature configuration validated successfully. "
            "Certificate subject: %s",
            certificate.subject.rfc4514_string(),
        )

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Failed to validate signature configuration: {e}. "
            f"Check that SIGNATURE_KEY_PATH ({settings.signature_key_path}) contains a valid "
            f"PEM-encoded private key and SIGNATURE_CERT_PATH ({settings.signature_cert_path}) "
            f"contains a valid PEM-encoded certificate."
        ) from e


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
