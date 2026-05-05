"""Setup Guard middleware for first-run initialization access control.

This middleware intercepts all incoming requests and enforces access control
based on the system's initialization state:

- **Uninitialized**: Only setup endpoints, health check, and documentation
  paths are accessible. All other requests receive HTTP 503.
- **Initialized**: Setup endpoints are permanently blocked (HTTP 403).
  All other requests pass through normally.

The initialization state is cached in-memory to avoid querying the database
on every request. The cache is invalidated by the service layer when setup
completes, triggering an immediate transition to initialized behavior without
requiring an application restart.

References:
    - Requirements: .kiro/specs/setup-wizard/requirements.md (Req 1.1–1.3, 2.1–2.4, 7.3)
    - Design: .kiro/specs/setup-wizard/design.md (SetupGuardMiddleware section)
"""

import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Paths that are always allowed regardless of initialization state.
_ALWAYS_ALLOWED_PATHS: tuple[str, ...] = (
    "/health",
    "/docs",
    "/openapi.json",
)

# Path prefix for setup wizard endpoints.
_SETUP_PATH_PREFIX: str = "/api/v1/setup"


class SetupGuardMiddleware(BaseHTTPMiddleware):
    """Guards all endpoints based on system initialization state.

    Caches the setup status in-memory with invalidation on state change
    to avoid querying the database on every request.

    Class Attributes:
        _is_initialized: Cached initialization state. None means unchecked,
            True means setup is complete, False means setup is pending.
    """

    _is_initialized: bool | None = None

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Route or block requests based on initialization state.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response, or an error response (503/403) if the
            request is blocked by the guard.
        """
        # Resolve cached state; query DB if needed
        is_initialized = await self._check_initialized()

        path = request.url.path

        if not is_initialized:
            # System is uninitialized: allow setup paths and exempt paths only
            if self._is_setup_path(path) or self._is_always_allowed(path):
                return await call_next(request)

            # Block all other paths with 503
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "System setup required",
                    "setup_url": "/api/v1/setup/",
                },
            )

        # System is initialized: block setup paths with 403
        if self._is_setup_path(path):
            return JSONResponse(
                status_code=403,
                content={"detail": "Setup already completed"},
            )

        # Allow all other paths
        return await call_next(request)

    @classmethod
    def invalidate_cache(cls) -> None:
        """Invalidate the cached initialization state.

        Call this from the service layer after setup completion to trigger
        an immediate transition to initialized behavior without requiring
        an application restart.
        """
        cls._is_initialized = None
        logger.info("Setup guard cache invalidated; will re-check on next request.")

    @classmethod
    async def _check_initialized(cls) -> bool:
        """Check whether the system is initialized, using the cache.

        On first call (or after cache invalidation), queries the
        setup_status table. Subsequent calls return the cached value.

        Returns:
            True if the system is initialized, False otherwise.
        """
        if cls._is_initialized is not None:
            return cls._is_initialized

        # Query the database to determine initialization state
        cls._is_initialized = await cls._query_setup_status()
        return cls._is_initialized

    @classmethod
    async def _query_setup_status(cls) -> bool:
        """Query the setup_status table to determine initialization state.

        Handles the case where the database session factory is not yet
        available (e.g., during early startup) by treating the system
        as uninitialized.

        Returns:
            True if a setup_status row exists with is_complete=True,
            False otherwise.
        """
        from alcoabase.database import _session_factory

        if _session_factory is None:
            # DB not initialized yet — treat as uninitialized
            logger.debug(
                "Session factory not available; treating system as uninitialized."
            )
            return False

        try:
            from sqlalchemy import select

            from alcoabase.models.setup_status import SetupStatus

            async with _session_factory() as session:
                result = await session.execute(
                    select(SetupStatus.is_complete).limit(1)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return False
                return bool(row)
        except Exception:
            # If we can't query (table doesn't exist yet, connection error, etc.),
            # treat as uninitialized so setup can proceed.
            logger.warning(
                "Failed to query setup_status table; treating system as uninitialized.",
                exc_info=True,
            )
            return False

    @staticmethod
    def _is_setup_path(path: str) -> bool:
        """Check if the path is a setup wizard endpoint.

        Matches paths that are exactly `/api/v1/setup` or start with
        `/api/v1/setup/`.

        Args:
            path: The request URL path.

        Returns:
            True if the path is a setup endpoint.
        """
        return path == _SETUP_PATH_PREFIX or path.startswith(
            f"{_SETUP_PATH_PREFIX}/"
        )

    @staticmethod
    def _is_always_allowed(path: str) -> bool:
        """Check if the path is always allowed regardless of state.

        Args:
            path: The request URL path.

        Returns:
            True if the path is in the always-allowed list.
        """
        return path in _ALWAYS_ALLOWED_PATHS
