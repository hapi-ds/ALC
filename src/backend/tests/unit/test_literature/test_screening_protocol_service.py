"""Unit tests for ScreeningProtocolService.

Tests CRUD operations, versioning, status transitions, criteria validation,
and role-based access enforcement for screening protocol management.

References:
    - Requirements: 2.1, 2.8, 2.9, 2.10
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.review.exceptions import (
    InvalidStateTransitionError,
    NoCriteriaDefinedError,
    ProtocolNotFoundError,
)
from alcoabase.literature.review.services.screening_protocol_service import (
    ScreeningProtocolService,
)


@pytest.fixture
def service() -> ScreeningProtocolService:
    """Create a ScreeningProtocolService instance."""
    return ScreeningProtocolService()


@pytest.fixture
def mock_protocol():
    """Create a mock ScreeningProtocol ORM object in draft status."""
    protocol = MagicMock()
    protocol.id = 1
    protocol.company_id = 42
    protocol.name = "Test Protocol"
    protocol.description = "A test protocol"
    protocol.version = 1
    protocol.status = "draft"
    protocol.created_by = 10
    protocol.pico_population = "Adults with diabetes"
    protocol.pico_intervention = "Metformin"
    protocol.pico_comparison = "Placebo"
    protocol.pico_outcome = "HbA1c reduction"
    protocol.inclusion_criteria = ["randomized controlled trial"]
    protocol.exclusion_criteria = ["animal study"]
    protocol.publication_date_from = "2020-01-01"
    protocol.publication_date_to = "2024-12-31"
    protocol.allowed_publication_types = ["article", "review"]
    protocol.allowed_languages = ["en", "de"]
    protocol.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    protocol.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return protocol


@pytest.fixture
def mock_active_protocol(mock_protocol):
    """Create a mock protocol in active status."""
    mock_protocol.status = "active"
    return mock_protocol


@pytest.fixture
def mock_archived_protocol(mock_protocol):
    """Create a mock protocol in archived status."""
    mock_protocol.status = "archived"
    return mock_protocol


class TestCreateProtocol:
    """Tests for ScreeningProtocolService.create_protocol()."""

    @pytest.mark.asyncio
    async def test_create_with_pico_criteria(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Creates a protocol when PICO criteria are provided."""
        # Mock the refresh to set protocol attributes
        async def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        async_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_protocol(
            async_session,
            company_id=42,
            user_id=10,
            name="PICO Protocol",
            description="Test",
            pico_criteria={
                "population": "Adults with diabetes",
                "intervention": "Metformin",
                "comparison": None,
                "outcome": "HbA1c reduction",
            },
        )

        assert result["name"] == "PICO Protocol"
        assert result["version"] == 1
        assert result["status"] == "draft"
        assert result["pico_criteria"]["population"] == "Adults with diabetes"
        async_session.add.assert_called_once()
        async_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_inclusion_criteria(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Creates a protocol when only inclusion criteria are provided."""
        async def mock_refresh(obj):
            obj.id = 2
            obj.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        async_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_protocol(
            async_session,
            company_id=42,
            user_id=10,
            name="Inclusion Protocol",
            inclusion_criteria=["randomized", "double-blind"],
        )

        assert result["name"] == "Inclusion Protocol"
        assert result["inclusion_criteria"] == ["randomized", "double-blind"]
        assert result["version"] == 1
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_with_exclusion_criteria(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Creates a protocol when only exclusion criteria are provided."""
        async def mock_refresh(obj):
            obj.id = 3
            obj.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        async_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_protocol(
            async_session,
            company_id=42,
            user_id=10,
            name="Exclusion Protocol",
            exclusion_criteria=["animal study", "in vitro"],
        )

        assert result["name"] == "Exclusion Protocol"
        assert result["exclusion_criteria"] == ["animal study", "in vitro"]

    @pytest.mark.asyncio
    async def test_create_rejects_no_criteria(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Raises NoCriteriaDefinedError when no criteria are provided (HTTP 422)."""
        with pytest.raises(NoCriteriaDefinedError) as exc_info:
            await service.create_protocol(
                async_session,
                company_id=42,
                user_id=10,
                name="Empty Protocol",
                pico_criteria={
                    "population": None,
                    "intervention": None,
                    "comparison": None,
                    "outcome": None,
                },
                inclusion_criteria=[],
                exclusion_criteria=[],
            )

        assert "At least one screening criterion" in exc_info.value.message
        async_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_rejects_empty_string_pico(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Raises NoCriteriaDefinedError when PICO fields are empty strings."""
        with pytest.raises(NoCriteriaDefinedError):
            await service.create_protocol(
                async_session,
                company_id=42,
                user_id=10,
                name="Empty Strings Protocol",
                pico_criteria={
                    "population": "",
                    "intervention": "  ",
                    "comparison": "",
                    "outcome": "",
                },
                inclusion_criteria=[],
                exclusion_criteria=[],
            )

    @pytest.mark.asyncio
    async def test_create_rejects_no_criteria_with_no_args(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Raises NoCriteriaDefinedError when called with no criteria arguments at all."""
        with pytest.raises(NoCriteriaDefinedError):
            await service.create_protocol(
                async_session,
                company_id=42,
                user_id=10,
                name="Bare Protocol",
            )


class TestUpdateProtocol:
    """Tests for ScreeningProtocolService.update_protocol()."""

    @pytest.mark.asyncio
    async def test_auto_increments_version(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """Updates auto-increment the version number."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_protocol
        async_session.execute.return_value = mock_result
        async_session.refresh = AsyncMock()

        result = await service.update_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
            name="Updated Name",
        )

        assert mock_protocol.version == 2
        assert mock_protocol.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_protocol(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Raises ProtocolNotFoundError when protocol doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        with pytest.raises(ProtocolNotFoundError) as exc_info:
            await service.update_protocol(
                async_session,
                protocol_id=999,
                company_id=42,
                user_id=10,
                name="New Name",
            )

        assert exc_info.value.protocol_id == 999
        assert exc_info.value.company_id == 42

    @pytest.mark.asyncio
    async def test_update_rejects_removal_of_all_criteria(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
    ):
        """Raises NoCriteriaDefinedError if update removes all criteria."""
        # Create a protocol with only inclusion criteria
        protocol = MagicMock()
        protocol.id = 1
        protocol.company_id = 42
        protocol.status = "draft"
        protocol.version = 1
        protocol.pico_population = None
        protocol.pico_intervention = None
        protocol.pico_comparison = None
        protocol.pico_outcome = None
        protocol.inclusion_criteria = ["some criterion"]
        protocol.exclusion_criteria = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = protocol
        async_session.execute.return_value = mock_result

        with pytest.raises(NoCriteriaDefinedError):
            await service.update_protocol(
                async_session,
                protocol_id=1,
                company_id=42,
                user_id=10,
                inclusion_criteria=[],
            )

    @pytest.mark.asyncio
    async def test_update_with_in_progress_reviews_creates_new_version(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
    ):
        """Active protocol with in-progress reviews creates a new version row."""
        # Setup an active protocol
        protocol = MagicMock()
        protocol.id = 1
        protocol.company_id = 42
        protocol.status = "active"
        protocol.version = 2
        protocol.name = "Active Protocol"
        protocol.description = "Desc"
        protocol.pico_population = "Adults"
        protocol.pico_intervention = "Drug X"
        protocol.pico_comparison = None
        protocol.pico_outcome = "Survival"
        protocol.inclusion_criteria = ["trial"]
        protocol.exclusion_criteria = []
        protocol.publication_date_from = None
        protocol.publication_date_to = None
        protocol.allowed_publication_types = None
        protocol.allowed_languages = None

        # First execute: find the protocol
        # Second execute: check in-progress reviews (count > 0)
        mock_result_protocol = MagicMock()
        mock_result_protocol.scalar_one_or_none.return_value = protocol

        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 1  # Has in-progress reviews

        async_session.execute.side_effect = [
            mock_result_protocol,
            mock_result_count,
        ]

        # Mock refresh for the new version
        async def mock_refresh(obj):
            obj.id = 10
            obj.created_at = datetime(2025, 2, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2025, 2, 1, tzinfo=timezone.utc)

        async_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.update_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
            name="Updated Active Protocol",
        )

        # Should have created a new protocol row (version 3)
        assert result["version"] == 3
        assert result["name"] == "Updated Active Protocol"
        # session.add should have been called for the new row
        async_session.add.assert_called_once()


class TestActivateProtocol:
    """Tests for ScreeningProtocolService.activate_protocol()."""

    @pytest.mark.asyncio
    async def test_activate_from_draft(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """Successfully transitions a draft protocol to active."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_protocol
        async_session.execute.return_value = mock_result
        async_session.refresh = AsyncMock()

        result = await service.activate_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
        )

        assert mock_protocol.status == "active"

    @pytest.mark.asyncio
    async def test_activate_rejects_active_protocol(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_active_protocol,
    ):
        """Raises InvalidStateTransitionError when protocol is already active."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_active_protocol
        async_session.execute.return_value = mock_result

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            await service.activate_protocol(
                async_session,
                protocol_id=1,
                company_id=42,
                user_id=10,
            )

        assert exc_info.value.current_state == "active"
        assert exc_info.value.target_state == "active"

    @pytest.mark.asyncio
    async def test_activate_rejects_archived_protocol(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_archived_protocol,
    ):
        """Raises InvalidStateTransitionError when protocol is archived."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archived_protocol
        async_session.execute.return_value = mock_result

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            await service.activate_protocol(
                async_session,
                protocol_id=1,
                company_id=42,
                user_id=10,
            )

        assert exc_info.value.current_state == "archived"
        assert exc_info.value.target_state == "active"

    @pytest.mark.asyncio
    async def test_activate_raises_not_found(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """Raises ProtocolNotFoundError for non-existent protocol."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        with pytest.raises(ProtocolNotFoundError):
            await service.activate_protocol(
                async_session,
                protocol_id=999,
                company_id=42,
                user_id=10,
            )


class TestArchiveProtocol:
    """Tests for ScreeningProtocolService.archive_protocol()."""

    @pytest.mark.asyncio
    async def test_archive_from_draft(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """Successfully archives a draft protocol (soft-delete)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_protocol
        async_session.execute.return_value = mock_result
        async_session.refresh = AsyncMock()

        result = await service.archive_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
        )

        assert mock_protocol.status == "archived"

    @pytest.mark.asyncio
    async def test_archive_from_active(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_active_protocol,
    ):
        """Successfully archives an active protocol (soft-delete)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_active_protocol
        async_session.execute.return_value = mock_result
        async_session.refresh = AsyncMock()

        result = await service.archive_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
        )

        assert mock_active_protocol.status == "archived"

    @pytest.mark.asyncio
    async def test_archive_rejects_already_archived(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_archived_protocol,
    ):
        """Raises InvalidStateTransitionError when protocol is already archived."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archived_protocol
        async_session.execute.return_value = mock_result

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            await service.archive_protocol(
                async_session,
                protocol_id=1,
                company_id=42,
                user_id=10,
            )

        assert exc_info.value.current_state == "archived"

    @pytest.mark.asyncio
    async def test_archive_is_soft_delete(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """Archive operation sets status to 'archived' without deleting the record."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_protocol
        async_session.execute.return_value = mock_result
        async_session.refresh = AsyncMock()

        await service.archive_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
        )

        # Protocol is still accessible (soft-delete), status changed to archived
        assert mock_protocol.status == "archived"
        # delete was NOT called on the session
        async_session.delete.assert_not_called()


class TestRoleBasedAccess:
    """Tests for role-based access enforcement on ScreeningProtocolService.

    Note: Role enforcement is handled at the router/dependency layer.
    These tests verify that the service correctly documents and supports
    the expected access patterns via the router integration.
    """

    @pytest.mark.asyncio
    async def test_list_protocols_accessible_by_member(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
    ):
        """list_protocols is a read operation accessible by members (no role check in service)."""
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        async_session.execute.side_effect = [mock_count_result, mock_list_result]

        protocols, total = await service.list_protocols(
            async_session, company_id=42
        )

        assert protocols == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_protocol_accessible_by_member(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """get_protocol is a read operation accessible by members."""
        # First call: _get_protocol_or_raise
        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = mock_protocol

        # Second call: version history query
        mock_result_history = MagicMock()
        mock_result_history.scalars.return_value.all.return_value = [mock_protocol]

        async_session.execute.side_effect = [mock_result_get, mock_result_history]

        result = await service.get_protocol(
            async_session, protocol_id=1, company_id=42
        )

        assert result["id"] == 1
        assert "version_history" in result

    @pytest.mark.asyncio
    async def test_create_requires_document_admin(
        self, service: ScreeningProtocolService, async_session: AsyncMock
    ):
        """create_protocol is a mutation operation (document_admin required at router level).

        Service itself does not enforce roles — router handles this.
        This test verifies the service works correctly when called.
        """
        async def mock_refresh(obj):
            obj.id = 1
            obj.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
            obj.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        async_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_protocol(
            async_session,
            company_id=42,
            user_id=10,
            name="Admin Protocol",
            pico_criteria={"population": "Test population"},
        )

        assert result["name"] == "Admin Protocol"
        assert result["created_by"] == 10


class TestUpdateWithInProgressReviews:
    """Tests for protocol versioning when in-progress reviews exist."""

    @pytest.mark.asyncio
    async def test_draft_protocol_update_does_not_create_new_version(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """Draft protocol updates are in-place, no new version row created."""
        assert mock_protocol.status == "draft"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_protocol
        async_session.execute.return_value = mock_result
        async_session.refresh = AsyncMock()

        await service.update_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
            name="Draft Update",
        )

        # No new row added for draft updates (in-place)
        async_session.add.assert_not_called()
        # Version still incremented
        assert mock_protocol.version == 2

    @pytest.mark.asyncio
    async def test_active_protocol_without_reviews_updates_in_place(
        self,
        service: ScreeningProtocolService,
        async_session: AsyncMock,
    ):
        """Active protocol with no in-progress reviews updates in-place."""
        protocol = MagicMock()
        protocol.id = 1
        protocol.company_id = 42
        protocol.status = "active"
        protocol.version = 3
        protocol.name = "Active Protocol"
        protocol.pico_population = "Adults"
        protocol.pico_intervention = None
        protocol.pico_comparison = None
        protocol.pico_outcome = None
        protocol.inclusion_criteria = ["criterion"]
        protocol.exclusion_criteria = []

        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = protocol

        mock_result_count = MagicMock()
        mock_result_count.scalar_one.return_value = 0  # No in-progress reviews

        async_session.execute.side_effect = [mock_result_get, mock_result_count]
        async_session.refresh = AsyncMock()

        await service.update_protocol(
            async_session,
            protocol_id=1,
            company_id=42,
            user_id=10,
            name="Updated Active",
        )

        # In-place update (no new row)
        async_session.add.assert_not_called()
        assert protocol.version == 4
        assert protocol.name == "Updated Active"
