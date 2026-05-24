"""Property-based tests for company-scoped agent filtering.

Tests Property 9: Company-scoped agent filtering from the
modular-agent-registry-personality-framework design document.

Property 9 validates that for any set of agents belonging to different companies,
listing agents with a specific company_id SHALL return only agents belonging to
that company, and filtering by archetype SHALL return only agents matching both
the company_id and the archetype value.

Feature: modular-agent-registry, Property 9: Company-scoped agent filtering

**Validates: Requirements 5.6, 6.7**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md (Property 9)
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/agent_registry.py
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.agent import AgentDefinition as AgentDefinitionDB
from alcoabase.services.agent_registry import AgentRegistryService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Available archetypes for testing
_ARCHETYPES = [
    "Regulatory Compliance Auditor",
    "Data Integrity Specialist",
    "Process Safety Reviewer",
    "Statistical Methods Auditor",
    "Technical Writer",
    "Educational Specialist",
]


def _make_agent_db(
    agent_id: int,
    company_id: int,
    archetype: str | None = None,
    is_active: bool = True,
    name: str = "Test Agent",
) -> AgentDefinitionDB:
    """Create a mock AgentDefinitionDB object with the given fields.

    Args:
        agent_id: Unique agent identifier.
        company_id: Company scope identifier.
        archetype: Optional archetype string.
        is_active: Whether the agent is active.
        name: Agent name.

    Returns:
        A MagicMock with AgentDefinitionDB spec and configured attributes.
    """
    agent = MagicMock(spec=AgentDefinitionDB)
    agent.id = agent_id
    agent.company_id = company_id
    agent.archetype = archetype
    agent.is_active = is_active
    agent.name = name
    return agent


def _make_service_with_agents(
    agents: list[AgentDefinitionDB],
) -> AgentRegistryService:
    """Create an AgentRegistryService with a mock session factory.

    The mock session factory simulates the database query by filtering
    the provided agents list based on company_id, is_active, and archetype
    — mirroring the SQL WHERE clauses in list_agents.

    Args:
        agents: List of mock AgentDefinitionDB objects to serve as the dataset.

    Returns:
        An AgentRegistryService configured with a mock session factory.
    """
    mock_schema_validator = MagicMock()
    service = AgentRegistryService(
        session_factory=MagicMock(),  # placeholder, replaced below
        schema_validator=mock_schema_validator,
        agents_dir=Path("/tmp/agents"),
        archetypes_dir=Path("/tmp/archetypes"),
    )

    all_agents = agents

    @asynccontextmanager
    async def mock_session_ctx():
        """Async context manager that yields a mock session."""
        session = AsyncMock()

        async def mock_execute(stmt: Any) -> Any:
            """Simulate SQL filtering by extracting WHERE clause bind params.

            Inspects the compiled SQL statement to determine which company_id
            and archetype filters are applied, then filters the in-memory
            agent list accordingly.
            """
            # Use SQLAlchemy's whereclause to extract filter parameters
            # by compiling with literal_binds for inspection
            try:
                compiled = stmt.compile(compile_kwargs={"literal_binds": True})
                compiled_str = str(compiled)
            except Exception:
                compiled_str = ""

            # Start with all agents, then apply filters
            filtered = list(all_agents)

            # Filter by is_active = true (always applied by list_agents)
            filtered = [a for a in filtered if a.is_active]

            # Filter by company_id
            # The compiled SQL contains "agent_definitions.company_id = <value>"
            import re

            company_match = re.search(
                r"company_id\s*=\s*(\d+)", compiled_str
            )
            if company_match:
                target_company_id = int(company_match.group(1))
                filtered = [
                    a for a in filtered
                    if a.company_id == target_company_id
                ]

            # Filter by archetype if present
            # The compiled SQL contains "agent_definitions.archetype = '<value>'"
            archetype_match = re.search(
                r"archetype\s*=\s*'([^']*)'", compiled_str
            )
            if archetype_match:
                target_archetype = archetype_match.group(1)
                filtered = [
                    a for a in filtered
                    if a.archetype == target_archetype
                ]

            result = MagicMock()
            result.scalars.return_value.all.return_value = filtered
            return result

        session.execute = mock_execute
        session.expunge = MagicMock()
        yield session

    service._session_factory = mock_session_ctx

    return service


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for company IDs (use small range to ensure collisions)
company_ids = st.integers(min_value=1, max_value=5)

# Strategy for archetype values
archetype_values = st.sampled_from(_ARCHETYPES)

# Strategy for optional archetype (can be None)
optional_archetype = st.one_of(st.none(), archetype_values)


@st.composite
def agent_set(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a set of agents with different company_ids and archetypes.

    Returns:
        List of dicts with keys: id, company_id, archetype, is_active.
    """
    num_agents = draw(st.integers(min_value=2, max_value=20))
    agents = []
    for i in range(num_agents):
        agents.append(
            {
                "id": i + 1,
                "company_id": draw(company_ids),
                "archetype": draw(optional_archetype),
                "is_active": draw(st.booleans()),
                "name": f"Agent-{i + 1}",
            }
        )
    return agents


