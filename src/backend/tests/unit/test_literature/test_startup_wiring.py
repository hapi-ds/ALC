"""Unit tests for literature gateway startup wiring in main.py.

Tests the _initialize_literature_gateway and _shutdown_literature_gateway
functions to verify correct initialization behaviour.

References:
    - Requirements 1.2, 1.7, 1.8, 4.5, 11.1, 16.1, 16.5, 16.6
"""

from __future__ import annotations

import asyncio
import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.exceptions import EncryptionKeyMissingError


@pytest.fixture
def mock_app() -> MagicMock:
    """Create a mock FastAPI app with a state attribute."""
    app = MagicMock()
    app.state = MagicMock(spec=[])
    return app


@pytest.fixture
def valid_encryption_key() -> str:
    """Generate a valid base64-encoded 32-byte key."""
    return base64.b64encode(os.urandom(32)).decode()


def _make_settings(
    *,
    literature_enabled: bool = False,
    literature_encryption_key: str | None = None,
    literature_adapter_dir: str | None = None,
    redis_url: str = "redis://localhost:6379/0",
    literature_health_check_interval_seconds: int = 300,
) -> MagicMock:
    """Create a mock Settings object with literature fields."""
    settings = MagicMock()
    settings.literature_enabled = literature_enabled
    settings.literature_encryption_key = literature_encryption_key
    settings.literature_adapter_dir = literature_adapter_dir
    settings.redis_url = redis_url
    settings.literature_health_check_interval_seconds = literature_health_check_interval_seconds
    return settings


class TestLiteratureGatewayDisabled:
    """Tests when ALC_LITERATURE_ENABLED=false."""

    @pytest.mark.asyncio
    async def test_skips_initialization_when_disabled(
        self, mock_app: MagicMock
    ) -> None:
        """When literature_enabled=False, no services are initialized."""
        from alcoabase.main import _initialize_literature_gateway

        settings = _make_settings(literature_enabled=False)

        with patch("alcoabase.config.get_settings", return_value=settings):
            await _initialize_literature_gateway(mock_app)

        # app.state should not have had any literature attrs set
        assert not hasattr(mock_app.state, "literature_gateway_service")


