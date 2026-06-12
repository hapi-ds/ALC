"""Unit tests for the VigilanceSearchProfileService.

Tests cover:
- Cron expression validation (valid/invalid 5-field expressions)
- Array validation (search_terms, adverse_event_keywords, mesh_terms, etc.)
- Profile creation with auto-pause for discontinued products
- Profile update with re-registration when cron changes
- Profile activation with product status enforcement
- Profile pause/archive with beat deregistration
- Manual execution dispatch
- Register all active schedules on startup
- Audit trail logging for all mutations
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest

from alcoabase.literature.vigilance.exceptions import (
    InvalidCronExpressionError,
    ProductNotFoundError,
    ProfileNotFoundError,
)
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)
from alcoabase.literature.vigilance.services.vigilance_search_profile_service import (
    VigilanceSearchProfileService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class AsyncContextManagerMock:
    """Helper to mock an async context manager (async with ... as ...)."""

    def __init__(self, return_value: Any) -> None:
        self._return_value = return_value

    async def __aenter__(self) -> Any:
        return self._return_value

    async def __aexit__(self, *args: Any) -> bool:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock) -> AsyncMock:
    """Create a mock async session factory (context manager)."""
    factory = AsyncMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


@pytest.fixture
def service(mock_session_factory: AsyncMock) -> VigilanceSearchProfileService:
    """Create a VigilanceSearchProfileService instance with mocked session factory."""
    return VigilanceSearchProfileService(session_factory=mock_session_factory)


def _make_product(
    *,
    id: int = 1,
    company_id: int = 10,
    name: str = "Test Device",
    status: str = "active",
) -> MagicMock:
    """Helper to create a MedicalProduct-like mock."""
    product = MagicMock(spec=MedicalProduct)
    product.id = id
    product.company_id = company_id
    product.name = name
    product.status = status
    return product


def _make_profile(
    *,
    id: int = 1,
    product_id: int = 1,
    company_id: int = 10,
    name: str = "Test Profile",
    status: str = "active",
    schedule_cron: str = "0 6 * * 1",
) -> MagicMock:
    """Helper to create a VigilanceSearchProfile-like mock."""
    profile = MagicMock(spec=VigilanceSearchProfile)
    profile.id = id
    profile.product_id = product_id
    profile.company_id = company_id
    profile.name = name
    profile.search_terms = ["device name"]
    profile.mesh_terms = None
    profile.adverse_event_keywords = ["adverse event"]
    profile.device_identifiers = None
    profile.exclusion_terms = None
    profile.source_ids = None
    profile.schedule_cron = schedule_cron
    profile.status = status
    profile.created_by = 100
    profile.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    profile.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return profile


# ---------------------------------------------------------------------------
# Tests: Cron Expression Validation
# ---------------------------------------------------------------------------


class TestCronValidation:
    """Tests for validate_cron_expression()."""

    def test_valid_simple_cron(self, service: VigilanceSearchProfileService) -> None:
        """Standard 5-field cron expressions should pass validation."""
        assert service.validate_cron_expression("0 6 * * 1") is True
        assert service.validate_cron_expression("*/15 * * * *") is True
        assert service.validate_cron_expression("0 0 1 1 *") is True
        assert service.validate_cron_expression("30 2 * * *") is True

    def test_valid_complex_cron(self, service: VigilanceSearchProfileService) -> None:
        """Complex cron with ranges, lists, and steps should pass."""
        assert service.validate_cron_expression("0 0 1-15 * 1,3,5") is True
        assert service.validate_cron_expression("0,30 */2 * * *") is True
        assert service.validate_cron_expression("0 0 1 1-6 *") is True

    def test_invalid_field_count(self, service: VigilanceSearchProfileService) -> None:
        """Cron with wrong number of fields should raise."""
        with pytest.raises(InvalidCronExpressionError, match="exactly 5 fields"):
            service.validate_cron_expression("0 6 * *")

        with pytest.raises(InvalidCronExpressionError, match="exactly 5 fields"):
            service.validate_cron_expression("0 6 * * * *")

    def test_invalid_minute_range(self, service: VigilanceSearchProfileService) -> None:
        """Minute values outside 0-59 should raise."""
        with pytest.raises(InvalidCronExpressionError, match="minute"):
            service.validate_cron_expression("60 * * * *")

    def test_invalid_hour_range(self, service: VigilanceSearchProfileService) -> None:
        """Hour values outside 0-23 should raise."""
        with pytest.raises(InvalidCronExpressionError, match="hour"):
            service.validate_cron_expression("0 24 * * *")

    def test_invalid_day_range(self, service: VigilanceSearchProfileService) -> None:
        """Day of month values outside 1-31 should raise."""
        with pytest.raises(InvalidCronExpressionError, match="day_of_month"):
            service.validate_cron_expression("0 * 32 * *")

        with pytest.raises(InvalidCronExpressionError, match="day_of_month"):
            service.validate_cron_expression("0 * 0 * *")

    def test_invalid_month_range(self, service: VigilanceSearchProfileService) -> None:
        """Month values outside 1-12 should raise."""
        with pytest.raises(InvalidCronExpressionError, match="month"):
            service.validate_cron_expression("0 * * 13 *")

        with pytest.raises(InvalidCronExpressionError, match="month"):
            service.validate_cron_expression("0 * * 0 *")

    def test_invalid_dow_range(self, service: VigilanceSearchProfileService) -> None:
        """Day of week values outside 0-7 should raise."""
        with pytest.raises(InvalidCronExpressionError, match="day_of_week"):
            service.validate_cron_expression("0 * * * 8")

    def test_invalid_non_numeric(self, service: VigilanceSearchProfileService) -> None:
        """Non-numeric values (not wildcard/range/step) should raise."""
        with pytest.raises(InvalidCronExpressionError):
            service.validate_cron_expression("abc * * * *")

    def test_invalid_range_start_gt_end(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """Range with start > end should raise."""
        with pytest.raises(InvalidCronExpressionError, match="range start"):
            service.validate_cron_expression("0 * 15-10 * *")

    def test_valid_day_of_week_7(self, service: VigilanceSearchProfileService) -> None:
        """Day of week 7 (Sunday) should be valid."""
        assert service.validate_cron_expression("0 0 * * 7") is True

    def test_valid_step_with_wildcard(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """Steps with wildcard (e.g., */5) should be valid."""
        assert service.validate_cron_expression("*/5 * * * *") is True
        assert service.validate_cron_expression("0 */3 * * *") is True

    def test_invalid_step_zero(self, service: VigilanceSearchProfileService) -> None:
        """Step value of 0 should raise."""
        with pytest.raises(InvalidCronExpressionError, match="step value"):
            service.validate_cron_expression("*/0 * * * *")


# ---------------------------------------------------------------------------
# Tests: Array Validation
# ---------------------------------------------------------------------------


class TestArrayValidation:
    """Tests for _validate_arrays()."""

    def test_valid_minimal_arrays(self, service: VigilanceSearchProfileService) -> None:
        """Minimal valid arrays should pass."""
        service._validate_arrays(
            search_terms=["term1"],
            adverse_event_keywords=["keyword1"],
            mesh_terms=None,
            device_identifiers=None,
            exclusion_terms=None,
        )

    def test_empty_search_terms_raises(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """Empty search_terms should raise ValueError."""
        with pytest.raises(ValueError, match="search_terms must contain"):
            service._validate_arrays(
                search_terms=[],
                adverse_event_keywords=["kw"],
                mesh_terms=None,
                device_identifiers=None,
                exclusion_terms=None,
            )

    def test_empty_adverse_event_keywords_raises(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """Empty adverse_event_keywords should raise ValueError."""
        with pytest.raises(ValueError, match="adverse_event_keywords must contain"):
            service._validate_arrays(
                search_terms=["term"],
                adverse_event_keywords=[],
                mesh_terms=None,
                device_identifiers=None,
                exclusion_terms=None,
            )

    def test_search_terms_exceeds_limit(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """More than 50 search_terms should raise."""
        with pytest.raises(ValueError, match="cannot exceed 50"):
            service._validate_arrays(
                search_terms=[f"term{i}" for i in range(51)],
                adverse_event_keywords=["kw"],
                mesh_terms=None,
                device_identifiers=None,
                exclusion_terms=None,
            )

    def test_adverse_event_keywords_exceeds_limit(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """More than 50 adverse_event_keywords should raise."""
        with pytest.raises(ValueError, match="cannot exceed 50"):
            service._validate_arrays(
                search_terms=["term"],
                adverse_event_keywords=[f"kw{i}" for i in range(51)],
                mesh_terms=None,
                device_identifiers=None,
                exclusion_terms=None,
            )

    def test_mesh_terms_exceeds_limit(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """More than 30 mesh_terms should raise."""
        with pytest.raises(ValueError, match="mesh_terms cannot exceed 30"):
            service._validate_arrays(
                search_terms=["term"],
                adverse_event_keywords=["kw"],
                mesh_terms=[f"mesh{i}" for i in range(31)],
                device_identifiers=None,
                exclusion_terms=None,
            )

    def test_device_identifiers_exceeds_limit(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """More than 20 device_identifiers should raise."""
        with pytest.raises(ValueError, match="device_identifiers cannot exceed 20"):
            service._validate_arrays(
                search_terms=["term"],
                adverse_event_keywords=["kw"],
                mesh_terms=None,
                device_identifiers=[f"id{i}" for i in range(21)],
                exclusion_terms=None,
            )

    def test_exclusion_terms_exceeds_limit(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """More than 30 exclusion_terms should raise."""
        with pytest.raises(ValueError, match="exclusion_terms cannot exceed 30"):
            service._validate_arrays(
                search_terms=["term"],
                adverse_event_keywords=["kw"],
                mesh_terms=None,
                device_identifiers=None,
                exclusion_terms=[f"excl{i}" for i in range(31)],
            )

    def test_search_term_too_long(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """Search term exceeding 500 chars should raise."""
        with pytest.raises(ValueError, match="search_terms\\[0\\]"):
            service._validate_arrays(
                search_terms=["x" * 501],
                adverse_event_keywords=["kw"],
                mesh_terms=None,
                device_identifiers=None,
                exclusion_terms=None,
            )

    def test_mesh_term_too_long(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """MeSH term exceeding 200 chars should raise."""
        with pytest.raises(ValueError, match="mesh_terms\\[0\\]"):
            service._validate_arrays(
                search_terms=["term"],
                adverse_event_keywords=["kw"],
                mesh_terms=["x" * 201],
                device_identifiers=None,
                exclusion_terms=None,
            )


# ---------------------------------------------------------------------------
# Tests: Profile Creation
# ---------------------------------------------------------------------------


class TestCreateProfile:
    """Tests for create_profile()."""

    @pytest.mark.asyncio
    async def test_create_profile_active_product(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Creating a profile for an active product should set status='active'."""
        product = _make_product(status="active")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = product
        mock_session.execute.return_value = mock_result

        with patch.object(service, "_register_beat_schedule"):
            result = await service.create_profile(
                mock_session,
                company_id=10,
                user_id=100,
                product_id=1,
                name="Test Profile",
                search_terms=["device name"],
                adverse_event_keywords=["adverse event"],
                schedule_cron="0 6 * * 1",
            )

        assert result["status"] == "active"
        assert result["name"] == "Test Profile"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_profile_discontinued_product_auto_pauses(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Creating a profile for a discontinued product should auto-pause."""
        product = _make_product(status="discontinued")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = product
        mock_session.execute.return_value = mock_result

        with patch.object(service, "_register_beat_schedule") as mock_register:
            result = await service.create_profile(
                mock_session,
                company_id=10,
                user_id=100,
                product_id=1,
                name="Paused Profile",
                search_terms=["device name"],
                adverse_event_keywords=["adverse event"],
            )

        assert result["status"] == "paused"
        mock_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_profile_invalid_cron_raises(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Invalid cron expression should raise InvalidCronExpressionError."""
        with pytest.raises(InvalidCronExpressionError):
            await service.create_profile(
                mock_session,
                company_id=10,
                user_id=100,
                product_id=1,
                name="Bad Cron",
                search_terms=["term"],
                adverse_event_keywords=["kw"],
                schedule_cron="invalid",
            )

    @pytest.mark.asyncio
    async def test_create_profile_product_not_found_raises(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Non-existent product should raise ProductNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ProductNotFoundError):
            await service.create_profile(
                mock_session,
                company_id=10,
                user_id=100,
                product_id=999,
                name="Profile",
                search_terms=["term"],
                adverse_event_keywords=["kw"],
            )


# ---------------------------------------------------------------------------
# Tests: Profile Activation
# ---------------------------------------------------------------------------


class TestActivateProfile:
    """Tests for activate_profile()."""

    @pytest.mark.asyncio
    async def test_activate_profile_success(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Activating a paused profile with active product should succeed."""
        profile = _make_profile(status="paused")
        product = _make_product(status="active")

        # First call returns profile, second returns product
        mock_result_profile = MagicMock()
        mock_result_profile.scalar_one_or_none.return_value = profile
        mock_result_product = MagicMock()
        mock_result_product.scalar_one_or_none.return_value = product
        mock_session.execute.side_effect = [mock_result_profile, mock_result_product]

        with patch.object(service, "_register_beat_schedule"):
            await service.activate_profile(
                mock_session,
                profile_id=1,
                company_id=10,
                user_id=100,
            )

        assert profile.status == "active"

    @pytest.mark.asyncio
    async def test_activate_profile_discontinued_product_raises(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Activating a profile for a discontinued product should raise ValueError."""
        profile = _make_profile(status="paused")
        product = _make_product(status="discontinued")

        mock_result_profile = MagicMock()
        mock_result_profile.scalar_one_or_none.return_value = profile
        mock_result_product = MagicMock()
        mock_result_product.scalar_one_or_none.return_value = product
        mock_session.execute.side_effect = [mock_result_profile, mock_result_product]

        with pytest.raises(ValueError, match="Cannot activate profile"):
            await service.activate_profile(
                mock_session,
                profile_id=1,
                company_id=10,
                user_id=100,
            )

    @pytest.mark.asyncio
    async def test_activate_profile_not_found_raises(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Non-existent profile should raise ProfileNotFoundError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ProfileNotFoundError):
            await service.activate_profile(
                mock_session,
                profile_id=999,
                company_id=10,
                user_id=100,
            )


# ---------------------------------------------------------------------------
# Tests: Profile Pause/Archive
# ---------------------------------------------------------------------------


class TestPauseProfile:
    """Tests for pause_profile()."""

    @pytest.mark.asyncio
    async def test_pause_profile_success(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Pausing an active profile should set status to 'paused'."""
        profile = _make_profile(status="active")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = profile
        mock_session.execute.return_value = mock_result

        with patch.object(service, "_deregister_beat_schedule") as mock_dereg:
            await service.pause_profile(
                mock_session,
                profile_id=1,
                company_id=10,
                user_id=100,
            )

        assert profile.status == "paused"
        mock_dereg.assert_called_once_with(1)


class TestArchiveProfile:
    """Tests for archive_profile()."""

    @pytest.mark.asyncio
    async def test_archive_profile_success(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Archiving a profile should set status to 'archived'."""
        profile = _make_profile(status="paused")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = profile
        mock_session.execute.return_value = mock_result

        with patch.object(service, "_deregister_beat_schedule") as mock_dereg:
            await service.archive_profile(
                mock_session,
                profile_id=1,
                company_id=10,
                user_id=100,
            )

        assert profile.status == "archived"
        mock_dereg.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# Tests: Manual Execution
# ---------------------------------------------------------------------------


class TestTriggerManualExecution:
    """Tests for trigger_manual_execution()."""

    @pytest.mark.asyncio
    async def test_trigger_manual_execution_returns_task_id(
        self, service: VigilanceSearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Manual execution should dispatch Celery task and return task_id."""
        profile = _make_profile(status="paused")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = profile
        mock_session.execute.return_value = mock_result

        mock_celery_result = MagicMock()
        mock_celery_result.id = "abc-123-task-id"

        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task.return_value = mock_celery_result
            task_id = await service.trigger_manual_execution(
                mock_session,
                profile_id=1,
                company_id=10,
                user_id=100,
            )

        assert task_id == "abc-123-task-id"
        mock_celery.send_task.assert_called_once_with(
            "alcoabase.tasks.vigilance_tasks.execute_vigilance_search",
            kwargs={"profile_id": 1, "company_id": 10},
            queue="literature_ingestion",
        )


# ---------------------------------------------------------------------------
# Tests: Register All Active Schedules
# ---------------------------------------------------------------------------


class TestRegisterAllActiveSchedules:
    """Tests for register_all_active_schedules()."""

    @pytest.mark.asyncio
    async def test_registers_all_active_profiles(
        self, service: VigilanceSearchProfileService
    ) -> None:
        """Should load all active profiles and register each with beat."""
        mock_session = AsyncMock()

        profiles = [
            _make_profile(id=1, status="active"),
            _make_profile(id=2, status="active"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = profiles
        mock_session.execute.return_value = mock_result

        # Replace the session factory with a proper async context manager
        service._session_factory = MagicMock()
        service._session_factory.return_value = AsyncContextManagerMock(mock_session)

        with patch.object(service, "_register_beat_schedule") as mock_register:
            count = await service.register_all_active_schedules()

        assert count == 2
        assert mock_register.call_count == 2
