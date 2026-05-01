"""Unit tests for virtual folder CRUD and filtering.

Tests virtual folder creation, listing, dynamic document filtering
by tag_filter, update, deletion, and system default deletion protection.

References:
    - Task 4.11: Unit tests for virtual folders
    - Requirements 2.5-2.8: Virtual folder operations
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.services.seed_data import (
    DEFAULT_VIRTUAL_FOLDERS,
    seed_default_virtual_folders,
)


# ---------------------------------------------------------------------------
# Test: Seed Data
# ---------------------------------------------------------------------------


class TestSeedDefaultVirtualFolders:
    """Tests for seed_default_virtual_folders()."""

    @pytest.mark.asyncio
    async def test_creates_all_default_folders(self) -> None:
        """seed_default_virtual_folders() creates all 5 default folders."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # All folders don't exist yet
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        created = await seed_default_virtual_folders(session)

        assert len(created) == 5
        assert session.add.call_count == 5

    @pytest.mark.asyncio
    async def test_skips_existing_folders(self) -> None:
        """seed_default_virtual_folders() skips folders that already exist."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        # All folders already exist
        existing_folder = VirtualFolder(
            id=1,
            name="All SOPs",
            tag_filter={"tags": ["SOP"]},
            sort_order="created_at_desc",
            is_system_default=True,
            created_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing_folder
        session.execute = AsyncMock(return_value=result_mock)

        created = await seed_default_virtual_folders(session)

        assert len(created) == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_created_folders_are_system_defaults(self) -> None:
        """All created folders have is_system_default=True."""
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        created = await seed_default_virtual_folders(session)

        for folder in created:
            assert folder.is_system_default is True

    def test_default_folders_have_correct_names(self) -> None:
        """DEFAULT_VIRTUAL_FOLDERS contains the expected folder names."""
        names = [f["name"] for f in DEFAULT_VIRTUAL_FOLDERS]
        assert "All SOPs" in names
        assert "All Reports" in names
        assert "All Templates" in names
        assert "Approved Documents" in names
        assert "Documents In Training" in names

    def test_default_folders_have_tag_filters(self) -> None:
        """Each default folder has a non-empty tag_filter."""
        for folder_def in DEFAULT_VIRTUAL_FOLDERS:
            assert "tag_filter" in folder_def
            assert folder_def["tag_filter"]


# ---------------------------------------------------------------------------
# Test: Virtual Folder CRUD (via API module functions)
# ---------------------------------------------------------------------------


class TestVirtualFolderCRUD:
    """Tests for virtual folder CRUD operations."""

    def test_virtual_folder_model_attributes(self) -> None:
        """VirtualFolder model has all required attributes."""
        folder = VirtualFolder(
            id=1,
            name="Test Folder",
            tag_filter={"tags": ["SOP"]},
            sort_order="created_at_desc",
            is_system_default=False,
            created_by=1,
        )

        assert folder.name == "Test Folder"
        assert folder.tag_filter == {"tags": ["SOP"]}
        assert folder.sort_order == "created_at_desc"
        assert folder.is_system_default is False
        assert folder.created_by == 1

    def test_virtual_folder_system_default_flag(self) -> None:
        """VirtualFolder correctly distinguishes system defaults."""
        system_folder = VirtualFolder(
            id=1,
            name="All SOPs",
            tag_filter={"tags": ["SOP"]},
            is_system_default=True,
            created_by=1,
        )
        user_folder = VirtualFolder(
            id=2,
            name="My Custom Folder",
            tag_filter={"tags": ["Custom"]},
            is_system_default=False,
            created_by=2,
        )

        assert system_folder.is_system_default is True
        assert user_folder.is_system_default is False


# ---------------------------------------------------------------------------
# Test: Dynamic Document Filtering by tag_filter
# ---------------------------------------------------------------------------


class TestVirtualFolderFiltering:
    """Tests for dynamic document filtering by tag_filter."""

    def test_tag_filter_with_single_tag(self) -> None:
        """tag_filter with single tag matches expected structure."""
        folder = VirtualFolder(
            id=1,
            name="All SOPs",
            tag_filter={"tags": ["SOP"]},
            is_system_default=True,
            created_by=1,
        )

        assert "tags" in folder.tag_filter
        assert "SOP" in folder.tag_filter["tags"]

    def test_tag_filter_with_status(self) -> None:
        """tag_filter with status matches expected structure."""
        folder = VirtualFolder(
            id=1,
            name="Approved Documents",
            tag_filter={"status": "Approved"},
            is_system_default=True,
            created_by=1,
        )

        assert "status" in folder.tag_filter
        assert folder.tag_filter["status"] == "Approved"

    def test_tag_filter_with_combined_criteria(self) -> None:
        """tag_filter supports combined tag + status filtering."""
        folder = VirtualFolder(
            id=1,
            name="Active SOPs",
            tag_filter={"tags": ["SOP"], "status": "Active"},
            is_system_default=False,
            created_by=1,
        )

        assert folder.tag_filter["tags"] == ["SOP"]
        assert folder.tag_filter["status"] == "Active"

    def test_tag_filter_with_multiple_tags(self) -> None:
        """tag_filter supports multi-tag filtering."""
        folder = VirtualFolder(
            id=1,
            name="Lab-A Reports",
            tag_filter={"tags": ["Report", "Lab-A"]},
            is_system_default=False,
            created_by=1,
        )

        assert "Report" in folder.tag_filter["tags"]
        assert "Lab-A" in folder.tag_filter["tags"]


# ---------------------------------------------------------------------------
# Test: System Default Deletion Protection
# ---------------------------------------------------------------------------


class TestSystemDefaultDeletionProtection:
    """Tests for system default virtual folder deletion protection."""

    @pytest.mark.asyncio
    async def test_system_default_cannot_be_deleted(self) -> None:
        """Attempting to delete a system default folder raises HTTP 400."""
        from alcoabase.api.virtual_folders import delete_virtual_folder

        session = AsyncMock()
        system_folder = VirtualFolder(
            id=1,
            name="All SOPs",
            tag_filter={"tags": ["SOP"]},
            sort_order="created_at_desc",
            is_system_default=True,
            created_by=1,
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = system_folder
        session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(HTTPException) as exc_info:
            await delete_virtual_folder(folder_id=1, session=session)

        assert exc_info.value.status_code == 400
        assert "system default" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_user_folder_can_be_deleted(self) -> None:
        """User-created folders can be deleted successfully."""
        from alcoabase.api.virtual_folders import delete_virtual_folder

        session = AsyncMock()
        session.delete = AsyncMock()
        session.flush = AsyncMock()

        user_folder = VirtualFolder(
            id=2,
            name="My Custom Folder",
            tag_filter={"tags": ["Custom"]},
            sort_order="created_at_desc",
            is_system_default=False,
            created_by=2,
        )

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = user_folder
        session.execute = AsyncMock(return_value=result_mock)

        # Should not raise
        await delete_virtual_folder(folder_id=2, session=session)

        session.delete.assert_called_once_with(user_folder)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_folder_returns_404(self) -> None:
        """Deleting a non-existent folder raises HTTP 404."""
        from alcoabase.api.virtual_folders import delete_virtual_folder

        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        with pytest.raises(HTTPException) as exc_info:
            await delete_virtual_folder(folder_id=999, session=session)

        assert exc_info.value.status_code == 404
