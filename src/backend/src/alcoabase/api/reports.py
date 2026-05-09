"""FastAPI router for report upload and extraction endpoints.

Provides the PDF upload endpoint that extracts field values from
completed offline PDFs using the PDFExtractor service, and the
manual report creation endpoint for direct field value submission.

References:
    - Design doc Section 4: PDF Extraction (PyMuPDF)
    - Requirements 5: PDF Data Extraction and Database Mapping
    - Requirements 11: Backend Report Submission Endpoint
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.report import Report, ReportFieldValue
from alcoabase.models.template import Template
from alcoabase.schemas.report import (
    ComparisonFieldRow,
    ComparisonResponse,
    ReportCreateRequest,
    ReportResponse,
    UploadErrorResponse,
    ValidationErrorDetail,
)
from alcoabase.services.field_validator import validate_single_value
from alcoabase.services.pdf_extractor import PDFExtractor

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("", response_model=list[ReportResponse])
async def list_reports(
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[ReportResponse]:
    """List all reports for the current tenant, newest first.

    Filters by company_id matching the resolved tenant, orders by
    uploaded_at descending, and eagerly loads field_values relationship.

    Args:
        session: Async database session.
        tenant: Resolved tenant context providing company_id filter.

    Returns:
        List of ReportResponse objects ordered by uploaded_at descending.
        Returns an empty list if no reports exist for the tenant.
    """
    stmt = (
        select(Report)
        .where(Report.company_id == tenant.company_id)
        .order_by(Report.uploaded_at.desc())
        .options(selectinload(Report.field_values))
    )
    result = await session.execute(stmt)
    reports = result.scalars().all()
    return [ReportResponse.model_validate(report) for report in reports]

# Module-level service instance
_pdf_extractor = PDFExtractor()


def get_pdf_extractor() -> PDFExtractor:
    """Provide the PDFExtractor instance as a dependency.

    Returns:
        The module-level PDFExtractor instance.
    """
    return _pdf_extractor


@router.get("/{report_id}/compare", response_model=ComparisonResponse)
async def compare_report(
    report_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ComparisonResponse:
    """Compare an extracted report with a manual entry report.

    Finds the source report (must be status "Extracted"), then finds
    a matching "Draft" report with the same document_uuid. Aligns
    fields by field_uuid and performs exact string comparison.

    Args:
        report_id: The ID of the source (extracted) report.
        session: Async database session.
        tenant: Resolved tenant context.

    Returns:
        ComparisonResponse with field-by-field comparison rows.

    Raises:
        HTTPException 404: If report does not exist or belongs to another tenant.
        HTTPException 400: If report status is not "Extracted".
    """
    # Step 1: Load source report (must belong to tenant)
    result = await session.execute(
        select(Report)
        .where(Report.id == report_id, Report.company_id == tenant.company_id)
        .options(selectinload(Report.field_values))
    )
    source_report = result.scalar_one_or_none()

    if source_report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    # Must be "Extracted" status
    if source_report.status != "Extracted":
        raise HTTPException(
            status_code=400,
            detail="Only reports with status 'Extracted' can be compared.",
        )

    # Step 2: Find matching "Draft" report with same document_uuid and company_id
    result = await session.execute(
        select(Report)
        .where(
            Report.document_uuid == source_report.document_uuid,
            Report.company_id == tenant.company_id,
            Report.status == "Draft",
            Report.id != source_report.id,
        )
        .options(selectinload(Report.field_values))
        .order_by(Report.uploaded_at.desc())
        .limit(1)
    )
    draft_report = result.scalar_one_or_none()

    # Step 3: If no matching Draft report, return empty comparison
    if draft_report is None:
        return ComparisonResponse(
            report_id=source_report.id,
            compared_with_report_id=None,
            total_fields=0,
            matches=0,
            discrepancies=0,
            rows=[],
        )

    # Step 4: Build value maps
    extracted_map: dict[str, str | None] = {
        fv.field_uuid: fv.value for fv in source_report.field_values
    }
    entered_map: dict[str, str | None] = {
        fv.field_uuid: fv.value for fv in draft_report.field_values
    }

    # Step 5: Union all field_uuids
    all_field_uuids = set(extracted_map.keys()) | set(entered_map.keys())

    # Resolve field labels from template
    result = await session.execute(
        select(Template)
        .where(Template.id == source_report.template_id)
        .options(selectinload(Template.fields))
    )
    template = result.scalar_one_or_none()

    label_map: dict[str, str] = {}
    if template is not None:
        label_map = {
            tf.field_uuid: tf.field_label
            for tf in template.fields
            if tf.element_type == "field"
        }

    # Step 6: Compare values for each field_uuid
    rows: list[ComparisonFieldRow] = []
    matches = 0
    discrepancies = 0

    for field_uuid in sorted(all_field_uuids):
        extracted_value = extracted_map.get(field_uuid)
        entered_value = entered_map.get(field_uuid)
        field_label = label_map.get(field_uuid, field_uuid)

        # Exact string comparison (case-sensitive, no trimming)
        # A missing value on either side counts as a discrepancy
        is_match = (
            extracted_value is not None
            and entered_value is not None
            and extracted_value == entered_value
        )

        if is_match:
            matches += 1
        else:
            discrepancies += 1

        rows.append(
            ComparisonFieldRow(
                field_uuid=field_uuid,
                field_label=field_label,
                extracted_value=extracted_value,
                entered_value=entered_value,
                is_match=is_match,
            )
        )

    # Step 7: Return ComparisonResponse
    return ComparisonResponse(
        report_id=source_report.id,
        compared_with_report_id=draft_report.id,
        total_fields=len(rows),
        matches=matches,
        discrepancies=discrepancies,
        rows=rows,
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ReportResponse:
    """Get a single report by ID, scoped to tenant.

    Queries by both report_id and company_id in a single query to prevent
    information leakage. Returns 404 for both not-found and cross-tenant
    access (indistinguishable responses).

    Args:
        report_id: The report's primary key.
        session: Async database session.
        tenant: Resolved tenant context.

    Returns:
        ReportResponse with field_values eagerly loaded.

    Raises:
        HTTPException 404: If report does not exist or belongs to another tenant.
    """
    result = await session.execute(
        select(Report)
        .where(Report.id == report_id, Report.company_id == tenant.company_id)
        .options(selectinload(Report.field_values))
    )
    report = result.scalar_one_or_none()

    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    return ReportResponse.model_validate(report)


@router.post(
    "",
    response_model=ReportResponse,
    status_code=201,
    responses={400: {"model": UploadErrorResponse}},
)
async def create_report(
    payload: ReportCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ReportResponse:
    """Create a report from manually entered field values.

    Validates document_uuid belongs to tenant, all field_uuids exist in
    the template, and all values pass type validation. Persists atomically.

    Args:
        payload: ReportCreateRequest with document_uuid and field_values.
        session: Async database session.
        tenant: Resolved tenant context.

    Returns:
        201 ReportResponse on success.

    Raises:
        HTTPException 400: Invalid document_uuid, unknown field_uuids,
            type validation failures, or empty field_values.
    """
    # Step 1: Query template by document_uuid + company_id
    result = await session.execute(
        select(Template)
        .where(
            Template.document_uuid == payload.document_uuid,
            Template.company_id == tenant.company_id,
        )
        .options(selectinload(Template.fields))
    )
    template = result.scalar_one_or_none()

    # Step 2: If not found -> 400
    if template is None:
        raise HTTPException(
            status_code=400,
            detail="No template found for document_uuid.",
        )

    # Step 3: Build field_map from template fields (element_type="field" only)
    field_map = {
        tf.field_uuid: tf
        for tf in template.fields
        if tf.element_type == "field"
    }

    # Step 4: Check each submitted field_uuid exists in field_map
    unknown_uuids = [
        fv.field_uuid
        for fv in payload.field_values
        if fv.field_uuid not in field_map
    ]
    if unknown_uuids:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Unknown field UUIDs not found in template.",
                "unknown_field_uuids": unknown_uuids,
            },
        )

    # Step 5: Validate each field value against its type
    validation_errors: list[ValidationErrorDetail] = []
    for fv in payload.field_values:
        # Skip validation for null/empty values
        if fv.value is None or fv.value == "":
            continue

        template_field = field_map[fv.field_uuid]
        error = validate_single_value(
            value=fv.value,
            field_type=template_field.field_type,
            field_uuid=fv.field_uuid,
            field_label=template_field.field_label,
            context="manual",
        )
        if error is not None:
            validation_errors.append(
                ValidationErrorDetail(
                    field_uuid=error.field_uuid,
                    field_label=error.field_label,
                    expected_type=error.expected_type,
                    actual_value=error.actual_value,
                    message=error.message,
                )
            )

    # Step 6: If validation errors -> 400
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Type validation failed. No data was persisted.",
                "validation_errors": [e.model_dump() for e in validation_errors],
            },
        )

    # Step 7: Create Report with status "Draft"
    report = Report(
        document_uuid=payload.document_uuid,
        template_id=template.id,
        uploaded_by=tenant.user_id,
        status="Draft",
        company_id=tenant.company_id,
    )
    session.add(report)
    await session.flush()

    # Step 8: Create ReportFieldValue for each entry
    for fv in payload.field_values:
        field_value = ReportFieldValue(
            report_id=report.id,
            field_uuid=fv.field_uuid,
            value=fv.value,
            validated=False,
        )
        session.add(field_value)

    await session.flush()

    # Step 9: Reload with relationships -> return ReportResponse
    result = await session.execute(
        select(Report)
        .where(Report.id == report.id)
        .options(selectinload(Report.field_values))
    )
    report = result.scalar_one()

    return ReportResponse.model_validate(report)


@router.post(
    "/upload-pdf",
    response_model=ReportResponse,
    status_code=201,
    responses={400: {"model": UploadErrorResponse}},
)
async def upload_pdf(
    file: UploadFile,
    user_id: int = 1,
    session: AsyncSession = Depends(get_db_session),
    extractor: PDFExtractor = Depends(get_pdf_extractor),
    tenant: TenantContext = Depends(get_tenant_context),
) -> ReportResponse:
    """Upload a completed PDF and extract field values.

    Reads the embedded Document-UUID to match the PDF to a template,
    extracts all field values by Field-UUID, validates types, and
    persists atomically (all-or-nothing).

    Args:
        file: The uploaded PDF file.
        user_id: ID of the uploading user (simplified auth for now).
        session: Database session dependency.
        extractor: PDFExtractor dependency.

    Returns:
        The created Report with extracted field values.

    Raises:
        HTTPException: 400 for unknown Document-UUID or validation failures.
    """
    # Read the PDF bytes
    pdf_bytes = await file.read()

    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # Step 1: Read the Document-UUID from the PDF
    document_uuid = extractor.read_document_uuid(pdf_bytes)
    if not document_uuid:
        raise HTTPException(
            status_code=400,
            detail="PDF does not contain a valid __DOC_UUID__ field. "
            "This PDF was not generated by AlcoaBase.",
        )

    # Step 2: Match Document-UUID to a template
    result = await session.execute(
        select(Template)
        .where(Template.document_uuid == document_uuid)
        .options(selectinload(Template.fields))
    )
    template = result.scalar_one_or_none()

    if template is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown Document-UUID: '{document_uuid}'. "
            f"No template found matching this PDF.",
        )

    # TODO: Validate cross-tenant template reference — reject with 403 if
    # template belongs to a different company than tenant.company_id

    # Step 3: Extract and validate field values
    extracted = extractor.extract_data(pdf_bytes, template)

    # Step 4: Check for validation errors — reject entirely if any
    if not extracted.is_valid:
        error_details = [
            ValidationErrorDetail(
                field_uuid=err.field_uuid,
                field_label=err.field_label,
                expected_type=err.expected_type,
                actual_value=err.actual_value,
                message=err.message,
            )
            for err in extracted.validation_errors
        ]
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Type validation failed. No data was persisted.",
                "validation_errors": [e.model_dump() for e in error_details],
            },
        )

    # Step 5: Atomic persistence — create Report + all ReportFieldValues
    # TODO: Set company_id=tenant.company_id on created resource
    report = Report(
        document_uuid=document_uuid,
        template_id=template.id,
        uploaded_by=user_id,
        status="Extracted",
    )
    session.add(report)
    await session.flush()

    # Create field value records
    for template_field in template.fields:
        value = extracted.field_values.get(template_field.field_uuid)
        field_value = ReportFieldValue(
            report_id=report.id,
            field_uuid=template_field.field_uuid,
            value=value,
            validated=True,
        )
        session.add(field_value)

    await session.flush()

    # Reload report with field_values relationship
    result = await session.execute(
        select(Report)
        .where(Report.id == report.id)
        .options(selectinload(Report.field_values))
    )
    report = result.scalar_one()

    return ReportResponse.model_validate(report)
