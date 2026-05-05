"""Property-based tests for tenant isolation across all resource types.

Tests Properties 7, 8, 9, 10, 11, 12, and 13 from the multi-tenancy design
document, validating that tenant-scoped resources are correctly isolated,
auto-scoped on creation, and inaccessible across tenant boundaries.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5,
5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3**

References:
    - Design: .kiro/specs/multi-tenancy/design.md (Correctness Properties 7-13)
    - Requirements: .kiro/specs/multi-tenancy/requirements.md (Requirements 3-7)
"""

import hypothesis.strategies as st
from hypothesis import given, settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag
from alcoabase.models.report import Report
from alcoabase.models.template import Template
from alcoabase.models.training import TrainingRecord, TrainingTask
from alcoabase.models.user import User
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.models.workflow import WorkflowDefinition

# Ensure sqlalchemy_continuum tables are registered in Base.metadata
configure_mappers()


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_company_slug(draw: st.DrawFn) -> str:
    """Generate a valid company slug matching ^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$.

    Returns:
        A URL-safe slug string between 3 and 100 characters.
    """
    start = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789")))
    end = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789")))
    middle_len = draw(st.integers(min_value=1, max_value=20))
    middle = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=middle_len,
            max_size=middle_len,
        )
    )
    return start + middle + end


def st_document_title() -> st.SearchStrategy[str]:
    """Generate a valid document title.

    Returns:
        Strategy producing non-empty title strings.
    """
    return st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=50,
    ).filter(lambda s: s.strip())


def st_tag() -> st.SearchStrategy[str]:
    """Generate a valid document tag.

    Returns:
        Strategy producing tag strings like SOP, Report, Protocol, etc.
    """
    return st.sampled_from(["SOP", "Report", "Protocol", "Form", "Manual", "WI"])


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



