"""Source registry for adapter discovery, validation, and health monitoring.

Manages the lifecycle of literature source adapters: discovering them from
a configured directory at startup, validating they implement the required
interface, and performing periodic health checks to classify their status.

References:
    - Requirements 1.1–1.8, 11.1–11.6
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from alcoabase.literature.adapters.base import AdapterMetadata, BaseSourceAdapter
from alcoabase.literature.schemas.search import AdapterCapabilities

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

REQUIRED_ADAPTER_METHODS: list[str] = [
    "search",
    "get_metadata",
    "health_check",
    "get_capabilities",
    "get_adapter_metadata",
]

HEALTH_HISTORY_MAX_LEN: int = 50
UNREACHABLE_FLAG_THRESHOLD_SECONDS: float = 1800.0  # 30 minutes

# Response time thresholds (seconds)
AVAILABLE_THRESHOLD: float = 5.0
DEGRADED_THRESHOLD: float = 15.0


# ─── Enums ────────────────────────────────────────────────────────────────────


class SourceStatus(StrEnum):
    """Health status classification for a source adapter."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class HealthCheckResult:
    """Record of a single health check execution.

    Attributes:
        timestamp: When the check was performed (UTC).
        response_time_seconds: Measured response time, or None on failure.
        status: Resulting status classification.
        error_message: Error details if the check failed.
    """

    timestamp: datetime
    response_time_seconds: float | None
    status: SourceStatus
    error_message: str | None = None


@dataclass
class AdapterRegistration:
    """Internal record for a registered adapter.

    Attributes:
        adapter: The adapter instance.
        metadata: Adapter metadata (name, version, etc.).
        capabilities: Declared adapter capabilities.
        status: Current health status.
        health_history: Last N health check results.
        first_unreachable_time: Timestamp when the adapter first became
            consecutively unreachable, or None if currently reachable.
        flagged_for_attention: Whether the adapter has been unreachable
            for more than 30 minutes.
    """

    adapter: BaseSourceAdapter
    metadata: AdapterMetadata
    capabilities: AdapterCapabilities
    status: SourceStatus = SourceStatus.AVAILABLE
    health_history: deque[HealthCheckResult] = field(
        default_factory=lambda: deque(maxlen=HEALTH_HISTORY_MAX_LEN)
    )
    first_unreachable_time: float | None = None
    flagged_for_attention: bool = False


# ─── Source Registry ──────────────────────────────────────────────────────────


