"""Setup wizard state model for first-run initialization tracking.

This module defines the SetupStatus model that persists the setup wizard's
progress across application restarts. The table follows a single-row pattern:
at most one row exists, and its state determines whether the system is
initialized.

References:
    - Setup wizard design: .kiro/specs/setup-wizard/design.md
    - Requirements: .kiro/specs/setup-wizard/requirements.md (Req 1.4, 7.1, 7.2)
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class SetupStatus(Base):
    """Persistent setup wizard state.

    This table has at most ONE row. Its existence and state determine
    whether the system is initialized. When `is_complete` is True, the
    setup guard middleware allows normal application traffic and blocks
    further access to setup endpoints.

    Attributes:
        id: Primary key.
        is_complete: Whether the full setup wizard has been completed.
        admin_created: Whether the root admin account has been created.
        company_created: Whether the initial company has been created.
        ai_mode_configured: Whether the AI hardware mode has been configured.
        demo_data_seeded: Whether demo data has been seeded.
        root_admin_id: Foreign key to the root admin user record.
        company_id: Foreign key to the initial company record.
        ai_hardware_mode: The selected AI hardware mode ("gpu", "cpu", or "mock").
        started_at: Server-side UTC timestamp of when setup began.
        completed_at: Timestamp of when setup was finalized (null if incomplete).
    """

    __tablename__ = "setup_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    is_complete: Mapped[bool] = mapped_column(default=False)

    # Step completion tracking
    admin_created: Mapped[bool] = mapped_column(default=False)
    company_created: Mapped[bool] = mapped_column(default=False)
    ai_mode_configured: Mapped[bool] = mapped_column(default=False)
    demo_data_seeded: Mapped[bool] = mapped_column(default=False)

    # References
    root_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    ai_hardware_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