class TestLiteratureGatewayEnabled:
    """Tests when ALC_LITERATURE_ENABLED=true."""

    @pytest.mark.asyncio
    async def test_refuses_start_without_encryption_key(
        self, mock_app: MagicMock
    ) -> None:
        """Raises EncryptionKeyMissingError when key is missing."""
        from alcoabase.main import _initialize_literature_gateway

        settings = _make_settings(
            literature_enabled=True,
            literature_encryption_key=None,
        )

        with patch("alcoabase.config.get_settings", return_value=settings):
            with pytest.raises(EncryptionKeyMissingError):
                await _initialize_literature_gateway(mock_app)

    @pytest.mark.asyncio
    async def test_refuses_start_with_empty_encryption_key(
        self, mock_app: MagicMock
    ) -> None:
        """Raises EncryptionKeyMissingError when key is empty string."""
        from alcoabase.main import _initialize_literature_gateway

        settings = _make_settings(
            literature_enabled=True,
            literature_encryption_key="",
        )

        with patch("alcoabase.config.get_settings", return_value=settings):
            with pytest.raises(EncryptionKeyMissingError):
                await _initialize_literature_gateway(mock_app)

    @pytest.mark.asyncio
    async def test_raises_on_invalid_base64_key(
        self, mock_app: MagicMock
    ) -> None:
        """Raises RuntimeError when key is not valid base64."""
        from alcoabase.main import _initialize_literature_gateway

        settings = _make_settings(
            literature_enabled=True,
            literature_encryption_key="not-valid-base64!!!",
        )

        with patch("alcoabase.config.get_settings", return_value=settings):
            with pytest.raises((RuntimeError, ValueError)):
                await _initialize_literature_gateway(mock_app)

    @pytest.mark.asyncio
    async def test_initializes_all_services(
        self, mock_app: MagicMock, valid_encryption_key: str
    ) -> None:
        """All services are initialized and stored on app.state."""
        from alcoabase.main import _initialize_literature_gateway

        mock_session_factory = AsyncMock()

        settings = _make_settings(
            literature_enabled=True,
            literature_encryption_key=valid_encryption_key,
            literature_adapter_dir=None,
        )

        with (
            patch("alcoabase.config.get_settings", return_value=settings),
            patch(
                "alcoabase.literature.services.source_registry.SourceRegistry.discover_adapters",
                new_callable=AsyncMock,
            ) as mock_discover,
            patch("alcoabase.database._session_factory", mock_session_factory),
        ):
            await _initialize_literature_gateway(mock_app)

        # Verify discover_adapters was called
        mock_discover.assert_called_once()

        # Verify all services were stored on app.state
        assert hasattr(mock_app.state, "literature_gateway_service")
        assert hasattr(mock_app.state, "literature_source_registry")
        assert hasattr(mock_app.state, "literature_rate_limiter")
        assert hasattr(mock_app.state, "literature_circuit_breaker")
        assert hasattr(mock_app.state, "literature_api_key_vault")
        assert hasattr(mock_app.state, "literature_audit_logger")
        assert hasattr(mock_app.state, "literature_proxy_manager")
        assert hasattr(mock_app.state, "literature_proxy_config")

    @pytest.mark.asyncio
    async def test_uses_configured_adapter_dir(
        self, mock_app: MagicMock, valid_encryption_key: str
    ) -> None:
        """Uses literature_adapter_dir setting when provided."""
        from alcoabase.main import _initialize_literature_gateway

        mock_session_factory = AsyncMock()

        settings = _make_settings(
            literature_enabled=True,
            literature_encryption_key=valid_encryption_key,
            literature_adapter_dir="/custom/adapters",
        )

        with (
            patch("alcoabase.config.get_settings", return_value=settings),
            patch(
                "alcoabase.literature.services.source_registry.SourceRegistry.discover_adapters",
                new_callable=AsyncMock,
            ) as mock_discover,
            patch("alcoabase.database._session_factory", mock_session_factory),
        ):
            await _initialize_literature_gateway(mock_app)

            mock_discover.assert_called_once_with("/custom/adapters")

    @pytest.mark.asyncio
    async def test_raises_when_session_factory_unavailable(
        self, mock_app: MagicMock, valid_encryption_key: str
    ) -> None:
        """Raises RuntimeError when database session factory is None."""
        from alcoabase.main import _initialize_literature_gateway

        settings = _make_settings(
            literature_enabled=True,
            literature_encryption_key=valid_encryption_key,
            literature_adapter_dir="/some/dir",
        )

        with (
            patch("alcoabase.config.get_settings", return_value=settings),
            patch(
                "alcoabase.literature.services.source_registry.SourceRegistry.discover_adapters",
                new_callable=AsyncMock,
            ),
            patch("alcoabase.database._session_factory", None),
        ):
            with pytest.raises(RuntimeError, match="session factory"):
                await _initialize_literature_gateway(mock_app)


class TestLiteratureGatewayShutdown:
    """Tests for _shutdown_literature_gateway."""

    @pytest.mark.asyncio
    async def test_cancels_health_check_task(self, mock_app: MagicMock) -> None:
        """Cancels the periodic health check task on shutdown."""
        from alcoabase import main
        from alcoabase.main import _shutdown_literature_gateway

        # Create a real asyncio task that sleeps forever
        async def _forever() -> None:
            await asyncio.sleep(3600)

        task = asyncio.create_task(_forever())
        original = main._literature_health_check_task
        main._literature_health_check_task = task

        try:
            await _shutdown_literature_gateway(mock_app)
            assert task.cancelled()
            assert main._literature_health_check_task is None
        finally:
            main._literature_health_check_task = original

    @pytest.mark.asyncio
    async def test_noop_when_no_task(self, mock_app: MagicMock) -> None:
        """Does nothing when no health check task is running."""
        from alcoabase import main
        from alcoabase.main import _shutdown_literature_gateway

        original = main._literature_health_check_task
        main._literature_health_check_task = None

        try:
            # Should not raise
            await _shutdown_literature_gateway(mock_app)
        finally:
            main._literature_health_check_task = original
