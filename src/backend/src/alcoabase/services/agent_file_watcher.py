"""Agent File Watcher for hot-reload of YAML agent definitions.

Watches the configured agents directory for YAML file changes using the
`watchfiles` package (polling-based). Detects file additions, modifications,
and removals, validates YAML content, and invokes a callback to notify the
registry of changes.

References:
    - Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.9
    - Design doc Section 4: File Watcher
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine

import yaml
import watchfiles

logger = logging.getLogger(__name__)

# Valid YAML file extensions for agent definitions
_VALID_EXTENSIONS = {".yaml", ".yml"}

# Type alias for the on_change callback
OnChangeCallback = Callable[[str, Path, dict[str, Any] | None], Coroutine[Any, Any, None]]


class AgentFileWatcher:
    """Watches agents directory for YAML file changes.

    Uses `watchfiles.awatch` for async filesystem watching with polling.
    Only processes files with .yaml or .yml extensions. Invokes the
    on_change callback with the action type, file path, and parsed data.

    Attributes:
        _agents_dir: Path to the directory being watched.
        _on_change: Async callback invoked on file changes.
        _task: Background asyncio task running the watcher.
    """

    def __init__(self, agents_dir: Path, on_change: OnChangeCallback) -> None:
        """Initialize the AgentFileWatcher.

        Args:
            agents_dir: Path to the agents directory to watch for YAML changes.
            on_change: Async callback with signature:
                async def on_change(action: str, file_path: Path, data: dict | None) -> None
                - action: "add", "modify", or "remove"
                - file_path: Path to the changed file
                - data: Parsed YAML dict for add/modify, None for remove or on parse failure
        """
        self._agents_dir = agents_dir
        self._on_change = on_change
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the file watcher as a background asyncio task.

        Creates a background task that watches the agents directory for
        file changes. If the directory doesn't exist, logs a warning and
        does not start the watcher.
        """
        if not self._agents_dir.exists():
            logger.warning(
                "Agents directory does not exist, file watcher not started: %s",
                self._agents_dir,
            )
            return

        self._task = asyncio.create_task(self._watch_loop())
        logger.info("Agent file watcher started for: %s", self._agents_dir)

    async def stop(self) -> None:
        """Stop the file watcher by cancelling the background task.

        Gracefully cancels the watcher task and waits for it to finish.
        """
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Agent file watcher stopped.")

    async def _watch_loop(self) -> None:
        """Main watch loop using watchfiles.awatch.

        Iterates over file change events, filters to YAML extensions,
        and dispatches to the appropriate handler based on change type.
        Handles exceptions gracefully so the watcher doesn't crash on
        individual file errors.
        """
        try:
            async for changes in watchfiles.awatch(self._agents_dir):
                for change_type, file_path_str in changes:
                    file_path = Path(file_path_str)

                    # Only process .yaml and .yml files
                    if file_path.suffix.lower() not in _VALID_EXTENSIONS:
                        continue

                    try:
                        await self._handle_change(change_type, file_path)
                    except Exception as e:
                        logger.warning(
                            "Error processing file change for %s: %s",
                            file_path,
                            e,
                        )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("File watcher loop crashed: %s", e)

    async def _handle_change(
        self, change_type: watchfiles.Change, file_path: Path
    ) -> None:
        """Handle a single file change event.

        Dispatches to the appropriate action based on the change type:
        - Change.added: Parse and validate, call on_change with action="add"
        - Change.modified: Parse and validate, call on_change with action="modify"
        - Change.deleted: Call on_change with action="remove" and data=None

        Args:
            change_type: The type of filesystem change detected.
            file_path: Path to the changed file.
        """
        if change_type == watchfiles.Change.added:
            data = self._load_yaml_file(file_path)
            if data is not None:
                await self._on_change("add", file_path, data)

        elif change_type == watchfiles.Change.modified:
            data = self._load_yaml_file(file_path)
            if data is not None:
                await self._on_change("modify", file_path, data)
            else:
                # Validation failed — log already emitted by _load_yaml_file.
                # Retain previous valid definition by not calling on_change.
                logger.warning(
                    "Modified file failed validation, retaining previous definition: %s",
                    file_path,
                )

        elif change_type == watchfiles.Change.deleted:
            await self._on_change("remove", file_path, None)

    def _load_yaml_file(self, file_path: Path) -> dict[str, Any] | None:
        """Load and parse a YAML file, returning the parsed dict or None on failure.

        Handles YAML syntax errors, file permission errors, and non-mapping
        content gracefully by logging warnings and returning None.

        Args:
            file_path: Path to the YAML file to load.

        Returns:
            Parsed YAML dict if successful, None if parsing or reading fails.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except PermissionError as e:
            logger.warning(
                "Permission denied reading file %s: %s", file_path, e
            )
            return None
        except OSError as e:
            logger.warning(
                "Error reading file %s: %s", file_path, e
            )
            return None

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.warning(
                "Invalid YAML syntax in file %s: %s", file_path, e
            )
            return None

        if not isinstance(data, dict):
            logger.warning(
                "Expected YAML mapping in file %s, got %s",
                file_path,
                type(data).__name__,
            )
            return None

        return data
