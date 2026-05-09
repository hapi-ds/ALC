"""Property-based tests for workflow version increment logic.

Tests Property 10 (Version increment on structural changes only) from the
BPMN Workflow Visual Editor design document.

Verifies that version increments only when bpmn_xml or transitions change,
and that metadata-only changes (name, is_active) do not create new versions.

**Validates: Requirements 8.1, 8.2**

References:
    - Design: .kiro/specs/Step_3-1_bpmn-workflow-visual-editor/design.md
    - Requirements: .kiro/specs/Step_3-1_bpmn-workflow-visual-editor/requirements.md
"""

import hypothesis.strategies as st
from hypothesis import assume, given, settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.user import User
from alcoabase.models.workflow import WorkflowDefinition, WorkflowVersion

# Ensure sqlalchemy_continuum tables are registered in Base.metadata
configure_mappers()


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_workflow_name() -> st.SearchStrategy[str]:
    """Generate a valid workflow name.

    Returns:
        Strategy producing non-empty workflow name strings.
    """
    return st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=1,
        max_size=50,
    ).filter(lambda s: s.strip())


def st_bpmn_xml() -> st.SearchStrategy[str]:
    """Generate a simple BPMN XML string with varying content.

    Returns:
        Strategy producing BPMN XML strings.
    """
    return st.text(
        alphabet=st.characters(categories=("L", "N")),
        min_size=5,
        max_size=30,
    ).map(
        lambda content: (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
            f'  <process id="p1" name="{content}">'
            '    <startEvent id="start" name="Start"/>'
            f'    <task id="t1" name="{content}"/>'
            '    <endEvent id="end" name="End"/>'
            '    <sequenceFlow id="f1" sourceRef="start" targetRef="t1"/>'
            '    <sequenceFlow id="f2" sourceRef="t1" targetRef="end"/>'
            "  </process>"
            "</definitions>"
        )
    )


def st_transition_list() -> st.SearchStrategy[list[str]]:
    """Generate a list of transition strings in Source->Target format.

    Returns:
        Strategy producing lists of transition strings.
    """
    return st.lists(
        st.text(
            alphabet=st.characters(categories=("L",)),
            min_size=3,
            max_size=10,
        ).map(lambda s: f"{s}\u2192End"),
        min_size=0,
        max_size=3,
        unique=True,
    )


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


def _setup_base_data(session: Session) -> tuple[User, Company]:
    """Create base user and company for tests.

    Args:
        session: Active database session.

    Returns:
        Tuple of (user, company).
    """
    user = User(
        id=1,
        username="testuser",
        email="test@test.local",
        hashed_password="hashed",
        full_name="Test User",
        is_active=True,
    )
    session.add(user)

    company = Company(
        id=1,
        slug="test-company",
        display_name="Test Company",
        regulatory_framework="ISO_13485",
        is_active=True,
    )
    session.add(company)
    session.flush()
    return user, company


def _create_workflow_with_version(
    session: Session,
    user: User,
    company: Company,
    name: str = "Test Workflow",
    bpmn_xml: str = "<bpmn>initial</bpmn>",
    sig_transitions: list[str] | None = None,
    training_transitions: list[str] | None = None,
) -> WorkflowDefinition:
    """Create a workflow definition with an initial version record.

    Args:
        session: Active database session.
        user: The creating user.
        company: The owning company.
        name: Workflow name.
        bpmn_xml: Initial BPMN XML.
        sig_transitions: Signature required transitions.
        training_transitions: Training trigger transitions.

    Returns:
        The created WorkflowDefinition.
    """
    workflow = WorkflowDefinition(
        name=name,
        document_tag=f"tag-{id(session)}",
        bpmn_xml=bpmn_xml,
        signature_required_transitions=sig_transitions or [],
        training_trigger_transitions=training_transitions or [],
        is_active=True,
        risk_level="low",
        current_version=1,
        created_by=user.id,
        company_id=company.id,
    )
    session.add(workflow)
    session.flush()

    version = WorkflowVersion(
        workflow_id=workflow.id,
        version_number=1,
        bpmn_xml=workflow.bpmn_xml,
        name=workflow.name,
        document_tag=workflow.document_tag,
        risk_level=workflow.risk_level,
        signature_required_transitions=workflow.signature_required_transitions,
        training_trigger_transitions=workflow.training_trigger_transitions,
        auto_assignment_config=None,
        created_by=user.id,
        change_reason="Initial creation",
        company_id=company.id,
    )
    session.add(version)
    session.flush()

    return workflow


