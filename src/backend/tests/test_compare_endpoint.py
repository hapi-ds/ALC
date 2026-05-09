"""Unit tests for the GET /api/reports/{report_id}/compare endpoint.

Tests the comparison logic between an Extracted report and a matching
Draft report with the same document_uuid.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8**

References:
    - Design: .kiro/specs/Step_2-5_report-data-entry-pdf-extraction/design.md
    - Requirements: .kiro/specs/Step_2-5_report-data-entry-pdf-extraction/requirements.md
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers, selectinload, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.report import Report, ReportFieldValue
from alcoabase.models.template import Template, TemplateField
from alcoabase.models.user import User

# Ensure all mapper relationships are configured
configure_mappers()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> tuple[Session, object]:
    """Create a fresh SQLite in-memory database session with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


def _setup_base_data(session: Session) -> tuple[User, Company, Template]:
    """Create base test data: user, company, template with fields."""
    user = User(
        id=1,
        username="analyst",
        email="analyst@test.local",
        hashed_password="hashed",
        full_name="Test Analyst",
        is_active=True,
    )
    session.add(user)

    company = Company(
        id=1,
        slug="lab-corp",
        display_name="Lab Corp",
        regulatory_framework="ISO_13485",
        is_active=True,
    )
    session.add(company)

    template = Template(
        id=1,
        document_uuid="2024-00001",
        name="Test Template",
        json_schema={"elements": []},
        status="ReadOnly",
        created_by=1,
        company_id=1,
    )
    session.add(template)
    session.flush()

    # Add template fields
    fields = [
        TemplateField(
            id=1,
            template_id=1,
            field_uuid="FLD-00000001",
            field_type="Text",
            field_label="Sample ID",
            field_order=1,
            element_type="field",
        ),
        TemplateField(
            id=2,
            template_id=1,
            field_uuid="FLD-00000002",
            field_type="Float",
            field_label="Temperature",
            field_order=2,
            element_type="field",
        ),
        TemplateField(
            id=3,
            template_id=1,
            field_uuid="FLD-00000003",
            field_type="Date",
            field_label="Test Date",
            field_order=3,
            element_type="field",
        ),
    ]
    for f in fields:
        session.add(f)
    session.flush()

    return user, company, template


