"""Unit tests for system configuration health monitoring API endpoints.

Tests the health monitoring endpoint handler functions directly:
- get_health_status
- get_health_history
- get_health_config
- update_health_config

Requirements: 10.1–10.9, 11.1–11.6, 15.1–15.5
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.api.system_config import (
    get_health_config,
    get_health_history,
    get_health_status,
    update_health_config,
)
from alcoabase.dependencies.tenant import TenantContext
from alcoabase.models.system_config import HealthCheckResult
from alcoabase.schemas.system_config import HealthCheckConfigUpdate
from alcoabase.services.system_config import SystemConfigurationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test tenant context with system_config permissions."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="admin",
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_config_service() -> AsyncMock:
    """Create a mock SystemConfigurationService."""
    return AsyncMock(spec=SystemConfigurationService)


# ---------------------------------------------------------------------------
# Tests: GET /health/status
# ---------------------------------------------------------------------------


class TestGetHealthStatus:
    """Tests for the get_health_status endpoint."""

    @pytest.mark.asyncio
    async def test_returns_status_for_all_services(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Returns health status for all monitored services."""
        now = datetime.now(timezone.utc)

        mock_config_service.get_config.return_value = {
            "polling_interval_seconds": 30,
            "degraded_threshold_seconds": 5,
            "unreachable_timeout_seconds": 10,
        }

        mock_statuses = [
            {
                "service_name": "postgresql",
                "status": "healthy",
                "response_time_ms": 12.5,
                "last_checked": now,
                "uptime_pct_24h": 99.8,
                "avg_response_time_5min": 15.2,
            },
            {
                "service_name": "redis",
                "status": "healthy",
                "response_time_ms": 2.1,
                "last_checked": now,
                "uptime_pct_24h": 100.0,
                "avg_response_time_5min": 1.8,
            },
            {
                "service_name": "minio",
                "status": "degraded",
                "response_time_ms": 6500.0,
                "last_checked": now,
                "uptime_pct_24h": 95.5,
                "avg_response_time_5min": 5800.0,
            },
        ]

        with patch(
            "alcoabase.api.system_config._config_service",
            mock_config_service,
        ), patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_current_status.return_value = mock_statuses
            MockHealthMonitor.return_value = mock_hm_instance

            result = await get_health_status(
                ctx=tenant_context,
                session=mock_session,
            )

        assert len(result) == 3
        assert result[0]["service_name"] == "postgresql"
        assert result[0]["status"] == "healthy"
        assert result[0]["response_time_ms"] == 12.5
        assert result[0]["uptime_pct_24h"] == 99.8
        assert result[0]["avg_response_time_5min"] == 15.2

        assert result[1]["service_name"] == "redis"
        assert result[1]["status"] == "healthy"

        assert result[2]["service_name"] == "minio"
        assert result[2]["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_handles_none_last_checked(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Uses current time when last_checked is None (no checks yet)."""
        mock_config_service.get_config.return_value = {
            "polling_interval_seconds": 30,
            "degraded_threshold_seconds": 5,
            "unreachable_timeout_seconds": 10,
        }

        mock_statuses = [
            {
                "service_name": "vllm",
                "status": "unreachable",
                "response_time_ms": None,
                "last_checked": None,
                "uptime_pct_24h": 0.0,
                "avg_response_time_5min": None,
            },
        ]

        with patch(
            "alcoabase.api.system_config._config_service",
            mock_config_service,
        ), patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_current_status.return_value = mock_statuses
            MockHealthMonitor.return_value = mock_hm_instance

            result = await get_health_status(
                ctx=tenant_context,
                session=mock_session,
            )

        assert len(result) == 1
        assert result[0]["service_name"] == "vllm"
        assert result[0]["status"] == "unreachable"
        # Fallback to current time when last_checked is None
        assert result[0]["last_checked"] is not None

    @pytest.mark.asyncio
    async def test_uses_config_thresholds(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Creates HealthMonitor with thresholds from config."""
        mock_config_service.get_config.return_value = {
            "polling_interval_seconds": 60,
            "degraded_threshold_seconds": 8,
            "unreachable_timeout_seconds": 15,
        }

        with patch(
            "alcoabase.api.system_config._config_service",
            mock_config_service,
        ), patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_current_status.return_value = []
            MockHealthMonitor.return_value = mock_hm_instance

            await get_health_status(
                ctx=tenant_context,
                session=mock_session,
            )

        # Verify HealthMonitor was created with correct thresholds (seconds * 1000)
        MockHealthMonitor.assert_called_once_with(
            degraded_threshold_ms=8000,
            timeout_ms=15000,
        )


# ---------------------------------------------------------------------------
# Tests: GET /health/history/{service}
# ---------------------------------------------------------------------------


class TestGetHealthHistory:
    """Tests for the get_health_history endpoint."""

    @pytest.mark.asyncio
    async def test_returns_history_for_valid_service(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
    ) -> None:
        """Returns health check history for a valid service name."""
        now = datetime.now(timezone.utc)
        mock_result = MagicMock(spec=HealthCheckResult)
        mock_result.id = 1
        mock_result.service_name = "postgresql"
        mock_result.status = "healthy"
        mock_result.response_time_ms = 12.5
        mock_result.error_message = None
        mock_result.checked_at = now
        mock_result.previous_status = "healthy"
        mock_result.is_transition = False

        with patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_service_history.return_value = [mock_result]
            MockHealthMonitor.return_value = mock_hm_instance

            result = await get_health_history(
                service="postgresql",
                limit=100,
                ctx=tenant_context,
                session=mock_session,
            )

        assert len(result) == 1
        assert result[0]["service_name"] == "postgresql"
        assert result[0]["status"] == "healthy"
        assert result[0]["response_time_ms"] == 12.5
        assert result[0]["is_transition"] is False

    @pytest.mark.asyncio
    async def test_rejects_unknown_service_with_404(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
    ) -> None:
        """Returns 404 for an unrecognized service name."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_health_history(
                service="unknown_service",
                limit=100,
                ctx=tenant_context,
                session=mock_session,
            )

        assert exc_info.value.status_code == 404
        assert "Unknown service" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_service_with_no_history(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
    ) -> None:
        """Returns empty list when service has no health check history."""
        with patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_service_history.return_value = []
            MockHealthMonitor.return_value = mock_hm_instance

            result = await get_health_history(
                service="redis",
                limit=50,
                ctx=tenant_context,
                session=mock_session,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
    ) -> None:
        """Passes the limit parameter to the health monitor service."""
        with patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_service_history.return_value = []
            MockHealthMonitor.return_value = mock_hm_instance

            await get_health_history(
                service="opensearch",
                limit=25,
                ctx=tenant_context,
                session=mock_session,
            )

            mock_hm_instance.get_service_history.assert_called_once_with(
                "opensearch", 25, mock_session
            )

    @pytest.mark.asyncio
    async def test_all_monitored_services_accepted(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
    ) -> None:
        """All services in MONITORED_SERVICES are accepted."""
        from alcoabase.services.health_monitor import MONITORED_SERVICES

        with patch(
            "alcoabase.services.health_monitor.HealthMonitor"
        ) as MockHealthMonitor:
            mock_hm_instance = AsyncMock()
            mock_hm_instance.get_service_history.return_value = []
            MockHealthMonitor.return_value = mock_hm_instance

            for service_name in MONITORED_SERVICES:
                result = await get_health_history(
                    service=service_name,
                    limit=10,
                    ctx=tenant_context,
                    session=mock_session,
                )
                assert result == []


# ---------------------------------------------------------------------------
# Tests: GET /health/config
# ---------------------------------------------------------------------------


class TestGetHealthConfig:
    """Tests for the get_health_config endpoint."""

    @pytest.mark.asyncio
    async def test_returns_current_config(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Returns the current health check configuration."""
        mock_config_service.get_config.return_value = {
            "polling_interval_seconds": 60,
            "degraded_threshold_seconds": 8,
            "unreachable_timeout_seconds": 15,
        }

        result = await get_health_config(
            ctx=tenant_context,
            session=mock_session,
            service=mock_config_service,
        )

        assert result["polling_interval_seconds"] == 60
        assert result["degraded_threshold_seconds"] == 8
        assert result["unreachable_timeout_seconds"] == 15

        mock_config_service.get_config.assert_called_once_with(
            "health_check", mock_session
        )

    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_config(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Returns default values when config keys are missing."""
        mock_config_service.get_config.return_value = {}

        result = await get_health_config(
            ctx=tenant_context,
            session=mock_session,
            service=mock_config_service,
        )

        assert result["polling_interval_seconds"] == 30
        assert result["degraded_threshold_seconds"] == 5
        assert result["unreachable_timeout_seconds"] == 10


# ---------------------------------------------------------------------------
# Tests: PUT /health/config
# ---------------------------------------------------------------------------


class TestUpdateHealthConfig:
    """Tests for the update_health_config endpoint."""

    @pytest.mark.asyncio
    async def test_updates_config_successfully(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Successfully updates health check configuration."""
        mock_config_service.update_config.return_value = MagicMock(
            updated_values={
                "polling_interval_seconds": 60,
                "degraded_threshold_seconds": 10,
                "unreachable_timeout_seconds": 20,
            },
            restart_required=False,
            snapshot_id=5,
        )

        payload = HealthCheckConfigUpdate(
            polling_interval_seconds=60,
            degraded_threshold_seconds=10,
            unreachable_timeout_seconds=20,
        )

        result = await update_health_config(
            payload=payload,
            x_change_reason="Tuning health check thresholds",
            ctx=tenant_context,
            session=mock_session,
            service=mock_config_service,
        )

        assert result["polling_interval_seconds"] == 60
        assert result["degraded_threshold_seconds"] == 10
        assert result["unreachable_timeout_seconds"] == 20
        assert result["restart_required"] is False
        assert result["snapshot_id"] == 5

        mock_config_service.update_config.assert_called_once_with(
            category="health_check",
            data={
                "polling_interval_seconds": 60,
                "degraded_threshold_seconds": 10,
                "unreachable_timeout_seconds": 20,
            },
            user_id=42,
            reason="Tuning health check thresholds",
            session=mock_session,
        )

    @pytest.mark.asyncio
    async def test_passes_user_id_from_context(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Uses user_id from tenant context for audit trail."""
        mock_config_service.update_config.return_value = MagicMock(
            updated_values={
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            },
            restart_required=False,
            snapshot_id=1,
        )

        payload = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )

        await update_health_config(
            payload=payload,
            x_change_reason="Testing user context",
            ctx=tenant_context,
            session=mock_session,
            service=mock_config_service,
        )

        call_kwargs = mock_config_service.update_config.call_args.kwargs
        assert call_kwargs["user_id"] == 42

    @pytest.mark.asyncio
    async def test_config_applied_without_restart(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Health config changes do not require service restart."""
        mock_config_service.update_config.return_value = MagicMock(
            updated_values={
                "polling_interval_seconds": 120,
                "degraded_threshold_seconds": 15,
                "unreachable_timeout_seconds": 30,
            },
            restart_required=False,
            snapshot_id=10,
        )

        payload = HealthCheckConfigUpdate(
            polling_interval_seconds=120,
            degraded_threshold_seconds=15,
            unreachable_timeout_seconds=30,
        )

        result = await update_health_config(
            payload=payload,
            x_change_reason="Adjusting thresholds for production",
            ctx=tenant_context,
            session=mock_session,
            service=mock_config_service,
        )

        # Health check config changes apply on next cycle without restart
        assert result["restart_required"] is False

    @pytest.mark.asyncio
    async def test_rejects_empty_change_reason(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Rejects update when X-Change-Reason is empty."""
        from fastapi import HTTPException

        payload = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_health_config(
                payload=payload,
                x_change_reason="   ",
                ctx=tenant_context,
                session=mock_session,
                service=mock_config_service,
            )

        assert exc_info.value.status_code == 400
        assert "must not be empty" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_rejects_too_long_change_reason(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Rejects update when X-Change-Reason exceeds 500 characters."""
        from fastapi import HTTPException

        payload = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_health_config(
                payload=payload,
                x_change_reason="x" * 501,
                ctx=tenant_context,
                session=mock_session,
                service=mock_config_service,
            )

        assert exc_info.value.status_code == 400
        assert "500 characters" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handles_validation_error(
        self,
        tenant_context: TenantContext,
        mock_session: AsyncMock,
        mock_config_service: AsyncMock,
    ) -> None:
        """Returns 422 when config service raises ValueError."""
        from fastapi import HTTPException

        mock_config_service.update_config.side_effect = ValueError(
            "Health check config validation failed"
        )

        payload = HealthCheckConfigUpdate(
            polling_interval_seconds=30,
            degraded_threshold_seconds=5,
            unreachable_timeout_seconds=10,
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_health_config(
                payload=payload,
                x_change_reason="Valid reason",
                ctx=tenant_context,
                session=mock_session,
                service=mock_config_service,
            )

        assert exc_info.value.status_code == 422
