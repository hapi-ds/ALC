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

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alcoabase.api.router import api_router
from alcoabase.middleware import AuditMiddleware, CSVTaggingMiddleware, SetupGuardMiddleware

if TYPE_CHECKING:
    from alcoabase.literature.services.source_registry import SourceRegistry

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
        - Initialize literature gateway services (when enabled)
    Shutdown:
        - Stop literature health check task
        - Stop agent file watcher
        - Close database connection pool
        - Shutdown inference services (close shared InferenceClient)
        - Gracefully disconnect from external services
    """
    # --- Startup ---
    from alcoabase.database import close_db, init_db

    await init_db()

    # Register immutability listeners for GxP audit trail models
    from alcoabase.models.immutability import register_immutability_listeners

    register_immutability_listeners()

    # Register impact analysis auto-trigger on DocumentVersion creation
    from alcoabase.services.impact_analysis_trigger import (
        register_impact_analysis_trigger,
    )

    register_impact_analysis_trigger()

    # Register traceability alert trigger on ImpactReport creation
    from alcoabase.services.traceability_alert_trigger import (
        register_traceability_alert_trigger,
    )

    register_traceability_alert_trigger()

    # Validate signature configuration
    _validate_signature_config()

    # Start agent file watcher for hot-reload
    await _start_agent_watcher()

    # Initialize literature gateway services
    await _initialize_literature_gateway(app)

    yield
    # --- Shutdown ---
    # Stop literature health check task
    await _shutdown_literature_gateway(app)

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
# Literature Gateway lifecycle helpers
# ---------------------------------------------------------------------------

# Module-level reference to the periodic health check task
_literature_health_check_task: asyncio.Task[None] | None = None


async def _initialize_literature_gateway(app: FastAPI) -> None:
    """Initialize the literature gateway services during startup.

    When ``ALC_LITERATURE_ENABLED=True``:
        1. Validates the encryption key is present (refuses to start if missing).
        2. Creates APIKeyVault with the decoded master key.
        3. Creates SourceRegistry and discovers adapters.
        4. Creates RateLimiter with Redis URL.
        5. Creates CircuitBreaker with Redis URL.
        6. Creates ProxyManager with vault and proxy config.
        7. Creates AuditLogger with async session factory.
        8. Creates LiteratureGatewayService with all dependencies.
        9. Stores all services on app.state for route handler access.
        10. Registers a periodic health check background task.

    When ``ALC_LITERATURE_ENABLED=False``:
        Skips all initialization. Route handlers will return HTTP 503
        since app.state services are None.

    Args:
        app: The FastAPI application instance.

    Raises:
        RuntimeError: If literature_enabled is True but the encryption key
            is missing (wraps EncryptionKeyMissingError).
    """
    import base64
    from pathlib import Path

    from alcoabase.config import get_settings

    settings = get_settings()

    if not settings.literature_enabled:
        logger.info(
            "Literature gateway disabled (ALC_LITERATURE_ENABLED=false). "
            "Skipping initialization."
        )
        return

    # ── Step 1: Validate and decode encryption key ────────────────────────
    if not settings.literature_encryption_key:
        from alcoabase.literature.exceptions import EncryptionKeyMissingError

        raise EncryptionKeyMissingError(
            "ALC_LITERATURE_ENCRYPTION_KEY is required when "
            "ALC_LITERATURE_ENABLED=true. Refusing to start.",
            env_var_name="ALC_LITERATURE_ENCRYPTION_KEY",
        )

    try:
        master_key = base64.b64decode(settings.literature_encryption_key)
    except Exception as e:
        raise RuntimeError(
            f"Failed to base64-decode ALC_LITERATURE_ENCRYPTION_KEY: {e}"
        ) from e

    # ── Step 2: Create APIKeyVault ────────────────────────────────────────
    from alcoabase.literature.services.api_key_vault import APIKeyVault

    api_key_vault = APIKeyVault(master_key)
    logger.info("Literature APIKeyVault initialized.")

    # ── Step 3: Create SourceRegistry and discover adapters ───────────────
    from alcoabase.literature.services.source_registry import SourceRegistry

    source_registry = SourceRegistry()

    # Determine adapter directory: use configured path or default built-in
    if settings.literature_adapter_dir:
        adapter_dir = settings.literature_adapter_dir
    else:
        adapter_dir = str(
            Path(__file__).parent / "literature" / "adapters"
        )

    await source_registry.discover_adapters(adapter_dir)
    logger.info("Literature SourceRegistry initialized.")

    # ── Step 4: Create RateLimiter ────────────────────────────────────────
    from alcoabase.literature.services.rate_limiter import RateLimiter

    rate_limiter = RateLimiter(settings.redis_url)
    logger.info("Literature RateLimiter initialized with Redis.")

    # ── Step 5: Create CircuitBreaker ─────────────────────────────────────
    from alcoabase.literature.services.circuit_breaker import CircuitBreaker

    circuit_breaker = CircuitBreaker(settings.redis_url)
    logger.info("Literature CircuitBreaker initialized with Redis.")

    # ── Step 6: Create ProxyManager ───────────────────────────────────────
    from alcoabase.literature.services.proxy_manager import ProxyManager

    proxy_manager = ProxyManager(vault=api_key_vault)
    logger.info("Literature ProxyManager initialized.")

    # ── Step 7: Create AuditLogger ────────────────────────────────────────
    from alcoabase import database
    from alcoabase.literature.services.audit_logger import AuditLogger

    session_factory = database._session_factory
    if session_factory is None:
        raise RuntimeError(
            "Database session factory not available during literature gateway init."
        )

    audit_logger = AuditLogger(session_factory)
    logger.info("Literature AuditLogger initialized.")

    # ── Step 8: Create LiteratureGatewayService ───────────────────────────
    from alcoabase.literature.services.gateway_service import LiteratureGatewayService

    gateway_service = LiteratureGatewayService(
        source_registry=source_registry,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        api_key_vault=api_key_vault,
        audit_logger=audit_logger,
        proxy_manager=proxy_manager,
    )
    logger.info("Literature LiteratureGatewayService initialized.")

    # ── Step 9: Store services on app.state ───────────────────────────────
    app.state.literature_gateway_service = gateway_service
    app.state.literature_source_registry = source_registry
    app.state.literature_rate_limiter = rate_limiter
    app.state.literature_circuit_breaker = circuit_breaker
    app.state.literature_api_key_vault = api_key_vault
    app.state.literature_audit_logger = audit_logger
    app.state.literature_proxy_manager = proxy_manager
    # proxy_config is loaded from DB on demand; set None initially
    app.state.literature_proxy_config = None

    # ── Step 10: Register periodic health check ───────────────────────────
    global _literature_health_check_task

    interval = settings.literature_health_check_interval_seconds
    _literature_health_check_task = asyncio.create_task(
        _periodic_health_check(source_registry, interval),
        name="literature_health_check",
    )

    logger.info(
        "Literature gateway fully initialized. Health check interval: %ds.",
        interval,
    )


async def _shutdown_literature_gateway(app: FastAPI) -> None:
    """Shutdown the literature gateway services.

    Cancels the periodic health check task if running.

    Args:
        app: The FastAPI application instance.
    """
    global _literature_health_check_task

    if _literature_health_check_task is not None:
        _literature_health_check_task.cancel()
        try:
            await _literature_health_check_task
        except asyncio.CancelledError:
            pass
        _literature_health_check_task = None
        logger.info("Literature health check task stopped.")


async def _periodic_health_check(
    source_registry: "SourceRegistry",
    interval_seconds: int,
) -> None:
    """Run periodic health checks against all registered adapters.

    Loops indefinitely, running health checks at the configured interval.
    Catches all exceptions to ensure the task never crashes silently.

    Args:
        source_registry: The SourceRegistry to check adapters through.
        interval_seconds: Seconds between health check cycles.
    """
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            adapters = source_registry.list_adapters()
            for adapter_info in adapters:
                adapter_name = adapter_info.get("name", "")
                if adapter_name:
                    try:
                        status = await source_registry.run_health_check(adapter_name)
                        logger.debug(
                            "Health check for '%s': %s", adapter_name, status
                        )
                    except Exception as e:
                        logger.warning(
                            "Health check failed for '%s': %s", adapter_name, e
                        )
        except asyncio.CancelledError:
            logger.info("Periodic health check task cancelled.")
            break
        except Exception as e:
            logger.error("Unexpected error in health check loop: %s", e)


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