@st.composite
def multi_company_agent_set(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate agents guaranteed to span at least 2 different companies.

    Returns:
        List of agent dicts spanning multiple companies.
    """
    # Ensure at least 2 different companies
    company_a = draw(st.integers(min_value=1, max_value=5))
    company_b = draw(
        st.integers(min_value=1, max_value=5).filter(lambda x: x != company_a)
    )

    agents = []
    agent_id = 1

    # At least one active agent per company
    agents.append(
        {
            "id": agent_id,
            "company_id": company_a,
            "archetype": draw(archetype_values),
            "is_active": True,
            "name": f"Agent-{agent_id}",
        }
    )
    agent_id += 1

    agents.append(
        {
            "id": agent_id,
            "company_id": company_b,
            "archetype": draw(archetype_values),
            "is_active": True,
            "name": f"Agent-{agent_id}",
        }
    )
    agent_id += 1

    # Additional random agents
    extra_count = draw(st.integers(min_value=0, max_value=10))
    for _ in range(extra_count):
        agents.append(
            {
                "id": agent_id,
                "company_id": draw(st.sampled_from([company_a, company_b])),
                "archetype": draw(optional_archetype),
                "is_active": draw(st.booleans()),
                "name": f"Agent-{agent_id}",
            }
        )
        agent_id += 1

    return agents


# ---------------------------------------------------------------------------
# Property 9: Company-scoped agent filtering
# ---------------------------------------------------------------------------


class TestCompanyScopedFilteringProperties:
    """Property tests for company-scoped agent filtering.

    For any set of agents belonging to different companies, listing agents with
    a specific company_id SHALL return only agents belonging to that company,
    and filtering by archetype SHALL return only agents matching both the
    company_id and the archetype value.

    Feature: modular-agent-registry, Property 9: Company-scoped agent filtering

    **Validates: Requirements 5.6, 6.7**
    """

    @given(data=multi_company_agent_set())
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_list_agents_returns_only_target_company(
        self, data: list[dict[str, Any]]
    ) -> None:
        """Listing agents with a company_id returns only that company's active agents.

        **Validates: Requirements 5.6, 6.7**
        """
        # Build mock agents
        mock_agents = [
            _make_agent_db(
                agent_id=a["id"],
                company_id=a["company_id"],
                archetype=a["archetype"],
                is_active=a["is_active"],
                name=a["name"],
            )
            for a in data
        ]

        service = _make_service_with_agents(mock_agents)

        # Pick a company_id that exists in the dataset
        target_company = data[0]["company_id"]

        result = await service.list_agents(company_id=target_company)

        # All returned agents must belong to the target company
        for agent in result:
            assert agent.company_id == target_company, (
                f"Agent {agent.id} has company_id={agent.company_id}, "
                f"expected {target_company}"
            )

        # All returned agents must be active
        for agent in result:
            assert agent.is_active, (
                f"Agent {agent.id} is inactive but was returned in list"
            )

        # The result should contain ALL active agents for the target company
        expected_ids = {
            a["id"] for a in data
            if a["company_id"] == target_company and a["is_active"]
        }
        result_ids = {agent.id for agent in result}
        assert result_ids == expected_ids, (
            f"Expected agent IDs {expected_ids}, got {result_ids}"
        )

    @given(data=multi_company_agent_set())
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_list_agents_excludes_other_companies(
        self, data: list[dict[str, Any]]
    ) -> None:
        """Listing agents for one company never returns agents from other companies.

        **Validates: Requirements 5.6, 6.7**
        """
        mock_agents = [
            _make_agent_db(
                agent_id=a["id"],
                company_id=a["company_id"],
                archetype=a["archetype"],
                is_active=a["is_active"],
                name=a["name"],
            )
            for a in data
        ]

        service = _make_service_with_agents(mock_agents)

        # Pick the first company
        target_company = data[0]["company_id"]
        other_company_ids = {
            a["company_id"] for a in data if a["company_id"] != target_company
        }

        result = await service.list_agents(company_id=target_company)

        # No agent from another company should appear
        for agent in result:
            assert agent.company_id not in other_company_ids, (
                f"Agent {agent.id} from company {agent.company_id} "
                f"leaked into results for company {target_company}"
            )

    @given(data=multi_company_agent_set(), archetype=archetype_values)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_archetype_filter_with_company_scope(
        self, data: list[dict[str, Any]], archetype: str
    ) -> None:
        """Filtering by archetype returns only agents matching both company and archetype.

        **Validates: Requirements 5.6, 6.7**
        """
        mock_agents = [
            _make_agent_db(
                agent_id=a["id"],
                company_id=a["company_id"],
                archetype=a["archetype"],
                is_active=a["is_active"],
                name=a["name"],
            )
            for a in data
        ]

        service = _make_service_with_agents(mock_agents)

        target_company = data[0]["company_id"]

        result = await service.list_agents(
            company_id=target_company, archetype=archetype
        )

        # All returned agents must match BOTH company_id AND archetype
        for agent in result:
            assert agent.company_id == target_company, (
                f"Agent {agent.id} has company_id={agent.company_id}, "
                f"expected {target_company}"
            )
            assert agent.archetype == archetype, (
                f"Agent {agent.id} has archetype='{agent.archetype}', "
                f"expected '{archetype}'"
            )
            assert agent.is_active, (
                f"Agent {agent.id} is inactive but was returned"
            )

        # Verify completeness: all matching agents are returned
        expected_ids = {
            a["id"] for a in data
            if a["company_id"] == target_company
            and a["archetype"] == archetype
            and a["is_active"]
        }
        result_ids = {agent.id for agent in result}
        assert result_ids == expected_ids, (
            f"Expected agent IDs {expected_ids} for company={target_company} "
            f"archetype='{archetype}', got {result_ids}"
        )

    @given(data=agent_set())
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_nonexistent_company_returns_empty(
        self, data: list[dict[str, Any]]
    ) -> None:
        """Listing agents for a company with no agents returns an empty list.

        **Validates: Requirements 5.6, 6.7**
        """
        mock_agents = [
            _make_agent_db(
                agent_id=a["id"],
                company_id=a["company_id"],
                archetype=a["archetype"],
                is_active=a["is_active"],
                name=a["name"],
            )
            for a in data
        ]

        service = _make_service_with_agents(mock_agents)

        # Use a company_id that doesn't exist in the dataset
        existing_companies = {a["company_id"] for a in data}
        nonexistent_company = max(existing_companies) + 100

        result = await service.list_agents(company_id=nonexistent_company)

        assert result == [], (
            f"Expected empty list for nonexistent company {nonexistent_company}, "
            f"got {len(result)} agents"
        )

    @given(data=multi_company_agent_set())
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_inactive_agents_excluded(
        self, data: list[dict[str, Any]]
    ) -> None:
        """Inactive agents are never returned regardless of company or archetype match.

        **Validates: Requirements 5.6, 6.7**
        """
        mock_agents = [
            _make_agent_db(
                agent_id=a["id"],
                company_id=a["company_id"],
                archetype=a["archetype"],
                is_active=a["is_active"],
                name=a["name"],
            )
            for a in data
        ]

        service = _make_service_with_agents(mock_agents)

        target_company = data[0]["company_id"]

        result = await service.list_agents(company_id=target_company)

        # No inactive agent should be in the results
        inactive_ids = {
            a["id"] for a in data if not a["is_active"]
        }
        result_ids = {agent.id for agent in result}

        assert result_ids.isdisjoint(inactive_ids), (
            f"Inactive agents {result_ids & inactive_ids} appeared in results"
        )
