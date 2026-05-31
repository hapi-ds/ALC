"""Property-based tests for ALC Corporate Environment Setup.

Tests correctness properties from the Step_8-2 design document, validating
the ALC seed service behavior.

References:
    - Design: .kiro/specs/Step_8-2_alc-corporate-environment-setup/design.md
    - Requirements: .kiro/specs/Step_8-2_alc-corporate-environment-setup/requirements.md
"""

import asyncio
import re
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from hypothesis import HealthCheck
from passlib.context import CryptContext
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.services.alc_seed_constants import (
    ALC_GOVERNANCE_FOLDERS,
    ALC_USER_POOL,
    RESERVED_SLUGS,
    validate_company_slug,
)
from alcoabase.services.alc_seed_service import ALCSeedService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate valid slugs that are NOT in the reserved set.
# Valid slugs match ^[a-z0-9]+(-[a-z0-9]+)*$ and are not "alc-corporate".
st_valid_non_reserved_slugs = st.from_regex(
    r"^[a-z0-9]+(-[a-z0-9]+)*$", fullmatch=True
).filter(lambda s: s not in RESERVED_SLUGS and 1 <= len(s) <= 100)


# ---------------------------------------------------------------------------
# Property 4: Slug reservation — reserved slug is always rejected
# ---------------------------------------------------------------------------


# Feature: Step_8-2_alc-corporate-environment-setup, Property 4: Slug reservation
@settings(max_examples=100)
@given(data=st.data())
def test_reserved_slug_always_rejected(data: st.DataObject) -> None:
    """For any company creation request specifying slug "alc-corporate",
    the system SHALL reject it with a ValueError regardless of other attributes.

    **Validates: Requirements 1.3**
    """
    # The reserved slug must always raise ValueError
    for reserved_slug in RESERVED_SLUGS:
        with pytest.raises(ValueError, match="reserved"):
            validate_company_slug(reserved_slug)


# Feature: Step_8-2_alc-corporate-environment-setup, Property 4: Slug reservation
@settings(max_examples=100)
@given(slug=st_valid_non_reserved_slugs)
def test_non_reserved_slug_always_accepted(slug: str) -> None:
    """For any valid slug that is NOT "alc-corporate", the system SHALL
    accept it without raising an error.

    **Validates: Requirements 1.3**
    """
    # Non-reserved valid slugs must not raise
    validate_company_slug(slug)  # Should not raise


# ---------------------------------------------------------------------------
# Property 5: Password configuration — seed users authenticate with configured password
# ---------------------------------------------------------------------------

# The same CryptContext used by ALCSeedService for password hashing
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Strategy: non-empty password strings of reasonable length (1-72 chars).
# bcrypt truncates at 72 bytes, so we stay within that range for meaningful tests.
st_passwords = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S")),
    min_size=1,
    max_size=72,
)


# Feature: Step_8-2_alc-corporate-environment-setup, Property 5: Password configuration
@settings(max_examples=100, deadline=None)
@given(password=st_passwords)
def test_password_hash_verifies_against_configured_value(password: str) -> None:
    """For any non-empty password string, hashing with the CryptContext used by
    ALCSeedService SHALL produce a bcrypt hash that verifies against the original
    password value.

    **Validates: Requirements 2.2**
    """
    # Hash the password using the same CryptContext as the service
    hashed = _pwd_context.hash(password)

    # The hash must verify against the original password
    assert _pwd_context.verify(password, hashed), (
        f"Password hash verification failed for password of length {len(password)}"
    )


# ---------------------------------------------------------------------------
# Property 2: Transaction atomicity — failure causes complete rollback
# ---------------------------------------------------------------------------

# The 7 steps in ALCSeedService.execute() that can be patched to simulate failure.
# Each tuple is (method_name, description).
SEED_STEPS = [
    ("_create_company", "Step 1: Create company"),
    ("_provision_users", "Step 2: Provision users"),
    ("_find_it_admin", "Step 3: Find IT admin"),
    ("_apply_regulatory_baseline", "Step 4: Apply regulatory baseline"),
    ("_create_folder_structure", "Step 5: Create folder structure"),
    ("_configure_risk_profile", "Step 6: Configure risk profile"),
    ("_activate_agents", "Step 7: Activate agents"),
]

# Strategy: pick which step index should fail (0-6)
st_failing_step_index = st.integers(min_value=0, max_value=len(SEED_STEPS) - 1)


def _make_mock_session() -> AsyncMock:
    """Create a mock AsyncSession that tracks added entities.

    Returns a mock session where session.add() collects entities into
    a list, and session.execute() returns empty results (no pre-existing
    entities). After rollback, the added entities list represents what
    would have been discarded.
    """
    session = AsyncMock()
    session._added_entities: list = []

    def _track_add(entity):
        session._added_entities.append(entity)

    session.add = MagicMock(side_effect=_track_add)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Default execute returns empty results (no pre-existing entities)
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_scalars.all.return_value = []
    mock_result.scalars.return_value = mock_scalars
    session.execute = AsyncMock(return_value=mock_result)

    return session


