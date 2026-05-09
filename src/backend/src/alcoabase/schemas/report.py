"""Pydantic request/response schemas for report endpoints.

Provides validated schemas for PDF upload responses and
report field value representations.

References:
    - Design doc Section 4: PDF Extraction
    - Requirements 5: PDF Data Extraction and Database Mapping
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ReportFieldValueResponse(BaseModel):
    """Response schema for a single extracted field value.

    Attributes:
        field_uuid: The Field-UUID identifying the template field.
        value: The extracted string value (None if field was empty).
        validated: Whether the value passed type validation.
    """

    field_uuid: str
    value: str | None
    validated: bool

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    """Response schema for a successfully extracted report.

    Attributes:
        id: Report primary key.
        document_uuid: The Document-UUID from the PDF.
        template_id: Foreign key to the source template.
        uploaded_by: ID of the uploading user.
        uploaded_at: Server-side upload timestamp.
        status: Report processing status.
        field_values: List of extracted field values.
    """

    id: int
    document_uuid: str
    template_id: int
    uploaded_by: int
    uploaded_at: datetime | None = None
    status: str
    field_values: list[ReportFieldValueResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ValidationErrorDetail(BaseModel):
    """Schema for a single validation error in the response.

    Attributes:
        field_uuid: The Field-UUID that failed validation.
        field_label: Human-readable label for the field.
        expected_type: The expected data type.
        actual_value: The value that failed validation.
        message: Descriptive error message.
    """

    field_uuid: str
    field_label: str
    expected_type: str
    actual_value: str | None
    message: str


class UploadErrorResponse(BaseModel):
    """Response schema for PDF upload errors.

    Attributes:
        detail: High-level error description.
        validation_errors: List of field-level validation errors (if applicable).
    """

    detail: str
    validation_errors: list[ValidationErrorDetail] = Field(default_factory=list)


class ReportFieldValueInput(BaseModel):
    """Input for a single field value in manual report creation.

    Attributes:
        field_uuid: The Field-UUID identifying the template field (max 40 chars).
        value: The entered string value (None if field left empty, max 10000 chars).
    """

    field_uuid: str = Field(max_length=40)
    value: str | None = Field(default=None, max_length=10000)


class ReportCreateRequest(BaseModel):
    """Request body for POST /api/reports.

    Attributes:
        document_uuid: The Document-UUID of the template (max 12 chars).
        field_values: List of field value inputs (at least one required).
    """

    document_uuid: str = Field(max_length=12)
    field_values: list[ReportFieldValueInput] = Field(min_length=1)


class ComparisonFieldRow(BaseModel):
    """A single row in the comparison response.

    Attributes:
        field_uuid: The Field-UUID for this comparison row.
        field_label: Human-readable label for the field.
        extracted_value: Value from the PDF-extracted report (None if missing).
        entered_value: Value from the manually entered report (None if missing).
        is_match: Whether extracted and entered values are exactly equal.
    """

    field_uuid: str
    field_label: str
    extracted_value: str | None
    entered_value: str | None
    is_match: bool


class ComparisonResponse(BaseModel):
    """Response for GET /api/reports/{report_id}/compare.

    Attributes:
        report_id: The ID of the source (extracted) report.
        compared_with_report_id: The ID of the matching manual entry report (None if not found).
        total_fields: Total number of unique fields compared.
        matches: Number of fields where values match exactly.
        discrepancies: Number of fields where values differ or one side is missing.
        rows: List of comparison rows, one per unique field.
    """

    report_id: int
    compared_with_report_id: int | None
    total_fields: int
    matches: int
    discrepancies: int
    rows: list[ComparisonFieldRow]
