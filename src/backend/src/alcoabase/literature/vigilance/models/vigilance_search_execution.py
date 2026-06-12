"""Vigilance Search Execution model (append-only after completion).

Records a single execution of a VigilanceSearchProfile including search
parameters, sources queried, result counts, and execution status. Once
completed, records are not modified (append-only for audit compliance).

References:
    - Requirements 4.4, 4.5, 4.6, 4.7
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base

if TYPE_CHECKING:
    from alcoabase.literature.vigilance.models.vigilance_search_profile import (
        VigilanceSearchProfile,
    )
    from alcoabase.models.company import Company


class VigilanceSearchExecution(Base):
    """Records a single vigilance search execution.

    Append-only after completion: once the execution reaches a terminal
    status (completed, partial_failure, failed), the record is not
    modified. Does NOT use AuditMixin/Continuum — immutability is
    enforced at the application layer.

    Attributes:
        id: Primary key.
        profile_id: FK to vigilance_search_profiles.
        company_id: FK to companies table (tenant isolation).
        execution_timestamp: UTC timestamp when the execution started.
        search_parameters: Full query as structured JSON.
        sources_queried: Array of source adapter names queried.
        total_results_found: Total raw results from all sources.
        results_after_exclusion: Results remaining after exclusion filtering.
        results_ingested: Results successfully ingested.
        results_duplicate: Results matching existing records (skipped).
        execution_duration_ms: Total execution time in milliseconds.
        status: Execution status (running, completed, partial_failure, failed).
    """

    __tablename__ = "vigilance_search_executions"
    __table_args__ = (
        Index(
            "ix_vigilance_search_executions_company_status",
            "company_id",
            "status",
        ),
        Index(
            "ix_vigilance_search_executions_profile",
            "profile_id",
        ),
        Index(
            "ix_vigilance_search_executions_timestamp",
            "company_id",
            "execution_timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("vigilance_search_profiles.id"), index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    execution_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    search_parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    sources_queried: Mapped[list] = mapped_column(ARRAY(String(100)))
    total_results_found: Mapped[int] = mapped_column(Integer, default=0)
    results_after_exclusion: Mapped[int] = mapped_column(Integer, default=0)
    results_ingested: Mapped[int] = mapped_column(Integer, default=0)
    results_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    execution_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")

    profile: Mapped["VigilanceSearchProfile"] = relationship()
    company: Mapped["Company"] = relationship()