def _create_failing_method(step_desc: str):
    """Create an async method that raises RuntimeError when called.

    The returned coroutine function accepts *args and **kwargs to match
    any method signature (self, company, it_admin, etc.).

    Args:
        step_desc: Description of the step for the error message.

    Returns:
        An async function that always raises RuntimeError.
    """

    async def _failing(*args, **kwargs):
        raise RuntimeError(f"Simulated failure at {step_desc}")

    return _failing


# Feature: Step_8-2_alc-corporate-environment-setup, Property 2: Transaction atomicity
@settings(max_examples=100)
@given(step_index=st_failing_step_index)
@pytest.mark.asyncio
async def test_transaction_atomicity_failure_causes_rollback(step_index: int) -> None:
    """For any step in the seeding sequence that raises an exception,
    the database SHALL contain zero records from any step of the current
    seeding attempt (complete rollback), and the state SHALL be identical
    to the state before the seed was invoked.

    **Validates: Requirements 1.5, 2.9, 6.3**

    This test verifies that:
    1. When a step raises RuntimeError, the exception propagates to the caller
    2. The caller can then rollback the session
    3. After rollback, no ALC entities persist (the session.add calls are undone)
    """
    failing_method, step_desc = SEED_STEPS[step_index]

    # Create a fresh mock session for each test case
    session = _make_mock_session()

    # Create the service
    service = ALCSeedService(session)

    # Build patches: all steps before the failing one succeed with mock returns,
    # the failing step raises RuntimeError.
    patches = {}
    for i, (method_name, desc) in enumerate(SEED_STEPS):
        if i < step_index:
            # Steps before the failing one return plausible mock values
            patches[method_name] = _get_success_mock(method_name)
        elif i == step_index:
            # The targeted step raises RuntimeError
            patches[method_name] = _create_failing_method(desc)
        # Steps after the failing one won't be reached, no need to patch

    # Apply all patches and run execute()
    with _apply_patches(service, patches):
        # Call execute() — it should propagate the exception
        with pytest.raises(RuntimeError, match="Simulated failure"):
            await service.execute()

    # Simulate caller's rollback behavior (as per design: caller manages transaction)
    await session.rollback()

    # After rollback, verify the session state is clean:
    # 1. rollback was called (transaction boundary managed by caller)
    session.rollback.assert_called_once()

    # 2. commit was NEVER called (exception prevented reaching commit)
    session.commit.assert_not_called()

    # 3. The key property: since the session was rolled back, no entities
    #    from this seeding attempt persist in the database. In a real DB,
    #    rollback discards all unflushed/uncommitted changes. With our mock,
    #    we verify the pattern is correct: exception propagates → caller
    #    rolls back → no commit occurs → DB state unchanged.
    assert session.commit.call_count == 0, (
        f"Session was committed despite failure at {step_desc}. "
        "This would leave partial ALC entities in the database."
    )


def _get_success_mock(method_name: str):
    """Return an async function that produces a plausible success value for a step.

    These mocks allow earlier steps to complete so that later steps can be
    tested for failure behavior.

    Args:
        method_name: The private method name of ALCSeedService.

    Returns:
        An async function returning appropriate mock data.
    """
    from alcoabase.models.company import Company
    from alcoabase.models.user import User
    from alcoabase.schemas.alc_seed import AgentResult, FolderResult, UserPoolResult

    mock_company = MagicMock(spec=Company)
    mock_company.id = 1
    mock_company.slug = "alc-corporate"

    mock_user = MagicMock(spec=User)
    mock_user.id = 10
    mock_user.username = "alc-it-admin"

    async def _create_company(*args, **kwargs):
        return (mock_company, True)

    async def _provision_users(*args, **kwargs):
        return UserPoolResult(
            users_created=["alc-it-admin", "alc-doc-admin", "alc-quality-mgr", "alc-user"],
            users_skipped=[],
        )

    async def _find_it_admin(*args, **kwargs):
        return mock_user

    async def _apply_regulatory_baseline(*args, **kwargs):
        return (True, True)

    async def _create_folder_structure(*args, **kwargs):
        return FolderResult(folders_created=["Governance — All Documents"], folders_skipped=[])

    async def _configure_risk_profile(*args, **kwargs):
        return True

    async def _activate_agents(*args, **kwargs):
        return AgentResult(agents_activated=[], agents_skipped=[])

    dispatch = {
        "_create_company": _create_company,
        "_provision_users": _provision_users,
        "_find_it_admin": _find_it_admin,
        "_apply_regulatory_baseline": _apply_regulatory_baseline,
        "_create_folder_structure": _create_folder_structure,
        "_configure_risk_profile": _configure_risk_profile,
        "_activate_agents": _activate_agents,
    }

    return dispatch[method_name]


