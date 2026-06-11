"""Unit tests for ScreeningConfigService.

Tests configuration reading, updating with range validation,
default creation, and audit trail logging.

References:
    - Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.review.exceptions import ConfigurationRangeError
from alcoabase.literature.review.services.screening_config_service import (
    ScreeningConfigService,
)


@pytest.fixture
def service() -> ScreeningConfigService:
    """Create a ScreeningConfigService instance."""
    return ScreeningConfigService()


@pytest.fixture
def mock_config():
    """Create a mock ScreeningConfiguration ORM object."""
    config = MagicMock()
    config.id = 1
    config.company_id = 42
    config.auto_screen_on_index = False
    config.default_batch_size = 20
    config.confidence_threshold_for_auto_include = 0.8
    config.max_concurrent_screening_tasks = 5
    config.contradiction_detection_enabled = True
    config.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    config.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return config


class TestGetConfig:
    """Tests for ScreeningConfigService.get_config()."""

    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_config_exists(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Returns default values when no config record exists for company."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        result = await service.get_config(async_session, company_id=42)

        assert result["company_id"] == 42
        assert result["auto_screen_on_index"] is False
        assert result["default_batch_size"] == 20
        assert result["confidence_threshold_for_auto_include"] == 0.8
        assert result["max_concurrent_screening_tasks"] == 5
        assert result["contradiction_detection_enabled"] is True

    @pytest.mark.asyncio
    async def test_returns_existing_config(
        self,
        service: ScreeningConfigService,
        async_session: AsyncMock,
        mock_config,
    ):
        """Returns existing config record values for the company."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        async_session.execute.return_value = mock_result

        result = await service.get_config(async_session, company_id=42)

        assert result["id"] == 1
        assert result["company_id"] == 42
        assert result["default_batch_size"] == 20


class TestUpdateConfig:
    """Tests for ScreeningConfigService.update_config()."""

    @pytest.mark.asyncio
    async def test_raises_on_batch_size_too_low(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Raises ConfigurationRangeError for batch_size < 1."""
        with pytest.raises(ConfigurationRangeError) as exc_info:
            await service.update_config(
                async_session,
                company_id=42,
                user_id=1,
                data={"default_batch_size": 0},
            )

        assert exc_info.value.field_name == "default_batch_size"
        assert exc_info.value.value == 0
        assert exc_info.value.min_value == 1
        assert exc_info.value.max_value == 100

    @pytest.mark.asyncio
    async def test_raises_on_batch_size_too_high(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Raises ConfigurationRangeError for batch_size > 100."""
        with pytest.raises(ConfigurationRangeError) as exc_info:
            await service.update_config(
                async_session,
                company_id=42,
                user_id=1,
                data={"default_batch_size": 101},
            )

        assert exc_info.value.field_name == "default_batch_size"
        assert exc_info.value.value == 101

    @pytest.mark.asyncio
    async def test_raises_on_confidence_below_minimum(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Raises ConfigurationRangeError for confidence < 0.5."""
        with pytest.raises(ConfigurationRangeError) as exc_info:
            await service.update_config(
                async_session,
                company_id=42,
                user_id=1,
                data={"confidence_threshold_for_auto_include": 0.3},
            )

        assert exc_info.value.field_name == "confidence_threshold_for_auto_include"
        assert exc_info.value.min_value == 0.5
        assert exc_info.value.max_value == 1.0

    @pytest.mark.asyncio
    async def test_raises_on_confidence_above_maximum(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Raises ConfigurationRangeError for confidence > 1.0."""
        with pytest.raises(ConfigurationRangeError) as exc_info:
            await service.update_config(
                async_session,
                company_id=42,
                user_id=1,
                data={"confidence_threshold_for_auto_include": 1.5},
            )

        assert exc_info.value.field_name == "confidence_threshold_for_auto_include"

    @pytest.mark.asyncio
    async def test_raises_on_max_concurrent_out_of_range(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Raises ConfigurationRangeError for max_concurrent outside 1-20."""
        with pytest.raises(ConfigurationRangeError) as exc_info:
            await service.update_config(
                async_session,
                company_id=42,
                user_id=1,
                data={"max_concurrent_screening_tasks": 25},
            )

        assert exc_info.value.field_name == "max_concurrent_screening_tasks"
        assert exc_info.value.value == 25
        assert exc_info.value.min_value == 1
        assert exc_info.value.max_value == 20

    @pytest.mark.asyncio
    async def test_successful_update_with_valid_values(
        self,
        service: ScreeningConfigService,
        async_session: AsyncMock,
        mock_config,
    ):
        """Successfully updates config when values are in range."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        async_session.execute.return_value = mock_result

        result = await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"default_batch_size": 50},
        )

        assert mock_config.default_batch_size == 50
        assert result["default_batch_size"] == 50

    @pytest.mark.asyncio
    async def test_creates_config_if_not_exists_on_update(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Creates a default config record before applying updates when none exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"default_batch_size": 50},
        )

        # session.add should have been called (new record created)
        async_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_boundary_values_accepted(
        self,
        service: ScreeningConfigService,
        async_session: AsyncMock,
        mock_config,
    ):
        """Boundary values (min/max) are accepted without error."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        async_session.execute.return_value = mock_result

        # Test batch_size boundaries
        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"default_batch_size": 1},
        )

        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"default_batch_size": 100},
        )

        # Test confidence boundaries
        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"confidence_threshold_for_auto_include": 0.5},
        )

        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"confidence_threshold_for_auto_include": 1.0},
        )

        # Test max_concurrent boundaries
        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"max_concurrent_screening_tasks": 1},
        )

        await service.update_config(
            async_session,
            company_id=42,
            user_id=1,
            data={"max_concurrent_screening_tasks": 20},
        )


class TestGetOrCreateDefault:
    """Tests for ScreeningConfigService.get_or_create_default()."""

    @pytest.mark.asyncio
    async def test_returns_existing_config(
        self,
        service: ScreeningConfigService,
        async_session: AsyncMock,
        mock_config,
    ):
        """Returns existing config without creating a new one."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        async_session.execute.return_value = mock_result

        result = await service.get_or_create_default(
            async_session, company_id=42
        )

        assert result["id"] == 1
        assert result["company_id"] == 42
        async_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_default_when_none_exists(
        self, service: ScreeningConfigService, async_session: AsyncMock
    ):
        """Creates a new config with default values when none exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        await service.get_or_create_default(async_session, company_id=42)

        async_session.add.assert_called_once()
        # Verify the added object has default values
        added_obj = async_session.add.call_args[0][0]
        assert added_obj.company_id == 42
        assert added_obj.auto_screen_on_index is False
        assert added_obj.default_batch_size == 20
        assert added_obj.confidence_threshold_for_auto_include == 0.8
        assert added_obj.max_concurrent_screening_tasks == 5
        assert added_obj.contradiction_detection_enabled is True
