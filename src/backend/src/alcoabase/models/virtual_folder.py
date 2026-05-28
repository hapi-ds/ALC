"""Virtual folder model for tag-based document aggregation.

This module defines the VirtualFolder model that provides named,
persistent tag-based filters for dynamic document views. Virtual
folders do not physically contain documents — they execute dynamic
queries against the document table.

References:
    - Virtual folders are persistent, named tag-based filters
    - System default folders cannot be deleted
    - tag_filter supports: tag matching, status filtering, multi-tag, combined
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class VirtualFolder(Base):
    """Named, persistent tag-based filter for document aggregation.

    Virtual folders provide quick-access views (e.g., "All SOPs",
    "Active Reports") without physically moving files. Opening a
    virtual folder executes a dynamic query filtered by the tag_filter
    expression.

    Attributes:
        id: Primary key.
        name: Unique folder name displayed in navigation.
        tag_filter: JSON expression defining the filter criteria
            (e.g., {"tags": ["SOP"], "status": "Active"}).
        sort_order: Default sort order for documents in this folder.
        is_system_default: Whether this is a built-in folder (cannot be deleted).
        created_by: Foreign key to the creating user.
        created_at: Server-side UTC timestamp of creation.
    """

    __tablename__ = "virtual_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    tag_filter: Mapped[dict] = mapped_column(JSON)
    sort_order: Mapped[str] = mapped_column(
        String(50), default="created_at_desc"
    )
    is_system_default: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    is_demo_data: Mapped[bool] = mapped_column(default=False)