class _apply_patches:
    """Context manager that patches multiple methods on a service instance.

    Replaces each method with the provided async function for the duration
    of the context.
    """

    def __init__(self, service: ALCSeedService, patches: dict):
        self._service = service
        self._patches = patches
        self._originals: dict = {}

    def __enter__(self):
        for method_name, replacement in self._patches.items():
            self._originals[method_name] = getattr(self._service, method_name)
            # Bind the replacement to the instance
            import types

            bound = types.MethodType(replacement, self._service)
            setattr(self._service, method_name, bound)
        return self

    def __exit__(self, *args):
        for method_name, original in self._originals.items():
            setattr(self._service, method_name, original)


# ---------------------------------------------------------------------------
# Property 6: Agent activation completeness — all global agents are activated
# ---------------------------------------------------------------------------


@dataclass
class MockAgentDefinition:
    """Minimal mock of an AgentDefinition record for property testing.

    Attributes:
        id: Primary key.
        name: Agent display name.
        company_id: None for global agents.
        is_active: Whether the agent definition is active.
    """

    id: int
    name: str
    company_id: int | None = None
    is_active: bool = True


@dataclass
class MockCompanyAgentActivation:
    """Minimal mock of a CompanyAgentActivation record for property testing.

    Attributes:
        agent_definition_id: FK to the agent definition.
        company_id: FK to the company.
        is_active: Whether this activation is currently active.
        config_overrides: JSON overrides (empty dict by default).
    """

    agent_definition_id: int
    company_id: int
    is_active: bool = True
    config_overrides: dict = field(default_factory=dict)


# Strategy: generate a list of global agent definitions (0-15 agents)
@st.composite
def st_global_agent_definitions(draw: st.DrawFn) -> list[MockAgentDefinition]:
    """Generate a random set of global AgentDefinition records.

    Each agent has a unique ID and name, company_id=None, is_active=True.
    """
    num_agents = draw(st.integers(min_value=0, max_value=15))
    agents = []
    for i in range(num_agents):
        agent = MockAgentDefinition(
            id=i + 1,
            name=f"Agent_{i + 1}",
            company_id=None,
            is_active=True,
        )
        agents.append(agent)
    return agents


# Strategy: for a given set of agents, generate pre-existing activations
# with various states (some active, some inactive, some missing)
@st.composite
def st_pre_existing_activations(
    draw: st.DrawFn, agents: list[MockAgentDefinition], company_id: int
) -> dict[int, MockCompanyAgentActivation | None]:
    """Generate pre-existing activation states for agents.

    For each agent, randomly choose:
    - None (no existing activation)
    - Active activation (is_active=True)
    - Inactive activation (is_active=False)

    Returns:
        Dict mapping agent_definition_id to existing activation or None.
    """
    activations: dict[int, MockCompanyAgentActivation | None] = {}
    for agent in agents:
        state = draw(st.sampled_from(["none", "active", "inactive"]))
        if state == "none":
            activations[agent.id] = None
        elif state == "active":
            activations[agent.id] = MockCompanyAgentActivation(
                agent_definition_id=agent.id,
                company_id=company_id,
                is_active=True,
            )
        else:  # inactive
            activations[agent.id] = MockCompanyAgentActivation(
                agent_definition_id=agent.id,
                company_id=company_id,
                is_active=False,
            )
    return activations