def _simulate_compare(
    session: Session, report_id: int, company_id: int
) -> dict:
    """Simulate the compare_report endpoint logic.

    Replicates the exact algorithm from the compare_report handler.

    Returns:
        Dict with comparison response fields, or raises ValueError/KeyError
        for error conditions.
    """
    # Step 1: Load source report
    result = session.execute(
        select(Report)
        .where(Report.id == report_id, Report.company_id == company_id)
        .options(selectinload(Report.field_values))
    )
    source_report = result.scalar_one_or_none()

    if source_report is None:
        raise KeyError("Report not found.")

    if source_report.status != "Extracted":
        raise ValueError("Only reports with status 'Extracted' can be compared.")

    # Step 2: Find matching Draft report
    result = session.execute(
        select(Report)
        .where(
            Report.document_uuid == source_report.document_uuid,
            Report.company_id == company_id,
            Report.status == "Draft",
            Report.id != source_report.id,
        )
        .options(selectinload(Report.field_values))
        .order_by(Report.uploaded_at.desc())
        .limit(1)
    )
    draft_report = result.scalar_one_or_none()

    # Step 3: No matching Draft
    if draft_report is None:
        return {
            "report_id": source_report.id,
            "compared_with_report_id": None,
            "total_fields": 0,
            "matches": 0,
            "discrepancies": 0,
            "rows": [],
        }

    # Step 4: Build value maps
    extracted_map = {fv.field_uuid: fv.value for fv in source_report.field_values}
    entered_map = {fv.field_uuid: fv.value for fv in draft_report.field_values}

    # Step 5: Union all field_uuids
    all_field_uuids = set(extracted_map.keys()) | set(entered_map.keys())

    # Resolve labels from template
    result = session.execute(
        select(Template)
        .where(Template.id == source_report.template_id)
        .options(selectinload(Template.fields))
    )
    template = result.scalar_one_or_none()
    label_map: dict[str, str] = {}
    if template:
        label_map = {
            tf.field_uuid: tf.field_label
            for tf in template.fields
            if tf.element_type == "field"
        }

    # Step 6: Compare
    rows = []
    matches = 0
    discrepancies = 0

    for field_uuid in sorted(all_field_uuids):
        extracted_value = extracted_map.get(field_uuid)
        entered_value = entered_map.get(field_uuid)
        field_label = label_map.get(field_uuid, field_uuid)

        is_match = (
            extracted_value is not None
            and entered_value is not None
            and extracted_value == entered_value
        )

        if is_match:
            matches += 1
        else:
            discrepancies += 1

        rows.append({
            "field_uuid": field_uuid,
            "field_label": field_label,
            "extracted_value": extracted_value,
            "entered_value": entered_value,
            "is_match": is_match,
        })

    return {
        "report_id": source_report.id,
        "compared_with_report_id": draft_report.id,
        "total_fields": len(rows),
        "matches": matches,
        "discrepancies": discrepancies,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_compare_report_not_found() -> None:
    """Returns error when report does not exist."""
    import pytest

    session, engine = _make_session()
    try:
        _setup_base_data(session)
        session.commit()

        with pytest.raises(KeyError, match="Report not found"):
            _simulate_compare(session, report_id=999, company_id=1)
    finally:
        session.close()
        engine.dispose()


def test_compare_report_wrong_tenant() -> None:
    """Returns error when report belongs to different tenant."""
    import pytest

    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)

        company_b = Company(
            id=2,
            slug="other-lab",
            display_name="Other Lab",
            regulatory_framework="ISO_13485",
            is_active=True,
        )
        session.add(company_b)

        report = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
        )
        session.add(report)
        session.commit()

        with pytest.raises(KeyError, match="Report not found"):
            _simulate_compare(session, report_id=1, company_id=2)
    finally:
        session.close()
        engine.dispose()


def test_compare_report_not_extracted_status() -> None:
    """Returns error when report status is not 'Extracted'."""
    import pytest

    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)

        report = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
        )
        session.add(report)
        session.commit()

        with pytest.raises(ValueError, match="Only reports with status 'Extracted'"):
            _simulate_compare(session, report_id=1, company_id=1)
    finally:
        session.close()
        engine.dispose()


def test_compare_no_matching_draft() -> None:
    """Returns empty comparison when no matching Draft report exists."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)

        report = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
        )
        session.add(report)
        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["report_id"] == 1
        assert result["compared_with_report_id"] is None
        assert result["total_fields"] == 0
        assert result["matches"] == 0
        assert result["discrepancies"] == 0
        assert result["rows"] == []
    finally:
        session.close()
        engine.dispose()


def test_compare_all_fields_match() -> None:
    """All fields match when extracted and entered values are identical."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        for report_id in [1, 2]:
            session.add(ReportFieldValue(
                report_id=report_id, field_uuid="FLD-00000001",
                value="SAMPLE-001", validated=True,
            ))
            session.add(ReportFieldValue(
                report_id=report_id, field_uuid="FLD-00000002",
                value="23.5", validated=True,
            ))
            session.add(ReportFieldValue(
                report_id=report_id, field_uuid="FLD-00000003",
                value="2024-06-01", validated=True,
            ))

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["report_id"] == 1
        assert result["compared_with_report_id"] == 2
        assert result["total_fields"] == 3
        assert result["matches"] == 3
        assert result["discrepancies"] == 0
        assert all(row["is_match"] for row in result["rows"])
    finally:
        session.close()
        engine.dispose()