# ---------------------------------------------------------------------------
# Property 7: Tenant-scoped resource isolation
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 7: Tenant-scoped resource isolation
@settings(max_examples=20)
@given(
    num_companies=st.integers(min_value=2, max_value=4),
    docs_per_company=st.integers(min_value=1, max_value=5),
)
def test_tenant_scoped_resource_isolation(
    num_companies: int,
    docs_per_company: int,
) -> None:
    """For any set of resources distributed across N companies, querying
    resources from company X's tenant context SHALL return only resources
    where company_id = X, and the count of returned resources SHALL equal
    the count of resources belonging to company X.

    **Validates: Requirements 3.2, 3.3, 4.2, 4.4, 5.3, 6.2, 7.2**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)

        # Create N companies
        companies = []
        for i in range(1, num_companies + 1):
            company = _create_company(session, company_id=i, slug=f"company-{i}")
            companies.append(company)

        # Create documents distributed across companies
        doc_id = 1
        expected_counts: dict[int, int] = {}
        for company in companies:
            expected_counts[company.id] = docs_per_company
            for j in range(docs_per_company):
                doc = Document(
                    id=doc_id,
                    document_uuid=f"2024-{doc_id:05d}",
                    title=f"Doc {doc_id}",
                    folder_path="/docs",
                    document_type="SOP",
                    current_status="Draft",
                    created_by=user.id,
                    company_id=company.id,
                )
                session.add(doc)
                doc_id += 1

        session.commit()

        # For each company, query documents filtered by company_id
        for company in companies:
            results = (
                session.execute(
                    select(Document).where(Document.company_id == company.id)
                )
                .scalars()
                .all()
            )

            # Only company's own documents are returned
            assert len(results) == expected_counts[company.id], (
                f"Expected {expected_counts[company.id]} docs for company "
                f"{company.id}, got {len(results)}"
            )

            # Every returned document belongs to this company
            for doc in results:
                assert doc.company_id == company.id, (
                    f"Document {doc.id} has company_id={doc.company_id}, "
                    f"expected {company.id}"
                )
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 8: Auto-scoping on resource creation
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 8: Auto-scoping on resource creation
@settings(max_examples=20)
@given(
    slug=st_company_slug(),
    title=st_document_title(),
)
def test_auto_scoping_on_resource_creation(
    slug: str,
    title: str,
) -> None:
    """For any user with an active tenant context for company X, creating a
    tenant-scoped resource SHALL result in that resource having company_id = X.

    This test verifies that when a resource is created with a specific
    company_id (simulating the auto-scoping behavior of the service layer),
    the persisted record correctly stores that company_id.

    **Validates: Requirements 3.1, 4.1, 4.3, 5.1, 6.1, 7.1**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company = _create_company(session, company_id=1, slug=slug)
        session.commit()

        # Simulate auto-scoping: create resources with company_id from tenant context
        doc = Document(
            id=1,
            document_uuid="2024-00001",
            title=title,
            folder_path="/docs",
            document_type="SOP",
            current_status="Draft",
            created_by=user.id,
            company_id=company.id,
        )
        session.add(doc)

        template = Template(
            id=1,
            document_uuid="2024-00002",
            name=f"Template {title}",
            json_schema={"fields": []},
            status="Draft",
            created_by=user.id,
            company_id=company.id,
        )
        session.add(template)

        vfolder = VirtualFolder(
            id=1,
            name=f"Folder {title}",
            tag_filter={"tags": ["SOP"]},
            created_by=user.id,
            company_id=company.id,
        )
        session.add(vfolder)

        workflow = WorkflowDefinition(
            id=1,
            name=f"Workflow {title}",
            document_tag="SOP",
            bpmn_xml="<bpmn/>",
            is_active=True,
            created_by=user.id,
            company_id=company.id,
        )
        session.add(workflow)

        training_task = TrainingTask(
            id=1,
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            assigned_user_id=user.id,
            task_title=f"Train on {title}",
            company_id=company.id,
        )
        session.add(training_task)

        session.commit()

        # Verify all resources have the correct company_id
        persisted_doc = session.execute(
            select(Document).where(Document.id == 1)
        ).scalar_one()
        assert persisted_doc.company_id == company.id

        persisted_template = session.execute(
            select(Template).where(Template.id == 1)
        ).scalar_one()
        assert persisted_template.company_id == company.id

        persisted_vfolder = session.execute(
            select(VirtualFolder).where(VirtualFolder.id == 1)
        ).scalar_one()
        assert persisted_vfolder.company_id == company.id

        persisted_workflow = session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == 1)
        ).scalar_one()
        assert persisted_workflow.company_id == company.id

        persisted_task = session.execute(
            select(TrainingTask).where(TrainingTask.id == 1)
        ).scalar_one()
        assert persisted_task.company_id == company.id
    finally:
        session.close()
        engine.dispose()



