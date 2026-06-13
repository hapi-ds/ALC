"""FastAPI router for system configuration endpoints (Phase 6.2).

Provides endpoints for AI hardware settings, storage quotas, backup
configuration, health monitoring, service status, and configuration
snapshot management. All endpoints require appropriate RBAC permissions
via the require_permission dependency.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 1.1–1.5, 2.1–2.7, 3.1–3.6, 4.1–4.5, 5.1–5.6, 6.1–6.6,
      7.1–7.5, 8.1–8.5, 9.1–9.6, 10.1–10.9, 11.1–11.6, 12.1–12.5, 13.1–13.5,
      14.1–14.7, 15.1–15.5
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.config import get_settings
from alcoabase.database import get_db_session
from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.models.system_config import (
    BackupRecord,
    ResourceMetricPoint,
    StorageQuota,
    SystemConfiguration,
)
from alcoabase.schemas.system_config import (
    AIHardwareConfigResponse,
    AIHardwareConfigUpdate,
    BackupRecordResponse,
    BackupScheduleUpdate,
    CompanyStorageUsageResponse,
    ConfigDiffItem,
    ConfigurationSnapshotResponse,
    HealthCheckConfigUpdate,
    ResourceMetricsResponse,
    RetentionPolicyUpdate,
    RollbackConfirmation,
    ServiceInfoResponse,
    StorageQuotaUpdate,
    StorageTotalsResponse,
    VLLMStatusResponse,
)
from alcoabase.services.backup_service import (
    BackupAlreadyRunningError,
    BackupService,
    InvalidCronExpressionError,
    InvalidRetentionPeriodError,
)
from alcoabase.services.service_registry import ServiceRegistry
from alcoabase.services.storage_quota import StorageQuotaService
from alcoabase.services.system_config import SystemConfigurationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-config", tags=["System Configuration"])

# Module-level service instances
_config_service = SystemConfigurationService()
_service_registry = ServiceRegistry()
_storage_quota_service = StorageQuotaService()
_backup_service = BackupService()

# Connection info mapping for Docker services (host:port)
_SERVICE_CONNECTION_INFO: dict[str, tuple[str, int]] = {
    "postgresql": ("alcoabase-postgres", 5432),
    "minio": ("alcoabase-minio", 9000),
    "opensearch": ("alcoabase-opensearch", 9200),
    "redis": ("alcoabase-redis", 6379),
    "vllm": ("alcoabase-vllm", 8000),
    "backend": ("alcoabase-backend", 8000),
    "celery-worker": ("alcoabase-celery-worker", 0),
    "frontend": ("alcoabase-frontend", 3000),
}


def _get_config_service() -> SystemConfigurationService:
    """Provide the SystemConfigurationService instance as a dependency."""
    return _config_service


def _get_service_registry() -> ServiceRegistry:
    """Provide the ServiceRegistry instance as a dependency."""
    return _service_registry


def _get_storage_quota_service() -> StorageQuotaService:
    """Provide the StorageQuotaService instance as a dependency."""
    return _storage_quota_service


def _get_backup_service() -> BackupService:
    """Provide the BackupService instance as a dependency."""
    return _backup_service


# ─────────────────────────────────────────────────────────────────────────────
# Storage & Quota Endpoints (Requirements 5.1–5.6, 6.1–6.6)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/storage/usage", summary="Get per-company storage usage")
async def get_storage_usage(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: StorageQuotaService = Depends(_get_storage_quota_service),
) -> dict:
    """Get storage usage per company with human-readable format.

    Returns a list of all companies with their current MinIO storage usage,
    quota status, and aggregate totals. Data is cached for 60 seconds.
    If MinIO is unreachable, returns stale cached data with a staleness indicator.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: StorageQuotaService instance.

    Returns:
        Dictionary containing per-company usage list, totals, and staleness flag.
    """
    usage_list, is_stale = await service.get_usage_per_company(session)
    totals = await service.get_total_usage(session)

    companies = [
        CompanyStorageUsageResponse(
            company_id=u.company_id,
            company_name=u.company_name,
            usage_bytes=u.usage_bytes,
            human_readable=u.human_readable,
            quota_status=u.quota_status,
            quota_limit_bytes=u.quota_limit_bytes,
            alert_threshold_pct=u.alert_threshold_pct,
        ).model_dump()
        for u in usage_list
    ]

    return {
        "companies": companies,
        "totals": StorageTotalsResponse(
            total_used_bytes=totals.total_used_bytes,
            total_capacity_bytes=totals.total_capacity_bytes,
            human_readable_used=totals.human_readable_used,
            human_readable_capacity=totals.human_readable_capacity,
        ).model_dump(),
        "is_stale": is_stale,
        "last_updated": totals.last_updated,
    }


@router.get("/storage/quotas", summary="Get all quota configurations")
async def get_storage_quotas(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Get all configured storage quotas.

    Returns a list of all quota configurations with company information,
    quota limits, and alert thresholds.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.

    Returns:
        List of quota configuration dictionaries.
    """
    stmt = (
        select(StorageQuota)
        .options(selectinload(StorageQuota.company))
        .order_by(StorageQuota.company_id)
    )
    result = await session.execute(stmt)
    quotas = result.scalars().all()

    quota_list: list[dict] = []
    for quota in quotas:
        company_name = ""
        if quota.company:
            company_name = quota.company.display_name

        quota_list.append({
            "company_id": quota.company_id,
            "company_name": company_name,
            "quota_limit_bytes": quota.quota_limit_bytes,
            "alert_threshold_pct": quota.alert_threshold_pct,
            "updated_at": quota.updated_at.isoformat() if quota.updated_at else None,
        })

    return quota_list


