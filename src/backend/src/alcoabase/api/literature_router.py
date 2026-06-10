"""FastAPI router for literature search engine endpoints.

Provides endpoints for:
- Literature search (POST /search) — dispatches to gateway service
- Source registry listing (GET /sources)
- Admin rate-limit management (GET/PUT /admin/rate-limits)
- Admin proxy configuration (GET/PUT /admin/proxy)
- Source health monitoring (GET /health)
- Company usage metrics (GET /usage/{company_id})
- Source configuration CRUD (under /sources/{company_id}/configurations)
- Search profile CRUD (under /sources/{company_id}/profiles)
- Async task polling and cancellation (GET/DELETE /tasks/{task_id})

Exception handlers:
- RateLimitExceededError → HTTP 429 with Retry-After header
- AllSourcesUnavailableError → HTTP 503

References:
    - Requirements: 3.1, 3.2, 3.7, 3.8, 3.9, 5.7, 6.6, 7.1, 8.1, 8.7,
      11.4, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 15.2, 15.4, 15.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import ceil
from typing import Annotated

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.literature.exceptions import (
    AllSourcesUnavailableError,
    RateLimitExceededError,
)
from alcoabase.literature.models.literature import SearchProfile, SourceConfiguration
from alcoabase.literature.schemas.admin import (
    CompanyUsageResponse,
    ProxyConfigurationResponse,
    ProxyConfigurationUpdate,
    SourceHealthResponse,
    SystemRateLimitResponse,
    SystemRateLimitUpdate,
)
from alcoabase.literature.schemas.configuration import (
    SourceConfigurationCreate,
    SourceConfigurationResponse,
    SourceConfigurationUpdate,
)
from alcoabase.literature.schemas.profiles import (
    SearchProfileCreate,
    SearchProfileResponse,
    SearchProfileUpdate,
)
from alcoabase.literature.schemas.search import (
    AdapterRegistryEntry,
    AsyncTaskResponse,
    AsyncTaskStatus,
    SearchQuery,
    SearchResponse,
    TaskStatus,
)
from alcoabase.literature.services.api_key_vault import APIKeyVault, EncryptedKey
from alcoabase.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/literature", tags=["Literature Search"])


# ─────────────────────────────────────────────────────────────────────────────
# Service Dependencies
# ─────────────────────────────────────────────────────────────────────────────


def _get_gateway_service():
    """Get the LiteratureGatewayService instance from app state.

    Returns a placeholder that will be replaced during app startup (task 17.1).
    For now, returns None — endpoints will raise 503 if service not initialized.
    """
    return None


def _get_source_registry():
    """Get the SourceRegistry instance from app state.

    Returns None until startup wiring (task 17.1) initializes it.
    """
    return None


def _get_rate_limiter():
    """Get the RateLimiter instance from app state.

    Returns None until startup wiring (task 17.1) initializes it.
    """
    return None


# ─────────────────────────────────────────────────────────────────────────────
# POST /search — Literature Search Endpoint
# Requirements: 8.1, 8.7, 14.5
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/search",
    response_model=SearchResponse,
    responses={
        202: {"model": AsyncTaskResponse, "description": "Search dispatched asynchronously"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "All sources unavailable"},
    },
    summary="Search literature sources",
)
async def search_literature(
    query: SearchQuery,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
) -> JSONResponse | SearchResponse:
    """Execute a literature search across enabled sources.

    Dispatches the search query to enabled adapters for the requesting
    company. If the query targets more than 3 sources or requests more
    than 50 results, it is dispatched asynchronously via Celery and an
    HTTP 202 response with a task ID is returned.

    Requires at least the ``member`` role within the requesting company.

    Args:
        query: Structured search query with terms, filters, pagination.
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with user_id and company_id.
        x_change_reason: Required audit trail reason for ALCOA+ compliance.

    Returns:
        SearchResponse (200) for synchronous results, or
        AsyncTaskResponse (202) for async dispatch.

    Raises:
        HTTPException 403: If user lacks member role.
        HTTPException 429: If company rate limit exceeded.
        HTTPException 503: If all sources are unavailable.
    """
    # Enforce minimum member role
    if ctx.membership_role not in ("member", "admin", "document_admin", "system_admin"):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Requires at least member role.",
        )

    # Get gateway service from app state
    gateway_service = getattr(request.app.state, "literature_gateway_service", None)
    if gateway_service is None:
        raise HTTPException(
            status_code=503,
            detail="Literature search service is not initialized.",
        )

    # Get source configs for the company from app state or DB
    source_configs = getattr(request.app.state, "_literature_source_configs", None)

    try:
        # Check if this should be dispatched async
        if gateway_service.should_dispatch_async(
            query, ctx.company_id, source_configs=source_configs
        ):
            # Dispatch as Celery task
            task = celery_app.send_task(
                "alcoabase.tasks.literature_search_tasks.execute_literature_search",
                kwargs={
                    "query_data": query.model_dump(mode="json"),
                    "company_id": ctx.company_id,
                    "user_id": ctx.user_id,
                },
            )
            async_response = AsyncTaskResponse(
                task_id=task.id,
                status=TaskStatus.QUEUED,
                status_url=f"/api/literature/tasks/{task.id}",
            )
            return JSONResponse(
                status_code=202,
                content=async_response.model_dump(mode="json"),
            )

        # Synchronous search
        response = await gateway_service.search(
            query=query,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            source_configs=source_configs,
        )
        return response

    except RateLimitExceededError as e:
        retry_after = ceil(e.retry_after_seconds)
        return JSONResponse(
            status_code=429,
            content={
                "detail": e.message,
                "retry_after_seconds": e.retry_after_seconds,
            },
            headers={"Retry-After": str(retry_after)},
        )
    except AllSourcesUnavailableError as e:
        return JSONResponse(
            status_code=503,
            content={
                "detail": e.message,
                "estimated_recovery_time": e.estimated_recovery_time,
                "unavailable_sources": e.unavailable_sources,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /sources — List Registered Adapters
# Requirements: 1.6, 14.6
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/sources",
    response_model=list[AdapterRegistryEntry],
    summary="List registered source adapters",
)
async def list_sources(
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
) -> list[AdapterRegistryEntry]:
    """List all registered source adapters with capabilities and health status.

    Returns adapter metadata, supported query capabilities, and current
    health classification for each registered adapter.

    Requires at least the ``member`` role.

    Args:
        request: FastAPI request for app state access.
        ctx: Resolved tenant context.

    Returns:
        List of AdapterRegistryEntry with name, version, capabilities, status.
    """
    source_registry = getattr(request.app.state, "literature_source_registry", None)
    if source_registry is None:
        return []

    adapters = source_registry.list_adapters()
    return [
        AdapterRegistryEntry(
            name=a["name"],
            version=a["version"],
            display_name=a["display_name"],
            requires_api_key=a["requires_api_key"],
            capabilities=a["capabilities"],
            status=a["status"],
            last_health_check=a.get("last_health_check"),
        )
        for a in adapters
    ]


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/rate-limits — System Rate Limit Configuration
# Requirements: 5.7, 14.3
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/rate-limits",
    response_model=list[SystemRateLimitResponse],
    summary="Get system-level rate limits",
)
async def get_rate_limits(
    request: Request,
    ctx: TenantContext = Depends(require_permission("literature_admin", "read")),
) -> list[SystemRateLimitResponse]:
    """Get system-level rate limit configuration for all sources.

    Returns the current rate limit settings for each registered source
    adapter including requests per second and max queue size.

    Requires ``system_admin`` role (via literature_admin:read permission).

    Args:
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with admin permissions.

    Returns:
        List of SystemRateLimitResponse for each configured source.
    """
    source_registry = getattr(request.app.state, "literature_source_registry", None)
    rate_limiter = getattr(request.app.state, "literature_rate_limiter", None)

    if source_registry is None or rate_limiter is None:
        return []

    adapters = source_registry.list_adapters()
    results: list[SystemRateLimitResponse] = []

    for adapter in adapters:
        limit = await rate_limiter.get_system_limit(adapter["name"])
        results.append(
            SystemRateLimitResponse(
                source_adapter_name=adapter["name"],
                requests_per_second=limit,
                max_queue_size=500,
                updated_at=datetime.now(timezone.utc),
            )
        )

    return results


@router.put(
    "/admin/rate-limits/{source_name}",
    response_model=SystemRateLimitResponse,
    summary="Update system-level rate limit for a source",
)
async def update_rate_limit(
    source_name: str,
    payload: SystemRateLimitUpdate,
    request: Request,
    ctx: TenantContext = Depends(require_permission("literature_admin", "update")),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
) -> SystemRateLimitResponse:
    """Update system-level rate limit for a specific source adapter.

    Sets a new requests-per-second limit (1–1000) for the specified source.
    The change takes effect within 1 second without requiring a restart.

    Requires ``system_admin`` role (via literature_admin:update permission).

    Args:
        source_name: Name of the source adapter to update.
        payload: Rate limit update with new RPS value.
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with admin permissions.
        x_change_reason: Required audit trail reason.

    Returns:
        Updated SystemRateLimitResponse.

    Raises:
        HTTPException 404: If source_name is not registered.
        HTTPException 422: If RPS is outside valid range.
    """
    source_registry = getattr(request.app.state, "literature_source_registry", None)
    rate_limiter = getattr(request.app.state, "literature_rate_limiter", None)

    if source_registry is None or rate_limiter is None:
        raise HTTPException(
            status_code=503,
            detail="Literature service is not initialized.",
        )

    # Validate source exists
    if source_registry.get_adapter(source_name) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Source adapter '{source_name}' not found in registry.",
        )

    # Update rate limit
    try:
        await rate_limiter.set_system_limit(source_name, payload.requests_per_second)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    logger.info(
        "System rate limit updated for '%s' to %d RPS by user %d. Reason: %s",
        source_name,
        payload.requests_per_second,
        ctx.user_id,
        x_change_reason,
    )

    return SystemRateLimitResponse(
        source_adapter_name=source_name,
        requests_per_second=payload.requests_per_second,
        max_queue_size=payload.max_queue_size or 500,
        updated_at=datetime.now(timezone.utc),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET/PUT /admin/proxy — Proxy Configuration
# Requirements: 7.1, 14.4
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/admin/proxy",
    response_model=ProxyConfigurationResponse,
    summary="Get proxy configuration",
)
async def get_proxy_config(
    request: Request,
    ctx: TenantContext = Depends(require_permission("literature_admin", "read")),
) -> ProxyConfigurationResponse:
    """Get the current global proxy configuration for literature API requests.

    Returns proxy URL, no-proxy list, active state, and whether credentials
    are configured (credentials are never returned in plaintext).

    Requires ``system_admin`` role (via literature_admin:read permission).

    Args:
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with admin permissions.

    Returns:
        ProxyConfigurationResponse with current proxy settings.

    Raises:
        HTTPException 404: If no proxy configuration exists.
    """
    proxy_config = getattr(request.app.state, "literature_proxy_config", None)

    if proxy_config is None:
        raise HTTPException(
            status_code=404,
            detail="No proxy configuration found.",
        )

    return ProxyConfigurationResponse(
        proxy_url=proxy_config.proxy_url,
        username_ciphertext=proxy_config.username_ciphertext,
        no_proxy_list=proxy_config.no_proxy_list or [],
        is_active=proxy_config.is_active,
        updated_at=proxy_config.updated_at,
    )


@router.put(
    "/admin/proxy",
    response_model=ProxyConfigurationResponse,
    summary="Update proxy configuration",
)
async def update_proxy_config(
    payload: ProxyConfigurationUpdate,
    request: Request,
    ctx: TenantContext = Depends(require_permission("literature_admin", "update")),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
) -> ProxyConfigurationResponse:
    """Update the global proxy configuration for literature API requests.

    Allows updating proxy URL, credentials (stored encrypted), no-proxy list,
    and active state. Only provided fields are updated.

    Requires ``system_admin`` role (via literature_admin:update permission).

    Args:
        payload: Proxy configuration update with optional fields.
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with admin permissions.
        x_change_reason: Required audit trail reason.

    Returns:
        Updated ProxyConfigurationResponse.

    Raises:
        HTTPException 503: If literature service is not initialized.
    """
    proxy_config = getattr(request.app.state, "literature_proxy_config", None)

    if proxy_config is None:
        raise HTTPException(
            status_code=503,
            detail="Literature service is not initialized. No proxy configuration available.",
        )

    # Apply updates to the proxy config object
    if payload.proxy_url is not None:
        proxy_config.proxy_url = payload.proxy_url
    if payload.no_proxy_list is not None:
        proxy_config.no_proxy_list = payload.no_proxy_list
    if payload.is_active is not None:
        proxy_config.is_active = payload.is_active

    # Handle credential encryption if provided
    if payload.username is not None or payload.password is not None:
        api_key_vault = getattr(request.app.state, "literature_api_key_vault", None)
        if api_key_vault is not None:
            if payload.username is not None:
                encrypted = api_key_vault.encrypt(payload.username)
                proxy_config.username_ciphertext = encrypted.ciphertext
                proxy_config.username_nonce = encrypted.nonce
                proxy_config.username_tag = encrypted.tag
            if payload.password is not None:
                encrypted = api_key_vault.encrypt(payload.password)
                proxy_config.password_ciphertext = encrypted.ciphertext
                proxy_config.password_nonce = encrypted.nonce
                proxy_config.password_tag = encrypted.tag

    proxy_config.updated_at = datetime.now(timezone.utc)

    logger.info(
        "Proxy configuration updated by user %d. Reason: %s",
        ctx.user_id,
        x_change_reason,
    )

    return ProxyConfigurationResponse(
        proxy_url=proxy_config.proxy_url,
        username_ciphertext=proxy_config.username_ciphertext,
        no_proxy_list=proxy_config.no_proxy_list or [],
        is_active=proxy_config.is_active,
        updated_at=proxy_config.updated_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /health — Source Health Status
# Requirements: 11.4
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/health",
    response_model=list[SourceHealthResponse],
    summary="Get source health status",
)
async def get_source_health(
    request: Request,
    ctx: TenantContext = Depends(require_permission("literature_admin", "read")),
) -> list[SourceHealthResponse]:
    """Get health status for all registered source adapters.

    Returns current health classification, last check timestamp, average
    response time, consecutive failure count, and whether the source is
    flagged for administrator attention.

    Requires ``system_admin`` role (via literature_admin:read permission).

    Args:
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with admin permissions.

    Returns:
        List of SourceHealthResponse for each registered adapter.
    """
    source_registry = getattr(request.app.state, "literature_source_registry", None)
    if source_registry is None:
        return []

    adapters = source_registry.list_adapters()
    results: list[SourceHealthResponse] = []

    for adapter in adapters:
        adapter_name = adapter["name"]
        health_history = source_registry.get_health_history(adapter_name) or []

        # Calculate average response time over recent checks
        recent_times = [
            h.response_time_seconds
            for h in health_history
            if h.response_time_seconds is not None
        ]
        avg_response_ms = (
            (sum(recent_times) / len(recent_times) * 1000)
            if recent_times
            else None
        )

        # Count consecutive failures from the end
        consecutive_failures = 0
        for h in reversed(health_history):
            if h.status == "unreachable":
                consecutive_failures += 1
            else:
                break

        last_check = health_history[-1].timestamp if health_history else None

        results.append(
            SourceHealthResponse(
                source_adapter_name=adapter_name,
                status=adapter["status"],
                last_check_timestamp=last_check,
                avg_response_time_ms=avg_response_ms,
                consecutive_failure_count=consecutive_failures,
                flagged_for_attention=adapter.get("flagged_for_attention", False),
            )
        )

    return results


# ─────────────────────────────────────────────────────────────────────────────
# GET /usage/{company_id} — Company Usage Metrics
# Requirements: 6.6
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/usage/{company_id}",
    response_model=CompanyUsageResponse,
    summary="Get company usage metrics",
)
async def get_company_usage(
    company_id: int,
    request: Request,
    ctx: TenantContext = Depends(require_permission("literature_config", "read")),
) -> CompanyUsageResponse:
    """Get literature search usage metrics for a specific company.

    Returns request counts (made, queued, rate-limited) for the current
    reporting period. Accessible by document_admin and system_admin roles.

    Requires ``document_admin`` or higher role (via literature_config:read
    permission).

    Args:
        company_id: The company to retrieve usage metrics for.
        request: FastAPI request for app state access.
        ctx: Resolved tenant context with admin permissions.

    Returns:
        CompanyUsageResponse with usage metrics for the company.

    Raises:
        HTTPException 503: If rate limiter is not initialized.
    """
    rate_limiter = getattr(request.app.state, "literature_rate_limiter", None)
    if rate_limiter is None:
        raise HTTPException(
            status_code=503,
            detail="Literature rate limiter is not initialized.",
        )

    usage = await rate_limiter.get_company_usage(company_id)
    now = datetime.now(timezone.utc)

    return CompanyUsageResponse(
        company_id=company_id,
        requests_made=usage.get("requests_made", 0),
        requests_queued=usage.get("requests_queued", 0),
        requests_rate_limited=usage.get("requests_rate_limited", 0),
        period_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
        period_end=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /tasks/{task_id} — Async Task Status
# Requirements: 15.2
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/tasks/{task_id}",
    response_model=AsyncTaskStatus,
    summary="Get async task status",
)
async def get_task_status(
    task_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
) -> AsyncTaskStatus:
    """Get the status of an asynchronous literature search task.

    Returns the current task status (queued, running, completed, failed),
    progress percentage, partial results if available, and error message
    if the task failed.

    Requires at least the ``member`` role.

    Args:
        task_id: Unique Celery task identifier.
        ctx: Resolved tenant context.

    Returns:
        AsyncTaskStatus with current task state and any results.

    Raises:
        HTTPException 404: If the task is not found.
    """
    result = AsyncResult(task_id, app=celery_app)

    # Check if the task actually exists in the backend
    # PENDING with no backend record means it was never created
    if result.state == "PENDING":
        backend_meta = celery_app.backend.get_task_meta(task_id)
        if backend_meta.get("result") is None and backend_meta.get("status") == "PENDING":
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found.",
            )

    # Map Celery states to our TaskStatus enum
    status, progress, partial_results, error_message = _map_celery_state(result)

    return AsyncTaskStatus(
        task_id=task_id,
        status=status,
        progress_percent=progress,
        partial_results=partial_results,
        error_message=error_message,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /tasks/{task_id} — Cancel Async Task
# Requirements: 15.4, 15.5
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/tasks/{task_id}",
    response_model=AsyncTaskStatus,
    summary="Cancel an async task",
)
async def cancel_task(
    task_id: str,
    ctx: TenantContext = Depends(get_tenant_context),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
) -> AsyncTaskStatus:
    """Cancel a running or queued asynchronous literature search task.

    Stops further source queries but retains any partial results already
    collected. The task is marked as failed with a cancellation message.

    Requires at least the ``member`` role and X-Change-Reason header.

    Args:
        task_id: Unique Celery task identifier to cancel.
        ctx: Resolved tenant context.
        x_change_reason: Required audit trail reason for cancellation.

    Returns:
        AsyncTaskStatus with final state after cancellation.

    Raises:
        HTTPException 404: If the task is not found.
    """
    result = AsyncResult(task_id, app=celery_app)

    # Check if the task exists
    if result.state == "PENDING":
        backend_meta = celery_app.backend.get_task_meta(task_id)
        if backend_meta.get("result") is None and backend_meta.get("status") == "PENDING":
            raise HTTPException(
                status_code=404,
                detail=f"Task '{task_id}' not found.",
            )

    # Get partial results before revoking
    partial_results = None
    progress = 0
    if result.info and isinstance(result.info, dict):
        progress = result.info.get("progress_percent", 0)
        partial_data = result.info.get("partial_results")
        if partial_data is not None:
            partial_results = SearchResponse(**partial_data)

    # Revoke the task
    celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")

    logger.info(
        "Task '%s' cancelled by user %d. Reason: %s",
        task_id,
        ctx.user_id,
        x_change_reason,
    )

    return AsyncTaskStatus(
        task_id=task_id,
        status=TaskStatus.FAILED,
        progress_percent=progress,
        partial_results=partial_results,
        error_message="Task cancelled by user.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Source Configuration CRUD Endpoints
# Requirements: 3.1, 3.2, 3.7, 3.8, 3.9, 14.1
# ═══════════════════════════════════════════════════════════════════════════════


def _require_config_admin_dep():
    """Return a dependency enforcing document_admin or system_admin role.

    Returns:
        A FastAPI dependency function that raises HTTP 403 if the user
        does not have an admin-level membership role.
    """

    async def _check(
        tenant: TenantContext = Depends(get_tenant_context),
    ) -> TenantContext:
        allowed_roles = {"document_admin", "system_admin", "admin"}
        if tenant.membership_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Requires document_admin or system_admin role.",
            )
        return tenant

    return _check


require_config_admin = _require_config_admin_dep()


def _get_vault() -> APIKeyVault | None:
    """Attempt to create an APIKeyVault from environment.

    Returns:
        APIKeyVault instance or None if encryption key is not configured.
    """
    try:
        return APIKeyVault.from_env()
    except Exception:
        return None


def _build_config_response(
    config: SourceConfiguration,
    vault: APIKeyVault | None,
) -> SourceConfigurationResponse:
    """Build a SourceConfigurationResponse from a model instance.

    Masks the API key if one is stored. Never exposes plaintext or ciphertext.

    Args:
        config: The SQLAlchemy SourceConfiguration model instance.
        vault: Optional APIKeyVault for decrypting and masking keys.

    Returns:
        SourceConfigurationResponse with masked API key.
    """
    api_key_masked: str | None = None
    if config.api_key_ciphertext and vault:
        try:
            encrypted = EncryptedKey(
                ciphertext=config.api_key_ciphertext,
                nonce=config.api_key_nonce or "",
                tag=config.api_key_tag or "",
            )
            plaintext = vault.decrypt(encrypted)
            api_key_masked = APIKeyVault.mask_key(plaintext)
        except Exception:
            api_key_masked = "****"
    elif config.api_key_ciphertext:
        api_key_masked = "****"

    return SourceConfigurationResponse(
        id=config.id,
        company_id=config.company_id,
        source_adapter_name=config.source_adapter_name,
        is_enabled=config.is_enabled,
        api_key_masked=api_key_masked,
        priority=config.priority,
        rate_limit_rpm=config.rate_limit_rpm,
        proxy_override_url=config.proxy_override_url,
        contact_email=config.contact_email,
        extra_config=config.extra_config,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.post(
    "/sources/{company_id}/configurations",
    response_model=SourceConfigurationResponse,
    status_code=201,
)
async def create_source_configuration(
    company_id: Annotated[int, Path(description="Company ID")],
    payload: SourceConfigurationCreate,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    tenant: TenantContext = Depends(require_config_admin),
    session: AsyncSession = Depends(get_db_session),
) -> SourceConfigurationResponse:
    """Create a per-company source configuration.

    Encrypts the API key before storage. Enforces uniqueness on
    (company_id, source_adapter_name).

    Args:
        company_id: The company this configuration belongs to.
        payload: Configuration creation data.
        x_change_reason: Audit trail reason (enforced by middleware).
        tenant: Tenant context with role check.
        session: Database session.

    Returns:
        Created source configuration with masked API key.

    Raises:
        HTTPException: 400 if X-Change-Reason missing.
        HTTPException: 403 if insufficient role.
        HTTPException: 409 if duplicate (company_id, source_adapter_name).
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )

    vault = _get_vault()
    api_key_ciphertext: str | None = None
    api_key_nonce: str | None = None
    api_key_tag: str | None = None

    if payload.api_key and vault:
        encrypted = vault.encrypt(payload.api_key)
        api_key_ciphertext = encrypted.ciphertext
        api_key_nonce = encrypted.nonce
        api_key_tag = encrypted.tag

    config = SourceConfiguration(
        company_id=company_id,
        source_adapter_name=payload.source_adapter_name,
        is_enabled=payload.is_enabled,
        api_key_ciphertext=api_key_ciphertext,
        api_key_nonce=api_key_nonce,
        api_key_tag=api_key_tag,
        priority=payload.priority,
        rate_limit_rpm=payload.rate_limit_rpm,
        proxy_override_url=payload.proxy_override_url,
        contact_email=payload.contact_email,
        extra_config=payload.extra_config,
    )
    session.add(config)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"Configuration for source '{payload.source_adapter_name}' "
                f"already exists for company_id={company_id}."
            ),
        )

    await session.refresh(config)

    logger.info(
        "Created source configuration '%s' for company_id=%d (reason='%s').",
        payload.source_adapter_name,
        company_id,
        x_change_reason,
    )

    return _build_config_response(config, vault)