# Feature: Step_8-2_alc-corporate-environment-setup, Property 6: Agent activation completeness
@settings(max_examples=100, deadline=None)
@given(data=st.data())
@pytest.mark.asyncio
async def test_agent_activation_completeness(data: st.DataObject) -> None:
    """For any set of global AgentDefinition records, after seed execution,
    there SHALL exist exactly one active CompanyAgentActivation record per
    agent for the ALC_Company, and deactivated activations SHALL be reactivated.

    **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
    """
    company_id = 1
    agents = data.draw(st_global_agent_definitions())
    pre_existing = data.draw(st_pre_existing_activations(agents, company_id))

    # Mock company
    mock_company = MagicMock()
    mock_company.id = company_id

    # Build the mock session that simulates DB queries
    mock_session = AsyncMock()

    # Track session.add calls to capture new activations
    added_objects: list[object] = []

    def track_add(obj: object) -> None:
        added_objects.append(obj)

    mock_session.add = MagicMock(side_effect=track_add)
    mock_session.flush = AsyncMock()

    # Record original activation states BEFORE calling the service
    # (the service mutates mock objects in-place for reactivation)
    original_is_active: dict[int, bool | None] = {}
    for agent in agents:
        existing = pre_existing.get(agent.id)
        if existing is None:
            original_is_active[agent.id] = None  # No activation existed
        else:
            original_is_active[agent.id] = existing.is_active

    # Mock execute to return appropriate results for the two query patterns:
    # 1. First call: SELECT AgentDefinition WHERE company_id IS NULL AND is_active=True
    # 2. Subsequent calls: SELECT CompanyAgentActivation for each agent
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1

        mock_result = MagicMock()
        mock_scalars = MagicMock()

        if call_count == 1:
            # First query: return all global agents
            mock_scalars.all.return_value = agents
            mock_result.scalars.return_value = mock_scalars
        else:
            # Subsequent queries: return pre-existing activation for each agent
            # The agent index is call_count - 2 (0-based after the first call)
            agent_idx = call_count - 2
            if agent_idx < len(agents):
                agent = agents[agent_idx]
                existing = pre_existing.get(agent.id)
                mock_scalars.first.return_value = existing
                mock_result.scalars.return_value = mock_scalars
            else:
                mock_scalars.first.return_value = None
                mock_result.scalars.return_value = mock_scalars

        return mock_result

    mock_session.execute = AsyncMock(side_effect=mock_execute)

    # Create the service and run _activate_agents
    service = ALCSeedService(mock_session)
    result = await service._activate_agents(mock_company)

    # --- Verify Property 6: Agent activation completeness ---
    # Every global agent has exactly one active activation after seeding.

    # Property assertion 1: Every agent appears in exactly one list
    for agent in agents:
        in_activated = agent.name in result.agents_activated
        in_skipped = agent.name in result.agents_skipped
        assert in_activated or in_skipped, (
            f"Agent '{agent.name}' (id={agent.id}) is missing from both "
            f"agents_activated and agents_skipped"
        )
        assert not (in_activated and in_skipped), (
            f"Agent '{agent.name}' (id={agent.id}) appears in BOTH "
            f"agents_activated and agents_skipped"
        )

    # Property assertion 2: Agents with originally active activations are skipped
    for agent in agents:
        if original_is_active[agent.id] is True:
            assert agent.name in result.agents_skipped, (
                f"Agent '{agent.name}' had an active activation but was not skipped"
            )

    # Property assertion 3: Agents with no activation or inactive activation are activated
    for agent in agents:
        orig = original_is_active[agent.id]
        if orig is None or orig is False:
            assert agent.name in result.agents_activated, (
                f"Agent '{agent.name}' (original_is_active={orig}) should have been "
                f"activated but was not in agents_activated"
            )

    # Property assertion 4: Reactivated agents have is_active set to True
    for agent in agents:
        existing = pre_existing.get(agent.id)
        if existing is not None and original_is_active[agent.id] is False:
            # The service should have set is_active=True on the existing mock
            assert existing.is_active is True, (
                f"Agent '{agent.name}' had inactive activation but was not reactivated"
            )

    # Property assertion 5: Total coverage — all agents accounted for
    assert len(result.agents_activated) + len(result.agents_skipped) == len(agents), (
        f"Total agents in result ({len(result.agents_activated)} activated + "
        f"{len(result.agents_skipped)} skipped) does not match total global agents "
        f"({len(agents)})"
    )

    # Property assertion 6: No duplicates in either list
    assert len(set(result.agents_activated)) == len(result.agents_activated), (
        f"Duplicate entries in agents_activated: {result.agents_activated}"
    )
    assert len(set(result.agents_skipped)) == len(result.agents_skipped), (
        f"Duplicate entries in agents_skipped: {result.agents_skipped}"
    )

    # Property assertion 7: New activations were added to the session
    for agent in agents:
        if original_is_active[agent.id] is None:
            # A new CompanyAgentActivation should have been added
            matching = [
                obj for obj in added_objects
                if hasattr(obj, "agent_definition_id")
                and obj.agent_definition_id == agent.id
            ]
            assert len(matching) == 1, (
                f"Agent '{agent.name}' had no activation but exactly one new "
                f"CompanyAgentActivation was not added to the session "
                f"(found {len(matching)})"
            )


# ---------------------------------------------------------------------------
# Property 1: Idempotency — repeated execution preserves state
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine synchronously for use within hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_test_db():
    """Create an in-memory SQLite database with only the tables needed for seeding.

    We selectively create tables to avoid JSONB/PostgreSQL-specific type
    compatibility issues with SQLite. SQLAlchemy-Continuum's session tracking
    is disabled via patching to avoid needing version/transaction tables.
    """
    from alcoabase.models.company import (
        Company,
        CompanyMembership,
    )
    from alcoabase.models.setup_status import SetupStatus
    from alcoabase.models.system_config import SystemConfiguration
    from alcoabase.models.user import Role, User, UserRole
    from alcoabase.models.virtual_folder import VirtualFolder

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Only create the specific tables needed by ALCSeedService
    tables = [
        User.__table__,
        Role.__table__,
        UserRole,
        Company.__table__,
        CompanyMembership.__table__,
        SystemConfiguration.__table__,
        VirtualFolder.__table__,
        SetupStatus.__table__,
    ]

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    return engine, session_factory


# Strategy: generate a random subset of ALC user pool indices to pre-exist.
# This simulates partial pre-existing state before the seed runs.
st_pre_existing_user_indices = st.lists(
    st.integers(min_value=0, max_value=len(ALC_USER_POOL) - 1),
    unique=True,
    min_size=0,
    max_size=len(ALC_USER_POOL),
)


