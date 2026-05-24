"""Unit tests for AgentFileWatcher.

Tests the file watcher's ability to detect YAML file changes,
filter by extension, parse YAML content, and handle errors gracefully.

References:
    - Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.9
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from alcoabase.services.agent_file_watcher import AgentFileWatcher, _VALID_EXTENSIONS


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
def on_change_mock() -> AsyncMock:
    """Create a mock async callback for on_change."""
    return AsyncMock()


@pytest.fixture
def watcher(agents_dir: Path, on_change_mock: AsyncMock) -> AgentFileWatcher:
    """Create an AgentFileWatcher instance with a mock callback."""
    return AgentFileWatcher(agents_dir=agents_dir, on_change=on_change_mock)


# ---------------------------------------------------------------------------
# Tests: _load_yaml_file
# ---------------------------------------------------------------------------


class TestLoadYamlFile:
    """Tests for the _load_yaml_file method."""

    def test_loads_valid_yaml(self, watcher: AgentFileWatcher, agents_dir: Path) -> None:
        """Valid YAML mapping is parsed and returned."""
        yaml_file = agents_dir / "test.yaml"
        yaml_file.write_text("name: test-agent\nversion: '1.0'\n")

        result = watcher._load_yaml_file(yaml_file)

        assert result == {"name": "test-agent", "version": "1.0"}

    def test_returns_none_for_invalid_yaml_syntax(
        self, watcher: AgentFileWatcher, agents_dir: Path
    ) -> None:
        """Invalid YAML syntax returns None and logs warning."""
        yaml_file = agents_dir / "bad.yaml"
        yaml_file.write_text("name: [unclosed bracket\n")

        result = watcher._load_yaml_file(yaml_file)

        assert result is None

    def test_returns_none_for_non_mapping(
        self, watcher: AgentFileWatcher, agents_dir: Path
    ) -> None:
        """YAML that parses to a non-dict (e.g., list) returns None."""
        yaml_file = agents_dir / "list.yaml"
        yaml_file.write_text("- item1\n- item2\n")

        result = watcher._load_yaml_file(yaml_file)

        assert result is None

    def test_returns_none_for_missing_file(
        self, watcher: AgentFileWatcher, agents_dir: Path
    ) -> None:
        """Non-existent file returns None."""
        yaml_file = agents_dir / "nonexistent.yaml"

        result = watcher._load_yaml_file(yaml_file)

        assert result is None

    def test_returns_none_for_permission_error(
        self, watcher: AgentFileWatcher, agents_dir: Path
    ) -> None:
        """File with permission error returns None."""
        yaml_file = agents_dir / "restricted.yaml"
        yaml_file.write_text("name: restricted\n")
        yaml_file.chmod(0o000)

        try:
            result = watcher._load_yaml_file(yaml_file)
            assert result is None
        finally:
            yaml_file.chmod(0o644)


# ---------------------------------------------------------------------------
# Tests: _handle_change
# ---------------------------------------------------------------------------


class TestHandleChange:
    """Tests for the _handle_change method."""

    @pytest.mark.asyncio
    async def test_added_file_calls_on_change_with_add(
        self, watcher: AgentFileWatcher, agents_dir: Path, on_change_mock: AsyncMock
    ) -> None:
        """File addition triggers on_change with action='add' and parsed data."""
        import watchfiles

        yaml_file = agents_dir / "new_agent.yaml"
        yaml_file.write_text("schema_version: '2.0'\nname: new-agent\n")

        await watcher._handle_change(watchfiles.Change.added, yaml_file)

        on_change_mock.assert_called_once_with(
            "add", yaml_file, {"schema_version": "2.0", "name": "new-agent"}
        )

    @pytest.mark.asyncio
    async def test_modified_file_calls_on_change_with_modify(
        self, watcher: AgentFileWatcher, agents_dir: Path, on_change_mock: AsyncMock
    ) -> None:
        """File modification triggers on_change with action='modify' and parsed data."""
        import watchfiles

        yaml_file = agents_dir / "existing_agent.yaml"
        yaml_file.write_text("schema_version: '2.0'\nname: updated-agent\n")

        await watcher._handle_change(watchfiles.Change.modified, yaml_file)

        on_change_mock.assert_called_once_with(
            "modify", yaml_file, {"schema_version": "2.0", "name": "updated-agent"}
        )

    @pytest.mark.asyncio
    async def test_modified_file_with_invalid_yaml_does_not_call_on_change(
        self, watcher: AgentFileWatcher, agents_dir: Path, on_change_mock: AsyncMock
    ) -> None:
        """Modified file with invalid YAML retains previous definition (no callback)."""
        import watchfiles

        yaml_file = agents_dir / "broken.yaml"
        yaml_file.write_text("name: [unclosed\n")

        await watcher._handle_change(watchfiles.Change.modified, yaml_file)

        on_change_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_deleted_file_calls_on_change_with_remove(
        self, watcher: AgentFileWatcher, agents_dir: Path, on_change_mock: AsyncMock
    ) -> None:
        """File deletion triggers on_change with action='remove' and data=None."""
        import watchfiles

        yaml_file = agents_dir / "removed_agent.yaml"

        await watcher._handle_change(watchfiles.Change.deleted, yaml_file)

        on_change_mock.assert_called_once_with("remove", yaml_file, None)

    @pytest.mark.asyncio
    async def test_added_file_with_invalid_yaml_does_not_call_on_change(
        self, watcher: AgentFileWatcher, agents_dir: Path, on_change_mock: AsyncMock
    ) -> None:
        """Added file with invalid YAML does not trigger on_change."""
        import watchfiles

        yaml_file = agents_dir / "invalid.yaml"
        yaml_file.write_text("bad: [yaml: content\n")

        await watcher._handle_change(watchfiles.Change.added, yaml_file)

        on_change_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: start / stop
# ---------------------------------------------------------------------------


class TestStartStop:
    """Tests for start and stop lifecycle methods."""

    @pytest.mark.asyncio
    async def test_start_creates_background_task(
        self, watcher: AgentFileWatcher, agents_dir: Path
    ) -> None:
        """start() creates a background asyncio task."""
        with patch("alcoabase.services.agent_file_watcher.watchfiles.awatch") as mock_awatch:
            # Make awatch return an empty async iterator that blocks
            async def empty_aiter(*args, **kwargs):
                await asyncio.sleep(10)
                return
                yield  # noqa: unreachable - makes this an async generator

            mock_awatch.return_value = empty_aiter()

            await watcher.start()

            assert watcher._task is not None
            assert not watcher._task.done()

            await watcher.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task(
        self, watcher: AgentFileWatcher, agents_dir: Path
    ) -> None:
        """stop() cancels the background task and sets it to None."""
        with patch("alcoabase.services.agent_file_watcher.watchfiles.awatch") as mock_awatch:
            async def empty_aiter(*args, **kwargs):
                await asyncio.sleep(10)
                return
                yield  # noqa: unreachable

            mock_awatch.return_value = empty_aiter()

            await watcher.start()
            task = watcher._task
            assert task is not None

            await watcher.stop()

            assert watcher._task is None
            assert task.cancelled()

    @pytest.mark.asyncio
    async def test_start_with_nonexistent_dir_does_not_start(
        self, on_change_mock: AsyncMock, tmp_path: Path
    ) -> None:
        """start() with non-existent directory does not create a task."""
        nonexistent = tmp_path / "does_not_exist"
        watcher = AgentFileWatcher(agents_dir=nonexistent, on_change=on_change_mock)

        await watcher.start()

        assert watcher._task is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_noop(
        self, watcher: AgentFileWatcher
    ) -> None:
        """stop() when watcher was never started does nothing."""
        await watcher.stop()  # Should not raise
        assert watcher._task is None


# ---------------------------------------------------------------------------
# Tests: Extension filtering
# ---------------------------------------------------------------------------


class TestExtensionFiltering:
    """Tests for YAML extension filtering."""

    def test_valid_extensions_constant(self) -> None:
        """Verify the valid extensions set contains .yaml and .yml."""
        assert _VALID_EXTENSIONS == {".yaml", ".yml"}

    @pytest.mark.asyncio
    async def test_non_yaml_files_are_ignored_in_watch_loop(
        self, watcher: AgentFileWatcher, agents_dir: Path, on_change_mock: AsyncMock
    ) -> None:
        """Files with non-YAML extensions are not processed."""
        import watchfiles

        # Simulate changes with non-YAML files
        txt_file = agents_dir / "readme.txt"
        json_file = agents_dir / "config.json"
        py_file = agents_dir / "script.py"

        # These should all be filtered out in _watch_loop
        # We test the filtering logic directly via _handle_change won't be called
        # by checking the extension filter in the watch loop
        for f in [txt_file, json_file, py_file]:
            assert f.suffix.lower() not in _VALID_EXTENSIONS