@router.get(
    "/sources/{company_id}/configurations",
    response_model=list[SourceConfigurationResponse],
)
async def list_source_configurations(
    company_id: Annotated[int, Path(description="Company ID")],
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[SourceConfigurationResponse]:
    """List all source configurations for a company.

    Args:
        company_id: The company to list configurations for.
        tenant: Tenant context (any authenticated user).
        session: Database session.

    Returns:
        List of source configurations with masked API keys.
    """
    stmt = (
        select(SourceConfiguration)
        .where(SourceConfiguration.company_id == company_id)
        .order_by(
            SourceConfiguration.priority,
            SourceConfiguration.source_adapter_name,
        )
    )
    result = await session.execute(stmt)
    configs = result.scalars().all()

    vault = _get_vault()
    return [_build_config_response(c, vault) for c in configs]


@router.get(
    "/sources/{company_id}/configurations/{config_id}",
    response_model=SourceConfigurationResponse,
)
async def get_source_configuration(
    company_id: Annotated[int, Path(description="Company ID")],
    config_id: Annotated[int, Path(description="Configuration ID")],
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> SourceConfigurationResponse:
    """Retrieve a specific source configuration by ID.

    Args:
        company_id: The company this configuration belongs to.
        config_id: The configuration record ID.
        tenant: Tenant context (any authenticated user).
        session: Database session.

    Returns:
        Source configuration with masked API key.

    Raises:
        HTTPException: 404 if configuration not found.
    """
    config = await session.get(SourceConfiguration, config_id)
    if config is None or config.company_id != company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Source configuration with id={config_id} not found.",
        )

    vault = _get_vault()
    return _build_config_response(config, vault)


@router.put(
    "/sources/{company_id}/configurations/{config_id}",
    response_model=SourceConfigurationResponse,
)
async def update_source_configuration(
    company_id: Annotated[int, Path(description="Company ID")],
    config_id: Annotated[int, Path(description="Configuration ID")],
    payload: SourceConfigurationUpdate,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    tenant: TenantContext = Depends(require_config_admin),
    session: AsyncSession = Depends(get_db_session),
) -> SourceConfigurationResponse:
    """Update an existing source configuration.

    Only non-None fields in the payload are applied. API key is
    re-encrypted if provided.

    Args:
        company_id: The company this configuration belongs to.
        config_id: The configuration record ID.
        payload: Partial update data.
        x_change_reason: Audit trail reason (enforced by middleware).
        tenant: Tenant context with role check.
        session: Database session.

    Returns:
        Updated source configuration with masked API key.

    Raises:
        HTTPException: 400 if X-Change-Reason missing.
        HTTPException: 403 if insufficient role.
        HTTPException: 404 if configuration not found.
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )

    config = await session.get(SourceConfiguration, config_id)
    if config is None or config.company_id != company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Source configuration with id={config_id} not found.",
        )

    vault = _get_vault()

    if payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled
    if payload.api_key is not None and vault:
        encrypted = vault.encrypt(payload.api_key)
        config.api_key_ciphertext = encrypted.ciphertext
        config.api_key_nonce = encrypted.nonce
        config.api_key_tag = encrypted.tag
    if payload.priority is not None:
        config.priority = payload.priority
    if payload.rate_limit_rpm is not None:
        config.rate_limit_rpm = payload.rate_limit_rpm
    if payload.proxy_override_url is not None:
        config.proxy_override_url = payload.proxy_override_url
    if payload.contact_email is not None:
        config.contact_email = payload.contact_email
    if payload.extra_config is not None:
        config.extra_config = payload.extra_config

    await session.flush()
    await session.refresh(config)

    logger.info(
        "Updated source configuration id=%d for company_id=%d (reason='%s').",
        config_id,
        company_id,
        x_change_reason,
    )

    return _build_config_response(config, vault)


@router.delete(
    "/sources/{company_id}/configurations/{config_id}",
    status_code=204,
)
async def delete_source_configuration(
    company_id: Annotated[int, Path(description="Company ID")],
    config_id: Annotated[int, Path(description="Configuration ID")],
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    tenant: TenantContext = Depends(require_config_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a source configuration.

    Args:
        company_id: The company this configuration belongs to.
        config_id: The configuration record ID.
        x_change_reason: Audit trail reason (enforced by middleware).
        tenant: Tenant context with role check.
        session: Database session.

    Raises:
        HTTPException: 400 if X-Change-Reason missing.
        HTTPException: 403 if insufficient role.
        HTTPException: 404 if configuration not found.
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )

    config = await session.get(SourceConfiguration, config_id)
    if config is None or config.company_id != company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Source configuration with id={config_id} not found.",
        )

    await session.delete(config)

    logger.info(
        "Deleted source configuration id=%d (adapter='%s', company_id=%d, reason='%s').",
        config_id,
        config.source_adapter_name,
        company_id,
        x_change_reason,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Search Profile CRUD Endpoints
# Requirements: 3.9, 14.2, 14.7
# ═══════════════════════════════════════════════════════════════════════════════


@router.post(
    "/sources/{company_id}/profiles",
    response_model=SearchProfileResponse,
    status_code=201,
)
async def create_search_profile(
    company_id: Annotated[int, Path(description="Company ID")],
    payload: SearchProfileCreate,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    tenant: TenantContext = Depends(require_config_admin),
    session: AsyncSession = Depends(get_db_session),
) -> SearchProfileResponse:
    """Create a search profile for a company.

    If ``is_default`` is True, atomically unsets any existing default
    profile for the company.

    Args:
        company_id: The company this profile belongs to.
        payload: Profile creation data.
        x_change_reason: Audit trail reason (enforced by middleware).
        tenant: Tenant context with role check.
        session: Database session.

    Returns:
        Created search profile.

    Raises:
        HTTPException: 400 if X-Change-Reason missing.
        HTTPException: 403 if insufficient role.
        HTTPException: 409 if duplicate (company_id, name).
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )

    # Enforce single default per company
    if payload.is_default:
        stmt = select(SearchProfile).where(
            SearchProfile.company_id == company_id,
            SearchProfile.is_default == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        existing_defaults = result.scalars().all()
        for profile in existing_defaults:
            profile.is_default = False

    profile = SearchProfile(
        company_id=company_id,
        name=payload.name,
        is_default=payload.is_default,
        enabled_sources=payload.enabled_sources,
        source_priorities=payload.source_priorities,
        default_filters=payload.default_filters,
    )
    session.add(profile)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"Search profile '{payload.name}' already exists "
                f"for company_id={company_id}."
            ),
        )

    await session.refresh(profile)

    logger.info(
        "Created search profile '%s' for company_id=%d (reason='%s').",
        payload.name,
        company_id,
        x_change_reason,
    )

    return SearchProfileResponse.model_validate(profile)