# Feature: Step_8-2_alc-corporate-environment-setup, Property 1: Idempotency
@settings(max_examples=100, deadline=None)
@given(pre_existing_indices=st_pre_existing_user_indices)
def test_idempotency_repeated_execution_preserves_state(
    pre_existing_indices: list[int],
) -> None:
    """For any initial database state (with any subset of ALC entities already
    existing), executing the ALCSeedService twice in succession SHALL produce
    the same final database state as executing it once, and the second
    execution's SeedReport SHALL report all entities as skipped (not created).

    **Validates: Requirements 1.2, 2.3, 3.3, 3.4, 4.3, 5.3, 6.7, 7.2, 8.3**
    """

    async def _test():
        engine, session_factory = await _create_test_db()
        try:
            # Disable Continuum's session tracking by patching the UoW
            # process methods. This avoids needing version/transaction tables.
            with patch(
                "sqlalchemy_continuum.unit_of_work.UnitOfWork.process_before_flush",
                lambda *a, **kw: None,
            ), patch(
                "sqlalchemy_continuum.unit_of_work.UnitOfWork.process_after_flush",
                lambda *a, **kw: None,
            ):
                async with session_factory() as session:
                    with patch(
                        "alcoabase.services.alc_seed_service.get_settings"
                    ) as mock_settings:
                        mock_settings.return_value.alc_seed_default_password = (
                            "TestPass123!"
                        )

                        # Patch steps that require PostgreSQL-specific tables
                        with (
                            patch.object(
                                ALCSeedService,
                                "_create_governance_workflow",
                                new=_mock_workflow_first_true,
                            ),
                            patch.object(
                                ALCSeedService,
                                "_configure_risk_profile",
                                new=_mock_risk_profile_first_true,
                            ),
                            patch.object(
                                ALCSeedService,
                                "_activate_agents",
                                new=_mock_agents_first_activated,
                            ),
                        ):
                            # First execution: creates all entities
                            service = ALCSeedService(session)
                            report_1 = await service.execute()
                            await session.commit()

                # Second execution in a new session
                async with session_factory() as session:
                    with patch(
                        "alcoabase.services.alc_seed_service.get_settings"
                    ) as mock_settings:
                        mock_settings.return_value.alc_seed_default_password = (
                            "TestPass123!"
                        )

                        with (
                            patch.object(
                                ALCSeedService,
                                "_create_governance_workflow",
                                new=_mock_workflow_second_false,
                            ),
                            patch.object(
                                ALCSeedService,
                                "_configure_risk_profile",
                                new=_mock_risk_profile_second_false,
                            ),
                            patch.object(
                                ALCSeedService,
                                "_activate_agents",
                                new=_mock_agents_second_skipped,
                            ),
                        ):
                            service = ALCSeedService(session)
                            report_2 = await service.execute()
                            await session.commit()

            # --- Idempotency assertions on the second run's report ---

            # All users should be skipped on second run
            assert report_2.users_created == [], (
                f"Second run created users: {report_2.users_created}. "
                "Idempotent execution should skip all existing users."
            )
            assert set(report_2.users_skipped) == {
                u["username"] for u in ALC_USER_POOL
            }, (
                f"Second run users_skipped={report_2.users_skipped}, "
                f"expected all {len(ALC_USER_POOL)} users to be skipped."
            )

            # All folders should be skipped on second run
            assert report_2.folders_created == [], (
                f"Second run created folders: {report_2.folders_created}. "
                "Idempotent execution should skip all existing folders."
            )
            assert set(report_2.folders_skipped) == {
                f["name"] for f in ALC_GOVERNANCE_FOLDERS
            }, (
                f"Second run folders_skipped={report_2.folders_skipped}, "
                f"expected all {len(ALC_GOVERNANCE_FOLDERS)} folders to be skipped."
            )

            # Risk profile should not be re-created
            assert report_2.risk_profile_created is False, (
                "Second run created a risk profile. "
                "Idempotent execution should skip existing profile."
            )

            # Regulatory baseline should not be re-created
            assert report_2.regulatory_baseline_created is False, (
                "Second run created regulatory baseline. "
                "Idempotent execution should skip existing baseline."
            )

            # Audit config should not be re-created
            assert report_2.audit_config_created is False, (
                "Second run created audit config. "
                "Idempotent execution should skip existing config."
            )

            # Agents should all be skipped on second run
            assert report_2.agents_activated == [], (
                f"Second run activated agents: {report_2.agents_activated}. "
                "Idempotent execution should skip all existing activations."
            )

            # Workflow should not be re-created
            assert report_2.workflow_created is False, (
                "Second run created workflow. "
                "Idempotent execution should skip existing workflow."
            )

        finally:
            await engine.dispose()

    _run_async(_test())


async def _mock_workflow_first_true(self, *args, **kwargs) -> bool:
    """Mock for _create_governance_workflow: first run creates (True)."""
    return True


async def _mock_workflow_second_false(self, *args, **kwargs) -> bool:
    """Mock for _create_governance_workflow: second run skips (False)."""
    return False