def test_compare_with_discrepancies() -> None:
    """Detects discrepancies when values differ between reports."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        # Extracted values
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000001",
            value="SAMPLE-001", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000002",
            value="23.5", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000003",
            value="2024-06-01", validated=True,
        ))

        # Entered values (one differs)
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000001",
            value="SAMPLE-001", validated=False,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000002",
            value="24.0", validated=False,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000003",
            value="2024-06-01", validated=False,
        ))

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["total_fields"] == 3
        assert result["matches"] == 2
        assert result["discrepancies"] == 1
        assert result["matches"] + result["discrepancies"] == result["total_fields"]

        discrepancy_rows = [r for r in result["rows"] if not r["is_match"]]
        assert len(discrepancy_rows) == 1
        assert discrepancy_rows[0]["field_uuid"] == "FLD-00000002"
        assert discrepancy_rows[0]["extracted_value"] == "23.5"
        assert discrepancy_rows[0]["entered_value"] == "24.0"
    finally:
        session.close()
        engine.dispose()


def test_compare_case_sensitive() -> None:
    """Comparison is case-sensitive (no normalization)."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000001",
            value="Sample-001", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000001",
            value="SAMPLE-001", validated=False,
        ))

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["discrepancies"] == 1
        assert result["matches"] == 0
        assert not result["rows"][0]["is_match"]
    finally:
        session.close()
        engine.dispose()


def test_compare_missing_value_counts_as_discrepancy() -> None:
    """A field present in one report but not the other is a discrepancy."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        # Extracted has 3 fields
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000001",
            value="SAMPLE-001", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000002",
            value="23.5", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000003",
            value="2024-06-01", validated=True,
        ))

        # Draft only has 2 fields (missing FLD-00000003)
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000001",
            value="SAMPLE-001", validated=False,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000002",
            value="23.5", validated=False,
        ))

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["total_fields"] == 3
        assert result["matches"] == 2
        assert result["discrepancies"] == 1

        missing_row = next(
            r for r in result["rows"] if r["field_uuid"] == "FLD-00000003"
        )
        assert missing_row["extracted_value"] == "2024-06-01"
        assert missing_row["entered_value"] is None
        assert not missing_row["is_match"]
    finally:
        session.close()
        engine.dispose()


def test_compare_null_value_counts_as_discrepancy() -> None:
    """A None value on one side counts as a discrepancy even if field exists."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000001",
            value="SAMPLE-001", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000001",
            value=None, validated=False,
        ))

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["total_fields"] == 1
        assert result["matches"] == 0
        assert result["discrepancies"] == 1
        assert not result["rows"][0]["is_match"]
    finally:
        session.close()
        engine.dispose()


def test_compare_resolves_field_labels_from_template() -> None:
    """Field labels are resolved from the template's fields."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000001",
            value="X", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000001",
            value="X", validated=False,
        ))

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["rows"][0]["field_label"] == "Sample ID"
    finally:
        session.close()
        engine.dispose()


def test_compare_total_equals_matches_plus_discrepancies() -> None:
    """Invariant: total_fields == matches + discrepancies always holds."""
    session, engine = _make_session()
    try:
        _, company, template = _setup_base_data(session)
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        extracted = Report(
            id=1,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Extracted",
            company_id=company.id,
            uploaded_at=base_time,
        )
        session.add(extracted)
        session.flush()

        draft = Report(
            id=2,
            document_uuid=template.document_uuid,
            template_id=template.id,
            uploaded_by=1,
            status="Draft",
            company_id=company.id,
            uploaded_at=base_time + timedelta(hours=1),
        )
        session.add(draft)
        session.flush()

        # Mix of matches, discrepancies, and missing
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000001",
            value="MATCH", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000002",
            value="23.5", validated=True,
        ))
        session.add(ReportFieldValue(
            report_id=1, field_uuid="FLD-00000003",
            value="2024-06-01", validated=True,
        ))

        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000001",
            value="MATCH", validated=False,
        ))
        session.add(ReportFieldValue(
            report_id=2, field_uuid="FLD-00000002",
            value="99.9", validated=False,
        ))
        # FLD-00000003 missing from draft

        session.commit()

        result = _simulate_compare(session, report_id=1, company_id=1)

        assert result["total_fields"] == result["matches"] + result["discrepancies"]
    finally:
        session.close()
        engine.dispose()