@router.get(
    "/sources/{company_id}/profiles",
    response_model=list[SearchProfileResponse],
)
async def list_search_profiles(
    company_id: Annotated[int, Path(description="Company ID")],
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[SearchProfileResponse]:
    """List all search profiles for a company.

    Args:
        company_id: The company to list profiles for.
        tenant: Tenant context (any authenticated user).
        session: Database session.

    Returns:
        List of search profiles ordered by name.
    """
    stmt = (
        select(SearchProfile)
        .where(SearchProfile.company_id == company_id)
        .order_by(SearchProfile.name)
    )
    result = await session.execute(stmt)
    profiles = result.scalars().all()

    return [SearchProfileResponse.model_validate(p) for p in profiles]


@router.get(
    "/sources/{company_id}/profiles/{profile_id}",
    response_model=SearchProfileResponse,
)
async def get_search_profile(
    company_id: Annotated[int, Path(description="Company ID")],
    profile_id: Annotated[int, Path(description="Profile ID")],
    tenant: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> SearchProfileResponse:
    """Retrieve a specific search profile by ID.

    Args:
        company_id: The company this profile belongs to.
        profile_id: The profile record ID.
        tenant: Tenant context (any authenticated user).
        session: Database session.

    Returns:
        The search profile.

    Raises:
        HTTPException: 404 if profile not found.
    """
    profile = await session.get(SearchProfile, profile_id)
    if profile is None or profile.company_id != company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Search profile with id={profile_id} not found.",
        )

    return SearchProfileResponse.model_validate(profile)


@router.put(
    "/sources/{company_id}/profiles/{profile_id}",
    response_model=SearchProfileResponse,
)
async def update_search_profile(
    company_id: Annotated[int, Path(description="Company ID")],
    profile_id: Annotated[int, Path(description="Profile ID")],
    payload: SearchProfileUpdate,
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    tenant: TenantContext = Depends(require_config_admin),
    session: AsyncSession = Depends(get_db_session),
) -> SearchProfileResponse:
    """Update an existing search profile.

    Only non-None fields in the payload are applied. If ``is_default``
    is set to True, atomically unsets any existing default for the company.

    Args:
        company_id: The company this profile belongs to.
        profile_id: The profile record ID.
        payload: Partial update data.
        x_change_reason: Audit trail reason (enforced by middleware).
        tenant: Tenant context with role check.
        session: Database session.

    Returns:
        Updated search profile.

    Raises:
        HTTPException: 400 if X-Change-Reason missing.
        HTTPException: 403 if insufficient role.
        HTTPException: 404 if profile not found.
        HTTPException: 409 if name conflict.
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )

    profile = await session.get(SearchProfile, profile_id)
    if profile is None or profile.company_id != company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Search profile with id={profile_id} not found.",
        )

    # Handle default enforcement
    if payload.is_default is True and not profile.is_default:
        stmt = select(SearchProfile).where(
            SearchProfile.company_id == company_id,
            SearchProfile.is_default == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        existing_defaults = result.scalars().all()
        for p in existing_defaults:
            p.is_default = False

    # Apply updates
    if payload.name is not None:
        profile.name = payload.name
    if payload.is_default is not None:
        profile.is_default = payload.is_default
    if payload.enabled_sources is not None:
        profile.enabled_sources = payload.enabled_sources
    if payload.source_priorities is not None:
        profile.source_priorities = payload.source_priorities
    if payload.default_filters is not None:
        profile.default_filters = payload.default_filters

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"Search profile name '{payload.name}' already exists "
                f"for company_id={company_id}."
            ),
        )

    await session.refresh(profile)

    logger.info(
        "Updated search profile id=%d (name='%s', company_id=%d, reason='%s').",
        profile_id,
        profile.name,
        company_id,
        x_change_reason,
    )

    return SearchProfileResponse.model_validate(profile)


@router.delete(
    "/sources/{company_id}/profiles/{profile_id}",
    status_code=204,
)
async def delete_search_profile(
    company_id: Annotated[int, Path(description="Company ID")],
    profile_id: Annotated[int, Path(description="Profile ID")],
    x_change_reason: Annotated[str | None, Header(alias="X-Change-Reason")] = None,
    tenant: TenantContext = Depends(require_config_admin),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a search profile.

    Args:
        company_id: The company this profile belongs to.
        profile_id: The profile record ID.
        x_change_reason: Audit trail reason (enforced by middleware).
        tenant: Tenant context with role check.
        session: Database session.

    Raises:
        HTTPException: 400 if X-Change-Reason missing.
        HTTPException: 403 if insufficient role.
        HTTPException: 404 if profile not found.
    """
    if not x_change_reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header is required for mutating requests.",
        )

    profile = await session.get(SearchProfile, profile_id)
    if profile is None or profile.company_id != company_id:
        raise HTTPException(
            status_code=404,
            detail=f"Search profile with id={profile_id} not found.",
        )

    await session.delete(profile)

    logger.info(
        "Deleted search profile id=%d (name='%s', company_id=%d, reason='%s').",
        profile_id,
        profile.name,
        company_id,
        x_change_reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _map_celery_state(
    result: AsyncResult,
) -> tuple[TaskStatus, int, SearchResponse | None, str | None]:
    """Map a Celery AsyncResult state to literature task status fields.

    Args:
        result: Celery AsyncResult object.

    Returns:
        Tuple of (status, progress_percent, partial_results, error_message).
    """
    state = result.state

    if state == "PENDING":
        # Task is queued but not yet started
        progress = 0
        if result.info and isinstance(result.info, dict):
            progress = result.info.get("progress_percent", 0)
        return TaskStatus.QUEUED, progress, None, None

    elif state == "STARTED":
        # Task is actively running
        progress = 0
        if result.info and isinstance(result.info, dict):
            progress = result.info.get("progress_percent", 0)
        return TaskStatus.RUNNING, progress, None, None

    elif state == "SUCCESS":
        # Task completed successfully
        partial_results = None
        if result.result and isinstance(result.result, dict):
            partial_results = SearchResponse(**result.result)
        return TaskStatus.COMPLETED, 100, partial_results, None

    elif state == "FAILURE":
        # Task failed
        error_message = str(result.info) if result.info else "Unknown error"
        return TaskStatus.FAILED, 0, None, error_message

    elif state == "REVOKED":
        # Task was cancelled
        error_message = "Task cancelled"
        if result.info and isinstance(result.info, dict):
            error_message = result.info.get("error_message", "Task cancelled")
        return TaskStatus.FAILED, 0, None, error_message

    else:
        # Unknown state — treat as running
        return TaskStatus.RUNNING, 0, None, None