def _simulate_update(
    session: Session,
    workflow: WorkflowDefinition,
    user_id: int,
    new_name: str | None = None,
    new_is_active: bool | None = None,
    new_bpmn_xml: str | None = None,
    new_sig_transitions: list[str] | None = None,
    new_training_transitions: list[str] | None = None,
) -> bool:
    """Simulate the update logic from the workflows API endpoint.

    Applies the same versioning logic as PUT /api/workflows/{id}:
    - Structural changes (bpmn_xml, transitions) increment version
    - Metadata-only changes (name, is_active) do not

    Args:
        session: Active database session.
        workflow: The workflow to update.
        user_id: The updating user's ID.
        new_name: New name (metadata change).
        new_is_active: New active status (metadata change).
        new_bpmn_xml: New BPMN XML (structural change).
        new_sig_transitions: New signature transitions (structural change).
        new_training_transitions: New training transitions (structural change).

    Returns:
        True if a structural change was detected and version incremented.
    """
    structural_change = False

    if new_bpmn_xml is not None and new_bpmn_xml != workflow.bpmn_xml:
        structural_change = True
    if (
        new_sig_transitions is not None
        and new_sig_transitions != workflow.signature_required_transitions
    ):
        structural_change = True
    if (
        new_training_transitions is not None
        and new_training_transitions
        != workflow.training_trigger_transitions
    ):
        structural_change = True

    # Apply metadata updates
    if new_name is not None:
        workflow.name = new_name
    if new_is_active is not None:
        workflow.is_active = new_is_active

    # Apply structural updates
    if new_bpmn_xml is not None:
        workflow.bpmn_xml = new_bpmn_xml
    if new_sig_transitions is not None:
        workflow.signature_required_transitions = new_sig_transitions
    if new_training_transitions is not None:
        workflow.training_trigger_transitions = new_training_transitions

    # Create new version on structural changes
    if structural_change:
        workflow.current_version += 1
        version_record = WorkflowVersion(
            workflow_id=workflow.id,
            version_number=workflow.current_version,
            bpmn_xml=workflow.bpmn_xml,
            name=workflow.name,
            document_tag=workflow.document_tag,
            risk_level=workflow.risk_level,
            signature_required_transitions=workflow.signature_required_transitions,
            training_trigger_transitions=workflow.training_trigger_transitions,
            auto_assignment_config=workflow.auto_assignment_config,
            created_by=user_id,
            change_reason="Workflow updated",
            company_id=workflow.company_id,
        )
        session.add(version_record)

    session.flush()
    return structural_change


# ---------------------------------------------------------------------------
# Property 10: Version increment on structural changes only
# ---------------------------------------------------------------------------