# ---------------------------------------------------------------------------
# Property 9: Cross-tenant access returns forbidden
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 9: Cross-tenant access returns forbidden
@settings(max_examples=20)
@given(
    num_docs_a=st.integers(min_value=1, max_value=5),
    num_docs_b=st.integers(min_value=1, max_value=5),
)
def test_cross_tenant_access_returns_forbidden(
    num_docs_a: int,
    num_docs_b: int,
) -> None:
    """For any resource belonging to company A and any user whose active
    tenant context is company B (A != B), attempting to access that resource
    SHALL return forbidden.

    At the model level, this verifies that querying with company_id=B
    never returns resources belonging to company_id=A.

    **Validates: Requirements 3.4, 4.5, 5.4, 6.4**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company_a = _create_company(session, company_id=1, slug="company-a")
        company_b = _create_company(session, company_id=2, slug="company-b")

        # Create documents for company A
        for i in range(1, num_docs_a + 1):
            doc = Document(
                id=i,
                document_uuid=f"2024-{i:05d}",
                title=f"Doc A-{i}",
                folder_path="/docs",
                document_type="SOP",
                current_status="Draft",
                created_by=user.id,
                company_id=company_a.id,
            )
            session.add(doc)

        # Create documents for company B
        for i in range(1, num_docs_b + 1):
            doc_id = num_docs_a + i
            doc = Document(
                id=doc_id,
                document_uuid=f"2024-{doc_id:05d}",
                title=f"Doc B-{i}",
                folder_path="/docs",
                document_type="Report",
                current_status="Draft",
                created_by=user.id,
                company_id=company_b.id,
            )
            session.add(doc)

        session.commit()

        # User in company B's context tries to access company A's resources
        # The tenant filter (company_id = B) should never return A's docs
        results_for_b = (
            session.execute(
                select(Document).where(Document.company_id == company_b.id)
            )
            .scalars()
            .all()
        )

        # None of company A's documents should appear
        for doc in results_for_b:
            assert doc.company_id != company_a.id, (
                f"Cross-tenant leak: document {doc.id} belongs to company A "
                f"but was returned in company B's query"
            )

        # Specifically, trying to access a company A document by ID
        # with a company_id filter for B should return nothing
        company_a_doc_ids = list(range(1, num_docs_a + 1))
        for doc_id in company_a_doc_ids:
            result = session.execute(
                select(Document).where(
                    Document.id == doc_id,
                    Document.company_id == company_b.id,
                )
            ).scalar_one_or_none()
            assert result is None, (
                f"Cross-tenant access: document {doc_id} from company A "
                f"was accessible with company B's tenant filter"
            )
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 10: Cross-tenant template reference rejection
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 10: Cross-tenant template reference rejection
@settings(max_examples=20)
@given(
    template_name=st_document_title(),
)
def test_cross_tenant_template_reference_rejection(
    template_name: str,
) -> None:
    """For any template belonging to company A and any user in company B
    (A != B), attempting to create a report referencing that template SHALL
    be rejected.

    At the model level, this verifies that a template with company_id=A
    cannot be found when querying with company_id=B, which is the guard
    the service layer uses before allowing report creation.

    **Validates: Requirements 4.5**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company_a = _create_company(session, company_id=1, slug="company-a")
        company_b = _create_company(session, company_id=2, slug="company-b")

        # Create a template belonging to company A
        template = Template(
            id=1,
            document_uuid="2024-00001",
            name=template_name,
            json_schema={"fields": []},
            status="ReadOnly",
            created_by=user.id,
            company_id=company_a.id,
        )
        session.add(template)
        session.commit()

        # User in company B tries to reference this template
        # The service layer checks: template.company_id == tenant.company_id
        # Simulate this check by querying the template with company B's filter
        template_for_b = session.execute(
            select(Template).where(
                Template.id == template.id,
                Template.company_id == company_b.id,
            )
        ).scalar_one_or_none()

        # Template should NOT be accessible from company B's context
        assert template_for_b is None, (
            f"Cross-tenant template reference: template {template.id} from "
            f"company A was accessible with company B's tenant filter"
        )

        # Verify the template IS accessible from company A's context
        template_for_a = session.execute(
            select(Template).where(
                Template.id == template.id,
                Template.company_id == company_a.id,
            )
        ).scalar_one_or_none()
        assert template_for_a is not None, (
            "Template should be accessible from its own company's context"
        )
        assert template_for_a.company_id == company_a.id
    finally:
        session.close()
        engine.dispose()