class SourceRegistry:
    """Manages adapter lifecycle: discovery, validation, health monitoring.

    The registry scans a configured directory at startup for Python modules
    that expose classes inheriting from BaseSourceAdapter. Valid adapters are
    registered and made available for search dispatch. Periodic health checks
    classify each adapter's status.

    Attributes:
        _adapters: Dict mapping adapter name to AdapterRegistration.
    """

    def __init__(self) -> None:
        """Initialize an empty source registry."""
        self._adapters: dict[str, AdapterRegistration] = {}

    async def discover_adapters(self, adapter_dir: str) -> None:
        """Scan adapter directory and register valid adapters.

        Iterates over all .py files in the given directory (excluding
        __init__.py and base.py), imports each module, and looks for
        classes that inherit from BaseSourceAdapter. Valid adapters are
        instantiated and registered.

        If the directory does not exist or is not readable, logs an error
        and starts with an empty registry.

        Args:
            adapter_dir: Filesystem path to scan for adapter modules.
        """
        adapter_path = Path(adapter_dir)

        if not adapter_path.exists():
            logger.error(
                "Adapter directory does not exist: %s. "
                "Starting with empty adapter registry.",
                adapter_dir,
            )
            return

        if not adapter_path.is_dir():
            logger.error(
                "Adapter path is not a directory: %s. "
                "Starting with empty adapter registry.",
                adapter_dir,
            )
            return

        try:
            py_files = list(adapter_path.glob("*.py"))
        except OSError as e:
            logger.error(
                "Cannot read adapter directory %s: %s. "
                "Starting with empty adapter registry.",
                adapter_dir,
                e,
            )
            return

        skip_files = {"__init__.py", "base.py"}
        module_files = [f for f in py_files if f.name not in skip_files]

        if not module_files:
            logger.info(
                "No adapter modules found in %s. "
                "Starting with empty adapter registry.",
                adapter_dir,
            )
            return

        for module_file in module_files:
            self._load_adapter_module(module_file)

        registered_count = len(self._adapters)
        logger.info(
            "Adapter discovery complete: %d adapter(s) registered from %s.",
            registered_count,
            adapter_dir,
        )

    def _load_adapter_module(self, module_file: Path) -> None:
        """Load a single module file and register any valid adapter classes.

        Args:
            module_file: Path to the Python module file.
        """
        module_name = f"literature_adapter_{module_file.stem}"

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if spec is None or spec.loader is None:
                logger.warning(
                    "Cannot create module spec for %s. Skipping.",
                    module_file,
                )
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except (ImportError, OSError, SyntaxError, Exception) as e:
            logger.warning(
                "Failed to import adapter module %s: %s. Skipping.",
                module_file.name,
                e,
            )
            return

        # Find classes that inherit from BaseSourceAdapter
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj is not BaseSourceAdapter
                and issubclass(obj, BaseSourceAdapter)
                and not inspect.isabstract(obj)
            ):
                self._try_register_adapter(obj, module_file.name)

    def _try_register_adapter(
        self, adapter_class: type, source_file: str
    ) -> None:
        """Attempt to instantiate and register an adapter class.

        Args:
            adapter_class: The adapter class to instantiate.
            source_file: Filename of the module (for logging).
        """
        try:
            adapter_instance = adapter_class()
        except Exception as e:
            logger.warning(
                "Failed to instantiate adapter class %s from %s: %s. Skipping.",
                adapter_class.__name__,
                source_file,
                e,
            )
            return

        is_valid, missing_methods = self.validate_adapter(adapter_instance)
        if not is_valid:
            logger.warning(
                "Adapter %s from %s failed validation — "
                "missing methods: %s. Excluded from registry.",
                adapter_class.__name__,
                source_file,
                ", ".join(missing_methods),
            )
            return

        try:
            metadata = adapter_instance.get_adapter_metadata()
            capabilities = adapter_instance.get_capabilities()
        except Exception as e:
            logger.warning(
                "Adapter %s from %s raised error during metadata retrieval: %s. "
                "Excluded from registry.",
                adapter_class.__name__,
                source_file,
                e,
            )
            return

        if metadata.name in self._adapters:
            logger.warning(
                "Duplicate adapter name '%s' from %s. "
                "Keeping previously registered adapter.",
                metadata.name,
                source_file,
            )
            return

        self._adapters[metadata.name] = AdapterRegistration(
            adapter=adapter_instance,
            metadata=metadata,
            capabilities=capabilities,
        )
        logger.info(
            "Registered adapter: %s v%s (%s) from %s.",
            metadata.name,
            metadata.version,
            metadata.display_name,
            source_file,
        )

    def validate_adapter(self, adapter: object) -> tuple[bool, list[str]]:
        """Validate that an object implements the full adapter interface.

        Checks for the presence of all required methods via hasattr.

        Args:
            adapter: Candidate adapter instance.

        Returns:
            Tuple of (is_valid, list_of_missing_methods). If is_valid is True,
            the missing list is empty.
        """
        missing: list[str] = [
            method
            for method in REQUIRED_ADAPTER_METHODS
            if not hasattr(adapter, method) or not callable(getattr(adapter, method))
        ]
        return (len(missing) == 0, missing)

    def get_adapter(self, name: str) -> BaseSourceAdapter | None:
        """Retrieve a registered adapter by name.

        Args:
            name: Adapter identifier.

        Returns:
            Adapter instance or None if not registered.
        """
        registration = self._adapters.get(name)
        if registration is None:
            return None
        return registration.adapter

    def list_adapters(self) -> list[dict[str, Any]]:
        """List all registered adapters with metadata and health status.

        Returns:
            List of dicts containing name, version, display_name,
            requires_api_key, capabilities, status, last_health_check,
            and flagged_for_attention.
        """
        result: list[dict[str, Any]] = []
        for name, reg in self._adapters.items():
            last_check: datetime | None = None
            if reg.health_history:
                last_check = reg.health_history[-1].timestamp

            result.append({
                "name": name,
                "version": reg.metadata.version,
                "display_name": reg.metadata.display_name,
                "requires_api_key": reg.metadata.requires_api_key,
                "capabilities": reg.capabilities,
                "status": reg.status,
                "last_health_check": last_check,
                "flagged_for_attention": reg.flagged_for_attention,
            })
        return result

    async def run_health_check(self, adapter_name: str) -> SourceStatus:
        """Execute health check for a specific adapter.

        Measures the response time of the adapter's health_check method
        and classifies the result. Stores the result in health history
        and updates the adapter's status.

        Args:
            adapter_name: Name of the adapter to check.

        Returns:
            Updated SourceStatus based on response time.

        Raises:
            KeyError: If adapter_name is not registered.
        """
        registration = self._adapters.get(adapter_name)
        if registration is None:
            msg = f"Adapter '{adapter_name}' is not registered."
            raise KeyError(msg)

        now = datetime.now(tz=timezone.utc)
        start = time.perf_counter()

        try:
            response_time = await registration.adapter.health_check()
            elapsed = time.perf_counter() - start
            # Use the adapter-reported response time if available,
            # otherwise fall back to measured elapsed time
            actual_time = response_time if response_time is not None else elapsed
            status = self.classify_response_time(actual_time)

            check_result = HealthCheckResult(
                timestamp=now,
                response_time_seconds=actual_time,
                status=status,
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            status = SourceStatus.UNREACHABLE

            check_result = HealthCheckResult(
                timestamp=now,
                response_time_seconds=elapsed if elapsed < DEGRADED_THRESHOLD else None,
                status=status,
                error_message=str(e),
            )
            logger.warning(
                "Health check failed for adapter '%s': %s",
                adapter_name,
                e,
            )

        registration.health_history.append(check_result)
        registration.status = status

        # Track consecutive unreachable time for flagging
        self._update_unreachable_tracking(registration, status)

        return status

    def _update_unreachable_tracking(
        self, registration: AdapterRegistration, status: SourceStatus
    ) -> None:
        """Update unreachable tracking state for flagging logic.

        If the adapter is unreachable, track how long it has been
        consecutively unreachable. Flag it for admin attention if
        unreachable for more than 30 minutes.

        Args:
            registration: The adapter registration to update.
            status: The current health status.
        """
        if status == SourceStatus.UNREACHABLE:
            if registration.first_unreachable_time is None:
                registration.first_unreachable_time = time.time()
            else:
                elapsed = time.time() - registration.first_unreachable_time
                if elapsed >= UNREACHABLE_FLAG_THRESHOLD_SECONDS:
                    registration.flagged_for_attention = True
                    logger.warning(
                        "Adapter '%s' has been unreachable for %.0f seconds "
                        "(> 30 minutes). Flagged for administrator attention.",
                        registration.metadata.name,
                        elapsed,
                    )
        else:
            # Reset tracking when adapter becomes reachable
            registration.first_unreachable_time = None
            registration.flagged_for_attention = False

    def classify_response_time(self, response_time_seconds: float) -> SourceStatus:
        """Classify a response time into a SourceStatus.

        Args:
            response_time_seconds: Measured response time in seconds.

        Returns:
            AVAILABLE if < 5s, DEGRADED if 5–15s, UNREACHABLE if >= 15s.
        """
        if response_time_seconds < AVAILABLE_THRESHOLD:
            return SourceStatus.AVAILABLE
        elif response_time_seconds < DEGRADED_THRESHOLD:
            return SourceStatus.DEGRADED
        else:
            return SourceStatus.UNREACHABLE

    def get_status(self, adapter_name: str) -> SourceStatus | None:
        """Get the current status of a registered adapter.

        Args:
            adapter_name: Name of the adapter.

        Returns:
            Current SourceStatus, or None if adapter not registered.
        """
        registration = self._adapters.get(adapter_name)
        if registration is None:
            return None
        return registration.status

    def get_health_history(
        self, adapter_name: str
    ) -> list[HealthCheckResult] | None:
        """Get the health check history for an adapter.

        Args:
            adapter_name: Name of the adapter.

        Returns:
            List of HealthCheckResult entries (up to 50), or None if
            the adapter is not registered.
        """
        registration = self._adapters.get(adapter_name)
        if registration is None:
            return None
        return list(registration.health_history)

    @property
    def adapter_count(self) -> int:
        """Return the number of currently registered adapters."""
        return len(self._adapters)