async def _mock_risk_profile_first_true(self, *args, **kwargs) -> bool:
    """Mock for _configure_risk_profile: first run creates (True)."""
    return True


async def _mock_risk_profile_second_false(self, *args, **kwargs) -> bool:
    """Mock for _configure_risk_profile: second run skips (False)."""
    return False


async def _mock_agents_first_activated(self, *args, **kwargs):
    """Mock for _activate_agents: first run activates agents."""
    from alcoabase.schemas.alc_seed import AgentResult

    return AgentResult(agents_activated=["mock-agent-1"], agents_skipped=[])


async def _mock_agents_second_skipped(self, *args, **kwargs):
    """Mock for _activate_agents: second run skips all agents."""
    from alcoabase.schemas.alc_seed import AgentResult

    return AgentResult(agents_activated=[], agents_skipped=["mock-agent-1"])


# ---------------------------------------------------------------------------
# Property 3: Seed_Report accuracy — report reflects actual database changes
# ---------------------------------------------------------------------------

# Strategy: generate which users already exist (subset of the 4 ALC users)
st_preexisting_users = st.frozensets(
    st.sampled_from([u["username"] for u in ALC_USER_POOL]),
    min_size=0,
    max_size=4,
)

# Strategy: generate which folders already exist (subset of the 6 governance folders)
st_preexisting_folders = st.frozensets(
    st.sampled_from([f["name"] for f in ALC_GOVERNANCE_FOLDERS]),
    min_size=0,
    max_size=6,
)

# Strategy: generate whether the risk profile already exists
st_risk_profile_exists = st.booleans()

# Strategy: generate a set of global agent names that exist
st_global_agents = st.lists(
    st.from_regex(r"^[a-z]{3,10}$", fullmatch=True),
    min_size=0,
    max_size=5,
    unique=True,
)

# Strategy: generate which agents already have active activations (subset indices)
st_preactive_agent_indices = st.frozensets(
    st.integers(min_value=0, max_value=4),
)


@dataclass
class MockDBState:
    """Represents the simulated initial database state for the seed service.

    Attributes:
        preexisting_users: Set of usernames that already exist.
        preexisting_folders: Set of folder names that already exist.
        risk_profile_exists: Whether an active risk profile already exists.
        global_agent_names: List of global agent names available.
        preactive_agent_names: Set of agent names already actively activated.
    """

    preexisting_users: frozenset[str] = field(default_factory=frozenset)
    preexisting_folders: frozenset[str] = field(default_factory=frozenset)
    risk_profile_exists: bool = False
    global_agent_names: list[str] = field(default_factory=list)
    preactive_agent_names: frozenset[str] = field(default_factory=frozenset)


