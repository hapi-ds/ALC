"""Property-based tests for audit profile quorum constraint.

Tests Property 6 from the multi-agent always-on auditing design document,
validating that the quorum value cannot exceed the number of assigned agent IDs.

**Validates: Requirements 4.5**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 6)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md (Requirement 4)
"""

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.audit_profile_service import AuditProfileService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_agent_ids() -> st.SearchStrategy[list[int]]:
    """Generate a non-empty list of unique agent IDs.

    Returns:
        Strategy producing lists of 1-20 unique positive integers.
    """
    return st.lists(
        st.integers(min_value=1, max_value=10000),
        min_size=1,
        max_size=20,
        unique=True,
    )


def st_quorum_exceeding(agent_ids: list[int]) -> st.SearchStrategy[int]:
    """Generate a quorum value that exceeds the agent list length.

    Args:
        agent_ids: The list of agent IDs to exceed.

    Returns:
        Strategy producing integers strictly greater than len(agent_ids).
    """
    return st.integers(min_value=len(agent_ids) + 1, max_value=len(agent_ids) + 100)


def st_quorum_valid(agent_ids: list[int]) -> st.SearchStrategy[int]:
    """Generate a quorum value that is valid (1 <= quorum <= len(agent_ids)).

    Args:
        agent_ids: The list of agent IDs to constrain against.

    Returns:
        Strategy producing integers in [1, len(agent_ids)].
    """
    return st.integers(min_value=1, max_value=len(agent_ids))


# ---------------------------------------------------------------------------
# Property 6: Audit profile quorum constraint
# ---------------------------------------------------------------------------


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 6: Audit profile quorum constraint
@settings(max_examples=100, deadline=None)
@given(data=st.data())
@pytest.mark.asyncio
async def test_quorum_exceeding_agent_count_is_rejected(
    data: st.DataObject,
) -> None:
    """For any list of agent_ids and any quorum value greater than
    len(agent_ids), creating an audit profile SHALL be rejected with
    a ValueError.

    This validates that the AuditProfileService enforces the constraint
    quorum <= len(assigned_agent_ids) on profile creation.

    **Validates: Requirements 4.5**
    """
    agent_ids = data.draw(st_agent_ids(), label="agent_ids")
    quorum = data.draw(st_quorum_exceeding(agent_ids), label="quorum")

    # Create service with a mock session factory — the quorum check
    # happens before any DB interaction, so no real session is needed.
    mock_session_factory = AsyncMock()
    service = AuditProfileService(session_factory=mock_session_factory)

    profile_data = {
        "name": "Test Profile",
        "description": "Test",
        "regulatory_frameworks": ["GMP"],
        "assigned_agent_ids": agent_ids,
        "quorum": quorum,
        "is_default": False,
    }

    with pytest.raises(ValueError, match=r"Quorum.*exceeds assigned agent count"):
        await service.create_profile(data=profile_data, company_id=1)


# Feature: Step_5-2_multi-agent-always-on-auditing, Property 6: Audit profile quorum constraint
@settings(max_examples=100, deadline=None)
@given(data=st.data())
@pytest.mark.asyncio
async def test_quorum_within_agent_count_passes_validation(
    data: st.DataObject,
) -> None:
    """For any list of agent_ids and any quorum value where
    quorum <= len(agent_ids), the quorum validation step SHALL NOT
    raise a ValueError (the call may fail later due to agent assignment
    validation, but the quorum check itself passes).

    This is the complementary property: valid quorum values are accepted.

    **Validates: Requirements 4.5**
    """
    agent_ids = data.draw(st_agent_ids(), label="agent_ids")
    quorum = data.draw(st_quorum_valid(agent_ids), label="quorum")

    # Mock the session factory and validate_agent_assignments to isolate
    # the quorum check. validate_agent_assignments is called after the
    # quorum check, so we mock it to return no errors.
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_session)
    service = AuditProfileService(session_factory=mock_session_factory)

    # Mock validate_agent_assignments to return empty list (no errors)
    # so we can verify the quorum check passes without hitting the DB.
    service.validate_agent_assignments = AsyncMock(return_value=[])

    profile_data = {
        "name": "Test Profile",
        "description": "Test",
        "regulatory_frameworks": ["GMP"],
        "assigned_agent_ids": agent_ids,
        "quorum": quorum,
        "is_default": False,
    }

    # The quorum check should pass. The call will proceed to the DB
    # session context manager, which we've mocked. We expect it to
    # NOT raise ValueError for quorum constraint.
    try:
        await service.create_profile(data=profile_data, company_id=1)
    except ValueError as e:
        # If a ValueError is raised, it must NOT be about quorum
        assert "Quorum" not in str(e) and "quorum" not in str(e), (
            f"Valid quorum {quorum} for {len(agent_ids)} agents "
            f"should not be rejected, but got: {e}"
        )
    except (AttributeError, TypeError, StopIteration):
        # These are expected from the mocked session factory internals
        # (e.g., session.add, session.commit). The important thing is
        # that no quorum ValueError was raised.
        pass
