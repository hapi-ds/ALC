"""Property-based tests for Company Role Provisioning.

Tests Property 2 from the admin-dashboard-user-management design document:
For any newly created company, the system SHALL provision exactly five roles
(system_admin, doc_admin, it_admin, member, viewer) with permission sets
matching the predefined defaults.

**Validates: Requirements 1.2**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 2)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (1.2)
"""

import asyncio
from unittest.mock import AsyncMock

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.rbac import DEFAULT_ROLE_PERMISSIONS, RBACService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_ROLE_NAMES = {"system_admin", "doc_admin", "it_admin", "member", "viewer"}


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine synchronously for use within hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Mock session builder
# ---------------------------------------------------------------------------


def _build_mock_session() -> AsyncMock:
    """Build a mock AsyncSession for seed_default_roles.

    The seed_default_roles method calls session.add() for each role
    and session.flush() at the end. We mock both to track what was added.

    Returns:
        A mock AsyncSession with tracked add calls and a no-op flush.
    """
    session = AsyncMock()
    session.add = lambda obj: session._added_objects.append(obj)
    session._added_objects = []
    session.flush = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_company_id(draw: st.DrawFn) -> int:
    """Generate a random positive company ID representing a new company.

    Returns:
        A positive integer company ID.
    """
    return draw(st.integers(min_value=1, max_value=100_000))


# ---------------------------------------------------------------------------
# Property 2: Company Role Provisioning
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(company_id=st_company_id())
def test_seed_default_roles_provisions_exactly_five_roles(
    company_id: int,
) -> None:
    """For any newly created company, seed_default_roles SHALL provision
    exactly five roles.

    **Validates: Requirements 1.2**
    """

    async def _test():
        rbac = RBACService()
        session = _build_mock_session()

        roles = await rbac.seed_default_roles(company_id=company_id, session=session)

        assert len(roles) == 5, (
            f"Expected exactly 5 roles provisioned for company_id={company_id}, "
            f"got {len(roles)}."
        )

    _run_async(_test())


@settings(max_examples=200, deadline=None)
@given(company_id=st_company_id())
def test_seed_default_roles_provisions_correct_role_names(
    company_id: int,
) -> None:
    """For any newly created company, seed_default_roles SHALL provision
    roles named system_admin, doc_admin, it_admin, member, and viewer.

    **Validates: Requirements 1.2**
    """

    async def _test():
        rbac = RBACService()
        session = _build_mock_session()

        roles = await rbac.seed_default_roles(company_id=company_id, session=session)

        provisioned_names = {role.name for role in roles}
        assert provisioned_names == EXPECTED_ROLE_NAMES, (
            f"Expected role names {EXPECTED_ROLE_NAMES} for company_id={company_id}, "
            f"got {provisioned_names}."
        )

    _run_async(_test())


@settings(max_examples=200, deadline=None)
@given(company_id=st_company_id())
def test_seed_default_roles_permissions_match_defaults(
    company_id: int,
) -> None:
    """For any newly created company, each provisioned role SHALL have
    permissions matching DEFAULT_ROLE_PERMISSIONS.

    **Validates: Requirements 1.2**
    """

    async def _test():
        rbac = RBACService()
        session = _build_mock_session()

        roles = await rbac.seed_default_roles(company_id=company_id, session=session)

        for role in roles:
            expected_permissions = DEFAULT_ROLE_PERMISSIONS[role.name]
            assert role.permissions == expected_permissions, (
                f"Permissions mismatch for role '{role.name}' in "
                f"company_id={company_id}. "
                f"Expected: {expected_permissions}, "
                f"Got: {role.permissions}"
            )

    _run_async(_test())


@settings(max_examples=200, deadline=None)
@given(company_id=st_company_id())
def test_seed_default_roles_all_scoped_to_company(
    company_id: int,
) -> None:
    """For any newly created company, all provisioned roles SHALL be
    scoped to that company (company_id set correctly) and marked as
    system roles (is_system=True).

    **Validates: Requirements 1.2**
    """

    async def _test():
        rbac = RBACService()
        session = _build_mock_session()

        roles = await rbac.seed_default_roles(company_id=company_id, session=session)

        for role in roles:
            assert role.company_id == company_id, (
                f"Role '{role.name}' has company_id={role.company_id}, "
                f"expected {company_id}."
            )
            assert role.is_system is True, (
                f"Role '{role.name}' has is_system={role.is_system}, "
                f"expected True. System roles must be non-editable."
            )

    _run_async(_test())


@settings(max_examples=200, deadline=None)
@given(company_id=st_company_id())
def test_seed_default_roles_added_to_session(
    company_id: int,
) -> None:
    """For any newly created company, all provisioned roles SHALL be
    added to the database session and flushed.

    **Validates: Requirements 1.2**
    """

    async def _test():
        rbac = RBACService()
        session = _build_mock_session()

        roles = await rbac.seed_default_roles(company_id=company_id, session=session)

        # Verify all roles were added to the session
        assert len(session._added_objects) == 5, (
            f"Expected 5 objects added to session for company_id={company_id}, "
            f"got {len(session._added_objects)}."
        )

        # Verify flush was called
        session.flush.assert_awaited_once()

    _run_async(_test())