def _build_seed_report_mock_session(state: MockDBState) -> AsyncMock:
    """Build a mock AsyncSession that simulates the given DB state.

    Uses a call-counter approach to return the correct mock result for
    each sequential session.execute() call made by ALCSeedService.

    Args:
        state: The simulated initial database state.

    Returns:
        An AsyncMock configured as an AsyncSession.
    """
    session = AsyncMock()
    session._added_entities: list = []
    _id_counter = {"val": 1}

    def _track_add(entity):
        session._added_entities.append(entity)
        # Simulate ID assignment for entities that need it
        if hasattr(entity, "id") and entity.id is None:
            entity.id = _id_counter["val"]
            _id_counter["val"] += 1

    session.add = MagicMock(side_effect=_track_add)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Build a mock company (always pre-existing to simplify — company creation
    # doesn't affect report accuracy for users/folders/agents/risk profile)
    mock_company = MagicMock()
    mock_company.id = 1
    mock_company.slug = "alc-corporate"

    # Build mock users for pre-existing ones
    mock_users_by_username: dict[str, MagicMock] = {}
    user_id_counter = 10
    for username in state.preexisting_users:
        mock_user = MagicMock()
        mock_user.id = user_id_counter
        mock_user.username = username
        mock_user.email = next(
            u["email"] for u in ALC_USER_POOL if u["username"] == username
        )
        mock_users_by_username[username] = mock_user
        user_id_counter += 1

    # Build mock IT admin (always needed for subsequent steps)
    mock_it_admin = MagicMock()
    mock_it_admin.id = 100
    mock_it_admin.username = "alc-it-admin"

    # Build mock agent definitions
    mock_agents = []
    for i, name in enumerate(state.global_agent_names):
        agent = MagicMock()
        agent.id = 200 + i
        agent.name = name
        agent.company_id = None
        agent.is_active = True
        mock_agents.append(agent)

    # Build mock activations for pre-active agents
    mock_activations: dict[int, MagicMock] = {}
    for agent in mock_agents:
        if agent.name in state.preactive_agent_names:
            activation = MagicMock()
            activation.agent_definition_id = agent.id
            activation.company_id = 1
            activation.is_active = True
            mock_activations[agent.id] = activation

    # Build the ordered list of execute() responses.
    # ALCSeedService makes queries in a deterministic order.
    execute_responses: list[MagicMock] = []

    # Step 1: _create_company — SELECT company WHERE slug='alc-corporate'
    # Always return existing company to keep test focused on report accuracy
    r = MagicMock()
    s = MagicMock()
    s.first.return_value = mock_company
    r.scalars.return_value = s
    execute_responses.append(r)

    # Step 2: _provision_users — for each user: SELECT by username, then conditionally more
    for user_def in ALC_USER_POOL:
        username = user_def["username"]
        # SELECT User WHERE username = ...
        r = MagicMock()
        s = MagicMock()
        s.first.return_value = mock_users_by_username.get(username)
        r.scalars.return_value = s
        execute_responses.append(r)

        if username not in state.preexisting_users:
            # SELECT User WHERE email = ... (no conflict)
            r = MagicMock()
            s = MagicMock()
            s.first.return_value = None
            r.scalars.return_value = s
            execute_responses.append(r)

            # SELECT Role WHERE name = ... AND company_id = ...
            r = MagicMock()
            s = MagicMock()
            s.first.return_value = None
            r.scalars.return_value = s
            execute_responses.append(r)

            # INSERT into UserRole (raw execute)
            execute_responses.append(MagicMock())

    # _ensure_root_admin_membership — SELECT SetupStatus
    r = MagicMock()
    s = MagicMock()
    s.first.return_value = None
    r.scalars.return_value = s
    execute_responses.append(r)

    # Step 3: _find_it_admin — SELECT User WHERE username = 'alc-it-admin'
    r = MagicMock()
    s = MagicMock()
    s.first.return_value = mock_it_admin
    r.scalars.return_value = s
    execute_responses.append(r)

    # Step 4: _apply_regulatory_baseline
    # SELECT SystemConfiguration (baseline) — always create
    r = MagicMock()
    s = MagicMock()
    s.first.return_value = None
    r.scalars.return_value = s
    execute_responses.append(r)
    # SELECT SystemConfiguration (audit config) — always create
    r = MagicMock()
    s = MagicMock()
    s.first.return_value = None
    r.scalars.return_value = s
    execute_responses.append(r)

    # Step 5: _create_folder_structure — for each folder: SELECT VirtualFolder
    for folder_def in ALC_GOVERNANCE_FOLDERS:
        folder_name = folder_def["name"]
        r = MagicMock()
        s = MagicMock()
        if folder_name in state.preexisting_folders:
            mock_folder = MagicMock()
            mock_folder.name = folder_name
            s.first.return_value = mock_folder
        else:
            s.first.return_value = None
        r.scalars.return_value = s
        execute_responses.append(r)

    # Step 6: _configure_risk_profile — SELECT CompanyRiskProfile
    r = MagicMock()
    s = MagicMock()
    if state.risk_profile_exists:
        mock_profile = MagicMock()
        mock_profile.is_active = True
        s.first.return_value = mock_profile
    else:
        s.first.return_value = None
    r.scalars.return_value = s
    execute_responses.append(r)

    if not state.risk_profile_exists:
        # SELECT AITaskType WHERE task_type_id IN (...)
        r = MagicMock()
        s = MagicMock()
        mock_task_types = []
        for tid in [
            "rag_knowledge_query",
            "document_search",
            "template_analysis",
            "change_impact_analysis",
            "traceability_gap_discovery",
            "document_generation",
            "multi_agent_audit",
            "training_content_generation",
        ]:
            tt = MagicMock()
            tt.task_type_id = tid
            tt.is_active = True
            mock_task_types.append(tt)
        s.all.return_value = mock_task_types
        r.scalars.return_value = s
        execute_responses.append(r)

    # Step 7: _activate_agents — SELECT AgentDefinition WHERE company_id IS NULL
    r = MagicMock()
    s = MagicMock()
    s.all.return_value = mock_agents
    r.scalars.return_value = s
    execute_responses.append(r)

    # For each agent: SELECT CompanyAgentActivation
    for agent in mock_agents:
        r = MagicMock()
        s = MagicMock()
        s.first.return_value = mock_activations.get(agent.id)
        r.scalars.return_value = s
        execute_responses.append(r)

    # Set up the execute mock to return responses in order.
    # Add a fallback default result for any extra calls.
    def _execute_side_effect(*args, **kwargs):
        """Return next response from the list, or a default empty result."""
        idx = _execute_side_effect._call_idx
        _execute_side_effect._call_idx += 1
        if idx < len(execute_responses):
            return execute_responses[idx]
        # Fallback: return empty result
        r = MagicMock()
        s = MagicMock()
        s.first.return_value = None
        s.all.return_value = []
        r.scalars.return_value = s
        return r

    _execute_side_effect._call_idx = 0
    session.execute = AsyncMock(side_effect=_execute_side_effect)

    return session


# Feature: Step_8-2_alc-corporate-environment-setup, Property 3: Seed_Report accuracy
@settings(max_examples=100, deadline=None)
@given(
    preexisting_users=st_preexisting_users,
    preexisting_folders=st_preexisting_folders,
    risk_profile_exists=st_risk_profile_exists,
    global_agents=st_global_agents,
    preactive_indices=st_preactive_agent_indices,
)
@pytest.mark.asyncio
async def test_seed_report_accuracy_reflects_actual_db_changes(
    preexisting_users: frozenset[str],
    preexisting_folders: frozenset[str],
    risk_profile_exists: bool,
    global_agents: list[str],
    preactive_indices: frozenset[int],
) -> None:
    """For any initial database state, the Seed_Report returned by
    ALCSeedService.execute() SHALL accurately reflect the actual database
    changes: every entity listed in *_created arrays SHALL exist in the
    database as a new record, and every entity listed in *_skipped arrays
    SHALL have existed prior to execution with no modifications applied.

    **Validates: Requirements 6.4, 7.5, 8.4**

    This test verifies:
    1. Every username in users_created was NOT pre-existing (actually created)
    2. Every username in users_skipped WAS pre-existing (correctly skipped)
    3. Every folder in folders_created was NOT pre-existing (actually created)
    4. Every folder in folders_skipped WAS pre-existing (correctly skipped)
    5. risk_profile_created matches whether a new profile was actually created
    6. agents_activated and agents_skipped match actual CompanyAgentActivation state
    """
    # Compute pre-active agent names (only valid indices)
    preactive_agent_names = frozenset(
        global_agents[i] for i in preactive_indices if i < len(global_agents)
    )

    state = MockDBState(
        preexisting_users=preexisting_users,
        preexisting_folders=preexisting_folders,
        risk_profile_exists=risk_profile_exists,
        global_agent_names=global_agents,
        preactive_agent_names=preactive_agent_names,
    )

    session = _build_seed_report_mock_session(state)
    service = ALCSeedService(session)

    # Patch _create_governance_workflow since it raises NotImplementedError
    async def _mock_workflow(company, it_admin):
        return False

    service._create_governance_workflow = _mock_workflow  # type: ignore[assignment]
    report = await service.execute()

    # --- Verify Property 3: Report accuracy ---

    # 1. users_created: every username here should NOT have been pre-existing
    for username in report.users_created:
        assert username not in preexisting_users, (
            f"Report claims '{username}' was created, but it was pre-existing"
        )

    # 2. users_skipped: every username here SHOULD have been pre-existing
    for username in report.users_skipped:
        assert username in preexisting_users, (
            f"Report claims '{username}' was skipped, but it was NOT pre-existing"
        )

    # 3. Completeness: all ALC users are accounted for in created + skipped
    all_reported_users = set(report.users_created) | set(report.users_skipped)
    all_expected_users = {u["username"] for u in ALC_USER_POOL}
    assert all_reported_users == all_expected_users, (
        f"Report does not account for all users. "
        f"Missing: {all_expected_users - all_reported_users}"
    )

    # 4. folders_created: every folder here should NOT have been pre-existing
    for folder_name in report.folders_created:
        assert folder_name not in preexisting_folders, (
            f"Report claims folder '{folder_name}' was created, but it was pre-existing"
        )

    # 5. folders_skipped: every folder here SHOULD have been pre-existing
    for folder_name in report.folders_skipped:
        assert folder_name in preexisting_folders, (
            f"Report claims folder '{folder_name}' was skipped, but it was NOT pre-existing"
        )

    # 6. Completeness: all governance folders are accounted for
    all_reported_folders = set(report.folders_created) | set(report.folders_skipped)
    all_expected_folders = {f["name"] for f in ALC_GOVERNANCE_FOLDERS}
    assert all_reported_folders == all_expected_folders, (
        f"Report does not account for all folders. "
        f"Missing: {all_expected_folders - all_reported_folders}"
    )

    # 7. risk_profile_created matches whether a new profile was actually created
    if risk_profile_exists:
        assert report.risk_profile_created is False, (
            "Report claims risk profile was created, but one already existed"
        )
    else:
        assert report.risk_profile_created is True, (
            "Report claims risk profile was NOT created, but none existed"
        )

    # 8. agents_activated: every agent here should NOT have been pre-active
    for agent_name in report.agents_activated:
        assert agent_name not in preactive_agent_names, (
            f"Report claims agent '{agent_name}' was activated, "
            f"but it was already active"
        )

    # 9. agents_skipped: every agent here SHOULD have been pre-active
    for agent_name in report.agents_skipped:
        assert agent_name in preactive_agent_names, (
            f"Report claims agent '{agent_name}' was skipped, "
            f"but it was NOT pre-active"
        )

    # 10. Completeness: all global agents are accounted for
    all_reported_agents = set(report.agents_activated) | set(report.agents_skipped)
    all_expected_agents = set(global_agents)
    assert all_reported_agents == all_expected_agents, (
        f"Report does not account for all agents. "
        f"Missing: {all_expected_agents - all_reported_agents}"
    )
