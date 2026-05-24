"""Unit tests for AgentRegistryService file watcher integration.

Tests the start_watcher(), stop_watcher(), _on_file_change(), and reload()
methods that integrate the AgentFileWatcher with the AgentRegistryService.

References:
    - Requirements: 3.6, 3.7
    - Task 8.2: Integrate file watcher with AgentRegistryService
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from alcoabase.schemas.agent import ReloadSummary
from alcoabase.services.agent_registry import AgentRegistryService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    """Create a temporary agents directory."""
    d = tmp_path / "agents"
    d.mkdir()
    return d


@pytest.fixture
def archetypes_dir(tmp_path: Path) -> Path:
    """Create a temporary archetypes directory."""
    d = tmp_path / "archetypes"
    d.mkdir()
    return d


@pytest.fixture
def mock_session_factory() -> AsyncMock:
    """Create a mock async session factory."""
    factory = AsyncMock()
    session = AsyncMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=None)
    return factory


@pytest.fixture
def mock_schema_validator() -> MagicMock:
    """Create a mock schema validator that passes all validation."""
    validator = MagicMock()
    validator.validate.return_value = []  # No errors
    return validator


@pytest.fixture
def service(
    mock_session_factory: AsyncMock,
    mock_schema_validator: MagicMock,
    agents_dir: Path,
    archetypes_dir: Path,
) -> AgentRegistryService:
    """Create an AgentRegistryService instance with mocked dependencies."""
    return AgentRegistryService(
        session_factory=mock_session_factory,
        schema_validator=mock_schema_validator,
        agents_dir=agents_dir,
        archetypes_dir=archetypes_dir,
    )


def _write_valid_agent_yaml(agents_dir: Path, name: str = "test-agent") -> Path:
    """Write a valid agent YAML file to the agents directory."""
    data = {
        "schema_version": "1.0",
        "name": name,
        "description": "A test agent",
        "agent_type": "generation",
        "system_prompt": "You are a test agent.",
        "dspy_modules": [{"name": "analyze", "type": "ChainOfThought", "params": {}}],
        "knowledge_scopes": {"tags": ["test"]},
    }
    file_path = agents_dir / f"{name}.yaml"
    file_path.write_text(yaml.dump(data))
    return file_path


# ---------------------------------------------------------------------------
# Tests: start_watcher / stop_watcher
# ---------------------------------------------------------------------------


class TestStartStopWatcher:
    """Tests for start_watcher() and stop_watcher() methods."""

    @pytest.mark.asyncio
    async def test_start_watcher_creates_watcher_instance(
        self, service: AgentRegistryService
    ) -> None:
        """start_watcher() creates an AgentFileWatcher and starts it."""
        with patch(
            "alcoabase.services.agent_registry.AgentFileWatcher"
        ) as MockWatcher:
            mock_watcher_instance = AsyncMock()
            MockWatcher.return_value = mock_watcher_instance

            await service.start_watcher()

            MockWatcher.assert_called_once_with(
                agents_dir=service._agents_dir,
                on_change=service._on_file_change,
            )
            mock_watcher_instance.start.assert_called_once()
            assert service._watcher is mock_watcher_instance

    @pytest.mark.asyncio
    async def test_stop_watcher_stops_and_clears_watcher(
        self, service: AgentRegistryService
    ) -> None:
        """stop_watcher() calls stop on the watcher and sets it to None."""
        mock_watcher = AsyncMock()
        service._watcher = mock_watcher

        await service.stop_watcher()

        mock_watcher.stop.assert_called_once()
        assert service._watcher is None

    @pytest.mark.asyncio
    async def test_stop_watcher_when_not_started_is_noop(
        self, service: AgentRegistryService
    ) -> None:
        """stop_watcher() when no watcher exists does nothing."""
        assert service._watcher is None
        await service.stop_watcher()  # Should not raise
        assert service._watcher is None


# ---------------------------------------------------------------------------
# Tests: _on_file_change callback
# ---------------------------------------------------------------------------


class TestOnFileChange:
    """Tests for the _on_file_change callback method."""

    @pytest.mark.asyncio
    async def test_add_action_with_valid_data_creates_agent(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """On 'add' action with valid data, creates agent via create_agent."""
        data = {"name": "new-agent", "schema_version": "1.0"}
        file_path = agents_dir / "new-agent.yaml"

        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(name="new-agent")
            await service._on_file_change("add", file_path, data)

            mock_create.assert_called_once_with(data, company_id=None, user_id=1)

    @pytest.mark.asyncio
    async def test_add_action_with_validation_errors_skips(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """On 'add' action with invalid data, does not create agent."""
        data = {"name": "bad-agent"}
        file_path = agents_dir / "bad-agent.yaml"
        service._schema_validator.validate.return_value = ["missing required field"]

        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            await service._on_file_change("add", file_path, data)

            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_modify_action_updates_existing_agent(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """On 'modify' action, updates existing agent in cache."""
        data = {"name": "existing-agent", "schema_version": "1.0"}
        file_path = agents_dir / "existing-agent.yaml"

        # Put an agent in the cache
        mock_agent = MagicMock()
        mock_agent.id = 42
        mock_agent.name = "existing-agent"
        mock_agent.company_id = 1
        service._cache[42] = mock_agent

        with patch.object(service, "update_agent", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = mock_agent
            await service._on_file_change("modify", file_path, data)

            mock_update.assert_called_once_with(42, data, 1)

    @pytest.mark.asyncio
    async def test_modify_action_creates_if_not_in_cache(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """On 'modify' action for unknown agent, creates it as new."""
        data = {"name": "unknown-agent", "schema_version": "1.0"}
        file_path = agents_dir / "unknown-agent.yaml"

        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = MagicMock(name="unknown-agent")
            await service._on_file_change("modify", file_path, data)

            mock_create.assert_called_once_with(data, company_id=None, user_id=1)

    @pytest.mark.asyncio
    async def test_remove_action_deactivates_agent(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """On 'remove' action, deactivates agent in DB and removes from cache."""
        file_path = agents_dir / "removed-agent.yaml"

        # Put an agent in the cache with matching name
        mock_agent = MagicMock()
        mock_agent.id = 99
        mock_agent.name = "removed-agent"
        mock_agent.company_id = 1
        service._cache[99] = mock_agent

        # Mock the session factory as a proper async context manager
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_agent_db = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_agent_db
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        service._session_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        await service._on_file_change("remove", file_path, None)

        assert 99 not in service._cache

    @pytest.mark.asyncio
    async def test_modify_action_with_validation_errors_retains_previous(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """On 'modify' with invalid data, retains previous definition."""
        data = {"name": "bad-modify"}
        file_path = agents_dir / "bad-modify.yaml"
        service._schema_validator.validate.return_value = ["invalid field"]

        with patch.object(service, "update_agent", new_callable=AsyncMock) as mock_update:
            await service._on_file_change("modify", file_path, data)

            mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: reload()
# ---------------------------------------------------------------------------


class TestReload:
    """Tests for the reload() method."""

    @pytest.mark.asyncio
    async def test_reload_returns_reload_summary(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() returns a ReloadSummary instance."""
        result = await service.reload()

        assert isinstance(result, ReloadSummary)
        assert result.loaded == []
        assert result.updated == []
        assert result.deactivated == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_reload_loads_new_agents(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() detects and loads new YAML files."""
        _write_valid_agent_yaml(agents_dir, "new-agent")

        with patch.object(service, "create_agent", new_callable=AsyncMock) as mock_create:
            mock_agent = MagicMock()
            mock_agent.name = "new-agent"
            mock_create.return_value = mock_agent

            result = await service.reload()

            assert "new-agent" in result.loaded
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_updates_existing_agents(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() detects and updates agents already in cache."""
        _write_valid_agent_yaml(agents_dir, "existing-agent")

        # Put agent in cache
        mock_agent = MagicMock()
        mock_agent.id = 10
        mock_agent.name = "existing-agent"
        mock_agent.company_id = 1
        service._cache[10] = mock_agent

        with patch.object(service, "update_agent", new_callable=AsyncMock) as mock_update:
            mock_update.return_value = mock_agent

            result = await service.reload()

            assert "existing-agent" in result.updated
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_deactivates_removed_agents(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() deactivates agents no longer on disk."""
        # Agent in cache but no file on disk
        mock_agent = MagicMock()
        mock_agent.id = 20
        mock_agent.name = "gone-agent"
        mock_agent.company_id = 1
        service._cache[20] = mock_agent

        # Mock the session factory as a proper async context manager
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_agent_db = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_agent_db
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        service._session_factory = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_session),
                __aexit__=AsyncMock(return_value=False),
            )
        )

        result = await service.reload()

        assert "gone-agent" in result.deactivated
        assert 20 not in service._cache

    @pytest.mark.asyncio
    async def test_reload_reports_validation_errors(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() reports validation errors for invalid files."""
        _write_valid_agent_yaml(agents_dir, "bad-agent")
        service._schema_validator.validate.return_value = ["missing archetype"]

        result = await service.reload()

        assert len(result.errors) == 1
        assert "bad-agent" in result.errors[0]["file"]
        assert "missing archetype" in result.errors[0]["error"]

    @pytest.mark.asyncio
    async def test_reload_reports_yaml_parse_errors(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() reports YAML parse errors."""
        bad_file = agents_dir / "broken.yaml"
        bad_file.write_text("name: [unclosed bracket\n")

        result = await service.reload()

        assert len(result.errors) == 1
        assert "broken.yaml" in result.errors[0]["file"]
        assert "YAML parse error" in result.errors[0]["error"]

    @pytest.mark.asyncio
    async def test_reload_with_nonexistent_dir_returns_empty_summary(
        self, service: AgentRegistryService, tmp_path: Path
    ) -> None:
        """reload() with non-existent directory returns empty summary."""
        service._agents_dir = tmp_path / "nonexistent"

        result = await service.reload()

        assert result.loaded == []
        assert result.updated == []
        assert result.deactivated == []
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_reload_ignores_non_yaml_files(
        self, service: AgentRegistryService, agents_dir: Path
    ) -> None:
        """reload() only processes .yaml and .yml files."""
        # Write a non-YAML file
        (agents_dir / "readme.txt").write_text("not an agent")
        (agents_dir / "config.json").write_text('{"key": "value"}')

        result = await service.reload()

        assert result.loaded == []
        assert result.errors == []
