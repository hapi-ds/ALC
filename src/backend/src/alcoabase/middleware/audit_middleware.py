"""Audit middleware for injecting ALCOA+ context into every request.

This middleware extracts audit-relevant metadata from each HTTP request and
stores it on the request state for downstream access by services and the
SQLAlchemy-Continuum transaction context.

Extracted fields:
    - user_id: From the authenticated JWT token (or X-User-Id header)
    - reason_for_change: From the X-Change-Reason request header
    - audit_timestamp: Server-side UTC timestamp (independent of client clock)

For mutating requests (POST, PUT, PATCH, DELETE) to GxP-relevant endpoints,
the X-Change-Reason header is required. If missing, the middleware returns
HTTP 400 to enforce ALCOA+ attributability and contemporaneousness.

References:
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
    - CFR 21 Part 11: electronic records and electronic signatures
    - SQLAlchemy-Continuum: https://sqlalchemy-continuum.readthedocs.io/
"""

from datetime import datetime, timezone

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


# HTTP methods that mutate data and require a change reason
_MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Path prefixes that are exempt from the X-Change-Reason requirement.
# Health checks, search, read-only endpoints, and auth endpoints don't need change reasons.
_EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/v1/auth",
    "/api/v1/setup",
)


class AuditMiddleware(BaseHTTPMiddleware):
    """Injects audit context (user_id, reason, timestamp) into each request.

    This middleware is compatible with SQLAlchemy-Continuum's transaction
    context. Downstream services can access the audit metadata via
    ``request.state.audit_user_id``, ``request.state.audit_reason``, and
    ``request.state.audit_timestamp``.

    Args:
        app: The ASGI application to wrap.
        require_reason_for_mutations: Whether to enforce X-Change-Reason
            on mutating requests. Defaults to True.
    """

    def __init__(
        self,
        app: ASGIApp,
        require_reason_for_mutations: bool = True,
    ) -> None:
        super().__init__(app)
        self.require_reason_for_mutations = require_reason_for_mutations

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, injecting audit context.

        Steps:
            1. Generate server-side UTC timestamp
            2. Extract user_id from X-User-Id header (JWT integration later)
            3. Extract reason_for_change from X-Change-Reason header
            4. For mutating requests to GxP endpoints, require X-Change-Reason
            5. Store audit metadata on request.state for downstream access

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response, or HTTP 400 if change reason is missing
            on a mutating request.
        """
        # 1. Server-side UTC timestamp (independent of client clock)
        audit_timestamp = datetime.now(timezone.utc)

        # 2. Extract user_id from header (JWT token extraction in future)
        # For now, use X-User-Id header. When JWT auth is implemented,
        # this will be replaced with token decoding.
        user_id = _extract_user_id(request)

        # 3. Extract reason for change
        reason_for_change = request.headers.get("X-Change-Reason")

        # 4. Enforce X-Change-Reason on mutating requests to GxP endpoints
        if self.require_reason_for_mutations and _is_mutating_gxp_request(request):
            if not reason_for_change or not reason_for_change.strip():
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": (
                            "X-Change-Reason header is required for mutating "
                            "requests to GxP-relevant endpoints."
                        )
                    },
                )

        # 5. Store audit metadata on request state for downstream access
        request.state.audit_timestamp = audit_timestamp
        request.state.audit_user_id = user_id
        request.state.audit_reason = reason_for_change

        response = await call_next(request)
        return response


def _extract_user_id(request: Request) -> str | None:
    """Extract user_id from the request.

    Currently reads from the X-User-Id header. When JWT authentication
    is implemented, this will decode the token and extract the subject claim.

    Args:
        request: The incoming HTTP request.

    Returns:
        The user ID string, or None if not provided.
    """
    # TODO: Replace with JWT token decoding when auth is implemented
    # token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    # if token:
    #     payload = decode_jwt(token)
    #     return payload.get("sub")
    return request.headers.get("X-User-Id")


def _is_mutating_gxp_request(request: Request) -> bool:
    """Determine if a request is a mutating request to a GxP-relevant endpoint.

    A request is considered mutating and GxP-relevant if:
        - The HTTP method is POST, PUT, PATCH, or DELETE
        - The path is NOT in the exempt list (health, docs, etc.)

    Args:
        request: The incoming HTTP request.

    Returns:
        True if the request requires a change reason.
    """
    if request.method not in _MUTATING_METHODS:
        return False

    path = request.url.path
    for prefix in _EXEMPT_PATH_PREFIXES:
        if path.startswith(prefix):
            return False

    return True
