"""Property-based tests for backend report API (Properties 7 and 8).

Property 7: Backend report list is tenant-isolated and ordered.
Property 8: Backend report detail enforces tenant isolation.

**Validates: Requirements 12.1, 12.3, 12.4, 13.2, 13.4**

References:
    - Design: .kiro/specs/Step_2-5_report-data-entry-pdf-extraction/design.md (Properties 7, 8)
    - Requirements: .kiro/specs/Step_2-5_report-data-entry-pdf-extraction/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import given, settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.report import Report, ReportFieldValue
from alcoabase.models.template import Template
from alcoabase.models.user import User

# Ensure all mapper relationships are configured
configure_mappers()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> tuple[Session, "Engine"]:
    """Create a fresh SQLite in-memory database session with all tables.

    Returns:
        Tuple of (session, engine) for cleanup.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


def _create_user(session: Session, user_id: int) -> User:
    """Create and persist a test user.

    Args:
        session: Active database session.
        user_id: The user ID to assign.

    Returns:
        The persisted User instance.
    """
    user = User(
        id=user_id,
        username=f"user_{user_id}",
        email=f"user_{user_id}@test.local",
        hashed_password="hashed",
        full_name=f"Test User {user_id}",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_company(session: Session, company_id: int, slug: str) -> Company:
    """Create and persist a test company.

    Args:
        session: Active database session.
        company_id: The company ID to assign.
        slug: Unique slug for the company.

    Returns:
        The persisted Company instance.
    """
    company = Company(
        id=company_id,
        slug=slug,
        display_name=f"Company {slug}",
        regulatory_framework="ISO_13485",
        is_active=True,
    )
    session.add(company)
    session.flush()
    return company


def _create_template(
    session: Session, template_id: int, company_id: int, user_id: int
) -> Template:
    """Create and persist a test template.

    Args:
        session: Active database session.
        template_id: The template ID to assign.
        company_id: The owning company ID.
        user_id: The creating user ID.

    Returns:
        The persisted Template instance.
    """
    template = Template(
        id=template_id,
        document_uuid=f"2024-{template_id:05d}",
        name=f"Template {template_id}",
        json_schema={"fields": []},
        status="ReadOnly",
        created_by=user_id,
        company_id=company_id,
    )
    session.add(template)
    session.flush()
    return template


def _get_report_for_tenant(
    session: Session, report_id: int, company_id: int
) -> Report | None:
    """Simulate the get_report endpoint query logic.

    This replicates the exact query used in the get_report handler:
    SELECT report WHERE id = report_id AND company_id = tenant.company_id.

    Both not-found and cross-tenant access return None, which the endpoint
    translates to an identical 404 response.

    Args:
        session: Active database session.
        report_id: The report ID to look up.
        company_id: The tenant's company ID.

    Returns:
        The Report if found and belongs to tenant, None otherwise.
    """
    result = session.execute(
        select(Report).where(
            Report.id == report_id,
            Report.company_id == company_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

st_num_reports = st.integers(min_value=1, max_value=5)
st_nonexistent_offset = st.integers(min_value=100, max_value=999)


# ---------------------------------------------------------------------------
# Property 8: Backend report detail enforces tenant isolation
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_reports_a=st_num_reports,
    num_reports_b=st_num_reports,
    nonexistent_offset=st_nonexistent_offset,
)
def test_cross_tenant_report_detail_returns_none(
    num_reports_a: int,
    num_reports_b: int,
    nonexistent_offset: int,
) -> None:
    """For any report belonging to tenant A, a GET /api/reports/{report_id}
    request from tenant B (where B != A) SHALL return a 404 response that is
    indistinguishable from the response for a non-existent report ID.

    This test verifies that:
    1. Cross-tenant access returns None (-> 404)
    2. Non-existent report ID returns None (-> 404)
    3. Both results are identical (indistinguishable)
    4. Same-tenant access succeeds (returns the report)

    **Validates: Requirements 13.2, 13.4**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company_a = _create_company(session, company_id=1, slug="company-a")
        company_b = _create_company(session, company_id=2, slug="company-b")
        template_a = _create_template(session, template_id=1, company_id=1, user_id=1)
        template_b = _create_template(session, template_id=2, company_id=2, user_id=1)

        # Create reports for company A
        report_ids_a = []
        report_id = 1
        for i in range(num_reports_a):
            report = Report(
                id=report_id,
                document_uuid=template_a.document_uuid,
                template_id=template_a.id,
                uploaded_by=user.id,
                status="Draft",
                company_id=company_a.id,
            )
            session.add(report)
            report_ids_a.append(report_id)
            report_id += 1

        # Create reports for company B
        report_ids_b = []
        for i in range(num_reports_b):
            report = Report(
                id=report_id,
                document_uuid=template_b.document_uuid,
                template_id=template_b.id,
                uploaded_by=user.id,
                status="Extracted",
                company_id=company_b.id,
            )
            session.add(report)
            report_ids_b.append(report_id)
            report_id += 1

        session.commit()

        # A non-existent report ID (guaranteed to not exist)
        nonexistent_id = report_id + nonexistent_offset

        # --- Verify cross-tenant access returns None ---
        for rid in report_ids_a:
            # Tenant B tries to access tenant A's report
            cross_tenant_result = _get_report_for_tenant(
                session, report_id=rid, company_id=company_b.id
            )
            assert cross_tenant_result is None, (
                f"Cross-tenant leak: report {rid} from company A was "
                f"accessible with company B's tenant filter"
            )

        for rid in report_ids_b:
            # Tenant A tries to access tenant B's report
            cross_tenant_result = _get_report_for_tenant(
                session, report_id=rid, company_id=company_a.id
            )
            assert cross_tenant_result is None, (
                f"Cross-tenant leak: report {rid} from company B was "
                f"accessible with company A's tenant filter"
            )

        # --- Verify non-existent report returns None ---
        not_found_result_a = _get_report_for_tenant(
            session, report_id=nonexistent_id, company_id=company_a.id
        )
        not_found_result_b = _get_report_for_tenant(
            session, report_id=nonexistent_id, company_id=company_b.id
        )
        assert not_found_result_a is None, (
            f"Non-existent report {nonexistent_id} returned a result for company A"
        )
        assert not_found_result_b is None, (
            f"Non-existent report {nonexistent_id} returned a result for company B"
        )

        # --- Verify indistinguishability ---
        # Both cross-tenant and not-found produce the same None result,
        # which the endpoint translates to the same HTTPException(404, "Report not found.")
        # The response body is identical in both cases.
        cross_tenant_for_b = _get_report_for_tenant(
            session, report_id=report_ids_a[0], company_id=company_b.id
        )
        assert cross_tenant_for_b == not_found_result_b, (
            "Cross-tenant access and non-existent report should produce "
            "indistinguishable results (both None)"
        )

        # --- Verify same-tenant access succeeds ---
        for rid in report_ids_a:
            same_tenant_result = _get_report_for_tenant(
                session, report_id=rid, company_id=company_a.id
            )
            assert same_tenant_result is not None, (
                f"Report {rid} should be accessible from its own tenant (company A)"
            )
            assert same_tenant_result.id == rid
            assert same_tenant_result.company_id == company_a.id

        for rid in report_ids_b:
            same_tenant_result = _get_report_for_tenant(
                session, report_id=rid, company_id=company_b.id
            )
            assert same_tenant_result is not None, (
                f"Report {rid} should be accessible from its own tenant (company B)"
            )
            assert same_tenant_result.id == rid
            assert same_tenant_result.company_id == company_b.id

    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 7: Backend report list is tenant-isolated and ordered
# ---------------------------------------------------------------------------

# Strategies for Property 7
st_num_tenants = st.integers(min_value=2, max_value=4)
st_reports_per_tenant = st.integers(min_value=0, max_value=6)
st_target_tenant_idx = st.integers(min_value=0, max_value=3)


def _list_reports_for_tenant(
    session: Session, company_id: int
) -> list[Report]:
    """Simulate the list_reports endpoint query logic.

    This replicates the exact query used in the list_reports handler:
    SELECT reports WHERE company_id = tenant.company_id
    ORDER BY uploaded_at DESC.

    Args:
        session: Active database session.
        company_id: The tenant's company ID.

    Returns:
        List of reports filtered by company_id, ordered by uploaded_at desc.
    """
    result = session.execute(
        select(Report)
        .where(Report.company_id == company_id)
        .order_by(Report.uploaded_at.desc())
    )
    return list(result.scalars().all())


@settings(max_examples=100)
@given(
    num_tenants=st_num_tenants,
    reports_per_tenant=st_reports_per_tenant,
    target_tenant_idx=st_target_tenant_idx,
)
def test_list_reports_tenant_isolation_and_ordering(
    num_tenants: int,
    reports_per_tenant: int,
    target_tenant_idx: int,
) -> None:
    """For any set of reports across multiple tenants, list_reports for a given
    tenant SHALL return only reports where company_id matches the tenant's
    company ID, and the returned list SHALL be ordered by uploaded_at
    descending (each report's uploaded_at >= the next report's uploaded_at).

    **Validates: Requirements 12.1, 12.3, 12.4**
    """
    from datetime import UTC, datetime, timedelta

    # Ensure target_tenant_idx is within range
    target_tenant_idx = target_tenant_idx % num_tenants

    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)

        # Create multiple companies
        companies = []
        for i in range(num_tenants):
            company = _create_company(
                session, company_id=i + 1, slug=f"company-{i}"
            )
            companies.append(company)

        # Create templates for each company
        templates = []
        for i, company in enumerate(companies):
            template = _create_template(
                session,
                template_id=i + 1,
                company_id=company.id,
                user_id=user.id,
            )
            templates.append(template)

        # Create reports for each tenant with varying timestamps
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        report_id = 1
        all_reports: list[Report] = []

        for tenant_idx, company in enumerate(companies):
            template = templates[tenant_idx]
            for j in range(reports_per_tenant):
                # Use different time offsets to create varied ordering
                offset_hours = (tenant_idx * 100) + (j * 7) + (j * j)
                report = Report(
                    id=report_id,
                    document_uuid=template.document_uuid,
                    template_id=template.id,
                    uploaded_by=user.id,
                    status="Draft",
                    company_id=company.id,
                    uploaded_at=base_time + timedelta(hours=offset_hours),
                )
                session.add(report)
                all_reports.append(report)
                report_id += 1

        session.commit()

        # Target tenant
        target_company = companies[target_tenant_idx]

        # Query reports for the target tenant
        result = _list_reports_for_tenant(session, company_id=target_company.id)

        # Property 1: Only reports with matching company_id are returned
        for report in result:
            assert report.company_id == target_company.id, (
                f"Report {report.id} has company_id={report.company_id} "
                f"but target tenant company_id={target_company.id}"
            )

        # Property 2: Result count matches expected
        expected_count = sum(
            1 for r in all_reports if r.company_id == target_company.id
        )
        assert len(result) == expected_count, (
            f"Expected {expected_count} reports for company_id={target_company.id}, "
            f"got {len(result)}"
        )

        # Property 3: Results are ordered by uploaded_at descending
        for i in range(len(result) - 1):
            current_time = result[i].uploaded_at
            next_time = result[i + 1].uploaded_at
            assert current_time >= next_time, (
                f"Reports not ordered by uploaded_at descending: "
                f"report[{i}].uploaded_at={current_time} < "
                f"report[{i+1}].uploaded_at={next_time}"
            )

        # Property 4: No reports from other tenants are included
        other_tenant_ids = {
            r.id for r in all_reports if r.company_id != target_company.id
        }
        result_ids = {r.id for r in result}
        leaked_ids = result_ids & other_tenant_ids
        assert not leaked_ids, (
            f"Reports from other tenants leaked into response: {leaked_ids}"
        )

    finally:
        session.close()
        engine.dispose()


@settings(max_examples=100)
@given(num_tenants=st_num_tenants)
def test_list_reports_empty_for_tenant_with_no_reports(
    num_tenants: int,
) -> None:
    """For any tenant with no reports, list_reports SHALL return an empty list
    even when other tenants have reports.

    **Validates: Requirements 12.1, 12.3, 12.4**
    """
    from datetime import UTC, datetime, timedelta

    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)

        # Create companies
        companies = []
        for i in range(num_tenants):
            company = _create_company(
                session, company_id=i + 1, slug=f"company-{i}"
            )
            companies.append(company)

        # Create template and reports only for the first tenant
        template = _create_template(
            session, template_id=1, company_id=companies[0].id, user_id=user.id
        )
        base_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        for j in range(3):
            report = Report(
                id=j + 1,
                document_uuid=template.document_uuid,
                template_id=template.id,
                uploaded_by=user.id,
                status="Extracted",
                company_id=companies[0].id,
                uploaded_at=base_time + timedelta(hours=j),
            )
            session.add(report)

        session.commit()

        # Query for any tenant other than the first (they have no reports)
        for company in companies[1:]:
            result = _list_reports_for_tenant(session, company_id=company.id)
            assert result == [], (
                f"Expected empty list for company_id={company.id} "
                f"(has no reports), got {len(result)} reports"
            )

    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 9: Backend submission response contains all submitted field values
# ---------------------------------------------------------------------------

# Strategies for Property 9
st_num_fields = st.integers(min_value=1, max_value=10)
st_field_value = st.one_of(
    st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P"))),
    st.none(),
)


@st.composite
def st_field_values(draw: st.DrawFn) -> list[dict[str, str | None]]:
    """Generate a list of field value entries with unique field_uuids.

    Each entry has a field_uuid in FLD-XXXXXXXX format and a string or None value.

    Args:
        draw: Hypothesis draw function.

    Returns:
        List of dicts with 'field_uuid' and 'value' keys.
    """
    num = draw(st.integers(min_value=1, max_value=10))
    field_values = []
    for i in range(num):
        value = draw(st_field_value)
        field_values.append({
            "field_uuid": f"FLD-{i:08X}",
            "value": value,
        })
    return field_values


def _simulate_create_report_response(
    session: Session,
    company_id: int,
    user_id: int,
    template_id: int,
    document_uuid: str,
    field_values: list[dict[str, str | None]],
) -> dict:
    """Simulate the create_report endpoint's persistence and response logic.

    This replicates the core logic of the create_report handler:
    1. Create a Report with status "Draft"
    2. Create ReportFieldValue for each submitted field value
    3. Reload and return the response structure

    This tests the invariant that the response field_values array
    contains exactly the submitted field values with matching UUIDs and values.

    Args:
        session: Active database session.
        company_id: The tenant's company ID.
        user_id: The submitting user's ID.
        template_id: The template ID.
        document_uuid: The template's document UUID.
        field_values: List of field value dicts with 'field_uuid' and 'value'.

    Returns:
        Dict representing the ReportResponse with field_values array.
    """
    # Step 1: Create Report
    report = Report(
        document_uuid=document_uuid,
        template_id=template_id,
        uploaded_by=user_id,
        status="Draft",
        company_id=company_id,
    )
    session.add(report)
    session.flush()

    # Step 2: Create ReportFieldValue for each entry
    for fv in field_values:
        field_value = ReportFieldValue(
            report_id=report.id,
            field_uuid=fv["field_uuid"],
            value=fv["value"],
            validated=False,
        )
        session.add(field_value)

    session.flush()

    # Step 3: Reload with field_values (simulates selectinload)
    session.expire(report)
    reloaded = session.execute(
        select(Report).where(Report.id == report.id)
    ).scalar_one()

    # Eagerly load field_values
    _ = reloaded.field_values

    # Build response dict matching ReportResponse structure
    response = {
        "id": reloaded.id,
        "document_uuid": reloaded.document_uuid,
        "template_id": reloaded.template_id,
        "uploaded_by": reloaded.uploaded_by,
        "status": reloaded.status,
        "field_values": [
            {
                "field_uuid": fv.field_uuid,
                "value": fv.value,
                "validated": fv.validated,
            }
            for fv in reloaded.field_values
        ],
    }
    return response


@settings(max_examples=100)
@given(field_values=st_field_values())
def test_submission_response_contains_all_submitted_field_values(
    field_values: list[dict[str, str | None]],
) -> None:
    """For any valid report submission with N field values, the 201 response
    SHALL contain a field_values array of exactly N entries, where each entry's
    field_uuid matches one of the submitted field UUIDs and the value matches
    the submitted value.

    This test verifies:
    1. Response field_values count == submitted field_values count
    2. Every submitted field_uuid appears in the response
    3. Every response value matches the submitted value for that field_uuid

    **Validates: Requirements 11.6**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company = _create_company(session, company_id=1, slug="test-company")
        template = _create_template(
            session, template_id=1, company_id=company.id, user_id=user.id
        )
        session.commit()

        # Simulate the create_report endpoint
        response = _simulate_create_report_response(
            session=session,
            company_id=company.id,
            user_id=user.id,
            template_id=template.id,
            document_uuid=template.document_uuid,
            field_values=field_values,
        )

        # Property: response field_values count == submitted count
        n_submitted = len(field_values)
        n_response = len(response["field_values"])
        assert n_response == n_submitted, (
            f"Response contains {n_response} field_values but "
            f"{n_submitted} were submitted"
        )

        # Build lookup from response field_values
        response_map: dict[str, str | None] = {
            fv["field_uuid"]: fv["value"]
            for fv in response["field_values"]
        }

        # Property: every submitted field_uuid appears in response
        submitted_uuids = {fv["field_uuid"] for fv in field_values}
        response_uuids = set(response_map.keys())
        missing_uuids = submitted_uuids - response_uuids
        assert not missing_uuids, (
            f"Submitted field UUIDs missing from response: {missing_uuids}"
        )

        # Property: every response value matches the submitted value
        for fv in field_values:
            submitted_uuid = fv["field_uuid"]
            submitted_value = fv["value"]
            response_value = response_map[submitted_uuid]
            assert response_value == submitted_value, (
                f"Value mismatch for {submitted_uuid}: "
                f"submitted={submitted_value!r}, response={response_value!r}"
            )

    finally:
        session.close()
        engine.dispose()
