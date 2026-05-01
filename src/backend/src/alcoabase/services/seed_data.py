"""Seed data for default virtual folders and system configuration.

Creates the default virtual folders that are available upon initial
system setup. These folders are marked as system defaults and cannot
be deleted by users.

References:
    - Design doc Section 3: Default Virtual Folders
    - Requirements 2.8: System default virtual folders
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.virtual_folder import VirtualFolder


# Default virtual folder definitions
DEFAULT_VIRTUAL_FOLDERS = [
    {
        "name": "All SOPs",
        "tag_filter": {"tags": ["SOP"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "All Reports",
        "tag_filter": {"tags": ["Report"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "All Templates",
        "tag_filter": {"tags": ["Template"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Approved Documents",
        "tag_filter": {"status": "Approved"},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Documents In Training",
        "tag_filter": {"status": "InTraining"},
        "sort_order": "created_at_desc",
    },
]


async def seed_default_virtual_folders(
    session: AsyncSession, system_user_id: int = 1
) -> list[VirtualFolder]:
    """Create default virtual folders if they don't already exist.

    This function is idempotent — it skips folders that already exist
    by name. All created folders are marked as system defaults.

    Args:
        session: Active async database session.
        system_user_id: User ID to assign as creator (defaults to system user).

    Returns:
        List of created VirtualFolder instances (empty if all already exist).
    """
    created: list[VirtualFolder] = []

    for folder_def in DEFAULT_VIRTUAL_FOLDERS:
        # Check if folder already exists
        result = await session.execute(
            select(VirtualFolder).where(VirtualFolder.name == folder_def["name"])
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            folder = VirtualFolder(
                name=folder_def["name"],
                tag_filter=folder_def["tag_filter"],
                sort_order=folder_def["sort_order"],
                is_system_default=True,
                created_by=system_user_id,
            )
            session.add(folder)
            created.append(folder)

    if created:
        await session.flush()

    return created
