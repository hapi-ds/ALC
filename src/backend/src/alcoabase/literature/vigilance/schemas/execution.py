"""Pydantic v2 schemas for Vigilance Search Execution endpoints.

Provides response schemas for vigilance search execution records
including pagination support for listing executions.

References:
    - Requirements: 4.4, 10.5, 10.6
    - Design doc: VigilanceMonitorService interface
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ExecutionStatusEnum = Literal["running", "completed", "partial_failure", "failed"]


class VigilanceSearchExecutionResponseSchema(BaseModel):
    """Response schema for a vigilance search execution record.

    Attributes:
        id: Execution record ID.
        profile_id: Originating search profile ID.
        company_id: Company this execution belongs to.
        execution_timestamp: When the execution was performed (UTC).
        search_parameters: Full query as JSON.
        sources_queried: Array of source adapter names queried.
        total_results_found: Total raw results from all sources.
        results_after_exclusion: Results remaining after exclusion filtering.
        results_ingested: Results successfully ingested.
        results_duplicate: Results matching existing records (skipped).
        execution_duration_ms: Total execution time in milliseconds.
        status: Execution outcome status.
    """

    id: int
    profile_id: int
    company_id: int
    execution_timestamp: datetime
    search_parameters: dict[str, Any]
    sources_queried: list[str]
    total_results_found: int = Field(ge=0)
    results_after_exclusion: int = Field(ge=0)
    results_ingested: int = Field(ge=0)
    results_duplicate: int = Field(ge=0)
    execution_duration_ms: int = Field(ge=0)
    status: ExecutionStatusEnum

    model_config = ConfigDict(from_attributes=True)


class ExecutionListResponseSchema(BaseModel):
    """Response schema for paginated list of search executions.

    Attributes:
        executions: List of execution records for the current page.
        total_count: Total number of matching executions before pagination.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
    """

    executions: list[VigilanceSearchExecutionResponseSchema]
    total_count: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
