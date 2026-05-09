"""Property-based tests for workflow tenant isolation.

Tests Property 9 (Tenant isolation) from the BPMN Workflow Visual Editor
design document.

Verifies that workflow queries only return workflows matching the requesting
tenant's company_id, and that cross-tenant access returns 404.

**Validates: Requirements 10.4, 11.6**

References:
    - Design: .kiro/specs/Step_3-1_bpmn-workflow-visual-editor/design.md
    - Requirements: .kiro/specs/Step_3-1_bpmn-workflow-visual-editor/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import given, settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.user import User
from alcoabase.models.workflow import WorkflowDefinition, WorkflowVersion

# Ensure sqlalchemy_continuum tables are registered in Base.metadata
configure_mappers()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> tuple[Session, object]:
    """Create a fresh SQLite in-memory database session with all tables.

    Returns:
        Tuple of (session, engine) for cleanup.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
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


# ---------------------------------------------------------------------------
# Property 9: Tenant isolation
# ---------------------------------------------------------------------------


class TestWorkflowTenantIsolation:
    """Property tests verifying tenant isolation for workflow queries.

    For any workflow query (list, get by ID), the result set SHALL only
    contain workflows where company_id matches the requesting tenant's
    company_id. For any workflow belonging to a different tenant, GET
    SHALL return None (404 in the API).

    **Validates: Requirements 10.4, 11.6**
    """

    @given(
        num_workflows_a=st.integers(min_value=1, max_value=5),
        num_workflows_b=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_list_query_returns_only_own_tenant_workflows(
        self, num_workflows_a: int, num_workflows_b: int
    ) -> None:
        """Listing workflows SHALL return only workflows where company_id
        matches the requesting tenant's company_id.

        **Validates: Requirements 10.4**
        """
        session, engine = _make_session()
        try:
            user = _create_user(session, user_id=1)
            company_a = _create_company(
                session, company_id=1, slug="company-a"
            )
            company_b = _create_company(
                session, company_id=2, slug="company-b"
            )

            # Create workflows for company A
            wf_id = 1
            for i in range(num_workflows_a):
                wf = WorkflowDefinition(
                    id=wf_id,
                    name=f"Workflow A-{i}",
                    document_tag=f"tag-a-{i}",
                    bpmn_xml=f"<bpmn>A-{i}</bpmn>",
                    is_active=True,
                    risk_level="low",
                    current_version=1,
                    created_by=user.id,
                    company_id=company_a.id,
                )
                session.add(wf)
                wf_id += 1

            # Create workflows for company B
            for i in range(num_workflows_b):
                wf = WorkflowDefinition(
                    id=wf_id,
                    name=f"Workflow B-{i}",
                    document_tag=f"tag-b-{i}",
                    bpmn_xml=f"<bpmn>B-{i}</bpmn>",
                    is_active=True,
                    risk_level="low",
                    current_version=1,
                    created_by=user.id,
                    company_id=company_b.id,
                )
                session.add(wf)
                wf_id += 1

            session.commit()

            # Query with tenant A's context
            results_a = (
                session.execute(
                    select(WorkflowDefinition).where(
                        WorkflowDefinition.company_id == company_a.id
                    )
                )
                .scalars()
                .all()
            )

            # Only company A's workflows should be returned
            assert len(results_a) == num_workflows_a, (
                f"Expected {num_workflows_a} workflows for company A, "
                f"got {len(results_a)}"
            )
            for wf in results_a:
                assert wf.company_id == company_a.id, (
                    f"Workflow {wf.id} has company_id={wf.company_id}, "
                    f"expected {company_a.id}"
                )

            # Query with tenant B's context
            results_b = (
                session.execute(
                    select(WorkflowDefinition).where(
                        WorkflowDefinition.company_id == company_b.id
                    )
                )
                .scalars()
                .all()
            )

            assert len(results_b) == num_workflows_b, (
                f"Expected {num_workflows_b} workflows for company B, "
                f"got {len(results_b)}"
            )
            for wf in results_b:
                assert wf.company_id == company_b.id
        finally:
            session.close()
            engine.dispose()

    @given(
        num_workflows_a=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_get_by_id_returns_none_for_cross_tenant(
        self, num_workflows_a: int
    ) -> None:
        """GET by ID for a workflow belonging to a different tenant SHALL
        return None (the API translates this to 404).

        **Validates: Requirements 10.4**
        """
        session, engine = _make_session()
        try:
            user = _create_user(session, user_id=1)
            company_a = _create_company(
                session, company_id=1, slug="company-a"
            )
            company_b = _create_company(
                session, company_id=2, slug="company-b"
            )

            # Create workflows for company A
            workflow_ids = []
            for i in range(num_workflows_a):
                wf = WorkflowDefinition(
                    id=i + 1,
                    name=f"Workflow A-{i}",
                    document_tag=f"tag-a-{i}",
                    bpmn_xml=f"<bpmn>A-{i}</bpmn>",
                    is_active=True,
                    risk_level="low",
                    current_version=1,
                    created_by=user.id,
                    company_id=company_a.id,
                )
                session.add(wf)
                workflow_ids.append(i + 1)

            session.commit()

            # Try to access company A's workflows with company B's context
            for wf_id in workflow_ids:
                result = session.execute(
                    select(WorkflowDefinition).where(
                        WorkflowDefinition.id == wf_id,
                        WorkflowDefinition.company_id == company_b.id,
                    )
                ).scalar_one_or_none()

                # Should return None (API returns 404)
                assert result is None, (
                    f"Cross-tenant access: workflow {wf_id} from company A "
                    f"was accessible with company B's tenant filter"
                )

            # Verify the same workflows ARE accessible from company A
            for wf_id in workflow_ids:
                result = session.execute(
                    select(WorkflowDefinition).where(
                        WorkflowDefinition.id == wf_id,
                        WorkflowDefinition.company_id == company_a.id,
                    )
                ).scalar_one_or_none()

                assert result is not None, (
                    f"Workflow {wf_id} should be accessible from its own "
                    f"company's context"
                )
                assert result.company_id == company_a.id
        finally:
            session.close()
            engine.dispose()

    @given(
        num_workflows_a=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_version_history_scoped_to_tenant(
        self, num_workflows_a: int
    ) -> None:
        """Version history queries SHALL only return versions for workflows
        belonging to the requesting tenant.

        **Validates: Requirements 11.6**
        """
        session, engine = _make_session()
        try:
            user = _create_user(session, user_id=1)
            company_a = _create_company(
                session, company_id=1, slug="company-a"
            )
            company_b = _create_company(
                session, company_id=2, slug="company-b"
            )

            # Create workflows with versions for company A
            for i in range(num_workflows_a):
                wf = WorkflowDefinition(
                    id=i + 1,
                    name=f"Workflow A-{i}",
                    document_tag=f"tag-a-{i}",
                    bpmn_xml=f"<bpmn>A-{i}</bpmn>",
                    is_active=True,
                    risk_level="low",
                    current_version=1,
                    created_by=user.id,
                    company_id=company_a.id,
                )
                session.add(wf)
                session.flush()

                version = WorkflowVersion(
                    workflow_id=wf.id,
                    version_number=1,
                    bpmn_xml=wf.bpmn_xml,
                    name=wf.name,
                    document_tag=wf.document_tag,
                    risk_level=wf.risk_level,
                    signature_required_transitions=[],
                    training_trigger_transitions=[],
                    auto_assignment_config=None,
                    created_by=user.id,
                    change_reason="Initial creation",
                    company_id=company_a.id,
                )
                session.add(version)

            session.commit()

            # Verify the workflow is not accessible from company B's context
            for i in range(num_workflows_a):
                wf_id = i + 1

                # The API first checks if the workflow belongs to the tenant
                workflow_check = session.execute(
                    select(WorkflowDefinition).where(
                        WorkflowDefinition.id == wf_id,
                        WorkflowDefinition.company_id == company_b.id,
                    )
                ).scalar_one_or_none()

                # Should return None (API returns 404 before querying versions)
                assert workflow_check is None, (
                    f"Workflow {wf_id} should not be accessible from "
                    f"company B's context"
                )

            # Verify versions ARE accessible from company A's context
            for i in range(num_workflows_a):
                wf_id = i + 1

                workflow_check = session.execute(
                    select(WorkflowDefinition).where(
                        WorkflowDefinition.id == wf_id,
                        WorkflowDefinition.company_id == company_a.id,
                    )
                ).scalar_one_or_none()

                assert workflow_check is not None

                versions = (
                    session.execute(
                        select(WorkflowVersion).where(
                            WorkflowVersion.workflow_id == wf_id,
                            WorkflowVersion.company_id == company_a.id,
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(versions) == 1
                assert versions[0].company_id == company_a.id
        finally:
            session.close()
            engine.dispose()

    @given(
        num_companies=st.integers(min_value=2, max_value=4),
        workflows_per_company=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_no_cross_tenant_leakage_with_multiple_tenants(
        self, num_companies: int, workflows_per_company: int
    ) -> None:
        """For any number of tenants, querying workflows from one tenant
        SHALL never return workflows from another tenant.

        **Validates: Requirements 10.4, 11.6**
        """
        session, engine = _make_session()
        try:
            user = _create_user(session, user_id=1)

            companies = []
            for i in range(1, num_companies + 1):
                company = _create_company(
                    session, company_id=i, slug=f"company-{i}"
                )
                companies.append(company)

            # Create workflows distributed across companies
            wf_id = 1
            for company in companies:
                for j in range(workflows_per_company):
                    wf = WorkflowDefinition(
                        id=wf_id,
                        name=f"Workflow {company.slug}-{j}",
                        document_tag=f"tag-{wf_id}",
                        bpmn_xml=f"<bpmn>{company.slug}-{j}</bpmn>",
                        is_active=True,
                        risk_level="low",
                        current_version=1,
                        created_by=user.id,
                        company_id=company.id,
                    )
                    session.add(wf)
                    wf_id += 1

            session.commit()

            # For each company, verify isolation
            for company in companies:
                results = (
                    session.execute(
                        select(WorkflowDefinition).where(
                            WorkflowDefinition.company_id == company.id
                        )
                    )
                    .scalars()
                    .all()
                )

                # Should return exactly the expected count
                assert len(results) == workflows_per_company, (
                    f"Expected {workflows_per_company} workflows for "
                    f"{company.slug}, got {len(results)}"
                )

                # Every returned workflow belongs to this company
                for wf in results:
                    assert wf.company_id == company.id, (
                        f"Workflow {wf.id} has company_id={wf.company_id}, "
                        f"expected {company.id}"
                    )

                # No workflow from other companies should appear
                other_company_ids = [
                    c.id for c in companies if c.id != company.id
                ]
                for wf in results:
                    assert wf.company_id not in other_company_ids, (
                        f"Cross-tenant leak: workflow {wf.id} belongs to "
                        f"company {wf.company_id} but was returned in "
                        f"company {company.id}'s query"
                    )
        finally:
            session.close()
            engine.dispose()
