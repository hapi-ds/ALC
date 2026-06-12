"""Pydantic v2 schemas for Periodic Safety Report endpoints.

Provides response schemas for periodic safety reports, status updates,
and report generation requests.

References:
    - Requirements: 8.5, 11.1, 11.3
    - Design doc: PeriodicReportService interface
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReportStatusEnum = Literal["generated", "reviewed", "approved", "submitted"]


class PeriodicSafetyReportResponseSchema(BaseModel):
    """Response schema for a periodic safety report.

    Attributes:
        id: Report record ID.
        product_id: Associated medical product ID.
        company_id: Company this report belongs to.
        period_start: Start date of the reporting period.
        period_end: End date of the reporting period.
        generated_at: When the report was generated.
        report_content: Full structured report content as JSON.
        status: Current report lifecycle status.
        version: Report version number (incremented on edits).
        status_history: List of status transition records.
        created_at: When the record was created.
        updated_at: When the record was last modified.
    """

    id: int
    product_id: int
    company_id: int
    period_start: date
    period_end: date
    generated_at: datetime
    report_content: dict[str, Any]
    status: ReportStatusEnum
    version: int = Field(ge=1)
    status_history: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportStatusUpdateSchema(BaseModel):
    """Request schema for advancing a report's lifecycle status.

    Valid transitions:
        generated → reviewed → approved → submitted

    Attributes:
        status: Target status.
        comment: Optional comment explaining the status change (max 2000 chars).
    """

    status: ReportStatusEnum
    comment: str | None = Field(None, max_length=2000)


class ReportGenerateRequestSchema(BaseModel):
    """Request schema for manually generating a periodic safety report.

    Attributes:
        product_id: Medical product for which to generate the report.
        period_start: Start date of the reporting period (ISO-8601).
        period_end: End date of the reporting period (ISO-8601).
    """

    product_id: int
    period_start: date
    period_end: date

    @field_validator("period_end")
    @classmethod
    def validate_period_end_after_start(cls, v: date, info: Any) -> date:
        """Ensure period_end is after period_start."""
        period_start = info.data.get("period_start")
        if period_start is not None and v <= period_start:
            msg = "period_end must be after period_start"
            raise ValueError(msg)
        return v