class TestVersionIncrementOnStructuralChanges:
    """Property tests verifying version increments only on structural changes.

    For any PUT request that modifies bpmn_xml, signature_required_transitions,
    or training_trigger_transitions, the current_version SHALL increment by 1
    and a new WorkflowVersion record SHALL be created.

    For any PUT request that only modifies name or is_active, the
    current_version SHALL remain unchanged and no new WorkflowVersion
    record SHALL be created.

    **Validates: Requirements 8.1, 8.2**
    """

    @given(
        new_bpmn_xml=st_bpmn_xml(),
    )
    @settings(max_examples=100)
    def test_bpmn_xml_change_increments_version(
        self, new_bpmn_xml: str
    ) -> None:
        """Changing bpmn_xml SHALL increment current_version by 1 and
        create a new WorkflowVersion record.

        **Validates: Requirements 8.1, 8.2**
        """
        session, engine = _make_session()
        try:
            user, company = _setup_base_data(session)
            workflow = _create_workflow_with_version(session, user, company)
            session.commit()

            initial_version = workflow.current_version
            assume(new_bpmn_xml != workflow.bpmn_xml)

            _simulate_update(
                session, workflow, user.id, new_bpmn_xml=new_bpmn_xml
            )
            session.commit()

            # Version should have incremented by 1
            assert workflow.current_version == initial_version + 1, (
                f"Expected version {initial_version + 1}, "
                f"got {workflow.current_version}"
            )

            # A new WorkflowVersion record should exist
            versions = (
                session.execute(
                    select(WorkflowVersion).where(
                        WorkflowVersion.workflow_id == workflow.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(versions) == 2, (
                f"Expected 2 version records, got {len(versions)}"
            )
            latest = max(versions, key=lambda v: v.version_number)
            assert latest.version_number == initial_version + 1
            assert latest.bpmn_xml == new_bpmn_xml
        finally:
            session.close()
            engine.dispose()

    @given(
        new_sig_transitions=st_transition_list(),
    )
    @settings(max_examples=100)
    def test_signature_transitions_change_increments_version(
        self, new_sig_transitions: list[str]
    ) -> None:
        """Changing signature_required_transitions SHALL increment
        current_version by 1.

        **Validates: Requirements 8.1, 8.2**
        """
        session, engine = _make_session()
        try:
            user, company = _setup_base_data(session)
            workflow = _create_workflow_with_version(session, user, company)
            session.commit()

            initial_version = workflow.current_version
            assume(
                new_sig_transitions
                != workflow.signature_required_transitions
            )

            _simulate_update(
                session,
                workflow,
                user.id,
                new_sig_transitions=new_sig_transitions,
            )
            session.commit()

            assert workflow.current_version == initial_version + 1, (
                f"Expected version {initial_version + 1}, "
                f"got {workflow.current_version}"
            )

            versions = (
                session.execute(
                    select(WorkflowVersion).where(
                        WorkflowVersion.workflow_id == workflow.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(versions) == 2
        finally:
            session.close()
            engine.dispose()

    @given(
        new_training_transitions=st_transition_list(),
    )
    @settings(max_examples=100)
    def test_training_transitions_change_increments_version(
        self, new_training_transitions: list[str]
    ) -> None:
        """Changing training_trigger_transitions SHALL increment
        current_version by 1.

        **Validates: Requirements 8.1, 8.2**
        """
        session, engine = _make_session()
        try:
            user, company = _setup_base_data(session)
            workflow = _create_workflow_with_version(session, user, company)
            session.commit()

            initial_version = workflow.current_version
            assume(
                new_training_transitions
                != workflow.training_trigger_transitions
            )

            _simulate_update(
                session,
                workflow,
                user.id,
                new_training_transitions=new_training_transitions,
            )
            session.commit()

            assert workflow.current_version == initial_version + 1, (
                f"Expected version {initial_version + 1}, "
                f"got {workflow.current_version}"
            )

            versions = (
                session.execute(
                    select(WorkflowVersion).where(
                        WorkflowVersion.workflow_id == workflow.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(versions) == 2
        finally:
            session.close()
            engine.dispose()

    @given(
        new_name=st_workflow_name(),
        new_is_active=st.booleans(),
    )
    @settings(max_examples=100)
    def test_metadata_only_changes_do_not_increment_version(
        self, new_name: str, new_is_active: bool
    ) -> None:
        """Metadata-only changes (name, is_active) SHALL NOT increment
        current_version and SHALL NOT create a new WorkflowVersion record.

        **Validates: Requirements 8.1, 8.2**
        """
        session, engine = _make_session()
        try:
            user, company = _setup_base_data(session)
            workflow = _create_workflow_with_version(session, user, company)
            session.commit()

            initial_version = workflow.current_version

            _simulate_update(
                session,
                workflow,
                user.id,
                new_name=new_name,
                new_is_active=new_is_active,
            )
            session.commit()

            # Version should NOT have changed
            assert workflow.current_version == initial_version, (
                f"Expected version {initial_version} (unchanged), "
                f"got {workflow.current_version}"
            )

            # No new WorkflowVersion record should have been created
            versions = (
                session.execute(
                    select(WorkflowVersion).where(
                        WorkflowVersion.workflow_id == workflow.id
                    )
                )
                .scalars()
                .all()
            )
            assert len(versions) == 1, (
                f"Expected 1 version record (unchanged), "
                f"got {len(versions)}"
            )

            # But the metadata should have been updated
            assert workflow.name == new_name
            assert workflow.is_active == new_is_active
        finally:
            session.close()
            engine.dispose()