@router.put(
    "/storage/quotas/{company_id}",
    summary="Set quota limit and alert threshold for a company",
)
async def update_storage_quota(
    company_id: int,
    payload: StorageQuotaUpdate,
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: StorageQuotaService = Depends(_get_storage_quota_service),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
) -> dict:
    """Set storage quota limit and alert threshold for a company.

    Upserts the quota configuration for the specified company. Both
    quota_limit_bytes and alert_threshold_pct are optional; only provided
    fields are updated.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        company_id: The company's database ID.
        payload: Quota update request with optional limit and threshold.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: StorageQuotaService instance.
        x_change_reason: Audit trail reason for the change.

    Returns:
        Updated quota configuration for the company.

    Raises:
        HTTPException 400: If neither quota_limit_bytes nor alert_threshold_pct is provided.
        HTTPException 400: If X-Change-Reason is empty or exceeds 500 characters.
    """
    # Validate X-Change-Reason
    reason = x_change_reason.strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header must not be empty.",
        )
    if len(reason) > 500:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header must not exceed 500 characters.",
        )

    if payload.quota_limit_bytes is None and payload.alert_threshold_pct is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of quota_limit_bytes or alert_threshold_pct must be provided.",
        )

    quota: StorageQuota | None = None

    if payload.quota_limit_bytes is not None:
        quota = await service.set_quota(company_id, payload.quota_limit_bytes, session)

    if payload.alert_threshold_pct is not None:
        quota = await service.set_alert_threshold(
            company_id, payload.alert_threshold_pct, session
        )

    # Update the updated_by field for audit trail
    if quota is not None:
        quota.updated_by = ctx.user_id
        await session.flush()

    await session.commit()

    return {
        "company_id": company_id,
        "quota_limit_bytes": quota.quota_limit_bytes if quota else None,
        "alert_threshold_pct": quota.alert_threshold_pct if quota else None,
        "updated_at": quota.updated_at.isoformat() if quota and quota.updated_at else None,
        "change_reason": reason,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AI Hardware Endpoints (Requirements 2.1–2.7, 3.1–3.6, 4.1–4.5)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/ai-hardware", response_model=AIHardwareConfigResponse)
async def get_ai_hardware_config(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> AIHardwareConfigResponse:
    """Get current AI hardware configuration.

    Returns the merged configuration (DB overrides .env defaults) including
    model names, paths, GPU settings, inference mode, and vLLM connection
    status for both chat and embedding instances.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        AI hardware configuration with vLLM reachability status.
    """
    config = await service.get_config("ai_hardware", session)

    # Check vLLM reachability for both instances
    settings = get_settings()
    chat_url = config.get("vllm_chat_url", "") or settings.vllm_base_url
    embedding_url = config.get("vllm_embedding_url", "") or getattr(settings, "vllm_embedding_url", chat_url)
    vllm_chat_status = await _check_vllm_reachability(chat_url)
    vllm_embedding_status = await _check_vllm_reachability(embedding_url)

    return AIHardwareConfigResponse(
        model_chat_name=config.get("model_chat_name", ""),
        model_chat_path=config.get("model_chat_path", ""),
        model_chat_max_gpu_memory_gb=config.get("model_chat_max_gpu_memory_gb", 0),
        model_embedding_name=config.get("model_embedding_name", ""),
        model_embedding_path=config.get("model_embedding_path", ""),
        model_embedding_dimension=config.get("model_embedding_dimension", 0),
        model_ocr_name=config.get("model_ocr_name", ""),
        model_ocr_path=config.get("model_ocr_path", ""),
        inference_mode=config.get("inference_mode", "mock"),
        gpu_device_id=config.get("gpu_device_id", 0),
        vllm_chat_url=chat_url,
        vllm_embedding_url=embedding_url,
        vllm_chat_status=vllm_chat_status,
        vllm_embedding_status=vllm_embedding_status,
    )


@router.put("/ai-hardware", response_model=AIHardwareConfigResponse)
async def update_ai_hardware_config(
    payload: AIHardwareConfigUpdate,
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> dict:
    """Update AI hardware configuration.

    Validates that specified model paths exist on the filesystem. Creates a
    pre-change configuration snapshot for rollback support. Returns the
    updated configuration with a restart_required flag indicating whether
    a vLLM restart is needed for changes to take effect.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        payload: Partial update with only the fields to change.
        x_change_reason: Required audit reason for the configuration change.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        Updated AI hardware configuration with restart_required flag.

    Raises:
        HTTPException 422: If a model path does not exist on the filesystem.
    """
    # Filter out None values — only update provided fields
    update_data = payload.model_dump(exclude_none=True)

    if not update_data:
        raise HTTPException(
            status_code=422,
            detail="No fields provided for update.",
        )

    # Validate model paths exist on filesystem
    path_fields = ["model_chat_path", "model_embedding_path", "model_ocr_path"]
    for field_name in path_fields:
        if field_name in update_data:
            if not service.validate_model_path(update_data[field_name]):
                raise HTTPException(
                    status_code=422,
                    detail=f"Model path does not exist: {update_data[field_name]}",
                )

    try:
        result = await service.update_config(
            category="ai_hardware",
            data=update_data,
            user_id=ctx.user_id,
            reason=x_change_reason,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await session.commit()

    # Build response with updated config + vLLM status
    config = result.updated_values
    vllm_chat_status = await _check_vllm_reachability(
        config.get("vllm_chat_url", "")
    )
    vllm_embedding_status = await _check_vllm_reachability(
        config.get("vllm_embedding_url", "")
    )

    response_data = {
        "model_chat_name": config.get("model_chat_name", ""),
        "model_chat_path": config.get("model_chat_path", ""),
        "model_chat_max_gpu_memory_gb": config.get(
            "model_chat_max_gpu_memory_gb", 0
        ),
        "model_embedding_name": config.get("model_embedding_name", ""),
        "model_embedding_path": config.get("model_embedding_path", ""),
        "model_embedding_dimension": config.get("model_embedding_dimension", 0),
        "model_ocr_name": config.get("model_ocr_name", ""),
        "model_ocr_path": config.get("model_ocr_path", ""),
        "inference_mode": config.get("inference_mode", "mock"),
        "gpu_device_id": config.get("gpu_device_id", 0),
        "vllm_chat_url": config.get("vllm_chat_url", ""),
        "vllm_embedding_url": config.get("vllm_embedding_url", ""),
        "vllm_chat_status": vllm_chat_status,
        "vllm_embedding_status": vllm_embedding_status,
        "restart_required": result.restart_required,
    }

    return response_data


@router.post("/ai-hardware/restart-vllm")
async def restart_vllm(
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> dict:
    """Trigger a vLLM service restart.

    Issues a Docker container restart command for the vLLM service with a
    180-second timeout. Records the restart event in the audit trail with
    the acting user and X-Change-Reason.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        x_change_reason: Required audit reason for the restart action.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        Dictionary with success status and message.

    Raises:
        HTTPException 500: If the restart operation fails.
    """
    result = await service.restart_vllm_service(
        user_id=ctx.user_id,
        reason=x_change_reason,
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=result.error or result.message,
        )

    return {
        "success": result.success,
        "message": result.message,
    }


@router.get("/ai-hardware/vllm-status", response_model=VLLMStatusResponse)
async def get_vllm_status(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> VLLMStatusResponse:
    """Get vLLM service health and restart status.

    Checks the current vLLM service status by attempting to reach its
    health endpoint. Returns the status classification (running, restarting,
    error, unreachable) along with any error information.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        service: SystemConfigurationService instance.

    Returns:
        VLLMStatusResponse with current status and optional error details.
    """
    settings = get_settings()
    vllm_url = settings.vllm_base_url

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{vllm_url}/health")
            if response.status_code == 200:
                return VLLMStatusResponse(status="running")
            else:
                return VLLMStatusResponse(
                    status="error",
                    error=f"Health endpoint returned status {response.status_code}",
                )
    except httpx.ConnectError:
        return VLLMStatusResponse(
            status="unreachable",
            error="Cannot connect to vLLM service.",
        )
    except httpx.TimeoutException:
        return VLLMStatusResponse(
            status="unreachable",
            error="vLLM service health check timed out.",
        )
    except Exception as e:
        return VLLMStatusResponse(
            status="error",
            error=str(e),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Service Status Endpoints (Requirements 12.1–12.5)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/services", response_model=list[ServiceInfoResponse])
async def get_all_services(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    registry: ServiceRegistry = Depends(_get_service_registry),
) -> list[ServiceInfoResponse]:
    """Get all Docker services with stats, versions, and connection info.

    Returns information about each Docker Compose service including container
    name, running state, software version, uptime, resource utilization, and
    connection parameters.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        registry: ServiceRegistry instance.

    Returns:
        List of service information for all Docker Compose services.
    """
    cached_data = await registry.get_all_services()
    services_response: list[ServiceInfoResponse] = []

    for svc in cached_data.services:
        # Get resource stats for running containers
        cpu_percent = 0.0
        memory_used_mb = 0.0
        memory_limit_mb: float | None = None

        if svc.running_state == "running":
            try:
                stats = await registry.get_service_stats(svc.container_name)
                cpu_percent = stats.cpu_percent
                memory_used_mb = stats.memory_used_mb
                memory_limit_mb = stats.memory_limit_mb
            except Exception:
                logger.warning(
                    "Failed to get stats for %s", svc.container_name
                )

        # Get connection info
        host, port = _SERVICE_CONNECTION_INFO.get(
            svc.service_name, (svc.container_name, 0)
        )

        services_response.append(
            ServiceInfoResponse(
                container_name=svc.container_name,
                service_name=svc.service_name,
                running_state=svc.running_state,
                version=svc.version,
                uptime=svc.uptime,
                cpu_percent=cpu_percent,
                memory_used_mb=memory_used_mb,
                memory_limit_mb=memory_limit_mb,
                host=host,
                port=port,
            )
        )

    return services_response


@router.get(
    "/services/{service}/metrics", response_model=list[ResourceMetricsResponse]
)
async def get_service_metrics(
    service: str,
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ResourceMetricsResponse]:
    """Get resource utilization history for a service over the last 60 minutes.

    Returns time-series CPU and memory utilization data points for the
    specified service, ordered by timestamp ascending.

    Requires `system_config:read` permission.

    Args:
        service: Logical service name (e.g., "postgresql", "redis").
        ctx: Resolved tenant context with permission check.
        session: Database session.

    Returns:
        List of resource metric data points for the last 60 minutes.

    Raises:
        HTTPException 404: If the service name is not recognized.
    """
    # Validate service name
    if service not in ServiceRegistry.DOCKER_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service}. Valid services: {', '.join(sorted(ServiceRegistry.DOCKER_SERVICES.keys()))}",
        )

    # Query metrics for the last 60 minutes
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
    stmt = (
        select(ResourceMetricPoint)
        .where(
            ResourceMetricPoint.service_name == service,
            ResourceMetricPoint.recorded_at >= cutoff,
        )
        .order_by(ResourceMetricPoint.recorded_at.asc())
    )
    result = await session.execute(stmt)
    metrics = result.scalars().all()

    return [
        ResourceMetricsResponse(
            service_name=m.service_name,
            cpu_percent=m.cpu_percent,
            memory_used_mb=m.memory_used_mb,
            memory_limit_mb=m.memory_limit_mb,
            recorded_at=m.recorded_at,
        )
        for m in metrics
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Configuration Snapshot Endpoints (Requirements 14.1–14.7)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/snapshots", response_model=dict)
async def get_snapshot_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> dict:
    """Get paginated configuration snapshot history.

    Returns a paginated list of configuration snapshots showing each change
    with timestamp, user, change reason, and modified keys. Default page
    size is 20 entries per page.

    Requires `system_config:read` permission.

    Args:
        page: Page number (1-indexed).
        page_size: Number of items per page (default 20, max 100).
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        Paginated snapshot history with items, total, page, page_size, total_pages.
    """
    result = await service.get_snapshot_history(
        page=page, page_size=page_size, session=session
    )
    return {
        "items": [
            ConfigurationSnapshotResponse(
                id=item["id"],
                created_at=item["created_at"],
                created_by_name=item["created_by_name"],
                change_reason=item["change_reason"],
                is_rollback=item["is_rollback"],
                changed_keys=item["changed_keys"],
            )
            for item in result.items
        ],
        "total": result.total,
        "page": result.page,
        "page_size": result.page_size,
        "total_pages": result.total_pages,
    }


@router.get("/snapshots/{snapshot_id}/diff", response_model=list[ConfigDiffItem])
async def get_snapshot_diff(
    snapshot_id: int,
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> list[ConfigDiffItem]:
    """Get diff between a snapshot and the current configuration state.

    Returns a list of configuration keys that differ between the selected
    snapshot and the current state, with old and new values for each.

    Requires `system_config:read` permission.

    Args:
        snapshot_id: ID of the snapshot to compare against current state.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        List of configuration differences.

    Raises:
        HTTPException 404: If the snapshot is not found.
    """
    try:
        diff = await service.get_snapshot_diff(snapshot_id, session)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return diff


@router.post("/snapshots/{snapshot_id}/rollback", response_model=RollbackConfirmation)
async def rollback_to_snapshot(
    snapshot_id: int,
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> RollbackConfirmation:
    """Rollback configuration to a previous snapshot.

    Restores all configuration values to the state captured in the selected
    snapshot. The rollback is atomic — if any value fails validation, the
    entire rollback is rejected without applying partial changes.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        snapshot_id: ID of the snapshot to restore.
        ctx: Resolved tenant context with permission check.
        x_change_reason: Reason for the rollback (ALCOA+ audit trail).
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        RollbackConfirmation with details of the rollback operation.

    Raises:
        HTTPException 404: If the snapshot is not found.
        HTTPException 422: If rollback validation fails (atomic rejection).
    """
    # Validate X-Change-Reason
    reason = x_change_reason.strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header must not be empty.",
        )
    if len(reason) > 500:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header must not exceed 500 characters.",
        )

    try:
        result = await service.rollback_to_snapshot(
            snapshot_id=snapshot_id,
            user_id=ctx.user_id,
            reason=reason,
            session=session,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        # Validation failure → atomic rejection
        raise HTTPException(status_code=422, detail=error_msg)

    await session.commit()

    return RollbackConfirmation(
        snapshot_id=result.snapshot_id,
        snapshot_timestamp=datetime.fromisoformat(result.snapshot_timestamp),
        acting_user=result.acting_user,
        changed_categories=result.changed_categories,
        diff=result.diff,
        services_requiring_restart=result.services_requiring_restart,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Health Monitoring Endpoints (Requirements 10.1–10.9, 11.1–11.6, 15.1–15.5)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health/status", summary="Get current health status for all services")
async def get_health_status(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Get current health status for all monitored services.

    Returns the latest health check result per service with uptime percentage
    over the last 24 hours and average response time over the last 5 minutes.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.

    Returns:
        List of health status dictionaries for each monitored service.
    """
    from alcoabase.services.health_monitor import HealthMonitor

    # Load current health check config to use correct thresholds
    config = await _config_service.get_config("health_check", session)
    degraded_ms = config.get("degraded_threshold_seconds", 5) * 1000
    timeout_ms = config.get("unreachable_timeout_seconds", 10) * 1000

    health_monitor = HealthMonitor(
        degraded_threshold_ms=degraded_ms,
        timeout_ms=timeout_ms,
    )

    statuses = await health_monitor.get_current_status(session)

    return [
        {
            "service_name": s["service_name"],
            "status": s["status"],
            "response_time_ms": s["response_time_ms"],
            "last_checked": (
                s["last_checked"].isoformat()
                if s["last_checked"]
                else datetime.now(timezone.utc).isoformat()
            ),
            "uptime_pct_24h": s["uptime_pct_24h"],
            "avg_response_time_5min": s["avg_response_time_5min"],
        }
        for s in statuses
    ]


@router.get(
    "/health/history/{service}",
    summary="Get health check history for a service",
)
async def get_health_history(
    service: str,
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of history entries to return",
    ),
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Get health check history for a specific service.

    Returns the last N health check results for the specified service,
    ordered by most recent first.

    Requires `system_config:read` permission.

    Args:
        service: Name of the monitored service (e.g., "postgresql", "redis").
        limit: Maximum number of results to return (1-100).
        ctx: Resolved tenant context with permission check.
        session: Database session.

    Returns:
        List of health check history entries.

    Raises:
        HTTPException 404: If the service name is not recognized.
    """
    from alcoabase.services.health_monitor import HealthMonitor, MONITORED_SERVICES

    if service not in MONITORED_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown service: '{service}'. "
                f"Must be one of: {', '.join(MONITORED_SERVICES)}"
            ),
        )

    health_monitor = HealthMonitor()
    results = await health_monitor.get_service_history(service, limit, session)

    return [
        {
            "id": r.id,
            "service_name": r.service_name,
            "status": r.status,
            "response_time_ms": r.response_time_ms,
            "error_message": r.error_message,
            "checked_at": r.checked_at.isoformat() if r.checked_at else None,
            "previous_status": r.previous_status,
            "is_transition": r.is_transition,
        }
        for r in results
    ]


@router.get("/health/config", summary="Get health check configuration")
async def get_health_config(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> dict:
    """Get current health check configuration.

    Returns the configured polling interval, degraded threshold, and
    unreachable timeout values.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        Dictionary with health check configuration parameters.
    """
    config = await service.get_config("health_check", session)
    return {
        "polling_interval_seconds": config.get("polling_interval_seconds", 30),
        "degraded_threshold_seconds": config.get("degraded_threshold_seconds", 5),
        "unreachable_timeout_seconds": config.get("unreachable_timeout_seconds", 10),
    }


@router.put("/health/config", summary="Update health check configuration")
async def update_health_config(
    payload: HealthCheckConfigUpdate,
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    session: AsyncSession = Depends(get_db_session),
    service: SystemConfigurationService = Depends(_get_config_service),
) -> dict:
    """Update health check configuration parameters.

    Updates the polling interval, degraded threshold, and unreachable timeout.
    New parameters are applied on the next health check cycle without requiring
    a service restart.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        payload: Health check configuration update data.
        x_change_reason: Required audit reason for the configuration change.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: SystemConfigurationService instance.

    Returns:
        Dictionary with updated health check configuration and metadata.
    """
    # Validate X-Change-Reason
    reason = x_change_reason.strip()
    if not reason:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header must not be empty.",
        )
    if len(reason) > 500:
        raise HTTPException(
            status_code=400,
            detail="X-Change-Reason header must not exceed 500 characters.",
        )

    update_data = payload.model_dump()

    try:
        result = await service.update_config(
            category="health_check",
            data=update_data,
            user_id=ctx.user_id,
            reason=reason,
            session=session,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await session.commit()

    return {
        "polling_interval_seconds": result.updated_values.get(
            "polling_interval_seconds", 30
        ),
        "degraded_threshold_seconds": result.updated_values.get(
            "degraded_threshold_seconds", 5
        ),
        "unreachable_timeout_seconds": result.updated_values.get(
            "unreachable_timeout_seconds", 10
        ),
        "restart_required": result.restart_required,
        "snapshot_id": result.snapshot_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Backup Endpoints (Requirements 7.1–7.5, 8.1–8.5, 9.1–9.6)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/backups/schedule", summary="Get current backup schedule")
async def get_backup_schedule(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: BackupService = Depends(_get_backup_service),
) -> dict:
    """Get the current backup schedule in cron and human-readable format.

    Returns the configured backup schedule as a cron expression along with
    a human-readable description (e.g., "Daily at 02:00 UTC").

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: BackupService instance.

    Returns:
        Dictionary with cron_expression and human_readable fields.
    """
    result = await session.execute(
        select(SystemConfiguration).where(
            SystemConfiguration.category == "backup_schedule"
        )
    )
    config = result.scalars().first()

    if config and config.config_values:
        cron_expr = config.config_values.get("cron_expression", "0 2 * * *")
        human_readable = config.config_values.get(
            "human_readable",
            service.cron_to_human_readable(cron_expr),
        )
    else:
        # Default schedule
        cron_expr = "0 2 * * *"
        human_readable = "Daily at 02:00 UTC"

    return {
        "cron_expression": cron_expr,
        "human_readable": human_readable,
    }


@router.put("/backups/schedule", summary="Update backup schedule")
async def update_backup_schedule(
    payload: BackupScheduleUpdate,
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    session: AsyncSession = Depends(get_db_session),
    service: BackupService = Depends(_get_backup_service),
) -> dict:
    """Update the backup schedule with a new cron expression.

    Validates the cron expression before persisting. Registers the new
    schedule with the Celery beat scheduler for periodic execution.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        payload: Request body with cron_expression field.
        ctx: Resolved tenant context with permission check.
        x_change_reason: Audit trail reason for the change.
        session: Database session.
        service: BackupService instance.

    Returns:
        Updated schedule with cron_expression and human_readable fields.

    Raises:
        HTTPException 422: If the cron expression is invalid.
    """
    try:
        await service.update_schedule(payload.cron_expression, session)
    except InvalidCronExpressionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await session.commit()

    return {
        "cron_expression": payload.cron_expression,
        "human_readable": service.cron_to_human_readable(payload.cron_expression),
    }


@router.get("/backups/retention", summary="Get current retention policy")
async def get_backup_retention(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get the current backup retention policy.

    Returns the configured retention period in days and the number of
    completed backups currently stored.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.

    Returns:
        Dictionary with retention_days and backup_count fields.
    """
    from sqlalchemy import func as sa_func

    result = await session.execute(
        select(SystemConfiguration).where(
            SystemConfiguration.category == "backup_retention"
        )
    )
    config = result.scalars().first()

    retention_days = 30  # Default
    if config and config.config_values:
        retention_days = config.config_values.get("retention_days", 30)

    # Count current completed backups
    count_result = await session.execute(
        select(sa_func.count(BackupRecord.id)).where(
            BackupRecord.status == "completed"
        )
    )
    backup_count = count_result.scalar() or 0

    return {
        "retention_days": retention_days,
        "backup_count": backup_count,
    }


@router.put("/backups/retention", summary="Update retention policy")
async def update_backup_retention(
    payload: RetentionPolicyUpdate,
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    session: AsyncSession = Depends(get_db_session),
    service: BackupService = Depends(_get_backup_service),
) -> dict:
    """Update the backup retention policy.

    Validates retention period is within 1-365 days and updates the
    configuration. Expired backups will be cleaned up during the next
    scheduled cleanup cycle.

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        payload: Request body with retention_days field.
        ctx: Resolved tenant context with permission check.
        x_change_reason: Audit trail reason for the change.
        session: Database session.
        service: BackupService instance.

    Returns:
        Updated retention policy with retention_days field.

    Raises:
        HTTPException 422: If the retention period is invalid.
    """
    try:
        await service.update_retention(payload.retention_days, session)
    except InvalidRetentionPeriodError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await session.commit()

    return {
        "retention_days": payload.retention_days,
    }


@router.post("/backups/trigger", status_code=202, summary="Trigger manual backup")
async def trigger_backup(
    ctx: TenantContext = Depends(require_permission("system_config", "update")),
    x_change_reason: str = Header(..., alias="X-Change-Reason"),
    session: AsyncSession = Depends(get_db_session),
    service: BackupService = Depends(_get_backup_service),
) -> BackupRecordResponse:
    """Trigger a manual database backup.

    Dispatches an asynchronous Celery task to perform the PostgreSQL
    database dump. Rejects with HTTP 409 if a backup is already in
    progress (queued or running).

    Requires `system_config:update` permission and X-Change-Reason header.

    Args:
        ctx: Resolved tenant context with permission check.
        x_change_reason: Audit trail reason for the backup.
        session: Database session.
        service: BackupService instance.

    Returns:
        BackupRecordResponse with the queued backup task details.

    Raises:
        HTTPException 409: If a backup is already in progress.
    """
    try:
        record = await service.trigger_backup(
            user_id=ctx.user_id,
            reason=x_change_reason,
            session=session,
        )
    except BackupAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail=str(e))

    await session.commit()

    return BackupRecordResponse(
        id=record.id,
        task_id=record.task_id,
        backup_type=record.backup_type,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        file_size_bytes=record.file_size_bytes,
        duration_seconds=record.duration_seconds,
        error_message=record.error_message,
    )


@router.get(
    "/backups/history",
    response_model=list[BackupRecordResponse],
    summary="Get backup history",
)
async def get_backup_history(
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: BackupService = Depends(_get_backup_service),
) -> list[BackupRecordResponse]:
    """Get the backup history list.

    Returns all backup records ordered by creation time descending,
    including timestamp, size, duration, type (scheduled/manual), and status.

    Requires `system_config:read` permission.

    Args:
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: BackupService instance.

    Returns:
        List of BackupRecordResponse objects.
    """
    records = await service.get_backup_history(session)
    return [
        BackupRecordResponse(
            id=record.id,
            task_id=record.task_id,
            backup_type=record.backup_type,
            status=record.status,
            started_at=record.started_at,
            completed_at=record.completed_at,
            file_size_bytes=record.file_size_bytes,
            duration_seconds=record.duration_seconds,
            error_message=record.error_message,
        )
        for record in records
    ]


@router.get(
    "/backups/status/{task_id}",
    response_model=BackupRecordResponse,
    summary="Get backup task status",
)
async def get_backup_status(
    task_id: str,
    ctx: TenantContext = Depends(require_permission("system_config", "read")),
    session: AsyncSession = Depends(get_db_session),
    service: BackupService = Depends(_get_backup_service),
) -> BackupRecordResponse:
    """Get the status of a specific backup task.

    Returns the current status and metadata for a backup identified by
    its Celery task ID.

    Requires `system_config:read` permission.

    Args:
        task_id: The Celery task ID of the backup.
        ctx: Resolved tenant context with permission check.
        session: Database session.
        service: BackupService instance.

    Returns:
        BackupRecordResponse with the current task status.

    Raises:
        HTTPException 404: If no backup with the given task_id exists.
    """
    record = await service.get_backup_status(task_id, session)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Backup task '{task_id}' not found.",
        )

    return BackupRecordResponse(
        id=record.id,
        task_id=record.task_id,
        backup_type=record.backup_type,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        file_size_bytes=record.file_size_bytes,
        duration_seconds=record.duration_seconds,
        error_message=record.error_message,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _check_vllm_reachability(url: str) -> str:
    """Check if a vLLM instance is reachable via its health endpoint.

    Args:
        url: Base URL of the vLLM instance.

    Returns:
        "reachable" if the health endpoint responds with 200, "unreachable" otherwise.
    """
    if not url:
        return "unreachable"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return "reachable"
            return "unreachable"
    except Exception:
        return "unreachable"