# ---------------------------------------------------------------------------
# Property 11: Virtual folder tag filter respects tenant boundary
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 11: Virtual folder tag filter respects tenant boundary
@settings(max_examples=20)
@given(
    tag=st_tag(),
    num_docs_x=st.integers(min_value=1, max_value=5),
    num_docs_y=st.integers(min_value=1, max_value=5),
)
def test_virtual_folder_tag_filter_respects_tenant_boundary(
    tag: str,
    num_docs_x: int,
    num_docs_y: int,
) -> None:
    """For any virtual folder in company X with a tag filter, and documents
    with matching tags distributed across multiple companies, applying the
    filter SHALL return only documents where company_id = X.

    **Validates: Requirements 7.3**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company_x = _create_company(session, company_id=1, slug="company-x")
        company_y = _create_company(session, company_id=2, slug="company-y")

        # Create a virtual folder in company X with a tag filter
        vfolder = VirtualFolder(
            id=1,
            name=f"All {tag}s",
            tag_filter={"tags": [tag]},
            created_by=user.id,
            company_id=company_x.id,
        )
        session.add(vfolder)

        # Create documents with matching tags in BOTH companies
        doc_id = 1
        tag_id = 1
        for i in range(num_docs_x):
            doc = Document(
                id=doc_id,
                document_uuid=f"2024-{doc_id:05d}",
                title=f"Doc X-{i}",
                folder_path="/docs",
                document_type=tag,
                current_status="Draft",
                created_by=user.id,
                company_id=company_x.id,
            )
            session.add(doc)
            session.flush()
            doc_tag = DocumentTag(id=tag_id, document_id=doc.id, tag=tag)
            session.add(doc_tag)
            doc_id += 1
            tag_id += 1

        for i in range(num_docs_y):
            doc = Document(
                id=doc_id,
                document_uuid=f"2024-{doc_id:05d}",
                title=f"Doc Y-{i}",
                folder_path="/docs",
                document_type=tag,
                current_status="Draft",
                created_by=user.id,
                company_id=company_y.id,
            )
            session.add(doc)
            session.flush()
            doc_tag = DocumentTag(id=tag_id, document_id=doc.id, tag=tag)
            session.add(doc_tag)
            doc_id += 1
            tag_id += 1

        session.commit()

        # Apply the virtual folder's tag filter within company X's boundary
        # The service layer query: documents WHERE company_id = X AND tag IN filter_tags
        filter_tags = vfolder.tag_filter["tags"]
        results = (
            session.execute(
                select(Document)
                .join(DocumentTag, DocumentTag.document_id == Document.id)
                .where(
                    Document.company_id == company_x.id,
                    DocumentTag.tag.in_(filter_tags),
                )
            )
            .scalars()
            .all()
        )

        # Only company X's documents should be returned
        assert len(results) == num_docs_x, (
            f"Expected {num_docs_x} docs for company X, got {len(results)}"
        )
        for doc in results:
            assert doc.company_id == company_x.id, (
                f"Virtual folder returned doc {doc.id} from company "
                f"{doc.company_id}, expected company {company_x.id}"
            )
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 12: Workflow evaluation uses only tenant's workflows
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 12: Workflow evaluation uses only tenant's workflows
@settings(max_examples=20)
@given(
    tag=st_tag(),
    num_workflows_x=st.integers(min_value=1, max_value=3),
    num_workflows_y=st.integers(min_value=1, max_value=3),
)
def test_workflow_evaluation_uses_only_tenants_workflows(
    tag: str,
    num_workflows_x: int,
    num_workflows_y: int,
) -> None:
    """For any document in company X, when evaluating workflow transitions,
    the system SHALL consider only workflow definitions where company_id = X,
    even if workflows with matching document_tag exist in other companies.

    **Validates: Requirements 5.2**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company_x = _create_company(session, company_id=1, slug="company-x")
        company_y = _create_company(session, company_id=2, slug="company-y")

        # Create workflows with the same document_tag in both companies
        wf_id = 1
        for i in range(num_workflows_x):
            wf = WorkflowDefinition(
                id=wf_id,
                name=f"Workflow X-{i}",
                document_tag=f"{tag}-{i}" if i > 0 else tag,
                bpmn_xml=f"<bpmn>X-{i}</bpmn>",
                is_active=True,
                created_by=user.id,
                company_id=company_x.id,
            )
            session.add(wf)
            wf_id += 1

        for i in range(num_workflows_y):
            wf = WorkflowDefinition(
                id=wf_id,
                name=f"Workflow Y-{i}",
                document_tag=f"{tag}-y-{i}" if i > 0 else f"{tag}-y",
                bpmn_xml=f"<bpmn>Y-{i}</bpmn>",
                is_active=True,
                created_by=user.id,
                company_id=company_y.id,
            )
            session.add(wf)
            wf_id += 1

        session.commit()

        # When evaluating workflows for a document in company X,
        # only company X's workflows should be considered
        workflows_for_x = (
            session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.company_id == company_x.id,
                    WorkflowDefinition.is_active == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )

        # Should return only company X's workflows
        assert len(workflows_for_x) == num_workflows_x, (
            f"Expected {num_workflows_x} workflows for company X, "
            f"got {len(workflows_for_x)}"
        )
        for wf in workflows_for_x:
            assert wf.company_id == company_x.id, (
                f"Workflow {wf.id} has company_id={wf.company_id}, "
                f"expected {company_x.id}"
            )

        # Verify company Y's workflows are NOT included
        all_workflows = (
            session.execute(select(WorkflowDefinition)).scalars().all()
        )
        assert len(all_workflows) == num_workflows_x + num_workflows_y

        # Cross-check: querying with company Y's filter returns only Y's workflows
        workflows_for_y = (
            session.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.company_id == company_y.id,
                )
            )
            .scalars()
            .all()
        )
        assert len(workflows_for_y) == num_workflows_y
        for wf in workflows_for_y:
            assert wf.company_id == company_y.id
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 13: Training compliance evaluation is tenant-scoped
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 13: Training compliance evaluation is tenant-scoped
@settings(max_examples=20)
@given(
    num_records_x=st.integers(min_value=1, max_value=5),
    num_records_y=st.integers(min_value=1, max_value=5),
)
def test_training_compliance_evaluation_is_tenant_scoped(
    num_records_x: int,
    num_records_y: int,
) -> None:
    """For any document in company X, the training gate evaluation SHALL
    consider only training records where company_id = X, ignoring training
    records for the same SOP in other companies.

    **Validates: Requirements 6.3**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company_x = _create_company(session, company_id=1, slug="company-x")
        company_y = _create_company(session, company_id=2, slug="company-y")

        # Both companies have training records for the SAME SOP document UUID
        shared_sop_uuid = "2024-00001"
        sop_version = "2.0"

        record_id = 1
        for i in range(num_records_x):
            record = TrainingRecord(
                id=record_id,
                user_id=user.id,
                sop_document_uuid=shared_sop_uuid,
                sop_version=sop_version,
                is_valid=True,
                company_id=company_x.id,
            )
            session.add(record)
            record_id += 1

        for i in range(num_records_y):
            record = TrainingRecord(
                id=record_id,
                user_id=user.id,
                sop_document_uuid=shared_sop_uuid,
                sop_version=sop_version,
                is_valid=True,
                company_id=company_y.id,
            )
            session.add(record)
            record_id += 1

        session.commit()

        # Training gate evaluation for company X:
        # Query training records WHERE company_id = X AND sop_document_uuid = ...
        records_for_x = (
            session.execute(
                select(TrainingRecord).where(
                    TrainingRecord.company_id == company_x.id,
                    TrainingRecord.sop_document_uuid == shared_sop_uuid,
                    TrainingRecord.is_valid == True,  # noqa: E712
                )
            )
            .scalars()
            .all()
        )

        # Only company X's training records should be considered
        assert len(records_for_x) == num_records_x, (
            f"Expected {num_records_x} training records for company X, "
            f"got {len(records_for_x)}"
        )
        for record in records_for_x:
            assert record.company_id == company_x.id, (
                f"Training record {record.id} has company_id={record.company_id}, "
                f"expected {company_x.id}"
            )

        # Verify company Y's records are NOT included in X's evaluation
        records_for_y = (
            session.execute(
                select(TrainingRecord).where(
                    TrainingRecord.company_id == company_y.id,
                    TrainingRecord.sop_document_uuid == shared_sop_uuid,
                )
            )
            .scalars()
            .all()
        )
        assert len(records_for_y) == num_records_y

        # Total records should be the sum of both companies
        all_records = (
            session.execute(
                select(TrainingRecord).where(
                    TrainingRecord.sop_document_uuid == shared_sop_uuid,
                )
            )
            .scalars()
            .all()
        )
        assert len(all_records) == num_records_x + num_records_y
    finally:
        session.close()
        engine.dispose()
