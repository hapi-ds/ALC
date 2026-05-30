"""Pydantic request/response schemas for audit trail endpoints.

Provides validated schemas for audit event listing, filtering,
detail views, and PDF export operations.

References:
    - Design doc: Data Models > Backend Schemas (Pydantic)
    - Requirements 1–3: Aggregation, pagination, filtering
    - Requirements 5–7: Search, detail view, PDF export
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# Allowed record types for audit trail filtering
ALLOWED_RECORD_TYPES = (
    "documents",
    "templates",
    "reports",
    "workflows",
    "signatures",
    "training_tasks",
    "training_records",
)


class AuditTrailFilters(BaseModel):
    """Filter criteria for audit trail queries.

    Attributes:
        user_id: Filter by the user who performed the action.
        date_start: Inclusive start of date range filter.
        date_end: Inclusive end of date range filter.
        record_type: Filter by record type (must be an allowed type).
        operation_type: Filter by operation type (INSERT, UPDATE, DELETE).
    """

    user_id: int | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    record_type: str | None = None
    operation_type: Literal["INSERT", "UPDATE", "DELETE"] | None = None

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, v: str | None) -> str | None:
        """Validate record_type against allowed values."""
        if v is not None and v not in ALLOWED_RECORD_TYPES:
            raise ValueError(
                f"Invalid record_type '{v}'. "
                f"Allowed types: {', '.join(ALLOWED_RECORD_TYPES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_date_range(self) -> "AuditTrailFilters":
        """Ensure date_start is not after date_end when both are provided."""
        if self.date_start is not None and self.date_end is not None:
            if self.date_start > self.date_end:
                raise ValueError("date_start must be before date_end")
        return self


class AuditEvent(BaseModel):
    """Single audit event in the aggregated view.

    Attributes:
        transaction_id: Continuum transaction ID (correlation identifier).
        timestamp: Server-side UTC timestamp of the change.
        user_id: Numeric ID of the user who performed the action.
        user_display_name: Resolved display name (None if user unavailable).
        record_type: Type of record that was changed.
        record_id: Primary key of the changed record.
        operation_type: Type of operation performed.
        change_reason: Human-readable justification for the change.
        changed_fields: List of changed field names (max 10 displayed).
        total_changed_fields: Actual count of all changed fields.
        company_id: Company the record belongs to.
    """

    transaction_id: int
    timestamp: datetime
    user_id: int
    user_display_name: str | None = None
    record_type: str
    record_id: int
    operation_type: Literal["INSERT", "UPDATE", "DELETE"]
    change_reason: str | None = None
    changed_fields: list[str] = Field(default_factory=list, max_length=10)
    total_changed_fields: int = 0
    company_id: int

    model_config = {"from_attributes": True}


class FieldChange(BaseModel):
    """Single field change within an audit event.

    Attributes:
        field_name: Name of the field that changed.
        old_value: Previous value (None for INSERT operations).
        new_value: New value (None for DELETE operations).
    """

    field_name: str
    old_value: Any | None = None
    new_value: Any | None = None


class AuditEventDetail(BaseModel):
    """Full detail view of a single audit event with field-level changes.

    Attributes:
        transaction_id: Continuum transaction ID.
        timestamp: Server-side UTC timestamp of the change.
        user_id: Numeric ID of the user who performed the action.
        user_display_name: Resolved display name (None if user unavailable).
        record_type: Type of record that was changed.
        record_id: Primary key of the changed record.
        operation_type: Type of operation performed.
        change_reason: Human-readable justification for the change.
        field_changes: Complete list of field-level changes.
        company_id: Company the record belongs to.
    """

    transaction_id: int
    timestamp: datetime
    user_id: int
    user_display_name: str | None = None
    record_type: str
    record_id: int
    operation_type: Literal["INSERT", "UPDATE", "DELETE"]
    change_reason: str | None = None
    field_changes: list[FieldChange] = Field(default_factory=list)
    company_id: int

    model_config = {"from_attributes": True}


class AuditTrailPage(BaseModel):
    """Paginated response for audit trail listing.

    Attributes:
        events: List of audit events for the current page.
        next_cursor: Opaque cursor for fetching the next page (None if last page).
        total_count: Total number of events matching the current filters.
        warnings: List of warnings (e.g., failed record type queries).
    """

    events: list[AuditEvent] = Field(default_factory=list)
    next_cursor: str | None = None
    total_count: int = 0
    warnings: list[str] | None = None


class ExportMetadata(BaseModel):
    """Metadata included in PDF export header.

    Attributes:
        company_name: Name of the company for the export.
        export_timestamp: UTC timestamp when the export was generated.
        filters_applied: Filter criteria that were active during export.
        total_event_count: Total number of events included in the export.
        requesting_user_name: Display name of the user who requested the export.
    """

    company_name: str
    export_timestamp: datetime
    filters_applied: AuditTrailFilters
    total_event_count: int
    requesting_user_name: str


class ExportRequest(BaseModel):
    """Request schema for triggering a PDF export.

    Attributes:
        filters: Optional filter criteria to apply to the export.
        search_query: Optional search query to apply to the export.
    """

    filters: AuditTrailFilters | None = None
    search_query: str | None = None


class ExportStatusResponse(BaseModel):
    """Response for export status check.

    Attributes:
        job_id: Unique identifier for the export job.
        status: Current status of the export job.
        download_url: Presigned URL for downloading the PDF (when completed).
        error_message: Error description (when failed).
    """

    job_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    download_url: str | None = None
    error_message: str | None = None


class AuditTrailListParams(BaseModel):
    """Query parameters for listing audit trail events.

    Attributes:
        cursor: Opaque cursor for pagination (None for first page).
        page_size: Number of events per page (1–200, default 50).
        search: Optional search query string.
        user_id: Filter by user ID.
        date_start: Filter by start date (inclusive).
        date_end: Filter by end date (inclusive).
        record_type: Filter by record type.
        operation_type: Filter by operation type.
    """

    cursor: str | None = None
    page_size: int = Field(default=50, ge=1, le=200)
    search: str | None = None
    user_id: int | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None
    record_type: str | None = None
    operation_type: Literal["INSERT", "UPDATE", "DELETE"] | None = None

    @field_validator("record_type")
    @classmethod
    def validate_record_type(cls, v: str | None) -> str | None:
        """Validate record_type against allowed values."""
        if v is not None and v not in ALLOWED_RECORD_TYPES:
            raise ValueError(
                f"Invalid record_type '{v}'. "
                f"Allowed types: {', '.join(ALLOWED_RECORD_TYPES)}"
            )
        return v
